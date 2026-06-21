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

import json
import logging
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF — ~85× faster than pdfplumber for text; credit_quality is fitz-only

from .extractor import NUM_PAT as _NUM_PAT_STR
from .extractor import parse_num

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-bank template registry — see data/banks/audit_templates.json.
#
# Each bank entry pins the EXACT row labels that bank uses for the main NPL
# movement table (gross / provision / net) plus the loans-by-stage Toplam
# label and the Stage 1+2 ECL row labels. When a bank has a template entry,
# we anchor on these exact labels instead of running the looser regex
# fallback — far fewer false matches on PDFs with multiple III/IV/V tables.
#
# Banks NOT in the registry fall back to the regex-driven path. A WARNING is
# logged the first time we extract such a bank so the gap is visible.
# ---------------------------------------------------------------------------
_TEMPLATES_PATH = Path(__file__).resolve().parents[2] / "data" / "banks" / "audit_templates.json"


def _load_templates() -> dict[str, dict]:
    """Read the per-bank template registry once. Returns {} if missing."""
    if not _TEMPLATES_PATH.exists():
        _log.warning("audit_templates.json not found at %s — falling back to regex extraction for every bank.",
                     _TEMPLATES_PATH)
        return {}
    with open(_TEMPLATES_PATH, encoding="utf-8") as f:
        data = json.load(f)
    # Strip _doc / _lang / _note keys etc that are just human-readable.
    return {k: v for k, v in data.items() if not k.startswith("_")}


_TEMPLATES = _load_templates()


def _norm(s: str) -> str:
    """Lowercase + collapse internal whitespace + strip leading/trailing.

    Used for both row-label lookup and line matching so we get tolerant
    prefix matches without writing regex per bank.
    """
    return re.sub(r"\s+", " ", s.lower()).strip()


def _classify_alias(alias: str) -> str:
    """Route an alias to the right row-type bucket using keyword content.

    Aliases in the registry are stored as a flat list per bank (mixing case
    variations of gross/provision/net). We split them at load time by which
    semantic keyword they contain. This keeps the JSON terse without
    sacrificing correctness — the keywords are unambiguous in practice.
    """
    low = _norm(alias)
    if any(kw in low for kw in (
        "karşılık", "provision", "beklenen zarar karşılığı",
        "özel karşılık",
    )):
        return "provision"
    if "net" in low or "bilanço" in low or "bilanco" in low:
        return "net"
    # Everything else (Bakiye / Balance / Brüt / Gross / End-of-period / etc.)
    return "gross"


def _bank_label_sets(template: dict) -> tuple[set[str], set[str], set[str]]:
    """Return ({gross_labels}, {provision_labels}, {net_labels}) for one bank.

    All labels are stored normalised so callers do `_norm(line)` once and
    compare with `startswith`.
    """
    npl = template.get("npl_movement", {})
    gross = {_norm(npl["gross_label"])} if "gross_label" in npl else set()
    prov = {_norm(npl["provision_label"])} if "provision_label" in npl else set()
    net = {_norm(npl["net_label"])} if "net_label" in npl else set()
    for alias in npl.get("aliases", []):
        cls = _classify_alias(alias)
        if cls == "provision":
            prov.add(_norm(alias))
        elif cls == "net":
            net.add(_norm(alias))
        else:
            gross.add(_norm(alias))
    return gross, prov, net


def _line_matches(line: str, label_set: set[str]) -> bool:
    """True when the stripped, normalised line starts with any of the labels."""
    nl = _norm(line)
    return any(nl.startswith(lbl) for lbl in label_set)


_logged_missing: set[str] = set()


def _template_for(bank_ticker: str) -> dict | None:
    """Return the bank's template, or None if not registered. Warns once."""
    if not bank_ticker:
        return None
    tmpl = _TEMPLATES.get(bank_ticker.upper())
    if tmpl is None:
        if bank_ticker.upper() not in _logged_missing:
            _logged_missing.add(bank_ticker.upper())
            _log.warning(
                "No template entry for %s in data/banks/audit_templates.json — "
                "falling back to regex extraction. Add an entry with the bank's "
                "gross/provision/net row labels for accurate IFRS 9 staging.",
                bank_ticker,
            )
    return tmpl

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


