import sys, bpy, bmesh, importlib, math, time
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import jm_api
jm = jm_api.load(sys.argv[-1]); jm.register()
RA, ARC = 60.0, math.radians(100)            # tail centreline: arc of radius 60 in the XZ plane
def centre(t):  return Vector((RA - RA * math.cos(t * ARC), 0, RA * math.sin(t * ARC)))
def tangent(t): return Vector((math.sin(t * ARC), 0, math.cos(t * ARC)))
def radius(t):  return 10 - 6 * t
# tapering curved tube
bm = bmesh.new(); rings = []
for k in range(61):
    t = k / 60; c, T = centre(t), tangent(t); X = Vector((0, 1, 0)); Y = T.cross(X)
    rings.append([bm.verts.new(c + (X * math.cos(a) + Y * math.sin(a)) * radius(t)) for a in [2 * math.pi * j / 40 for j in range(40)]])
for k in range(60):
    for j in range(40):
        a, b = rings[k][j], rings[k][(j + 1) % 40]; c, d = rings[k + 1][(j + 1) % 40], rings[k + 1][j]
        bm.faces.new((a, b, c, d))
bm.faces.new(rings[0][::-1]); bm.faces.new(rings[-1])
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
me = bpy.data.meshes.new("tail"); bm.to_mesh(me); bm.free()
tail = bpy.data.objects.new("tail", me); bpy.context.scene.collection.objects.link(tail)
tail.rotation_euler = (0, 0, math.radians(25)); tail.location = (5, 3, -2)        # transformed object
bpy.context.view_layer.update()
# placement curve: same arc but 2 mm off-centre (snapping should fix it), in world space
cd = bpy.data.curves.new("path", "CURVE"); cd.dimensions = '3D'; sp = cd.splines.new('POLY')
pts = [tail.matrix_world @ (centre(k / 80) + Vector((0, 2.0, 0))) for k in range(81)]
sp.points.add(len(pts) - 1)
for pnt, v in zip(sp.points, pts): pnt.co = (v.x, v.y, v.z, 1)
crv = bpy.data.objects.new("path", cd); bpy.context.scene.collection.objects.link(crv)
bpy.context.view_layer.objects.active = tail; tail.select_set(True)
js = tail.joint_maker
with bpy.context.temp_override(active_object=tail, object=tail):
    bpy.ops.joint_maker.add()
js.live = False; js.mm_per_unit = 1.0

def evaluate():
    t0 = time.time(); res = jm.rebuild(tail)
    dg = bpy.context.evaluated_depsgraph_get(); ev = tail.evaluated_get(dg); m = ev.to_mesh()
    b = bmesh.new(); b.from_mesh(m); ev.to_mesh_clear()
    nm = sum(1 for e in b.edges if not e.is_manifold)
    shells = []
    for g in jm._linked_shells(b):
        vs = list({v for f in g for v in f.verts}); idx = {v: i for i, v in enumerate(vs)}
        shells.append(([v.co.copy() for v in vs], [[idx[v] for v in f.verts] for f in g]))
    b.free()
    return res, shells, nm, time.time() - t0

def arc_param(p):   # nearest centreline parameter of a local point
    return min(range(201), key=lambda k: (centre(k / 200) - p).length) / 200

