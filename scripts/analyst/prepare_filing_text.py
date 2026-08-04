"""Prepare per-page filing text for the V2 research tools.

Downloads the filing PDF from R2 (key convention:
`<ticker_lower>/<TICKER>_<period>_<kind>.pdf`) and extracts the text of every
page with PyMuPDF into `data/filing_text_<BANK>_<PERIOD>_<KIND>.json`, which
`search_filing_text` / `get_source_page` read. Runs in CI (R2 creds are
secrets); locally it degrades to a warning unless creds exist.

    python scripts/analyst/prepare_filing_text.py --bank ALBRK --period 2025Q1 --kind unconsolidated
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bank", required=True)
    ap.add_argument("--period", required=True)
    ap.add_argument("--kind", required=True, choices=["consolidated", "unconsolidated"])
    ap.add_argument("--out-dir", default=str(REPO / "data"))
    a = ap.parse_args()

    try:
        import fitz  # PyMuPDF — the repo's only sanctioned PDF engine
        from src.audit_reports import r2_storage
    except ImportError as e:
        print(f"prepare_filing_text: missing dependency ({e}) — source-page tools will be unavailable")
        return 0  # degrade, don't block the research run

    key = f"{a.bank.lower()}/{a.bank}_{a.period}_{a.kind}.pdf"
    if not r2_storage.exists(key):
        print(f"prepare_filing_text: {key} not in R2 — source-page tools will be unavailable")
        return 0
    tmp = Path(a.out_dir) / f"_filing_{a.bank}_{a.period}_{a.kind}.pdf"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    r2_storage.download_to(key, tmp)

    pages = []
    with fitz.open(tmp) as doc:
        for i, page in enumerate(doc):
            pages.append({"page": i + 1, "text": page.get_text()})
    tmp.unlink(missing_ok=True)

    out = Path(a.out_dir) / f"filing_text_{a.bank}_{a.period}_{a.kind}.json"
    out.write_text(
        json.dumps({"bank": a.bank, "period": a.period, "kind": a.kind, "pages": pages}, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"prepare_filing_text: {len(pages)} pages → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
