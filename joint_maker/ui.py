"""The Joints sidebar panel."""

import bpy
from .core.frame import cylinder_frame, offset_axes
from .core.helpers import target_object
from .geometry.repair import mesh_problems


def _fold(lay, idname, title, icon='NONE', closed=False):
    """a collapsible section (Blender remembers whether it's open)"""
    header, body = lay.panel(idname, default_closed=closed)
    header.label(text=title, icon=icon)
    return body


class JOINTMAKER_PT_panel(bpy.types.Panel):
    bl_label = "Joint Maker"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Joints"

    def draw(self, context):
        lay = self.layout
        obj = target_object(context)
        if obj is None:
            lay.label(text="Select a cylinder", icon='INFO')
            return
        js = obj.joint_maker
        lay.prop(js, "joint_type", text="")

        if not js.active:
            col = lay.column(align=True)
            col.prop(js, "axis", expand=True)
            lay.operator("joint_maker.add", icon='MOD_BOOLEAN')
            return

        fr = cylinder_frame(obj, js)
        if fr:
            _, R, H, s_perp = fr
            k = js.mm_per_unit * s_perp
            box = lay.box()
            box.label(text=f"Printed size: \u00d8{2 * R * k:.1f} \u00d7 {H * k:.1f} mm", icon='OBJECT_DATA')
            row = box.row(align=True)
            row.prop(js, "mm_per_unit")
            row.label(text="mm")
        if js.warning:
            wb = lay.box()
            for w in js.warning.split("; "):
                wb.label(text=w, icon='ERROR')

        # ---- placement
        body = _fold(lay, "JM_place", "Placement", 'OBJECT_ORIGIN')
        if body:
            col = body.column(align=True)
            col.row(align=True).prop(js, "axis", expand=True)
            movable = not (js.array_count > 1 and js.array_mode == 'FIT')
            r = col.row(align=True)
            r.active = movable
            r.prop(js, "position", slider=True)
            r = col.row(align=True)
            r.active = movable
            r.prop(js, "position_mm")
            op = r.operator("joint_maker.nudge", text="", icon='TRIA_DOWN'); op.move = -1
            op = r.operator("joint_maker.nudge", text="", icon='TRIA_UP'); op.move = 1
            r = col.row(align=True)
            r.prop(js, "tilt_x")
            r.prop(js, "tilt_y")
            r = col.row(align=True)
            r.prop(js, "rotation")
            op = r.operator("joint_maker.nudge", text="", icon='LOOP_BACK'); op.turn = -1
            op = r.operator("joint_maker.nudge", text="", icon='LOOP_FORWARDS'); op.turn = 1
            for (letter, _d), attr, step in zip(offset_axes(obj, js), ("offset_a", "offset_b"),
                                                 ("off_a", "off_b")):
                r = col.row(align=True)
                r.prop(js, attr, text=f"Offset {letter} (mm)")
                op = r.operator("joint_maker.nudge", text="", icon='TRIA_LEFT'); setattr(op, step, -1)
                op = r.operator("joint_maker.nudge", text="", icon='TRIA_RIGHT'); setattr(op, step, 1)
            r = col.row(align=True)
            r.operator("joint_maker.center", icon='PIVOT_BOUNDBOX')
            r.operator("joint_maker.reset_offset", text="Reset", icon='LOOP_BACK')
            r = col.row(align=True)
            r.prop(js, "nudge_mm")
            r.prop(js, "nudge_deg")
            r = col.row(align=True)
            r.prop(js, "flip", toggle=True)
            r.prop(js, "show_gizmo", toggle=True, icon='GIZMO')
            if js.show_gizmo:
                r.prop(js, "gizmo_size", slider=True)

        # ---- size and cutting
        body = _fold(lay, "JM_size", "Size & cutting", 'MOD_BOOLEAN')
        if body:
            col = body.column(align=True)
            col.row(align=True).prop(js, "radius_mode", expand=True)
            col.prop(js, "joint_scale", slider=True)
            if js.joint_scale < 0.999:
                wb = col.box()
                wb.row(align=True).prop(js, "waist_taper", expand=True)
                if js.waist_taper == 'CUSTOM':
                    wb.prop(js, "taper_len")
                wb.prop(js, "keep_range")
            sb = col.box()
            sb.row(align=True).prop(js, "solver_mode", expand=True)
            bad = mesh_problems(obj)
            if bad:
                r = sb.row(align=True)
                r.label(text=f"{bad} non-manifold edges", icon='ERROR')
                r.operator("joint_maker.repair", icon='TOOL_SETTINGS')
            lb = col.box()
            lb.prop(js, "limit_reach_on", icon='MESH_CYLINDER')
            if js.limit_reach_on:
                sub = lb.column(align=True)
                sub.prop(js, "limit_reach")
                sub.prop(js, "limit_bevel")
            fb = col.box()
            fb.prop(js, "fit_cutter", icon='MOD_SHRINKWRAP')
            if js.fit_cutter:
                fb.prop(js, "fit_margin")

        # ---- tolerances
        body = _fold(lay, "JM_tol", "Tolerances", 'DRIVER_DISTANCE')
        if body:
            col = body.column(align=True)
            col.prop(js, "gap")
            col.prop(js, "pin_clearance")

        # ---- shape
        body = _fold(lay, "JM_shape", "Shape", 'MESH_CYLINDER')
        if body:
            col = body.column(align=True)
            if js.joint_type == 'SHAPE':
                col.prop(js, "shape_preset", text="")
                if js.shape_preset == 'CUSTOM':
                    col.prop(js, "shape_object", text="")
                    col.row(align=True).prop(js, "shape_axis", expand=True)
                col.row(align=True).prop(js, "shape_size_mode", expand=True)
                col.prop(js, "shape_fit" if js.shape_size_mode == 'FIT' else "shape_dia")
                col.prop(js, "shape_height")
                col.prop(js, "shape_limit")
            is_ball = js.joint_type == 'BALL' or (js.joint_type == 'DOUBLE' and js.link_end == 'BALL')
            if js.joint_type == 'DOUBLE':
                col.row(align=True).prop(js, "link_end", expand=True)
                col.prop(js, "link_length")
                if js.link_end == 'PIVOT':
                    row = col.row(align=True)
                    row.prop(js, "pivot_twist")
                    op = row.operator("joint_maker.set_twist", text="0\u00b0"); op.angle = 0.0
                    op = row.operator("joint_maker.set_twist", text="90\u00b0"); op.angle = 90.0
            if is_ball:
                col.prop(js, "ball_size", slider=True)
                col.prop(js, "stem_size", slider=True)
                col.row(align=True).prop(js, "ball_control", expand=True)
                col.prop(js, "snap_lip" if js.ball_control == 'LIP' else "swing")
                if js.joint_type == 'BALL':
                    col.prop(js, "neck_length")
                col.prop(js, "socket_wall", text="Socket wall (mm, 0 = full)")
                box = col.box()
                box.prop(js, "snap_relief")
                if js.snap_relief:
                    sub = box.column(align=True)
                    sub.prop(js, "slots")
                    sub.prop(js, "slot_w")
                    sub.prop(js, "slot_depth", slider=True)
                    sub.prop(js, "slot_angle")
            elif js.joint_type == 'DOUBLE' and js.link_end == 'CLIP':
                col.prop(js, "tongue_width", text="Link thickness", slider=True)
                col.prop(js, "axle_size", slider=True)
                col.prop(js, "clip_wall", slider=True)
                col.prop(js, "snap")
                col.row(align=True).prop(js, "mouth_side", expand=True)
                gb = col.box()
                gb.prop(js, "gear_mesh")
                if js.gear_mesh:
                    sub = gb.column(align=True)
                    sub.prop(js, "gear_module")
                    sub.prop(js, "gear_backlash")
            elif js.joint_type != 'SHAPE':
                col.prop(js, "tongue_width", slider=True)
                col.row(align=True).prop(js, "pin_style", expand=True)
                col.prop(js, "pin_size", slider=True)
                if js.pin_style == 'CONE':
                    col.prop(js, "cone_angle")
                elif js.pin_style == 'PIN':
                    col.prop(js, "press_fit")
                    col.prop(js, "head_tol")
            col.prop(js, "segments")

        # ---- array / curve / path
        body = _fold(lay, "JM_array", "Array", 'MOD_ARRAY', closed=True)
        if body:
            c = body.column(align=True)
            c.prop(js, "array_count")
            if js.array_count > 1:
                c.row(align=True).prop(js, "array_mode", expand=True)
                if js.array_mode == 'SPACING':
                    c.prop(js, "array_spacing")
                c.prop(js, "array_twist")
        body = _fold(lay, "JM_curve", "Placement curve", 'CURVE_BEZCURVE', closed=True)
        if body:
            body.prop(js, "place_curve", text="")
            if js.place_curve:
                c = body.column(align=True)
                r = c.row(align=True)
                r.prop(js, "curve_start", slider=True)
                r.prop(js, "curve_end", slider=True)
                c.prop(js, "curve_snap")
                c.label(text="Joints, spread and spacing come from Array", icon='INFO')
        body = _fold(lay, "JM_path", "Path (pose preview)", 'CURVE_DATA', closed=True)
        if body:
            body.prop(js, "path", text="")
            if js.path:
                c = body.column(align=True)
                c.prop(js, "path_roll")
                c.prop(js, "path_hide_straight")

        # ---- cross-section
        body = _fold(lay, "JM_section", "Cross-section", 'MOD_BOOLEAN', closed=True)
        if body:
            body.prop(js, "section_show", toggle=True, icon='HIDE_OFF' if js.section_show else 'HIDE_ON')
            c = body.column(align=True)
            c.active = js.section_show
            if js.array_count > 1:
                c.prop(js, "section_joint")
            c.prop(js, "section_offset")
            c.prop(js, "section_angle")
            r = c.row(align=True)
            r.prop(js, "section_tilt")
            op = r.operator("joint_maker.section_tilt", text="Along"); op.tilt = 0.0
            op = r.operator("joint_maker.section_tilt", text="Across"); op.tilt = 90.0
            r = c.row(align=True)
            r.prop(js, "section_flip", toggle=True)
            r.prop(js, "section_hide_model", toggle=True)

        # ---- readout
        if js.info:
            body = _fold(lay, "JM_info", "Info", 'INFO')
            if body:
                b = body.box()
                for line in js.info.split(" | "):
                    b.label(text=line)

        row = lay.row(align=True)
        row.prop(js, "show_cutter", toggle=True)
        row.prop(js, "show_result", toggle=True)
        row = lay.row(align=True)
        row.prop(js, "live", toggle=True)
        row.operator("joint_maker.update", text="", icon='FILE_REFRESH')

        lay.separator()
        lay.prop(js, "separate")
        row = lay.row(align=True)
        row.scale_y = 1.4
        row.operator("joint_maker.apply", icon='CHECKMARK')
        row.operator("joint_maker.remove", text="", icon='TRASH')
