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
from dataclasses import dataclass, field, replace

from .extractor import (
    HIERARCHY_PAT, NUM_PAT, _FOOTNOTE_RX, _LINE_HIER_RX, _SECTION_REF_RX,
    _fitz_page_text, _fitz_page_count, parse_num,
)
# Self-contained equity validators reused to SCORE reconstruction candidates
# (validator.py imports only stdlib → no circular import).
from .validator import _eq_roman as _v_eq_roman, _eq_closing as _v_eq_closing
from .units import UnitContext

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


def _period_header(line: str) -> str | None:
    """Read the table's block heading, excluding profit-column/row labels.

    TSKB prints both "Prior Period" and "Current Period" in its column labels,
    but the actual block header is "Prior Period – 31 March 2022". Date tokens
    belong to that heading and must not make it look like a wide data row.
    """
    line = line.strip()
    for pattern, kind in ((_CURRENT_RX, 'current'), (_PRIOR_RX, 'prior')):
        match = pattern.match(line)
        if match:
            tail = line[match.end():].strip().lstrip('-–:(').strip()
            if not tail or tail[0].isdigit():
                return kind
    return None


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
    masked = _SECTION_REF_RX.sub(lambda m: " " * len(m.group()), _norm_dashes(line))
    masked = _FOOTNOTE_RX.sub(lambda m: " " * len(m.group()), masked)
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


# A standards citation inside a row label — "TMS 8", "TAS 8", "TFRS 9". Its
# numeral is not a value, and unlike a footnote ref it can sit at the very END
# of the label ("Correction made as per TAS 8"), where the last-letter cut below
# would leave it on the value side.
_STD_REF_RX = re.compile(r'\b(?:TMS|TAS|TFRS|IFRS|IAS|UFRS)\s*\d{1,2}\b', re.I)
_CALENDAR_DATE_RX = re.compile(
    r'\b(?:0?[1-9]|[12]\d|3[01])([/.-])(?:0?[1-9]|1[0-2])\1(?:19|20)\d{2}\b'
)


def _mask_label_refs(text: str) -> str:
    """Blank numeric references that belong to the label, preserving offsets.

    Equity rows use both standards citations (``TMS 8``) and dotted dipnot
    references (``(5.5.3)`` / ``(5.2.15)``).  ``NUM_PAT`` otherwise splits a
    dotted reference into value tokens and can make the reference plus a row of
    dashes look like a complete value grid.
    """
    text = _STD_REF_RX.sub(lambda m: " " * len(m.group()), text)
    # ICBC's closing label includes 30/06/2026 immediately before the values.
    # Treat its calendar date as metadata before counting columns, otherwise
    # the surplus date tokens hide genuine short parenthesised losses.
    text = _CALENDAR_DATE_RX.sub(lambda m: " " * len(m.group()), text)
    return _SECTION_REF_RX.sub(lambda m: " " * len(m.group()), text)


def _value_region(text: str) -> str:
    """The value grid alone: the longest run of numeric tokens that no letter
    interrupts.

    An equity row is ``<marker> <label> <values…>``, and the grid is the one
    stretch of the line with no words in it. Taking "everything after the last
    letter" is not equivalent — AKBNK's y-bucketed closing row ends
    ``… 324.751 - 324.751 Kâr veya``, a header fragment the bucketing drags onto
    the row, and that reading would return nothing at all. The longest-run
    reading returns the 16 values and the row foots exactly.

    Standards citations are masked first, because they are the one part of a
    label that can end in a numeral and would otherwise join the grid's run.

    Without this cut a numeral inside the label becomes the first value, and
    every bank's row II carries one: "TMS 8 Uyarınca Yapılan Düzeltmeler",
    "Correction made as per TAS 8", "Adjustment in accordance with TAS 8". The
    surplus window in `_try_fit` takes the leading 16 of 17 tokens, the row-sum
    gate waves it through (|8 - 0| under a tolerance of 48), and paid-in capital
    is stored as 8. In Bin TL that was ₺8k — invisible for four years. Scaled to
    Milyon it is ₺8mn, and `eq_row_sum` failed it on all 11 Q2 filings.

    Also drops a date printed beside the label ("Dönem Sonu Bakiyesi
    30.06.2025"), which the same window would otherwise read as two values.
    """
    scan = _mask_label_refs(text)
    runs: list[list] = []
    cur: list = []
    prev_end = 0
    for m in _NUM_RX.finditer(scan):
        if cur and any(ch.isalpha() for ch in scan[prev_end:m.start()]):
            runs.append(cur)
            cur = []
        cur.append(m)
        prev_end = m.end()
    if cur:
        runs.append(cur)
    if not runs:
        return ""
    best = max(runs, key=len)
    return scan[best[0].start():best[-1].end()]


def _trailing_text(text: str) -> str:
    """Whatever is printed AFTER a row's value grid.

    On AKBNK's rotated landscape page the y-bucketing strands the closing row's
    label on the previous line — "11.3Diğer … - - Dönem Sonu" — and drags a
    column-header fragment onto the closing row itself ("… 324.751 Kâr veya").
    So the label of row N+1 has to be read off the end of row N.
    """
    scan = _mask_label_refs(text)
    region = _value_region(text)
    if not region:
        return ""
    end = scan.rfind(region)
    return scan[end + len(region):].strip() if end >= 0 else ""


