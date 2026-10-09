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

import bpy
from mathutils import Color, Vector, Euler

from . import needs_linking, UnsupportedNodeException, is_group_node, get_image_linking_info, SUPPORTED_NODE_TREE


IGNORED_NODE_ATTRIBUTES = {
    "color",
    "dimensions",
    "width",
    "width_hidden",
    "height",
    "hide",
    "label",
    "location",
    "name",
    "select",
    "show_options",
    "show_preview",
    "show_texture",
    "type",
    "use_custom_color",
    "image",  # Handled by special code
    "node_tree",  # Handled by special code
    "inputs",
    "internal_links",
    "outputs",
    "parent",
    "rna_type",
    "node_preview",  # Only used in display.py, not in the background thread
    "bytecode",  # OSL script node
    "bytecode_hash",  # OSL script node
}

node_attributes_cache = {}


# node_tree_owner is the material, world etc. that contains the node_tree
def make_node_key(node, node_tree, node_tree_owner):
    # The node_tree_owner typename is added because a material and a world could have the same unique name
    return node.name + node_tree.name_full + type(node_tree_owner).__name__ + node_tree_owner.name_full


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


def to_valid_identifier(node_name: str):
    result = "n"  # Identifiers must start with a letter, not a digit
    for c in node_name:
        if c.isalnum():
            result += c
        else:
            result += "_" + str(ord(c))
    return result


def _get_attributes(source, ignore_list):
    return [attr for attr in dir(source)
            if not callable(getattr(source, attr))
            and not attr.startswith("__")
            and not attr.startswith("bl_")
            and not attr in ignore_list]


def build_node_attributes_cache():
    node_tree = bpy.data.node_groups.new(".NodePreviewTempTree", "ShaderNodeTree")

    for type_str in dir(bpy.types):
        if type_str.startswith("__"):
            continue

        try:
            if issubclass(getattr(bpy.types, type_str), bpy.types.ShaderNode):
                node = node_tree.nodes.new(type_str)
                node_attributes_cache[type_str] = _get_attributes(node, IGNORED_NODE_ATTRIBUTES)
        except:
            # Some classes like ShaderNode or node groups can't be instanced by node_tree.nodes.new(type_str)
            # Also, getattr(bpy.types, type_str) threw an error for one user, possibly a custom Blender build
            pass

    def register(type_str):
        node = node_tree.nodes.new(type_str)
        node_attributes_cache[type_str] = _get_attributes(node, IGNORED_NODE_ATTRIBUTES)

    register("NodeGroupInput")
    register("NodeGroupOutput")
    register("NodeReroute")
    register("NodeFrame")

    # Ignore named UV maps. Since they never exist on the preview mesh, they would make the UV output black
    uvmap_attributes = node_attributes_cache["ShaderNodeUVMap"]
    uvmap_attributes.remove("from_instancer")
    uvmap_attributes.remove("uv_map")

    bpy.data.node_groups.remove(node_tree)


def node_to_script(node, node_tree_owner, node_scripts_cache, group_hashes, incoming_links,
                   background_colors, node_tree_hierarchy, engine):
    script = [
        "material = bpy.data.materials['Material']",
        "node_tree = material.node_tree",
        "output_node = node_tree.nodes['Material Output']",
        # Background color settings
        "background_tex = bpy.data.materials['checker_plane'].node_tree.nodes['Checker Texture']",
        "background_tex.inputs[1].default_value = " + str(background_colors[0]),
        "background_tex.inputs[2].default_value = " + str(background_colors[1]),
    ]

    if engine == "BLENDER_EEVEE" and isinstance(node_tree_owner, bpy.types.Material):
        script += [
            f"material.use_backface_culling = {node_tree_owner.use_backface_culling}",
            f"material.blend_method = {repr(node_tree_owner.blend_method)}",
            f"material.alpha_threshold = {node_tree_owner.alpha_threshold}",
            f"material.show_transparent_back = {node_tree_owner.show_transparent_back}",
            f"material.use_screen_refraction = {node_tree_owner.use_screen_refraction}",
            f"material.refraction_depth = {node_tree_owner.refraction_depth}",
            f"material.use_sss_translucency = {node_tree_owner.use_sss_translucency}",

            # TODO Lineart?
        ]

    images_to_load = set()
    images_to_link = set()

    # Create linking script and check which nodes we need to create before we can link them
    node_linking_script = []
    required_nodes = set()
    link_cache = set()
    _make_node_linking_script(node, incoming_links, node_linking_script, required_nodes, link_cache, node_tree_hierarchy)

    node_creation_script = []
    for required_node in required_nodes:
        try:
            node_script, sub_images_to_load, sub_images_to_link = node_scripts_cache[required_node.name]
        except KeyError:
            node_script, sub_images_to_load, sub_images_to_link = _make_node_creation_script(required_node, group_hashes)
            node_scripts_cache[required_node.name] = node_script, sub_images_to_load, sub_images_to_link
        node_creation_script += node_script
        images_to_load.update(sub_images_to_load)
        images_to_link.update(sub_images_to_link)

    script += node_creation_script
    script += node_linking_script

    outputs = node.outputs

    # Link the node
    if node.node_preview.auto_choose_output:
        first_enabled = _find_first_enabled_socket(outputs)
        output_index = _find_first_linked_socket(outputs, fallback=first_enabled)
    else:
        output_index = node.node_preview.output_index

    if outputs[output_index].name == "Volume":
        input_index = 1
    else:
        input_index = 0

    script.append(f"node_tree.links.new(node_tree.nodes[{repr(node.name)}].outputs[{output_index}], output_node.inputs[{input_index}])")

    # print("--- script: ---")
    # print("\n".join(script))
    # print("---------------")
    return "\n".join(script), images_to_load, images_to_link


