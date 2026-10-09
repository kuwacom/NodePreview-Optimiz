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
from bpy.types import AddonPreferences
from bpy.props import FloatProperty, FloatVectorProperty, IntProperty, EnumProperty, BoolProperty
from bpy.utils import register_class, unregister_class

from os.path import basename, dirname


addon_name = basename(dirname(__file__))
THUMB_CHANNEL_COUNT = 4
SUPPORTED_NODE_TREE = "ShaderNodeTree"
addon_keymaps = []

bl_info = {
    "name": "NodePreview-Optimiz",
    "author": "Guillaume Henrion aka GYOMH (based on Node Preview by Simon Wendsche)",
    "version": (1, 0, 1),
    "blender": (4, 5, 0),
    "category": "Node",
    "location": "Shader Node Editor",
    "description": "Displays rendered thumbnails above shader nodes",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
}

# The original "Node Preview" addon (by Simon Wendsche) registers the same class/operator
# identifiers as this fork. Having both installed and enabled at the same time causes
# Blender to fail registration ("already registered as a subclass"). If the original is
# found installed under its default module name, disable and remove it automatically.
_LEGACY_ADDON_MODULE = "NodePreview"


def _handle_legacy_addon_conflict():
    if _LEGACY_ADDON_MODULE == addon_name or _LEGACY_ADDON_MODULE not in bpy.context.preferences.addons:
        return None

    print(f"[{bl_info['name']}] Detected the original 'Node Preview' addon (module "
          f"'{_LEGACY_ADDON_MODULE}') installed alongside this fork. It uses the same internal "
          f"identifiers and would break registration, so it is being disabled and removed automatically.")

    # Must run before this fork's own classes register: if our classes register first, Blender
    # silently replaces the old addon's identically-named classes with ours, so the old addon's
    # own unregister() then fails ("missing bl_rna attribute, may not be registered") and its
    # addon_remove() is never reached.
    try:
        bpy.ops.preferences.addon_disable(module=_LEGACY_ADDON_MODULE)
    except Exception as error:
        print(f"[{bl_info['name']}] Could not cleanly disable the old 'Node Preview' addon: {error}")

    try:
        bpy.ops.preferences.addon_remove(module=_LEGACY_ADDON_MODULE)
    except Exception:
        # addon_remove()'s own implementation can raise on a trailing UI redraw call
        # (context.area is None) when invoked outside a normal UI context, like this deferred
        # timer, even though the actual file removal already succeeded. Verify the real outcome
        # below instead of trusting the exception.
        pass

    import os
    import addon_utils
    still_installed = any(os.path.isdir(os.path.join(p, _LEGACY_ADDON_MODULE)) for p in addon_utils.paths())
    if still_installed:
        print(f"[{bl_info['name']}] Could not automatically remove the old 'Node Preview' addon. "
              f"Please remove it manually in Edit > Preferences > Add-ons to avoid conflicts.")
    else:
        print(f"[{bl_info['name']}] Removed the old 'Node Preview' addon.")
    return None


class UnsupportedNodeException(Exception):
    pass


def is_group_node(node):
    return hasattr(node, "node_tree") and (isinstance(node.node_tree, bpy.types.ShaderNodeTree) or node.node_tree is None)


def needs_sphere_preview(node):
    preview_object = node.node_preview.preview_object
    if preview_object == "AUTO":
        bl_idname = node.bl_idname

        if bl_idname == "ShaderNodeGroup" and node.node_tree:
            for subnode in node.node_tree.nodes:
                if needs_sphere_preview(subnode):
                    return True

        return (bl_idname.startswith("ShaderNodeBsdf")
                or bl_idname in {
                    "ShaderNodeSubsurfaceScattering",
                    "ShaderNodeVolumeScatter",
                    "ShaderNodeVolumePrincipled",
                    "ShaderNodeVolumeAbsorption",
                    "ShaderNodeMixShader",
                    "ShaderNodeAddShader",
                    "ShaderNodeEeveeSpecular",
                    "ShaderNodeEmission",
                })
    elif preview_object == "SPHERE":
        return True
    elif preview_object == "PLANE":
        return False
    else:
        raise NotImplementedError("Unknown preview_object value")


