#!/usr/bin/env python3
"""Source each bank's brand mark into web/public/logos/<TICKER>.png.

Deterministic, re-runnable, no API keys. For every ticker in
data/banks/bank_logo_domains.json we:

  1. Fetch the bank's homepage and read its declared icons — preferring the
     largest ``apple-touch-icon`` (a 180px+ square brand mark), then any sized
     ``rel=icon`` PNG. Well-known paths (/apple-touch-icon.png, /favicon.ico)
     are probed as a backstop.
  2. Fall back to the DuckDuckGo and Google favicon services when the site
     declares nothing usable.
  3. Validate each candidate is a real raster image at least MIN_EDGE px on its
     short side, pick the largest, pad it to a centred square and write a
     capped-size PNG.

Anything that can't be sourced at acceptable quality is listed under NEEDS
MANUAL so it can be dropped in by hand (web/public/logos/<TICKER>.png). The
UI degrades to a neutral placeholder for missing files, so partial coverage
never breaks a page.

Usage:
    python scripts/fetch_bank_logos.py            # all banks
    python scripts/fetch_bank_logos.py AKBNK GARAN  # a subset
    python scripts/fetch_bank_logos.py --force    # re-fetch even if present
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup
from PIL import Image

# Banks that expose no usable square icon on-site. Curated real logos, best
# source per bank. These are wide wordmarks — the UI renders every logo at a
# fixed height so shape is fine.
#
# WIKIMEDIA: Commons file titles, rendered to PNG by Wikimedia's own SVG
# rasteriser (imageinfo thumburl) and downloaded with a Commons referer.
# OVERRIDES: direct logo URLs from the bank's own site; SVGs are rasterised
# through the weserv image proxy since we have no local SVG renderer.
WIKIMEDIA: dict[str, str] = {
    "AKBNK": "File:Akbank logo.svg",
    "ALNTF": "File:Alternatif Bank logo.png",
    "GARAN": "File:Garanti Bankası Logo.svg",  # on-site icon was a stray graphic
    "QNBFB": "File:QNB Logo.svg",
    "VAKBN": "File:Vakıfbank logo.svg",
    "TEB": "File:TEB LOGO.png",
    "YKBNK": "File:Yapı kredi logo.png",       # upgrade bare aries mark -> wordmark
}
OVERRIDES: dict[str, str] = {
    "ODEA": "https://www.odeabank.com.tr/_assets/img/logo.svg",
    "SKBNK": "https://www.sekerbank.com.tr/icons/sekerbankLogo73tr.svg",
    "TSKB": "https://www.tskb.com.tr/assets/svg/logotype-color.svg",
    "TFKB": "https://www.turkiyefinans.com.tr/SiteAssets/img/tfkb-logo_2x.png",
    "ICBCT": "https://www.icbc.com.tr/tr/images/logo/logo.png",
}
WESERV = "https://images.weserv.nl/?url={}&w=512&output=png"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"

ROOT = Path(__file__).resolve().parents[1]
DOMAINS_FILE = ROOT / "data" / "banks" / "bank_logo_domains.json"
OUT_DIR = ROOT / "web" / "public" / "logos"
MANIFEST_FILE = ROOT / "web" / "app" / "lib" / "bank-logos.generated.ts"

MIN_EDGE = 48          # reject anything smaller than this on its short side
TARGET_MAX = 256       # cap the stored logo's long edge at this many px
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept": "text/html,image/*,*/*"}
TIMEOUT = 20


def _get(url: str, headers: dict | None = None) -> requests.Response | None:
    try:
        r = requests.get(
            url, headers=headers or HEADERS, timeout=TIMEOUT, allow_redirects=True
        )
        if r.status_code == 200 and r.content:
            return r
    except requests.RequestException:
        pass
    return None


def _size_key(sizes: str | None) -> int:
    """Largest edge declared in a link's ``sizes`` attribute (0 if absent)."""
    if not sizes:
        return 0
    best = 0
    for tok in sizes.replace(",", " ").split():
        if "x" in tok.lower():
            try:
                w, h = (int(p) for p in tok.lower().split("x")[:2])
                best = max(best, w, h)
            except ValueError:
                continue
    return best


