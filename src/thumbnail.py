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

import blf
import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader

from .lib.constants import ID_PREFIX, SHADERS_DIR
from .lib.i18n import format_message
from .lib.logger import addon_print

_shader = None
use_fallback_shader = False


def create_thumbnail_shader():
    # GPUShaderCreateInfo is the cross-backend (OpenGL/Vulkan/Metal) shader API.
    # ModelViewProjectionMatrix is a reserved/builtin uniform name: Blender fills it in
    # automatically on batch.draw(), no manual uniform_float() call needed.
    vert_out = gpu.types.GPUStageInterfaceInfo(f"{ID_PREFIX}_thumbnail_interface")
    vert_out.smooth("VEC2", "texCoord_interp")

    shader_info = gpu.types.GPUShaderCreateInfo()
    shader_info.push_constant("MAT4", "ModelViewProjectionMatrix")
    shader_info.push_constant("BOOL", "gamma_correct")
    shader_info.sampler(0, "FLOAT_2D", "image")
    shader_info.vertex_in(0, "VEC2", "pos")
    shader_info.vertex_in(1, "VEC2", "texCoord")
    shader_info.vertex_out(vert_out)
    shader_info.fragment_out(0, "VEC4", "fragColor")

    with open(os.path.join(SHADERS_DIR, "thumbnail_vert.glsl")) as vert:
        shader_info.vertex_source(vert.read())
    with open(os.path.join(SHADERS_DIR, "thumbnail_frag.glsl")) as frag:
        shader_info.fragment_source(frag.read())

    return gpu.shader.create_from_info(shader_info)


def get_shader():
    """
    ### get_shader
    サムネイル描画用のシェーダーを返す（初回呼び出し時に作る）

    @returns コンパイル済みのシェーダー。コンパイルに失敗した場合は組み込みの IMAGE シェーダー
    """
    # GPU が使えるのは描画中のメインスレッドだけなので、読み込み時ではなく最初の描画時に作る
    global _shader, use_fallback_shader
    if _shader is None:
        try:
            _shader = create_thumbnail_shader()
        except Exception as error:
            addon_print("Could not compile shaders:", str(error))
            use_fallback_shader = True
            _shader = gpu.shader.from_builtin("IMAGE")
    return _shader


class Thumbnail:
    """
    # Thumbnail
    裏プロセスから受け取ったサムネイル 1 枚分の画素と、それを描画するためのテクスチャ
    """

    def __init__(self, pixels, width, height, channel_count, message):
        self.pixels = pixels
        # The thumbnail is created in a thread, but the texture has to be initialized
        # in the main thread, so we can't do it here yet. init_texture() must be called
        # from the main thread.
        self.texture = None

        self.width = width
        self.height = height
        self.channel_count = channel_count
        # 言語の切り替えにすぐ追従できるよう、訳すのは描画時に行う
        self.message = message

    def init_texture(self):
        get_shader()
        if use_fallback_shader:
            # Normally the shader would do the gamma correction, but the builtin fallback shader doesn't do this.
            # Note: this operation also affects the alpha channel, which is not correct, but since
            # the alpha channel is currently not used, it doesn't matter.
            self.pixels = np.power(self.pixels, 2.2)

        buffer = gpu.types.Buffer("FLOAT", self.width * self.height * self.channel_count, self.pixels)

        # TODO is this actually (height, width)? And is the format correct, why not 32F?
        # (Code from https://docs.blender.org/api/current/bpy.types.RenderEngine.html)
        self.texture = gpu.types.GPUTexture((self.width, self.height), format="RGBA16F", data=buffer)

        # No longer needed, delete to save memory
        self.pixels = None

    def draw(self, bottom_left, bottom_right, top_right, top_left, scaled_zoom, text_x):
        shader = get_shader()
        shader.bind()
        shader.uniform_sampler("image", self.texture)

        try:
            shader.uniform_int("gamma_correct", True)
        except ValueError:
            # There's no gamma_correct uniform when using the builtin "IMAGE" shader on the Metal backend
            pass

        batch = batch_for_shader(
            shader,
            "TRIS",
            {
                "pos": (bottom_left, bottom_right, top_right, top_left),
                "texCoord": ((0, 0), (1, 0), (1, 1), (0, 1)),
            },
            indices=((0, 1, 2), (0, 2, 3)),
        )
        batch.draw(shader)

        text = format_message(self.message)
        if text:
            position = (text_x, top_left[1] + 3 * scaled_zoom)
            draw_text(text, position, 10, scaled_zoom)


def draw_text(text, position, font_size, scaled_zoom):
    # Somewhere in the blf functions the blend mode is overwritten,
    # so we need to save it before and restore it after we use blf
    old_blend_mode = gpu.state.blend_get()

    FONT_ID = 0

    x, y = position
    for line in reversed(text.split("\n")):
        blf.position(FONT_ID, x, y, 0)
        blf.size(FONT_ID, round(font_size * scaled_zoom))
        blf.draw(FONT_ID, line)
        y += font_size * scaled_zoom

    gpu.state.blend_set(old_blend_mode)
    return y