def _parse_row_tokens(line: str,
                      n_cols: int | None = None) -> list[float | None] | None:
    """Extract all value tokens from a line as floats. Returns None if <2 tokens.

    `(55)` is ambiguous: a dipnot reference, or the value -55. The footnote mask
    (``\\(\\s*\\d{1,2}\\s*\\)``) has always resolved it as a reference, which was
    safe while amounts printed in Bin TL — a real equity component was never
    two digits there. The 2026Q2 Milyon switch removed three digits from every
    printed figure and made small parenthesised negatives ordinary: TEB's prior
    block carries ``(55)`` for -55 million in the OCI-reclassified column, the
    mask ate it, the row came back one token short, and `_try_fit`'s zero-insert
    missed the row-sum gate by 7 on a tolerance of 48 — so BOTH the opening and
    the new-balance row were dropped, the roman sequence never restarted, the
    mid-page split never fired, and all 32 surviving rows were stored as
    `current`.

    So when the caller knows the template, let the column count decide: the
    reading that fits it is the right one. Masked wins ties and every ambiguous
    case, which is exactly today's behaviour — a row that already fits cannot
    change.
    """
    # Dotted dipnot references are unambiguously label metadata.  Mask them
    # before deciding whether a short parenthesised integer is a footnote or a
    # real negative value; PASHA's ``(5.5.3)`` otherwise becomes 5.5 and 3 and
    # displaces the genuine ``(65)`` dividend cells.
    base = _mask_label_refs(_norm_dashes(line))

    def _tokens_of(text: str) -> list[float | None]:
        # Strip the row marker only when it is one this table can actually
        # carry. `_LINE_HIER_RX` is the generic statement matcher and reads
        # AKBNK's markerless closing row — "5.200 3.506 - 1.815 …" — as
        # hierarchy "5.200", eating its paid-in capital and leaving 15 tokens
        # in a 16-column table, which drops the closing balance and takes the
        # BS cross-check and the column chain down with it.
        hier_m = _LINE_HIER_RX.match(text)
        if hier_m and hier_m.group().strip().rstrip('.') in _EQ_MARKERS:
            text = text[hier_m.end():]
        return [parse_num(t.strip()) for t in _NUM_RX.findall(_value_region(text))]

    masked = _tokens_of(_FOOTNOTE_RX.sub(lambda m: " " * len(m.group()), base))
    if n_cols is not None and len(masked) != n_cols:
        unmasked = _tokens_of(base)
        if len(unmasked) == n_cols:
            masked = unmasked
        elif (n_cols in (14, 16) and len(unmasked) == n_cols + 1
              and _FOOTNOTE_RX.match(_value_region(base))):
            # A leading note reference can coexist with real short negatives:
            # SKBNK's adjusted opening row is ``(13) 2,500 ... (6) ...``.
            # Masking every short parenthesis drops both the note and the
            # loss, then zero-insertion shifts the remaining columns. Remove
            # only the leading reference when the complete printed values
            # reconcile EXACTLY (including minority for a 16-column table).
            # Keep the established read on any tie or residual; ordinary
            # rounding slack is not evidence for discarding a numeric token.
            candidate = unmasked[1:]
            masked_fit = _try_fit(masked, n_cols)
            if (all(value is not None for value in candidate)
                    and _row_fit_residual(candidate, n_cols) == 0
                    and (masked_fit is None
                         or _row_fit_residual(masked_fit, n_cols) > 0)):
                masked = candidate
        elif n_cols in (14, 16) and n_cols - 2 <= len(unmasked) < n_cols:
            # A real 1-2 digit negative can coexist with one genuinely blank
            # grid cell.  In that case neither token count equals the template:
            # compare the identity-gated reconstructions and keep the unmasked
            # read only when it is strictly better.  Masked keeps every tie, so
            # established footnote handling is unchanged.
            masked_fit = _try_fit(masked, n_cols)
            unmasked_fit = _try_fit(unmasked, n_cols)
            if (unmasked_fit is not None
                    and (masked_fit is None
                         or _row_fit_residual(unmasked_fit, n_cols)
                         < _row_fit_residual(masked_fit, n_cols))):
                masked = unmasked
    return masked if len(masked) >= 2 else None


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
    # Match validator.check_equity_change exactly.  Using n_cols here gave a
    # 16-column row a tolerance of 48 while the stored row was rechecked with
    # 13 components (tolerance 39), so the extractor could knowingly emit a row
    # that validation rejected immediately.
    tol = max(len(components) * 3.0, abs(total) * 5e-5)
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


