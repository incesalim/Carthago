"""Triage a FAILING partition into a named cause — deterministic, read-only.

A validator failure says an identity broke. It does not say *why*, and the why
has always been one of a small, recurring set of mechanical causes: the anchor
landed on the wrong page, the cell wrapped, the columns slipped, the page is
drawn rather than typed, the filing switched reporting units, the label ate its
own digits, the PDF behind the R2 key is the wrong filing — or the bank's own
printed statement simply does not foot, in which case nothing is wrong with us.

Every one of those is detectable from the PDF plus the stored rows, so this
module assigns the label mechanically. **No model is consulted and no number is
produced**: the output is a hypothesis with its evidence, for a human to act on.

The decisive test is whether each STORED figure is actually printed in the
filing. That, not the validator's arithmetic, is the evidence base:

    every stored figure printed  → we transcribed faithfully and the identity
                                   still breaks, so the SOURCE does not foot.
                                   Not an extraction bug.
    some stored figure absent    → we hold a number the filing never prints.
                                   A read defect, narrowed by the cell-level
                                   detectors below (wrapped / slipped / fused).
    most stored figures absent   → we are not looking at the right page, or at
                                   a readable page, at all.

`failed_detail`'s `expected` is deliberately *not* the pivot. It is a value the
validator DERIVED — for `Total = A + B` it is A + B computed from stored rows —
so a derived sum is usually absent from the page even when nothing is wrong with
the source, and treating its absence as a verdict yields a confident,
wrong "the bank's statement doesn't foot" on every ordinary misread component.
`expected` is used only as a search hint.

The first row above is the expensive one to get wrong in either direction, and
the one nobody can afford to check by hand: every entry in revalidate_audit_db's
skip-lists is a human having read a PDF to establish exactly this, and the rule
those lists carry — a skip is only ever justified when the data is verified
faithful and the source itself is inconsistent — is precisely what this
mechanises.

Read-only by construction: opens the local SQLite `mode=ro`, never writes a row,
never touches D1, never edits an extractor.
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

try:
    import fitz  # PyMuPDF — the only PDF engine in this repo (pdfplumber is banned)
    _HAS_FITZ = True
except ImportError:  # pragma: no cover - CI installs pymupdf
    _HAS_FITZ = False


# --------------------------------------------------------------------------
# Taxonomy. These labels are the ones every past fix in this repo actually
# landed on, so a triage note stays comparable with the write-ups in
# docs/knowledge/. Adding a label means adding a detector below.
# --------------------------------------------------------------------------
WRONG_PDF = "wrong_pdf"
DRAWN_PAGE = "drawn_page"
ROTATED_PAGE = "rotated_page"
ANCHOR_MISS = "anchor_miss"
UNIT_SWITCH = "unit_switch"
WRAPPED_CELL = "wrapped_cell"
DROPPED_CELL = "dropped_cell"
MISSING_ROW = "missing_row"
COLUMN_SLIP = "column_slip"
LABEL_DIGIT_FUSION = "label_digit_fusion"
TRAILING_DOT_HIERARCHY = "trailing_dot_hierarchy"
SOURCE_DEFECT = "source_defect"
UNCLASSIFIED = "unclassified"

#: Ordered worst-first. A note reports the whole cascade but leads with this.
#: DROPPED_CELL outranks the rest of the cell-level causes because it is the one
#: that can be *proved* from the page rather than inferred.
#: MISSING_ROW outranks SOURCE_DEFECT because it is the case that most easily
#: masquerades as one: every figure we hold can be printed exactly as stored and
#: the identity still break, simply because the row that would close it was never
#: extracted. Presence-checking stored values cannot see an absent row.
#: ROTATED_PAGE sits BELOW the cell-level causes: the extractor is already
#: rotation-aware, so a rotated page is context that accompanies a failure far
#: more often than it explains one. Ranked high it simply masked whatever was
#: really wrong.
SEVERITY_ORDER = [
    WRONG_PDF, DRAWN_PAGE, UNIT_SWITCH, ANCHOR_MISS,
    DROPPED_CELL, MISSING_ROW, COLUMN_SLIP, WRAPPED_CELL, LABEL_DIGIT_FUSION,
    TRAILING_DOT_HIERARCHY, ROTATED_PAGE, SOURCE_DEFECT, UNCLASSIFIED,
]

#: What each label implies for the person reading the note. Kept here so the
#: note and the docs cannot drift apart.
REMEDY = {
    WRONG_PDF: "Re-sync the filing: the object at this R2 key is a different report.",
    DRAWN_PAGE: "Page carries no text layer — transcribe by hand (data/manual_statements.json).",
    ROTATED_PAGE: "Page has /Rotate set AND data is missing. The extractor already "
                  "normalises rotation, so treat this as context, not the cause.",
    ANCHOR_MISS: "Locator picked the wrong page — widen or correct the anchor, not the parser.",
    UNIT_SWITCH: "Filing changed reporting unit; scale on ingest and re-check the period seam.",
    COLUMN_SLIP: "Right page, wrong column — fix the column mapping, not the number.",
    WRAPPED_CELL: "Value is word-wrapped inside its cell; get_text() splits it. Parser fix.",
    DROPPED_CELL: "A cell stored as 0 whose printed figure is exactly the identity's "
                  "shortfall — the extractor never read that column.",
    MISSING_ROW: "A row printed in the statement has no stored counterpart — the "
                 "identity closes on a line that was never extracted.",
    LABEL_DIGIT_FUSION: "Digits fused into item_name — the label/value split is misplaced.",
    TRAILING_DOT_HIERARCHY: "Hierarchy key differs from the printed marker by a trailing dot.",
    SOURCE_DEFECT: "The bank's own printed statement does not foot. Not an extraction bug — "
                   "verify, then record a skip with the reason.",
    UNCLASSIFIED: "No mechanical cause matched — needs a human read.",
}

# Columns that are never a reported figure, so never a triage subject.
_NON_VALUE_COLS = frozenset({
    "item_order", "source_page", "extracted_at", "validated_at", "derived_at",
    "checks_passed", "checks_failed", "checks_skipped", "is_manual", "is_modified",
    "row_count", "pdf_present", "sort_order", "section_rank",
})
# Columns that identify a row rather than carry a value.
_LABEL_COLS = ("item_name", "hierarchy", "currency", "sector", "section",
               "stage", "period_type", "statement")

_UNIT_THOUSAND = re.compile(r"BİN\s*T[LP]|BIN\s*T[LP]|THOUSAND", re.I)
_UNIT_MILLION = re.compile(r"MİLYON\s*T[LP]|MILYON\s*T[LP]|MILLION", re.I)


@dataclass(frozen=True)
class BrokenCheck:
    """One entry of bank_audit_validation.failed_detail."""
    check: str
    node: str
    expected: float | None
    actual: float | None
    diff: float | None

    @classmethod
    def from_json(cls, d: dict) -> BrokenCheck:
        def num(k):
            v = d.get(k)
            return float(v) if isinstance(v, (int, float)) else None
        return cls(str(d.get("check", "?")), str(d.get("node", "")),
                   num("expected"), num("actual"), num("diff"))


@dataclass
class PageFacts:
    """Everything the detectors need from one page, read once."""
    page1: int
    rotation: int = 0
    text_len: int = 0
    n_drawings: int = 0
    n_images: int = 0
    tokens: list[tuple[float, float, str]] = field(default_factory=list)
    rows: list[list[tuple[float, float, str]]] = field(default_factory=list)

    @property
    def flat_text(self) -> str:
        return " ".join(t[2] for t in self.tokens)

    def unit_hint(self) -> str | None:
        """'thousand' | 'million' | None, from the unit line filings print."""
        txt = self.flat_text
        if _UNIT_MILLION.search(txt):
            return "million"
        if _UNIT_THOUSAND.search(txt):
            return "thousand"
        return None

    def is_unreadable(self) -> bool:
        """Drawn, scanned or vector-only: reads fine to a human, empty to fitz.

        Marks of EITHER kind against a near-empty text layer — a page can be
        unreadable via DRAWINGS with zero images, which is the mechanism a
        naive `not text and images` test misses entirely.
        """
        return self.text_len < 60 and (self.n_drawings > 40 or self.n_images > 0)


@dataclass
class Finding:
    label: str
    detail: str
    page: int | None = None
    evidence: list[str] = field(default_factory=list)
    #: 'confirmed' when the PDF itself demonstrates it; 'likely' when inferred.
    confidence: str = "likely"

    def __str__(self) -> str:
        where = f" p{self.page}" if self.page else ""
        return f"[{self.label}{where}] {self.detail}"


@dataclass
class TriageNote:
    bank: str
    period: str
    kind: str
    statement: str
    checks: list[BrokenCheck] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    anchor_page: int | None = None
    best_page: int | None = None
    window: list[int] = field(default_factory=list)
    pdf_pages: int = 0
    error: str | None = None

    @property
    def partition(self) -> str:
        return f"{self.bank} {self.period} {self.kind} / {self.statement}"

    @property
    def verdict(self) -> str:
        """The single label this partition gets filed under."""
        if self.error:
            return UNCLASSIFIED
        got = {f.label for f in self.findings}
        for label in SEVERITY_ORDER:
            if label in got:
                return label
        return UNCLASSIFIED

    def to_dict(self) -> dict:
        return {
            "bank_ticker": self.bank, "period": self.period, "kind": self.kind,
            "statement": self.statement, "verdict": self.verdict,
            "anchor_page": self.anchor_page, "best_page": self.best_page,
            "window": self.window, "pdf_pages": self.pdf_pages, "error": self.error,
            "checks": [{"check": c.check, "node": c.node, "expected": c.expected,
                        "actual": c.actual} for c in self.checks],
            "findings": [{"label": f.label, "detail": f.detail, "page": f.page,
                          "confidence": f.confidence, "evidence": f.evidence}
                         for f in self.findings],
        }


# --------------------------------------------------------------------------
# Value matching. A figure printed in a Turkish filing can appear as
# 1.234.567 / 1,234,567 / 1234567, and negatives print parenthesised.
# --------------------------------------------------------------------------

def formatted_variants(v: float) -> list[str]:
    n = abs(int(round(v)))
    grouped = f"{n:,}"
    return [grouped, grouped.replace(",", "."), str(n)]


def _digits(v: float) -> str:
    return str(abs(int(round(v))))


def find_value(page: PageFacts, value: float) -> tuple[str, str | None]:
    """Locate one value on one page.

    Returns (verdict, evidence) where verdict is:
      'exact'   — a formatted variant is printed
      'wrapped' — printed, but word-wrapped inside its cell so get_text() emits
                  a prefix token and the remaining digits separately. Position
                  is not cell membership, so this fools coordinate parsers and
                  text models alike.
      'absent'  — not on this page in any form
    """
    if value is None:
        return "absent", None
    toks = [t[2] for t in page.tokens]
    text = " ".join(toks)
    for f in formatted_variants(value):
        if f in text:
            return "exact", f

    want = _digits(value)
    if len(want) < 6:                      # too short to judge a split safely
        return "absent", None
    for i, t in enumerate(toks):
        d = re.sub(r"\D", "", t)
        if not d or len(d) >= len(want) or not want.startswith(d):
            continue
        if len(d) < len(want) - 3:         # a genuine prefix, not a coincidence
            continue
        rest = want[len(d):]
        for j in range(i + 1, min(i + 6, len(toks))):
            if re.sub(r"\D", "", toks[j]) == rest:
                return "wrapped", f"{t!r} + {toks[j]!r}"
    return "absent", None


def find_scaled(page: PageFacts, value: float) -> tuple[float, str] | None:
    """The value printed at a different power of ten — the unit-switch shape."""
    for factor in (1000.0, 1 / 1000.0):
        scaled = value * factor
        if not judgeable(scaled):     # a 3-digit "match" is noise, not evidence
            continue
        verdict, ev = find_value(page, scaled)
        if verdict == "exact":
            return factor, ev or ""
    return None


#: Below six digits a figure is not distinctive enough for presence-matching to
#: mean anything: a statement page prints hundreds of short numbers, so "743 is
#: on the page" is satisfied by chance. Ratios (15.62), branch counts (711) and
#: headcounts fall below this line and are reported as unjudgeable rather than
#: silently treated as absent — which would manufacture an extraction defect.
_MIN_JUDGEABLE = 100_000


def judgeable(value: float | None) -> bool:
    return value is not None and abs(value) >= _MIN_JUDGEABLE


@dataclass(frozen=True)
class CellCheck:
    """One stored figure, checked against the filing."""
    label: str          # row identity, for the note
    column: str         # DB column it was stored in
    value: float
    verdict: str        # 'exact' | 'wrapped' | 'absent' | 'unjudgeable' | 'zero'
    page: int | None = None
    evidence: str | None = None


def find_in_window(window: list[PageFacts], value: float) -> tuple[str, int | None, str | None]:
    """Locate a value anywhere in the statement's page window.

    A BRSA statement is routinely printed across several pages — the §4 capital
    table runs CET1, then AT1/Tier1, then RWA over three consecutive pages — so
    judging a partition against a single "best" page marks two thirds of its own
    figures absent and manufactures an extraction defect out of normal pagination.
    """
    best: tuple[str, int | None, str | None] = ("absent", None, None)
    for facts in window:
        verdict, ev = find_value(facts, value)
        if verdict == "exact":
            return "exact", facts.page1, ev
        if verdict == "wrapped" and best[0] == "absent":
            best = ("wrapped", facts.page1, ev)
    return best


def audit_stored_values(window: list[PageFacts], rows: list,
                        cols: list[str]) -> list[CellCheck]:
    """Check every stored figure for this partition against the page window.

    This is the evidence base for every verdict below: what we hold versus what
    the filing actually prints.
    """
    out: list[CellCheck] = []
    for r in rows:
        keys = r.keys()
        label = " ".join(str(r[k]) for k in _LABEL_COLS if k in keys and r[k])[:70] or "-"
        for col in cols:
            if col not in keys:
                continue
            v = r[col]
            if not isinstance(v, (int, float)):
                continue                      # NULL: a disclosure never made
            if v == 0:
                # A stored 0 is not checkable by presence, but it is the single
                # most common shape of a dropped cell, so it is carried through
                # rather than discarded — see detect_dropped_cell.
                out.append(CellCheck(label, col, 0.0, "zero"))
                continue
            if not judgeable(v):
                out.append(CellCheck(label, col, float(v), "unjudgeable"))
                continue
            verdict, page, ev = find_in_window(window, float(v))
            out.append(CellCheck(label, col, float(v), verdict, page, ev))
    return out


# --------------------------------------------------------------------------
# Column geometry. Numeric tokens on a statement page cluster into vertical
# bands, one per reported column. Knowing which band a figure sits in is what
# separates "we read the wrong number" from "we read the right number from the
# wrong column" — a distinction no arithmetic identity can make on its own.
# --------------------------------------------------------------------------

_NUM_TOKEN = re.compile(r"^\(?-?[\d.,]{3,}\)?$")


def column_bands(page: PageFacts, tol: float = 14.0) -> list[tuple[float, float]]:
    """Cluster numeric-token x-centres into column bands, left to right."""
    centres = sorted((t[0] + t[1]) / 2 for t in page.tokens
                     if _NUM_TOKEN.match(t[2]) and any(c.isdigit() for c in t[2]))
    if not centres:
        return []
    bands: list[list[float]] = [[centres[0]]]
    for c in centres[1:]:
        if c - bands[-1][-1] <= tol:
            bands[-1].append(c)
        else:
            bands.append([c])
    # A real column has several figures in it; a stray label number does not.
    return [(min(b), max(b)) for b in bands if len(b) >= 3]


def band_of(page: PageFacts, value: float) -> int | None:
    """Index of the column band a value is printed in, or None."""
    bands = column_bands(page)
    if not bands:
        return None
    variants = set(formatted_variants(value))
    for x0, x1, txt in page.tokens:
        if txt.strip("()") in variants or txt in variants:
            centre = (x0 + x1) / 2
            for i, (b0, b1) in enumerate(bands):
                if b0 - 14 <= centre <= b1 + 14:
                    return i
    return None


# --------------------------------------------------------------------------
# PDF access
# --------------------------------------------------------------------------

def read_page(pdf_path: str | Path, page1: int) -> PageFacts | None:
    """Read one 1-indexed page into PageFacts. None if out of range."""
    if not _HAS_FITZ:
        return None
    doc = fitz.open(str(pdf_path))
    try:
        if not (1 <= page1 <= doc.page_count):
            return None
        page = doc[page1 - 1]
        words = page.get_text("words")
        facts = PageFacts(
            page1=page1,
            rotation=int(getattr(page, "rotation", 0) or 0),
            text_len=len(page.get_text().strip()),
            n_drawings=len(page.get_drawings()),
            n_images=len(page.get_images(full=True)),
            tokens=[(w[0], w[2], w[4]) for w in words],
        )
        rows: dict[int, list[tuple[float, float, str]]] = defaultdict(list)
        for w in words:
            rows[int(round(w[1]))].append((w[0], w[2], w[4]))
        facts.rows = [sorted(rows[y], key=lambda t: t[0]) for y in sorted(rows)]
        return facts
    finally:
        doc.close()


def page_count(pdf_path: str | Path) -> int:
    if not _HAS_FITZ:
        return 0
    doc = fitz.open(str(pdf_path))
    try:
        return doc.page_count
    finally:
        doc.close()


def render_page(pdf_path: str | Path, page1: int, dest: str | Path, dpi: int = 110) -> bool:
    """Rasterise one page next to the note, so the hypothesis can be eyeballed."""
    if not _HAS_FITZ:
        return False
    doc = fitz.open(str(pdf_path))
    try:
        if not (1 <= page1 <= doc.page_count):
            return False
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        doc[page1 - 1].get_pixmap(dpi=dpi).save(str(dest))
        return True
    finally:
        doc.close()


# --------------------------------------------------------------------------
# Stored-row access
# --------------------------------------------------------------------------

def value_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    """Numeric columns of `table` that carry a reported figure."""
    cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [c[1] for c in cols
            if c[2].upper() in ("REAL", "INTEGER", "NUMERIC")
            and c[1] not in _NON_VALUE_COLS]


def stored_rows(conn: sqlite3.Connection, table: str, bank: str, period: str,
                kind: str, statement: str | None = None) -> list[sqlite3.Row]:
    sql = (f"SELECT * FROM {table} WHERE bank_ticker=? AND period=? AND kind=?")
    args: list = [bank, period, kind]
    cols = {c[1] for c in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if statement and "statement" in cols:
        sql += " AND statement=?"
        args.append(statement)
    if "item_order" in cols:
        sql += " ORDER BY item_order"
    return conn.execute(sql, args).fetchall()


def stored_source_page(conn: sqlite3.Connection, table: str, bank: str,
                       period: str, kind: str) -> int | None:
    cols = {c[1] for c in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if "source_page" not in cols:
        return None
    r = conn.execute(
        f"SELECT source_page FROM {table} WHERE bank_ticker=? AND period=? AND kind=? "
        f"AND source_page IS NOT NULL LIMIT 1", (bank, period, kind)).fetchone()
    return int(r[0]) if r and r[0] else None


# --------------------------------------------------------------------------
# Detectors. Each returns Findings; none of them mutates anything.
# --------------------------------------------------------------------------

def detect_wrong_pdf(pdf_path: str | Path, bank: str, period: str) -> Finding | None:
    """Does the filing behind this R2 key name this bank and this period?

    The third mechanism behind an "empty" extraction, after a drawn page and a
    missed anchor: the object is simply a different report, and every downstream
    symptom looks like a parser bug.
    """
    facts = read_page(pdf_path, 1)
    if facts is None or facts.text_len < 40:
        return None                                # cover may legitimately be an image
    head = facts.flat_text.upper()
    year, q = period[:4], period[4:]
    if year and year not in head:
        # The year is on nearly every cover; its absence with a readable cover is
        # the signal. Report the first line so a human can confirm in one glance.
        first = " ".join(t[2] for t in facts.rows[0]) if facts.rows else ""
        return Finding(WRONG_PDF, f"cover does not mention {year}", page=1,
                       evidence=[f"cover line 1: {first[:110]!r}", f"expected period {period}"],
                       confidence="likely")
    _ = q
    return None


def detect_page_defects(facts: PageFacts, values_missing: bool = True) -> list[Finding]:
    """Page-level causes. `values_missing` gates the ones that only matter when
    something actually failed to come through."""
    out: list[Finding] = []
    if facts.rotation and values_missing:
        # The extractor already maps bboxes through page.rotation_matrix
        # (extractor.py `_fitz_page_text`, and equity_change's rotation-aware
        # scan), so a rotated page is NOT a defect on its own — most rotated
        # pages in this corpus extract fine. Reporting it unconditionally
        # promoted "this page is landscape" to a diagnosis and masked the real
        # cause underneath it. It is context, and only when data is missing.
        out.append(Finding(
            ROTATED_PAGE, f"/Rotate {facts.rotation}, and figures are missing — worth "
            f"ruling out as a layout cause, though the extractor is already "
            f"rotation-aware so this is context rather than a diagnosis",
            page=facts.page1,
            evidence=[f"page.rotation = {facts.rotation}"], confidence="likely"))
    if facts.is_unreadable():
        out.append(Finding(
            DRAWN_PAGE, "page is drawn/scanned: it reads fine to a human and "
            "returns nothing from get_text()", page=facts.page1,
            evidence=[f"text_len={facts.text_len}", f"drawings={facts.n_drawings}",
                      f"images={facts.n_images}"], confidence="confirmed"))
    return out


def detect_unit_switch(window: list[PageFacts], cells: list[CellCheck]) -> Finding | None:
    """Figures printed at a different power of ten than the ones we stored.

    ⚠️ This catches only the case where the stored SCALE disagrees with the print.
    It cannot catch the 2026Q2 sector-wide Bin→Milyon change, and nothing inside
    one filing can: when a filing switches unit and we ingest what it prints, the
    stored figure MATCHES the page exactly and every internal identity — all of
    them ratios of figures sharing a scale — still foots. Only a comparison
    against something outside the filing sees it, which is what
    scripts/watch_cross_period.py exists to do.

    Corroboration is mandatory. A single value that happens to match at ÷1000 is
    a coincidence, not a unit switch: a statement page is dense with figures, so
    for any 7-digit value some 4-digit token on the page will match its
    thousands-scaled form nearly always. Require several values agreeing on the
    SAME factor, and require them to be absent at their stored scale.
    """
    votes: dict[float, list[CellCheck]] = defaultdict(list)
    for c in cells:
        if c.verdict != "absent" or not judgeable(c.value):
            continue
        for facts in window:
            hit = find_scaled(facts, c.value)
            if hit:
                votes[hit[0]].append(c)
                break
    if not votes:
        return None
    factor, backing = max(votes.items(), key=lambda kv: len(kv[1]))
    if len(backing) < 3:
        return None
    direction = "×1000" if factor >= 1000 else "÷1000"
    hints = {f.unit_hint() for f in window} - {None}
    return Finding(
        UNIT_SWITCH,
        f"{len(backing)} stored figures are printed at {direction} their stored "
        f"scale — the filing's reporting unit differs from the one we ingested",
        page=window[0].page1 if window else None,
        evidence=[f"unit line reads {', '.join(sorted(hints)) or 'unstated'}"]
        + [f"{c.label} · {c.column}: stored {c.value:,.0f}, printed "
           f"{c.value * factor:,.0f}" for c in backing[:4]],
        confidence="confirmed" if len(backing) >= 5 else "likely")


def detect_label_digit_fusion(rows: list[sqlite3.Row]) -> Finding | None:
    """Digits that belong to a figure ended up inside item_name.

    A long run of digits inside a label means the label/value split landed in
    the wrong place, so the row's own figure is short by exactly those digits.
    """
    cols = rows[0].keys() if rows else []
    if "item_name" not in cols:
        return None
    bad = []
    for r in rows:
        name = r["item_name"] or ""
        # Ignore ordinary references — "(1)", "TFRS 9", section numbers.
        stripped = re.sub(r"\(\s*\d{1,2}\s*\)|\b\d{1,2}\b", "", name)
        m = re.search(r"\d[\d.,]{4,}", stripped)
        if m:
            bad.append(f"{(r['hierarchy'] if 'hierarchy' in cols else '') or '-'} "
                       f"{name[:60]!r} → {m.group(0)!r}")
    if not bad:
        return None
    return Finding(LABEL_DIGIT_FUSION,
                   f"{len(bad)} stored label(s) carry a figure's digits",
                   evidence=bad[:5], confidence="confirmed")


def detect_trailing_dot(rows: list[sqlite3.Row], facts: PageFacts | None) -> Finding | None:
    """Hierarchy keys that differ from the printed marker by a trailing dot.

    Harmless to read, fatal to a parent=Σchildren rollup: '1' and '1.' are two
    different nodes, so the children hang off a parent that does not exist.
    """
    cols = rows[0].keys() if rows else []
    if "hierarchy" not in cols:
        return None
    keys = [r["hierarchy"] for r in rows if r["hierarchy"]]
    if not keys:
        return None
    # A statement legitimately mixes styles — BRSA romans carry a dot ('I.', 'II.')
    # while their children do not ('2.1', '11.3'). Mixed styles are therefore NOT
    # the defect; the defect is the SAME node stored under two spellings, which is
    # what actually splits a parent from its children.
    forms: dict[str, set[str]] = defaultdict(set)
    for k in keys:
        forms[k.rstrip(".")].add(k)
    ambiguous = {base: v for base, v in forms.items() if len(v) > 1 and base}
    if not ambiguous:
        return None
    sample = list(ambiguous.items())[:4]
    return Finding(
        TRAILING_DOT_HIERARCHY,
        f"{len(ambiguous)} hierarchy node(s) are stored under two spellings that "
        f"differ only by a trailing dot — a parent=Σchildren rollup cannot tie "
        f"across the two forms",
        page=facts.page1 if facts else None,
        evidence=[f"{base!r} stored as {sorted(v)}" for base, v in sample],
        confidence="confirmed")


#: Row markers as the filings print them: BRSA romans, lettered sections, and
#: dotted decimals. The trailing lookahead admits a label that runs straight into
#: the marker — fitz emits "I.Önceki Dönem Sonu Bakiyesi" with no space, so a
#: marker pattern that insists on whitespace matches almost nothing on a real
#: statement page. Same allowance the extractor's own _LINE_HIER_RX makes.
_ROW_MARKER_RX = re.compile(
    r"^(?P<h>[IVX]{1,6}\.|[A-Z]\.|\d{1,2}(?:\.\d{1,2}){0,3}\.?)"
    r"(?=\s|$|[A-Za-zÇĞİÖŞÜçğıöşü(])")

_ROMAN_VALUE = {"I": 1, "V": 5, "X": 10}


def _roman_rank(key: str) -> int | None:
    """Ordinal of a BRSA roman marker, or None if it is not one."""
    s = key.rstrip(".")
    if not s or any(ch not in _ROMAN_VALUE for ch in s):
        return None
    total, prev = 0, 0
    for ch in reversed(s):
        v = _ROMAN_VALUE[ch]
        total += -v if v < prev else v
        prev = max(prev, v)
    return total


def printed_markers(pdf_path: str | Path, pages: list[int]) -> list[str]:
    """Row markers actually printed across the statement's pages, in order.

    Reads through the extractor's own page-text helper rather than a private
    reconstruction, so "what the filing prints" here means the same thing it
    means to the code being diagnosed. A triage that saw a different page than
    the extractor would produce confident findings about a document nobody else
    is reading.
    """
    from .extractor import _fitz_page_text

    seen: list[str] = []
    for p in pages:
        for line in _fitz_page_text(str(pdf_path), p - 1).split("\n"):
            m = _ROW_MARKER_RX.match(line.strip())
            if m and m.group("h") not in seen:
                seen.append(m.group("h"))
    return seen


def orphan_value_lines(pdf_path: str | Path, pages: list[int], stored: set[int],
                       min_values: int = 4) -> list[tuple[int, str, list[float]]]:
    """Printed lines of figures that no stored row accounts for.

    The label of a statement's closing row routinely wraps onto the END of the
    preceding row's line, leaving its figures on a line of their own with no
    marker at all. A marker-based check cannot see that row go missing — there is
    no marker to miss — but the orphaned figures are unmistakable: a run of
    values, none of which we hold.
    """
    out: list[tuple[int, str, list[float]]] = []
    for p in pages:
        for line in _statement_lines(pdf_path, p):
            nums = [v for tok in line.split()
                    if (v := _token_value(tok)) is not None]
            big = [v for v in nums if judgeable(v)]
            if len(nums) < min_values or not big:
                continue
            unheld = [v for v in big if int(round(v)) not in stored]
            if len(unheld) / len(big) >= 0.6:
                out.append((p, line.strip()[:90], unheld))
    return out


def _statement_lines(pdf_path: str | Path, page1: int) -> list[str]:
    from .extractor import _fitz_page_text
    return _fitz_page_text(str(pdf_path), page1 - 1).split("\n")


def _token_value(tok: str) -> float | None:
    """Parse one printed token as a figure, or None. Turkish grouping."""
    t = tok.strip().strip("()")
    if not t or not any(ch.isdigit() for ch in t):
        return None
    if not re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+(?:,\d+)?|-?\d+(?:,\d+)?", t):
        return None
    try:
        return abs(float(t.replace(".", "").replace(",", ".")))
    except ValueError:
        return None


def detect_missing_row(pdf_path: str | Path, window: list[PageFacts], rows: list,
                       cols: list[str], checks: list[BrokenCheck]) -> Finding | None:
    """A row the filing prints that we hold no counterpart for.

    The shape that hides behind a clean-looking extraction: every stored figure
    checks out against the page, so every value-level detector passes, and the
    identity still breaks because the line that closes it — a period-end balance,
    a total — was never extracted at all. The validator then closes the chain on
    whatever row happened to come last and reports an arithmetic mismatch that
    describes nothing. Left unlabelled this reads as `source_defect`, i.e. "the
    bank's statement is wrong", which is both false and the most expensive
    verdict to get wrong.
    """
    if not rows:
        return None
    pages = [f.page1 for f in window]
    stored_values = {int(round(r[c])) for r in rows for c in cols
                     if c in r.keys() and isinstance(r[c], (int, float)) and r[c]}

    # (a) A run of printed figures with no stored row behind it.
    orphans = orphan_value_lines(pdf_path, pages, stored_values)
    if orphans:
        p, line, unheld = orphans[0]
        closes = ""
        for c in checks:
            if c.actual is not None and any(
                    abs(v - abs(c.actual)) < 1 for v in unheld):
                closes = (f" The identity `{c.check}` closes on {abs(c.actual):,.0f}, "
                          f"which is one of them.")
                break
        return Finding(
            MISSING_ROW,
            f"p{p} prints a row of {len(unheld)} figures that no stored row holds — "
            f"the statement's closing line was never extracted.{closes}",
            page=p,
            evidence=[f"orphan line: {line!r}",
                      f"unheld figures: {', '.join(f'{v:,.0f}' for v in unheld[:6])}",
                      f"{len(orphans)} orphan line(s) across pages {pages}"],
            confidence="confirmed")

    # (b) A gap or truncated tail in the ROMAN spine. Romans are the statement's
    # top level and strictly ordered, so a gap there is unambiguous; decimal
    # sub-items are often legitimately absent (a bank with no 11.2 simply has
    # none), so counting those would fire constantly.
    if "hierarchy" not in rows[0].keys():
        return None
    stored_keys = {(r["hierarchy"] or "").rstrip(".") for r in rows}
    printed = printed_markers(pdf_path, pages)
    romans = [(k, n) for k in printed if (n := _roman_rank(k))]
    if len(romans) < 4:                       # not a roman-spined statement
        return None
    missing = [k for k, _ in romans if k.rstrip(".") not in stored_keys]
    if not missing:
        return None
    top_stored = max((_roman_rank(h) or 0 for h in stored_keys), default=0)
    tail = [k for k in missing if (_roman_rank(k) or 0) > top_stored]
    return Finding(
        MISSING_ROW,
        f"{len(missing)} row(s) printed in the statement have no stored counterpart "
        f"({', '.join(missing[:6])}) — "
        + ("the statement continues past the last row we stored"
           if tail else "a row inside the stored range has no counterpart"),
        page=pages[0] if pages else None,
        evidence=[f"printed markers: {', '.join(printed[:16])}",
                  f"highest stored roman: {top_stored}",
                  f"missing beyond the stored tail: {', '.join(tail) or 'none'}"],
        confidence="confirmed" if tail else "likely")


def detect_missing_auditor(pdf_path: str | Path, rows: list,
                           checks: list[BrokenCheck], scan_pages: int = 25) -> Finding | None:
    """`opinion_auditor_missing`: is the signature actually absent, or just late?

    The opinion lane is text, not figures, so the numeric evidence base below says
    nothing about it — and defaulting to a numeric verdict there would attach a
    confident label to a lane it never examined. The equivalent test is the same
    shape: read what the filing prints, and compare.

    The extractor reads only the front matter (audit_opinion.extract's
    `max_pages`), which is where the signature sits *when the opinion is short*. A
    qualified opinion carries a Basis paragraph that pushes the signature block
    further back, so "not captured" and "not present" are different claims — and
    the page number separates them.
    """
    if not any(c.check.startswith("opinion_") for c in checks):
        return None
    if not rows or "auditor" not in rows[0].keys() or rows[0]["auditor"]:
        return None
    # Imported eagerly and NOT guarded: a swallowed ImportError here would turn
    # every opinion partition into a silent "unclassified" that looks like a
    # finding rather than a broken detector.
    from .audit_opinion import _AUDITORS, extract_opinion_from_pdf

    # Read the real front-matter window off the extractor rather than restating
    # it, so widening it there cannot leave this diagnosis quietly stale.
    import inspect
    default = inspect.signature(extract_opinion_from_pdf).parameters["max_pages"].default
    front_window = default if isinstance(default, int) else 6

    n = min(scan_pages, page_count(pdf_path))
    for p in range(1, n + 1):
        facts = read_page(pdf_path, p)
        if facts is None:
            continue
        text = facts.flat_text
        for pat, name in _AUDITORS:
            if pat.search(text):
                if p > front_window:
                    return Finding(
                        ANCHOR_MISS,
                        f"the auditor ({name}) IS named on p{p}, but the opinion "
                        f"extractor only reads the first {front_window} pages — the "
                        f"signature is past its window, not absent from the filing",
                        page=p,
                        evidence=[f"matched firm {name} on p{p}",
                                  f"audit_opinion.extract max_pages={front_window}"],
                        confidence="confirmed")
                return Finding(
                    UNCLASSIFIED,
                    f"the auditor ({name}) is named on p{p}, inside the extractor's "
                    f"{front_window}-page window, yet was not captured — the parse, "
                    f"not the page range, is at fault",
                    page=p, evidence=[f"matched firm {name} on p{p}"],
                    confidence="confirmed")
    drawn = [p for p in range(1, min(8, n) + 1)
             if (f := read_page(pdf_path, p)) is not None and f.is_unreadable()]
    if drawn:
        return Finding(
            DRAWN_PAGE,
            f"no known audit firm appears in the first {n} pages and the front "
            f"matter is drawn rather than typed — the signature is an image",
            page=drawn[0], evidence=[f"unreadable pages {drawn}"], confidence="confirmed")
    return Finding(
        UNCLASSIFIED,
        f"no known audit firm name appears in the first {n} pages, and the text "
        f"layer is readable — the signature is likely a firm outside the known set",
        evidence=[f"{len(_AUDITORS)} firm patterns tried"], confidence="likely")


def detect_dropped_cell(window: list[PageFacts], cells: list[CellCheck],
                        checks: list[BrokenCheck]) -> Finding | None:
    """A cell stored as 0 whose real figure is printed and equals the shortfall.

    This is the one cause the filing can *prove* rather than merely suggest. When
    an identity is short by D, and |D| is printed in the statement, and the
    partition holds a 0 in a column that identity sums over, then the extractor
    read a column it should have read and got nothing — it did not misread a
    digit, it never saw the cell.

    It matters that this is separated from column_slip: the remedy differs. A slip
    is a mapping bug over data that was read; a dropped cell means the value never
    entered the pipeline, and a `0` written for it is the failure mode this repo
    treats as inventing data — a disclosure never made and a disclosed zero are
    different facts.
    """
    zeros = [c for c in cells if c.verdict == "zero"]
    if not zeros:
        return None
    for c in checks:
        if c.diff is None or not judgeable(abs(c.diff)):
            continue
        # When the stored side is 0 the shortfall IS the required figure, so
        # "the shortfall is printed" restates "the figure the identity wants is
        # printed" and proves nothing about which cell went missing. Those cases
        # belong to missing_row / column_slip, which can still say something
        # specific; claiming a dropped column here would attach a confident
        # remedy to whichever unrelated zeros the partition happens to hold.
        if not c.actual:
            continue
        verdict, page, ev = find_in_window(window, abs(c.diff))
        if verdict != "exact":
            continue
        # Name only the zeros the broken identity plausibly sums over: a node
        # reads "Tier1 = CET1 + AT1", so match its words against the columns.
        # Digits are stripped from BOTH sides — the node writes "Tier1" and the
        # column writes "tier1", and a comparison that keeps them never matches.
        node_words = set(re.findall(r"[a-z]+", c.node.lower()))
        suspect = [z for z in zeros
                   if node_words & {re.sub(r"\d+", "", part)
                                    for part in z.column.lower().split("_")}]
        targeted = bool(suspect)
        suspect = suspect or zeros
        return Finding(
            DROPPED_CELL,
            f"`{c.check}` is short by {abs(c.diff):,.0f}, and {abs(c.diff):,.0f} is "
            f"printed in the filing — while this partition stores 0 in "
            f"{', '.join(sorted({z.column for z in suspect}))}. The extractor never "
            f"read that column",
            page=page,
            evidence=[f"node {c.node}",
                      f"stored {c.actual:,.0f}, identity requires {c.expected:,.0f}"
                      if c.expected is not None else f"diff {c.diff}",
                      f"shortfall printed on p{page} as {ev!r}"]
            + [f"stored zero: {z.label} · {z.column}" for z in suspect[:3]],
            confidence="confirmed" if targeted else "likely")
    return None


def classify_partition(window: list[PageFacts], cells: list[CellCheck],
                       checks: list[BrokenCheck],
                       wide: list[PageFacts] | None = None) -> list[Finding]:
    """Assign causes from what the filing prints versus what we stored.

    `wide` is the window plus a margin, used only when asking whether a figure
    exists ANYWHERE nearby — a statement's continuation sheet can fall outside the
    scored window, and concluding "printed nowhere" from too narrow a look is how
    a wrong-cell gets promoted to "the bank's statement is wrong".
    """
    out: list[Finding] = []
    wide = wide or window
    pages = [f.page1 for f in window]
    lead = window[0].page1 if window else None
    judged = [c for c in cells if c.verdict in ("exact", "wrapped", "absent")]
    wrapped = [c for c in judged if c.verdict == "wrapped"]
    absent = [c for c in judged if c.verdict == "absent"]
    exact = [c for c in judged if c.verdict == "exact"]

    if wrapped:
        out.append(Finding(
            WRAPPED_CELL,
            f"{len(wrapped)} stored figure(s) are word-wrapped inside their cell, so "
            f"get_text() emits a truncated token and the digits regroup wrongly",
            page=wrapped[0].page,
            evidence=[f"{c.label} · {c.column} = {c.value:,.0f} ← {c.evidence}"
                      for c in wrapped[:4]],
            confidence="confirmed"))

    if not judged:
        out.append(Finding(
            UNCLASSIFIED,
            "no stored figure on this partition is large enough to verify by "
            "presence (ratios and counts are not distinctive) — needs a human read",
            page=lead,
            evidence=[f"{len(cells)} stored values, all below the judgeable threshold"]))
        return out

    share_absent = len(absent) / len(judged)

    # Everything we hold is printed, yet an identity breaks. That is NECESSARY for
    # "the bank's statement does not foot" but nowhere near sufficient: a figure
    # lifted from the wrong line is still a figure printed on the page. Two things
    # have to be ruled out before the expensive verdict is allowed.
    if not absent and not wrapped and exact:
        # (1) Is the figure the identity actually needs printed in the filing? If
        # it is, a correct cell exists and we simply took a different one.
        for c in checks:
            if not judgeable(c.expected):
                continue
            verdict, page, ev = find_in_window(wide, c.expected)
            if verdict == "exact":
                out.append(Finding(
                    COLUMN_SLIP,
                    f"every stored figure is printed, but so is {c.expected:,.0f} — "
                    f"the figure `{c.check}` requires — on p{page}, while we stored "
                    f"{c.actual:,.0f}. A correct cell exists and a different one was "
                    f"read",
                    page=page,
                    evidence=[f"node {c.node}", f"printed token {ev!r} on p{page}",
                              f"statement window {pages}"],
                    confidence="confirmed"))
                return out
        # (2) Are the broken identities even decidable this way? Ratio and count
        # identities are argued in numbers too short to presence-check, so a
        # verdict there would rest on no evidence at all.
        if not any(judgeable(c.expected) for c in checks):
            out.append(Finding(
                UNCLASSIFIED,
                f"all {len(exact)} stored figures are printed as stored, but every "
                f"broken identity is argued over ratios or counts too short to verify "
                f"by presence — this method cannot separate a wrong cell from a "
                f"source defect here",
                page=lead,
                evidence=[f"broken: {'; '.join(c.node for c in checks[:3])}",
                          f"statement window {pages}"]))
            return out
        broken = "; ".join(f"{c.check} ({c.node})" for c in checks[:2]) or "the identity"
        out.append(Finding(
            SOURCE_DEFECT,
            f"all {len(exact)} verifiable stored figures are printed exactly as stored, "
            f"the figure {broken} requires is printed nowhere in the statement — the "
            f"bank's own statement does not foot",
            page=lead,
            evidence=[f"pages {pages}"]
            + [f"{c.label} · {c.column} = {c.value:,.0f} (p{c.page})" for c in exact[:4]],
            confidence="likely"))
        return out

    if absent and share_absent < 0.5:
        # A minority missing from an otherwise well-matched window: the values were
        # read from the wrong cell, not the wrong page. If the identity's derived
        # target IS printed here, the column mapping is the thing to look at.
        hint = next(((c, p) for c in checks
                     if c.expected is not None and judgeable(c.expected)
                     and (p := find_in_window(wide, c.expected)[1]) is not None), None)
        if hint is not None:
            chk, page = hint
            facts = next((f for f in window if f.page1 == page), None)
            band = band_of(facts, chk.expected) if facts else None
            nbands = len(column_bands(facts)) if facts else 0
            out.append(Finding(
                COLUMN_SLIP,
                f"the filing prints {chk.expected:,.0f} — what `{chk.check}` requires — "
                f"but {len(absent)} of {len(judged)} stored figures appear nowhere in the "
                f"statement: read from the wrong column",
                page=page,
                evidence=[f"printed on p{page} in column band {band} of {nbands}",
                          f"node {chk.node}"]
                + [f"absent: {c.label} · {c.column} = {c.value:,.0f}" for c in absent[:3]],
                confidence="likely"))
        else:
            out.append(Finding(
                COLUMN_SLIP,
                f"{len(absent)} of {len(judged)} stored figures are not printed anywhere "
                f"in a statement that otherwise matches ({len(exact)} exact) — a "
                f"cell-level misread",
                page=lead,
                evidence=[f"pages {pages}"]
                + [f"absent: {c.label} · {c.column} = {c.value:,.0f}" for c in absent[:5]],
                confidence="likely"))
    elif absent:
        out.append(Finding(
            ANCHOR_MISS,
            f"{len(absent)} of {len(judged)} stored figures are absent from every page "
            f"of the located statement — this is probably not where the values came from",
            page=lead,
            evidence=[f"pages searched {pages}"]
            + [f"absent: {c.label} · {c.column} = {c.value:,.0f}" for c in absent[:5]],
            confidence="likely"))
    return out


# --------------------------------------------------------------------------
# The page-search loop
# --------------------------------------------------------------------------

def score_page(facts: PageFacts, values: list[float]) -> int:
    """How many of the partition's stored figures this page prints."""
    return sum(1 for v in values if find_value(facts, v)[0] != "absent")