def _socket_interfaces_to_script(socket_interfaces, attr_name, script):
    for socket_interface in socket_interfaces:
        script.append(f"socket = node_tree.{attr_name}.new({repr(socket_interface.bl_socket_idname)}, {repr(socket_interface.name)})")

        if hasattr(socket_interface, "default_value"):
            value, success = _property_to_string(socket_interface.default_value)
            if success:
                script.append(f"with suppress(Exception): socket.default_value = {value}")
            else:
                print("Conversion of default_value failed:", socket_interface.name, socket_interface.default_value)


def _socket_interfaces_to_script_Blender4(interface, script):
    for item in interface.items_tree:
        if item.item_type == "SOCKET":
            valid_idnames = {"NodeSocketVector", "NodeSocketShader", "NodeSocketFloat", "NodeSocketColor"}
            socket_idname = item.bl_socket_idname

            # Try to fix e.g. "NodeSocketFloatFactor" -> "NodeSocketFloat"
            if socket_idname not in valid_idnames:
                for valid_idname in valid_idnames:
                    if socket_idname.startswith(valid_idname):
                        socket_idname = valid_idname
                        break

            # TODO Not sure how to create sockets of other types - limitation in the Blender API?
            if socket_idname not in valid_idnames:
                # print("Error on socket", repr(item.name), "with bl_socket_idname", repr(item.bl_socket_idname), "of node group", repr(item.id_data.name))
                # Use a float socket to avoid indexing problems elsewhere due to a missing socket
                socket_idname = "NodeSocketFloat"

            # NodeTreeInterface.new_socket(name, description="", in_out='INPUT', socket_type='DEFAULT', parent=None)
            script.append(f"socket = node_tree.interface.new_socket({repr(item.name)}, "
                          f"in_out={repr(item.in_out)}, "
                          f"socket_type={repr(socket_idname)})")

            # Not sure if this is needed, couldn't find a difference without it in some quick tests
            if hasattr(item, "default_value"):
                value, success = _property_to_string(item.default_value)
                if success:
                    script.append(f"with suppress(Exception): socket.default_value = {value}")
                else:
                    print("Conversion of default_value failed:", item.name, item.default_value)


class AnnotatedNodeGroup:
    def __init__(self, group):
        self.group = group
        self.dependent_groups = set()


