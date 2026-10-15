# Joint Maker

![Joint Maker: pivot, ball and socket, geared E-clip and joints along a curve](docs/img/hero.png)

A Blender add-on that turns a part, such as a limb, tail, finger or tube, into a 3D-printable joint.
You pick a joint type and tune it in the sidebar. A live boolean cutter shows the result as you
go. **Apply** splits the part into separate pieces that print interlocked (print-in-place) or
snap together.

The cutter is the *gap* geometry. Subtracting it leaves pieces that don't touch, shaped so
they can only move the way the joint allows. Every clearance is set in printed millimetres.

## Documentation

**[Read the docs →](docs/README.md)**: a step-by-step guide with a visual snapshot for each feature.

| | |
|---|---|
| [Getting started](docs/01-getting-started.md) | Install, units, adding a joint, the panel at a glance, Apply |
| [Joint types](docs/02-joint-types.md) | Pivot, ball and socket, double joints, shape cutter |
| [Placement](docs/03-placement.md) | Position, bend direction, tilt, offsets, gizmos |
| [Size and cutting](docs/04-size-and-cutting.md) | Joint size and taper, limit outer reach, fit cutter, solver and repair |
| [Tolerances and printing](docs/05-tolerances.md) | Gaps, press fit, snap, backlash, printing tips |
| [Arrays, curves and posing](docs/06-arrays-curves-posing.md) | Several joints on one part, joints along a curve, pose preview |
| [Cross-section](docs/07-cross-section.md) | Slicing the live result to check the inside |
| [Troubleshooting](docs/08-troubleshooting.md) | What each warning means |

## What it does

### Joint types ([details](docs/02-joint-types.md))

| Type | What it makes |
|---|---|
| **Pivot** | Knuckle hinge with cone pins, a rod, or a separate headed pin (assemblable, with press fit) |
| **Ball and socket** | Ball on a neck in a domed socket. Optional snap-fit relief slots, socket wall thickness and a direct snap-lip setting |
| **Double joint** | Two joints joined by a link. The link ends can be **Pivot** (H link, optional 90° offset), **Ball** (dog-bone) or **E-clip** (snap-on E link, optional meshing gears so both sides bend together) |
| **Shape cutter** | A ready-made cutout shape. Two bundled presets (Hook & loop, Cone socket), or use any mesh in your scene |

### Placing joints ([details](docs/03-placement.md), [arrays and curves](docs/06-arrays-curves-posing.md))

- **Placement:** axis, position (slider or exact mm), bend direction, tilt on both cross axes,
  and off-centre offsets. **Center on shape** snaps the joint onto the middle of the part's
  cross-section. Viewport gizmos let you slide, offset and rotate the joint directly.
- **Array:** several joints along one part, spread evenly or at a fixed spacing, with an
  optional twist per joint.
- **Placement curve:** put the array's joints along a curve, each one square to it and sized
  from the part's cross-section at that spot. Good for curved, tapering parts like tails. An
  object holds one joint setup, so separate each appendage into its own object.
- **Path (pose preview):** lay the finished chain along a curve as rigid parts to see how it
  moves. **Apply** produces the parts already posed.

### Keeping cuts tidy ([details](docs/04-size-and-cutting.md))

- **Joint size** makes the joint smaller than the part. The part slims to a waist around the
  joint, with a 45°, custom-length or square taper.
- **Limit outer reach** trims every cutter to a tube just past the part's surface. An optional
  outer bevel tapers the cut off, so neighbouring geometry isn't cut, such as the body around a
  shoulder joint.
- **Fit cutter to shape** trims the cutters to a tight hull around the part at each joint.
- **Solver: Auto** uses Blender's fast Manifold solver on watertight meshes and falls back to
  Exact otherwise. **Repair Mesh** fixes common problems (stray flaps, small holes, flipped
  normals) so the fast solver can be used.

### Checking the result ([details](docs/07-cross-section.md))

- **Cross-section** slices the result live, with each part in its own colour. You control the
  slice position, rotation and tilt, and which joint is sliced.
- The **Info** box reports the actual sizes, the clearances and the range of motion. Warnings
  flag anything likely to fuse, break or collide ([what they mean](docs/08-troubleshooting.md)).

## Requirements

Blender **4.5** or newer.

## Install

1. Download `joint_maker-<version>.zip` (or build it, see below).
2. In Blender: **Edit → Preferences → Get Extensions →** ▾ (top right) **→ Install from Disk…**
   and pick the zip.
3. Open the **Joints** tab in the 3D View sidebar (**N**).

## Quick start

1. Select the part and set its axis (X/Y/Z), then press **Add Joint**.
2. Pick the joint type and adjust placement, size, tolerances and shape. The result updates
   live.
3. Check the inside with **Cross-section**.
4. Press **Apply** to bake the cut and split the part into its printable pieces. Separate pins
   come out as their own objects.

Tips:

- Set **1 unit = N mm** so the printed size shown in the panel is right. Very small parts are
  assumed to be 20 mm across until you change it.
- Printed holes usually come out a little small. If separate pins won't go in, raise
  **Press fit** to about 0.1–0.2 mm. Print-in-place joints usually need a gap of 0.3–0.4 mm.
  See [Tolerances and printing](docs/05-tolerances.md).

## Project layout

```
joint_maker/          the add-on (this folder is what gets packaged)
  __init__.py         registration
  properties.py       per-object settings and live-update callbacks
  operators.py        panel buttons
  ui.py               the sidebar panel
  gizmos.py           viewport handles
  handlers.py         app handlers
  constants.py
  geometry/           bmesh building blocks, plane sections, mesh repair, STL reading
  joints/             one module per joint type; joints/__init__.py is the type registry
  core/               placement, array/curve layout, rebuild, cutter trimming, previews
  shapes/             bundled cutout shapes (STL)
docs/                 the documentation; docs/img holds the figures
tests/                headless regression tests (run in a background Blender)
scripts/              build.sh (test + build + validate), and the docs figure generator
```

### Adding a joint type

Write a module in `joints/` with a builder `build_<name>(p, F)` that returns
`(cut_pieces, pin_bmesh, info, warnings)`. `F` maps the joint frame into the part's local
space: Z is the part axis, X is the hinge axis, and the origin is the joint centre. Then register
the builder in `joints/__init__.py` (`JOINT_BUILDERS` and `JOINT_TYPES`).

## Development

```
tests/run_all.sh                    # runs every regression test in a background Blender
scripts/build.sh                    # runs the tests, then builds and validates dist/joint_maker-<version>.zip
python3 scripts/make_docs_figures.py   # rebuilds docs/img (needs Pillow: pip install pillow)
```

Set `BLENDER=/path/to/blender` if Blender isn't in the default macOS location. See
[Rebuilding the figures](docs/08-troubleshooting.md#rebuilding-the-figures) for how the docs
images are made.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
