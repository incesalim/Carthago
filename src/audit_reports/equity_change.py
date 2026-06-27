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

from .extractor import (
    HIERARCHY_PAT, NUM_PAT, _FOOTNOTE_RX, _LINE_HIER_RX, _norm,
    _fitz_page_text, _fitz_page_count, parse_num,
)
# Self-contained equity validators reused to SCORE reconstruction candidates
# (validator.py imports only stdlib → no circular import).
from .validator import _eq_roman as _v_eq_roman, _eq_closing as _v_eq_closing

try:
    import fitz as _fitz
    _HAS_FITZ = True
except ImportError:
    _HAS_FITZ = False

_NUM_RX = re.compile(NUM_PAT)
_CLOSING_RX = re.compile(r'BAK[Iİ]YE|BALANCE|BAK[IİIi]YES', re.I)
_CURRENT_RX  = re.compile(r'CAR[Iİ]\s*D[OÖ]NEM|CURRENT\s*PERIOD', re.I)
# "Önceki Dönem" (the standard BRSA term for prior period) MUST match — the old
# pattern only covered "Önce(si) Dönem" and missed the "ki", so a bank that
# prints its prior-period matrix FIRST (HSBC: 2023 page before the 2024 page)
# had that page default to 'current' → the enforce-distinct fallback then swapped
# the two periods positionally (stored "current" = the prior-year matrix, closing
# ≠ BS equity). Accept Önce / Öncesi / Önceki.
_PRIOR_RX    = re.compile(r'[OÖ]NCE(?:K[İI]|S[İI]?)?\s*D[OÖ]NEM|PRIOR\s*PERIOD|PREVIOUS\s*PERIOD', re.I)
_EQ_ANCHORS  = ("OZKAYNAKDEGISIM", "OZKAYNAKDEĞIŞIM", "CHANGESINSHAREHOLDERS",
                "CHANGESINEQUITY", "STATEMENTOFCHANGES")
_DASH_RUN_RX = re.compile(r'-{2,}')
_YEAR_RX = re.compile(r'\b(20\d\d)\b')


def _max_year(text: str) -> int | None:
    """The latest 20xx year on the page. The current equity table closes on the
    later period-end date, so when the CARİ/ÖNCEKİ markers are absent (ALNTF
    prints bare date-keyed rows) the page with the larger max-year is current."""
    yrs = _YEAR_RX.findall(text or '')
    return max(int(y) for y in yrs) if yrs else None


def _norm_dashes(line: str) -> str:
    """A run of 2+ dashes is a zero cell rendered as "--" (DenizBank). NUM_PAT
    only recognises a lone space-padded "-" as a zero, so collapse each "--" run
    to " - " — otherwise the zero columns are dropped and the row mis-aligns
    (DENIZ → only 14 of its 16 tokens survived, every row failed the sum gate)."""
    return _DASH_RUN_RX.sub(' - ', line)


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
    masked = _FOOTNOTE_RX.sub(lambda m: " " * len(m.group()), _norm_dashes(line))
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
    # Clamp to known templates. Only ≥16 is the consolidated 16-col layout; a
    # modal of 15 is a 14-col row with a duplicated trailing total (EMLAK), not a
    # 16-col table — rounding it up to 16 made the 14-col gate reject every row.
    if modal >= 16:
        return 16
    return 14