def node_groups_to_script(node_groups):
    groups = set([group for group in node_groups if group.bl_idname == SUPPORTED_NODE_TREE])

    # Build a DAG structure of groups and their dependent groups
    annotated_groups = {group: AnnotatedNodeGroup(group) for group in groups}
    for group in groups:
        for node in group.nodes:
            if is_group_node(node) and node.node_tree:
                annotated_groups[node.node_tree].dependent_groups.add(annotated_groups[group])

    # Make sure that groups that other groups depend on are evaluated first
    def get_dependent_groups(annotated_group):
        return annotated_group.dependent_groups
    sorted_groups = sort_topologically(annotated_groups.values(), get_dependent_groups)

    script = ["node_group_mapping = {}"]
    images_to_load = set()
    images_to_link = set()
    group_hashes = {}
    for annotated_group in sorted_groups:
        group = annotated_group.group
        unique_name = group.name_full
        group_script = []
        # Note: max length for node group names in Blender is 63 characters
        group_script.append(f"node_tree = bpy.data.node_groups.new({repr(unique_name)}, 'ShaderNodeTree')")
        # This is used in node group instances to set the correct node_tree for the instance node
        group_script.append(f"node_group_mapping[{repr(unique_name)}] = node_tree")

        # Create group inputs and outputs
        if bpy.app.version >= (4, 0, 0):
            _socket_interfaces_to_script_Blender4(group.interface, group_script)
        else:
            _socket_interfaces_to_script(group.inputs, "inputs", group_script)
            _socket_interfaces_to_script(group.outputs, "outputs", group_script)

        for node in group.nodes:
            node_script, sub_images_to_load, sub_images_to_link = _single_node_to_script(node, group_hashes)
            group_script += node_script
            images_to_load.update(sub_images_to_load)
            images_to_link.update(sub_images_to_link)

        # socket.links is a very expensive property to access, so we cache the link types we are interested in most in this dict
        outgoing_links = {}
        for link in group.links:
            try:
                outgoing_links[link.from_socket].append(link)
            except KeyError:
                outgoing_links[link.from_socket] = [link]

        # Create all links
        # On regular nodes, multiple sockets may have the same name, so we have to use the index to refer to them.
        # On OSL script nodes, the socket order might be jumbled, but two sockets can never have the same name.
        # Thus we can and have to use the name to reference the input socket on OSL nodes.
        for source_node_index, source_node in enumerate(group.nodes):
            source_is_OSL_node = source_node.bl_idname == "ShaderNodeScript"

            for source_socket_index, source_socket in enumerate(source_node.outputs):
                source_socket_identifier = repr(source_socket.name) if source_is_OSL_node else source_socket_index

                if source_socket.is_linked:
                    for link in outgoing_links[source_socket]:
                        target_is_OSL_node = link.to_node.bl_idname == "ShaderNodeScript"
                        target_node_index = group.nodes.find(link.to_node.name)
                        if target_node_index == -1:
                            raise Exception(f"Could not find target node: {link.to_node.name} in node group: {group.name}")

                        # Can't use find here because a node can have multiple sockets with the same name
                        target_socket_identifier = -1
                        for i, socket in enumerate(link.to_node.inputs):
                            if socket == link.to_socket:
                                target_socket_identifier = repr(socket.name) if target_is_OSL_node else i
                                break
                        if target_socket_identifier == -1:
                            raise Exception(f"Could not find target socket: {link.to_socket.name} in node group: {group.name}")

                        group_script.append(f"node_tree.links.new(node_tree.nodes[{source_node_index}].outputs[{source_socket_identifier}], "
                                                                f"node_tree.nodes[{target_node_index}].inputs[{target_socket_identifier}])")

        group_script_joined = "\n".join(group_script)
        script.append(group_script_joined)
        group_hashes[unique_name] = hash(group_script_joined)

    return "\n".join(script), images_to_load, images_to_link, group_hashes


def _attributes_to_script(attributes, source, target_identifier, script):
    for attr in attributes:
        value, success = _property_to_string(getattr(source, attr))
        if success:
            script.append(f"with suppress(Exception): {target_identifier}.{attr} = {value}")


