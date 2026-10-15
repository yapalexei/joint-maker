import sys, bpy, bmesh, math, importlib
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import jm_api
jm = jm_api.load(sys.argv[-1]); jm.register()
bpy.ops.mesh.primitive_cylinder_add(radius=10, depth=110, vertices=48)
ob = bpy.context.active_object; js = ob.joint_maker
with bpy.context.temp_override(active_object=ob, object=ob):
    bpy.ops.joint_maker.add()

def parts():
    res = jm.rebuild(ob)
    dg = bpy.context.evaluated_depsgraph_get(); ev = ob.evaluated_get(dg); me = ev.to_mesh()
    bm = bmesh.new(); bm.from_mesh(me); ev.to_mesh_clear()
    nm = sum(1 for e in bm.edges if not e.is_manifold)
    lo, hi = jm._ends(ob, js); a = (hi - lo).normalized()
    sh = []
    for grp in jm._linked_shells(bm):
        vs = list({v for f in grp for v in f.verts}); idx = {v: i for i, v in enumerate(vs)}
        sh.append(([v.co.copy() for v in vs], [[idx[v] for v in f.verts] for f in grp]))
    bm.free()
    sh.sort(key=lambda s_: sum(v.dot(a) for v in s_[0]) / len(s_[0]))
    arts = sorted(res["arts"], key=lambda x: x["pt"].dot(a))
    return sh, nm, arts, a

def tr(M, pt): return BVHTree.FromPolygons([M @ v for v in pt[0]], pt[1])
def Rot(ax, d, c): return Matrix.Translation(c) @ Matrix.Rotation(math.radians(d), 4, ax) @ Matrix.Translation(-c)

def bend(sh, arts, a, frac, direction):
    """bend each joint to frac of its limit; balls tilt about a fixed side axis; geared pairs
    move equal and opposite. Returns overlapping part pairs."""
    G, poses, prev = Matrix(), [Matrix()], None
    side = arts[0]["axis"] if arts else Vector((1, 0, 0))
    for k, art in enumerate(arts):
        ang = direction * art["limit"] * frac
        if k and art.get("pair") is not None and arts[k - 1].get("pair") == art.get("pair"):
            ang = prev                     # geared: same turn relative to the link
        axis = art["axis"] if art["kind"] == 'hinge' else side
        c = G @ art["pt"]
        G = Rot((G.to_3x3() @ axis).normalized(), ang, c) @ G
        poses.append(G); prev = ang
    trees = [tr(poses[min(i, len(poses) - 1)], s_) for i, s_ in enumerate(sh)]
    return [(i, j) for i in range(len(trees)) for j in range(i + 1, len(trees)) if trees[i].overlap(trees[j])]

js.live = False
configs = [("HINGE", dict(pin_style='CONE')), ("HINGE", dict(pin_style='PIN')), ("BALL", dict(snap_relief=True)),
           ("DOUBLE", dict(link_end='PIVOT', pin_style='CONE')), ("DOUBLE", dict(link_end='BALL')),
           ("DOUBLE", dict(link_end='CLIP', gear_mesh=False)), ("DOUBLE", dict(link_end='CLIP', gear_mesh=True))]
for jt, kw in configs:
    js.joint_type = jt
    for k, v in kw.items(): setattr(js, k, v)
    for sc in (1.0, 0.7, 0.5, 0.3):
        js.joint_scale = sc
        sh, nm, arts, a = parts()
        h = {f"{int(f*100)}%{'+' if d > 0 else '-'}": bend(sh, arts, a, f, d) for f in (0.5, 0.95) for d in (1, -1)}
        bad = {k: v for k, v in h.items() if v}
        tag = "/".join(str(v) for v in kw.values())
        print(f"RES {jt:6s} {tag:10s} size {sc:.1f}: parts {len(sh)}/{len(arts)+1} nm {nm} collisions {bad or 'none'} | "
              f"{js.info.split(' | ')[0]} | warn: {js.warning}")
jm.unregister()
