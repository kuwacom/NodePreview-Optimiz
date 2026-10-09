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

import bpy

from .constants import PREVIEW_SHAPE_OBJECTS, PROP_NAME

UNSUPPORTED_NODES = {
    "NodeReroute",
    "ShaderNodeHoldout",  # Makes no sense to render a black thumbnail every time
    "ShaderNodeAttribute",
    "NodeGroupInput",
    "NodeGroupOutput",
}
EEVEE_ONLY_NODES = {
    "ShaderNodeShaderToRGB",
    "ShaderNodeEeveeSpecular",
}
UNSUPPORTED_NODES_CYCLES = UNSUPPORTED_NODES | EEVEE_ONLY_NODES
UNSUPPORTED_NODES_EEVEE = UNSUPPORTED_NODES
NODES_NEEDING_MORE_SAMPLES = {
    "ShaderNodeSubsurfaceScattering",
    "ShaderNodeVolumeScatter",
    "ShaderNodeVolumePrincipled",
    "ShaderNodeBevel",
    "ShaderNodeMixShader",
    "ShaderNodeAddShader",
}
SPHERE_PREVIEW_NODES = {
    "ShaderNodeSubsurfaceScattering",
    "ShaderNodeVolumeScatter",
    "ShaderNodeVolumePrincipled",
    "ShaderNodeVolumeAbsorption",
    "ShaderNodeMixShader",
    "ShaderNodeAddShader",
    "ShaderNodeEeveeSpecular",
    "ShaderNodeEmission",
}
# Above these thresholds, procedural textures become too fine-grained for the preview (at default texture mapping)
SCALE_HELP_THRESHOLDS = {
    "ShaderNodeTexBrick": 11,
    "ShaderNodeTexChecker": 35,
    "ShaderNodeTexMagic": 16,
    "ShaderNodeTexNoise": 40,
    "ShaderNodeTexWave": 11,
    "ShaderNodeTexVoronoi": 30,
}
# EEVEE の識別子は 4.2〜4.5 では BLENDER_EEVEE_NEXT、それ以外では BLENDER_EEVEE
EEVEE_ENGINES = {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}


class UnsupportedNodeException(Exception):
    pass


def is_eevee(engine):
    """
    ### is_eevee
    @param engine - scene.render.engine の値
    @returns EEVEE なら True（Blender のバージョンによる識別子の違いを吸収する）
    """
    return engine in EEVEE_ENGINES


def is_group_node(node):
    return hasattr(node, "node_tree") and (
        isinstance(node.node_tree, bpy.types.ShaderNodeTree) or node.node_tree is None
    )


def get_node_settings(node):
    """
    ### get_node_settings
    @param node - 対象のノード
    @returns ノード毎のプレビュー設定（一部の特殊なノードには無いため None になり得る）
    """
    return getattr(node, PROP_NAME, None)


def get_tree_settings(node_tree):
    """
    ### get_tree_settings
    @param node_tree - 対象のノードツリー
    @returns ノードツリー毎のプレビュー設定
    """
    return getattr(node_tree, PROP_NAME)


def is_node_enabled(node, enabled_by_default):
    """
    ### is_node_enabled
    @param node - 対象のノード
    @param enabled_by_default - ユーザーが個別に切り替えていない場合の値（Previews Visible by Default）
    @returns このノードのプレビューを表示するなら True
    """
    settings = get_node_settings(node)
    return settings.enabled if settings.enabled_modified else enabled_by_default


def is_surface_node(node):
    """
    ### is_surface_node
    @returns シェーダー（BSDF など）を出力するノード、またはそれを含むグループなら True
    """
    bl_idname = node.bl_idname

    if bl_idname == "ShaderNodeGroup" and node.node_tree:
        for subnode in node.node_tree.nodes:
            if is_surface_node(subnode):
                return True

    return bl_idname.startswith("ShaderNodeBsdf") or bl_idname in SPHERE_PREVIEW_NODES


def get_preview_shape(node, surface_shape):
    """
    ### get_preview_shape
    @param node - 判定するノード
    @param surface_shape - Auto の時にシェーダー系のノードで使う形状（アドオン設定）
    @returns PREVIEW_SHAPE_OBJECTS のキーのいずれか
    """
    preview_object = get_node_settings(node).preview_object
    if preview_object == "AUTO":
        return surface_shape if is_surface_node(node) else "PLANE"
    elif preview_object in PREVIEW_SHAPE_OBJECTS:
        return preview_object
    else:
        raise NotImplementedError("Unknown preview_object value")


def needs_more_than_1_sample(node, is_3d_preview):
    bl_idname = node.bl_idname

    if bl_idname == "ShaderNodeGroup" and node.node_tree:
        for subnode in node.node_tree.nodes:
            if needs_more_than_1_sample(subnode, is_3d_preview):
                return True

    if bl_idname == "ShaderNodeBsdfTransparent":
        return False

    if bl_idname == "ShaderNodeBsdfDiffuse" and node.inputs["Normal"].is_linked:
        return True

    # In sphere mode, an area light prevents these from being noise-free at 1 sample
    # 4.0 で Glossy BSDF は ShaderNodeBsdfAnisotropic に統合された
    if not is_3d_preview and bl_idname in {"ShaderNodeBsdfDiffuse", "ShaderNodeBsdfAnisotropic"}:
        roughness_input = node.inputs["Roughness"]
        # At roughness = 0, there's no noise with 1 sample
        return roughness_input.is_linked or roughness_input.default_value > 0

    return bl_idname.startswith("ShaderNodeBsdf") or bl_idname in NODES_NEEDING_MORE_SAMPLES


def is_node_supported(node, engine):
    if len(node.outputs) == 0:
        return False

    if is_eevee(engine):
        return node.bl_idname not in UNSUPPORTED_NODES_EEVEE
    else:
        return node.bl_idname not in UNSUPPORTED_NODES_CYCLES


# ノード名とツリーの部分を区切り、ツリー単位でキーを見分けられるようにする（名前に入らない制御文字を使う）
NODE_KEY_SEPARATOR = "\x1f"


def make_tree_key_suffix(node_tree, node_tree_owner):
    """
    ### make_tree_key_suffix
    @returns このツリーに属するノードの node_key に共通する末尾部分
    """
    # The node_tree_owner typename is added because a material and a world could have the same unique name
    return NODE_KEY_SEPARATOR + NODE_KEY_SEPARATOR.join(
        (node_tree.name_full, type(node_tree_owner).__name__, node_tree_owner.name_full)
    )


# node_tree_owner is the material, world etc. that contains the node_tree
def make_node_key(node, node_tree, node_tree_owner):
    return node.name + make_tree_key_suffix(node_tree, node_tree_owner)


def sort_topologically(nodes, get_dependent_nodes):
    # Depth-first search from https://en.wikipedia.org/wiki/Topological_sorting
    sorted_nodes = []
    temporary_marks = set()
    permanent_marks = set()
    unmarked_nodes = list(nodes)

    def visit(node):
        if node in permanent_marks:
            return

        temporary_marks.add(node)

        for subnode in get_dependent_nodes(node):
            visit(subnode)

        temporary_marks.remove(node)
        permanent_marks.add(node)
        unmarked_nodes.remove(node)
        sorted_nodes.insert(0, node)

    while unmarked_nodes:
        visit(unmarked_nodes[0])

    return sorted_nodes