def _parse_row_tokens(line: str) -> list[float | None] | None:
    """Extract all value tokens from a line as floats. Returns None if <2 tokens."""
    masked = _FOOTNOTE_RX.sub(lambda m: " " * len(m.group()), _norm_dashes(line))
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
    """Fit `tokens` into exactly `n_cols`, accepting only a gate-passing alignment.

    Three shapes occur in real reports:
      • exactly n_cols                → use as-is;
      • more than n_cols (a surplus token — EMLAK prints the period-end total
        twice)                        → try the first-n and last-n windows;
      • exactly n_cols-1 (a component column rendered fully blank — no value, not
        even a dash — so it never tokenises; AKBNK's comprehensive-income row IV)
                                      → insert a 0.0 at each position and take the
        one the row-sum gate admits. The gate (Σcomponents == total; for 16-col
        also total+minority == grand) is discriminating, so only the real slot
        passes — this can only recover an otherwise-dropped row, never re-shape a
        row that already fits.
    """
    if len(tokens) == n_cols:
        return tokens if _row_gate(tokens, n_cols) else None
    if len(tokens) > n_cols:
        first = tokens[:n_cols]
        if _row_gate(first, n_cols):
            return first
        last = tokens[-n_cols:]
        if _row_gate(last, n_cols):
            return last
        return None
    if len(tokens) == n_cols - 1:
        for ins in range(n_cols):
            cand = tokens[:ins] + [0.0] + tokens[ins:]
            if _row_gate(cand, n_cols):
                return cand
    if len(tokens) == n_cols - 2:
        # Two component columns rendered fully blank (ANADOLU's consolidated
        # comprehensive-income row IV drops both prior-period-P&L and a reserve
        # column → 14 tokens in a 16-col table → dropped → its total left out of
        # Σromans → eq_col_chain fails). Place two 0.0s at every column pair; the
        # dual row-gate (Σcomponents==total AND total+minority==grand) admits only
        # an alignment that lands the totals correctly, and the inserts are zeros
        # so they can't perturb any captured value.
        #
        # CAVEAT: on a letter-spacing-corrupted text layer (ISCTR's image-only
        # quarters, ~2 rows) the looser 2-blank search can false-pass the gate and
        # recover a mis-aligned row. Those partitions are sparse-but-"passing"
        # (checks skip), so the non-destructive skip-if-passing guard and the
        # --only-failing re-extract lane both leave them untouched — n-2 only ever
        # runs on a partition deliberately being re-extracted (failing/--force).
        for a in range(n_cols - 1):
            for b in range(a + 1, n_cols):
                cand, it = [], iter(tokens)
                for pos in range(n_cols):
                    cand.append(0.0 if pos in (a, b) else next(it))
                if _row_gate(cand, n_cols):
                    return cand
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


# ---------------------------------------------------------------------------
# Checklist-anchored row admission
# ---------------------------------------------------------------------------
# BRSA equity-change tables are rigidly standardised: every report — Turkish OR
# English — carries the SAME fixed rows in the same order. We admit a line as a
# data row only when it bears one of these known markers (or is the closing
# balance), anchoring on the marker rather than guessing from line shape. The
# marker is language-neutral, so admission survives English labels (GARAN) and
# footnote text bleeding into a row ("The accompanying notes … VI. Capital
# Increase …", which buried the marker and made the old line-start matcher drop
# rows VI/VII/VIII/XI).
_EQ_ROMANS = ('I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI')
_EQ_SUBS = ('2.1', '2.2', '11.1', '11.2', '11.3')
_EQ_MARKERS = set(_EQ_ROMANS) | set(_EQ_SUBS)
# The main roman chain in order (with dots, as stored in `hierarchy`) — the fixed
# "checklist" used to infer a row whose marker the text layer dropped.
_EQ_ROW_SEQ = tuple(r + '.' for r in _EQ_ROMANS)
# The closing balance prints its own roman formula that always sums THROUGH XI,
# e.g. "(III+IV+…+X+XI)" / "(I+II+III+…+X+XI)". This must NOT match the new-balance
# row III's "(I+II)" — so the formula is required to reach XI.
_EQ_CLOSING_FORMULA_RX = re.compile(r'\(\s*[IVX][IVX0-9.+\s…]*XI')


def _eq_is_closing(line: str) -> bool:
    """True for the prefix-less closing row ("Dönem Sonu Bakiyesi" / "Balances at
    end of the period (III+IV+…+XI)"). Only consulted when no marker was found, so
    the opening "I. Balances at Beginning" (which carries marker I.) is never
    mistaken for it — which is why matching the otherwise-ambiguous word
    "Balance/Bakiye" is safe here."""
    head = line[:80]
    return bool(_EQ_CLOSING_FORMULA_RX.search(head) or _CLOSING_RX.search(head))


# A marker glued to its label with no space ("VIII.Convertible", "VI.İç"). The
# trailing '.' is mandatory so an English word that merely starts with a roman
# letter ("Income", "Internal", "Increase") is NOT mistaken for marker "I.".
_EQ_GLUED_RX = re.compile(r'^([IVX]{1,5}|\d{1,2}\.\d{1,2})\.(.+)$')