def _row_fit_residual(vals: list[float | None], n_cols: int) -> float:
    """Absolute identity error used only to choose between two gated reads."""
    total = vals[13]
    if total is None:
        return float("inf")
    residual = abs(sum(v for v in vals[:13] if v is not None) - total)
    if n_cols == 16 and vals[14] is not None and vals[15] is not None:
        residual += abs(total + vals[14] - vals[15])
    return residual


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
        if _row_gate(tokens, n_cols):
            return tokens
        if n_cols == 16 and all(v is not None for v in tokens[:13]):
            # A few consolidated filings carry a visibly clipped text-layer
            # token in total_equity while every component, minority interest,
            # and the grand total remains intact (TSKB 2024Q4 prints
            # ``8.647.3`` for 8,647,377).  Consolidated rows give us two
            # independent identities, so recover the damaged total only when
            # Σ(components) + minority == grand total.  This cannot run on a
            # 14-column row, where there is no independent grand-total check,
            # and it never changes a row that already passed the normal gate.
            inferred_total = sum(v for v in tokens[:13] if v is not None)
            minority, grand = tokens[14], tokens[15]
            if minority is not None and grand is not None:
                grand_tol = max(3.0, abs(grand) * 5e-5)
                if abs(inferred_total + minority - grand) <= grand_tol:
                    repaired = list(tokens)
                    repaired[13] = inferred_total
                    if _row_gate(repaired, n_cols):
                        return repaired
        return None
    if len(tokens) > n_cols:
        first = tokens[:n_cols]
        if _row_gate(first, n_cols):
            return first
        last = tokens[-n_cols:]
        if _row_gate(last, n_cols):
            return last
        return None
    if len(tokens) == n_cols - 1:
        # Preserve the positions already present whenever the identity cannot
        # distinguish several zero-insertion sites.  A missing/blank trailing
        # cell is common; inserting from the left instead shifted every real
        # value to its right (AKBNK's offsetting -46/+46 pair).
        for ins in range(n_cols - 1, -1, -1):
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
        for b in range(n_cols - 1, 0, -1):
            for a in range(b - 1, -1, -1):
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
        name = _mask_label_refs(m.group('rest')).strip()
        # Strip trailing numeric garbage
        name = _NUM_RX.sub('', name).rstrip('()-, ').strip()
        return h, name
    # Closing row: "Dönem Sonu Bakiyesi …" or "Closing Balance …"
    if _CLOSING_RX.search(stripped[:60]):
        name = _NUM_RX.sub('', _mask_label_refs(stripped)).rstrip('()-, ').strip()
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
                x1, text = w[2], w[4]
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


def _join_equity_words(words: list[tuple[float, float, str]]) -> str:
    """Join geometry-adjacent number fragments without merging separate cells."""
    joined: list[tuple[float, float, str]] = []
    for left, right, text in sorted(words):
        if joined:
            prev_left, prev_right, prev = joined[-1]
            gap = left - prev_right
            if (prev == '-' and re.fullmatch(r'\d[\d.,]*', text)
                    and 0 <= gap <= 2):
                # TSKB prints '- 33' with a 1.06pt gap; zero cells have ~26pt
                # before the next column. Text alone cannot distinguish them.
                joined[-1] = (prev_left, right, '-' + text)
                continue
            if 0 <= gap < 4 and (
                (re.fullmatch(r'\d{1,2}', prev) and re.match(r'^[.,\d]', text))
                or (prev[-1:].isdigit() and re.match(r'^[.,]\d', text))
            ):
                joined[-1] = (prev_left, right, prev + text)
                continue
        joined.append((left, right, text))
    return ' '.join(text for _, _, text in joined)


def _fitz_dense_page_lines(pdf_path: str, page_idx_0: int) -> list[str]:
    """An additional reconstruction for small-font equity matrices.

    FIBA's dash glyphs sit 3.8pt above the same row's figures. The shared 3pt
    bucketing splits row IV into two incomplete rows. A bounded 4pt bucket joins
    that row, while the next row begins more than 7pt later. This candidate is
    still subject to the same row and column-chain identities as other reads.
    """
    if not _HAS_FITZ:
        return []
    try:
        with _fitz.open(pdf_path) as doc:
            page = doc[page_idx_0]
            words = []
            for word in page.get_text('words'):
                rect = _fitz.Rect(word[:4])
                if page.rotation:
                    rect = rect * page.rotation_matrix
                    rect.normalize()
                words.append((rect.y0, rect.x0, rect.x1, word[4]))
        buckets: list[list[tuple[float, float, str]]] = []
        start_y = None
        for y, left, right, text in sorted(words):
            if start_y is None or y - start_y > 4:
                start_y = y
                buckets.append([])
            buckets[-1].append((left, right, text))
        return [_join_equity_words(row) for row in buckets]
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
_EQ_ADJUSTED_FORMULA_RX = re.compile(r'\(\s*I\s*\+\s*II\s*\)')
_EQ_CLIPPED_SUB_LABELS = (
    ('2.1', re.compile(r'^(?:Hatalar|Effects? of Errors?)', re.I)),
    ('2.2', re.compile(r'^(?:Muhasebe|Effects? of (?:the )?Changes? in Accounting)', re.I)),
    ('11.1', re.compile(r'^(?:Dağıtılan\s+Temettü|Dividends?)', re.I)),
    ('11.2', re.compile(r'^(?:Yedeklere|Transfers? to Reserves?)', re.I)),
    ('11.3', re.compile(r'^(?:Diğer|Diger|Other)\b', re.I)),
)
_EQ_CLIPPED_ROMAN_LABELS = (
    ('VI', re.compile(r'^(?:İç Kaynaklardan|Capital Increase by Internal Sources)', re.I)),
    ('VII', re.compile(r'^(?:Ödenmiş Sermaye Enflasyon|Effect of Inflation on Paid-in Capital)', re.I)),
    ('VIII', re.compile(r'^(?:Hisse Senedine Dönüştürülebilir|Convertible Bonds)', re.I)),
    ('XI', re.compile(r'^(?:K[aâ]r Dağıtımı|Profit Distribution)', re.I)),
)


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
# A NUMERIC sub-marker glued to its label with no separating dot at all —
# "2.1Hataların", "11.1Dağıtılan". AKBNK started typesetting this way in 2026Q1
# and its equity statement fell from 34 rows to 22: every 2.x and 11.x row lost
# its marker, and with no marker and no label they were skipped outright. Unlike
# the roman case this needs no trailing dot to be unambiguous — a digit pair
# followed directly by a letter is never a word.
_EQ_GLUED_NUM_RX = re.compile(r'^(\d{1,2}\.\d{1,2})(?=[^\W\d_])(.+)$')


