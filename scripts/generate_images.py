#!/usr/bin/env python3
"""
Generate the 7 Salawat sequence images as coherent, aniconic illustrations.

These are hand-composed in code (numpy + Pillow) — NOT AI-photoreal renders.
They share one palette (deep blue night + warm gold), one star / particle /
vignette treatment, and simple silhouettes so the 7 frames read as a single
continuous film through the Ken Burns + cross-dissolve montage.

Respectful Islamic constraints are honoured throughout:
  * no faces, no identifiable figures;
  * no depiction of Allah or the Prophet Muhammad (peace be upon him);
  * mosques, believers (from behind, as silhouettes), a Quran and light are
    the only motifs; no text, no watermark.

Output: salawat/images/01.png … 07.png at 1920x1080 (16:9).
Swap any of them for an AI-generated photo of the same scene at will — the
montage just reads 01.png … 07.png in order.
"""

import argparse
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

W, H = 1920, 1080

# Shared palette (deep blue night -> warm gold).
NIGHT_TOP = np.array([10, 16, 44], dtype=np.float32) / 255
NIGHT_BOT = np.array([26, 36, 78], dtype=np.float32) / 255
GOLD = np.array([224, 176, 92], dtype=np.float32) / 255
WARM = np.array([240, 205, 150], dtype=np.float32) / 255
DARK = np.array([6, 9, 20], dtype=np.float32) / 255       # silhouette colour


# ---------------------------------------------------------------- helpers
def to_pil(arr):
    return Image.fromarray((np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8))


def to_arr(pil):
    return np.asarray(pil.convert("RGB"), dtype=np.float32) / 255


def screen(a, b):
    """Screen blend (lighten) of two float arrays."""
    return 1.0 - (1.0 - a) * (1.0 - b)


def vgrad(top, bot):
    t = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
    return (top[None, None, :] * (1 - t) + bot[None, None, :] * t) * np.ones((H, W, 1), np.float32)


def radial_glow(cx, cy, rx, ry, color, strength=1.0):
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xs - cx) / rx) ** 2 + ((ys - cy) / ry) ** 2)
    falloff = np.clip(1.0 - d, 0.0, 1.0) ** 2
    return (color[None, None, :] * (falloff[..., None] * strength)).astype(np.float32)


def add_stars(arr, rng, count=900, ymax=0.72, big=40):
    layer = np.zeros((H, W), np.float32)
    ys = rng.integers(0, int(H * ymax), count)
    xs = rng.integers(0, W, count)
    layer[ys, xs] = rng.uniform(0.4, 1.0, count)
    glow = np.asarray(to_pil(np.repeat(layer[..., None], 3, 2)).filter(
        ImageFilter.GaussianBlur(1.3)), np.float32) / 255
    out = screen(arr, glow * 0.9)
    # a few brighter stars with a wider halo
    layer2 = np.zeros((H, W), np.float32)
    ys = rng.integers(0, int(H * ymax * 0.9), big)
    xs = rng.integers(0, W, big)
    layer2[ys, xs] = 1.0
    halo = np.asarray(to_pil(np.repeat(layer2[..., None], 3, 2)).filter(
        ImageFilter.GaussianBlur(3.5)), np.float32) / 255
    tint = halo * np.array([0.85, 0.9, 1.0], np.float32)[None, None, :]
    return screen(out, tint)


def particles(rng, count, color, xrange=(0.0, 1.0), yrange=(0.0, 1.0), rmax=0.02):
    """Soft floating light particles (optionally confined to a region)."""
    layer = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(layer)
    x0, x1 = int(W * xrange[0]), int(W * xrange[1])
    y0, y1 = int(H * yrange[0]), int(H * yrange[1])
    for _ in range(count):
        x = rng.integers(x0, max(x0 + 1, x1))
        y = rng.integers(y0, max(y0 + 1, y1))
        r = int(rng.uniform(2, 2 + rmax * H))
        a = int(rng.uniform(60, 160))
        d.ellipse([x - r, y - r, x + r, y + r], fill=a)
    blur = np.asarray(layer.filter(ImageFilter.GaussianBlur(2.5)), np.float32) / 255
    return (color[None, None, :] * blur[..., None]).astype(np.float32)


