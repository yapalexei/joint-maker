"""Slicing a mesh with a plane: outlines, point-in-polygon and the outline around a joint."""

import bmesh
import math


def section_loops(edges):
    """group cut edges into chains of vertices (ordered when they form loops)"""
    adj = {}
    for e in edges:
        a, b = e.verts
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    seen, loops = set(), []
    for start in adj:
        if start in seen:
            continue
        chain, prev, cur = [start], None, start
        seen.add(start)
        while True:
            nxt = [w for w in adj[cur] if w is not prev and w not in seen]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
            seen.add(cur)
            chain.append(cur)
        loops.append(chain)
    return loops


def section_info(obj, plane_pt, a_hat):
    """
    Slice the object's mesh through plane_pt (normal a_hat, local space) and look at the outline
    around the joint axis there: the loop that surrounds the axis point, or the nearest one.
    Returns (area centroid, farthest distance from the axis) or None. Other parts of the
    mesh that the slice also hits are ignored.
    """
    u = a_hat.orthogonal().normalized()
    w = a_hat.cross(u)
    bm = bmesh.new(); bm.from_mesh(obj.data)
    try:
        res = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                                     plane_co=plane_pt, plane_no=a_hat)
        edges = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
        best, best_d = None, None
        for loop in section_loops(edges):
            poly = [((v.co - plane_pt).dot(u), (v.co - plane_pt).dot(w)) for v in loop]
            if len(poly) < 3:
                continue
            d = 0.0 if point_in_polygon((0.0, 0.0), poly) else min(math.hypot(x, y) for x, y in poly)
            if best_d is None or d < best_d:
                best, best_d = poly, d
    finally:
        bm.free()
    if best is None:
        return None
    a2 = cx = cy = 0.0                                   # shoelace area centroid
    for (x1, y1), (x2, y2) in zip(best, best[1:] + best[:1]):
        cr = x1 * y2 - x2 * y1
        a2 += cr; cx += (x1 + x2) * cr; cy += (y1 + y2) * cr
    if abs(a2) < 1e-12:
        cx = sum(x for x, _ in best) / len(best); cy = sum(y for _, y in best) / len(best)
    else:
        cx /= 3 * a2; cy /= 3 * a2
    reach = max(math.hypot(x, y) for x, y in best)
    return plane_pt + u * cx + w * cy, reach


def point_in_polygon(pt2, poly2):
    """2D point-in-polygon (even-odd)"""
    x, y = pt2
    inside = False
    for (x1, y1), (x2, y2) in zip(poly2, poly2[1:] + poly2[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside
