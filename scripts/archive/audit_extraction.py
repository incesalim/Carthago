"""One-off audit: find banks whose balance sheet has 3+ period columns.

The BS extractor assumes 2 periods (6 cols: TL/FC/Total x current/prior). Banks
that print extra period columns (e.g. Eximbank's 3 periods = 9 numbers/row) were
mis-parsed — the prior period was stored as current. The extractor fix takes the
first 6 columns for clean triplet-multiples. This script re-extracts each bank's
latest report and reports the number of numeric columns on its TOTAL ASSETS row
+ the (now-fixed) current total, so we know which banks to re-extract + backfill.

  python scripts/audit_extraction.py
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

import pdfplumber  # noqa: E402

from src.audit_reports import discovery as D  # noqa: E402
from src.audit_reports import extractor as E  # noqa: E402

CONFIG = REPO / "data" / "banks" / "audit_report_urls.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120 Safari/537.36"}


def latest_url(ticker: str, bank: dict) -> tuple[str, str] | None:
    """(period, url) for the bank's most recent report — prefer auto-discovery."""
    cands: dict[str, str] = {}
    try:
        for period, kind, url in D.discover_from_ir(ticker, bank):
            if kind == "unconsolidated" or kind not in cands.get(period, ""):
                cands[period] = url
    except Exception:
        pass
    for kind, pm in bank.get("urls", {}).items():
        for period, url in pm.items():
            cands.setdefault(period, url)
    if not cands:
        return None
    p = max(cands)
    return p, cands[p]


def audit_one(ticker: str, bank: dict) -> dict:
    got = latest_url(ticker, bank)
    if not got:
        return {"ticker": ticker, "status": "no-url"}
    period, url = got
    try:
        r = requests.get(url, headers=UA, timeout=90)
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001
        return {"ticker": ticker, "period": period, "status": f"fetch:{type(e).__name__}"}
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(r.content)
        tmp = f.name
    try:
        # number of columns on the assets total row (pre-fix indicator)
        ncols = None
        try:
            with pdfplumber.open(tmp) as pdf:
                loc = E._locate_pages(pdf)
                if "bs_assets" in loc:
                    txt = E.extract_page_text_repaired(pdf.pages[loc["bs_assets"] - 1])
                    for line in txt.splitlines():
                        if re.search(r"\b(TOTAL ASSETS|TOPLAM AKT|VARLIKLAR TOPLAM|AKTİF TOPLAM)",
                                     line, re.I):
                            ncols = len(re.findall(E.NUM_PAT, line))
                            break
        except Exception:
            pass
        rep = E.extract(tmp)
        cur = rep.bs_assets[-1].cur_total if rep.bs_assets else None
        return {"ticker": ticker, "period": period, "status": "ok",
                "ncols": ncols, "cur_total": cur,
                "multi": bool(ncols and ncols > 6 and ncols % 3 == 0)}
    finally:
        Path(tmp).unlink(missing_ok=True)


def main() -> None:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    wanted = [t.upper() for t in sys.argv[1:]] or list(cfg["banks"])
    affected = []
    for tk in wanted:
        if tk not in cfg["banks"]:
            continue
        r = audit_one(tk, cfg["banks"][tk])
        flag = "  <-- 3-PERIOD" if r.get("multi") else ""
        ct = f"{r['cur_total']:,.0f}" if r.get("cur_total") else "-"
        print(f"{tk:<8} {r['status']:<14} period={r.get('period','?'):<7} "
              f"cols={r.get('ncols')} cur_total={ct}{flag}", flush=True)
        if r.get("multi"):
            affected.append(tk)
    print("\n" + "=" * 60)
    print(f"3-period (affected) banks: {affected}")


if __name__ == "__main__":
    main()
