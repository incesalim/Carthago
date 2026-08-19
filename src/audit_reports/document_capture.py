"""Full-fidelity capture of every table in a BRSA filing — rows, columns, cells
and the notes that qualify them.

The analytical `bank_audit_*` tables stay narrow and typed on purpose: each one
answers a question we already know how to ask. This module answers the other
half — "what did the filing actually print?" — for the WHOLE document, not just
the pages a lane locator happens to find.

Three things separate it from `source_capture.py`, which it complements rather
than replaces:

* **Document-scoped, not lane-scoped.** Every page is read, so a table nobody
  has written a parser for yet (exposure-class RWA, average interest rates, the
  maturity ladder, related-party balances) is still captured. Adding a lane
  later becomes a query against this ledger instead of a fleet-wide re-read of
  1,050 PDFs out of R2.
* **Cells, not just lines.** Values are grouped into table BLOCKS and each
  numeric cell is snapped to an inferred column, so a row's cells carry a
  column index and not merely a position in a token list.
* **Notes are linked.** A "(*)" on a row and the "(*) …" sentence under the
  table become one fact: the marker, the note text, and the row(s) it qualifies.

Nothing here writes an analytical row, so it is safe to run over the settled
balance-sheet and P&L partitions: it only ever adds evidence beside them.

PyMuPDF (`fitz`) only — `pdfplumber` is banned repo-wide.
"""
from __future__ import annotations

import dataclasses
import hashlib
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

try:
    import fitz  # PyMuPDF
    _HAS_FITZ = True
except ImportError:  # pragma: no cover - fitz is a hard dep in CI/local
    _HAS_FITZ = False


# --- tuning constants ------------------------------------------------------
# Words within this many points of each other's baseline are one physical line.
# 3.0 is the value every other parser in this package uses; keeping it identical
# means a line here is the same object a lane parser saw.
_Y_TOLERANCE = 3.0
# Right edges within this many points belong to the same column. BRSA value
# columns are right-aligned, so their x1 clusters very tightly; 6.0 absorbs
# sub-point kerning drift without merging genuinely adjacent narrow columns.
_COL_TOLERANCE = 6.0
# A table block is a run of value-bearing lines. Wrapped labels and blank
# separators are tolerated inside a block up to this many consecutive lines.
_BLOCK_MAX_GAP = 2
# Below this many value-bearing lines a run is a stray figure in prose, not a
# table. Three is the smallest thing that can have a header and two data rows.
_BLOCK_MIN_ROWS = 2
# A column cluster must be backed by this share of the block's rows (floor of 2).
_COLUMN_SUPPORT_SHARE = 0.12
# A block must print at least this many SUBSTANTIAL figures — a grouped amount,
# a 4+ digit integer or a ratio. Without it the cover page's address block
# ("Telefon : (0 212) 385 55 55") and the numbered list of subsidiaries both
# satisfy every structural test and render as tables of nonsense.
_BLOCK_MIN_SUBSTANTIAL = 3
# Substantial = a thousands group, 4+ consecutive digits, or a 1-2dp decimal.
# Deliberately excludes bare small integers and bare ordinals ("1.", "55").
_SUBSTANTIAL = re.compile(r"[.,]\d{3}(?!\d)|\d{4,}|\d[.,]\d{1,2}(?!\d)")
# A line repeated on at least this fraction of pages is running furniture (the
# bank name, the "31 MART 2026 …" date banner, the unit caption).
_FURNITURE_PAGE_FRACTION = 0.55

# A numeric/nil cell: 1,234.56 / 1.234,56 / (1,208) / 14.08 / %5,50 / - .
# Mirrors the token grammar the lane parsers use so cell counts here and there
# are comparable.
_NUM_TOKEN = re.compile(r"^%?\(?-?\d[\d.,]*%?\)?$")
_NIL = {"-", "—", "–", "--", "---"}
# Footnote markers as they are PRINTED, both in a row's label and at the head of
# the note itself: (*) (**) (1) (12) (a). A bare "(2)" inside a label is a
# marker; a parenthesised NEGATIVE always carries a separator or 3+ digits, so
# the two do not collide.
_MARKER = re.compile(r"\((\*{1,6}|\d{1,2}|[a-zA-Z])\)")
_NOTE_START = re.compile(r"^\s*(?:\((\*{1,6}|\d{1,2}|[a-zA-Z])\)|(\*{1,6}))\s*(?=\S)")
_SPACE_RX = re.compile(r"\s+")
_VALUE_SHAPE = re.compile(r"(?<![\w])(?:%?\(?-?\d(?:[\d.,]*\d)?%?\)?|[-–—]+)(?![\w])")

_TR_TRANSLATION = str.maketrans({
    "ı": "i", "İ": "I", "ş": "s", "Ş": "S", "ğ": "g", "Ğ": "G",
    "ç": "c", "Ç": "C", "ö": "o", "Ö": "O", "ü": "u", "Ü": "U",
})

# Line roles. `data` carries values inside a table block; `heading` is the text
# immediately above one; `footnote` qualifies one; `paragraph` is narrative;
# `furniture` is the repeating page banner.
ROLE_DATA = "data"
ROLE_HEADING = "heading"
ROLE_FOOTNOTE = "footnote"
ROLE_PARAGRAPH = "paragraph"
ROLE_FURNITURE = "furniture"


def _fold(value: str) -> str:
    """Turkish-aware ASCII fold — same normalisation source_capture.py uses, so
    a label matched there matches here."""
    translated = value.translate(_TR_TRANSLATION)
    ascii_text = unicodedata.normalize("NFKD", translated).encode(
        "ascii", "ignore").decode("ascii")
    return _SPACE_RX.sub(" ", re.sub(r"[^a-zA-Z0-9]+", " ", ascii_text).lower()).strip()


# Per-LINE fingerprints are stored ~5.5M times each, so a full 64-char SHA-256
# hex digest would cost ~0.7 GB of the ledger on its own. 16 hex chars (64 bits)
# is ample for change detection at this scale — the birthday bound over 5.5M
# lines is ~1e-6 — and these hashes only ever answer "did this line change?".
# The DOCUMENT-level hashes that reach D1 keep the full digest.
_LINE_DIGEST_CHARS = 16


def _digest(parts, chars: int | None = None) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(str(part).encode("utf-8", "replace"))
        h.update(b"\n")
    return h.hexdigest()[:chars] if chars else h.hexdigest()


def _line_digest(parts) -> str:
    return _digest(parts, _LINE_DIGEST_CHARS)


def _shape(value: str) -> str:
    """The line with every value replaced by <N> — a layout fingerprint that is
    stable when only the figures change, so a template change is detectable
    separately from a restatement."""
    return _SPACE_RX.sub(" ", _VALUE_SHAPE.sub("<N>", value)).strip()


def _is_value(token: str) -> bool:
    return token in _NIL or bool(_NUM_TOKEN.match(token))


def _is_numeric(token: str) -> bool:
    return bool(_NUM_TOKEN.match(token)) and any(c.isdigit() for c in token)


def parse_cell(token: str) -> float | None:
    """Parse a printed cell to a float, honouring both TR (1.234,56) and EN
    (1,234.56) conventions and parenthesised negatives. Returns None for a nil
    dash — a dash is 'nothing printed here', which is not the number zero, and
    the distinction is load-bearing across this project."""
    t = token.strip()
    if not t or t in _NIL:
        return None
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()").strip()
    pct = t.endswith("%") or t.startswith("%")
    t = t.strip("%").strip()
    if not t:
        return None
    if t.startswith("-"):
        neg = True
        t = t[1:]
    if "," in t and "." in t:
        # The RIGHTMOST separator is the decimal one.
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif "," in t:
        # A lone comma is a decimal point only when it leaves <3 trailing
        # digits ("16,79"); "1,234" is a thousands group.
        head, _, tail = t.rpartition(",")
        t = f"{head}.{tail}" if len(tail) != 3 else t.replace(",", "")
    elif "." in t:
        head, _, tail = t.rpartition(".")
        if len(tail) == 3 and head.replace(".", "").isdigit():
            t = t.replace(".", "")
    try:
        val = float(t)
    except ValueError:
        return None
    _ = pct  # percent-ness is recorded on the cell, not folded into the value
    return -val if neg else val


@dataclass(frozen=True)
class Cell:
    line_order: int
    cell_index: int              # position within the line, left→right
    col_index: int | None        # column in the block's inferred grid
    x0: float
    x1: float
    text: str
    is_numeric: bool
    value: float | None


@dataclass(frozen=True)
class Line:
    page: int
    line_order: int
    y: float
    x0: float
    x1: float
    text: str
    label: str                   # leading non-value text
    role: str
    block_id: int | None
    # Physical lines are captured 1:1, but a printed table ROW can span two of
    # them when its label wraps and its figures land on the continuation line
    # (BRSA LCR rows 5/11/13/14/15 do exactly this). `logical_row` groups the
    # physical lines that form one printed row, so a consumer can reassemble
    # the row without losing the evidence of how it was actually laid out.
    logical_row: int | None
    numeric_count: int
    markers: tuple[str, ...]
    line_hash: str
    shape_hash: str


@dataclass(frozen=True)
class Note:
    page: int
    note_order: int
    marker: str | None
    text: str
    block_id: int | None
    linked_line_orders: tuple[int, ...]


@dataclass(frozen=True)
class Block:
    page: int
    block_id: int
    first_line: int
    last_line: int
    n_cols: int
    col_x: tuple[float, ...]
    # What the filing PRINTS above each column ("EURO", "USD", "Diğer YP",
    # "Toplam"). Empty string where no header token sits over that column.
    col_labels: tuple[str, ...]
    heading: str
    row_count: int
    cell_count: int


@dataclass
class PageCapture:
    page: int
    rotation: int
    width: float
    height: float
    lines: list[Line] = field(default_factory=list)
    cells: list[Cell] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)
    blocks: list[Block] = field(default_factory=list)
    # 'text'   — the page's content is typed and was read
    # 'vector' — its glyphs are drawn as outlines; NOTHING here is readable
    # 'raster' — its content zone is an embedded image (İş Bankası files whole
    #            statement pages this way); only the typed banner was read
    text_layer: str = "text"


@dataclass
class DocumentCapture:
    pdf_path: str
    page_count: int
    pages: list[PageCapture] = field(default_factory=list)
    # 'captured'   — every page was readable
    # 'partial'    — some pages are drawn or imaged; their tables are not here
    # 'unreadable' — no text at all
    status: str = "captured"

    @property
    def line_count(self) -> int:
        return sum(len(p.lines) for p in self.pages)

    @property
    def cell_count(self) -> int:
        return sum(len(p.cells) for p in self.pages)

    @property
    def note_count(self) -> int:
        return sum(len(p.notes) for p in self.pages)

    @property
    def block_count(self) -> int:
        return sum(len(p.blocks) for p in self.pages)

    @property
    def table_page_count(self) -> int:
        return sum(1 for p in self.pages if p.blocks)

    @property
    def unreadable_page_count(self) -> int:
        """Pages whose content is drawn or imaged, not typed — vector outlines
        (Fibabanka) and raster statement bodies (İş Bankası) alike; see
        `_probe_text_layer`.

        This is the difference between "this bank files a short report" and "we
        cannot read this bank's statements", which the row counts alone cannot
        tell apart. It must reach the manifest so the gap is visible rather than
        inferred from a suspiciously small capture.
        """
        return sum(1 for p in self.pages if p.text_layer != "text")

    def content_hash(self) -> str:
        return _digest(ln.line_hash for p in self.pages for ln in p.lines)

    def shape_hash(self) -> str:
        return _digest(ln.shape_hash for p in self.pages for ln in p.lines)

    def grid_hash(self) -> str:
        """Fingerprint of the table GEOMETRY — how many blocks, each of how many
        columns and rows. Changes when a filer restructures a table even if
        every label survives."""
        return _digest(
            f"{b.page}:{b.block_id}:{b.n_cols}:{b.row_count}"
            for p in self.pages for b in p.blocks
        )


