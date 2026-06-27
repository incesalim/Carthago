"""Validate investor-presentation IR discovery against the hand-maintained config.

Sibling of validate_discovery.py for the earnings lane. For each seeded bank,
runs src.earnings.presentations.discover_presentation and compares the result to
data/banks/investor_presentation_urls.json (the oracle):

  - correct  : period in both, same document path
  - MISMATCH : period in both, DIFFERENT path  ← scan grabbed the wrong link
  - new      : period discovered but not in config (candidate newer quarter)

A bank PASSES (safe to add to presentations.PRESENTATION_BANKS) when it
reproduces its latest known period with no recent mismatch. Run ad hoc:

  python scripts/diagnostics/validate_presentation_discovery.py            # all seeded
  python scripts/diagnostics/validate_presentation_discovery.py GARAN AKBNK
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

from src.earnings import presentations  # noqa: E402

CONFIG = REPO / "data" / "banks" / "investor_presentation_urls.json"


def _path(u: str) -> str:
    return re.sub(r"^https?://[^/]+", "", u).split("?")[0].lower().rstrip("/")


def validate(ticker: str, bank: dict) -> dict:
    known = {p.upper(): u for p, u in (bank.get("urls", {}).get("presentation") or {}).items()}
    try:
        disc = {p.upper(): u for (p, u) in presentations.discover_presentation(ticker, bank)}
    except Exception as e:  # noqa: BLE001
        return {"ticker": ticker, "status": f"ERROR:{type(e).__name__}", "detail": str(e)[:120]}
    if not disc:
        return {"ticker": ticker, "status": "no-discovery (opaque URL / no IR match)"}

    overlap = set(known) & set(disc)
    correct = [k for k in overlap if _path(known[k]) == _path(disc[k])]
    mismatch = [k for k in overlap if _path(known[k]) != _path(disc[k])]
    new = sorted(set(disc) - set(known))

    known_latest = max(known, default=None)
    latest_ok = known_latest in correct
    recent = set(sorted(known)[-4:])
    recent_bad = [k for k in mismatch if k in recent]

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
    results = [validate(tk, cfg["banks"][tk]) for tk in wanted if tk in cfg["banks"]]

    passed = []
    for r in sorted(results, key=lambda r: (r["status"] != "PASS", r["ticker"])):
        line = f"{r['ticker']:<8} {r['status']:<10}"
        if "known" in r:
            line += (f" known={r['known']} correct={r['correct']} "
                     f"latest={r['known_latest']}({'ok' if r['latest_ok'] else 'MISS'})")
            if r["recent_bad"]:
                line += f"  RECENT-MISMATCH={r['recent_bad']}"
            old_bad = [k for k in r["mismatch"] if k not in r["recent_bad"]]
            if old_bad:
                line += f"  old-mismatch={len(old_bad)}(tolerated)"
            if r["new"]:
                line += f"  NEW={r['new']}"
        elif "detail" in r:
            line += f" {r['detail']}"
        print(line)
        if r["status"] == "PASS":
            passed.append(r["ticker"])

    print("\n" + "=" * 70)
    print(f"PASS ({len(passed)}): {passed}")
    print("Add PASS tickers to src/earnings/presentations.PRESENTATION_BANKS.")


if __name__ == "__main__":
    main()
