"""App handlers: re-pose chains when the curve they follow is edited."""

import bpy
from .core.rebuild import rebuild


_handler_busy = False


def _on_depsgraph(scene, depsgraph):
    """re-pose chains when the curve they follow is edited"""
    global _handler_busy
    if _handler_busy:
        return
    changed = set()
    for u in depsgraph.updates:
        idb = getattr(u.id, "original", u.id)
        if isinstance(idb, bpy.types.Curve):
            changed.add(idb)
        elif isinstance(idb, bpy.types.Object) and idb.type == 'CURVE':
            changed.add(idb.data)
    if not changed:
        return
    _handler_busy = True
    try:
        for ob in scene.objects:
            js = getattr(ob, "joint_maker", None)
            if js and js.active and js.live and js.path and js.path.data in changed:
                rebuild(ob)
    finally:
        _handler_busy = False


def register():
    if _on_depsgraph not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph)


def unregister():
    for h in list(bpy.app.handlers.depsgraph_update_post):
        if getattr(h, "__name__", "") == "_on_depsgraph":
            bpy.app.handlers.depsgraph_update_post.remove(h)
