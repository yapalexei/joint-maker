import sys, bpy, bmesh, importlib, math, time
from mathutils import Vector, Matrix
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import jm_api
jm = jm_api.load(sys.argv[-1]); jm.register()
bpy.ops.mesh.primitive_cylinder_add(radius=8.5, depth=70, vertices=96)
ob = bpy.context.active_object; js = ob.joint_maker
with bpy.context.temp_override(active_object=ob, object=ob):
    bpy.ops.joint_maker.add()
js.live = False; js.joint_type = 'SHAPE'
def check(tag):
    t = time.time(); res = jm.rebuild(ob)
    dg = bpy.context.evaluated_depsgraph_get(); ev = ob.evaluated_get(dg); me = ev.to_mesh()
    bm = bmesh.new(); bm.from_mesh(me); ev.to_mesh_clear()
    n = len(jm._linked_shells(bm)); nm = sum(1 for e in bm.edges if not e.is_manifold); bm.free()
    print(f"SH {tag}: parts {n} nm {nm} solver {ob.modifiers['JointMaker'].solver} {time.time()-t:.2f}s | {js.info} | warn: {js.warning}")
for preset in ('HOOK', 'CONE'):
    js.shape_preset = preset
    js.shape_size_mode = 'FIT'; js.shape_fit = 1.15; check(f"{preset} fit 1.15")
    js.flip = True; js.rotation = 45; check(f"{preset} flipped, turned 45"); js.flip = False; js.rotation = 0
    js.shape_size_mode = 'FIXED'; js.shape_dia = 19.0; check(f"{preset} fixed 19 mm")
    js.shape_dia = 15.0; check(f"{preset} fixed 15 mm (narrower than the part)")
    js.shape_size_mode = 'FIT'; js.fit_cutter = True; check(f"{preset} with fit-to-shape"); js.fit_cutter = False
    js.array_count = 2; js.array_mode = 'FIT'; check(f"{preset} array x2"); js.array_count = 1
# custom object: a torus-shaped cutout ring around a short peg = a simple swivel
bpy.ops.mesh.primitive_torus_add(major_radius=6, minor_radius=1.0, location=(40, 0, 0))
tor = bpy.context.active_object
bpy.context.view_layer.objects.active = ob
js.shape_preset = 'CUSTOM'; js.shape_object = tor; js.shape_axis = 'Z'; js.shape_fit = 1.15
check("custom object (torus)")
js.shape_object = None; check("custom with no object")
# apply, end to end
js.shape_preset = 'CONE'
with bpy.context.temp_override(active_object=ob, object=ob):
    bpy.ops.joint_maker.apply()
print("SH applied ->", sorted(o.name for o in bpy.data.objects if o.name.startswith("Cylinder")))
jm.unregister()
