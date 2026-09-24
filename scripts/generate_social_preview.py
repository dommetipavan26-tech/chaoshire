"""Draw the lightweight 1200×630 social sharing card without external assets.

Install Pillow (`python -m pip install pillow`) and run
`python -m scripts.generate_social_preview` after changing the brand copy.
The generated PNG is committed because crawlers cannot run a Python generator.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUTPUT = (
    Path(__file__).resolve().parent.parent / "chaoshire" / "web" / "static" / "social-preview.png"
)
NAVY = (11, 18, 32)
CARD = (22, 35, 60)
BLUE = (56, 189, 248)
LIGHT = (229, 236, 248)
MUTED = (173, 190, 217)


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(name, size)
    except OSError:
        return ImageFont.load_default(size=size)


def main() -> None:
    image = Image.new("RGB", (1200, 630), NAVY)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (35, 35, 1165, 595), radius=36, fill=CARD, outline=(48, 67, 101), width=2
    )
    draw.ellipse((870, 40, 1170, 340), fill=(29, 58, 89))
    draw.ellipse((920, 360, 1090, 530), fill=(23, 69, 88))

    # The existing app icon anchors the card; all illustrations are vector shapes.
    icon_path = OUTPUT.parent / "icons" / "icon-192.png"
    with Image.open(icon_path) as source:
        icon = source.convert("RGBA").resize((80, 80), Image.Resampling.LANCZOS)
    image.paste(icon, (85, 77), icon)
    draw.text((180, 84), "Chaos", font=font(44, bold=True), fill=LIGHT)
    draw.text((327, 84), "Hire", font=font(44, bold=True), fill=BLUE)
    draw.text((87, 207), "SYNTHETIC FAIRNESS AUDIT", font=font(19, bold=True), fill=BLUE)
    draw.text((82, 260), "Stress-test hiring AI", font=font(58, bold=True), fill=LIGHT)
    draw.text((82, 335), "before unfair decisions.", font=font(51, bold=True), fill=BLUE)
    draw.text(
        (86, 466),
        "Measure disparity  ·  Probe decisions  ·  Review evidence",
        font=font(22),
        fill=MUTED,
    )
    draw.text(
        (86, 541), "Educational prototype — not a hiring decision tool", font=font(18), fill=MUTED
    )

    draw.rounded_rectangle(
        (865, 220, 1105, 420), radius=22, fill=(17, 29, 49), outline=(66, 94, 132), width=2
    )
    for index, (height, color) in enumerate(
        ((68, (56, 189, 248)), (111, (167, 139, 250)), (146, (52, 211, 153)))
    ):
        left = 905 + index * 68
        draw.rounded_rectangle((left, 380 - height, left + 38, 380), radius=12, fill=color)
    draw.line(((891, 398), (1078, 398)), fill=(74, 99, 132), width=3)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT, "PNG", optimize=True)
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
