"""Sector-level loan exposure extractor — Stage 2 / Stage 3 / ECL by sector.

Every BRSA audit report includes a table titled along the lines of
"Information by major sectors and type of counterparties" (EN) or
"Önemli Sektörlere veya Karşı Taraf Türüne Göre Muhtelif Bilgiler" (TR).
Three numeric columns per row:
  - Stage 2 — loans with significant increase in credit risk
  - Stage 3 — defaulted / impaired loans (the NPL gross amount per sector)
  - ECL    — expected credit loss provisions for the row

Sector taxonomy is universal across all 31 banks (BRSA-mandated):
  Agriculture
    Farming and Stockbreeding / Forestry / Fishery
  Manufacturing
    Mining and Quarrying / Production / Electricity, Gas and Water
  Construction
  Services
    Wholesale and Retail Trade / Accommodation and Dining /
    Transportation and Telecommunication / Financial Institutions /
    Real Estate and Rental Services / Professional Services /
    Educational Services / Health and Social Services
  Other
  Total

Output rows are tagged with `period_type='current'` for the current
period and `period_type='prior'` for the comparative when the bank
publishes both (most do, on adjacent pages or in stacked tables).
"""
from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

from .extractor import _HAS_FITZ, _fitz_page_text, _n_pages, parse_num


