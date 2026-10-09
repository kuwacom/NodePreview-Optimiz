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

# Blender が自動で訳さない文字列（値を埋め込む文字列・レポート・blf で描く文字）を訳すための関数
# 静的な文字列のラベルやプロパティ名は Blender が描画時に訳すため、ここを通さなくて良い

from bpy.app import translations

iface_ = translations.pgettext_iface
tip_ = translations.pgettext_tip
# pgettext_rpt が無い古いバージョンでは、ツールチップと同じ設定で訳す
rpt_ = getattr(translations, "pgettext_rpt", translations.pgettext_tip)


def format_message(message):
    """
    ### format_message
    裏プロセスから受け取ったメッセージを、今の言語で文字列にする

    @param message - (書式文字列, 引数のタプル)。メッセージが無い場合は None
    @returns 表示する文字列（メッセージが無い場合は空文字）
    """
    if not message:
        return ""
    template, args = message
    return iface_(template).format(*args)