def force_node_editor_draw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "NODE_EDITOR":
                for region in area.regions:
                    if region.type == "WINDOW":
                        region.tag_redraw()


def needs_linking(image):
    return bool(image.packed_file) or image.source == "GENERATED"


def get_blend_abspath():
    return bpy.path.abspath(bpy.data.filepath)


def get_image_linking_info(image):
    # Note: for linking, we need the original image name as it appears in the library .blend file
    return image.name, bpy.path.abspath(image.library.filepath) if image.library else get_blend_abspath()


def make_unique_image_name(image):
    BLENDER_MAX_NAME_LENGTH = 63
    lib_name = image.library.name if image.library else bpy.path.basename(bpy.data.filepath)
    name = image.name + lib_name
    if len(name) < 55:
        return name
    else:
        import hashlib
        # The md5 hexdigest is always 32 characters long, so it should be OK for Blender
        return hashlib.md5(name.encode("utf-8")).hexdigest()


class BACKGROUND_PATTERNS:
    CHECKER = "CHECKER"
    WHITE = "WHITE"


BG_COLOR_DESC = ("Visible when parts of a shader are transparent. Note that very dark or saturated background "
                 "colors can produce misleading results for thumbnails of colored transparent shaders")


class NodePreviewAddonPreferences(AddonPreferences):
    # Must be the addon directory name
    # (by default "NodePreview", but a user/dev might change the folder name)
    bl_idname = addon_name

    previews_enabled_by_default: BoolProperty(name="Previews Visible by Default", default=True,
                                              description="Choose wether the thumbnails should be visible by default or not. "
                                                          "If disabled, thumbnails are only shown after selecting nodes and "
                                                          "pressing Ctrl+Shift+P to make them visible")

    update_during_animation_playback: BoolProperty(name="Update During Animation Playback", default=True,
                                                   description="When disabled, previews will not update while animation playback "
                                                               "is running. Can be used to improve performance of animation playback "
                                                               "in complex scenes")

    thumb_scale: FloatProperty(name="Thumbnail Scale", default=50, min=1, max=100, subtype="PERCENTAGE",
                               description="Size of the thumbnails in the node editor")

    thumb_z_offset: FloatProperty(name="Vertical Offset", default=5, min=0, max=50,
                                  description="Vertical offset of the thumbnails from the node")

    thumb_resolution: IntProperty(name="Thumbnail Resolution", default=150, min=50, soft_max=300, max=500,
                                  description="Higher resolutions preserve fine detail in textures better, but lead to slower updates")

    background_pattern_items = [
        (BACKGROUND_PATTERNS.CHECKER, "Checkerboard Pattern", "", 0),
        (BACKGROUND_PATTERNS.WHITE, "Solid Color", "", 1),
    ]
    background_pattern: EnumProperty(name="Background", items=background_pattern_items, default="CHECKER",
                                     description="The background pattern is visible when parts of a shader are transparent/transmissive")

    background_color_1: FloatVectorProperty(name="Background Color", default=(0.994, 0.994, 0.994), min=0, max=1, subtype="COLOR",
                                            description=BG_COLOR_DESC)
    background_color_2: FloatVectorProperty(name="Background Color", default=(0.8086, 0.8086, 0.8086), min=0, max=1, subtype="COLOR",
                                            description=BG_COLOR_DESC)

    show_help: BoolProperty(name="Show Help Messages", default=True,
                            description="Show the following help message:\n"
                                        "Procedural texture scale can be ignored with Ctrl+Shift+I (shown if texture scale is so large "
                                        "that the texture is no longer recognizable, or if texture scale is driven by another texture")

    need_blender_restart = False
    def update_enable_debug_output(self, context):
        NodePreviewAddonPreferences.need_blender_restart = True

    enable_debug_output: BoolProperty(name="Enable Debug Output", default=False,
                                      update=update_enable_debug_output,
                                      description="Print debug information to the system console")

    def draw(self, context):
        layout = self.layout

        layout.prop(self, "previews_enabled_by_default")
        layout.prop(self, "update_during_animation_playback")

        row = layout.row()
        row.prop(self, "thumb_scale")
        row.prop(self, "thumb_z_offset")
        row.prop(self, "thumb_resolution")

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
        if NodePreviewAddonPreferences.need_blender_restart:
            layout.label(text="Please restart Blender for the change to take effect", icon="ERROR")

        col = layout.column(align=True)
        col.label(text="Shortcuts:", icon="INFO")
        col.label(text="Ctrl+Shift+P: Toggle thumbnail visibility on selected nodes")
        col.label(text="Ctrl+Shift+i: Toggle wether to ignore the Scale socket on selected procedural texture nodes")
        col.label(text="Shift+O: Set the output to show in the preview thumbnail for the active node")
        col.label(text="Ctrl+P: Switch between a flat plane and a 3D sphere as preview object on selected nodes")
        col.label(text="(These shortcuts can be changed in the Keymap settings)")


