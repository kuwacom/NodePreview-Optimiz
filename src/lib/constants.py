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

import os
import tomllib

# アドオンのルートモジュール名
# エクステンションとして入れた場合は bl_ext.<リポジトリ>.<id> になるため、固定の文字列にはできない
# AddonPreferences の bl_idname や preferences.addons のキーに使う
ADDON_PACKAGE = __name__.rsplit(".", 3)[0]

SRC_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
ADDON_ROOT_DIR = os.path.dirname(SRC_DIR)

# 表示名は blender_manifest.toml を唯一の定義元にする
with open(os.path.join(ADDON_ROOT_DIR, "blender_manifest.toml"), "rb") as manifest_file:
    ADDON_NAME = tomllib.load(manifest_file)["name"]

SHADERS_DIR = os.path.join(SRC_DIR, "shaders")
PREVIEW_SCENE_PATH = os.path.join(SRC_DIR, "data", "previewscene.blend")

# オペレーターやプロパティなど、Blender に登録する識別子の接頭辞
ID_PREFIX = "nodepreview_optimiz"
# Node / NodeTree に追加するプロパティ名
PROP_NAME = ID_PREFIX

THUMB_CHANNEL_COUNT = 4
SUPPORTED_NODE_TREE = "ShaderNodeTree"

# 裏プロセスがレンダリングしたサムネイルの保存先
TEMP_DIR_PREFIX = "BlenderNodePreviewOptimiz_"
TEMP_DIR_REGEX_PATTERN = TEMP_DIR_PREFIX + r"[0-9]+"


# プレビューの形状 : プレビュー用シーン内のオブジェクト名（Cube と Monkey は裏プロセスの起動時に作る）
PREVIEW_SHAPE_OBJECTS = {
    "PLANE": "Plane",
    "SPHERE": "Sphere",
    "CUBE": "Cube",
    "MONKEY": "Monkey",
}


class BACKGROUND_PATTERNS:
    CHECKER = "CHECKER"
    WHITE = "WHITE"
