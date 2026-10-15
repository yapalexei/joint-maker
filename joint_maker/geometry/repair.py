"""Watertight checks, mesh repair and choosing the boolean solver."""

import bmesh


def bad_edges(bm):
    return sum(1 for e in bm.edges if not e.is_manifold or not e.is_contiguous)


def repair_mesh(me, max_flap=50, max_hole=32):
    """
    Make a mesh watertight where possible, without remeshing:
      1. merge duplicate vertices
      2. detach small stray flaps: split along edges shared by 3+ faces, delete the small
         pieces that fall off (<= max_flap faces, typical sculpt/remesh leftovers), re-weld
      3. delete interior faces (all edges shared by 3+ faces)
      4. drop loose edges/vertices
      5. weld near-duplicate open vertices and fill small holes, make normals consistent
    Returns (bad edges before, after, flaps removed).
    """
    bm = bmesh.new(); bm.from_mesh(me)
    before = bad_edges(bm)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    flaps = 0
    multi = [e for e in bm.edges if len(e.link_faces) > 2]
    if multi:
        bmesh.ops.split_edges(bm, edges=multi)
        faces, small = set(bm.faces), []
        while faces:
            f = faces.pop(); grp = [f]; st = [f]
            while st:
                x = st.pop()
                for e in x.edges:
                    for o in e.link_faces:
                        if o in faces:
                            faces.remove(o); grp.append(o); st.append(o)
            if len(grp) <= max_flap and len(grp) < len(bm.faces) * 0.01:
                small += grp; flaps += 1
        if small:
            bmesh.ops.delete(bm, geom=small, context='FACES')
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)          # re-weld the seams
    for _ in range(3):
        interior = [f for f in bm.faces if all(len(e.link_faces) > 2 for e in f.edges)]
        if not interior:
            break
        bmesh.ops.delete(bm, geom=interior, context='FACES_ONLY')
    loose_e = [e for e in bm.edges if not e.link_faces]
    if loose_e:
        bmesh.ops.delete(bm, geom=loose_e, context='EDGES')
    loose_v = [v for v in bm.verts if not v.link_edges]
    if loose_v:
        bmesh.ops.delete(bm, geom=loose_v, context='VERTS')
    # 5. weld near-duplicates on open edges, then close the small holes left behind
    #    (only openings with up to `max_hole` sides; big openings are left for you to judge)
    open_v = list({v for e in bm.edges if e.is_boundary for v in e.verts})
    if open_v:
        avg = sum(e.calc_length() for e in bm.edges) / max(1, len(bm.edges))
        bmesh.ops.remove_doubles(bm, verts=open_v, dist=avg * 1e-3)
        bnd = [e for e in bm.edges if e.is_boundary]
        if bnd:
            bmesh.ops.holes_fill(bm, edges=bnd, sides=max_hole)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    after = bad_edges(bm)
    bm.to_mesh(me); bm.free(); me.update()
    return before, after, flaps


MANIFOLD_CACHE = {}


def mesh_problems(obj):
    """count edges the Manifold solver rejects (not exactly two faces, or flipped neighbours).
    Cached per mesh state so live sliders stay fast."""
    me = obj.data
    key = (me.as_pointer(), len(me.vertices), len(me.edges), len(me.polygons))
    if key not in MANIFOLD_CACHE:
        bm = bmesh.new(); bm.from_mesh(me)
        bad = sum(1 for e in bm.edges if not e.is_manifold or not e.is_contiguous)
        bm.free()
        if len(MANIFOLD_CACHE) > 64:
            MANIFOLD_CACHE.clear()
        MANIFOLD_CACHE[key] = bad
    return MANIFOLD_CACHE[key]


def target_solver(obj, js, warn=None):
    """Manifold (fast, robust) needs a watertight mesh; otherwise fall back to Exact"""
    if js.solver_mode != 'AUTO':
        return js.solver_mode
    bad = mesh_problems(obj)
    if bad:
        if warn is not None:
            slow = " (big mesh: turn Live off while adjusting)" if len(obj.data.polygons) > 20000 else ""
            warn.append(f"mesh isn't watertight ({bad} bad edges): using the slower Exact solver{slow}. "
                        "Repair Mesh fixes this for faster updates")
        return 'EXACT'
    return 'MANIFOLD'


def set_solver(md, solver):
    md.solver = solver
    if solver == 'EXACT':
        md.use_hole_tolerant = True
        md.use_self = False
