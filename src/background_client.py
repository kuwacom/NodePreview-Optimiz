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
import traceback
from collections import OrderedDict
from multiprocessing import current_process
from multiprocessing.connection import Listener
from time import time

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

# 送信待ちのジョブ（node_key : job）。同じノードは最新のジョブだけを残し、最後に追加したものから送る
pending_jobs = OrderedDict()
# 描画ハンドラー（メインスレッド）と各裏プロセスの受信スレッドから送信するため、送信と送信待ちの操作をまとめて守る
send_lock = threading.RLock()
# 最後の描画で画面内にあったノード。これらのジョブを優先して送る
visible_node_keys = frozenset()
# 裏プロセスに伝える .blend のパス。bpy.data はメインスレッドでしか触らないため、ここに写しておく
current_blend_abspath = ""

# 起動中の裏プロセス。ジョブが溜まった時だけ、設定の最大数まで増やす
processes = []

# 裏プロセスが予期せず終了した時は自動で起動し直すが、起動直後に落ち続ける場合に繰り返さないよう回数を制限する
MAX_CRASHES = 3
CRASH_WINDOW_SECONDS = 60
crash_times = []
gave_up_restarting = False
# 最後に起きた起動失敗・異常終了の内容（停止中の表示に使う）
last_error = ""


class STATUS:
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"


