import sys, bpy, bmesh, importlib, math
from mathutils import Vector
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import jm_api
jm = jm_api.load(sys.argv[-1]); jm.register()
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
# body + arm as one mesh
bpy.ops.mesh.primitive_cylinder_add(radius=20, depth=80, vertices=96, location=(0, 0, 0)); body = bpy.context.active_object
bpy.ops.mesh.primitive_cylinder_add(radius=6, depth=50, vertices=64, location=(35, 0, 0), rotation=(0, math.radians(90), 0)); arm = bpy.context.active_object
md = body.modifiers.new("u", 'BOOLEAN'); md.operation = 'UNION'; md.object = arm; md.solver = 'EXACT'
bpy.context.view_layer.objects.active = body; bpy.ops.object.modifier_apply(modifier="u")
bpy.data.objects.remove(arm)
body.name = "body"
BODY_VOL = math.pi * 20 ** 2 * 80

def vol_below(me_bm, xcut):
    """volume of the part of the mesh with x < xcut (sliced and capped)"""
    b = me_bm.copy()
    r = bmesh.ops.bisect_plane(b, geom=b.verts[:] + b.edges[:] + b.faces[:], plane_co=(xcut, 0, 0), plane_no=(1, 0, 0), clear_outer=True)
    cut = [e for e in r["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
    if cut: bmesh.ops.triangle_fill(b, use_beauty=True, edges=cut, normal=(1, 0, 0))
    v = b.calc_volume(); b.free(); return v

with bpy.context.temp_override(active_object=body, object=body):
    bpy.ops.joint_maker.add()
js = body.joint_maker; js.live = False
js.axis = 'X'; js.mm_per_unit = 1.0; js.position = (24 + 20) / 80   # joint 4 mm outside the body
js.joint_type = 'HINGE'; js.joint_scale = 0.6

def run(tag):
    jm.rebuild(body)
    dg = bpy.context.evaluated_depsgraph_get(); ev = body.evaluated_get(dg); me = ev.to_mesh()
    bm = bmesh.new(); bm.from_mesh(me); ev.to_mesh_clear()
    parts = len(jm._linked_shells(bm)); nm = sum(1 for e in bm.edges if not e.is_manifold)
    lost = BODY_VOL - vol_below(bm, 19.99)
    bm.free()
    print(f"LT {tag}: parts {parts} nm {nm} | material removed from the BODY (x<20): {lost:7.1f} mm3 | warn: {js.warning}")
    print(f"LT     {[i for i in js.info.split(' | ') if 'limit' in i or 'waist' in i]}")

js.limit_reach_on = False; js.fit_cutter = False; run("limit OFF")
js.fit_cutter = True; run("fit cutter only")
js.fit_cutter = False; js.limit_reach_on = True
for reach, bev in ((1.0, 0.0), (0.5, 0.0), (1.0, 2.0), (1.0, 4.0)):
    js.limit_reach, js.limit_bevel = reach, bev; run(f"limit reach {reach} mm, outer bevel {bev} mm")
js.fit_cutter = True; js.limit_reach, js.limit_bevel = 1.0, 2.0; run("limit + fit together")
for jt, kw in (('BALL', {}), ('DOUBLE', {'link_end': 'CLIP'}), ('SHAPE', {'shape_preset': 'HOOK'})):
    js.joint_type = jt
    for k, v in kw.items(): setattr(js, k, v)
    js.limit_reach_on = False; js.fit_cutter = False; run(f"{jt} limit OFF")
    js.limit_reach_on = True; js.limit_reach, js.limit_bevel = 1.0, 2.0; run(f"{jt} limit 1 mm + bevel 2")
jm.unregister()