def _node_properties_to_script(node, node_identifier, is_OSL_node, script, group_hashes):
    images_to_load = set()
    images_to_link = set()
    _is_group_node = is_group_node(node)

    try:
        attributes = node_attributes_cache[node.bl_idname]
    except KeyError:
        if _is_group_node:
            # It is most likely a custom node with an internal node group.
            # Put it in the attributes cache and treat it like a group node.
            attributes = _get_attributes(node, IGNORED_NODE_ATTRIBUTES)
            node_attributes_cache[node.bl_idname] = attributes
        else:
            raise UnsupportedNodeException(f"Unsupported node type: {node.bl_idname}")

    # A change of the counter causes a change in the script hash, which
    # automatically updates this node and all dependent nodes
    script.append(f"# {node.node_preview.force_update_counter}")

    _attributes_to_script(attributes, node, node_identifier, script)

    if getattr(node, "image", None):
        image = node.image

        if needs_linking(image):
            image_linking_info = get_image_linking_info(image)
            images_to_link.add(image_linking_info)
            _, library_path = image_linking_info
        else:
            library_path = None

        # Try to load the image even if we're linking it, as fallback in case the linking fails
        # (e.g. because the image was just packed, but the .blend was not saved yet)
        if image.source == "TILED":
            filepath = image.filepath.replace("<UDIM>", str(image.tiles.active.number))
        else:
            filepath = image.filepath
        abspath = bpy.path.abspath(filepath, library=image.library)
        background_image_name = image.name
        images_to_load.add((background_image_name, library_path, abspath, image.colorspace_settings.name))

        # TODO what about image sequences/other image user settings?

        # Note: Do NOT try to set the color space here. We create images "manually" because they need to be downscaled
        # specially, and Blender has a bug where it sets all pixels to black if the colorspace of a manually created
        # image is changed afterwards. All colorspace conversion has to be done in the background process during loading
        # of the image.

        # The path and colorspace are part of the script so a change triggers an update through the script hash
        script.append(f"# {abspath}")
        script.append(f"# {image.colorspace_settings.name}")

        script.append("try:")
        script.append(f"    image = bpy.data.images[{repr(background_image_name)}, {repr(library_path) if library_path else None}]")
        script.append(f"    {node_identifier}.image = image")
        script.append("except:")
        script.append(f'    print("failed to find image", {repr(background_image_name)}, "(library:", {repr(library_path)}, ")")')

    # Special properties: color ramp
    if hasattr(node, "color_ramp"):
        ramp = node.color_ramp
        _attributes_to_script(_get_attributes(ramp, []), ramp, f"{node_identifier}.color_ramp", script)

        # Ramp has two elements by default, but user might have deleted one, so remove it
        script.append(f"{node_identifier}.color_ramp.elements.remove({node_identifier}.color_ramp.elements[0])")
        # Then re-add as many elements as needed
        for i in range(len(ramp.elements) - 1):
            script.append(f"{node_identifier}.color_ramp.elements.new(0)")

        for i in range(len(ramp.elements)):
            script.append(f"{node_identifier}.color_ramp.elements[{i}].position = {ramp.elements[i].position}")
            color, _ = _property_to_string(ramp.elements[i].color)
            script.append(f"{node_identifier}.color_ramp.elements[{i}].color = {color}")

    # Special properties: Curves
    if node.bl_idname in {"ShaderNodeRGBCurve", "ShaderNodeFloatCurve", "ShaderNodeVectorCurve"}:
        mapping = node.mapping
        _attributes_to_script(_get_attributes(mapping, []), mapping, f"{node_identifier}.mapping", script)

        for curve_index, curve in enumerate(mapping.curves):
            # Curves have 2 points by default, and a minimum of 2, so we ignore the first 2 points here
            for i in range(2, len(curve.points)):
                script.append(f"{node_identifier}.mapping.curves[{curve_index}].points.new(0, 0)")

            for point_index, point in enumerate(curve.points):
                handle_type, _ = _property_to_string(point.handle_type)
                script.append(
                    f"{node_identifier}.mapping.curves[{curve_index}].points[{point_index}].handle_type = {handle_type}")
                location, _ = _property_to_string(point.location)
                script.append(f"{node_identifier}.mapping.curves[{curve_index}].points[{point_index}].location = {location}")
    elif _is_group_node and node.node_tree:
        group_name = node.node_tree.name_full
        # The hash over the node group script is appended as a comment here so the node script hash changes
        # when the group hash changes, to flag this node for updating
        script.append(f"{node_identifier}.node_tree = node_group_mapping[{repr(group_name)}]  # {group_hashes[group_name]}")

    if is_OSL_node:
        success = False

        if node.mode == "INTERNAL":
            if node.script:
                osl_script = node.script.as_string()
                textblock_name = node.script.name_full
                success = True
        elif node.mode == "EXTERNAL":
            try:
                with open(node.filepath, "r") as file:
                    osl_script = file.read()
                    textblock_name = "loaded_from_file"
                    success = True
            except:
                pass
        else:
            raise UnsupportedNodeException("Unsupported OSL script node mode: " + node.mode)

        if not success:
            raise UnsupportedNodeException("OSL script node is in an invalid state")

        # For some reason, external OSL scripts don't work in background, so we always use internal mode
        script.append(f"{node_identifier}.mode = 'INTERNAL'")

        script.append(f"text = bpy.data.texts.new({repr(textblock_name)})")
        script.append(f"text.from_string({repr(osl_script)})")
        script.append(f"{node_identifier}.script = text")

    return images_to_load, images_to_link


