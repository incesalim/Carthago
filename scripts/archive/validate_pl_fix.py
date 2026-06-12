"""Validate the P&L column fix against every bank.

Re-extracts each bank's latest report with the current extractor and compares
its P&L magnitude (MAX(ABS(cur_amount))) to what's stored in D1. Expectation:

  - 2-column banks: UNCHANGED (the fix is a no-op for them) — proves no regression
  - 4-column interim banks: CHANGED — the correction (was storing the prior period)

  python scripts/validate_pl_fix.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

from src.audit_reports import extractor as E  # noqa: E402

CONFIG = REPO / "data" / "banks" / "audit_report_urls.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120 Safari/537.36"}


def d1_pl_max() -> dict[tuple[str, str], float]:
    out = subprocess.run(
        ["npx", "wrangler", "d1", "execute", "bddk-data", "--remote", "--json",
         "--command", "SELECT bank_ticker, period, MAX(ABS(amount)) m "
                      "FROM bank_audit_profit_loss GROUP BY bank_ticker, period"],
        cwd=str(REPO / "web"), capture_output=True, text=True, shell=(sys.platform == "win32"))
    data = json.loads(out.stdout)
    rows = data[0]["results"] if isinstance(data, list) else data["results"]
    return {(r["bank_ticker"], r["period"]): r["m"] for r in rows if r.get("m") is not None}


def latest(bank: dict):
    c = {}
    for _kind, pm in bank.get("urls", {}).items():
        for p, u in pm.items():
            c.setdefault(p, u)
    return (max(c), c[max(c)]) if c else None


def fetch(tk, bank):
    g = latest(bank)
    if not g:
        return tk, None, None, "no-url"
    p, u = g
    try:
        r = requests.get(u, headers=UA, timeout=25)
        r.raise_for_status()
        fd, path = tempfile.mkstemp(suffix=".pdf")
        Path(path).write_bytes(r.content)
        import os
        os.close(fd)
        return tk, p, path, "ok"
    except Exception as e:  # noqa: BLE001
        return tk, p, None, f"err:{type(e).__name__}"


def main() -> None:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    d1 = d1_pl_max()
    res = {}
    with ThreadPoolExecutor(max_workers=12) as ex:
        for f in as_completed(ex.submit(fetch, tk, cfg["banks"][tk]) for tk in cfg["banks"]):
            tk, p, path, st = f.result()
            res[tk] = (p, path, st)

    changed, regressions = [], []
    for tk in sorted(cfg["banks"]):
        p, path, st = res[tk]
        if st != "ok":
            print(f"{tk:<8} {st}")
            continue
        try:
            rep = E.extract(path)
            new = max((abs(r.cur_amount) for r in rep.profit_loss if r.cur_amount is not None),
                      default=None)
        except Exception as e:  # noqa: BLE001
            print(f"{tk:<8} extract-err {type(e).__name__}")
            Path(path).unlink(missing_ok=True)
            continue
        Path(path).unlink(missing_ok=True)
        old = d1.get((tk, p))
        if new is None or old is None:
            print(f"{tk:<8} period={p} new={new} d1={old}  (no compare)")
            continue
        delta = abs(new - old) / old if old else (0 if new == old else 1)
        tag = ""
        if delta > 0.005:
            tag = "  <-- CHANGED"
            changed.append(tk)
        print(f"{tk:<8} period={p} d1={old:,.0f} new={new:,.0f}{tag}")
    print("\nCHANGED banks (P&L corrected by the fix):", changed)


if __name__ == "__main__":
    main()
