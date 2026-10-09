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

import bpy
from bpy.props import EnumProperty

from .lib.constants import ADDON_NAME, ID_PREFIX
from .lib.editor_utils import (
    force_node_editor_draw,
    get_active_node,
    get_edited_node_tree,
    get_preferences,
    poll_node_tree,
)
from .lib.i18n import iface_, rpt_, tip_
from .lib.node_utils import get_node_settings, get_preview_shape
from .properties import PREVIEW_OBJECT_ITEMS

# Ctrl+P で切り替える順番
PREVIEW_SHAPE_CYCLE = ("PLANE", "SPHERE", "CUBE", "MONKEY")


def get_selected_nodes(context):
    """
    ### get_selected_nodes
    @returns 表示中のノードツリーで選択されていて、プレビュー設定を持つノードの一覧
    """
    node_tree = get_edited_node_tree(context)
    return [node for node in node_tree.nodes if node.select and get_node_settings(node) is not None]


class NODEPREVIEW_OPTIMIZ_OT_open_preferences(bpy.types.Operator):
    bl_idname = f"{ID_PREFIX}.open_preferences"
    bl_label = "Open Preferences"
    bl_description = f"Open the {ADDON_NAME} addon user preferences"

    def execute(self, context):
        bpy.ops.screen.userpref_show(section="ADDONS")
        context.window_manager.addon_search = ADDON_NAME
        return {"FINISHED"}


class NODEPREVIEW_OPTIMIZ_OT_restart_background(bpy.types.Operator):
    bl_idname = f"{ID_PREFIX}.restart_background"
    bl_label = "Restart Preview Rendering"
    bl_description = "Restart the background processes that render the thumbnails"

    def execute(self, context):
        from . import background_client

        background_client.restart_processes()
        return {"FINISHED"}


class NODEPREVIEW_OPTIMIZ_OT_toggle_preview(bpy.types.Operator):
    bl_idname = f"{ID_PREFIX}.toggle_preview"
    bl_label = "Toggle Node Previews"
    bl_description = "On selected nodes: Toggle visibility of the node preview thumbnail on/off"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        return poll_node_tree(context)

    def invoke(self, context, event):
        preferences = get_preferences(context)
        selection = get_selected_nodes(context)

        if not selection:
            self.report({"ERROR"}, rpt_("No nodes selected"))
            return {"CANCELLED"}

        # If at least one node has the preview enabled, this operator should switch them all off.
        # Only when all selected nodes have the preview disabled, switch them on.
        initial_state = any(get_node_settings(node).is_enabled(preferences) for node in selection)

        for node in selection:
            get_node_settings(node).enabled = not initial_state

        force_node_editor_draw()
        return {"FINISHED"}


class NODEPREVIEW_OPTIMIZ_OT_toggle_ignore_scale(bpy.types.Operator):
    bl_idname = f"{ID_PREFIX}.toggle_ignore_scale"
    bl_label = "Toggle Ignore Scale"
    bl_description = (
        "On selected nodes: Toggle wether to ignore procedural texture scale when rendering the node preview "
        "(useful on procedural textures like Voronoi, Noise etc.)"
    )
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        return poll_node_tree(context)

    def invoke(self, context, event):
        selection = get_selected_nodes(context)

        if not selection:
            self.report({"ERROR"}, rpt_("No nodes selected"))
            return {"CANCELLED"}

        for node in selection:
            settings = get_node_settings(node)
            settings.ignore_scale = not settings.ignore_scale

        force_node_editor_draw()
        return {"FINISHED"}


