bl_info = {
    "name": "UV Effects Modifier",
    "author": "Codex",
    "version": (0, 4, 6),
    "blender": (5, 3, 0),
    "location": "Object > UV Effects",
    "category": "Object",
}

import math

import bpy


def build_group(source, target, radial_axis):
    tree = bpy.data.node_groups.new("UV Effects", "GeometryNodeTree")
    try:
        configure_group(tree, source, target, radial_axis)
        tree["uv_effects_modifier"] = True
    except Exception:
        bpy.data.node_groups.remove(tree)
        raise
    return tree


def configure_group(tree, source, target, radial_axis):
    def socket(name, kind, direction="INPUT", default=None):
        if hasattr(tree, "interface"):
            item = tree.interface.new_socket(name, in_out=direction, socket_type=kind)
        else:
            sockets = tree.inputs if direction == "INPUT" else tree.outputs
            item = sockets.new(kind, name)
        if default is not None:
            item.default_value = default
        return item

    socket("Geometry", "NodeSocketGeometry")
    socket("Geometry", "NodeSocketGeometry", "OUTPUT")
    socket("Source UV", "NodeSocketString", default=source)
    socket("Output UV", "NodeSocketString", default=target)
    strength = socket("Remap Strength", "NodeSocketFloat", default=1.0)
    strength.min_value = 0.0
    strength.max_value = 1.0
    socket("Soft Offset", "NodeSocketFloat", default=0.0)

    def node(kind, x_pos, y_pos, label=""):
        result = tree.nodes.new(kind)
        result.location = (x_pos, y_pos)
        result.label = label
        return result

    link = tree.links.new
    inputs = node("NodeGroupInput", -800, 250).outputs
    output = node("NodeGroupOutput", 960, 250).inputs
    read = node("GeometryNodeInputNamedAttribute", -590, -40)
    read.data_type = "FLOAT_VECTOR"
    link(inputs["Source UV"], read.inputs["Name"])
    split = node("ShaderNodeSeparateXYZ", -380, -40)
    link(read.outputs["Attribute"], split.inputs[0])
    radial, tangent = (0, 1) if radial_axis == "U" else (1, 0)
    coordinate = split.outputs[radial]

    remap = node("ShaderNodeFloatCurve", -150, 0, "Stretch / Squeeze")
    remap.width = 235
    link(inputs["Remap Strength"], remap.inputs[0])
    link(coordinate, remap.inputs[1])

    falloff = node("ShaderNodeFloatCurve", -150, -310, "Soft Offset Falloff")
    falloff.width = 235
    link(coordinate, falloff.inputs[1])
    weight = node("ShaderNodeMath", 120, -310)
    weight.operation = "MULTIPLY"
    link(falloff.outputs[0], weight.inputs[0])
    link(inputs["Soft Offset"], weight.inputs[1])
    offset = node("ShaderNodeMath", 310, -310)
    offset.operation = "ADD"
    link(split.outputs[tangent], offset.inputs[0])
    link(weight.outputs[0], offset.inputs[1])
    combine = node("ShaderNodeCombineXYZ", 500, -40)
    link(remap.outputs[0], combine.inputs[radial])
    link(offset.outputs[0], combine.inputs[tangent])

    store = node("GeometryNodeStoreNamedAttribute", 730, 250)
    store.domain = "CORNER"
    store.data_type = "FLOAT2"
    link(inputs["Geometry"], store.inputs["Geometry"])
    link(inputs["Output UV"], store.inputs["Name"])
    link(read.outputs["Exists"], store.inputs["Selection"])
    link(combine.outputs[0], next(sock for sock in store.inputs if sock.name == "Value" and sock.enabled))
    link(store.outputs["Geometry"], output["Geometry"])


def add_modifier(obj, source, target, axis):
    tree = build_group(source, target, axis)
    modifier = obj.modifiers.new("UV Effects", "NODES")
    modifier.node_group = tree
    return modifier


class OBJECT_OT_uv_effects_add(bpy.types.Operator):
    bl_idname = "object.uv_effects_add"
    bl_label = "Add UV Effects Modifier"
    bl_options = {"REGISTER", "UNDO"}

    source: bpy.props.StringProperty(name="Source UV")
    target: bpy.props.StringProperty(name="Output UV", default="UV_Effects")
    axis: bpy.props.EnumProperty(name="Remap Axis", items=(("U", "U", ""), ("V", "V", "")), default="V")

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == "MESH" and context.mode == "OBJECT"

    def invoke(self, context, event):
        active = context.object.data.uv_layers.active
        self.source = active.name if active else "UVMap"
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.prop_search(self, "source", context.object.data, "uv_layers")
        self.layout.prop(self, "target")
        self.layout.prop(self, "axis")

    def execute(self, context):
        obj = context.object
        target = self.target.strip()
        if not obj.data.uv_layers.get(self.source) or not target:
            self.report({"ERROR"}, "Choose an existing source UV and a non-empty output name.")
            return {"CANCELLED"}
        existing = obj.data.attributes.get(target)
        if existing and (existing.data_type != "FLOAT2" or existing.domain != "CORNER"):
            self.report({"ERROR"}, "Output name conflicts with a non-UV attribute.")
            return {"CANCELLED"}
        add_modifier(obj, self.source, target, self.axis)
        return {"FINISHED"}


class OBJECT_OT_uv_effects_demo(bpy.types.Operator):
    bl_idname = "object.uv_effects_demo"
    bl_label = "Create UV Effects Ring Demo"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT"

    def execute(self, context):
        segments = 32
        vertices = [
            (radius * math.cos(math.tau * step / segments), radius * math.sin(math.tau * step / segments), 0)
            for step in range(segments) for radius in (0.65, 1.0)
        ]
        faces = [
            (2 * step, 2 * step + 1, 2 * ((step + 1) % segments) + 1, 2 * ((step + 1) % segments))
            for step in range(segments)
        ]
        mesh = bpy.data.meshes.new("UV Effects Ring")
        mesh.from_pydata(vertices, [], faces)
        uv = mesh.uv_layers.new(name="UVMap")
        for face in mesh.polygons:
            start = face.index / segments
            end = (face.index + 1) / segments
            for index, point in zip(face.loop_indices, ((start, 0), (start, 1), (end, 1), (end, 0))):
                uv.data[index].uv = point
        obj = bpy.data.objects.new("UV Effects Ring", mesh)
        context.collection.objects.link(obj)
        obj.location = context.scene.cursor.location

        subdivision = obj.modifiers.new("Change Levels to Test", "SUBSURF")
        subdivision.subdivision_type = "SIMPLE"
        subdivision.levels = 2
        modifier = add_modifier(obj, "UVMap", "UV_Effects", "V")
        curve = next(node for node in modifier.node_group.nodes if node.label == "Stretch / Squeeze")
        curve.mapping.curves[0].points.new(0.72, 0.3)
        curve.mapping.update()

        material = bpy.data.materials.new("UV Effects Checker")
        material.use_nodes = True
        nodes = material.node_tree.nodes
        uv_node = nodes.new("ShaderNodeUVMap")
        uv_node.uv_map = "UV_Effects"
        uv_node.location = (-600, 0)
        checker = nodes.new("ShaderNodeTexChecker")
        checker.location = (-350, 0)
        checker.inputs["Scale"].default_value = 12
        material.node_tree.links.new(uv_node.outputs["UV"], checker.inputs["Vector"])
        material.node_tree.links.new(checker.outputs["Color"], nodes.get("Principled BSDF").inputs["Base Color"])
        mesh.materials.append(material)
        for selected in context.selected_objects:
            selected.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        return {"FINISHED"}


