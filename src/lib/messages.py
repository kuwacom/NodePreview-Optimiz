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

# メイン側と裏プロセス側でやり取りするメッセージの種類

STOP = 1
NEW_JOB = 2
JOB_DONE = 3
BACKGROUND_PROCESS_READY = 4
FREE_RESSOURCES = 5
IMAGES_FAILED_TO_LINK = 6
NEW_BLEND_ABSPATH = 7
# 古いジョブなどを処理せずに飛ばしたことの通知。メイン側が次のジョブを送るきっかけにする
JOB_SKIPPED = 8
