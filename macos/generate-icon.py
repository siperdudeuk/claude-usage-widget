#!/usr/bin/env python3
"""Generate the ClaudeWidget app icon as an .icns file."""

import subprocess
import os
import sys

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("PIL not available, skipping icon generation")
    sys.exit(0)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ICONSET = os.path.join(SCRIPT_DIR, "ClaudeWidget.iconset")
ICNS = os.path.join(SCRIPT_DIR, "ClaudeWidget.icns")

os.makedirs(ICONSET, exist_ok=True)

SIZES = [16, 32, 64, 128, 256, 512, 1024]


def make_icon(size):
    """Draw a dark rounded-rect icon with a lightning bolt."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Rounded rectangle background
    pad = max(1, size // 16)
    r = size // 5
    draw.rounded_rectangle([pad, pad, size - pad, size - pad], radius=r, fill=(20, 16, 36))

    # Purple gradient-ish circle glow
    cx, cy = size // 2, size // 2
    for i in range(size // 3, 0, -1):
        alpha = int(40 * (i / (size // 3)))
        draw.ellipse(
            [cx - i, cy - i, cx + i, cy + i],
            fill=(188, 140, 255, alpha),
        )

    # Lightning bolt
    s = size / 512  # scale factor
    bolt = [
        (220 * s, 80 * s),
        (170 * s, 230 * s),
        (240 * s, 220 * s),
        (190 * s, 430 * s),
        (340 * s, 200 * s),
        (270 * s, 210 * s),
        (320 * s, 80 * s),
    ]
    draw.polygon(bolt, fill=(188, 140, 255))

    # Bright core
    inner = [
        (230 * s, 120 * s),
        (195 * s, 230 * s),
        (245 * s, 225 * s),
        (215 * s, 380 * s),
        (310 * s, 210 * s),
        (265 * s, 215 * s),
        (300 * s, 120 * s),
    ]
    draw.polygon(inner, fill=(212, 160, 255))

    return img


for size in SIZES:
    img = make_icon(size)
    # Standard resolution
    if size <= 512:
        img.resize((size, size), Image.LANCZOS).save(
            os.path.join(ICONSET, f"icon_{size}x{size}.png")
        )
    # @2x resolution
    half = size // 2
    if half >= 16:
        img.resize((size, size), Image.LANCZOS).save(
            os.path.join(ICONSET, f"icon_{half}x{half}@2x.png")
        )

# Convert iconset to icns
subprocess.run(["iconutil", "-c", "icns", ICONSET, "-o", ICNS], check=True)

# Cleanup
import shutil
shutil.rmtree(ICONSET)

print(f"Icon generated: {ICNS}")
