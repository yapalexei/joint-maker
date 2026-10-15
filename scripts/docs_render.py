"""Renders the individual snapshots ("cells") used by the documentation, one PNG per cell, by
building every scene with the add-on itself in a background Blender.

    blender -b --factory-startup --python scripts/docs_render.py -- <repo root> <output dir> [cell ids...]

Normally you run scripts/make_docs_figures.py, which calls this and then stacks the cells into
the numbered figures. Every cell is rendered at SS times its final size; the figure script
shrinks it back down for clean edges.
"""
import importlib
import math
import os
import re
import sys
import traceback

import bmesh
import bpy
from mathutils import Matrix, Vector

args = sys.argv[sys.argv.index("--") + 1:]
ROOT, OUT = args[0], args[1]
ONLY = set(args[2:])
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, ROOT)
jm = importlib.import_module("joint_maker")
jm.register()
from joint_maker.constants import PIN_COLOUR, SECTION_COLOURS   # noqa: E402
from joint_maker.core import frame, helpers, rebuild as rb, state   # noqa: E402
from joint_maker.core.frame import center_on_shape          # noqa: E402
from joint_maker.geometry import mesh as gmesh              # noqa: E402
from joint_maker.geometry.repair import bad_edges, repair_mesh    # noqa: E402

SS = 2                                    # supersampling factor
PIN_RGB = PIN_COLOUR
GREY_RGB = (0.62, 0.66, 0.72)
RED_RGB = (0.90, 0.10, 0.10)

# ----------------------------------------------------------------------------- scene setup
sc = bpy.context.scene
sc.render.engine = 'BLENDER_WORKBENCH'
sd = sc.display.shading
sd.light = 'STUDIO'
sd.color_type = 'MATERIAL'
sd.show_cavity = True
sd.show_object_outline = True
sd.object_outline_color = (0.08, 0.09, 0.12)
sc.display.render_aa = '8'
sc.render.film_transparent = False
try:
    sc.view_settings.view_transform = 'Standard'
except TypeError:
    pass
world = bpy.data.worlds.new("docs")
world.color = (0.95, 0.96, 0.98)
sc.world = world

_MATS = {}


def mat(key):
    """material for a part index (palette) or an (r, g, b) tuple"""
    if key not in _MATS:
        rgb = SECTION_COLOURS[key % len(SECTION_COLOURS)] if isinstance(key, int) else key
        m = bpy.data.materials.new(f"doc{len(_MATS)}")
        m.diffuse_color = (*rgb, 1.0)
        _MATS[key] = m
    return _MATS[key]


def fresh():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    for me in list(bpy.data.meshes):
        if me.users == 0:
            bpy.data.meshes.remove(me)
    for cu in list(bpy.data.curves):
        if cu.users == 0:
            bpy.data.curves.remove(cu)


def camera(loc, target, scale, up=Vector((0, 0, 1))):
    cd = bpy.data.cameras.new("c")
    cd.type = 'ORTHO'
    cd.ortho_scale = scale
    cd.clip_start, cd.clip_end = 0.1, 3000
    co = bpy.data.objects.new("cam", cd)
    sc.collection.objects.link(co)
    sc.camera = co
    fwd = (target - loc).normalized()
    if abs(fwd.dot(up)) > 0.98:
        up = Vector((0, 1, 0))
    right = fwd.cross(up).normalized()
    upv = right.cross(fwd).normalized()
    co.matrix_world = Matrix(((right.x, upv.x, -fwd.x, loc.x),
                              (right.y, upv.y, -fwd.y, loc.y),
                              (right.z, upv.z, -fwd.z, loc.z),
                              (0, 0, 0, 1)))


def direction(az, el):
    """unit vector from the subject towards the camera (az 0 = from the front, -Y)"""
    a, e = math.radians(az), math.radians(el)
    return Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))


