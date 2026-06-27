"""Idempotent upserts for the faaliyet_* tables + a read-only cross-check.

``upsert_report`` replaces a bank's ``(bank_ticker, fiscal_year)`` partition in
``faaliyet_franchise`` and writes one ``faaliyet_extractions`` provenance row,
both with a fresh ``extracted_at`` so the incremental D1 push picks them up.

Cross-check: ``branch_total`` and ``employee_count`` are compared against the
``bank_audit_profile`` figure already extracted from the year-end audit report.
Agreement (±5%) → confidence 'high'; disagreement → keep the franchise value but
downgrade and record a note. ``bank_audit_profile`` is READ ONLY here — the
audit lane is frozen.
"""
from __future__ import annotations

import sqlite3

from .extractor import FranchiseReport, FranchiseStat

_INSERT = (
    "INSERT OR REPLACE INTO faaliyet_franchise"
    " (bank_ticker, fiscal_year, metric_key, period_type, value, unit,"
    "  source_page, source_lang, anchor, raw_snippet, confidence, extracted_at)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)"
)

# franchise metric_key → bank_audit_profile column for the year-end cross-check.
_PROFILE_COL = {
    "branch_total": "branches_total",
    "branch_domestic": "branches_domestic",
    "branch_foreign": "branches_foreign",
    "employee_count": "personnel",
}


def _profile_value(conn: sqlite3.Connection, ticker: str, year: int, col: str
                   ) -> int | None:
    """Year-end (``{year}Q4``) value of a bank_audit_profile column, if present.
    Read-only. Returns None when the audit profile table/row is absent."""
    # `col` is whitelisted via _PROFILE_COL, so interpolation here is safe.
    try:
        row = conn.execute(
            f"SELECT {col} FROM bank_audit_profile"
            f"  WHERE bank_ticker = ? AND period = ? AND {col} IS NOT NULL"
            "  ORDER BY kind LIMIT 1",
            (ticker, f"{year}Q4"),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    return row[0] if row else None


def crosscheck(conn: sqlite3.Connection, ticker: str, year: int,
               stats: list[FranchiseStat]) -> str | None:
    """Mutate confidences in-place against bank_audit_profile; return a note."""
    notes: list[str] = []
    for s in stats:
        if s.period_type != "current":
            continue
        col = _PROFILE_COL.get(s.metric_key)
        if not col:
            continue
        ref = _profile_value(conn, ticker, year, col)
        if ref is None or ref == 0:
            continue
        rel = abs(s.value - ref) / ref
        if rel <= 0.05:
            s.confidence = "high"
        else:
            s.confidence = "low" if s.confidence == "low" else "medium"
            notes.append(f"{s.metric_key} {s.value:.0f} vs audit {ref} ({rel:.0%})")
    return "; ".join(notes) if notes else None


def upsert_report(conn: sqlite3.Connection, ticker: str, year: int,
                  rep: FranchiseReport, source_url: str | None = None,
                  r2_key: str | None = None) -> int:
    """Replace the (ticker, year) partition and log the extraction. Returns rows."""
    note = crosscheck(conn, ticker, year, rep.stats)
    conn.execute(
        "DELETE FROM faaliyet_franchise WHERE bank_ticker = ? AND fiscal_year = ?",
        (ticker, year),
    )
    rows = [(
        ticker, year, s.metric_key, s.period_type, s.value, s.unit,
        s.source_page, s.source_lang, s.anchor, s.raw_snippet, s.confidence,
    ) for s in rep.stats]
    if rows:
        conn.executemany(_INSERT, rows)
    n_current = sum(1 for s in rep.stats if s.period_type == "current")
    conn.execute(
        "INSERT OR REPLACE INTO faaliyet_extractions"
        " (bank_ticker, fiscal_year, source_url, r2_key, n_pages, report_lang,"
        "  is_ocr, metrics_found, success, note, extracted_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
        (ticker, year, source_url, r2_key, rep.n_pages, rep.report_lang,
         int(rep.is_ocr), n_current, int(n_current > 0 and not rep.is_ocr), note),
    )
    conn.commit()
    return len(rows)


def mark_fetch(conn: sqlite3.Connection, ticker: str, year: int, status: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO faaliyet_fetch_log (bank_ticker, fiscal_year, status,"
        " fetched_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
        (ticker, year, status),
    )
    conn.commit()


def fetch_done(conn: sqlite3.Connection, ticker: str, year: int) -> bool:
    row = conn.execute(
        "SELECT status FROM faaliyet_fetch_log WHERE bank_ticker = ? AND fiscal_year = ?",
        (ticker, year),
    ).fetchone()
    return bool(row) and row[0] in ("done", "ocr", "no_pdf")
