"""Generate the deterministic ChaosHire PWA icon set.

The icons are committed to ``chaoshire/static`` so the application, Docker image,
and Render deployment stay dependency-free at runtime. Regenerate them with:

    python -m pip install pillow
    python -m scripts.generate_icons

The drawing is fully deterministic: the same Pillow version produces byte-stable
output for a fixed size, so the manifest icons can be reviewed in git.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

BACKGROUND = (11, 18, 32, 255)  # #0b1220 — matches the dashboard theme
EDGE = (31, 44, 72, 255)  # #1f2c48
BAR_BOTTOM = (56, 189, 248, 255)  # #38bdf8
BAR_TOP = (167, 139, 250, 255)  # #a78bfa
ACCENT = (251, 113, 133, 255)  # #fb7185 — the "chaos" slash
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "chaoshire" / "static"


def _mix(first: tuple[int, int, int, int], second: tuple[int, int, int, int], ratio: float):
    return tuple(round(a + (b - a) * ratio) for a, b in zip(first, second, strict=True))


def draw_icon(size: int, maskable: bool = False) -> Image.Image:
    """Draw ascending audit bars crossed by a chaos slash."""
    image = Image.new("RGBA", (size, size), BACKGROUND)
    draw = ImageDraw.Draw(image)

    # Maskable icons must keep their content inside the central 80% safe zone
    # and bleed the background to the edges; "any" icons get rounded corners.
    inset = round(size * 0.20) if maskable else round(size * 0.10)
    if not maskable:
        corner = round(size * 0.22)
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=corner, fill=BACKGROUND)
        draw.rounded_rectangle(
            [round(size * 0.02)] * 2 + [size - 1 - round(size * 0.02)] * 2,
            radius=corner,
            outline=EDGE,
            width=max(2, round(size * 0.012)),
        )

    canvas = size - 2 * inset
    bar_width = round(canvas * 0.20)
    gap = round((canvas - 3 * bar_width) / 2)
    baseline = inset + canvas
    heights = (0.42, 0.66, 0.92)
    for index, height in enumerate(heights):
        left = inset + index * (bar_width + gap)
        top = baseline - round(canvas * height)
        fill = _mix(BAR_BOTTOM, BAR_TOP, index / (len(heights) - 1))
        draw.rounded_rectangle(
            [left, top, left + bar_width, baseline],
            radius=round(bar_width * 0.35),
            fill=fill,
        )

    # Chaos slash: the deliberate break through the measured bars.
    stroke = max(3, round(size * 0.045))
    draw.line(
        [
            (inset + round(canvas * 0.02), baseline - round(canvas * 0.30)),
            (inset + round(canvas * 0.98), baseline - round(canvas * 0.78)),
        ],
        fill=ACCENT,
        width=stroke,
    )
    return image


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(OUTPUT_DIR))
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    targets = [
        ("icon-192.png", 192, False),
        ("icon-512.png", 512, False),
        ("icon-maskable-512.png", 512, True),
    ]
    for name, size, maskable in targets:
        path = output / name
        draw_icon(size, maskable).save(path, format="PNG", optimize=True)
        print(f"Wrote {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