def render(name, w, h):
    sc.render.resolution_x, sc.render.resolution_y = w * SS, h * SS
    sc.render.resolution_percentage = 100
    sc.render.filepath = os.path.join(OUT, name + ".png")
    bpy.ops.render.render(write_still=True)


# ----------------------------------------------------------------------------- scene helpers
def part(length=70.0, radius=10.0, horizontal=False, segs=96):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=length, vertices=segs)
    ob = bpy.context.active_object
    ob.name = "Part"
    if horizontal:
        ob.rotation_euler = (0, math.radians(90), 0)
    bpy.context.view_layer.update()
    return ob


def build(jtype, props=None, maker=None, **part_kw):
    fresh()
    ob = maker() if maker else part(**part_kw)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    with bpy.context.temp_override(active_object=ob, object=ob):
        bpy.ops.joint_maker.add()
    js = ob.joint_maker
    js.live = False
    js.mm_per_unit = 1.0
    js.joint_type = jtype
    for k, v in (props or {}).items():
        setattr(js, k, v() if callable(v) else v)
    rb.rebuild(ob)
    return ob, js


def world_frame(ob, i=0):
    return state.LAST_FRAMES[ob.as_pointer()][i]


def world_shells(ob):
    """the evaluated result as one bmesh per loose piece, in world space"""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    src = bmesh.new()
    src.from_mesh(ev.to_mesh())
    ev.to_mesh_clear()
    src.transform(ob.matrix_world)
    src.faces.index_update()
    out = []
    for grp in gmesh.linked_shells(src):
        keep = {f.index for f in grp}
        p = src.copy()
        p.faces.ensure_lookup_table()
        drop = [f for f in p.faces if f.index not in keep]
        if drop:
            bmesh.ops.delete(p, geom=drop, context='FACES')
        loose = [v for v in p.verts if not v.link_faces]
        if loose:
            bmesh.ops.delete(p, geom=loose, context='VERTS')
        out.append(p)
    src.free()
    return out


def centroid(bm):
    return sum((v.co for v in bm.verts), Vector()) / max(1, len(bm.verts))


def show(bms, colours, offsets=None):
    for i, bm in enumerate(bms):
        me = bpy.data.meshes.new(f"s{i}")
        bm.to_mesh(me)
        bm.free()
        me.materials.append(mat(colours[i]))
        o = bpy.data.objects.new(f"s{i}", me)
        sc.collection.objects.link(o)
        if offsets and offsets.get(i) is not None:
            o.location = offsets[i]


def cap_normal(ob, js):
    """world direction the cut face of the section preview looks towards"""
    F = world_frame(ob, max(0, js.section_joint - 1))
    rot = F.to_3x3().normalized()
    n = (rot @ (Matrix.Rotation(math.radians(js.section_angle), 3, 'Z')
                @ Matrix.Rotation(math.radians(js.section_tilt), 3, 'X') @ Vector((0, 1, 0)))).normalized()
    return -n if js.section_flip else n


