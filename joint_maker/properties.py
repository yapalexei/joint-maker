"""Per-object joint settings and their live-update callbacks."""

import bpy
from bpy.props import FloatProperty, IntProperty, BoolProperty, EnumProperty, PointerProperty
from .core.frame import mm_per_position
from .core.preview import update_section
from .core.rebuild import rebuild
from .joints import JOINT_TYPES
from .joints.shape import SHAPE_PRESETS


def _update(self, context):
    obj = self.id_data
    if self.active and self.live:
        rebuild(obj)


def _section_update(self, context):
    obj = self.id_data
    if not self.active:
        return
    if self.section_show:
        update_section(obj)
    else:
        update_section(obj)                              # removes the preview
        obj.display_type = 'TEXTURED'
        if self.path is not None:
            rebuild(obj)                                 # let the pose preview set the display again


def _get_pos_mm(self):
    obj = self.id_data
    return self.position * mm_per_position(obj, self) if obj.type == 'MESH' else 0.0


def _set_pos_mm(self, value):
    k = mm_per_position(self.id_data, self)
    if k > 0:
        self.position = min(1.0, max(0.0, value / k))


def nudge(js, move_mm=0.0, turn_deg=0.0):
    if move_mm:
        k = mm_per_position(js.id_data, js)
        if k > 0:
            js.position = min(1.0, max(0.0, js.position + move_mm / k))
    if turn_deg:
        js.rotation = (js.rotation + turn_deg + 180.0) % 360.0 - 180.0


