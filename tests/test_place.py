import sys, bpy, importlib, math
from mathutils import Vector, Matrix
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import jm_api
jm = jm_api.load(sys.argv[-1]); jm.register()
print("PT gizmo group registered:", hasattr(bpy.types, "JOINTMAKER_GGT_place"))
# rotated, scaled cylinder to exercise world-space maths
bpy.ops.mesh.primitive_cylinder_add(radius=1, depth=10, location=(3, 2, 1), rotation=(0, math.radians(90), 0))
ob = bpy.context.active_object
ob.scale = (2, 2, 2)
bpy.context.view_layer.update()
js = ob.joint_maker
with bpy.context.temp_override(active_object=ob, object=ob):
    bpy.ops.joint_maker.add()
print("PT mm/unit", round(js.mm_per_unit, 3), "printed length mm", round(jm.mm_per_position(ob, js), 2))
print("PT position", js.position, "-> position_mm", round(js.position_mm, 3))
js.position_mm = 30.0
print("PT set position_mm=30 -> position", round(js.position, 4), "back:", round(js.position_mm, 3))
js.position_mm = 9999; print("PT clamp high ->", js.position); js.position_mm = -5; print("PT clamp low ->", js.position)
js.position = 0.5; js.nudge_mm = 2.5; js.nudge_deg = 15
with bpy.context.temp_override(active_object=ob, object=ob):
    bpy.ops.joint_maker.nudge(move=1); p1 = js.position_mm
    bpy.ops.joint_maker.nudge(move=-2); p2 = js.position_mm
    js.rotation = 170
    bpy.ops.joint_maker.nudge(turn=1); r1 = js.rotation
    bpy.ops.joint_maker.nudge(turn=-2); r2 = js.rotation
print("PT nudges: +1 step", round(p1, 3), "then -2 steps", round(p2, 3), "| rotation 170 +15 ->", round(r1, 2), "then -30 ->", round(r2, 2))
# gizmo handlers (use the active object)
bpy.context.view_layer.objects.active = ob
aw = jm.axis_world(ob, js)
print("PT axis world: base", tuple(round(c, 3) for c in aw[0]), "dir", tuple(round(c, 3) for c in aw[1]), "len", round(aw[2], 3), "centre", tuple(round(c, 3) for c in aw[3]), "radius", round(aw[4], 3))
js.position = 0.25
print("PT slide get at 0.25:", round(jm._giz_get_slide(), 4), "(expect", round(0.25 * aw[2], 4), ")")
jm._giz_set_slide(aw[2] * 0.75); print("PT slide set 75% ->", round(js.position, 4))
jm._giz_set_turn(math.radians(200)); print("PT turn set 200deg ->", round(js.rotation, 2), "get", round(math.degrees(jm._giz_get_turn()), 2))
# joint centre in world should sit at base + dir * position*len
aw = jm.axis_world(ob, js)
print("PT centre matches slide:", (aw[0] + aw[1] * aw[2] * js.position - aw[3]).length < 1e-5)
# geometry still valid after moves
import bmesh
jm.rebuild(ob)
dg = bpy.context.evaluated_depsgraph_get(); ev = ob.evaluated_get(dg); me = ev.to_mesh()
bm = bmesh.new(); bm.from_mesh(me); ev.to_mesh_clear()
print("PT parts", len(jm._linked_shells(bm)), "nonmanifold", sum(1 for e in bm.edges if not e.is_manifold))
jm.unregister(); print("PT unregistered OK")
