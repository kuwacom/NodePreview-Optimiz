#
#     This file is part of NodePreview-Optimiz, a fork of Node Preview Reborn.
#     Copyright (C) 2021 Simon Wendsche
#     Copyright (C) 2026 Guillaume Henrion aka GYOMH (fork/modifications)
#     Copyright (C) 2026 kuwacom (NodePreview-Optimiz)
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

# ノードエディターの再描画のたびに、ジョブの作成とサムネイルの描画を行う

import base64
import os
from math import sqrt
from time import time

import bpy
import gpu
from bpy.types import SpaceNodeEditor

from . import background_client, node_converter, preview_cache, scene_converter, update_tracker
from .lib.constants import BACKGROUND_PATTERNS, SUPPORTED_NODE_TREE
from .lib.editor_utils import get_preferences
from .lib.i18n import iface_
from .lib.image_utils import get_blend_abspath, get_image_linking_info, needs_linking
from .lib.node_utils import (
    SCALE_HELP_THRESHOLDS,
    UnsupportedNodeException,
    get_node_settings,
    get_preview_shape,
    get_tree_settings,
    is_node_enabled,
    is_node_supported,
    make_node_key,
    make_tree_key_suffix,
    needs_more_than_1_sample,
    sort_topologically,
)
from .thumbnail import draw_text

handle = None  # Draw handler


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


def to_valid_filename(name):
    return base64.urlsafe_b64encode(name.encode("UTF-8")).decode("UTF-8")


def get_background_colors(preferences):
    using_checker_pattern = preferences.background_pattern == BACKGROUND_PATTERNS.CHECKER
    background_col_1 = list(preferences.background_color_1) + [1]
    background_col_2 = list(preferences.background_color_2) + [1] if using_checker_pattern else background_col_1
    return background_col_1, background_col_2


def make_job(node, node_key, script, group_scripts, images_to_load, images_to_link, thumb_resolution):
    """
    ### make_job
    裏プロセスに送るジョブを組み立てる

    @returns ジョブのタプル（最後の要素は作成時刻）
    """
    thumb_path = os.path.join(background_client.temp_dir, to_valid_filename(node_key) + ".png")

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

    return (
        node_key,
        script,
        group_scripts,
        images_to_load,
        images_to_link,
        image_info,
        get_blend_abspath(),
        thumb_path,
        thumb_resolution,
        time(),
    )


def make_single_node_job(context, node, node_key, thumb_resolution):
    """
    ### make_single_node_job
    描画ハンドラーを通さずに、1 つのノードだけのジョブを作る（拡大表示用など）

    @param node - 表示中のノードツリーにあるノード
    @param node_key - 結果を受け取るキー（通常のサムネイルと分けたい場合は別のキーを渡す）
    @param thumb_resolution - レンダリングする解像度
    @returns ジョブ。対応していないノードなら None
    """
    space = context.space_data
    node_tree_hierarchy = [elem.node_tree for elem in space.path]
    node_tree = node_tree_hierarchy[-1]
    engine = context.scene.render.engine
    preferences = get_preferences(context)
    if not is_node_supported(node, engine):
        return None
    if not node_converter.node_attributes_cache:
        node_converter.build_node_attributes_cache()

    group_scripts, group_images_to_load, group_images_to_link, group_hashes = update_tracker.get_group_script(
        node_tree_hierarchy
    )
    incoming_links = {link.to_socket: link for link in node_tree.links}
    try:
        node_script, images_to_load, images_to_link = node_converter.node_to_script(
            node,
            space.id,
            {},
            group_hashes,
            incoming_links,
            get_background_colors(preferences),
            node_tree_hierarchy,
            engine,
        )
    except UnsupportedNodeException:
        return None

    # 大きく表示するとノイズが目立つため、常にサンプル数を増やしてノイズ除去も掛ける
    scene_script = scene_converter.scene_to_script(
        context, True, get_preview_shape(node, preferences.surface_preview_shape)
    )
    return make_job(
        node,
        node_key,
        "\n".join((scene_script, node_script)),
        group_scripts,
        images_to_load | group_images_to_load,
        images_to_link | group_images_to_link,
        thumb_resolution,
    )


