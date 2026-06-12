"""Load extracted BankReport records into the SQLite database."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from . import registry
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
    cur.execute(
        'DELETE FROM bank_audit_oci WHERE bank_ticker=? AND period=? AND kind=?',
        (bank_ticker, period, kind),
    )
    cur.execute(
        'DELETE FROM bank_audit_cash_flow WHERE bank_ticker=? AND period=? AND kind=?',
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

    # OCI (Other Comprehensive Income)
    oci_rows = []
    for r in getattr(rep, 'other_comprehensive_income', []):
        oci_rows.append((
            bank_ticker, period, kind, r.order,
            r.hierarchy, r.name, r.footnote, r.cur_amount,
        ))
    if oci_rows:
        cur.executemany(
            'INSERT INTO bank_audit_oci '
            '(bank_ticker, period, kind, item_order, hierarchy, item_name, footnote, amount) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            oci_rows,
        )

    # Cash flow (single-column, same shape as OCI)
    cf_rows = []
    for r in getattr(rep, 'cash_flow', []):
        cf_rows.append((
            bank_ticker, period, kind, r.order,
            r.hierarchy, r.name, r.footnote, r.cur_amount,
        ))
    if cf_rows:
        cur.executemany(
            'INSERT INTO bank_audit_cash_flow '
            '(bank_ticker, period, kind, item_order, hierarchy, item_name, footnote, amount) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            cf_rows,
        )

    # Footnote / §4 sub-statements. Each extractor module exposes the same
    # contract — upsert(conn, bank, period, kind, report) -> int|None — and the
    # report rides along on the BankReport (a rows list or a full report object).
    # Driving them from one table keeps the loader uniform: adding a statement
    # type is a new persister entry, not another bespoke block. (Construction
    # still differs per extractor; that's the next uniformity step.)
    from .credit_quality import CreditQualityReport, upsert as _upsert_cq
    from .loans_by_sector import LoansBySectorReport, upsert as _upsert_lbs
    from .npl_movement import NplMovementReport, upsert as _upsert_nplm
    from .capital_adequacy import CapitalReport, upsert as _upsert_cap
    from .liquidity import LiquidityReport, upsert as _upsert_liq
    from .bank_profile import upsert_profile as _upsert_bp
    from .equity_change import EquityChangeReport, upsert as _upsert_eq

    # (counts key, build report from rep, upsert fn, skip when empty)
    persisters = [
        ('credit_quality',  lambda: CreditQualityReport(pdf_path=pdf_path, rows=getattr(rep, 'credit_quality', []) or []),  _upsert_cq,  False),
        ('loans_by_sector', lambda: LoansBySectorReport(pdf_path=pdf_path, rows=getattr(rep, 'loans_by_sector', []) or []), _upsert_lbs, False),
        ('npl_movement',    lambda: NplMovementReport(pdf_path=pdf_path, rows=getattr(rep, 'npl_movement', []) or []),      _upsert_nplm, False),
        # §4 ratios: extract() attaches a full report object; rebuild an empty one
        # if the scan was skipped/failed so the upsert still clears stale rows.
        ('capital',         lambda: getattr(rep, 'capital', None) or CapitalReport(pdf_path=pdf_path),                     _upsert_cap, False),
        ('liquidity',       lambda: getattr(rep, 'liquidity', None) or LiquidityReport(pdf_path=pdf_path),                 _upsert_liq, False),
        # profile is INSERT OR REPLACE (no delete) — skip when empty so a failed
        # re-extract doesn't wipe a previously-captured branches/personnel row.
        ('profile',         lambda: getattr(rep, 'bank_profile', None),                                                    _upsert_bp,  True),
        ('equity_change',   lambda: getattr(rep, 'equity_change', None) or EquityChangeReport(pdf_path=pdf_path),          _upsert_eq,  False),
    ]
    counts = {
        'bs_assets': len(rep.bs_assets),
        'bs_liabilities': len(rep.bs_liabilities),
        'off_balance': len(rep.off_balance),
        'profit_loss': len(rep.profit_loss),
        'oci': len(getattr(rep, 'other_comprehensive_income', [])),
        'cash_flow': len(getattr(rep, 'cash_flow', [])),
    }
    for key, build, upsert_fn, skip_if_empty in persisters:
        report = build()
        if skip_if_empty and (report is None or getattr(report, 'is_empty', lambda: True)()):
            continue
        n = upsert_fn(conn, bank_ticker, period, kind, report)
        if n is not None:
            counts[key] = n

    # Structural validation (internal-sum identities) — persisted per
    # statement so crons/dashboard can see WHICH partitions are trustworthy.
    # Isolated: a validator bug must never sink the extraction itself.
    try:
        from .validator import upsert_validation, validate_report
        upsert_validation(conn, bank_ticker, period, kind,
                          validate_report(rep, period=period))
    except Exception:
        pass

    # Extractions log row (idempotent via REPLACE)
    cur.execute(
        'INSERT OR REPLACE INTO bank_audit_extractions '
        '(bank_ticker, period, kind, pdf_path, rows_bs_assets, rows_bs_liabilities, '
        ' rows_off_balance, rows_profit_loss, rows_credit_quality, rows_oci, '
        ' rows_cash_flow, rows_equity_change, success) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (
            bank_ticker, period, kind, pdf_path,
            counts['bs_assets'], counts['bs_liabilities'],
            counts['off_balance'], counts['profit_loss'],
            counts.get('credit_quality', 0),
            counts.get('oci', 0),
            counts.get('cash_flow', 0),
            counts.get('equity_change', 0),
            1 if registry.success_from_counts(counts) else 0,
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
