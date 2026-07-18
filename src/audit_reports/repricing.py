"""Interest-rate repricing-gap extractor — BRSA §4 "Interest-rate risk" footnote.

Most BRSA audit reports (~81% of the corpus; participation banks word it as
profit-share-rate risk and often omit it) carry an interest-rate sensitivity
table laying assets/liabilities out by repricing bucket:

    Cari Dönem   1 Aya Kadar  1-3 Ay  3-12 Ay  1-5 Yıl  5 Yıl ve Üzeri  Faizsiz  Toplam
    Toplam Varlıklar   890,697,566  268,437,220  467,986,977  331,343,904  133,594,673  423,536,314  2,515,596,654
    Toplam Yükümlülükler ...
    Toplam Pozisyon   (118,680,506) (57,142,966) 177,037,251 291,530,881 64,907,609 (331,627,652) 26,024,617

A "Prior Period" block (usually the next page) repeats the table. English and
Turkish; the standard template has 5 maturity buckets + a non-interest-bearing
("Faizsiz" / "Non-Interest Bearing") column + Total = 7 columns.

We keep only the three summary rows — total assets (rate-sensitive assets),
total liabilities (rate-sensitive liabilities), and total position (the gap,
which nets on- and off-balance positions) — read as the trailing N values in
bucket order. The 1-year cumulative gap is derived. Banks whose table isn't the
standard 7-column shape (some participation banks, image-only quarters) are left
to the validated N/A tail. Footing identities are checked in validator.py.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from .extractor import _HAS_FITZ, parse_num

# fitz-only: the §4 interest-rate-risk table is a single narrow footnote — fitz
# word clustering reads it faithfully and is far cheaper than pdfplumber per page,
# which adds no accuracy here (per the project's per-statement engine strategy).

_NUM_TOKEN = re.compile(r"^%?\(?-?\d[\d.,]*%?\)?$")
_NIL = {"-", "—", "–", "--", "---"}

# Standard 7-column bucket order (5 maturity + non-interest + total). Buckets
# ≤1y are the first three (used for the 1y cumulative gap).
_BUCKETS_7 = ["lt_1m", "1_3m", "3_12m", "1_5y", "gt_5y", "non_sensitive", "total"]
_LE_1Y = {"lt_1m", "1_3m", "3_12m"}

_ROWS: list[tuple[str, list[str]]] = [
    ("rate_sensitive_assets", [r"^Total\s+assets\b", r"^Toplam\s+Varlıklar\b", r"^Toplam\s+Aktifler\b"]),
    # `Liab[a-z]+` tolerates the QNBFB template's misspelling "Total Liabalities".
    ("rate_sensitive_liab", [r"^Total\s+Liab[a-z]+\b", r"^Toplam\s+Yükümlülükler\b"]),
    # The reported total repricing gap row (on + off balance). `Net\s+Pozisyon`
    # (re.I) catches TAKAS's Turkish "Net pozisyon" — without it the table locator
    # never fired and all 16 TAKAS quarters read as missing.
    ("gap", [r"^Total\s+position\b", r"^Toplam\s+Pozisyon\b",
             r"^Net\s+position\b", r"^Net\s+Pozisyon\b"]),
]
_ROW_RX = [(f, [re.compile(p, re.I) for p in pats]) for f, pats in _ROWS]
# A footnote reference — a parenthesised 1–2-digit integer with NO thousands/
# decimal separator ("(1)", "(5)"). It matches _NUM_TOKEN and so leaked into the
# value stream, inflating the column count (ZIRAAT/KLNMA/ZIRAATD locked ncols too
# high → the b1..b8 fallback → the liabilities/position rows, one marker short,
# were dropped). A genuine parenthesised negative always carries a separator
# ("(682.431)"), so it is never caught here.
_MARKER_RX = re.compile(r"^\(\d{1,2}\)$")

_PRIOR_RX = re.compile(r"\b(Prior\s+Period|Önceki\s+Dönem|Geçmiş\s+Dönem)\b", re.I)
# Bucket-header signal: a non-interest / non-rate-sensitive column ("Faizsiz" /
# "Non-interest bearing") next to a Total — distinguishes the repricing table
# from the FX one. English convenience translations vary the word order
# ("Non-bearing interest" — Halkbank — vs "Non-interest bearing") and Turkish
# filings vary the phrase ("Faizsiz" / "Faiz Getirmeyen"), so match the whole
# family rather than one fixed order (a fixed "Non-Interest" missed HALKB
# entirely — all 17 quarters — because "bearing" sits between the two words).
_NONINT_RX = re.compile(
    r"(Faizsiz"
    r"|Faiz\s*(?:Getirmeyen|İçermeyen|Taşımayan)"
    r"|Non[\s-]*(?:Interest|Bearing)"
    r"|Interest[\s-]*Free)",
    re.I,
)
_SKIP_PAGES = 20
_MAX_SECTION_PAGES = 6


@dataclass
class RepricingRow:
    period_type: str   # 'current' | 'prior'
    bucket: str        # lt_1m | 1_3m | 3_12m | 1_5y | gt_5y | non_sensitive | total
    rate_sensitive_assets: float | None = None
    rate_sensitive_liab: float | None = None
    gap: float | None = None
    cumulative_gap: float | None = None


@dataclass
class RepricingReport:
    pdf_path: str = ""
    source_page: int | None = None
    rows: list[RepricingRow] = field(default_factory=list)


def _fitz_word_lines(pdf_path: str):
    """Word-lines per page. A token is (x0, x1, text): the right edge is kept
    because bucket columns are right-aligned, so x1 is what identifies the
    column a cell sits under when a row can't be read by token count alone."""
    import fitz
    doc = fitz.open(pdf_path)
    pages = []
    for i in range(len(doc)):
        words = doc[i].get_text("words")
        rows = []
        for w in sorted(words, key=lambda w: (w[1], w[0])):
            if rows and w[1] - rows[-1][0] <= 3.0:
                rows[-1][1].append((w[0], w[2], w[4]))
            else:
                rows.append((w[1], [(w[0], w[2], w[4])]))
        pages.append([sorted(toks) for _, toks in rows])
    return pages, doc


