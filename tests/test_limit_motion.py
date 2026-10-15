import sys, bpy, bmesh, importlib, math
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import jm_api
jm = jm_api.load(sys.argv[-1]); jm.register()
bpy.ops.mesh.primitive_cylinder_add(radius=10, depth=100, vertices=64); ob = bpy.context.active_object
with bpy.context.temp_override(active_object=ob, object=ob):
    bpy.ops.joint_maker.add()
js = ob.joint_maker; js.live = False; js.mm_per_unit = 1.0
def max_bend(tag):
    res = jm.rebuild(ob)
    dg = bpy.context.evaluated_depsgraph_get(); ev = ob.evaluated_get(dg); me = ev.to_mesh()
    bm = bmesh.new(); bm.from_mesh(me); ev.to_mesh_clear()
    sh = []
    for g in jm._linked_shells(bm):
        vs = list({v for f in g for v in f.verts}); idx = {v: i for i, v in enumerate(vs)}
        sh.append(([v.co.copy() for v in vs], [[idx[v] for v in f.verts] for f in g]))
    bm.free()
    sh.sort(key=lambda s_: sum(v.z for v in s_[0]) / len(s_[0]))
    art = res["arts"][0]
    lo_t = BVHTree.FromPolygons(sh[0][0], sh[0][1])
    best = {}
    for sgn in (1, -1):
        ok = 0
        for a in range(0, 91, 5):
            M = Matrix.Translation(art["pt"]) @ Matrix.Rotation(math.radians(sgn * a), 4, art["axis"] if art["kind"] == 'hinge' else Vector((1, 0, 0))) @ Matrix.Translation(-art["pt"])
            if lo_t.overlap(BVHTree.FromPolygons([M @ v for v in sh[1][0]], sh[1][1])): break
            ok = a
        best[sgn] = ok
    print(f"LM {tag}: parts {len(sh)} | bends freely to +{best[1]} / -{best[-1]} deg")
for jt in ('HINGE', 'BALL'):
    js.joint_type = jt
    for sc in (1.0, 0.6):
        js.joint_scale = sc
        js.limit_reach_on = False; max_bend(f"{jt} {int(sc*100)}% limit off")
        js.limit_reach_on = True
        for reach, bev in ((1.0, 0.0), (1.0, 2.0), (1.0, 4.0)):
            js.limit_reach, js.limit_bevel = reach, bev; max_bend(f"{jt} {int(sc*100)}% limit {reach} bevel {bev}")
jm.unregister()