def _node_outputs_to_script(node, node_identifier, is_OSL_node, script):
    if node.bl_idname == "NodeReroute":
        return

    for i, socket in enumerate(node.outputs):
        if hasattr(socket, "default_value"):
            value, success = _property_to_string(socket.default_value)
            if success:
                # On regular nodes, multiple sockets may have the same name, so we have to use the index to refer to them.
                # On OSL script nodes, the socket order might be jumbled, but two sockets can never have the same name.
                # Thus we can and have to use the name to reference the input socket on OSL nodes.
                output_identifier = repr(socket.name) if is_OSL_node else i
                script.append(f"with suppress(Exception): {node_identifier}.outputs[{output_identifier}].default_value = {value}")
            else:
                print("Conversion of default_value failed:", node, socket.name, socket.default_value)


def _single_node_to_script(node, group_hashes):
    """ Used in node group conversion. Only creates a single node without evaluating linked nodes. """
    node_identifier = to_valid_identifier(node.name)
    bl_idname = "ShaderNodeGroup" if is_group_node(node) else node.bl_idname
    script = [f"{node_identifier} = node_tree.nodes.new('{bl_idname}')"]
    is_OSL_node = node.bl_idname == "ShaderNodeScript"

    if node.bl_idname == "NodeReroute" and not node.inputs[0].is_linked:
        # Ignore reroutes without any inputs, but still create them so node indices are correct for link creation later.
        # (New reroutes always have color inputs, so if they are created from e.g. a float reroute,
        # reroute.inputs[0].default_value = 0.0 will fail. We should connect the reroutes first (so they get the
        # correct input/output type), then set any default_values, but IMO that would be too much effort to make
        # something work that is essentially a badly formed node tree anyway)
        return script, set(), set()

    # Properties
    images_to_load, images_to_link = _node_properties_to_script(node, node_identifier, is_OSL_node, script, group_hashes)

    # Input sockets
    for i, socket in enumerate(node.inputs):
        if socket.name == "Scale" and node.node_preview.ignore_scale:
            continue

        if not socket.is_linked and hasattr(socket, "default_value"):
            value, success = _property_to_string(socket.default_value)
            if success:
                # On regular nodes, multiple sockets may have the same name, so we have to use the index to refer to them.
                # On OSL script nodes, the socket order might be jumbled, but two sockets can never have the same name.
                # Thus we can and have to use the name to reference the input socket on OSL nodes.
                input_identifier = repr(socket.name) if node.bl_idname == "ShaderNodeScript" else i
                script.append(f"with suppress(Exception): {node_identifier}.inputs[{input_identifier}].default_value = {value}")
            else:
                print("Conversion of default_value failed:", node, socket.name, socket.default_value)

    # Output sockets (used on nodes like Value or RGB)
    _node_outputs_to_script(node, node_identifier, is_OSL_node, script)

    return script, images_to_load, images_to_link


def _get_link_skipping_reroutes(socket, incoming_links):
    try:
        link = incoming_links[socket]
    except KeyError:
        # When a user has detached a node wire, but not let go yet, socket.is_linked is still reporting True
        # but there's no actual link anymore, making the lookup in incoming_links fail
        return None

    while link.from_node.bl_idname == "NodeReroute":
        reroute_input = link.from_node.inputs[0]
        if reroute_input.is_linked:
            link = incoming_links[reroute_input]
        else:
            # If the left-most reroute has no input, it is like self.is_linked == False
            return None
    return link


def _find_socket_index(outputs, socket):
    for i, output in enumerate(outputs):
        if output == socket:
            return i
    raise Exception("Output socket not found:", socket.name)