class BackgroundProcess:
    """
    # BackgroundProcess
    サムネイルをレンダリングする裏プロセス 1 つ分の起動・通信・状態

    ### 特徴
    - 1 度に 1 件のジョブだけを処理させ、終わったら次を送る
    - 準備完了の通知を受けたら、ジョブより先に .blend のパスを送る
    - 予期せず終了したら、処理中だったジョブを送信待ちに戻して起動し直す
    """

    def __init__(self):
        self.process: subprocess.Popen | None = None
        self.listener: Listener | None = None
        self.connection = None
        self.ready = False
        # 処理中のジョブ（空いていれば None）。裏プロセスが落ちた時に送り直すため丸ごと持つ
        self.busy_job = None
        self._stop_event = threading.Event()

    @property
    def busy_node_key(self):
        return self.busy_job[0] if self.busy_job else None

    def start(self):
        # In case the background process throws an exception, the process_starter thread could get stuck
        # on listener.accept(). Enable the daemon flag to make sure the Blender process doesn't hang after
        # quit when this happens.
        threading.Thread(target=self._start_and_watch, daemon=True).start()

    def send(self, tag, data=None):
        with send_lock:
            self.connection.send((tag, data))

    def stop(self):
        self.ready = False
        self._stop_event.set()

        if self.connection:
            try:
                self.send(messages.STOP)
            except OSError:
                # 裏プロセスが既に終了している
                pass
            self.connection.close()
            self.connection = None

        if self.listener:
            self.listener.close()
            self.listener = None

        if self.process:
            try:
                self.process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.communicate()
                addon_print("Background Process was killed after timeout.")

            self.process = None

    def _start_and_watch(self):
        global last_error
        try:
            connected = self._start_and_connect()
        except Exception as error:
            # 別スレッドの例外は黙って消えてしまい、原因が分からないまま起動中のままになるため記録する
            last_error = f"{type(error).__name__}: {error}"
            addon_print("Could not start the background process:\n" + traceback.format_exc())
            self._on_unexpected_exit()
            return
        if connected:
            self._watch()

    def _start_and_connect(self):
        """
        ### _start_and_connect
        裏プロセスを起動して接続を待つ

        @returns 接続できたら True。待っている間に停止・終了した場合は False
        """
        authkey = current_process().authkey

        port = 6000
        while port < 10000:
            try:
                self.listener = Listener(("localhost", port), authkey=authkey)
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
            self.process = subprocess.Popen(process_args, env=env_copy)
        else:
            self.process = subprocess.Popen(
                process_args, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, env=env_copy
            )
        # 接続前に落ちると accept() が戻らないため、終了を別スレッドで見張って listener を閉じる
        threading.Thread(target=self._wait_for_exit, daemon=True).start()

        try:
            self.connection = self.listener.accept()
        except OSError:
            # 停止処理、または裏プロセスの終了で listener が閉じられた
            return False
        return True

    def _wait_for_exit(self):
        process = self.process
        process.wait()
        if not self._stop_event.is_set():
            self._on_unexpected_exit()

    def _on_unexpected_exit(self):
        global last_error
        with send_lock:
            # 受信スレッドと終了待ちスレッドの両方から呼ばれ得るため、最初の 1 回だけ処理する
            if self._stop_event.is_set():
                return
            self._stop_event.set()
            self.ready = False
            job, self.busy_job = self.busy_job, None
            if job and job[0] not in pending_jobs:
                pending_jobs[job[0]] = job
            if self in processes:
                processes.remove(self)

        for closable in (self.connection, self.listener):
            try:
                if closable:
                    closable.close()
            except OSError:
                pass
        exit_code = self.process.poll() if self.process else None
        if exit_code is not None:
            last_error = f"Background process exited with code {exit_code}"
            addon_print(
                f"Background process exited unexpectedly (exit code {exit_code}). "
                "Enable Debug Output in the add-on preferences to see its log"
            )
        on_process_crashed()

    def _watch(self):
        """裏プロセスからのメッセージ（準備完了・レンダリング結果など）を受け取り続ける"""
        while not self._stop_event.is_set():
            try:
                if not self.connection.poll(timeout=0.05):
                    continue
                tag, data = self.connection.recv()
            except (OSError, EOFError, AttributeError):
                # 停止処理で接続が閉じられた、または裏プロセスが終了した
                self._on_unexpected_exit()
                return

            try:
                self._handle_message(tag, data)
            except Exception:
                # 1 件の処理に失敗しても受信は続ける（スレッドごと止まると以降の結果を受け取れなくなる）
                addon_print("Error while handling a message from the background process:\n" + traceback.format_exc())

    def _handle_message(self, tag, data):
        if tag == messages.BACKGROUND_PROCESS_READY:
            # ジョブより先に届かないと全てのジョブが古い .blend 用として捨てられるため、最初に送る
            self.send(messages.NEW_BLEND_ABSPATH, current_blend_abspath)
            self.ready = True
            # Force one refresh to render all nodes that are currently visible
            force_node_editor_draw(("WINDOW", "HEADER"))
            dispatch_jobs()
        elif tag == messages.JOB_DONE:
            try:
                on_job_done(data)
            finally:
                # 結果の処理に失敗しても、処理中のままにすると以降のジョブが送られなくなる
                self._finish_job()
        elif tag == messages.JOB_SKIPPED:
            self._finish_job()
        elif tag == messages.IMAGES_FAILED_TO_LINK:
            with images_failed_to_link_lock:
                images_failed_to_link.update(data)

    def _finish_job(self):
        with send_lock:
            self.busy_job = None
        dispatch_jobs()


def on_process_crashed():
    global gave_up_restarting
    now = time()
    crash_times[:] = [crashed_at for crashed_at in crash_times if now - crashed_at < CRASH_WINDOW_SECONDS]
    crash_times.append(now)

    if len(crash_times) > MAX_CRASHES:
        gave_up_restarting = True
        addon_print("Background process keeps crashing, stopped restarting it")
    elif not processes:
        # 残りの裏プロセスがあれば、足りない分はジョブが溜まった時に増える
        start_process()
    dispatch_jobs()
    force_node_editor_draw(("WINDOW", "HEADER"))


def get_status():
    """
    ### get_status
    @returns 裏プロセス全体の状態（STATUS のいずれか）
    """
    if gave_up_restarting:
        return STATUS.STOPPED
    if any(process.ready for process in processes):
        return STATUS.RUNNING
    return STATUS.STARTING


