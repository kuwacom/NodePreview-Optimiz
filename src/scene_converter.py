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

from .lib.node_utils import is_eevee


def scene_to_script(context, needs_more_samples, use_sphere_preview):
    engine = context.scene.render.engine
    # EEVEE の識別子は Blender のバージョンで異なるため、ユーザーが使っているものをそのまま渡す
    preview_engine = engine if is_eevee(engine) else "CYCLES"
    cycles = context.scene.cycles
    # feature_set は 5.0 で削除されたため、4.x の時だけユーザーの設定（Experimental など）に合わせる
    feature_set_line = f"scene.cycles.feature_set = {cycles.feature_set!r}" if hasattr(cycles, "feature_set") else ""

    # Note: These settings are not cleaned up/reset after the thumbnail is rendered!
    return f"""
scene = bpy.context.scene
scene.render.engine = {preview_engine!r}

{feature_set_line}
scene.cycles.shading_system = {cycles.shading_system}

# Some shaders are too noisy at 1 sample per pixel
scene.cycles.samples = {4 if needs_more_samples else 1}
scene.render.use_compositing = {needs_more_samples}  # Toggles OIDN (denoising)
scene.render.threads = {4 if needs_more_samples else 1}

bpy.data.objects["Sphere"].hide_render = {not use_sphere_preview}
bpy.data.objects["Light"].hide_render = {not use_sphere_preview}
bpy.data.objects["Plane"].hide_render = {use_sphere_preview}
bpy.data.worlds["World"].node_tree.nodes["Background"].inputs["Strength"].default_value = {0.025 if use_sphere_preview else 1}
"""