def _eq_split(line: str) -> tuple[str | None, str]:
    """Return (marker, label) for an equity-table row, or (None, '') to skip.

    marker is the normalised BRSA marker ('VI.', '2.1', …) found among the first
    few whitespace tokens — even when footnote words precede it, and even when it
    is glued to its label. The closing row returns (None, <label>). Value
    extraction is unaffected: `_parse_row_tokens` finds the numeric tokens
    regardless of any leading words."""
    # The closing formula can carry a parenthesised dipnot marker immediately
    # before the values (VAKIFK: ``...+X+XI) (V) 30.000.000 ...``).  Scanning
    # the first six tokens first reads that note as row V., after which the
    # real row V wins duplicate removal and both closing balances disappear.
    # The formula reaching XI is unambiguous and, unlike the word "Bakiye",
    # cannot occur on the opening I. row, so give it priority over marker scan.
    if _EQ_CLOSING_FORMULA_RX.search(line[:100]):
        clean = _mask_label_refs(line)
        return None, _NUM_RX.sub('', clean).rstrip('()-, ').strip()

    # A clipped roman marker can turn III into II (ZIRAATK). The adjusted
    # balance's explicit I+II formula is unambiguous, just like the closing
    # formula above; preserve its figures and canonicalise only the marker.
    if (re.match(r'^II\.?\s+', line)
            and _EQ_ADJUSTED_FORMULA_RX.search(line[:100])
            and re.search(r'BAK[Iİ]YE|BALANCE', line[:100], re.I)):
        clean = _mask_label_refs(line)
        hier_m = _LINE_HIER_RX.match(clean)
        if hier_m:
            clean = clean[hier_m.end():]
        return 'III.', _NUM_RX.sub('', clean).rstrip('()-, ').strip()

    # The same clipped marker column can lose the last digit of 2.x / 11.x.
    # These five BRSA subrows have distinct labels. Resolve only those labels;
    # an unknown line must not be guessed into the next main roman instead.
    clipped = re.match(r'^(2|11)\.?\s+(.+)', line)
    if clipped:
        for marker, label_rx in _EQ_CLIPPED_SUB_LABELS:
            if marker.startswith(clipped[1] + '.') and label_rx.search(clipped[2]):
                clean = _mask_label_refs(clipped[2])
                return marker, _NUM_RX.sub('', clean).rstrip('()-, ').strip()

    toks = line.split()
    for i, tok in enumerate(toks[:6]):
        marker_core, rest = None, ''
        core = tok.strip('().,')
        if core in _EQ_MARKERS:                 # exact token: "VI." "2.1" "11.1"
            marker_core = core
        else:
            m = (_EQ_GLUED_RX.match(tok)         # glued: "VIII.Convertible"
                 or _EQ_GLUED_NUM_RX.match(tok))  # glued, no dot: "11.1Dağıtılan"
            if m and m.group(1) in _EQ_MARKERS:
                marker_core, rest = m.group(1), m.group(2)
        if marker_core is None:
            continue
        after = _mask_label_refs((rest + ' ' + ' '.join(toks[i + 1:])).strip())
        for canonical, label_rx in _EQ_CLIPPED_ROMAN_LABELS:
            if canonical.startswith(marker_core) and label_rx.search(after):
                marker_core = canonical
                break
        marker = marker_core + '.' if marker_core in _EQ_ROMANS else marker_core
        label = _NUM_RX.sub('', after).rstrip('()-, ').strip()
        return marker, label
    if _eq_is_closing(line):
        clean = _mask_label_refs(line)
        return None, _NUM_RX.sub('', clean).rstrip('()-, ').strip()
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
    lines = text.split('\n')
    close_i = next((i for i, ln in enumerate(lines)
                    if _EQ_CLOSING_FORMULA_RX.search(ln)), None)
    # Prefer the table's own short block header.  Some prior-first pages
    # (ANADOLU) print only "Önceki Dönem" above block 1 and "Cari Dönem" above
    # block 2; the only year on the page is the report-title year, so the old
    # latest-year heuristic defaulted to current and swapped every value.  Data
    # rows such as "I. Önceki Dönem Sonu Bakiyesi" are excluded by their wide
    # value grid.
    headers: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        kind = _period_header(line)
        if kind:
            headers.append((i, kind))
    if headers:
        # When both headings are present they directly establish block order.
        # ANADOLU's first closing row loses its label in the text layer, leaving
        # only the SECOND closing formula. Taking the last heading before that
        # formula incorrectly reverses the two complete tables.
        if len({kind for _, kind in headers}) == 2:
            return headers[0][1]
        if close_i is None:
            return headers[0][1]
        before = [kind for i, kind in headers if i < close_i]
        if before:
            return before[-1]
        after = [kind for i, kind in headers if i > close_i]
        if after:
            return 'prior' if after[0] == 'current' else 'current'

    years = [int(m.group(1)) for m in _YEAR_RX.finditer(text)]
    if not years or close_i is None:
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


