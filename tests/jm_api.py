"""Loads the Joint Maker package from a source folder and exposes the internals the
regression tests use under one namespace. Run tests as:
    blender -b --factory-startup --python tests/<test>.py -- <folder containing joint_maker/>
"""
import importlib
import sys
import types


def load(root):
    sys.path.insert(0, root)
    pkg = importlib.import_module("joint_maker")
    from joint_maker import gizmos, ui
    from joint_maker.core import frame, rebuild, state
    from joint_maker.geometry import mesh
    return types.SimpleNamespace(
        register=pkg.register, unregister=pkg.unregister,
        rebuild=rebuild.rebuild, _linked_shells=mesh.linked_shells,
        cylinder_frame=frame.cylinder_frame, axis_world=frame.axis_world, _ends=frame.axis_ends,
        offset_axes=frame.offset_axes, mm_per_position=frame.mm_per_position,
        _LAST_FRAMES=state.LAST_FRAMES,
        _giz_get_slide=gizmos._giz_get_slide, _giz_set_slide=gizmos._giz_set_slide,
        _giz_get_turn=gizmos._giz_get_turn, _giz_set_turn=gizmos._giz_set_turn,
        _giz_offset_handlers=gizmos._giz_offset_handlers,
        JOINTMAKER_PT_panel=ui.JOINTMAKER_PT_panel,
    )
