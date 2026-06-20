"""OCI (Other Comprehensive Income / "Diğer Kapsamlı Gelir") extraction.

Validation-guided, mirroring equity_change.py: the located OCI page is read by
several engines (pdfplumber-repaired + fitz) at several column templates, and we
keep the reconstruction whose roman chain VALIDATES (III ≈ I + II) rather than the
one with the most rows. This self-corrects the common BRSA-interim failure where
the P&L-tuned column detector reads a 2-column OCI page as 4 columns and the
shared parser then returns 0 / garbage rows.

ADDITIVE: uses the extractor's shared parsers READ-ONLY; it never modifies
`_parse_page` / `_detect_pl_ncols` (shared with the frozen BS/P&L extraction).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from .extractor import (
    _HAS_FITZ,
    StatementRow,
    _detect_pl_ncols,
    _fitz_merge_rows,
    _fitz_page_text,
    _parse_rows,
    _safe_repaired_text,
    _split_label,
)
from .validator import _roman_to_int, _tol, check_hierarchy_sums

_OCI_MIN_REAL_ROWS = 3


@dataclass
class OCIReport:
    pdf_path: str
    rows: list[StatementRow] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.rows


def _rows_from_parsed(parsed: list[tuple[str, list[float | None]]], n_cols: int) -> list[StatementRow]:
    """Turn (label, values) tuples into OCI StatementRows (current = col 0,
    prior = col n//2 — the BRSA cumulative-current / cumulative-prior mapping)."""
    out: list[StatementRow] = []
    for order, (label, vals) in enumerate(parsed, 1):
        h, name, fn = _split_label(label)
        out.append(StatementRow(
            order=order, hierarchy=h, name=name, footnote=fn,
            cur_amount=vals[0] if vals else None,
            pri_amount=vals[n_cols // 2] if len(vals) > n_cols // 2 else None,
        ))
    return out


def _parse_oci_with(text: str, n_cols: int) -> list[StatementRow]:
    """One candidate: parse a text reconstruction at a column template."""
    return _rows_from_parsed(_parse_rows(_fitz_merge_rows(text, n_cols), n_cols), n_cols)


def _oci_romans(rows: list[StatementRow]) -> dict[int, float]:
    """First current-amount per roman ordinal (I/II/III …) — the chain spine."""
    roman: dict[int, float] = {}
    for r in rows:
        h = (r.hierarchy or "").strip()
        o = _roman_to_int(h.rstrip(".")) if h else None
        if o is not None and o not in roman and r.cur_amount is not None:
            roman[o] = r.cur_amount
    return roman


def _oci_chain_closes(rows: list[StatementRow]) -> bool:
    """True iff OCI III ≈ I + II (the TOPLAM KAPSAMLI GELİR identity) — the same
    self-contained check `check_oci` runs, computed on candidate rows (no DB).
    Guards a degenerate parse via row I (period net profit, always large), since
    the OCI total itself can legitimately be ~0."""
    roman = _oci_romans(rows)
    if not ({1, 2, 3} <= set(roman)):
        return False
    r1, r2, r3 = roman[1], roman[2], roman[3]
    if abs(r1) <= 1.0:  # net profit is never ~0 → reject a 0==0 degenerate parse
        return False
    return abs(r3 - (r1 + r2)) <= _tol(r3, base=3.0, rel=5e-5)


def _oci_hierarchy_ok(rows: list[StatementRow]) -> bool:
    """The 2.1 = Σ2.1.x / 2.2 = Σ2.2.x sub-trees foot (check_oci's V1)."""
    adapted = [{"hierarchy": r.hierarchy, "item_name": r.name, "amount_total": r.cur_amount}
               for r in rows]
    hs = check_hierarchy_sums(adapted)
    return hs.failed == 0 and hs.passed > 0


def _oci_candidate_score(rows: list[StatementRow]) -> tuple[int, int, int, int]:
    """Lexicographic (chain_validates, hierarchy_ok, n_real, n_rows) — higher is
    better. tier-1 (first element 1) requires the III=I+II chain to close AND
    enough real rows, so a near-empty 0==0 parse stays tier-0."""
    if not rows:
        return (0, 0, 0, 0)
    n_real = sum(1 for r in rows if r.cur_amount is not None and abs(r.cur_amount) > 1.0)
    chain = n_real >= _OCI_MIN_REAL_ROWS and _oci_chain_closes(rows)
    tier1 = 1 if chain else 0
    hier = 1 if (tier1 and _oci_hierarchy_ok(rows)) else 0
    return (tier1, hier, n_real, len(rows))


def extract_oci(pdf_path: str, oci_page: int) -> OCIReport:
    """Validation-guided OCI extraction from an already-located OCI page."""
    n0 = _detect_pl_ncols(pdf_path, oci_page)
    n_templates = sorted({n0, 2, 4})

    def _cands_from(text: str) -> list[list[StatementRow]]:
        return [c for c in (_parse_oci_with(text, n) for n in n_templates) if c]

    # FITZ-FIRST: read the page once with fitz and try each column template; the
    # validation-guided selection (below) picks the right one. fitz reads the
    # narrow single-column OCI table cleanly for the vast majority of banks and
    # costs no extra PDF re-open. The detector mis-reads OCI as 4-col on interim
    # reports; n=2 is the fix.
    candidates: list[list[StatementRow]] = []
    if _HAS_FITZ:
        fz = _fitz_page_text(pdf_path, oci_page - 1)
        if fz:
            candidates += _cands_from(fz)
    # PDFPLUMBER FALLBACK: wide-interleaved-table banks (GARAN/AKBNK) present a
    # combined "…Profit or Loss AND Other Comprehensive Income" page that fitz
    # linearizes into garbage; only pdfplumber's x-clustering layout-repair
    # separates the period columns. Add it when fitz produced nothing OR nothing
    # that validates — so the fitz-only fast path (and its ~225 ms/page saving) is
    # preserved for every bank fitz reads correctly.
    if not any(_oci_candidate_score(c)[0] == 1 for c in candidates):
        pp = _safe_repaired_text(pdf_path, oci_page)
        if pp:
            candidates += _cands_from(pp)
    if not candidates:
        return OCIReport(pdf_path=pdf_path)

    # Prefer the reconstruction whose chain validates; fall back to most-rows when
    # none validates (== today's behaviour). Don't trade a much-fuller parse for a
    # marginally-shorter validating one.
    scored = [(_oci_candidate_score(c), c) for c in candidates]
    validating = [(s, c) for (s, c) in scored if s[0] == 1]
    fullest = max(len(c) for c in candidates)
    if validating:
        win_s, win_c = max(validating, key=lambda sc: sc[0])
        best = win_c if win_s[3] >= fullest - 2 else max(candidates, key=len)
    else:
        best = max(candidates, key=len)
    for i, r in enumerate(best, 1):
        r.order = i
    return OCIReport(pdf_path=pdf_path, rows=best)


def upsert(conn: sqlite3.Connection, bank: str, period: str,
           kind: str, report: OCIReport) -> int:
    """Delete + insert OCI rows for (bank, period, kind). Returns row count."""
    conn.execute(
        'DELETE FROM bank_audit_oci WHERE bank_ticker=? AND period=? AND kind=?',
        (bank, period, kind),
    )
    if not report.rows:
        return 0
    conn.executemany(
        'INSERT INTO bank_audit_oci '
        '(bank_ticker, period, kind, item_order, hierarchy, item_name, footnote, amount) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        [(bank, period, kind, r.order, r.hierarchy, r.name, r.footnote, r.cur_amount)
         for r in report.rows],
    )
    return len(report.rows)
