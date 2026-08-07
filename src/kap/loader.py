"""Upsert kap_ownership rows with bank-level reconciliation semantics.

Each run reconciles a bank's entire partition (all items) so removed
shareholders / shrunk grids can't leave stale rows locally. Identical rows are
left untouched, so their ``downloaded_at`` stamps do not trigger a D1 rewrite.
The loader reports the (bank_ticker, item, seq) keys that existed before but not
after — the update script mirrors those deletes to D1, because the shared
``push_to_d1.py`` is INSERT OR REPLACE-only and would otherwise leave
orphans remotely (same gotcha as the audit backfill lane).
"""
from __future__ import annotations

import sqlite3

from .parser import OwnershipRow


def replace_bank_rows(
    conn: sqlite3.Connection, bank_ticker: str, rows: list[OwnershipRow]
) -> tuple[int, list[tuple[str, str, int]]]:
    """Reconcile one bank partition. Returns (rows_written, removed_keys)."""
    columns = (
        "bank_ticker", "bank_name", "kap_company_id", "item", "seq",
        "holder", "share_tl", "ratio_pct", "voting_pct", "as_of",
        "currency", "activity", "relation",
    )
    old_rows = list(conn.execute(
        f"SELECT {', '.join(columns)} FROM kap_ownership WHERE bank_ticker = ?",
        (bank_ticker,),
    ))
    old = {(r[0], r[3], r[4]): tuple(r) for r in old_rows}
    incoming = [
        (r.bank_ticker, r.bank_name, r.kap_company_id, r.item, r.seq,
         r.holder, r.share_tl, r.ratio_pct, r.voting_pct, r.as_of,
         r.currency, r.activity, r.relation)
        for r in rows
    ]
    new = {(r[0], r[3], r[4]): r for r in incoming}
    removed = sorted(set(old) - set(new))
    changed = [row for key, row in new.items() if old.get(key) != row]

    if removed:
        conn.executemany(
            "DELETE FROM kap_ownership WHERE bank_ticker=? AND item=? AND seq=?",
            removed,
        )
    if changed:
        conn.executemany(
            "INSERT OR REPLACE INTO kap_ownership"
            " (bank_ticker, bank_name, kap_company_id, item, seq,"
            "  holder, share_tl, ratio_pct, voting_pct, as_of,"
            "  currency, activity, relation)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            changed,
        )
    conn.commit()
    return len(changed), removed
