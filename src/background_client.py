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

# メイン側から裏プロセス（サムネイルをレンダリングする別の Blender）を起動し、やり取りする

import atexit
import os
import platform
import re
import shutil
import subprocess
import tempfile
import threading
from collections import OrderedDict
from multiprocessing import current_process
from multiprocessing.connection import Connection, Listener
from time import sleep, time

import bpy
from bpy.app.handlers import persistent

from . import preview_cache, update_tracker
from .lib import messages
from .lib.constants import (
    ADDON_PACKAGE,
    PREVIEW_SCENE_PATH,
    SUPPORTED_NODE_TREE,
    TEMP_DIR_PREFIX,
    TEMP_DIR_REGEX_PATTERN,
    THUMB_CHANNEL_COUNT,
)
from .lib.editor_utils import force_node_editor_draw, get_preferences
from .lib.logger import addon_print
from .lib.node_utils import get_node_settings
from .thumbnail import Thumbnail

# Output directory where rendered thumbnails are saved by our Blender sub-process
temp_dir = os.path.join(tempfile.gettempdir(), f"{TEMP_DIR_PREFIX}{os.getpid()}")

images_failed_to_link_lock = threading.Lock()
images_failed_to_link = set()

background_process_ready = False
background_process: subprocess.Popen | None = None
listener: Listener | None = None
connection: Connection | None = None

# 送信待ちのジョブ（node_key : job）。同じノードは最新のジョブだけを残し、最後に追加したものから送る
pending_jobs = OrderedDict()
# 裏プロセスが処理中のジョブがあるか。処理中は次のジョブを送らず、送信待ちの中で古いジョブを上書きさせる
background_process_busy = False
# 描画ハンドラー（メインスレッド）と WatcherThread の両方から送信するため、送信と送信待ちの操作をまとめて守る
send_lock = threading.RLock()