def joint_cell(view, jtype, props=None, maker=None, part_kw=None, scale=46.0, explode=0.0, pin_out=0.0,
               sec=None, az=-35.0, el=18.0, centre=None, cen_off=None, only=None, post=None,
               cutter=False, sec_view=0.0, pose=False, cap_only=False, grey_far=0.0):
    """a cell that shows a joint. view: 'ext' (parts coloured), 'sec' (cross-section preview) or
    'below' (the top part seen from underneath)"""
    def fn(w, h):
        ob, js = build(jtype, props, maker, **(part_kw or {}))
        if post:
            post(ob, js)
            rb.rebuild(ob)
        F = world_frame(ob)
        jc = F.translation.copy()
        tgt = Vector(centre) if centre is not None else jc.copy()
        if cen_off is not None:
            tgt = tgt + Vector(cen_off)
        axis = (F.to_3x3() @ Vector((0, 0, 1))).normalized()
        hinge_axis = (F.to_3x3() @ Vector((1, 0, 0))).normalized()
        if view == 'sec':
            for k, v in (sec or {}).items():
                setattr(js, "section_" + k, v)
            js.section_show = True
            n = cap_normal(ob, js)
            bpy.data.objects[ob.name + "_Section"].hide_render = False
            ob.hide_render = True
            for po in helpers.part_objects(ob):            # whole pins would sit in front of the cut
                po.hide_render = True
            if cap_only:                                   # keep only the flat cut face (a plan view)
                bpy.context.view_layer.update()
                so = bpy.data.objects[ob.name + "_Section"]
                M = ob.matrix_world
                nn = cap_normal(ob, js)
                b2 = bmesh.new()
                b2.from_mesh(so.data)
                pd = max((M @ v.co).dot(nn) for v in b2.verts)
                drop = [f for f in b2.faces if any(abs((M @ v.co).dot(nn) - pd) > 1e-3 for v in f.verts)]
                bmesh.ops.delete(b2, geom=drop, context='FACES')
                b2.to_mesh(so.data)
                b2.free()
            d = n
            if sec_view:                                   # a three-quarter look at the half model
                d = Matrix.Rotation(math.radians(sec_view), 3, Vector((0, 0, 1))) @ d
                ax = d.cross(Vector((0, 0, 1)))
                ax = ax.normalized() if ax.length > 1e-3 else Vector((1, 0, 0))
                d = Matrix.Rotation(math.radians(22), 3, ax) @ d
            camera(tgt + d * 300, tgt, scale)
        else:
            shells = world_shells(ob)
            far = set()
            if grey_far:                                   # pieces away from the joint axis (neighbours)
                for i, bm in enumerate(shells):
                    rel = centroid(bm) - jc
                    if (rel - axis * rel.dot(axis)).length > grey_far:
                        far.add(i)
            order = sorted((i for i in range(len(shells)) if i not in far), key=lambda i: centroid(shells[i]).dot(axis))
            rank = {i: r for r, i in enumerate(order)}
            if pose:                                       # tilt the upper part about the hinge axis
                m = re.search(r"swing ±(\d+)", js.info)
                deg = min(40.0, max(5.0, (int(m.group(1)) if m else 20) - 1.0))
                side_axis = (F.to_3x3() @ Vector((0, 1, 0))).normalized()    # tilt sideways, across the image
                M = (Matrix.Translation(jc) @ Matrix.Rotation(math.radians(deg), 4, side_axis)
                     @ Matrix.Translation(-jc))
                for i, bm in enumerate(shells):
                    if rank[i] >= 1:
                        bm.transform(M)
            keep = None
            if only is not None:
                keep = {order[k] for k in only}
            offsets, colours, bms = {}, [], []
            for i in range(len(shells)):
                if keep is not None and i not in keep:
                    shells[i].free()
                    continue
                offsets[len(bms)] = (axis * (rank[i] - (len(order) - 1) / 2) * explode
                                     if explode and i not in far else None)
                colours.append(GREY_RGB if i in far else rank[i])
                bms.append(shells[i])
            for po in helpers.part_objects(ob):
                bm = bmesh.new()
                bm.from_mesh(po.data)
                bm.transform(ob.matrix_world)
                offsets[len(bms)] = hinge_axis * pin_out if pin_out else None
                colours.append(PIN_RGB)
                bms.append(bm)
            show(bms, colours, offsets)
            ob.hide_render = True
            if cutter:                                     # draw the cutter pieces as a wire cage
                for o in bpy.data.objects:
                    if "_Cut" in o.name:
                        o.hide_render = False
                        md = o.modifiers.new("wire", 'WIREFRAME')
                        md.thickness = 0.16
                        o.data.materials.append(mat((0.85, 0.25, 0.25)))
            if view == 'below':
                camera(tgt + Vector((0, 0, -300)), tgt, scale, up=Vector((0, 1, 0)))
            else:
                camera(tgt + direction(az, el) * 300, tgt, scale)
    return fn