def is_uv_effect(modifier):
    if modifier.type != "NODES" or not modifier.node_group:
        return False
    tree = modifier.node_group
    if tree.get("uv_effects_modifier"):
        return True
    labels = {node.label for node in tree.nodes if node.bl_idname == "ShaderNodeFloatCurve"}
    return {"Stretch / Squeeze", "Soft Offset Falloff"} <= labels


def active_effect(context):
    obj = context.object
    if not obj or obj.type != "MESH":
        return None
    effects = [mod for mod in obj.modifiers if is_uv_effect(mod)]
    return obj.modifiers.active if obj.modifiers.active in effects else next(reversed(effects), None)


def parameter(modifier, name):
    socket = next(item for item in modifier.node_group.interface.items_tree if item.name == name)
    return getattr(modifier.properties.inputs, socket.identifier)


def uv_edges(mesh, name):
    layer = mesh.uv_layers.get(name)
    if not layer:
        return []
    stride = max(1, math.ceil(len(mesh.polygons) / 6000))
    vertices = []
    for index in range(0, len(mesh.polygons), stride):
        face = mesh.polygons[index]
        start = face.loop_start
        end = start + face.loop_total
        for corner in range(start, end):
            following = corner + 1 if corner + 1 < end else start
            vertices.extend((tuple(layer.uv[corner].vector), tuple(layer.uv[following].vector)))
    return vertices


def preview_texture_batch(mesh, source, target, origin, bottom, scale, min_u, min_v, shader, make_batch):
    source_layer = mesh.uv_layers.get(source)
    target_layer = mesh.uv_layers.get(target)
    if not source_layer or not target_layer:
        return None
    mesh.calc_loop_triangles()
    if len(mesh.loop_triangles) > 24000:
        return None
    positions, samples = [], []
    source_uv, target_uv = source_layer.uv, target_layer.uv
    for triangle in mesh.loop_triangles:
        for corner in triangle.loops:
            u_coord, v_coord = source_uv[corner].vector
            positions.append((origin + (u_coord - min_u) * scale, bottom + (v_coord - min_v) * scale))
            samples.append(tuple(target_uv[corner].vector))
    return make_batch(shader, "TRIS", {"pos": positions, "texCoord": samples}) if positions else None


_SOURCE_PREVIEW_SCALE = 0.55


def preview_layout(before, after, width, height):
    left, bottom, gap = 30, 70, 24
    side = min(270, (width - 2 * left - gap) / (1 + _SOURCE_PREVIEW_SCALE), height * 0.42)
    if side < 72:
        return None

    min_u = min_v = 0.0
    max_u = max_v = 1.0
    for points in (before, after):
        for u_coord, v_coord in points:
            min_u = min(min_u, u_coord)
            max_u = max(max_u, u_coord)
            min_v = min(min_v, v_coord)
            max_v = max(max_v, v_coord)
    scale = side / max(max_u - min_u, max_v - min_v)
    return left, bottom, gap, side, scale, min_u, min_v


def draw_uv_preview():
    context = bpy.context
    if not context.window_manager.uv_effects_preview:
        return
    modifier = active_effect(context)
    region = context.region
    if not modifier or not region or context.mode != "OBJECT":
        return

    import blf
    import gpu
    from gpu_extras.batch import batch_for_shader

    obj = context.object
    mesh = obj.evaluated_get(context.evaluated_depsgraph_get()).data
    if not mesh:
        return
    source = parameter(modifier, "Source UV").value
    target = parameter(modifier, "Output UV").value
    before = uv_edges(mesh if source != target and mesh.uv_layers.get(source) else obj.data, source)
    after = uv_edges(mesh, target)
    layout = preview_layout(before, after, region.width, region.height)
    if layout is None:
        return
    left, bottom, gap, side, scale, min_u, min_v = layout
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    texture = None
    if context.window_manager.uv_effects_uv_texture:
        image = preview_image(context)
        if image:
            try:
                texture = gpu.texture.from_image(image)
            except (RuntimeError, ValueError):
                pass
    image_shader = gpu.shader.from_builtin("IMAGE") if texture else None

    def lines(points, origin, panel_scale, color):
        if points:
            batch = batch_for_shader(shader, "LINES", {
                "pos": [(origin + (u_coord - min_u) * panel_scale,
                         bottom + (v_coord - min_v) * panel_scale, 0)
                        for u_coord, v_coord in points]
            })
            shader.bind()
            shader.uniform_float("color", color)
            batch.draw(shader)

    gpu.state.blend_set("ALPHA")
    try:
        panels = (
            (before, f"Source: {source}" if before else "Source UV unavailable", (0.54, 0.72, 0.82, 0.45)),
            (after, f"Output: {target}" if after else "Output UV unavailable", (1.0, 0.56, 0.14, 1.0)),
        )
        for index, (points, label, color) in enumerate(panels):
            ratio = 1.0 if index else _SOURCE_PREVIEW_SCALE
            panel_side = side * ratio
            panel_scale = scale * ratio
            origin = left + (side * _SOURCE_PREVIEW_SCALE + gap if index else 0)
            batch = None
            if image_shader:
                batch = preview_texture_batch(mesh, source, target if index else source, origin, bottom,
                                              panel_scale, min_u, min_v, image_shader, batch_for_shader)
            if batch:
                image_shader.bind()
                image_shader.uniform_sampler("image", texture)
                batch.draw(image_shader)
                label = "Result texture" if index else "Source texture"
            else:
                lines(points, origin, panel_scale, color)
            blf.size(0, 13 if index else 11)
            if blf.dimensions(0, label)[0] > panel_side:
                while label and blf.dimensions(0, label + "...")[0] > panel_side:
                    label = label[:-1]
                label += "..."
            blf.position(0, origin, bottom + panel_side + 12, 0)
            blf.color(0, *color)
            blf.draw(0, label)
    finally:
        gpu.state.blend_set("NONE")


class OBJECT_OT_uv_effects_reset(bpy.types.Operator):
    bl_idname = "object.uv_effects_reset"
    bl_label = "Reset UV Transform"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        modifier = active_effect(context)
        if not modifier:
            return {"CANCELLED"}
        parameter(modifier, "Remap Strength").value = 1.0
        parameter(modifier, "Soft Offset").value = 0.0
        for node in modifier.node_group.nodes:
            if node.bl_idname == "ShaderNodeFloatCurve":
                curve = node.mapping.curves[0]
                for point in list(curve.points)[1:-1]:
                    curve.points.remove(point)
                curve.points[0].location = (0.0, 0.0)
                curve.points[-1].location = (1.0, 1.0)
                node.mapping.update()
        modifier.node_group.update_tag()
        context.object.update_tag()
        return {"FINISHED"}


_preview_handle = None
_curve_states = {}


def curve_state(tree):
    return tuple(
        (node.name, tuple((tuple(point.location), point.handle_type)
                          for point in node.mapping.curves[0].points))
        for node in tree.nodes if node.bl_idname == "ShaderNodeFloatCurve"
    )


