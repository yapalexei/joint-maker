# Changelog

## 1.0.1
- Cross-section preview: fixed wrong cap faces that appeared when the plane passed exactly
  through mesh vertices (a ball's equator, mirror-symmetric parts).
- Cross-section colours now follow position along the joint (lower part first), and separate
  pins are always red. Whole pins are hidden while the section is shown, so the cut pin is visible.
- Documentation: a guide with a figure for each feature (docs/), and a script that renders the
  figures from the add-on itself.

## 1.0.0
- Code split into modules by responsibility (geometry, joints, core, properties, operators,
  ui, gizmos, handlers). Behaviour is unchanged; the regression tests pass.
- Prepared for publishing: GPL-3.0 licence, README, build script, headless test suite.
- Requires Blender 4.5+ (Manifold boolean solver).

## 0.6.1
- Link length can go down to each double joint's real geometric minimum. The bend range is
  reduced to match and shown in the panel.

## 0.6.0
- Limit outer reach with an outer bevel, so cuts don't reach neighbouring geometry.

## 0.5.0
- Live cross-section preview. All panel sections are collapsible.

## 0.4.0
- Placement curve: array joints placed along a curve, snapped to the cross-section.
- Tilt X / Y.

## 0.3.0
- Shape cutter joint type with bundled Hook & loop and Cone socket presets, and custom
  mesh shapes.

## 0.2.x
- Automatic Exact-solver fallback and Repair Mesh for meshes that aren't watertight.
- Shrink-fit cutter, waist taper modes, cross-section-based joint radius.
- Off-centre offsets and Center on shape; viewport gizmos with a fixed screen size.
- Joint size with tapered waist.

## 0.1.x
- Pivot, ball, double (pivot / ball / E-clip with gears) joints; separate pins; snap-fit
  relief; arrays and path posing.
