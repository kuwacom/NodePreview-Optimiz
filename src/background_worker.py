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

import os
import queue
import threading
from multiprocessing.connection import Client
from time import perf_counter, time

import bpy
import numpy as np
from bpy_extras.image_utils import load_image

from .lib import messages
from .lib.constants import ID_PREFIX, THUMB_CHANNEL_COUNT
from .lib.image_utils import get_image_linking_info
from .lib.logger import background_print

jobs = queue.LifoQueue()
results = queue.SimpleQueue()
images_failed_to_link = queue.SimpleQueue()
node_timestamps = {}
free_requested = False
stop_requested = False
current_blend_abspath = ""

# 4.0 で Raw は無くなり、リニアは Linear Rec.709 に改名された
COLORSPACES_SUPPORTED = {"sRGB", "Linear Rec.709", "Non-Color"}
COLORSPACES_GAMMA_CORRECTED = {"sRGB", "Filmic sRGB"}
# 読み込んだ画像の元パスを覚えておくカスタムプロパティ名
IMAGE_ABSPATH_KEY = f"{ID_PREFIX}_abspath"


def free():
    """Must be executed from main thread!"""
    background_print("Freeing ressources")
    images = bpy.data.images
    for image in images:
        images.remove(image)

    node_timestamps.clear()

    # TODO better thread-safe way to clear a SimpleQueue?
    while not images_failed_to_link.empty():
        try:
            images_failed_to_link.get(block=False)
        except queue.Empty:
            pass


def watcher_func(wakeup_condition, port, authkey):
    with Client(("localhost", port), authkey=authkey) as connection:
        try:
            connection.send((messages.BACKGROUND_PROCESS_READY, None))

            while True:
                # background_print("Listener: polling")
                if connection.poll(timeout=0.05):
                    try:
                        msg = connection.recv()
                        tag, data = msg
                    except EOFError as error:
                        background_print(error)
                        tag = messages.STOP

                    if tag == messages.NEW_JOB:
                        with wakeup_condition:
                            jobs.put(data)
                            wakeup_condition.notify()
                    elif tag == messages.NEW_BLEND_ABSPATH:
                        global current_blend_abspath
                        current_blend_abspath = data
                        background_print("New .blend abspath:", current_blend_abspath)
                    elif tag == messages.FREE_RESSOURCES:
                        with wakeup_condition:
                            global free_requested
                            free_requested = True
                            wakeup_condition.notify()
                    elif tag == messages.STOP:
                        background_print("Listener: Stopping")
                        break

                while not results.empty():
                    try:
                        result = results.get(block=False)
                        connection.send((messages.JOB_DONE, result))
                    except queue.Empty:
                        pass

                while not images_failed_to_link.empty():
                    try:
                        image_names = images_failed_to_link.get(block=False)
                        connection.send((messages.IMAGES_FAILED_TO_LINK, image_names))
                    except queue.Empty:
                        pass

        except ConnectionResetError as error:
            background_print(error)

    with wakeup_condition:
        # No lock required because this operation is atomic in CPython
        global stop_requested
        stop_requested = True
        wakeup_condition.notify()


def run(port, authkey):
    global free_requested

    wakeup_condition = threading.Condition()

    watcher = threading.Thread(target=watcher_func, args=(wakeup_condition, port, authkey))
    watcher.start()

    while True:
        with wakeup_condition:
            while jobs.empty() and not stop_requested and not free_requested:
                wakeup_condition.wait()

        if stop_requested:
            break

        if free_requested:
            free()
            free_requested = False

        try:
            job = jobs.get(block=False)

            start = perf_counter()
            success, result = do(job)

            if success:
                elapsed = perf_counter() - start
                background_print(f"job done in {elapsed:.3f} s")
                results.put(result)
        except queue.Empty:
            continue

    watcher.join()