def _restore_equity_source_labels(
    rows: list[EquityChangeRow], recons: list[list[str]],
) -> list[EquityChangeRow]:
    """Restore wrapped metadata only when every printed value already matches.

    Some reconstructions retain a row's values but strand its label above it
    (HALKB/TSKB II, SKBNK III, VAKBN 11.2). The source marker plus the complete
    14/16-cell vector proves which existing row the text belongs to. This does
    not insert cells, change figures, or guess metadata for an unknown row.
    """
    fields = (
        'paid_in_capital', 'share_premium', 'share_cancellation_profits',
        'other_capital_reserves', 'oci_not_reclassified_1',
        'oci_not_reclassified_2', 'oci_not_reclassified_3',
        'oci_reclassified_1', 'oci_reclassified_2', 'oci_reclassified_3',
        'profit_reserves', 'prior_period_profit_loss', 'period_net_profit_loss',
        'total_equity', 'minority_interest', 'total_equity_incl_minority',
    )
    evidence: dict[tuple, set[str]] = {}
    widths = {16 if row.total_equity_incl_minority is not None else 14 for row in rows}
    for lines in recons:
        for index, line in enumerate(lines):
            prefix: list[str] = []
            for previous in reversed(lines[max(0, index - 3):index]):
                if _count_value_tokens(previous) >= 10:
                    break
                prefix.insert(0, previous)
            for source in (line, ' '.join([*prefix, line])):
                marker, name = _eq_split(source)
                if not marker or not name:
                    continue
                # _eq_split masks standards citations along with value tokens.
                # Here the value boundary is known, so retain the literal label
                # (including TAS 8 and a complete I+II formula) from the source.
                region = _value_region(source)
                offset = _mask_label_refs(source).find(region) if region else -1
                source_label = source[:offset].strip() if offset >= 0 else ''
                label_match = re.match(
                    r'^(?:[IVX]{1,5}\.|\d{1,2}\.\d{1,2}\.?)\s*(.+)$', source_label)
                if label_match:
                    name = label_match[1].strip()
                for width in widths:
                    values = _parse_row_tokens(source, width)
                    if values is not None and len(values) == width and all(
                            value is not None for value in values):
                        evidence.setdefault((marker, tuple(values)), set()).add(name)

    restored = list(rows)
    for index, row in enumerate(rows):
        if row.name:
            continue
        marker = row.hierarchy
        if not marker and 0 < index < len(rows) - 1:
            # A markerless 11.2 can have exactly the same values as its parent
            # XI. Only its two retained sibling markers distinguish the row.
            previous, following = rows[index - 1].hierarchy, rows[index + 1].hierarchy
            if previous == '11.1' and following == '11.3':
                marker = '11.2'
        if not marker:
            continue
        width = 16 if row.total_equity_incl_minority is not None else 14
        values = tuple(getattr(row, field) for field in fields[:width])
        names = evidence.get((marker, values), set())
        # A shorter reconstruction may have retained only part of the label.
        # Accept a unique full source label; conflicting labels stay untouched.
        complete = {name for name in names if not any(
            name != other and name in other for other in names)}
        if len(complete) == 1:
            restored[index] = replace(row, hierarchy=marker, name=complete.pop())
    return restored


def _fitz_wrapped_digit_page_lines(pdf_path: str, page_idx_0: int) -> list[str]:
    """Join a thousands-group digit wrapped immediately below its own cell.

    TSKB prints ``2.071.47`` above ``7`` in a narrow revaluation column. Both
    glyph runs are visible, their right edges align, and their boxes almost
    touch vertically. Require a unique physical pair; the caller additionally
    admits this reconstruction only when the statement's identities close.
    """
    if not _HAS_FITZ:
        return []
    try:
        with _fitz.open(pdf_path) as doc:
            page = doc[page_idx_0]
            words = []
            for word in page.get_text('words'):
                rect = _fitz.Rect(word[:4]) * page.rotation_matrix
                words.append([rect.x0, rect.y0, rect.x1, rect.y1, word[4]])
    except Exception:
        return []
    pairs: list[tuple[int, int]] = []
    for index, word in enumerate(words):
        partial = re.fullmatch(r'\d{1,3}([.,])(?:\d{3}\1)*(\d{1,2})', word[4])
        if partial is None:
            continue
        needed = 3 - len(partial[2])
        tails = [i for i, tail in enumerate(words)
                 if re.fullmatch(r'\d{' + str(needed) + '}', tail[4])
                 and 0 <= tail[1] - word[3] <= 1
                 and abs(tail[2] - word[2]) <= 1]
        if len(tails) > 1:
            return []
        if tails:
            pairs.append((index, tails[0]))
    if not pairs or len({tail for _, tail in pairs}) != len(pairs):
        return []
    removed = set()
    for head, tail in pairs:
        words[tail][4] = words[head][4] + words[tail][4]
        removed.add(head)
    buckets: list[list[tuple[float, float, str]]] = []
    last_y = 0.0
    for index, word in sorted(enumerate(words), key=lambda item: (item[1][1], item[1][0])):
        if index in removed:
            continue
        item = (word[0], word[2], word[4])
        if buckets and word[1] - last_y <= 3:
            buckets[-1].append(item)
        else:
            buckets.append([item])
            last_y = word[1]
    return [_join_equity_words(bucket) for bucket in buckets]


