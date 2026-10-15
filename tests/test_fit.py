import sys, bpy, bmesh, importlib, math
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import jm_api
jm = jm_api.load(sys.argv[-1]); jm.register()

def make(name, segs):
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segs, radius1=10, radius2=10, depth=110)   # only end verts
    blk = bmesh.ops.create_cube(bm, size=1)["verts"]                       # neighbour, 1.5 mm away
    bmesh.ops.scale(bm, vec=(8.5, 30, 16), verts=blk); bmesh.ops.translate(bm, vec=(15.75, 0, 0), verts=blk)
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob; ob.select_set(True)
    with bpy.context.temp_override(active_object=ob, object=ob):
        bpy.ops.joint_maker.add()
        bpy.ops.joint_maker.center()          # bbox is skewed by the block
    return ob

def evaluate(ob):
    jm.rebuild(ob)
    dg = bpy.context.evaluated_depsgraph_get(); ev = ob.evaluated_get(dg); me = ev.to_mesh()
    bm = bmesh.new(); bm.from_mesh(me); ev.to_mesh_clear()
    nm = sum(1 for e in bm.edges if not e.is_manifold)
    shells = []
    for grp in jm._linked_shells(bm):
        vs = list({v for f in grp for v in f.verts}); idx = {v: i for i, v in enumerate(vs)}
        vol = 0.0
        for f in grp:
            q = [v.co for v in f.verts]
            for i in range(1, len(q) - 1): vol += q[0].dot(q[i].cross(q[i + 1])) / 6
        cx = sum(v.co.x for v in vs) / len(vs)
        shells.append((cx, vol, [v.co.copy() for v in vs], [[idx[v] for v in f.verts] for f in grp]))
    bm.free()
    blk = [s for s in shells if s[0] > 11]
    cyl = sorted([s for s in shells if s[0] <= 11], key=lambda s: sum(v.z for v in s[2]) / len(s[2]))
    return nm, cyl, blk

BLOCK_VOL = 8.5 * 30 * 16
def report(tag, ob):
    nm, cyl, blk = evaluate(ob)
    bv = round(sum(b[1] for b in blk), 2)
    js = ob.joint_maker
    print(f"FT {tag}: cylinder parts {len(cyl)}, block pieces {len(blk)} vol {bv} (intact {BLOCK_VOL}), nm {nm} | warn: {js.warning}")
    return cyl

def motion(ob, cyl, frac=0.95):
    js = ob.joint_maker
    res = jm.rebuild(ob)
    lo, hi = jm._ends(ob, js); a = (hi - lo).normalized()
    arts = sorted(res["arts"], key=lambda x: x["pt"].dot(a))
    hits = []
    for d in (1, -1):
        G, poses = Matrix(), [Matrix()]
        side = arts[0]["axis"]
        for art in arts:
            axis = art["axis"] if art["kind"] == 'hinge' else side
            c = G @ art["pt"]
            G = Matrix.Translation(c) @ Matrix.Rotation(math.radians(d * art["limit"] * frac), 4, (G.to_3x3() @ axis).normalized()) @ Matrix.Translation(-c) @ G
            poses.append(G)
        trees = [BVHTree.FromPolygons([poses[min(i, len(poses) - 1)] @ v for v in s[2]], s[3]) for i, s in enumerate(cyl)]
        hits += [(i, j) for i in range(len(trees)) for j in range(i + 1, len(trees)) if trees[i].overlap(trees[j])]
    return hits or "none"

for segs in (32, 96):
    ob = make(f"t{segs}", segs); js = ob.joint_maker; js.live = False
    print(f"FT ===== {segs}-sided cylinder (verts only at its ends) =====")
    js.joint_type = 'HINGE'; js.pin_style = 'CONE'
    js.fit_cutter = False; report("hinge, no fit", ob)
    js.fit_cutter = True; js.fit_margin = 1.0; cyl = report("hinge, fit 1mm", ob); print("FT    bend 95%:", motion(ob, cyl))
    js.joint_type = 'BALL'; js.joint_scale = 0.6
    for mode, keep in (('AUTO', True), ('CUSTOM', True), ('NONE', True), ('CUSTOM', False), ('NONE', False)):
        js.waist_taper = mode; js.taper_len = 1.5; js.keep_range = keep
        cyl = report(f"ball 60% taper {mode} keep={keep}, fit", ob)
        print("FT    bend 95%:", motion(ob, cyl))
    js.joint_type = 'DOUBLE'; js.link_end = 'CLIP'; js.gear_mesh = True; js.joint_scale = 0.7; js.waist_taper = 'AUTO'; js.keep_range = True
    cyl = report("geared E-clip 70%, fit", ob)
    js.fit_cutter = False; report("geared E-clip 70%, no fit", ob)
jm.unregister(); print("FT done")
