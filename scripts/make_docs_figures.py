#!/usr/bin/env python3
"""Builds the documentation figures in docs/img/.

    python3 scripts/make_docs_figures.py [--blender PATH] [--no-render] [--only name,name]

1. Runs scripts/docs_render.py in a background Blender; it builds every scene with the add-on
   itself and renders one snapshot ("cell") per image into docs/img/_cells/.
2. Stacks the cells into numbered figures: one row per option, a numbered badge and a caption
   on the left. Dropdown-style settings read top to bottom as Fig. 1, 2, 3 ...

Needs Pillow (pip install pillow). Set BLENDER, or pass --blender, if Blender isn't in the
default macOS location.
"""
import argparse
import math
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG = os.path.join(ROOT, "docs", "img")
CELLS = os.path.join(IMG, "_cells")
SS = 2                                                  # cells are rendered at SS x their size

INK, MUTED, ACCENT = (31, 41, 51), (96, 108, 122), (47, 111, 214)
LINE, ROW_A, ROW_B = (221, 226, 232), (255, 255, 255), (247, 249, 251)
GUTTER, MARGIN, GAP = 262, 14, 8

# name -> (column titles, rows); a row is (caption, [cell ids])
FIGURES = {
    "gs-steps": ([""], [
        ("Select a plain part", ["gs_plain"]),
        ("Add Joint: the cutter (red wire) is attached with a live Boolean", ["gs_cutter"]),
        ("Apply: the part splits into separate pieces (pulled apart here)", ["gs_parts"]),
    ]),
    "pivot-pins": (["Assembled", "Section"], [
        ("Cones: print-in-place, no supports", ["pp_cone_ext", "pp_cone_sec"]),
        ("Rod: a straight pin", ["pp_rod_ext", "pp_rod_sec"]),
        ("Separate: holes plus a headed pin you print on its own", ["pp_pin_ext", "pp_pin_sec"]),
    ]),
    "ball-control": (["Section", "Bent to its swing"], [
        ("Set by Swing, 20°", ["bc_sw20_sec", "bc_sw20_pose"]),
        ("Set by Swing, 45°", ["bc_sw45_sec", "bc_sw45_pose"]),
        ("Set by Snap lip, 0.3 mm", ["bc_lip03_sec", "bc_lip03_pose"]),
        ("Set by Snap lip, 0.8 mm", ["bc_lip08_sec", "bc_lip08_pose"]),
    ]),
    "ball-slots": (["Socket from below", "Socket from the side"], [
        ("Snap-fit relief off", ["bs_0_below", "bs_0_side"]),
        ("1 slot: 2 fingers", ["bs_1_below", "bs_1_side"]),
        ("2 slots: 4 fingers", ["bs_2_below", "bs_2_side"]),
        ("3 slots: 6 fingers", ["bs_3_below", "bs_3_side"]),
    ]),
    "double-link": (["Assembled", "Section"], [
        ("Pivot ends: an H-shaped link", ["dj_pivot_ext", "dj_pivot_sec"]),
        ("Ball ends: a dog-bone link", ["dj_ball_ext", "dj_ball_sec"]),
        ("E-clip: a snap-on E-shaped link", ["dj_clip_ext", "dj_clip_sec"]),
        ("E-clip with Gear mesh: both sides bend together", ["dj_gear_ext", "dj_gear_sec"]),
    ]),
    "double-offset": (["Assembled", "Section"], [
        ("Second pivot angle 0°: both pivots bend the same way", ["dt_0_ext", "dt_0_sec"]),
        ("45°", ["dt_45_ext", "dt_45_sec"]),
        ("90°: a universal joint, bending on two axes", ["dt_90_ext", "dt_90_sec"]),
    ]),
    "shape-cutter": (["Pulled apart", "Section"], [
        ("Hook & loop preset", ["sh_hook_ext", "sh_hook_sec"]),
        ("Cone socket preset", ["sh_cone_ext", "sh_cone_sec"]),
        ("Custom object: here a flat lens modelled in the scene", ["sh_custom_ext", "sh_custom_sec"]),
    ]),
    "place-bend": (["Side", "Plan section at the joint"], [
        ("Bend direction 0°", ["pb_0_ext", "pb_0_sec"]),
        ("Bend direction 45°", ["pb_45_ext", "pb_45_sec"]),
        ("Bend direction 90°", ["pb_90_ext", "pb_90_sec"]),
    ]),
    "place-tilt": (["Side view", "Three-quarter view"], [
        ("Tilt X 0°", ["pt_0_ext", "pt_0_3q"]),
        ("Tilt X 20°", ["pt_20_ext", "pt_20_3q"]),
        ("Tilt X 30°", ["pt_30_ext", "pt_30_3q"]),
    ]),
    "place-offset": (["Plan section", "Section along the part"], [
        ("Offset 0: the joint sits on the bounding-box centre, off the part's centre", ["po_0_sec", "po_0_side"]),
        ("After Center on shape: the joint sits on the part's own centre", ["po_1_sec", "po_1_side"]),
    ]),
    "size-scale": (["Assembled", "Section"], [
        ("Joint size 100%", ["sz_100_ext", "sz_100_sec"]),
        ("Joint size 70%: the part slims to a waist", ["sz_70_ext", "sz_70_sec"]),
        ("Joint size 50%", ["sz_50_ext", "sz_50_sec"]),
    ]),
    "size-taper": (["Assembled", "Section"], [
        ("Taper 45° (the default)", ["tp_auto_ext", "tp_auto_sec"]),
        ("Taper Length, 4 mm", ["tp_len_ext", "tp_len_sec"]),
        ("Taper None: a straight step", ["tp_none_ext", "tp_none_sec"]),
        ("None, with Keep range of motion off: the most compact waist", ["tp_nokeep_ext", "tp_nokeep_sec"]),
    ]),
    "size-limit": (["Section along the arm", "Plan section"], [
        ("Limit outer reach off: the cutter bites into the body wall", ["lm_off_sec", "lm_off_plan"]),
        ("On, reach 1 mm: the bite is smaller", ["lm_on_sec", "lm_on_plan"]),
        ("On, reach 1 mm and outer bevel 2 mm: it tapers off before the wall", ["lm_bev_sec", "lm_bev_plan"]),
    ]),
    "size-fit": (["Three-quarter view", "Plan section at the joint"], [
        ("Fit cutter off: the cutter carves a pocket out of the neighbouring block", ["ft_off_ext", "ft_off_plan"]),
        ("Fit cutter on, margin 1 mm: the block is left alone", ["ft_on_ext", "ft_on_plan"]),
    ]),
    "repair": (["Part with stray flaps"], [
        ("Before: red marks show the non-manifold edges", ["rp_before"]),
        ("After Repair Mesh: watertight", ["rp_after"]),
    ]),
    "tol-gap": (["Section, zoomed on the hinge"], [
        ("Gap 0.2 mm", ["tg_2_sec"]),
        ("Gap 0.4 mm", ["tg_4_sec"]),
        ("Gap 0.8 mm", ["tg_8_sec"]),
    ]),
    "tol-snap": (["E-clip socket, zoomed"], [
        ("Snap 0: the mouth is as wide as the axle", ["ts_0_sec"]),
        ("Snap 0.6 mm: narrower, so the link clicks on", ["ts_6_sec"]),
        ("Snap 1.2 mm: very firm", ["ts_12_sec"]),
    ]),
    "array-count": ([""], [
        ("Joints 1", ["ar_1_ext"]),
        ("Joints 2", ["ar_2_ext"]),
        ("Joints 3", ["ar_3_ext"]),
    ]),
    "array-twist": ([""], [
        ("Twist per joint 0°: every joint bends the same way", ["aw_0_ext"]),
        ("Twist per joint 90°: the bend direction alternates", ["aw_90_ext"]),
    ]),
    "array-curve": ([""], [
        ("Pivots placed along the curve", ["ac_hinge_ext"]),
        ("Ball joints placed along the curve", ["ac_ball_ext"]),
        ("Cone-socket shapes placed along the curve", ["ac_shape_ext"]),
    ]),
    "path-pose": (["Without a path", "With a path: the rigid parts follow the curve"], [
        ("Path (pose preview)", ["ap_straight", "ap_posed"]),
    ]),
    "section-controls": (["Face-on", "Three-quarter"], [
        ("Along the joint (Tilt 0°)", ["sc_along_face", "sc_along_3q"]),
        ("Across the joint (Tilt 90°)", ["sc_across_face", "sc_across_3q"]),
        ("Offset 3 mm", ["sc_offset_face", "sc_offset_3q"]),
        ("Rotate 90°", ["sc_rotate_face", "sc_rotate_3q"]),
    ]),
}
HERO = [("hero_a", "Pivot"), ("hero_b", "Ball and socket"), ("hero_c", "E-clip with gears"),
        ("hero_d", "Joints along a curve")]