def _merge_split_digits(line: str) -> str:
    """Reattach a leading digit that pdfplumber separated from its number.

    pdfplumber sometimes splits the leading 1-2 digits off a large number with
    a stray space — e.g. TFKB renders '334,098' as '3 34,098' and '1,553,507'
    as '1 ,553,507'. Without this normalization the tokenizer sees two numeric
    tokens for one column, throwing off column counts and value magnitudes.

    The leading digit MUST NOT be preceded by another digit — otherwise we'd
    incorrectly merge the trailing digit of a date or label into the next
    number, e.g. '...2024 6.124.453 ...' would become '...20246.124.453...'
    which the tokenizer reads as 46,124,453 (AKBNK p64 prior period).

    It must also NOT fuse two SEPARATE column values. A TRUE split keeps the
    combined leading group ≤3 digits ('3 34,098' -> '334,098'); fusing two real
    values overflows it ('13 11,390' -> '1311,390', which mis-parses as 131 /
    1,390 — the ALNTF NPL net row: Group III 13 + Group IV 11,390). So only merge
    when standalone-digits + the group's leading segment stay ≤3 digits.
    """
    # '1 95,170,209' -> '195,170,209'  (standalone digit, space, digit-group), but
    # only when the merged leading group stays ≤3 digits (else it's two values).
    def _join(m: "re.Match[str]") -> str:
        lead, seg = m.group(1), m.group(2)
        return lead + seg if len(lead) + len(seg) <= 3 else m.group(0)

    line = re.sub(r"(?<!\d)(\d{1,2})\s+(\d{1,3})(?=[.,]\d{3})", _join, line)
    # '1 ,553,507'   -> '1,553,507'    (standalone digit, leading-separator)
    line = re.sub(r"(?<!\d)(\d{1,2})\s+([.,]\d{3})", r"\1\2", line)
    return line


# -- Section classifier ------------------------------------------------------
#
# Given a chunk of text that PRECEDES a Stage-header on the same page, pick
# a section label. Order matters — more-specific patterns first.
# ---------------------------------------------------------------------------
# COLUMN SEMANTICS — read before touching stage1/2/3_amount.
#
# bank_audit_credit_quality reuses three POSITIONAL columns (stage1_amount,
# stage2_amount, stage3_amount) across every section, but their meaning is
# SECTION-DEPENDENT:
#
#   • Most sections (loans_ecl, loans_by_stage, loans_amounts, loans_ecl_brsa,
#     cash_ecl, amortised_cost_ecl, non_cash_ecl, …) → IFRS-9 STAGE 1 / 2 / 3.
#
#   • The npl_brsa_* sections → BRSA non-performing GROUPS III / IV / V
#     (substandard / doubtful / loss). These are NOT IFRS stages — all three
#     are sub-buckets of IFRS Stage 3. The Stage-3 figure is the npl_brsa
#     TOTAL (= III+IV+V), never stage1_amount.
#
# So NEVER read npl_brsa_*.stage1_amount as "Stage 1". The derived
# bank_audit_stages table maps npl_brsa_gross.total_amount → Stage 3 (see
# scripts/build_bank_audit_stages.py); compute_bank_metrics labels the split
# npl_group3/4/5; a guard test in tests/test_audit_validator.py locks this.
NPL_GROUP_SECTIONS: frozenset[str] = frozenset(
    {"npl_brsa_gross", "npl_brsa_net", "npl_brsa_provision"})


def stage_columns_are_brsa_groups(section: str) -> bool:
    """True iff this section's stage1/2/3_amount hold BRSA NPL groups III/IV/V
    (sub-buckets of IFRS Stage 3) rather than IFRS-9 stages."""
    return section in NPL_GROUP_SECTIONS


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

# Header pattern — tolerates all wording variants observed across banks:
#   "III. Group / IV. Group / V. Group"  (HALKB, YKBNK, QNBFB)
#   "Group III / Group IV / Group V"     (GARAN, ALBRK)
#   "GroupIII GroupIV GroupV"            (ISCTR 2024 — pdfplumber drops spaces)
#   "III. Grup / IV. Grup / V. Grup"     (Turkish — VAKBN, AKBNK, TEB, ...)
#   "III.Group / IV.Group / V.Group"     (TSKB — no space)
#   "III. Group: / IV. Group: / V. Group:" (SKBNK — colons)
# The space between "Group" and the Roman numeral is \s* (not \s+) because
# pdfplumber sometimes renders the header with no space ("GroupIII").
_NPL_HEADER_PAT = re.compile(
    r"(?:Group\s*III|III\.?\s*(?:Group|Grup):?)"
    r"\s*(?:Group\s*IV|IV\.?\s*(?:Group|Grup):?)"
    r"\s*(?:Group\s*V|V\.?\s*(?:Group|Grup):?)",
    re.IGNORECASE,
)

