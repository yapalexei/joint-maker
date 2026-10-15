"""Trimming the cutters: fit to shape, limit outer reach, and gear trimming."""

import bpy
import bmesh
import math
from mathutils import Matrix, Vector
from ..constants import GEAR_MOD_NAME
from .helpers import new_helper
from ..geometry.mesh import add_cone, add_revolve
from ..geometry.repair import set_solver
from ..geometry.sections import point_in_polygon, section_loops


def fit_hull(obj, js, p, axis_pt, a_hat, z_lo, z_hi):
    """
    Convex hull of the object right around one joint, grown by the fit margin.
    The mesh is sliced at several planes across the joint zone (so low-poly parts with no
    vertices there still work). At each slice only the outline that surrounds the joint's
    axis is kept, so other parts of the same mesh (an arm next to a body...) are left out.
    """
    m = js.fit_margin * p["mm"]
    u = a_hat.orthogonal().normalized()
    w = a_hat.cross(u)
    nplanes = 9
    pts, reach = [], 0.0
    for k in range(nplanes):
        z = z_lo + (z_hi - z_lo) * k / (nplanes - 1)
        bm = bmesh.new(); bm.from_mesh(obj.data)
        res = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                                     plane_co=a_hat * z, plane_no=a_hat)
        edges = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
        c = axis_pt + a_hat * (z - axis_pt.dot(a_hat))            # joint axis at this slice
        best, best_d = None, None
        for loop in section_loops(edges):
            poly = [((v.co - c).dot(u), (v.co - c).dot(w)) for v in loop]
            if len(poly) >= 3 and point_in_polygon((0.0, 0.0), poly):
                d = 0.0                                          # surrounds the axis
            else:
                d = min(math.hypot(x, y) for x, y in poly)
            if best_d is None or d < best_d:
                best, best_d = loop, d
        if best is not None:
            for v in best:
                pts.append(v.co.copy())
                rel = v.co - c
                reach = max(reach, (rel - a_hat * rel.dot(a_hat)).length)
        bm.free()
    if len(pts) < 4:
        return None
    # original vertices inside the zone and within that reach (catches bulges between slices)
    for v in obj.data.vertices:
        z = v.co.dot(a_hat)
        if z_lo <= z <= z_hi:
            rel = v.co - axis_pt
            if (rel - a_hat * rel.dot(a_hat)).length <= reach + 1e-9:
                pts.append(v.co.copy())
    h = bmesh.new()
    vs = [h.verts.new(c) for c in pts]
    res = bmesh.ops.convex_hull(h, input=vs)
    junk = list({g for g in res["geom_interior"] + res["geom_unused"] if isinstance(g, bmesh.types.BMVert)})
    if junk:
        bmesh.ops.delete(h, geom=junk, context='VERTS')
    loose = [v for v in h.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(h, geom=loose, context='VERTS')
    if len(h.faces) < 4:
        h.free()
        return None
    bmesh.ops.recalc_face_normals(h, faces=h.faces)
    h.normal_update()
    # grow by the margin: push each vertex out so every face moves ~m along its normal
    new = {}
    for v in h.verts:
        n = v.normal
        worst = min((n.dot(f.normal) for f in v.link_faces), default=1.0)
        new[v] = v.co + n * (m / max(worst, 0.35))
    for v, c in new.items():
        v.co = c
    return h


def update_fit(obj, js, p, piece_objs, owner, axes_i, warn):
    home = obj.users_collection[0] if obj.users_collection else bpy.context.scene.collection
    prefix = obj.name + "_JointFit"
    hulls = []
    if js.fit_cutter and piece_objs:
        # each joint's zone = the axial extent of its own cutter pieces, plus the margin
        m = js.fit_margin * p["mm"]
        for j, (axis_pt, jz, _ro, _rj) in enumerate(axes_i):
            zs = [v.co.dot(jz) for ob, oi in zip(piece_objs, owner) if oi == j for v in ob.data.vertices]
            hb = fit_hull(obj, js, p, axis_pt, jz, min(zs) - m, max(zs) + m) if zs else None
            name = f"{prefix}{j:02d}"
            ho = bpy.data.objects.get(name)
            if hb is None:
                warn.append("fit: no geometry found around a joint, cutter left untrimmed")
                hulls.append(None)
                continue
            if ho is None:
                ho = new_helper(obj, name, home)
            hb.to_mesh(ho.data); hb.free()
            ho.data.update()
            ho.hide_set(not js.show_cutter)
            hulls.append(ho)
    for ob, oi in zip(piece_objs, owner):
        md = ob.modifiers.get("Fit")
        ho = hulls[oi] if oi < len(hulls) else None
        if ho is None:
            if md:
                ob.modifiers.remove(md)
            continue
        md = md or ob.modifiers.new("Fit", 'BOOLEAN')
        md.operation, md.solver, md.object = 'INTERSECT', 'MANIFOLD', ho
    keep = {h.name for h in hulls if h is not None}
    for ob in [o for o in bpy.data.objects if o.name.startswith(prefix) and o.get("joint_maker_helper")]:
        if ob.name not in keep:
            me = ob.data
            bpy.data.objects.remove(ob, do_unlink=True)
            if me.users == 0:
                bpy.data.meshes.remove(me)
    return hulls


def update_limits(obj, js, p, piece_objs, owner, axes_i, info, waist_pieces=()):
    """
    Limit outer reach: trim every cutter piece of a joint to a tube around that joint whose
    outer radius is the part's cross-section there plus `limit_reach`, with the tube's outer
    end edges bevelled by `limit_bevel`. Stops the cutters (incl. the waist "pipe") from
    reaching neighbouring geometry, e.g. the body around a shoulder joint.
    """
    home = obj.users_collection[0] if obj.users_collection else bpy.context.scene.collection
    prefix = obj.name + "_JointLimit"
    tubes = []                                       # per joint: (plain tube, bevelled tube)

    def tube(name, prof, Fa):
        bm = bmesh.new()
        add_revolve(bm, prof, p["segs"], Fa)
        to = bpy.data.objects.get(name)
        if to is None:
            to = new_helper(obj, name, home)
        bm.to_mesh(to.data); bm.free()
        to.data.update()
        to.hide_set(not js.show_cutter)
        return to

    if js.limit_reach_on and piece_objs:
        mm = p["mm"]
        for j, (jc, jz, ro, rj) in enumerate(axes_i):
            mine = [(k, ob) for k, (ob, oi) in enumerate(zip(piece_objs, owner)) if oi == j]
            zs = [(v.co - jc).dot(jz) for _k, ob in mine for v in ob.data.vertices]
            if not zs:
                tubes.append((None, None))
                continue
            z0, z1 = min(zs) - 0.01 * mm, max(zs) + 0.01 * mm
            rod = ro + js.limit_reach * mm
            Fa = Matrix.Translation(jc) @ Vector((0, 0, 1)).rotation_difference(jz).to_matrix().to_4x4()
            # the joint's own pieces: radial limit only (they must reach the surface to split it)
            plain = tube(f"{prefix}{j:02d}", [(0.0, z0), (rod, z0), (rod, z1), (0.0, z1)], Fa)
            # the waist pipe: radial limit + chamfered outer ends, so it tapers off into the body
            bev = None
            wz = [(v.co - jc).dot(jz) for k, ob in mine if k in waist_pieces for v in ob.data.vertices]
            b = 0.0
            if wz:
                w0, w1 = min(wz) - 0.01 * mm, max(wz) + 0.01 * mm
                b = min(js.limit_bevel * mm, rod * 0.95, (w1 - w0) * 0.45)
                if b > 0:
                    bev = tube(f"{prefix}{j:02d}b", [(0.0, w0), (rod - b, w0), (rod, w0 + b), (rod, w1 - b),
                                                    (rod - b, w1), (0.0, w1)], Fa)
            tubes.append((plain, bev))
            if j == 0 and b > 0 and js.joint_scale < 0.999:
                info.append("outer bevel trims the waist ends: the bend range can drop, "
                            "check it with the Cross-section")
            if j == 0:
                wall = rod - rj if js.joint_scale < 0.999 else None
                info.append(f"cutter limited to \u00d8{2 * rod / mm:.1f} mm"
                            + (f", waist pipe wall {wall / mm:.2f} mm" if wall is not None else "")
                            + (f", outer bevel {b / mm:.2f} mm" if b > 0 else ""))
    for k, (ob, oi) in enumerate(zip(piece_objs, owner)):
        md = ob.modifiers.get("Limit")
        plain, bev = tubes[oi] if oi < len(tubes) else (None, None)
        to = (bev or plain) if k in waist_pieces else plain
        if to is None:
            if md:
                ob.modifiers.remove(md)
            continue
        md = md or ob.modifiers.new("Limit", 'BOOLEAN')
        md.operation, md.solver, md.object = 'INTERSECT', 'MANIFOLD', to
    tubes = [t for pair in tubes for t in pair]
    keep = {t.name for t in tubes if t is not None}
    for ob in [o for o in bpy.data.objects if o.name.startswith(prefix) and o.get("joint_maker_helper")]:
        if ob.name not in keep:
            me = ob.data
            bpy.data.objects.remove(ob, do_unlink=True)
            if me.users == 0:
                bpy.data.meshes.remove(me)


def update_gears(obj, js, gear_bm, waist=None, solver='MANIFOLD'):
    home = obj.users_collection[0] if obj.users_collection else bpy.context.scene.collection
    gears = bpy.data.objects.get(obj.name + "_JointGears")
    clip = bpy.data.objects.get(obj.name + "_JointClip")
    gm = obj.modifiers.get(GEAR_MOD_NAME)
    if not len(gear_bm.faces):
        gear_bm.free()
        if gm:
            obj.modifiers.remove(gm)
        for ob in (gears, clip):
            if ob is not None and ob.get("joint_maker_helper"):
                me = ob.data
                bpy.data.objects.remove(ob, do_unlink=True)
                if me.users == 0:
                    bpy.data.meshes.remove(me)
        return
    if clip is None:
        clip = new_helper(obj, obj.name + "_JointClip", home)
    old = clip.data
    if waist is None:
        clip.data = obj.data.copy()             # own copy: obj's mesh must stay single-user
    else:                                       # trim to the slimmer waist around the joint
        bm = bmesh.new()
        for r, Fa, z0, z1, segs in waist:                 # one short cylinder per joint
            add_cone(bm, r, r, (0, 0, z0 - 1.0), (0, 0, z1 + 1.0), segs, Fa)
        clip.data = bpy.data.meshes.new(clip.name)
        bm.to_mesh(clip.data); bm.free()
    clip.data.name = clip.name
    if old.users == 0:
        bpy.data.meshes.remove(old)
    clip.hide_set(True)
    if gears is None:
        gears = new_helper(obj, obj.name + "_JointGears", home)
    gear_bm.to_mesh(gears.data); gear_bm.free()
    gears.data.update()
    im = gears.modifiers.get("Trim") or gears.modifiers.new("Trim", 'BOOLEAN')
    im.operation, im.solver, im.object = 'INTERSECT', 'MANIFOLD', clip
    gears.hide_set(True)
    gm = gm or obj.modifiers.new(GEAR_MOD_NAME, 'BOOLEAN')
    gm.operation, gm.operand_type, gm.object = 'UNION', 'OBJECT', gears
    set_solver(gm, solver)
    gm.show_viewport = js.show_result
