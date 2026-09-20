#!/usr/bin/env python3
"""
Nighttime window cinemagraph renderer.

Takes a single still photograph and produces a subtle, photorealistic looking
animation of it by adding localized, physically-plausible motion — nothing in
the scene is invented or replaced, only gently moved or modulated:

  * an extremely slow cinematic push-in toward the open window
  * stars that gently twinkle in the night sky
  * clouds that slowly drift across the distant sky
  * meadow grass and wildflowers swaying in a faint night breeze
  * sheer curtains softly billowing with the air
  * the warm table lamp flickering naturally and very slightly
  * faint delicate steam rising slowly from the cup

The composition, architecture, window, furniture, book, cup, lamp, landscape
and lighting are all preserved. No new objects, no people, no morphing.

Every effect is driven by smooth periodic (or slowly ramping) functions so the
motion is continuous and seamless-looking. Effect strengths and the regions
they act on are fully configurable near the top of the file.

Usage:
    python3 scripts/cinemagraph.py \
        --input assets/source.png \
        --output out/night_window.mp4 \
        --seconds 8 --fps 24

Frames are streamed straight to ffmpeg (rawvideo over stdin) so no intermediate
PNGs touch the disk. A bundled static ffmpeg (imageio-ffmpeg) is used if a
system ffmpeg is not on PATH.
"""

import argparse
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image


# --------------------------------------------------------------------------
# Scene layout
#
# All regions are expressed in NORMALIZED coordinates (0..1) relative to the
# image so the layout is resolution independent. Values were measured against
# the 1024x1536 source: the open casement window sits left-of-centre, the sky
# fills the upper two thirds seen through the glass, a wildflower meadow runs
# across the lower third, sheer curtains hang at both sides, the warm lamp is
# bottom-right and the teacup sits centre-bottom on the sill.
# --------------------------------------------------------------------------

# Focal point of the slow push-in: the open window opening.
PUSH_CENTER = (0.54, 0.40)
PUSH_MAX_SCALE = 1.045          # final zoom factor at the end of the clip

# Sky band (stars + clouds) seen through the window glass.
SKY_Y = (0.05, 0.52)            # vertical extent of visible sky
SKY_X = (0.19, 0.98)            # horizontal extent (right of the wooden frame)

# Cloud drift band sits low in the sky, near the horizon glow.
CLOUD_Y = (0.30, 0.53)

# Meadow of grass and wildflowers.
MEADOW_Y = (0.50, 0.82)
MEADOW_X = (0.19, 0.98)

# Sheer curtains. Left curtain is a thin translucent strip at the far left;
# the right curtain drapes down the right edge of the opening.
LEFT_CURTAIN_X = (0.00, 0.085)
RIGHT_CURTAIN_X = (0.90, 1.00)
CURTAIN_Y = (0.00, 0.70)

# Warm lamp glow, bottom right (shade + cast light).
LAMP_CENTER = (0.885, 0.735)
LAMP_RADIUS = (0.17, 0.19)      # (x, y) radius of the glow falloff

# Teacup rim — steam origin. Steam rises in a narrow plume above this point.
CUP_CENTER = (0.635, 0.815)
STEAM_WIDTH = 0.075             # half-width of the plume at the rim
STEAM_TOP = 0.58                # normalized y the plume fades out by (upwards)


# --------------------------------------------------------------------------
# Effect strengths (kept deliberately gentle — this is a cinemagraph, not a
# music video). Displacements are in pixels at the source resolution.
# --------------------------------------------------------------------------

STAR_TWINKLE_AMP = 0.55         # peak fractional brightness swing of a star
STAR_THRESHOLD = 0.62           # min luma (0..1) in sky for a pixel to twinkle
STAR_FREQS = (0.5, 0.8, 1.15)   # Hz — a few overlaid rates so it never pulses

CLOUD_DRIFT_PX = 9.0            # total horizontal cloud travel across the clip
CLOUD_SWAY_PX = 2.0             # gentle periodic sway layered on the drift

GRASS_AMP_PX = 2.6              # max horizontal sway at the bottom of the meadow
GRASS_FREQ = 0.32              # Hz base sway rate of the breeze