def poll_node_tree(context):
    space = context.space_data
    # Path contains a chain of nested node trees, the last one is the currently active one
    if not getattr(space, "path", False):
        return False
    node_tree = space.path[-1].node_tree
    return space.type == "NODE_EDITOR" and node_tree and space.tree_type == SUPPORTED_NODE_TREE


class NODE_PT_node_preview(bpy.types.Panel):
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'HEADER'
    bl_label = bl_info["name"]
    bl_description = f"Settings of the {bl_info['name']} Addon"
    bl_ui_units_x = 9
    bl_idname = "NODE_PT_node_preview"

    def draw(self, context):
        layout = self.layout
        layout.label(text=bl_info["name"])

        layout.separator()
        layout.operator("nodepreview.toggle_preview")
        layout.operator("nodepreview.cycle_preview_object")
        layout.operator("nodepreview.set_output")

        preferences = context.preferences.addons[addon_name].preferences
        layout.separator()
        layout.label(text="Addon Preferences")
        layout.prop(preferences, "thumb_scale")
        layout.prop(preferences, "thumb_z_offset")
        layout.prop(preferences, "previews_enabled_by_default")
        layout.operator("nodepreview.open_userprefs", icon="PREFERENCES")


def draw_node_header_menu(self, context):
    if not poll_node_tree(context):
        return

    layout = self.layout

    row = layout.row(align=True)
    node_tree = context.space_data.path[-1].node_tree
    row.prop(node_tree.node_preview, "enabled", toggle=True, text="", icon="STATUSBAR")
    row.popover(panel=NODE_PT_node_preview.bl_idname, text="")


class NODEPREVIEW_OT_open_userprefs(bpy.types.Operator):
    bl_idname = "nodepreview.open_userprefs"
    bl_label = "Open Preferences"
    bl_description = f"Open the {bl_info['name']} addon user preferences"

    def execute(self, context):
        bpy.ops.screen.userpref_show(section="ADDONS")
        bpy.data.window_managers["WinMan"].addon_search = bl_info["name"]
        return {"FINISHED"}


class NODEPREVIEW_OT_toggle_preview(bpy.types.Operator):
    bl_idname = "nodepreview.toggle_preview"
    bl_label = "Toggle Node Previews"
    bl_description = "On selected nodes: Toggle visibility of the node preview thumbnail on/off"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        return poll_node_tree(context)

    def invoke(self, context, event):
        space = context.space_data
        node_tree = space.path[-1].node_tree
        preferences = context.preferences.addons[addon_name].preferences

        selection = [node for node in node_tree.nodes if node.select and hasattr(node, "node_preview")]

        if not selection:
            self.report({"ERROR"}, "No nodes selected")
            return {"CANCELLED"}

        # If at least one node has the preview enabled, this operator should switch them all off.
        # Only when all selected nodes have the preview disabled, switch them on.
        initial_state = any((node.node_preview.is_enabled(preferences) for node in selection))

        for node in selection:
            node.node_preview.enabled = not initial_state

        force_node_editor_draw()
        return {"FINISHED"}


