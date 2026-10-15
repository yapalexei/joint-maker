"""Regenerating a joint: cutters, pins, parts, trims, preview and pose."""

import bpy
import bmesh
import math
from mathutils import Matrix, Vector
from ..constants import MOD_NAME, PIN_MOD_NAME
from .frame import axis_ends, cylinder_frame, joint_params, section_radius
from .helpers import cutter_collection, new_helper, part_objects
from .placement import curve_frames, joint_layout
from .posing import update_pose
from .preview import update_section
from .state import LAST_FRAMES, REBUILDING
from .trimming import update_fit, update_gears, update_limits
from ..geometry.mesh import Pieces, add_revolve, linked_shells, merge_bm
from ..geometry.repair import set_solver, target_solver
from ..joints import JOINT_BUILDERS
from ..joints.common import cut_reach


def rebuild(obj):
    """regenerate the cutter, pins, parts and posed preview for obj (re-entrancy safe: posing
    evaluates the depsgraph, which can fire the curve-edit handler mid-rebuild)"""
    key = obj.as_pointer()
    if key in REBUILDING:
        return None
    REBUILDING.add(key)
    try:
        return _rebuild(obj)
    finally:
        REBUILDING.discard(key)


def _rebuild(obj):
    js = obj.joint_maker
    if not js.active:
        return None
    p, F0 = joint_params(obj, js)
    if p is None:
        return None
    _, R, H, s_perp = cylinder_frame(obj, js)
    lo, hi = axis_ends(obj, js)
    a_hat = (hi - lo).normalized()
    on_curve = js.place_curve is not None
    if on_curve:
        cf = curve_frames(obj, js, p["mm"])
        if cf is None:
            frames, arcs, warn = [], [], ["placement curve has no usable points"]
        else:
            frames, arcs, warn = cf
    else:
        layout, warn = joint_layout(obj, js, H, p["mm"])
        frames = [cylinder_frame(obj, js, position=frac, extra_rot=rot)[0] for frac, rot in layout]
        arcs = [(F.translation - lo).dot(a_hat) for F in frames]
    LAST_FRAMES[obj.as_pointer()] = [obj.matrix_world @ F for F in frames]   # for the gizmos
    pieces, pin_bm, info = Pieces(), bmesh.new(), []
    spans, owner, axes_i, waists = [], [], [], []   # per-joint extents, piece owner, axes, waists
    waist_pieces = set()                            # indices (in `pieces`) of the waist pipes
    for i, F in enumerate(frames):
        jc = F.translation.copy()
        jz = (F.to_3x3() @ Vector((0, 0, 1))).normalized()     # this joint's own axis
        Rs = section_radius(obj, js, F, R)                     # the shape right at this joint
        p["R_out"], p["R"] = Rs, Rs * js.joint_scale
        tilt = 0.0 if on_curve else min(math.radians(80), jz.angle(a_hat) if jz.dot(a_hat) >= 0 else jz.angle(-a_hat))
        p["reach_extra"] = 1.3 * (R + Rs + p["gap"]) * math.tan(tilt)
        cut_i, pin_i, info_i, warn_i = JOINT_BUILDERS[js.joint_type](p, F)
        zs = [(v.co - jc).dot(jz) for bm in cut_i for v in bm.verts]
        spans.append((arcs[i] + min(zs), arcs[i] + max(zs)) if zs else (arcs[i], arcs[i]))
        if js.joint_scale < 0.999 and zs:
            # smaller joint: slim the cylinder to the joint radius around it.
            # Full width may only return (real R - joint R) beyond the joint, where the wide
            # bodies can't collide when it bends: a taper covers part of that distance and,
            # with "keep range", a straight neck covers the rest.
            Rj, Ro = p["R"], p["R_out"]
            W = cut_reach(p)
            need = Ro - Rj
            if js.waist_taper == 'AUTO':
                t = need                                             # 45 deg
            elif js.waist_taper == 'CUSTOM':
                t = max(0.0, js.taper_len * p["mm"])
            else:
                t = 0.0                                              # straight step
            e = max(0.0, need - t) if js.keep_range else 0.0         # straight neck
            if not js.keep_range and t + 1e-9 < need and i == 0:
                warn.append(f"short waist: bending range reduced (full range needs "
                            f"{need / p['mm']:.1f} mm of taper/neck)")
            z0, z1 = min(zs), max(zs)
            Fa = Matrix.Translation(jc) @ Vector((0, 0, 1)).rotation_difference(jz).to_matrix().to_4x4()
            waists.append((Rj, Fa, z0 - e - t, z1 + e + t))
            waist_pieces.add(len(pieces) + len(cut_i))
            add_revolve(cut_i.new(),
                        [(Rj, z0 - e), (Rj, z1 + e), (Ro, z1 + e + t), (W, z1 + e + t),
                         (W, z0 - e - t), (Ro, z0 - e - t)],
                        p["segs"], Fa)
        owner += [i] * len(cut_i)
        axes_i.append((jc, jz, p["R_out"], p["R"]))
        pieces.extend(cut_i)
        merge_bm(pin_bm, pin_i)
        if i == 0:
            info = info_i
        for w in warn_i:
            if w not in warn:
                warn.append(w)
    if any(a[1] > b[0] for a, b in zip(spans, spans[1:])):
        warn.append("joints overlap: more spacing or fewer joints")
    elif any(b[0] - a[1] < 1.0 * p["mm"] for a, b in zip(spans, spans[1:])):
        warn.append("under 1 mm of solid between joints: weak, more spacing or fewer joints")
    if js.joint_scale < 0.999:
        info.insert(0, f"joint size {js.joint_scale * 100:.0f}%: waist \u00d8{2 * p['R'] / p['mm']:.1f} mm")
    if len(frames) > 1:
        gaps = [(b[0] - a[1]) / p["mm"] for a, b in zip(spans, spans[1:])]
        info.insert(0, f"{len(frames)} joints, solid between joints {min(gaps):.1f} mm")
    if on_curve and arcs:
        info.insert(0, f"on curve '{js.place_curve.name}': joints at "
                       + ", ".join(f"{a_ / p['mm']:.0f}" for a_ in arcs) + " mm along it")

    coll = cutter_collection(obj, js)
    existing = sorted((o for o in coll.objects if o.name.startswith(obj.name + "_Cut")), key=lambda o: o.name)
    for i, bm in enumerate(pieces):
        ob = existing[i] if i < len(existing) else new_helper(obj, f"{obj.name}_Cut{i:02d}", coll)
        bm.to_mesh(ob.data); bm.free()
        ob.data.update()
        ob.hide_set(not js.show_cutter)
    for ob in existing[len(pieces):]:
        me = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        bpy.data.meshes.remove(me)
    piece_objs = sorted((o for o in coll.objects if o.name.startswith(obj.name + "_Cut")), key=lambda o: o.name)

    # shrink-fit: trim every cutter piece to a hull around the object at its joint
    update_fit(obj, js, p, piece_objs, owner, axes_i, warn)
    update_limits(obj, js, p, piece_objs, owner, axes_i, info, waist_pieces)

    pins = js.pins
    if pins is None or pins.name not in bpy.data.objects:
        # outside the cutter collection, otherwise it would be subtracted too
        home = obj.users_collection[0] if obj.users_collection else bpy.context.scene.collection
        pins = js.pins = new_helper(obj, obj.name + "_JointPins", home)
    pin_bm.to_mesh(pins.data); pin_bm.free()
    pins.data.update()
    pins.hide_set(True)

    # 1) subtract every cutter piece (unioned by the Manifold solver)
    m = obj.modifiers.get(MOD_NAME) or obj.modifiers.new(MOD_NAME, 'BOOLEAN')
    solver = 'EXACT' if (p.get("force_exact") and js.solver_mode == 'AUTO') else target_solver(obj, js, warn)
    m.operation = 'DIFFERENCE'
    set_solver(m, solver)
    m.operand_type, m.collection = 'COLLECTION', coll
    m.show_viewport = js.show_result
    # 2) add the pins back (they bridge the gaps they were cut from)
    pm = obj.modifiers.get(PIN_MOD_NAME)
    if len(pins.data.vertices):
        pm = pm or obj.modifiers.new(PIN_MOD_NAME, 'BOOLEAN')
        pm.operation, pm.operand_type, pm.object = 'UNION', 'OBJECT', pins
        set_solver(pm, solver)
        pm.show_viewport = js.show_result
    elif pm:
        obj.modifiers.remove(pm)

    # 2b) gears: added back, trimmed to the original cylinder (a hidden copy of its mesh)
    # (a smaller joint trims its gears to the waist radius instead of the full cylinder)
    waist = [(r, Fa, z0, z1, p["segs"]) for r, Fa, z0, z1 in waists] if (js.joint_scale < 0.999 and waists) else None
    update_gears(obj, js, p["gear_bm"], waist, solver)

    # 3) separate printable parts (e.g. assemblable pins): real solid objects next to the joint
    home = obj.users_collection[0] if obj.users_collection else bpy.context.scene.collection
    old = part_objects(obj)
    for i, bm in enumerate(p["parts"]):
        if i < len(old):
            ob = old[i]
        else:
            ob = new_helper(obj, f"{obj.name}_Pin{i:02d}", home)
            ob.display_type = 'SOLID'
            ob.hide_render = False
            ob["joint_maker_part"] = True
        bm.to_mesh(ob.data); bm.free()
        ob.data.update()
        if obj.data.materials and not ob.data.materials:
            ob.data.materials.append(obj.data.materials[0])
    for ob in old[len(p["parts"]):]:
        me = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        bpy.data.meshes.remove(me)

    # fitted cutter / custom shapes: make sure the parts really came apart
    tilted = abs(js.tilt_x) > 1e-6 or abs(js.tilt_y) > 1e-6
    if js.fit_cutter or js.joint_type == 'SHAPE' or on_curve or tilted or js.limit_reach_on:
        dg = bpy.context.evaluated_depsgraph_get()
        ev = obj.evaluated_get(dg)
        eb = bmesh.new(); eb.from_mesh(ev.to_mesh()); ev.to_mesh_clear()
        got = len(linked_shells(eb)); eb.free()
        bb = bmesh.new(); bb.from_mesh(obj.data)
        base = len(linked_shells(bb)); bb.free()
        want = base + len(p["arts"])
        if got > want and on_curve:
            warn.append(f"got {got - base + 1} parts instead of {len(p['arts']) + 1}: stray slivers, "
                        "a joint may be off the shape's centre (turn on Snap to section centre)")
        elif got > want and js.limit_reach_on and js.limit_bevel > 0:
            warn.append(f"got {got - base + 1} parts instead of {len(p['arts']) + 1}: the outer bevel "
                        "leaves stray slivers, use a smaller Outer bevel")
        elif got > want and tilted:
            warn.append(f"got {got - base + 1} parts instead of {len(p['arts']) + 1}: the steep tilt "
                        "leaves stray slivers, keep the tilt under ~35\u00b0")
        if got < want:
            if js.limit_reach_on and not js.fit_cutter:
                warn.append(f"parts still joined ({got - base + 1} of {len(p['arts']) + 1}): the part is "
                            "wider somewhere along the joint, raise Reach past surface")
            elif on_curve and not js.fit_cutter and js.joint_type != 'SHAPE':
                warn.append(f"got {got - base + 1} parts instead of {len(p['arts']) + 1}: a joint may "
                            "be off the shape's centre (turn on Snap to section centre)")
            elif js.joint_type == 'SHAPE' and not js.fit_cutter:
                warn.append(f"the shape doesn't split the part ({got - base + 1} of {len(p['arts']) + 1} "
                            "parts): make it wider, or check it reaches the outside all round")
            else:
                warn.append(f"fit: parts still joined ({got - base + 1} of {len(p['arts']) + 1}): "
                            "something outside the fit hull bridges the joint, raise the margin")

    # 4) pose the chain along the path (preview)
    if on_curve and js.path is not None:
        warn.append("Path posing is off while joints follow a placement curve")
    poses, pwarn = update_pose(obj, js, [] if on_curve else p["arts"])
    warn += pwarn
    if poses is not None:
        info.append(f"posed along '{js.path.name}': {len(poses)} rigid parts")

    js.info = " | ".join(info)
    js.warning = "; ".join(warn)
    update_section(obj)
    return dict(poses=poses, arts=p["arts"])
