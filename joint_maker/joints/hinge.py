"""Pivot (print-in-place knuckle hinge) with cone, rod or separate headed pins."""

import bmesh
import math
from mathutils import Matrix
from ..geometry.mesh import Pieces, add_box, add_cone, add_prism, add_revolve, lobe_profile
from .common import add_art, cut_reach, short_link_range


def hinge_into(p, F, cut, pin, lobe=None):
    """
    Adds one print-in-place hinge to the `cut` / `pin` bmeshes.
    Part A (below, -Z): centre tongue  = {z<0} U lobe, in |x| < tw/2
    Part B (above, +Z): two outer prongs = {z>0} U lobe, in |x| > tw/2 + gap
    Each part's full-width body stops `gap` beyond the other part's lobe, so the joint
    swings +-90 deg. B carries the pin (cones or a rod) that runs into a clearance
    recess in A's tongue.
    """
    R, g, c, segs = p["R"], p["gap"], p["clr"], p["segs"]
    info, warn = [], []
    W = cut_reach(p)                         # reach past the (real) cylinder wall
    RL = R if lobe is None else min(R, lobe)  # radius of the round ends (smaller for short links)
    top = RL + g                             # where the opposing body starts
    eps = g * 0.25

    # tongue width, kept so that prongs stay printable
    min_wall = p["min_wall"]
    tw = max(2 * min_wall, min(p["tongue"] * 2 * R, 2 * (R - g - min_wall)))
    hw = tw / 2

    add_prism(cut.new(), lobe_profile(RL, W, top, segs, True), -hw - eps, hw + eps, F)      # above tongue
    for s in (1, -1):
        xa, xb = sorted((s * (hw + g - eps), s * W))
        add_prism(cut.new(), lobe_profile(RL, W, top, segs, False), xa, xb, F)               # below prongs
        xa, xb = sorted((s * hw, s * (hw + g)))
        add_box(cut.new(), xa, xb, -W, W, -top - eps, top + eps, F)                          # side slots

    web = max(min_wall, 2 * g)               # material kept between the two pin recesses
    if p["pin_style"] == 'CONE':
        ang = math.radians(p["cone_angle"])  # half-angle from the axis; 45 deg prints w/o support
        t = math.tan(ang)
        rp = min(p["pin"] * R, max(RL - c - min_wall, g))
        # largest cone that still leaves `web` in the middle of the tongue
        h_max = hw + g - c / math.sin(ang) - web / 2
        h = min(rp / t, h_max)
        if h < 0.75 * rp / t:
            warn.append("pin much smaller than set: widen the tongue")
        if h <= g:
            warn.append("tongue too narrow for cone pins")
            h = max(h, g * 1.01)
        rp = h * t
        for s in (1, -1):
            x_apex = s * (hw + g - h)
            x_root = s * (hw + g + g)                   # root a little inside the prong
            add_cone(pin, (abs(x_root - x_apex)) * t, R * 1e-4,
                     (x_root, 0, 0), (x_apex, 0, 0), segs, F)                           # male
            fa = s * (abs(x_apex) - c / math.sin(ang))                                   # female apex
            x_mid = s * (hw + g * 0.5)                  # end inside the slot, not on a face
            add_cone(cut.new(), abs(x_mid - fa) * t, R * 1e-4,
                     (x_mid, 0, 0), (fa, 0, 0), segs, F)                                # female (clearance)
        info.append(f"cone pins: Ø{2 * rp / p['mm']:.2f} mm, {math.degrees(ang):.0f}°")
    elif p["pin_style"] == 'PIN':
        # assemblable: plain holes + a separate headed pin (printed on its own).
        # +X prong and tongue: clearance (pin turns); -X prong: press fit (pin is gripped);
        # head sits in a counterbore below the curved surface of the +X prong.
        mm = p["mm"]
        rp = min(p["pin"] * R, 0.45 * R, max(RL - c - min_wall, g))
        rh = min(rp + max(0.6 * mm, 0.3 * rp), 0.8 * R)                 # head radius
        hh = max(1.0 * mm, 0.4 * rp)                                    # head height
        rcb = rh + p["head_tol"] * mm / 2                               # counterbore radius
        x_f = math.sqrt(max(R * R - rcb * rcb, 0.0)) - hh - 0.1 * mm    # counterbore floor
        if x_f < hw + g + min_wall:
            warn.append("prong too thin behind the pin head: smaller pin or narrower tongue")
        x_end = -(math.sqrt(R * R - rp * rp) - 0.2 * mm)                # pin tip, just inside
        rpress = rp + p["press"] * mm / 2
        add_cone(cut.new(), rp + c, rp + c, (-(hw + g * 0.5), 0, 0), (W, 0, 0), segs, F)       # clearance
        add_cone(cut.new(), rpress, rpress, (-W, 0, 0), (-(hw + g * 0.25), 0, 0), segs, F)    # press fit
        add_cone(cut.new(), rcb, rcb, (x_f, 0, 0), (W, 0, 0), segs, F)                         # counterbore
        # the pin itself: one solid of revolution about the hinge axis (X)
        tip = min(0.3 * mm, rp * 0.2)
        prof = [(0.0, x_end), (rp - tip, x_end), (rp, x_end + tip), (rp, x_f),
                (rh, x_f), (rh, x_f + hh), (0.0, x_f + hh)]
        bm = bmesh.new()
        add_revolve(bm, prof, segs, F @ Matrix.Rotation(math.pi / 2, 4, 'Y'))
        p["parts"].append(bm)
        info.append(f"separate pin: \u00d8{2 * rp / mm:.2f} \u00d7 {(x_f + hh - x_end) / mm:.1f} mm, "
                    f"head \u00d8{2 * rh / mm:.2f} \u00d7 {hh / mm:.1f} mm")
    else:
        rp = min(p["pin"] * R, R - g - c - min_wall, max(RL - c - min_wall, g))
        add_cone(pin, rp, rp, (-(hw + 2 * g), 0, 0), (hw + 2 * g, 0, 0), segs, F)       # male rod
        add_cone(cut.new(), rp + c, rp + c, (-(hw + eps), 0, 0), (hw + eps, 0, 0), segs, F)   # clearance bore
        info.append(f"rod pin: Ø{2 * rp / p['mm']:.2f} mm")

    info.append(f"tongue {tw / p['mm']:.2f} mm, prongs {(R - hw - g) / p['mm']:.2f} mm")
    lim = short_link_range(RL, g, p["R_out"])
    p["_hinge_lim"] = lim
    add_art(p, F, 0.0, 'hinge', lim)
    return info, warn


def build_hinge(p, F):
    cut, pin = Pieces(), bmesh.new()
    info, warn = hinge_into(p, F, cut, pin)
    info.append("range of motion ±90°")
    return cut, pin, info, warn
