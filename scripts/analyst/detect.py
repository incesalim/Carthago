"""Task 1.6 — run every analyst detector against the audit-lane snapshot.

Emits signals as JSONL plus a per-type summary, optionally staging rows into
`data/analyst.db` (the staging SQLite `push_to_d1.py` will read WHEN the D1
write freeze lifts — this script itself never touches D1, by design; see the
standing freeze note in docs/OPERATIONS.md).

Usage:
    python scripts/analyst/detect.py                        # full corpus
    python scripts/analyst/detect.py --bank SKBNK           # one bank
    python scripts/analyst/detect.py --signal-type divergence
    python scripts/analyst/detect.py --stage                # also write data/analyst.db
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from src.analyst import (  # noqa: E402
    detect_cross_period,
    detect_divergence,
    detect_opinion_change,
    detect_perimeter_change,
    detect_unit_change,
    extract_basis_metadata,
    snapshot,
)
from src.analyst.schema import init_analyst_schema  # noqa: E402
from src.analyst.signals import Signal  # noqa: E402

DETECTORS = {
    "unit_change": detect_unit_change.detect,
    "cross_period_mismatch": detect_cross_period.detect,
    "opinion_change": detect_opinion_change.detect,
    "perimeter_change": detect_perimeter_change.detect,
    "divergence": detect_divergence.detect,
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=snapshot.DEFAULT_DB)
    ap.add_argument("--bank")
    ap.add_argument("--period", help="filter emitted signals to one period (YYYYQN)")
    ap.add_argument("--signal-type", choices=sorted(DETECTORS))
    ap.add_argument("--out", default="data/analyst_signals.jsonl")
    ap.add_argument("--basis-out", default="data/analyst_basis_metadata.jsonl")
    ap.add_argument("--stage", action="store_true",
                    help="also write signals + basis metadata into data/analyst.db")
    args = ap.parse_args()

    t0 = time.time()
    conn = snapshot.connect(args.db)

    signals: list[Signal] = []
    for name, fn in DETECTORS.items():
        if args.signal_type and name != args.signal_type:
            continue
        signals.extend(fn(conn, args.bank))
    if args.period:
        signals = [s for s in signals if s.period == args.period]
    signals.sort(key=lambda s: s.signal_id)

    basis_rows = extract_basis_metadata.build_rows(conn, args.bank)
    conn.close()

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for s in signals:
            f.write(json.dumps(s.to_row(), ensure_ascii=False) + "\n")
    with open(args.basis_out, "w", encoding="utf-8") as f:
        for r in basis_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    if args.stage:
        import sqlite3
        stage = sqlite3.connect(REPO / "data" / "analyst.db")
        init_analyst_schema(stage)
        stage.executemany(
            "INSERT OR REPLACE INTO analyst_signals "
            "(signal_id, signal_type, bank_ticker, period, kind, severity, payload) "
            "VALUES (:signal_id, :signal_type, :bank_ticker, :period, :kind, :severity, :payload)",
            [s.to_row() for s in signals])
        stage.executemany(
            "INSERT OR REPLACE INTO analyst_basis_metadata "
            "(bank_ticker, period, kind, reporting_unit, unit_source, "
            " assurance_level, assurance_source, consolidation_basis) "
            "VALUES (:bank_ticker, :period, :kind, :reporting_unit, :unit_source, "
            "        :assurance_level, :assurance_source, :consolidation_basis)",
            basis_rows)
        stage.commit()
        stage.close()

    by_type = Counter(s.signal_type for s in signals)
    by_sev = Counter(s.severity for s in signals)
    print(f"{len(signals)} signals in {time.time() - t0:.1f}s "
          f"({len(basis_rows)} basis rows)")
    for k, v in sorted(by_type.items()):
        print(f"  {k:24s} {v}")
    print("  severity:", dict(sorted(by_sev.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