def homepage_candidates(base: str) -> list[str]:
    """Ordered icon URLs declared by a homepage, best first."""
    r = _get(base)
    if not r:
        return []
    final = str(r.url)
    soup = BeautifulSoup(r.text, "lxml")
    apple: list[tuple[int, str]] = []
    icons: list[tuple[int, str]] = []
    for link in soup.find_all("link"):
        rels = " ".join(link.get("rel") or []).lower()
        href = link.get("href")
        if not href:
            continue
        url = urljoin(final, href)
        px = _size_key(link.get("sizes"))
        if "apple-touch-icon" in rels:
            apple.append((px or 180, url))  # apple icons are 180px by convention
        elif "icon" in rels and "mask-icon" not in rels:
            if url.lower().split("?")[0].endswith((".png", ".ico")):
                icons.append((px, url))
    apple.sort(key=lambda t: t[0], reverse=True)
    icons.sort(key=lambda t: t[0], reverse=True)
    # Well-known fallbacks the page may not declare.
    guesses = [
        urljoin(final, "/apple-touch-icon.png"),
        urljoin(final, "/apple-touch-icon-precomposed.png"),
    ]
    ordered = [u for _, u in apple] + [u for _, u in icons] + guesses
    # De-dup, preserve order.
    seen, out = set(), []
    for u in ordered:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def service_candidates(domain: str) -> list[str]:
    return [
        f"https://icons.duckduckgo.com/ip3/{domain}.ico",
        f"https://www.google.com/s2/favicons?domain={domain}&sz=256",
    ]


def load_image(url: str) -> Image.Image | None:
    r = _get(url)
    if not r:
        return None
    try:
        img = Image.open(io.BytesIO(r.content))
        img.load()
    except Exception:
        return None
    # .ico files carry several sizes — take the biggest frame.
    if getattr(img, "format", "") == "ICO":
        try:
            biggest = max(img.ico.sizes()) if hasattr(img, "ico") else img.size
            img = img.ico.getimage(biggest) if hasattr(img, "ico") else img
        except Exception:
            pass
    if img.mode not in ("RGBA", "RGB", "P", "LA"):
        img = img.convert("RGBA")
    return img


def load_via_weserv(url: str) -> Image.Image | None:
    """Fetch through the weserv proxy, which rasterises SVG and re-encodes PNG."""
    return load_image(WESERV.format(quote(url.split("://", 1)[-1])))


def load_override(url: str) -> Image.Image | None:
    """A curated logo URL: SVG (or a blocked host) goes via weserv, else direct."""
    if url.lower().split("?")[0].endswith(".svg"):
        return load_via_weserv(url)
    return load_image(url) or load_via_weserv(url)


def load_wikimedia(file_title: str) -> Image.Image | None:
    """Render a Commons file to PNG via its API thumburl (Wikimedia rasterises
    SVG server-side); download it with a Commons referer to satisfy hotlink
    protection."""
    try:
        r = requests.get(
            COMMONS_API,
            params={
                "action": "query", "titles": file_title, "prop": "imageinfo",
                "iiprop": "url", "iiurlwidth": 960, "format": "json",
            },
            headers=HEADERS, timeout=TIMEOUT,
        ).json()
    except (requests.RequestException, ValueError):
        return None
    thumb = None
    for _, p in r.get("query", {}).get("pages", {}).items():
        for ii in p.get("imageinfo", []):
            thumb = ii.get("thumburl") or ii.get("url")
    if not thumb:
        return None
    img_r = _get(thumb, {**HEADERS, "Referer": "https://commons.wikimedia.org/"})
    if not img_r:
        return None
    try:
        img = Image.open(io.BytesIO(img_r.content))
        img.load()
        return img
    except Exception:
        return None


def normalize(img: Image.Image) -> Image.Image:
    """Trim transparent margins and cap the long edge, keeping the natural
    aspect ratio. Logos are a mix of square marks and wide wordmarks; the UI
    renders every one at a fixed height, so a tight natural-aspect crop keeps
    both legible (a square padded to fit would shrink a wordmark to a sliver)."""
    img = img.convert("RGBA")
    bbox = img.split()[3].getbbox()  # non-transparent region
    if bbox:
        img = img.crop(bbox)
    edge = max(img.size)
    if edge > TARGET_MAX:
        scale = TARGET_MAX / edge
        img = img.resize(
            (round(img.width * scale), round(img.height * scale)), Image.LANCZOS
        )
    return img


