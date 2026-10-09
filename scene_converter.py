#
#     This file is part of Node Preview Reborn, a fork of NodePreview.
#     Copyright (C) 2021 Simon Wendsche
#     Copyright (C) 2026 Guillaume Henrion aka GYOMH (fork/modifications)
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

from math import ceil


def scene_to_script(context, needs_more_samples, use_sphere_preview, thumb_resolution):
    # Note: These settings are not cleaned up/reset after the thumbnail is rendered!
    return f"""
scene = bpy.context.scene

if {context.scene.render.engine == "BLENDER_EEVEE"}:
    scene.render.engine = 'BLENDER_EEVEE'
else:
    scene.render.engine = 'CYCLES'

{"scene.cycles.feature_set = '" + context.scene.cycles.feature_set + "'" if hasattr(context.scene.cycles, "feature_set") else ""}
scene.cycles.shading_system = {context.scene.cycles.shading_system}

# Some shaders are too noisy at 1 sample per pixel
scene.cycles.samples = {4 if needs_more_samples else 1}
scene.render.use_compositing = {needs_more_samples}  # Toggles OIDN (denoising)
scene.render.threads = {4 if needs_more_samples else 1}

if {needs_more_samples} and bpy.app.version < (3, 0, 0):
    scene.render.tile_x = {ceil(thumb_resolution / 2)}
    scene.render.tile_y = {ceil(thumb_resolution / 2)}

bpy.data.objects["Sphere"].hide_render = {not use_sphere_preview}
bpy.data.objects["Light"].hide_render = {not use_sphere_preview}
bpy.data.objects["Plane"].hide_render = {use_sphere_preview}
bpy.data.worlds["World"].node_tree.nodes["Background"].inputs["Strength"].default_value = {0.025 if use_sphere_preview else 1}
"""