# ----------------------------------------------------------------------------- shapes for scenes
def ring_tube(length, radius, rings=10, segs=48, flaps=0):
    bm = bmesh.new()
    rs = []
    for k in range(rings + 1):
        z = -length / 2 + length * k / rings
        rs.append([bm.verts.new((radius * math.cos(2 * math.pi * j / segs), radius * math.sin(2 * math.pi * j / segs), z))
                   for j in range(segs)])
    for k in range(rings):
        for j in range(segs):
            bm.faces.new((rs[k][j], rs[k][(j + 1) % segs], rs[k + 1][(j + 1) % segs], rs[k + 1][j]))
    bm.faces.new(rs[0][::-1])
    bm.faces.new(rs[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def object_from(bm, name="Part"):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    sc.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    return ob


def maker_sheared():
    ob = part()
    for v in ob.data.vertices:
        v.co.x += 0.18 * v.co.z                            # a leaning part: its axis is off the box centre
    ob.data.update()
    return ob


def maker_shoulder():
    body = part(length=70, radius=20)
    bpy.ops.mesh.primitive_cylinder_add(radius=6, depth=50, vertices=64, location=(35, 0, 0),
                                        rotation=(0, math.radians(90), 0))
    arm = bpy.context.active_object
    md = body.modifiers.new("u", 'BOOLEAN')
    md.operation, md.object, md.solver = 'UNION', arm, 'EXACT'
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.modifier_apply(modifier="u")
    bpy.data.objects.remove(arm)
    return body


def maker_block():
    ob = part(length=110, radius=10)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(15.75, 0, 0))
    blk = bpy.context.active_object
    blk.scale = (8.5, 30, 16)
    bpy.context.view_layer.update()
    bpy.ops.object.select_all(action='DESELECT')
    blk.select_set(True)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.join()
    return ob


_TAIL = {}


def maker_tail():
    RA, ARC = 60.0, math.radians(100)

    def centre(t):
        return Vector((RA - RA * math.cos(t * ARC), 0, RA * math.sin(t * ARC)))

    def tangent(t):
        return Vector((math.sin(t * ARC), 0, math.cos(t * ARC)))
    bm = bmesh.new()
    rings = []
    for k in range(61):
        t = k / 60
        c, T = centre(t), tangent(t)
        X = Vector((0, 1, 0))
        Y = T.cross(X)
        rings.append([bm.verts.new(c + (X * math.cos(a) + Y * math.sin(a)) * (10 - 6 * t))
                      for a in [2 * math.pi * j / 48 for j in range(48)]])
    for k in range(60):
        for j in range(48):
            bm.faces.new((rings[k][j], rings[k][(j + 1) % 48], rings[k + 1][(j + 1) % 48], rings[k + 1][j]))
    bm.faces.new(rings[0][::-1])
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = object_from(bm, "Tail")
    cd = bpy.data.curves.new("TailCurve", "CURVE")
    cd.dimensions = '3D'
    sp = cd.splines.new('POLY')
    pts = [centre(i / 80) + Vector((0, 1.5, 0)) for i in range(81)]       # drawn 1.5 mm off-centre
    sp.points.add(len(pts) - 1)
    for pnt, v in zip(sp.points, pts):
        pnt.co = (v.x, v.y, v.z, 1)
    crv = bpy.data.objects.new("TailCurve", cd)
    sc.collection.objects.link(crv)
    crv.hide_render = True
    _TAIL["curve"] = crv
    return ob


def maker_chain():
    ob = part(length=80, radius=8)
    cd = bpy.data.curves.new("PathCurve", "CURVE")
    cd.dimensions = '3D'
    sp = cd.splines.new('POLY')
    pts = [Vector((0, 0, -40)), Vector((0, 0, -25))]
    pts += [Vector((45 - 45 * math.cos(math.radians(a)), 0, -25 + 45 * math.sin(math.radians(a)))) for a in range(4, 101, 4)]
    sp.points.add(len(pts) - 1)
    for pnt, v in zip(sp.points, pts):
        pnt.co = (v.x, v.y, v.z, 1)
    crv = bpy.data.objects.new("PathCurve", cd)
    sc.collection.objects.link(crv)
    crv.hide_render = True
    _TAIL["path"] = crv
    return ob


# ----------------------------------------------------------------------------- cell registry
CELLS = {}


def reg(name, fn, w=340, h=340):
    CELLS[name] = (fn, w, h)


# ---- getting started
def gs_plain(w, h):
    fresh()
    ob = part()
    me = ob.data
    me.materials.append(mat(GREY_RGB))
    camera(Vector((0, 0, 0)) + direction(-35, 18) * 300, Vector((0, 0, 0)), 70)


def gs_cutter(w, h):
    joint_cell('ext', 'HINGE', cutter=True, scale=70, centre=(0, 0, 0))(w, h)


reg("gs_plain", gs_plain)
reg("gs_cutter", gs_cutter)
reg("gs_parts", joint_cell('ext', 'HINGE', scale=70, explode=9, centre=(0, 0, 0)))

# ---- pivot pins
for key, style in (("cone", "CONE"), ("rod", "ROD"), ("pin", "PIN")):
    reg(f"pp_{key}_ext", joint_cell('ext', 'HINGE', {'pin_style': style}, scale=58, pin_out=17 if style == 'PIN' else 0,
                                    centre=(8 if style == 'PIN' else 0, 0, 0), az=-30, el=14))
    reg(f"pp_{key}_sec", joint_cell('sec', 'HINGE', {'pin_style': style}, scale=40))

# ---- ball: swing / snap lip
BALL_ROWS = {"sw20": {'ball_control': 'SWING', 'swing': 20.0}, "sw45": {'ball_control': 'SWING', 'swing': 45.0},
             "lip03": {'ball_control': 'LIP', 'snap_lip': 0.3}, "lip08": {'ball_control': 'LIP', 'snap_lip': 0.8}}
for key, pr in BALL_ROWS.items():
    reg(f"bc_{key}_sec", joint_cell('sec', 'BALL', pr, scale=40))
    reg(f"bc_{key}_pose", joint_cell('ext', 'BALL', pr, scale=54, pose=True, az=0, el=8))

# ---- ball: snap-fit relief slots
for n in range(4):
    pr = {'snap_relief': n > 0, 'slots': max(1, n)}
    reg(f"bs_{n}_below", joint_cell('below', 'BALL', pr, scale=24, only=[-1]))
    reg(f"bs_{n}_side", joint_cell('ext', 'BALL', pr, scale=36, only=[-1], cen_off=(0, 0, 8), az=-30, el=-25))

# ---- double joints
DOUBLE_ROWS = {"pivot": {'link_end': 'PIVOT'}, "ball": {'link_end': 'BALL'},
               "clip": {'link_end': 'CLIP', 'gear_mesh': False}, "gear": {'link_end': 'CLIP', 'gear_mesh': True}}
for key, pr in DOUBLE_ROWS.items():
    clip = pr['link_end'] == 'CLIP'
    reg(f"dj_{key}_ext", joint_cell('ext', 'DOUBLE', pr, part_kw={'length': 100}, scale=72, centre=(0, 0, 0)))
    reg(f"dj_{key}_sec", joint_cell('sec', 'DOUBLE', pr, part_kw={'length': 100}, scale=72, centre=(0, 0, 0),
                                    sec={'angle': 90.0} if clip else None))
for t in (0, 45, 90):
    pr = {'link_end': 'PIVOT', 'pivot_twist': float(t)}
    reg(f"dt_{t}_ext", joint_cell('ext', 'DOUBLE', pr, part_kw={'length': 100}, scale=72, centre=(0, 0, 0)))
    reg(f"dt_{t}_sec", joint_cell('sec', 'DOUBLE', pr, part_kw={'length': 100}, scale=72, centre=(0, 0, 0)))


# ---- shape cutter
def post_custom(ob, js):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=1.0)
    bmesh.ops.scale(bm, vec=(12, 12, 2.2), verts=bm.verts)
    lens = object_from(bm, "Lens")
    lens.hide_render = True
    bpy.context.view_layer.objects.active = ob
    js.shape_preset, js.shape_object, js.shape_axis = 'CUSTOM', lens, 'Z'


