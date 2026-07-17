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

import re
import sqlite3
from dataclasses import dataclass, field

from .extractor import (
    _HAS_FITZ,
    StatementRow,
    _detect_pl_ncols,
    _fitz_merge_rows,
    _fitz_page_text,
    _fitz_visual_rows,
    _parse_rows,
    _split_label,
)
from .validator import _roman_to_int, _tol, check_hierarchy_sums

_OCI_MIN_REAL_ROWS = 3

# Coordinate-reconstruction token classes (a leading hierarchy marker, a numeric
# value possibly parenthesised, a "-"/"--" nil cell).
# The OCI statement's ENTIRE template: romans I/II/III and the 2.x sub-tree.
# Nothing else is a row. Anything outside this is a page artefact — the date
# header ("31 MART 2024 TARİHİNDE SONA EREN…" → hierarchy '31', name 'MART') or
# the statement title ("KAR VEYA ZARAR VE DİĞER KAPSAMLI GELİR TABLOSU" → the
# section's own roman 'IV.'/'V.'), both carrying the bare 4-digit year truncated
# to its first thousands group as an "amount" of 202.
#
# This is the OCI sibling of the defect dedup_hierarchy_rows.py already cleaned
# out of the frozen BS/PL tables ("a statement TITLE mis-parsed as a data row
# with a garbage amount (<=202) … max |amount| = 202") — the same fingerprint,
# never extended here. Corpus: 577 such rows across 574 of 1050 partitions (55%),
# against 16,709 template rows. Zero real rows fall outside the template and no
# real row anywhere carries amount == 202.0, so the filter cannot take data.
_OCI_TEMPLATE = re.compile(r'^(?:I{1,3}\.?|2(?:\.\d+){1,2}\.?)$')

_COORD_MARK = re.compile(r'^(?:[IVXL]+\.|\d+(?:\.\d+)*\.?)$')
_COORD_VAL = re.compile(r'^\(?-?[\d][\d.,]*\)?$')
_COORD_NIL = re.compile(r'^-{1,2}$')


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


def _drop_offtemplate(rows: list[StatementRow]) -> list[StatementRow]:
    """Drop rows whose hierarchy is outside the OCI template (see _OCI_TEMPLATE).

    Applied to every CANDIDATE, not to the winner, and that ordering is the whole
    point: when no candidate validates, extract_oci falls back to
    `max(candidates, key=len)` — so a stray row inflates its candidate's length
    and helps the WRONG column template win. Filtering first makes the
    length comparison count real rows only.
    """
    return [r for r in rows if _OCI_TEMPLATE.fullmatch((r.hierarchy or "").strip())]


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


def _coord_oci_text(pdf_path: str, oci_page: int) -> str:
    """Rebuild the OCI rows from fitz word COORDINATES, reassembling rows whose
    hierarchy marker, label and values landed on different physical lines, then
    emit one clean "marker label v1 v2" line per logical row for the normal text
    parser to consume.

    Handles the two BRSA-interim pathologies the line-based parser drops:
      • a wrapped label whose continuation / values sit on the line(s) BELOW the
        marker (e.g. DENIZ 2.1.4 "… Diğer Kapsamlı" / "Unsurları -- 15.039");
      • a value on its own line ABOVE a marker-only line (ALNTF 2.2.2: "(43,619)"
        above "2.2.2 …Giderleri (62,374)") — the marker comes AFTER its current
        value, so a line parser can't see them as one row.

    Walks visual rows top→bottom. A non-marker row FILLS the current logical row
    while it is still value-INCOMPLETE (< ncol cells, nils counted); once complete
    its trailing label/value fragments BUFFER and prepend to the NEXT marker. Stops
    at roman III (the OCI total is the last row) so footers/notes can't bleed in.
    Values are emitted left→right by x, so the current-period column precedes the
    prior-period one regardless of which physical line each came from."""
    vrows = _fitz_visual_rows(pdf_path, oci_page - 1)
    if not vrows:
        return ""
    classified: list[tuple[str | None, str, list[tuple[float, str]]]] = []
    for toks in vrows:
        if not toks:
            continue
        marker: str | None = None
        start = 0
        if _COORD_MARK.match(toks[0][2]):
            marker, start = toks[0][2], 1
        label: list[str] = []
        vals: list[tuple[float, str]] = []
        for x0, _x1, t in toks[start:]:
            (vals.append((x0, t)) if (_COORD_VAL.match(t) or _COORD_NIL.match(t))
             else label.append(t))
        classified.append((marker, ' '.join(label).strip(), vals))
    # Column count = number of value cells on the roman "I." row (period net
    # profit — always fully populated). Falls back to 2.
    ncol = 2
    for m, _l, v in classified:
        if m and m.rstrip('.') == 'I' and v:
            ncol = len(v)
            break

    logical: list[dict] = []
    buf_label: list[str] = []
    buf_vals: list[tuple[float, str]] = []
    for marker, label, vals in classified:
        if marker:
            lab = ' '.join(buf_label + ([label] if label else [])).strip()
            logical.append({'m': marker, 'l': lab, 'v': list(buf_vals) + vals})
            buf_label, buf_vals = [], []
            if marker.rstrip('.') == 'III':
                break  # OCI total is the last row — ignore any trailing notes
        else:
            cur = logical[-1] if logical else None
            if cur is not None and len(cur['v']) < ncol and (vals or label):
                if vals:
                    cur['v'].extend(vals)
                if label:
                    cur['l'] = (cur['l'] + ' ' + label).strip()
            else:  # current row complete (or none yet) → belongs to the NEXT marker
                if vals:
                    buf_vals.extend(vals)
                if label:
                    buf_label.append(label)
    lines = []
    for r in logical:
        vs = ' '.join(t for _, t in sorted(r['v'], key=lambda z: z[0]))
        lines.append(f"{r['m']} {r['l']} {vs}".strip())
    return '\n'.join(lines)


def extract_oci(pdf_path: str, oci_page: int) -> OCIReport:
    """Validation-guided OCI extraction from an already-located OCI page."""
    n0 = _detect_pl_ncols(pdf_path, oci_page)
    n_templates = sorted({n0, 2, 4})

    def _cands_from(text: str) -> list[list[StatementRow]]:
        return [c for c in (_drop_offtemplate(_parse_oci_with(text, n))
                            for n in n_templates) if c]

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
    # The wide-interleaved GARAN/AKBNK "…Profit or Loss AND Other Comprehensive
    # Income" page used to need pdfplumber here — but that page is /Rotate-90
    # landscape, and the rotation-aware _fitz_page_text now reads its columns
    # cleanly (the garbling was un-rotated word bboxes, not a fitz limitation), so
    # the fitz candidates above cover it. No pdfplumber.
    # COORDINATE RECONSTRUCTION: when no candidate yet foots the 2.1/2.2 sub-trees
    # (hierarchy_sum fail — a leaf row dropped because its label/value wrapped to
    # another physical line, or its marker prints below its value), rebuild rows
    # from word coordinates. Added ONLY if it itself FULLY validates (chain AND
    # hierarchy, score tier 2) — a coincidental all-sums-foot on wrong data is
    # effectively impossible — so it can never displace a correct parse or corrupt
    # the proven-passing partitions; at worst it changes nothing.
    if not any(_oci_candidate_score(c)[1] == 1 for c in candidates):
        for c in _cands_from(_coord_oci_text(pdf_path, oci_page)):
            if _oci_candidate_score(c)[1] == 1:
                candidates.append(c)
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