def report(tag, check_motion=False):
    res, shells, nm, dt = evaluate()
    frames = [tail.matrix_world.inverted() @ F for F in jm._LAST_FRAMES[tail.as_pointer()]]
    rows = []
    for F in frames:
        c = F.translation; z = (F.to_3x3() @ Vector((0, 0, 1))).normalized(); t = arc_param(c)
        rows.append(f"t={t:.2f} off-centre {(c - centre(t)).length:.2f}mm axis-vs-curve {math.degrees(z.angle(tangent(t))) if z.angle(tangent(t)) < 1.6 else 180 - math.degrees(z.angle(tangent(t))):.1f}deg")
    print(f"CV {tag}: parts {len(shells)} (expect {len(frames) * (2 if js.joint_type != 'DOUBLE' else 2) - (len(frames) - 1) if js.joint_type != 'DOUBLE' else 2 * len(frames) + 1}) nm {nm} {dt:.2f}s")
    for r in rows: print("CV    ", r)
    print("CV     info:", js.info, "| warn:", js.warning)
    if check_motion:
        shells.sort(key=lambda s_: arc_param(sum(s_[0], Vector()) / len(s_[0])))
        arts = sorted(res["arts"], key=lambda a: arc_param(a["pt"]))
        worst = []
        for k, art in enumerate(arts):
            for ang in ((45, -45) if art['kind'] == 'hinge' else (25, -25)):
                M = Matrix.Translation(art["pt"]) @ Matrix.Rotation(math.radians(ang), 4, art["axis"]) @ Matrix.Translation(-art["pt"])
                moved = [BVHTree.FromPolygons([M @ v for v in s_[0]], s_[1]) for s_ in shells[k + 1:]]
                fixed = [BVHTree.FromPolygons(s_[0], s_[1]) for s_ in shells[:k + 1]]
                if any(a.overlap(b) for a in moved for b in fixed): worst.append((k, ang))
        print("CV     bend each joint (hinges +-45, balls +-25 inside their 30 deg swing):", worst or "no collisions")

js.joint_type = 'HINGE'; js.pin_style = 'CONE'; js.array_count = 3; js.array_mode = 'FIT'
js.place_curve = crv; js.curve_snap = False; report("3 hinges on curve, snap OFF")
js.curve_snap = True; report("3 hinges on curve, snap ON", check_motion=True)
js.curve_start, js.curve_end = 0.1, 0.7; report("3 hinges, curve section 10-70%"); js.curve_start, js.curve_end = 0.0, 1.0
js.array_mode = 'SPACING'; js.array_spacing = 25; js.position = 0.5; report("3 hinges, 25 mm spacing"); js.array_mode = 'FIT'
js.array_twist = 90; report("3 hinges, twist 90 per joint"); js.array_twist = 0
js.joint_type = 'BALL'; report("3 balls on curve", check_motion=True)
js.joint_type = 'SHAPE'; js.shape_preset = 'CONE'; report("3 cone-socket shapes on curve")
js.joint_type = 'HINGE'; js.fit_cutter = True; report("3 hinges + fit cutter"); js.fit_cutter = False
js.joint_scale = 0.7; report("3 hinges at 70% size"); js.joint_scale = 1.0
cd2 = bpy.data.curves.new("pose", "CURVE"); sp2 = cd2.splines.new('POLY'); sp2.points.add(1); sp2.points[1].co = (0, 0, 10, 1)
js.path = bpy.data.objects.new("pose", cd2); report("with a pose path set too"); js.path = None
# tilt on a plain cylinder
js.place_curve = None
bpy.ops.mesh.primitive_cylinder_add(radius=10, depth=100, location=(80, 0, 0)); cyl = bpy.context.active_object
with bpy.context.temp_override(active_object=cyl, object=cyl):
    bpy.ops.joint_maker.add()
cj = cyl.joint_maker; cj.live = False
for tx, ty in ((20, 0), (0, -30), (25, 15), (0, 45), (-40, 30)):
    cj.tilt_x, cj.tilt_y = tx, ty; jm.rebuild(cyl)
    dg = bpy.context.evaluated_depsgraph_get(); ev = cyl.evaluated_get(dg); m = ev.to_mesh()
    b = bmesh.new(); b.from_mesh(m); ev.to_mesh_clear()
    F = jm.cylinder_frame(cyl, cj)[0]; z = (F.to_3x3() @ Vector((0, 0, 1))).normalized()
    print(f"CV tilt x={tx} y={ty}: parts {len(jm._linked_shells(b))} nm {sum(1 for e in b.edges if not e.is_manifold)} joint axis tilted {math.degrees(z.angle(Vector((0,0,1)))):.1f} deg | warn: {cj.warning}")
    b.free()
jm.unregister()