for key, pr in (("hook", {'shape_preset': 'HOOK'}), ("cone", {'shape_preset': 'CONE'})):
    reg(f"sh_{key}_ext", joint_cell('ext', 'SHAPE', pr, scale=50, explode=7, centre=(0, 0, 0)))
    reg(f"sh_{key}_sec", joint_cell('sec', 'SHAPE', pr, scale=40))
reg("sh_custom_ext", joint_cell('ext', 'SHAPE', None, scale=50, explode=7, centre=(0, 0, 0), post=post_custom))
reg("sh_custom_sec", joint_cell('sec', 'SHAPE', None, scale=40, post=post_custom))

# ---- placement
for r in (0, 45, 90):
    reg(f"pb_{r}_ext", joint_cell('ext', 'HINGE', {'rotation': float(r)}, scale=46))
    reg(f"pb_{r}_sec", joint_cell('sec', 'HINGE', {'rotation': float(r)}, scale=34, sec={'tilt': 90.0}))
for t in (0, 20, 30):
    reg(f"pt_{t}_ext", joint_cell('ext', 'HINGE', {'tilt_x': float(t)}, scale=46, az=90, el=0))
    reg(f"pt_{t}_3q", joint_cell('ext', 'HINGE', {'tilt_x': float(t)}, scale=46))


