#!/usr/bin/env python3
"""
Ken Burns + cross-dissolve montage renderer.

Assembles an ordered set of still images (e.g. the 7 images of the Salawat
sequence) into a single continuous 16:9 video that feels like one film rather
than a slideshow:

  * each image is shown for a few seconds with an extremely slow Ken Burns
    zoom (and a slight drift), alternating pan direction image to image;
  * consecutive images are joined with a cross-dissolve of ~0.5-1 s;
  * the whole clip fades in from black and out to black.

Images are fitted to the 16:9 canvas with a centre-crop ("cover") so nothing
is stretched. Frames are streamed straight to ffmpeg (rawvideo over stdin);
a bundled static ffmpeg (imageio-ffmpeg) is used if none is on PATH.

Usage:
    python3 scripts/montage.py \
        --images-dir salawat/images \
        --output out/salawat.mp4 \
        --seconds-per-image 4.5 --dissolve 0.75 --fps 24

Images are picked up in sorted filename order, so name them 01.png, 02.png, …
(any mix of .png/.jpg/.jpeg/.webp is fine).
"""

import argparse
import glob
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image


def bilinear_sample(img, sx, sy):
    """Sample float image (H,W,3) at fractional coords (sx, sy) -> (H,W,3)."""
    h, w = img.shape[:2]
    x0 = np.floor(sx).astype(np.int32)
    y0 = np.floor(sy).astype(np.int32)
    fx = (sx - x0)[..., None]
    fy = (sy - y0)[..., None]
    x0c = np.clip(x0, 0, w - 1)
    x1c = np.clip(x0 + 1, 0, w - 1)
    y0c = np.clip(y0, 0, h - 1)
    y1c = np.clip(y0 + 1, 0, h - 1)
    Ia = img[y0c, x0c]
    Ib = img[y0c, x1c]
    Ic = img[y1c, x0c]
    Id = img[y1c, x1c]
    top = Ia * (1 - fx) + Ib * fx
    bot = Ic * (1 - fx) + Id * fx
    return top * (1 - fy) + bot * fy


def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def cover_fit(pil_img, W, H):
    """Resize + centre-crop a PIL image to exactly W x H (no distortion)."""
    iw, ih = pil_img.size
    scale = max(W / iw, H / ih)
    nw, nh = int(round(iw * scale)), int(round(ih * scale))
    resized = pil_img.resize((nw, nh), Image.LANCZOS)
    left = (nw - W) // 2
    top = (nh - H) // 2
    cropped = resized.crop((left, top, left + W, top + H))
    return np.asarray(cropped, dtype=np.float32) / 255.0


class Clip:
    """One image with its Ken Burns motion baked into a per-time sampler."""

    def __init__(self, canvas, index):
        self.canvas = canvas                     # (H,W,3) float, already 16:9
        self.h, self.w = canvas.shape[:2]
        gy = (np.arange(self.h, dtype=np.float32) + 0.5)
        gx = (np.arange(self.w, dtype=np.float32) + 0.5)
        self.Y, self.X = np.meshgrid(gy, gx, indexing="ij")

        # Slow zoom-in for every clip keeps the cross-dissolves continuous.
        self.z0, self.z1 = 1.0, 1.08
        # Alternate the pan direction so the sequence does not feel mechanical.
        dirs = [(-1, -1), (1, -1), (-1, 1), (1, 1), (0, -1), (1, 0), (-1, 0)]
        self.pan_dir = dirs[index % len(dirs)]

    def frame(self, lt):
        """Render this clip at local progress lt in [0, 1]."""
        e = smoothstep(lt)
        z = self.z0 + (self.z1 - self.z0) * e
        vis_w = self.w / z
        vis_h = self.h / z
        # Pan travels from centred toward the chosen corner as we zoom.
        max_off_x = (self.w - vis_w) / 2.0
        max_off_y = (self.h - vis_h) / 2.0
        pan = 0.6 * e
        cx = self.w / 2.0 + self.pan_dir[0] * pan * max_off_x
        cy = self.h / 2.0 + self.pan_dir[1] * pan * max_off_y
        left = cx - vis_w / 2.0
        top = cy - vis_h / 2.0
        sx = left + (self.X / self.w) * vis_w
        sy = top + (self.Y / self.h) * vis_h
        return bilinear_sample(self.canvas, sx, sy)