def _sideways_x(boxes) -> frozenset[int]:
    """x positions holding a column of SIDEWAYS text, to be ignored.

    Garanti prints "The accompanying notes are an integral part of these
    consolidated financial statements" rotated 90° down the left margin of its
    landscape equity statement. Each word sits at x=30 with its own y, so
    y-bucketing hands one word to each table row and every label came out as
    "accompanying VII. Capital Reserves…", "notes XI. Profit Distribution",
    "are 11.2 Transfers to Reserves" — the sentence dealt across the table.

    What identifies the column is which dimension stays CONSTANT down it. Every
    rotated word is exactly one glyph-height wide and as tall as it is long —
    12 words at x=30 all measure 5.98 wide against heights from 4.55 to 31.83 —
    while an upright column is the transpose: the roman numerals on a contents
    page are all 9.96 tall against widths from 5.25 ("I.") to 17.74 ("VIII.").

    Judging each word by its own aspect ratio does NOT work and was measured:
    "III." and "(-)" are narrow enough to be taller than wide, so that version
    deleted the numbering from every contents page and the deduction markers
    from statement rows. Three words are required, so a coincidence of two
    cannot condemn a column.
    """
    from collections import defaultdict
    at_x: defaultdict[int, list[tuple[float, float]]] = defaultdict(list)
    for x0, y0, x1, y1, text in boxes:
        # Single characters cannot vote. A column of "-" placeholders — how a
        # BRSA statement prints "not disclosed", so never safe to drop — has
        # identical widths and a full line-height box, which satisfies every
        # test below. Excluding them cost nothing: a rotated word of one letter
        # carries no label either.
        if len(text.strip()) >= 2:
            at_x[round(x0)].append((x1 - x0, y1 - y0))
    out = set()
    for x, dims in at_x.items():
        if len(dims) < 3:
            continue
        widths = [w for w, _h in dims]
        heights = [h for _w, h in dims]
        # The constant dimension must also be ONE GLYPH: amounts of equal digit
        # count share a width too, and ascenders make their heights differ by a
        # few points, so constancy alone deleted real figures (VAKIFK p53 lost
        # 45.400.031, 33.896.880, 81.550.957). A rotated word runs many glyphs
        # along the axis that varies, which no upright column can imitate.
        if (max(widths) - min(widths) < 1.0
                and max(heights) >= 3.0 * max(widths)):
            out.add(x)
    return frozenset(out)


def _sideways_dir(page, rot_m) -> dict[int, float]:
    """Which way each sideways column READS, as the sign of its y advance.

    Rotation direction cannot be inferred from position: Garanti's margin note
    advances down the page (dir 0,+1) and Albaraka's row-group labels advance
    up it (dir 0,-1). Guessing one of them reverses the other — "statements.
    financial consolidated these of part integral an are notes accompanying
    The". PyMuPDF reports the writing direction per line, so it is read rather
    than assumed, mapped through the page rotation so it means the same thing
    as the bboxes it will order.
    """
    out: dict[int, float] = {}
    try:
        blocks = page.get_text("dict")["blocks"]
    except Exception:
        return out
    for b in blocks:
        for ln in b.get("lines", []):
            dx, dy = ln.get("dir", (1.0, 0.0))
            for s in ln.get("spans", []):
                x0, y0, x1, y1 = s["bbox"]
                if rot_m is not None:
                    r = fitz.Rect(x0, y0, x1, y1) * rot_m
                    r.normalize()
                    x0 = r.x0
                    dx, dy = (rot_m.a * dx + rot_m.c * dy,
                              rot_m.b * dx + rot_m.d * dy)
                if abs(dy) > abs(dx):
                    out[round(x0)] = dy
    return out


def _page_word_lines(page) -> tuple[list[tuple[float, list[tuple[float, float, str]]]], int]:
    """Physical lines for one page as (y, [(x0, x1, text), …]), in DISPLAY space.

    A /Rotate 90|270 page (GARAN/AKBNK file their landscape statements that way)
    reports word bboxes in UN-rotated space, where visual columns share a y and
    visual rows share an x — y-bucketing those scrambles the table into garbage.
    Mapping each bbox through the page's rotation_matrix first fixes it, and the
    matrix is the identity when rotation == 0, so upright pages are unchanged.
    This is the same correction `extractor._fitz_page_text` applies; without it
    "capture everything" would silently capture the landscape pages as noise.
    """
    words = page.get_text("words")
    rotation = int(page.rotation or 0)
    if not words:
        return [], rotation
    rot_m = page.rotation_matrix if rotation else None
    boxes: list[tuple[float, float, float, float, str]] = []
    for w in words:
        x0, y0, x1, y1, text = w[0], w[1], w[2], w[3], w[4]
        if rot_m is not None:
            r = fitz.Rect(x0, y0, x1, y1) * rot_m
            r.normalize()
            x0, y0, x1, y1 = r.x0, r.y0, r.x1, r.y1
        boxes.append((x0, y0, x1, y1, text))
    sideways = _sideways_x(boxes)
    # Sideways words are pulled OUT of the y-clustering — one per table row is
    # exactly how they corrupt labels — but not thrown away. Albaraka prints
    # the row-group names of its credit-ratings table vertically ("Long term
    # credit ratings", "Ratings for long term securitisation positions"), and
    # those name real groups of rows. Each column is re-emitted as a single
    # line, read top-to-bottom, so the text survives as its own line instead of
    # being dealt across the table.
    aside: dict[int, list[tuple[float, str]]] = {}
    if sideways:
        for x0, y0, _x1, _y1, text in boxes:
            if round(x0) in sideways and text.strip():
                aside.setdefault(round(x0), []).append((y0, text))
    placed: list[tuple[float, float, float, str]] = []
    for x0, y0, x1, _y1, text in boxes:
        if round(x0) in sideways:
            continue
        if text and text.strip():
            m = _GLUED_VALUE_LABEL.match(text.strip())
            if m:
                # Split the run proportionally by character count so each half
                # keeps a usable x-range: the figure must land in its column and
                # the label must sit where the next row's label belongs.
                head, tail = m.group(1), m.group(2)
                cut = x0 + (x1 - x0) * len(head) / len(text.strip())
                placed.append((y0, x0, cut, head))
                placed.append((y0, cut, x1, tail))
            else:
                placed.append((y0, x0, x1, text))
    placed.sort(key=lambda t: (t[0], t[1]))
    rows: list[tuple[float, list[tuple[float, float, str]]]] = []
    for y0, x0, x1, text in placed:
        if rows and y0 - rows[-1][0] <= _Y_TOLERANCE:
            rows[-1][1].append((x0, x1, text))
        else:
            rows.append((y0, [(x0, x1, text)]))
    dirs = _sideways_dir(page, rot_m) if aside else {}
    for x, items in aside.items():
        # Order by the direction the column actually reads, defaulting to
        # top-to-bottom when the span carried none.
        items.sort(key=lambda t: t[0], reverse=dirs.get(x, 1.0) < 0)
        rows.append((min(y for y, _t in items),
                     [(float(x), float(x), " ".join(t for _y, t in items))]))
    rows.sort(key=lambda r: r[0])
    return [(y, sorted(toks)) for y, toks in rows], rotation


