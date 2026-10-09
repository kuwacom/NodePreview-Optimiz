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

from . import background_client
from .lib.constants import ADDON_NAME
from .lib.editor_utils import get_edited_node_tree, get_preferences, poll_node_tree
from .lib.node_utils import get_tree_settings
from .operators import (
    NODEPREVIEW_OPTIMIZ_OT_cycle_preview_object,
    NODEPREVIEW_OPTIMIZ_OT_open_preferences,
    NODEPREVIEW_OPTIMIZ_OT_restart_background,
    NODEPREVIEW_OPTIMIZ_OT_set_output,
    NODEPREVIEW_OPTIMIZ_OT_set_preview_object,
    NODEPREVIEW_OPTIMIZ_OT_toggle_preview,
)


class NODEPREVIEW_OPTIMIZ_PT_header_popover(bpy.types.Panel):
    """ノードエディターのヘッダー右端から開くポップオーバー"""

    bl_space_type = "NODE_EDITOR"
    bl_region_type = "HEADER"
    bl_label = ADDON_NAME
    bl_description = f"Settings of the {ADDON_NAME} Addon"
    bl_ui_units_x = 9

    def draw(self, context):
        layout = self.layout
        layout.label(text=ADDON_NAME)

        if background_client.get_status() == background_client.STATUS.STOPPED:
            box = layout.box()
            box.label(text="Preview rendering has stopped", icon="ERROR")
            if background_client.last_error:
                # 例外の文面は訳せないため、翻訳の対象から外す
                box.label(text=background_client.last_error, translate=False)
            box.label(text="See the system console for details")
            box.operator(NODEPREVIEW_OPTIMIZ_OT_restart_background.bl_idname, icon="FILE_REFRESH")

        layout.separator()
        layout.operator(NODEPREVIEW_OPTIMIZ_OT_toggle_preview.bl_idname)
        draw_shape_buttons(layout, icon_only=True)
        layout.operator(NODEPREVIEW_OPTIMIZ_OT_set_output.bl_idname)

        preferences = get_preferences(context)
        layout.separator()
        layout.label(text="Addon Preferences")
        layout.prop(preferences, "thumb_scale")
        layout.prop(preferences, "thumb_z_offset")
        layout.prop(preferences, "previews_enabled_by_default")
        layout.prop(preferences, "surface_preview_shape")
        layout.operator(NODEPREVIEW_OPTIMIZ_OT_open_preferences.bl_idname, icon="PREFERENCES")


def draw_shape_buttons(layout, icon_only):
    """
    ### draw_shape_buttons
    選択中のノードのプレビュー形状を 1 クリックで設定するボタンを並べる
    """
    col = layout.column(align=True)
    col.label(text="Preview Shape:")
    row = col.row(align=True)
    row.operator_enum(NODEPREVIEW_OPTIMIZ_OT_set_preview_object.bl_idname, "shape", icon_only=icon_only)
    col.operator(NODEPREVIEW_OPTIMIZ_OT_cycle_preview_object.bl_idname, icon="FILE_REFRESH")


def draw_node_header_menu(self, context):
    if not poll_node_tree(context):
        return

    layout = self.layout

    row = layout.row(align=True)
    node_tree = get_edited_node_tree(context)
    status = background_client.get_status()
    if status == background_client.STATUS.STOPPED:
        row.label(text="Preview stopped", icon="ERROR")
    elif status == background_client.STATUS.STARTING:
        # 起動は数秒で終わるため、場所を取らないようアイコンだけにする
        row.label(text="", icon="SORTTIME")
    row.prop(get_tree_settings(node_tree), "enabled", toggle=True, text="", icon="STATUSBAR")
    row.popover(panel=NODEPREVIEW_OPTIMIZ_PT_header_popover.__name__, text="")


class NodePreviewOptimizSidebarPanel:
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = ADDON_NAME

    @classmethod
    def poll(cls, context):
        return poll_node_tree(context)


class NODEPREVIEW_OPTIMIZ_PT_node_tree_settings(bpy.types.Panel, NodePreviewOptimizSidebarPanel):
    bl_label = "Node Tree Settings"

    def draw(self, context):
        layout = self.layout
        layout.prop(get_tree_settings(get_edited_node_tree(context)), "enabled")

        preferences = get_preferences(context)
        layout.prop(preferences, "thumb_scale")
        layout.prop(preferences, "thumb_z_offset")


class NODEPREVIEW_OPTIMIZ_PT_node_tools(bpy.types.Panel, NodePreviewOptimizSidebarPanel):
    bl_label = "Selected Nodes"

    def draw(self, context):
        layout = self.layout
        layout.operator(NODEPREVIEW_OPTIMIZ_OT_toggle_preview.bl_idname)
        draw_shape_buttons(layout, icon_only=True)


classes = (
    NODEPREVIEW_OPTIMIZ_PT_header_popover,
    NODEPREVIEW_OPTIMIZ_PT_node_tree_settings,
    NODEPREVIEW_OPTIMIZ_PT_node_tools,
)


def register():
    bpy.types.NODE_HT_header.append(draw_node_header_menu)


def unregister():
    bpy.types.NODE_HT_header.remove(draw_node_header_menu)
