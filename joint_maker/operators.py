"""Operators (panel buttons)."""

import bpy
from mathutils import Vector
from bpy.props import FloatProperty
from .constants import ALL_MODS
from .core.frame import axis_ends, center_on_shape, cylinder_frame
from .core.helpers import part_objects, remove_helpers, target_object
from .core.rebuild import rebuild
from .geometry.repair import MANIFOLD_CACHE, repair_mesh
from .properties import nudge


class JOINTMAKER_OT_add(bpy.types.Operator):
    bl_idname = "joint_maker.add"
    bl_label = "Add Joint"
    bl_description = "Generate a joint cutter for the active cylinder"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return target_object(context) is not None

    def execute(self, context):
        obj = target_object(context)
        js = obj.joint_maker
        fr = cylinder_frame(obj, js)
        if fr is None:
            self.report({'ERROR'}, "Object has no geometry")
            return {'CANCELLED'}
        _, R, H, s_perp = fr
        dia_mm = 2 * R * js.mm_per_unit * s_perp
        if dia_mm < 8.0:   # too small to hold sub-mm clearances: assume a 20 mm print
            js.mm_per_unit = 20.0 / (2 * R * s_perp)
            self.report({'INFO'}, f"Assuming a 20 mm printed diameter (1 unit = {js.mm_per_unit:.3g} mm)")
        js.active = True
        rebuild(obj)
        return {'FINISHED'}


class JOINTMAKER_OT_update(bpy.types.Operator):
    bl_idname = "joint_maker.update"
    bl_label = "Rebuild"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        t = target_object(context)
        return t is not None and t.joint_maker.active

    def execute(self, context):
        rebuild(target_object(context))
        return {'FINISHED'}


class JOINTMAKER_OT_nudge(bpy.types.Operator):
    bl_idname = "joint_maker.nudge"
    bl_label = "Nudge Joint"
    bl_description = "Slide the joint along the cylinder or turn its bend direction by one step"
    bl_options = {'REGISTER', 'UNDO'}
    move: FloatProperty(default=0.0)       # in steps (+1 = towards the top)
    turn: FloatProperty(default=0.0)       # in steps (+1 = counter-clockwise seen from the top)
    off_a: FloatProperty(default=0.0)      # in steps across the axis
    off_b: FloatProperty(default=0.0)

    @classmethod
    def poll(cls, context):
        t = target_object(context)
        return t is not None and t.joint_maker.active

    def execute(self, context):
        js = target_object(context).joint_maker
        nudge(js, self.move * js.nudge_mm, self.turn * js.nudge_deg)
        if self.off_a:
            js.offset_a += self.off_a * js.nudge_mm
        if self.off_b:
            js.offset_b += self.off_b * js.nudge_mm
        return {'FINISHED'}


class JOINTMAKER_OT_center(bpy.types.Operator):
    bl_idname = "joint_maker.center"
    bl_label = "Center on Shape"
    bl_description = ("Slice the mesh at the joint and move the joint onto the middle of the "
                      "cross-section (for shapes that aren't centred in their bounding box)")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        t = target_object(context)
        return t is not None and t.joint_maker.active

    def execute(self, context):
        if not center_on_shape(target_object(context), target_object(context).joint_maker):
            self.report({'WARNING'}, "No geometry at the joint position to centre on")
            return {'CANCELLED'}
        return {'FINISHED'}


class JOINTMAKER_OT_repair(bpy.types.Operator):
    bl_idname = "joint_maker.repair"
    bl_label = "Repair Mesh"
    bl_description = ("Remove small stray flaps and interior faces, merge duplicate vertices and "
                      "fix flipped normals so the fast Manifold solver can be used (edits the "
                      "object's mesh; undoable)")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        t = target_object(context)
        return t is not None and context.mode == 'OBJECT'

    def execute(self, context):
        obj = target_object(context)
        before, after, flaps = repair_mesh(obj.data)
        MANIFOLD_CACHE.clear()
        if obj.joint_maker.active:
            rebuild(obj)
        if after:
            self.report({'WARNING'}, f"Bad edges {before} -> {after}: the rest need manual cleanup "
                                     "(Select > All by Trait > Non Manifold); Exact solver stays on")
        else:
            self.report({'INFO'}, f"Mesh repaired: {before} bad edges fixed ({flaps} stray flaps "
                                  "removed), now watertight")
        return {'FINISHED'}


