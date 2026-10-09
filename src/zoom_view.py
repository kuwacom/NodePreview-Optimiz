#
#     This file is part of NodePreview-Optimiz, a fork of Node Preview Reborn.
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

# アクティブなノードのプレビューを、高い解像度でレンダリングし直してノードエディターの中央に大きく表示する

import bpy
import gpu
from bpy.types import SpaceNodeEditor
from gpu_extras.batch import batch_for_shader

from . import background_client, preview_cache, preview_drawer
from .lib.constants import ID_PREFIX
from .lib.editor_utils import force_node_editor_draw, get_active_node, get_edited_node_tree, poll_node_tree
from .lib.i18n import iface_, rpt_
from .lib.node_utils import NODE_KEY_SEPARATOR, is_node_supported, make_node_key
from .thumbnail import draw_text

ZOOM_RESOLUTION = 512
# 通常のサムネイルを上書きしないよう、拡大表示の結果は別のキーで受け取る
ZOOM_KEY_SUFFIX = NODE_KEY_SEPARATOR + "zoom"
# 表示中は閉じる操作以外を止めるが、ビューの移動・拡大縮小は通す
PASS_THROUGH_EVENTS = {
    "MOUSEMOVE",
    "INBETWEEN_MOUSEMOVE",
    "MIDDLEMOUSE",
    "WHEELUPMOUSE",
    "WHEELDOWNMOUSE",
    "TRACKPADPAN",
    "TRACKPADZOOM",
    "TIMER",
}
CLOSE_EVENTS = {"ESC", "LEFTMOUSE", "RIGHTMOUSE", "RET", "SPACE"}

# 表示中の拡大プレビュー。描画ハンドラーはオペレーターより長く生きるため、状態はここに置く
state = {"area": None, "node_key": None, "node_name": ""}
handle = None


def _draw_backdrop(width, height):
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    batch = batch_for_shader(
        shader, "TRIS", {"pos": ((0, 0), (width, 0), (width, height), (0, height))}, indices=((0, 1, 2), (0, 2, 3))
    )
    shader.bind()
    shader.uniform_float("color", (0.0, 0.0, 0.0, 0.6))
    batch.draw(shader)


def draw_overlay():
    context = bpy.context
    if state["area"] is None or context.area is None or context.area.as_pointer() != state["area"]:
        return

    region = context.region
    zoomed = preview_cache.thumbnails.get(state["node_key"] + ZOOM_KEY_SUFFIX)
    # 高解像度の結果が届くまでは、手元のサムネイルを引き伸ばして見せる
    thumb = zoomed or preview_cache.thumbnails.get(state["node_key"])
    ui_scale = context.preferences.system.ui_scale

    old_blend_mode = gpu.state.blend_get()
    gpu.state.blend_set("ALPHA")
    _draw_backdrop(region.width, region.height)

    size = min(region.width, region.height) * 0.8
    x0 = (region.width - size) / 2
    y0 = (region.height - size) / 2
    if thumb is not None and (thumb.texture is not None or thumb.pixels is not None):
        if thumb.texture is None:
            thumb.init_texture()
        thumb.draw((x0, y0), (x0 + size, y0), (x0 + size, y0 + size), (x0, y0 + size), ui_scale * 1.5, x0)

    title = state["node_name"] if zoomed else iface_("{} (rendering...)").format(state["node_name"])
    draw_text(title, (x0, y0 + size + 24 * ui_scale), 14, ui_scale)
    draw_text(iface_("Esc / Click: Close"), (x0, y0 - 24 * ui_scale), 11, ui_scale)

    gpu.state.blend_set(old_blend_mode)
    gpu.shader.unbind()


def close():
    """
    ### close
    拡大表示を閉じ、拡大用に受け取った画像を捨てる
    """
    if state["node_key"]:
        preview_cache.thumbnails.pop(state["node_key"] + ZOOM_KEY_SUFFIX, None)
    state.update(area=None, node_key=None, node_name="")
    force_node_editor_draw()


class NODEPREVIEW_OPTIMIZ_OT_zoom_preview(bpy.types.Operator):
    bl_idname = f"{ID_PREFIX}.zoom_preview"
    bl_label = "Enlarge Preview"
    bl_description = "On active node: Render the preview at a higher resolution and show it enlarged"

    @classmethod
    def poll(cls, context):
        if not poll_node_tree(context):
            return False
        node = get_active_node(context)
        return node is not None and is_node_supported(node, context.scene.render.engine)

    def invoke(self, context, event):
        node = get_active_node(context)
        node_key = make_node_key(node, get_edited_node_tree(context), context.space_data.id)
        job = preview_drawer.make_single_node_job(context, node, node_key + ZOOM_KEY_SUFFIX, ZOOM_RESOLUTION)
        if job is None:
            self.report({"ERROR"}, rpt_("This node can't be previewed"))
            return {"CANCELLED"}

        if state["area"] is not None:
            close()
        state.update(area=context.area.as_pointer(), node_key=node_key, node_name=node.name)
        background_client.submit_jobs([job])

        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if state["area"] is None:
            # 別の操作で閉じられた
            return {"FINISHED"}
        if event.type in PASS_THROUGH_EVENTS:
            return {"PASS_THROUGH"}
        is_toggle_key = event.type == "P" and event.shift
        if event.value == "PRESS" and (event.type in CLOSE_EVENTS or is_toggle_key):
            close()
            return {"FINISHED"}
        return {"RUNNING_MODAL"}


classes = (NODEPREVIEW_OPTIMIZ_OT_zoom_preview,)


def register():
    global handle
    handle = SpaceNodeEditor.draw_handler_add(draw_overlay, (), "WINDOW", "POST_PIXEL")


def unregister():
    close()
    SpaceNodeEditor.draw_handler_remove(handle, "WINDOW")
