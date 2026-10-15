"""Single ball and socket, and the socket helpers shared with the double ball."""

import bmesh
import math
from mathutils import Matrix
from ..geometry.mesh import Pieces, add_prism, add_revolve
from .common import add_art, cut_reach


def dome_radius(p, R, rc, warn):
    """radius of the dome that holds a ball socket: the full cylinder by default, or the
    cavity plus `socket_wall` so the socket (and its snap fingers) can be thinner"""
    wall = p["socket_wall"] * p["mm"]
    if wall <= 0:
        return R
    if wall < p["min_wall"]:
        warn.append("socket wall under 0.8 mm: fragile")
    return min(R, rc + wall)


def tilt_reach(swing, R, Rd):
    """how far below the ball centre a tilted socket part can reach: its dome, or the edge
    of its full-width body swinging down"""
    return max(Rd, R * math.sin(math.radians(min(85.0, swing + 5.0))))


def ball_angles(p, rb, rs, rc, g, warn):
    """
    Socket mouth (swing-cone half-angle phi) and the swing it allows.
      Swing mode: phi = swing + the angle the neck (plus clearance) takes up.
      Lip mode:   the mouth is sized so the socket wraps the ball by exactly `lip`
                  (rb - rc*sin(phi) = lip); the swing follows from it.
    Returns (phi, swing_deg).
    """
    neck_ang = math.asin(min(0.95, (rs + g) / rb))
    if p["ball_control"] == 'LIP':
        lip = p["lip"] * p["mm"]
        sin_phi = (rb - lip) / rc
        if sin_phi >= math.sin(math.radians(80)):
            warn.append("lip too small: capped by the 80\u00b0 mouth")
            sin_phi = math.sin(math.radians(80))
        if sin_phi <= math.sin(neck_ang + math.radians(1)):
            warn.append("lip too big for this neck: no swing left, thinner neck or smaller lip")
            sin_phi = math.sin(neck_ang + math.radians(1))
        phi = math.asin(sin_phi)
    else:
        phi = math.radians(p["swing"]) + neck_ang
        if phi > math.radians(80):
            phi = math.radians(80)
            warn.append("swing limited by the stem size")
    return phi, math.degrees(phi - neck_ang)


def socket_relief(p, cut, F, zc, down, rc, rs, R, g, info, warn, Rd=None):
    """
    Snap-fit flex relief: slot(s) cut down through the socket wall, from the mouth to past
    the ball centre, splitting the socket into fingers that spread as the ball snaps in.
    The strip around the axis (|x| < stem + clearance) is left alone, so the ball and its
    neck are never cut. `down`: the socket opens towards -Z (mouth below the ball centre).
    """
    if not p["snap_relief"]:
        return
    n = max(8, p["segs"] // 4)
    mm = p["mm"]
    W = cut_reach(p)
    w = max(p["slot_w"] * mm, g)
    xa = min(rs + 1.5 * g, rc * 0.9)                              # keep clear of the neck
    depth = min(p["slot_depth"] * rc, 0.85 * rc)                  # slot top above the centre
    z0 = -((Rd or R) + 1.5 * g)                                   # starts in the gap below the dome
    t1 = math.asin(depth / rc)
    t2 = -math.acos(xa / rc)
    side = ([(xa, z0), (W, z0), (W, depth)]
            + [(rc * math.cos(t1 + (t2 - t1) * i / n), rc * math.sin(t1 + (t2 - t1) * i / n))
               for i in range(n + 1)])
    s = -1.0 if down else 1.0                                     # socket opening up = mirror in z
    planes = p["slots"]
    for k in range(planes):
        ang = math.pi * k / planes + math.radians(p["slot_angle"])
        Fk = F @ Matrix.Translation((0, 0, zc)) @ Matrix.Rotation(ang, 4, 'Z') @ Matrix.Rotation(math.pi / 2, 4, 'Z')
        for sx in (1.0, -1.0):
            prof = [(sx * x, -s * z) for x, z in side]
            add_prism(cut.new(), prof, -w / 2, w / 2, Fk)
    fingers = 2 * planes
    info.append(f"snap relief: {planes} slot{'s' if planes > 1 else ''} \u2192 {fingers} fingers, "
                f"{w / mm:.2f} mm wide, {(R + depth) / mm:.1f} mm long")


def build_ball(p, F):
    """
    Lower part: body + neck (stem) + ball.  Upper part: ends in a dome centred on the ball,
    holding a socket cavity (ball + gap) with a swing cone so the neck can tilt `swing` deg
    in any direction; twist is unlimited. The dome stays inside its own sphere while it
    tilts, so the lower body only has to sit a little below the dome.
    Built as one solid of revolution (always manifold, no booleans).
    """
    R, g, segs = p["R"], p["gap"], p["segs"]
    cut, pin = Pieces(), bmesh.new()
    info, warn = [], []
    n = max(12, segs // 2)
    W = cut_reach(p)

    rb = min(p["ball"] * R, R - g - p["min_wall"])
    rs = min(p["stem"] * R, rb * 0.8)
    rc = rb + g
    phi, swing = ball_angles(p, rb, rs, rc, g, warn)
    Rd = dome_radius(p, R, rc, warn)
    neck = max(p["neck"] * R, tilt_reach(swing, p["R_out"], Rd) + 3 * g)   # ball centre -> lower body
    if neck > p["neck"] * R + 1e-9:
        warn.append("neck lengthened so the dome clears the body")
    zc, zb = 0.0, -neck

    def pt(rho, a):              # polar point around the ball centre; a = angle from +Z
        return (rho * math.sin(a), zc + rho * math.cos(a))

    def sweep(rho, a0, a1):
        return [pt(rho, a0 + (a1 - a0) * i / n) for i in range(n + 1)]

    a_s = math.asin(rs / rb)
    prof = (sweep(rc, 0.0, math.pi - phi)                         # socket cavity
            + [pt(Rd, math.pi - phi)]                             # swing cone wall
            + sweep(Rd, math.pi - phi, math.pi / 2)[1:]           # dome
            + [(W, zc), (W, zb), (rs, zb)]                        # gap above the lower body
            + sweep(rb, math.pi - a_s, 0.0))                      # up the neck, round the ball
    prof[0] = (0.0, prof[0][1])
    prof[-1] = (0.0, prof[-1][1])
    add_revolve(cut.new(), prof, segs, F)
    socket_relief(p, cut, F, zc, True, rc, rs, R, g, info, warn, Rd)

    lip = rb - rc * math.sin(phi)
    if lip < 0.3 * p["mm"]:
        warn.append("weak ball retention (lip under 0.3 mm): " + ("raise Snap lip" if p["ball_control"] == 'LIP' else "bigger ball, thinner neck or less swing"))
    elif p["snap_relief"] and lip > 0.6 * p["mm"]:
        warn.append("lip over 0.6 mm: hard to snap in, lower Snap lip or add slots")
    mm = p["mm"]
    info.append(f"ball \u00d8{2 * rb / mm:.2f} mm, neck \u00d8{2 * rs / mm:.2f} mm, "
                f"exposed neck {(neck - Rd) / mm:.2f} mm")
    info.append(f"socket lip {lip / mm:.2f} mm, socket wall {(Rd - rc) / mm:.2f} mm")
    info.append(f"swing \u00b1{swing:.0f}\u00b0 any direction, twist 360\u00b0")
    add_art(p, F, zc, 'ball', swing)
    return cut, pin, info, warn
