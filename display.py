#
#     This file is part of Node Preview Reborn, a fork of NodePreview.
#     Copyright (C) 2021 Simon Wendsche
#     Copyright (C) 2026 Guillaume Henrion aka GYOMH (fork/modifications)
#
#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with this program.  If not, see <http://www.gnu.org/licenses/>.

import bpy
from bpy.app.handlers import persistent
from bpy.types import SpaceImageEditor, SpaceNodeEditor, AddonPreferences
import blf
import gpu
from gpu_extras.batch import batch_for_shader

from time import time, sleep
from math import sqrt
import os
join_paths = os.path.join
import platform
import tempfile
import shutil
import subprocess
import threading
from multiprocessing import current_process
from multiprocessing.connection import Listener, Connection
from typing import Optional
import base64
import re
import queue

current_dir = os.path.dirname(os.path.realpath(__file__))


from . import (addon_name, THUMB_CHANNEL_COUNT, SUPPORTED_NODE_TREE, force_node_editor_draw,
               needs_linking, UnsupportedNodeException, BACKGROUND_PATTERNS, get_blend_abspath,
               get_image_linking_info, needs_sphere_preview)
from . import messages, node_converter, scene_converter
from .node_converter import node_to_script, make_node_key


images_failed_to_link_lock = threading.Lock()
images_failed_to_link = set()