def _sparse_grid_closes(rows: list[tuple[str, list[float | None]]]) -> bool:
    """Require exact source identities before admitting a sparse PDF grid.

    Blank positions stay None. Summing the printed operands can establish the
    table's alignment, but must never manufacture a zero disclosure in them.
    Unlike the ordinary parser, this recovery has no rounding allowance.
    """
    starts = [i for i, (label, _) in enumerate(rows) if _eq_split(label)[0] == 'I.']
    if len(starts) != 2:
        return False
    for start, end in zip(starts, starts[1:] + [len(rows)]):
        block = rows[start:end]
        marked = [(_eq_split(label)[0], values) for label, values in block]
        by_marker = {marker: values for marker, values in marked if marker}
        if len(by_marker) != sum(marker is not None for marker, _ in marked):
            return False
        closing = [values for (label, values), (marker, _) in zip(block, marked)
                   if marker is None and _eq_is_closing(label)]
        if (len(block) < 8 or len(closing) != 1
                or not {'I.', 'III.', 'IV.', 'XI.'} <= by_marker.keys()
                or any(value is None for value in closing[0])):
            return False
        for marker, values in marked:
            if len(values) != 16:
                return False
            total = values[13]
            components = sum(value for value in values[:13] if value is not None)
            if total is None:
                # A reserve transfer may print only equal, opposite components.
                # Keep its undisclosed total null; no other missing-total row
                # has enough evidence to admit through this fallback.
                if marker != '11.2' or components != 0:
                    return False
            elif components != total:
                return False
            if values[15] is not None and (total is None
                    or total + (values[14] or 0) != values[15]):
                return False
        for col in range(16):
            opening = by_marker['I.'][col]
            adjusted = by_marker['III.'][col]
            correction = by_marker.get('II.', [None] * 16)[col]
            if (opening or 0) + (correction or 0) != (adjusted or 0):
                return False
            printed_sum = sum(by_marker[marker][col] or 0 for marker in _EQ_ROW_SEQ[2:]
                              if marker in by_marker)
            if printed_sum != closing[0][col]:
                return False
    return True