def _make_node_creation_script(node, group_hashes):
    # Inside a node tree, the name is unique
    # Note: name collisions aren't allowed to happen between this node and nodes linked to it
    node_identifier = to_valid_identifier(node.name)
    bl_idname = "ShaderNodeGroup" if is_group_node(node) else node.bl_idname
    script = [
        f"{node_identifier} = node_tree.nodes.new({repr(bl_idname)})",
        f"{node_identifier}.name = {repr(node.name)}",
    ]
    is_OSL_node = node.bl_idname == "ShaderNodeScript"

    # Properties
    images_to_load, images_to_link = _node_properties_to_script(node, node_identifier, is_OSL_node, script, group_hashes)

    # Input sockets
    for i, socket in enumerate(node.inputs):
        if socket.name == "Scale" and node.node_preview.ignore_scale:
            continue

        if not socket.is_linked and hasattr(socket, "default_value"):
            value, success = _property_to_string(socket.default_value)
            if success:
                # On OSL script nodes, the socket order might be jumbled, but two sockets can never have the same name.
                # Thus we can and have to use the name to reference the input socket on OSL nodes
                input_identifier = repr(socket.name) if is_OSL_node else i
                script.append(f"with suppress(Exception): {node_identifier}.inputs[{input_identifier}].default_value = {value}")
            else:
                print("Conversion of default_value failed:", node, socket.name, socket.default_value)

    # Output sockets (used on nodes like Value or RGB)
    _node_outputs_to_script(node, node_identifier, is_OSL_node, script)

    return script, images_to_load, images_to_link


# TODO group input support:
#  - if possible, make it transparent, e.g. throw all nodes together in display.py already (as early as possible)
#  - support for node groups in outside nodes
#  - support for nested groups

def _make_node_linking_script(node, incoming_links, node_linking_script, required_nodes, link_cache, node_tree_hierarchy):
    required_nodes.add(node)
    is_OSL_node = node.bl_idname == "ShaderNodeScript"
    node_name_string = repr(node.name)

    for i, socket in enumerate(node.inputs):
        if socket.name == "Scale" and node.node_preview.ignore_scale:
            continue

        if socket.is_linked:
            link = _get_link_skipping_reroutes(socket, incoming_links)
            if link:
                if link.from_node.bl_idname == "NodeGroupInput":
                    current_index = -1  # TODO find actual index, e.g. with node_tree_hierarchy.index(node_tree)
                    try:
                        parent_node_tree = node_tree_hierarchy[current_index - 1]
                    except IndexError:
                        # Can't access node group instance. The node group was probably opened directly instead of through an instance.
                        continue

                    node_group_instance = parent_node_tree.nodes.active
                    instance_input = node_group_instance.inputs[link.from_socket.name]
                    if not instance_input.is_linked:
                        # TODO use node_group_instance default_value in this case (probably in node creation script?)
                        continue

                    # TODO hacky, other code needs to be checked to make sure it works with such a mix of links between nodetrees
                    incoming_links.update({link.to_socket: link for link in parent_node_tree.links})

                    # instance_link = instance_input.links[0]
                    instance_link = _get_link_skipping_reroutes(instance_input, incoming_links)
                    from_node = instance_link.from_node
                    from_socket = instance_link.from_socket
                    # TODO recursively include required nodes from the parent node tree
                else:
                    from_node = link.from_node
                    from_socket = link.from_socket

                # On OSL script nodes, the socket order might be jumbled, but two sockets can never have the same name.
                # Thus we can and have to use the name to reference the input socket on OSL nodes
                input_identifier = repr(socket.name) if is_OSL_node else i
                output_index = _find_socket_index(from_node.outputs, from_socket)
                link_code = (f"node_tree.links.new(node_tree.nodes[{repr(from_node.name)}].outputs[{output_index}], "
                                                 f"node_tree.nodes[{node_name_string}].inputs[{input_identifier}])")

                if link_code not in link_cache:
                    node_linking_script.append(link_code)
                    _make_node_linking_script(from_node, incoming_links, node_linking_script, required_nodes, link_cache, node_tree_hierarchy)
                    link_cache.add(link_code)


def _property_to_string(prop):
    if isinstance(prop, (Color, Vector, bpy.types.bpy_prop_array)):
        return str(list(prop)), True
    elif isinstance(prop, (float, int)):
        return str(prop), True
    elif isinstance(prop, str):
        return repr(prop), True
    elif isinstance(prop, Euler):
        return f"mathutils.Euler({list(prop)}, '{prop.order}')", True

    return None, False


def _find_first_enabled_socket(outputs, fallback=0):
    for i, socket in enumerate(outputs):
        if socket.enabled:
            return i
    return fallback


def _find_first_linked_socket(outputs, fallback):
    for i, socket in enumerate(outputs):
        if socket.enabled and socket.is_linked:
            return i
    return fallback