# The "Provision (-)" / "Karşılık (-)" anchor row.
# Must be ANCHORED to the start of the (stripped) line — otherwise we match
# the row label "Loans to Individuals and Corporates (Net)" because some banks
# use "Provision" as part of column headers too.
# Variants in the wild:
#   "Provision (-)"           — most common (GARAN, AKBNK)
#   "Provisions (-)"          — plural (ISCTR, YKBNK)
#   "Specific Provision (-)"  — BURGAN
#   "Provisions"              — no `(-)` suffix, values wrapped in accounting
#                                parens instead (EXIM)
#   "Karşılık (-)" / "Özel Karşılık (-)" — Turkish
#   "Beklenen Zarar Karşılığı (3. Aşama) (-)" — ZIRAATK
#   "Beklenen Zarar Karşılığı (Üçüncü Aşama) (-)" — variant phrasing
_NPL_PROVISION_ROW = re.compile(
    r"^\s*(?:"
    r"Provisions?\s*\(\s*-\s*\)"
    r"|Specific\s+Provisions?\s*\(\s*-\s*\)"
    r"|Provisions?\s+(?=\(\s*\d)"                # EXIM: 'Provisions (26.483) ...'
    # Turkish: '(Özel )?Karşılık( Tutarı)? (-)'. The 'Tutarı' (= 'amount')
    # variant is the most common Turkish provision-row label (TFKB uses
    # 'Özel Karşılık Tutarı (-)'); without it the regex fallback misses
    # every Turkish bank whose template path also failed.
    r"|(?:Özel\s+)?Karşılık(?:\s+Tutarı)?\s*\(\s*-\s*\)"
    r"|Beklenen\s+Zarar\s+Karşılığı"
    r"\s*\(\s*(?:3\.?|Üçüncü)\s*Aşama\s*\)\s*\(\s*-\s*\)"
    r")",
    re.IGNORECASE,
)
# III/IV/V header pattern (line-anchored variant used by the block walker).
# Group↔numeral gap is \s* (pdfplumber may drop it); the gaps BETWEEN the
# three group tokens stay \s+ so we don't match a single run-together word.
_NPL_HEADER_LINE = re.compile(
    r"^\s*(?:Group\s*III|III\.?\s*(?:Group|Grup):?)"
    r"\s+(?:Group\s*IV|IV\.?\s*(?:Group|Grup):?)"
    r"\s+(?:Group\s*V|V\.?\s*(?:Group|Grup):?)",
    re.IGNORECASE,
)
# A row qualifies as "data" if it has at least 3 numeric tokens with thousands
# separators (filters out short administrative rows like "Sold (-)").
_NPL_DATA_ROW_FILTER = re.compile(r"\d{1,3}[.,]\d{3}")

# FC-only NPL sub-tables (e.g. ALBRK h.3, AKBNK iii) report only the FC-
# denominated subset and are MUCH smaller than the total NPL classification.
# When this sub-section comes before the total on the same page, the
# Provision-anchored extractor would otherwise emit it as 'npl_brsa_gross'
# and the later (correct) total gets dropped by the (section, period_type)
# dedup. Detect the FC-only banner and skip the block.
_NPL_FC_ONLY_HEADING = re.compile(
    r"(?:in\s+foreign\s+currenc(?:y|ies)|"
    r"foreign[-\s]?currency\s+(?:loans?|receivables?|non[-\s]?performing)|"
    r"yabancı\s+para\s+olarak\s+kullandırılan|"
    r"yabancı\s+paraya\s+endeksli|"
    r"yp\s+olarak\s+kullandırılan)",
    re.IGNORECASE,
)


def _is_fc_only_block(lines: list[str], header_idxs: list[int], anchor_idx: int) -> bool:
    """True when the III/IV/V table block containing `anchor_idx` is the FC-only
    sub-table (heading 'in foreign currencies' / 'yabancı para olarak
    kullandırılan').

    The block starts at the nearest III/IV/V header above the anchor; the
    section heading typically sits a few lines above that header, so we scan
    from `header − 6` down to the anchor row. Shared by BOTH the regex and the
    template NPL extractors so neither emits the small FC-only subset (5-20% of
    total NPL) as the total Stage-3 balance — e.g. DENIZ/FIBA 2026Q1 where the
    FC-only table reports only a few thousand TL against a ~5-6% real NPL.
    """
    block_start = 0
    for hi in header_idxs:
        if hi < anchor_idx:
            block_start = hi
        else:
            break
    for j in range(max(0, block_start - 6), anchor_idx):
        if _NPL_FC_ONLY_HEADING.search(lines[j]):
            return True
    return False


