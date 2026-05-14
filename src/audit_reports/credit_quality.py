"""IFRS 9 credit-quality extraction from BRSA audit-report PDFs.

Banks must disclose loan portfolios staged per TFRS 9 (Aşama 1/2/3):
  Stage 1 = performing
  Stage 2 = significant increase in credit risk
  Stage 3 = non-performing (NPL)

The disclosures appear in the footnotes as multi-line "movement" tables with a
fixed column header — "Stage 1 / Stage 2 / Stage 3 / Total" (or the Turkish
"Aşama 1 / Aşama 2 / Aşama 3 / Toplam") — and a final summary row
("Period end Balance" / "Balances at End of Period" / "Dönem Sonu (date)").

We extract that final summary row for **every** such table in the PDF and
label each by the section heading immediately above it (loans-ECL, cash-ECL,
amortised-cost-ECL, non-cash-loans-ECL, or "other"). The most analytically
valuable section is `loans_ecl` (Stage 3 = NPL provisions) and, where the
bank provides it, `loans_amounts` (Stage 3 = NPL balance).

Layout varies a lot bank-to-bank:
  * AKBNK / HALKB / Ziraat — Turkish "Aşama 1/2/3/Toplam" movement table.
  * GARAN — English Stage 1/2/3/Total movement table, plus a separate
    summary table with TL/FC split per stage on a different page.
  * Some banks omit the loan-amount summary entirely; only the ECL table
    is present.

The extractor is intentionally tolerant: it captures whatever it can find and
stores rows with a section label. Downstream code can filter to the rows it
cares about (e.g. `section='loans_ecl'`).
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

from .extractor import NUM_PAT as _NUM_PAT_STR
from .extractor import parse_num

# -- Header-row detector -----------------------------------------------------
#
# Match the four-column header that introduces a Stage 1/2/3/Total table.
# Whitespace tolerance is wide because pdfplumber sometimes collapses spaces.
_STAGE_HEADER_EN = re.compile(
    r"Stage\s*1\s+Stage\s*2\s+Stage\s*3\s+Total",
    re.IGNORECASE,
)
_STAGE_HEADER_TR = re.compile(
    r"(?:1\.?\s*Aşama|Aşama\s*1)\s+(?:2\.?\s*Aşama|Aşama\s*2)"
    r"\s+(?:3\.?\s*Aşama|Aşama\s*3)\s+(?:Toplam|Total)",
)
# Some Turkish reports drop the "Total" column entirely (AKBNK page 46 ECL
# table is 3-col Aşama 1/2/3 without a Toplam). We still want to catch those.
_STAGE_HEADER_TR_3COL = re.compile(
    r"(?:Aşama\s*1)\s+(?:Aşama\s*2)\s+(?:Aşama\s*3)(?!\s*(?:Toplam|Total))",
)

# -- "Period-end balance" row detector ---------------------------------------
#
# Several wordings used across banks:
#   English:  "Balances at End of Period", "Period end Balance", "Closing Balance"
#   Turkish:  "Dönem Sonu" (often followed by a date in parens)
_END_ROW_PAT = re.compile(
    r"^(?P<label>"
    r"(?:Balances?\s+at\s+End\s+of\s+(?:the\s+)?Period"
    r"|Period[\s-]*end[\s-]*Balance"
    r"|Provisions?\s+at\s+End\s+of\s+(?:the\s+)?Period"
    r"|Closing\s+Balance"
    r"|Dönem\s*Sonu(?:\s*\([^)]*\))?"
    r"|Period\s+End(?:\s+Balance)?"
    r")"
    r")\s+(?P<rest>.*)$",
    re.IGNORECASE,
)

# Compiled form of extractor.NUM_PAT for cheap repeated findall.
# Numeric-token regex + TR/EN-aware parser are shared with the main extractor —
# keeping a single implementation avoids the two parsers diverging.
_NUM = re.compile(_NUM_PAT_STR)


# -- Section classifier ------------------------------------------------------
#
# Given a chunk of text that PRECEDES a Stage-header on the same page, pick
# a section label. Order matters — more-specific patterns first.
_SECTION_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("cash_ecl", re.compile(
        r"(?:Expected\s+credit\s+loss(?:es)?\s+for\s+cash"
        r"|Nakit\s+(?:ve\s+)?(?:nakit\s+)?benzer(?:ler)?i?\s+için)",
        re.IGNORECASE,
    )),
    ("amortised_cost_ecl", re.compile(
        r"(?:Expected\s+credit\s+loss(?:es)?\s+for\s+financial\s+assets"
        r"\s+(?:measured\s+at\s+)?amortis|"
        r"İtfa\s+edilmiş\s+maliyeti\s+ile)",
        re.IGNORECASE,
    )),
    ("non_cash_ecl", re.compile(
        r"(?:Expected\s+(?:credit\s+)?loss(?:es)?\s+for\s+non[\s-]*cash"
        r"|Gayrinakdi\s+kredi(?:ler)?\s+için)",
        re.IGNORECASE,
    )),
    # Loan ECL — covers AKBNK "Krediler için ayrılan beklenen zarar
    # karşılıkları", HALKB "Information regarding expected credit loss
    # provisions", GARAN "Expected credit loss for loans".
    ("loans_ecl", re.compile(
        r"(?:Expected\s+credit\s+loss(?:es)?\s+for\s+loans"
        r"|Information\s+regarding\s+expected\s+credit\s+loss"
        r"|Krediler\s+için\s+ayrılan\s+beklenen\s+zarar"
        r"|beklenen\s+zarar\s+karşılıklarına\s+ilişkin)",
        re.IGNORECASE,
    )),
    # Loan movements (actual amounts) — AKBNK "j. Kredi hareketlerine ilişkin".
    ("loans_amounts", re.compile(
        r"(?:Kredi\s+hareketlerine\s+ilişkin"
        r"|Loan\s+movements"
        r"|Movement(?:s)?\s+of\s+loans)",
        re.IGNORECASE,
    )),
]


def _classify_section(preceding_text: str) -> tuple[str, str]:
    """Pick a section label for a stage-table based on the heading above it.

    Returns (section_id, matched_snippet). Falls back to ('other_ecl', '')
    when nothing matched."""
    # Search bottom-up: the closest heading wins.
    chunks = [c.strip() for c in preceding_text.split("\n") if c.strip()]
    for line in reversed(chunks[-15:]):  # only look at last ~15 lines
        for sect, pat in _SECTION_PATTERNS:
            if pat.search(line):
                return sect, line[:120]
    return "other_ecl", ""


# -- Period detector ---------------------------------------------------------
#
# When two stage-tables sit back-to-back, the first is usually labeled
# "Current Period" and the second "Prior Period". We tag them so callers can
# pick whichever they want.
_CURRENT_PAT = re.compile(r"(?:Current\s+Period|Cari\s+Dönem)", re.IGNORECASE)
_PRIOR_PAT = re.compile(r"(?:Prior\s+Period|Önceki\s+Dönem|Geçmiş\s+Dönem)", re.IGNORECASE)
# Tokens that mean the line is a movement-table ROW LABEL ("Prior period end
# balance" / "Önceki Dönem Sonu Bakiyesi"), NOT a period-context header.
_ROW_LABEL_TOKENS = re.compile(
    r"(?:balance|bakiye|provision|karşılı|net\s|sonu)",
    re.IGNORECASE,
)


def _detect_period_type(line: str) -> str | None:
    """Return 'current' / 'prior' if line is a period CONTEXT header, else None.

    Ignores:
      * movement-table row labels like 'Prior period end balance' /
        'Önceki Dönem Sonu Bakiyesi' (contains balance/sonu/etc.)
      * sub-table data rows like 'Önceki Dönem 243.535 215.200 4.290.210'
        (a row label that happens to be the period word, with thousands-
        separated values trailing). DENIZ uses this for its restructured-loans
        sub-table just above the main NPL classification block.
    """
    s = line.strip()
    # Real period headers are short ("Current Period" / "Cari Dönem - 31 Aralık 2024").
    if len(s) > 80:
        return None
    if _ROW_LABEL_TOKENS.search(s):
        return None
    # Real period headers carry 0 or 1 thousands-separated numeric tokens
    # (rare — sometimes a year-with-dots like "31.12.2024"). 2+ such tokens
    # means this is a data row, not a header.
    if len(re.findall(r"\d{1,3}(?:[.,]\d{3})+", s)) >= 2:
        return None
    if _PRIOR_PAT.search(s):
        return "prior"
    if _CURRENT_PAT.search(s):
        return "current"
    return None


@dataclass
class StageRow:
    section: str
    period_type: str            # 'current' | 'prior'
    page: int
    stage1: float | None
    stage2: float | None
    stage3: float | None
    total: float | None
    heading: str = ""


@dataclass
class CreditQualityReport:
    pdf_path: str
    rows: list[StageRow] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _extract_from_page(page_num: int, page_text: str) -> list[StageRow]:
    """Find every Stage 1/2/3 table on a single page; pull its end-of-period row."""
    if not page_text:
        return []

    out: list[StageRow] = []
    lines = page_text.split("\n")

    # Locate stage-header line indices.
    header_idxs: list[tuple[int, int]] = []  # (line_idx, n_cols)
    for i, ln in enumerate(lines):
        if _STAGE_HEADER_EN.search(ln) or _STAGE_HEADER_TR.search(ln):
            header_idxs.append((i, 4))
        elif _STAGE_HEADER_TR_3COL.search(ln):
            # 3-col header (no Total column) — only useful for ECL movement
            # tables. Treat the missing 4th value as None.
            header_idxs.append((i, 3))

    if not header_idxs:
        return []

    # Walk each header → scan forward until we hit either:
    #   (a) the next header, or
    #   (b) end of page,
    # whichever comes first. Within that window, find the "Period End Balance" row.
    for k, (hidx, ncols) in enumerate(header_idxs):
        end = header_idxs[k + 1][0] if k + 1 < len(header_idxs) else len(lines)
        # Section label: the closest meaningful heading in the preceding ~15 lines.
        preceding = "\n".join(lines[max(0, hidx - 20): hidx])
        section, heading = _classify_section(preceding)

        # Period type: scan from the header line BACK up to 4 lines for a
        # "Current Period" / "Prior Period" marker. Most templates put it on
        # the same line as the header.
        period_type = None
        for j in range(hidx, max(-1, hidx - 5), -1):
            period_type = _detect_period_type(lines[j])
            if period_type:
                break
        period_type = period_type or "current"

        # Now find the end-of-period row anywhere between header+1 and `end`.
        for j in range(hidx + 1, end):
            ln = lines[j]
            m = _END_ROW_PAT.match(ln.strip())
            if not m:
                continue
            nums = _NUM.findall(m.group("rest"))
            if len(nums) < ncols:
                # Some banks split the row: label on one line, numbers on next.
                # Try concatenating up to 2 lookahead lines.
                joined = m.group("rest")
                for la in range(j + 1, min(j + 3, end)):
                    joined = joined + " " + lines[la]
                    nums = _NUM.findall(joined)
                    if len(nums) >= ncols:
                        break
            if len(nums) < ncols:
                continue
            # Take the LAST ncols numbers — protects against stray nums in the label.
            vals = [parse_num(n) for n in nums[-ncols:]]
            if ncols == 3:
                s1, s2, s3 = vals
                total = None
            else:
                s1, s2, s3, total = vals
            out.append(StageRow(
                section=section,
                period_type=period_type,
                page=page_num,
                stage1=s1, stage2=s2, stage3=s3, total=total,
                heading=heading,
            ))
            break  # only one end-row per stage-header block

    return out


# -- P&L-expense-decomposition pattern --------------------------------------
#
# Pattern observed in HALKB, AKTIF and many other smaller banks where the
# only Stage-broken-out figure is the period EXPENSE in the P&L:
#
#   "Expected Credit Losses                     35.144.908   7.249.890"
#   "12 Month Expected Credit Loss (Stage 1)    6.581.980     92.438"
#   "Significant Increase in Credit Risk (Stage 2)  3.490.980  499.231"
#   "Non – Performing Loans (Stage 3)           25.071.948   6.658.221"
#
# AKTIF Turkish variant:
#   "12 Aylık Beklenen Zarar Karşılığı (Birinci Aşama)   133.367  100.478"
#   "Kredi Riskinde Önemli Artış (İkinci Aşama)          169.029   26.238"
#   "Temerrüt (Üçüncü Aşama)                             387.940  174.074"
#
# Stage 3 of this section ≈ NPL provision EXPENSE for the period — a flow,
# not the stock that loans_ecl provides. Useful for small banks where the
# stock table isn't disclosed at all.
# Whitespace is `\s*` (not `\s+`) and singular/plural inflections are optional
# because pdfplumber occasionally drops inter-word spaces on some banks
# (TSKB/SKBNK) and English wording varies a lot:
#   "Expected Credit Loss" (Garanti) vs "credit losses" (YKBNK) vs "ECL" (SKBNK)
#   "12 Month" (HALKB) vs "12-Month" (SKBNK) vs "12 Months" (TSKB)
#   "Non-Performing Loans" (HALKB) vs "Impaired Loans / Credits" (SKBNK)
_STAGE_ROW_PATS = {
    1: re.compile(
        r"(?:"
        r"12[\s-]*Months?\s*(?:Expected\s*Credit\s*Loss(?:es)?|ECL)"
        r"\s*\(\s*Stage\s*1\s*\)"
        r"|12\s*Aylık\s*Beklenen\s*(?:Zarar\s*Karşılığı|Kredi\s*Zarar(?:ı|ları))"
        r"\s*\(\s*(?:Birinci\s+Aşama|1\.?\s*Aşama|Aşama\s*1)\s*\)"
        r")",
        re.IGNORECASE,
    ),
    2: re.compile(
        r"(?:"
        r"Significant\s*Increase\s*in\s*Credit\s*Risk\s*\(\s*Stage\s*2\s*\)"
        r"|Kredi\s*Riskinde\s*Önemli\s*Artış"
        r"\s*\(\s*(?:İkinci\s+Aşama|2\.?\s*Aşama|Aşama\s*2)\s*\)"
        r")",
        re.IGNORECASE,
    ),
    3: re.compile(
        r"(?:"
        r"(?:Non[\s–—-]*Performing\s*Loans?|Impaired\s*(?:Loans?|Credits?))"
        r"\s*\(\s*Stage\s*3\s*\)"
        r"|Temerrüt"
        r"\s*\(\s*(?:Üçüncü\s+Aşama|3\.?\s*Aşama|Aşama\s*3)\s*\)"
        r")",
        re.IGNORECASE,
    ),
}


# "Current Period" / "Cari Dönem" header — must appear within ~6 lines above
# the first stage row to confirm we're looking at a 2-column P&L expense table
# (vs. a 4-column cross-tab like SKBNK p116 with Corporate/SME/Consumer/Total
# segment columns that share the same `(Stage N)` row markers).
_PERIOD_HEADER_PAT = re.compile(
    r"(?:Current\s*Period|Cari\s*Dönem)", re.IGNORECASE,
)


def _extract_pl_expense_from_page(page_num: int, page_text: str) -> list[StageRow]:
    """Look for the P&L expense decomposition by stage. Returns 0 or 2 rows
    (current + prior, since these tables usually show both years side-by-side).

    The row labels contain stray digits ("12 Month...", "(Stage 2)") that
    must NOT be parsed as data values. We anchor by extracting numbers from
    the text AFTER the matched stage marker only.
    """
    if not page_text:
        return []
    lines = page_text.split("\n")
    matches: dict[int, list[float]] = {}
    first_stage_line_idx: int | None = None
    for line_idx, ln in enumerate(lines):
        for stage, pat in _STAGE_ROW_PATS.items():
            m = pat.search(ln)
            if not m or stage in matches:
                continue
            # Only parse numbers AFTER the stage marker (avoids the "12" in
            # "12 Month" and the "2"/"3" inside "(Stage 2)" / "(Stage 3)").
            tail = ln[m.end():]
            # Strip leading footnote refs like "(1)" / "(2)" that TSKB writes
            # right after the stage marker — otherwise NUM_PAT parses them as
            # negative single-digit values and shifts every column by one.
            tail = re.sub(r"^\s*\(\d{1,2}\)\s*", "", tail)
            nums = _NUM.findall(tail)
            if nums:
                parsed = [parse_num(n) for n in nums]
                matches[stage] = [v for v in parsed if v is not None]
                if first_stage_line_idx is None:
                    first_stage_line_idx = line_idx
            break
    if len(matches) < 3 or first_stage_line_idx is None:
        return []
    # Guard against cross-tab segment tables (Corporate / SME / Consumer / Total
    # columns share the same `(Stage N)` markers). Require a "Current Period"
    # header within 8 lines above the first stage row — confirms 2-column P&L.
    preceding = "\n".join(lines[max(0, first_stage_line_idx - 8): first_stage_line_idx])
    if not _PERIOD_HEADER_PAT.search(preceding):
        return []
    n_cols = min(len(matches[1]), len(matches[2]), len(matches[3]))
    # A real P&L expense table has 1 or 2 numeric columns. Anything wider is
    # almost certainly a cross-tab — refuse to emit garbled rows.
    n_cols = min(n_cols, 2)
    if n_cols == 0:
        return []
    out: list[StageRow] = []
    # First numeric column = current period; second (if any) = prior.
    for col, period_type in enumerate(("current", "prior")[:n_cols]):
        out.append(StageRow(
            section="loans_ecl_expense",
            period_type=period_type,
            page=page_num,
            stage1=matches[1][col],
            stage2=matches[2][col],
            stage3=matches[3][col],
            total=None,
            heading="",
        ))
    return out


# ---------------------------------------------------------------------------
# BRSA NPL classification table — universal across Turkish audit reports.
#
# Every BRSA-format audit report includes a footnote (typically "j.2 Information
# on the movement of non-performing loans" or "Gross and net non-performing
# loans as per customer categories") that classifies NPLs into three regulatory
# severity groups:
#   Group III  — Substandard / Tahsil İmkanı Sınırlı (limited collectability)
#   Group IV   — Doubtful / Tahsili Şüpheli
#   Group V    — Uncollectible / Zarar Niteliğindeki (loss)
#
# Sum of all three groups = total Stage 3 NPL loan balance. This is the data
# we need to compute the NPL ratio; the IFRS 9 stage-movement tables we
# already extract show only PROVISIONS, not the loan balances themselves.
#
# Table structure (universal):
#   <header row with III/IV/V Roman numerals>
#   ...intermediate movement rows...
#   <row label> 123,456 234,567 345,678   ← GROSS NPL by group
#   Provision (-) 50,000 80,000 200,000   ← provision against each group
#   <row label> 73,456 154,567 145,678    ← NET balance on balance sheet
#
# We anchor on the universal "Provision (-)" / "Karşılık (-)" row and read the
# immediately-adjacent gross/net rows.
# ---------------------------------------------------------------------------

# Header pattern — tolerates all 6 wording variants observed across 14 banks:
#   "III. Group / IV. Group / V. Group"  (HALKB, YKBNK, QNBFB)
#   "Group III / Group IV / Group V"     (GARAN, ALBRK)
#   "III. Grup / IV. Grup / V. Grup"     (Turkish — VAKBN, AKBNK, TEB, ...)
#   "III.Group / IV.Group / V.Group"     (TSKB — no space)
#   "III. Group: / IV. Group: / V. Group:" (SKBNK — colons)
_NPL_HEADER_PAT = re.compile(
    r"(?:Group\s+III|III\.?\s*(?:Group|Grup):?)"
    r"\s*(?:Group\s+IV|IV\.?\s*(?:Group|Grup):?)"
    r"\s*(?:Group\s+V|V\.?\s*(?:Group|Grup):?)",
    re.IGNORECASE,
)

# The "Provision (-)" / "Karşılık (-)" anchor row.
# Must be ANCHORED to the start of the (stripped) line — otherwise we match
# the row label "Loans to Individuals and Corporates (Net)" because some banks
# use "Provision" as part of column headers too.
# BURGAN uses "Specific Provision (-)" so we also accept that variant.
_NPL_PROVISION_ROW = re.compile(
    r"^\s*(?:Provision|Specific\s+Provision|Karşılık|Özel\s+Karşılık)\s*\(\s*-\s*\)",
    re.IGNORECASE,
)
# III/IV/V header pattern (line-anchored variant used by the block walker).
_NPL_HEADER_LINE = re.compile(
    r"^\s*(?:Group\s+III|III\.?\s*(?:Group|Grup):?)"
    r"\s+(?:Group\s+IV|IV\.?\s*(?:Group|Grup):?)"
    r"\s+(?:Group\s+V|V\.?\s*(?:Group|Grup):?)",
    re.IGNORECASE,
)
# A row qualifies as "data" if it has at least 3 numeric tokens with thousands
# separators (filters out short administrative rows like "Sold (-)").
_NPL_DATA_ROW_FILTER = re.compile(r"\d{1,3}[.,]\d{3}")


def _extract_npl_brsa_from_page(page_num: int, page_text: str) -> list[StageRow]:
    """Find the BRSA NPL classification table on this page and emit gross /
    provision / net rows. Each row carries Group III/IV/V in stage1/2/3 and
    III+IV+V sum in total.

    Returns 0 or up to 6 rows (3 row-kinds × 2 period-types).
    """
    if not page_text or not _NPL_HEADER_PAT.search(page_text):
        return []
    lines = page_text.split("\n")
    out: list[StageRow] = []

    # Pre-locate every III/IV/V header on the page — period detection is
    # scoped to the table block (header → next-header / EOF) instead of the
    # whole page, so a stray "Önceki Dönem" line from a different sub-table
    # higher up doesn't pollute the main NPL block's period_type. Some pages
    # have multiple III/IV/V tables (restructured-loans + main NPL + FC-NPL).
    header_idxs = [i for i, ln in enumerate(lines) if _NPL_HEADER_LINE.match(ln.strip())]

    def _period_for_provision(prov_idx: int) -> str:
        # Find the III/IV/V header band this provision row belongs to.
        block_start = 0
        for hi in header_idxs:
            if hi < prov_idx:
                block_start = hi
            else:
                break
        # Within the band, the LAST explicit period marker wins.
        for j in range(prov_idx, block_start - 1, -1):
            pt = _detect_period_type(lines[j].strip())
            if pt is not None:
                return pt
        # No marker in the band → default 'current' (first table on each page
        # almost always reports the current period).
        return "current"

    for i, ln in enumerate(lines):
        stripped = ln.strip()
        # Anchor: provision row.
        if not _NPL_PROVISION_ROW.match(stripped):
            continue
        current_period = _period_for_provision(i)
        nums = _NUM.findall(stripped)
        if len(nums) < 3:
            continue
        # The row label "Karşılık (-)" / "Provision (-)" already encodes that
        # values are deductions. Some banks (KLNMA / PASHA) ALSO write the
        # numbers in accounting parentheses, so parse_num returns negatives —
        # take abs to normalize to magnitude, matching the convention the
        # other banks use.
        prov = [abs(parse_num(n)) if parse_num(n) is not None else None
                for n in nums[-3:]]

        # Walk back up to 4 lines to find the gross row (3 numbers, doesn't
        # contain "Net" / "Provision" / "Karşılık"). Skip movement-table noise.
        gross = None
        for j in range(i - 1, max(-1, i - 5), -1):
            cand = lines[j].strip()
            if not _NPL_DATA_ROW_FILTER.search(cand):
                continue
            if re.search(r"\b(?:Net|Provision|Karşılık)\b", cand, re.IGNORECASE):
                continue
            cnums = _NUM.findall(cand)
            if len(cnums) >= 3:
                gross = [parse_num(n) for n in cnums[-3:]]
                break

        # Walk forward up to 4 lines to find the net row.
        net = None
        for j in range(i + 1, min(len(lines), i + 5)):
            cand = lines[j].strip()
            if not _NPL_DATA_ROW_FILTER.search(cand):
                continue
            if not re.search(r"\bNet\b", cand, re.IGNORECASE):
                # Continue past explanatory lines without "Net"; many banks have
                # a movement-table closing row right after Provision.
                continue
            cnums = _NUM.findall(cand)
            if len(cnums) >= 3:
                net = [parse_num(n) for n in cnums[-3:]]
                break

        def _sum_or_none(v: list[float | None]) -> float | None:
            clean = [x for x in v if x is not None]
            return sum(clean) if clean else None

        if gross is not None:
            out.append(StageRow(
                section="npl_brsa_gross", period_type=current_period, page=page_num,
                stage1=gross[0], stage2=gross[1], stage3=gross[2],
                total=_sum_or_none(gross), heading="III/IV/V groups",
            ))
        out.append(StageRow(
            section="npl_brsa_provision", period_type=current_period, page=page_num,
            stage1=prov[0], stage2=prov[1], stage3=prov[2],
            total=_sum_or_none(prov), heading="",
        ))
        if net is not None:
            out.append(StageRow(
                section="npl_brsa_net", period_type=current_period, page=page_num,
                stage1=net[0], stage2=net[1], stage3=net[2],
                total=_sum_or_none(net), heading="",
            ))
    return out


# ---------------------------------------------------------------------------
# BRSA "Standart Nitelikli ve Yakın İzlemedeki" loan-by-stage table.
#
# A mandated section in every Turkish-language BRSA audit report — typically
# section "7.2. Standart Nitelikli ve Yakın İzlemedeki (Birinci ve İkinci
# Grup Krediler) İle Yeniden Yapılandırılan Yakın İzlemedeki Kredilere
# İlişkin Bilgiler" (or the English equivalent "Performing Loans and Loans
# Under Close Monitoring").
#
# Structure (Cari Dönem / Current Period block):
#   Header: "Standart Nitelikli Krediler | <2-3 sub-columns of Yakın İzlemedeki>"
#   Rows:   industry segments (İhtisas Dışı Krediler / İhracat / Tüketici / etc.)
#   Final:  "Toplam <S1> <S2-not-restructured> <S2-restructured-decision-change> <S2-refinanced>"
#
# Stage 1 = first column of the Toplam row.
# Stage 2 = sum of the remaining columns (Yakın İzlemedeki sub-types).
# Stage 3 = comes from the npl_brsa_gross table we already extract.
#
# This unlocks per-bank Stage 1 / Stage 2 LOAN amounts (not just provisions)
# for the entire system — every Turkish bank discloses this table.
# ---------------------------------------------------------------------------
# Full BRSA-mandated section title — present in every Turkish bank's audit
# report under either section number "7.2" or thereabouts. Both phrases must
# appear in the heading; their proximity is what distinguishes a real
# Standart-Nitelikli-vs-Yakın-İzlemedeki section from incidental mentions.
#
# Variants encountered:
#   ZIRAAT/AKBNK/VAKBN — "Standart Nitelikli ve Yakın İzlemedeki"
#   HALKB              — "Standard Loans Loans Under Follow-up"
#   YKBNK              — "Standard loans Loans under close monitoring"
#   ISCTR              — "Standard loans and loans under close monitoring"
#   GARAN              — uses inline "(Stage 1)" / "(Stage 2)" markers; handled
#                        by a separate row-based fallback below.
# Detect the section by presence of BOTH the Stage 1 column-header phrase AND
# the Stage 2 column-header phrase anywhere on the page (order-independent —
# some PDFs render the Stage 2 sub-headers physically above the Stage 1 label
# because they wrap to multiple lines).
_STAGE12_S1_PHRASE = re.compile(
    r"(?:Standart\s+Nitelikli|Standard\s+[Ll]oans?|Performing\s+Loans?)",
    re.IGNORECASE,
)
_STAGE12_S2_PHRASE = re.compile(
    r"(?:Yakın\s+İzlemedeki|Loans?\s+Under\s+(?:Close\s+Monitor|Follow)|Close\s+Monitor)",
    re.IGNORECASE,
)
# GARAN-style: Stage 1 + Stage 2 disclosed as ROW labels with TL/FC columns.
_STAGE12_GARAN_S1_ROW = re.compile(
    r"^\s*Performing\s+Loans?\s*\(\s*Stage\s*1\s*\)\s+(.*)$",
    re.IGNORECASE,
)
_STAGE12_GARAN_S2_ROW = re.compile(
    r"^\s*Loans?\s+Under\s+(?:Follow[\s-]?up|Close\s+Monitor\w*)\s*\(\s*Stage\s*2\s*\)\s+(.*)$",
    re.IGNORECASE,
)
# The Toplam / Total row.
_STAGE12_TOTAL_ROW = re.compile(
    r"^\s*(?:Toplam|Total)\s",
    re.IGNORECASE,
)


def _extract_loans_by_stage_from_page(page_num: int, page_text: str) -> list[StageRow]:
    """Capture Stage 1 / Stage 2 loan AMOUNTS from BRSA section 7.2.

    Algorithm:
      1. Find each occurrence of the section title
         "Standart Nitelikli ve Yakın İzlemedeki ... İlişkin Bilgiler".
      2. Within the next ~40 lines after the title, locate the Toplam / Total
         row of the data table.
      3. Track Cari Dönem / Önceki Dönem context within that block.
    """
    if not page_text:
        return []
    # The page must reference BOTH Stage 1 and Stage 2 column-header phrases.
    s1_match = _STAGE12_S1_PHRASE.search(page_text)
    s2_match = _STAGE12_S2_PHRASE.search(page_text)
    has_section_header = s1_match is not None and s2_match is not None
    # GARAN-style fallback markers (inline "(Stage 1)" / "(Stage 2)" rows).
    has_garan_markers = (
        re.search(r"Performing\s+Loans?\s*\(\s*Stage\s*1\s*\)", page_text, re.IGNORECASE) is not None
        and re.search(r"Loans?\s+Under\s+(?:Follow|Close\s+Monitor)\w*\s*\(\s*Stage\s*2\s*\)",
                       page_text, re.IGNORECASE) is not None
    )
    if not has_section_header and not has_garan_markers:
        return []

    lines = page_text.split("\n")
    # Build a mapping of char-offset → line index for fast lookups.
    line_offsets: list[int] = []
    offset = 0
    for ln in lines:
        line_offsets.append(offset)
        offset += len(ln) + 1  # +1 for the newline

    def _char_to_line(pos: int) -> int:
        # Binary-search-ish: linear is fine for ~200 lines per page.
        for li, lo in enumerate(line_offsets):
            if lo > pos:
                return li - 1
        return len(lines) - 1

    out: list[StageRow] = []
    seen: set[tuple[int, str]] = set()  # (page, period_type) dedup within this page
    # Start the scan from the earlier of the two phrase anchors (the
    # column-headers usually appear within ~5 lines of each other).
    scan_starts: list[int] = []
    if has_section_header:
        first_pos = min(s1_match.start(), s2_match.start())
        scan_starts.append(_char_to_line(first_pos))
    for hdr_line in scan_starts:
        # Scan up to 40 lines after the section heading for one or two Toplam
        # rows (current + prior period each emit one).
        current_period: str = "current"
        for li in range(hdr_line + 1, min(len(lines), hdr_line + 45)):
            stripped = lines[li].strip()
            pt = _detect_period_type(stripped)
            if pt is not None:
                current_period = pt
            if not _STAGE12_TOTAL_ROW.match(stripped):
                continue
            nums = re.findall(_NUM_PAT_STR, stripped)
            # A real BRSA 7.2 Toplam row carries 2-5 numeric columns
            # (Stage 1 + 1-4 Yakın İzlemedeki sub-types). Reject narrower
            # tables (employee-loan disclosures have 4 numbers split across
            # current/prior).
            if not (2 <= len(nums) <= 5):
                continue
            vals = [parse_num(n) for n in nums]
            # Sanity gate: Stage 1 column must be:
            #  * non-null
            #  * in magnitude range (>1 bn TL = >10^6 thousand TL)
            #  * larger than the sum of the Stage 2 sub-columns — Stage 1 is
            #    always the dominant portfolio. ECL provision Total rows
            #    violate this (Stage 2 ECL usually > Stage 1 ECL) and would
            #    otherwise pollute the result, e.g. YKBNK p96's ECL "Total
            #    7.48B 20.55B".
            if not (vals[0] is not None and vals[0] >= 1_000_000):
                continue
            stage1 = vals[0]
            stage2 = sum(v for v in vals[1:] if v is not None) or None
            if stage2 is not None and stage1 < stage2:
                continue
            key = (page_num, current_period)
            if key in seen:
                continue
            seen.add(key)
            out.append(StageRow(
                section="loans_by_stage",
                period_type=current_period,
                page=page_num,
                stage1=stage1, stage2=stage2, stage3=None,
                total=(stage1 + stage2) if (stage1 is not None and stage2 is not None) else stage1,
                heading="Standart Nitelikli / Yakın İzlemedeki",
            ))

    # GARAN-style fallback: explicit "(Stage 1)" / "(Stage 2)" row labels with
    # TL/FC × Corporate/Consumer/Total columns. Last 2 numbers per row are
    # the TL Total + FC Total — summing them gives the all-portfolios total.
    s1_match = None
    s2_match = None
    s1_line_idx = s2_line_idx = -1
    for li, ln in enumerate(lines):
        if s1_match is None:
            m = _STAGE12_GARAN_S1_ROW.match(ln)
            if m:
                s1_match = m.group(1)
                s1_line_idx = li
        if s2_match is None:
            m = _STAGE12_GARAN_S2_ROW.match(ln)
            if m:
                s2_match = m.group(1)
                s2_line_idx = li
        if s1_match and s2_match:
            break
    if s1_match and s2_match:
        # GARAN p124 (current period). Check if there's a "prior period"
        # marker between Stage 1 and Stage 2 — if so this is a single-period
        # block (otherwise both rows belong to the same period).
        s1_nums = re.findall(_NUM_PAT_STR, s1_match)
        s2_nums = re.findall(_NUM_PAT_STR, s2_match)
        # Need at least 2 numbers per row (TL Total + FC Total).
        if len(s1_nums) >= 2 and len(s2_nums) >= 2:
            s1_vals = [parse_num(n) for n in s1_nums]
            s2_vals = [parse_num(n) for n in s2_nums]
            # Last 2 cols = TL Total + FC Total → sum.
            stage1 = sum(v for v in s1_vals[-2:] if v is not None) or None
            stage2 = sum(v for v in s2_vals[-2:] if v is not None) or None
            # Determine period from context within ~10 lines preceding S1 row.
            ctx = "\n".join(lines[max(0, s1_line_idx - 10):s1_line_idx])
            period_type = "prior" if _PRIOR_PAT.search(ctx) else "current"
            key = (page_num, period_type)
            if key not in seen and stage1 and stage1 >= 1_000_000:
                seen.add(key)
                out.append(StageRow(
                    section="loans_by_stage",
                    period_type=period_type,
                    page=page_num,
                    stage1=stage1, stage2=stage2, stage3=None,
                    total=(stage1 + stage2) if (stage1 is not None and stage2 is not None) else stage1,
                    heading="Performing Loans (Stage 1) / Loans under Follow-up (Stage 2)",
                ))
    return out


# ---------------------------------------------------------------------------
# Stage 1 + Stage 2 ECL sub-table — comes right below the loans-by-stage
# table in BRSA section 7.2. Universally disclosed by all Turkish banks.
#
# Turkish layout (ZIRAAT/AKBNK/VAKBN):
#   Birinci ve İkinci Aşama       Standart  Yakın       Standart  Yakın
#   Beklenen Zarar Karşılıkları   Nitelikli İzlemedeki  Nitelikli İzlemedeki
#   12 Aylık Beklenen Zarar       <S1_curr>  -          <S1_prior> -
#   Kredi Riskinde Önemli Artış   -          <S2_curr>  -          <S2_prior>
#
# English layout (HALKB/YKBNK/ISCTR):
#   12 Months Expected Loss Provision    <S1_curr> -  <S1_prior> -
#   Significant Increase in Credit Risk  -  <S2_curr>  -  <S2_prior>
#
# We extract:
#   loans_ecl_brsa.stage1 = current-period Stage 1 ECL provision balance
#   loans_ecl_brsa.stage2 = current-period Stage 2 ECL provision balance
#   (Stage 3 ECL comes from npl_brsa_provision.total; together they give
#    full Stage 1/2/3 coverage ratios for every bank/period.)
# ---------------------------------------------------------------------------

_ECL_S1_ROW_PAT = re.compile(
    r"(?:12\s*Aylık\s*Beklenen\s*(?:Zarar|Kredi\s*Zarar(?:ı|ları))"
    r"\s*(?:Karşılığı?)?"
    r"|12\s*Months?\s*Expected\s*(?:Credit\s*)?Loss\s*(?:Provision)?)",
    re.IGNORECASE,
)
_ECL_S2_ROW_PAT = re.compile(
    r"(?:Kredi\s+Riskinde\s+Önemli\s+Artış"
    r"|Significant\s+Increase\s+in\s+Credit\s+Risk)",
    re.IGNORECASE,
)


def _extract_stage12_ecl_from_page(page_num: int, page_text: str) -> list[StageRow]:
    """Capture Stage 1 + Stage 2 ECL provisions from BRSA section 7.2 sub-table.

    Strategy:
      - Find the "12 Aylık Beklenen Zarar" / "12 Months Expected Loss" row.
        First non-zero number on this row = current-period Stage 1 ECL.
      - Find the "Kredi Riskinde Önemli Artış" / "Significant Increase" row.
        First non-zero number = current-period Stage 2 ECL.
      - Guard against false matches in the P&L expense decomposition table
        (which uses similar wording but has "(Stage 1)" / "(Stage 2)"
        inline markers — those are caught by `loans_ecl_expense`).
    """
    if not page_text:
        return []

    # Both rows must be present on the same page (= same sub-table block).
    s1_row_match = _ECL_S1_ROW_PAT.search(page_text)
    s2_row_match = _ECL_S2_ROW_PAT.search(page_text)
    if not (s1_row_match and s2_row_match):
        return []

    # Skip if this is the P&L expense table (has inline "(Stage 1)" markers).
    if re.search(r"\(\s*Stage\s*1\s*\)", page_text, re.IGNORECASE):
        return []

    lines = page_text.split("\n")
    s1_line: str | None = None
    s2_line: str | None = None
    for ln in lines:
        if s1_line is None and _ECL_S1_ROW_PAT.search(ln):
            s1_line = ln
        if s2_line is None and _ECL_S2_ROW_PAT.search(ln):
            s2_line = ln
        if s1_line and s2_line:
            break
    if not (s1_line and s2_line):
        return []

    def _parse_first_nonzero(line: str, label_pat: re.Pattern) -> float | None:
        # Numbers must come AFTER the row label, otherwise the "12" prefix
        # of "12 Aylık" / "12 Months" gets parsed as the first numeric column.
        m = label_pat.search(line)
        tail = line[m.end():] if m else line
        for tok in re.findall(_NUM_PAT_STR, tail):
            v = parse_num(tok)
            if v is not None and v != 0:
                return v
        return None

    s1_ecl = _parse_first_nonzero(s1_line, _ECL_S1_ROW_PAT)
    s2_ecl = _parse_first_nonzero(s2_line, _ECL_S2_ROW_PAT)

    if s1_ecl is None and s2_ecl is None:
        return []

    return [StageRow(
        section="loans_ecl_brsa",
        period_type="current",
        page=page_num,
        stage1=s1_ecl,
        stage2=s2_ecl,
        stage3=None,
        total=(s1_ecl or 0) + (s2_ecl or 0) if (s1_ecl or s2_ecl) else None,
        heading="12 Aylık / Kredi Riskinde Önemli Artış",
    )]


def extract_from_pdf(pdf: pdfplumber.PDF, pdf_path: str = "") -> CreditQualityReport:
    """Scan an already-open pdfplumber.PDF for IFRS 9 stage tables.

    Prefer this over `extract` when the caller already has the PDF open —
    pdfplumber's open() costs ~5–15s on a typical audit report, and the main
    `extractor.extract` pipeline also opens the same PDF. Sharing one handle
    halves per-PDF cost in the sync_audit_reports worker.
    """
    rep = CreditQualityReport(pdf_path=pdf_path)
    for i, page in enumerate(pdf.pages, 1):
        text = page.extract_text() or ""
        # Stock tables (movement-table end-row) — primary signal.
        if (_STAGE_HEADER_EN.search(text) or _STAGE_HEADER_TR.search(text)
                or _STAGE_HEADER_TR_3COL.search(text)):
            rep.rows.extend(_extract_from_page(i, text))
        # P&L expense decomposition — fallback signal for banks that omit
        # the stock table. Cheap to check — just look for the row-pattern.
        rep.rows.extend(_extract_pl_expense_from_page(i, text))
        # BRSA NPL classification (III/IV/V groups) — the actual NPL loan
        # balances broken into severity groups. Universal across BRSA reports.
        rep.rows.extend(_extract_npl_brsa_from_page(i, text))
        # BRSA section 7.2 "Standart Nitelikli ve Yakın İzlemedeki" loan
        # amounts. Gives Stage 1 + Stage 2 portfolio balances for every bank
        # (combined with npl_brsa_gross's Stage 3 = full stage breakdown).
        rep.rows.extend(_extract_loans_by_stage_from_page(i, text))
        # Stage 1 + Stage 2 ECL provisions from the same section 7.2.
        # Completes per-stage coverage ratio coverage for every bank.
        rep.rows.extend(_extract_stage12_ecl_from_page(i, text))
    # Keep the first row per (section, period_type); later same-key matches are
    # usually narrower sub-tables (e.g. consumer-only) we already classified.
    seen: set[tuple[str, str]] = set()
    deduped: list[StageRow] = []
    for r in rep.rows:
        key = (r.section, r.period_type)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    rep.rows = deduped
    return rep


def extract(pdf_path: str | Path) -> CreditQualityReport:
    """Open the PDF and run the stage-table extractor. Convenience wrapper
    around `extract_from_pdf` for callers that don't already have a PDF handle.
    """
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
    rep: CreditQualityReport,
) -> int:
    """Idempotently store one bank's credit-quality rows. Returns row count."""
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM bank_audit_credit_quality "
        "WHERE bank_ticker=? AND period=? AND kind=?",
        (bank_ticker, period, kind),
    )
    rows = [(
        bank_ticker, period, kind, r.section, r.period_type,
        r.page, r.stage1, r.stage2, r.stage3, r.total, r.heading,
    ) for r in rep.rows]
    if rows:
        cur.executemany(
            "INSERT INTO bank_audit_credit_quality "
            "(bank_ticker, period, kind, section, period_type, source_page, "
            " stage1_amount, stage2_amount, stage3_amount, total_amount, heading_snippet) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
    conn.commit()
    return len(rows)


def summarize(rep: CreditQualityReport) -> str:
    if not rep.rows:
        return f"{Path(rep.pdf_path).name}\n  (no stage tables found)"
    lines = [Path(rep.pdf_path).name]
    for r in rep.rows:
        s1 = f"{r.stage1:,.0f}" if r.stage1 is not None else "-"
        s2 = f"{r.stage2:,.0f}" if r.stage2 is not None else "-"
        s3 = f"{r.stage3:,.0f}" if r.stage3 is not None else "-"
        tt = f"{r.total:,.0f}" if r.total is not None else "-"
        lines.append(
            f"  p.{r.page:>3}  {r.section:<20} {r.period_type:<7}  "
            f"S1={s1:>20}  S2={s2:>18}  S3={s3:>18}  T={tt:>20}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    path = sys.argv[1] if len(sys.argv) > 1 else "data/_tmp_akbnk_2025q4.pdf"
    rep = extract(path)
    print(summarize(rep))
