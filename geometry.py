"""
Cabinet Cube DSL — geometry core.

No Blender / bpy dependency. Everything here is plain Python so it can be
read, tested, and reasoned about without a running Blender instance. The
Blender-specific half (turning this module's output into bmesh geometry,
materials, a camera, world settings) lives in blender_adapter.py.

Coordinate convention
----------------------
Logical cube space: (x, y, z), each in [-1, 1].
    x : left (-1)  / right (+1)
    y : bottom(-1) / top   (+1)
    z : back (-1)  / front (+1)   <- +1 is nearest the viewer

Render-space transform
-----------------------
Every logical point maps into render space by one fixed linear shear:

    X = x - 0.5*z + 1.5
    Y = y - 0.5*z + 1.5
    Z = z + 1

This is a cabinet-oblique projection: it's derived from choosing the
front-face edge length = 2 units and the depth offset = 1 unit (i.e. an
inner-square : margin ratio of 1:1 — the "3x3 grid" construction: the
front face occupies 2 grid units, the depth recedes 1 unit). A real
Blender camera never needs to know this — it's an orthographic camera
looking straight down -Z at this already-sheared geometry; the shear
itself is what produces the cabinet-projection look, not the camera.

Because the transform is linear and defined for *any* z (not just the
cube's own ±1 boundary), a "plane inserted at some position along an
axis" and a "face of the cube" are literally the same primitive — a
cube face is just the special case where position = ±1.

The DSL
-------
A shape spec is a dict with up to three keys — "x", "y", "z" — each
mapping to a list of numbers in [-1, 1]. Every number in a list inserts
one solid plane perpendicular to that axis, at that position, spanning
the other two axes' full [-1, 1] range. An axis absent from the dict
means no planes on that axis (that direction stays open). See
schema.json for the formal grammar (and note it is deliberately
data-format-agnostic: a spec can arrive as a JSON file, a pasted
snippet, or a plain Python dict literal — anything that satisfies the
schema is valid input to this module).

The wireframe (the cube's own 12 edges) is a separate, fixed thing: it
does not depend on the spec at all, and is always drawn in full — this
system does not do hidden-line removal on the wireframe itself, only on
solid planes occluding it (see wireframe_edges below).
"""

from __future__ import annotations

Point3 = tuple[float, float, float]
Point2 = tuple[float, float]


# ---------------------------------------------------------------------------
# Render-space transform
# ---------------------------------------------------------------------------

def render_point(x: float, y: float, z: float) -> Point3:
    """Map a logical-space point to render space (see module docstring)."""
    return (x - 0.5 * z + 1.5, y - 0.5 * z + 1.5, z + 1.0)


def _norm(v: float) -> float:
    """[-1, 1] -> [0, 1], direct (low->0, high->1)."""
    return (v + 1) / 2


def _inv_norm(v: float) -> float:
    """[-1, 1] -> [0, 1], reversed (low->1, high->0)."""
    return (1 - v) / 2


# Shared (u, w) corner order for a unit square in the two free axes of a
# plane, chosen so it traces a simple (non-self-intersecting) quad. Used
# directly for x-planes and y-planes; z-planes use their own listed order
# below since front/back faces are conventionally wound the other way.
_CORNER_ORDER = [(-1, 1), (1, 1), (1, -1), (-1, -1)]
_Z_CORNER_ORDER = [(-1, -1), (1, -1), (1, 1), (-1, 1)]


# ---------------------------------------------------------------------------
# DSL validation
# ---------------------------------------------------------------------------

_AXES = ("x", "y", "z")


def validate_spec(spec: dict) -> None:
    """Raise ValueError if spec does not conform to schema.json."""
    if not isinstance(spec, dict):
        raise ValueError(f"spec must be an object/dict, got {type(spec).__name__}")
    for axis, values in spec.items():
        if axis not in _AXES:
            raise ValueError(f"unknown axis key {axis!r}; must be one of {_AXES}")
        if not isinstance(values, list):
            raise ValueError(f"spec[{axis!r}] must be a list, got {type(values).__name__}")
        for v in values:
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise ValueError(f"spec[{axis!r}] contains non-numeric value {v!r}")
            if not (-1 <= v <= 1):
                raise ValueError(f"spec[{axis!r}] value {v!r} is outside [-1, 1]")


# ---------------------------------------------------------------------------
# DSL -> planes
# ---------------------------------------------------------------------------

class Plane:
    """One solid quad: 4 verts (render space) + 4 UVs, same winding order."""

    __slots__ = ("axis", "value", "verts", "uvs")

    def __init__(self, axis: str, value: float, verts: list[Point3], uvs: list[Point2]):
        self.axis = axis
        self.value = value
        self.verts = verts
        self.uvs = uvs


def planes_for_spec(spec: dict) -> list[Plane]:
    """
    Translate a validated DSL spec into a list of Planes.

    UV convention per axis (derived so a photo fill reads right-side-up,
    i.e. "sky up", on every face type):
        z-plane (front/back) : U = norm(x),      V = norm(y)       -- flat, undistorted
        y-plane (top/bottom) : U = norm(x),      V = inv_norm(z)   -- front edge = bottom of image
        x-plane (left/right) : U = inv_norm(z),  V = norm(y)       -- front edge = near/left of image
    """
    validate_spec(spec)
    planes: list[Plane] = []

    for val in spec.get("y", []):
        pts = _CORNER_ORDER  # (x, z)
        planes.append(Plane(
            "y", val,
            verts=[render_point(x, val, z) for (x, z) in pts],
            uvs=[(_norm(x), _inv_norm(z)) for (x, z) in pts],
        ))

    for val in spec.get("x", []):
        pts = _CORNER_ORDER  # (y, z)
        planes.append(Plane(
            "x", val,
            verts=[render_point(val, y, z) for (y, z) in pts],
            uvs=[(_inv_norm(z), _norm(y)) for (y, z) in pts],
        ))

    for val in spec.get("z", []):
        pts = _Z_CORNER_ORDER  # (x, y)
        planes.append(Plane(
            "z", val,
            verts=[render_point(x, y, val) for (x, y) in pts],
            uvs=[(_norm(x), _norm(y)) for (x, y) in pts],
        ))

    return planes


# ---------------------------------------------------------------------------
# The fixed outer wireframe (independent of any spec)
# ---------------------------------------------------------------------------

# The 8 logical cube corners, indexed 0-7. 0-3 are the front face
# (z=+1), 4-7 the back face (z=-1) — matching the order used throughout
# this project's development.
CUBE_VERTS_LOGICAL: dict[int, Point3] = {
    0: (-1, -1, 1), 1: (1, -1, 1), 2: (1, 1, 1), 3: (-1, 1, 1),
    4: (-1, -1, -1), 5: (1, -1, -1), 6: (1, 1, -1), 7: (-1, 1, -1),
}

CUBE_EDGES: list[tuple[int, int]] = [
    (0, 1), (1, 2), (2, 3), (3, 0),   # front face
    (4, 5), (5, 6), (6, 7), (7, 4),   # back face
    (0, 4), (1, 5), (2, 6), (3, 7),   # depth edges
]


class Edge:
    """One wireframe edge, as two render-space endpoints with their true depth."""

    __slots__ = ("a", "b")

    def __init__(self, a: Point3, b: Point3):
        self.a = a
        self.b = b


def wireframe_edges() -> list[Edge]:
    """
    The cube's 12 fixed edges in render space, each carrying the *true*
    render-space depth of its endpoints (front-face vertices land at
    Z=2, back-face at Z=0; depth edges interpolate between). This is
    what lets a renderer's normal depth buffer occlude the wireframe
    correctly against whichever planes happen to be solid — no
    per-shape special-casing needed, and no artificial "always nearest
    camera" offset.
    """
    verts = {i: render_point(*p) for i, p in CUBE_VERTS_LOGICAL.items()}
    return [Edge(verts[a], verts[b]) for (a, b) in CUBE_EDGES]
