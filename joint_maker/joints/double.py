"""Double joints: double pivot (H link), double ball (dog-bone) and E-clip (with gears)."""

import bmesh
import math
from mathutils import Matrix
from ..geometry.mesh import Pieces, add_box, add_cone, add_prism, add_revolve
from .ball import ball_angles, dome_radius, socket_relief, tilt_reach
from .common import add_art, cut_reach, short_link_range
from .hinge import hinge_into


def gear_outline(z, rp, backlash, zc, down, n_flank=8, alpha=math.radians(20)):
    """
    2D outline (y, z) of an involute spur gear: z teeth, pitch radius rp, centred on the axis
    at height zc. Angles are measured from the direction facing the other gear (-Z when
    `down`), and the gear facing up is offset half a tooth so the two mesh at the middle.
    `backlash` (total) is split between the two gears; root clearance is 0.25 module.
    """
    m = 2 * rp / z
    rb = rp * math.cos(alpha)
    ra = rp + m
    rf = rp - 1.25 * m
    inv = lambda a: math.tan(a) - a
    phi_p = (math.pi * m / 2 - backlash / 2) / (2 * rp)          # half tooth angle at the pitch circle

    def flank_angle(r):                                          # half tooth angle at radius r
        r = max(r, rb)
        return phi_p + inv(alpha) - inv(math.acos(rb / r))

    r_lo = max(rf, rb)
    radii = [r_lo + (ra - r_lo) * i / n_flank for i in range(n_flank + 1)]
    sgn = -1.0 if down else 1.0
    off = 0.0 if down else math.pi / z

    def P(r, a):
        return (r * math.sin(a), zc + sgn * r * math.cos(a)) if down else \
               (r * math.sin(a), zc + r * math.cos(a))

    pts = []
    for i in range(z):
        c = 2 * math.pi * i / z + off
        if rf < rb:
            pts.append(P(rf, c - flank_angle(rb)))
        pts += [P(r, c - flank_angle(r)) for r in radii]                       # leading flank
        tip = flank_angle(ra)
        pts += [P(ra, c - tip + 2 * tip * k / 3) for k in range(1, 3)]        # tip land
        pts += [P(r, c + flank_angle(r)) for r in reversed(radii)]             # trailing flank
        if rf < rb:
            pts.append(P(rf, c + flank_angle(rb)))
        nxt = c + 2 * math.pi / z
        a0, a1 = c + flank_angle(r_lo), nxt - flank_angle(r_lo)
        pts += [P(rf, a0 + (a1 - a0) * k / 4) for k in range(1, 4)]          # root
    if not down:
        pts.reverse()
    return pts, m, ra, rf


def eclip_profile(rc, rh, m, ch, zu, zl, n, back=False):
    """side outline (y, z) of the E-shaped link: a stadium (round ends radius rc around the
    two axles) with a round socket (radius rh) at each end, each opened towards -y (front)
    by a mouth of half-width m with a lead-in chamfer ch. One simple polygon."""
    def P(a, rho, zc):
        return (rho * math.cos(a), zc + rho * math.sin(a))

    def arc(a0, a1, rho, zc):
        return [P(a0 + (a1 - a0) * i / n, rho, zc) for i in range(n + 1)]

    pi = math.pi
    a_out = math.asin(min(0.999, (m + ch) / rc))     # outer arc ends just past the chamfer
    a_in = math.asin(m / rh)                          # where the mouth meets the socket
    yo = -math.sqrt(rc * rc - (m + ch) ** 2)
    yh = -math.sqrt(rh * rh - m * m)
    pts = []
    pts += arc(pi - a_out, 0.0, rc, zu)               # upper round end, over the top to the back
    pts += arc(0.0, -pi + a_out, rc, zl)              # back line, lower round end to the front
    pts += [(yo + ch, zl - m), (yh, zl - m)]          # lower mouth (chamfered), lower edge
    pts += arc(-pi + a_in, pi - a_in, rh, zl)         # lower socket
    pts += [(-rc + ch, zl + m), (-rc, zl + m + ch)]   # lower mouth, upper edge
    pts += [(-rc, zu - m - ch), (-rc + ch, zu - m)]   # front line, upper mouth lower edge
    pts += arc(-pi + a_in, pi - a_in, rh, zu)         # upper socket
    pts += [(yo + ch, zu + m)]                        # upper mouth, upper edge (closes to start)
    if back:
        pts = [(-y, z) for y, z in reversed(pts)]
    return pts


