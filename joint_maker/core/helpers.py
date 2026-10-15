"""Helper objects (cutter pieces, pins, previews) and the active target."""

import bpy
from mathutils import Matrix
from ..constants import ALL_MODS


def new_helper(obj, name, coll):
    ob = bpy.data.objects.new(name, bpy.data.meshes.new(name))
    coll.objects.link(ob)
    ob.parent = obj
    ob.matrix_parent_inverse = Matrix()
    ob.hide_render = True
    ob.display_type = 'WIRE'
    ob["joint_maker_helper"] = True
    return ob


def cutter_collection(obj, js):
    c = js.cutter_coll
    if c is None or c.name not in bpy.data.collections:
        c = bpy.data.collections.new(obj.name + "_JointCutter")
        (obj.users_collection[0] if obj.users_collection else bpy.context.scene.collection).children.link(c)
        js.cutter_coll = c
    return c


def part_objects(obj):
    return sorted((o for o in bpy.data.objects if o.parent == obj and o.get("joint_maker_part")),
                  key=lambda o: o.name)


def remove_helpers(obj):
    js = obj.joint_maker
    for name in ALL_MODS:
        m = obj.modifiers.get(name)
        if m:
            obj.modifiers.remove(m)
    for nm in (obj.name + "_JointGears", obj.name + "_JointClip"):
        ob = bpy.data.objects.get(nm)
        if ob is not None and ob.get("joint_maker_helper"):
            me = ob.data
            bpy.data.objects.remove(ob, do_unlink=True)
            if me.users == 0:
                bpy.data.meshes.remove(me)
    sec = bpy.data.objects.get(obj.name + "_Section")
    if sec is not None and sec.get("joint_maker_helper"):
        me = sec.data
        bpy.data.objects.remove(sec, do_unlink=True)
        if me.users == 0:
            bpy.data.meshes.remove(me)
    for ob in [o for o in bpy.data.objects
               if (o.name.startswith(obj.name + "_JointFit") or o.name.startswith(obj.name + "_JointLimit"))
               and o.get("joint_maker_helper")]:
        me = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        if me.users == 0:
            bpy.data.meshes.remove(me)
    if js.pins is not None:
        me = js.pins.data
        bpy.data.objects.remove(js.pins, do_unlink=True)
        if me.users == 0:
            bpy.data.meshes.remove(me)
    c = js.cutter_coll
    if c is not None:
        for ob in list(c.objects):
            me = ob.data
            bpy.data.objects.remove(ob, do_unlink=True)
            if me and me.users == 0:
                bpy.data.meshes.remove(me)
        bpy.data.collections.remove(c)
    js.cutter_coll = None
    js.pins = None
    if js.posed is not None:
        me = js.posed.data
        bpy.data.objects.remove(js.posed, do_unlink=True)
        if me.users == 0:
            bpy.data.meshes.remove(me)
        js.posed = None
    obj.display_type = 'TEXTURED'
    for ob in part_objects(obj):
        me = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        if me.users == 0:
            bpy.data.meshes.remove(me)


def target_object(context):
    ob = context.active_object
    if ob is None or ob.type != 'MESH' or ob.get("joint_maker_helper") or "_Cut" in ob.name \
            or ob.name.endswith("_JointPins"):
        return None
    return ob
