"""Joint type registry. To add a type: write build_<name>(p, F) ->
(cut_pieces, pin_bm, info, warn) in its own module and list it here."""

from .ball import build_ball
from .double import build_double
from .hinge import build_hinge
from .shape import build_shape


JOINT_BUILDERS = {"HINGE": build_hinge, "BALL": build_ball, "DOUBLE": build_double, "SHAPE": build_shape}


JOINT_TYPES = [
    ("HINGE", "Pivot (print-in-place)", "Knuckle hinge with built-in pins, prints assembled"),
    ("BALL", "Ball and socket (print-in-place)", "Ball on a neck inside a domed socket"),
    ("DOUBLE", "Double joint (print-in-place)", "Two joints joined by a link: pivots, balls or E-clip"),
    ("SHAPE", "Shape cutter", "Use a ready-made cutout shape (bundled presets or any mesh object)"),
    # coming next: PIN (assemblable), DOUBLE_FLOAT, DOUBLE_90
]
