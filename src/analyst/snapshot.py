"""Read-only access to the audit-lane snapshot, plus the shared corpus queries.

Two rules are load-bearing and non-obvious, both inherited from the corpus
rules in `web/app/lib/bot-schema.ts` and the feasibility test:

- The balance-sheet TOTAL row is `hierarchy = ''` (empty string) — every detail
  row carries a roman (`I.`) or dotted numeral. `item_name` matching is unsafe
  (bilingual, and sometimes space-fused: `VARLIKLARTOPLAMI`).
- Total assets = `MAX(amount_total)` across BOTH legs (assets, liabilities) —
  the legs must equal, and MAX survives one leg missing.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict

DEFAULT_DB = "data/bank_audit.db"


def connect(path: str = DEFAULT_DB) -> sqlite3.Connection:
    """Read-only connection — the snapshot is never written by this package."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def total_assets(conn: sqlite3.Connection,
                 bank: str | None = None) -> dict[tuple[str, str], dict[str, float]]:
    """`{(bank, kind): {period: total_assets}}` for every stored partition."""
    sql = """
        SELECT bank_ticker, period, kind, MAX(amount_total) AS total
        FROM bank_audit_balance_sheet
        WHERE hierarchy = '' AND statement IN ('assets', 'liabilities')
          AND amount_total IS NOT NULL
    """
    params: list[str] = []
    if bank:
        sql += " AND bank_ticker = ?"
        params.append(bank)
    sql += " GROUP BY bank_ticker, period, kind"
    out: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    for r in conn.execute(sql, params):
        out[(r["bank_ticker"], r["kind"])][r["period"]] = r["total"]
    return dict(out)


def series(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    return conn.execute(sql, params).fetchall()
