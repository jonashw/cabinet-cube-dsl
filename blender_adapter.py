"""
Cabinet Cube DSL — Blender adapter.

Turns geometry.py's pure-Python output (planes, wireframe edges) into
actual Blender data: bmesh geometry, materials, camera, world. This is
the only module in cube_dsl that imports bpy.

Usage from a live Blender session (e.g. via the MCP execute_blender_code
tool) — point sys.path at the repo root once per session, then import
normally:

    import sys
    sys.path.insert(0, "/Users/jwilson4/personal_repos/blender-mcp-demo")
    import cube_dsl.geometry as geo
    import cube_dsl.blender_adapter as ba
    import importlib; importlib.reload(geo); importlib.reload(ba)

    ba.setup_scene()                                    # camera + white world, once
    wire = ba.build_wireframe_object("CabinetProjectionCube")
    mat  = ba.make_photo_material("CityscapePhoto", "/path/to/cityscape.png")
    shape = ba.build_shape_object("ShapeMesh", {"y": [-1, 1]}, mat)  # "sandwich"
    ba.render_shape(shape, "/tmp/out.png")

Every function here takes plain data in (a dict spec, a color tuple, a
file path) and returns/updates a bpy object — no hidden global state
beyond the Blender scene itself.
"""

from __future__ import annotations

import bpy
import bmesh

from . import geometry as geo


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------

def make_flat_material(name: str, color=(0.0, 0.0, 0.0, 1.0)) -> "bpy.types.Material":
    """Unlit emission material — renders as exactly `color`, ignoring scene lighting."""
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    emit = nt.nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = color
    emit.inputs["Strength"].default_value = 1.0
    nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    return mat


def make_photo_material(name: str, image_path: str) -> "bpy.types.Material":
    """Unlit emission material textured with the image at image_path."""
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    emit = nt.nodes.new("ShaderNodeEmission")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(image_path, check_existing=True)
    nt.links.new(tex.outputs["Color"], emit.inputs["Color"])
    emit.inputs["Strength"].default_value = 1.0
    nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    return mat


# ---------------------------------------------------------------------------
# Wireframe
# ---------------------------------------------------------------------------

def add_wireframe_to_bmesh(
    bm: "bmesh.types.BMesh",
    line_width: float = 0.04,
    joint_segments: int = 32,
    stroke_eps: float = 0.003,
    joint_eps: float = 0.006,
) -> None:
    """
    Add the cube's 12 fixed edges to bm as flat ribbon quads, with a
    round join (a small filled disc) at every vertex.

    The disc radius equals half the stroke width, which is exactly the
    distance from a vertex to every incident stroke's corner — so the
    join closes every gap with no overlap and no seam, regardless of
    the angle between edges meeting there. See geometry.wireframe_edges
    for why depth (Z) is true per-vertex rather than a flat offset:
    that's what makes this wireframe occlude correctly against
    whichever planes are solid, with no special-casing per shape.

    stroke_eps / joint_eps lift the wireframe a hair toward the camera
    relative to its native depth, so an edge lying exactly on a solid
    face's own boundary doesn't z-fight with that face.
    """
    import math

    half = line_width / 2
    edges = geo.wireframe_edges()

    for edge in edges:
        (xa, ya, za), (xb, yb, zb) = edge.a, edge.b
        dx, dy = xb - xa, yb - ya
        length = math.hypot(dx, dy)
        ux, uy = dx / length, dy / length
        nx, ny = -uy * half, ux * half
        v1 = bm.verts.new((xa + nx, ya + ny, za + stroke_eps))
        v2 = bm.verts.new((xa - nx, ya - ny, za + stroke_eps))
        v3 = bm.verts.new((xb - nx, yb - ny, zb + stroke_eps))
        v4 = bm.verts.new((xb + nx, yb + ny, zb + stroke_eps))
        bm.faces.new((v1, v2, v3, v4))

    for (x, y, z) in geo.CUBE_VERTS_LOGICAL.values():
        rx, ry, rz = geo.render_point(x, y, z)
        ring = []
        for i in range(joint_segments):
            a = 2 * math.pi * i / joint_segments
            ring.append(bm.verts.new((rx + half * math.cos(a), ry + half * math.sin(a), rz + joint_eps)))
        bm.faces.new(ring)


def build_wireframe_object(
    name: str = "CabinetProjectionCube",
    material: "bpy.types.Material | None" = None,
    **wireframe_kwargs,
) -> "bpy.types.Object":
    """Create (or replace) the standalone wireframe object. Reused as-is across every shape — it doesn't depend on any spec."""
    old = bpy.data.objects.get(name)
    if old:
        old_mesh = old.data
        bpy.data.objects.remove(old, do_unlink=True)
        bpy.data.meshes.remove(old_mesh)

    bm = bmesh.new()
    add_wireframe_to_bmesh(bm, **wireframe_kwargs)
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    mat = material or make_flat_material("PureBlackLine")
    obj.data.materials.append(mat)
    return obj