def _label(tokens) -> str:
    return " ".join(t[-1] for t in tokens).strip()


def _unglue(tok: str) -> list[str]:
    """Split two grouped integers fused with no space (fitz joins tight columns —
    HALKB's Faizsiz|Total: "701.658.8113.362.509.545"). A correctly formatted value
    has strictly 3-digit interior groups, so an interior group with >3 digits is a
    boundary: cut after its first 3 digits. Safe — no legitimate value has one."""
    m = re.match(r"^(-?)(\d[\d.,]*\d)$", tok)
    if not m:
        return [tok]
    neg, body = m.group(1), m.group(2)
    groups = re.split(r"([.,])", body)          # ['701','.','658','.','8113',...]
    for k, gi in enumerate(range(0, len(groups), 2)):
        if k > 0 and len(groups[gi]) > 3:
            first = neg + "".join(groups[:gi]) + groups[gi][:3]
            second = groups[gi][3:] + "".join(groups[gi + 1:])
            return [first, second]
    return [tok]


def _destray(tok: str) -> str | None:
    """Recover a numeric cell with ONE stray alpha glyph fused to it — TAKAS
    2023Q3 prints the Faizsiz total assets as '3,768,782f'. The token fails
    _NUM_TOKEN, so it was dropped, the assets row came out one value short, and
    ncols locked at 6 — which then rejected every 7-value row below it.

    Strip a single leading/trailing ASCII letter iff what remains is a grouped
    number. Requiring a thousands/decimal separator is what keeps this safe: a
    real label never survives it, and neither does a bare 'digit+letter'."""
    for core, dropped in ((tok[:-1], tok[-1:]), (tok[1:], tok[:1])):
        if (len(dropped) == 1 and dropped.isascii() and dropped.isalpha()
                and ("," in core or "." in core) and _NUM_TOKEN.match(core)):
            return core
    return None


def _value_tokens(tokens) -> list[str]:
    out: list[str] = []
    for tok in tokens:
        t = tok[-1]
        if _MARKER_RX.match(t):               # footnote ref, not a value
            continue
        if t in _NIL or _NUM_TOKEN.match(t):
            out.extend(_unglue(t))
            continue
        core = _destray(t)
        if core is not None:
            out.extend(_unglue(core))
    return out


def _is_value_line(tokens) -> bool:
    """True if every token on the line is a value (or a footnote marker) and at
    least one is — i.e. a continuation line carrying figures but no label."""
    seen = 0
    for tok in tokens:
        t = tok[-1]
        if _MARKER_RX.match(t):
            continue
        if t in _NIL or _NUM_TOKEN.match(t) or _destray(t) is not None:
            seen += 1
        else:
            return False
    return seen > 0


