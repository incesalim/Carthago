"""Load extracted BankReport records into the SQLite database."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .extractor import BankReport, extract


def upsert_report(
    conn: sqlite3.Connection,
    bank_ticker: str,
    period: str,
    kind: str,
    rep: BankReport,
    pdf_path: str,
) -> dict[str, int]:
    """Idempotently insert one bank's report. Replaces any existing rows for
    the same (bank, period, kind). Returns row counts."""
    cur = conn.cursor()
    # Wipe existing rows for this (bank, period, kind)
    cur.execute(
        'DELETE FROM bank_audit_balance_sheet WHERE bank_ticker=? AND period=? AND kind=?',
        (bank_ticker, period, kind),
    )
    cur.execute(
        'DELETE FROM bank_audit_profit_loss WHERE bank_ticker=? AND period=? AND kind=?',
        (bank_ticker, period, kind),
    )

    # Insert balance sheet rows (3 statements: assets / liabilities / off_balance)
    bs_rows = []
    for stmt_name, rows in (
        ('assets', rep.bs_assets),
        ('liabilities', rep.bs_liabilities),
        ('off_balance', rep.off_balance),
    ):
        for r in rows:
            bs_rows.append((
                bank_ticker, period, kind, stmt_name, r.order,
                r.hierarchy, r.name, r.footnote,
                r.cur_tl, r.cur_fc, r.cur_total,
            ))
    if bs_rows:
        cur.executemany(
            'INSERT INTO bank_audit_balance_sheet '
            '(bank_ticker, period, kind, statement, item_order, hierarchy, item_name, footnote, amount_tl, amount_fc, amount_total) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            bs_rows,
        )

    # P&L
    pl_rows = []
    for r in rep.profit_loss:
        pl_rows.append((
            bank_ticker, period, kind, r.order,
            r.hierarchy, r.name, r.footnote, r.cur_amount,
        ))
    if pl_rows:
        cur.executemany(
            'INSERT INTO bank_audit_profit_loss '
            '(bank_ticker, period, kind, item_order, hierarchy, item_name, footnote, amount) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            pl_rows,
        )

    counts = {
        'bs_assets': len(rep.bs_assets),
        'bs_liabilities': len(rep.bs_liabilities),
        'off_balance': len(rep.off_balance),
        'profit_loss': len(rep.profit_loss),
    }

    # Extractions log row (idempotent via REPLACE)
    cur.execute(
        'INSERT OR REPLACE INTO bank_audit_extractions '
        '(bank_ticker, period, kind, pdf_path, rows_bs_assets, rows_bs_liabilities, rows_off_balance, rows_profit_loss, success) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (
            bank_ticker, period, kind, pdf_path,
            counts['bs_assets'], counts['bs_liabilities'],
            counts['off_balance'], counts['profit_loss'],
            1 if all(c >= 20 for c in [counts['bs_assets'], counts['bs_liabilities'], counts['profit_loss']]) else 0,
        ),
    )
    conn.commit()
    return counts


def load_pdf(
    db_path: str | Path,
    bank_ticker: str,
    period: str,
    kind: str,
    pdf_path: str | Path,
) -> dict[str, int]:
    """End-to-end: extract one PDF and upsert into DB."""
    rep = extract(str(pdf_path))
    with sqlite3.connect(str(db_path)) as conn:
        return upsert_report(conn, bank_ticker, period, kind, rep, str(pdf_path))


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    # Smoke test on Garanti 2024Q4 unconsolidated
    counts = load_pdf(
        'data/bddk_data.db', 'GARAN', '2024Q4', 'unconsolidated',
        'data/audit_reports/garanti/31_December_2024_Unconsolidated_Financial_Report.pdf',
    )
    print('loaded:', counts)
