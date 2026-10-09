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

# 描画ハンドラーと、裏プロセスの結果を受け取るスレッドの両方から参照するサムネイルの状態

from . import update_tracker

thumbnails = {}  # node_key : Thumbnail
cached_nodes = {}  # node_key : hash(node_script), timestamp
# Used to decide wether to update only the first or second part of the nodes in a tree in the draw handler
update_first_part = {}  # node_tree : Bool


def prune_tree(tree_key_suffix, current_node_keys):
    """
    ### prune_tree
    消えたノード（削除・名前変更）のサムネイルとキャッシュを捨てる

    @param tree_key_suffix - 対象のツリーの node_key の末尾部分
    @param current_node_keys - 今ツリーにあるノードの node_key の集合
    """
    for cache in (thumbnails, cached_nodes):
        # 裏プロセスの結果を受け取るスレッドが追加し得るため、キーを写してから消す
        for key in list(cache):
            if key.endswith(tree_key_suffix) and key not in current_node_keys:
                cache.pop(key, None)


def forget_rendered(tree_key_suffix):
    """
    ### forget_rendered
    ツリーのノードを「レンダリング済み」として扱わないようにし、次の変換で作り直させる
    （サムネイルは新しい結果が届くまで描き続ける）

    @param tree_key_suffix - 対象のツリーの node_key の末尾部分
    """
    for key in list(cached_nodes):
        if key.endswith(tree_key_suffix):
            cached_nodes.pop(key, None)


def free():
    """
    ### free
    保持しているサムネイルとキャッシュを全て捨てる
    """
    cached_nodes.clear()
    update_first_part.clear()
    thumbnails.clear()
    update_tracker.reset()