def _eq_split(line: str) -> tuple[str | None, str]:
    """Return (marker, label) for an equity-table row, or (None, '') to skip.

    marker is the normalised BRSA marker ('VI.', '2.1', …) found among the first
    few whitespace tokens — even when footnote words precede it, and even when it
    is glued to its label. The closing row returns (None, <label>). Value
    extraction is unaffected: `_parse_row_tokens` finds the numeric tokens
    regardless of any leading words."""
    toks = line.split()
    for i, tok in enumerate(toks[:6]):
        marker_core, rest = None, ''
        core = tok.strip('().,')
        if core in _EQ_MARKERS:                 # exact token: "VI." "2.1" "11.1"
            marker_core = core
        else:
            m = _EQ_GLUED_RX.match(tok)          # glued: "VIII.Convertible"
            if m and m.group(1) in _EQ_MARKERS:
                marker_core, rest = m.group(1), m.group(2)
        if marker_core is None:
            continue
        marker = marker_core + '.' if marker_core in _EQ_ROMANS else marker_core
        after = (rest + ' ' + ' '.join(toks[i + 1:])).strip()
        label = _NUM_RX.sub('', after).rstrip('()-, ').strip()
        return marker, label
    if _eq_is_closing(line):
        return None, _NUM_RX.sub('', line).rstrip('()-, ').strip()
    return None, ''


_YEAR_RX = re.compile(r'(?<!\d)(20[12]\d)(?!\d)')


def _block1_period_for_split(pdf_path: str, page_idx_1: int) -> str:
    """For a single page carrying BOTH period blocks, return block1's period
    ('current' | 'prior'). BRSA standard is current-then-prior (block1='current'),
    but some banks print prior-then-current (GARAN, KUVEYT). Detect the reversed
    case robustly: the report's CURRENT period is the LATEST year on the page; if
    that latest year appears AFTER block1's closing-balance line (i.e. in block2),
    the page is reversed and block1 is 'prior'. This is title-immune (the title
    year sits before the closing) and works for annual AND interim. Defaults to
    'current' when undetermined (the standard order)."""
    text = _fitz_page_text(pdf_path, page_idx_1 - 1) if _HAS_FITZ else ''
    years = [int(m.group(1)) for m in _YEAR_RX.finditer(text)]
    if not years:
        return 'current'
    lines = text.split('\n')
    close_i = next((i for i, ln in enumerate(lines)
                    if _EQ_CLOSING_FORMULA_RX.search(ln)), None)
    if close_i is None:
        return 'current'
    after = '\n'.join(lines[close_i + 1:])
    return 'prior' if str(max(years)) in after else 'current'