def post_centre(ob, js):
    center_on_shape(ob, js)


SHEAR = {'position': 0.5 + 20 / 70}
reg("po_0_sec", joint_cell('sec', 'BALL', SHEAR, maker=maker_sheared, scale=34, sec={'tilt': 90.0}, cap_only=True))
reg("po_0_side", joint_cell('sec', 'BALL', SHEAR, maker=maker_sheared, scale=46, cen_off=(0, 0, 0)))
reg("po_1_sec", joint_cell('sec', 'BALL', SHEAR, maker=maker_sheared, scale=34, sec={'tilt': 90.0}, post=post_centre,
                           cap_only=True))
reg("po_1_side", joint_cell('sec', 'BALL', SHEAR, maker=maker_sheared, scale=46, post=post_centre))

# ---- size and cutting
for s in (100, 70, 50):
    reg(f"sz_{s}_ext", joint_cell('ext', 'HINGE', {'joint_scale': s / 100}, scale=46))
    reg(f"sz_{s}_sec", joint_cell('sec', 'HINGE', {'joint_scale': s / 100}, scale=40))
TAPERS = {"auto": {'waist_taper': 'AUTO'}, "len": {'waist_taper': 'CUSTOM', 'taper_len': 4.0},
          "none": {'waist_taper': 'NONE'}, "nokeep": {'waist_taper': 'NONE', 'keep_range': False}}
for key, pr in TAPERS.items():
    pr = dict(pr, joint_scale=0.6)
    reg(f"tp_{key}_sec", joint_cell('sec', 'HINGE', pr, scale=40))
    reg(f"tp_{key}_ext", joint_cell('ext', 'HINGE', pr, scale=46))
SHOULDER = {'axis': 'X', 'position': 0.55, 'joint_scale': 0.6}
for key, pr in (("off", {}), ("on", {'limit_reach_on': True, 'limit_reach': 1.0, 'limit_bevel': 0.0}),
                ("bev", {'limit_reach_on': True, 'limit_reach': 1.0, 'limit_bevel': 2.0})):
    reg(f"lm_{key}_sec", joint_cell('sec', 'HINGE', dict(SHOULDER, **pr), maker=maker_shoulder, scale=38, centre=(20, 0, 0),
                                    sec={'flip': True}))
    reg(f"lm_{key}_plan", joint_cell('sec', 'HINGE', dict(SHOULDER, **pr), maker=maker_shoulder, scale=38, centre=(20, 0, 0),
                                     sec={'angle': 90.0}, cap_only=True))