class JointMakerSettings(bpy.types.PropertyGroup):
    active: BoolProperty(default=False)
    live: BoolProperty(name="Live update", default=True,
                       description="Rebuild the cutter whenever a value changes")
    joint_type: EnumProperty(name="Type", items=JOINT_TYPES, update=_update)
    axis: EnumProperty(name="Cylinder axis", items=[('Z', "Z", ""), ('X', "X", ""), ('Y', "Y", "")],
                       default='Z', update=_update)
    radius_mode: EnumProperty(name="Radius from", default='SECTION', update=_update, items=[
        ('SECTION', "Cross-section", "Size the joint from the shape's outline at the joint "
                                     "(ignores other parts of the mesh)"),
        ('BBOX', "Bounding box", "Size the joint from the whole object's bounding box "
                                 "(how versions before 0.2.4 worked)")])
    joint_scale: FloatProperty(name="Joint size", default=1.0, min=0.3, max=1.0, subtype='FACTOR',
                               update=_update,
                               description="Scale the joint's features relative to the cylinder "
                                           "(clearances stay in mm). Below 1 the cylinder slims to "
                                           "a waist around the joint, tapering back at 45 deg")
    waist_taper: EnumProperty(name="Taper", default='AUTO', update=_update, items=[
        ('AUTO', "45\u00b0", "Taper back to full width at 45 deg (prints without supports)"),
        ('CUSTOM', "Length", "Set the taper length yourself"),
        ('NONE', "None", "Straight step back to full width")])
    taper_len: FloatProperty(name="Taper length (mm)", default=3.0, min=0.0, soft_max=30.0, precision=2,
                             update=_update, description="Length of the waist taper")
    keep_range: BoolProperty(name="Keep range of motion", default=True, update=_update,
                             description="Add a straight neck so the full-width body returns only "
                                         "where it can't collide when the joint bends. Off = most "
                                         "compact waist, less bend")
    solver_mode: EnumProperty(name="Solver", default='AUTO', update=_update, items=[
        ('AUTO', "Auto", "Manifold when the mesh is watertight, otherwise Exact"),
        ('MANIFOLD', "Manifold", "Fast and robust, but needs a watertight mesh (else nothing is cut)"),
        ('EXACT', "Exact", "Slower, but copes with meshes that aren't watertight")])
    limit_reach_on: BoolProperty(name="Limit outer reach", default=False, update=_update,
                                 description="Trim every cutter piece to a tube just past the part's "
                                             "surface at the joint, so neighbouring geometry (the body "
                                             "around a shoulder) isn't cut")
    limit_reach: FloatProperty(name="Reach past surface (mm)", default=1.0, min=0.0, soft_max=10.0,
                               precision=2, update=_update,
                               description="How far the cutters may reach past the part's surface; "
                                           "sets the waist pipe's outer diameter")
    limit_bevel: FloatProperty(name="Outer bevel (mm)", default=0.0, min=0.0, soft_max=20.0, precision=2,
                               update=_update, description="Chamfer the outer end edges of the cutter "
                                                           "tube so the cut tapers off at its ends")
    fit_cutter: BoolProperty(name="Fit cutter to shape", default=False, update=_update,
                             description="Trim the cutter to a tight hull around the object at each "
                                         "joint (plus margin), so nearby geometry isn't cut")
    fit_margin: FloatProperty(name="Margin (mm)", default=1.0, min=0.0, soft_max=10.0, precision=2,
                              update=_update, description="How far the fitted cutter reaches past "
                                                          "the object's surface")
    section_show: BoolProperty(name="Show cross-section", default=False, update=_section_update,
                               description="Slice the result with a plane and show the inside, "
                                           "each part in its own colour")
    section_joint: IntProperty(name="Joint", default=1, min=1, soft_max=20, update=_section_update,
                               description="Which joint to slice through (when there are several)")
    section_offset: FloatProperty(name="Offset (mm)", default=0.0, precision=2, step=10,
                                  update=_section_update,
                                  description="Move the slicing plane along its normal")
    section_angle: FloatProperty(name="Rotate", default=0.0, min=-180, max=180, update=_section_update,
                                 description="Turn the slicing plane around the joint's axis (deg)")
    section_tilt: FloatProperty(name="Tilt", default=0.0, min=-90, max=90, update=_section_update,
                                description="Tip the slicing plane: 0 = along the joint, 90 = across it")
    section_flip: BoolProperty(name="Flip side", default=False, update=_section_update,
                               description="Keep the other half of the slice")
    section_hide_model: BoolProperty(name="Hide model", default=True, update=_section_update,
                                     description="Show the model as wire while the section is shown")
    tilt_x: FloatProperty(name="Tilt X", default=0.0, min=-90, max=90, update=_update,
                          description="Tilt the joint around its first cross axis (deg)")
    tilt_y: FloatProperty(name="Tilt Y", default=0.0, min=-90, max=90, update=_update,
                          description="Tilt the joint around its second cross axis (deg)")
    place_curve: PointerProperty(name="Placement curve", type=bpy.types.Object, update=_update,
                                 poll=lambda self, ob: ob.type == 'CURVE',
                                 description="Place the joints along this curve, each one square to it "
                                             "(for curved or tapering parts)")
    curve_start: FloatProperty(name="Start", default=0.0, min=0.0, max=1.0, subtype='FACTOR',
                               update=_update, description="Where along the curve joints may start")
    curve_end: FloatProperty(name="End", default=1.0, min=0.0, max=1.0, subtype='FACTOR',
                             update=_update, description="Where along the curve joints must end")
    curve_snap: BoolProperty(name="Snap to section centre", default=True, update=_update,
                             description="Move each joint onto the centre of the shape's cross-section "
                                         "where it sits, so the curve doesn't have to run exactly "
                                         "down the middle")
    position: FloatProperty(name="Position", default=0.5, min=0.0, max=1.0, subtype='FACTOR',
                            description="Joint centre along the cylinder (0 = bottom, 1 = top)",
                            update=_update)
    rotation: FloatProperty(name="Bend direction", default=0.0, min=-180, max=180,
                            description="Rotate the hinge axis around the cylinder axis (deg)",
                            update=_update)
    position_mm: FloatProperty(name="Position (mm)", get=_get_pos_mm, set=_set_pos_mm, precision=2,
                               step=10, description="Joint centre, measured from the bottom of the "
                                                    "cylinder in printed mm")
    offset_a: FloatProperty(name="Offset A (mm)", default=0.0, precision=2, step=10, update=_update,
                            description="Move the joint off-centre along the first axis across the "
                                        "cylinder (printed mm)")
    offset_b: FloatProperty(name="Offset B (mm)", default=0.0, precision=2, step=10, update=_update,
                            description="Move the joint off-centre along the second axis across the "
                                        "cylinder (printed mm)")
    nudge_mm: FloatProperty(name="Step (mm)", default=1.0, min=0.01, soft_max=20.0, precision=2,
                            description="How far the move buttons slide the joint")
    nudge_deg: FloatProperty(name="Step (\u00b0)", default=15.0, min=0.1, max=180.0,
                             description="How far the rotate buttons turn the joint")
    gizmo_size: FloatProperty(name="Size", default=1.0, min=0.2, max=4.0, subtype='FACTOR',
                              description="On-screen size of the viewport handles (constant at any "
                                          "zoom or object size)")
    show_gizmo: BoolProperty(name="Gizmos", default=True,
                             description="Show the viewport arrow (slide) and ring (rotate)")
    flip: BoolProperty(name="Flip", default=False, update=_update,
                       description="Swap which end gets the tongue and which the prongs")
    mm_per_unit: FloatProperty(name="1 unit =", default=1.0, min=1e-4, soft_max=1000, unit='NONE',
                               description="Printed millimetres per Blender unit (STL export scale)",
                               update=_update)
    gap: FloatProperty(name="Gap (mm)", default=0.40, min=0.05, soft_max=1.0, step=1, precision=2,
                       description="Clearance between faces that slide past each other", update=_update)
    pin_clearance: FloatProperty(name="Pin clearance (mm)", default=0.40, min=0.05, soft_max=1.0,
                                 step=1, precision=2, update=_update,
                                 description="Radial clearance between the pin and its recess")
    tongue_width: FloatProperty(name="Tongue width", default=0.36, min=0.1, max=0.8, subtype='FACTOR',
                                description="Width of the centre tongue as a fraction of the diameter",
                                update=_update)
    pin_style: EnumProperty(name="Pin", default='CONE', update=_update, items=[
        ('CONE', "Cones", "Conical pins: print-in-place without supports"),
        ('ROD', "Rod", "Straight through-pin"),
        ('PIN', "Separate", "Assemblable: holes + a separate headed pin printed on its own")])
    press_fit: FloatProperty(name="Press fit (mm)", default=0.0, min=-0.3, soft_max=0.4, step=1,
                             precision=2, update=_update,
                             description="Extra diameter of the hole that grips the pin "
                                         "(0 = same as the pin; printed holes usually come out small)")
    head_tol: FloatProperty(name="Head clearance (mm)", default=0.4, min=0.0, soft_max=1.0, step=1,
                            precision=2, update=_update,
                            description="Extra diameter of the counterbore around the pin head")
    pin_size: FloatProperty(name="Pin size", default=0.35, min=0.05, max=0.8, subtype='FACTOR',
                            description="Pin radius as a fraction of the cylinder radius", update=_update)
    cone_angle: FloatProperty(name="Cone angle", default=45.0, min=30, max=60,
                              description="Cone half-angle; 45° or more prints without supports",
                              update=_update)
    shape_preset: EnumProperty(name="Shape", default='HOOK', update=_update, items=[
        (k, v[0], v[3]) for k, v in SHAPE_PRESETS.items()] + [
        ('CUSTOM', "Custom object", "Use any mesh object in the scene as the cutout shape")])
    shape_object: PointerProperty(name="Shape object", type=bpy.types.Object, update=_update,
                                  poll=lambda self, ob: ob.type == 'MESH' and ob != self.id_data,
                                  description="Mesh to use as the cutout (hide it in the viewport)")
    shape_axis: EnumProperty(name="Shape axis", default='Z', update=_update,
                             items=[('X', "X", ""), ('Y', "Y", ""), ('Z', "Z", "")],
                             description="The shape's own axis that should line up with the part")
    shape_size_mode: EnumProperty(name="Size", default='FIT', update=_update, items=[
        ('FIT', "Fit", "Scale the shape to the part's diameter times a factor"),
        ('FIXED', "Fixed", "Give the shape an exact diameter in mm")])
    shape_fit: FloatProperty(name="Shape size", default=1.15, min=0.3, soft_max=3.0, precision=3,
                             update=_update, description="Shape diameter / part diameter "
                                                         "(above 1 so it cuts all the way through)")
    shape_dia: FloatProperty(name="Diameter (mm)", default=20.0, min=0.1, soft_max=200.0, precision=2,
                             update=_update)
    shape_height: FloatProperty(name="Height", default=1.0, min=0.1, soft_max=4.0, precision=3,
                                update=_update, description="Stretch the shape along the part's axis")
    shape_limit: FloatProperty(name="Bend limit", default=30.0, min=0.0, max=90.0, update=_update,
                               description="How far the joint bends when posing along a path (deg)")
    link_end: EnumProperty(name="Link ends", default='PIVOT', update=_update, items=[
        ('PIVOT', "Pivot", "Hinge at each end of the link (double-fork link)"),
        ('BALL', "Ball", "Ball at each end of the link (dog-bone link)"),
        ('CLIP', "E-clip", "Forks with axles; an E-shaped link snaps onto both axles")])
    pivot_twist: FloatProperty(name="Second pivot angle", default=0.0, min=-90.0, max=90.0,
                               description="Turn the upper pivot around the cylinder axis "
                                           "(90 = offset double joint, bends on two axes)",
                               update=_update)
    axle_size: FloatProperty(name="Axle size", default=0.28, min=0.1, max=0.6, subtype='FACTOR',
                             description="Axle radius as a fraction of the cylinder radius", update=_update)
    clip_wall: FloatProperty(name="Clip wall", default=0.3, min=0.08, max=0.6, subtype='FACTOR',
                             description="Wall around each socket of the E link, fraction of the radius",
                             update=_update)
    snap: FloatProperty(name="Snap (mm)", default=0.3, min=0.0, soft_max=1.0, step=1, precision=2,
                        description="How much narrower the clip mouth is than the axle", update=_update)
    gear_mesh: BoolProperty(name="Gear mesh", default=False, update=_update,
                            description="Mesh gears between the top and bottom forks so both sides "
                                        "bend together and the link can't slip")
    gear_module: FloatProperty(name="Tooth size (mm)", default=1.0, min=0.4, soft_max=3.0, step=5,
                               precision=2, update=_update,
                               description="Gear module: pitch diameter / tooth count")
    gear_backlash: FloatProperty(name="Backlash (mm)", default=0.3, min=0.0, soft_max=1.0, step=1,
                                 precision=2, update=_update,
                                 description="Play between meshing teeth (printed gears need 0.2-0.4)")
    mouth_side: EnumProperty(name="Opening", default='FRONT', update=_update, items=[
        ('FRONT', "Front", "Clip openings face the front"),
        ('BACK', "Back", "Clip openings face the back")])
    link_length: FloatProperty(name="Link length", default=2.6, min=0.0, soft_max=6.0, precision=3,
                               description="Distance between the two joint centres, in cylinder radii",
                               update=_update)
    ball_size: FloatProperty(name="Ball size", default=0.6, min=0.2, max=0.9, subtype='FACTOR',
                             description="Ball radius as a fraction of the cylinder radius", update=_update)
    stem_size: FloatProperty(name="Stem size", default=0.25, min=0.08, max=0.6, subtype='FACTOR',
                             description="Link stem radius as a fraction of the cylinder radius",
                             update=_update)
    neck_length: FloatProperty(name="Neck length", default=1.3, min=1.0, soft_max=3.0,
                               description="Ball centre to the lower body, in cylinder radii",
                               update=_update)
    socket_wall: FloatProperty(name="Socket wall (mm)", default=0.0, min=0.0, soft_max=5.0, step=10,
                               precision=2, update=_update,
                               description="Wall around the ball socket. 0 = full cylinder width; "
                                           "smaller = thinner, more flexible snap fingers")
    snap_relief: BoolProperty(name="Snap-fit relief", default=False, update=_update,
                              description="Slot the socket so it can flex open when the ball is "
                                          "snapped in (for printing the parts separately)")
    slots: IntProperty(name="Slots", default=1, min=1, max=3, update=_update,
                       description="Slots through the socket: 1 = one cut down the middle (2 fingers)")
    slot_w: FloatProperty(name="Slot width (mm)", default=0.8, min=0.2, soft_max=2.0, step=5,
                          precision=2, update=_update)
    slot_depth: FloatProperty(name="Slot depth", default=0.5, min=0.0, max=0.85, subtype='FACTOR',
                              description="How far past the ball centre the slot runs (fraction of "
                                          "the socket radius)", update=_update)
    slot_angle: FloatProperty(name="Slot angle", default=0.0, min=-90, max=90, update=_update,
                              description="Turn the slots around the axis (deg)")
    ball_control: EnumProperty(name="Set by", default='SWING', update=_update, items=[
        ('SWING', "Swing", "Choose the tilt angle; the socket lip follows"),
        ('LIP', "Snap lip", "Choose how far the socket wraps the ball (mm); the swing follows")])
    snap_lip: FloatProperty(name="Snap lip (mm)", default=0.4, min=0.0, soft_max=1.5, step=1,
                            precision=2, update=_update,
                            description="How far the socket wraps past the ball's widest point: the "
                                        "amount the fingers must spread to snap the ball in")
    swing: FloatProperty(name="Swing", default=30.0, min=5.0, max=60.0,
                         description="Tilt each ball allows before the stem touches the socket (deg)",
                         update=_update)
    array_count: IntProperty(name="Joints", default=1, min=1, soft_max=20, max=100, update=_update,
                             description="Number of joints along the cylinder")
    array_mode: EnumProperty(name="Spread", default='FIT', update=_update, items=[
        ('FIT', "Fit", "Spread the joints so all parts are the same length"),
        ('SPACING', "Spacing", "Fixed distance between joints, centred on Position")])
    array_spacing: FloatProperty(name="Spacing (mm)", default=30.0, min=0.1, soft_max=200.0,
                                 update=_update, description="Distance between joint centres")
    array_twist: FloatProperty(name="Twist per joint", default=0.0, min=-180, max=180, update=_update,
                               description="Turn each joint this much further than the previous one "
                                           "(90 = alternate bend directions for a 3D chain)")
    path: PointerProperty(name="Path", type=bpy.types.Object, update=_update,
                          poll=lambda self, ob: ob.type == 'CURVE',
                          description="Curve to lay the jointed chain along (parts stay rigid)")
    path_roll: FloatProperty(name="Roll", default=0.0, min=-180, max=180, update=_update,
                             description="Spin the chain around its axis on the path")
    path_hide_straight: BoolProperty(name="Hide straight", default=True, update=_update,
                                     description="Show the straight cylinder as wire while posed")
    posed: PointerProperty(type=bpy.types.Object)
    segments: IntProperty(name="Segments", default=64, min=16, max=256, update=_update)
    show_cutter: BoolProperty(name="Show cutter", default=True, update=_update)
    show_result: BoolProperty(name="Show result", default=True, update=_update)
    separate: BoolProperty(name="Separate parts on apply", default=True)
    cutter_coll: PointerProperty(type=bpy.types.Collection)
    pins: PointerProperty(type=bpy.types.Object)
    info: bpy.props.StringProperty()
    warning: bpy.props.StringProperty()
