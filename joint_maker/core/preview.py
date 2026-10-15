"""Cross-section preview of the joint result."""

import bpy
import bmesh
import math
from mathutils import Matrix, Vector
from ..constants import PIN_COLOUR, SECTION_COLOURS
from .frame import cylinder_frame
from .helpers import new_helper, part_objects
from .state import LAST_FRAMES
from ..geometry.mesh import linked_shells, merge_bm


def _section_materials():
    mats = []
    for i, c in enumerate(list(SECTION_COLOURS) + [PIN_COLOUR]):      # the last one is for pins
        name = f"JM Section {i + 1}"
        m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        m.diffuse_color = (*c, 1.0)
        mats.append(m)
    return mats


def update_section(obj):
    """
    Live cross-section preview: the joint result (and any separate pins) sliced by a plane
    through the chosen joint, with the cut faces capped and every part in its own colour.
    Plane: through the joint centre, normal = the joint's Y axis turned by Rotate around the
    joint axis and tipped by Tilt (0 = slice along the joint, 90 = across it), shifted by Offset.
    """
    js = obj.joint_maker
    name = obj.name + "_Section"
    sec = bpy.data.objects.get(name)
    if not (js.active and js.section_show):
        if sec is not None and sec.get("joint_maker_helper"):
            me = sec.data
            bpy.data.objects.remove(sec, do_unlink=True)
            if me.users == 0:
                bpy.data.meshes.remove(me)
        if js.posed is None:                           # give the pins back (they're cut in the section)
            for po in part_objects(obj):
                po.hide_set(False)
        return
    frames = LAST_FRAMES.get(obj.as_pointer())
    if not frames:
        return
    Finv = obj.matrix_world.inverted()
    j = max(0, min(len(frames) - 1, js.section_joint - 1))
    F = Finv @ frames[j]
    rot = F.to_3x3().normalized()
    n = (rot @ (Matrix.Rotation(math.radians(js.section_angle), 3, 'Z')
                @ Matrix.Rotation(math.radians(js.section_tilt), 3, 'X') @ Vector((0, 1, 0)))).normalized()
    mm = 1.0 / (js.mm_per_unit * max(1e-9, cylinder_frame(obj, js)[3]))
    co = F.translation + n * (js.section_offset * mm)
    # nudge the plane a hair off the mesh: when it passes exactly through vertices (a ball's
    # equator, mirror-symmetric parts) the cap fill can go wrong
    co = co + n * (2e-4 * max(1e-9, cylinder_frame(obj, js)[1]))
    if js.section_flip:                                  # keep the other half
        n = -n
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    src = bmesh.new(); src.from_mesh(ev.to_mesh()); ev.to_mesh_clear()
    n_obj_faces = len(src.faces)
    for po in part_objects(obj):                       # separate pins are cut too
        pb = bmesh.new(); pb.from_mesh(po.data)
        merge_bm(src, pb)
    # slice and cap each part on its own, so parts whose cut outlines touch (a press-fit pin
    # in its hole) stay separate. Each part is isolated in a full copy of the mesh, which keeps
    # its faces intact.
    src.faces.index_update()                         # merged-in pins need fresh face numbers
    axis_l = rot @ Vector((0, 0, 1))                 # the joint's own axis
    shells = []
    for g in linked_shells(src):
        vs = {v for f in g for v in f.verts}
        c = sum((v.co for v in vs), Vector()) / max(1, len(vs))
        shells.append(({f.index for f in g}, c.dot(axis_l), any(f.index >= n_obj_faces for f in g)))
    # colours go by position along the joint (lower part first), pins always get the last colour
    rank = {i: r for r, i in enumerate(sorted((i for i, s_ in enumerate(shells) if not s_[2]),
                                              key=lambda i: shells[i][1]))}
    out = bmesh.new()
    for k, (keep, _c, is_pin) in enumerate(shells):
        part = src.copy()
        part.faces.ensure_lookup_table()
        drop = [f for f in part.faces if f.index not in keep]
        if drop:
            bmesh.ops.delete(part, geom=drop, context='FACES')
        res = bmesh.ops.bisect_plane(part, geom=part.verts[:] + part.edges[:] + part.faces[:],
                                     plane_co=co, plane_no=n, clear_outer=True)
        cut = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge) and e.is_valid]
        cut += [e for e in part.edges if len(e.link_faces) == 1 and e not in cut
                and all(abs((v.co - co).dot(n)) < 1e-5 for v in e.verts)]   # edges on the plane
        open_cut = [e for e in cut if len(e.link_faces) < 2]
        if open_cut:
            # triangle fill understands outlines with holes inside (a ring around a pin, a
            # socket around a ball); a hole-fill pass closes any tiny gaps left over
            bmesh.ops.triangle_fill(part, use_beauty=True, use_dissolve=False, edges=open_cut, normal=n)
            left = [e for e in part.edges if len(e.link_faces) == 1]
            if left:
                bmesh.ops.holes_fill(part, edges=left, sides=0)
        for f in part.faces:
            f.material_index = len(SECTION_COLOURS) if is_pin else rank[k] % len(SECTION_COLOURS)
        merge_bm(out, part)
    src.free()
    if sec is None:
        home = obj.users_collection[0] if obj.users_collection else bpy.context.scene.collection
        sec = new_helper(obj, name, home)
        sec.display_type = 'SOLID'
    if len(sec.data.materials) != len(SECTION_COLOURS) + 1:
        sec.data.materials.clear()
        for m in _section_materials():
            sec.data.materials.append(m)
    out.to_mesh(sec.data); out.free()
    sec.data.update()
    sec.hide_set(False)
    for po in part_objects(obj):                       # the pins are part of the section: hide the whole ones
        po.hide_set(js.section_hide_model)
    if js.section_hide_model:
        obj.display_type = 'WIRE'