def on_job_done(data):
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


def is_ready():
    """
    ### is_ready
    @returns ジョブを受け付けられる裏プロセスが 1 つ以上あれば True
    """
    return any(process.ready for process in processes)


def broadcast(tag, data=None):
    """
    ### broadcast
    準備のできている全ての裏プロセスにメッセージを送る
    """
    with send_lock:
        for process in processes:
            if process.ready:
                process.send(tag, data)


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


def _pick_job(in_flight):
    candidates = [key for key in reversed(pending_jobs) if key not in in_flight]
    if not candidates:
        return None
    # 同じノードを 2 つの裏プロセスで同時に描くと、同じファイルに書き込んでしまうため避ける
    node_key = next((key for key in candidates if key in visible_node_keys), candidates[0])
    return pending_jobs.pop(node_key)


def dispatch_jobs():
    """
    ### dispatch_jobs
    空いている裏プロセスに送信待ちのジョブを送る。全て埋まっていれば、最大数まで裏プロセスを増やす
    """
    with send_lock:
        in_flight = {process.busy_node_key for process in processes if process.busy_node_key}
        for process in processes:
            if not process.ready or process.busy_node_key is not None:
                continue
            job = _pick_job(in_flight)
            if job is None:
                break
            process.busy_job = job
            in_flight.add(job[0])
            try:
                process.send(messages.NEW_JOB, job)
            except OSError:
                # 送信中に裏プロセスが落ちた。ジョブは終了の検知で送信待ちに戻る
                pass

        starting = sum(1 for process in processes if not process.ready)
        waiting = len(pending_jobs) - len(in_flight & pending_jobs.keys())
        if not gave_up_restarting and waiting > starting and len(processes) < get_max_processes():
            start_process()


def get_max_processes():
    return get_preferences().max_background_processes


def start_process():
    process = BackgroundProcess()
    processes.append(process)
    process.start()


def set_visible_node_keys(node_keys):
    """
    ### set_visible_node_keys
    画面内にあるノードを知らせ、それらのジョブを先に処理させる

    @param node_keys - 画面内にあるノードの node_key の集合
    """
    global visible_node_keys
    visible_node_keys = frozenset(node_keys)


def stop_threads_and_process():
    with send_lock:
        pending_jobs.clear()
        stopping = list(processes)
        processes.clear()
    for process in stopping:
        process.stop()


def restart_processes():
    """
    ### restart_processes
    裏プロセスを全て止めてから 1 つ起動し直す（最大数の変更時や、ユーザーによる再起動）
    """
    global gave_up_restarting, last_error
    gave_up_restarting = False
    last_error = ""
    crash_times.clear()
    stop_threads_and_process()
    preview_cache.cached_nodes.clear()
    update_tracker.request_update()
    start_process()
    force_node_editor_draw(("WINDOW", "HEADER"))


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
    global current_blend_abspath
    current_blend_abspath = bpy.path.abspath(bpy.data.filepath)
    # 準備中の裏プロセスには、準備完了時に送られる
    broadcast(messages.NEW_BLEND_ABSPATH, current_blend_abspath)


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
    broadcast(messages.FREE_RESSOURCES)


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


def register():
    # Make sure we only register the callback once
    atexit.unregister(exit_callback)
    atexit.register(exit_callback)

    bpy.app.handlers.load_pre.append(load_pre)
    bpy.app.handlers.load_post.append(load_post)
    bpy.app.handlers.save_post.append(save_post)

    # 遅延登録のため load_post を取り逃しているので、ここで今の .blend のパスを控える
    update_blend_path()
    start_process()


def unregister():
    bpy.app.handlers.load_pre.remove(load_pre)
    bpy.app.handlers.load_post.remove(load_post)
    bpy.app.handlers.save_post.remove(save_post)
    stop_threads_and_process()
    preview_cache.free()