def _fitz_sparse_page_grid(pdf_path: str, page_idx_0: int
                           ) -> tuple[list[str], dict[int, list[float | None]]] | None:
    """Read sparse 16-column tables using two complete closing rows as anchors.

    ISCTR leaves unused cells physically blank, so a positional token list loses
    their column positions. Two independently footing closing rows must expose
    all 16 aligned column edges. Every other printed number must align uniquely
    with one edge, and both blocks must reconcile in every component column.
    This fallback neither guesses a missing amount nor fills a blank with zero.
    """
    if not _HAS_FITZ:
        return None
    try:
        with _fitz.open(pdf_path) as doc:
            page = doc[page_idx_0]
            words = []
            for word in page.get_text('words'):
                rect = _fitz.Rect(word[:4]) * page.rotation_matrix
                words.append((rect.x0, rect.y0, rect.x1, word[4]))
    except Exception:
        return None
    buckets: list[list[tuple[float, float, float, str]]] = []
    for word in sorted(words, key=lambda value: (value[1], value[0])):
        if buckets and abs(word[1] - buckets[-1][0][1]) < 1.5:
            buckets[-1].append(word)
        else:
            buckets.append([word])
    for bucket in buckets:
        bucket.sort(key=lambda value: value[0])
    lines = [' '.join(word[3] for word in bucket) for bucket in buckets]
    anchors = []
    for line, bucket in zip(lines, buckets):
        marker, name = _eq_split(line)
        if marker is not None or not name or not _eq_is_closing(line):
            continue
        numeric = [word for word in bucket if _NUM_RX.fullmatch(word[3])]
        if len(numeric) == 16:
            values = [parse_num(word[3]) for word in numeric]
            if (all(value is not None for value in values)
                    and _row_fit_residual(values, 16) == 0):
                anchors.append([word[2] for word in numeric])
    if len(anchors) != 2 or any(abs(a - b) > 1 for a, b in zip(*anchors)):
        return None
    edges = anchors[0]
    if min(b - a for a, b in zip(edges, edges[1:])) < 8:
        return None
    grid: dict[int, list[float | None]] = {}
    source_rows = []
    inside_block = False
    for index, (line, bucket) in enumerate(zip(lines, buckets)):
        marker, name = _eq_split(line)
        if marker == 'I.':
            inside_block = True
        if marker is None and not (name and _eq_is_closing(line)):
            # Unknown movements can cancel each other in every identity.
            # Never omit a numeric source row inside an admitted period block.
            if inside_block and any(_NUM_RX.fullmatch(word[3]) for word in bucket):
                return None
            continue
        prefix = ' '.join(word[3] for word in bucket if word[2] < edges[0] - 2)
        prefix = re.sub(r'^(?:[IVX]{1,5}\.?(?=\s)|\d{1,2}\.\d{1,2}\.?)\s*',
                        '', _mask_label_refs(prefix))
        # A misaligned first-column zero cannot be silently treated as label
        # text: it would disappear without disturbing any arithmetic identity.
        # Only known label references and the row marker may contain numbers.
        if _NUM_RX.search(prefix):
            return None
        values: list[float | None] = [None] * 16
        for word in bucket:
            if word[2] < edges[0] - 2:
                continue
            if not _NUM_RX.fullmatch(word[3]):
                return None
            column = min(range(16), key=lambda i: abs(edges[i] - word[2]))
            value = parse_num(word[3])
            if (abs(edges[column] - word[2]) > 1 or values[column] is not None
                    or value is None):
                return None
            values[column] = value
        if any(value is not None for value in values):
            grid[index] = values
            source_rows.append((line, values))
        if marker is None:
            inside_block = False
    if not _sparse_grid_closes(source_rows):
        return None
    return lines, grid


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

    def _parse_with(lines: list[str], nc: int,
                    grid: dict[int, list[float | None]] | None = None
                    ) -> list[EquityChangeRow]:
        result: list[EquityChangeRow] = []
        order = 0
        last_ri = -1            # index in _EQ_ROW_SEQ of the last main roman seen
        stranded = ''           # label left over from the previous row's line
        closing_taken = False   # at most one label-less closing row per block
        source_line = 0
        dated_values = None
        pending_opening = None
        zero_adjustment = False
        opening_candidates = []
        for line_index, line in enumerate(lines):
            if grid is not None and line_index not in grid:
                continue
            line = line.strip()
            if not line:
                continue
            source_line += 1
            marker, name = _eq_split(line)
            years = list(_YEAR_RX.finditer(line))
            date_range_values = (line[years[1].end():]
                                 if marker is None and not name and len(years) >= 2
                                 and years[1].end() <= 60 else None)
            tokens = (grid[line_index] if grid is not None
                      else _parse_row_tokens(date_range_values or line, nc))
            if tokens is None:
                # ANADOLU prints the closing label on its own line, followed
                # by a date and the complete values. Keep that label attached
                # to the next otherwise-unlabelled closing row.
                if marker is None and name and _eq_is_closing(line):
                    stranded = name
                continue
            fitted = tokens if grid is not None else _try_fit(tokens, nc)
            if fitted is None:
                continue
            # TAKAS prints its opening values on the date-range line directly
            # above the I label. Retain that complete, exactly-footing source
            # row for a later component-by-component match to III. A single
            # dated closing row (ANADOLU) is not a date range.
            if (date_range_values is not None and len(tokens) >= nc
                    and all(value is not None for value in fitted)
                    and fitted[0] > 0 and _row_fit_residual(fitted, nc) == 0):
                dated_values = (source_line, fitted)
                continue
            # Checklist walk: a wide data row that fits but carries no marker AND no
            # label is a row whose marker the text layer dropped (GARAN prints its
            # current-period IV. "Total Comprehensive Income" as values only). The
            # row order is fixed, so it must be the next main roman after the last
            # one seen. (The closing row is excluded — it returns a non-empty label.)
            if marker is None and not name and 0 <= last_ri < len(_EQ_ROW_SEQ) - 1:
                marker = _EQ_ROW_SEQ[last_ri + 1]
            if marker is None and not name:
                # Past XI the standard table has exactly one row left: the
                # closing balance. AKBNK's arrives markerless AND nameless
                # because the bucketing stranded "Dönem Sonu" on the 11.3 line,
                # and dropping it costs the BS cross-check, the paid-in-capital
                # check and both column chains. The row-sum gate has already
                # admitted the values; take the stranded label as its name
                # rather than inventing one.
                if last_ri == len(_EQ_ROW_SEQ) - 1 and not closing_taken:
                    closing_taken = True
                    name = stranded
                else:
                    stranded = _trailing_text(line)
                    continue
            if marker in _EQ_ROW_SEQ:        # reset on each block (second I. → 0)
                last_ri = _EQ_ROW_SEQ.index(marker)
                if marker == 'I.':
                    closing_taken = False
                    stranded = ''
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
            if marker == 'I.':
                pending_opening = None
                zero_adjustment = False
                if (dated_values and dated_values[0] == source_line - 1
                        and all(value == 0 for value in cols)):
                    pending_opening = (len(result), dated_values[1])
                dated_values = None
            elif marker == 'II.':
                zero_adjustment = all(value == 0 for value in cols)
            elif marker == 'III.' and pending_opening:
                opening_index, header_cols = pending_opening
                if zero_adjustment and cols == header_cols:
                    original = result[opening_index]
                    opening_candidates.append((opening_index, replace(
                        row, order=original.order, hierarchy=original.hierarchy,
                        name=original.name)))
                pending_opening = None
            stranded = _trailing_text(line)
            result.append(row)
        for opening_index, replacement in opening_candidates:
            end = next((i for i in range(opening_index + 1, len(result))
                        if result[i].hierarchy == 'I.'), len(result))
            block = [replacement] + result[opening_index + 1:end]
            # Do not apply a label-placement recovery to an incomplete or
            # inconsistent table. No value is inferred or rounded here.
            if _eq_chain_closes(_eq_score_dicts(block)):
                result[opening_index] = replacement
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
    # Only expand the geometry search when neither established reconstruction
    # closes the statement. In particular, keep already valid page reads stable.
    if not any(_eq_candidate_score(c)[0] == 1 for c in candidates):
        dense_lines = _fitz_dense_page_lines(pdf_path, page_idx_1 - 1)
        if dense_lines:
            recons.append(dense_lines)
            candidates.append(_parse_with(dense_lines, n_cols))
    if not any(_eq_candidate_score(c)[0] == 1 for c in candidates):
        wrapped_lines = _fitz_wrapped_digit_page_lines(pdf_path, page_idx_1 - 1)
        if wrapped_lines:
            # Preserve the established template, including minority columns.
            # Repair the visible glyph before considering a different width.
            wrapped = _parse_with(wrapped_lines, n_cols)
            if _eq_candidate_score(wrapped)[0] == 1:
                recons.append(wrapped_lines)
                candidates.append(wrapped)

    # Self-gated both-template search: if NO candidate's column chain validates at
    # the detected n_cols, the template may be wrong for this bank — also parse each
    # reconstruction with the OTHER template (14↔16) and let the scorer pick. This
    # runs ONLY for partitions that don't already validate, so it can't touch the
    # clean set; it can only turn a chain-failure into a chain-closing parse.
    if not any(_eq_candidate_score(c)[0] == 1 for c in candidates):
        other = 16 if n_cols == 14 else 14
        candidates += [_parse_with(lines, other) for lines in recons]

    if not any(_eq_candidate_score(c)[0] == 1 for c in candidates):
        sparse = _fitz_sparse_page_grid(pdf_path, page_idx_1 - 1)
        if sparse is not None:
            lines, grid = sparse
            candidates.append(_parse_with(lines, 16, grid))

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
        # Explicit, distinct block headings take precedence over a coincidental
        # equality between a closing balance and the next opening balance.
        # Keep the value-based fallback for pages whose headers are unreadable.
        header_orders = set()
        for lines in recons:
            headings = tuple(kind for line in lines if (kind := _period_header(line)))
            if len(headings) == 2 and headings[0] != headings[1]:
                header_orders.add(headings)
        c1 = best[split_idx].total_equity
        o2 = best[split_idx + 1].total_equity if split_idx + 1 < len(best) else None
        if len(header_orders) == 1:
            block1 = next(iter(header_orders))[0]
        elif c1 and o2 is not None and abs(c1 - o2) <= abs(c1) * 1e-4:
            block1 = 'prior'
        else:
            block1 = _block1_period_for_split(pdf_path, page_idx_1)
        block2 = 'prior' if block1 == 'current' else 'current'
        for r in best[:split_idx + 1]:
            r.period_type = block1
        for r in best[split_idx + 1:]:
            r.period_type = block2
    # Drop spurious positional-inference roman duplicates and renumber.
    return _restore_equity_source_labels(_dedup_roman_rows(best), recons)


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
        block_headers = [kind for line in ptext.splitlines()
                         if (kind := _period_header(line))]
        if block_headers:
            period_type = block_headers[0]
        elif _CURRENT_RX.search(ptext):
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
    # Corrupted/image-only guard: a letter-spacing-corrupted text layer (ISCTR's
    # image-only quarters) yields only a handful of partial rows — opening /
    # new-balance / closing, with the IV-XI movement rows lost — that pass the
    # row-gate but form an INCOMPLETE statement. Emitting them is worse than
    # nothing: it flips a sparse-"passing" (all-checks-skip) partition into
    # partial-failing. A complete statement (even a failing one) carries ≥22 rows
    # across its two periods; the broken parses top out at 9, so <14 is always a
    # corrupted/incomplete parse — drop it so the partition stays empty/skip.
    if 0 < len(rep.rows) < 14:
        rep.rows = []
    return rep


