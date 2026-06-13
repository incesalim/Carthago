"""Equity-change (özkaynak değişim tablosu) extractor.

BRSA statement of changes in shareholders' equity — a WIDE table that follows
the OCI page. Two pages per report: CARİ DÖNEM (current period) and ÖNCEKİ
DÖNEM (prior period), each with:

  14 value columns (unconsolidated):
    0  paid_in_capital
    1  share_premium
    2  share_cancellation_profits
    3  other_capital_reserves
    4  oci_not_reclassified_1   (e.g. revaluation surplus)
    5  oci_not_reclassified_2   (e.g. actuarial remeasurements)
    6  oci_not_reclassified_3   (e.g. equity-method OCI share)
    7  oci_reclassified_1       (e.g. fx translation differences)
    8  oci_reclassified_2       (e.g. cash-flow hedge gains/losses)
    9  oci_reclassified_3       (e.g. equity-method reclassified OCI)
   10  profit_reserves
   11  prior_period_profit_loss
   12  period_net_profit_loss
   13  total_equity

  + 2 for consolidated (16 total):
   14  minority_interest
   15  total_equity_incl_minority

Column identification is POSITIONAL — modal value-token count over rows with
≥10 tokens, clamped to {14, 16}. Header rows are multi-line wrapped Turkish/
English text and are never parsed. Every accepted row must pass the gate:
   |total_equity − Σ(first 13 components)| ≤ tolerance
which prevents misaligned rows from being stored.

Rows: romans I.–XI. (+2.1/2.2, 11.1–11.3) plus the prefix-less closing row
"Dönem Sonu Bakiyesi" / "Closing Balance".

Hazards:
- Split digits ("3 .505.742") — fitz coordinate-merge repairs these.
- ALBRK-style label wrapping — _fitz_merge_rows handles lookahead-4.
- "-" zeros, paren negatives (parse_num handles both).
- Surplus/missing tokens per row — try first-n and last-n windows.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

from .extractor import (
    HIERARCHY_PAT, NUM_PAT, _FOOTNOTE_RX, _LINE_HIER_RX, _norm,
    extract_page_text_repaired, parse_num,
)

try:
    import fitz as _fitz
    _HAS_FITZ = True
except ImportError:
    _HAS_FITZ = False

_NUM_RX = re.compile(NUM_PAT)
_CLOSING_RX = re.compile(r'BAK[Iİ]YE|BALANCE|BAK[IİIi]YES', re.I)
_CURRENT_RX  = re.compile(r'CAR[Iİ]\s*D[OÖ]NEM|CURRENT\s*PERIOD', re.I)
_PRIOR_RX    = re.compile(r'[OÖ]NCES?\s*D[OÖ]NEM|[OÖ]NCES?[İI]\s*D[OÖ]NEM|PRIOR\s*PERIOD|PREVIOUS\s*PERIOD', re.I)
_EQ_ANCHORS  = ("OZKAYNAKDEGISIM", "OZKAYNAKDEĞIŞIM", "CHANGESINSHAREHOLDERS",
                "CHANGESINEQUITY", "STATEMENTOFCHANGES")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class EquityChangeRow:
    order: int
    hierarchy: str
    name: str
    period_type: str                   # 'current' | 'prior'
    source_page: int
    paid_in_capital: float | None            = None
    share_premium: float | None              = None
    share_cancellation_profits: float | None = None
    other_capital_reserves: float | None     = None
    oci_not_reclassified_1: float | None     = None
    oci_not_reclassified_2: float | None     = None
    oci_not_reclassified_3: float | None     = None
    oci_reclassified_1: float | None         = None
    oci_reclassified_2: float | None         = None
    oci_reclassified_3: float | None         = None
    profit_reserves: float | None            = None
    prior_period_profit_loss: float | None   = None
    period_net_profit_loss: float | None     = None
    total_equity: float | None               = None
    minority_interest: float | None          = None
    total_equity_incl_minority: float | None = None


@dataclass
class EquityChangeReport:
    pdf_path: str
    rows: list[EquityChangeRow] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.rows


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _count_value_tokens(line: str) -> int:
    """Count numeric value tokens on a line, stripping the leading hierarchy marker."""
    masked = _FOOTNOTE_RX.sub(lambda m: " " * len(m.group()), line)
    hier_m = _LINE_HIER_RX.match(masked)
    if hier_m:
        masked = masked[hier_m.end():]
    return len(_NUM_RX.findall(masked))


def _modal_ncols(lines: list[str], min_tokens: int = 10) -> int:
    """Modal value-token count across lines with ≥min_tokens tokens, clamped to {14,16}."""
    counts: dict[int, int] = {}
    for line in lines:
        n = _count_value_tokens(line)
        if n >= min_tokens:
            counts[n] = counts.get(n, 0) + 1
    if not counts:
        return 14
    modal = max(counts, key=counts.__getitem__)
    # Clamp to known templates
    if modal >= 15:
        return 16
    return 14


def _parse_row_tokens(line: str) -> list[float | None] | None:
    """Extract all value tokens from a line as floats. Returns None if <2 tokens."""
    masked = _FOOTNOTE_RX.sub(lambda m: " " * len(m.group()), line)
    hier_m = _LINE_HIER_RX.match(masked)
    if hier_m:
        masked = masked[hier_m.end():]
    tokens = _NUM_RX.findall(masked)
    if len(tokens) < 2:
        return None
    result = []
    for t in tokens:
        t = t.strip()
        result.append(parse_num(t))
    return result


def _row_gate(vals: list[float | None], n_cols: int) -> bool:
    """Accept row if total_equity ≈ Σ(first 13 components).
    For 16-col also check grand_total ≈ total + minority."""
    if len(vals) < n_cols:
        return False
    components = [v for v in vals[:13] if v is not None]
    total = vals[13]
    if total is None or not components:
        return False
    comp_sum = sum(components)
    tol = max(n_cols * 3.0, abs(total) * 5e-5)
    if abs(comp_sum - total) > tol:
        return False
    if n_cols == 16:
        minority = vals[14]
        grand = vals[15]
        if minority is not None and grand is not None:
            tol2 = max(3.0, abs(grand) * 5e-5)
            if abs((total + minority) - grand) > tol2:
                return False
    return True


def _try_fit(tokens: list[float | None], n_cols: int) -> list[float | None] | None:
    """Try to fit `tokens` into exactly `n_cols` by first-n or last-n window."""
    if len(tokens) == n_cols:
        if _row_gate(tokens, n_cols):
            return tokens
        return None
    if len(tokens) > n_cols:
        # Try first-n
        first = tokens[:n_cols]
        if _row_gate(first, n_cols):
            return first
        # Try last-n
        last = tokens[-n_cols:]
        if _row_gate(last, n_cols):
            return last
    return None


def _split_label_eq(line: str) -> tuple[str, str]:
    """Return (hierarchy, item_name) for an equity-table row.
    Accepts HIERARCHY_PAT matches AND the closing-row pattern (no prefix)."""
    stripped = line.strip()
    m = HIERARCHY_PAT.match(stripped)
    if m:
        h = m.group('h')
        name = m.group('rest').strip()
        # Strip trailing numeric garbage
        name = _NUM_RX.sub('', name).rstrip('()-, ').strip()
        return h, name
    # Closing row: "Dönem Sonu Bakiyesi …" or "Closing Balance …"
    if _CLOSING_RX.search(stripped[:60]):
        name = _NUM_RX.sub('', stripped).rstrip('()-, ').strip()
        return '', name
    return '', ''


def _fitz_page_lines(pdf_path: str, page_idx_0: int) -> list[str]:
    """Get fitz-coordinate-merged text lines for one page (0-indexed)."""
    if not _HAS_FITZ:
        return []
    try:
        doc = _fitz.open(pdf_path)
        page = doc[page_idx_0]
        blocks = page.get_text("words")  # (x0,y0,x1,y1, word, block, line, word_no)
        # Group by (block, line)
        from collections import defaultdict
        line_map: dict = defaultdict(list)
        for item in blocks:
            line_map[(item[5], item[6])].append(item)
        lines = []
        for key in sorted(line_map):
            words = sorted(line_map[key], key=lambda w: w[0])
            # Merge split digits
            merged = []
            i = 0
            while i < len(words):
                w = words[i]
                x0, x1, text = w[0], w[2], w[4]
                j = i + 1
                while j < len(words) and j < i + 4:
                    nxt = words[j]
                    gap = nxt[0] - x1
                    if (re.match(r'^\d{1,2}$', text) and re.match(r'^[.,\d]', nxt[4]) and gap < 4):
                        text, x1 = text + nxt[4], nxt[2]
                        j += 1
                        continue
                    if (text and text[-1].isdigit() and re.match(r'^[.,]\d', nxt[4]) and gap < 4):
                        text, x1 = text + nxt[4], nxt[2]
                        j += 1
                        continue
                    break
                merged.append(text)
                i = j
            lines.append(' '.join(merged))
        doc.close()
        return lines
    except Exception:
        return []


def _parse_equity_page(pdf_path: str, page_idx_1: int, period_type: str,
                       n_cols: int) -> list[EquityChangeRow]:
    """Parse one equity-change page into EquityChangeRow objects."""
    # Try pdfplumber-repaired path first, then fitz
    rows_pp: list[EquityChangeRow] = []
    rows_fz: list[EquityChangeRow] = []

    for use_fitz in (False, True) if _HAS_FITZ else (False,):
        result: list[EquityChangeRow] = []
        if use_fitz:
            lines = _fitz_page_lines(pdf_path, page_idx_1 - 1)
        else:
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    lines = extract_page_text_repaired(pdf.pages[page_idx_1 - 1]).split('\n')
            except Exception:
                lines = []

        order = 0
        for line in lines:
            line = line.strip()
            if not line:
                continue
            h, name = _split_label_eq(line)
            if not name:
                continue
            tokens = _parse_row_tokens(line)
            if tokens is None:
                continue
            fitted = _try_fit(tokens, n_cols)
            if fitted is None:
                continue
            order += 1
            cols = fitted
            row = EquityChangeRow(
                order=order, hierarchy=h, name=name,
                period_type=period_type, source_page=page_idx_1,
                paid_in_capital=cols[0],
                share_premium=cols[1],
                share_cancellation_profits=cols[2],
                other_capital_reserves=cols[3],
                oci_not_reclassified_1=cols[4],
                oci_not_reclassified_2=cols[5],
                oci_not_reclassified_3=cols[6],
                oci_reclassified_1=cols[7],
                oci_reclassified_2=cols[8],
                oci_reclassified_3=cols[9],
                profit_reserves=cols[10],
                prior_period_profit_loss=cols[11],
                period_net_profit_loss=cols[12],
                total_equity=cols[13],
                minority_interest=cols[14] if n_cols == 16 else None,
                total_equity_incl_minority=cols[15] if n_cols == 16 else None,
            )
            result.append(row)

        if use_fitz:
            rows_fz = result
        else:
            rows_pp = result

    # Pick the path with more accepted rows
    best = rows_fz if len(rows_fz) > len(rows_pp) else rows_pp
    # Mid-page split: some PDFs print both the current and prior equity tables on
    # a single page, so every row arrives tagged with the same period_type.  We
    # split them and re-tag the second block with the opposite period.
    opposite = 'prior' if period_type == 'current' else 'current'
    split_idx: int | None = None
    # (a) Preferred signal: the current table's closing row ("Dönem Sonu
    #     Bakiyesi", hierarchy='') sitting somewhere other than the last row.
    for idx, r in enumerate(best):
        if not r.hierarchy and _CLOSING_RX.search(r.name) and idx < len(best) - 1:
            split_idx = idx
            break
    # (b) Fallback: some banks (e.g. TEB) omit the current table's closing row, so
    #     the only marker that a second table has begun is the roman sequence
    #     restarting — a second row opening with "I." after the first.  Split
    #     immediately before it.  (A normal single-table page has just one "I.",
    #     so this never fires spuriously.)
    if split_idx is None and best and best[0].hierarchy == 'I.':
        for idx in range(1, len(best)):
            if best[idx].hierarchy == 'I.':
                split_idx = idx - 1
                break
    if split_idx is not None:
        for new_ord, r in enumerate(best[split_idx + 1:], start=1):
            r.period_type = opposite
            r.order = new_ord
    return best


# ---------------------------------------------------------------------------
# Page location
# ---------------------------------------------------------------------------

def _locate_equity_pages(pdf, pdf_path: str,
                         after_page: int | None) -> list[tuple[int, str]]:
    """Return list of (page_idx_1, period_type) for up to 2 equity pages.

    The statement of changes in equity is the ONLY BRSA statement laid out as a
    WIDE table (14 value columns unconsolidated, 16 consolidated); every other
    statement carries ≤6.  We therefore detect it by that fingerprint — ≥3 lines
    each with ≥10 numeric value tokens — rather than by its title anchor.  The
    anchor is unreliable: ODEA renders the title in an image the text layer never
    exposes (the only anchor hit is the table of contents, which has no data),
    and Ziraat writes "ÖZKAYNAKLAR DEĞİŞİM" → normalised ``OZKAYNAKLARDEGISIM``,
    which doesn't contain the ``OZKAYNAKDEGISIM`` anchor.

    Scanning starts just after the OCI/P&L page (equity always immediately
    follows them) and stops as soon as the run of wide pages ends, so it never
    reaches the wide footnote tables (interest-rate sensitivity, maturity gap)
    deeper in the report.  period_type is taken from CARİ/ÖNCEKİ DÖNEM when
    present, else positional (first=current, second=prior).
    """
    if after_page is None:
        return []
    found: list[tuple[int, str]] = []
    n_pages = len(pdf.pages)
    for i in range(after_page + 1, n_pages + 1):
        text = pdf.pages[i - 1].extract_text() or ''
        # The wide-table fingerprint: ≥3 lines carrying ≥10 numeric tokens.
        wide_rows = sum(1 for ln in text.split('\n') if _count_value_tokens(ln) >= 10)
        if wide_rows < 3:
            if found:
                break                 # the run of equity pages has ended
            # Equity sits within a few pages of OCI; bound the scan so a report
            # whose equity is image-only (unrecoverable) doesn't sweep 150 pages.
            if i - after_page > 12:
                break
            continue
        period_type = 'current'
        if _PRIOR_RX.search(text):
            period_type = 'prior'
        elif _CURRENT_RX.search(text):
            period_type = 'current'
        elif found:
            # Second matched page defaults to prior
            period_type = 'prior'
        found.append((i, period_type))
        if len(found) == 2:
            break
    # Enforce distinct period_types.  BRSA standard order: current then prior.
    # If the detector assigned the same type to both pages (CARİ DÖNEM label
    # absent from first page, present on second, etc.), fall back to positional.
    if len(found) == 2 and found[0][1] == found[1][1]:
        found = [(found[0][0], 'current'), (found[1][0], 'prior')]
    return found


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_from_pdf(pdf, pdf_path: str, after_page: int | None) -> EquityChangeReport:
    """Extract both equity-change pages from an open pdfplumber PDF."""
    pdf_path = str(pdf_path)
    rep = EquityChangeReport(pdf_path=pdf_path)
    pages = _locate_equity_pages(pdf, pdf_path, after_page)
    if not pages:
        return rep
    # Determine column count from the first (widest) page
    try:
        with pdfplumber.open(pdf_path) as _pdf2:
            first_text = _pdf2.pages[pages[0][0] - 1].extract_text() or ''
    except Exception:
        first_text = ''
    lines = first_text.split('\n')
    n_cols = _modal_ncols(lines)
    for page_idx_1, period_type in pages:
        rows = _parse_equity_page(pdf_path, page_idx_1, period_type, n_cols)
        rep.rows.extend(rows)
    return rep


def upsert(conn: sqlite3.Connection, bank: str, period: str,
           kind: str, report: EquityChangeReport) -> int:
    """Delete + insert equity-change rows for (bank, period, kind). Returns row count."""
    conn.execute(
        'DELETE FROM bank_audit_equity_change WHERE bank_ticker=? AND period=? AND kind=?',
        (bank, period, kind),
    )
    if not report.rows:
        return 0
    # Deduplicate by (period_type, order) — keep last occurrence.  Guards
    # against the unlikely but possible case of duplicate rows from the extractor.
    seen: dict[tuple, int] = {}
    deduped = []
    for r in report.rows:
        key = (r.period_type, r.order)
        if key in seen:
            deduped[seen[key]] = r  # type: ignore[index]
        else:
            seen[key] = len(deduped)
            deduped.append(r)
    conn.executemany(
        'INSERT INTO bank_audit_equity_change '
        '(bank_ticker, period, kind, period_type, item_order, hierarchy, item_name, '
        ' paid_in_capital, share_premium, share_cancellation_profits, other_capital_reserves, '
        ' oci_not_reclassified_1, oci_not_reclassified_2, oci_not_reclassified_3, '
        ' oci_reclassified_1, oci_reclassified_2, oci_reclassified_3, '
        ' profit_reserves, prior_period_profit_loss, period_net_profit_loss, total_equity, '
        ' minority_interest, total_equity_incl_minority, source_page) '
        'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        [(bank, period, kind, r.period_type, r.order, r.hierarchy, r.name,
          r.paid_in_capital, r.share_premium, r.share_cancellation_profits,
          r.other_capital_reserves,
          r.oci_not_reclassified_1, r.oci_not_reclassified_2, r.oci_not_reclassified_3,
          r.oci_reclassified_1, r.oci_reclassified_2, r.oci_reclassified_3,
          r.profit_reserves, r.prior_period_profit_loss, r.period_net_profit_loss,
          r.total_equity, r.minority_interest, r.total_equity_incl_minority,
          r.source_page)
         for r in deduped],
    )
    return len(deduped)
