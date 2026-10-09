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

# 変更の無い再描画（パン・ズーム・マウス移動）で重い変換処理を丸ごと省くための変更検知

import bpy
from bpy.app.handlers import persistent

from . import node_converter
from .lib.node_utils import get_node_settings

update_generation = 0  # ノード等に変更が入るたびに増える世代番号
processed_state = {}  # node_tree : (update_generation, signature, 処理済みパート数)
group_script_cache = {}  # frozenset(ノードグループ名) : node_groups_to_script の結果
# この型の ID が更新されたときだけサムネイルが変わり得る
WATCHED_ID_TYPES = (bpy.types.Material, bpy.types.World, bpy.types.Light, bpy.types.NodeTree, bpy.types.Image)


def request_update():
    """
    ### request_update
    次の再描画でサムネイル用スクリプトの再変換を行わせる（別スレッドから呼んでも良い）
    """
    global update_generation
    update_generation += 1


def invalidate_caches():
    """
    ### invalidate_caches
    ノードグループ変換のキャッシュを破棄し、再変換を要求する
    """
    group_script_cache.clear()
    request_update()


def reset():
    """
    ### reset
    .blend の読み込み時などに、変更検知の状態を全て捨てる
    """
    processed_state.clear()
    invalidate_caches()


def get_group_script(node_tree_hierarchy):
    """
    ### get_group_script
    編集中の階層から参照されるノードグループだけを変換し、結果をキャッシュする

    @param node_tree_hierarchy - 編集中のノードツリー階層
    @returns node_groups_to_script の戻り値
    """
    used_groups = node_converter.collect_used_node_groups(node_tree_hierarchy)
    cache_key = frozenset(group.name_full for group in used_groups)
    try:
        return group_script_cache[cache_key]
    except KeyError:
        result = node_converter.node_groups_to_script(used_groups)
        group_script_cache[cache_key] = result
        return result


def make_update_signature(context, node_tree, node_tree_hierarchy, node_tree_owner, preferences):
    """
    ### make_update_signature
    depsgraph の通知が来ない変更（設定・エンジン・ノード毎のプレビュー設定など）を検出するための値を作る

    @returns 前回と比較するためのタプル
    """
    node_settings = []
    for node in node_tree.nodes:
        props = get_node_settings(node)
        if props is None:
            continue
        node_settings.append(
            (
                node.name,
                props.enabled,
                props.enabled_modified,
                props.ignore_scale,
                props.auto_choose_output,
                props.output_index,
                props.preview_object,
                props.force_update_counter,
            )
        )

    # Group Input の解決に親ツリーのアクティブノード（グループのインスタンス）が使われるため含める
    parent_active_nodes = tuple(
        tree.nodes.active.name if tree.nodes.active else None for tree in node_tree_hierarchy[:-1]
    )

    return (
        node_tree_owner.as_pointer() if node_tree_owner else None,
        tuple(tree.as_pointer() for tree in node_tree_hierarchy),
        parent_active_nodes,
        context.scene.render.engine,
        preferences.previews_enabled_by_default,
        preferences.thumb_resolution,
        preferences.surface_preview_shape,
        preferences.background_pattern,
        tuple(preferences.background_color_1),
        tuple(preferences.background_color_2),
        tuple(node_settings),
    )


@persistent
def depsgraph_update_post(scene, depsgraph):
    for update in depsgraph.updates:
        if isinstance(update.id, WATCHED_ID_TYPES):
            invalidate_caches()
            return


def register():
    bpy.app.handlers.depsgraph_update_post.append(depsgraph_update_post)


def unregister():
    bpy.app.handlers.depsgraph_update_post.remove(depsgraph_update_post)
