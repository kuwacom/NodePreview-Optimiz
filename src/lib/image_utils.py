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


def needs_linking(image):
    """
    ### needs_linking
    裏プロセスでファイルから読めず、.blend からリンクする必要がある画像か（パック済み・生成画像）

    @param image - 判定する画像
    @returns リンクが必要なら True
    """
    return bool(image.packed_file) or image.source == "GENERATED"


def get_blend_abspath():
    """
    ### get_blend_abspath
    @returns 今開いている .blend の絶対パス（未保存なら空文字）
    """
    return bpy.path.abspath(bpy.data.filepath)


def get_image_linking_info(image):
    """
    ### get_image_linking_info
    @param image - 対象の画像
    @returns (画像名, 画像を含む .blend の絶対パス)
    """
    # Note: for linking, we need the original image name as it appears in the library .blend file
    return image.name, bpy.path.abspath(image.library.filepath) if image.library else get_blend_abspath()
