# 8. Troubleshooting

Warnings appear in a box at the top of the panel, one per line. Most say what to change.

## Nothing happens, or the part isn't cut

| Symptom | Cause | Fix |
|---|---|---|
| The joint is added but the part looks unchanged | The mesh isn't watertight and the Manifold solver refuses it | Leave **Solver** on **Auto**, or press **Repair Mesh** ([details](04-size-and-cutting.md#solver-and-repair-mesh)) |
| Cutting is slow (several seconds per change) | A big mesh on the Exact solver | Press **Repair Mesh** so the fast solver can be used, or turn **Live update** off while you adjust |
| The part is cut, but not into the number of pieces you expect | The cutter doesn't reach through, or something joins the pieces | See "parts still joined" below |
| The joint is in the wrong place on a leaning or tapering part | It's on the bounding-box centre | **Center on shape**, or use a [placement curve](06-arrays-curves-posing.md#placement-curve) |

## What the warnings mean

### Parts and cutting

| Warning | Meaning | What to do |
|---|---|---|
| `mesh isn't watertight (N bad edges): using the slower Exact solver` | The Auto solver switched to Exact | **Repair Mesh** |
| `parts still joined (N of M)` | The cutter left the pieces connected; the part is wider somewhere along the joint | Raise **Reach past surface** (Limit outer reach) or the **Margin** (Fit cutter) |
| `the shape doesn't split the part` | A shape cutter that doesn't reach through the part | Make the shape wider, or check that it reaches the outside all round |
| `shape is narrower than the part here: it may not split it` | Fixed shape diameter smaller than the part | Use **Fit**, or a bigger **Diameter** |
| `got N parts instead of M: stray slivers` | A joint is off the part's centre, or the cut leaves thin slivers | Turn on **Snap to section centre**, use **Center on shape**, or reduce the tilt or outer bevel |
| `the steep tilt leaves stray slivers` | Tilt above about 35° | Reduce **Tilt X** / **Tilt Y** |
| `the outer bevel leaves stray slivers` | A large **Outer bevel** | Use a smaller bevel |
| `fit: no geometry found around a joint, cutter left untrimmed` | Fit cutter to shape found nothing near a joint | Check the joint is on the part; turn the option off |

### Size, strength and clearances

| Warning | Meaning | What to do |
|---|---|---|
| `pin much smaller than set: widen the tongue` | The pin had to shrink to fit the tongue | Raise **Tongue width** or lower **Pin size** |
| `tongue too narrow for cone pins` | There's no room for the cone pins | Raise **Tongue width**, or use **Rod** |
| `prong too thin behind the pin head` | A separate pin's head leaves too little wall | Smaller **Pin size**, or a narrower tongue |
| `socket wall under 0.8 mm: fragile` | Thin ball socket | Raise **Socket wall** |
| `clip wall thinner than 0.8 mm` | Thin E-clip sockets | Raise **Clip wall** |
| `clearance only ≈ X mm: may fuse when printed` | A shape preset at a size where its built-in gaps are tiny | Make the shape bigger |
| `joints overlap: more spacing or fewer joints` | Array joints are too close together | Fewer joints, or **Spacing** |
| `under 1 mm of solid between joints: weak` | Array joints leave little material between them | More spacing or fewer joints |
| `joints run past the ends of the curve section` / `array runs past the cylinder ends` | The array doesn't fit | Fewer joints, less spacing, or a longer curve section |

### Ball joints and snap-fits

| Warning | Meaning | What to do |
|---|---|---|
| `weak ball retention (lip under 0.3 mm)` | The socket barely wraps the ball: it may fall out | Raise **Snap lip**, or use a bigger ball, a thinner neck or less swing |
| `lip over 0.6 mm: hard to snap in` | Too much interference (shown with snap-fit relief on) | Lower **Snap lip** or add slots |
| `lip too big for this neck: no swing left` | The neck is too thick for the lip you asked for | Thinner **Stem size**, or a smaller lip |
| `lip too small: capped by the 80° mouth` | The socket mouth can't open any wider | Raise **Snap lip** |
| `swing limited by the stem size` | Thick stem restricts the tilt | Thinner **Stem size** |
| `neck lengthened so the dome clears the body` | A shorter neck would make the parts collide | Nothing: it is the shortest that works. A smaller **Socket wall** allows a shorter neck |

### Links, gears and waists

| Warning | Meaning | What to do |
|---|---|---|
| `link at its minimum N mm` | **Link length** is below what the joint can physically have | Nothing: it is clamped to the minimum shown |
| `short link: bend limited to ±N° ...` | A short link trades bend range for length | Raise **Link length** if you need more bend |
| `only N teeth: smaller module for smoother meshing` | Coarse gears | Lower **Tooth size** |
| `gear teeth reach the axle` | The teeth are too deep for the axle | Smaller **Tooth size** or **Axle size** |
| `short waist: bending range reduced` | **Keep range of motion** is off and the taper is short | Turn it on, or use a longer taper |

### Paths and curves

| Warning | Meaning | What to do |
|---|---|---|
| `path too tight at N joint(s): bend capped at the joint limit` | The path bends further than the joints can | A gentler curve, or more joints |
| `chain runs into itself on this path` | The posed parts collide | A gentler curve, fewer joints, or **Roll** |
| `Path posing is off while joints follow a placement curve` | Both curves are set | Clear one of them |
| `placement curve has no usable points` | The curve object has no spline | Use a curve with at least two points |

## Rebuilding the figures

The figures in these docs are made by a script, so they stay true to what the add-on does. They
need Blender and the [Pillow](https://pypi.org/project/pillow/) image library:

```
pip install pillow
python3 scripts/make_docs_figures.py            # renders the snapshots, then stacks them into docs/img/
```

Use `--only name,name` to rebuild a few figures, `--no-render` to reuse the snapshots already in
`docs/img/_cells/`, and `--blender /path/to/blender` (or the `BLENDER` variable) if Blender isn't in
the default macOS location.

How it works: `scripts/docs_render.py` runs in a background Blender. It builds every scene with
the add-on itself and renders one snapshot per image. `scripts/make_docs_figures.py` then stacks
them into numbered figures: one row per option, a numbered badge and a caption on the left.
To add a figure, define its snapshots in `docs_render.py` (`reg(...)`) and its rows in
`FIGURES` in `make_docs_figures.py`.

## Running the tests

```
tests/run_all.sh        # every regression test, in a background Blender
scripts/build.sh        # the tests, then the extension zip in dist/
```

← [Cross-section](07-cross-section.md) · [Back to the contents](README.md)
