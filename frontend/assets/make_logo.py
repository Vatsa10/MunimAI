"""Regenerate the Munim.ai wordmark PNG.

The logo is a plain raster asset, so it is drawn here rather than kept as an
opaque binary nobody can edit. Run:  python frontend/assets/make_logo.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1774, 887
INK = (15, 23, 42)        # --auth-text
GREEN = (15, 122, 85)     # --auth-green
BG = (255, 255, 255)

OUT = Path(__file__).with_name("munim-dot-ai-logo-v3.png")

# Bold UI faces, first one that exists wins. Falls back to PIL's bitmap font,
# which looks poor but keeps the script from failing on a bare machine.
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]


def _font(size):
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def draw_monogram(d, left, mid_y, height, stroke):
    """The 'M' mark: two strokes down, one V between them."""
    half = height / 2
    top, bottom = mid_y - half, mid_y + half
    width = height * 1.05
    apex_x = left + width / 2
    apex_y = mid_y + half * 0.20
    points = [
        (left, bottom),
        (left, top),
        (apex_x, apex_y),
        (left + width, top),
        (left + width, bottom),
    ]
    d.line(points, fill=INK, width=stroke, joint="curve")
    # Square off the stroke ends the joint= option leaves rounded.
    for x in (left, left + width):
        d.rectangle([x - stroke / 2, bottom - stroke / 2,
                     x + stroke / 2, bottom + stroke / 2], fill=INK)
    return left + width


def main():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    mid_y = H // 2

    mark_right = draw_monogram(d, left=150, mid_y=mid_y, height=300, stroke=56)

    dot_r = 40
    dot_cx = mark_right + 110
    d.ellipse([dot_cx - dot_r, mid_y - dot_r, dot_cx + dot_r, mid_y + dot_r],
              fill=GREEN)

    font = _font(210)
    text_x = dot_cx + dot_r + 90
    name, suffix = "Munim", ".ai"
    # anchor="lm" keeps both runs on the same optical centre line.
    d.text((text_x, mid_y), name, font=font, fill=INK, anchor="lm")
    text_x += d.textlength(name, font=font)
    d.text((text_x, mid_y), suffix, font=font, fill=GREEN, anchor="lm")

    img.save(OUT)
    print(f"wrote {OUT} {img.size}")


if __name__ == "__main__":
    main()