def search_pages(pdf_path: str | Path, values: list[float], anchor: int | None,
                 n_pages: int, radius: int = 6) -> tuple[int | None, dict[int, int]]:
    """Walk outward from the anchor, then the whole filing if nothing scores.

    This is the loop the diagnosis needs: a missed anchor and a parser bug are
    indistinguishable from the stored rows alone, and only become distinguishable
    once you have looked at the pages the anchor did NOT pick.
    """
    scores: dict[int, int] = {}
    if not n_pages or not values:
        return None, scores

    def consider(p: int) -> None:
        if p in scores or not (1 <= p <= n_pages):
            return
        facts = read_page(pdf_path, p)
        if facts is not None:
            scores[p] = score_page(facts, values)

    if anchor:
        for off in range(0, radius + 1):
            consider(anchor + off)
            consider(anchor - off)
    if not any(scores.values()):
        for p in range(1, n_pages + 1):        # the anchor was no help — sweep
            consider(p)
    if not scores:
        return None, scores
    best = max(scores, key=lambda p: (scores[p], -abs(p - (anchor or 1))))
    return (best if scores[best] else None), scores


def statement_window(scores: dict[int, int], best: int | None,
                     min_share: float = 0.25) -> list[int]:
    """The contiguous run of pages that carry this statement.

    Contiguity alone is not enough. Statements sit next to each other in a BRSA
    filing and share figures — total equity is printed on the balance sheet, the
    period net on the P&L — so "any adjacent page with a hit" walks straight into
    the neighbouring statement and imports its row markers as if they were missing
    from this one. A continuation page of the SAME table carries a real share of
    the statement's figures; an adjacent different table carries a handful.
    """
    if best is None:
        return []
    floor = max(2, int(scores.get(best, 0) * min_share))
    pages = [best]
    for step in (-1, 1):
        p = best + step
        while scores.get(p, 0) >= floor:
            pages.append(p)
            p += step
    return sorted(pages)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def triage_partition(conn: sqlite3.Connection, pdf_path: str | Path, bank: str,
                     period: str, kind: str, statement: str, table: str,
                     failed_detail: str | None, db_statement: str | None = None,
                     radius: int = 6) -> TriageNote:
    """Diagnose one failing (bank, period, kind, statement). Read-only."""
    note = TriageNote(bank=bank, period=period, kind=kind, statement=statement)
    try:
        note.checks = [BrokenCheck.from_json(d) for d in json.loads(failed_detail or "[]")]
    except (ValueError, TypeError):
        note.checks = []

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        note.error = f"PDF not available locally: {pdf_path.name}"
        return note
    if not _HAS_FITZ:
        note.error = "PyMuPDF not installed"
        return note

    note.pdf_pages = page_count(pdf_path)
    rows = stored_rows(conn, table, bank, period, kind, db_statement)
    if not rows:
        note.error = "no stored rows for this partition — nothing to compare"
        return note
    cols = value_columns(conn, table)
    note.anchor_page = stored_source_page(conn, table, bank, period, kind)

    wrong = detect_wrong_pdf(pdf_path, bank, period)
    if wrong:
        note.findings.append(wrong)

    fusion = detect_label_digit_fusion(rows)
    if fusion:
        note.findings.append(fusion)

    missing_text = detect_missing_auditor(pdf_path, rows, note.checks)
    if missing_text:
        note.findings.append(missing_text)
        return note

    # Search on the stored figures, not the validator's derived ones: there are
    # more of them and they are what the page must actually contain.
    values = [float(r[c]) for r in rows for c in cols
              if c in r.keys() and isinstance(r[c], (int, float)) and judgeable(r[c])]
    if not values:
        # Nothing distinctive enough to presence-check. Saying so is the honest
        # answer; a numeric verdict here would be a label with no evidence.
        note.findings.append(Finding(
            UNCLASSIFIED,
            "this lane stores no figure large enough to verify by presence "
            "(text fields, ratios and counts are not distinctive) — the numeric "
            "evidence base does not apply and a human read is needed",
            evidence=[f"{len(rows)} stored rows over columns {cols}"]))
        return note
    best, scores = search_pages(pdf_path, values, note.anchor_page,
                                note.pdf_pages, radius)
    note.best_page = best

    window_pages = statement_window(scores, best)
    note.window = window_pages
    window = [f for f in (read_page(pdf_path, p) for p in window_pages) if f is not None]
    if not window:
        note.findings.append(Finding(
            ANCHOR_MISS, "no page in the filing prints any of the stored figures — "
            "the statement is not where the locator looked, or not readable at all",
            evidence=[f"anchor page {note.anchor_page}", f"{note.pdf_pages} pages scanned",
                      f"{len(values)} judgeable stored figures"]))
        return note

    cells = audit_stored_values(window, rows, cols)
    missing = any(c.verdict in ("absent", "wrapped") for c in cells)
    for facts in window:
        note.findings.extend(detect_page_defects(facts, values_missing=missing))
    dot = detect_trailing_dot(rows, window[0])
    if dot:
        note.findings.append(dot)

    if (note.anchor_page and best and best != note.anchor_page
            and scores.get(note.anchor_page, 0) == 0):
        note.findings.append(Finding(
            ANCHOR_MISS,
            f"the anchored page {note.anchor_page} prints none of the stored figures; "
            f"page {best} prints {scores[best]} of {len(values)}",
            page=best,
            evidence=[f"anchor={note.anchor_page}", f"best={best}",
                      f"scores={ {k: v for k, v in sorted(scores.items()) if v} }"],
            confidence="confirmed"))

    unit = detect_unit_switch(window, cells)
    if unit:
        note.findings.append(unit)
        return note              # a unit switch explains every absent figure below

    dropped = detect_dropped_cell(window, cells, note.checks)
    if dropped:
        note.findings.append(dropped)
        return note              # a proved cause outranks the inferred ones below

    gap = detect_missing_row(pdf_path, window, rows, cols, note.checks)
    if gap:
        note.findings.append(gap)
        return note              # checked before source_defect, which it mimics

    # A margin around the window, for "is this figure printed anywhere nearby?"
    margin = range(max(1, window_pages[0] - 2), min(note.pdf_pages, window_pages[-1] + 2) + 1)
    wide = [f for f in (read_page(pdf_path, p) for p in margin) if f is not None]
    note.findings.extend(classify_partition(window, cells, note.checks, wide))

    if not note.findings:
        note.findings.append(Finding(
            UNCLASSIFIED,
            "no mechanical cause matched: the stored figures are not printed in the "
            "located statement in any recognised form",
            page=best, evidence=[f"window {window_pages}"]))
    return note