def _channel_fields(tokens: list[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
    """Split a line into printed fields at its column channels.

    A gap at word spacing continues a field; a gap at least `_COLUMN_CHANNEL_PT`
    wide starts a new one. This is the same boundary the rest of the module uses
    to tell a column from a sentence, applied to text as well as to figures, so
    "Süleyman Sözen | Chairman | 29.05.1997 | University | 45 years" resolves to
    the five fields the filing prints. Returns (x0, x1, text) per field; the
    first is the row label.
    """
    if not tokens:
        return []
    fields: list[list[tuple[float, float, str]]] = [[tokens[0]]]
    for k in range(1, len(tokens)):
        if tokens[k][0] - tokens[k - 1][1] >= _COLUMN_CHANNEL_PT:
            fields.append([tokens[k]])
        else:
            fields[-1].append(tokens[k])
    return [(f[0][0], f[-1][1], " ".join(t for _a, _b, t in f).strip())
            for f in fields]


def _split_label(tokens: list[tuple[float, float, str]]) -> str:
    """The leading non-value text of a row — everything up to its last word.

    Running to the LAST word (rather than stopping at the first figure) keeps a
    label whose own text embeds a figure intact — "Ortaklık paylarının %10 veya
    daha azına sahip…".

    But when the NEXT row's label is glued onto this line's end ("…280.664.505
    B. EMANET"), that trailing fragment would drag every figure between it and
    the real label into the label. A run of three or more figures separating the
    two is the tell, and the label is cut before that run.

    A figure carrying a unit defeats the last-word rule outright: Akbank's FX
    table prints "Bilanço değerleme kuru 44,3961 TL 50,9294 TL", so the final
    word is "TL" and the label swallowed the row's own figures — which were then
    printed a second time as cells. The column channel settles it. Where a value
    is reached across one, the columns have begun and the label ends there; the
    embedded "%10" above is at word spacing and so keeps its label whole.
    """
    fields = _channel_fields(tokens)
    if len(fields) > 1:
        head = fields[0][2]
        # Only when the first field is real text. A row identified by a bare
        # figure ("2026" opening a maturity ladder) has no label, and calling
        # its identifier one would invent a label the filing does not print.
        if any(ch.isalpha() for ch in head) and not all(
                _is_value(w) for w in head.split()):
            return head

    last_text = -1
    for i, (_x0, _x1, t) in enumerate(tokens):
        if not _is_value(t):
            last_text = i
    if last_text < 0:
        return ""
    j = last_text
    while j - 1 >= 0 and not _is_value(tokens[j - 1][2]):
        j -= 1
    run, k = 0, j - 1
    while k >= 0 and _is_value(tokens[k][2]):
        run += 1
        k -= 1
    if run >= _TRAILING_VALUE_RUN and k >= 0:
        last_text = k
    return " ".join(t for _x0, _x1, t in tokens[:last_text + 1]).strip()


def _infer_columns(rows: list[list[tuple[float, float, str]]]) -> list[float]:
    """Column right-edges for one table block, clustered from its value cells.

    BRSA value columns are right-aligned, so a column is a tight cluster of x1.
    Clustering the FIGURES rather than reading a header row is what makes this
    work on the pages whose headers wrap, letter-space or go missing entirely —
    the same pathologies the lane parsers each carry bespoke repairs for.

    A cluster must be backed by a real share of the block's rows. Two members was
    too weak: a table carrying a date caption ("Cari Dönem – 31 Mart 2026 …") and
    a repeated year gets one stray cell per period block, which is enough to mint
    a phantom column at the far left — and every real column then renders one or
    two positions to the right of where it belongs.
    """
    # Clustering the FIELD edges instead — so text-only columns get their own
    # column rather than leaving their cells unplaced — was measured and cost
    # 30 blocks and 272 rows across eight filings (Akbank alone -11 and -72):
    # the extra edges shift cluster support and blocks stop reaching their
    # terminal column. Text cells stay captured-but-unplaced until column
    # inference can admit them without destabilising the statement grids.
    # Letting only channel-reached values vote — to stop a figure inside a row
    # label ("Less than 1 Year") minting a phantom leading column — was measured
    # and reverted: it cost 9 blocks, 139 rows and 1,563 placed cells to remove
    # 12 dead columns, because a narrow table sets adjacent figures closer than
    # a channel and their columns stopped being found at all. Dead columns are
    # pruned after the fact instead, where nothing can be lost.
    edges = sorted(x1 for row in rows for _x0, x1, t in row if _is_value(t))
    if not edges:
        return []
    clusters: list[list[float]] = [[edges[0]]]
    for e in edges[1:]:
        if e - clusters[-1][-1] <= _COL_TOLERANCE:
            clusters[-1].append(e)
        else:
            clusters.append([e])
    support = max(2, int(len(rows) * _COLUMN_SUPPORT_SHARE))
    kept = [sum(c) / len(c) for c in clusters if len(c) >= support]
    # Never return nothing: a very short block legitimately has few members.
    return kept or [sum(c) / len(c) for c in clusters if len(c) >= 2] or \
        [sum(c) / len(c) for c in clusters]


def _detect_blocks(lines: list[tuple[float, list[tuple[float, float, str]]]],
                   note_idx: frozenset[int]) -> list[list[int]]:
    """Group line indices into table blocks — maximal runs of value-bearing
    lines, tolerating short gaps for wrapped labels and rule lines.

    A footnote line ENDS its table. Footnotes routinely quote figures ("…içinde
    91.834.297 TL … bulunmaktadır"), so on pure value-density they look like more
    table rows and would otherwise be swallowed into the block — which both
    inflates the row count and denies the note its own role. Treating a note
    marker as a hard terminator is what keeps `(*) …` a note rather than a row.
    """
    def _candidate(i: int, toks) -> bool:
        if i in note_idx:
            return False
        vals = sum(1 for _x0, _x1, t in toks if _is_value(t))
        if not vals:
            return False
        if any(c.isalpha() for _x0, _x1, t in toks for c in t):
            return True
        # A line of pure figures is still a table row. TSKB's KAP filings print
        # the label in two halves with the VALUES BETWEEN them ("Financial
        # Assets at Fair Value Through Other" / "(4) 17.871.217 …" /
        # "Comprehensive Income"), so the figure line carries no letters at all.
        # Requiring letters dropped those rows and split the balance sheet into
        # several "tables".
        #
        # Three would be the safe floor, because a page's date header is also
        # figures-only ("31.03.2026 31.12.2025"). But a two-column statement's
        # wrapped row carries exactly TWO figures ("1.672.951 1.324.173"), and
        # requiring three lost the whole row — label, figures and all — on every
        # such line. Tell them apart by what the tokens ARE: dates look like
        # dates. Counting alone cannot separate them.
        dated = any(_DATE_TOKEN.match(t) for _x0, _x1, t in toks if _is_value(t))
        return vals >= (3 if dated else 2)

    value_rows = [i for i, (_y, toks) in enumerate(lines) if _candidate(i, toks)]
    if not value_rows:
        return []
    blocks: list[list[int]] = [[value_rows[0]]]
    for i in value_rows[1:]:
        prev = blocks[-1][-1]
        bridged_note = any(j in note_idx for j in range(prev + 1, i))
        if i - prev - 1 <= _BLOCK_MAX_GAP and not bridged_note:
            blocks[-1].append(i)
        else:
            blocks.append([i])
    return [b for b in blocks if len(b) >= _BLOCK_MIN_ROWS]


# At least this share of a block's rows must carry a cell in its last column
# for the run to count as a table rather than as figure-bearing prose.
_TERMINAL_COLUMN_SHARE = 0.5

# A period caption introduces a block of rows; it is never a row label and so
# never the first half of a wrapped one. It is matched on the Turkish-aware fold
# so "Cari Dönem" / "CARİ DÖNEM" / "Current Period" all reach the same guard.
_PERIOD_CAPTION = re.compile(
    r"^(cari donem|onceki donem|gecmis donem|current period|prior period|"
    r"previous period)\b")

# A row label that OPENS a statement line: the filing's own hierarchy marker
# ("I.", "1.1.4", "2.3.1"). Its presence identifies a new row; its absence on a
# line that follows one identifies a continuation — a far better signal than
# letter case, since Turkish labels wrap onto capitalised words as often as not
# ("1.4.1 …Değer Farkı Kar" / "Zarara Yansıtılan Kısmı").
_ROW_OPENER = re.compile(r"^(?:[IVXLCDM]+\.|\d+(?:\.\d+)*\.?)(?:\s|$)")
# How many physical lines one printed row's label may wrap over before its
# figures appear. BRSA's capital-deduction labels reach five; the bound stops a
# malformed page from swallowing a whole table into one row.
_MAX_WRAP_LINES = 6
# Date-shaped text: two numbers joined by a date separator. Distinguishes a
# period column header ("01/01/2024- 31/12/2024") from stray digits.
_DATEISH = re.compile(r"\d[./-]\d")
# A DATE token: dd.mm.yyyy or a bare year. Unlike _DATEISH this does not also
# match a grouped amount ("1.672.951"), so it can gate a figures-only row.
_DATE_TOKEN = re.compile(r"^\d{1,2}[./]\d{1,2}[./]\d{4}$|^(?:19|20)\d{2}$")
# A grouped amount with the NEXT row's label glued to it — "280.664.505B." for
# "280.664.505" + "B. EMANET KIYMETLER". The text layer drops the space, which
# costs BOTH the value (the token no longer parses as a number) and the label.
# Requiring a thousands group keeps ordinary alphanumeric codes intact.
_GLUED_VALUE_LABEL = re.compile(r"^(\(?-?\d{1,3}(?:[.,]\d{3})+\)?)([^\W\d_].*)$")
# Figures separating a label from a trailing fragment glued on from the next row.
_TRAILING_VALUE_RUN = 3
# A cell-less row longer than this is narrative, not an in-table section
# caption. Captions are short ("ASSETS", "Cekirdek Sermayeden Yapilacak
# Indirimler"); a sentence that drifted into the block is not.
_PROSE_ROW_MIN = 70
# A colon-terminated line at least this long is a numbered note heading that
# separates two tables, not a row. Short ones are ordinary labels.
_SECTION_HEADING_MIN = 15
# How many lines from a block's start may serve as its in-table header row.
_HEADER_SCAN_ROWS = 3
# How far above a block to look for its column header row.
_HEADER_LOOKBACK = 8
# An inter-word gap wider than this is a column channel, not a space. Corpus
# spaces measure 1.7-4.9pt; header channels 21-226pt.
_COLUMN_CHANNEL_PT = 15.0
# At or below this token count a single column channel identifies a header.
_SHORT_HEADER_TOKENS = 4
# Vector path items per extracted word above which a page's glyphs are drawn
# outlines rather than text. See `_probe_text_layer` for the measured margin.
_VECTOR_INK_PER_WORD = 25.0
# A blockless page whose content zone is covered by embedded images while its
# typed words keep to the margin bands is a statement filed as a PICTURE. All
# four thresholds sit in measured gaps — see `_raster_content`.
_RASTER_MIN_COVERAGE = 0.10   # rasterized statements measure 17-48%; logos <5%
_RASTER_BAND_TOP = 0.18       # banner + caption end by ~15% on every measured case
_RASTER_BAND_BOTTOM = 0.86    # footer / page number sits at 93-96%
_RASTER_MAX_ZONE_WORDS = 8    # a cover's title puts 20+ words INSIDE the zone
# A figure that can NAME a column rather than fill one: a year or full date, or
# a bare integer percentage ("0%", "%10", "150%"). Anything carrying a decimal
# or a thousands group is an amount — including the Turkish ratio form
# "%69,47", which is data however it is punctuated.
_HEADER_FIGURE = re.compile(r"^%?\d{1,3}%?$|^\d{1,2}[./]\d{1,2}[./]\d{4}$|^(?:19|20)\d{2}$")
# A column header made only of percentages ("0%", "%20", "100%"), possibly a
# run of them where two share a span.
_PERCENT_ONLY = re.compile(r"(?:%?\d{1,3}%?)(?:\s+%?\d{1,3}%?)*")


def _column_labels(lines, idxs: list[int], cols: list[float],
                   heading_idx: list[int]) -> list[str]:
    """The header word(s) printed over each column.

    Read from the value-less lines at the top of the block plus the caption
    lines above it, assigning each word to the column whose horizontal span
    contains the word's centre. A column's span runs from the previous column's
    right edge to its own, which is what makes right-aligned BRSA headers land
    correctly; a word over the label column is discarded with it.

    Without this a table renders as "c0 c1 c2 c3" and reads as unlabelled even
    when every figure is in the right place.
    """
    if not cols:
        return []
    # Every column's span is one typical column WIDTH back from its right edge —
    # not "back to the previous column". Statement tables put the row-number
    # column at the far left (col_x [81, 455, 554]), so bounding by the previous
    # column made the second span 380pt wide and swept the entire row-label area
    # into it: "Cari Dönem Risk Sınıfları Risk Tutarı" instead of "Cari Dönem
    # Risk Tutarı", long enough that the plausibility filter dropped it and the
    # table rendered unlabelled. A uniform width is identical for evenly-spaced
    # columns and correct for irregular ones.
    # MEDIAN gap, not the minimum: statements put a hierarchy column and a
    # footnote column within a few points of each other (col_x [86, 93, 461,
    # 536] — a 7pt gap), and using the minimum shrank EVERY span to 7pt so no
    # header word landed anywhere. That single pathology accounted for most of
    # the unlabelled tables. The lower bound is still clamped at the previous
    # column so widened spans cannot overlap and duplicate a word.
    # LOWER median: with an even number of gaps, the upper middle is the wider
    # one, and for the common two-gap table ([100, 373]) that picked 373 and
    # swept the row-label words back into the first value column.
    gaps = sorted(cols[k] - cols[k - 1] for k in range(1, len(cols)))
    width = gaps[(len(gaps) - 1) // 2] if gaps else 90.0
    bounds = [(max(cx - width, cols[k - 1]) if k else cx - width,
               cx + _COL_TOLERANCE)
              for k, cx in enumerate(cols)]
    def _aligned(i: int) -> bool:
        """Does this line contribute a DATA cell to the grid? A header does not.

        The original test — any aligned figure at all — assumed a header's own
        figures are dates that "sit nowhere near a value column". They often sit
        exactly on one, because a header can be numeric by nature: Halkbank
        names its risk-weight columns "0% 10% 20% 50% 75% 100%", each printed
        over the column it labels, and dates its shareholder columns "31
        December 2025 | 31 December 2024" above the amounts. Both were read as
        data rows, so the table rendered unlabelled with its header sitting in
        plain sight one line above the figures.

        A printed header figure is a date or a bare integer percentage; a data
        figure is a grouped amount or a decimal. That keeps a Turkish ratio
        column ("%69,47") on the data side, where it belongs.
        """
        return any(_is_value(t) and any(abs(x1 - cx) <= _COL_TOLERANCE * 2 for cx in cols)
                   for _x0, x1, t in lines[i][1])

    def _aligned_amounts(i: int) -> bool:
        """`_aligned`, but blind to figures that can name a column.

        Used ONLY as a fallback. Applying it first was measured: it admits the
        date caption as an extra header source, and "January 2026 – 31 March"
        then crowds the real words out of the mapping. Garanti p11 went from
        "TL | CURRENT PERIOD FC | Total | TL | PRIOR PERIOD FC | Total" to
        "March | December" — 117 headers changed, many from right to wrong,
        against 16 gained. Tried second, it only speaks where the strict test
        found nothing at all.
        """
        return any(_is_value(t) and not _HEADER_FIGURE.match(t)
                   and any(abs(x1 - cx) <= _COL_TOLERANCE * 2 for cx in cols)
                   for _x0, x1, t in lines[i][1])

    def _labels_from(sources: list[int], keep_figures: bool = False) -> list[str]:
        # Figures are normally not header WORDS — a date caption over a column
        # names nothing. But where the header IS numeric ("0% 20% 50%"), those
        # tokens are the only header there is, so the last-resort pass keeps
        # them; every earlier pass still drops them.
        words = [(x0, x1, t) for i in sources for x0, x1, t in lines[i][1]
                 if not _is_value(t) or (keep_figures and _HEADER_FIGURE.match(t))]
        out: list[str] = []
        for lo, hi in bounds:
            got = [t for x0, x1, t in words if lo < (x0 + x1) / 2 <= hi]
            out.append(" ".join(got)[:40])
        return out

    # Prefer the filing's own in-table header row; fall back to the caption
    # above only when the table prints no header of its own.
    # Only the block's OPENING lines can be its header row. Any unaligned line
    # was eligible before, so an all-dash data row deep in the table ("XIII.
    # SATIŞ AMAÇLI…") became the header — and because it yielded something, the
    # real caption above the block was never consulted.
    # Requiring the header to PRECEDE all data — stopping the scan at the first
    # aligned line — was measured and reverted. A maturity ladder prints its
    # caption on line 1 and its header on line 2, so the scan stopped before
    # reaching it and fell back to the caption: HALKB p83 went from "Current |
    # Period:(1) | month | 1-3 Months | 3-12 Months | 1-5 Years | Over Years |
    # Total" to sentence fragments, and ALBRK p109 and p122 likewise. Sixteen
    # header sets changed, most of them from right to wrong.
    labels = _plausible_headers(
        _labels_from([j for j in idxs[:_HEADER_SCAN_ROWS] if not _aligned(j)]))
    if not labels:
        labels = _plausible_headers(_labels_from(list(heading_idx)))
    if not labels:
        # Last resort, for a header that is ITSELF numeric: Halkbank names its
        # risk-weight columns "0% 10% 20% 50% 75% 100%" and dates its
        # shareholder columns "31 December 2025 | 31 December 2024", both of
        # which read as data rows to the strict test, leaving the table
        # unlabelled with its header one line above the figures.
        #
        # It must come after the caption. Tried before it, this pass answers
        # for tables whose caption would have answered BETTER — Garanti p11
        # went from "TL | CURRENT PERIOD FC | Total | …" to "March | December",
        # 96 headers changed against 16 gained. Last, it only fills silence.
        labels = _plausible_headers(
            _labels_from([j for j in idxs[:_HEADER_SCAN_ROWS]
                          if not _aligned_amounts(j)], keep_figures=True))
    # Assigning header FIELDS to columns positionally when their counts match —
    # to rescue a header phrase wider than the median column gap, which the
    # span arithmetic cuts ("31 December 2025" over columns 43pt apart keeps
    # only "2025") — was measured and reverted. It named 26 tables and roughly
    # sixteen of those were wrong: a board member ("ZAHRAN", "Başkanı"), the
    # subsidiary names of a data row ("Kıbrıs", "Kiralama", "Banking"), and the
    # fragments of a header that wraps ("limited", "doubtful", "loans"). Being
    # blind to x is what produces confidently wrong labels, which this module
    # already holds to be worse than none — and it did not even fix Halkbank
    # p10, the case that prompted it.
    # A "header" spanning only the label column is a caption, not column names.
    return labels if labels and any(labels[1:]) else []


def _plausible_headers(labels: list[str]) -> list[str]:
    """Keep only label fragments that can actually be column headers.

    A column header is a short noun phrase — "EURO", "Toplam", "Cari Dönem",
    "1-3 Ay". Any line the mapper is given gets chopped at column boundaries, so
    when a table has no header row of its own and the caption above it is a
    SENTENCE, the pieces come back as "agencies NSFR ratio", "in the ended
    quarter of is shown", "table below:" — confidently wrong labels over
    correctly-parsed figures, which is worse than no labels at all.

    Fragments that are too long, or that end mid-sentence, are dropped; if
    fewer than two survive there is no header worth showing.
    """
    def _ok(s: str) -> bool:
        # Bound by WORD COUNT, not characters. A 24-character cap rejected real
        # headers — "ÖNCEKİ DÖNEM (31/12/2023)" is 25, "Beklenen Kredi Zararı
        # Karşılıkları" is 34 — while still admitting short prose fragments.
        # Header phrases are a handful of words; a sliced sentence is not.
        if not s or len(s) > 40 or len(s.split()) > 5:
            return False
        if s.endswith((".", ":", ",")):
            return False
        # A header is normally a word, but a BRSA income statement names its
        # columns with a DATE RANGE alone — "(01/01/2024- 31/12/2024)" — which
        # contains no letter at all. Demanding one rejected the correct header
        # on every P&L in the corpus, so a date-shaped fragment qualifies too.
        # A risk-weight table names its columns with percentages alone — "0%",
        # "20%", "100%" — which carry neither a letter nor a date.
        return (any(c.isalpha() for c in s) or bool(_DATEISH.search(s))
                or bool(_PERCENT_ONLY.fullmatch(s)))

    kept = [s if _ok(s) else "" for s in labels]
    named = [s for s in kept if s]
    # Three or more columns sharing one label is a sentence sliced up. TWO
    # sharing one is normal — a current/prior pair is often printed "Tutar" /
    # "Tutar" — so that case must survive.
    if len(named) < 2 or (len(set(named)) == 1 and len(named) >= 3):
        return []
    return kept


def _inside_block(i: int, block_line_idx: list[list[int]]) -> bool:
    """Does line `i` fall within some table's first..last span?"""
    return any(b[0] <= i <= b[-1] for b in block_line_idx if b)


def _spans_columns(lines, members) -> bool:
    """True when a line's words are clustered over columns rather than flowing.

    This is what finally separates a wide COLUMN HEADER from a wide SENTENCE,
    after length and position both failed. A header leaves wide channels between
    its column groups; running text does not. Measured on the corpus: the
    repricing header has 7 gaps over 15pt (max 91) and the currency header 4
    (max 226), while narrative lines have none at all — their gaps are the
    uniform 1.7-4.9pt of a single space.
    """
    for i in members:
        toks = sorted(lines[i][1])
        wide = sum(1 for k in range(len(toks) - 1)
                   if toks[k + 1][0] - toks[k][1] > _COLUMN_CHANNEL_PT)
        # Two channels normally, but ONE is enough on a short line: a narrow
        # table's header is just "USD EURO", which has a single gap and was
        # being rejected. Prose is never this short, and a one-word caption has
        # no gap at all, so neither slips through.
        if wide >= (1 if len(toks) <= _SHORT_HEADER_TOKENS else 2):
            return True
    return False


def _prose_rows(lines, block_line_idx, block_cols, logical, line_cells, line_labels) -> set[int]:
    """Line indices belonging to logical rows that are narrative, not data.

    A row qualifies when it puts nothing in any column AND reads as a sentence —
    long, or closing with a full stop or colon. A SHORT cell-less row is kept:
    those are the in-table section captions ("Çekirdek Sermayeden Yapılacak
    İndirimler"), which are real structure. The first row of a block is kept too,
    being the table's printed title.
    """
    drop: set[int] = set()
    for bi, idxs in enumerate(block_line_idx, start=1):
        # ONE aligned cell is enough to call a row data. Requiring two also
        # discarded legitimate single-value rows (a total, a lone ratio) and
        # collapsed their columns — AKBNK lost five clean tables to it. The
        # residue is a paragraph whose in-sentence figure lands under a column
        # by chance; that is rarer than the rows the stricter test destroyed.
        need = 1
        rows: dict[int, list[int]] = {}
        for i in idxs:
            rows.setdefault(logical.get(i, -i), []).append(i)
        if not rows:
            continue
        first = min(rows)
        for lr, members in rows.items():
            aligned = sum(1 for i in members for c in line_cells.get(i, [])
                          if c.col_index is not None)
            if aligned >= need:
                continue
            label = " ".join(line_labels.get(i, "") for i in members).strip()
            # The first row is normally the table's printed title and is kept —
            # but only while it reads like one. Splitting a fused block can make
            # a paragraph the new first row, and exempting it unconditionally
            # let that narrative back in at the top of the table.
            # Exempting the block's opening rows from the LENGTH rule was tried
            # so a wide column header ("Cari Dönem – 31 Mart 2026 Kadar 1-3 Ay
            # …", 78 characters) would survive. It restored one header and cost
            # FIVE clean tables, because the same exemption spared genuine prose
            # sitting at a block's top — gating it on "does this row map to
            # columns?" changed nothing. Measured and reverted; a long cell-less
            # row is treated as prose wherever it sits.
            if lr == first and len(label) <= _PROSE_ROW_MIN:
                continue
            # A row whose words cluster over the columns is a header or a
            # structural row, however long it is — keep it. Only flowing text
            # is prose.
            if _spans_columns(lines, members):
                continue
            if len(label) > _PROSE_ROW_MIN or label.endswith((".", ":")):
                drop.update(members)
    return drop


def _trim_trailing_prose(lines, idxs: list[int], cols: list[float]) -> list[int]:
    """Drop trailing lines that put no figure in any of the table's columns.

    Narrative routinely follows a table on the same page — "Mevcut istikrarlı
    fonlar %20 oranında özkaynaklar, %53 oranında…" under the NSFR ladder. Those
    sentences carry figures and letters, so they pass every structural test and
    were being appended as rows; but their numbers sit at prose x-positions and
    land in NO column, whereas every real row puts at least one figure in one.
    That difference is exact, so the tail can be cut without judgement.

    A wrapped label tail also has no aligned cell, but it carries no figures at
    all and is re-attached by the absorption pass that follows.
    """
    # A real row lands at least two figures in columns (its marker plus a value,
    # or two values). Requiring only one let a single coincidence anchor the
    # tail — "%114,7 seviyesindedir." happened to sit under a column and kept
    # eight lines of narrative inside the NSFR table. One-column tables keep the
    # weaker test, since one cell is all they can offer.
    need = 2 if len(cols) >= 2 else 1

    def _anchors(i: int) -> bool:
        hits = sum(1 for _x0, x1, t in lines[i][1]
                   if _is_value(t)
                   and any(abs(x1 - cx) <= _COL_TOLERANCE * 2 for cx in cols))
        return hits >= need

    end = len(idxs)
    while end > 0 and not _anchors(idxs[end - 1]):
        end -= 1
    return idxs[:end]


def _has_substantial_figures(lines, idxs: list[int]) -> bool:
    """True when the block prints enough real figures to be a financial table.

    Structure alone cannot tell a table from the cover page's address block —
    "Telefon : (0 212) 385 55 55" is a label followed by five right-aligned
    numeric tokens on consecutive lines, which is exactly the shape being looked
    for. What separates them is the MAGNITUDE grammar: financial tables print
    grouped amounts, long integers or ratios; addresses, phone numbers and
    ordinal lists print bare small integers.
    """
    n = 0
    for i in idxs:
        for _x0, _x1, t in lines[i][1]:
            if _is_value(t) and _SUBSTANTIAL.search(t):
                n += 1
                if n >= _BLOCK_MIN_SUBSTANTIAL:
                    return True
    return False


def _every_figure_is_inline(lines, idxs: list[int]) -> bool:
    """True when every figure in the run sits inside running text — no table.

    Turkish narrative defeats column clustering by being too regular. Four
    consecutive sentences opening "4 Mart 2003 tarihinde…", "28 Kasım 2006
    tarihinde…" put the day at the left margin and the year at a near-constant
    x, because the month names are similar widths — so the dates cluster into
    two clean columns and the bank's history is minted as a 4x2 table of day
    and year numbers. Every other structural test passes: the run foots, its
    rows are long, its figures are substantial.

    What no prose can fake is the column channel to the figure's LEFT. A figure
    printed in a column is reached across a wide gap — measured on Akbank's FX
    rate table, 237.2pt and 88.0pt — while a figure inside a sentence is one
    word space from its neighbour, 2.4-3.0pt. A value opening a line counts as
    inline: it has no channel before it, and that is how a sentence beginning
    "4 Mart 2003…" starts.

    Judging by what FOLLOWS the figure was tried first and is wrong. Every
    amount in that same FX table is followed by "TL" at word spacing, so the
    rule read the whole table as prose and deleted it — caught only by diffing
    the captured blocks, never by the finding count, which improved.

    Requiring EVERY figure in the block to be inline keeps a real table whose
    row labels carry numbers: its own row numbers are inline, but its amounts
    are not, and one channelled figure is enough to save it.
    """
    saw = False
    for i in idxs:
        toks = lines[i][1]
        for k, (x0, _x1, t) in enumerate(toks):
            if not _is_value(t):
                continue
            saw = True
            if k and (x0 - toks[k - 1][1]) >= _COLUMN_CHANNEL_PT:
                return False
    return saw


def _reaches_terminal(lines, idxs: list[int], cols: list[float]) -> bool:
    """True when enough of a candidate block's rows populate its final column.

    A genuine table foots: nearly every row prints a value in the rightmost
    (total / latest-period) column. Prose that merely quotes figures does not,
    so this separates the two without needing to understand either.
    """
    if len(cols) < 2:
        return False
    terminal = cols[-1]
    hits = 0
    for i in idxs:
        for _x0, x1, t in lines[i][1]:
            if _is_value(t) and abs(x1 - terminal) <= _COL_TOLERANCE * 2:
                hits += 1
                break
    # Floor of TWO rows reaching the last column. Lowering it to one — to admit
    # a two-row aging table whose header row does not reach it — let sparse junk
    # through everywhere: weak_column findings went 1 to 94 on one filing.
    return hits >= max(2, int(len(idxs) * _TERMINAL_COLUMN_SHARE))


def _logical_rows(block_line_idx, block_cols, line_cells, line_labels) -> dict[int, int]:
    """Map each block line index → the logical (printed) row it belongs to.

    A printed row spans two physical lines whenever its label wraps and its
    figures land on the continuation line — BRSA's LCR rows 5/11/13/14/15 do
    this in every filing. Such a pair is recognised by geometry rather than by
    label text: the first line holds cells but NOT the block's last column, the
    next line's columns are disjoint from it, and the union reaches that last
    column. Requiring the first line to already hold at least one cell is what
    keeps an in-block header row (which holds none) from swallowing the data row
    beneath it.

    Rows the rule does not recognise simply stay one-line-per-row; the physical
    lines are captured either way, so this can add grouping but never lose text.
    """
    out: dict[int, int] = {}
    for bi, idxs in enumerate(block_line_idx, start=1):
        cols = block_cols.get(bi, [])
        if not cols:
            for n, i in enumerate(idxs, start=1):
                out[i] = n
            continue
        terminal = len(cols) - 1

        def _cols_of(i: int) -> set[int]:
            return {c.col_index for c in line_cells.get(i, [])
                    if c.col_index is not None}

        def _has_letters(i: int) -> bool:
            return any(c.isalpha() for c in line_labels.get(i, ""))

        def _bind_tail(out, idxs, k, n) -> int:
            """Attach a label TAIL printed under the row's figures.

            Filings wrap a long label around its own figures — head, figures,
            then the rest of the label ("1 Merkezi yönetimlerden veya merkez
            bankalarından şarta bağlı" / "49.309.893 …" / "olan ve olmayan
            alacaklar"). The tail carries no figures of its own, so without this
            it surfaces as an empty row directly beneath a complete one.
            Returns how many lines were consumed.
            """
            if k + 1 >= len(idxs) or _has_letters(idxs[k]) or not _cols_of(idxs[k]):
                return 0
            nxt = idxs[k + 1]
            if _cols_of(nxt) or not _has_letters(nxt):
                return 0
            # Garanti's landscape deposit table prints every long label on its
            # own line above its figures — "Commercial Deposits" / "96,333,623
            # …" — so binding any text-only line beneath a figures line
            # swallowed the NEXT row's label as this row's tail and left its
            # figures unlabelled.
            #
            # Orthography cannot separate the two: a real tail is title-cased
            # as often as not ("Financial Assets At Fair Value Through Other" /
            # figures / "Comprehensive Income"), and requiring a lower-case
            # resume orphaned exactly those tails. What separates them is what
            # comes AFTER: a new row's label is followed by its own figures, a
            # tail is not. A lower-case resume still binds outright, being
            # unambiguous.
            tail = line_labels.get(nxt, "").lstrip()
            after = idxs[k + 2] if k + 2 < len(idxs) else None
            opens_a_row = (after is not None and _cols_of(after)
                           and not _has_letters(after))
            if opens_a_row and not _resumes_lowercase(tail):
                return 0
            out[nxt] = n
            return 1

        n = 0
        k = 0
        while k < len(idxs):
            i = idxs[k]
            n += 1
            out[i] = n
            cur = _cols_of(i)
            # A figures-only line belongs to the label printed ABOVE it, and its
            # label may continue BELOW it (the TSKB three-line row). Bind both
            # halves to this row before the column-completion rules run.
            if cur and not _has_letters(i):
                nxt = idxs[k + 1] if k + 1 < len(idxs) else None
                if nxt is not None and not _cols_of(nxt) and _has_letters(nxt):
                    out[nxt] = n
                    k += 1
            # A merge never STARTS on the block's first line. That line is the
            # column header far more often than it is a wrapped label, and a
            # header carrying a date ("Cari Dönem – 31 Mart 2026 EURO USD …")
            # holds stray cells and no terminal column — which is exactly the
            # shape this rule absorbs, so unguarded it swallows the first real
            # data row into the header.
            # …unless the first line is unmistakably a wrapped DATA row: it
            # opens with a row marker and the next line resumes in lower case.
            # Albaraka's risk tables start exactly there — "1 Receivables from
            # central" / "governments or central banks 34.833.367 …" — and
            # because the row number is itself a cell, the cell-less wrap branch
            # below never sees the line either. Row 1 of every such table lost
            # half its label while rows 2..n merged correctly. No header opens
            # with a row marker AND is followed by a lower-case resume.
            opens_wrapped_data = (
                k == 0 and k + 1 < len(idxs)
                and _ROW_OPENER.match(line_labels.get(i, "").lstrip())
                and _resumes_lowercase(line_labels.get(idxs[k + 1], "").lstrip()))
            can_merge = (k > 0 or bool(opens_wrapped_data)) \
                and not _PERIOD_CAPTION.match(_fold(line_labels.get(i, "")))
            # A label can also wrap BEFORE its figures: "…9 uncu maddesinin
            # birinci fıkrasının (i) bendi uyarınca hesaplanan" on one line and
            # "değerleme ayarlamaları  -  -" on the next. The first line holds no
            # cells at all, so the column-completion rule below never fires. The
            # tell is orthographic: a wrapped continuation resumes in lower case,
            # whereas a new row label opens with a capital, a digit or a roman.
            # A cell-less line may open a wrapped row even at the block's start,
            # since an absorbed label head lands there; the lower-case test below
            # is what keeps a header row (also cell-less) from merging.
            if not _PERIOD_CAPTION.match(_fold(line_labels.get(i, ""))) \
                    and not cur and k + 1 < len(idxs):
                # A label can wrap over SEVERAL lines before its figures appear.
                # BRSA's capital deductions run to five: a head, three
                # lower-case continuations, then "…indirilmeyen kısmı  -  -".
                # Binding only one line left the rest as empty rows, so walk the
                # chain until a line carries cells (or nothing continues).
                head = line_labels.get(i, "").lstrip()
                taken_lines = 0
                while taken_lines < _MAX_WRAP_LINES and k + 1 < len(idxs):
                    nxt_i = idxs[k + 1]
                    nxt_label = line_labels.get(nxt_i, "").lstrip()
                    # Continuation when the next line resumes in lower case; when
                    # it is figures-only (no label of its own, so it belongs to
                    # the label above); or when THIS row opened with a hierarchy
                    # marker and the next line opens none. Requiring one of these
                    # keeps a period caption from swallowing its first data row.
                    cont = (
                        _resumes_lowercase(nxt_label)
                        or not nxt_label.strip()
                        or (_ROW_OPENER.match(head) and not _ROW_OPENER.match(nxt_label)))
                    if not cont:
                        break
                    out[nxt_i] = n
                    k += 1
                    taken_lines += 1
                    # ALIGNED cells, not any cell: a wrapped label line often
                    # carries a stray token that parses as a value ("Geçici 2
                    # nci maddesinin" yields "2") which lands in no column.
                    # Treating that as the row's figures stopped the chain one
                    # line short of the line actually holding "- -".
                    # A line holding ONLY the row number does not complete the
                    # row — its figures are still below ("…unsurları ve" / "13"
                    # / "yükümlülükler 5.564.558 …"). Treating that single
                    # aligned cell as the figures split the tail into its own
                    # row and left the label head stranded.
                    lone_marker = (not _has_letters(nxt_i)
                                   and len(line_cells.get(nxt_i, [])) <= 1)
                    if _cols_of(nxt_i) and not lone_marker:
                        # Figures reached — the row is complete, but its label
                        # may still continue BELOW (head / figures / tail).
                        k += _bind_tail(out, idxs, k, n)
                        break
                if taken_lines:
                    k += 1
                    continue
            bridged = 0
            while can_merge and cur and terminal not in cur and k + 1 < len(idxs):
                j = idxs[k + 1]
                nxt = {c.col_index for c in line_cells.get(j, []) if c.col_index is not None}
                # The continuation must fall ENTIRELY within the columns this
                # line is missing, and must reach the last one. Demanding it fill
                # every missing column was too strict: a wrapped statement line
                # ("1.4.1 …Kar" holding only its hierarchy code, then "Zarara
                # Yansıtılan Kısmı" holding six figures) legitimately leaves the
                # note column empty. The subset test still rejects a genuine next
                # row, because that carries its own marker back in column 0.
                remaining = set(range(max(cur) + 1, terminal + 1))
                if not nxt:
                    # A label can wrap over a line that carries NO figures at
                    # all before the ones that complete the row: Albaraka's
                    # exposure classes print "3 Receivables from" (the row
                    # number alone) / "administrative units and non-" / then
                    # "commercial enterprises 68.234 …". Breaking on the empty
                    # middle left the head as its own labelled-but-figureless
                    # row and the figures under a fragment. Step over it only
                    # when it RESUMES the label — an upper-case line here is
                    # the next row, not this one's continuation.
                    if (bridged < _MAX_WRAP_LINES
                            and _resumes_lowercase(line_labels.get(j, "").lstrip())):
                        out[j] = n
                        bridged += 1
                        k += 1
                        continue
                    break
                if not nxt <= remaining or terminal not in nxt:
                    break
                out[j] = n
                cur |= nxt
                k += 1
            # Same tail check for the column-completion path. A row whose label
            # head carries its own row number ("1 Merkezi yönetimlerden…") has
            # cells, so it completes HERE rather than through the branch above —
            # and its tail ("olan ve olmayan alacaklar") was being left behind as
            # an empty row on every exposure-class table.
            k += _bind_tail(out, idxs, k, n)
            k += 1
    return out


def _resumes_lowercase(label: str) -> bool:
    """True when a label resumes mid-phrase — its first LETTER is lower case.

    The first letter, not the first character: BRSA continuations routinely
    begin with punctuation or a figure ("%15'ini aşan tutarlar", "(-) …"), and
    testing character zero read those as new rows, stranding the label head
    above them as an empty row.
    """
    for ch in label:
        if ch.isalpha():
            return ch.islower()
    return False


def _row_markers(text: str) -> tuple[str, ...]:
    """Footnote markers printed on one row, read from the full line.

    Not from the label: "(2)" matches the numeric-token grammar, so a numbered
    marker is split off into the cells and never appears in the label.
    """
    return tuple(dict.fromkeys(m.group(1) for m in _MARKER.finditer(text)))


def _note_lines(line_text: list[str], raw) -> frozenset[int]:
    """Indices of lines that genuinely open a footnote.

    A star marker ("(*)", "(**)") is unambiguous — nothing else is printed that
    way. A NUMBERED marker is not: BRSA filings enumerate clauses mid-sentence
    ("…çerçevesinde (1) Banka'nın faaliyet izninin kaldırılması veya (2)
    Banka'nın hissedarlarının…"), and when such a sentence happens to wrap onto
    a new line the line now *starts* with "(2)". Left unguarded that invents a
    footnote, and — worse — truncates the table above it, since a note ends its
    block.

    So a numbered marker only counts when some table row on the page actually
    prints it. Blocks are detected twice for this: once with the unambiguous
    star notes alone, to learn which markers the rows carry, then again with the
    confirmed set. A genuine footnote whose marker appears nowhere in the table
    is left as prose rather than guessed at.
    """
    starts: dict[int, str] = {}
    for i, t in enumerate(line_text):
        m = _NOTE_START.match(t)
        if m:
            starts[i] = m.group(1) or m.group(2)
    stars = frozenset(i for i, mk in starts.items() if set(mk) == {"*"})
    numbered = {i: mk for i, mk in starts.items() if i not in stars}
    if not numbered:
        return stars
    row_markers: set[str] = set()
    for idxs in _detect_blocks(raw, stars):
        for i in idxs:
            # A candidate must never confirm ITSELF. In pass 1 only star notes
            # are excluded, so "(2) Banka'nın hissedarlarının…" can still land
            # inside a block — and its own label then supplies the "2" that
            # would vouch for it. Only OTHER rows may confirm a marker.
            if i in numbered:
                continue
            # Read the whole line, not the label: a NUMERIC marker like "(2)"
            # satisfies the numeric-token grammar, so _split_label hands it to
            # the cells and it never reaches the label at all. Star markers do
            # survive in the label, which is why this only surfaced for numbered
            # ones — both confirmation here and row-linking below need the line.
            row_markers.update(m.group(1) for m in _MARKER.finditer(line_text[i]))
    return stars | frozenset(i for i, mk in numbered.items() if mk in row_markers)


def _header_candidates(lines, first_line: int, heading_idx, taken) -> list[int]:
    """Lines above a block that could be its column header.

    `_heading_for` stops after three adjacent lines, which is right for a
    caption but too short for a header: BRSA maturity tables print the header,
    then a period caption, a section caption and a wrapped row label before the
    first data line — five or six lines in all — so the real header
    ("Vadesiz Kadar 1-3 Ay 3-12 Ay 1-5 Yıl Üzeri") fell outside the window.

    Reach further back, but keep only lines whose words are clustered over
    columns. That admits the header and rejects the captions and wrapped labels
    in between, which flow as ordinary text.
    """
    # The caption lines `_heading_for` returns are for DISPLAY and are often
    # prose ("Ana Ortaklık Banka'nın finansal tablo tarihi ile bu tarihten
    # geriye doğru son beş günü kamuya duyurulan cari döviz alış kurları…").
    # Mapped alongside a real header they produce long fragments that the
    # plausibility filter then discards, losing the header with them — so the
    # same column test applies to them.
    # PREFER the caption lines whose words sit over columns, but fall back to
    # all of them. `_heading_for` returns lines for DISPLAY, so they are often
    # prose ("…kamuya duyurulan cari döviz alış kurları…"); mapped beside a real
    # header they yield fragments the plausibility filter discards, taking the
    # header with them. Requiring the column test outright was worse still — it
    # stripped legitimate sources from 22 tables, since many headers wrap in
    # ways that leave only one channel.
    spanning = [j for j in heading_idx if _spans_columns(lines, [j])]
    out = spanning or list(heading_idx)
    # Above the block…
    scan = list(range(max(0, first_line - _HEADER_LOOKBACK), first_line))
    # …and just below its first line. When a page's banner is glued to the
    # statement title, the block starts on line 1 and its real header ("TP YP
    # Toplam TP YP Toplam") prints BELOW that — nothing above it to find.
    scan += list(range(first_line + 1, min(len(lines), first_line + 1 + _HEADER_SCAN_ROWS)))
    for j in scan:
        if j in out or j in taken:
            continue
        if _spans_columns(lines, [j]):
            out.append(j)
    # A header cannot sit on the far side of ANOTHER table. Garanti p86 stacks
    # four tables on one page, so the reach-back finds the previous table's
    # header ("Current Period Prior Period" / "TL FC TL FC", four columns) as
    # well as this table's own two-column one. Mapped together they produce
    # "Period FC TL" / "Prior Period TL FC", which the plausibility filter then
    # discards — taking the correct header down with it. Alone, the near one
    # yields "Current Period | Prior Period".
    return sorted(j for j in set(out)
                  if j >= first_line
                  or not any(t in taken for t in range(j + 1, first_line)))


def _heading_for(lines, first_line: int, taken: set[int]) -> tuple[str, list[int]]:
    """The text lines immediately above a block that carry no values — the
    printed table caption. At most three, stopping at a blank or a line already
    claimed by the previous block."""
    out: list[int] = []
    i = first_line - 1
    while i >= 0 and len(out) < 3:
        if i in taken:
            break
        _y, toks = lines[i]
        if any(_is_value(t) for _x0, _x1, t in toks):
            break
        text = " ".join(t for _x0, _x1, t in toks).strip()
        if not text:
            break
        out.append(i)
        i -= 1
    out.reverse()
    return " ".join(" ".join(t for _x0, _x1, t in lines[i][1]).strip()
                    for i in out).strip(), out


def _probe_text_layer(page, word_count: int) -> str:
    """Decide how a page that yielded no table hid its content, if it did.

    Two disguises, one failure: content legible on screen that no text
    extractor can see, captured as a suspiciously small page that nothing marks
    as a hole.

    'vector' — Fibabanka prints a complete balance sheet whose every glyph is a
    path outline: 28,366 curve segments and 35 words of header. Ink per
    extracted word separates drawn from typed cleanly — drawn pages score
    54–2,050, every typed page (dense ruled statement grids included) 0–1 — so
    the threshold sits in an empty band two orders of magnitude wide.
    `_MIN_ITEMS` keeps a near-blank divider (few words, but no ink either) out;
    the ratio alone would be undefined there.

    'raster' — İş Bankası 2025Q1/Q2 and Fibabanka 2023Q3 file statement BODIES
    as embedded images under a typed banner: ~40 words of caption, zero path
    items, one full-page image (or hundreds of tiles) where the figures should
    be. Ink-per-word scores 0, so the vector rule is blind to it — that is how
    both filings sat in the ledger stamped 'text' with 3 cells per statement
    page until `check_capture_reconcile` caught them (19% / 61%). Geometry
    identifies it where ink cannot: see `_raster_content`.

    Only called for pages that produced no block, which is both the population
    worth explaining and the reason this costs nothing on a normal filing.
    """
    _MIN_ITEMS = 2000
    try:
        items = sum(len(d["items"]) for d in page.get_drawings())
    except Exception:
        items = 0
    if items >= _MIN_ITEMS and items / max(word_count, 1) >= _VECTOR_INK_PER_WORD:
        return "vector"
    if _raster_content(page):
        return "raster"
    return "text"


def _raster_content(page) -> bool:
    """True when embedded images cover the page's content zone while its typed
    words keep to the margin bands — the signature of a page filed as a picture.

    The zone is the band between the running banner and the footer, in DISPLAY
    space (the rotation matrix is applied, so GARAN-style /Rotate 90 landscape
    pages measure the same as upright ones). Measured over the corpus
    (2026-08-19): rasterized statement pages carry 31–43 typed words, all of
    them banner and footer, under images covering 17–48% of the page; a cover
    with artwork puts its title INSIDE the zone (TSKB 2026Q2 p1: ~25 words
    there); a divider's logo covers <5%; a scanned auditor's letter is the
    degenerate case — zero words, image over everything — and is equally
    unreadable, so it is flagged too. Each threshold sits in the gap between
    those populations.
    """
    try:
        infos = page.get_image_info()
    except Exception:
        return False
    if not infos:
        return False
    m = page.rotation_matrix
    box = fitz.Rect(page.rect) * m
    box.normalize()
    if box.is_empty:
        return False
    covered = 0.0
    for info in infos:
        r = fitz.Rect(info["bbox"]) * m
        r.normalize()
        r = r & box
        if not r.is_empty:
            covered += r.get_area()
    if covered / box.get_area() < _RASTER_MIN_COVERAGE:
        return False
    top = box.y0 + box.height * _RASTER_BAND_TOP
    bottom = box.y0 + box.height * _RASTER_BAND_BOTTOM
    in_zone = 0
    for w in page.get_text("words"):
        r = fitz.Rect(w[:4]) * m
        r.normalize()
        if top <= (r.y0 + r.y1) / 2 <= bottom:
            in_zone += 1
            if in_zone > _RASTER_MAX_ZONE_WORDS:
                return False
    return True


def capture_page(page, page_number: int, furniture: frozenset[str]) -> PageCapture:
    """Capture one page: lines with roles, cells snapped to inferred columns,
    table blocks, and footnotes linked back to the rows they qualify."""
    raw, rotation = _page_word_lines(page)
    rect = page.rect
    cap = PageCapture(page=page_number, rotation=rotation,
                      width=float(rect.width), height=float(rect.height))
    word_count = sum(len(toks) for _y, toks in raw)
    if not raw:
        cap.text_layer = _probe_text_layer(page, word_count)
        return cap

    line_text = [" ".join(t for _x0, _x1, t in toks).strip() for _y, toks in raw]
    note_idx = _note_lines(line_text, raw)
    # The running page banner ("AKBANK T.A.Ş.", "31 MART 2026 TARİHİ İTİBARIYLA
    # KONSOLİDE") is never a table row, but it carries a year — and that stray
    # cell was minting a phantom leading column in every table on the page.
    # Excluding it here keeps it captured (role=furniture) while removing it
    # from the grid.
    # A numbered note heading ends one table and introduces the next
    # ("15. Ertelenmiş Vergi Varlığına İlişkin Açıklamalar:"). It carries a
    # figure — its own section number — so block detection ran straight through
    # it and fused two tables with DIFFERENT column geometry into one grid.
    section_idx = frozenset(
        i for i, t in enumerate(line_text)
        if t.rstrip().endswith(":") and len(t) >= _SECTION_HEADING_MIN
        and sum(1 for _x0, _x1, tok in raw[i][1] if _is_value(tok)) <= 1)
    excluded = note_idx | section_idx | frozenset(
        i for i, t in enumerate(line_text) if _fold(t) and _fold(t) in furniture)
    candidates = _detect_blocks(raw, excluded)
    # A candidate run only becomes a table once its rows actually REACH its last
    # column. The wrapped continuation lines of a long footnote quote figures at
    # scattered x, so they cluster into a nominal grid but almost never populate
    # its terminal column — which is how "(***) …" spilling over three lines was
    # being promoted to a second table and stealing the notes below it.
    block_line_idx: list[list[int]] = []
    block_cols: dict[int, list[float]] = {}
    for idxs in candidates:
        if not _has_substantial_figures(raw, idxs):
            continue
        cols = _infer_columns([raw[i][1] for i in idxs])
        if not _reaches_terminal(raw, idxs, cols):
            continue
        idxs = _trim_trailing_prose(raw, idxs, cols)
        if len(idxs) < _BLOCK_MIN_ROWS:
            continue
        # Checked on the TRIMMED run: trimming is what removes the narrative
        # tail from a real table, and asking before it would judge the block on
        # lines it is not going to keep.
        if _every_figure_is_inline(raw, idxs):
            continue
        block_line_idx.append(idxs)
        block_cols[len(block_line_idx)] = cols

    # A row's label can wrap onto a line with NO figures at all ("Net dönem
    # zararı … ile TMS uyarınca" above "özkaynaklara yansıtılan kayıplar
    # 55.226.979"). Block detection only ever admits value-bearing lines, so that
    # first half was dropped from the table and the row rendered with half a
    # label. Absorb it here — after validation, so a text-only line cannot
    # influence whether the run counted as a table or where its columns are.
    claimed = {i for idxs in block_line_idx for i in idxs}

    def _free(j: int) -> bool:
        return (0 <= j < len(raw) and j not in claimed and j not in excluded
                and bool(line_text[j]))

    def _textonly(j: int) -> bool:
        """Line j is a label fragment: text, no figures, not already claimed."""
        return _free(j) and not any(_is_value(t) for _x0, _x1, t in raw[j][1])

    def _bare_marker(j: int) -> bool:
        """Line j is just a row number sitting on its own line.

        NSFR tables print a row as three lines — label head, the row number
        alone, then the label tail with the figures. The number is not text, so
        a text-only walk stopped at it and stranded the head above it.
        """
        toks = raw[j][1] if 0 <= j < len(raw) else []
        return (_free(j) and 0 < len(toks) <= 2
                and all(_is_value(t) for _x0, _x1, t in toks))

    for idxs in block_line_idx:
        for i in list(idxs):
            here = _split_label(raw[i][1]).lstrip()
            figures_only = not any(c.isalpha() for c in here)
            j = i - 1
            # Evaluate BEFORE claiming j: both predicates require j to be
            # unclaimed, so asking after the claim always answers False.
            j_is_marker = _bare_marker(j)
            if _textonly(j) or j_is_marker:
                above = _split_label(raw[j][1]).lstrip()
                # Signals that line j is the HEAD of this row's label: this line
                # resumes in lower case; an opener above whose row continues here
                # ("II. İTFA EDİLMİŞ MALİYETİ…" / "VARLIKLAR (Net)"); or this
                # line is figures-only, so it has no label of its own.
                #
                # These must stay EXACTLY the conditions under which _logical_rows
                # will bind the pair. A looser test (e.g. "the line above is long,
                # so it probably wrapped") pulls captions and prose into the table
                # that the merge then declines to bind, and each one surfaces as
                # an empty row — 80 → 180 of them on one filing when tried.
                if (figures_only or _resumes_lowercase(here)
                        or (_ROW_OPENER.match(above) and not _ROW_OPENER.match(here))):
                    idxs.append(j)
                    claimed.add(j)
                    # Keep walking up past a stranded row number to reach the
                    # label head above it ("…özkaynak unsurları ve" / "13" /
                    # "yükümlülükler 5.564.558 …").
                    if j_is_marker and _textonly(j - 1):
                        idxs.append(j - 1)
                        claimed.add(j - 1)
            # A figures-only line's label can also continue BELOW it — TSKB
            # prints "…Through Other" / "(4) 17.871.217 …" / "Comprehensive
            # Income" as one row. Without this the tail was left as prose.
            if figures_only and _textonly(i + 1):
                idxs.append(i + 1)
                claimed.add(i + 1)
        idxs.sort()

    line_block: dict[int, int] = {}
    heading_lines: set[int] = set()
    taken: set[int] = set()
    for bi, idxs in enumerate(block_line_idx, start=1):
        for i in idxs:
            line_block[i] = bi
        taken.update(idxs)

    # --- cells first, so logical rows can be inferred from their columns ---
    line_cells: dict[int, list[Cell]] = {}
    for i, (_y, toks) in enumerate(raw):
        order = i + 1
        bid = line_block.get(i)
        cols = block_cols.get(bid, []) if bid else []
        ci = 0
        out: list[Cell] = []

        def _col_of(x1: float) -> int | None:
            if not cols:
                return None
            dist, best = min((abs(x1 - cx), k) for k, cx in enumerate(cols))
            return best if dist <= _COL_TOLERANCE * 2 else None

        for x0, x1, t in toks:
            if not _is_value(t):
                continue
            out.append(Cell(
                line_order=order, cell_index=ci, col_index=_col_of(x1),
                x0=float(x0), x1=float(x1), text=t,
                is_numeric=_is_numeric(t), value=parse_cell(t),
            ))
            ci += 1
        # A column can hold TEXT. The board-of-directors table prints "Süleyman
        # Sözen | Chairman | 29.05.1997 | University | 45 years" — five columns,
        # every boundary a wide channel, of which only the date and "45" are
        # values. Clustering values alone saw two columns and dropped
        # "Chairman" and "University" entirely; they survived only by accident,
        # swallowed into an over-long row label, until that was fixed.
        #
        # Captured additively: existing value cells and the inferred columns are
        # untouched, so the statement tables are unaffected. A text field that
        # matches no value-derived column keeps `col_index=None` — recorded but
        # unplaced, which is honest about what the geometry proved.
        fields = _channel_fields(toks)
        for x0, x1, text in fields[1:] if len(fields) > 1 else []:
            words = text.split()
            # Skip only a field that is ENTIRELY figures — those were emitted
            # above, one cell per value. A MIXED field is printed prose and has
            # to be kept whole: Akbank's capital-instrument disclosure answers
            # "Aracın muhasebesel olarak takip edildiği hesap" with "Sermaye
            # Benzeri Krediler (347011 Muhasebe Hesabı)", and testing for any
            # figure at all reduced that answer to the fragment "(347011".
            if words and all(_is_value(w) for w in words):
                continue
            out.append(Cell(
                line_order=order, cell_index=ci, col_index=_col_of(x1),
                x0=float(x0), x1=float(x1), text=text,
                is_numeric=False, value=None,
            ))
            ci += 1
        out.sort(key=lambda c: c.x0)
        line_cells[i] = out
        cap.cells.extend(out)

    line_labels = {i: _split_label(toks) for i, (_y, toks) in enumerate(raw)}
    logical = _logical_rows(block_line_idx, block_cols, line_cells, line_labels)

    # --- drop narrative that landed inside a table ------------------------
    # A block can bridge two tables with prose between them ("Bulunmamaktadır
    # (31 Aralık 2023: Bulunmamaktadır).", "Grup, 31 Aralık 2024 tarihi
    # itibarıyla…"). Those lines carry figures inside sentences, so they pass
    # every structural test, but once rows are bound they stand out exactly:
    # a whole logical row with NO cell in any column, reading as a sentence.
    # Trimming only the block's tail could not reach them.
    drop = _prose_rows(raw, block_line_idx, block_cols, logical, line_cells, line_labels)
    if drop:
        for bi, idxs in enumerate(block_line_idx, start=1):
            block_line_idx[bi - 1] = [i for i in idxs if i not in drop]
        for i in drop:
            line_block.pop(i, None)
            taken.discard(i)
            logical.pop(i, None)
            # A cell outside every table has no column.
            line_cells[i] = [dataclasses.replace(c, col_index=None)
                             for c in line_cells.get(i, [])]
        cap.cells = [c for i in sorted(line_cells) for c in line_cells[i]]
        block_line_idx[:] = [b for b in block_line_idx if len(b) >= _BLOCK_MIN_ROWS]
        line_block.clear()
        for bi, idxs in enumerate(block_line_idx, start=1):
            for i in idxs:
                line_block[i] = bi

    # --- drop columns no row fills ------------------------------------------
    # A column is inferred from value edges BEFORE prose rows are dropped and
    # before cells are matched to it within tolerance, so a cluster can survive
    # with nothing in it: a figure inside a row label ("Less than 1 Year",
    # "Longer than 5 Years") mints one in the label region, and Garanti p131
    # carried two 8pt apart that no row could reach. Pruning here rather than by
    # refusing the edge is what makes it safe — only an empty column goes, and
    # the surviving cells keep their order.
    for bi, idxs in enumerate(block_line_idx, start=1):
        cols = block_cols.get(bi) or []
        if not cols:
            continue
        held = defaultdict(list)
        for i in idxs:
            for c in line_cells.get(i, []):
                if c.col_index is not None:
                    held[c.col_index].append((i, c))
        used = set(held)
        # A column ONE row reaches is real often enough to keep by default — a
        # footnote-reference column carries a value on 4 of 38 rows on TSKB's
        # balance sheet — so it goes only on evidence that its single cell was
        # never a cell: a figure sitting inside the row's own label ("Less than
        # 1 Year" → 1, "II. TMS 8 Uyarınca" → 8), or a section marker that is
        # the row's numbering ("9.3.", "5.10.2"). A lone real amount stays.
        for k, items in held.items():
            if len(items) != 1:
                continue
            i, cell = items[0]
            toks = raw[i][1]
            at = next((n for n, (x0, _x1, t) in enumerate(toks)
                       if t == cell.text and abs(x0 - cell.x0) < 0.5), None)
            inline = (at is not None and at > 0
                      and (toks[at][0] - toks[at - 1][1]) < _COLUMN_CHANNEL_PT)
            if inline or _ROW_OPENER.match(cell.text):
                used.discard(k)
        if len(used) == len(cols):
            continue
        keep = [k for k in range(len(cols)) if k in used]
        if not keep:
            continue
        remap = {old: new for new, old in enumerate(keep)}
        block_cols[bi] = [cols[k] for k in keep]
        for i in idxs:
            # `.get` — a pruned column may still HOLD its cell (the phantom's
            # single figure). The cell is kept, unplaced: it is printed on the
            # page, it just never belonged to a column.
            line_cells[i] = [
                dataclasses.replace(c, col_index=remap.get(c.col_index))
                if c.col_index is not None else c
                for c in line_cells.get(i, [])
            ]
    cap.cells = [c for i in sorted(line_cells) for c in line_cells[i]]

    for bi, idxs in enumerate(block_line_idx, start=1):
        heading, hidx = _heading_for(raw, idxs[0], taken)
        heading_lines.update(hidx)
        cols = block_cols.get(bi, [])
        cell_count = sum(1 for i in idxs for _x0, _x1, t in raw[i][1] if _is_value(t))
        cap.blocks.append(Block(
            page=page_number, block_id=bi, first_line=idxs[0] + 1,
            last_line=idxs[-1] + 1, n_cols=len(cols), col_x=tuple(cols),
            col_labels=tuple(_column_labels(raw, idxs, cols,
                                             _header_candidates(raw, idxs[0], hidx, taken))),
            heading=heading, row_count=len(idxs), cell_count=cell_count,
        ))

    # --- lines --------------------------------------------------------------
    # `note_seeds` accumulates (first_line, marker, [text parts]). A footnote's
    # text routinely wraps over several lines with no marker of its own, so a
    # line that follows one — and is neither table nor furniture nor a new note —
    # continues it. Without this the stored note is truncated at its first line,
    # which is exactly where the qualifying detail usually starts.
    note_seeds: list[tuple[int, str | None, list[str]]] = []
    open_note = False
    for i, (y, toks) in enumerate(raw):
        order = i + 1
        text = " ".join(t for _x0, _x1, t in toks).strip()
        label = _split_label(toks)
        numeric = sum(1 for _x0, _x1, t in toks if _is_numeric(t))
        bid = line_block.get(i)
        # `note_idx` — not a bare regex match — decides what opens a footnote, so
        # the numbered-marker confirmation in _note_lines governs the ROLE and
        # the stored note, not merely where a table stops.
        note_m = _NOTE_START.match(text) if i in note_idx else None
        folded = _fold(text)
        if folded and folded in furniture:
            role = ROLE_FURNITURE
            open_note = False
        elif note_m:
            role = ROLE_FOOTNOTE
        elif bid is not None:
            role = ROLE_DATA
            open_note = False
        elif i in heading_lines:
            role = ROLE_HEADING
            open_note = False
        elif text.strip().isdigit() and not _inside_block(i, block_line_idx):
            # A bare integer alone on a line is usually the page number — but
            # inside a table it is a ROW number whose label and figures wrapped
            # onto neighbouring lines (ALBRK's NSFR rows 16 and 18 print exactly
            # that way). Calling those furniture deleted the row's identity, so
            # the test is scoped to lines outside every table's span.
            role = ROLE_FURNITURE
            open_note = False
        elif open_note and text:
            role = ROLE_FOOTNOTE             # continuation of the note above
        else:
            role = ROLE_PARAGRAPH
            open_note = False
        if role == ROLE_FOOTNOTE:
            if note_m:
                note_seeds.append(
                    (order, note_m.group(1) or note_m.group(2), [text]))
                open_note = True
            elif note_seeds:
                note_seeds[-1][2].append(text)
        # A note line's own leading marker is not a reference to itself.
        markers = () if role == ROLE_FOOTNOTE else _row_markers(text)
        cap.lines.append(Line(
            page=page_number, line_order=order, y=float(y),
            x0=float(toks[0][0]), x1=float(max(t[1] for t in toks)),
            text=text, label=label, role=role, block_id=bid,
            logical_row=logical.get(i), numeric_count=numeric, markers=markers,
            line_hash=_line_digest((text,)), shape_hash=_line_digest((_shape(text),)),
        ))

    # --- notes, linked to the rows that carry their marker -----------------
    # A footnote belongs to the nearest table block ABOVE it; its marker is then
    # matched against the markers printed in that block's row labels. Scoping the
    # search to one block is what keeps a "(*)" under one table from claiming a
    # "(*)" row under a different table on the same page.
    # Each table's region runs from just after the previous table on the page.
    region_start: dict[int, int] = {}
    prev_end = 0
    for b in cap.blocks:
        region_start[b.block_id] = prev_end + 1
        prev_end = b.last_line

    for n, (order, marker, parts) in enumerate(note_seeds, start=1):
        owner = None
        for b in cap.blocks:
            if b.last_line <= order and (owner is None or b.last_line > owner.last_line):
                owner = b
        linked: tuple[int, ...] = ()
        if marker and owner is not None:
            linked = tuple(
                ln.line_order for ln in cap.lines
                if ln.block_id == owner.block_id and marker in ln.markers
            )
            if not linked:
                # The marker may sit on the table's COLUMN HEADER rather than on
                # any row — "Krediler (*) Karşılıklar", "Değer Farkı (*) Kısım
                # (**)" — in which case the note explains a column. Header lines
                # are not block members, so widen the search to this table's
                # REGION: from the end of the previous table on the page down to
                # this one's last line. A fixed three-line lookback was too
                # short — headers wrap and sit five or six lines up — while the
                # previous block is a bound that cannot reach another table.
                lo = region_start.get(owner.block_id, 1)
                linked = tuple(
                    ln.line_order for ln in cap.lines
                    if lo <= ln.line_order <= owner.last_line
                    and ln.block_id is None
                    and f"({marker})" in ln.text
                )
            if not linked:
                # Last resort: the whole page. Footnotes are printed once at the
                # foot and qualify EVERY table above them — on the maturity page
                # a single set of six notes covers three blocks, so five of the
                # six referred to rows outside the block they were filed under.
                # A marker is unique within a page in these filings, so widening
                # this far cannot cross-link two different notes.
                linked = tuple(
                    ln.line_order for ln in cap.lines
                    if ln.role != ROLE_FOOTNOTE and f"({marker})" in ln.text
                )
        elif marker and set(marker) == {"*"}:
            # A note that owns no TABLE can still qualify a printed line, and
            # every link above was gated on having a block. Garanti's ratings
            # pages carry "(*) Latest date in risk ratings or outlooks" under
            # "MOODY'S (October 2025) (*)" with no table on the page at all, so
            # the relationship the filing prints was recorded nowhere.
            #
            # Only star markers. "(1)" and "(i)" are also legal citations —
            # Halkbank prints "Clause 2, Paragraph (1) and (2) of the
            # Regulation" as ordinary text — and linking a note to those would
            # invent a reference the filing does not make. A star is never
            # anything but a footnote mark.
            linked = tuple(
                ln.line_order for ln in cap.lines
                if ln.role != ROLE_FOOTNOTE and f"({marker})" in ln.text
            )
        cap.notes.append(Note(
            page=page_number, note_order=n, marker=marker,
            text=_SPACE_RX.sub(" ", " ".join(parts)).strip(),
            block_id=owner.block_id if owner else None, linked_line_orders=linked,
        ))
    # A page that yielded a table is readable by construction; only ask about
    # the ones that did not, which keeps the drawings parse off the hot path.
    if not cap.blocks:
        cap.text_layer = _probe_text_layer(page, word_count)
    return cap


def _furniture_lines(doc) -> frozenset[str]:
    """Folded text of lines that repeat across most pages — the running header,
    the date banner, the "(Tutarlar … bin Türk Lirası …)" unit caption. Marked
    rather than dropped: they are how a page proves which period and unit it is
    denominated in, so a consumer may want them, but they must not be mistaken
    for table content."""
    seen: Counter = Counter()
    n = len(doc)
    if n < 4:
        return frozenset()
    for i in range(n):
        raw, _rot = _page_word_lines(doc[i])
        for _y, toks in raw:
            text = " ".join(t for _x0, _x1, t in toks)
            # Only TEXT lines can be running furniture. An all-zero data row
            # ("0 0 0 0 0 0") recurs on most pages of a filing and was being
            # classified as the page banner — which then split its table in two,
            # because furniture is excluded from blocks.
            if not any(c.isalpha() for c in text):
                continue
            folded = _fold(text)
            if len(folded) >= 8:
                seen[folded] += 1
    threshold = max(3, int(n * _FURNITURE_PAGE_FRACTION))
    return frozenset(k for k, c in seen.items() if c >= threshold)


def _inherit_column_labels(cap: DocumentCapture) -> None:
    """Carry a table's column headers onto its continuation blocks.

    A statement that runs past the foot of a page — or past an intervening
    caption — prints its header ONCE. Every block after the first therefore has
    no header of its own and renders as "c0 c1 c2 …" even though it is the same
    table with the same columns.

    Columns are matched by their x position rather than by index or count: a
    continuation page often drops a column the first page had (TSKB's footnote
    column appears on pages 4-5 but not 6), so the counts differ while the
    remaining columns sit at exactly the same x. Requiring most columns to find
    a match keeps an unrelated table from inheriting the wrong names.
    """
    import dataclasses

    last: Block | None = None
    for page in cap.pages:
        for pos, blk in enumerate(page.blocks):
            if blk.col_labels:
                last = blk
                continue
            if last is None or not blk.n_cols:
                continue
            inherited: list[str] = []
            hits = 0
            for cx in blk.col_x:
                best, label = _COL_TOLERANCE * 2, ""
                for k, px in enumerate(last.col_x):
                    if abs(px - cx) <= best and k < len(last.col_labels):
                        best, label = abs(px - cx), last.col_labels[k]
                        hits += 1
                inherited.append(label)
            if hits >= max(2, len(blk.col_x) * 0.6) and any(inherited):
                page.blocks[pos] = dataclasses.replace(
                    blk, col_labels=tuple(inherited))


def capture_document(pdf_path: str | Path) -> DocumentCapture:
    """Capture every page of one filing. Read-only; opens the PDF twice (once to
    learn the running furniture, once to capture) because a line can only be
    known to repeat after the whole document has been seen."""
    if not _HAS_FITZ:
        raise RuntimeError("PyMuPDF (fitz) is required for document capture")
    path = str(pdf_path)
    doc = fitz.open(path)
    try:
        furniture = _furniture_lines(doc)
        cap = DocumentCapture(pdf_path=path, page_count=len(doc))
        for i in range(len(doc)):
            cap.pages.append(capture_page(doc[i], i + 1, furniture))
        _inherit_column_labels(cap)
    finally:
        doc.close()
    if cap.line_count == 0:
        cap.status = "unreadable"
    elif cap.unreadable_page_count:
        # Some of this filing was legible on paper and unreadable to us —
        # vector outlines or an imaged content zone alike. Say so in the status
        # rather than letting the row count imply full coverage.
        cap.status = "partial"
    return cap


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    target = sys.argv[1] if len(sys.argv) > 1 else \
        "data/eye/AKBNK_2026Q1_consolidated.pdf"
    c = capture_document(target)
    print(f"{Path(c.pdf_path).name}: {c.page_count} pages, {c.line_count} lines, "
          f"{c.cell_count} cells, {c.block_count} blocks on {c.table_page_count} pages, "
          f"{c.note_count} notes  [{c.status}]")
