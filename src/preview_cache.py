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


def free():
    """
    ### free
    保持しているサムネイルとキャッシュを全て捨てる
    """
    cached_nodes.clear()
    update_first_part.clear()
    thumbnails.clear()
    update_tracker.reset()