def _extract_npl_brsa_via_template(
    page_num: int, page_text: str, template: dict,
) -> list[StageRow]:
    """Template-driven NPL/III-IV-V extractor.

    Walks the page line-by-line, anchoring on this bank's known gross row
    label. When it finds a gross row, it walks forward for the provision row
    and the net row using this bank's labels. No regex guessing.

    Returns 0 or N rows (one gross/provision/net triple per occurrence;
    typically 2 — current and prior period from the same page).
    """
    if not page_text or not _NPL_HEADER_PAT.search(page_text):
        return []
    gross_labels, prov_labels, net_labels = _bank_label_sets(template)
    if not (gross_labels and prov_labels):
        return []  # bank not configured for npl_brsa

    lines = [_merge_split_digits(ln) for ln in page_text.split("\n")]
    out: list[StageRow] = []
    header_idxs = [i for i, ln in enumerate(lines) if _NPL_HEADER_LINE.match(ln.strip())]
    if not header_idxs:
        return []

    def _period_for(i: int) -> str:
        # Scan back from i to find the most recent period marker within the
        # same III/IV/V band.
        block_start = max((h for h in header_idxs if h < i), default=0)
        for j in range(i, block_start - 1, -1):
            pt = _detect_period_type(lines[j].strip())
            if pt is not None:
                return pt
        return "current"

    # Walk every gross-label hit. For each, peek forward (bounded by next
    # III/IV/V header) for the provision line, and after that the net line.
    seen_keys: set[tuple[str, int]] = set()
    for i, ln in enumerate(lines):
        if not _line_matches(ln, gross_labels):
            continue
        # The gross line should carry 3 numeric tokens (Group III, IV, V).
        gnums = _NUM.findall(ln)
        if len(gnums) < 3:
            continue
        # Skip the FC-only sub-table: its gross row carries the same label
        # ("Dönem Sonu Bakiyesi") but only the foreign-currency subset, so it
        # would shadow the real total via the (section, period_type) dedup —
        # exactly DENIZ/FIBA 2026Q1, where the template otherwise emitted a
        # ~36k / ~24k Stage-3 against a real ~60bn / ~4.4bn balance. When this
        # leaves the template with no gross row, extract_from_pdf falls back to
        # the regex path, which scopes the total table correctly.
        if _is_fc_only_block(lines, header_idxs, i):
            continue
        # Bound the forward walk by the next III/IV/V header (or EOF).
        next_hdr = min((h for h in header_idxs if h > i), default=len(lines))
        prov_idx: int | None = None
        net_idx: int | None = None
        for j in range(i + 1, next_hdr):
            cand = lines[j]
            if prov_idx is None and _line_matches(cand, prov_labels):
                if len(_NUM.findall(cand)) >= 3:
                    prov_idx = j
                    continue
            if prov_idx is not None and net_idx is None and _line_matches(cand, net_labels):
                if len(_NUM.findall(cand)) >= 3:
                    net_idx = j
                    break
        if prov_idx is None:
            continue
        pt = _period_for(prov_idx)
        key = (pt, header_idxs and max((h for h in header_idxs if h <= i), default=-1) or 0)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        gross = [parse_num(n) for n in gnums[-3:]]
        pnums = _NUM.findall(lines[prov_idx])
        prov = [abs(parse_num(n)) if parse_num(n) is not None else None
                for n in pnums[-3:]]

        def _sum_or_none(v: list[float | None]) -> float | None:
            clean = [x for x in v if x is not None]
            return sum(clean) if clean else None

        out.append(StageRow(
            section="npl_brsa_gross", period_type=pt, page=page_num,
            stage1=gross[0], stage2=gross[1], stage3=gross[2],
            total=_sum_or_none(gross), heading="III/IV/V groups (template)",
        ))
        out.append(StageRow(
            section="npl_brsa_provision", period_type=pt, page=page_num,
            stage1=prov[0], stage2=prov[1], stage3=prov[2],
            total=_sum_or_none(prov), heading="",
        ))
        if net_idx is not None:
            nnums = _NUM.findall(lines[net_idx])
            net = [parse_num(n) for n in nnums[-3:]]
            out.append(StageRow(
                section="npl_brsa_net", period_type=pt, page=page_num,
                stage1=net[0], stage2=net[1], stage3=net[2],
                total=_sum_or_none(net), heading="",
            ))
    return out