CURTAIN_AMP_PX = 3.4            # max horizontal billow of the sheer curtains
CURTAIN_FREQ = 0.22            # Hz

LAMP_FLICKER_AMP = 0.05         # peak fractional brightness swing of the lamp

STEAM_OPACITY = 0.16            # peak additive whiteness of the steam
STEAM_RISE = 0.9               # how fast the plume scrolls upward


def smoothstep(edge0, edge1, x):
    """Vectorized smoothstep for building feathered masks."""
    t = np.clip((x - edge0) / (edge1 - edge0 + 1e-9), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def band_mask(coord, lo, hi, feather):
    """Soft 1-D band that is 1 inside [lo, hi] and feathers to 0 outside."""
    rising = smoothstep(lo - feather, lo + feather, coord)
    falling = 1.0 - smoothstep(hi - feather, hi + feather, coord)
    return rising * falling


def value_noise(shape, rng, octaves=4):
    """Cheap fractal value noise in [0,1] built from upscaled random grids."""
    h, w = shape
    out = np.zeros(shape, dtype=np.float32)
    amp = 1.0
    total = 0.0
    size = 4
    for _ in range(octaves):
        grid = rng.random((size, size)).astype(np.float32)
        tile = np.asarray(
            Image.fromarray((grid * 255).astype(np.uint8)).resize(
                (w, h), Image.BICUBIC
            ),
            dtype=np.float32,
        ) / 255.0
        out += amp * tile
        total += amp
        amp *= 0.5
        size *= 2
    return out / total


def bilinear_sample(img, sx, sy):
    """Sample float image (H,W,3) at fractional coords (sx, sy) -> (H,W,3)."""
    h, w = img.shape[:2]
    x0 = np.floor(sx).astype(np.int32)
    y0 = np.floor(sy).astype(np.int32)
    x1 = x0 + 1
    y1 = y0 + 1
    fx = (sx - x0)[..., None]
    fy = (sy - y0)[..., None]
    x0c = np.clip(x0, 0, w - 1)
    x1c = np.clip(x1, 0, w - 1)
    y0c = np.clip(y0, 0, h - 1)
    y1c = np.clip(y1, 0, h - 1)
    Ia = img[y0c, x0c]
    Ib = img[y0c, x1c]
    Ic = img[y1c, x0c]
    Id = img[y1c, x1c]
    top = Ia * (1 - fx) + Ib * fx
    bot = Ic * (1 - fx) + Id * fx
    return top * (1 - fy) + bot * fy


class Cinemagraph:
    def __init__(self, image_path, seconds, fps, seed=7):
        base = Image.open(image_path).convert("RGB")
        self.img = np.asarray(base, dtype=np.float32) / 255.0
        self.h, self.w = self.img.shape[:2]
        self.seconds = seconds
        self.fps = fps
        self.frames = max(1, int(round(seconds * fps)))
        self.rng = np.random.default_rng(seed)

        # Normalized coordinate grids (output == source resolution).
        ys = (np.arange(self.h, dtype=np.float32) + 0.5) / self.h
        xs = (np.arange(self.w, dtype=np.float32) + 0.5) / self.w
        self.ny, self.nx = np.meshgrid(ys, xs, indexing="ij")
        self.px_x = self.nx * self.w
        self.px_y = self.ny * self.h

        self._build_masks()
        self._build_stars()
        self._build_steam()

    # -- static precomputation -------------------------------------------
    def _build_masks(self):
        nx, ny = self.nx, self.ny

        sky = band_mask(ny, *SKY_Y, 0.03) * band_mask(nx, *SKY_X, 0.02)
        self.sky_mask = sky

        cloud = band_mask(ny, *CLOUD_Y, 0.04) * band_mask(nx, *SKY_X, 0.03)
        self.cloud_mask = cloud

        meadow = band_mask(ny, *MEADOW_Y, 0.03) * band_mask(nx, *MEADOW_X, 0.02)
        # Sway grows toward the foreground (bottom of the meadow).
        depth = smoothstep(MEADOW_Y[0], MEADOW_Y[1], ny)
        self.meadow_mask = meadow
        self.meadow_depth = depth

        left = band_mask(nx, *LEFT_CURTAIN_X, 0.02) * band_mask(ny, *CURTAIN_Y, 0.05)
        right = band_mask(nx, *RIGHT_CURTAIN_X, 0.02) * band_mask(ny, *CURTAIN_Y, 0.05)
        self.left_curtain = left
        self.right_curtain = right

        # Radial lamp glow.
        dx = (nx - LAMP_CENTER[0]) / LAMP_RADIUS[0]
        dy = (ny - LAMP_CENTER[1]) / LAMP_RADIUS[1]
        r = np.sqrt(dx * dx + dy * dy)
        self.lamp_mask = 1.0 - smoothstep(0.4, 1.0, r)

    def _build_stars(self):
        luma = (
            0.2126 * self.img[..., 0]
            + 0.7152 * self.img[..., 1]
            + 0.0722 * self.img[..., 2]
        )
        # Only bright, isolated points high in the sky twinkle — not the
        # horizon glow or the meadow.
        star_region = self.sky_mask * band_mask(self.ny, 0.05, 0.44, 0.05)
        stars = (luma > STAR_THRESHOLD).astype(np.float32) * star_region
        self.star_field = stars
        # A per-pixel random phase so stars are out of sync with each other.
        self.star_phase = self.rng.random((self.h, self.w)).astype(np.float32) * (2 * np.pi)

    def _build_steam(self):
        nx, ny = self.nx, self.ny
        # Horizontal falloff around the plume centre; widens slightly as it rises.
        rise = smoothstep(CUP_CENTER[1], STEAM_TOP, ny)          # 0 at rim -> 1 at top
        width = STEAM_WIDTH * (1.0 + 1.3 * (1.0 - rise))
        horiz = 1.0 - smoothstep(0.0, 1.0, np.abs(nx - CUP_CENTER[0]) / width)
        # Vertical envelope: rises from the rim, fades out near the top.
        vert = band_mask(ny, STEAM_TOP, CUP_CENTER[1] + 0.01, 0.05)
        vert *= smoothstep(STEAM_TOP - 0.02, STEAM_TOP + 0.12, ny)
        self.steam_mask = np.clip(horiz * vert, 0.0, 1.0)
        # Tall noise texture we scroll upward for the wisps.
        self.steam_noise = value_noise((self.h, self.w), self.rng, octaves=5)

    # -- per-frame rendering ---------------------------------------------
    def render_frame(self, i):
        t = i / self.frames               # 0..1 over the clip
        tsec = t * self.seconds
        two_pi = 2.0 * np.pi

        # --- geometric displacement field (sampled from the source) ------
        sx = self.px_x.copy()
        sy = self.px_y.copy()

        # Push-in: sample from a slightly zoomed-in window around PUSH_CENTER.
        scale = 1.0 + (PUSH_MAX_SCALE - 1.0) * smoothstep(0.0, 1.0, t)
        cx = PUSH_CENTER[0] * self.w
        cy = PUSH_CENTER[1] * self.h
        sx = cx + (sx - cx) / scale
        sy = cy + (sy - cy) / scale

        # Cloud drift: slow one-way travel + a faint sway, feathered to the band.
        cloud_dx = CLOUD_DRIFT_PX * t + CLOUD_SWAY_PX * np.sin(two_pi * 0.05 * tsec)
        sx = sx - self.cloud_mask * cloud_dx

        # Grass & wildflowers: horizontal breeze, amplitude grows to foreground,
        # phase varies along x so blades don't move in lockstep.
        gphase = self.nx * 9.0
        grass_dx = (
            GRASS_AMP_PX
            * self.meadow_depth
            * self.meadow_mask
            * (
                np.sin(two_pi * GRASS_FREQ * tsec + gphase)
                + 0.4 * np.sin(two_pi * GRASS_FREQ * 1.7 * tsec + gphase * 1.5)
            )
        )
        sx = sx + grass_dx

        # Curtains: gentle billow. Left and right sway in slight counter-phase.
        billow = np.sin(two_pi * CURTAIN_FREQ * tsec)
        billow2 = np.sin(two_pi * CURTAIN_FREQ * tsec + 1.1)
        vert_profile_l = smoothstep(CURTAIN_Y[0], CURTAIN_Y[1], self.ny)
        vert_profile_r = smoothstep(CURTAIN_Y[0], CURTAIN_Y[1], self.ny)
        sx = sx + self.left_curtain * vert_profile_l * CURTAIN_AMP_PX * billow
        sx = sx - self.right_curtain * vert_profile_r * CURTAIN_AMP_PX * 0.8 * billow2

        frame = bilinear_sample(self.img, sx, sy)

        # --- photometric modulation (applied in output space) ------------
        # Star twinkle: sum of a few slow sinusoids per star, unique phase each.
        twinkle = np.zeros((self.h, self.w), dtype=np.float32)
        for f in STAR_FREQS:
            twinkle += np.sin(two_pi * f * tsec + self.star_phase)
        twinkle /= len(STAR_FREQS)
        star_mod = 1.0 + STAR_TWINKLE_AMP * self.star_field * twinkle
        frame *= star_mod[..., None]

        # Lamp flicker: warm, mostly-steady glow with a tiny irregular quiver.
        flick = (
            0.6 * np.sin(two_pi * 5.0 * tsec)
            + 0.3 * np.sin(two_pi * 8.3 * tsec + 1.7)
            + 0.1 * np.sin(two_pi * 13.0 * tsec + 0.5)
        )
        lamp_mod = 1.0 + LAMP_FLICKER_AMP * self.lamp_mask * flick
        # Bias the flicker toward the warm channels so it reads as a flame, not
        # a global exposure wobble.
        warm = np.stack(
            [lamp_mod, 1.0 + (lamp_mod - 1.0) * 0.85, 1.0 + (lamp_mod - 1.0) * 0.55],
            axis=-1,
        )
        frame *= warm

        # Steam: scroll the noise upward, threshold into soft wisps, add white.
        shift = int((STEAM_RISE * tsec % 1.0) * self.h)
        scrolled = np.roll(self.steam_noise, shift, axis=0)
        # Slight horizontal drift of the wisps as they rise.
        hshift = int(6 * np.sin(two_pi * 0.08 * tsec))
        scrolled = np.roll(scrolled, hshift, axis=1)
        wisp = smoothstep(0.45, 0.75, scrolled)
        steam = STEAM_OPACITY * self.steam_mask * wisp
        frame = frame + steam[..., None] * (1.0 - frame)   # additive toward white

        out = np.clip(frame, 0.0, 1.0)
        return (out * 255.0 + 0.5).astype(np.uint8)


def find_ffmpeg():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        sys.exit("ffmpeg not found and imageio-ffmpeg not installed.")


def main():
    ap = argparse.ArgumentParser(description="Render a nighttime window cinemagraph.")
    ap.add_argument("--input", default="assets/source.png")
    ap.add_argument("--output", default="out/night_window.mp4")
    ap.add_argument("--seconds", type=float, default=8.0)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--crf", type=int, default=17, help="x264 quality (lower=better)")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    cg = Cinemagraph(args.input, args.seconds, args.fps, seed=args.seed)
    ffmpeg = find_ffmpeg()

    cmd = [
        ffmpeg, "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{cg.w}x{cg.h}", "-r", str(args.fps),
        "-i", "-",
        "-an",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-crf", str(args.crf), "-preset", "slow",
        "-movflags", "+faststart",
        args.output,
    ]
    print(f"Rendering {cg.frames} frames at {cg.w}x{cg.h}, {args.fps} fps "
          f"({args.seconds}s) -> {args.output}", flush=True)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for i in range(cg.frames):
            proc.stdin.write(cg.render_frame(i).tobytes())
            if (i + 1) % 12 == 0 or i + 1 == cg.frames:
                print(f"  frame {i + 1}/{cg.frames}", flush=True)
    finally:
        proc.stdin.close()
        rc = proc.wait()
    if rc != 0:
        sys.exit(f"ffmpeg exited with code {rc}")
    print("Done.", flush=True)


if __name__ == "__main__":
    main()
