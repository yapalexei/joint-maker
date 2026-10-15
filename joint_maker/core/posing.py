"""Path (pose preview): laying the jointed chain along a curve as rigid parts."""

import bpy
import bmesh
import math
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from .frame import axis_ends
from .helpers import part_objects
from .placement import Polyline, curve_polyline
from ..geometry.mesh import linked_shells


def pose_chain(obj, js, arts, ctr_lo, ctr_hi):
    """
    Lay the jointed cylinder along js.path as a rigid chain. Every part keeps its shape;
    each pivot bends only the way it can (hinge: about its pin axis, ball: any direction),
    clamped to its range of motion. Returns (world matrices per part, clamped count).
    """
    pts = curve_polyline(js.path)
    if not pts:
        return None, 0
    curve = Polyline(pts)
    M0 = obj.matrix_world
    R0 = M0.to_3x3()
    a_hat = (ctr_hi - ctr_lo).normalized()
    A = (R0 @ a_hat).normalized()
    scale = (R0 @ a_hat).length
    arts = [dict(a) for a in sorted(arts, key=lambda a: a["pt"].dot(a_hat))]
    for a, b in zip(arts, arts[1:]):                  # geared pairs: first leads, second follows
        if a.get("pair") is not None and a.get("pair") == b.get("pair") and not a.get("sync"):
            a["lead"], b["sync"] = True, True
    stops = [ctr_lo] + [a["pt"] for a in arts] + [ctr_hi]            # local points along the chain
    s_at = [0.0]
    for a, b in zip(stops, stops[1:]):
        s_at.append(s_at[-1] + (b - a).dot(a_hat) * scale)

    # first part: bottom end on the curve start, axis along the start tangent
    T0 = curve.tangent(0.0)
    G = Matrix.Translation(curve.at(0.0)) @ A.rotation_difference(T0).to_matrix().to_4x4() \
        @ Matrix.Translation(-(M0 @ ctr_lo))
    # roll so the first hinge axis is square to the curve's plane (lets a planar curve be followed)
    N = curve.plane_normal()
    if arts and arts[0]["kind"] == 'hinge' and N is not None:
        h = (G.to_3x3() @ (R0 @ arts[0]["axis"])).normalized()
        hp = (h - T0 * h.dot(T0)).normalized()
        Np = (N - T0 * N.dot(T0))
        if Np.length > 1e-6 and hp.length > 1e-6:
            Np.normalize()
            ang = math.atan2(T0.dot(hp.cross(Np)), hp.dot(Np))
            P0 = curve.at(0.0)
            G = Matrix.Translation(P0) @ Matrix.Rotation(ang, 4, T0) @ Matrix.Translation(-P0) @ G
    if abs(js.path_roll) > 1e-9:
        P0 = curve.at(0.0)
        G = Matrix.Translation(P0) @ Matrix.Rotation(math.radians(js.path_roll), 4, T0) \
            @ Matrix.Translation(-P0) @ G

    poses, clamped, forced = [G], 0, None
    for k, art in enumerate(arts):
        J = G @ (M0 @ art["pt"])
        lead = art.get("lead") and k + 3 < len(stops)
        ahead = k + 3 if lead else k + 2               # geared pair: aim past both pivots
        nxt = G @ (M0 @ stops[ahead])
        u = (nxt - J).normalized()
        d = (curve.at(s_at[ahead]) - J).normalized()
        lim = math.radians(art["limit"])
        if art.get("sync") and forced is not None:     # geared: same bend as its partner
            h = (G.to_3x3() @ (R0 @ art["axis"])).normalized()
            G = Matrix.Translation(J) @ Matrix.Rotation(forced, 4, h) @ Matrix.Translation(-J) @ G
            poses.append(G)
            forced = None
            continue
        if art["kind"] == 'hinge':
            h = (G.to_3x3() @ (R0 @ art["axis"])).normalized()
            up, dp = u - h * u.dot(h), d - h * d.dot(h)
            ang = math.atan2(h.dot(up.cross(dp)), up.dot(dp)) if dp.length > 1e-9 else 0.0
            axis = h
        else:
            axis = u.cross(d)
            ang = u.angle(d) if axis.length > 1e-9 else 0.0
            axis = axis.normalized() if axis.length > 1e-9 else Vector((1, 0, 0))
        if lead:
            ang = ang / 2                              # split the bend across the pair
        if abs(ang) > lim:
            ang = math.copysign(lim, ang)
            clamped += 1
        if lead:
            forced = ang
        G = Matrix.Translation(J) @ Matrix.Rotation(ang, 4, axis) @ Matrix.Translation(-J) @ G
        poses.append(G)
    return poses, clamped


