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

from .constants import ADDON_PACKAGE, SUPPORTED_NODE_TREE


def get_preferences(context=None):
    """
    ### get_preferences
    @param context - 省略時は bpy.context を使う
    @returns このアドオンの設定
    """
    context = context or bpy.context
    return context.preferences.addons[ADDON_PACKAGE].preferences


def force_node_editor_draw(region_types=("WINDOW",)):
    """
    ### force_node_editor_draw
    開いている全てのノードエディターに再描画を要求する

    @param region_types - 再描画するリージョンの種類（ヘッダーの表示を変えた時は "HEADER" も含める）
    """
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "NODE_EDITOR":
                for region in area.regions:
                    if region.type in region_types:
                        region.tag_redraw()


def poll_node_tree(context):
    """
    ### poll_node_tree
    @returns 対応するノードツリー（シェーダー）を開いているノードエディターなら True
    """
    space = context.space_data
    # Path contains a chain of nested node trees, the last one is the currently active one
    if not getattr(space, "path", False):
        return False
    node_tree = space.path[-1].node_tree
    return space.type == "NODE_EDITOR" and node_tree and space.tree_type == SUPPORTED_NODE_TREE


def get_edited_node_tree(context):
    """
    ### get_edited_node_tree
    @returns ノードエディターで今表示しているノードツリー（グループの中に入っていればそのグループ）
    """
    return context.space_data.path[-1].node_tree


def get_active_node(context):
    """
    ### get_active_node
    @returns 表示中のノードツリーのアクティブノード（無ければ None）
    """
    space = context.space_data
    if not space.path:
        return None
    return get_edited_node_tree(context).nodes.active
