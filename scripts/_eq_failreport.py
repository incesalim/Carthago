"""Per-partition equity_change validation report for 2025/2026 (read-only).

Run AFTER reextract_statement.py (equity, dry-run) + revalidate_audit_db.py.
Prints every 2025/2026 equity_change partition with checks_failed and, for any
failing one, the failed_detail. Summarises the total clean vs failing so we can
verify the "zero failures" target exhaustively (no sampling)."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")
DB = REPO / "data" / "bank_audit.db"

PERIODS = ("2025Q1", "2025Q2", "2025Q3", "2025Q4", "2026Q1")

con = sqlite3.connect(str(DB))
rows = con.execute(
    "SELECT bank_ticker, period, kind, checks_passed, checks_failed, checks_skipped, failed_detail "
    "FROM bank_audit_validation WHERE statement='equity_change' "
    f"AND period IN ({','.join('?' * len(PERIODS))}) "
    "ORDER BY period, bank_ticker, kind", PERIODS).fetchall()

total = len(rows)
failing = [r for r in rows if r[4] > 0]
clean = total - len(failing)

print(f"=== equity_change 2025/2026: {total} partitions | clean={clean} | FAILING={len(failing)} ===\n")

# Break down failing by check name
from collections import Counter
check_counter: Counter = Counter()
for b, p, k, cp, cf, cs, detail in failing:
    print(f"FAIL {b:8} {p} {k:14} passed={cp} failed={cf} skipped={cs}")
    if detail:
        try:
            items = json.loads(detail)
        except Exception:
            items = [{"raw": detail}]
        for it in items:
            cn = it.get("check") or it.get("name") or it.get("raw") or "?"
            check_counter[cn] += 1
            exp = it.get("expected")
            act = it.get("actual")
            msg = it.get("node") or it.get("message") or it.get("detail") or ""
            print(f"       - {cn}: {msg} (exp={exp} act={act})")
    print()

print("=== failing checks by type ===")
for cn, n in check_counter.most_common():
    print(f"  {cn}: {n}")