def light_beams(origin, targets, color, spread=26):
    """Volumetric-looking downward light shafts, blurred and screened."""
    layer = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(layer)
    ox, oy = origin
    for tx, ty, inten in targets:
        d.polygon([(ox, oy), (tx - spread, ty), (tx + spread, ty)], fill=int(inten))
    blur = np.asarray(layer.filter(ImageFilter.GaussianBlur(30)), np.float32) / 255
    return (color[None, None, :] * blur[..., None]).astype(np.float32)


def vignette(arr, strength=0.55):
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xs - W / 2) / (W / 2)) ** 2 + ((ys - H / 2) / (H / 2)) ** 2)
    v = 1.0 - strength * np.clip(d - 0.5, 0, 1) ** 1.6
    return arr * v[..., None]


# -------------------------------------------------------------- motifs
def mosque(draw, cx, base_y, scale, color, glow_windows=False):
    """Draw a classic mosque silhouette (dome + gate + two minarets)."""
    c = tuple((color * 255).astype(int))
    bw = int(220 * scale)              # building width
    bh = int(150 * scale)              # building height
    x0, x1 = cx - bw // 2, cx + bw // 2
    y0 = base_y - bh
    draw.rectangle([x0, y0, x1, base_y], fill=c)
    # central dome
    dome_w = int(bw * 0.62)
    dome_h = int(dome_w * 0.8)
    dx0, dx1 = cx - dome_w // 2, cx + dome_w // 2
    draw.pieslice([dx0, y0 - dome_h, dx1, y0 + dome_h], 180, 360, fill=c)
    # finial
    draw.line([cx, y0 - dome_h, cx, y0 - dome_h - int(30 * scale)], fill=c, width=max(1, int(4 * scale)))
    draw.ellipse([cx - int(6 * scale), y0 - dome_h - int(46 * scale),
                  cx + int(6 * scale), y0 - dome_h - int(34 * scale)], fill=c)
    # two minarets
    for sgn in (-1, 1):
        mx = cx + sgn * int(bw * 0.62)
        mw = int(26 * scale)
        mtop = base_y - int(bh * 1.9)
        draw.rectangle([mx - mw // 2, mtop, mx + mw // 2, base_y], fill=c)
        draw.pieslice([mx - mw, mtop - mw, mx + mw, mtop + mw], 180, 360, fill=c)
        draw.line([mx, mtop - mw, mx, mtop - int(46 * scale)], fill=c, width=max(1, int(3 * scale)))
    # arched gate
    gw = int(bw * 0.24)
    gate = tuple((WARM * 255).astype(int)) if glow_windows else c
    draw.pieslice([cx - gw // 2, base_y - int(bh * 0.9),
                   cx + gw // 2, base_y - int(bh * 0.9) + gw], 180, 360, fill=gate)
    draw.rectangle([cx - gw // 2, base_y - int(bh * 0.9) + gw // 2, cx + gw // 2, base_y], fill=gate)
    if glow_windows:
        wc = tuple((WARM * 255).astype(int))
        for sgn in (-1, 1):
            for k in range(2):
                wx = cx + sgn * int(bw * (0.22 + 0.14 * k))
                wy = base_y - int(bh * 0.55)
                ww = int(14 * scale)
                draw.pieslice([wx - ww, wy - ww, wx + ww, wy + ww], 180, 360, fill=wc)
                draw.rectangle([wx - ww, wy, wx + ww, wy + int(26 * scale)], fill=wc)


def city_skyline(draw, base_y, color, rng, n=7):
    for i in range(n):
        cx = int((i + 0.5) / n * W + rng.integers(-40, 40))
        mosque(draw, cx, base_y, rng.uniform(0.25, 0.45), color)


def palm(draw, x, base_y, scale, color):
    c = tuple((color * 255).astype(int))
    top = base_y - int(240 * scale)
    draw.line([x, base_y, x + int(10 * scale), top], fill=c, width=max(2, int(9 * scale)))
    for ang in range(-70, 71, 20):
        a = np.radians(ang - 90)
        ex = x + int(150 * scale * np.cos(a))
        ey = top + int(150 * scale * np.sin(a))
        mx = x + int(80 * scale * np.cos(a)) + int(20 * scale)
        my = top + int(80 * scale * np.sin(a)) - int(30 * scale)
        draw.line([x, top, mx, my, ex, ey], fill=c, width=max(1, int(4 * scale)), joint="curve")


def believer(draw, x, base_y, scale, color):
    """A single person seen from behind — head + shoulders + robe. No face."""
    c = tuple((color * 255).astype(int))
    hw = int(26 * scale)               # half shoulder width
    hh = int(150 * scale)              # body height
    head_r = int(18 * scale)
    top = base_y - hh
    # robe: tapered body
    draw.polygon([(x - hw, base_y), (x + hw, base_y),
                  (x + int(hw * 0.6), top), (x - int(hw * 0.6), top)], fill=c)
    # head
    draw.ellipse([x - head_r, top - head_r * 2, x + head_r, top], fill=c)


# -------------------------------------------------------------- scenes
def scene_01(rng):
    """Introduction — peaceful night sky over an ancient city."""
    arr = vgrad(NIGHT_TOP, NIGHT_BOT)
    arr = screen(arr, radial_glow(W * 0.5, H * 1.02, W * 0.8, H * 0.45, GOLD, 0.55))
    arr = add_stars(arr, rng, 1000, ymax=0.7)
    pil = to_pil(arr)
    d = ImageDraw.Draw(pil)
    city_skyline(d, int(H * 0.9), DARK, rng, n=8)
    arr = to_arr(pil)
    arr = screen(arr, particles(rng, 60, WARM, yrange=(0.0, 0.9), rmax=0.008) * 0.6)
    return vignette(arr)


def scene_02(rng):
    """Inna Allaha — heavenly light descending through luminous clouds."""
    arr = vgrad(NIGHT_TOP * 0.8, NIGHT_BOT)
    # luminous cloud band near the top
    band = Image.new("L", (W, H), 0)
    bd = ImageDraw.Draw(band)
    for _ in range(26):
        cx = rng.integers(0, W); cy = rng.integers(int(H * 0.08), int(H * 0.32))
        rx = rng.integers(120, 280); ry = rng.integers(30, 70)
        bd.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=int(rng.uniform(50, 120)))
    cloud = np.asarray(band.filter(ImageFilter.GaussianBlur(28)), np.float32) / 255
    arr = screen(arr, (WARM[None, None, :] * cloud[..., None]) * 0.8)
    # descending shafts
    tgts = [(int(W * f), int(H * 0.95), rng.uniform(70, 130)) for f in (0.32, 0.45, 0.55, 0.68)]
    arr = screen(arr, light_beams((int(W * 0.5), int(H * 0.05)), tgts, WARM, spread=34))
    arr = add_stars(arr, rng, 500, ymax=0.5)
    arr = screen(arr, particles(rng, 240, WARM, yrange=(0.0, 1.0), rmax=0.006))
    pil = to_pil(arr); d = ImageDraw.Draw(pil)
    city_skyline(d, int(H * 0.96), DARK, rng, n=9)
    return vignette(to_arr(pil), 0.4)


def scene_03(rng):
    """Yusalluna — ancient Medina at sunset, a simple mosque, palms."""
    top = np.array([28, 40, 92], np.float32) / 255
    bot = np.array([232, 150, 78], np.float32) / 255
    arr = vgrad(top, bot)
    arr = screen(arr, radial_glow(W * 0.5, H * 0.92, W * 0.7, H * 0.5, GOLD, 0.7))
    arr = add_stars(arr, rng, 260, ymax=0.4)
    pil = to_pil(arr); d = ImageDraw.Draw(pil)
    city_skyline(d, int(H * 0.9), DARK, rng, n=6)
    mosque(d, int(W * 0.5), int(H * 0.9), 1.1, DARK)
    palm(d, int(W * 0.16), int(H * 0.92), 1.2, DARK)
    palm(d, int(W * 0.86), int(H * 0.93), 1.35, DARK)
    return vignette(to_arr(pil), 0.45)


def scene_04(rng):
    """Ya Ayyuha — believers walking toward a mosque at sunset, from behind."""
    top = np.array([30, 42, 96], np.float32) / 255
    bot = np.array([224, 156, 96], np.float32) / 255
    arr = vgrad(top, bot)
    arr = screen(arr, radial_glow(W * 0.5, H * 0.6, W * 0.55, H * 0.5, GOLD, 0.85))
    haze = np.asarray(to_pil(arr).filter(ImageFilter.GaussianBlur(2)), np.float32) / 255
    arr = 0.7 * arr + 0.3 * haze
    pil = to_pil(arr); d = ImageDraw.Draw(pil)
    mosque(d, int(W * 0.5), int(H * 0.7), 0.9, DARK)
    # a small crowd walking away toward it, larger (nearer) at the front
    xs = np.linspace(W * 0.2, W * 0.8, 9)
    for i, x in enumerate(xs):
        s = 0.9 + 0.5 * (i % 3) / 2 + rng.uniform(-0.05, 0.15)
        believer(d, int(x + rng.integers(-20, 20)), int(H * 0.98), s, DARK)
    arr = screen(to_arr(pil), particles(rng, 40, WARM, yrange=(0.0, 0.8), rmax=0.006) * 0.7)
    return vignette(arr, 0.5)


def scene_05(rng):
    """Sallu alayhi — a Quran on a wooden stand, beads on a rug, window light."""
    # Warm dark interior: deep brown wall (top) to a slightly lit floor (bottom).
    wall_top = np.array([26, 18, 14], np.float32) / 255
    wall_bot = np.array([48, 32, 22], np.float32) / 255
    arr = vgrad(wall_top, wall_bot)
    # ornate arched window casting warm light from the upper left
    win = Image.new("L", (W, H), 0); wd = ImageDraw.Draw(win)
    wx, wy, ww, wh = int(W * 0.14), int(H * 0.12), int(W * 0.19), int(H * 0.42)
    wd.pieslice([wx, wy, wx + ww, wy + ww], 180, 360, fill=230)
    wd.rectangle([wx, wy + ww // 2, wx + ww, wy + wh], fill=230)
    winblur = np.asarray(win.filter(ImageFilter.GaussianBlur(5)), np.float32) / 255
    arr = screen(arr, WARM[None, None, :] * winblur[..., None])
    # soft warm ambient glow pooling on the floor around the Quran
    arr = screen(arr, radial_glow(W * 0.5, H * 0.82, W * 0.42, H * 0.28, GOLD, 0.35))
    # a broad light shaft from the window down to the stand
    win_cx, win_cy = wx + ww // 2, wy + ww // 2
    tgts = [(int(W * f), int(H * 0.82), 110) for f in (0.42, 0.5, 0.58)]
    beam = light_beams((win_cx, win_cy), tgts, WARM, spread=55)
    arr = screen(arr, beam * 0.9)
    # dust motes ONLY within the shaft (between the window and the book)
    arr = screen(arr, particles(rng, 90, WARM, xrange=(0.30, 0.62),
                                yrange=(0.16, 0.80), rmax=0.004) * 0.9)
    pil = to_pil(arr); d = ImageDraw.Draw(pil)
    gc = tuple((GOLD * 255).astype(int))
    # rug
    d.rounded_rectangle([int(W * 0.24), int(H * 0.72), int(W * 0.80), int(H * 0.99)],
                        radius=26, fill=(70, 44, 34))
    d.rounded_rectangle([int(W * 0.265), int(H * 0.745), int(W * 0.775), int(H * 0.965)],
                        radius=20, outline=gc, width=3)
    # rehal (X-shaped wooden stand)
    cx, cy = int(W * 0.5), int(H * 0.82)
    d.line([cx - 120, cy + 95, cx + 120, cy - 55], fill=(92, 58, 34), width=22)
    d.line([cx + 120, cy + 95, cx - 120, cy - 55], fill=(92, 58, 34), width=22)
    # open Quran (two facing pages, no text) resting in the stand's cradle
    d.polygon([(cx, cy - 78), (cx - 175, cy - 40), (cx - 162, cy + 14), (cx, cy - 26)],
              fill=(240, 234, 216))
    d.polygon([(cx, cy - 78), (cx + 175, cy - 40), (cx + 162, cy + 14), (cx, cy - 26)],
              fill=(228, 221, 200))
    d.line([cx, cy - 78, cx, cy - 26], fill=(150, 120, 76), width=4)
    # faint gold page edges
    d.line([(cx - 175, cy - 40), (cx - 162, cy + 14)], fill=gc, width=2)
    d.line([(cx + 175, cy - 40), (cx + 162, cy + 14)], fill=gc, width=2)
    # prayer beads (tasbih) resting on the rug
    bx, by = int(W * 0.68), int(H * 0.90)
    for k in range(16):
        a = k / 16 * np.pi
        px = bx + int(90 * np.cos(a)); py = by + int(30 * np.sin(a))
        d.ellipse([px - 6, py - 6, px + 6, py + 6], fill=gc)
    return vignette(to_arr(pil), 0.5)


def scene_06(rng):
    """Wa sallimu — a magnificent mosque glowing under a starry night."""
    arr = vgrad(NIGHT_TOP, NIGHT_BOT)
    arr = add_stars(arr, rng, 1100, ymax=0.72)
    # soft moon glow
    arr = screen(arr, radial_glow(W * 0.82, H * 0.2, W * 0.14, W * 0.14, np.array([0.8, 0.85, 1.0], np.float32), 0.7))
    pil = to_pil(arr); d = ImageDraw.Draw(pil)
    mosque(d, int(W * 0.5), int(H * 0.86), 1.5, DARK, glow_windows=True)
    arr = to_arr(pil)
    # warm halo around the mosque + courtyard reflection
    arr = screen(arr, radial_glow(W * 0.5, H * 0.7, W * 0.4, H * 0.35, GOLD, 0.35))
    refl = arr[::-1].copy()
    ref_region = np.zeros((H, W, 1), np.float32)
    ref_region[int(H * 0.86):] = 1.0
    arr = arr * (1 - ref_region * 0.5) + refl * ref_region * 0.5 * np.array([0.6, 0.62, 0.8])[None, None, :]
    return vignette(arr, 0.5)


def scene_07(rng):
    """Conclusion — looking up from a courtyard, clean dark centre for text."""
    arr = vgrad(NIGHT_TOP * 0.7, NIGHT_BOT * 0.9)
    arr = add_stars(arr, rng, 1300, ymax=1.0)
    pil = to_pil(arr); d = ImageDraw.Draw(pil)
    dc = tuple((DARK * 255).astype(int))
    # framing arches around the edges (as if looking up in a courtyard)
    for sgn, fx in ((-1, 0.0), (1, 1.0)):
        base = int(W * fx)
        for k in range(3):
            mx = base + sgn * int(W * (0.06 + 0.1 * k))
            mosque(d, mx, int(H * 1.02), 0.7 - 0.12 * k, DARK)
    # bottom courtyard edge
    d.polygon([(0, H), (0, int(H * 0.9)), (int(W * 0.3), int(H * 0.96)),
               (int(W * 0.7), int(H * 0.96)), (W, int(H * 0.9)), (W, H)], fill=dc)
    arr = to_arr(pil)
    arr = screen(arr, particles(rng, 160, WARM, yrange=(0.0, 1.0), rmax=0.006))
    # keep centre clean/dark for later text overlay
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    dctr = np.sqrt(((xs - W / 2) / (W * 0.32)) ** 2 + ((ys - H / 2) / (H * 0.3)) ** 2)
    darken = np.clip(1.0 - dctr, 0, 1)[..., None]
    arr = arr * (1 - 0.35 * darken)
    return vignette(arr, 0.4)


SCENES = [scene_01, scene_02, scene_03, scene_04, scene_05, scene_06, scene_07]


def main():
    ap = argparse.ArgumentParser(description="Generate the 7 Salawat images.")
    ap.add_argument("--out-dir", default="salawat/images")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    for i, scene in enumerate(SCENES, 1):
        rng = np.random.default_rng(args.seed + i * 101)
        arr = scene(rng)
        path = os.path.join(args.out_dir, f"{i:02d}.png")
        to_pil(arr).save(path)
        print(f"  wrote {path}", flush=True)
    print("Done.", flush=True)


if __name__ == "__main__":
    main()
