import sys, bpy, bmesh, importlib
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import jm_api
jm = jm_api.load(sys.argv[-1])
jm.register()
bpy.ops.mesh.primitive_cylinder_add(radius=10, depth=110)
ob = bpy.context.active_object
js = ob.joint_maker
res = []
for jt, kw in [("HINGE", dict(pin_style='CONE')), ("HINGE", dict(pin_style='PIN')), ("BALL", dict(snap_relief=True, socket_wall=1.5, ball_control='LIP')),
               ("DOUBLE", dict(link_end='PIVOT', pivot_twist=90)), ("DOUBLE", dict(link_end='BALL')), ("DOUBLE", dict(link_end='CLIP', gear_mesh=True))]:
    js.joint_type = jt
    for k, v in kw.items(): setattr(js, k, v)
    if not js.active:
        with bpy.context.temp_override(active_object=ob, object=ob):
            bpy.ops.joint_maker.add()
    jm.rebuild(ob)
    dg = bpy.context.evaluated_depsgraph_get(); ev = ob.evaluated_get(dg); me = ev.to_mesh()
    bm = bmesh.new(); bm.from_mesh(me); ev.to_mesh_clear()
    res.append((jt, list(kw.values())[0], len(jm._linked_shells(bm)), sum(1 for e in bm.edges if not e.is_manifold), js.warning))
    bm.free()
for r in res: print("SMOKE", r)
jm.unregister()
print("SMOKE unregistered OK")
