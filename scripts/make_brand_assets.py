"""Rasterise the Carthago brand mark into every static asset the site serves.

The mark — an open navy "C" enclosing a data mosaic and a rising bar chart — is
authored as vector geometry in ``web/app/components/BrandMark.tsx``. That file is
the source of truth; the constants below mirror it on the same 64x64 grid. Change
one, re-run this script.

Outputs (all regenerated from scratch):
    web/public/logo.png         256  transparent   generic mark (docs, mockups)
    web/app/icon.png            512  white plate    <link rel=icon> + JSON-LD logo
    web/app/apple-icon.png      180  white square   iOS home screen (it masks its own corners)
    web/app/favicon.ico         16/32/48 RGBA       browser tab
    web/app/opengraph-image.png 1200x630            social card
    web/app/twitter-image.png   1200x630            social card

favicon.ico MUST stay RGBA — Next 16 rejects an RGB .ico at build time.

Usage:  python scripts/make_brand_assets.py
Needs:  pillow, requests (not CI deps — this is a local, one-off generator).
"""

from __future__ import annotations

import io
import math
import tempfile
from pathlib import Path

import requests
from PIL import Image, ImageChops, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parent.parent
WEB = REPO / "web"

# ---------------------------------------------------------------------------
# Geometry — mirrors web/app/components/BrandMark.tsx on a 64x64 grid.
# ---------------------------------------------------------------------------
GRID = 64.0
CX = CY = 32.0
RING_R, RING_W = 25.5, 8.0  # centreline radius, stroke width
RING_GAP_DEG = 38.0  # the C opens +/-38 degrees off east
DISC_R = 19.5  # clips mosaic + bars -> the globe's curved edge

CELL, BASELINE, BAR_W = 4.7, 44.0, 5.0

# (x, y, tone) — rim cells are left to be clipped by the disc; that cut edge is
# what reads as a globe.
CELLS = [
    (13.5, 19.5, "m"), (13.5, 25.0, "p"), (13.5, 30.5, "l"), (13.5, 36.0, "m"),
    (19.0, 14.0, "p"), (19.0, 19.5, "l"), (19.0, 25.0, "m"), (19.0, 30.5, "p"),
    (19.0, 36.0, "l"), (19.0, 41.5, "p"),
    (24.5, 14.0, "l"), (24.5, 19.5, "p"), (24.5, 25.0, "l"), (24.5, 30.5, "m"),
    (24.5, 36.0, "p"), (24.5, 41.5, "l"),
]
# (x, top, tone) — bars rise left->right and deepen as they grow
BARS = [(30.2, 36.5, "l"), (36.0, 30.0, "m"), (41.8, 23.0, "d")]

# Tone ramps. The dark ramp inverts (the tall bar stays the highest-contrast
# element on a dark ground) and matches the dark: classes in BrandMark.tsx.
LIGHT = {"ring": "#0D1B2A", "d": "#1F2E4A", "m": "#2D5B8C", "l": "#7FA0BF", "p": "#E6EEF6"}
ON_NAVY = {"ring": "#FFFFFF", "d": "#A8C3E0", "m": "#6E97C8", "l": "#4E7092", "p": "#C9D8E8"}

SS = 4  # supersampling factor


def _hex(c: str) -> tuple[int, int, int, int]:
    c = c.lstrip("#")
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), 255)


def draw_mark(px: int, tones: dict[str, str]) -> Image.Image:
    """The mark alone, on transparency, at px x px."""
    n = px * SS
    s = n / GRID  # grid units -> supersampled pixels

    # Mosaic + bars, then punched through the disc so cells at the rim curve.
    content = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(content)
    for x, y, tone in CELLS:
        d.rounded_rectangle(
            [x * s, y * s, (x + CELL) * s, (y + CELL) * s],
            radius=0.5 * s, fill=_hex(tones[tone]),
        )
    for x, top, tone in BARS:
        d.rounded_rectangle(
            [x * s, top * s, (x + BAR_W) * s, BASELINE * s],
            radius=0.6 * s, fill=_hex(tones[tone]),
        )
    disc = Image.new("L", (n, n), 0)
    ImageDraw.Draw(disc).ellipse(
        [(CX - DISC_R) * s, (CY - DISC_R) * s, (CX + DISC_R) * s, (CY + DISC_R) * s],
        fill=255,
    )
    content.putalpha(ImageChops.multiply(content.getchannel("A"), disc))

    # The C: an arc from +38 to -38 degrees the long way round, round-capped.
    ring = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring)
    outer = RING_R + RING_W / 2
    rd.arc(
        [(CX - outer) * s, (CY - outer) * s, (CX + outer) * s, (CY + outer) * s],
        start=RING_GAP_DEG, end=360 - RING_GAP_DEG,
        fill=_hex(tones["ring"]), width=int(round(RING_W * s)),
    )
    for sign in (1, -1):
        a = math.radians(RING_GAP_DEG * sign)
        ex, ey = CX + RING_R * math.cos(a), CY + RING_R * math.sin(a)
        cap = RING_W / 2
        rd.ellipse(
            [(ex - cap) * s, (ey - cap) * s, (ex + cap) * s, (ey + cap) * s],
            fill=_hex(tones["ring"]),
        )

    mark = Image.alpha_composite(content, ring)
    return mark.resize((px, px), Image.LANCZOS)