def refresh_live_curves():
    current = {}
    for window in bpy.context.window_manager.windows:
        with bpy.context.temp_override(window=window):
            modifier = active_effect(bpy.context)
            if not modifier:
                continue
            tree = modifier.node_group
            key = tree.as_pointer()
            state = current.get(key)
            if state is None:
                state = current[key] = curve_state(tree)
            previous = _curve_states.get(key)
            if previous is not None and previous != state:
                for node in tree.nodes:
                    if node.bl_idname == "ShaderNodeFloatCurve":
                        node.mapping.update()
                tree.update_tag()
                bpy.context.object.update_tag()
                bpy.context.view_layer.update()
                for area in window.screen.areas:
                    if area.type in {"VIEW_3D", "IMAGE_EDITOR"}:
                        area.tag_redraw()
    _curve_states.clear()
    _curve_states.update(current)
    return 1 / 30


def preview_image(context):
    chosen = context.window_manager.uv_effects_image
    if chosen:
        return chosen
    material = context.object.active_material
    if not material or not material.node_tree:
        return None
    images = {node.image for node in material.node_tree.nodes
              if node.type == "TEX_IMAGE" and node.image}
    return next(iter(images)) if len(images) == 1 else None


def build_displacement_group(name):
    tree = bpy.data.node_groups.new(name, "GeometryNodeTree")
    tree.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    tree.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nodes, link = tree.nodes, tree.links.new
    input_node = nodes.new("NodeGroupInput")
    output_node = nodes.new("NodeGroupOutput")
    uv = nodes.new("GeometryNodeInputNamedAttribute")
    uv.name = "Height UV"
    uv.data_type = "FLOAT_VECTOR"
    image = nodes.new("GeometryNodeImageTexture")
    image.name = "Height Image"
    tiling = nodes.new("ShaderNodeVectorMath")
    tiling.name = "Height Tiling"
    tiling.operation = "MULTIPLY"
    link(uv.outputs["Attribute"], tiling.inputs[0])
    link(tiling.outputs["Vector"], image.inputs["Vector"])
    centered = nodes.new("ShaderNodeMath")
    centered.operation = "SUBTRACT"
    centered.inputs[1].default_value = 0.5
    link(image.outputs["Color"], centered.inputs[0])
    strength = nodes.new("ShaderNodeMath")
    strength.name = "Height Strength"
    strength.operation = "MULTIPLY"
    link(centered.outputs[0], strength.inputs[0])
    direction = nodes.new("ShaderNodeVectorMath")
    direction.name = "Height Direction"
    direction.operation = "SCALE"
    nodes.new("GeometryNodeInputNormal").name = "Height Normal"
    link(strength.outputs[0], direction.inputs["Scale"])
    position = nodes.new("GeometryNodeSetPosition")
    link(input_node.outputs["Geometry"], position.inputs["Geometry"])
    link(uv.outputs["Exists"], position.inputs["Selection"])
    link(direction.outputs["Vector"], position.inputs["Offset"])
    link(position.outputs["Geometry"], output_node.inputs["Geometry"])
    return tree


def update_displacement(settings, context):
    effect = active_effect(context)
    if not effect or context.mode != "OBJECT":
        return
    obj = context.object
    name = f"UVFX Displacement Preview {effect.persistent_uid}"
    displacement = obj.modifiers.get(name)
    if not settings.uvfx_displace or not settings.uvfx_height:
        if displacement:
            displacement.show_viewport = False
        return
    if not displacement:
        displacement = obj.modifiers.new(name, "NODES")
        displacement.show_render = False
        displacement.is_active = False
        effect.is_active = True
    if not displacement.node_group or not displacement.node_group.nodes.get("Height Tiling"):
        displacement.node_group = build_displacement_group(name)
    tree = displacement.node_group
    nodes = tree.nodes
    nodes["Height Image"].inputs["Image"].default_value = settings.uvfx_height
    nodes["Height Tiling"].inputs[1].default_value = (*settings.uvfx_height_tiling, 1.0)
    nodes["Height UV"].inputs["Name"].default_value = parameter(
        effect, "Source UV" if settings.uvfx_vertex_source else "Output UV"
    ).value
    nodes["Height Strength"].inputs[1].default_value = settings.uvfx_height_strength
    direction = nodes["Height Direction"].inputs[0]
    for link in list(direction.links):
        tree.links.remove(link)
    if settings.uvfx_direction == "NORMAL":
        tree.links.new(nodes["Height Normal"].outputs[0], direction)
    else:
        direction.default_value = tuple(float(axis == settings.uvfx_direction) for axis in ("X", "Y", "Z"))
    displacement.show_viewport = True
    tree.update_tag()
    obj.update_tag()


def configure_distortion(tree, transform, texture, settings):
    nodes = tree.nodes
    flow = nodes.get("UVFX Flow Map")
    if not settings.uvfx_distort or not settings.uvfx_flow:
        tree.links.new(transform.outputs["Vector"], texture.inputs["Vector"])
        return
    if not flow:
        flow = nodes.new("ShaderNodeTexImage")
        flow.name = "UVFX Flow Map"
        tree.links.new(transform.outputs["Vector"], flow.inputs["Vector"])
        separate = nodes.new("ShaderNodeSeparateColor")
        tree.links.new(flow.outputs["Color"], separate.inputs[0])
        combine = nodes.new("ShaderNodeCombineXYZ")
        tree.links.new(separate.outputs["Red"], combine.inputs["X"])
        tree.links.new(separate.outputs["Green"], combine.inputs["Y"])
        center = nodes.new("ShaderNodeVectorMath")
        center.operation = "SUBTRACT"
        center.inputs[1].default_value = (0.5, 0.5, 0)
        tree.links.new(combine.outputs[0], center.inputs[0])
        strength = nodes.new("ShaderNodeVectorMath")
        strength.name = "UVFX Flow Strength"
        strength.operation = "SCALE"
        tree.links.new(center.outputs[0], strength.inputs[0])
        add = nodes.new("ShaderNodeVectorMath")
        add.name = "UVFX Flow UV"
        add.operation = "ADD"
        tree.links.new(transform.outputs["Vector"], add.inputs[0])
        tree.links.new(strength.outputs[0], add.inputs[1])
    flow.image = settings.uvfx_flow
    tiling = nodes.get("UVFX Flow Tiling")
    if not tiling:
        tiling = nodes.new("ShaderNodeVectorMath")
        tiling.name = "UVFX Flow Tiling"
        tiling.operation = "MULTIPLY"
        uv = next(node for node in nodes if node.type == "UVMAP")
        tree.links.new(uv.outputs["UV"], tiling.inputs[0])
        tree.links.new(tiling.outputs["Vector"], flow.inputs["Vector"])
    tiling.inputs[1].default_value = (*settings.uvfx_flow_tiling, 1.0)
    nodes["UVFX Flow Strength"].inputs["Scale"].default_value = settings.uvfx_flow_strength
    tree.links.new(nodes["UVFX Flow UV"].outputs[0], texture.inputs["Vector"])


_glow_viewports = {}