def _x_columns(window):
    """Group the tokens of a few consecutive word-lines into vertically aligned
    columns by x-interval overlap. Each column comes back as
    [(line_offset, x0, text), ...] in reading order, so a header cell that wraps
    over several rows is reassembled into one string."""
    items = [(li, x0, x1, t)
             for li, ln in enumerate(window) for (x0, x1, t) in ln]
    items.sort(key=lambda it: it[1])
    cols: list[list] = []                      # [lo, hi, [(line, x0, text)…]]
    for li, x0, x1, t in items:
        for c in cols:
            if x0 <= c[1] and c[0] <= x1:      # x-intervals overlap
                c[0], c[1] = min(c[0], x0), max(c[1], x1)
                c[2].append((li, x0, t))
                break
        else:
            cols.append([x0, x1, [(li, x0, t)]])
    return [sorted(c[2]) for c in cols]


def _nonint_line(lines) -> int | None:
    """Index of the line carrying the non-interest bucket header, else None.

    Nearly every filing prints it on one word-line. COLENDI's English template
    stacks it vertically across three header rows ('Non-' / 'Interest' /
    'Bearing'), one fragment per row, so no single line matches and the whole
    table was missed — three quarters read as having no repricing schedule at
    all. Falling back to the x-aligned column reconstruction rebuilds the cell
    and matches it there. The caller still demands the gap row on the same page,
    so this stays pinned to the repricing ladder and can't latch onto prose.

    Returns the LAST line of a wrapped header, so the caller can treat anything
    above it as belonging to a different table."""
    for j, toks in enumerate(lines):
        if _NONINT_RX.search(_label(toks)):
            return j
    for j in range(len(lines) - 1):
        window = lines[j:j + 3]
        if len(window) < 2:
            break
        for col in _x_columns(window):
            if len({li for li, _, _ in col}) < 2:   # must genuinely wrap
                continue
            if _NONINT_RX.search(" ".join(t for _, _, t in col)):
                return j + max(li for li, _, _ in col)
    return None


def _col_anchors(tokens, ncols) -> list[float] | None:
    """Right-edge x of each bucket column, read off one fully-populated row.
    Trusted only when the row holds exactly one raw token per column — if any
    cell had to be unglued or de-strayed the anchors no longer line up 1:1 with
    the buckets, so we return None and the column fallback stays switched off."""
    xs = [x1 for (_, x1, t) in tokens
          if not _MARKER_RX.match(t) and (t in _NIL or _NUM_TOKEN.match(t))]
    return xs if len(xs) == ncols else None


def _page_anchors(lines, ncols, first=0) -> list[float] | None:
    """Bucket-column right edges for ONE page, off its first complete row.

    Anchors must be read from the page being parsed rather than carried across
    the section: ICBCT's prior-period table is laid out some 30pt to the right
    of its current-period one, so page-1 anchors land between page-2 columns."""
    for toks in lines[first:]:
        xs = _col_anchors(toks, ncols)
        if xs:
            return xs
    return None


def _row_by_columns(lines, j, col_x, ncols) -> list[str] | None:
    """Rebuild a summary row that doesn't come out as ncols tokens on one line,
    by mapping each value to the bucket column it physically sits under.

    Two real layouts need this. A cell can be genuinely BLANK — ZIRAATD 2025Q4
    prints nothing under '5 Yıl ve Üzeri', not even a dash, leaving the position
    row one token short and positionally ambiguous without x. Or a cell's text
    can wrap onto its own line and shove the label down with it — EXIM 2025Q3
    breaks '(111.782.553)' into '(111.782.55' and '3)' three lines apart, so the
    label line carries no usable figures and the line above holds only six.

    Tokens are gathered from the label line plus the run of pure-value lines
    directly above and below it, snapped to the nearest column anchor, and
    fragments landing in the same column are rejoined in reading order; a column
    with no token reads as nil. The row is accepted only if every token found a
    column, at most one column is empty, and the values FOOT — that footing test
    is what makes this an alignment rather than a guess."""
    if not col_x or len(col_x) != ncols or ncols < 3:
        return None
    span = [(0, lines[j])]
    for step in (-1, 1):                       # walk out over value-only lines
        k = j + step
        while 0 <= k < len(lines) and abs(k - j) <= 3 and _is_value_line(lines[k]):
            span.append((k - j, lines[k]))
            k += step
    items = [(order, x0, x1, t)
             for order, ln in span for (x0, x1, t) in ln
             if not _MARKER_RX.match(t)
             and (t in _NIL or _NUM_TOKEN.match(t) or _destray(t) is not None)]
    if len(items) < ncols - 1:
        return None
    tol = 0.5 * min(abs(col_x[i + 1] - col_x[i]) for i in range(ncols - 1))
    slots: list[list] = [[] for _ in col_x]
    for order, x0, x1, t in items:
        dist, ci = min((abs(x1 - cx), ci) for ci, cx in enumerate(col_x))
        if dist > tol:
            return None                        # orphan token — refuse to guess
        slots[ci].append((order, x0, t))
    if sum(1 for s in slots if not s) > 1 or not slots[-1]:
        return None
    vals = ["".join(t for _, _, t in sorted(s)) if s else "-" for s in slots]
    nums = [parse_num(v) for v in vals]
    if any(v is None for v in nums) or abs(sum(nums[:-1]) - nums[-1]) > 1.0:
        return None
    return vals