def on_plate(px: int, inset: float, radius: float, bg: str = "#FFFFFF") -> Image.Image:
    """The mark centred on an opaque (optionally rounded) plate."""
    n = px * SS
    plate = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    ImageDraw.Draw(plate).rounded_rectangle(
        [0, 0, n - 1, n - 1], radius=radius * n, fill=_hex(bg)
    )
    plate = plate.resize((px, px), Image.LANCZOS)

    size = int(px * inset)
    mark = draw_mark(size, LIGHT)
    off = (px - size) // 2
    plate.alpha_composite(mark, (off, off))
    return plate


# ---------------------------------------------------------------------------
# Social card
# ---------------------------------------------------------------------------
FONT_URL = (
    "https://raw.githubusercontent.com/google/fonts/main/ofl/instrumentsans/"
    "InstrumentSans%5Bwdth%2Cwght%5D.ttf"
)


def _font_path() -> Path:
    """Instrument Sans (the site face). Cached in the OS temp dir."""
    cached = Path(tempfile.gettempdir()) / "InstrumentSans-var.ttf"
    if not cached.exists():
        r = requests.get(FONT_URL, timeout=30)
        r.raise_for_status()
        cached.write_bytes(r.content)
    return cached


def _font(size: int, weight: str) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(_font_path()), size)
    f.set_variation_by_name(weight)
    return f


def _track_to_width(d: ImageDraw.ImageDraw, xy, text, font, fill, width: float) -> None:
    """Letter-space `text` so it spans exactly `width` — the concept sets the
    tagline flush to the wordmark. Pillow has no tracking, so step glyph by glyph."""
    glyphs = sum(d.textlength(ch, font=font) for ch in text)
    tracking = (width - glyphs) / max(len(text) - 1, 1)
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=font, fill=fill)
        x += d.textlength(ch, font=font) + tracking


def social_card() -> Image.Image:
    w, h = 1200, 630

    # Vertical gradient: deep navy shading to the ink of the C.
    top, bot = _hex(LIGHT["d"]), _hex(LIGHT["ring"])
    grad = Image.new("RGBA", (1, h))
    for y in range(h):
        t = y / (h - 1)
        grad.putpixel((0, y), tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(4)))
    card = grad.resize((w, h), Image.BICUBIC)

    card.alpha_composite(draw_mark(300, ON_NAVY), (110, (h - 300) // 2))

    d = ImageDraw.Draw(card)
    word_font = _font(112, "Bold")
    x0 = 480
    d.text((x0, 232), "Carthago", font=word_font, fill=_hex("#FFFFFF"))

    # Rule + tagline run flush to the wordmark's own width.
    word_w = d.textlength("Carthago", font=word_font)
    d.line([(x0 + 6, 372), (x0 + word_w, 372)], fill=(255, 255, 255, 60), width=2)
    _track_to_width(
        d, (x0 + 6, 392), "TURKISH BANKING DATA",
        _font(28, "Medium"), _hex("#8FB0CF"), width=word_w - 6,
    )
    return card


def main() -> None:
    out: list[tuple[Path, Image.Image]] = []

    out.append((WEB / "public" / "logo.png", draw_mark(256, LIGHT)))
    # Rounded plate keeps the navy C legible against dark browser chrome.
    out.append((WEB / "app" / "icon.png", on_plate(512, inset=0.80, radius=0.22)))
    # iOS masks its own corners -> hand it a full-bleed square.
    out.append((WEB / "app" / "apple-icon.png", on_plate(180, inset=0.76, radius=0.0)))

    card = social_card()
    out.append((WEB / "app" / "opengraph-image.png", card))
    out.append((WEB / "app" / "twitter-image.png", card))

    for path, img in out:
        img.convert("RGBA").save(path, "PNG")
        print(f"  {path.relative_to(REPO)}  {img.size[0]}x{img.size[1]}")

    # RGBA, or Next 16's build rejects it.
    ico = on_plate(256, inset=0.80, radius=0.22).convert("RGBA")
    ico_path = WEB / "app" / "favicon.ico"
    ico.save(ico_path, "ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    with Image.open(io.BytesIO(ico_path.read_bytes())) as check:
        assert check.mode == "RGBA", f"favicon must be RGBA, got {check.mode}"
    print(f"  {ico_path.relative_to(REPO)}  16/32/48 RGBA")


if __name__ == "__main__":
    main()