def best_logo(domains: list[str]) -> tuple[Image.Image, str] | None:
    """Best (image, source) across a bank's candidate domains."""
    best: tuple[int, Image.Image, str] | None = None
    for domain in domains:
        urls: list[tuple[str, str]] = []
        for base in (f"https://www.{domain}", f"https://{domain}"):
            urls += [(u, "site") for u in homepage_candidates(base)]
            if urls:
                break
        urls += [(u, "favicon-svc") for u in service_candidates(domain)]
        for url, kind in urls:
            img = load_image(url)
            if img is None:
                continue
            short = min(img.size)
            if short < MIN_EDGE:
                continue
            score = short + (1000 if kind == "site" else 0)  # prefer site icons
            if best is None or score > best[0]:
                best = (score, img, f"{kind}:{url}")
            # A large site icon is good enough; stop probing this domain.
            if kind == "site" and short >= 120:
                return best[1], best[2]
    return (best[1], best[2]) if best else None


def write_manifest() -> None:
    """Emit each committed logo's intrinsic [width, height], so the UI renders a
    real <Image> (with the right aspect ratio, at a fixed height) for those and a
    neutral placeholder for the rest — no broken-image requests. Kept in sync on
    every run."""
    rows = []
    for p in sorted(OUT_DIR.glob("*.png")):
        w, h = Image.open(p).size
        rows.append(f'  "{p.stem}": [{w}, {h}],')
    body = "\n".join(rows)
    MANIFEST_FILE.write_text(
        "// AUTO-GENERATED by scripts/fetch_bank_logos.py — do not edit by hand.\n"
        "// Tickers with a committed brand logo in web/public/logos/<TICKER>.png,\n"
        "// mapped to the PNG's intrinsic [width, height] (natural aspect ratio).\n"
        "export const BANK_LOGOS: Record<string, readonly [number, number]> = {\n"
        + body
        + "\n};\n",
        encoding="utf-8",
    )
    print(f"  manifest: {len(rows)} tickers -> {MANIFEST_FILE.relative_to(ROOT)}")


def renormalize() -> int:
    """Re-apply normalize() to every committed logo in place (no network)."""
    for p in sorted(OUT_DIR.glob("*.png")):
        normalize(Image.open(p)).save(p, "PNG")
        print(f"  {p.stem:8s} {Image.open(p).size}")
    write_manifest()
    return 0


def main(argv: list[str]) -> int:
    # Sources carry Turkish characters; keep the console from dying on cp1252.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if "--renorm" in argv:
        return renormalize()
    force = "--force" in argv
    only = [a.upper() for a in argv if not a.startswith("-")]

    cfg = json.loads(DOMAINS_FILE.read_text(encoding="utf-8"))["domains"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    ok, skipped, failed = [], [], []
    for ticker, val in cfg.items():
        if only and ticker not in only:
            continue
        out = OUT_DIR / f"{ticker}.png"
        if out.exists() and not force:
            skipped.append(ticker)
            continue
        # Curated sources win over on-site scraping when present.
        img = source = None
        if ticker in WIKIMEDIA:
            img = load_wikimedia(WIKIMEDIA[ticker])
            source = f"wikimedia:{WIKIMEDIA[ticker]}"
        if img is None and ticker in OVERRIDES:
            img = load_override(OVERRIDES[ticker])
            source = f"override:{OVERRIDES[ticker]}"
        if img is None:
            domains = [val] if isinstance(val, str) else list(val)
            res = best_logo(domains)
            if res is not None:
                img, source = res
        if img is None:
            failed.append(ticker)
            print(f"  {ticker:8s} FAIL   (no usable logo)")
            continue
        normalize(img).save(out, "PNG")
        px = min(Image.open(out).size)
        ok.append(ticker)
        print(f"  {ticker:8s} OK     {px}px  <- {source[:88]}")

    print("\n--- summary ---")
    print(f"  fetched : {len(ok)}  {' '.join(ok)}")
    if skipped:
        print(f"  skipped : {len(skipped)} (already present; --force to refresh)")
    if failed:
        print(f"  NEEDS MANUAL ({len(failed)}): {' '.join(failed)}")
        print("  -> drop a square PNG at web/public/logos/<TICKER>.png")
    write_manifest()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