def handler():
    # from time import perf_counter
    # __start = perf_counter()

    # 裏プロセスの起動中・再起動中も、手元のサムネイルは描き、ジョブは送信待ちに積んでおく
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

    if not get_tree_settings(node_tree).enabled:
        return

    preferences = get_preferences(context)
    enabled_by_default = preferences.previews_enabled_by_default
    selected_nodes_only = preferences.selected_nodes_only

    def is_shown(node):
        return is_node_enabled(node, enabled_by_default) and (not selected_nodes_only or node.select)

    all_previews_disabled = True
    for node in node_tree.nodes:
        try:
            if is_shown(node):
                all_previews_disabled = False
                break
        except AttributeError:  # Some special nodes might not have the node_preview attribute
            pass
    if all_previews_disabled:
        return

    if not node_converter.node_attributes_cache:
        node_converter.build_node_attributes_cache()

    area = context.area
    engine = context.scene.render.engine
    ui_scale = context.preferences.system.ui_scale
    zoom = get_region_zoom(context)
    scaled_zoom = zoom * ui_scale
    thumb_scale = preferences.thumb_scale / 100
    thumb_z_offset = preferences.thumb_z_offset
    thumb_resolution = preferences.thumb_resolution

    background_colors = get_background_colors(preferences)

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

    sorted_nodes = sort_topologically(node_tree.nodes, get_dependent_nodes)

    old_blend_mode = gpu.state.blend_get()
    gpu.state.blend_set("ALPHA")

    # node_tree_owner is the material, world etc. that contains the node_tree
    node_tree_owner = context.space_data.id

    # 50 ノード以上のツリーは前半/後半を交互に処理するため、2 回処理して初めて全ノードが最新になる
    parts_needed = 1 if len(sorted_nodes) < 50 else 2
    signature = update_tracker.make_update_signature(
        context, node_tree, node_tree_hierarchy, node_tree_owner, preferences
    )
    generation = update_tracker.update_generation
    last_state = update_tracker.processed_state.get(node_tree)
    state_matches = last_state is not None and last_state[0] == generation and last_state[1] == signature
    needs_conversion = not (state_matches and last_state[2] >= parts_needed)
    # 一時停止中は手元のサムネイルを描くだけにする。溜まった変更は再開時に世代番号の違いから検知される
    if needs_conversion and preferences.pause_updates and not update_tracker.consume_manual_refresh():
        needs_conversion = False

    if needs_conversion:
        group_scripts, group_images_to_load, group_images_to_link, group_hashes = update_tracker.get_group_script(
            node_tree_hierarchy
        )

    # socket.links is a very expensive property to access, so we cache the link types we are interested in most in this dict
    incoming_links = {link.to_socket: link for link in node_tree.links}
    # node.name: node_creation_script, images_to_load, images_to_link
    node_scripts_cache = {}
    jobs_to_send = []

    # Note: Can't store this as a property on the node tree, because setting is sometimes not possible in a draw handler
    update_first_part = preview_cache.update_first_part
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
        processed_parts = last_state[2] + 1 if state_matches else 1
        update_tracker.processed_state[node_tree] = (generation, signature, processed_parts)
        if preferences.pause_updates and processed_parts >= parts_needed:
            # 小さいツリーは 1 回で更新が終わるため、余った分で一時停止中の編集まで反映しないようにする
            update_tracker.manual_refresh_passes = 0
        preview_cache.prune_tree(
            make_tree_key_suffix(node_tree, node_tree_owner),
            {make_node_key(node, node_tree, node_tree_owner) for node in node_tree.nodes},
        )

        for node in sorted_nodes[start:end]:
            if not is_node_supported(node, engine):
                continue

            try:
                # Even if the preview is disabled, we need to convert the script so dependent nodes can retrieve it from the node scripts cache
                node_script, images_to_load, images_to_link = node_converter.node_to_script(
                    node,
                    node_tree_owner,
                    node_scripts_cache,
                    group_hashes,
                    incoming_links,
                    background_colors,
                    node_tree_hierarchy,
                    engine,
                )
            except UnsupportedNodeException:
                continue

            if not is_shown(node):
                continue

            preview_shape = get_preview_shape(node, preferences.surface_preview_shape)
            needs_more_samples = needs_more_than_1_sample(node, preview_shape != "PLANE")

            scene_script = scene_converter.scene_to_script(context, needs_more_samples, preview_shape)
            script_hash = hash(node_script + scene_script)
            node_key = make_node_key(node, node_tree, node_tree_owner)

            cached_nodes = preview_cache.cached_nodes
            if node_key not in cached_nodes or cached_nodes[node_key][0] != script_hash:
                job = make_job(
                    node,
                    node_key,
                    "\n".join((scene_script, node_script)),
                    group_scripts,
                    images_to_load | group_images_to_load,
                    images_to_link | group_images_to_link,
                    thumb_resolution,
                )
                jobs_to_send.append(job)
                cached_nodes[node_key] = script_hash, job[-1]

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
    visible_node_keys = set()
    for node in sorted_nodes:
        if not is_node_supported(node, engine):
            continue

        if not is_shown(node):
            continue

        location = node.location.copy()
        n = node
        while n.parent:
            # Take (possibly nested) frames into account
            location += n.parent.location
            n = n.parent

        topleft_x, topleft_y = view_to_region_scaled(context, *location, clip=False)
        topright_x, _ = view_to_region_scaled(context, location[0] + node.width, 0, clip=False)
        node_width = topright_x - topleft_x

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

        node_key = make_node_key(node, node_tree, node_tree_owner)
        visible_node_keys.add(node_key)

        try:
            thumb = preview_cache.thumbnails[node_key]
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

        node_settings = get_node_settings(node)
        if not node_settings.auto_choose_output:
            output = node.outputs[node_settings.output_index].name
            text_y = draw_text(iface_("Output: {}").format(output), (text_x, text_y), text_size, scaled_zoom)
            text_y += text_size * scaled_zoom * 0.5  # A bit of spacing in case of more text after

        if preferences.show_help and "Scale" in node.inputs:
            try:
                threshold = SCALE_HELP_THRESHOLDS[node.bl_idname]
                if node.inputs["Scale"].is_linked or abs(node.inputs["Scale"].default_value) > threshold:
                    if node_settings.ignore_scale:
                        text_y = draw_text(iface_("Scale ignored"), (text_x, text_y), text_size, scaled_zoom)
                    else:
                        text_y = draw_text(
                            iface_("Scale can be ignored\nwith Ctrl+Shift+i"), (text_x, text_y), text_size, scaled_zoom
                        )
            except KeyError:
                # Node doesn't have a known scale threshold, don't show the help message
                pass

    gpu.state.blend_set(old_blend_mode)
    gpu.shader.unbind()

    background_client.set_visible_node_keys(visible_node_keys)
    # Send jobs in reversed order so the leftmost node (which was edited) is rendered first for fast feedback
    if jobs_to_send:
        background_client.submit_jobs(reversed(jobs_to_send))

    # elapsed = perf_counter() - __start
    # print("draw handler took %.3f s (%d fps)" % (elapsed, round(1 / elapsed)))
    # draw_text("Node Preview Frametime: %.3f s (%d FPS)" % (elapsed, round(1 / elapsed)), (30, 30), 15, 1)


def register():
    global handle
    # Note: not using "BACKDROP" because the thumbnails would be behind frames in that mode
    handle = SpaceNodeEditor.draw_handler_add(handler, (), "WINDOW", "POST_PIXEL")


def unregister():
    SpaceNodeEditor.draw_handler_remove(handle, "WINDOW")