def _dedup_roman_rows(rows: list[EquityChangeRow]) -> list[EquityChangeRow]:
    """Drop spurious positional-inference duplicates. The checklist walk can label a
    markerless sub/blank row as the next main roman even when that roman ALSO appears
    later with its own marker (ZIRAAT: III.=0 inferred + III.=471M real). The real
    row carries a label; the inferred one is nameless — so, per period block, when a
    main roman (I.–XI.) appears more than once, keep the labelled row(s) and drop the
    nameless one(s) (if all nameless, keep the first). Then renumber item_order."""
    from collections import Counter, defaultdict
    main = set(_EQ_ROW_SEQ)
    groups: dict[tuple, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        if r.hierarchy in main:
            groups[(r.period_type, r.hierarchy)].append(i)
    drop: set[int] = set()
    for idxs in groups.values():
        if len(idxs) <= 1:
            continue
        named = [i for i in idxs if (rows[i].name or '').strip()]
        if named:
            drop.update(i for i in idxs if i not in named)
        else:
            drop.update(idxs[1:])
    out = [r for i, r in enumerate(rows) if i not in drop]
    cnt: Counter = Counter()
    for r in out:
        cnt[r.period_type] += 1
        r.order = cnt[r.period_type]
    return out


# --- validation-guided candidate scoring -----------------------------------
# The reconstruction candidates are scored by whether their column chain CLOSES
# (closing.total_equity ≈ Σ romans III..XI, and I+II=III when present) rather than
# by raw row count, so the parser self-selects the reconstruction that VALIDATES.
# Reuses the validator's own helpers so "the parser agrees with the validator."
_EQ_MIN_REAL_ROWS = 4   # a real page has ≥ opening, III, IV, closing with real totals


def _eq_score_dicts(rows: list["EquityChangeRow"]) -> list[dict]:
    return [{"hierarchy": r.hierarchy, "item_name": r.name,
             "total_equity": r.total_equity,
             "total_equity_incl_minority": r.total_equity_incl_minority}
            for r in rows]


def _eq_chain_closes(d: list[dict]) -> bool:
    """True iff closing.total_equity ≈ Σ(romans III..XI) — the self-contained
    eq_col_chain identity, computed on candidate dicts (no DB). Guards against a
    degenerate parse: the closing total must be a REAL number (>1.0), not 0==0."""
    closing = _v_eq_closing(d)
    r3 = _v_eq_roman(d, 3)
    if closing is None or r3 is None:
        return False
    cl = closing.get("total_equity")
    if cl is None or abs(cl) <= 1.0:
        return False
    roman_sum, found = 0.0, False
    for o in range(3, 12):
        rx = _v_eq_roman(d, o)
        if rx and rx.get("total_equity") is not None:
            roman_sum += rx["total_equity"]
            found = True
    if not found or abs(roman_sum - cl) > max(10.0, abs(cl) * 5e-5):
        return False
    r1, r2 = _v_eq_roman(d, 1), _v_eq_roman(d, 2)   # also require I+II=III when present
    if r1 and r2:
        t1, t2, t3 = r1.get("total_equity"), r2.get("total_equity"), r3.get("total_equity")
        if None not in (t1, t2, t3) and abs((t1 + t2) - t3) > max(3.0, abs(t3) * 5e-5):
            return False
    return True


def _eq_candidate_score(rows: list["EquityChangeRow"]) -> tuple[int, int, int]:
    """Lexicographic (validates_and_substantial, n_real_rows, n_rows) — higher is
    better. tier-1 (first element 1) requires the chain to close AND enough rows
    carrying a non-trivial total, so a near-empty parse that trivially satisfies
    0==0 stays tier-0."""
    if not rows:
        return (0, 0, 0)
    n_real = sum(1 for r in rows
                 if r.total_equity is not None and abs(r.total_equity) > 1.0)
    tier1 = 1 if (n_real >= _EQ_MIN_REAL_ROWS and _eq_chain_closes(_eq_score_dicts(rows))) else 0
    return (tier1, n_real, len(rows))


def _parse_equity_page(pdf_path: str, page_idx_1: int, period_type: str,
                       n_cols: int) -> list[EquityChangeRow]:
    """Parse one equity-change page into EquityChangeRow objects.

    Tries two fitz line reconstructions and keeps whichever admits the most rows
    (fitz-only — no pdfplumber):
      • fitz block/line grouping (_fitz_page_lines) — fitz's own segmentation.
      • fitz y-coordinate bucketing (_fitz_page_text) — rebuilds a visual row from
        cells fitz scatters across block/lines; parses VAKBN's table where
        block/line grouping yields zero wide rows, AND (now rotation-aware) the
        GARAN/AKBNK landscape /Rotate-90 statements that previously only
        pdfplumber's x-clustering could read."""

    def _parse_with(lines: list[str], nc: int) -> list[EquityChangeRow]:
        result: list[EquityChangeRow] = []
        order = 0
        last_ri = -1            # index in _EQ_ROW_SEQ of the last main roman seen
        for line in lines:
            line = line.strip()
            if not line:
                continue
            marker, name = _eq_split(line)
            tokens = _parse_row_tokens(line)
            if tokens is None:
                continue
            fitted = _try_fit(tokens, nc)
            if fitted is None:
                continue
            # Checklist walk: a wide data row that fits but carries no marker AND no
            # label is a row whose marker the text layer dropped (GARAN prints its
            # current-period IV. "Total Comprehensive Income" as values only). The
            # row order is fixed, so it must be the next main roman after the last
            # one seen. (The closing row is excluded — it returns a non-empty label.)
            if marker is None and not name and 0 <= last_ri < len(_EQ_ROW_SEQ) - 1:
                marker = _EQ_ROW_SEQ[last_ri + 1]
            if marker is None and not name:
                continue
            if marker in _EQ_ROW_SEQ:        # reset on each block (second I. → 0)
                last_ri = _EQ_ROW_SEQ.index(marker)
            h = marker or ''
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
                minority_interest=cols[14] if nc == 16 else None,
                total_equity_incl_minority=cols[15] if nc == 16 else None,
            )
            result.append(row)
        return result

    # The line reconstructions, kept so we can re-parse with the other column
    # template (below) if nothing validates at the primary n_cols.
    recons: list[list[str]] = []
    if _HAS_FITZ:
        recons.append(_fitz_page_lines(pdf_path, page_idx_1 - 1))
        recons.append(_fitz_page_text(pdf_path, page_idx_1 - 1).split('\n'))
    if not recons:
        recons.append([])

    candidates: list[list[EquityChangeRow]] = [_parse_with(lines, n_cols) for lines in recons]
    # Self-gated both-template search: if NO candidate's column chain validates at
    # the detected n_cols, the template may be wrong for this bank — also parse each
    # reconstruction with the OTHER template (14↔16) and let the scorer pick. This
    # runs ONLY for partitions that don't already validate, so it can't touch the
    # clean set; it can only turn a chain-failure into a chain-closing parse.
    if not any(_eq_candidate_score(c)[0] == 1 for c in candidates):
        other = 16 if n_cols == 14 else 14
        candidates += [_parse_with(lines, other) for lines in recons]

    # Hybrid selection: prefer the reconstruction whose column chain VALIDATES
    # (closing ≈ Σ romans III..XI), falling back to most-rows when none clearly
    # validates — so the parser self-selects the correct engine/template instead
    # of guessing by row count, WITHOUT regressing the partitions that pass today.
    scored = [(_eq_candidate_score(c), c) for c in candidates]
    validating = [(s, c) for (s, c) in scored if s[0] == 1]
    fullest = max(len(c) for c in candidates)
    if validating:
        win_s, win_c = max(validating, key=lambda sc: sc[0])
        # Don't trade a much-fuller parse for a marginally-shorter validating one.
        best = win_c if win_s[2] >= fullest - 2 else max(candidates, key=len)
    else:
        best = max(candidates, key=len)   # exactly the previous behaviour
    # Mid-page split: some PDFs print both the current and prior equity tables on
    # a single page, so every row arrives tagged with the same period_type.  Find
    # the boundary, then label each block by the dates on the page (not the located
    # period_type, which the period regex can flip for standard current-then-prior
    # banks).
    split_idx: int | None = None
    # (a) Preferred signal: the current table's closing row ("Dönem Sonu
    #     Bakiyesi", hierarchy='') sitting somewhere other than the last row.
    #     It must come AFTER the table body (a III.–XI. row): the opening balance
    #     ("Önceki Dönem Sonu Bakiyesi"/"Beginning") also has hierarchy='' and
    #     matches _CLOSING_RX, but no body precedes it — so a single-period page
    #     whose opening lost its "I." marker (VAKBN) is no longer mis-split.
    _seen_body = False
    for idx, r in enumerate(best):
        if r.hierarchy in _EQ_ROW_SEQ[2:]:        # III. … XI.
            _seen_body = True
        if (_seen_body and not r.hierarchy and _CLOSING_RX.search(r.name)
                and idx < len(best) - 1):
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
        # Order signal, value-based first: in prior-then-current order block1
        # (prior) CLOSES where block2 (current) OPENS, so the period totals chain
        # (block1.closing == block2.opening). Robust where the year-text heuristic
        # can't read the order — ANADOLU prints the period year only in the page
        # header, never beside the closing row, so _block1_period_for_split
        # defaulted to 'current' and swapped its prior-first page. Two years of
        # movement separate block1.closing from block2.opening under the standard
        # current-then-prior order, so this never false-fires there.
        c1 = best[split_idx].total_equity
        o2 = best[split_idx + 1].total_equity if split_idx + 1 < len(best) else None
        if c1 and o2 is not None and abs(c1 - o2) <= abs(c1) * 1e-4:
            block1 = 'prior'
        else:
            block1 = _block1_period_for_split(pdf_path, page_idx_1)
        block2 = 'prior' if block1 == 'current' else 'current'
        for r in best[:split_idx + 1]:
            r.period_type = block1
        for r in best[split_idx + 1:]:
            r.period_type = block2
    # Drop spurious positional-inference roman duplicates and renumber.
    return _dedup_roman_rows(best)