def upsert(conn: sqlite3.Connection, bank: str, period: str,
           kind: str, report: EquityChangeReport, *, unit: UnitContext) -> int:
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
        unit.scale_rows(
            "bank_audit_equity_change",
            ["bank_ticker", "period", "kind", "period_type", "item_order",
             "hierarchy", "item_name",
             "paid_in_capital", "share_premium", "share_cancellation_profits",
             "other_capital_reserves",
             "oci_not_reclassified_1", "oci_not_reclassified_2",
             "oci_not_reclassified_3",
             "oci_reclassified_1", "oci_reclassified_2", "oci_reclassified_3",
             "profit_reserves", "prior_period_profit_loss",
             "period_net_profit_loss", "total_equity", "minority_interest",
             "total_equity_incl_minority", "source_page"],
            [(bank, period, kind, r.period_type, r.order, r.hierarchy, r.name,
              r.paid_in_capital, r.share_premium, r.share_cancellation_profits,
              r.other_capital_reserves,
              r.oci_not_reclassified_1, r.oci_not_reclassified_2,
              r.oci_not_reclassified_3,
              r.oci_reclassified_1, r.oci_reclassified_2, r.oci_reclassified_3,
              r.profit_reserves, r.prior_period_profit_loss,
              r.period_net_profit_loss,
              r.total_equity, r.minority_interest, r.total_equity_incl_minority,
              r.source_page)
             for r in deduped]),
    )
    return len(deduped)
