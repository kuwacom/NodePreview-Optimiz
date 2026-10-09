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

# 日本語の訳文。キーは (翻訳コンテキスト, 英語の原文)
# Blender 本体がすでに訳している語（Background, Color, Output, File not found など）は、本体の UI 全体を書き換えないよう含めない

from ..lib.constants import ADDON_NAME

DEFAULT = "*"
OPERATOR = "Operator"

TRANSLATIONS = {
    # アドオン一覧（bl_info）
    (
        DEFAULT,
        "Displays rendered thumbnails above shader nodes",
    ): "シェーダーノードの上にレンダリングしたサムネイルを表示します",
    (DEFAULT, "Shader Node Editor"): "シェーダーノードエディター",
    # アドオン設定
    (DEFAULT, "Previews Visible by Default"): "プレビューを最初から表示",
    (
        DEFAULT,
        "Choose wether the thumbnails should be visible by default or not. "
        "If disabled, thumbnails are only shown after selecting nodes and "
        "pressing Ctrl+Shift+P to make them visible",
    ): "サムネイルを最初から表示するかどうか。オフにすると、ノードを選んで Ctrl+Shift+P を押したときだけ表示されます",
    (DEFAULT, "Update During Animation Playback"): "アニメーション再生中も更新",
    (
        DEFAULT,
        "When disabled, previews will not update while animation playback "
        "is running. Can be used to improve performance of animation playback "
        "in complex scenes",
    ): "オフにすると、アニメーション再生中はプレビューを更新しません。複雑なシーンで再生を軽くしたいときに使います",
    (DEFAULT, "Thumbnail Scale"): "サムネイルの大きさ",
    (DEFAULT, "Size of the thumbnails in the node editor"): "ノードエディター上でのサムネイルの大きさ",
    (DEFAULT, "Vertical Offset"): "縦方向の距離",
    (DEFAULT, "Vertical offset of the thumbnails from the node"): "ノードからサムネイルまでの縦方向の距離",
    (DEFAULT, "Thumbnail Resolution"): "サムネイルの解像度",
    (
        DEFAULT,
        "Higher resolutions preserve fine detail in textures better, but lead to slower updates",
    ): "高くするとテクスチャの細部まで見えますが、更新が遅くなります",
    (DEFAULT, "Max Background Processes"): "裏プロセスの最大数",
    (
        DEFAULT,
        "Maximum number of Blender processes that render thumbnails in parallel. "
        "Higher values update faster, but use more memory",
    ): "サムネイルを並行してレンダリングする Blender の最大数。増やすと更新が速くなりますが、メモリを多く使います",
    (DEFAULT, "Checkerboard Pattern"): "チェッカー柄",
    (
        DEFAULT,
        "The background pattern is visible when parts of a shader are transparent/transmissive",
    ): "シェーダーが透明・透過している部分に見える背景の柄",
    (
        DEFAULT,
        "Visible when parts of a shader are transparent. Note that very dark or saturated background "
        "colors can produce misleading results for thumbnails of colored transparent shaders",
    ): "シェーダーの透明な部分に見える色。暗すぎる色や鮮やかすぎる色にすると、色付きの透明なシェーダーのサムネイルが実際と違って見えることがあります",
    (DEFAULT, "Background:"): "背景:",
    (DEFAULT, "Solid Color"): "単色",
    (DEFAULT, "Color 1"): "カラー 1",
    (DEFAULT, "Color 2"): "カラー 2",
    (DEFAULT, "Show Help Messages"): "ヒントを表示",
    (
        DEFAULT,
        "Show the following help message:\n"
        "Procedural texture scale can be ignored with Ctrl+Shift+I (shown if texture scale is so large "
        "that the texture is no longer recognizable, or if texture scale is driven by another texture",
    ): "次のヒントを表示します:\n"
    "手続き型テクスチャの Scale は Ctrl+Shift+I で無視できます（Scale が大きすぎて模様が分からないときや、"
    "Scale が別のテクスチャで制御されているときに表示）",
    (DEFAULT, "Enable Debug Output"): "デバッグ出力を有効化",
    (DEFAULT, "Print debug information to the system console"): "システムコンソールにデバッグ情報を出力します",
    (
        DEFAULT,
        "Please restart Blender for the change to take effect",
    ): "変更を反映するには Blender を再起動してください",
    (DEFAULT, "Shortcuts:"): "ショートカット:",
    (
        DEFAULT,
        "Ctrl+Shift+P: Toggle thumbnail visibility on selected nodes",
    ): "Ctrl+Shift+P: 選択中のノードのサムネイルの表示を切り替える",
    (
        DEFAULT,
        "Ctrl+Shift+i: Toggle wether to ignore the Scale socket on selected procedural texture nodes",
    ): "Ctrl+Shift+I: 選択中の手続き型テクスチャで Scale を無視するかを切り替える",
    (
        DEFAULT,
        "Shift+O: Set the output to show in the preview thumbnail for the active node",
    ): "Shift+O: アクティブなノードで、プレビューに使う出力を選ぶ",
    (
        DEFAULT,
        "Ctrl+P: Switch between a flat plane and a 3D sphere as preview object on selected nodes",
    ): "Ctrl+P: 選択中のノードのプレビューを平面と球で切り替える",
    (
        DEFAULT,
        "(These shortcuts can be changed in the Keymap settings)",
    ): "（ショートカットはキーマップの設定で変更できます）",
    # ノード / ノードツリー毎の設定
    (DEFAULT, f"{ADDON_NAME} Settings"): f"{ADDON_NAME} の設定",
    (DEFAULT, "Use the first output with an outgoing connection"): "接続されている最初の出力を使います",
    (DEFAULT, "Preview Object"): "プレビューの形状",
    (DEFAULT, "Flat Plane"): "平らな面",
    (
        DEFAULT,
        "Use sphere for surface (BxDF) nodes, plane for everything else",
    ): "サーフェス（BxDF）のノードは球、それ以外は平面を使います",
    (DEFAULT, "Show Previews"): "プレビューを表示",
    (
        DEFAULT,
        "Show thumbnails above the nodes in this node tree",
    ): "このノードツリーのノードの上にサムネイルを表示します",
    # オペレーター
    (OPERATOR, "Toggle Node Previews"): "プレビューの表示を切り替え",
    (
        DEFAULT,
        "On selected nodes: Toggle visibility of the node preview thumbnail on/off",
    ): "選択中のノード: プレビューの表示 / 非表示を切り替えます",
    (OPERATOR, "Toggle Ignore Scale"): "Scale の無視を切り替え",
    (
        DEFAULT,
        "On selected nodes: Toggle wether to ignore procedural texture scale when rendering the node preview "
        "(useful on procedural textures like Voronoi, Noise etc.)",
    ): "選択中のノード: プレビューで手続き型テクスチャの Scale を無視するかを切り替えます（Voronoi や Noise などで便利です）",
    (OPERATOR, "Set Node Output to Preview"): "プレビューする出力を選択",
    (
        DEFAULT,
        "On active node: Choose output to show in the node preview thumbnail",
    ): "アクティブなノード: プレビューに使う出力を選びます",
    (OPERATOR, "Change Preview Object"): "プレビューの形状を切り替え",
    (
        DEFAULT,
        "On selected nodes: Change preview object between plane and sphere",
    ): "選択中のノード: プレビューの形状を平面と球で切り替えます",
    (OPERATOR, "Open Preferences"): "設定を開く",
    (DEFAULT, f"Open the {ADDON_NAME} addon user preferences"): f"{ADDON_NAME} のアドオン設定を開きます",
    (DEFAULT, "No nodes selected"): "ノードが選択されていません",
    (DEFAULT, 'Node: "{}"'): "ノード: 「{}」",
    (DEFAULT, "Output:"): "出力:",
    (DEFAULT, "Node has no outputs"): "このノードには出力がありません",
    (DEFAULT, "Show preview for output {}"): "出力「{}」をプレビューに表示",
    # パネル
    (DEFAULT, f"Settings of the {ADDON_NAME} Addon"): f"{ADDON_NAME} の設定",
    (DEFAULT, "Addon Preferences"): "アドオン設定",
    (DEFAULT, "Node Tree Settings"): "ノードツリーの設定",
    (DEFAULT, "Selected Nodes"): "選択中のノード",
    # サムネイルの上に表示する文字
    (DEFAULT, "Output: {}"): "出力: {}",
    (DEFAULT, "Scale ignored"): "Scale を無視中",
    (DEFAULT, "Scale can be ignored\nwith Ctrl+Shift+i"): "Ctrl+Shift+I で\nScale を無視できます",
    (DEFAULT, "Save .blend to render preview"): ".blend を保存すると表示されます",
    (DEFAULT, "Could not load image"): "画像を読み込めません",
    (DEFAULT, "Unsupported Colorspace: {}"): "未対応のカラースペース: {}",
}
