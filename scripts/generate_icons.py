"""Generate the deterministic ChaosHire PWA icon set.

The icons are committed to ``chaoshire/web/static/icons`` so the application, Docker image,
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

BACKGROUND = (28, 23, 20, 255)  # #1c1714 — Night Ledger paper
EDGE = (58, 50, 42, 255)  # #3a322a
BAR_BOTTOM = (203, 187, 166, 255)  # #cbbba6
BAR_TOP = (243, 235, 223, 255)  # #f3ebdf
ACCENT = (198, 161, 91, 255)  # #c6a15b — the brass slash
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "chaoshire" / "web" / "static" / "icons"


def _mix(first: tuple[int, int, int, int], second: tuple[int, int, int, int], ratio: float):
    return tuple(round(a + (b - a) * ratio) for a, b in zip(first, second, strict=True))


def draw_icon(size: int, maskable: bool = False) -> Image.Image:
    """Draw ascending audit bars crossed by a chaos slash."""
    image = Image.new("RGBA", (size, size), BACKGROUND)
    draw = ImageDraw.Draw(image)

    # Maskable icons must keep their content inside the central 80% safe zone
    # and bleed the background to the edges.
    inset = round(size * 0.20) if maskable else round(size * 0.12)
    if not maskable:
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rectangle([0, 0, size - 1, size - 1], fill=BACKGROUND)
        draw.rectangle([0, 0, size - 1, max(3, round(size * 0.045))], fill=ACCENT)

    canvas = size - 2 * inset
    bar_width = round(canvas * 0.20)
    gap = round((canvas - 3 * bar_width) / 2)
    baseline = inset + canvas
    heights = (0.42, 0.66, 0.92)
    for index, height in enumerate(heights):
        left = inset + index * (bar_width + gap)
        top = baseline - round(canvas * height)
        fill = _mix(BAR_BOTTOM, BAR_TOP, index / (len(heights) - 1))
        draw.rectangle([left, top, left + bar_width, baseline], fill=fill)

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

    source = draw_icon(192)
    small = output / "favicon-32.png"
    source.resize((32, 32), Image.Resampling.LANCZOS).save(small, format="PNG", optimize=True)
    browser_icon = output / "favicon.ico"
    source.save(browser_icon, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    for path in (small, browser_icon):
        print(f"Wrote {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
