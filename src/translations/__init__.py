#
#     This file is part of NodePreview-Optimiz, a fork of Node Preview Reborn.
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

# UI の多言語対応。原文は英語で、Blender の「インターフェイスの翻訳」設定に従って切り替わる
# 言語を増やすときは、同じ形式の辞書を持つモジュールを追加して TRANSLATIONS に登録する

import bpy

from ..lib.constants import ADDON_PACKAGE
from . import ja_jp

# 言語コード : {(翻訳コンテキスト, 原文): 訳文}
TRANSLATIONS = {
    "ja_JP": ja_jp.TRANSLATIONS,
}


def register():
    bpy.app.translations.register(ADDON_PACKAGE, TRANSLATIONS)


def unregister():
    bpy.app.translations.unregister(ADDON_PACKAGE)
