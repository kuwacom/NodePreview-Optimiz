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

from .operators import (
    NODEPREVIEW_OPTIMIZ_OT_cycle_preview_object,
    NODEPREVIEW_OPTIMIZ_OT_set_output,
    NODEPREVIEW_OPTIMIZ_OT_toggle_ignore_scale,
    NODEPREVIEW_OPTIMIZ_OT_toggle_preview,
)

# (オペレーター, キー, 修飾キー)
KEYMAP_DEFINITIONS = (
    (NODEPREVIEW_OPTIMIZ_OT_toggle_ignore_scale, "I", {"ctrl": True, "shift": True}),
    (NODEPREVIEW_OPTIMIZ_OT_toggle_preview, "P", {"ctrl": True, "shift": True}),
    (NODEPREVIEW_OPTIMIZ_OT_set_output, "O", {"shift": True}),
    (NODEPREVIEW_OPTIMIZ_OT_cycle_preview_object, "P", {"ctrl": True}),
)

addon_keymaps = []


def register():
    wm = bpy.context.window_manager
    keymap = wm.keyconfigs.addon.keymaps.new(name="Node Editor", space_type="NODE_EDITOR")

    for operator, key, modifiers in KEYMAP_DEFINITIONS:
        keymap_item = keymap.keymap_items.new(operator.bl_idname, key, "PRESS", **modifiers)
        addon_keymaps.append((keymap, keymap_item))


def unregister():
    for keymap, keymap_item in addon_keymaps:
        keymap.keymap_items.remove(keymap_item)
    addon_keymaps.clear()