# ---------------------------------------------------------------------------
# Sector taxonomy
# ---------------------------------------------------------------------------
# Map every observed row label (TR + EN, with minor variants) to a canonical
# English sector key. The canonical form is what gets stored in the DB so
# downstream queries don't have to deal with bilingual / capitalisation
# variants. Keys are matched as substrings, longest-first, on lowercased
# input.
_SECTOR_LABELS: list[tuple[str, str]] = [
    # --- Agriculture group -------------------------------------------------
    ("farming and stockbreeding", "agri_farming"),
    ("farming and raising livestock", "agri_farming"),  # YKBNK wording
    ("çiftçilik ve hayvancılık", "agri_farming"),
    ("forestry", "agri_forestry"),
    ("ormancılık", "agri_forestry"),
    ("fishery", "agri_fishery"),
    ("fishing", "agri_fishery"),                         # YKBNK wording
    ("balıkçılık", "agri_fishery"),
    ("agricultural", "agri_total"),                      # YKBNK wording ("Agricultural")
    ("agriculture", "agri_total"),
    ("tarım", "agri_total"),
    # --- Manufacturing group ----------------------------------------------
    ("mining and quarrying", "mfg_mining"),
    ("madencilik ve taşocakçılığı", "mfg_mining"),
    ("madencilik", "mfg_mining"),
    ("production", "mfg_production"),
    ("manufacturing industry", "mfg_production"),  # QNBFB: the İmalat sub, NOT the group total (which is "Manufacturing")
    ("imalat sanayi", "mfg_production"),
    ("i̇malat sanayi", "mfg_production"),
    ("electricity, gas and water", "mfg_utilities"),
    ("electricity, gas, water", "mfg_utilities"),
    ("elektrik, gaz, su", "mfg_utilities"),
    ("elektrik. gaz. su", "mfg_utilities"),
    # The Turkish "Sanayi" sometimes appears as a group header (sum-row);
    # we still capture it under a distinct key so it's separable.
    ("manufacturing", "mfg_total"),
    ("industry", "mfg_total"),  # ISCTR's sector-2 parent is "Industry", not "Manufacturing"
    ("sanayi", "mfg_total"),
    # --- Construction (no sub) --------------------------------------------
    ("construction", "construction"),
    ("inşaat", "construction"),
    ("i̇nşaat", "construction"),
    # --- Services group ----------------------------------------------------
    ("wholesale and retail trade", "svc_trade"),
    ("toptan ve perakende ticaret", "svc_trade"),
    ("accommodation and dining", "svc_hospitality"),
    ("hotel, food and beverage services", "svc_hospitality"),  # YKBNK wording
    ("hotel and restaurant services", "svc_hospitality"),
    ("otel ve lokanta hizmetleri", "svc_hospitality"),
    ("transportation and telecommunication", "svc_transport"),
    ("transportation and telecom", "svc_transport"),
    ("ulaştırma ve haberleşme", "svc_transport"),
    ("financial institutions", "svc_financial"),
    ("mali kuruluşlar", "svc_financial"),
    ("real estate and rental services", "svc_realestate"),
    ("real estate and rental", "svc_realestate"),
    ("real estate and renting", "svc_realestate"),  # YKBNK wording ("renting")
    ("gayrimenkul ve kira", "svc_realestate"),
    ("professional services", "svc_professional"),
    ("independent business services", "svc_professional"),  # QNBFB wording
    ("serbest meslek hizmetleri", "svc_professional"),
    ("educational services", "svc_education"),
    ("education services", "svc_education"),  # YKBNK wording ("Education" not "Educational")
    ("eğitim hizmetleri", "svc_education"),
    ("health and social services", "svc_health"),
    ("sağlık ve sosyal hizmetler", "svc_health"),
    ("services", "svc_total"),
    ("hizmetler", "svc_total"),
    # --- Other / Total ----------------------------------------------------
    ("others", "other"),
    ("other", "other"),
    ("diğer", "other"),
    ("total", "total"),
    ("toplam", "total"),
]
# Compile a longest-first regex that captures whichever known label appears
# at the start of a (stripped) row. Using a single alternation keeps the
# scan cheap.
_SECTOR_LABELS_SORTED = sorted(_SECTOR_LABELS, key=lambda kv: -len(kv[0]))
_LABEL_TO_KEY = dict(_SECTOR_LABELS_SORTED)
_LABEL_RX = re.compile(
    r"^(?P<label>(?:"
    + "|".join(re.escape(lbl) for lbl, _ in _SECTOR_LABELS_SORTED)
    + r"))(?P<rest>\s+.+)?$",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Heading detector
# ---------------------------------------------------------------------------
# Match the heading that introduces the cash-loan sector table. We avoid
# matching the non-cash variants (which we'd want to extract separately
# later) and the deposit-side breakdowns.
_HEADING_PATTERNS = [
    re.compile(
        # YKBNK titles the cash-loan table "Information according to sectors and
        # counterparties" — "according to" is folded in below so the broad
        # "Information …" alt covers it WITHOUT also matching the risk-profile
        # table "2.8. Risk profile according to sectors and counterparties" (no
        # "Information" prefix) or the equity-investment one (excluded separately).
        r"(?:Information\s+(?:by|on|according\s+to)\s+(?:major\s+)?sectors?|"
        r"major\s+sectors?\s+(?:or|and)\s+type\s+of\s+counterparties?|"
        # ISCTR/SKBNK: "Information According to (Type of) Counterparty of/and
        # (Major) Sectors" — counterparty between "according to" and "sectors".
        r"Information\s+according\s+to\s+(?:type\s+of\s+)?counterpart\w*\s+(?:of|and)\s+(?:major\s+)?sectors?|"
        # ISCTR/EMLAK/ALBRK header variant "(Significant/Major) Sectors / Counterparty"
        # — ALBRK prints it bare ("Sectors / Counterparties"), prefix optional.
        r"(?:significant\s+|major\s+)?sectors?\s*/\s*counter|"
        r"sectoral\s+concentration\s+of\s+(?:cash\s+)?loans?|"
        # "Önemli Sektörler" (EMLAK "…Sektörler/Karşı Taraflar") + "…Sektörlere".
        r"Önemli\s+Sektörler|"
        r"sektörlere?\s+göre\s+kırılım)",
        re.IGNORECASE,
    ),
]
# Pages we *don't* want — non-cash loan sector tables. The non-cash version
# uses TL/FC columns and percentages; we recognise it by '(%)' headers.
_NONCASH_HINTS = re.compile(
    r"(non[\s-]?cash|gayri\s*nakdi|sectoral\s+risk\s+concentration\s+of\s+non[\s-]?cash)",
    re.IGNORECASE,
)
# WRONG table: "Information on sectors and the carrying amounts of (consolidated)
# investments" is the equity-participations-by-sector footnote, NOT loans — it
# matches the broad "Information on sectors" alt above and (e.g. for YKBNK, where
# the real loans table reads "according to sectors and counterparties") gets
# grabbed instead. Exclude any page whose sector heading is about carrying
# amounts of investments.
_WRONG_TABLE_HINTS = re.compile(
    r"carrying\s+amounts?\s+of\s+(?:(?:un)?consolidated\s+)?investments", re.IGNORECASE)


@dataclass
class SectorRow:
    sector: str                       # canonical key (e.g. 'mfg_production')
    stage2_amount: float | None = None
    stage3_amount: float | None = None
    ecl_amount: float | None = None
    period_type: str = "current"      # 'current' | 'prior'
    page: int = 0
    raw_label: str = ""               # original label as it appeared, for debug


@dataclass
class LoansBySectorReport:
    pdf_path: str = ""
    rows: list[SectorRow] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Number parser shared with extractor.parse_num — but we accept '-' as zero
# (audit reports use '-' for "nil" entries).
# ---------------------------------------------------------------------------
def _parse_amount(s: str) -> float | None:
    s = s.strip()
    if not s or all(c in "-–—" for c in s):  # "", "-", "--", "—" … → nil
        return 0.0
    return parse_num(s)


# Three numbers in a row, separated by whitespace, optionally with commas
# inside numbers and an optional leading footnote ref like "(1)". A nil cell is
# one OR MORE dashes ("--" as well as "-", en/em variants) — accept a run, else a
# trailing "--" drops the row (e.g. FIBA's "Balıkçılık -- -- --" got merged with
# the next line and grabbed the wrong sector's numbers → Σ sectors ≠ total → fail).
# Leading group is \d{1,4} not \d{1,3}: a few reports print a missing-separator
# typo like "1466,551" (= 1.466.551) — with \d{1,3} the regex matches only the
# "466,551" suffix and silently drops the leading digit (ICBCT 2025Q4 Hizmetler).
# For well-formed numbers the leading group is still bounded by the next
# separator, so this only ever helps (and reads bare 4-digit numbers correctly).
_NUM_TOKEN = r"(?:\(?\d{1,4}(?:[.,]\d{3})*(?:[.,]\d+)?\)?|[-–—]+)"
_THREE_NUMS_TAIL = re.compile(
    rf"(?P<n1>{_NUM_TOKEN})\s+(?P<n2>{_NUM_TOKEN})\s+(?P<n3>{_NUM_TOKEN})\s*$"
)


def _merge_wrapped_labels(lines: list[str]) -> list[str]:
    """Merge a label split across two lines: "Transportation and\nTelecommunication 1 2 3"
    becomes "Transportation and Telecommunication 1 2 3". Only merges when
    the *next* line has 3 trailing numbers (the table-row pattern) and the
    *current* line has no numbers anywhere — keeps free-text paragraphs out."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        cur = lines[i]
        # Skip empty lines
        if not cur.strip():
            out.append(cur)
            i += 1
            continue
        cur_has_num = bool(re.search(r"\d", cur))
        # Only consider lines that look like label-continuations:
        # short (<=80 chars), no digits at all, no terminating period
        # (avoid swallowing the end of a sentence).
        looks_like_label_head = (
            not cur_has_num
            # An all-nil row ("Balıkçılık -- -- --") has no digits but IS a
            # complete row — don't treat it as a label-head and merge it with the
            # next line (that grabbed the next sector's total → Σ ≠ total → fail).
            and not _THREE_NUMS_TAIL.search(cur.strip())
            and len(cur.strip()) <= 80
            and not cur.strip().endswith((".", ":", ";", "."))
        )
        if looks_like_label_head and i + 1 < len(lines):
            nxt = lines[i + 1]
            # Next line must end with 3 numbers to qualify as a wrapped row.
            if _THREE_NUMS_TAIL.search(nxt.strip()):
                merged = cur.strip() + " " + nxt.strip()
                out.append(merged)
                i += 2
                continue
        out.append(cur)
        i += 1
    return out


def _xy_lines(pdf_path: str, page_idx_0: int, ytol: float = 3.0
              ) -> list[list[tuple[float, float, str]]]:
    """Page words clustered into rows by y. Each row is a list of (x0, x1, text)
    sorted left-to-right. Adjacent single-digit fragments are merged (fitz
    occasionally splits a leading digit off a number)."""
    if not _HAS_FITZ:
        return []
    import fitz
    try:
        doc = fitz.open(pdf_path)
        words = doc[page_idx_0].get_text("words")
        doc.close()
    except Exception:
        return []
    if not words:
        return []
    buckets: dict[int, list[tuple[float, float, str]]] = defaultdict(list)
    for w in words:
        buckets[int(round(w[1]))].append((w[0], w[2], w[4]))
    keys = sorted(buckets)
    merged: dict[int, list[tuple[float, float, str]]] = {}
    last = None
    for k in keys:
        if last is not None and k - last <= ytol:
            merged[last].extend(buckets[k])
        else:
            merged[k] = list(buckets[k])
            last = k
    out: list[list[tuple[float, float, str]]] = []
    for y in sorted(merged):
        ws = sorted(merged[y], key=lambda t: t[0])
        toks: list[tuple[float, float, str]] = []
        i = 0
        while i < len(ws):
            x0, x1, t = ws[i]
            j = i + 1
            while j < len(ws):
                nx0, nx1, nt = ws[j]
                if re.match(r"^\d{1,2}$", t) and re.match(r"^[\d.,]", nt) and nx0 - x1 < 4:
                    t, x1 = t + nt, nx1
                    j += 1
                else:
                    break
            toks.append((x0, x1, t))
            i = j
        out.append(toks)
    return out


def _stage_col_x(lines: list[list[tuple[float, float, str]]]) -> tuple[float | None, float | None]:
    """Right-edge x of the Stage 2 and Stage 3 column headers (leftmost pair —
    the loan columns sit left of any provision/ECL columns labelled the same)."""
    def clean(t: str) -> str:
        return t.lower().strip("().:%–-—* ")
    s2 = s3 = None
    for row in lines:
        for i, (x0, x1, t) in enumerate(row):
            c = clean(t)
            x = x1
            if c in ("stage2", "2.aşama", "2aşama"):
                pass
            elif c in ("stage", "aşama") and i + 1 < len(row):
                n = clean(row[i + 1][2])
                if n == "2":
                    x, c = row[i + 1][1], "stage2"
                elif n == "3":
                    x, c = row[i + 1][1], "stage3"
                else:
                    continue
            elif c in ("second", "ikinci", "i̇kinci") and i + 1 < len(row) \
                    and clean(row[i + 1][2]) in ("stage", "aşama"):
                # EXIM-style "(Second Stage)" / "İkinci Aşama"
                x, c = row[i + 1][1], "stage2"
            elif c in ("third", "üçüncü", "uçuncu") and i + 1 < len(row) \
                    and clean(row[i + 1][2]) in ("stage", "aşama"):
                x, c = row[i + 1][1], "stage3"
            elif c in ("stage3", "3.aşama", "3aşama"):
                c = "stage3"
            else:
                continue
            if c == "stage2" and (s2 is None or x < s2):
                s2 = x
            elif c == "stage3" and (s3 is None or x < s3):
                s3 = x
    return s2, s3


def _extract_section_xy(page_idx: int, lines: list[list[tuple[float, float, str]]]
                        ) -> list[SectorRow] | None:
    """Column-aware extraction: align each row's numbers to the Stage 2 / Stage 3
    header columns by x-position. Robust to banks that add a gross-Loans column
    before the stages or provision/ECL columns after (QNBFB's 5-column layout),
    which the trailing-3-numbers heuristic mis-reads. Returns None (→ caller falls
    back to the text parser) when the stage headers can't be located."""
    s2x, s3x = _stage_col_x(lines)
    if s2x is None or s3x is None or abs(s2x - s3x) < 8:
        return None
    rows: list[SectorRow] = []
    period_type = "current"
    seen_current = False
    for row in lines:
        text = " ".join(t for _, _, t in row).strip()
        low = text.lower()
        if re.search(r"\bcurrent\s+period\b|\bcari\s+dönem\b", low):
            period_type, seen_current = "current", True
            continue
        if re.search(r"\bprior\s+period\b|\bönceki\s+dönem\b", low):
            if seen_current:
                period_type = "prior"
            continue
        clean = re.sub(r"^(?:\(\w\)|[\w.]{1,5})[.\)]\s+", "", text)
        clean = re.sub(r"^\(\d+\)\s+", "", clean)
        # VAKIFK/ANADOLU/TFKB number their sector rows "1 Tarım" / "2.2 İmalat"
        # — a bare index with NO trailing dot, which the rules above leave intact.
        clean = re.sub(r"^\d+(?:\.\d+)*\s+", "", clean)
        sector_key = None
        for lbl, key in _SECTOR_LABELS_SORTED:
            if clean.lower().startswith(lbl):
                sector_key = key
                break
        if sector_key is None:
            continue
        # numbers with their right-edge x (skip the label tokens)
        nums = [(_parse_amount(t), x1) for _x0, x1, t in row if re.fullmatch(_NUM_TOKEN, t)]
        nums = [(v, x) for v, x in nums if v is not None]
        if not nums:
            continue

        def nearest(anchor: float, other: float):
            best, bestd = None, 1e9
            for v, x in nums:
                d = abs(x - anchor)
                if d < bestd and d <= abs(x - other):  # closer to this column than the other
                    best, bestd = v, d
            return best

        s2v = nearest(s2x, s3x)
        s3v = nearest(s3x, s2x)
        rows.append(SectorRow(
            sector=sector_key, stage2_amount=s2v, stage3_amount=s3v,
            ecl_amount=None, period_type=period_type, page=page_idx,
            raw_label=clean[:60],
        ))
    return rows or None


def _extract_section(page_idx: int, text: str) -> list[SectorRow]:
    """Pull every (sector, n1, n2, n3) tuple from this page's text.

    Each sector heading line has the pattern
        <known_sector_label> <stage2> <stage3> <ecl>
    occasionally with a leading hierarchy code ("a. Tarım") or a footnote
    ref. We strip those before matching.

    A bank that reports current + prior comparatives often does so by
    repeating the entire table twice on the same page (or on adjacent
    pages) with a "Current Period" / "Prior Period" caption between
    them. We tag rows by whichever caption most-recently preceded them.
    """
    rows: list[SectorRow] = []
    period_type = "current"
    seen_current_caption = False
    raw_lines = text.splitlines()
    merged_lines = _merge_wrapped_labels(raw_lines)
    for raw in merged_lines:
        ln = raw.strip()
        if not ln:
            continue
        lower = ln.lower()
        # Period captions reset the period_type
        if re.search(r"\bcurrent\s+period\b|\bcari\s+dönem\b", lower):
            period_type = "current"
            seen_current_caption = True
            continue
        if re.search(r"\bprior\s+period\b|\bönceki\s+dönem\b", lower):
            # Only flip to prior once we've seen a current caption — some
            # banks print "Prior Period - 31.12.2024" as a column header
            # on the first table, which doesn't mean the rows are prior.
            if seen_current_caption:
                period_type = "prior"
            continue
        # Strip a leading hierarchy code: "a. ", "1. ", "i. ", "1.1.1 ", "(a) "
        ln_clean = re.sub(r"^(?:\(\w\)|\w{1,3})[\.\)]\s+", "", ln)
        # Strip leading footnote refs
        ln_clean = re.sub(r"^\(\d+\)\s+", "", ln_clean)
        # TFKB numbers its rows "1 Tarım" / "2.2 İmalat" — a bare index, no dot.
        ln_clean = re.sub(r"^\d+(?:\.\d+)*\s+", "", ln_clean)
        # Attempt to locate three trailing numbers
        m_nums = _THREE_NUMS_TAIL.search(ln_clean)
        if not m_nums:
            continue
        label_part = ln_clean[: m_nums.start()].strip()
        if not label_part:
            continue
        # Match the label against our taxonomy. Try the whole label first,
        # then progressively trim trailing footnote markers like "(*)".
        candidate = label_part
        candidate = re.sub(r"\(\*+\)\s*$", "", candidate).strip()
        candidate = re.sub(r"\(\d+\)\s*$", "", candidate).strip()
        # Match against the known-label table (case-insensitive).
        sector_key = None
        for lbl, key in _SECTOR_LABELS_SORTED:
            # Match as a prefix or exact match on the lowercased label
            if candidate.lower().startswith(lbl):
                # Reject if the label is "manufacturing" but the row is the
                # full Turkish phrase "imalat sanayi" appearing after it.
                # Longest-first ordering handles this naturally.
                sector_key = key
                break
        if sector_key is None:
            continue
        n2 = _parse_amount(m_nums.group("n1"))
        n3 = _parse_amount(m_nums.group("n2"))
        ecl = _parse_amount(m_nums.group("n3"))
        rows.append(SectorRow(
            sector=sector_key,
            stage2_amount=n2,
            stage3_amount=n3,
            ecl_amount=ecl,
            period_type=period_type,
            page=page_idx,
            raw_label=candidate,
        ))
    return rows


def _page_has_sector_heading(text: str) -> bool:
    if _WRONG_TABLE_HINTS.search(text):
        # Page is the investments-by-sector footnote, not what we want.
        return False
    return any(rx.search(text) for rx in _HEADING_PATTERNS)


# Tier-1 sectors (the parents that sum their sub-sectors). Useful for
# downstream consumers that want either the parent or the leaf level.
PARENT_SECTORS = {"agri_total", "mfg_total", "construction", "svc_total", "other", "total"}


def extract_from_pdf(
    pdf: pdfplumber.PDF,
    pdf_path: str = "",
    skip_pages: int = 30,
) -> LoansBySectorReport:
    """Scan the PDF for the sector-by-loan-stage table.

    `skip_pages` skips the BS/PL statements — the cash-sector table is
    always in the credit-risk footnote section (typically pages 50–80
    in Turkish audit reports, ~60-100 in English ones), never in the
    early statement pages.
    """
    # Scan + parse with fitz (the engine the statement locators use) — faster and
    # poison-hang-safe, consistent with the OCI/CF/NPL lanes; fitz's row text
    # parses identically here. Falls back to pdfplumber text only without fitz.
    rep = LoansBySectorReport(pdf_path=pdf_path)
    use_fitz = _HAS_FITZ and bool(pdf_path)
    n_pages = _n_pages(pdf) if use_fitz else len(pdf.pages)
    # Build BOTH parses — x-coordinate column alignment (handles gross-Loans-first
    # and provision/ECL columns, e.g. QNBFB's 5-column table) and the legacy
    # trailing-3-numbers text parser — then keep whichever FOOTS better (Σ
    # top-level sectors ≈ total). This guarantees the new aligner never regresses
    # a bank the text parser already read correctly.
    xy_rows: list[SectorRow] = []
    txt_rows: list[SectorRow] = []
    for i in range(skip_pages + 1, n_pages + 1):
        text = (_fitz_page_text(pdf_path, i - 1) if use_fitz
                else (pdf.pages[i - 1].extract_text() or ""))
        if not _page_has_sector_heading(text):
            continue
        lines = _xy_lines(pdf_path, i - 1) if use_fitz else None
        # Non-cash sector table: skip — UNLESS the page also carries the cash
        # table's Stage 2/3 LOAN columns. ANADOLU mentions "gayri nakdi krediler"
        # in a sector ROW of the cash table, which must not exclude the page.
        if _NONCASH_HINTS.search(text):
            s2, s3 = _stage_col_x(lines) if lines else (None, None)
            if s2 is None or s3 is None:
                continue
        if use_fitz and lines is not None:
            xy = _extract_section_xy(i, lines)
            # GARAN unconsolidated splits the table: the stage-column HEADER sits on
            # this page but the sector ROWS are on the next (which has no heading, so
            # it's skipped). If this heading page has stage columns but yielded no
            # rows, retry with the next page's lines appended so they align to this
            # page's columns.
            if not xy and i < n_pages:
                s2, s3 = _stage_col_x(lines)
                if s2 is not None and s3 is not None:
                    xy = _extract_section_xy(i, lines + _xy_lines(pdf_path, i))
                    txt_rows.extend(_extract_section(i + 1, _fitz_page_text(pdf_path, i)))
            if xy:
                xy_rows.extend(xy)
        txt_rows.extend(_extract_section(i, text))

    def _dedupe(rows: list[SectorRow]) -> list[SectorRow]:
        # Keep the first occurrence of each (sector, period_type) — EXCEPT 'total':
        # a page can carry two sector tables (e.g. ICBCT's loans then a second
        # breakdown), each ending in its own "Toplam", so keep every total and let
        # _pick_total choose the one that foots with the captured sectors.
        seen: set[tuple[str, str]] = set()
        out: list[SectorRow] = []
        for idx, r in enumerate(rows):
            key = (r.sector, r.period_type, idx) if r.sector == "total" else (r.sector, r.period_type)
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
        return _pick_total(out)

    xy_d, txt_d = _dedupe(xy_rows), _dedupe(txt_rows)
    rep.rows = xy_d if (xy_d and _foot_error(xy_d) <= _foot_error(txt_d)) else txt_d
    return rep


def _pick_total(rows: list[SectorRow]) -> list[SectorRow]:
    """When several current-period 'total' rows survive (multi-table page), keep
    the one whose stage2+stage3 best match the sum of the top-level sectors and
    drop the rest. No-op for the usual single-total table."""
    totals = [r for r in rows if r.sector == "total" and r.period_type == "current"]
    if len(totals) <= 1:
        return rows
    from .validator import _resolved_top_level
    cur = [{"sector": r.sector, "stage2_amount": r.stage2_amount,
            "stage3_amount": r.stage3_amount}
           for r in rows if r.period_type == "current" and r.sector != "total"]
    top = _resolved_top_level(cur)
    sums = {c: sum(r[c] for r in top if r.get(c) is not None)
            for c in ("stage2_amount", "stage3_amount")}

    def err(t: SectorRow) -> float:
        e = 0.0
        for c in ("stage2_amount", "stage3_amount"):
            tv = getattr(t, c)
            if tv is not None:
                e += abs((tv or 0) - sums[c]) / max(1.0, abs(tv) or 1.0)
        return e

    best = min(totals, key=err)
    drop = {id(t) for t in totals if t is not best}
    return [r for r in rows if id(r) not in drop]


def _foot_error(rows: list[SectorRow]) -> float:
    """Relative error of Σ top-level sectors vs the total row (avg over the
    stage2/stage3 columns) — used to pick the better of two parses. Big sentinel
    when there's no total row to check against."""
    from .validator import _resolved_top_level
    cur = [{"sector": r.sector, "stage2_amount": r.stage2_amount,
            "stage3_amount": r.stage3_amount}
           for r in rows if r.period_type == "current"]
    total = next((r for r in cur if r["sector"] == "total"), None)
    if total is None:
        return 1e18
    top = _resolved_top_level(cur)
    if not top:
        return 1e18
    errs = []
    for col in ("stage2_amount", "stage3_amount"):
        tv = total.get(col)
        if tv is None:
            continue
        sv = sum(r[col] for r in top if r.get(col) is not None)
        errs.append(abs(sv - tv) / max(1.0, abs(tv)))
    return sum(errs) / len(errs) if errs else 1e18


def extract(pdf_path: str | Path) -> LoansBySectorReport:
    """Convenience wrapper for callers that don't already have a PDF handle."""
    pdf_path = str(pdf_path)
    with pdfplumber.open(pdf_path) as pdf:
        return extract_from_pdf(pdf, pdf_path)


# ---------------------------------------------------------------------------
# DB loader
# ---------------------------------------------------------------------------
def upsert(
    conn: sqlite3.Connection,
    bank_ticker: str,
    period: str,
    kind: str,
    rep: LoansBySectorReport,
) -> int:
    """Idempotently store one bank's sector rows. Returns row count."""
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM bank_audit_loans_by_sector "
        "WHERE bank_ticker=? AND period=? AND kind=?",
        (bank_ticker, period, kind),
    )
    rows = [(
        bank_ticker, period, kind, r.sector, r.period_type,
        r.page, r.stage2_amount, r.stage3_amount, r.ecl_amount,
        r.raw_label,
    ) for r in rep.rows]
    if rows:
        cur.executemany(
            "INSERT INTO bank_audit_loans_by_sector "
            "(bank_ticker, period, kind, sector, period_type, source_page, "
            " stage2_amount, stage3_amount, ecl_amount, raw_label) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
    conn.commit()
    return len(rows)


def summarize(rep: LoansBySectorReport) -> str:
    if not rep.rows:
        return f"{Path(rep.pdf_path).name}\n  (no sector table found)"
    lines = [Path(rep.pdf_path).name]
    for r in rep.rows:
        s2 = f"{r.stage2_amount:,.0f}" if r.stage2_amount is not None else "-"
        s3 = f"{r.stage3_amount:,.0f}" if r.stage3_amount is not None else "-"
        ecl = f"{r.ecl_amount:,.0f}" if r.ecl_amount is not None else "-"
        lines.append(
            f"  p.{r.page:>3}  {r.period_type:<7}  {r.sector:<18}  "
            f"S2={s2:>18}  S3={s3:>18}  ECL={ecl:>18}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    path = sys.argv[1] if len(sys.argv) > 1 else "data/_tmp_akbnk_2025q4.pdf"
    rep = extract(path)
    print(summarize(rep))
