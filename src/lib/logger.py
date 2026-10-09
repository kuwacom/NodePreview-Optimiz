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

from .constants import ADDON_NAME


def addon_print(*args, **kwargs):
    """
    ### addon_print
    メイン側（UI のある Blender）のログをシステムコンソールに出す
    """
    print(f"[{ADDON_NAME}]", *args, **kwargs)


def background_print(*args, **kwargs):
    """
    ### background_print
    裏プロセス側のログをシステムコンソールに出す（Enable Debug Output が有効な時だけ表示される）
    """
    print(f"[{ADDON_NAME} BG Process]", *args, **kwargs)