def _extract_npl_brsa_from_page(page_num: int, page_text: str) -> list[StageRow]:
    """Find the BRSA NPL classification table on this page and emit gross /
    provision / net rows. Each row carries Group III/IV/V in stage1/2/3 and
    III+IV+V sum in total.

    Returns 0 or up to 6 rows (3 row-kinds × 2 period-types).
    """
    if not page_text or not _NPL_HEADER_PAT.search(page_text):
        return []
    # Pre-normalize every line to repair pdfplumber's split-digit numbers.
    lines = [_merge_split_digits(ln) for ln in page_text.split("\n")]
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

    # Index every "Provisions" anchor line. We need its position to bound the
    # gross/net walks — banks like ISCTR put multiple III/IV/V tables on one
    # page, each with its own gross/provision/net trio. Without bounds the
    # walk-forward from prior-period provision crosses into the next table.
    provision_idxs = [
        i for i, ln in enumerate(lines)
        if _NPL_PROVISION_ROW.match(ln.strip())
    ]

    for i, ln in enumerate(lines):
        stripped = ln.strip()
        # Anchor: provision row.
        if not _NPL_PROVISION_ROW.match(stripped):
            continue
        # Reject FC-only sub-tables — they're 5-20% of total NPL and would
        # silently displace the real total via dedup. (Shared helper, also
        # used by the template path.)
        if _is_fc_only_block(lines, header_idxs, i):
            continue
        current_period = _period_for_provision(i)
        nums = _NUM.findall(stripped)
        if len(nums) < 3:
            continue
        # Find the bounds of this provision's block: from the prev provision
        # (exclusive) to the next provision (exclusive), additionally clipped
        # by III/IV/V header_idxs so we never cross a table boundary.
        prev_prov = max((p for p in provision_idxs if p < i), default=-1)
        next_prov = min((p for p in provision_idxs if p > i), default=len(lines))
        prev_header = max((h for h in header_idxs if h < i), default=-1)
        next_header = min((h for h in header_idxs if h > i), default=len(lines))
        block_lo = max(prev_prov, prev_header) + 1
        block_hi = min(next_prov, next_header)
        # The row label "Karşılık (-)" / "Provision (-)" already encodes that
        # values are deductions. Some banks (KLNMA / PASHA) ALSO write the
        # numbers in accounting parentheses, so parse_num returns negatives —
        # take abs to normalize to magnitude, matching the convention the
        # other banks use.
        prov = [abs(parse_num(n)) if parse_num(n) is not None else None
                for n in nums[-3:]]

        # Walk back up to 10 lines to find the gross row. Some banks (ISCTR)
        # interpose 4-5 customer-segment sub-rows (Corporate / Retail / Credit
        # Cards / Other) between the parent gross row and the Provisions row,
        # so we can't stop at the first eligible row — that's a sub-row, not
        # the real gross balance. Collect ALL candidates and pick the one
        # whose values sum to the LARGEST magnitude: the parent row equals
        # the sum of its sub-rows so it always has the largest values.
        gross_candidates: list[list[float | None]] = []
        for j in range(i - 1, block_lo - 1, -1):
            cand = lines[j].strip()
            if not _NPL_DATA_ROW_FILTER.search(cand):
                continue
            if re.search(r"\b(?:Net|Provisions?|Karşılık|Beklenen\s+Zarar)\b",
                         cand, re.IGNORECASE):
                break
            cnums = _NUM.findall(cand)
            if len(cnums) >= 3:
                gross_candidates.append([parse_num(n) for n in cnums[-3:]])

        def _abs_sum(v: list[float | None]) -> float:
            return sum(abs(x) for x in v if x is not None)

        # Pick the row with the largest magnitude — for banks like ISCTR that
        # interpose customer-segment sub-rows (Corporate / Retail / Credit
        # Cards / Other) between the parent gross row and the Provisions row,
        # the parent row sums to a larger value than any single sub-row.
        gross = max(gross_candidates, key=_abs_sum) if gross_candidates else None

        # Walk forward, bounded by the next provision/header, to find the net
        # row. Apply the same largest-magnitude pick over sub-rows.
        net_candidates: list[list[float | None]] = []
        for j in range(i + 1, block_hi):
            cand = lines[j].strip()
            if not _NPL_DATA_ROW_FILTER.search(cand):
                continue
            if not re.search(r"\bNet\b|Bilançodaki", cand, re.IGNORECASE):
                continue
            cnums = _NUM.findall(cand)
            if len(cnums) >= 3:
                net_candidates.append([parse_num(n) for n in cnums[-3:]])

        net = max(net_candidates, key=_abs_sum) if net_candidates else None

        def _sum_or_none(v: list[float | None]) -> float | None:
            clean = [x for x in v if x is not None]
            return sum(clean) if clean else None

        # Prefer the gross candidate satisfying the closing-balance identity
        # gross = provision + net. The period-end balance ("Dönem Sonu Bakiyesi")
        # is the ONLY row that foots it; a movement/inflow row ("Dönem İçinde
        # İntikal") sums larger and wins the magnitude pick above — the DENIZ
        # 2025Q4 mis-grab where the NPL *movement* table's inflow (63.4bn) beat the
        # 55bn closing balance. Override only when a candidate foots within 1%, so a
        # bank whose provision bundles general reserves keeps the historical pick.
        _net_tot = _sum_or_none(net) if net is not None else None
        _prov_tot = _sum_or_none(prov)
        if _net_tot is not None and _prov_tot is not None and gross_candidates:
            _target = _prov_tot + _net_tot
            _best = min(gross_candidates,
                        key=lambda c: abs(sum(x for x in c if x is not None) - _target))
            if abs(sum(x for x in _best if x is not None) - _target) <= max(1000.0, 0.01 * abs(_target)):
                gross = _best

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
    # "Standart Nitelikli" is the table's column header, but pdfplumber often
    # wraps column headers across visual lines so the words land on different
    # rows of extract_text() output (VAKIFK, TFKB). Fall back to the universal
    # BRSA section title "Birinci ve İkinci Grup Krediler" — every Turkish
    # bank uses it.
    # \s* (not \s+): some banks' PDFs tokenise words with NO inter-word spaces
    # ("StandardLoans", "LoansUnderCloseMonitoring") — İşbank EN, TSKB. The
    # zero-or-more keeps spaced reports matching while allowing the glued form.
    r"(?:Standart\s*Nitelikli"
    r"|Standard\s*[Ll]oans?"
    r"|Performing\s*Loans?"
    r"|Birinci\s*ve\s*İkinci\s*Grup)",
    re.IGNORECASE,
)
_STAGE12_S2_PHRASE = re.compile(
    r"(?:Yak[ıi]n\s*İzlemedeki|Loans?\s*Under\s*(?:Close\s*Monitor|Follow)|Close\s*Monitor)",
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
# Cheap, space-tolerant signals that a page carries the section-7.2 stage table —
# used only to decide whether the coordinate fallback is worth running. pdfplumber
# concatenates words without spaces on column-split layouts ("Standard Loans" →
# "StandardLoans"), so the real spaced anchors miss; these allow zero whitespace.
# BOTH a Stage-1 AND a Stage-2 column signal must be present (the prose mentions
# "standard loans" on many pages of an English report — requiring the Stage-2
# header too restricts the expensive coord pass to the actual table page). The
# strict S1/S2 anchors still gate the actual parse on the coord-rebuilt text.
_STAGE12_LOOSE_S1 = re.compile(
    r"(?:Standar[dt]\s*(?:Nitelik|Loan)|Performing\s*Loan|Birinci\s*ve\s*İkinci)",
    re.IGNORECASE,
)
_STAGE12_LOOSE_S2 = re.compile(
    r"(?:Yak[ıi]n\s*İzleme|İzlemedeki|Close\s*Monitor|Follow\s*-?up)",
    re.IGNORECASE,
)


def _fitz_clustered_lines(page, y_tol: float = 5.5) -> list[str]:
    """Rebuild visual rows from a fitz page by clustering words on y-coordinate.

    fitz's line-mode get_text() puts each CELL on its own line (label split from
    its numbers), which the row parsers reject. Grouping words within `y_tol` px
    rebuilds the real row ("Dönem Sonu Bakiyesi 16.063.819 19.187.412 …") so the
    existing pdfplumber-tuned parsers read it unchanged. This is the SAME 5.5px
    clustering the old pdfplumber `extract_words()` fallback used — credit_quality
    is now fitz-only (≈85× faster), and this clustering also subsumes the old
    column-split coordinate fallback, so no pdfplumber path remains.

    fitz `get_text("words")` yields (x0, y0, x1, y1, word, block, line, word_no).
    """
    words = page.get_text("words")
    if not words:
        return []
    words = sorted(words, key=lambda w: (w[1], w[0]))  # by y0, then x0
    lines: list[list] = []
    cur: list = []
    base: float | None = None
    for w in words:
        if base is None or w[1] - base <= y_tol:
            cur.append(w)
            if base is None:
                base = w[1]
        else:
            lines.append(cur)
            cur = [w]
            base = w[1]
    if cur:
        lines.append(cur)
    return [" ".join(t[4] for t in sorted(ln, key=lambda w: w[0])) for ln in lines]


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
    # The Stage-2 header ("Yakın İzlemedeki" / "Loans Under Close Monitoring") is
    # the table-specific anchor: the Stage-1 "Standart Nitelikli" header is wrapped
    # across visual lines with the other column headers interleaved (ANADOLU p53),
    # so requiring BOTH would skip the table. S2 alone is safe — a prose page that
    # merely says "close monitoring" can't produce a Toplam row that clears the
    # 3–5-number + Stage1≥1bn + Stage1>Stage2 sanity gates below.
    s1_match = _STAGE12_S1_PHRASE.search(page_text)
    s2_match = _STAGE12_S2_PHRASE.search(page_text)
    has_section_header = s2_match is not None
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
        first_pos = (s2_match.start() if s1_match is None
                     else min(s1_match.start(), s2_match.start()))
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
            nums = re.findall(_NUM_PAT_STR, _merge_split_digits(stripped))
            # A real BRSA 7.2 Toplam row carries 3-5 numeric columns: Stage 1
            # + 2-4 Yakın İzlemedeki sub-types (Yeniden Yapılandırma /
            # Sözleşme Koşullarında Değişiklik / Yeniden Finansman). 2-column
            # Toplam rows on the same page are unrelated tables: aging-
            # analysis Toplam (AKBNK p59 L47: "Toplam 16.622.792 15.101.565"),
            # currency split totals, etc. — reject those.
            if not (3 <= len(nums) <= 5):
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
    # Turkish: "Karşılığı" (genitive) is REQUIRED — without it the regex matches
    # narrative prose like "12 Aylık beklenen zarar değerleri" (sentence about
    # 12-month expected loss values) which appears in the IFRS 9 policy
    # description that almost every Turkish bank includes before the data table.
    r"(?:12\s*Aylık\s*Beklenen\s*(?:Zarar|Kredi\s*Zarar(?:ı|ları))\s*Karşılığı"
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
    # Collect ALL candidate lines (the policy section often repeats the row
    # label as a heading before the actual data table appears). Try each and
    # pick the first one that yields data-like numbers.
    s1_candidates = [ln for ln in lines if _ECL_S1_ROW_PAT.search(ln)]
    s2_candidates = [ln for ln in lines if _ECL_S2_ROW_PAT.search(ln)]
    if not (s1_candidates and s2_candidates):
        return []

    def _parse_first_nonzero(line: str, label_pat: re.Pattern) -> float | None:
        # Numbers must come AFTER the row label, otherwise the "12" prefix
        # of "12 Aylık" / "12 Months" gets parsed as the first numeric column.
        # Also reject bare 1-3 digit tokens without thousands separators —
        # those are footnote refs, stage markers like "(1. Aşama)", or stray
        # digits from prose. Real data-table values are thousand-TL and almost
        # always have a separator or magnitude >= 1000.
        m = label_pat.search(line)
        tail = line[m.end():] if m else line
        for tok in re.findall(_NUM_PAT_STR, tail):
            v = parse_num(tok)
            if v is None or v == 0:
                continue
            if re.search(r"\d[.,]\d{3}", tok) or abs(v) >= 1000:
                return v
        return None

    s1_ecl: float | None = None
    for ln in s1_candidates:
        v = _parse_first_nonzero(ln, _ECL_S1_ROW_PAT)
        if v is not None:
            s1_ecl = v
            break
    s2_ecl: float | None = None
    for ln in s2_candidates:
        v = _parse_first_nonzero(ln, _ECL_S2_ROW_PAT)
        if v is not None:
            s2_ecl = v
            break

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


_FILENAME_TICKER_PAT = re.compile(r"^([A-Z]+)_\d{4}Q\d_", re.IGNORECASE)


def _infer_ticker(pdf_path: str) -> str:
    """Pull the bank ticker out of a canonical filename like AKBNK_2025Q3_..."""
    name = Path(pdf_path).name
    m = _FILENAME_TICKER_PAT.match(name)
    return m.group(1).upper() if m else ""


def extract_from_pdf(
    pdf=None, pdf_path: str = "", bank_ticker: str = "",
) -> CreditQualityReport:
    """Scan a PDF for IFRS-9 stage tables — FITZ-ONLY (≈85× faster than pdfplumber).

    `pdf` is accepted for backward compatibility with the shared-handle call site
    in `extractor.extract`, but is IGNORED: credit_quality opens the PDF itself via
    fitz from `pdf_path` and reconstructs each row by clustering words on their
    y-coordinate (`_fitz_clustered_lines`), which the existing row parsers consume
    unchanged. fitz word-clustering subsumes the old column-split coordinate
    fallback, so no pdfplumber path remains.

    `bank_ticker` selects the per-bank template registry entry (see
    data/banks/audit_templates.json). If empty, we infer it from the
    filename `<TICKER>_<period>_<kind>.pdf`. If still unknown, npl_brsa
    extraction falls back to regex.
    """
    if not bank_ticker:
        bank_ticker = _infer_ticker(pdf_path)
    if not pdf_path:
        return CreditQualityReport(pdf_path=pdf_path)  # fitz needs a path
    template = _template_for(bank_ticker)
    rep = CreditQualityReport(pdf_path=pdf_path)
    # NPL rows are collected separately so we can fall back from the template
    # path to the regex path per-PDF (see below).
    npl_tmpl: list[StageRow] = []
    npl_regex: list[StageRow] = []
    doc = fitz.open(pdf_path)
    try:
        for i, page in enumerate(doc, 1):
            text = "\n".join(_fitz_clustered_lines(page))
            # Stock tables (movement-table end-row) — primary signal.
            if (_STAGE_HEADER_EN.search(text) or _STAGE_HEADER_TR.search(text)
                    or _STAGE_HEADER_TR_3COL.search(text)):
                rep.rows.extend(_extract_from_page(i, text))
            # P&L expense decomposition — fallback signal for banks that omit
            # the stock table. Cheap to check — just look for the row-pattern.
            rep.rows.extend(_extract_pl_expense_from_page(i, text))
            # BRSA NPL classification (III/IV/V groups). Run BOTH the template path
            # (precise — anchors on this bank's known labels) and the regex path
            # (language-agnostic — matches Karşılık/Provision and Dönem Sonu/Balance
            # generically). We prefer the template result, but fall back to the
            # regex result when the template yields nothing — e.g. a bank switching
            # report language between periods (BURGAN went EN→TR), a provision-row
            # label that drifted, or a gross row on a later page than the first
            # III/IV/V header. This guarantees we never regress a bank to zero NPL
            # rows just because its template entry is stale.
            if template is not None:
                npl_tmpl.extend(_extract_npl_brsa_via_template(i, text, template))
            npl_regex.extend(_extract_npl_brsa_from_page(i, text))
            # BRSA section 7.2 "Standart Nitelikli ve Yakın İzlemedeki" loan
            # amounts — Stage 1 + Stage 2 portfolio balances (combined with
            # npl_brsa_gross's Stage 3 = full stage breakdown). The y-clustered
            # fitz text already rebuilds the İşbank-style column-split rows that
            # used to need a separate coordinate fallback.
            rep.rows.extend(_extract_loans_by_stage_from_page(i, text))
            # Stage 1 + Stage 2 ECL provisions from the same section 7.2.
            rep.rows.extend(_extract_stage12_ecl_from_page(i, text))
    finally:
        doc.close()

    # Choose the NPL source: template if it found a gross row, else regex.
    tmpl_has_gross = any(r.section == "npl_brsa_gross" for r in npl_tmpl)
    if tmpl_has_gross:
        rep.rows.extend(npl_tmpl)
    else:
        if template is not None and npl_regex:
            _log.warning(
                "%s: template NPL extraction found no gross row; using regex "
                "fallback (template may be stale — check labels in "
                "audit_templates.json).", bank_ticker or _infer_ticker(pdf_path),
            )
        rep.rows.extend(npl_regex)
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


def extract(pdf_path: str | Path, bank_ticker: str = "") -> CreditQualityReport:
    """Run the (fitz-only) stage-table extractor on a PDF path. Thin wrapper —
    `extract_from_pdf` opens the PDF itself via fitz."""
    return extract_from_pdf(None, str(pdf_path), bank_ticker=bank_ticker)


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
