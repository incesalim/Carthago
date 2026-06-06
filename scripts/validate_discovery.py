"""Validate IR-page auto-discovery against the hand-maintained config.

For each bank, runs src.audit_reports.discovery.discover_from_ir and compares
the result to data/banks/audit_report_urls.json (the oracle):

  - correct  : (kind, period) in both, same document path
  - MISMATCH : (kind, period) in both, DIFFERENT path  ← parser grabbed wrong link
  - new      : (kind, period) discovered but not in config (candidate new quarter)

A bank PASSES (safe to add to discovery.DISCOVERY_BANKS) when it reproduces its
latest known period and has no mismatch within the most recent few periods.
Older-period mismatches are tolerated: scrape_to_r2 keys R2 by (ticker, period,
kind) and skips anything already stored, so a wrong URL for an already-ingested
quarter is a harmless no-op — only the next new quarter's URL must be right, and
the recent window is the proxy for that. Run ad hoc:

  python scripts/validate_discovery.py            # all banks
  python scripts/validate_discovery.py AKTIF ALBRK # a subset
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

from src.audit_reports import discovery  # noqa: E402

CONFIG = REPO / "data" / "banks" / "audit_report_urls.json"


def _path(u: str) -> str:
    import re
    return re.sub(r"^https?://[^/]+", "", u).split("?")[0].lower().rstrip("/")


def _known(bank: dict) -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    for kind, pm in bank.get("urls", {}).items():
        nk = "unconsolidated" if kind == "unconsolidated_zip" else kind
        for period, url in pm.items():
            out[(nk, period.upper())] = url
    return out


def validate(ticker: str, bank: dict) -> dict:
    known = _known(bank)
    try:
        disc_list = discovery.discover_from_ir(ticker, bank)
    except Exception as e:  # noqa: BLE001
        return {"ticker": ticker, "status": f"ERROR:{type(e).__name__}", "detail": str(e)[:120]}
    disc = {(k, p.upper()): u for (p, k, u) in disc_list}
    if not disc:
        return {"ticker": ticker, "status": "no-discovery (opaque URL / no IR match)"}

    overlap = set(known) & set(disc)
    correct = [k for k in overlap if _path(known[k]) == _path(disc[k])]
    mismatch = [k for k in overlap if _path(known[k]) != _path(disc[k])]
    new = sorted(set(disc) - set(known))

    known_latest = max((p for (_k, p) in known), default=None)
    latest_keys = [k for k in known if k[1] == known_latest]
    latest_ok = all(k in correct for k in latest_keys)

    # Recent window = the 4 most recent known periods. Mismatches outside it are
    # tolerated (those quarters are already in R2 and get skipped on scrape).
    recent = set(sorted({p for (_k, p) in known})[-4:])
    recent_bad = [k for k in mismatch if k[1] in recent]

    passed = latest_ok and not recent_bad
    return {
        "ticker": ticker, "status": "PASS" if passed else "FAIL",
        "known": len(known), "correct": len(correct), "mismatch": mismatch,
        "recent_bad": recent_bad, "new": new,
        "known_latest": known_latest, "latest_ok": latest_ok,
    }


def main() -> None:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    wanted = [t.upper() for t in sys.argv[1:]] or list(cfg["banks"])
    results = []
    for tk in wanted:
        if tk not in cfg["banks"]:
            continue
        results.append(validate(tk, cfg["banks"][tk]))

    passed = []
    for r in sorted(results, key=lambda r: (r["status"] != "PASS", r["ticker"])):
        line = f"{r['ticker']:<8} {r['status']:<10}"
        if "known" in r:
            line += (f" known={r['known']} correct={r['correct']} "
                     f"latest={r['known_latest']}({'ok' if r['latest_ok'] else 'MISS'})")
            if r["recent_bad"]:
                line += f"  RECENT-MISMATCH={[f'{k[0][:5]}:{k[1]}' for k in r['recent_bad']]}"
            old_bad = [k for k in r["mismatch"] if k not in r["recent_bad"]]
            if old_bad:
                line += f"  old-mismatch={len(old_bad)}(tolerated)"
            if r["new"]:
                line += f"  NEW={[f'{k[0][:5]}:{k[1]}' for k in r['new']]}"
        elif "detail" in r:
            line += f" {r['detail']}"
        print(line)
        if r["status"] == "PASS":
            passed.append(r["ticker"])

    print("\n" + "=" * 70)
    print(f"PASS ({len(passed)}): {passed}")


if __name__ == "__main__":
    main()
