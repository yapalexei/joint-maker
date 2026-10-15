"""bmesh building blocks. Everything is authored in a joint's local frame and mapped by a
matrix F (Z = part axis, X = hinge axis, origin = joint centre)."""

import bmesh
import math
from mathutils import Matrix, Vector


class Pieces(list):
    """the cutter is kept as separate closed pieces (one object each); the Manifold boolean
    unions them robustly, which a single self-overlapping mesh can't guarantee"""
    def new(self):
        bm = bmesh.new()
        self.append(bm)
        return bm


def orient_outward(bm, faces):
    """make a closed set of faces point outward (positive signed volume)"""
    vol = 0.0
    for f in faces:
        v = [x.co for x in f.verts]
        for i in range(1, len(v) - 1):
            vol += v[0].dot(v[i].cross(v[i + 1]))
    if vol < 0:
        bmesh.ops.reverse_faces(bm, faces=faces)


def add_prism(bm, profile, x0, x1, F):
    """extrude a simple 2D polygon given in (y, z) along joint-frame X from x0 to x1"""
    a = [bm.verts.new(F @ Vector((x0, y, z))) for y, z in profile]
    b = [bm.verts.new(F @ Vector((x1, y, z))) for y, z in profile]
    n = len(profile)
    faces = [bm.faces.new(a[::-1]), bm.faces.new(b)]
    for i in range(n):
        j = (i + 1) % n
        faces.append(bm.faces.new((a[i], a[j], b[j], b[i])))
    orient_outward(bm, faces)


def add_box(bm, x0, x1, y0, y1, z0, z1, F):
    add_prism(bm, [(y0, z0), (y1, z0), (y1, z1), (y0, z1)], x0, x1, F)


def add_cone(bm, r0, r1, p0, p1, segs, F):
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix().to_4x4()
    M = F @ Matrix.Translation((p0 + p1) / 2) @ rot
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segs,
                          radius1=r0, radius2=r1, depth=d.length, matrix=M)


def lobe_profile(R, W, top, segs, upper=True):
    """region |y|<W, 0<z<top (or -top<z<0), outside the circle of radius R around the X axis"""
    s = 1 if upper else -1
    n = max(8, segs // 2)
    arc = [(R * math.cos(math.pi * (1 - i / n)), s * R * math.sin(math.pi * (1 - i / n)))
           for i in range(n + 1)]                       # (-R,0) .. over the top/bottom .. (R,0)
    pts = [(-W, 0.0)] + arc + [(W, 0.0), (W, s * top), (-W, s * top)]
    if not upper:
        pts.reverse()
    return pts


def add_revolve(bm, prof, segs, F):
    """solid of revolution about joint-frame Z. prof = closed loop of (r, z); points with
    r == 0 lie on the axis and become poles"""
    rings = []
    for r, z in prof:
        if r < 1e-9:
            rings.append([bm.verts.new(F @ Vector((0, 0, z)))])
        else:
            rings.append([bm.verts.new(F @ Vector((r * math.cos(2 * math.pi * k / segs),
                                                   r * math.sin(2 * math.pi * k / segs), z)))
                          for k in range(segs)])
    faces = []
    n = len(rings)
    for i in range(n):
        a, b = rings[i], rings[(i + 1) % n]
        if len(a) == 1 and len(b) == 1:
            continue
        for k in range(segs):
            k1 = (k + 1) % segs
            if len(a) == 1:
                faces.append(bm.faces.new((a[0], b[k], b[k1])))
            elif len(b) == 1:
                faces.append(bm.faces.new((a[k1], a[k], b[0])))
            else:
                faces.append(bm.faces.new((a[k], b[k], b[k1], a[k1])))
    vol = 0.0
    for f in faces:
        v = [x.co for x in f.verts]
        for i in range(1, len(v) - 1):
            vol += v[0].dot(v[i].cross(v[i + 1]))
    if vol < 0:
        bmesh.ops.reverse_faces(bm, faces=faces)


def add_sphere(bm, c, r, segs, F):
    # poles on joint-frame Y so they never sit on the Z (stem) axis
    M = F @ Matrix.Translation(c) @ Matrix.Rotation(math.pi / 2, 4, 'X')
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=max(8, segs // 2), radius=r, matrix=M)


def arc(R, zc, a0, a1, n, down=False):
    """points (r, z) on a circle of radius R centred on the axis at zc; angle from the +Z
    (or -Z if down) axis, from a0 to a1 (radians)"""
    s = -1 if down else 1
    return [(R * math.sin(a0 + (a1 - a0) * i / n), zc + s * R * math.cos(a0 + (a1 - a0) * i / n))
            for i in range(n + 1)]


def merge_bm(dst, src):
    """append all of src's geometry to dst (src is freed)"""
    vmap = {v: dst.verts.new(v.co) for v in src.verts}
    for f in src.faces:
        try:
            nf = dst.faces.new([vmap[v] for v in f.verts])
            nf.material_index = f.material_index
        except ValueError:
            pass                                     # duplicate face
    src.free()


def linked_shells(bm):
    faces, groups = set(bm.faces), []
    while faces:
        f = faces.pop(); grp = [f]; stack = [f]
        while stack:
            x = stack.pop()
            for e in x.edges:
                for o in e.link_faces:
                    if o in faces:
                        faces.remove(o); grp.append(o); stack.append(o)
        groups.append(grp)
    return groups