FIT_PROPS = {'link_end': 'CLIP', 'gear_mesh': True, 'joint_scale': 0.7, 'fit_margin': 1.0}
for key, fit in (("off", False), ("on", True)):
    reg(f"ft_{key}_ext", joint_cell('ext', 'DOUBLE', dict(FIT_PROPS, fit_cutter=fit), maker=maker_block, scale=62,
                                    centre=(5, 0, 0), az=-45, el=22, grey_far=6.0, post=post_centre))
    reg(f"ft_{key}_plan", joint_cell('sec', 'DOUBLE', dict(FIT_PROPS, fit_cutter=fit), maker=maker_block, scale=50,
                                     centre=(5, 0, 0), sec={'tilt': 90.0}, cap_only=True, post=post_centre))


def repair_cell(after):
    def fn(w, h):
        fresh()
        bm = ring_tube(34, 10, rings=8)
        bm.verts.ensure_lookup_table()
        ring_edges = [e for e in bm.edges if abs(e.verts[0].co.z - e.verts[1].co.z) < 1e-6
                      and abs(e.verts[0].co.z) < 16.5 and e.verts[0].co.y < 3]      # the side facing the camera
        ring_edges.sort(key=lambda e: (round(e.verts[0].co.z, 3), math.atan2(e.verts[0].co.y, e.verts[0].co.x)))
        for k, e in enumerate(ring_edges[3::max(1, len(ring_edges) // 8)][:8]):
            mid = (e.verts[0].co + e.verts[1].co) / 2
            out = bm.verts.new(mid + Vector((mid.x, mid.y, 0)).normalized() * 2.4 + Vector((0, 0, 0.9)))
            bm.faces.new((e.verts[0], e.verts[1], out))
        ob = object_from(bm)
        me = ob.data
        marks = []
        if not after:
            b = bmesh.new()
            b.from_mesh(me)
            marks = [(e.verts[0].co + e.verts[1].co) / 2 for e in b.edges if not e.is_manifold]
            b.free()
        else:
            repair_mesh(me)
        me.materials.append(mat(GREY_RGB))
        for p in marks:
            bm2 = bmesh.new()
            bmesh.ops.create_uvsphere(bm2, u_segments=16, v_segments=8, radius=1.5)
            bmesh.ops.translate(bm2, vec=p * 1.04, verts=bm2.verts)
            m2 = bpy.data.meshes.new("mk")
            bm2.to_mesh(m2)
            bm2.free()
            m2.materials.append(mat(RED_RGB))
            sc.collection.objects.link(bpy.data.objects.new("mk", m2))
        camera(direction(-20, 18) * 300, Vector((4, 0, 0)), 34)
    return fn


reg("rp_before", repair_cell(False))
reg("rp_after", repair_cell(True))

# ---- tolerances
for g in (0.2, 0.4, 0.8):
    reg(f"tg_{int(g * 10)}_sec", joint_cell('sec', 'HINGE', {'gap': g}, scale=17))
for s in (0.0, 0.6, 1.2):
    reg(f"ts_{int(s * 10)}_sec", joint_cell('sec', 'DOUBLE', {'link_end': 'CLIP', 'snap': s}, part_kw={'length': 100},
                                            scale=14, sec={'angle': 90.0}, cen_off=(0, 0, -13)))

# ---- arrays, curves, posing
HZ = {'length': 110, 'radius': 8, 'horizontal': True}
for n in (1, 2, 3):
    reg(f"ar_{n}_ext", joint_cell('ext', 'HINGE', {'array_count': n, 'array_mode': 'FIT'}, part_kw=HZ, scale=126,
                                  centre=(0, 0, 0), az=0, el=10), w=720, h=190)
for t in (0, 90):
    reg(f"aw_{t}_ext", joint_cell('ext', 'HINGE', {'array_count': 4, 'array_twist': float(t)}, part_kw=HZ, scale=126,
                                  centre=(0, 0, 0), az=-20, el=22), w=720, h=190)
CURVE_PROPS = lambda **k: dict({'array_count': 3, 'array_mode': 'FIT', 'place_curve': lambda: _TAIL["curve"]}, **k)
for key, jt, extra in (("hinge", 'HINGE', {}), ("ball", 'BALL', {}), ("shape", 'SHAPE', {'shape_preset': 'CONE'})):
    reg(f"ac_{key}_ext", joint_cell('ext', jt, CURVE_PROPS(**extra), maker=maker_tail, scale=88, centre=(35, 0, 30), az=0, el=0),
        w=560, h=460)
reg("ap_straight", joint_cell('ext', 'HINGE', {'array_count': 3}, maker=maker_chain, scale=100, centre=(22, 0, 8), az=0, el=0))


def ap_posed(w, h):
    ob, js = build('HINGE', {'array_count': 3, 'path': lambda: _TAIL["path"]}, maker_chain)
    po = js.posed
    po.hide_render = True
    bm = bmesh.new()
    bm.from_mesh(po.data)
    bm.transform(po.matrix_world)
    bm.faces.index_update()
    shells = []
    for grp in gmesh.linked_shells(bm):
        keep = {f.index for f in grp}
        p = bm.copy()
        p.faces.ensure_lookup_table()
        drop = [f for f in p.faces if f.index not in keep]
        if drop:
            bmesh.ops.delete(p, geom=drop, context='FACES')
        shells.append(p)
    bm.free()
    start = Vector((0, 0, -40))
    order = sorted(range(len(shells)), key=lambda i: (centroid(shells[i]) - start).length)
    show([shells[i] for i in order], list(range(len(order))))
    ob.hide_render = True
    camera(direction(0, 0) * 300 + Vector((22, 0, 8)), Vector((22, 0, 8)), 100)


reg("ap_posed", ap_posed)

# ---- cross-section controls
SEC_ROWS = {"along": {'tilt': 0.0}, "across": {'tilt': 90.0}, "offset": {'offset': 3.0}, "rotate": {'angle': 90.0}}
for key, pr in SEC_ROWS.items():
    reg(f"sc_{key}_face", joint_cell('sec', 'HINGE', None, scale=34, sec=pr))
    reg(f"sc_{key}_3q", joint_cell('sec', 'HINGE', None, scale=44, sec=pr, sec_view=38))

# ---- hero tiles
reg("hero_a", joint_cell('sec', 'HINGE', None, scale=40, sec={}, sec_view=36), w=420, h=420)
reg("hero_b", joint_cell('sec', 'BALL', None, scale=40, sec={}, sec_view=36), w=420, h=420)
reg("hero_c", joint_cell('ext', 'DOUBLE', {'link_end': 'CLIP', 'gear_mesh': True}, part_kw={'length': 100}, scale=52,
                         az=-35, el=16), w=420, h=420)
reg("hero_d", joint_cell('ext', 'HINGE', CURVE_PROPS(), maker=maker_tail, scale=92, centre=(35, 0, 30), az=0, el=0),
    w=420, h=420)

# ----------------------------------------------------------------------------- main
done, failed = 0, []
for name, (fn, w, h) in CELLS.items():
    if ONLY and name not in ONLY:
        continue
    try:
        fn(w, h)
        render(name, w, h)
        done += 1
        print("CELL ok", name)
    except Exception as exc:                      # keep going: report at the end
        traceback.print_exc()
        failed.append(name)
        print("CELL FAIL", name, exc)
print(f"CELLS rendered {done}, failed {len(failed)}: {failed}")
