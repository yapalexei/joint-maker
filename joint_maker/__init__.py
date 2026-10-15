"""
Joint Maker - turn a cylinder-like part into a 3D-printable joint with a live boolean cutter.

Select a part, open the "Joints" tab in the 3D view sidebar (N) and press "Add Joint". A cutter is
generated and attached with a live Boolean modifier, so every setting updates the result
immediately; "Apply" bakes it and splits the part into its printable pieces. The cutter is the
*gap* geometry: subtracting it leaves separate pieces that don't touch, interlocked so they can
only move the way the joint allows.

Package layout
  constants      shared names (modifier names, axis table, preview colours)
  geometry/      bmesh building blocks, plane sections, mesh repair, STL reading
  joints/        one module per joint type + the type registry (joints/__init__.py)
  core/          joint frame & placement, array/curve layout, rebuild, trimming, previews
  properties     per-object settings (Object.joint_maker) and live-update callbacks
  operators      panel buttons
  gizmos         viewport handles
  ui             the sidebar panel
  handlers       app handlers (re-pose when a path curve is edited)

Joint frame used by every builder: Z = part axis, X = hinge axis, origin = joint centre.
"""

import bpy
from bpy.props import PointerProperty

from . import gizmos, handlers, operators, properties, ui

CLASSES = (
    properties.JointMakerSettings,
    operators.JOINTMAKER_OT_add,
    operators.JOINTMAKER_OT_update,
    operators.JOINTMAKER_OT_remove,
    operators.JOINTMAKER_OT_set_twist,
    operators.JOINTMAKER_OT_nudge,
    operators.JOINTMAKER_OT_center,
    operators.JOINTMAKER_OT_reset_offset,
    operators.JOINTMAKER_OT_repair,
    operators.JOINTMAKER_OT_section_tilt,
    operators.JOINTMAKER_OT_apply,
    gizmos.JOINTMAKER_GGT_place,
    ui.JOINTMAKER_PT_panel,
)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Object.joint_maker = PointerProperty(type=properties.JointMakerSettings)
    handlers.register()


def unregister():
    handlers.unregister()
    del bpy.types.Object.joint_maker
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