class WatcherThread(threading.Thread):
    def __init__(self,  *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def stopped(self):
        return self._stop_event.is_set()

    def run(self):
        while not self.stopped():
            if connection.poll(timeout=0.05):
                msg = connection.recv()
                tag, data = msg

                if tag == messages.BACKGROUND_PROCESS_READY:
                    global background_process_ready
                    background_process_ready = True
                    # Force one refresh to render all nodes that are currently visible
                    force_node_editor_draw()
                elif tag == messages.JOB_DONE:
                    node_key, result_array, thumb_resolution, job_timestamp, error_message, full_error_log = data
                    
                    if full_error_log:
                        addon_print(full_error_log)

                    thumbnails[node_key] = Thumbnail(result_array, thumb_resolution, thumb_resolution, THUMB_CHANNEL_COUNT, error_message)

                    try:
                        last_timestamp = cached_nodes[node_key][1]
                        if job_timestamp < last_timestamp:
                            # Force re-sending the job if the last job didn't go through
                            del cached_nodes[node_key]
                            # 再送は変換処理の中で行われるため、スキップされないよう更新を要求する
                            request_update()
                    except KeyError:
                        pass

                    force_node_editor_draw()
                elif tag == messages.IMAGES_FAILED_TO_LINK:
                    with images_failed_to_link_lock:
                        images_failed_to_link.update(data)


handle = None  # Draw handler
thumbnails = {}  # filepath : Thumbnail
texture_ids_to_delete = queue.Queue()
cached_nodes = {}  # node_key : hash(node_script), timestamp
# Used to decide wether to update only the first or second part of the nodes in a tree in the draw handler
update_first_part = {}  # node_tree : Bool
# Output directory where rendered thumbnails are saved by our Blender sub-process
temp_dir = join_paths(tempfile.gettempdir(), f"BlenderNodePreview_{os.getpid()}")
TEMP_DIR_REGEX_PATTERN = r"BlenderNodePreview_[0-9]+"

background_process_ready = False
background_process: Optional[subprocess.Popen] = None
listener: Optional[Listener] = None
connection: Optional[Connection] = None
watcher_thread: Optional[WatcherThread] = None

# 変更の無い再描画（パン・ズーム・マウス移動）で重い変換処理を丸ごと省くための状態
update_generation = 0  # ノード等に変更が入るたびに増える世代番号
processed_state = {}  # node_tree : (update_generation, signature, 処理済みパート数)
group_script_cache = {}  # frozenset(ノードグループ名) : node_groups_to_script の結果
# この型の ID が更新されたときだけサムネイルが変わり得る
WATCHED_ID_TYPES = (bpy.types.Material, bpy.types.World, bpy.types.Light, bpy.types.NodeTree, bpy.types.Image)


def request_update():
    """
    ### request_update
    次の再描画でサムネイル用スクリプトの再変換を行わせる（別スレッドから呼んでも良い）
    """
    global update_generation
    update_generation += 1


def invalidate_caches():
    """
    ### invalidate_caches
    ノードグループ変換のキャッシュを破棄し、再変換を要求する
    """
    group_script_cache.clear()
    request_update()


def get_group_script(node_tree_hierarchy):
    """
    ### get_group_script
    編集中の階層から参照されるノードグループだけを変換し、結果をキャッシュする

    @param node_tree_hierarchy - 編集中のノードツリー階層
    @returns node_groups_to_script の戻り値
    """
    used_groups = node_converter.collect_used_node_groups(node_tree_hierarchy)
    cache_key = frozenset(group.name_full for group in used_groups)
    try:
        return group_script_cache[cache_key]
    except KeyError:
        result = node_converter.node_groups_to_script(used_groups)
        group_script_cache[cache_key] = result
        return result


def make_update_signature(context, node_tree, node_tree_hierarchy, node_tree_owner, preferences):
    """
    ### make_update_signature
    depsgraph の通知が来ない変更（設定・エンジン・ノード毎のプレビュー設定など）を検出するための値を作る

    @returns 前回と比較するためのタプル
    """
    node_settings = []
    for node in node_tree.nodes:
        props = getattr(node, "node_preview", None)
        if props is None:
            continue
        node_settings.append((node.name, props.enabled, props.enabled_modified, props.ignore_scale,
                              props.auto_choose_output, props.output_index, props.preview_object,
                              props.force_update_counter))

    # Group Input の解決に親ツリーのアクティブノード（グループのインスタンス）が使われるため含める
    parent_active_nodes = tuple(tree.nodes.active.name if tree.nodes.active else None
                                for tree in node_tree_hierarchy[:-1])

    return (
        node_tree_owner.as_pointer() if node_tree_owner else None,
        tuple(tree.as_pointer() for tree in node_tree_hierarchy),
        parent_active_nodes,
        context.scene.render.engine,
        preferences.previews_enabled_by_default,
        preferences.thumb_resolution,
        preferences.background_pattern,
        tuple(preferences.background_color_1),
        tuple(preferences.background_color_2),
        tuple(node_settings),
    )


@persistent
def depsgraph_update_post(scene, depsgraph):
    for update in depsgraph.updates:
        if isinstance(update.id, WATCHED_ID_TYPES):
            invalidate_caches()
            return


UNSUPPORTED_NODES = {
    "NodeReroute",
    "ShaderNodeHoldout",  # Makes no sense to render a black thumbnail every time
    "ShaderNodeAttribute",
    "NodeGroupInput",
    "NodeGroupOutput",
}
EEVEE_ONLY_NODES = {
    "ShaderNodeShaderToRGB",
    "ShaderNodeEeveeSpecular",
}
UNSUPPORTED_NODES_CYCLES = UNSUPPORTED_NODES | EEVEE_ONLY_NODES
UNSUPPORTED_NODES_EEVEE = UNSUPPORTED_NODES
NODES_NEEDING_MORE_SAMPLES = {
    "ShaderNodeSubsurfaceScattering",
    "ShaderNodeVolumeScatter",
    "ShaderNodeVolumePrincipled",
    "ShaderNodeBevel",
    "ShaderNodeMixShader",
    "ShaderNodeAddShader",
}
# Above these thresholds, procedural textures become too fine-grained for the preview (at default texture mapping)
SCALE_HELP_THRESHOLDS = {
    "ShaderNodeTexBrick": 11,
    "ShaderNodeTexChecker": 35,
    "ShaderNodeTexMagic": 16,
    "ShaderNodeTexMusgrave": 50,
    "ShaderNodeTexNoise": 40,
    "ShaderNodeTexWave": 11,
    "ShaderNodeTexVoronoi": 30,
}
NULL = 0


def addon_print(*args, **kwargs):
    print("[NodePreview]", *args, **kwargs)


def create_thumbnail_shader():
    # GPUShaderCreateInfo is the cross-backend (OpenGL/Vulkan/Metal) shader API.
    # ModelViewProjectionMatrix is a reserved/builtin uniform name: Blender fills it in
    # automatically on batch.draw(), no manual uniform_float() call needed.
    vert_out = gpu.types.GPUStageInterfaceInfo("node_preview_thumbnail_interface")
    vert_out.smooth('VEC2', "texCoord_interp")

    shader_info = gpu.types.GPUShaderCreateInfo()
    shader_info.push_constant('MAT4', "ModelViewProjectionMatrix")
    shader_info.push_constant('BOOL', "gamma_correct")
    shader_info.sampler(0, 'FLOAT_2D', "image")
    shader_info.vertex_in(0, 'VEC2', "pos")
    shader_info.vertex_in(1, 'VEC2', "texCoord")
    shader_info.vertex_out(vert_out)
    shader_info.fragment_out(0, 'VEC4', "fragColor")

    with open(join_paths(current_dir, "shaders", "thumbnail_vert.glsl")) as vert:
        shader_info.vertex_source(vert.read())
    with open(join_paths(current_dir, "shaders", "thumbnail_frag.glsl")) as frag:
        shader_info.fragment_source(frag.read())

    return gpu.shader.create_from_info(shader_info)


use_fallback_shader = False


def using_fallback_shader():
    return use_fallback_shader

if not bpy.app.background:
    try:
        shader = create_thumbnail_shader()
    except Exception as error:
        addon_print("Could not compile shaders:", str(error))
        use_fallback_shader = True
        shader = gpu.shader.from_builtin("IMAGE")


class Thumbnail:
    def __init__(self, pixels, width, height, channel_count, text):
        self.pixels = pixels
        # The thumbnail is created in a thread, but the texture has to be initialized
        # in the main thread, so we can't do it here yet. init_texture() must be called
        # from the main thread.
        self.texture = None

        self.width = width
        self.height = height
        self.channel_count = channel_count
        self.text = text

    def init_texture(self):
        if using_fallback_shader():
            # Normally the shader would do the gamma correction, but the builtin fallback shader doesn't do this.
            # Note: this operation also affects the alpha channel, which is not correct, but since
            # the alpha channel is currently not used, it doesn't matter.
            import numpy as np
            self.pixels = np.power(self.pixels, 2.2)

        buffer = gpu.types.Buffer('FLOAT', self.width * self.height * self.channel_count, self.pixels)

        # TODO is this actually (height, width)? And is the format correct, why not 32F?
        # (Code from https://docs.blender.org/api/current/bpy.types.RenderEngine.html)
        self.texture = gpu.types.GPUTexture((self.width, self.height), format='RGBA16F', data=buffer)

        # No longer needed, delete to save memory
        self.pixels = None

    def draw(self, bottom_left, bottom_right, top_right, top_left, scaled_zoom, text_x):
        shader.bind()
        shader.uniform_sampler("image", self.texture)

        try:
            shader.uniform_int("gamma_correct", bpy.app.version >= (2, 91, 0))
        except ValueError:
            # There's no gamma_correct uniform when using the builtin "IMAGE" shader on the Metal backend
            pass

        batch = batch_for_shader(
            shader,
            'TRIS',
            {
                "pos": (bottom_left, bottom_right, top_right, top_left),
                "texCoord": ((0, 0), (1, 0), (1, 1), (0, 1)),
            },
            indices=((0, 1, 2), (0, 2, 3)),
        )
        batch.draw(shader)

        if self.text:
            position = (text_x, top_left[1] + 3 * scaled_zoom)
            draw_text(self.text, position, 10, scaled_zoom)


def draw_text(text, position, font_size, scaled_zoom):
    # Somewhere in the blf functions the blend mode is overwritten,
    # so we need to save it before and restore it after we use blf
    old_blend_mode = gpu.state.blend_get()

    FONT_ID = 0

    x, y = position
    for line in reversed(text.split("\n")):
        blf.position(FONT_ID, x, y, 0)

        if bpy.app.version < (4, 0, 0):
            # 72 is the DPI
            blf.size(FONT_ID, round(font_size * scaled_zoom), 72)
        else:
            blf.size(FONT_ID, round(font_size * scaled_zoom))

        blf.draw(FONT_ID, line)
        y += font_size * scaled_zoom

    gpu.state.blend_set(old_blend_mode)
    return y


def view_to_region_scaled(context, x, y, clip=True):
    ui_scale = context.preferences.system.ui_scale
    return context.region.view2d.view_to_region(x * ui_scale, y * ui_scale, clip=clip)


def get_region_zoom(context):
    test_length = 1000
    x0, y0 = context.region.view2d.view_to_region(0, 0, clip=False)
    x1, y1 = context.region.view2d.view_to_region(test_length, test_length, clip=False)
    xl = x1 - x0
    yl = y1 - y0
    return sqrt(xl**2 + yl**2) / test_length


def needs_more_than_1_sample(node, use_sphere_preview):
    bl_idname = node.bl_idname

    if bl_idname == "ShaderNodeGroup" and node.node_tree:
        for subnode in node.node_tree.nodes:
            if needs_more_than_1_sample(subnode, use_sphere_preview):
                return True

    if bl_idname == "ShaderNodeBsdfTransparent":
        return False

    if bl_idname == "ShaderNodeBsdfDiffuse" and node.inputs["Normal"].is_linked:
        return True

    # In sphere mode, an area light prevents these from being noise-free at 1 sample
    if not use_sphere_preview and bl_idname in {"ShaderNodeBsdfDiffuse", "ShaderNodeBsdfGlossy"}:
        roughness_input = node.inputs["Roughness"]
        # At roughness = 0, there's no noise with 1 sample
        return roughness_input.is_linked or roughness_input.default_value > 0

    return (bl_idname.startswith("ShaderNodeBsdf")
            or bl_idname in NODES_NEEDING_MORE_SAMPLES)


def is_node_supported(node, engine):
    if len(node.outputs) == 0:
        return False

    if engine == "BLENDER_EEVEE":
        return node.bl_idname not in UNSUPPORTED_NODES_EEVEE
    else:
        return node.bl_idname not in UNSUPPORTED_NODES_CYCLES


def to_valid_filename(name):
    return base64.urlsafe_b64encode(name.encode("UTF-8")).decode("UTF-8")


def handler():
    from time import perf_counter
    __start = perf_counter()

    if not background_process_ready:
        return

    context = bpy.context

    if context.space_data.tree_type != SUPPORTED_NODE_TREE:
        return

    if not context.space_data.path:
        return

    # Path contains a chain of nested node trees, the last one is the one that's currently visible
    node_tree_hierarchy = [elem.node_tree for elem in context.space_data.path]
    node_tree = node_tree_hierarchy[-1]
    if not node_tree:
        return

    # TODO cleanup
    # # TODO handle nested groups
    # if len(path) > 1:
    #     path_index = -1 # TODO
    #     node_group_instance = path[path_index - 1].node_tree.nodes.active
    #
    #     # if node_tree.name == "NodeGroup":
    #     #     breakpoint()
    # else:
    #     node_group_instance = None

    if not node_tree.node_preview.enabled:
        return

    preferences = context.preferences.addons[addon_name].preferences
    enabled_by_default = preferences.previews_enabled_by_default
    all_previews_disabled = True
    for node in node_tree.nodes:
        try:
            enabled = node.node_preview.enabled if node.node_preview.enabled_modified else enabled_by_default
            if enabled:
                all_previews_disabled = False
                break
        except AttributeError:  # Some special nodes might not have the node_preview attribute
            pass
    if all_previews_disabled:
        return

    if not node_converter.node_attributes_cache:
        node_converter.build_node_attributes_cache()

    area = context.area
    ui_scale = context.preferences.system.ui_scale
    zoom = get_region_zoom(context)
    scaled_zoom = zoom * ui_scale
    thumb_scale = preferences.thumb_scale / 100
    thumb_z_offset = preferences.thumb_z_offset
    thumb_resolution = preferences.thumb_resolution

    using_checker_pattern = preferences.background_pattern == BACKGROUND_PATTERNS.CHECKER
    background_col_1 = list(preferences.background_color_1) + [1]
    background_col_2 = list(preferences.background_color_2) + [1] if using_checker_pattern else background_col_1
    background_colors = background_col_1, background_col_2

    # Sort nodes
    # Build node dependency mapping
    node_deps = {}
    for link in node_tree.links:
        try:
            node_deps[link.from_node].append(link.to_node)
        except KeyError:
            node_deps[link.from_node] = [link.to_node]

    def get_dependent_nodes(node):
        try:
            return node_deps[node]
        except KeyError:
            return []

    sorted_nodes = node_converter.sort_topologically(node_tree.nodes, get_dependent_nodes)

    old_blend_mode = gpu.state.blend_get()
    gpu.state.blend_set("ALPHA")

    # node_tree_owner is the material, world etc. that contains the node_tree
    node_tree_owner = context.space_data.id

    # 50 ノード以上のツリーは前半/後半を交互に処理するため、2 回処理して初めて全ノードが最新になる
    parts_needed = 1 if len(sorted_nodes) < 50 else 2
    signature = make_update_signature(context, node_tree, node_tree_hierarchy, node_tree_owner, preferences)
    generation = update_generation
    last_state = processed_state.get(node_tree)
    state_matches = last_state is not None and last_state[0] == generation and last_state[1] == signature
    needs_conversion = not (state_matches and last_state[2] >= parts_needed)

    if needs_conversion:
        group_script, group_images_to_load, group_images_to_link, group_hashes = get_group_script(node_tree_hierarchy)

    # socket.links is a very expensive property to access, so we cache the link types we are interested in most in this dict
    incoming_links = {link.to_socket: link for link in node_tree.links}
    # node.name: node_creation_script, images_to_load, images_to_link
    node_scripts_cache = {}
    jobs_to_send = []

    # Note: Can't store this as a property on the node tree, because setting is sometimes not possible in a draw handler
    update_first_part[node_tree] = not update_first_part.get(node_tree, False)
    # The nodes near the end of the list take the most time to convert, so we divide the list unevenly to get balanced execution times
    divider = int(len(sorted_nodes) * 0.82)
    if len(sorted_nodes) < 50:
        start = 0
        end = len(sorted_nodes)
    elif update_first_part[node_tree]:
        start = 0
        end = divider
        # context.region.tag_redraw()  # TODO needed?
    else:
        start = divider
        end = len(sorted_nodes)

    #####################
    # Update Thumbnails #
    #####################
    if needs_conversion and (not context.screen.is_animation_playing or preferences.update_during_animation_playback):
        processed_state[node_tree] = (generation, signature, last_state[2] + 1 if state_matches else 1)

        for node in sorted_nodes[start:end]:
            if not is_node_supported(node, context.scene.render.engine):
                continue

            try:
                # Even if the preview is disabled, we need to convert the script so dependent nodes can retrieve it from the node scripts cache
                node_script, images_to_load, images_to_link = node_to_script(node, node_tree_owner, node_scripts_cache,
                                                                             group_hashes, incoming_links, background_colors,
                                                                             node_tree_hierarchy, context.scene.render.engine)
            except UnsupportedNodeException:
                continue

            enabled = node.node_preview.enabled if node.node_preview.enabled_modified else enabled_by_default
            if not enabled:
                continue

            use_sphere_preview = needs_sphere_preview(node)
            needs_more_samples = needs_more_than_1_sample(node, use_sphere_preview)

            scene_script = scene_converter.scene_to_script(context, needs_more_samples, use_sphere_preview, thumb_resolution)
            script_hash = hash(node_script + scene_script)
            node_key = make_node_key(node, node_tree, node_tree_owner)

            if node_key not in cached_nodes or cached_nodes[node_key][0] != script_hash:
                timestamp = time()
                thumb_path = join_paths(temp_dir, to_valid_filename(node_key) + ".png")

                if getattr(node, "image", None):
                    # This info is used to show accurate error messages when images failed to link or load
                    image = node.image
                    image_needs_linking = needs_linking(image)
                    name, library_path = get_image_linking_info(image)
                    image_info = (
                        name,
                        library_path if image_needs_linking else None,
                        image_needs_linking,
                        bpy.path.abspath(image.filepath, library=image.library),
                    )
                else:
                    image_info = None

                job = (
                    node_key,
                    "\n".join((scene_script, group_script, node_script)),
                    images_to_load | group_images_to_load,
                    images_to_link | group_images_to_link,
                    image_info,
                    get_blend_abspath(),
                    thumb_path,
                    thumb_resolution,
                    timestamp,
                )
                jobs_to_send.append(job)
                cached_nodes[node_key] = script_hash, timestamp

                # For debugging complex scripts
                # if False and node.name == "Math":
                #     test_file_path = join_paths(current_dir, "data", "script.py")
                #     with open(test_file_path, "w") as f:
                #         f.write("\n".join(("import bpy; import mathutils; ", scene_script, group_script, node_script)))
                #
                #     process_args = [
                #         bpy.app.binary_path,
                #         "--factory-startup",
                #         join_paths(current_dir, "data", "previewscene.blend"),
                #         "--python", test_file_path,
                #     ]
                #     subprocess.Popen(process_args)

    #####################
    #  Draw Thumbnails  #
    #####################
    for node in sorted_nodes:
        if not is_node_supported(node, context.scene.render.engine):
            continue

        enabled = node.node_preview.enabled if node.node_preview.enabled_modified else enabled_by_default
        if not enabled:
            continue

        location = node.location.copy()
        n = node
        while n.parent:
            # Take (possibly nested) frames into account
            location += n.parent.location
            n = n.parent

        topleft_x, topleft_y = view_to_region_scaled(context, *location, clip=False)
        topright_x, _ = view_to_region_scaled(context, location[0] + node.width, 0, clip=False)
        node_width = (topright_x - topleft_x)

        BASE_WIDTH = 150
        size = BASE_WIDTH * scaled_zoom * thumb_scale
        offset_x = (node_width - size) / 2 + 1  # For some reason we are one pixel too far to the left, thus +1
        offset_y = thumb_z_offset * scaled_zoom * thumb_scale  # Vertical offset from the node

        bottom_left = (topleft_x + offset_x, topleft_y + offset_y)
        bottom_right = (topleft_x + offset_x + size, topleft_y + offset_y)
        top_right = (topleft_x + offset_x + size, topleft_y + offset_y + size)
        top_left = (topleft_x + offset_x, topleft_y + offset_y + size)

        # Don't draw the texture when it is out of bounds
        if bottom_right[0] < 0 or bottom_left[0] > area.width or top_left[1] < 0 or bottom_left[1] > area.height:
            continue

        try:
            node_key = make_node_key(node, node_tree, node_tree_owner)
            thumb = thumbnails[node_key]
        except KeyError:
            # No thumbnail was created for this node, meaning it should not
            # have one (e.g. because it's a material output node)
            continue

        if thumb.texture is None and thumb.pixels is None:
            # Texture not initialized, but no pixels to use. This means the background process could not render the thumbnail
            continue

        if thumb.texture is None:
            thumb.init_texture()

        text_x = topleft_x
        text_y = top_left[1] + 3 * scaled_zoom
        text_size = 10

        thumb.draw(bottom_left, bottom_right, top_right, top_left, scaled_zoom, text_x)

        if not node.node_preview.auto_choose_output:
            output = node.outputs[node.node_preview.output_index].name
            text_y = draw_text(f"Output: {output}", (text_x, text_y), text_size, scaled_zoom)
            text_y += text_size * scaled_zoom * 0.5  # A bit of spacing in case of more text after

        if preferences.show_help and "Scale" in node.inputs:
            try:
                threshold = SCALE_HELP_THRESHOLDS[node.bl_idname]
                if node.inputs["Scale"].is_linked or abs(node.inputs["Scale"].default_value) > threshold:
                    if node.node_preview.ignore_scale:
                        text_y = draw_text("Scale ignored", (text_x, text_y), text_size, scaled_zoom)
                    else:
                        text_y = draw_text("Scale can be ignored\nwith Ctrl+Shift+i", (text_x, text_y), text_size, scaled_zoom)
            except KeyError:
                # Node doesn't have a known scale threshold, don't show the help message
                pass

    gpu.state.blend_set(old_blend_mode)
    gpu.shader.unbind()

    # Send jobs in reversed order so the leftmost node (which was edited) is rendered first for fast feedback
    for job in reversed(jobs_to_send):
        connection.send((messages.NEW_JOB, job))

    # elapsed = perf_counter() - __start
    # print("draw handler took %.3f s (%d fps)" % (elapsed, round(1 / elapsed)))
    # draw_text("Node Preview Frametime: %.3f s (%d FPS)" % (elapsed, round(1 / elapsed)), (30, 30), 15, 1)


def free():
    cached_nodes.clear()
    update_first_part.clear()
    thumbnails.clear()
    processed_state.clear()
    invalidate_caches()


def stop_threads_and_process():
    global watcher_thread, connection, listener, background_process, background_process_ready
    background_process_ready = False

    if watcher_thread:
        watcher_thread.stop()
        watcher_thread.join(timeout=0.2)
        watcher_thread = None

    if connection:
        connection.send((messages.STOP, None))
        connection.close()
        connection = None

    if listener:
        listener.close()
        listener = None

    if background_process:
        try:
            background_process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            background_process.kill()
            background_process.communicate()
            addon_print("Background Process was killed after timeout.")

        background_process = None


def clean_temp_dir():
    os_temp_dir = os.path.dirname(temp_dir)
    addon_temp_dirs = [join_paths(os_temp_dir, name) for name in os.listdir(os_temp_dir)
                       if re.match(TEMP_DIR_REGEX_PATTERN, name)]

    for path in addon_temp_dirs:
        try:
            # Only delete old temp dirs. Recent ones might still be in use by another Blender process.
            seconds_since_last_modification = time() - os.path.getmtime(path)
            if seconds_since_last_modification > 60 * 60 * 24:
                shutil.rmtree(path)
        except Exception as error:
            addon_print("Could not delete temp dir:", path)
            addon_print(error)


def update_blend_path():
    def notify_new_blend_loaded():
        while not background_process_ready:
            sleep(1/60)
        connection.send((messages.NEW_BLEND_ABSPATH, bpy.path.abspath(bpy.data.filepath)))

    if background_process_ready:
        notify_new_blend_loaded()
    else:
        # Wait until the process is ready to receive the message, because it must
        # arrive, otherwise all future jobs will be ignored
        notifier = threading.Thread(target=notify_new_blend_loaded)
        notifier.setDaemon(True)
        notifier.start()


@persistent
def load_pre(_=None):
    free()
    # Delete images in the background process to free up RAM
    if background_process_ready:
        connection.send((messages.FREE_RESSOURCES, None))


@persistent
def load_post(arg1, arg2):
    update_blend_path()


@persistent
def save_post(arg1, arg2):
    update_blend_path()

    with images_failed_to_link_lock:
        if images_failed_to_link:
            for mat in bpy.data.materials:
                if not mat.node_tree:
                    continue
                for node in mat.node_tree.nodes:
                    if getattr(node, "image", None) and node.image.name in images_failed_to_link:
                        node.node_preview.force_update()

            for node_tree in bpy.data.node_groups:
                if node_tree.bl_idname not in SUPPORTED_NODE_TREE:
                    continue
                for node in node_tree.nodes:
                    if getattr(node, "image", None) and node.image.name in images_failed_to_link:
                        node.node_preview.force_update()

        force_node_editor_draw()
        images_failed_to_link.clear()


def exit_callback():
    stop_threads_and_process()
    free()
    clean_temp_dir()


def start_background_process():
    authkey = current_process().authkey
    global listener

    port = 6000
    while port < 10000:
        try:
            listener = Listener(('localhost', port), authkey=authkey)
            break
        except OSError as error:
            if ((platform.system() == "Windows" and error.errno == 10048)
                or (platform.system() == "Linux" and error.errno == 98)
                or (platform.system() == "Darwin" and error.errno == 48)):
                # Windows: [WinError 10048] Only one usage of each socket address (protocol/network address/port) is normally permitted
                # Linux: [Errno 98] Address already in use
                # macOS: [Errno 48] Address already in use
                port += 1
            else:
                raise

    global background_process
    process_args = [
        bpy.app.binary_path,
        "--factory-startup",
        "--addons", f"{addon_name}",
        "-b",  # Run in background without UI
        join_paths(current_dir, "data", "previewscene.blend"),
        "--python-expr", f"import {addon_name}; {addon_name}.background.run({port}, {authkey})",
    ]

    env_copy = os.environ.copy()

    if bpy.app.version < (3, 6, 0):
        custom_script_dir = bpy.context.preferences.filepaths.script_directory
        # Only use the custom script dir if the addon is installed there. If BLENDER_USER_SCRIPTS is set, but the addon
        # is installed in the default location, the background process will fail to import the addon.
        if custom_script_dir and os.path.exists(join_paths(custom_script_dir, "addons", addon_name)):
            env_copy["BLENDER_USER_SCRIPTS"] = custom_script_dir
    else:
        # Since Blender 3.6, this is a list of script directories
        for custom_script_dir in bpy.context.preferences.filepaths.script_directories:
            # Only use the custom script dir if the addon is installed there. If BLENDER_USER_SCRIPTS is set, but the addon
            # is installed in the default location, the background process will fail to import the addon.
            if os.path.exists(join_paths(custom_script_dir.directory, "addons", addon_name)):
                env_copy["BLENDER_USER_SCRIPTS"] = custom_script_dir.directory
                break

    enable_debug_output = bpy.context.preferences.addons[addon_name].preferences.enable_debug_output
    if enable_debug_output:
        background_process = subprocess.Popen(process_args, env=env_copy)
    else:
        background_process = subprocess.Popen(process_args, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, env=env_copy)

    global connection
    connection = listener.accept()

    global watcher_thread
    watcher_thread = WatcherThread()
    watcher_thread.setDaemon(True)
    watcher_thread.start()


def display_register():
    import atexit
    # Make sure we only register the callback once
    atexit.unregister(exit_callback)
    atexit.register(exit_callback)

    handler_args = ()
    global handle
    # Note: not using "BACKDROP" because the thumbnails would be behind frames in that mode
    handle = SpaceNodeEditor.draw_handler_add(handler, handler_args, "WINDOW", "POST_PIXEL")

    bpy.app.handlers.load_pre.append(load_pre)
    bpy.app.handlers.load_post.append(load_post)
    bpy.app.handlers.save_post.append(save_post)
    bpy.app.handlers.depsgraph_update_post.append(depsgraph_update_post)

    process_starter = threading.Thread(target=start_background_process)
    # In case the background process throws an exception, the process_starter thread could get stuck
    # on listener.accept(). Enable the daemon flag to make sure the Blender process doesn't hang after
    # quit when this happens.
    process_starter.setDaemon(True)
    process_starter.start()

    # 遅延登録のため load_post を取り逃しており、blend のパスが裏プロセスに伝わらず全ジョブが破棄されてしまう
    update_blend_path()


def display_unregister():
    SpaceNodeEditor.draw_handler_remove(handle, "WINDOW")
    bpy.app.handlers.load_pre.remove(load_pre)
    bpy.app.handlers.load_post.remove(load_post)
    bpy.app.handlers.save_post.remove(save_post)
    bpy.app.handlers.depsgraph_update_post.remove(depsgraph_update_post)
    stop_threads_and_process()
    free()