def load_clips(images_dir, W, H):
    exts = ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.PNG", "*.JPG", "*.JPEG")
    paths = []
    for e in exts:
        paths.extend(glob.glob(os.path.join(images_dir, e)))
    paths = sorted(set(paths))
    if not paths:
        sys.exit(
            f"No images found in '{images_dir}'.\n"
            f"Generate the 7 images from salawat/PROMPTS.md, name them "
            f"01.png … 07.png, and place them there."
        )
    clips = []
    for i, p in enumerate(paths):
        canvas = cover_fit(Image.open(p).convert("RGB"), W, H)
        clips.append(Clip(canvas, i))
    return paths, clips


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
    ap = argparse.ArgumentParser(description="Ken Burns + cross-dissolve montage.")
    ap.add_argument("--images-dir", default="salawat/images")
    ap.add_argument("--output", default="out/salawat.mp4")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--seconds-per-image", type=float, default=4.5)
    ap.add_argument("--dissolve", type=float, default=0.75,
                    help="cross-dissolve duration between images (s)")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--fade", type=float, default=0.75,
                    help="fade in/out from/to black at the ends (s)")
    ap.add_argument("--crf", type=int, default=18)
    args = ap.parse_args()

    W, H = args.width, args.height
    dur = args.seconds_per_image
    dis = min(args.dissolve, dur * 0.9)
    paths, clips = load_clips(args.images_dir, W, H)
    n = len(clips)

    # Timeline: each clip starts `dur - dis` after the previous, so adjacent
    # clips overlap by exactly `dis` seconds (the cross-dissolve window).
    step = dur - dis
    starts = [i * step for i in range(n)]
    ends = [s + dur for s in starts]
    total = ends[-1]
    frames = max(1, int(round(total * args.fps)))

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    ffmpeg = find_ffmpeg()
    cmd = [
        ffmpeg, "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{W}x{H}", "-r", str(args.fps),
        "-i", "-", "-an",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-crf", str(args.crf), "-preset", "slow",
        "-movflags", "+faststart", args.output,
    ]
    print(f"Montage: {n} images, {dur}s each, {dis}s dissolve -> "
          f"{total:.1f}s @ {args.fps}fps, {W}x{H}", flush=True)
    for i, p in enumerate(paths):
        print(f"  [{i+1}] {os.path.basename(p)}", flush=True)

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for f in range(frames):
            t = f / args.fps
            # Which clips are active at time t, and with what blend weight.
            acc = np.zeros((H, W, 3), dtype=np.float32)
            wsum = 0.0
            for i in range(n):
                if t < starts[i] or t >= ends[i]:
                    continue
                lt = (t - starts[i]) / dur
                w = 1.0
                if i > 0:  # fade in over the overlap with the previous clip
                    w *= min(1.0, (t - starts[i]) / dis)
                if i < n - 1:  # fade out over the overlap with the next clip
                    w *= min(1.0, (ends[i] - t) / dis)
                if w <= 0.0:
                    continue
                acc += w * clips[i].frame(lt)
                wsum += w
            frame = acc / wsum if wsum > 0 else acc

            # Global fade in/out from/to black.
            if args.fade > 0:
                if t < args.fade:
                    frame *= smoothstep(t / args.fade)
                if t > total - args.fade:
                    frame *= smoothstep((total - t) / args.fade)

            out = (np.clip(frame, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
            proc.stdin.write(out.tobytes())
            if (f + 1) % 24 == 0 or f + 1 == frames:
                print(f"  frame {f+1}/{frames}", flush=True)
    finally:
        proc.stdin.close()
        rc = proc.wait()
    if rc != 0:
        sys.exit(f"ffmpeg exited with code {rc}")
    print(f"Done -> {args.output}", flush=True)


if __name__ == "__main__":
    main()
