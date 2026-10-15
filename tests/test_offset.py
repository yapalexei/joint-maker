import sys, bpy, bmesh, importlib, math
from mathutils import Vector, Matrix
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import jm_api
jm = jm_api.load(sys.argv[-1]); jm.register()
# irregular part: a cylinder along local X plus a separate block off to +Y near one end,
# so the bounding box centre is NOT on the cylinder's axis
me = bpy.data.meshes.new("irr"); bm = bmesh.new()
bmesh.ops.create_cone(bm, cap_ends=True, segments=48, radius1=10, radius2=10, depth=100,
                      matrix=Matrix.Rotation(math.radians(90), 4, 'Y'))
blk = bmesh.ops.create_cube(bm, size=1)["verts"]
bmesh.ops.scale(bm, vec=(8, 6, 6), verts=blk); bmesh.ops.translate(bm, vec=(-44, 27, 0), verts=blk)
bm.to_mesh(me); bm.free()
ob = bpy.data.objects.new("irr", me); bpy.context.scene.collection.objects.link(ob)
ob.rotation_euler = (0, 0, math.radians(30)); ob.scale = (1.5, 1.5, 1.5); ob.location = (5, -3, 2)
bpy.context.view_layer.objects.active = ob; ob.select_set(True); bpy.context.view_layer.update()
js = ob.joint_maker; js.axis = 'X'
with bpy.context.temp_override(active_object=ob, object=ob):
    bpy.ops.joint_maker.add()
print("OT axes across:", [l for l, d in jm.offset_axes(ob, js)], "| mm/unit", js.mm_per_unit)
vs = [v.co for v in me.vertices]; ymin = min(v.y for v in vs); ymax = max(v.y for v in vs)
expect_y = (0 - (ymin + ymax) / 2) * js.mm_per_unit * 1.5
F0 = jm.cylinder_frame(ob, js)[0]
print("OT before: joint centre local", tuple(round(c, 3) for c in F0.translation))
with bpy.context.temp_override(active_object=ob, object=ob):
    print("OT center op:", bpy.ops.joint_maker.center())
print(f"OT offsets after centring: Y {js.offset_a:.3f} mm (expected {expect_y:.3f}), Z {js.offset_b:.3f} mm (expected 0)")
F1 = jm.cylinder_frame(ob, js)[0]
print("OT after: joint centre local", tuple(round(c, 3) for c in F1.translation), "(cylinder axis is y=0, z=0)")
# parts: cylinder splits in 2, plus the separate block
jm.rebuild(ob)
dg = bpy.context.evaluated_depsgraph_get(); ev = ob.evaluated_get(dg); m2 = ev.to_mesh()
b2 = bmesh.new(); b2.from_mesh(m2); ev.to_mesh_clear()
print("OT shells", len(jm._linked_shells(b2)), "(expect 3) nonmanifold", sum(1 for e in b2.edges if not e.is_manifold)); b2.free()
# manual offsets / nudges / gizmo handlers
js.offset_a = 0; js.offset_b = 0; js.nudge_mm = 2.0
with bpy.context.temp_override(active_object=ob, object=ob):
    bpy.ops.joint_maker.nudge(off_a=1); bpy.ops.joint_maker.nudge(off_b=-1)
print("OT nudges -> Y", js.offset_a, "Z", js.offset_b)
F2 = jm.cylinder_frame(ob, js)[0]
d_world = ob.matrix_world.to_3x3() @ (F2.translation - F0.translation)
print("OT world shift of joint (mm):", tuple(round(c * js.mm_per_unit, 3) for c in d_world), "length", round(d_world.length * js.mm_per_unit, 3), "(expect sqrt(8)=2.828)")
ga, sa = jm._giz_offset_handlers("offset_a")
print("OT gizmo get Y (world units):", round(ga(), 4), "= mm/mm_per_unit", round(js.offset_a / js.mm_per_unit, 4))
sa(1.25); print("OT gizmo set 1.25 world ->", round(js.offset_a, 4), "mm")
with bpy.context.temp_override(active_object=ob, object=ob):
    bpy.ops.joint_maker.reset_offset()
print("OT reset ->", js.offset_a, js.offset_b)
for jt, kw in [("BALL", {}), ("DOUBLE", dict(link_end='CLIP', gear_mesh=True))]:
    js.joint_type = jt
    for k, v in kw.items(): setattr(js, k, v)
    with bpy.context.temp_override(active_object=ob, object=ob):
        bpy.ops.joint_maker.center()
    js.joint_scale = 0.7; js.array_count = 1
    jm.rebuild(ob)
    dg = bpy.context.evaluated_depsgraph_get(); ev = ob.evaluated_get(dg); m2 = ev.to_mesh()
    b2 = bmesh.new(); b2.from_mesh(m2); ev.to_mesh_clear()
    print(f"OT {jt} centred + 70% size: shells {len(jm._linked_shells(b2))} nonmanifold {sum(1 for e in b2.edges if not e.is_manifold)}")
    b2.free()
jm.unregister(); print("OT unregistered OK")
