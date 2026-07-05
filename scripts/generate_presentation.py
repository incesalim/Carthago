"""Quick presentation generator — the sector "Read" as a PDF slide deck.

Pulls the deterministic per-tab takeaways from the live dashboard
({SITE_URL}/api/reads) — the same headline + driver bullets each page shows —
and lays them out as a self-contained 16:9 HTML deck (title + one slide per
section + closing), then renders it to PDF via headless Chrome/Edge. No LLM, no
metric re-derivation: the figures are exactly what the dashboard reports, so the
deck can never drift from the site.

Output lands in reports/ (gitignored): presentation-YYYY-MM-DD.pdf + .html.

Usage:
  python scripts/generate_presentation.py                 # fetch live → PDF
  python scripts/generate_presentation.py --open          # ...and open the PDF
  python scripts/generate_presentation.py --html-only     # skip the PDF render
  python scripts/generate_presentation.py --file reads.json   # render offline
  python scripts/generate_presentation.py --tabs overview,capital,profitability
  python scripts/generate_presentation.py --title "Q1 Board Pack" --out deck.pdf

Env: SITE_URL (default prod), CHROME_PATH (browser override).
Deps: requests (already in requirements.txt) + a local Chrome/Edge for the PDF.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_SITE = "https://turkish-banking-dashboard.incesalim10.workers.dev"

# Friendly section titles, keyed by the /api/reads `tab` slug. The default deck
# order is whatever order the endpoint returns (overview first).
SECTION_TITLES: dict[str, str] = {
    "overview": "Sector Overview",
    "credit": "Credit",
    "deposits": "Deposits",
    "asset-quality": "Asset Quality",
    "capital": "Capital",
    "profitability": "Profitability",
    "liquidity": "Liquidity",
    "market-risk": "Market Risk",
}

# --- "editorial" palette, mirrored from web/app/lib/chart-theme.ts (LIGHT) ---
PAPER = "#FBFAF7"
INK = "#16243B"
NAVY = "#1C3A60"
MUTED = "#5A6472"
HAIRLINE = "#E2DCD0"
FIG = "#1C3A60"  # figures — navy, bold

# Numeric figures to emphasise in prose: currency amounts (₺…) and any number
# glued to a unit (%, pp, ×, bp). Deliberately NOT bare integers/years, so
# "2026-05" and "4-week" stay plain. Applied AFTER html-escaping (the escaped
# entities never form a number+unit token, so this can't corrupt them).
FIG_RE = re.compile(
    r"(₺\s?\d[\d.,]*\s?(?:trn|bn|mn|m|k)?"
    r"|[+\-−]?\d[\d.,]*\s?(?:%|pp|ppt|bps|bp|×))"
)


def load_reads(site: str, file: str | None) -> list[dict]:
    """Fetch the takeaways from /api/reads, or read a saved JSON dump."""
    if file:
        data = json.loads(Path(file).read_text(encoding="utf-8"))
    else:
        r = requests.get(f"{site}/api/reads", timeout=90)
        r.raise_for_status()
        data = r.json()
    if not isinstance(data, list) or not data:
        raise SystemExit("reads payload is empty or not a list")
    return data


def select_tabs(reads: list[dict], tabs: str | None) -> list[dict]:
    """Filter + reorder sections by a comma-separated --tabs list."""
    if not tabs:
        return reads
    by_tab = {r["tab"]: r for r in reads}
    out: list[dict] = []
    for want in [t.strip() for t in tabs.split(",") if t.strip()]:
        if want in by_tab:
            out.append(by_tab[want])
        else:
            print(f"  (unknown tab '{want}' — skipping)", flush=True)
    if not out:
        raise SystemExit(f"--tabs matched nothing; available: {', '.join(by_tab)}")
    return out


def as_of(reads: list[dict]) -> str:
    """Pull the 'As of YYYY-MM' period out of the overview headline."""
    for r in reads:
        m = re.search(r"[Aa]s of (\d{4}-\d{2})", r.get("headline", ""))
        if m:
            return m.group(1)
    return ""


def emphasise(text: str) -> str:
    """HTML-escape, then wrap figure tokens in a styled span."""
    return FIG_RE.sub(r'<span class="fig">\1</span>', html.escape(text))


def strip_as_of(headline: str) -> str:
    """Drop a leading 'As of YYYY-MM:' clause — it's shown as the deck period —
    and re-capitalise the first word so the remainder reads as a sentence."""
    out = re.sub(r"^\s*[Aa]s of \d{4}-\d{2}:\s*", "", headline).strip()
    return out[:1].upper() + out[1:] if out else out


# ---------------------------------------------------------------- HTML build ---

def _css() -> str:
    return f"""
    @page {{ size: 1280px 720px; margin: 0; }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    body {{
      font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      color: {INK}; background: #ddd;
    }}
    .slide {{
      position: relative; width: 1280px; height: 720px; overflow: hidden;
      background: {PAPER}; page-break-after: always;
      display: flex; flex-direction: column; padding: 84px 96px 72px;
    }}
    .slide:last-child {{ page-break-after: auto; }}

    /* accents */
    .kicker {{
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
      font-size: 15px; letter-spacing: .22em; text-transform: uppercase;
      color: {NAVY}; font-weight: 600;
    }}
    .kicker::before {{
      content: ""; display: inline-block; width: 30px; height: 3px;
      background: {NAVY}; vertical-align: middle; margin-right: 14px;
      margin-bottom: 4px;
    }}
    .fig {{ color: {FIG}; font-weight: 600; }}
    .slide-num {{
      position: absolute; right: 96px; bottom: 40px;
      font-family: "SFMono-Regular", Consolas, monospace;
      font-size: 13px; color: {MUTED}; letter-spacing: .1em;
    }}
    .slide-foot {{
      position: absolute; left: 96px; bottom: 40px;
      font-size: 13px; color: {MUTED};
    }}
    .ghost {{
      position: absolute; right: 60px; top: 20px; font-family: Georgia, serif;
      font-size: 340px; line-height: 1; color: {NAVY}; opacity: .04;
      font-weight: 700; user-select: none;
    }}

    /* section slide */
    .headline {{
      font-family: Georgia, "Times New Roman", serif; font-weight: 600;
      font-size: 42px; line-height: 1.28; color: {INK};
      margin: 30px 0 34px; max-width: 1000px;
    }}
    .bullets {{ list-style: none; max-width: 1010px; }}
    .bullets li {{
      position: relative; font-size: 22px; line-height: 1.5; color: #3A4759;
      padding-left: 30px; margin-bottom: 18px;
    }}
    .bullets li::before {{
      content: ""; position: absolute; left: 4px; top: 12px;
      width: 8px; height: 8px; background: {NAVY}; border-radius: 50%;
    }}

    /* title slide */
    .title {{ justify-content: center; padding-left: 110px; }}
    .title::before {{
      content: ""; position: absolute; left: 0; top: 0; bottom: 0;
      width: 14px; background: {NAVY};
    }}
    .brand {{
      font-family: "SFMono-Regular", Consolas, monospace; font-size: 16px;
      letter-spacing: .22em; text-transform: uppercase; color: {NAVY};
      font-weight: 600; margin-bottom: 26px;
    }}
    h1.deck-title {{
      font-family: Georgia, serif; font-weight: 700; font-size: 76px;
      line-height: 1.08; color: {INK}; letter-spacing: -.5px; max-width: 940px;
    }}
    .deck-sub {{ font-size: 27px; color: {MUTED}; margin-top: 18px; font-weight: 400; }}
    .deck-period {{
      display: inline-block; margin-top: 40px; font-size: 20px; font-weight: 600;
      color: {NAVY}; border: 1.5px solid {NAVY}; border-radius: 999px;
      padding: 8px 22px;
    }}
    .deck-meta {{
      position: absolute; left: 110px; bottom: 56px; font-size: 15px;
      color: {MUTED};
    }}

    /* closing slide */
    .closing {{ justify-content: center; padding-left: 110px; }}
    .closing::before {{
      content: ""; position: absolute; left: 0; top: 0; bottom: 0;
      width: 14px; background: {NAVY};
    }}
    .closing h2 {{
      font-family: Georgia, serif; font-size: 40px; color: {INK};
      margin-bottom: 26px;
    }}
    .closing p {{
      font-size: 20px; line-height: 1.65; color: #3A4759; max-width: 880px;
      margin-bottom: 16px;
    }}
    .closing .fine {{ font-size: 15px; color: {MUTED}; margin-top: 20px; }}
    """


def _title_slide(title: str, subtitle: str, period: str, gen: str) -> str:
    period_pill = f'<div class="deck-period">As of {html.escape(period)}</div>' if period else ""
    return f"""
    <section class="slide title">
      <div class="brand">BDDK · Sector Analytics</div>
      <h1 class="deck-title">{html.escape(title)}</h1>
      <div class="deck-sub">{html.escape(subtitle)}</div>
      {period_pill}
      <div class="deck-meta">Generated {gen} · Source: BDDK monthly &amp; weekly
      bulletins + BRSA quarterly audit reports</div>
    </section>"""


def _section_slide(idx: int, total: int, tab: str, rd: dict, period: str) -> str:
    title = SECTION_TITLES.get(tab, tab.replace("-", " ").title())
    headline = emphasise(strip_as_of(rd.get("headline", "")))
    items = "".join(f"<li>{emphasise(i)}</li>" for i in rd.get("items", []))
    foot = f"Turkish Banking Sector · The Read" + (f" · {period}" if period else "")
    return f"""
    <section class="slide section">
      <div class="ghost">{idx:02d}</div>
      <div class="kicker">{idx:02d} · {html.escape(title.upper())}</div>
      <h2 class="headline">{headline}</h2>
      <ul class="bullets">{items}</ul>
      <div class="slide-foot">{html.escape(foot)}</div>
      <div class="slide-num">{idx} / {total}</div>
    </section>"""


def _closing_slide() -> str:
    return f"""
    <section class="slide closing">
      <div class="kicker">Methodology</div>
      <h2>How this deck is built</h2>
      <p>Every figure is drawn from the dashboard's deterministic insight
      engine — no model rewriting, no estimates. The same headline and drivers
      shown on each tab, generated on demand.</p>
      <p>Underlying data: BDDK monthly &amp; weekly banking bulletins and BRSA
      quarterly audit reports, refreshed on the pipeline's regular cadence.</p>
      <p class="fine">Indicative analytics for internal use — not investment
      advice. Ratios follow BDDK / BRSA definitions; audited metrics (CET1, LCR,
      NSFR) are quarterly.</p>
    </section>"""


def build_html(reads: list[dict], title: str, subtitle: str, gen: str) -> str:
    period = as_of(reads)
    total = len(reads)
    slides = [_title_slide(title, subtitle, period, gen)]
    for i, rd in enumerate(reads, start=1):
        slides.append(_section_slide(i, total, rd["tab"], rd, period))
    slides.append(_closing_slide())
    body = "\n".join(slides)
    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>{html.escape(title)}</title>\n<style>{_css()}</style>\n"
        f"</head>\n<body>\n{body}\n</body>\n</html>\n"
    )


# ------------------------------------------------------------------ PDF render ---

def find_browser(override: str | None) -> str | None:
    """Locate a Chromium-family browser for --print-to-pdf."""
    candidates: list[str] = []
    if override:
        candidates.append(override)
    if os.environ.get("CHROME_PATH"):
        candidates.append(os.environ["CHROME_PATH"])
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local = os.environ.get("LOCALAPPDATA", "")
    candidates += [
        rf"{pf}\Google\Chrome\Application\chrome.exe",
        rf"{pf86}\Google\Chrome\Application\chrome.exe",
        rf"{local}\Google\Chrome\Application\chrome.exe" if local else "",
        rf"{pf86}\Microsoft\Edge\Application\msedge.exe",
        rf"{pf}\Microsoft\Edge\Application\msedge.exe",
    ]
    for name in ("chrome", "google-chrome", "chromium", "chromium-browser", "msedge"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    for c in candidates:
        if c and Path(c).exists():
            return c
    return None


def render_pdf(browser: str, html_path: Path, pdf_path: Path) -> None:
    """Print the deck to PDF with a throwaway profile (won't touch the user's)."""
    with tempfile.TemporaryDirectory(prefix="deck-profile-") as profile:
        cmd = [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--no-first-run",
            f"--user-data-dir={profile}",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path}",
            html_path.as_uri(),
        ]
        print(f"$ {Path(browser).name} --print-to-pdf ...", flush=True)
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        raise SystemExit(
            f"PDF render failed (rc={res.returncode}).\n{res.stderr.strip()[:800]}"
        )


def open_file(path: Path) -> None:
    try:
        if os.name == "nt":
            os.startfile(str(path))  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception as e:  # noqa: BLE001
        print(f"  (couldn't auto-open: {e})", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--site", default=os.environ.get("SITE_URL") or DEFAULT_SITE)
    ap.add_argument("--file", help="Render from a saved /api/reads JSON dump (offline).")
    ap.add_argument("--out", help="Output PDF path (default reports/presentation-<date>.pdf).")
    ap.add_argument("--tabs", help="Comma-separated section slugs to include/reorder.")
    ap.add_argument("--title", default="Turkish Banking Sector")
    ap.add_argument("--subtitle", default="The Read — Sector Snapshot")
    ap.add_argument("--html-only", action="store_true", help="Write the HTML, skip the PDF.")
    ap.add_argument("--browser", help="Path to a Chrome/Edge/Chromium binary.")
    ap.add_argument("--open", action="store_true", help="Open the result when done.")
    args = ap.parse_args()

    reads = select_tabs(load_reads(args.site, args.file), args.tabs)
    print(f"[reads] {len(reads)} sections: {', '.join(r['tab'] for r in reads)}", flush=True)

    gen = date.today().isoformat()
    out_pdf = Path(args.out) if args.out else REPO / "reports" / f"presentation-{gen}.pdf"
    out_pdf = out_pdf.resolve()
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    out_html = out_pdf.with_suffix(".html")

    out_html.write_text(build_html(reads, args.title, args.subtitle, gen), encoding="utf-8")
    print(f"[html] {out_html}", flush=True)

    if args.html_only:
        print("[done] HTML only (--html-only). Open it and Ctrl+P → Save as PDF.", flush=True)
        if args.open:
            open_file(out_html)
        return 0

    browser = find_browser(args.browser)
    if not browser:
        print("[warn] No Chrome/Edge found — kept the HTML. Open it and "
              "Ctrl+P → Save as PDF, or pass --browser <path>.", flush=True)
        if args.open:
            open_file(out_html)
        return 0

    render_pdf(browser, out_html, out_pdf)
    print(f"[pdf]  {out_pdf}", flush=True)
    print(f"[done] {len(reads) + 2} slides.", flush=True)
    if args.open:
        open_file(out_pdf)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
