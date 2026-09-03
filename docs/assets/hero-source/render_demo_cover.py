#!/usr/bin/env python3
"""ageval README demo-video cover — why-ageval diagram + YouTube play button.

Rasterizes docs/assets/why-ageval.svg and bakes
docs/assets/demo-cover.png: the N×M diagram itself doubles as the README's
YouTube entry, so the README carries one visual instead of diagram + video
cover stacked. Compose at 2x then LANCZOS down.

Rasterizer is system Chrome (headless screenshot), not rsvg-convert: the
Excalidraw export leans on <symbol>/<use>, data-URI images, and an emoji
font fallback, which librsvg renders incompletely (icons drop out).
"""
from __future__ import annotations

import math
import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT.parent  # docs/assets
SVG = ASSETS / "why-ageval.svg"
OUT = ASSETS / "demo-cover.png"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

SCALE = 2
# Dim the why-diagram behind the button; 1.0 = unchanged.
BG_BRIGHTNESS = 0.65
# Plate 170×120 mirrors the official mark's 24:16.91; corner radius 3.016/16.91.
BTN_W, BTN_H, BTN_R = 170, 120, 21
YT_RED = (255, 0, 0, 255)
SHADOW = (0, 0, 0, 110)
# Official triangle proportions and its optical right-shift (bbox center 12.68/24).
TRI_W_R = 6.273 / 24
TRI_H_R = 7.136 / 16.91
TRI_X_OFF = (12.68 - 12) / 24


def _svg_size() -> tuple[int, int]:
    vb = re.search(
        r'viewBox="\s*[\d.e+-]+[ ,]+[\d.e+-]+[ ,]+([\d.e+-]+)[ ,]+([\d.e+-]+)', SVG.read_text()
    )
    if not vb:
        raise SystemExit("why-ageval.svg has no viewBox")
    return math.ceil(float(vb.group(1))), math.ceil(float(vb.group(2)))


def _rasterize() -> Image.Image:
    """Screenshot the SVG with system Chrome at SCALE — browser-exact output."""
    w, h = _svg_size()
    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        subprocess.run(
            [
                CHROME,
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                f"--force-device-scale-factor={SCALE}",
                f"--window-size={w},{h}",
                "--virtual-time-budget=10000",
                f"--screenshot={tmp.name}",
                f"file://{SVG.resolve()}",
            ],
            check=True,
            capture_output=True,
        )
        return Image.open(tmp.name).convert("RGBA")


def triangle(w: int, h: int) -> list[tuple[float, float]]:
    # Right-pointing triangle, optically centered in the button.
    return [(0, 0), (0, h), (w, h / 2)]


def main() -> None:
    big = _rasterize()
    if BG_BRIGHTNESS < 1.0:
        big = ImageEnhance.Brightness(big).enhance(BG_BRIGHTNESS)

    btn_w, btn_h, btn_r = BTN_W * SCALE, BTN_H * SCALE, BTN_R * SCALE
    cx, cy = big.width // 2, big.height // 2
    x0, y0 = cx - btn_w // 2, cy - btn_h // 2

    # Soft drop shadow so the button separates from light covers.
    shadow = Image.new("RGBA", big.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (x0 + 3 * SCALE, y0 + 6 * SCALE, x0 + btn_w + 3 * SCALE, y0 + btn_h + 6 * SCALE),
        radius=btn_r,
        fill=SHADOW,
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(6 * SCALE))

    overlay = Image.new("RGBA", big.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rounded_rectangle((x0, y0, x0 + btn_w, y0 + btn_h), radius=btn_r, fill=YT_RED)

    tri_w, tri_h = int(btn_w * TRI_W_R), int(btn_h * TRI_H_R)
    tri = triangle(tri_w, tri_h)
    ox = x0 + (btn_w - tri_w) // 2 + int(TRI_X_OFF * btn_w)
    oy = y0 + (btn_h - tri_h) // 2
    draw.polygon([(ox + px, oy + py) for px, py in tri], fill=(255, 255, 255, 255))

    big = Image.alpha_composite(big, shadow)
    big = Image.alpha_composite(big, overlay)
    out = big.convert("RGB").resize((big.width // SCALE, big.height // SCALE), Image.LANCZOS)
    out.save(OUT, "PNG")
    print(f"wrote {OUT} {out.size}")


if __name__ == "__main__":
    main()