class NODEPREVIEW_OT_toggle_ignore_scale(bpy.types.Operator):
    bl_idname = "nodepreview.toggle_ignore_scale"
    bl_label = "Toggle Ignore Scale"
    bl_description = ("On selected nodes: Toggle wether to ignore procedural texture scale when rendering the node preview "
                      "(useful on procedural textures like Musgrave, Voronoi, Noise etc.)")
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        return poll_node_tree(context)

    def invoke(self, context, event):
        space = context.space_data
        node_tree = space.path[-1].node_tree

        nodes_selected = False
        for node in node_tree.nodes:
            if node.select:
                node.node_preview.ignore_scale = not node.node_preview.ignore_scale
                nodes_selected = True

        if not nodes_selected:
            self.report({"ERROR"}, "No nodes selected")
            return {"CANCELLED"}

        force_node_editor_draw()
        return {"FINISHED"}


def get_active_node(context):
    space = context.space_data
    if not space.path:
        return None
    node_tree = space.path[-1].node_tree
    return node_tree.nodes.active

class NODEPREVIEW_OT_set_output(bpy.types.Operator):
    bl_idname = "nodepreview.set_output"
    bl_label = "Set Node Output to Preview"
    bl_description = "On active node: Choose output to show in the node preview thumbnail"
    bl_options = {"UNDO"}

    def update_output(self, context):
        node = get_active_node(context)
        node.node_preview.output_index = int(self.output)
        node.node_preview.auto_choose_output = False

    def callback_output_items(self, context):
        return NODEPREVIEW_OT_set_output.output_items

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

        NODEPREVIEW_OT_set_output.output_items.clear()
        index = 0
        for socket in node.outputs:
            if socket.enabled:
                NODEPREVIEW_OT_set_output.output_items.append((str(index), socket.name, f"Show preview for output {socket.name}", index))
                index += 1

        wm = context.window_manager
        return wm.invoke_popup(self, width=120)

    def draw(self, context):
        layout = self.layout
        node = get_active_node(context)

        layout.label(text=f'Node: "{node.name}"')

        if node.outputs:
            col = layout.column()
            col.label(text="Output:")
            col.prop(node.node_preview, "auto_choose_output")
            col.prop(self, "output", expand=True)
        else:
            layout.label(text="Node has no outputs")

    def execute(self, context):
        return {"FINISHED"}


class NODEPREVIEW_OT_cycle_preview_object(bpy.types.Operator):
    bl_idname = "nodepreview.cycle_preview_object"
    bl_label = "Change Preview Object"
    bl_description = "On selected nodes: Change preview object between plane and sphere"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        return poll_node_tree(context)

    def invoke(self, context, event):
        space = context.space_data
        node_tree = space.path[-1].node_tree

        selection = [node for node in node_tree.nodes if node.select and hasattr(node, "node_preview")]

        if not selection:
            self.report({"ERROR"}, "No nodes selected")
            return {"CANCELLED"}

        initial_state = set([needs_sphere_preview(node) for node in selection])
        if any(initial_state):
            # At least one node was showing a sphere preview
            new_state = "PLANE"
        else:
            new_state = "SPHERE"

        for node in selection:
            node.node_preview.preview_object = new_state

        force_node_editor_draw()
        return {"FINISHED"}


class NodePreviewNodeProps(bpy.types.PropertyGroup):
    def update_enabled(self, context):
        self.enabled_modified = True

    enabled: BoolProperty(default=True, update=update_enabled)
    enabled_modified: BoolProperty(default=False)
    ignore_scale: BoolProperty(default=False)
    auto_choose_output: BoolProperty(default=True, name="Auto", description="Use the first output with an outgoing connection")
    output_index: IntProperty(default=0, min=0)
    preview_object: EnumProperty(name="Preview Object",
                                 items=(("PLANE", "Plane", "Flat Plane", 0),
                                        ("SPHERE", "Sphere", "Sphere", 1),
                                        ("AUTO", "Auto", "Use sphere for surface (BxDF) nodes, plane for everything else", 2)),
                                 default="AUTO")

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
        bpy.types.Node.node_preview = bpy.props.PointerProperty(name=f"{bl_info['name']} Settings", type=cls)

    @classmethod
    def unregister(cls):
        del bpy.types.Node.node_preview


class NodePreviewTreeProps(bpy.types.PropertyGroup):
    enabled: BoolProperty(name="Show Previews", default=True,
                          description="Show thumbnails above the nodes in this node tree")

    @classmethod
    def register(cls):
        bpy.types.NodeTree.node_preview = bpy.props.PointerProperty(name=f"{bl_info['name']} Settings", type=cls)

    @classmethod
    def unregister(cls):
        del bpy.types.NodeTree.node_preview