class JOINTMAKER_OT_reset_offset(bpy.types.Operator):
    bl_idname = "joint_maker.reset_offset"
    bl_label = "Reset Offset"
    bl_description = "Put the joint back on the bounding-box centre line"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        t = target_object(context)
        return t is not None and t.joint_maker.active

    def execute(self, context):
        js = target_object(context).joint_maker
        js.offset_a = js.offset_b = 0.0
        return {'FINISHED'}


class JOINTMAKER_OT_section_tilt(bpy.types.Operator):
    bl_idname = "joint_maker.section_tilt"
    bl_label = "Section Orientation"
    bl_options = {'REGISTER', 'UNDO'}
    tilt: FloatProperty()

    def execute(self, context):
        t = target_object(context)
        if t:
            t.joint_maker.section_tilt = self.tilt
        return {'FINISHED'}


class JOINTMAKER_OT_set_twist(bpy.types.Operator):
    bl_idname = "joint_maker.set_twist"
    bl_label = "Set Second Pivot Angle"
    bl_options = {'REGISTER', 'UNDO'}
    angle: FloatProperty()

    def execute(self, context):
        t = target_object(context)
        if t:
            t.joint_maker.pivot_twist = self.angle
        return {'FINISHED'}


class JOINTMAKER_OT_remove(bpy.types.Operator):
    bl_idname = "joint_maker.remove"
    bl_label = "Remove Joint"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        t = target_object(context)
        return t is not None and t.joint_maker.active

    def execute(self, context):
        obj = target_object(context)
        remove_helpers(obj)
        obj.joint_maker.active = False
        return {'FINISHED'}


class JOINTMAKER_OT_apply(bpy.types.Operator):
    bl_idname = "joint_maker.apply"
    bl_label = "Apply Joint"
    bl_description = "Bake the boolean and split the cylinder into its printable parts"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        t = target_object(context)
        return t is not None and t.joint_maker.active and context.mode == 'OBJECT'

    def execute(self, context):
        obj = target_object(context)
        js = obj.joint_maker
        res = rebuild(obj) or {}
        poses, arts = res.get("poses"), res.get("arts", [])
        lo, hi = axis_ends(obj, js)
        a_hat = (hi - lo).normalized()
        arts_sorted = sorted(arts, key=lambda a: a["pt"].dot(a_hat))
        cuts = [a["pt"].dot(a_hat) for a in arts_sorted]

        def centroid(o):
            return sum((v.co for v in o.data.vertices), Vector()) / max(1, len(o.data.vertices))

        extra = part_objects(obj)
        pin_pose = []
        for ob in extra:                               # which part each pin rides with
            c = centroid(ob)
            pin_pose.append(min(range(len(arts_sorted)), key=lambda i: (arts_sorted[i]["pt"] - c).length) + 1
                            if arts_sorted else 0)
        for i, ob in enumerate(extra):                 # keep separate pins as real parts
            mw = ob.matrix_world.copy()
            ob.parent = None
            ob.matrix_world = mw
            del ob["joint_maker_part"]
            del ob["joint_maker_helper"]
            ob.name = ob.data.name = f"{obj.name}_Pin{i + 1}"
        with context.temp_override(object=obj, active_object=obj):
            for name in ALL_MODS:
                m = obj.modifiers.get(name)
                if m:
                    m.show_viewport = True
                    bpy.ops.object.modifier_apply(modifier=name)
        remove_helpers(obj)
        js.active = False
        parts = [obj]
        if js.separate or poses is not None:
            for o in context.selected_objects:
                o.select_set(False)
            obj.select_set(True)
            context.view_layer.objects.active = obj
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.separate(type='LOOSE')
            bpy.ops.object.mode_set(mode='OBJECT')
            parts = list(context.selected_objects)
            base = obj.name
            # name parts in order along the cylinder axis (A = bottom)
            parts.sort(key=lambda o: centroid(o).dot(a_hat))
            for i, o in enumerate(parts):
                o.name = f"{base}_{chr(65 + i)}" if len(parts) <= 26 else f"{base}_{i + 1:02d}"
                o.data.name = o.name
                if poses is not None:                  # lay each rigid part on the path
                    k = sum(1 for c in cuts if centroid(o).dot(a_hat) > c + 1e-9)
                    o.matrix_world = poses[min(k, len(poses) - 1)] @ o.matrix_world
            if poses is not None:
                for ob, k in zip(extra, pin_pose):
                    ob.matrix_world = poses[min(k, len(poses) - 1)] @ ob.matrix_world
                    ob.hide_set(False)
        self.report({'INFO'}, f"Joint applied: {len(parts)} part(s)"
                    + (f" + {len(extra)} pin(s)" if extra else ""))
        return {'FINISHED'}