def update_pose(obj, js, arts):
    """posed preview of the chain along the path (helper object); returns the part poses"""
    posed = js.posed
    if js.path is None or not arts:
        if posed is not None:
            me = posed.data
            bpy.data.objects.remove(posed, do_unlink=True)
            if me.users == 0:
                bpy.data.meshes.remove(me)
            js.posed = None
        obj.display_type = 'TEXTURED'
        for ob in part_objects(obj):
            ob.hide_set(False)
        return None, []
    lo, hi = axis_ends(obj, js)
    poses, clamped = pose_chain(obj, js, arts, lo, hi)
    if poses is None:
        return None, ["path has no usable points"]
    warn = [f"path too tight at {clamped} joint(s): bend capped at the joint limit"] if clamped else []

    a_hat = (hi - lo).normalized()
    arts_sorted = sorted(arts, key=lambda a: a["pt"].dot(a_hat))
    cuts = [a["pt"].dot(a_hat) for a in arts_sorted]

    def part_index(z):                 # which chain part a point along the axis belongs to
        return sum(1 for c in cuts if z > c + 1e-9)

    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    src = bmesh.new(); src.from_mesh(ev.to_mesh()); ev.to_mesh_clear()
    out = bmesh.new()
    M0 = obj.matrix_world
    trees = []                         # posed parts, to catch the chain running into itself
    for grp in linked_shells(src):
        vs = list({v for f in grp for v in f.verts})
        zc = sum(v.co.dot(a_hat) for v in vs) / len(vs)
        G = poses[min(part_index(zc), len(poses) - 1)] @ M0
        vmap = {v: out.verts.new(G @ v.co) for v in vs}
        for f in grp:
            out.faces.new([vmap[v] for v in f.verts])
        idx = {v: i for i, v in enumerate(vs)}
        trees.append(BVHTree.FromPolygons([vmap[v].co.copy() for v in vs],
                                          [[idx[v] for v in f.verts] for f in grp]))
    src.free()
    hits = sum(1 for i in range(len(trees)) for j in range(i + 1, len(trees)) if trees[i].overlap(trees[j]))
    if hits:
        warn.append(f"chain runs into itself on this path ({hits} contact(s)): gentler curve, "
                    "fewer joints or Roll")
    for ob in part_objects(obj):      # separate pins ride with the part above their pivot
        c = sum((v.co for v in ob.data.vertices), Vector()) / max(1, len(ob.data.vertices))
        k = min(range(len(arts_sorted)), key=lambda i: (arts_sorted[i]["pt"] - c).length) + 1
        G = poses[min(k, len(poses) - 1)] @ M0
        vmap = [out.verts.new(G @ v.co) for v in ob.data.vertices]
        for poly in ob.data.polygons:
            out.faces.new([vmap[i] for i in poly.vertices])
        ob.hide_set(True)

    posed = js.posed                   # re-read: evaluating the depsgraph may have run handlers
    if posed is None or posed.name not in bpy.data.objects:
        home = obj.users_collection[0] if obj.users_collection else bpy.context.scene.collection
        posed = bpy.data.objects.new(obj.name + "_Posed", bpy.data.meshes.new(obj.name + "_Posed"))
        home.objects.link(posed)
        posed["joint_maker_helper"] = True
        js.posed = posed
        if obj.data.materials:
            posed.data.materials.append(obj.data.materials[0])
    out.to_mesh(posed.data); out.free()
    posed.data.update()
    obj.display_type = 'WIRE' if js.path_hide_straight else 'TEXTURED'
    return poses, warn
