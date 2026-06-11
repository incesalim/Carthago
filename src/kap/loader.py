"""Upsert kap_ownership rows with bank-level replace semantics.

Each run replaces a bank's entire partition (all items) so removed
shareholders / shrunk grids can't leave stale rows locally. The loader
reports the (bank_ticker, item, seq) keys that existed before but not
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
    """Replace one bank's kap_ownership partition. Returns (inserted, removed_keys)."""
    old = set(conn.execute(
        "SELECT bank_ticker, item, seq FROM kap_ownership WHERE bank_ticker = ?",
        (bank_ticker,),
    ))
    new = {(r.bank_ticker, r.item, r.seq) for r in rows}
    removed = sorted(old - new)

    conn.execute("DELETE FROM kap_ownership WHERE bank_ticker = ?", (bank_ticker,))
    conn.executemany(
        "INSERT INTO kap_ownership"
        " (bank_ticker, bank_name, kap_company_id, item, seq,"
        "  holder, share_tl, ratio_pct, voting_pct, as_of,"
        "  currency, activity, relation)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (r.bank_ticker, r.bank_name, r.kap_company_id, r.item, r.seq,
             r.holder, r.share_tl, r.ratio_pct, r.voting_pct, r.as_of,
             r.currency, r.activity, r.relation)
            for r in rows
        ],
    )
    conn.commit()
    return len(rows), removed
