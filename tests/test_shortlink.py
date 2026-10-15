import sys, bpy, bmesh, importlib, math, re
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import jm_api
jm = jm_api.load(sys.argv[-1]); jm.register()
bpy.ops.mesh.primitive_cylinder_add(radius=10, depth=110, vertices=64); ob = bpy.context.active_object
with bpy.context.temp_override(active_object=ob, object=ob):
    bpy.ops.joint_maker.add()
js = ob.joint_maker; js.live = False; js.mm_per_unit = 1.0; js.joint_type = 'DOUBLE'
def run(tag):
    res = jm.rebuild(ob)
    dg = bpy.context.evaluated_depsgraph_get(); ev = ob.evaluated_get(dg); me = ev.to_mesh()
    bm = bmesh.new(); bm.from_mesh(me); ev.to_mesh_clear()
    nm = sum(1 for e in bm.edges if not e.is_manifold)
    sh = []
    for g in jm._linked_shells(bm):
        vs = list({v for f in g for v in f.verts}); idx = {v: i for i, v in enumerate(vs)}
        sh.append(([v.co.copy() for v in vs], [[idx[v] for v in f.verts] for f in g]))
    bm.free()
    sh.sort(key=lambda s_: sum(v.z for v in s_[0]) / len(s_[0]))
    arts = sorted(res["arts"], key=lambda a: a["pt"].z)
    lim = arts[0]["limit"]
    spacing = (arts[1]["pt"] - arts[0]["pt"]).length
    ok = None
    if len(sh) == 3:
        D, K, U = sh
        TK = BVHTree.FromPolygons(K[0], K[1])
        def tr(M, s_): return BVHTree.FromPolygons([M @ v for v in s_[0]], s_[1])
        def R(art, a):
            ax = art["axis"] if art["kind"] == 'hinge' else Vector((1, 0, 0))
            return Matrix.Translation(art["pt"]) @ Matrix.Rotation(math.radians(a), 4, ax) @ Matrix.Translation(-art["pt"])
        def free(a):   # both ends bent `a` deg (opposite sides relative to the link) and same side
            for sgn in ((1,) if js.link_end == 'CLIP' and js.gear_mesh else (1, -1)):   # gears only allow geared motion
                tu, tl = tr(R(arts[1], a), U), tr(R(arts[0], -sgn * a), D)
                if TK.overlap(tu) or TK.overlap(tl) or tu.overlap(tl): return False
            return True
        ok = (free(max(0, lim - 2)), free(min(90, lim + 12)))
    w = [x for x in js.warning.split("; ") if "link" in x or "bend" in x or "swing" in x]
    print(f"SL {tag}: parts {len(sh)} nm {nm} spacing {spacing:.2f} mm, reported range +-{lim:.0f} | free at range-2: {ok[0] if ok else '-'}, at range+12: {ok[1] if ok else '-'} | {w}")
for end, kw in (('PIVOT', {'pin_style': 'CONE'}), ('PIVOT', {'pin_style': 'PIN'}), ('CLIP', {'gear_mesh': False}), ('CLIP', {'gear_mesh': True}), ('BALL', {})):
    js.link_end = end
    for k, v in kw.items(): setattr(js, k, v)
    for ll in (3.0, 2.2, 1.6, 1.2, 0.6, 0.0):
        js.link_length = ll
        run(f"{end:5s} {str(list(kw.values()))[:7]:7s} link {ll}")
jm.unregister()
