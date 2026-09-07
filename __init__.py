"""
Cabinet Cube DSL.

    cube_dsl.geometry         - pure Python (no bpy). Coordinate convention,
                                 shear transform, DSL -> planes, wireframe edges.
    cube_dsl.blender_adapter  - bpy-dependent. Turns geometry.py's output into
                                 bmesh/materials/camera/scene.

Deliberately not imported eagerly here: geometry.py works with a plain
`python3` interpreter (no Blender needed) for testing or inspecting the
DSL/math on their own; blender_adapter.py requires bpy and is only
importable from inside Blender's Python. Import whichever you need
directly, e.g.:

    import cube_dsl.geometry as geo
    import cube_dsl.blender_adapter as ba   # only inside Blender
"""