def do(job):
    (
        node_key,
        script,
        images_to_load,
        images_to_link,
        image_info,
        blend_abspath,
        thumb_path,
        thumb_resolution,
        timestamp,
    ) = job
    failure = False, None

    try:
        # print("\nScript: --------------------\n")
        # print(node_key, "\n")
        # print("import bpy")
        # print(script)
        # print("--------------------\n")

        try:
            last_timestamp = node_timestamps[node_key]
            if timestamp < last_timestamp:
                # Job is outdated, ignore it (a newer job was already completed)
                return failure
        except KeyError:
            pass

        if blend_abspath != current_blend_abspath:
            # Job is outdated, ignore it (another .blend was loaded)
            return failure

        # Link images from .blend files
        loaded_images = set()
        for image in bpy.data.images:
            loaded_images.add(get_image_linking_info(image))

        new_images_to_link = images_to_link - loaded_images

        blendpath_image_mapping = {}
        for image_name, blendpath in new_images_to_link:
            try:
                blendpath_image_mapping[blendpath].add(image_name)
            except KeyError:
                blendpath_image_mapping[blendpath] = {image_name}

        for blendpath in blendpath_image_mapping.keys():
            image_names = blendpath_image_mapping[blendpath]
            if os.path.isfile(blendpath):
                with bpy.data.libraries.load(blendpath, link=True) as (data_from, data_to):
                    data_to.images = [name for name in data_from.images if name in image_names]

                for name in image_names:
                    if (name, blendpath) not in bpy.data.images:
                        # The image could not be linked, probably because it doesn't exist (yet) in the .blend.
                        # Can e.g. happen if a new generated image is created and used in a node without saving the .blend.
                        images_failed_to_link.put({name})
            else:
                # .blend doesn't exist (e.g. because it was not saved yet)
                background_print(".blend doesn't exist:", blendpath)
                images_failed_to_link.put(image_names)

        # メイン側で今の言語に訳せるよう、(書式文字列, 引数) の形で返す
        error_message = None
        full_error_log = ""

        # Load images from disk
        for image_name, library_path, abspath, colorspace in images_to_load:
            need_to_load = False
            if (image_name, library_path) not in bpy.data.images:
                background_print("loading image", image_name, "for the first time")
                need_to_load = True
            else:
                old_image = bpy.data.images[image_name]
                old_abspath = old_image.get(IMAGE_ABSPATH_KEY, "")
                # Ignore images without old abspath. These were linked in successfully already
                if old_abspath and old_abspath != abspath:
                    background_print("replacing image", image_name, "because the path changed")
                    bpy.data.images.remove(old_image)
                    need_to_load = True
                elif old_image.colorspace_settings.name != colorspace:
                    background_print("replacing image", image_name, "because the colorspace changed")
                    bpy.data.images.remove(old_image)
                    need_to_load = True

            if need_to_load:
                # Load full resolution image and scale it down.
                # I'm copying the loaded and scaled image pixels into a new image because of this Blender bug:
                # https://developer.blender.org/T85772 (it would cause the scaled image to revert back to full size after rendering)
                temp_image = load_image(abspath, check_existing=True, force_reload=False)
                if temp_image:
                    temp_image.scale(thumb_resolution, thumb_resolution)
                    temp_image.name = temp_image.name + "___temp"

                    # Create new image with target (small) resolution
                    image = bpy.data.images.new(
                        image_name, thumb_resolution, thumb_resolution, alpha=True, float_buffer=True, is_data=False
                    )
                    image.colorspace_settings.name = colorspace

                    # Note: Blender images are always created with 4 channels
                    pixel_array_size = thumb_resolution * thumb_resolution * THUMB_CHANNEL_COUNT
                    temp_pixels = np.zeros(pixel_array_size, dtype=np.float32)
                    temp_image.pixels.foreach_get(temp_pixels)

                    if colorspace in COLORSPACES_GAMMA_CORRECTED:
                        # Apply gamma correction
                        gamma = np.full(pixel_array_size, 2.2, dtype=np.float32)
                        gamma_alpha = gamma[3::4]  # A view of the gamma values affecting the alpha channel
                        gamma_alpha[:] = 1.0  # Don't affect the alpha channel
                        temp_pixels = np.power(temp_pixels, gamma)

                    image.pixels.foreach_set(temp_pixels)
                    bpy.data.images.remove(temp_image)
                    image[IMAGE_ABSPATH_KEY] = abspath
                    assert image.name == image_name

                    if colorspace not in COLORSPACES_SUPPORTED:
                        error_message = ("Unsupported Colorspace: {}", (colorspace,))

        node_tree = bpy.data.materials["Material"].node_tree
        starting_nodes = [node.name for node in node_tree.nodes]

        try:
            script = "import bpy; import mathutils; from contextlib import suppress; " + script
            exec(script)
        except Exception as error:
            error_message = ("{}", (str(error),))

            full_error_log += "\nScript: --------------------\n"
            for i, line in enumerate(script.split("\n")):
                full_error_log += str(i + 1) + " \t" + line + "\n"
            full_error_log += "----------------------------"

            import traceback

            full_error_log += traceback.format_exc()

            # Red surface
            node_tree = bpy.data.materials["Material"].node_tree
            output_node = node_tree.nodes["Material Output"]
            error_node = node_tree.nodes.new("ShaderNodeEmission")
            error_node.inputs[0].default_value = [1, 0, 0, 1]
            node_tree.links.new(error_node.outputs[0], output_node.inputs[0])

        settings = bpy.context.scene.render
        settings.filepath = thumb_path
        settings.resolution_x = thumb_resolution
        settings.resolution_y = thumb_resolution
        bpy.ops.render.render(write_still=True)
        result_array = load_render_result(thumb_path)

        for node in node_tree.nodes:
            if node.name not in starting_nodes:
                node_tree.nodes.remove(node)

        # Delete all node groups
        for node_tree in bpy.data.node_groups[:]:
            bpy.data.node_groups.remove(node_tree, do_unlink=True, do_id_user=True, do_ui_user=True)

        # Check if this node contains an image that could not be loaded, and show a helpful error message in that case
        if image_info:
            name, library_path, needs_linking, abspath = image_info
            if (name, library_path) not in bpy.data.images:
                if needs_linking:
                    error_message = ("Save .blend to render preview", ())
                else:
                    if os.path.exists(abspath):
                        error_message = ("Could not load image", ())
                    else:
                        error_message = ("File not found", ())

        node_timestamps[node_key] = time()
        return True, (node_key, result_array, thumb_resolution, timestamp, error_message, full_error_log)
    except Exception as error:
        import traceback

        background_print("Error in background process job:\n", error, "\n", traceback.format_exc())
        return failure


def load_render_result(path: str):
    render_result = load_image(path, check_existing=True, force_reload=True)
    array_size = len(render_result.pixels)
    result_array = np.zeros(array_size, dtype=np.float32)
    render_result.pixels.foreach_get(result_array)
    bpy.data.images.remove(render_result)
    return result_array
