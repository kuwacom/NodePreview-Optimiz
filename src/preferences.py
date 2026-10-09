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

from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty
from bpy.types import AddonPreferences

from .lib.constants import ADDON_PACKAGE, BACKGROUND_PATTERNS

BG_COLOR_DESC = (
    "Visible when parts of a shader are transparent. Note that very dark or saturated background "
    "colors can produce misleading results for thumbnails of colored transparent shaders"
)


class NodePreviewOptimizPreferences(AddonPreferences):
    """
    # NodePreviewOptimizPreferences
    プリファレンスのアドオン一覧に表示される設定
    """

    # Must be the addon directory name
    # (by default "NodePreview", but a user/dev might change the folder name)
    bl_idname = ADDON_PACKAGE

    previews_enabled_by_default: BoolProperty(
        name="Previews Visible by Default",
        default=True,
        description="Choose wether the thumbnails should be visible by default or not. "
        "If disabled, thumbnails are only shown after selecting nodes and "
        "pressing Ctrl+Shift+P to make them visible",
    )

    def update_redraw(self, context):
        from .lib.editor_utils import force_node_editor_draw

        force_node_editor_draw(("WINDOW", "HEADER"))

    selected_nodes_only: BoolProperty(
        name="Selected Nodes Only",
        default=False,
        update=update_redraw,
        description="Only show and render previews of selected nodes. Useful in large node trees",
    )

    pause_updates: BoolProperty(
        name="Pause Updates",
        default=False,
        update=update_redraw,
        description="Stop updating previews when nodes are edited. Existing thumbnails stay visible, "
        "and Refresh Previews updates them manually",
    )

    update_during_animation_playback: BoolProperty(
        name="Update During Animation Playback",
        default=True,
        description="When disabled, previews will not update while animation playback "
        "is running. Can be used to improve performance of animation playback "
        "in complex scenes",
    )

    thumb_scale: FloatProperty(
        name="Thumbnail Scale",
        default=50,
        min=1,
        max=100,
        subtype="PERCENTAGE",
        description="Size of the thumbnails in the node editor",
    )

    thumb_z_offset: FloatProperty(
        name="Vertical Offset", default=5, min=0, max=50, description="Vertical offset of the thumbnails from the node"
    )

    surface_preview_shape: EnumProperty(
        name="Surface Preview Shape",
        items=(
            ("SPHERE", "Sphere", "Sphere", "MESH_UVSPHERE", 0),
            ("CUBE", "Cube", "Cube", "MESH_CUBE", 1),
            ("MONKEY", "Monkey", "Monkey (Suzanne)", "MESH_MONKEY", 2),
        ),
        default="SPHERE",
        description="Shape used for surface (BxDF) nodes when their preview object is set to Auto",
    )

    def update_max_background_processes(self, context):
        # 裏プロセスは UI のある Blender でだけ動かすため、設定画面から変更された時にだけ読み込む
        from . import background_client

        background_client.restart_processes()

    max_background_processes: IntProperty(
        name="Max Background Processes",
        default=2,
        min=1,
        soft_max=4,
        max=8,
        update=update_max_background_processes,
        description="Maximum number of Blender processes that render thumbnails in parallel. "
        "Higher values update faster, but use more memory",
    )

    thumb_resolution: IntProperty(
        name="Thumbnail Resolution",
        default=150,
        min=50,
        soft_max=300,
        max=500,
        description="Higher resolutions preserve fine detail in textures better, but lead to slower updates",
    )

    background_pattern_items = [
        (BACKGROUND_PATTERNS.CHECKER, "Checkerboard Pattern", "", 0),
        (BACKGROUND_PATTERNS.WHITE, "Solid Color", "", 1),
    ]
    background_pattern: EnumProperty(
        name="Background",
        items=background_pattern_items,
        default="CHECKER",
        description="The background pattern is visible when parts of a shader are transparent/transmissive",
    )

    background_color_1: FloatVectorProperty(
        name="Background Color", default=(0.994, 0.994, 0.994), min=0, max=1, subtype="COLOR", description=BG_COLOR_DESC
    )
    background_color_2: FloatVectorProperty(
        name="Background Color",
        default=(0.8086, 0.8086, 0.8086),
        min=0,
        max=1,
        subtype="COLOR",
        description=BG_COLOR_DESC,
    )

    show_help: BoolProperty(
        name="Show Help Messages",
        default=True,
        description="Show the following help message:\n"
        "Procedural texture scale can be ignored with Ctrl+Shift+I (shown if texture scale is so large "
        "that the texture is no longer recognizable, or if texture scale is driven by another texture",
    )

    need_blender_restart = False

    def update_enable_debug_output(self, context):
        NodePreviewOptimizPreferences.need_blender_restart = True

    enable_debug_output: BoolProperty(
        name="Enable Debug Output",
        default=False,
        update=update_enable_debug_output,
        description="Print debug information to the system console",
    )

    def draw(self, context):
        layout = self.layout

        layout.prop(self, "previews_enabled_by_default")
        layout.prop(self, "selected_nodes_only")
        layout.prop(self, "pause_updates")
        layout.prop(self, "update_during_animation_playback")

        row = layout.row()
        row.prop(self, "thumb_scale")
        row.prop(self, "thumb_z_offset")
        row.prop(self, "thumb_resolution")

        layout.prop(self, "surface_preview_shape")
        layout.prop(self, "max_background_processes")

        row = layout.row()
        row.label(text="Background:")
        row.prop(self, "background_pattern", expand=True)

        using_checker_pattern = self.background_pattern == BACKGROUND_PATTERNS.CHECKER
        row = layout.row()
        row.label(text="")
        if using_checker_pattern:
            row.label(text="")
        row.prop(self, "background_color_1", text=("Color 1" if using_checker_pattern else "Color"))
        if using_checker_pattern:
            row.prop(self, "background_color_2", text="Color 2")

        layout.prop(self, "show_help")
        layout.prop(self, "enable_debug_output")
        if NodePreviewOptimizPreferences.need_blender_restart:
            layout.label(text="Please restart Blender for the change to take effect", icon="ERROR")

        col = layout.column(align=True)
        col.label(text="Shortcuts:", icon="INFO")
        col.label(text="Ctrl+Shift+P: Toggle thumbnail visibility on selected nodes")
        col.label(text="Ctrl+Shift+i: Toggle wether to ignore the Scale socket on selected procedural texture nodes")
        col.label(text="Shift+O: Set the output to show in the preview thumbnail for the active node")
        col.label(text="Ctrl+P: Cycle the preview shape (plane, sphere, cube, monkey) on selected nodes")
        col.label(text="Shift+P: Show the preview of the active node enlarged")
        col.label(text="Ctrl+Alt+P: Toggle showing previews of selected nodes only")
        col.label(text="(These shortcuts can be changed in the Keymap settings)")


classes = (NodePreviewOptimizPreferences,)
