import sys, bpy, bmesh, importlib, math
from mathutils import Vector, Matrix
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import jm_api
jm = jm_api.load(sys.argv[-1]); jm.register()
bpy.ops.mesh.primitive_cylinder_add(radius=10, depth=110, vertices=64)
ob = bpy.context.active_object; js = ob.joint_maker
with bpy.context.temp_override(active_object=ob, object=ob):
    bpy.ops.joint_maker.add()
js.live = False

def section_check(tag):
    jm.rebuild(ob)
    sec = bpy.data.objects.get(ob.name + "_Section")
    if sec is None:
        print(f"SC {tag}: no section object | display {ob.display_type}"); return
    F = ob.matrix_world.inverted() @ jm._LAST_FRAMES[ob.as_pointer()][max(0, js.section_joint - 1)]
    rot = F.to_3x3().normalized()
    n = (rot @ (Matrix.Rotation(math.radians(js.section_angle), 3, 'Z') @ Matrix.Rotation(math.radians(js.section_tilt), 3, 'X') @ Vector((0, 1, 0)))).normalized()
    co = F.translation + n * js.section_offset
    d = [ (v.co - co).dot(n) for v in sec.data.vertices ]
    bm = bmesh.new(); bm.from_mesh(sec.data)
    shells = len(jm._linked_shells(bm))
    caps = sum(1 for f in bm.faces if abs((f.calc_center_median() - co).dot(n)) < 1e-4 and abs(abs(f.normal.dot(n)) - 1) < 1e-3)
    mats = sorted({f.material_index for f in bm.faces})
    nm = sum(1 for e in bm.edges if not e.is_manifold)
    bm.free()
    print(f"SC {tag}: section pieces {shells}, max distance past plane {max(d):.4f} (should be <= 0), cap faces {caps}, colours used {mats}, open edges {nm}, model display {ob.display_type}")

js.joint_type = 'HINGE'; js.pin_style = 'CONE'
js.section_show = True; section_check("hinge, along")
js.section_offset = 2.0; section_check("hinge, offset 2 mm")
js.section_offset = 0; js.section_angle = 90; section_check("hinge, rotated 90")
js.section_angle = 0; js.section_tilt = 90; section_check("hinge, across")
js.section_tilt = 0
js.pin_style = 'PIN'; section_check("hinge with separate pin (pin is cut too)")
js.pin_style = 'CONE'
js.joint_type = 'BALL'; section_check("ball")
js.joint_type = 'DOUBLE'; js.link_end = 'CLIP'; js.gear_mesh = True; section_check("geared E-clip")
js.joint_type = 'SHAPE'; js.shape_preset = 'HOOK'; section_check("hook & loop shape")
js.joint_type = 'HINGE'; js.array_count = 3
for jn in (1, 3):
    js.section_joint = jn; section_check(f"3-joint array, slicing joint {jn}")
js.array_count = 1; js.section_joint = 1
js.section_hide_model = False; section_check("hide model off")
js.section_hide_model = True
js.section_show = False
print("SC section off -> object gone:", bpy.data.objects.get(ob.name + "_Section") is None, "| model display", ob.display_type)
js.section_show = True; jm.rebuild(ob)
with bpy.context.temp_override(active_object=ob, object=ob):
    bpy.ops.joint_maker.apply()
print("SC after apply -> section gone:", bpy.data.objects.get("Cylinder_Section") is None, "| parts", sorted(o.name for o in bpy.data.objects))

# ---- panel draw against a checking stand-in layout
class Lay:
    def __init__(self, log): self.log = log; self.active = True; self.scale_y = 1.0
    def _sub(self, *a, **k): return Lay(self.log)
    row = column = box = _sub
    def prop(self, data, name, **k):
        if not hasattr(data, name): raise AttributeError(f"panel uses missing property '{name}'")
        self.log.append(name)
    def operator(self, idname, **k):
        mod, op = idname.split(".")
        if not hasattr(getattr(bpy.ops, mod), op): raise AttributeError(f"panel uses missing operator '{idname}'")
        class O: pass
        return O()
    def label(self, **k): pass
    def separator(self, **k): pass
    def panel(self, idname, default_closed=False):
        self.log.append("panel:" + idname)
        return Lay(self.log), Lay(self.log)
bpy.ops.mesh.primitive_cylinder_add(radius=10, depth=110); c2 = bpy.context.active_object
bpy.context.view_layer.objects.active = c2
with bpy.context.temp_override(active_object=c2, object=c2):
    bpy.ops.joint_maker.add()
j2 = c2.joint_maker
class Ctx: pass
ctx = Ctx(); ctx.active_object = c2; ctx.mode = 'OBJECT'
total = set()
for jt, extra in [('HINGE', {'pin_style': 'PIN'}), ('BALL', {'snap_relief': True}), ('DOUBLE', {'link_end': 'CLIP', 'gear_mesh': True}),
                  ('DOUBLE', {'link_end': 'PIVOT'}), ('SHAPE', {'shape_preset': 'CUSTOM'}), ('HINGE', {'joint_scale': 0.6, 'array_count': 3, 'fit_cutter': True})]:
    j2.joint_type = jt
    for k, v in extra.items(): setattr(j2, k, v)
    log = []
    try:
        jm.JOINTMAKER_PT_panel.draw(type("P", (), {"layout": Lay(log)})(), ctx)
        total |= set(log)
        print(f"PN {jt} {list(extra.values())[0]}: draw OK, {len([x for x in log if not x.startswith('panel:')])} controls, sections {[x[6:] for x in log if x.startswith('panel:')]}")
    except Exception as e:
        print("PN draw FAILED:", jt, e)
jm.unregister()
