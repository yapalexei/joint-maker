"""Where a joint sits: the joint frame on the part, its radius and printed-mm conversions."""

import bmesh
import math
from mathutils import Matrix, Vector
from ..constants import AXES
from ..geometry.sections import section_info


def joint_turn(js, extra_rot=0.0):
    """the joint's own orientation on top of its axis frame: tilt on the two cross axes,
    then the bend direction around the axis, then the optional flip"""
    M = (Matrix.Rotation(math.radians(js.tilt_x), 4, 'X') @ Matrix.Rotation(math.radians(js.tilt_y), 4, 'Y')
         @ Matrix.Rotation(math.radians(js.rotation + extra_rot), 4, 'Z'))
    if js.flip:
        M = M @ Matrix.Rotation(math.pi, 4, 'X')
    return M


def cylinder_frame(obj, js, position=None, extra_rot=0.0):
    vs = [v.co for v in obj.data.vertices]
    if not vs:
        return None
    lo = Vector([min(v[i] for v in vs) for i in range(3)])
    hi = Vector([max(v[i] for v in vs) for i in range(3)])
    a = AXES[js.axis]
    o = [i for i in range(3) if i != a]
    ctr = (lo + hi) / 2
    R = max(hi[o[0]] - lo[o[0]], hi[o[1]] - lo[o[1]]) / 2
    H = hi[a] - lo[a]
    axis_vec = Vector([1.0 if i == a else 0.0 for i in range(3)])
    align = {'Z': Matrix(),
             'X': Matrix.Rotation(math.radians(90), 4, 'Y'),
             'Y': Matrix.Rotation(math.radians(-90), 4, 'X')}[js.axis]
    sc = obj.matrix_world.to_scale()
    # off-centre offset (printed mm) across the plane perpendicular to the axis
    off = Vector((0.0, 0.0, 0.0))
    for i, val in zip(o, (js.offset_a, js.offset_b)):
        off[i] = val / (js.mm_per_unit * max(abs(sc[i]), 1e-9))
    pos = js.position if position is None else position
    F = Matrix.Translation(ctr + off + axis_vec * (pos - 0.5) * H) @ align @ joint_turn(js, extra_rot)
    # world scale perpendicular to the axis -> converts world mm into local units
    s_perp = (sc[o[0]] + sc[o[1]]) / 2
    return F, R, H, s_perp


def section_radius(obj, js, F, fallback):
    """radius of the shape around the joint axis at the joint (ignores other mesh parts)"""
    if js.radius_mode == 'BBOX':
        return fallback
    sec = section_info(obj, F.translation, (F.to_3x3() @ Vector((0, 0, 1))).normalized())
    return sec[1] if sec and sec[1] > 1e-9 else fallback


def joint_params(obj, js):
    fr = cylinder_frame(obj, js)
    if fr is None:
        return None, None
    F, R, H, s_perp = fr
    R = section_radius(obj, js, F, R)
    mm = 1.0 / (js.mm_per_unit * s_perp)     # 1 printed mm in local units
    p = dict(R=R * js.joint_scale, R_out=R, H=H, mm=mm, mm_unit=js.mm_per_unit * s_perp,
             gap=js.gap * mm, clr=js.pin_clearance * mm,
             tongue=js.tongue_width, pin=js.pin_size, pin_style=js.pin_style,
             cone_angle=js.cone_angle, segs=js.segments,
             link_end=js.link_end, link_len=js.link_length, ball=js.ball_size,
             neck=js.neck_length, axle=js.axle_size, pivot_twist=js.pivot_twist,
             press=js.press_fit, head_tol=js.head_tol, parts=[],
             gears=(js.joint_type == 'DOUBLE' and js.link_end == 'CLIP' and js.gear_mesh),
             gear_module=js.gear_module, gear_backlash=js.gear_backlash, gear_bm=bmesh.new(),
             snap_relief=js.snap_relief, socket_wall=js.socket_wall, slots=js.slots, slot_w=js.slot_w,
             slot_depth=js.slot_depth, slot_angle=js.slot_angle, clip_wall=js.clip_wall, snap=js.snap, mouth=js.mouth_side,
             stem=js.stem_size, swing=js.swing, ball_control=js.ball_control, lip=js.snap_lip)
    p["min_wall"] = max(2.0 * p["gap"], 0.8 * mm)   # ~0.8 mm minimum printable feature
    p["arts"] = []                                   # pivots, recorded by the builders (for posing)
    p["js"] = js
    return p, F


def axis_ends(obj, js):
    """local points at the bottom and top of the cylinder axis"""
    F_lo, R, H, s = cylinder_frame(obj, js, position=0.0)
    F_hi = cylinder_frame(obj, js, position=1.0)[0]
    return F_lo.translation.copy(), F_hi.translation.copy()


def axis_world(obj, js):
    """(bottom point, unit axis, length, joint centre, radius) of the cylinder in world space"""
    fr = cylinder_frame(obj, js)
    if fr is None:
        return None
    F, R, H, s_perp = fr
    M = obj.matrix_world
    lo, hi = axis_ends(obj, js)
    a = M.to_3x3() @ (hi - lo)
    return M @ lo, a.normalized(), a.length, M @ F.translation, R * s_perp


def mm_per_position(obj, js):
    """printed mm for a change of 1.0 in js.position (the cylinder's printed length)"""
    fr = cylinder_frame(obj, js)
    if fr is None:
        return 0.0
    lo, hi = axis_ends(obj, js)
    return (obj.matrix_world.to_3x3() @ (hi - lo)).length * js.mm_per_unit


def offset_axes(obj, js):
    """the two local axes across the cylinder axis: [(letter, world unit direction), ...]"""
    a = AXES[js.axis]
    M3 = obj.matrix_world.to_3x3()
    out = []
    for i in (i for i in range(3) if i != a):
        e = Vector((0.0, 0.0, 0.0)); e[i] = 1.0
        out.append(("XYZ"[i], (M3 @ e).normalized()))
    return out


def center_on_shape(obj, js):
    """slice the mesh at the joint and move the joint onto the area centre of the outline that
    surrounds it (other parts of the mesh in the same slice are ignored). Returns False if the
    slice is empty."""
    fr = cylinder_frame(obj, js)
    if fr is None:
        return False
    F = fr[0]
    a = AXES[js.axis]
    n = Vector((0.0, 0.0, 0.0)); n[a] = 1.0
    sec = section_info(obj, F.translation, n)
    if sec is None:
        return False
    c = sec[0]
    vs = [v.co for v in obj.data.vertices]
    ctr = Vector([(min(v[i] for v in vs) + max(v[i] for v in vs)) / 2 for i in range(3)])
    sc = obj.matrix_world.to_scale()
    o = [i for i in range(3) if i != a]
    js.offset_a = (c[o[0]] - ctr[o[0]]) * js.mm_per_unit * sc[o[0]]
    js.offset_b = (c[o[1]] - ctr[o[1]]) * js.mm_per_unit * sc[o[1]]
    return True