def extract_from_pdf(pdf: object = None, pdf_path: str = "") -> RepricingReport:
    # `pdf` (a pdfplumber handle) is accepted for signature parity with the audit
    # lane but unused — parsing is fitz-only via pdf_path.
    rep = RepricingReport(pdf_path=pdf_path)
    if not pdf_path or not _HAS_FITZ:
        return rep
    pages, doc = _fitz_word_lines(pdf_path)
    try:
        n = len(pages)
        _gap_rx = _ROW_RX[2][1]
        _assets_rx = _ROW_RX[0][1]
        # Locate the IR table: a page with the gap row AND a non-interest bucket
        # header (the gap row alone could be a different table; the Faizsiz/
        # Non-Interest header pins it to the repricing schedule).
        start = header_j = None
        for i in range(min(_SKIP_PAGES, n), n):
            lns = pages[i]
            has_gap = any(any(rx.match(_label(t)) for rx in _gap_rx) for t in lns)
            if not has_gap:
                continue
            nonint_j = _nonint_line(lns)
            if nonint_j is not None:
                start, header_j = i, nonint_j
                break
        if start is None:
            return rep
        rep.source_page = start + 1
        # Anything above the non-interest header on the first page belongs to a
        # different table. The currency-risk ladder often ends on this page, and
        # its prior-period "Toplam varlıklar" — four columns wide (EUR/USD/other/
        # total) — was being met first and locking ncols=4, after which every
        # 7-column repricing row was rejected (TAKAS 2023Q1). Only gate when a
        # real assets row actually follows the header, so that a filing whose
        # only Faizsiz mention is a footnote UNDER the table is left untouched.
        if header_j is not None and not any(
                any(rx.match(_label(t)) for rx in _assets_rx)
                for t in pages[start][header_j + 1:]):
            header_j = None

        ncols: int | None = None     # number of bucket columns incl. total
        data: dict[tuple[str, str], dict[str, float | None]] = {}
        period = "current"
        for i in range(start, min(n, start + _MAX_SECTION_PAGES)):
            lines = pages[i]
            gate = header_j + 1 if (i == start and header_j is not None) else 0
            col_x: list[float] | None = None   # bucket column edges, THIS page
            col_x_tried = False
            for j, tokens in enumerate(lines):
                if i == start and header_j is not None and j < header_j:
                    continue                 # above the header ⇒ another table
                lab = _label(tokens)
                if not lab:
                    continue
                # Flip to the prior column only AFTER the current table's total is
                # in hand. The Section-III FX-sensitivity table that sits above the
                # repricing ladder carries "Current Period / Prior Period" (or
                # "Cari/Önceki Dönem") in its header — an ungated flip latched
                # 'prior' before the current repricing rows were read (ISCTR/ENPARA
                # lost their current table). The real prior is found either by its
                # own Prior/Önceki marker below, or the second-assets-block heuristic.
                if _PRIOR_RX.search(lab) and \
                        data.get(("current", "total"), {}).get("rate_sensitive_assets") is not None:
                    period = "prior"
                for fld, rxs in _ROW_RX:
                    if not any(rx.match(lab) for rx in rxs):
                        continue
                    vals = _value_tokens(tokens)
                    # A summary label alone on its word-line (ATBANK's position row)
                    # — its figures are on the next line. Borrow them only if that
                    # line is PURE values of the right width. Testing that it isn't
                    # one of the three summary labels was too weak: ZIRAATD 2025Q4's
                    # prior "Toplam Yükümlülükler" is one cell short, so the borrow
                    # reached past it and took "Bilançodaki Uzun Pozisyon"'s figures
                    # as the liabilities. A donor carrying any label is never right.
                    if ncols is not None and len(vals) < ncols and j + 1 < len(lines):
                        nxt = lines[j + 1]
                        if _is_value_line(nxt) and len(_value_tokens(nxt)) == ncols:
                            vals = _value_tokens(nxt)
                    # Still the wrong width: fall back to placing each value under
                    # its bucket column by x. Only reached for rows that would
                    # otherwise be dropped, and only accepted when the row foots.
                    if ncols is not None and len(vals) != ncols:
                        if not col_x_tried:
                            col_x = _page_anchors(lines, ncols, gate)
                            col_x_tried = True
                        rebuilt = _row_by_columns(lines, j, col_x, ncols)
                        if rebuilt is not None:
                            vals = rebuilt
                    # Lock the column count off the first assets row we see.
                    if ncols is None and fld == "rate_sensitive_assets":
                        ncols = len(vals)
                    if ncols is None or len(vals) != ncols:
                        break
                    # Second assets block w/o a marker ⇒ prior comparative.
                    if fld == "rate_sensitive_assets" and period == "current" \
                            and ("current", "total") in data \
                            and data[("current", "total")].get("rate_sensitive_assets") is not None:
                        period = "prior"
                    buckets = _BUCKETS_7 if ncols == 7 else \
                        [f"b{k+1}" for k in range(ncols - 1)] + ["total"]
                    for bk, tok in zip(buckets, vals):
                        data.setdefault((period, bk), {})[fld] = parse_num(tok)
                    break
    finally:
        doc.close()

    # Build rows + the running cumulative gap (over dated buckets, in order).
    for ptype in ("current", "prior"):
        buckets = _BUCKETS_7 if ncols == 7 else \
            [f"b{k+1}" for k in range((ncols or 1) - 1)] + ["total"]
        run = 0.0
        for bk in buckets:
            fields = data.get((ptype, bk))
            if fields is None:
                continue
            row = RepricingRow(period_type=ptype, bucket=bk, **fields)
            if bk != "total" and row.gap is not None:
                run += row.gap
                row.cumulative_gap = run
            rep.rows.append(row)
    return rep


