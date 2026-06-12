"""Download quarterly BRSA audit reports for all banks listed in
data/banks/audit_report_urls.json.

URLs are explicit per-bank, per-period, per-kind (consolidated / unconsolidated /
unconsolidated_zip for VAKBN). Filenames are heterogeneous across IR sites, so
URLs cannot be auto-constructed from a template — when a new period is published
each quarter, add the new URLs to that JSON file (see audit_reports/README.md).

Idempotent: skips files already on disk. Parallel: 16 worker threads.
Output: data/audit_reports/{ticker}/{TICKER}_{period}_{kind}.pdf
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG = REPO_ROOT / "data" / "banks" / "audit_report_urls.json"
OUT_ROOT = REPO_ROOT / "data" / "audit_reports"

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Accept": "application/pdf,application/octet-stream,*/*",
}
# Banks whose CDN blocks bare requests — supply Referer to bypass
REFERERS = {
    "TSKB":   "https://www.tskb.com.tr/en/investor-relations/financial-information",
    "QNBFB":  "https://www.qnb.com.tr/en/investor-relations/financial-information",
    "PASHA":  "https://www.pashabank.com.tr/tr/yatirimci-iliskileri",
    "AKTIF":  "https://www.aktifbank.com.tr/hakkimizda/finansal-bilgiler/denetim-raporlari",
    "VAKIFK": "https://www.vakifkatilim.com.tr/",
}


def download_pdf(url: str, dest: Path, ticker: str) -> tuple[bool, int, str]:
    """Returns (ok, size_or_status, note). Skips if file exists & non-empty."""
    if dest.exists() and dest.stat().st_size > 0:
        return True, dest.stat().st_size, "skip"
    headers = dict(UA)
    if ticker in REFERERS:
        headers["Referer"] = REFERERS[ticker]
    try:
        r = requests.get(url, headers=headers, timeout=120, allow_redirects=True)
    except requests.RequestException as e:
        return False, 0, f"err:{type(e).__name__}"
    if r.status_code != 200:
        return False, r.status_code, f"http:{r.status_code}"
    body = r.content
    # VAKIFK CMS bug: PDFs wrapped in 27-byte Java ObjectOutputStream header
    if body[:4] == b"\xac\xed\x00\x05" and b"%PDF" in body[:64]:
        body = body[body.find(b"%PDF"):]
    if not body.startswith(b"%PDF"):
        return False, len(body), "not-pdf"
    dest.write_bytes(body)
    return True, len(body), "ok"


def download_zip_extract_pdf(url: str, dest: Path, ticker: str) -> tuple[bool, int, str]:
    """For VAKBN solo files: download ZIP, extract first PDF inside."""
    if dest.exists() and dest.stat().st_size > 0:
        return True, dest.stat().st_size, "skip"
    try:
        r = requests.get(url, headers=UA, timeout=120)
    except requests.RequestException as e:
        return False, 0, f"err:{type(e).__name__}"
    if r.status_code != 200:
        return False, r.status_code, f"http:{r.status_code}"
    try:
        zf = zipfile.ZipFile(io.BytesIO(r.content))
    except zipfile.BadZipFile:
        return False, len(r.content), "bad-zip"
    pdf_names = [n for n in zf.namelist() if n.lower().endswith(".pdf")]
    if not pdf_names:
        return False, len(r.content), "no-pdf-in-zip"
    pdf = zf.read(pdf_names[0])
    if not pdf.startswith(b"%PDF"):
        return False, len(pdf), "extracted-not-pdf"
    dest.write_bytes(pdf)
    return True, len(pdf), "ok"


def build_targets(banks_cfg: dict) -> list[tuple[str, str, str, str, Path]]:
    """Returns (ticker, period, kind, url, dest) tuples for every URL in config."""
    targets: list[tuple[str, str, str, str, Path]] = []
    for ticker, b in banks_cfg.items():
        if "urls" not in b:
            continue
        out_dir = OUT_ROOT / ticker.lower()
        out_dir.mkdir(parents=True, exist_ok=True)
        for kind, period_map in b["urls"].items():
            normalised_kind = "unconsolidated" if kind == "unconsolidated_zip" else kind
            for period, url in period_map.items():
                fname = f"{ticker}_{period}_{normalised_kind}.pdf"
                targets.append((ticker, period, normalised_kind, url, out_dir / fname))
    return targets


def fetch_one(t):
    ticker, period, kind, url, dest = t
    if "_zip" in url[-10:]:  # crude detection
        ok, size, note = download_zip_extract_pdf(url, dest, ticker)
    elif url.endswith(".zip"):
        ok, size, note = download_zip_extract_pdf(url, dest, ticker)
    else:
        ok, size, note = download_pdf(url, dest, ticker)
    return ticker, period, kind, ok, size, note, dest


def main():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    targets = build_targets(cfg["banks"])
    print(f"{len(targets)} URLs to fetch (parallel, 16 workers)")
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    new = skipped = failed = 0
    manifest: list[dict] = []
    with ThreadPoolExecutor(max_workers=16) as ex:
        for fut in as_completed(ex.submit(fetch_one, t) for t in targets):
            ticker, period, kind, ok, size, note, dest = fut.result()
            if ok and note == "skip":
                skipped += 1
            elif ok:
                disp = f"{size/1024:7.1f} KB"
                print(f"  [OK]   {ticker:<8} {period} {kind:<14} {disp}", flush=True)
                new += 1
            else:
                print(f"  [FAIL] {ticker:<8} {period} {kind:<14} {note}", flush=True)
                failed += 1
            manifest.append({
                "ticker": ticker, "period": period, "kind": kind,
                "ok": ok, "note": note,
                "path": str(dest.relative_to(REPO_ROOT)),
            })

    (OUT_ROOT / "manifest_all_banks.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nnew={new}  skipped={skipped}  failed={failed}  total={len(targets)}")
    print(f"manifest: {OUT_ROOT/'manifest_all_banks.json'}")


if __name__ == "__main__":
    main()