# ----------------------------------------------------------------------------- drawing helpers
def font(size, bold=False):
    names = (["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc",
              "/Library/Fonts/Arial Bold.ttf", "DejaVuSans-Bold.ttf"] if bold else
             ["/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc",
              "/Library/Fonts/Arial.ttf", "DejaVuSans.ttf"])
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def wrap(draw, text, fnt, width):
    lines, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if draw.textlength(t, font=fnt) <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = word
    return lines + [cur]


def load_cell(cid):
    path = os.path.join(CELLS, cid + ".png")
    if not os.path.exists(path):
        sys.exit(f"missing cell image: {cid} (render failed?)")
    im = Image.open(path).convert("RGB")
    return im.resize((im.width // SS, im.height // SS), Image.LANCZOS)


def compose(name, cols, rows):
    first = load_cell(rows[0][1][0])
    cw, ch = first.size
    ncols = max(len(r[1]) for r in rows)
    head = 40 if any(cols) else 0
    pady = 10
    width = MARGIN + GUTTER + ncols * cw + (ncols - 1) * GAP + MARGIN
    height = head + len(rows) * (ch + 2 * pady)
    im = Image.new("RGB", (width, height), ROW_A)
    d = ImageDraw.Draw(im)
    f_cap, f_num, f_head = font(19), font(22, True), font(17, True)
    for c, title in enumerate(cols):
        if title:
            x = MARGIN + GUTTER + c * (cw + GAP)
            d.text((x + cw / 2, head / 2 + 2), title, font=f_head, fill=MUTED, anchor="mm")
    for i, (caption, cells) in enumerate(rows):
        y0 = head + i * (ch + 2 * pady)
        d.rectangle([0, y0, width, y0 + ch + 2 * pady], fill=ROW_A if i % 2 == 0 else ROW_B)
        d.line([0, y0, width, y0], fill=LINE)
        cy = y0 + pady + ch / 2
        r = 21
        d.ellipse([MARGIN, cy - r, MARGIN + 2 * r, cy + r], fill=ACCENT)
        d.text((MARGIN + r, cy + 1), str(i + 1), font=f_num, fill="white", anchor="mm")
        tx = MARGIN + 2 * r + 12
        lines = wrap(d, caption, f_cap, GUTTER - 2 * r - 14)
        ty = cy - len(lines) * 12
        for ln in lines:
            d.text((tx, ty), ln, font=f_cap, fill=INK)
            ty += 25
        for c, cid in enumerate(cells):
            im.paste(load_cell(cid), (MARGIN + GUTTER + c * (cw + GAP), y0 + pady))
    d.line([0, height - 1, width, height - 1], fill=LINE)
    out = os.path.join(IMG, name + ".png")
    im.save(out, optimize=True)
    return out


def arrow(d, p0, p1, colour, width=7, head=24):
    d.line([p0, p1], fill=colour, width=width)
    ang = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
    a = (p1[0] - head * math.cos(ang - 0.4), p1[1] - head * math.sin(ang - 0.4))
    b = (p1[0] - head * math.cos(ang + 0.4), p1[1] - head * math.sin(ang + 0.4))
    d.polygon([p1, a, b], fill=colour)


def gizmo_schematic():
    """a drawn schematic of the viewport handles (gizmos can't be rendered in a background Blender)"""
    s = 2
    W, H = 640 * s, 400 * s
    im = Image.new("RGB", (W, H), (244, 246, 250))
    d = ImageDraw.Draw(im)
    f, fb, fs = font(20 * s), font(24 * s, True), font(15 * s)
    X = lambda v: v * s
    d.rectangle([X(250), X(40), X(350), X(350)], fill=(150, 168, 196), outline=(40, 50, 70), width=2 * s)
    d.rectangle([X(250), X(168), X(350), X(212)], fill=(228, 233, 241), outline=(40, 50, 70), width=2 * s)
    d.text((X(300), X(190)), "joint", font=fs, fill=(70, 80, 100), anchor="mm")
    d.ellipse([X(206), X(160), X(394), X(220)], outline=(150, 90, 215), width=5 * s)
    arrow(d, (X(300), X(340)), (X(300), X(232)), (240, 140, 30), 6 * s, 22 * s)
    arrow(d, (X(350), X(190)), (X(470), X(190)), (225, 70, 80), 6 * s, 20 * s)
    arrow(d, (X(300), X(190)), (X(246), X(250)), (110, 190, 40), 6 * s, 18 * s)
    d.text((X(366), X(300)), "Slide arrow", font=f, fill=(190, 100, 10))
    d.text((X(366), X(326)), "(position along the part)", font=fs, fill=MUTED)
    d.text((X(30), X(112)), "Rotate ring", font=f, fill=(120, 60, 190))
    d.text((X(30), X(138)), "(bend direction)", font=fs, fill=MUTED)
    d.text((X(478), X(172)), "Offset arrow", font=f, fill=(190, 50, 60))
    d.text((X(478), X(198)), "(red = X)", font=fs, fill=MUTED)
    d.text((X(150), X(262)), "Offset arrow", font=f, fill=(70, 140, 20), anchor="ra")
    d.text((X(150), X(288)), "(green = Y)", font=fs, fill=MUTED, anchor="ra")
    d.text((X(14), X(14)), "Schematic of the viewport handles", font=fb, fill=INK)
    d.text((X(14), X(376)), "Drawn for illustration. They appear on the selected part at its joint.", font=fs, fill=MUTED)
    im = im.resize((W // s, H // s), Image.LANCZOS)
    out = os.path.join(IMG, "place-gizmos.png")
    im.save(out, optimize=True)
    return out


def hero():
    tile, gap, top = 420, 14, 112
    W = 2 * tile + 3 * gap
    H = top + 2 * tile + 3 * gap
    im = Image.new("RGB", (W, H), (244, 246, 250))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, top - gap], fill=(31, 41, 51))
    d.text((gap + 6, 34), "Joint Maker", font=font(44, True), fill="white", anchor="lm")
    d.text((gap + 8, 78), "3D-printable joints for any part, live in Blender", font=font(21), fill=(190, 205, 225), anchor="lm")
    chip = font(18, True)
    for i, (cid, label) in enumerate(HERO):
        x = gap + (i % 2) * (tile + gap)
        y = top + (i // 2) * (tile + gap)
        t = load_cell(cid)
        im.paste(t, (x, y))
        tw = d.textlength(label, font=chip)
        d.rounded_rectangle([x + 10, y + tile - 40, x + 10 + tw + 22, y + tile - 10], radius=8, fill=(31, 41, 51))
        d.text((x + 21, y + tile - 25), label, font=chip, fill="white", anchor="lm")
    out = os.path.join(IMG, "hero.png")
    im.save(out, optimize=True)
    return out


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blender", default=os.environ.get("BLENDER", "/Applications/Blender.app/Contents/MacOS/Blender"))
    ap.add_argument("--no-render", action="store_true", help="reuse the cell images already in docs/img/_cells")
    ap.add_argument("--only", default="", help="comma-separated figure names (default: all)")
    a = ap.parse_args()
    os.makedirs(CELLS, exist_ok=True)
    if not a.no_render:
        cmd = [a.blender, "--background", "--factory-startup", "--python",
               os.path.join(ROOT, "scripts", "docs_render.py"), "--", ROOT, CELLS]
        res = subprocess.run(cmd, capture_output=True, text=True)
        tail = [l for l in res.stdout.splitlines() if l.startswith("CELLS")]
        print(tail[-1] if tail else res.stdout[-800:])
        if res.returncode != 0 or not tail or "failed 0" not in tail[-1]:
            sys.exit("rendering the snapshots failed:\n" + res.stdout[-1500:] + res.stderr[-800:])
    only = {n for n in a.only.split(",") if n}
    made = []
    for name, (cols, rows) in FIGURES.items():
        if only and name not in only:
            continue
        made.append(compose(name, cols, rows))
    if not only or "place-gizmos" in only:
        made.append(gizmo_schematic())
    if not only or "hero" in only:
        made.append(hero())
    for m in made:
        print("wrote", os.path.relpath(m, ROOT), f"({os.path.getsize(m) // 1024} KB)")


if __name__ == "__main__":
    main()