class WatcherThread(threading.Thread):
    """
    # WatcherThread
    裏プロセスからのメッセージ（準備完了・レンダリング結果など）を受け取り続けるスレッド
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, daemon=True, **kwargs)
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def stopped(self):
        return self._stop_event.is_set()

    def run(self):
        while not self.stopped():
            if connection.poll(timeout=0.05):
                msg = connection.recv()
                tag, data = msg

                if tag == messages.BACKGROUND_PROCESS_READY:
                    global background_process_ready
                    background_process_ready = True
                    # Force one refresh to render all nodes that are currently visible
                    force_node_editor_draw()
                    dispatch_jobs()
                elif tag == messages.JOB_DONE:
                    node_key, result_array, thumb_resolution, job_timestamp, error_message, full_error_log = data

                    if full_error_log:
                        addon_print(full_error_log)

                    preview_cache.thumbnails[node_key] = Thumbnail(
                        result_array, thumb_resolution, thumb_resolution, THUMB_CHANNEL_COUNT, error_message
                    )

                    try:
                        last_timestamp = preview_cache.cached_nodes[node_key][1]
                        if job_timestamp < last_timestamp:
                            # Force re-sending the job if the last job didn't go through
                            del preview_cache.cached_nodes[node_key]
                            # 再送は変換処理の中で行われるため、スキップされないよう更新を要求する
                            update_tracker.request_update()
                    except KeyError:
                        pass

                    force_node_editor_draw()
                    on_job_finished()
                elif tag == messages.JOB_SKIPPED:
                    on_job_finished()
                elif tag == messages.IMAGES_FAILED_TO_LINK:
                    with images_failed_to_link_lock:
                        images_failed_to_link.update(data)


watcher_thread: WatcherThread | None = None


def is_ready():
    """
    ### is_ready
    @returns 裏プロセスがジョブを受け付けられる状態なら True
    """
    return background_process_ready


def send_message(tag, data=None):
    """
    ### send_message
    裏プロセスにメッセージを送る（どのスレッドから呼んでも良い）
    """
    with send_lock:
        connection.send((tag, data))


def submit_jobs(jobs):
    """
    ### submit_jobs
    サムネイルのレンダリングを依頼する。同じノードの未送信のジョブは新しいもので置き換える

    @param jobs - preview_drawer で組み立てたジョブ。後ろにあるものほど先に処理される
    """
    with send_lock:
        for job in jobs:
            node_key = job[0]
            pending_jobs.pop(node_key, None)
            pending_jobs[node_key] = job
    dispatch_jobs()


def dispatch_jobs():
    """
    ### dispatch_jobs
    裏プロセスが空いていれば、送信待ちのジョブを 1 件送る
    """
    global background_process_busy
    with send_lock:
        if not background_process_ready or background_process_busy or not pending_jobs:
            return
        _, job = pending_jobs.popitem(last=True)
        background_process_busy = True
        send_message(messages.NEW_JOB, job)


def on_job_finished():
    global background_process_busy
    with send_lock:
        background_process_busy = False
    dispatch_jobs()


def clear_pending_jobs():
    global background_process_busy
    with send_lock:
        pending_jobs.clear()
        background_process_busy = False


def stop_threads_and_process():
    global watcher_thread, connection, listener, background_process, background_process_ready
    background_process_ready = False
    clear_pending_jobs()

    if watcher_thread:
        watcher_thread.stop()
        watcher_thread.join(timeout=0.2)
        watcher_thread = None

    if connection:
        send_message(messages.STOP)
        connection.close()
        connection = None

    if listener:
        listener.close()
        listener = None

    if background_process:
        try:
            background_process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            background_process.kill()
            background_process.communicate()
            addon_print("Background Process was killed after timeout.")

        background_process = None


def clean_temp_dir():
    os_temp_dir = os.path.dirname(temp_dir)
    addon_temp_dirs = [
        os.path.join(os_temp_dir, name) for name in os.listdir(os_temp_dir) if re.match(TEMP_DIR_REGEX_PATTERN, name)
    ]

    for path in addon_temp_dirs:
        try:
            # Only delete old temp dirs. Recent ones might still be in use by another Blender process.
            seconds_since_last_modification = time() - os.path.getmtime(path)
            if seconds_since_last_modification > 60 * 60 * 24:
                shutil.rmtree(path)
        except Exception as error:
            addon_print("Could not delete temp dir:", path)
            addon_print(error)


def update_blend_path():
    def notify_new_blend_loaded():
        while not background_process_ready:
            sleep(1 / 60)
        send_message(messages.NEW_BLEND_ABSPATH, bpy.path.abspath(bpy.data.filepath))

    if background_process_ready:
        notify_new_blend_loaded()
    else:
        # Wait until the process is ready to receive the message, because it must
        # arrive, otherwise all future jobs will be ignored
        notifier = threading.Thread(target=notify_new_blend_loaded, daemon=True)
        notifier.start()


def force_update_failed_images(node_trees):
    for node_tree in node_trees:
        for node in node_tree.nodes:
            if getattr(node, "image", None) and node.image.name in images_failed_to_link:
                get_node_settings(node).force_update()


@persistent
def load_pre(_=None):
    preview_cache.free()
    # 前の .blend 用のジョブは送っても裏プロセスで捨てられるだけなので、送る前に消す
    with send_lock:
        pending_jobs.clear()
    # Delete images in the background process to free up RAM
    if background_process_ready:
        send_message(messages.FREE_RESSOURCES)


@persistent
def load_post(arg1, arg2):
    update_blend_path()


@persistent
def save_post(arg1, arg2):
    update_blend_path()

    with images_failed_to_link_lock:
        if images_failed_to_link:
            force_update_failed_images(mat.node_tree for mat in bpy.data.materials if mat.node_tree)
            force_update_failed_images(
                node_tree for node_tree in bpy.data.node_groups if node_tree.bl_idname == SUPPORTED_NODE_TREE
            )

        force_node_editor_draw()
        images_failed_to_link.clear()


def exit_callback():
    stop_threads_and_process()
    preview_cache.free()
    clean_temp_dir()


def start_background_process():
    authkey = current_process().authkey
    global listener

    port = 6000
    while port < 10000:
        try:
            listener = Listener(("localhost", port), authkey=authkey)
            break
        except OSError as error:
            if (
                (platform.system() == "Windows" and error.errno == 10048)
                or (platform.system() == "Linux" and error.errno == 98)
                or (platform.system() == "Darwin" and error.errno == 48)
            ):
                # Windows: [WinError 10048] Only one usage of each socket address (protocol/network address/port) is normally permitted
                # Linux: [Errno 98] Address already in use
                # macOS: [Errno 48] Address already in use
                port += 1
            else:
                raise

    global background_process
    # import 文ではフォルダ名にハイフンなどを含むと構文エラーになるため、importlib で読み込む
    worker_module = f"{ADDON_PACKAGE}.src.background_worker"
    process_args = [
        bpy.app.binary_path,
        "--factory-startup",
        "--addons",
        ADDON_PACKAGE,
        "-b",  # Run in background without UI
        PREVIEW_SCENE_PATH,
        "--python-expr",
        f"import importlib; importlib.import_module({worker_module!r}).run({port}, {authkey})",
    ]

    env_copy = os.environ.copy()

    for custom_script_dir in bpy.context.preferences.filepaths.script_directories:
        # Only use the custom script dir if the addon is installed there. If BLENDER_USER_SCRIPTS is set, but the addon
        # is installed in the default location, the background process will fail to import the addon.
        if os.path.exists(os.path.join(custom_script_dir.directory, "addons", ADDON_PACKAGE)):
            env_copy["BLENDER_USER_SCRIPTS"] = custom_script_dir.directory
            break

    if get_preferences().enable_debug_output:
        background_process = subprocess.Popen(process_args, env=env_copy)
    else:
        background_process = subprocess.Popen(
            process_args, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, env=env_copy
        )

    global connection
    connection = listener.accept()

    global watcher_thread
    watcher_thread = WatcherThread()
    watcher_thread.start()


def register():
    # Make sure we only register the callback once
    atexit.unregister(exit_callback)
    atexit.register(exit_callback)

    bpy.app.handlers.load_pre.append(load_pre)
    bpy.app.handlers.load_post.append(load_post)
    bpy.app.handlers.save_post.append(save_post)

    # In case the background process throws an exception, the process_starter thread could get stuck
    # on listener.accept(). Enable the daemon flag to make sure the Blender process doesn't hang after
    # quit when this happens.
    process_starter = threading.Thread(target=start_background_process, daemon=True)
    process_starter.start()

    # 遅延登録のため load_post を取り逃しており、blend のパスが裏プロセスに伝わらず全ジョブが破棄されてしまう
    update_blend_path()


def unregister():
    bpy.app.handlers.load_pre.remove(load_pre)
    bpy.app.handlers.load_post.remove(load_post)
    bpy.app.handlers.save_post.remove(save_post)
    stop_threads_and_process()
    preview_cache.free()
