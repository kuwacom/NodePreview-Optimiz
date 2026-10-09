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
from bpy.utils import register_class, unregister_class

from . import preferences


def _ui_modules():
    # UI 用のモジュールは GPU などを使うため、裏プロセス（-b）では読み込まない
    from . import background_client, keymaps, operators, preview_drawer, properties, ui, update_tracker

    return properties, operators, ui, keymaps, update_tracker, preview_drawer, background_client


def _deferred_register():
    # Runs after Blender finishes starting up (real context, e.g. view_layer, is available here,
    # unlike during register() at startup where context is a restricted stub).
    for module in _ui_modules():
        for cls in getattr(module, "classes", ()):
            register_class(cls)
        if hasattr(module, "register"):
            module.register()
    return None


def register():
    for cls in preferences.classes:
        register_class(cls)

    if not bpy.app.background:
        # persistent=True にしないと起動直後の .blend 読み込みでタイマーが破棄され、登録が行われない
        bpy.app.timers.register(_deferred_register, first_interval=0.3, persistent=True)


def unregister():
    if not bpy.app.background:
        if bpy.app.timers.is_registered(_deferred_register):
            # 遅延登録の前に無効化された場合は、登録されていないものを解除しようとしないようにする
            bpy.app.timers.unregister(_deferred_register)
        else:
            for module in reversed(_ui_modules()):
                if hasattr(module, "unregister"):
                    module.unregister()
                for cls in reversed(getattr(module, "classes", ())):
                    unregister_class(cls)

    for cls in reversed(preferences.classes):
        unregister_class(cls)