# ---------------------------------------------------------------------------
# Page location
# ---------------------------------------------------------------------------

def _locate_equity_pages(pdf_path: str,
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
    # fitz-only (no pdfplumber): page count + page text from fitz. `len(pdf.pages)`
    # also triggers the pdfminer page-tree hang on poison PDFs (VAKBN 2025Q4).
    n_pages = (_fitz_page_count(pdf_path) if (_HAS_FITZ and pdf_path) else 0)
    for i in range(after_page + 1, (n_pages or 0) + 1):
        # fitz text (fast, ~50× over pdfplumber) for the page scan; same y-bucketed
        # line structure, so the wide-fingerprint count is equivalent.
        text = _fitz_page_text(pdf_path, i - 1)
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
        # period_type from the CARİ/ÖNCEKİ DÖNEM header. Check CURRENT first: the
        # current page's header says "Cari Dönem" but its OPENING row usually reads
        # "Önceki Dönem Sonu Bakiyesi" (the prior-period END = this table's
        # opening), so a PRIOR-first test mislabels the current page as prior
        # (TSKB). The prior page carries "Önceki Dönem" but never "Cari Dönem".
        # Pages with NO period word at all (ALNTF prints bare date-keyed rows) stay
        # None and are resolved by year below. (Mid-page-split single pages are
        # reassigned downstream by _block1_period_for_split regardless.)
        ptext = text  # the rotation-aware fitz text already read for the scan
        if _CURRENT_RX.search(ptext):
            period_type = 'current'
        elif _PRIOR_RX.search(ptext):
            period_type = 'prior'
        else:
            period_type = None
        found.append((i, period_type, _max_year(ptext)))
        if len(found) == 2:
            break
    # Resolve the two pages' period_types. Priority: (1) distinct markers as read;
    # (2) the later period-end YEAR is current (covers marker-less, prior-first
    # layouts like ALNTF); (3) one known marker → the other is its complement;
    # (4) positional (BRSA standard current-then-prior).
    if len(found) == 2:
        (p0, t0, y0), (p1, t1, y1) = found
        if t0 and t1 and t0 != t1:
            return [(p0, t0), (p1, t1)]
        if y0 is not None and y1 is not None and y0 != y1:
            return [(p0, 'current' if y0 > y1 else 'prior'),
                    (p1, 'current' if y1 > y0 else 'prior')]
        if t0 or t1:
            cur_is_0 = (t0 == 'current') or (t1 == 'prior')
            return [(p0, 'current' if cur_is_0 else 'prior'),
                    (p1, 'prior' if cur_is_0 else 'current')]
        return [(p0, 'current'), (p1, 'prior')]
    if len(found) == 1:
        return [(found[0][0], found[0][1] or 'current')]
    return found


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_from_pdf(pdf_path: str, after_page: int | None) -> EquityChangeReport:
    """Extract both equity-change pages — fitz-only, by path (no pdfplumber)."""
    pdf_path = str(pdf_path)
    rep = EquityChangeReport(pdf_path=pdf_path)
    pages = _locate_equity_pages(pdf_path, after_page)
    if not pages:
        return rep
    # Column count (14 unconsolidated / 16 consolidated) from the first equity
    # page, off the rotation-aware fitz y-bucketed text. (Earlier the fitz count
    # over-counted AKBNK 2025 unconsolidated as 16 — but that was the un-rotated
    # /Rotate-90 garbling; with rotation applied the per-row token counts are
    # accurate, so pdfplumber is no longer needed here.)
    try:
        first_text = _fitz_page_text(pdf_path, pages[0][0] - 1) if _HAS_FITZ else ''
    except Exception:
        first_text = ''
    n_cols = _modal_ncols(first_text.split('\n'))
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