def extract(pdf_path: str | Path) -> RepricingReport:
    return extract_from_pdf(None, str(pdf_path))


# ---------------------------------------------------------------------------
# DB loader
# ---------------------------------------------------------------------------
_VALUE_COLS = ["rate_sensitive_assets", "rate_sensitive_liab", "gap", "cumulative_gap"]


def upsert(conn: sqlite3.Connection, bank_ticker: str, period: str, kind: str,
           rep: RepricingReport) -> int:
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM bank_audit_repricing WHERE bank_ticker=? AND period=? AND kind=?",
        (bank_ticker, period, kind),
    )
    cols = ["bank_ticker", "period", "kind", "period_type", "bucket",
            *_VALUE_COLS, "source_page"]
    ph = ", ".join("?" for _ in cols)
    rows = [(
        bank_ticker, period, kind, r.period_type, r.bucket,
        *[getattr(r, c) for c in _VALUE_COLS], rep.source_page,
    ) for r in rep.rows]
    if rows:
        cur.executemany(
            f"INSERT INTO bank_audit_repricing ({', '.join(cols)}) VALUES ({ph})", rows
        )
    conn.commit()
    return len(rows)


def summarize(rep: RepricingReport) -> str:
    if not rep.rows:
        return f"{Path(rep.pdf_path).name}\n  (no interest-rate-risk table found)"
    lines = [f"{Path(rep.pdf_path).name}  (page {rep.source_page})"]
    for r in rep.rows:
        def f(v):
            return f"{v:,.0f}" if v is not None else "-"
        lines.append(
            f"  {r.period_type:<7} {r.bucket:<14} RSA={f(r.rate_sensitive_assets):>16} "
            f"RSL={f(r.rate_sensitive_liab):>16} gap={f(r.gap):>15} cum={f(r.cumulative_gap):>15}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    path = sys.argv[1] if len(sys.argv) > 1 else \
        "data/eye/AKBNK_2024Q4_unconsolidated.pdf"
    print(summarize(extract(path)))
