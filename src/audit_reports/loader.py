"""Load extracted BankReport records into the SQLite database."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from . import registry
from .extractor import BankReport, extract

# Some banks' source PDFs print hierarchy codes off the BRSA standard in TWO ways,
# and consumers that key on the EXACT code — the per-bank Financials table and the
# cross-bank heatmap — then can't match those rows, so the numbers silently vanish
# from the UI (or, for a dotless asset roman, drop out of the SUMMED total assets, so
# the bank reads ~40-50% smaller for that quarter — ALNTF's "I" = Financial Assets):
#   • a multi-level NUMERIC sub-code with a TRAILING dot ("1.1." / "2.1." — KUVEYT,
#     partially ALBRK / EXIM / ICBCT) where the standard is "1.1" / "2.1"; and
#   • a top-level ROMAN code WITHOUT its trailing dot ("XI" Personnel Expenses —
#     EXIM 2024Q2/Q3; "I" Financial Assets — ALNTF; "V" Dividend Income — 6 banks)
#     where the standard is "XI." / "I." / "V.".
# Normalise the KEY on write, ONLY for the catalog-driven displayed statements
# (assets, liabilities, profit_loss): STRIP the dot from a multi-level numeric code,
# and ADD a dot to a bare roman-numeral code. Single-level numerics ("1."), synthetic
# suffixes ("1.1.ecl") and already-correct codes are left intact. off_balance is
# EXCLUDED on purpose — its sub-items are dotted as a convention across ~19 banks (24k
# rows), it isn't rendered through the catalog, and its indentation derives from the
# code, so its dots are kept. oci / cash_flow are likewise left alone (not keyed by
# the UI). Values are never touched.
#
# The roman-dot rule is a pure KEY canonicalisation. Two frozen partitions carry a
# roman code that is itself mis-extracted CONTENT (a post-merger line keyed "X" where
# "X." = Other Provisions already exists — a collision; and TOMK 2023Q3 "XI" whose
# content is Other Operating Expenses, semantically XII.). Those are content bugs, not
# dot bugs; the one-time backfill (scripts/normalize_roman_hierarchy.py) skips them
# via a collision guard + a semantic guard, and they can't recur because BS/PL are
# frozen (never re-extracted).
_HIER_TRAILING_DOT = re.compile(r"^(\d+(?:\.\d+)+)\.$")
_HIER_BARE_ROMAN = re.compile(r"^[IVXLCDM]+$")
_NORMALIZE_HIER = frozenset({"assets", "liabilities", "profit_loss"})


def _canon_hier(statement: str, h: str | None) -> str | None:
    if statement not in _NORMALIZE_HIER or not h:
        return h
    m = _HIER_TRAILING_DOT.match(h)
    if m:
        return m.group(1)
    if _HIER_BARE_ROMAN.match(h):
        return h + "."
    return h


def upsert_report(
    conn: sqlite3.Connection,
    bank_ticker: str,
    period: str,
    kind: str,
    rep: BankReport,
    pdf_path: str,
    force: bool = False,
) -> dict[str, int]:
    """Idempotently insert one bank's report. Replaces existing rows for the
    same (bank, period, kind).

    NON-DESTRUCTIVE by default: any statement whose stored data ALREADY passes
    validation is left untouched — a re-extract can improve failing/missing
    statements but can never overwrite correct data with worse data. Pass
    `force=True` to overwrite everything regardless of validation.

    Returns row counts."""
    cur = conn.cursor()

    from .validator import statement_passes

    def _keep(statement: str) -> bool:
        """Protect this statement's stored rows (skip the re-write)?"""
        return (not force) and statement_passes(conn, bank_ticker, period, kind, statement)

    def _existing(table: str, statement: str | None = None) -> int:
        q = f"SELECT COUNT(*) FROM {table} WHERE bank_ticker=? AND period=? AND kind=?"
        a: list = [bank_ticker, period, kind]
        if statement is not None:
            q += " AND statement=?"
            a.append(statement)
        return cur.execute(q, a).fetchone()[0]

    counts: dict[str, int] = {}

    # --- Balance sheet (assets / liabilities / off_balance), per statement ---
    # assets & liabilities cross-check each other (the 'cross' identity), so they
    # are protected as a pair; off_balance is independent.
    _bs_pair_keep = _keep('assets') and _keep('liabilities')
    for stmt_name, ckey, rows, keep in (
        ('assets',      'bs_assets',      rep.bs_assets,      _bs_pair_keep),
        ('liabilities', 'bs_liabilities', rep.bs_liabilities, _bs_pair_keep),
        ('off_balance', 'off_balance',    rep.off_balance,    _keep('off_balance')),
    ):
        if keep:
            counts[ckey] = _existing('bank_audit_balance_sheet', stmt_name)
            continue
        cur.execute(
            'DELETE FROM bank_audit_balance_sheet '
            'WHERE bank_ticker=? AND period=? AND kind=? AND statement=?',
            (bank_ticker, period, kind, stmt_name),
        )
        if rows:
            cur.executemany(
                'INSERT INTO bank_audit_balance_sheet '
                '(bank_ticker, period, kind, statement, item_order, hierarchy, item_name, footnote, amount_tl, amount_fc, amount_total) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                [(bank_ticker, period, kind, stmt_name, r.order, _canon_hier(stmt_name, r.hierarchy), r.name,
                  r.footnote, r.cur_tl, r.cur_fc, r.cur_total) for r in rows],
            )
        counts[ckey] = len(rows)

    # --- single-column statements: P&L / OCI / cash flow ---
    for stmt_name, table, ckey, rows in (
        ('profit_loss', 'bank_audit_profit_loss', 'profit_loss', rep.profit_loss),
        ('oci',         'bank_audit_oci',         'oci',         getattr(rep, 'other_comprehensive_income', [])),
        ('cash_flow',   'bank_audit_cash_flow',   'cash_flow',   getattr(rep, 'cash_flow', [])),
    ):
        if _keep(stmt_name):
            counts[ckey] = _existing(table)
            continue
        cur.execute(f'DELETE FROM {table} WHERE bank_ticker=? AND period=? AND kind=?',
                    (bank_ticker, period, kind))
        if rows:
            cur.executemany(
                f'INSERT INTO {table} '
                '(bank_ticker, period, kind, item_order, hierarchy, item_name, footnote, amount) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                [(bank_ticker, period, kind, r.order, _canon_hier(stmt_name, r.hierarchy), r.name, r.footnote, r.cur_amount)
                 for r in rows],
            )
        counts[ckey] = len(rows)

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
    from .fx_position import FxReport, upsert as _upsert_fx
    from .repricing import RepricingReport, upsert as _upsert_rp
    from .bank_profile import upsert_profile as _upsert_bp
    from .audit_opinion import upsert_opinion as _upsert_op
    from .free_provision import upsert_free_provision as _upsert_fp
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
        ('fx_position',     lambda: getattr(rep, 'fx_position', None) or FxReport(pdf_path=pdf_path),                      _upsert_fx, False),
        ('repricing',       lambda: getattr(rep, 'repricing', None) or RepricingReport(pdf_path=pdf_path),                 _upsert_rp, False),
        # profile is INSERT OR REPLACE (no delete) — skip when empty so a failed
        # re-extract doesn't wipe a previously-captured branches/personnel row.
        ('profile',         lambda: getattr(rep, 'bank_profile', None),                                                    _upsert_bp,  True),
        # opinion is INSERT OR REPLACE + skip-if-empty (no validator), like profile:
        # a failed re-extract (opinion_type='unknown') must not wipe a stored verdict.
        ('opinion',         lambda: getattr(rep, 'audit_opinion', None),                                                   _upsert_op,  True),
        # free provision: INSERT OR REPLACE + skip-if-empty (no validator), like
        # opinion/profile — a re-extract that finds no disclosure keeps the value.
        ('free_provision',  lambda: getattr(rep, 'free_provision', None),                                                  _upsert_fp,  True),
        ('equity_change',   lambda: getattr(rep, 'equity_change', None) or EquityChangeReport(pdf_path=pdf_path),          _upsert_eq,  False),
    ]
    # Footnote / §4 persisters: gate each on its own validation statement so a
    # passing one is left intact (same non-destructive rule as above). 'profile'
    # has no validator — its skip-if-empty + INSERT-OR-REPLACE already protect it.
    _PERSISTER_TABLE = {
        'credit_quality':  'bank_audit_credit_quality',
        'loans_by_sector': 'bank_audit_loans_by_sector',
        'npl_movement':    'bank_audit_npl_movement',
        'capital':         'bank_audit_capital',
        'liquidity':       'bank_audit_liquidity',
        'fx_position':     'bank_audit_fx_position',
        'repricing':       'bank_audit_repricing',
        'equity_change':   'bank_audit_equity_change',
    }
    for key, build, upsert_fn, skip_if_empty in persisters:
        if key in _PERSISTER_TABLE and _keep(key):
            counts[key] = _existing(_PERSISTER_TABLE[key])
            continue
        report = build()
        if skip_if_empty and (report is None or getattr(report, 'is_empty', lambda: True)()):
            continue
        n = upsert_fn(conn, bank_ticker, period, kind, report)
        if n is not None:
            counts[key] = n

    # Structural validation — recompute the WHOLE partition from its STORED rows
    # (not the in-memory report) so the recorded result always matches what's in
    # the DB, including any statements left untouched above. This also covers all
    # 14 statement types (validate_report only covers the core 8). Isolated: a
    # validator bug must never sink the extraction itself.
    try:
        import sys as _sys
        _repo = str(Path(__file__).resolve().parents[2])
        if _repo not in _sys.path:
            _sys.path.insert(0, _repo)
        from scripts.revalidate_audit_db import revalidate_partition

        from .validator import upsert_validation
        upsert_validation(conn, bank_ticker, period, kind,
                          revalidate_partition(conn, bank_ticker, period, kind))
    except Exception:
        pass

    # Extractions log row (idempotent via REPLACE)
    cur.execute(
        'INSERT OR REPLACE INTO bank_audit_extractions '
        '(bank_ticker, period, kind, pdf_path, rows_bs_assets, rows_bs_liabilities, '
        ' rows_off_balance, rows_profit_loss, rows_credit_quality, rows_oci, '
        ' rows_cash_flow, rows_equity_change, rows_fx_position, rows_repricing, success) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (
            bank_ticker, period, kind, pdf_path,
            counts['bs_assets'], counts['bs_liabilities'],
            counts['off_balance'], counts['profit_loss'],
            counts.get('credit_quality', 0),
            counts.get('oci', 0),
            counts.get('cash_flow', 0),
            counts.get('equity_change', 0),
            counts.get('fx_position', 0),
            counts.get('repricing', 0),
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