def build_eclip(p, F):
    """
    Double joint with snap-on E link.
    Top and bottom parts: forks (two prongs) with a fixed axle across the slot.
    Link: a flat bar (straight stick seen from the front) that looks like a rounded E from
    the side: each end is a round socket around an axle, opened on one side by a mouth that
    is `snap` narrower than the axle, so the link clicks onto both axles.
    """
    R, g, c, segs = p["R"], p["gap"], p["clr"], p["segs"]
    cut, add = Pieces(), bmesh.new()
    info, warn = [], []
    n = max(12, segs // 2)
    W = cut_reach(p)
    eps = g * 0.25
    mw = p["min_wall"]

    tw = max(2 * mw, min(p["tongue"] * 2 * R, 2 * (R - g - mw)))     # link thickness (along X)
    hw = tw / 2
    ra = p["axle"] * R                                               # axle radius
    rh = ra + c                                                      # socket radius
    rc = min(rh + p["clip_wall"] * R, R - g)                         # round end radius of the link
    if rc - rh < mw:
        warn.append("clip wall thinner than 0.8 mm")
    m = max(ra * 0.3, ra - p["snap"] * p["mm"] / 2)                   # mouth half-width
    ch = min(0.35 * ra, 0.6 * (rc - rh))                             # lead-in chamfer
    L_full = 2 * p["R_out"] + 2 * g                                  # full range: full-width bodies clear
    r_min = ra + mw                                                  # prong end must hold the axle
    L_min = max(2 * r_min + g, 2 * rh + mw, 2 * (m + ch) + mw)       # prong ends / link sockets fit
    L = max(p["link_len"] * R, L_min)
    if L > p["link_len"] * R + 1e-9:
        warn.append(f"link at its minimum {L_min / p['mm']:.2f} mm (axles and the link's sockets must fit)")
    RL = R if L >= L_full else min(R, (L - g) / 2)                   # round prong ends
    zu, zl = L / 2, -L / 2
    z0, z1 = zl - rc - g, zu + rc + g                                # where the fork bodies start
    geared = p["gears"]
    mm = p["mm"]

    # --- gaps
    add_box(cut.new(), -hw - eps, hw + eps, -W, W, z0, z1, F)       # the link's slot
    for s in (1, -1):
        xa, xb = sorted((s * hw, s * (hw + g)))
        add_box(cut.new(), xa, xb, -W, W, z0 - eps, z1 + eps, F)     # side slots
        xa, xb = sorted((s * (hw + g - eps), s * W))
        if geared:
            # clear the whole space between the forks; the gears are added back (trimmed to
            # the cylinder) so the prong ends become meshing gear sectors
            add_box(cut.new(), xa, xb, -W, W, zl, zu, F)
            continue
        prof = ([(-W, zl), (-RL, zl)] + [(RL * math.cos(math.pi * (1 - i / n)), zl + RL * math.sin(math.pi * (1 - i / n))) for i in range(1, n)]
                + [(RL, zl), (W, zl), (W, zu), (RL, zu)]
                + [(RL * math.cos(-math.pi * i / n), zu + RL * math.sin(-math.pi * i / n)) for i in range(1, n)]
                + [(-RL, zu), (-W, zu)])
        add_prism(cut.new(), prof, xa, xb, F)                         # between the prongs

    # --- added back: the two axles (part of the forks) and the E link itself
    for zc in (zu, zl):
        add_cone(add, ra, ra, (-(hw + 2 * g), 0, zc), (hw + 2 * g, 0, zc), segs, F)
    add_prism(add, eclip_profile(rc, rh, m, ch, zu, zl, n, back=p["mouth"] == 'BACK'), -hw, hw, F)

    lim = short_link_range(RL, g, p["R_out"])
    if RL < R - 1e-9:
        warn.append(f"short link: bend limited to \u00b1{lim:.0f}\u00b0 per axle")
    if geared:
        rp = L / 2                                                   # gears meet halfway
        z_t = max(6, int(round(2 * rp / (p["gear_module"] * mm))))
        bl = p["gear_backlash"] * mm
        gu, mod_, ra_g, rf_g = gear_outline(z_t, rp, bl, zu, True)
        gd, _, _, _ = gear_outline(z_t, rp, bl, zl, False)
        if rf_g <= ra + 0.5 * mm:
            warn.append("gear teeth reach the axle: smaller module or thinner axle")
        if z_t < 10:
            warn.append(f"only {z_t} teeth: smaller module for smoother meshing")
        x0 = hw + g + eps                                            # just past the side slot
        for s in (1, -1):
            xa, xb = sorted((s * x0, s * W))
            for outline in (gu, gd):
                add_prism(p["gear_bm"], outline, xa, xb, F)
        # teeth only exist inside the cylinder: contact at angle t sits at y = rp*sin(t)
        y_in = math.sqrt(max(R * R - x0 * x0, 0.0))
        lim = min(lim, 85.0, math.degrees(math.asin(min(1.0, (y_in - mod_) / rp))))
        info.append(f"gears: {z_t} teeth, module {mod_ / mm:.2f} mm, backlash {bl / mm:.2f} mm")
    add_art(p, F, zu, 'hinge', lim)
    add_art(p, F, zl, 'hinge', lim)
    if geared:                                                       # the pair bends together
        p["arts"][-2]["pair"] = p["arts"][-1]["pair"] = len(p["arts"])
    info.append(f"axles \u00d8{2 * ra / mm:.2f} mm, mouth {2 * m / mm:.2f} mm (snap {2 * (ra - m) / mm:.2f} mm)")
    info.append(f"clip wall {(rc - rh) / mm:.2f} mm, link {tw / mm:.2f} mm thick, axle spacing {L / mm:.2f} mm")
    if geared:
        info.append(f"geared: both sides bend together, \u00b1{lim:.0f}\u00b0 each (\u00b1{2 * lim:.0f}\u00b0 total)")
    else:
        info.append(f"range of motion \u00b1{lim:.0f}\u00b0 per axle (\u00b1{2 * lim:.0f}\u00b0 total)")
    info.append(f"axle spacing: full range from {L_full / mm:.2f} mm, minimum {L_min / mm:.2f} mm")
    return cut, add, info, warn


def build_double(p, F):
    if p["link_end"] == 'CLIP':
        return build_eclip(p, F)
    R, g, segs = p["R"], p["gap"], p["segs"]
    cut, pin = Pieces(), bmesh.new()
    info, warn = [], []

    if p["link_end"] == 'PIVOT':
        mw = p["min_wall"]
        L_full = 2 * (p["R_out"] + g) + mw          # full +-90 deg: the full-width bodies clear
        r_min = max(p["clr"] + 2 * mw, 0.15 * R)    # smallest round end that still holds its pin
        # the link's two side plates stay joined by a cross-bar at least one wall thick
        L_min = 2 * (r_min + g) + mw
        L = max(p["link_len"] * R, L_min)
        if L > p["link_len"] * R + 1e-9:
            warn.append(f"link at its minimum {L_min / p['mm']:.2f} mm (the round ends must hold their pins)")
        lobe = None if L >= L_full else min(R, (L - mw) / 2 - g)
        i1, w1 = hinge_into(p, F @ Matrix.Translation((0, 0, -L / 2)), cut, pin, lobe)
        twist = Matrix.Rotation(math.radians(p["pivot_twist"]), 4, 'Z')   # 90 = universal-joint style
        hinge_into(p, F @ Matrix.Translation((0, 0, L / 2)) @ twist @ Matrix.Rotation(math.pi, 4, 'X'), cut, pin, lobe)
        info += i1
        warn += w1
        lim = p["_hinge_lim"]
        info.append(f"pivot spacing {L / p['mm']:.2f} mm (full range from {L_full / p['mm']:.2f}, "
                    f"minimum {L_min / p['mm']:.2f})")
        if abs(p["pivot_twist"]) > 1e-6:
            info.append(f"upper pivot turned {p['pivot_twist']:.0f}\u00b0: \u00b1{lim:.0f}\u00b0 on each axis")
        else:
            info.append(f"range of motion \u00b1{lim:.0f}\u00b0 per pivot (\u00b1{2 * lim:.0f}\u00b0 total)")
        if lobe is not None:
            warn.append(f"short link: bend limited to \u00b1{lim:.0f}\u00b0 per pivot")
        return cut, pin, info, warn

    # ---- ball ends: the link is a dog-bone (two balls + stem); each part ends in a dome
    # centred on its ball, so it can swivel without touching the other part
    n = max(12, segs // 2)
    rb = p["ball"] * R
    rs = p["stem"] * R
    rb = min(rb, R - g - p["min_wall"])
    rs = min(rs, rb * 0.8)
    G = 3 * g                                                     # dome-to-dome gap (minimum)
    rc = rb + g                                                   # socket cavity radius
    phi, swing = ball_angles(p, rb, rs, rc, g, warn)              # swing-cone half-angle
    Rd = dome_radius(p, R, rc, warn)
    L_full = 2 * tilt_reach(swing, p["R_out"], Rd) + G           # full swing: tilted parts clear
    L_min = 2 * Rd + G                                            # the two domes just clear
    L = max(p["link_len"] * R, L_min)
    if L > p["link_len"] * R + 1e-9:
        warn.append(f"link at its minimum {L_min / p['mm']:.2f} mm (the two domes must clear)")
    if L < L_full - 1e-9:
        # a tilted part's full-width edge reaches R*sin(tilt+5) below its ball: keep it clear
        reach = (L - G) / 2
        sw2 = math.degrees(math.asin(min(1.0, reach / max(p["R_out"], 1e-9)))) - 5.0 if reach < p["R_out"] else 85.0
        swing = max(0.0, min(swing, sw2))
        warn.append(f"short link: swing limited to \u00b1{swing:.0f}\u00b0 per ball")
    zu, zl = L / 2, -L / 2
    W = cut_reach(p)

    def pt(rho, a, zc):          # polar point around a ball centre; a = angle from +Z
        return (rho * math.sin(a), zc + rho * math.cos(a))

    def sweep(rho, a0, a1, zc):
        return [pt(rho, a0 + (a1 - a0) * i / n, zc) for i in range(n + 1)]

    # The whole cutter is one solid of revolution: the gap around the link, built as a
    # single 2D outline (cutter outline, then the link outline traced back) and spun
    # around the axis -> always manifold, no booleans needed.
    outer = (sweep(rc, 0.0, math.pi - phi, zu)                    # upper socket cavity
             + [pt(Rd, math.pi - phi, zu)]                        # swing cone wall
             + sweep(Rd, math.pi - phi, math.pi / 2, zu)[1:]      # upper dome
             + [(W, zu), (W, zl)]
             + sweep(Rd, math.pi / 2, phi, zl)                    # lower dome
             + sweep(rc, phi, math.pi, zl))                       # cone wall + lower cavity
    a_s = math.asin(rs / rb)
    link = (sweep(rb, math.pi, a_s, zl)                           # lower ball, up to the stem
            + sweep(rb, math.pi - a_s, 0.0, zu))                  # stem, then upper ball
    prof = outer + link
    prof[0] = (0.0, prof[0][1]); prof[len(outer) - 1] = (0.0, prof[len(outer) - 1][1])
    prof[len(outer)] = (0.0, prof[len(outer)][1]); prof[-1] = (0.0, prof[-1][1])
    add_revolve(cut.new(), prof, segs, F)
    socket_relief(p, cut, F, zu, True, rc, rs, R, g, info, warn, Rd)
    socket_relief(p, cut, F, zl, False, rc, rs, R, g, info, warn, Rd)
    if len(info) > 1:
        info.pop()                                                # same note twice

    lip = rb - (rb + g) * math.sin(phi)                           # how far the socket wraps the ball
    if lip < 0.3 * p["mm"]:
        warn.append("weak ball retention (lip under 0.3 mm): " + ("raise Snap lip" if p["ball_control"] == 'LIP' else "bigger ball, thinner neck or less swing"))
    elif p["snap_relief"] and lip > 0.6 * p["mm"]:
        warn.append("lip over 0.6 mm: hard to snap in, lower Snap lip or add slots")
    info.append(f"balls Ø{2 * rb / p['mm']:.2f} mm, stem Ø{2 * rs / p['mm']:.2f} mm")
    info.append(f"socket lip {lip / p['mm']:.2f} mm, socket wall {(Rd - rc) / p['mm']:.2f} mm, "
                f"ball spacing {L / p['mm']:.2f} mm")
    info.append(f"swing ±{swing:.0f}° per ball (±{2 * swing:.0f}° total), twist 360°")
    add_art(p, F, zu, 'ball', swing)
    add_art(p, F, zl, 'ball', swing)
    return cut, pin, info, warn
