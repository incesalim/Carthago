"""Narrative prose from a BRSA audit report, as section-scoped item rows.

Every other lane in this package reads *tables*. This one reads what is left: the
accounting-policy notes, the risk narrative, the review-report explanations, the
interim activity report. It emits rows shaped like a statement's item rows —
`(section, heading, item_order, text)` — so prose sits beside the tables in the
coverage matrix instead of living in a separate world.

Four things had to be solved, each of which fails *silently* if skipped, and each
of which was measured failing before it was fixed:

  * **Language.** 32% of filings are English convenience translations, and it
    varies per filing, not per bank — AKBNK files both. A Turkish-only pattern
    returns zero sections and no error.
  * **Headings vs cross-references.** "as detailed in footnote number one of
    section six" is not a section start. Taking the first match lands on the
    contents page; taking the last lands on a cross-reference. Both were measured
    at 1-2/10. Section starts are resolved as the highest-scoring *strictly
    increasing* chain instead, which no single page and no scattered mention can
    satisfy.
  * **Tables vs prose.** Counting numbers in a line files
    "…31 Mart 2022 itibarıyla Grup'un kıdem tazminatı yükümlülüğü 29.447 TL'dir"
    under "table" — a sentence stating a figure, which is precisely the class
    prose exists to capture. The decidable signal is geometric: a table row's
    tokens sit on x-positions shared with the rows above and below; a prose
    line's do not.
  * **Page furniture.** The bank name, statement title, period line and unit
    declaration repeat on nearly every page — 5.4% of one measured filing.

Reads `_fitz_page_line_tokens`, the shared reader's own geometry, so the text
here is the same text every statement extractor sees.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field

# `from .extractor import …` is deferred into _read_lines: everything else in
# this module is a pure function over Line objects, and CI's Python job installs
# only ruff + pytest + stdlib. A module-level import would make the whole test
# file unimportable there.

# --- section identity -------------------------------------------------------
# §1–§5 are stable. §6/§7 swap between annual and interim filings, so the printed
# number is not the meaning — `role` is. Interim: §6 points at the review report
# (it is bound in front of the statements) and §7 is the activity report. Annual:
# §6 is other explanations and §7 is the audit report itself.
SECTION_ROLES_ANNUAL = {
    1: "general_info", 2: "financial_statements", 3: "accounting_policies",
    4: "risk", 5: "notes", 6: "other_explanations", 7: "audit_report",
}
SECTION_ROLES_INTERIM = {
    1: "general_info", 2: "financial_statements", 3: "accounting_policies",
    4: "risk", 5: "notes", 6: "review_report_pointer", 7: "interim_activity_report",
}

# Eight, not seven: ALTERNATİFBANK splits the review report and the activity
# report into §7 and §8, so a hard 1–7 assumption drops its last section and
# mislabels the one before it. The count is not fixed and the roles are not
# positional — they are read off the filing's own declared titles below.
TR_ORDINALS = ["BIRINCI", "IKINCI", "UCUNCU", "DORDUNCU", "BESINCI", "ALTINCI",
               "YEDINCI", "SEKIZINCI"]
EN_ORDINALS = ["ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT"]
_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8}

_TR_SECTION = re.compile(r"^(" + "|".join(TR_ORDINALS) + r")\s+BOLUM\b")
_EN_SECTION = re.compile(r"^SECTION\s+(" + "|".join(EN_ORDINALS) + r")\b")
# The running-header form. HALKB labels every body page "SECTION III: …" and
# prints no in-body dividers at all — without this its sections are unfindable.
# The trailing colon/period is required: "presented in Section III, No: VIII" is
# a cross-reference and must not match.
_EN_ROMAN_SECTION = re.compile(r"^SECTION\s+([IVX]{1,4})\s*[:.]")
_TR_IDX = {o: i + 1 for i, o in enumerate(TR_ORDINALS)}
_EN_IDX = {o: i + 1 for i, o in enumerate(EN_ORDINALS)}

# Role from the section's own declared title. Ordered: "FAALIYET RAPORU" and
# "DENETIM RAPORU" both end in "RAPORU", so the activity report must be tested
# first or every §7 in the fleet reads as an audit report.
_ROLE_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("interim_activity_report", ("FAALIYET RAPORU", "ARA DONEM FAALIYET",
                                 "ACTIVITY REPORT")),
    ("audit_report", ("DENETIM RAPORU", "DENETCI RAPORU", "AUDITOR", "AUDIT REPORT",
                      "REVIEW REPORT")),
    # Before `notes`: ALNTF titles §6 "Diğer Açıklama ve Dipnotlar" — singular
    # "Açıklama", so it misses "DIGER ACIKLAMALAR" and, tested later, would fall
    # through to the notes rule and label the section a second §5.
    # "Other DISCLOSURES on Activities" is GARANTİ's §6. Broadening `notes` to
    # match any disclosure word made it a second §5 unless this rule names the
    # variant too.
    ("other_explanations", ("DIGER ACIKLAMA", "OTHER EXPLANATION",
                            "OTHER DISCLOSURE")),
    ("accounting_policies", ("MUHASEBE POLITIKA", "ACCOUNTING POLICIES")),
    ("risk", ("MALI BUNYE", "RISK YONETIM", "FINANCIAL STRUCTURE",
              "FINANCIAL POSITION AND RISK",
              # GARANTİ: "Financial Position and Results of Operations and Risk
              # Management" — the title runs long and is captured truncated.
              "FINANCIAL POSITION AND RESULTS")),
    ("general_info", ("GENEL BILGILER", "GENERAL INFORMATION")),
    # §2 and §5 are both "…financial statements"; what separates them is the
    # DISCLOSURE word, not the noun. §2 is the statements themselves ("Konsolide
    # Olmayan Finansal Tablolar"); §5 is always *about* them — "Explanations and
    # Disclosures on …", "Information and Disclosures Related to …", "…Tablolara
    # İlişkin Açıklama ve Dipnotlar". Matching only on "notes"/"footnotes" left
    # 23 filings (EXIM, QNBFB, SKBNK, TSKB, PASHA) reading §5 as a second §2.
    # Safe at this position: `other_explanations`, `accounting_policies` and
    # `risk` all carry disclosure words too and are tested above.
    # "TABLOLARA ILISKIN" (dative — *relating to* the statements) is the Turkish
    # discriminator on its own, and carries §5 even when the title is captured
    # truncated before "Açıklama ve Dipnotlar" (PASHA).
    ("notes", ("DIPNOT", "ACIKLAMA", "NOTE", "FOOTNOTE", "EXPLANATION",
               "DISCLOSURE", "TABLOLARA ILISKIN")),
    ("financial_statements", ("FINANSAL TABLOLAR", "FINANCIAL STATEMENTS")),
]


def role_from_title(title: str | None) -> str | None:
    if not title:
        return None
    folded = _fold(title)
    for role, keys in _ROLE_RULES:
        if any(k in folded for k in keys):
            return role
    return None

# A heading carries a numbering marker: roman (I. II. XVIII.), letter (a. b.) or
# decimal (1. 1.1 2.4.3). BRSA mandates the numbering, not the wording, which is
# why this is regex territory and the body of the note is not.
# The trailing "." or ")" is required for a roman, a letter or a bare integer —
# without it "2024 was a year of…" would open a heading. A MULTI-component
# decimal is self-delimiting, so its trailing period is optional: GARANTİ prints
# "4.2.7 Movements in value adjustments" with none, which left 340 of its 478
# blocks with no heading at all.
# The period-optional branch is deliberately narrow: it must be rooted in a
# plausible section (1–8) with 1–2 digit components. Allowing any decimal made
# "31.12.2024 Toplam …" a heading, which produced 11-deep paths out of a date.
_HEAD_MARKER = re.compile(
    r"^((?:[IVXLC]{1,6}|[a-zA-Z]|\d+(?:\.\d+)*)[.)]|[1-8](?:\.\d{1,2})+)"
    r"\s+(\S.{1,160})$")
_PAGE_NO = re.compile(r"^\(?\d{1,4}\)?$")
_NUMERIC = re.compile(r"^\(?-?[\d.,]*\d[\d.,]*\)?%?$")
_HAS_ALPHA = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşü]")
# A period that ends a real sentence: preceded by a word, not by an initial.
_SENTENCE_END = re.compile(r"[a-zçğıöşü]{3}\.\s")

# Geometry thresholds. Tuned on the 10-filing random sample; see the lane doc.
_ANCHOR_BUCKET = 2.0     # pt — x positions within this are the same column
_ANCHOR_MIN_LINES = 3    # a column anchor must recur on this many lines
_MARGIN_TOL = 6.0        # pt — anchors this close to the text margin are the margin
_GAP_TABLE = 35.0        # pt — an intra-line gap this wide is column whitespace
_GAP_PROSE = 22.0        # pt — below this, spacing is word spacing, not columns
_PROSE_MIN_WORDS = 8     # a run of this many words is a sentence, not a row
_MIN_BLOCK_CHARS = 40    # shorter blocks are labels, not narrative
_MIN_SOLE_BLOCK_CHARS = 8  # …unless it is all a section has to say
_CONTENTS_MAX_PAGE = 15  # a contents block always precedes §1


def _fold(s: str) -> str:
    """Diacritic-insensitive upper. Turkish dotted/dotless i first, so 'İ' and
    'ı' fold onto the same letter as their ASCII counterparts rather than
    surviving as separate characters that no pattern matches."""
    s = s.replace("İ", "I").replace("ı", "i").replace("Ş", "S").replace("ş", "s")
    s = s.replace("Ğ", "G").replace("ğ", "g").replace("Ç", "C").replace("ç", "c")
    s = s.replace("Ö", "O").replace("ö", "o").replace("Ü", "U").replace("ü", "u")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper()


@dataclass
class Line:
    page: int
    order: int
    tokens: list[tuple[float, float, str]]
    text: str
    seq: int = 0          # document-wide reading order
    is_table: bool = False
    is_heading: bool = False
    marker: str | None = None


@dataclass
class ProseRow:
    section: int
    section_role: str
    heading: str | None
    heading_path: str | None
    item_order: int
    page_start: int
    page_end: int
    lang: str
    text: str

    @property
    def char_count(self) -> int:
        return len(self.text)


@dataclass
class ProseResult:
    rows: list[ProseRow] = field(default_factory=list)
    lang: str = "tr"
    period_type: str = "interim"
    section_pages: dict[int, int] = field(default_factory=dict)
    section_titles: dict[int, str] = field(default_factory=dict)
    section_roles: dict[int, str] = field(default_factory=dict)
    furniture: list[str] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.rows


# --- stage 1: read ----------------------------------------------------------
def _read_lines(pdf_path: str) -> list[Line]:
    from .extractor import _fitz_page_count, _fitz_page_line_tokens
    n = _fitz_page_count(pdf_path) or 0
    out: list[Line] = []
    for i in range(n):
        for j, toks in enumerate(_fitz_page_line_tokens(pdf_path, i)):
            text = " ".join(t for _, _, t in toks).strip()
            if text:
                out.append(Line(page=i + 1, order=j, tokens=toks, text=text,
                                seq=len(out)))
    return out


# --- stage 2: language ------------------------------------------------------
def detect_language(lines: list[Line]) -> str:
    head = " ".join(_fold(ln.text) for ln in lines if ln.page <= 8)
    tr = len(re.findall(r"\b(?:" + "|".join(TR_ORDINALS) + r")\s+BOLUM", head))
    en = len(re.findall(r"\bSECTION\s+(?:" + "|".join(EN_ORDINALS) + r")\b", head))
    return "en" if en > tr else "tr"


# --- stage 3: page furniture ------------------------------------------------
def find_furniture(lines: list[Line], n_pages: int) -> set[str]:
    """Lines that repeat across most pages are running headers, not content."""
    seen: dict[str, set[int]] = defaultdict(set)
    for ln in lines:
        seen[ln.text].add(ln.page)
    threshold = max(3, int(n_pages * 0.4))
    return {t for t, pages in seen.items() if len(pages) >= threshold}


# --- stage 4: table vs prose, by column geometry ----------------------------
def _column_anchors(page_lines: list[Line]) -> tuple[set[int], set[int], float]:
    """x positions shared by ≥3 lines on this page — the page's table columns.

    The text margin is excluded: every prose line starts there, so counting it
    would make justified body text look like a two-column table.
    """
    left = Counter()
    starts = Counter()
    ends = Counter()
    for ln in page_lines:
        if not ln.tokens:
            continue
        left[int(ln.tokens[0][0] / _ANCHOR_BUCKET)] += 1
        for x0, x1, _t in ln.tokens:
            starts[int(x0 / _ANCHOR_BUCKET)] += 1
            ends[int(x1 / _ANCHOR_BUCKET)] += 1
    margin = (left.most_common(1)[0][0] * _ANCHOR_BUCKET) if left else 0.0
    keep = lambda c: {b for b, n in c.items()
                      if n >= _ANCHOR_MIN_LINES
                      and abs(b * _ANCHOR_BUCKET - margin) > _MARGIN_TOL}
    return keep(starts), keep(ends), margin


def _mark_tables(lines: list[Line]) -> None:
    by_page: dict[int, list[Line]] = defaultdict(list)
    for ln in lines:
        by_page[ln.page].append(ln)
    for page_lines in by_page.values():
        anchors_x0, anchors_x1, _margin = _column_anchors(page_lines)
        for ln in page_lines:
            toks = ln.tokens
            if len(toks) < 2:
                continue
            aligned = sum(1 for x0, x1, _t in toks
                          if int(x0 / _ANCHOR_BUCKET) in anchors_x0
                          or int(x1 / _ANCHOR_BUCKET) in anchors_x1)
            max_gap = max((toks[i + 1][0] - toks[i][1]) for i in range(len(toks) - 1))
            # A leading dash is a bullet, not a value — counting it made bulleted
            # policy sentences look like all-dash table rows.
            numeric = sum(1 for i, (_x0, _x1, t) in enumerate(toks)
                          if _NUMERIC.match(t) or (t == "-" and i > 0))
            words = sum(1 for _x0, _x1, t in toks
                        if len(_HAS_ALPHA.findall(t)) >= 2 and not _NUMERIC.match(t))
            # Column whitespace, or ≥2 tokens standing in this page's columns with
            # at least one figure among them. Neither test counts figures alone —
            # a sentence quoting an amount must stay prose.
            table = max_gap >= _GAP_TABLE or (aligned >= 2 and numeric >= 1)
            # A page holding a table gives every line on it column anchors,
            # including the narrative around the table. A run of words at normal
            # word spacing is a sentence whatever the page's geometry says.
            if table and words >= _PROSE_MIN_WORDS and max_gap < _GAP_PROSE:
                table = False
            ln.is_table = table
        _smooth_tables(page_lines)


def _smooth_tables(page_lines: list[Line]) -> None:
    """A table row has table rows above and below it; an isolated one does not.

    This is the "shares x-positions with the rows around it" test taken
    literally, and it catches what the per-line rules cannot: a lone sentence
    that happens to align, and a stray short cell inside a real table.
    """
    flags = [ln.is_table for ln in page_lines]
    out = list(flags)
    for i, ln in enumerate(page_lines):
        prev_t = flags[i - 1] if i > 0 else False
        next_t = flags[i + 1] if i + 1 < len(flags) else False
        words = len(_HAS_ALPHA.findall(ln.text)) and len(ln.text.split())
        if flags[i] and not prev_t and not next_t and words >= _PROSE_MIN_WORDS:
            out[i] = False           # isolated "row" among prose = a sentence
        elif not flags[i] and prev_t and next_t and words < _PROSE_MIN_WORDS:
            out[i] = True            # short line inside a table = a cell
    for ln, f in zip(page_lines, out):
        ln.is_table = f


# --- stage 5: headings ------------------------------------------------------
def _mark_headings(lines: list[Line]) -> None:
    for ln in lines:
        if ln.is_table or len(ln.text) > 180:
            continue
        m = _HEAD_MARKER.match(ln.text)
        if m and _HAS_ALPHA.search(m.group(2)):
            # A numbered heading does not run on into a second sentence — but
            # counting ". " as the break makes "T.C." and "A.Ş." look like two
            # sentences, and Turkish bank filings are full of both. A real
            # sentence end needs a word before the period, not an initial.
            if not _SENTENCE_END.search(m.group(2)):
                ln.is_heading = True
                ln.marker = m.group(1).rstrip(".)")


# --- stage 6: section starts ------------------------------------------------
def _section_candidates(lines: list[Line], lang: str) -> dict[int, list[Line]]:
    """Lines that *open* with a section heading, in word or roman form.

    A cross-reference sits inside a sentence and is filtered here by requiring
    the match at position 0; the contents page survives and is handled by the
    monotonic chain below."""
    pat, idx = (_EN_SECTION, _EN_IDX) if lang == "en" else (_TR_SECTION, _TR_IDX)
    out: dict[int, list[Line]] = defaultdict(list)
    for ln in lines:
        folded = _fold(ln.text).lstrip("•* \t")
        m = pat.match(folded)
        if m and len(ln.text) <= 90:
            out[idx[m.group(1)]].append(ln)
            continue
        if lang == "en":
            rm = _EN_ROMAN_SECTION.match(folded)
            if rm and rm.group(1) in _ROMAN:
                out[_ROMAN[rm.group(1)]].append(ln)
    return out


def declared_titles(lines: list[Line], lang: str) -> dict[int, str]:
    """Section titles as the filing itself lists them on its contents page.

    Two layouts: the title trails the ordinal on one line ("Altıncı Bölüm -
    SINIRLI DENETİM RAPORU"), or the ordinal stands alone and the title is the
    next line (ALNTF, FIBA). Both appear in the fleet.
    """
    pat, idx = (_EN_SECTION, _EN_IDX) if lang == "en" else (_TR_SECTION, _TR_IDX)
    out: dict[int, str] = {}
    # Read titles only off the contents block. The auditor's report quotes
    # section names in passing ("Beşinci Bölüm II.8.3.1 numaralı dipnotta
    # belirtildiği üzere, …"), and that sentence sits on page 2 — ahead of the
    # contents page, so a first-match scan adopts it as §5's title.
    hosts: dict[int, set[int]] = defaultdict(set)
    for ln in lines:
        if ln.page > 14:
            break
        m = pat.match(_fold(ln.text).lstrip("•* \t"))
        if m:
            hosts[ln.page].add(idx[m.group(1)])
    contents = {p for p, ss in hosts.items() if len(ss) >= 3} or set(hosts)
    for i, ln in enumerate(lines):
        if ln.page > 14:
            break
        if ln.page not in contents:
            continue
        folded = _fold(ln.text).lstrip("•* \t")
        m = pat.match(folded)
        if not m:
            continue
        s = idx[m.group(1)]
        rest = ln.text[len(ln.text) - len(folded) + m.end():].strip(" -–—:•\t")
        if len(rest) < 6 and i + 1 < len(lines) and lines[i + 1].page == ln.page:
            nxt = lines[i + 1]
            if not pat.match(_fold(nxt.text).lstrip("•* \t")):
                rest = nxt.text.strip(" -–—:•\t")
        rest = re.sub(r"\s*\d{1,3}(\s*[-–]\s*\d{1,3})?$", "", rest).strip()
        # The next-line fallback can pick up the contents table's column header
        # instead of a title (GARANTİ: "Page No"). A title that short is junk.
        if len(rest) >= 10 and not re.fullmatch(
                r"(?i)(page|sayfa)\s*(no|number)?\.?", rest):
            out.setdefault(s, rest[:120])
    return out


def _title_key(title: str) -> str:
    """Comparable form of a declared title — folded, punctuation-free, truncated
    to the leading words that identify it."""
    return re.sub(r"[^A-Z ]+", " ", _fold(title)).strip()[:34]


def _fill_from_titles(lines: list[Line], starts: dict[int, int],
                      titles: dict[int, str], contents_pages: set[int],
                      n_pages: int) -> dict[int, int]:
    """Resolve sections the dividers missed, using the filing's own titles.

    Deliberately a second pass constrained to the window between the sections
    that *were* resolved: a title like "…AÇIKLAMA VE DİPNOTLAR" also serves as
    the running header for several sections, so searching the whole document for
    it would drag a section start backwards. Inside a known window it cannot.
    """
    if not titles:
        return starts
    out = dict(starts)
    for s in sorted(titles):
        if s in out:
            continue
        key = _title_key(titles[s])
        if len(key) < 12:
            continue
        lo = max((p for sec, p in out.items() if sec < s), default=0)
        hi = min((p for sec, p in out.items() if sec > s), default=n_pages + 1)
        # Containment, not prefix: a running header can arrive interleaved with
        # the unit declaration when both sit on the same y-band ("I. Banka
        # (Tutarlar Yönetim aksi belirtilmedikçe Kurulu Başkanı Bin Türk …"),
        # which no prefix test survives. The page window keeps it honest.
        probe = key[:22]
        hit = next((ln.page for ln in lines
                    if lo < ln.page < hi and ln.page not in contents_pages
                    and probe in _title_key(ln.text)), None)
        if hit is None and role_from_title(titles[s]) == "financial_statements":
            # §2 is the primary statements. When its divider is absent (ALNTF
            # prints none) the section is still identifiable by what it is: the
            # first page in the window that is essentially all table.
            hit = _first_table_page(lines, lo, hi, contents_pages)
        if hit is not None:
            out[s] = hit
    return dict(sorted(out.items()))


_NOTE_NUMBER = re.compile(r"^([1-8])\.\d+(?:\.\d+)*\s+\S")


def _fill_from_note_numbers(lines: list[Line], starts: dict[int, int],
                            titles: dict[int, str],
                            contents_pages: set[int]) -> dict[int, int]:
    """Last resort: read the section off the note numbering.

    GARANTİ prints no section marker anywhere in the body — no divider, no
    running header, no roman numeral — but numbers its notes from the section:
    "4.2.7 Movements in value adjustments", "5.6.6 Restricted cash". The leading
    component IS the section, so the first page whose notes start with `N.` is
    where section N begins.

    Guarded by a minimum count so a stray "5.1" in a sentence cannot anchor a
    section, and by the page window of whatever the earlier passes resolved.
    """
    want = set(range(1, (max(titles) if titles else 7) + 1)) - set(starts)
    if not want:
        return starts
    first_page: dict[int, int] = {}
    seen: Counter = Counter()
    for ln in lines:
        if ln.page in contents_pages or ln.is_table:
            continue
        m = _NOTE_NUMBER.match(ln.text)
        if not m:
            continue
        s = int(m.group(1))
        seen[s] += 1
        first_page.setdefault(s, ln.page)
    out = dict(starts)
    for s in sorted(want):
        if seen.get(s, 0) < 4 or s not in first_page:
            continue
        lo = max((p for sec, p in out.items() if sec < s), default=0)
        hi = min((p for sec, p in out.items() if sec > s), default=10**6)
        if lo < first_page[s] < hi:
            out[s] = first_page[s]
    return dict(sorted(out.items()))


def _first_table_page(lines: list[Line], lo: int, hi: int,
                      contents_pages: set[int]) -> int | None:
    by_page: dict[int, list[Line]] = defaultdict(list)
    for ln in lines:
        # A contents page is dense in short numbered lines and reads as "mostly
        # table" — excluded, or §2 anchors on the table of contents.
        if lo < ln.page < hi and ln.page not in contents_pages:
            by_page[ln.page].append(ln)
    for page in sorted(by_page):
        page_lines = by_page[page]
        if len(page_lines) >= 8 and sum(
                ln.is_table for ln in page_lines) / len(page_lines) >= 0.7:
            return page
    return None


def resolve_sections(
    lines: list[Line], lang: str, titles: dict[int, str] | None = None,
) -> tuple[dict[int, int], dict[int, int]]:
    """Pick one start page per section as the best strictly increasing chain.

    Neither "first match" nor "last match" works — the contents page puts all
    seven on one page, and cross-references scatter them through the body. A
    strictly increasing chain excludes the contents page structurally (a single
    page cannot host two increasing starts) and penalises stray mentions, which
    do not line up in section order.
    """
    cands = _section_candidates(lines, lang)
    if not lines:
        return {}, {}
    n_pages = max(ln.page for ln in lines)
    # A page announcing three or more different sections is the contents block,
    # not a section start — and it is *never* one, since it precedes §1. Dropping
    # its candidates outright (rather than merely down-weighting them) is what
    # stops GARAN, whose body prints no dividers at all, from resolving its whole
    # chain onto the two contents pages.
    per_page: dict[int, set[int]] = defaultdict(set)
    for s, lns in cands.items():
        for ln in lns:
            per_page[ln.page].add(s)
    # Bounded to the front matter. KUVEYT's FINAL page opens §6, §7 and §8
    # together (three short closing sections), and an unbounded rule reads that
    # as a contents page, drops all three, and truncates the filing at §5.
    # A contents block precedes §1 by definition, so the page bound is safe.
    contents_pages = {p for p, ss in per_page.items()
                      if len(ss) >= 3 and p <= _CONTENTS_MAX_PAGE}

    # DP over the sections, ordered by document-wide line position rather than by
    # page: in an ANNUAL filing §6 and §7 both open on the final page, so a
    # strictly-increasing-PAGE chain can hold only one of them and every annual
    # report resolves to six sections. Line order separates them.
    best: dict[tuple[int, int], tuple[float, tuple[int, int] | None]] = {}
    page_of: dict[int, int] = {}
    order: list[tuple[int, int]] = []
    for s in range(1, len(TR_ORDINALS) + 1):
        for ln in cands.get(s, []):
            if ln.page in contents_pages:
                continue
            page_of[ln.seq] = ln.page
            order.append((s, ln.seq))
    for s, seq in sorted(set(order)):
        base = 1.0 - seq * 1e-7          # ties go to the earliest occurrence
        cur = (base, None)
        for (ps, pseq), (pscore, _bp) in best.items():
            if ps < s and pseq < seq and pscore + base > cur[0]:
                cur = (pscore + base, (ps, pseq))
        prev = best.get((s, seq))
        if prev is None or cur[0] > prev[0]:
            best[(s, seq)] = cur
    chain: dict[int, int] = {}
    chain_seq: dict[int, int] = {}
    if best:
        node: tuple[int, int] | None = max(best, key=lambda k: best[k][0])
        while node is not None:
            chain[node[0]] = page_of[node[1]]
            chain_seq[node[0]] = node[1]
            node = best[node][1]
    starts = _fill_from_titles(lines, dict(sorted(chain.items())), titles or {},
                               contents_pages, n_pages)
    starts = _fill_from_note_numbers(lines, starts, titles or {}, contents_pages)
    # Attribution keys on line position, never page: an annual filing opens §6
    # and §7 on the SAME page, and a page-based lookup hands every line on it to
    # whichever section is last — leaving §6 with zero rows while its start page
    # still reads as resolved.
    first_seq_on_page: dict[int, int] = {}
    for ln in lines:
        first_seq_on_page.setdefault(ln.page, ln.seq)
    for s, page in starts.items():
        if s not in chain_seq:
            chain_seq[s] = first_seq_on_page.get(page, 0)
    return starts, {s: chain_seq[s] for s in starts if s in chain_seq}


# --- stage 7: blocks --------------------------------------------------------
def _reflow(parts: list[str]) -> str:
    text = ""
    for p in parts:
        if not text:
            text = p
        elif text.endswith("-") and not text.endswith(" -"):
            text = text[:-1] + p        # word broken across lines
        else:
            text = f"{text} {p}"
    return re.sub(r"\s{2,}", " ", text).strip()


def _section_of(seq: int, starts_seq: dict[int, int]) -> int | None:
    hit = None
    for s in sorted(starts_seq):
        if seq >= starts_seq[s]:
            hit = s
    return hit


# Marker forms, in the nesting order BRSA mandates: I. → a. → 1. → (i).
# Roman is matched against I/V/X combinations ONLY. A bare "C." or "D." is the
# third/fourth item of a lettered list far more often than it is 100 or 500, and
# admitting them as roman would hoist those blocks to the top level.
_ROMAN_UPPER = re.compile(r"^(?:X{0,3})(?:IX|IV|V?I{0,3})$")
_ROMAN_LOWER = re.compile(r"^(?:x{0,3})(?:ix|iv|v?i{0,3})$")
_DECIMAL_PATH = re.compile(r"^\d+(?:\.\d+)+$")


def _marker_depth(marker: str) -> int:
    """Nesting depth of a heading marker, 1 = directly under the section."""
    if _DECIMAL_PATH.match(marker):
        return 2 + marker.count(".")
    if marker.isupper() and _ROMAN_UPPER.match(marker):
        return 1
    if len(marker) > 1 and marker.islower() and _ROMAN_LOWER.match(marker):
        return 4
    if len(marker) == 1 and marker.isalpha():
        return 2
    if marker.isdigit():
        return 3
    return 3


def _push_path(stack: list[str], marker: str, section: int) -> list[str]:
    """Update the heading stack with a marker and return the new path.

    A dotted marker whose first component IS the section number is already
    absolute — GARANTİ numbers its notes "4.2.7", "5.6.6" — so it replaces the
    stack rather than nesting under it, or the path would read "4.4.2.7".
    """
    if _DECIMAL_PATH.match(marker) and marker.split(".")[0] == str(section):
        stack[:] = marker.split(".")[1:]
        return list(stack)
    depth = _marker_depth(marker)
    del stack[depth - 1:]
    stack.append(marker)
    return list(stack)


def _is_divider(text: str, lang: str) -> bool:
    """The 'ÜÇÜNCÜ BÖLÜM …' banner that opens a section is structure, not prose —
    it would otherwise become the first row of every section."""
    folded = _fold(text).lstrip("•* \t")
    pat = _EN_SECTION if lang == "en" else _TR_SECTION
    return bool(pat.match(folded) or (lang == "en" and _EN_ROMAN_SECTION.match(folded)))


def build_rows(lines: list[Line], starts_seq: dict[int, int], lang: str,
               roles: dict[int, str]) -> list[ProseRow]:
    rows: list[ProseRow] = []
    buf: list[str] = []
    buf_pages: list[int] = []
    heading: str | None = None
    heading_path: str | None = None
    cur_section: int | None = None
    rows_in_section = 0
    stack: list[str] = []

    def flush() -> None:
        nonlocal buf, buf_pages, rows_in_section
        text = _reflow(buf)
        buf, pages, buf_pages = [], buf_pages, []
        if cur_section is None:
            return
        # "Bulunmamaktadır." is 16 characters and is the entire content of §6 in
        # most annual filings — an explicit "there is none", which is a
        # disclosure, not an absence. Dropping it on the length floor left the
        # section with zero rows and read as a hole in the sectioning.
        floor = _MIN_BLOCK_CHARS if rows_in_section else _MIN_SOLE_BLOCK_CHARS
        if len(text) < floor:
            return
        if not _HAS_ALPHA.search(text):
            return
        rows_in_section += 1
        rows.append(ProseRow(
            section=cur_section, section_role=roles.get(cur_section, "unknown"),
            heading=heading, heading_path=heading_path,
            item_order=len(rows) + 1,
            page_start=min(pages), page_end=max(pages), lang=lang, text=text,
        ))

    for ln in lines:
        sec = _section_of(ln.seq, starts_seq)
        if sec != cur_section:
            flush()
            cur_section, heading, heading_path = sec, None, None
            rows_in_section = 0
            stack = []
            if sec is not None:
                heading_path = str(sec)   # a block before the first heading
        if ln.is_table or _is_divider(ln.text, lang):
            flush()
            continue
        if ln.is_heading:
            flush()
            m = _HEAD_MARKER.match(ln.text)
            heading = m.group(2).strip() if m else ln.text
            # The FULL path, not the leaf marker. "1" alone cannot say whether
            # the block sits under I.a or under II.d, and two sibling "1."s in
            # different parents were indistinguishable.
            path = _push_path(stack, ln.marker, cur_section) if ln.marker else []
            heading_path = ".".join([str(cur_section), *path])
            continue
        buf.append(ln.text)
        buf_pages.append(ln.page)
    flush()
    return rows


def upsert(conn, bank_ticker: str, period: str, kind: str,
           rep: "ProseResult") -> int:
    """DELETE + INSERT the partition. item_order is positional, so a partial
    overwrite would interleave two extractions' numbering."""
    cur = conn.cursor()
    cur.execute("DELETE FROM bank_audit_prose "
                "WHERE bank_ticker=? AND period=? AND kind=?",
                (bank_ticker, period, kind))
    rows = [(bank_ticker, period, kind, r.item_order, r.section, r.section_role,
             r.heading, r.heading_path, r.page_start, r.page_end, r.lang,
             r.text, r.char_count) for r in rep.rows]
    if rows:
        cur.executemany(
            "INSERT INTO bank_audit_prose "
            "(bank_ticker, period, kind, item_order, section, section_role, "
            " heading, heading_path, page_start, page_end, lang, text, "
            " char_count) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    return len(rows)


# --- entry point ------------------------------------------------------------
def extract_prose(pdf_path: str, period: str = "") -> ProseResult:
    lines = _read_lines(pdf_path)
    if not lines:
        return ProseResult()
    n_pages = max(ln.page for ln in lines)
    lang = detect_language(lines)
    furniture = find_furniture(lines, n_pages)
    body = [ln for ln in lines
            if ln.text not in furniture and not _PAGE_NO.match(ln.text)]
    _mark_tables(body)
    _mark_headings(body)
    titles = declared_titles(lines, lang)
    starts, starts_seq = resolve_sections(body, lang, titles)
    annual = period.endswith("Q4")
    # The filing's own title wins; the positional map is the fallback for a
    # section whose title we could not read. §6/§7 swap between annual and
    # interim, and ALNTF has eight sections — neither is safe to assume.
    fallback = SECTION_ROLES_ANNUAL if annual else SECTION_ROLES_INTERIM
    roles = {s: (role_from_title(titles.get(s)) or fallback.get(s, "unknown"))
             for s in starts}
    rows = build_rows(body, starts_seq, lang, roles)
    return ProseResult(
        rows=rows, lang=lang, period_type="annual" if annual else "interim",
        section_pages=starts, section_titles=titles, section_roles=roles,
        furniture=sorted(furniture),
        stats={
            "pages": n_pages,
            "lines_total": len(lines),
            "lines_furniture": len(lines) - len(body),
            "lines_table": sum(1 for ln in body if ln.is_table),
            "lines_heading": sum(1 for ln in body if ln.is_heading),
            "lines_prose": sum(1 for ln in body if not ln.is_table and not ln.is_heading),
            "rows": len(rows),
            "chars": sum(r.char_count for r in rows),
        },
    )