def restore_glow_viewports():
    for space, previous in _glow_viewports.values():
        try:
            space.shading.use_compositor = previous
        except ReferenceError:
            pass
    _glow_viewports.clear()


def update_glow(settings, context):
    scene = context.scene
    tree = scene.compositing_node_group
    owned = tree and tree.get("uvfx_glow_preview")
    if not settings.uvfx_glow:
        if owned:
            scene.compositing_node_group = None
            if tree.users == 0:
                bpy.data.node_groups.remove(tree)
        restore_glow_viewports()
        return
    if tree and not owned:
        return
    if not tree:
        tree = bpy.data.node_groups.new("UVFX Glow Preview", "CompositorNodeTree")
        tree["uvfx_glow_preview"] = True
        tree.interface.new_socket(name="Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        layers = tree.nodes.new("CompositorNodeRLayers")
        glare = tree.nodes.new("CompositorNodeGlare")
        glare.name = "UVFX Glow"
        glare.inputs["Type"].default_value = "Fog Glow"
        output = tree.nodes.new("NodeGroupOutput")
        tree.links.new(layers.outputs["Image"], glare.inputs["Image"])
        tree.links.new(glare.outputs["Image"], output.inputs["Image"])
        scene.compositing_node_group = tree
    glare = tree.nodes["UVFX Glow"]
    glare.inputs["Threshold"].default_value = settings.uvfx_glow_threshold
    glare.inputs["Strength"].default_value = settings.uvfx_glow_strength
    glare.inputs["Tint"].default_value = (*settings.uvfx_glow_color, 1.0)
    if context.area and context.area.type == "VIEW_3D":
        shading = context.space_data.shading
        space = context.space_data
        _glow_viewports.setdefault(space.as_pointer(), (space, shading.use_compositor))
        shading.use_compositor = "ALWAYS"
        context.area.tag_redraw()


def update_vertex_alpha(settings, context):
    obj = context.object
    if not obj or obj.type != "MESH" or obj.mode != "EDIT":
        return
    import bmesh

    mesh = obj.data
    editable = bmesh.from_edit_mesh(mesh)
    if not any(vertex.select and not vertex.hide for vertex in editable.verts):
        return
    layer = editable.verts.layers.float_color.get("UVFX Color")
    if not layer:
        layer = editable.verts.layers.float_color.new("UVFX Color")
        for vertex in editable.verts:
            vertex[layer] = (1.0, 1.0, 1.0, 1.0)
    for vertex in editable.verts:
        if vertex.select and not vertex.hide:
            red, green, blue, _ = vertex[layer]
            vertex[layer] = (red, green, blue, settings.uvfx_selected_alpha)
    bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
    modifier = active_effect(context)
    if modifier:
        preview = modifier.node_group.nodes.get("UV Effects Texture Preview")
        material = preview.inputs["Material"].default_value if preview else None
        if material and material.node_tree:
            configure_texture_transform(material, settings)
    if context.area:
        context.area.tag_redraw()


def configure_texture_transform(material, settings):
    tree = material.node_tree
    nodes = tree.nodes
    uv = next(node for node in nodes if node.type == "UVMAP")
    texture = next(node for node in nodes if node.type == "TEX_IMAGE")
    texture.extension = settings.uv_effects_wrap
    emission = next((node for node in nodes if node.type == "EMISSION"), None)
    if emission:
        emission.inputs["Strength"].default_value = 1.0
        color = texture.outputs["Color"]
        if settings.uvfx_color_remap:
            ramp = nodes.get("UVFX Color Remap")
            if not ramp:
                ramp = nodes.new("ShaderNodeValToRGB")
                ramp.name = "UVFX Color Remap"
                tree.links.new(color, ramp.inputs["Fac"])
            if not ramp.get("uvfx_editable_ramp"):
                ramp.color_ramp.elements[0].color = (*settings.uvfx_color_dark, 1.0)
                ramp.color_ramp.elements[1].color = (*settings.uvfx_color_light, 1.0)
                ramp["uvfx_editable_ramp"] = True
            color = ramp.outputs["Color"]
        tree.links.new(color, emission.inputs["Color"])
        output = next(node for node in nodes if node.type == "OUTPUT_MATERIAL" and node.is_active_output)
        surface = emission.outputs["Emission"]
        if settings.uvfx_transparency != "OPAQUE" or settings.uvfx_vertex_alpha:
            mix = nodes.get("UVFX Transparency")
            if not mix:
                mix = nodes.new("ShaderNodeMixShader")
                mix.name = "UVFX Transparency"
                transparent = nodes.new("ShaderNodeBsdfTransparent")
                tree.links.new(transparent.outputs[0], mix.inputs[1])
                tree.links.new(surface, mix.inputs[2])
            mode = settings.uvfx_transparency
            mask = texture.outputs["Alpha" if mode == "ALPHA" else "Color"] if mode != "OPAQUE" else None
            if settings.uvfx_vertex_alpha:
                attribute = nodes.get("UVFX Vertex Alpha")
                if not attribute:
                    attribute = nodes.new("ShaderNodeVertexColor")
                    attribute.name = "UVFX Vertex Alpha"
                    attribute.layer_name = "UVFX Color"
                if mask:
                    multiply = nodes.get("UVFX Combined Alpha")
                    if not multiply:
                        multiply = nodes.new("ShaderNodeMath")
                        multiply.name = "UVFX Combined Alpha"
                        multiply.operation = "MULTIPLY"
                    tree.links.new(attribute.outputs["Alpha"], multiply.inputs[0])
                    tree.links.new(mask, multiply.inputs[1])
                    mask = multiply.outputs[0]
                else:
                    mask = attribute.outputs["Alpha"]
            tree.links.new(mask, mix.inputs[0])
            surface = mix.outputs[0]
        tree.links.new(surface, output.inputs["Surface"])
    transform = nodes.get("UV Effects Tiling Offset")
    if not transform:
        transform = nodes.new("ShaderNodeVectorMath")
        transform.name = "UV Effects Tiling Offset"
        transform.operation = "MULTIPLY_ADD"
        tree.links.new(uv.outputs["UV"], transform.inputs[0])
        tree.links.new(transform.outputs["Vector"], texture.inputs["Vector"])
    transform.inputs[1].default_value = (*settings.uv_effects_tiling, 1.0)
    transform.inputs[2].default_value = (*settings.uv_effects_offset, 0.0)
    rotation = nodes.get("UV Effects Rotation")
    if not rotation:
        rotation = nodes.new("ShaderNodeVectorRotate")
        rotation.name = "UV Effects Rotation"
        rotation.rotation_type = "Z_AXIS"
        rotation.inputs["Center"].default_value = (0.5, 0.5, 0.0)
        tree.links.new(uv.outputs["UV"], rotation.inputs["Vector"])
        tree.links.new(rotation.outputs["Vector"], transform.inputs[0])
    rotation.inputs["Angle"].default_value = settings.uv_effects_rotation
    configure_distortion(tree, transform, texture, settings)


def update_texture_transform(settings, context):
    modifier = active_effect(context)
    if not modifier or context.mode not in {"OBJECT", "EDIT_MESH"}:
        return
    preview = modifier.node_group.nodes.get("UV Effects Texture Preview")
    if not preview or not preview.inputs["Selection"].default_value:
        if context.mode == "OBJECT" and preview_image(context):
            bpy.ops.object.uv_effects_texture(mode="OUTPUT")
        return
    material = preview.inputs["Material"].default_value
    if material and material.node_tree:
        configure_texture_transform(material, settings)
        if context.area:
            context.area.tag_redraw()


def update_preview_image(settings, context):
    modifier = active_effect(context)
    if not modifier or not settings.uv_effects_image or context.mode != "OBJECT":
        return
    preview = modifier.node_group.nodes.get("UV Effects Texture Preview")
    if not preview or not preview.inputs["Selection"].default_value:
        bpy.ops.object.uv_effects_texture(mode="OUTPUT")
        return
    material = preview.inputs["Material"].default_value
    if not material or not material.node_tree:
        return
    uv_node = next((node for node in material.node_tree.nodes if node.type == "UVMAP"), None)
    mode = preview.get("uv_effects_preview_mode")
    if mode not in {"SOURCE", "OUTPUT"}:
        mode = "OUTPUT" if uv_node and uv_node.uv_map == parameter(modifier, "Output UV").value else "SOURCE"
    bpy.ops.object.uv_effects_texture(mode=mode)


class OBJECT_OT_uv_effects_texture(bpy.types.Operator):
    bl_idname = "object.uv_effects_texture"
    bl_label = "Preview Texture on Model"
    bl_options = {"REGISTER", "UNDO"}

    mode: bpy.props.EnumProperty(items=(
        ("SOURCE", "Source", ""), ("OUTPUT", "Output", ""), ("OFF", "Off", ""),
    ))

    def execute(self, context):
        modifier = active_effect(context)
        if not modifier or context.mode != "OBJECT":
            return {"CANCELLED"}
        tree = modifier.node_group
        image = preview_image(context) if self.mode != "OFF" else None
        uv_name = ""
        if self.mode != "OFF":
            if not image:
                self.report({"WARNING"}, "请先选择一张预览贴图")
                return {"CANCELLED"}
            uv_name = parameter(modifier, "Source UV" if self.mode == "SOURCE" else "Output UV").value
            mesh = context.object.evaluated_get(context.evaluated_depsgraph_get()).data
            if not mesh.uv_layers.get(uv_name):
                self.report({"WARNING"}, "找不到预览所需的 UV 图层")
                return {"CANCELLED"}
        if tree.users > 1:
            tree = tree.copy()
            modifier.node_group = tree
        preview = tree.nodes.get("UV Effects Texture Preview")
        if self.mode == "OFF" and not preview:
            return {"FINISHED"}
        if not preview:
            output = next(node for node in tree.nodes if node.type == "GROUP_OUTPUT" and node.is_active_output)
            geometry = output.inputs["Geometry"]
            upstream = geometry.links[0].from_socket
            preview = tree.nodes.new("GeometryNodeSetMaterial")
            preview.name = "UV Effects Texture Preview"
            preview.location = (output.location.x, output.location.y - 200)
            tree.links.new(upstream, preview.inputs["Geometry"])
            tree.links.new(preview.outputs["Geometry"], geometry)
        preview.inputs["Selection"].default_value = self.mode != "OFF"
        if self.mode != "OFF":
            modifier.show_in_editmode = True
        preview["uv_effects_preview_mode"] = self.mode
        if self.mode != "OFF":
            slot = preview.inputs["Material"]
            material = slot.default_value
            if not material or material.users > 1:
                material = material.copy() if material else bpy.data.materials.new("UV Effects · Texture Preview")
                if not material.node_tree:
                    material.use_nodes = True
                slot.default_value = material
            nodes = material.node_tree.nodes
            uv = next((node for node in nodes if node.type == "UVMAP"), None)
            if not uv:
                nodes.clear()
                uv = nodes.new("ShaderNodeUVMap")
                nodes.new("ShaderNodeTexImage")
                nodes.new("ShaderNodeEmission")
                nodes.new("ShaderNodeOutputMaterial")
            uv.uv_map = uv_name
            texture = next(node for node in nodes if node.type == "TEX_IMAGE" and node.name != "UVFX Flow Map")
            texture.image = image
            configure_texture_transform(material, context.window_manager)
            if context.area and context.area.type == "VIEW_3D":
                context.space_data.shading.type = "MATERIAL"
        tree.update_tag()
        context.object.update_tag()
        return {"FINISHED"}


class OBJECT_OT_uv_effects_rotate(bpy.types.Operator):
    bl_idname = "object.uv_effects_rotate"
    bl_label = "Rotate Preview UV"
    bl_options = {"UNDO"}

    quarter_turn: bpy.props.IntProperty(default=0, min=-1, max=1)

    def execute(self, context):
        settings = context.window_manager
        angle = settings.uv_effects_rotation
        settings.uv_effects_rotation = (
            math.remainder(angle + self.quarter_turn * math.pi / 2, math.tau)
            if self.quarter_turn else 0.0
        )
        return {"FINISHED"}


class VIEW3D_PT_uv_effects(bpy.types.Panel):
    bl_label = "UV Effects"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "UV Effects"

    def draw(self, context):
        layout = self.layout
        layout.operator(OBJECT_OT_uv_effects_add.bl_idname, text="添加 UV 特效修改器", icon="ADD")
        modifier = active_effect(context)
        if not modifier:
            layout.label(text="选择模型并添加修改器")
            return
        channels = layout.box()
        channels.label(text=modifier.name, icon="MOD_UVPROJECT")
        maps = channels.row()
        maps.prop_search(parameter(modifier, "Source UV"), "value",
                         context.object.data, "uv_layers", text="输入")
        maps.prop(parameter(modifier, "Output UV"), "value", text="输出")
        comparison = channels.row(align=True)
        comparison.prop(context.window_manager, "uv_effects_preview", text="UV 对照")
        image_toggle = comparison.row(align=True)
        image_toggle.enabled = context.window_manager.uv_effects_preview
        image_toggle.prop(context.window_manager, "uv_effects_uv_texture", text="显示贴图")
        if context.mode != "OBJECT":
            channels.label(text="切到物体模式查看计算结果", icon="INFO")
        if parameter(modifier, "Source UV").value == parameter(modifier, "Output UV").value:
            channels.label(text="输入和输出同名，将覆盖计算结果", icon="ERROR")
        texture = layout.box()
        texture.label(text="模型贴图预览", icon="IMAGE_DATA")
        fields = texture.split(factor=0.63)
        transforms = fields.column(align=True)
        for prop_name, label in (("uv_effects_tiling", "Tiling"),
                                 ("uv_effects_offset", "Offset")):
            row = transforms.row(align=True)
            row.label(text=label)
            row.prop(context.window_manager, prop_name, index=0, text="X")
            row.prop(context.window_manager, prop_name, index=1, text="Y")
        fields.column().prop(context.window_manager, "uv_effects_image", text="")
        texture.prop(context.window_manager, "uv_effects_wrap", text="Wrap")
        rotation = texture.split(factor=0.47)
        rotation.prop(context.window_manager, "uv_effects_rotation", text="旋转")
        turns = rotation.row(align=True)
        for step, label, icon in ((-1, "90°", "LOOP_BACK"), (0, "归零", "NONE"), (1, "90°", "LOOP_FORWARDS")):
            turns.operator(OBJECT_OT_uv_effects_rotate.bl_idname, text=label, icon=icon).quarter_turn = step
        if not preview_image(context):
            texture.label(text="请选择预览贴图", icon="INFO")
        preview = modifier.node_group.nodes.get("UV Effects Texture Preview")
        mode = "OFF"
        if preview and preview.inputs["Selection"].default_value:
            mode = preview.get("uv_effects_preview_mode")
            if not mode:
                material = preview.inputs["Material"].default_value
                uv_node = next((node for node in material.node_tree.nodes if node.type == "UVMAP"), None) if material and material.node_tree else None
                mode = "OUTPUT" if uv_node and uv_node.uv_map == parameter(modifier, "Output UV").value else "SOURCE"
        controls = texture.row(align=True)
        controls.enabled = context.mode == "OBJECT"
        for choice, label in (("OUTPUT", "结果 UV"), ("SOURCE", "原始 UV"), ("OFF", "原材质")):
            controls.operator(OBJECT_OT_uv_effects_texture.bl_idname, text=label,
                              depress=mode == choice).mode = choice
        colors = texture.row(align=True)
        colors.prop(context.window_manager, "uvfx_color_remap", text="颜色映射")
        if context.window_manager.uvfx_color_remap:
            material = preview.inputs["Material"].default_value if preview else None
            ramp = material.node_tree.nodes.get("UVFX Color Remap") if material and material.node_tree else None
            if ramp:
                texture.template_color_ramp(ramp, "color_ramp", expand=True)
            else:
                texture.label(text="开启结果 UV 预览以编辑渐变", icon="INFO")
        texture.prop(context.window_manager, "uvfx_transparency", text="透明")
        effects = layout.column()
        effects.label(text="效果预览")
        settings = context.window_manager
        vertex_alpha = effects.box()
        alpha_row = vertex_alpha.row(align=True)
        alpha_row.prop(settings, "uvfx_vertex_alpha", text="顶点 Alpha 预览")
        slider = alpha_row.row()
        slider.enabled = context.mode == "EDIT_MESH"
        slider.prop(settings, "uvfx_selected_alpha", text="所选 Alpha", slider=True)
        displacement = effects.box()
        displacement.prop(settings, "uvfx_displace")
        if settings.uvfx_displace:
            fields = displacement.box().column(align=True)
            fields.prop(settings, "uvfx_height", text="灰度高度图")
            tiling = fields.row(align=True)
            tiling.label(text="Tiling")
            tiling.prop(settings, "uvfx_height_tiling", index=0, text="X")
            tiling.prop(settings, "uvfx_height_tiling", index=1, text="Y")
            fields.prop(settings, "uvfx_height_strength")
            fields.prop(settings, "uvfx_direction")
            fields.prop(settings, "uvfx_vertex_source")
        distortion = effects.box()
        distortion.prop(settings, "uvfx_distort")
        if settings.uvfx_distort:
            fields = distortion.box().column(align=True)
            fields.prop(settings, "uvfx_flow", text="RG 流向图")
            tiling = fields.row(align=True)
            tiling.label(text="Tiling")
            tiling.prop(settings, "uvfx_flow_tiling", index=0, text="X")
            tiling.prop(settings, "uvfx_flow_tiling", index=1, text="Y")
            fields.prop(settings, "uvfx_flow_strength")
        bloom = effects.box()
        compositor = context.scene.compositing_node_group
        if compositor and not compositor.get("uvfx_glow_preview"):
            bloom.label(text="当前场景有合成节点，不会覆盖", icon="INFO")
        else:
            bloom.prop(settings, "uvfx_glow")
            if settings.uvfx_glow:
                fields = bloom.box().column(align=True)
                fields.prop(settings, "uvfx_glow_threshold")
                fields.prop(settings, "uvfx_glow_strength")
                fields.prop(settings, "uvfx_glow_color", text="辉光色")
                fields.label(text="场景级效果，测试后请关闭", icon="INFO")
        for title, name, label in (
            ("拉伸 / 挤压", "Remap Strength", "Stretch / Squeeze"),
            ("软偏移", "Soft Offset", "Soft Offset Falloff"),
        ):
            section = layout.box()
            section.label(text=title)
            section.prop(parameter(modifier, name), "value", text="强度")
            curve = next(node for node in modifier.node_group.nodes if node.label == label)
            section.template_curve_mapping(curve, "mapping")
        layout.operator(OBJECT_OT_uv_effects_reset.bl_idname, text="重置曲线与强度")


class OBJECT_OT_uvfx_mesh(bpy.types.Operator):
    bl_idname = "object.uvfx_mesh"
    bl_label = "特效网格"
    bl_options = {"REGISTER", "UNDO"}

    edit_existing: bpy.props.BoolProperty(options={"HIDDEN", "SKIP_SAVE"})
    shape: bpy.props.EnumProperty(items=(("RING", "环片", ""), ("STRIP", "条带", "")))
    def get_length(self):
        return self.get("length_value", 1.0)

    def set_length(self, value):
        minimum = self.inner_radius + 0.001 if self.shape == "RING" else 0.001
        self["length_value"] = max(minimum, value)

    def get_inner_radius(self):
        return min(self.get("inner_radius_value", 0.65), max(0.0, self.length - 0.001))

    def set_inner_radius(self, value):
        self["inner_radius_value"] = min(max(0.0, value), max(0.0, self.length - 0.001))

    length: bpy.props.FloatProperty(name="长度 / 外半径", min=0.001, step=1,
                                    get=get_length, set=set_length)
    inner_radius: bpy.props.FloatProperty(name="内半径", min=0.0, step=1,
                                          get=get_inner_radius, set=set_inner_radius)
    width: bpy.props.FloatProperty(name="宽度", default=0.35, min=0.001, step=1)
    arc: bpy.props.FloatProperty(name="弧度", subtype="ANGLE", default=math.tau, min=0.001, max=math.tau)
    segments: bpy.props.IntProperty(name="长度分段", default=48, min=3, max=512)
    rows: bpy.props.IntProperty(name="宽度分段", default=8, min=1, max=128)

    def invoke(self, context, event):
        if context.mode != "OBJECT":
            return {"CANCELLED"}
        if self.edit_existing:
            obj = context.object
            values = obj.get("uvfx_mesh") if obj and obj.type == "MESH" else None
            if not values:
                self.report({"WARNING"}, "请先选中插件生成的环片或条带")
                return {"CANCELLED"}
            for field in ("shape", "length", "width", "arc", "segments", "rows"):
                if field == "length":
                    self["length_value"] = values[field]
                else:
                    setattr(self, field, values[field])
            self.inner_radius = values.get("inner_radius", self.length - self.width)
            self._preview_object = obj
            self._original_mesh = obj.data
        return context.window_manager.invoke_props_dialog(self)

    def restore_preview(self):
        obj = getattr(self, "_preview_object", None)
        if obj is not None and obj.data != self._original_mesh:
            temporary = obj.data
            obj.data = self._original_mesh
            if not temporary.users:
                bpy.data.meshes.remove(temporary)

    def check(self, context):
        obj = getattr(self, "_preview_object", None)
        if obj is None:
            return True
        self.restore_preview()
        mesh = self.build_mesh(context, obj)
        for material in self._original_mesh.materials:
            mesh.materials.append(material)
        obj.data = mesh
        if context.area:
            context.area.tag_redraw()
        return True

    def cancel(self, context):
        self.restore_preview()

    def draw(self, context):
        self.layout.prop(self, "shape", expand=True)
        self.layout.prop(self, "length", text="外半径" if self.shape == "RING" else "长度")
        self.layout.prop(self, "inner_radius" if self.shape == "RING" else "width")
        if self.shape == "RING":
            self.layout.prop(self, "arc")
        row = self.layout.row(align=True)
        row.prop(self, "segments")
        row.prop(self, "rows")

    def build_mesh(self, context, obj):
        ring = self.shape == "RING"
        closed = ring and abs(self.arc - math.tau) < 1e-5
        stride = self.rows + 1
        vertices, faces, uvs = [], [], []
        for column in range(self.segments if closed else self.segments + 1):
            u_coord = column / self.segments
            angle = self.arc * u_coord
            for row in range(stride):
                v_coord = row / self.rows
                if ring:
                    radius = self.inner_radius + (self.length - self.inner_radius) * v_coord
                    vertices.append((radius * math.cos(angle), radius * math.sin(angle), 0))
                else:
                    vertices.append(((u_coord - 0.5) * self.length, (v_coord - 0.5) * self.width, 0))
        for column in range(self.segments):
            following = (column + 1) % (self.segments if closed else self.segments + 1)
            for row in range(self.rows):
                first = column * stride + row
                second = following * stride + row
                corners = (first, second, second + 1, first + 1)
                coords = ((column / self.segments, row / self.rows),
                          ((column + 1) / self.segments, row / self.rows),
                          ((column + 1) / self.segments, (row + 1) / self.rows),
                          (column / self.segments, (row + 1) / self.rows))
                if ring and self.inner_radius == 0.0 and row == 0:
                    corners = (0, second + 1, first + 1)
                    coords = (coords[0], coords[2], coords[3])
                faces.append(corners[::-1] if ring else corners)
                uvs.extend(coords[::-1] if ring else coords)
        mesh = bpy.data.meshes.new("UVFX Ring" if ring else "UVFX Strip")
        if ring and self.inner_radius == 0.0:
            indices = {index: index - max(0, (index - 1) // stride)
                       for index in range(len(vertices)) if index == 0 or index % stride}
            faces = [tuple(indices[index] for index in face) for face in faces]
            vertices = [vertex for index, vertex in enumerate(vertices) if index in indices]
        mesh.from_pydata(vertices, [], faces)
        previous = obj.data if obj else None
        effect = active_effect(context) if obj else None
        source = parameter(effect, "Source UV").value if effect else (
            previous.uv_layers.active.name if previous and previous.uv_layers.active else "UVMap"
        )
        layer = mesh.uv_layers.new(name=source or "UVMap")
        layer.uv.foreach_set("vector", [value for coord in uvs for value in coord])
        if closed:
            for edge in mesh.edges:
                edge.use_seam = all(vertex < stride for vertex in edge.vertices)
        return mesh

    def execute(self, context):
        self.restore_preview()
        if context.mode != "OBJECT":
            return {"CANCELLED"}
        obj = context.object if self.edit_existing else None
        if self.edit_existing and (not obj or not obj.get("uvfx_mesh")):
            return {"CANCELLED"}
        previous = obj.data if obj else None
        mesh = self.build_mesh(context, obj)
        if obj:
            for material in previous.materials:
                mesh.materials.append(material)
            obj.data = mesh
            if previous.users == 0:
                bpy.data.meshes.remove(previous)
        else:
            obj = bpy.data.objects.new(mesh.name, mesh)
            context.collection.objects.link(obj)
            obj.location = context.scene.cursor.location
            for selected in context.selected_objects:
                selected.select_set(False)
            obj.select_set(True)
            context.view_layer.objects.active = obj
            add_modifier(obj, mesh.uv_layers.active.name, "UV_Effects", "V")
        obj["uvfx_mesh"] = {field: getattr(self, field) for field in
                           ("shape", "length", "width", "inner_radius", "arc", "segments", "rows")}
        return {"FINISHED"}


def uv_seam_edges(mesh, name):
    layer = mesh.uv_layers.get(name)
    if not layer:
        return []
    pairs, seams = {}, set()
    uv = layer.uv
    for polygon in mesh.polygons:
        start, total = polygon.loop_start, polygon.loop_total
        for offset in range(total):
            loop = mesh.loops[start + offset]
            following = mesh.loops[start + (offset + 1) % total]
            edge = mesh.edges[loop.edge_index]
            coords = (uv[loop.index].vector.copy(), uv[following.index].vector.copy())
            if loop.vertex_index != edge.vertices[0]:
                coords = coords[::-1]
            previous = pairs.setdefault(edge.index, coords)
            if any((first - second).length_squared > 1e-10 for first, second in zip(previous, coords)):
                seams.add(edge.index)
    return [mesh.vertices[vertex].co for index in seams for vertex in mesh.edges[index].vertices]


def draw_uv_seams():
    context = bpy.context
    if not context.window_manager.uvfx_seams or context.mode != "OBJECT":
        return
    effect = active_effect(context)
    if not effect:
        return
    obj = context.object
    mesh = obj.evaluated_get(context.evaluated_depsgraph_get()).data
    points = uv_seam_edges(mesh, parameter(effect, "Source UV").value)
    if not points:
        return
    import gpu
    from gpu_extras.batch import batch_for_shader

    shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
    batch = batch_for_shader(shader, "LINES", {"pos": [obj.matrix_world @ point for point in points]})
    shader.bind()
    shader.uniform_float("viewportSize", (context.region.width, context.region.height))
    shader.uniform_float("lineWidth", 3.0)
    shader.uniform_float("color", (1.0, 0.22, 0.68, 1.0))
    batch.draw(shader)


class VIEW3D_PT_uvfx_mesh(bpy.types.Panel):
    bl_label = "特效网格"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "UV Effects"
    bl_parent_id = "VIEW3D_PT_uv_effects"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        row.enabled = context.mode == "OBJECT"
        for shape, label in (("RING", "新建环片"), ("STRIP", "新建条带")):
            create = row.operator(OBJECT_OT_uvfx_mesh.bl_idname, text=label)
            create.shape = shape
            create.edit_existing = False
        if context.object and context.object.get("uvfx_mesh"):
            layout.operator(OBJECT_OT_uvfx_mesh.bl_idname, text="重设尺寸与分段").edit_existing = True
        layout.prop(context.window_manager, "uvfx_seams", text="标出 UV 接缝")
        effect = active_effect(context)
        if context.window_manager.uvfx_seams and effect:
            layout.label(text="粉色：原始 UV 断边，不代表纹理一定断开")
            if context.window_manager.uv_effects_wrap == "EXTEND":
                layout.label(text="环片周向跨 0–1 时，Clamp 会拉伸边缘", icon="INFO")


_seam_handle = None


CLASSES = (OBJECT_OT_uv_effects_add, OBJECT_OT_uv_effects_demo, OBJECT_OT_uv_effects_reset,
           OBJECT_OT_uv_effects_texture, OBJECT_OT_uv_effects_rotate, OBJECT_OT_uvfx_mesh,
           VIEW3D_PT_uv_effects, VIEW3D_PT_uvfx_mesh)


def register():
    global _preview_handle, _seam_handle
    bpy.types.WindowManager.uvfx_vertex_alpha = bpy.props.BoolProperty(
        name="顶点 Alpha 预览", update=update_texture_transform
    )
    bpy.types.WindowManager.uvfx_selected_alpha = bpy.props.FloatProperty(
        name="所选顶点 Alpha", default=1.0, min=0.0, max=1.0, update=update_vertex_alpha
    )
    bpy.types.WindowManager.uvfx_seams = bpy.props.BoolProperty(name="UV Seam Overlay")
    bpy.types.WindowManager.uvfx_transparency = bpy.props.EnumProperty(
        name="透明预览",
        items=(
            ("OPAQUE", "不透明", "Show the texture without a transparency mask"),
            ("ALPHA", "贴图 Alpha", "Use the image alpha channel as opacity"),
            ("LUMA", "亮度去黑", "Use the original texture brightness as opacity"),
        ),
        default="OPAQUE", update=update_texture_transform,
    )
    bpy.types.WindowManager.uvfx_color_remap = bpy.props.BoolProperty(
        name="颜色映射", update=update_texture_transform
    )
    for name, label, default, callback in (
        ("color_dark", "暗部颜色", (0.0, 0.0, 0.0), update_texture_transform),
        ("color_light", "亮部颜色", (1.0, 1.0, 1.0), update_texture_transform),
        ("glow_color", "辉光颜色", (1.0, 1.0, 1.0), update_glow),
    ):
        setattr(bpy.types.WindowManager, f"uvfx_{name}", bpy.props.FloatVectorProperty(
            name=label, subtype="COLOR", size=3, min=0.0, max=1.0, default=default, update=callback
        ))
    bpy.types.WindowManager.uvfx_glow = bpy.props.BoolProperty(name="辉光", update=update_glow)
    bpy.types.WindowManager.uvfx_glow_threshold = bpy.props.FloatProperty(
        name="阈值", default=1.0, min=0.0, update=update_glow
    )
    bpy.types.WindowManager.uvfx_glow_strength = bpy.props.FloatProperty(
        name="扩散强度", default=1.0, min=0.0, update=update_glow
    )
    bpy.types.WindowManager.uvfx_height_tiling = bpy.props.FloatVectorProperty(
        name="Height Tiling", size=2, default=(1.0, 1.0), update=update_displacement
    )
    bpy.types.WindowManager.uvfx_flow_tiling = bpy.props.FloatVectorProperty(
        name="Flow Tiling", size=2, default=(1.0, 1.0), update=update_texture_transform
    )

    bpy.types.WindowManager.uvfx_displace = bpy.props.BoolProperty(name="顶点置换", update=update_displacement)
    bpy.types.WindowManager.uvfx_height = bpy.props.PointerProperty(type=bpy.types.Image, update=update_displacement)
    bpy.types.WindowManager.uvfx_vertex_source = bpy.props.BoolProperty(name="读取原始 UV", update=update_displacement)
    bpy.types.WindowManager.uvfx_height_strength = bpy.props.FloatProperty(name="置换强度", default=0.1, update=update_displacement)
    bpy.types.WindowManager.uvfx_direction = bpy.props.EnumProperty(
        name="方向", items=tuple((axis, axis, "") for axis in ("NORMAL", "X", "Y", "Z")),
        default="NORMAL", update=update_displacement,
    )
    bpy.types.WindowManager.uvfx_distort = bpy.props.BoolProperty(name="纹理扭曲", update=update_texture_transform)
    bpy.types.WindowManager.uvfx_flow = bpy.props.PointerProperty(type=bpy.types.Image, update=update_texture_transform)
    bpy.types.WindowManager.uvfx_flow_strength = bpy.props.FloatProperty(name="扭曲强度", default=0.1, update=update_texture_transform)
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.uv_effects_image = bpy.props.PointerProperty(
        type=bpy.types.Image, update=update_preview_image
    )
    bpy.types.WindowManager.uv_effects_tiling = bpy.props.FloatVectorProperty(
        name="Tiling", size=2, default=(1.0, 1.0), update=update_texture_transform
    )
    bpy.types.WindowManager.uv_effects_offset = bpy.props.FloatVectorProperty(
        name="Offset", size=2, default=(0.0, 0.0), update=update_texture_transform
    )
    bpy.types.WindowManager.uv_effects_rotation = bpy.props.FloatProperty(
        name="UV Rotation", subtype="ANGLE", update=update_texture_transform
    )
    bpy.types.WindowManager.uv_effects_wrap = bpy.props.EnumProperty(
        name="Texture Wrap",
        items=(
            ("REPEAT", "Repeat", "Repeat the texture outside the UV tile"),
            ("EXTEND", "Clamp", "Extend the edge pixels outside the UV tile"),
            ("MIRROR", "Mirror", "Repeat with alternating mirrored tiles"),
        ),
        default="REPEAT", update=update_texture_transform,
    )
    bpy.types.WindowManager.uv_effects_uv_texture = bpy.props.BoolProperty(
        name="Compare Texture", default=False, options={"SKIP_SAVE"}
    )
    bpy.types.WindowManager.uv_effects_preview = bpy.props.BoolProperty(
        name="UV Comparison", default=True, options={"SKIP_SAVE"}
    )
    if not bpy.app.background:
        _preview_handle = bpy.types.SpaceView3D.draw_handler_add(draw_uv_preview, (), "WINDOW", "POST_PIXEL")
        _seam_handle = bpy.types.SpaceView3D.draw_handler_add(draw_uv_seams, (), "WINDOW", "POST_VIEW")
        bpy.app.timers.register(refresh_live_curves, persistent=True)


def unregister():
    global _preview_handle, _seam_handle
    if _seam_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_seam_handle, "WINDOW")
        _seam_handle = None
    del bpy.types.WindowManager.uvfx_seams
    restore_glow_viewports()
    for scene in bpy.data.scenes:
        tree = scene.compositing_node_group
        if tree and tree.get("uvfx_glow_preview"):
            scene.compositing_node_group = None
            if tree.users == 0:
                bpy.data.node_groups.remove(tree)
    if bpy.app.timers.is_registered(refresh_live_curves):
        bpy.app.timers.unregister(refresh_live_curves)
    _curve_states.clear()
    if _preview_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_preview_handle, "WINDOW")
        _preview_handle = None
    del bpy.types.WindowManager.uv_effects_preview
    del bpy.types.WindowManager.uv_effects_image
    del bpy.types.WindowManager.uv_effects_tiling
    del bpy.types.WindowManager.uv_effects_offset
    del bpy.types.WindowManager.uv_effects_rotation
    del bpy.types.WindowManager.uv_effects_wrap
    for name in ("displace", "height", "vertex_source", "height_strength",
                 "direction", "distort", "flow", "flow_strength", "height_tiling", "flow_tiling",
                 "glow", "glow_threshold", "glow_strength",
                 "color_remap", "color_dark", "color_light", "glow_color", "transparency",
                 "vertex_alpha", "selected_alpha"):
        delattr(bpy.types.WindowManager, f"uvfx_{name}")
    del bpy.types.WindowManager.uv_effects_uv_texture
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
