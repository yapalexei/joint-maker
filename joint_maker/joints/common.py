"""Helpers shared by the joint builders."""

import math
from mathutils import Vector


def add_art(p, F, z, kind, limit):
    """record a pivot (in the cylinder's local space) so a chain can be posed along a path"""
    p["arts"].append(dict(pt=F @ Vector((0, 0, z)), axis=(F.to_3x3() @ Vector((1, 0, 0))).normalized(),
                          kind=kind, limit=limit))


def cut_reach(p):
    """how far the cutters reach across the joint: past the part's wall, plus extra when the
    joint is tilted against the part (its cross-section is then a stretched oval)"""
    return p["R_out"] * 1.25 + p["gap"] * 4 + p.get("reach_extra", 0.0)


def short_link_range(r_lobe, g, r_body):
    """bend range (deg) of a pivot whose round ends have radius r_lobe: the full-width body
    (radius r_body) swinging round may only come within `g` of the other part's round end"""
    if r_lobe >= r_body - 1e-9:
        return 85.0
    return min(85.0, math.degrees(math.asin(min(1.0, (r_lobe + g) / max(r_body, 1e-9)))))