# ---------------------------------------------------------------------------
# Shape (the DSL-driven solid planes)
# ---------------------------------------------------------------------------

def add_spec_to_bmesh(bm: "bmesh.types.BMesh", spec: dict) -> None:
    """Add every plane in spec (see geometry.planes_for_spec) to bm, with UVs."""
    uv_layer = bm.loops.layers.uv.verify() if bm.loops.layers.uv.active is None else bm.loops.layers.uv.active
    for plane in geo.planes_for_spec(spec):
        verts = [bm.verts.new(p) for p in plane.verts]
        face = bm.faces.new(verts)
        for loop, uv in zip(face.loops, plane.uvs):
            loop[uv_layer].uv = uv


def build_shape_object(
    name: str,
    spec: dict,
    material: "bpy.types.Material",
) -> "bpy.types.Object":
    """
    Create (or replace the mesh data of) the named object so it renders
    exactly `spec`, filled with `material`. Safe to call repeatedly on
    the same name to swap shapes without accumulating objects.
    """
    bm = bmesh.new()
    add_spec_to_bmesh(bm, spec)
    new_mesh = bpy.data.meshes.new(f"{name}Mesh")
    bm.to_mesh(new_mesh)
    bm.free()
    new_mesh.materials.append(material)

    obj = bpy.data.objects.get(name)
    if obj is None:
        obj = bpy.data.objects.new(name, new_mesh)
        bpy.context.scene.collection.objects.link(obj)
    else:
        old_mesh = obj.data
        obj.data = new_mesh
        bpy.data.meshes.remove(old_mesh)
    return obj


# ---------------------------------------------------------------------------
# Camera / world / scene
# ---------------------------------------------------------------------------

def _render_space_bounds(margin: float = 0.0):
    pts = [geo.render_point(*p) for p in geo.CUBE_VERTS_LOGICAL.values()]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs) - margin, max(xs) + margin, min(ys) - margin, max(ys) + margin)


def setup_camera(name: str = "CabinetCubeCam", frame_margin: float = 1.25) -> "bpy.types.Object":
    """
    Create (or reuse) a fixed orthographic camera, framed dead-on to
    the cube's render-space bounds — X/Y axis-aligned, looking straight
    down -Z. This is what makes the shear in geometry.py read as a
    cabinet projection rather than a generic 3D view: the camera does
    nothing but flatten it.
    """
    x_min, x_max, y_min, y_max = _render_space_bounds()
    cx, cy = (x_min + x_max) / 2, (y_min + y_max) / 2
    span = (x_max - x_min) * frame_margin

    cam_data = bpy.data.cameras.get(name) or bpy.data.cameras.new(name)
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = span

    cam_obj = bpy.data.objects.get(name)
    if cam_obj is None:
        cam_obj = bpy.data.objects.new(name, cam_data)
        bpy.context.scene.collection.objects.link(cam_obj)
    cam_obj.location = (cx, cy, 10.0)
    cam_obj.rotation_euler = (0.0, 0.0, 0.0)  # default orientation looks down -Z, up = +Y
    bpy.context.scene.camera = cam_obj
    return cam_obj


def setup_world_white(strength: float = 1.0) -> None:
    """Pure white world background (so open/unfilled cube regions render as (255,255,255))."""
    world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background") or world.node_tree.nodes.new("ShaderNodeBackground")
    bg.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    bg.inputs["Strength"].default_value = strength


def setup_render_settings(resolution: int = 800, samples: int = 32) -> None:
    """Cycles, Standard view transform (no filmic/AgX curve), square resolution."""
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.render.film_transparent = False
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"


def setup_scene(camera_name: str = "CabinetCubeCam", resolution: int = 800, samples: int = 32) -> "bpy.types.Object":
    """One-call convenience: white world + render settings + framed camera. Call once per session; the objects it creates are safe to reuse."""
    setup_world_white()
    setup_render_settings(resolution=resolution, samples=samples)
    return setup_camera(camera_name)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_shape(obj: "bpy.types.Object", output_path: str, isolate: bool = True) -> str:
    """
    Render the current scene to output_path. If isolate is True,
    temporarily excludes every top-level collection *other than* the
    one containing obj and the wireframe from the active view layer,
    so pre-existing scene content (e.g. a user's own default Cube)
    doesn't leak into the frame. Restores exclusion state afterward.
    """
    scene = bpy.context.scene
    excluded = []
    if isolate:
        target_coll = obj.users_collection[0] if obj.users_collection else scene.collection
        for lc in bpy.context.view_layer.layer_collection.children:
            if lc.collection is not target_coll and not lc.exclude:
                lc.exclude = True
                excluded.append(lc)
    try:
        scene.render.filepath = output_path
        bpy.ops.render.render(write_still=True)
    finally:
        for lc in excluded:
            lc.exclude = False
    return output_path