class NODEPREVIEW_OPTIMIZ_OT_set_output(bpy.types.Operator):
    bl_idname = f"{ID_PREFIX}.set_output"
    bl_label = "Set Node Output to Preview"
    bl_description = "On active node: Choose output to show in the node preview thumbnail"
    bl_options = {"UNDO"}

    def update_output(self, context):
        settings = get_node_settings(get_active_node(context))
        settings.output_index = int(self.output)
        settings.auto_choose_output = False

    def callback_output_items(self, context):
        return NODEPREVIEW_OPTIMIZ_OT_set_output.output_items

    # TODO can we somehow set the correct default (current output)? Probably not, according to Blender documentation
    output: EnumProperty(name="Output", items=callback_output_items, update=update_output)
    output_items = []

    @classmethod
    def poll(cls, context):
        if not poll_node_tree(context):
            return False
        # Make sure there's an active node to work with
        return get_active_node(context)

    def invoke(self, context, event):
        node = get_active_node(context)

        NODEPREVIEW_OPTIMIZ_OT_set_output.output_items.clear()
        index = 0
        for socket in node.outputs:
            if socket.enabled:
                NODEPREVIEW_OPTIMIZ_OT_set_output.output_items.append(
                    (str(index), socket.name, tip_("Show preview for output {}").format(socket.name), index)
                )
                index += 1

        wm = context.window_manager
        return wm.invoke_popup(self, width=120)

    def draw(self, context):
        layout = self.layout
        node = get_active_node(context)

        # 訳した後の文字列が再度翻訳の対象にならないよう translate=False にする
        layout.label(text=iface_('Node: "{}"').format(node.name), translate=False)

        if node.outputs:
            col = layout.column()
            col.label(text="Output:")
            col.prop(get_node_settings(node), "auto_choose_output")
            col.prop(self, "output", expand=True)
        else:
            layout.label(text="Node has no outputs")

    def execute(self, context):
        return {"FINISHED"}


class NODEPREVIEW_OPTIMIZ_OT_cycle_preview_object(bpy.types.Operator):
    bl_idname = f"{ID_PREFIX}.cycle_preview_object"
    bl_label = "Change Preview Object"
    bl_description = "On selected nodes: Cycle the preview shape between plane, sphere, cube and monkey"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        return poll_node_tree(context)

    def invoke(self, context, event):
        selection = get_selected_nodes(context)

        if not selection:
            self.report({"ERROR"}, rpt_("No nodes selected"))
            return {"CANCELLED"}

        # アクティブ（無ければ先頭）のノードの今の形状を基準に、全員を次の形状へ揃える
        reference = context.active_node if context.active_node in selection else selection[0]
        current = get_preview_shape(reference, get_preferences(context).surface_preview_shape)
        new_state = PREVIEW_SHAPE_CYCLE[(PREVIEW_SHAPE_CYCLE.index(current) + 1) % len(PREVIEW_SHAPE_CYCLE)]

        for node in selection:
            get_node_settings(node).preview_object = new_state

        force_node_editor_draw()
        return {"FINISHED"}


class NODEPREVIEW_OPTIMIZ_OT_set_preview_object(bpy.types.Operator):
    bl_idname = f"{ID_PREFIX}.set_preview_object"
    bl_label = "Set Preview Shape"
    bl_description = "On selected nodes: Set the shape used for the preview"
    bl_options = {"UNDO"}

    shape: EnumProperty(name="Shape", items=PREVIEW_OBJECT_ITEMS)

    @classmethod
    def poll(cls, context):
        return poll_node_tree(context)

    def execute(self, context):
        selection = get_selected_nodes(context)

        if not selection:
            self.report({"ERROR"}, rpt_("No nodes selected"))
            return {"CANCELLED"}

        for node in selection:
            get_node_settings(node).preview_object = self.shape

        force_node_editor_draw()
        return {"FINISHED"}


classes = (
    NODEPREVIEW_OPTIMIZ_OT_open_preferences,
    NODEPREVIEW_OPTIMIZ_OT_set_preview_object,
    NODEPREVIEW_OPTIMIZ_OT_restart_background,
    NODEPREVIEW_OPTIMIZ_OT_toggle_preview,
    NODEPREVIEW_OPTIMIZ_OT_toggle_ignore_scale,
    NODEPREVIEW_OPTIMIZ_OT_set_output,
    NODEPREVIEW_OPTIMIZ_OT_cycle_preview_object,
)
