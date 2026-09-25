"""Draw the lightweight 1200×630 social sharing card without external assets.

Install Pillow (`python -m pip install pillow`) and run
`python -m scripts.generate_social_preview` after changing the brand copy.
The generated PNG is committed because crawlers cannot run a Python generator.

Headlines use Besley when ``CHAOSHIRE_BESLEY`` points at the TTF, or when a
local checkout still has ``/tmp/fonts/Besley-600.ttf``. Otherwise the card
falls back to DejaVu, which is enough to regenerate the colors.
"""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUTPUT = (
    Path(__file__).resolve().parent.parent / "chaoshire" / "web" / "static" / "social-preview.png"
)
PAPER = (28, 23, 20)
CARD = (36, 30, 25)
BRASS = (198, 161, 91)
CREAM = (243, 235, 223)
MUTED = (203, 187, 166)
FAIL = (238, 125, 106)


def font(size: int, *, heading: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = []
    if heading:
        if os.getenv("CHAOSHIRE_BESLEY"):
            candidates.append(os.environ["CHAOSHIRE_BESLEY"])
        candidates.append("/tmp/fonts/Besley-600.ttf")
    candidates.append("DejaVuSans-Bold.ttf" if heading else "DejaVuSans.ttf")
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def main() -> None:
    image = Image.new("RGB", (1200, 630), PAPER)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1199, 7), fill=BRASS)
    draw.rectangle((72, 72, 1128, 558), outline=(58, 50, 42), width=1)

    icon_path = OUTPUT.parent / "icons" / "icon-192.png"
    with Image.open(icon_path) as source:
        icon = source.convert("RGBA").resize((72, 72), Image.Resampling.LANCZOS)
    image.paste(icon, (96, 108), icon)
    draw.text((184, 118), "ChaosHire", font=font(42, heading=True), fill=CREAM)
    draw.text((96, 214), "Stress-test hiring AI", font=font(54, heading=True), fill=CREAM)
    draw.text((96, 286), "while the résumé stays still.", font=font(40, heading=True), fill=BRASS)
    draw.text(
        (96, 390),
        "Zara Garcia, C-1489. Same résumé. Marked female, rejected.",
        font=font(22),
        fill=MUTED,
    )
    draw.text(
        (96, 428),
        "Marked male, accepted. 169 of 1,000 decisions flip.",
        font=font(22),
        fill=MUTED,
    )
    draw.text((96, 500), "A synthetic audit. Not a hiring tool.", font=font(18), fill=MUTED)

    # A small ledger entry, not a gradient chart.
    draw.rectangle((860, 168, 1088, 470), outline=BRASS, width=1)
    draw.text((884, 188), "C-1489", font=font(18), fill=BRASS)
    draw.text((884, 230), "0.485", font=font(36, heading=True), fill=FAIL)
    draw.text((884, 278), "rejected", font=font(18), fill=MUTED)
    draw.line((884, 322, 1064, 322), fill=(58, 50, 42), width=1)
    draw.text((884, 344), "0.530", font=font(36, heading=True), fill=CREAM)
    draw.text((884, 392), "accepted", font=font(18), fill=MUTED)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT, "PNG", optimize=True)
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
