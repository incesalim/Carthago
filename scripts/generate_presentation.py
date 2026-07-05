"""Quick presentation generator — the sector "Read" as a PDF slide deck.

Thin CLI wrapper: fetches the fully-rendered deck HTML from the dashboard's
`/api/presentation` route (the single source of truth — dark title slide, KPI
vitals, one slide per tab with a trend chart, methodology; built by
web/app/lib/presentation-deck.ts off the site's own metric functions), then
prints it to PDF with a headless Chrome/Edge. The route can't produce a PDF
itself (Workers can't run headless Chrome); this script is that render step for
an unattended file. In the browser, use /admin → Presentation → Generate PDF.

Output lands in reports/ (gitignored): presentation-YYYY-MM-DD.pdf + .html.

Usage:
  python scripts/generate_presentation.py                 # fetch live → PDF
  python scripts/generate_presentation.py --open          # ...and open the PDF
  python scripts/generate_presentation.py --html-only     # save the HTML only
  python scripts/generate_presentation.py --tabs overview,capital,profitability
  python scripts/generate_presentation.py --title "Q1 Board Pack" --out deck.pdf
  python scripts/generate_presentation.py --file deck.html   # print a local HTML

Env: SITE_URL (default prod), CHROME_PATH (browser override).
Deps: requests (already in requirements.txt) + a local Chrome/Edge for the PDF.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import urllib.parse
from datetime import date
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_SITE = "https://turkish-banking-dashboard.incesalim10.workers.dev"


def fetch_html(site: str, tabs: str | None, title: str | None) -> str:
    """Pull the rendered deck HTML from /api/presentation."""
    params = {}
    if tabs:
        params["tabs"] = tabs
    if title:
        params["title"] = title
    url = f"{site}/api/presentation"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    print(f"[fetch] {url}", flush=True)
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    return r.text


def find_browser(override: str | None) -> str | None:
    """Locate a Chromium-family browser for --print-to-pdf."""
    import shutil

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
    ap.add_argument("--file", help="Print a local deck HTML instead of fetching.")
    ap.add_argument("--out", help="Output PDF path (default reports/presentation-<date>.pdf).")
    ap.add_argument("--tabs", help="Comma-separated section slugs to include/reorder.")
    ap.add_argument("--title", help="Override the deck title.")
    ap.add_argument("--html-only", action="store_true", help="Save the HTML, skip the PDF.")
    ap.add_argument("--browser", help="Path to a Chrome/Edge/Chromium binary.")
    ap.add_argument("--open", action="store_true", help="Open the result when done.")
    args = ap.parse_args()

    html = Path(args.file).read_text(encoding="utf-8") if args.file else fetch_html(
        args.site, args.tabs, args.title
    )

    gen = date.today().isoformat()
    out_pdf = Path(args.out) if args.out else REPO / "reports" / f"presentation-{gen}.pdf"
    out_pdf = out_pdf.resolve()
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    out_html = out_pdf.with_suffix(".html")

    out_html.write_text(html, encoding="utf-8")
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
    print("[done]", flush=True)
    if args.open:
        open_file(out_pdf)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
