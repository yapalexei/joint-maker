"""Shape cutter: a ready-made cutout shape (bundled STL presets or any mesh object)."""

import bpy
import bmesh
import math
import os
from mathutils import Matrix, Vector
from ..geometry.mesh import Pieces
from ..geometry.repair import bad_edges, repair_mesh
from ..geometry.stl import read_stl
from .common import add_art


# bundled shapes live next to the package root: joint_maker/shapes/
SHAPE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shapes")


SHAPE_PRESETS = {
    # id: (label, file, the shape's symmetry axis in the file, description)
    'HOOK': ("Hook & loop", "hook_loop.stl", 'X',
             "Two interlocked loops at 90 deg, like chain links: bends on two axes"),
    'CONE': ("Cone socket", "cone_socket.stl", 'Z',
             "Cone peg with a captured cross-bar head in a matching socket"),
}


# smallest clearance between the two parts as a fraction of the shape's diameter
# (measured on the cut result; the gap scales with the shape)
SHAPE_GAP = {'HOOK': 0.367 / 19.6, 'CONE': 0.322 / 19.6}


_SHAPE_CACHE = {}


def _normalised(bm, axis):
    """symmetry axis -> Z, bbox centre -> origin, diameter across the axis -> 1"""
    rot = {'Z': Matrix(), 'X': Matrix.Rotation(math.radians(-90), 4, 'Y'),
           'Y': Matrix.Rotation(math.radians(90), 4, 'X')}[axis]
    bmesh.ops.transform(bm, matrix=rot, verts=bm.verts)
    lo = Vector([min(v.co[i] for v in bm.verts) for i in range(3)])
    hi = Vector([max(v.co[i] for v in bm.verts) for i in range(3)])
    dia = max(hi.x - lo.x, hi.y - lo.y)
    M = Matrix.Scale(1.0 / dia, 4) @ Matrix.Translation(-(lo + hi) / 2)
    bmesh.ops.transform(bm, matrix=M, verts=bm.verts)
    return dia, (hi.z - lo.z) / dia


def load_shape(js):
    """the chosen cutout shape, normalised: (verts, faces, file diameter, height ratio, bad edges,
    label). STL presets are repaired once (stray flaps, holes) and cached."""
    if js.shape_preset == 'CUSTOM':
        src = js.shape_object
        if src is None or src.type != 'MESH' or not len(src.data.polygons):
            return None
        bm = bmesh.new(); bm.from_mesh(src.data)
        axis, label = js.shape_axis, src.name
        key = None
    else:
        label, fname, axis, _ = SHAPE_PRESETS[js.shape_preset]
        path = os.path.join(SHAPE_DIR, fname)
        if not os.path.exists(path):
            return None
        key = (path, os.path.getmtime(path))
        if key in _SHAPE_CACHE:
            return _SHAPE_CACHE[key]
        bm = bmesh.new(); idx = {}
        for tri in read_stl(path):
            vs = []
            for c in tri:
                k = tuple(round(x, 7) for x in c)
                if k not in idx:
                    idx[k] = bm.verts.new(c)
                vs.append(idx[k])
            if len(set(vs)) == 3:
                try:
                    bm.faces.new(vs)
                except ValueError:
                    pass                                     # duplicate triangle
    me = bpy.data.meshes.new("_jm_shape"); bm.to_mesh(me); bm.free()
    repair_mesh(me)
    bm = bmesh.new(); bm.from_mesh(me); bpy.data.meshes.remove(me)
    bad = bad_edges(bm)
    dia, hr = _normalised(bm, axis)
    out = ([v.co.copy() for v in bm.verts], [[v.index for v in f.verts] for f in bm.faces], dia, hr, bad, label)
    bm.free()
    if key is not None:
        _SHAPE_CACHE[key] = out
    return out


def build_shape(p, F):
    """the cutout shape itself is the cutter: centred on the joint, its axis along the part"""
    cut, pin = Pieces(), bmesh.new()
    info, warn = [], []
    shp = load_shape(p["js"])
    if shp is None:
        warn.append("no shape: pick a mesh object (Custom) or reinstall the add-on's shapes")
        return cut, pin, info, warn
    verts, faces, file_dia, hr, bad, label = shp
    js, mm = p["js"], p["mm"]
    if js.shape_size_mode == 'FIT':
        dia = 2 * p["R"] * js.shape_fit
    else:
        dia = js.shape_dia * mm
    h = dia * hr * js.shape_height
    M = F @ Matrix.Diagonal((dia, dia, dia * js.shape_height, 1.0))
    bm = cut.new()
    vmap = [bm.verts.new(M @ v) for v in verts]
    for f in faces:
        try:
            bm.faces.new([vmap[i] for i in f])
        except ValueError:
            pass
    if bad:
        p["force_exact"] = True
        warn.append(f"shape isn't watertight ({bad} bad edges): using the Exact solver")
    if dia < 2 * p["R"] * 0.999:
        warn.append("shape is narrower than the part here: it may not split it")
    add_art(p, F, 0.0, 'ball', js.shape_limit)
    info.append(f"shape '{label}': \u00d8{dia / mm:.1f} \u00d7 {h / mm:.1f} mm "
                f"({dia / max(file_dia, 1e-12):.3g}\u00d7 the file)")
    if js.shape_preset in SHAPE_GAP:
        gap = SHAPE_GAP[js.shape_preset] * dia * min(1.0, js.shape_height) / mm
        info.append(f"clearance \u2248 {gap:.2f} mm (scales with the shape)")
        if gap < 0.2:
            warn.append(f"clearance only \u2248{gap:.2f} mm: may fuse when printed, make the shape bigger")
    else:
        info.append("clearances scale with the shape: check them at this size")
    return cut, pin, info, warn