class NodePreviewPanel:
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = bl_info["name"]

    @classmethod
    def poll(cls, context):
        return poll_node_tree(context)


class NODEPREVIEW_PT_node_tree_settings(bpy.types.Panel, NodePreviewPanel):
    bl_label = "Node Tree Settings"

    def draw(self, context):
        layout = self.layout
        node_tree = context.space_data.path[-1].node_tree
        layout.prop(node_tree.node_preview, "enabled")

        preferences = context.preferences.addons[addon_name].preferences
        layout.prop(preferences, "thumb_scale")
        layout.prop(preferences, "thumb_z_offset")


class NODEPREVIEW_PT_node_tools(bpy.types.Panel, NodePreviewPanel):
    bl_label = "Selected Nodes"

    def draw(self, context):
        layout = self.layout
        layout.operator("nodepreview.toggle_preview")
        layout.operator("nodepreview.cycle_preview_object")


classes = (
    NodePreviewNodeProps,
    NodePreviewTreeProps,
    NODEPREVIEW_OT_open_userprefs,
    NODEPREVIEW_OT_toggle_preview,
    NODEPREVIEW_OT_toggle_ignore_scale,
    NODEPREVIEW_OT_set_output,
    NODEPREVIEW_OT_cycle_preview_object,
    NODEPREVIEW_PT_node_tree_settings,
    NODEPREVIEW_PT_node_tools,
    NODE_PT_node_preview,
)


def _deferred_register():
    # Runs after Blender finishes starting up (real context, e.g. view_layer, is available here,
    # unlike during register() at startup where context is a restricted stub). Must resolve the
    # legacy addon conflict before ANY of this fork's own classes register: once our classes
    # register under the same bl_idnames, Blender silently replaces the old addon's class objects,
    # so the old addon's own unregister() then fails ("missing bl_rna", may not be registered) and
    # never reaches its own addon_remove() cleanup.
    _handle_legacy_addon_conflict()

    register_class(NodePreviewAddonPreferences)

    from .display import display_register
    display_register()

    for cls in classes:
        register_class(cls)

    bpy.types.NODE_HT_header.append(draw_node_header_menu)

    # Register keymap
    wm = bpy.context.window_manager
    keymap = wm.keyconfigs.addon.keymaps.new(name="Node Editor", space_type="NODE_EDITOR")

    keymap_item = keymap.keymap_items.new(NODEPREVIEW_OT_toggle_ignore_scale.bl_idname, "I", "PRESS", ctrl=True, shift=True)
    addon_keymaps.append((keymap, keymap_item))
    keymap_item = keymap.keymap_items.new(NODEPREVIEW_OT_toggle_preview.bl_idname, "P", "PRESS", ctrl=True, shift=True)
    addon_keymaps.append((keymap, keymap_item))
    keymap_item = keymap.keymap_items.new(NODEPREVIEW_OT_set_output.bl_idname, "O", "PRESS", shift=True)
    addon_keymaps.append((keymap, keymap_item))
    keymap_item = keymap.keymap_items.new(NODEPREVIEW_OT_cycle_preview_object.bl_idname, "P", "PRESS", ctrl=True)
    addon_keymaps.append((keymap, keymap_item))
    return None


def register():
    if bpy.app.background:
        # No addon preferences UI/operators to conflict-check against in a headless subprocess
        # (e.g. this addon's own spawned thumbnail-rendering process); register directly.
        register_class(NodePreviewAddonPreferences)
        from . import background
    else:
        # persistent=True にしないと起動直後の .blend 読み込みでタイマーが破棄され、登録が行われない
        bpy.app.timers.register(_deferred_register, first_interval=0.3, persistent=True)


def unregister():
    unregister_class(NodePreviewAddonPreferences)

    if not bpy.app.background:
        bpy.types.NODE_HT_header.remove(draw_node_header_menu)

        from .display import display_unregister
        display_unregister()

        for cls in reversed(classes):
            unregister_class(cls)

        # Unregister keymaps
        for keymap, keymap_item in addon_keymaps:
            keymap.keymap_items.remove(keymap_item)
        addon_keymaps.clear()
