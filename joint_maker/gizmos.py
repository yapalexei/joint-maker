"""Viewport gizmos: slide arrow, offset arrows and the bend-direction ring."""

import bpy
import math
from mathutils import Matrix, Vector
from .core.frame import axis_world, cylinder_frame, offset_axes
from .core.helpers import target_object
from .core.state import LAST_FRAMES


def _gizmo_target():
    t = target_object(bpy.context)
    return t if t is not None and t.joint_maker.active else None


def _giz_get_slide():
    t = _gizmo_target()
    if t is None:
        return 0.0
    aw = axis_world(t, t.joint_maker)
    return t.joint_maker.position * aw[2] if aw else 0.0


def _giz_set_slide(value):
    t = _gizmo_target()
    if t is None:
        return
    aw = axis_world(t, t.joint_maker)
    if aw and aw[2] > 0:
        t.joint_maker.position = min(1.0, max(0.0, value / aw[2]))


def _giz_get_turn():
    t = _gizmo_target()
    return math.radians(t.joint_maker.rotation) if t else 0.0


def _giz_set_turn(value):
    t = _gizmo_target()
    if t is not None:
        t.joint_maker.rotation = (math.degrees(value) + 180.0) % 360.0 - 180.0


def _giz_offset_handlers(attr):
    def get():
        t = _gizmo_target()
        return getattr(t.joint_maker, attr) / t.joint_maker.mm_per_unit if t else 0.0

    def set(value):
        t = _gizmo_target()
        if t is not None:
            setattr(t.joint_maker, attr, value * t.joint_maker.mm_per_unit)
    return get, set


class JOINTMAKER_GGT_place(bpy.types.GizmoGroup):
    """viewport handles: an arrow on the cylinder axis slides the joint, a ring turns it"""
    bl_idname = "JOINTMAKER_GGT_place"
    bl_label = "Joint Maker Placement"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'PERSISTENT'}

    @classmethod
    def poll(cls, context):
        t = target_object(context)
        return (t is not None and t.joint_maker.active and t.joint_maker.show_gizmo
                and context.mode == 'OBJECT')

    def setup(self, context):
        a = self.gizmos.new("GIZMO_GT_arrow_3d")
        a.target_set_handler("offset", get=_giz_get_slide, set=_giz_set_slide)
        a.color = (1.0, 0.55, 0.1)
        a.color_highlight = (1.0, 0.8, 0.4)
        a.alpha, a.alpha_highlight = 0.8, 1.0
        self.slide = a
        d = self.gizmos.new("GIZMO_GT_dial_3d")
        d.target_set_handler("offset", get=_giz_get_turn, set=_giz_set_turn)
        d.draw_options = {'ANGLE_VALUE'}
        d.line_width = 3
        d.color = (0.75, 0.45, 1.0)
        d.color_highlight = (0.9, 0.75, 1.0)
        d.alpha, d.alpha_highlight = 0.7, 1.0
        self.turn = d
        # two arrows across the axis (off-centre offset), coloured like Blender's axes
        self.across = []
        for attr in ("offset_a", "offset_b"):
            g = self.gizmos.new("GIZMO_GT_arrow_3d")
            get, set_ = _giz_offset_handlers(attr)
            g.target_set_handler("offset", get=get, set=set_)
            g.alpha, g.alpha_highlight = 0.8, 1.0
            self.across.append(g)

    def draw_prepare(self, context):
        t = target_object(context)
        aw = axis_world(t, t.joint_maker) if t else None
        if not aw:
            return
        base, axis, length, centre, radius = aw
        rot = Vector((0, 0, 1)).rotation_difference(axis).to_matrix().to_4x4()
        # arrow: based at the cylinder's bottom; its offset is the joint's distance along the axis
        self.slide.matrix_basis = Matrix.Translation(base) @ rot
        gs = t.joint_maker.gizmo_size          # fixed on-screen size, independent of the object
        self.slide.use_draw_scale = True
        self.slide.length = 1.0 * gs
        self.slide.hide = ((t.joint_maker.array_count > 1 and t.joint_maker.array_mode == 'FIT')
                           or t.joint_maker.place_curve is not None)
        # ring: around the joint's own (possibly tilted / curve-following) axis at its centre
        js_ = t.joint_maker
        if js_.place_curve is not None:
            fr = LAST_FRAMES.get(t.as_pointer())
            Fw = fr[0] if fr else None
        else:
            Fw = t.matrix_world @ cylinder_frame(t, js_)[0]
        if Fw is not None:
            # undo the flip and the bend turn so the ring's zero stays put while dragging
            if js_.flip:
                Fw = Fw @ Matrix.Rotation(math.pi, 4, 'X')
            Fw = Fw @ Matrix.Rotation(-math.radians(js_.rotation), 4, 'Z')
            loc, q, _s = Fw.decompose()
            self.turn.matrix_basis = Matrix.Translation(loc) @ q.to_matrix().to_4x4()
        self.turn.hide = Fw is None
        self.turn.use_draw_scale = True
        self.turn.scale_basis = 1.0 * gs
        # across-axis arrows: based where the joint would be without the offset, so each
        # arrow's offset is the joint's off-centre distance along that axis (world units)
        js = t.joint_maker
        colours = {"X": (0.95, 0.25, 0.3), "Y": (0.5, 0.85, 0.15), "Z": (0.25, 0.55, 1.0)}
        axes = offset_axes(t, js)
        for g, (letter, d), attr in zip(self.across, axes, ("offset_a", "offset_b")):
            here = centre - d * (getattr(js, attr) / js.mm_per_unit)
            g.matrix_basis = Matrix.Translation(here) @ Vector((0, 0, 1)).rotation_difference(d).to_matrix().to_4x4()
            g.use_draw_scale = True
            g.length = 0.8 * gs
            g.hide = js.place_curve is not None           # offsets don't apply on a curve
            g.color = colours[letter]
            g.color_highlight = tuple(min(1.0, c + 0.3) for c in colours[letter])
