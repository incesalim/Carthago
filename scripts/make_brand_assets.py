"""Composite the Carthago brand mark into every static asset the site serves.

The mark — an open navy "C" enclosing a globe, a data mosaic and a rising bar
chart that forms an "i" — is the user's own artwork, keyed to transparency from
the brand sheet and committed at ``scripts/brand/carthago-mark.png``. That file
is the source of truth; every asset below is composited from it, so the mark can
never drift between uses. To change the logo, replace that one PNG and re-run.

Outputs (all regenerated from scratch):
    web/public/logo.png          84  transparent   the mark alone, NAV SIZE (see below)
    web/public/logo-dark.png     84  transparent   dark-sheet variant of the same
    web/app/icon.png            512  white plate    <link rel=icon> + JSON-LD logo
    web/app/apple-icon.png      180  white square   iOS home screen (masks its own corners)
    web/app/favicon.ico         16/32/48 RGBA       browser tab
    web/app/opengraph-image.png 1200x630 light      social card
    web/app/twitter-image.png   1200x630 light      social card

favicon.ico MUST stay RGBA — Next 16 rejects an RGB .ico at build time.

The nav logos are sized for the NAV, not for archival. They render at 28 CSS px,
`unoptimized` (OpenNext serves no image optimizer), and BOTH are in the DOM with
`priority` — the light/dark swap is a CSS class, so the browser preloads each. At
256px that was 76 KB of PNG to paint a 28px mark, which the 2026-07-12 site
evaluation flagged and the 07-25 re-check measured as still the largest trivially
avoidable payload on every page. They are now emitted at 84px (3x, crisp to
DPR 3) and palette-quantised: ~3.3 KB each, mean per-pixel error 1.1/255 against
the straight resample — invisible at 28px, ~70 KB saved on every page load.
Anything that needs the mark LARGE should composite it from
`scripts/brand/carthago-mark.png`, which stays the source of truth.

Usage:  python scripts/make_brand_assets.py
Needs:  pillow, requests (not CI deps — this is a local, one-off generator).
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parent.parent
WEB = REPO / "web"
MARK_SRC = REPO / "scripts" / "brand" / "carthago-mark.png"

# Brand palette (web/DESIGN.md). Logo + social card only — not a UI palette.
INK = "#0D1B2A"      # the C
MID = "#2D5B8C"      # tagline
PAPER = "#F7F8F6"    # card ground (matches the app's light ground)
CHIP = "#FFFFFF"     # icon plate


def _hex(c: str) -> tuple[int, int, int, int]:
    c = c.lstrip("#")
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), 255)


def load_mark() -> Image.Image:
    return Image.open(MARK_SRC).convert("RGBA")


def lighten_for_dark(mark: Image.Image, lift: float = 0.5) -> Image.Image:
    """A dark-mode variant of the mark: the same compass, tonally lifted so its
    navy elements (ring, hub, needle) read on a dark ground instead of sinking
    into it. Each pixel's lightness is raised toward white while its hue and
    chroma are preserved, so it stays the blue compass — just brighter."""
    import numpy as np

    a = np.asarray(mark.convert("RGBA"), dtype=np.float32) / 255.0
    r, g, b, al = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    lo = np.minimum(np.minimum(r, g), b)
    hi = np.maximum(np.maximum(r, g), b)
    lum = (lo + hi) / 2
    lum_new = lum + (1 - lum) * lift
    # rescale chroma into the lightness headroom so hue is kept and nothing clips
    room = np.minimum(lum_new, 1 - lum_new)
    have = np.minimum(lum, 1 - lum)
    scale = np.where(have > 1e-3, room / np.maximum(have, 1e-3), 1.0)
    out = np.stack(
        [np.clip(lum_new + (c - lum) * scale, 0, 1) for c in (r, g, b)] + [al],
        axis=-1,
    )
    return Image.fromarray((out * 255).astype("uint8"), "RGBA")


def fit(mark: Image.Image, box: int) -> Image.Image:
    """Scale the mark to fit a box x box square, preserving aspect + transparency."""
    m = mark.copy()
    m.thumbnail((box, box), Image.LANCZOS)
    out = Image.new("RGBA", (box, box), (0, 0, 0, 0))
    out.alpha_composite(m, ((box - m.width) // 2, (box - m.height) // 2))
    return out


def transparent(mark: Image.Image, px: int, inset: float = 1.0) -> Image.Image:
    """The mark on a transparent canvas, so it blends with any surface (a browser
    tab bar, the paper ground) instead of sitting in a plate. `inset` < 1 leaves a
    little breathing room around the mark."""
    canvas = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    m = fit(mark, round(px * inset))
    canvas.alpha_composite(m, ((px - m.width) // 2, (px - m.height) // 2))
    return canvas


def on_plate(mark: Image.Image, px: int, inset: float, radius: float,
             bg: str = CHIP) -> Image.Image:
    """The mark centred on an opaque (optionally rounded) plate."""
    SS = 4
    n = px * SS
    plate = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    ImageDraw.Draw(plate).rounded_rectangle(
        [0, 0, n - 1, n - 1], radius=radius * n, fill=_hex(bg)
    )
    plate = plate.resize((px, px), Image.LANCZOS)
    plate.alpha_composite(fit(mark, int(px * inset)),
                          (round(px * (1 - inset) / 2), round(px * (1 - inset) / 2)))
    return plate


# ---------------------------------------------------------------------------
# Social card — the mark + wordmark on the light brand ground (matches the sheet).
# ---------------------------------------------------------------------------
FONT_URL = (
    "https://raw.githubusercontent.com/google/fonts/main/ofl/instrumentsans/"
    "InstrumentSans%5Bwdth%2Cwght%5D.ttf"
)


def _font_path() -> Path:
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


def _track_to_width(d, xy, text, font, fill, width: float) -> None:
    """Letter-space `text` to span exactly `width` (the sheet sets the tagline
    flush to the wordmark). Pillow has no tracking, so step glyph by glyph."""
    glyphs = sum(d.textlength(ch, font=font) for ch in text)
    tracking = (width - glyphs) / max(len(text) - 1, 1)
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=font, fill=fill)
        x += d.textlength(ch, font=font) + tracking


def social_card(mark: Image.Image) -> Image.Image:
    w, h = 1200, 630
    card = Image.new("RGBA", (w, h), _hex(PAPER))

    m = fit(mark, 320)
    card.alpha_composite(m, (150, (h - m.height) // 2))

    d = ImageDraw.Draw(card)
    word_font = _font(120, "Bold")
    x0 = 510
    d.text((x0, 224), "Carthago", font=word_font, fill=_hex(INK))
    word_w = d.textlength("Carthago", font=word_font)
    d.line([(x0 + 6, 372), (x0 + word_w, 372)], fill=_hex(MID)[:3] + (110,), width=2)
    _track_to_width(
        d, (x0 + 6, 392), "TURKISH BANKING DATA",
        _font(29, "Medium"), _hex(MID), width=word_w - 6,
    )
    return card


# Nav display is 28 CSS px; 3x covers every DPR in the wild.
NAV_PX = 84
# 255 colours costs 3.3 KB and beats 200 on encoding while halving the error of
# 128 (measured mean 1.11 vs 1.33 /255). Full RGBA at this size is 10 KB — 3x the
# bytes for a difference no eye resolves on a 28px mark.
NAV_COLOURS = 255


def save_nav_logo(img: Image.Image, path: Path) -> int:
    """Write a nav mark: quantised, optimised, alpha intact. Returns bytes."""
    q = img.convert("RGBA").quantize(colors=NAV_COLOURS, method=Image.FASTOCTREE)
    q.save(path, "PNG", optimize=True)
    return path.stat().st_size


def main() -> None:
    mark = load_mark()
    dark = lighten_for_dark(mark)
    # The two nav marks take the quantised path — see NAV_PX above.
    for path, img in (
        (WEB / "public" / "logo.png", transparent(mark, NAV_PX)),
        # Dark-mode nav variant — same compass, lifted to read on the graphite sheet.
        (WEB / "public" / "logo-dark.png", transparent(dark, NAV_PX)),
    ):
        n = save_nav_logo(img, path)
        print(f"  {path.relative_to(REPO)}  {NAV_PX}x{NAV_PX}  {n:,} B")

    out: list[tuple[Path, Image.Image]] = [
        # Transparent so the tab-bar / page ground shows through and the mark
        # blends in, rather than sitting in a white box.
        (WEB / "app" / "icon.png", transparent(mark, 256, inset=0.92)),
        # iOS ignores transparency (renders it black) and masks its own corners,
        # so this one alone gets an opaque white square.
        (WEB / "app" / "apple-icon.png", on_plate(mark, 180, inset=0.72, radius=0.0)),
    ]
    card = social_card(mark)
    out.append((WEB / "app" / "opengraph-image.png", card))
    out.append((WEB / "app" / "twitter-image.png", card))

    for path, img in out:
        img.convert("RGBA").save(path, "PNG")
        print(f"  {path.relative_to(REPO)}  {img.size[0]}x{img.size[1]}")

    # Transparent (blends with the tab bar), RGBA — an RGB .ico fails the Next build.
    ico = transparent(mark, 64, inset=0.92).convert("RGBA")
    ico_path = WEB / "app" / "favicon.ico"
    ico.save(ico_path, "ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    with Image.open(io.BytesIO(ico_path.read_bytes())) as check:
        assert check.mode == "RGBA", f"favicon must be RGBA, got {check.mode}"
    print(f"  {ico_path.relative_to(REPO)}  16/32/48 RGBA")


if __name__ == "__main__":
    main()
