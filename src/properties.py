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
from bpy.props import BoolProperty, EnumProperty, IntProperty, PointerProperty

from .lib.constants import ADDON_NAME, PROP_NAME

# 保存済みの .blend の値が変わらないよう、既存の番号は変えずに後ろへ追加する
PREVIEW_OBJECT_ITEMS = (
    ("AUTO", "Auto", "Use the surface preview shape for surface (BxDF) nodes, plane for everything else", "AUTO", 2),
    ("PLANE", "Plane", "Flat Plane", "MESH_PLANE", 0),
    ("SPHERE", "Sphere", "Sphere", "MESH_UVSPHERE", 1),
    ("CUBE", "Cube", "Cube", "MESH_CUBE", 3),
    ("MONKEY", "Monkey", "Monkey (Suzanne)", "MESH_MONKEY", 4),
)


class NodePreviewOptimizNodeSettings(bpy.types.PropertyGroup):
    """
    # NodePreviewOptimizNodeSettings
    ノード毎のプレビュー設定（Node.nodepreview_optimiz として登録する）
    """

    def update_enabled(self, context):
        self.enabled_modified = True

    enabled: BoolProperty(default=True, update=update_enabled)
    enabled_modified: BoolProperty(default=False)
    ignore_scale: BoolProperty(default=False)
    auto_choose_output: BoolProperty(
        default=True, name="Auto", description="Use the first output with an outgoing connection"
    )
    output_index: IntProperty(default=0, min=0)
    preview_object: EnumProperty(name="Preview Object", items=PREVIEW_OBJECT_ITEMS, default="AUTO")

    def is_enabled(self, addon_preferences):
        if self.enabled_modified:
            return self.enabled
        else:
            return addon_preferences.previews_enabled_by_default

    force_update_counter: IntProperty(default=0, min=0)

    def force_update(self):
        try:
            self.force_update_counter += 1
        except ValueError:
            # Overflow
            self.force_update_counter = 0

    @classmethod
    def register(cls):
        setattr(bpy.types.Node, PROP_NAME, PointerProperty(name=f"{ADDON_NAME} Settings", type=cls))

    @classmethod
    def unregister(cls):
        delattr(bpy.types.Node, PROP_NAME)


class NodePreviewOptimizTreeSettings(bpy.types.PropertyGroup):
    """
    # NodePreviewOptimizTreeSettings
    ノードツリー毎のプレビュー設定（NodeTree.nodepreview_optimiz として登録する）
    """

    enabled: BoolProperty(
        name="Show Previews", default=True, description="Show thumbnails above the nodes in this node tree"
    )

    @classmethod
    def register(cls):
        setattr(bpy.types.NodeTree, PROP_NAME, PointerProperty(name=f"{ADDON_NAME} Settings", type=cls))

    @classmethod
    def unregister(cls):
        delattr(bpy.types.NodeTree, PROP_NAME)


classes = (
    NodePreviewOptimizNodeSettings,
    NodePreviewOptimizTreeSettings,
)
