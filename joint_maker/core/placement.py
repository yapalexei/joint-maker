"""Where the joints of an array go: along the part, or along a placement curve."""

import bpy
from mathutils import Matrix, Vector
from .frame import joint_turn
from ..geometry.sections import section_info


def joint_layout(obj, js, H, mm):
    """(position fraction, extra rotation) for every joint of the array"""
    n = js.array_count
    if n <= 1:
        return [(js.position, 0.0)], []
    warn = []
    if js.array_mode == 'FIT':
        fr = [(i + 1) / (n + 1) for i in range(n)]                  # equal-length parts
    else:
        step = js.array_spacing * mm / H
        fr = [js.position + (i - (n - 1) / 2) * step for i in range(n)]
        if fr[0] < 0 or fr[-1] > 1:
            warn.append("array runs past the cylinder ends")
    return [(f, i * js.array_twist) for i, f in enumerate(fr)], warn


# ----------------------------------------------------------------------
# posing a rigid chain along a curve
# ----------------------------------------------------------------------
def curve_polyline(curve_obj):
    """world-space points along the (first) spline of a curve object, in order"""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = curve_obj.evaluated_get(dg)
    me = ev.to_mesh()
    try:
        pts = [curve_obj.matrix_world @ v.co for v in me.vertices]
        adj = {i: [] for i in range(len(pts))}
        for e in me.edges:
            a, b = e.vertices
            adj[a].append(b); adj[b].append(a)
    finally:
        ev.to_mesh_clear()
    if len(pts) < 2:
        return None
    start = next((i for i in adj if len(adj[i]) == 1), 0)
    order, prev, cur = [start], None, start
    while True:
        nxt = [j for j in adj[cur] if j != prev and j not in order[-2:]]
        if not nxt or nxt[0] == start:
            break
        prev, cur = cur, nxt[0]
        order.append(cur)
    out = [pts[i] for i in order]
    return out if len(out) >= 2 else None


class Polyline:
    def __init__(self, pts):
        self.p = pts
        self.s = [0.0]
        for a, b in zip(pts, pts[1:]):
            self.s.append(self.s[-1] + (b - a).length)
        self.length = self.s[-1]

    def at(self, s):
        """point at arc length s (extrapolates straight past either end)"""
        p, S = self.p, self.s
        if s <= 0:
            return p[0] + (p[1] - p[0]).normalized() * s
        if s >= self.length:
            return p[-1] + (p[-1] - p[-2]).normalized() * (s - self.length)
        lo, hi = 0, len(S) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if S[mid] <= s:
                lo = mid
            else:
                hi = mid
        t = (s - S[lo]) / max(S[hi] - S[lo], 1e-12)
        return p[lo].lerp(p[hi], t)

    def tangent(self, s):
        e = max(self.length * 1e-3, 1e-6)
        return (self.at(s + e) - self.at(s - e)).normalized()

    def plane_normal(self):
        o, n = self.p[0], Vector()
        for a, b in zip(self.p[1:], self.p[2:]):
            n += (a - o).cross(b - o)
        return n.normalized() if n.length > 1e-9 else None


def curve_frames(obj, js, mm):
    """
    Joint frames along the placement curve (object-local): each joint sits on the curve with
    its axis along the curve's direction. The hinge axis is carried along the curve without
    twisting (and starts square to the curve's plane, so flat curves bend in that plane).
    With snapping, each joint moves onto the centre of the shape's cross-section there.
    Returns (frames, arc positions, warnings) or None.
    """
    pts_w = curve_polyline(js.place_curve)
    if not pts_w:
        return None
    Minv = obj.matrix_world.inverted()
    pts = [Minv @ q for q in pts_w]
    poly = Polyline(pts)
    L = poly.length
    if L <= 1e-12:
        return None
    a, b = sorted((js.curve_start, js.curve_end))
    s0, s1 = L * a, L * b
    n, warn = js.array_count, []
    if n <= 1:
        ss = [s0 + (s1 - s0) * js.position]
    elif js.array_mode == 'FIT':
        ss = [s0 + (s1 - s0) * (i + 1) / (n + 1) for i in range(n)]
    else:
        step = js.array_spacing * mm
        mid = s0 + (s1 - s0) * js.position
        ss = [mid + (i - (n - 1) / 2) * step for i in range(n)]
        if ss[0] < s0 - 1e-9 or ss[-1] > s1 + 1e-9:
            warn.append("joints run past the ends of the curve section")
    # carry a cross axis along the polyline without twist (parallel transport)
    T0 = (pts[1] - pts[0]).normalized()
    N = poly.plane_normal()
    X = (N - T0 * N.dot(T0)) if N is not None else T0.orthogonal()
    X = X.normalized() if X.length > 1e-9 else T0.orthogonal().normalized()
    xs, prevT = [X], T0
    for k in range(1, len(pts)):
        Tk = (pts[min(k + 1, len(pts) - 1)] - pts[k - 1]).normalized()
        X = prevT.rotation_difference(Tk) @ X
        X = (X - Tk * X.dot(Tk)).normalized()
        xs.append(X); prevT = Tk
    frames = []
    for i, sv in enumerate(ss):
        P = poly.at(sv)
        T = poly.tangent(sv)
        k = max(0, min(len(poly.s) - 1, next((j for j, sj in enumerate(poly.s) if sj > sv), len(poly.s)) - 1))
        X = xs[k] - T * xs[k].dot(T)
        X = X.normalized() if X.length > 1e-9 else T.orthogonal().normalized()
        if js.curve_snap:
            sec = section_info(obj, P, T)
            if sec is not None:
                P = sec[0]
        Y = T.cross(X)
        B = Matrix((X, Y, T)).transposed().to_4x4()
        frames.append(Matrix.Translation(P) @ B @ joint_turn(js, i * js.array_twist))
    return frames, ss, warn
