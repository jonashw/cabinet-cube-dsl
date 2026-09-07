# Cabinet Cube DSL

A terse notation for describing which faces (or internal cross-sections) of
a cube are solid, rendered as a cabinet-oblique wireframe cube in Blender.
Built for the "cube rule of food identification" exploration — Salad,
Toast, Sandwich, Sushi, Taco, Quiche, Calzone, Cake, and friends — but
general enough for any shape describable as stacked/nested planes on a
cube.

This doc is written to be handed to a fresh session (human or coding
agent) with no other context. If you're picking this up cold, follow
**Setup** below in order — each step names the actual thing it depends on,
not just "make sure Blender is connected."

## Setup

You need two things before any of this can render: an MCP-connected
Blender, and this package's files on local disk. Neither is contained in
the gist/files alone — a gist is text, not a running process.

**1. Get an MCP-connected Blender running.** See
[`blender-mcp-setup.md`](./blender-mcp-setup.md) — it's a separate
file because it's about Blender+MCP generally and has nothing to do with
the DSL specifically. Confirm the connection actually works (e.g.
successfully call whatever "list objects in the scene" tool the server
exposes) before going further — if that fails, the fix is there, not here.

**2. Get this package onto local disk** so Blender's Python can import it
(pointing an agent at a URL does not put files on disk by itself):

```
git clone https://github.com/jonashw/cabinet-cube-dsl.git cube_dsl
```

## Coordinate convention

Logical cube space is `(x, y, z)`, each in `[-1, 1]`:

| axis | `-1`   | `+1`                     |
|------|--------|--------------------------|
| `x`  | left   | right                    |
| `y`  | bottom | top                      |
| `z`  | back   | front (nearest viewer)   |

## The DSL

```
{ "x": [v, ...], "y": [v, ...], "z": [v, ...] }
```

Every number `v` in a list inserts **one solid plane** perpendicular to
that axis, at position `v`, spanning the other two axes' full `[-1, 1]`
range. `v = ±1` happens to land exactly on the cube's own boundary (so it
reads as a normal face); an interior value (e.g. `0`) is the same
primitive, just floating inside the wireframe. An axis absent from the
object means no planes on that axis — fully open in that direction.

The formal grammar is [`schema.json`](./schema.json) — a standard JSON
Schema, so any spec (from a file, pasted inline, or a Python dict literal)
can be validated the same way regardless of where it lives.

### The 12 worked examples

| Name | Spec |
|---|---|
| Salad | `{}` |
| Toast | `{"y": [-1]}` |
| Sandwich | `{"y": [-1, 1]}` |
| Sushi | `{"y": [-1, 1], "x": [-1, 1]}` |
| Taco | `{"y": [-1], "x": [-1, 1]}` |
| Quiche | `{"y": [-1], "x": [-1, 1], "z": [-1, 1]}` |
| Calzone | `{"x": [-1, 1], "y": [-1, 1], "z": [-1, 1]}` |
| Cake | `{"y": [-1, 0, 1]}` |
| Gator | `{"z": [-1], "y": [-1, 1]}` |
| Lid | `{"y": [1]}` |
| Hat | `{"x": [-1, 1], "y": [1], "z": [-1]}` |
| Record Collection | `{"x": [-1, -0.5, 0, 0.5, 1]}` |

## How it renders

`geometry.py` maps every logical point into render space with one fixed
linear shear:

```
X = x - 0.5*z + 1.5
Y = y - 0.5*z + 1.5
Z = z + 1
```

This is what produces the cabinet-projection look — a plain orthographic
camera then just looks straight down `-Z` at the already-sheared geometry.
The shear comes from a specific choice made early in this project's
development: front-face edge = 2 units, depth offset = 1 unit (inner
square : margin = 1:1, derived from a "3×3 grid" construction).

The cube's 12 edges are drawn in full, always — this system does not do
hidden-line removal on the wireframe itself. Instead, every edge carries
its *true* render-space depth (front-face vertices at `Z=2`, back-face at
`Z=0`, depth-edges interpolating between), so Blender's ordinary depth
buffer occludes the wireframe correctly against whichever planes happen to
be solid. No per-shape special-casing.

## Quickstart

Once Setup above is done (Blender running, MCP connected, package cloned
locally), run this inside your MCP client's "execute Python in Blender"
tool. This first example uses a flat color fill and needs no external
image at all:

```python
import sys
sys.path.insert(0, "/path/to/parent/of/cube_dsl")   # wherever step 5 cloned it
import cube_dsl.geometry as geo
import cube_dsl.blender_adapter as ba
import importlib; importlib.reload(geo); importlib.reload(ba)

ba.setup_scene()                          # white world, Cycles + Standard view transform, framed camera — once
wireframe = ba.build_wireframe_object()   # the fixed 12-edge cube, reused for every shape

blue = ba.make_flat_material("Blue", (0.1, 0.3, 0.9, 1.0))
shape = ba.build_shape_object("ShapeMesh", {"y": [-1, 1]}, blue)  # Sandwich
ba.render_shape(shape, "/tmp/sandwich.png")
```

To use a photo fill instead, once you have an image path of your own:

```python
photo = ba.make_photo_material("MyPhoto", "/path/to/your/image.png")
shape = ba.build_shape_object("ShapeMesh", {"y": [-1, 0, 1]}, photo)  # Cake
ba.render_shape(shape, "/tmp/cake.png")
```

Swap shapes by calling `build_shape_object` again with the same name — it
replaces the mesh data in place rather than accumulating objects.

`render_shape` temporarily excludes any other top-level collection from
the view layer (e.g. a user's own default Cube/Camera/Light) so it doesn't
leak into the frame, and restores it afterward — it does not delete or
otherwise touch pre-existing scene content.

## Style parameters

- `build_wireframe_object(line_width=0.04, joint_segments=32, stroke_eps=0.003, joint_eps=0.006)`
  — stroke thickness, round-join smoothness, and the two epsilon lifts
  that keep an edge from z-fighting against a coincident solid face.
- `setup_scene(resolution=800, samples=32)` — output size and Cycles
  sample count.
- `setup_camera(frame_margin=1.25)` — extra margin around the cube in
  the framed camera view.

## Deliberately out of scope (for now)

Every plane in a spec currently shares one material — there is no
per-plane color or texture. Extending the schema for that later (e.g.
`{"at": v, "color": "..."}` objects instead of bare numbers) is a natural
next step, but was explicitly deferred rather than designed speculatively.

This package is used interactively via an MCP-connected Blender session,
not headless — there is no `blender --background` CLI entry point here by
design.
