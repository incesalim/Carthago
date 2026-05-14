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
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

from .extractor import parse_num


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
    ("çiftçilik ve hayvancılık", "agri_farming"),
    ("forestry", "agri_forestry"),
    ("ormancılık", "agri_forestry"),
    ("fishery", "agri_fishery"),
    ("balıkçılık", "agri_fishery"),
    ("agriculture", "agri_total"),
    ("tarım", "agri_total"),
    # --- Manufacturing group ----------------------------------------------
    ("mining and quarrying", "mfg_mining"),
    ("madencilik ve taşocakçılığı", "mfg_mining"),
    ("madencilik", "mfg_mining"),
    ("production", "mfg_production"),
    ("imalat sanayi", "mfg_production"),
    ("i̇malat sanayi", "mfg_production"),
    ("electricity, gas and water", "mfg_utilities"),
    ("electricity, gas, water", "mfg_utilities"),
    ("elektrik, gaz, su", "mfg_utilities"),
    ("elektrik. gaz. su", "mfg_utilities"),
    # The Turkish "Sanayi" sometimes appears as a group header (sum-row);
    # we still capture it under a distinct key so it's separable.
    ("manufacturing", "mfg_total"),
    ("sanayi", "mfg_total"),
    # --- Construction (no sub) --------------------------------------------
    ("construction", "construction"),
    ("inşaat", "construction"),
    ("i̇nşaat", "construction"),
    # --- Services group ----------------------------------------------------
    ("wholesale and retail trade", "svc_trade"),
    ("toptan ve perakende ticaret", "svc_trade"),
    ("accommodation and dining", "svc_hospitality"),
    ("otel ve lokanta hizmetleri", "svc_hospitality"),
    ("transportation and telecommunication", "svc_transport"),
    ("transportation and telecom", "svc_transport"),
    ("ulaştırma ve haberleşme", "svc_transport"),
    ("financial institutions", "svc_financial"),
    ("mali kuruluşlar", "svc_financial"),
    ("real estate and rental services", "svc_realestate"),
    ("real estate and rental", "svc_realestate"),
    ("gayrimenkul ve kira", "svc_realestate"),
    ("professional services", "svc_professional"),
    ("serbest meslek hizmetleri", "svc_professional"),
    ("educational services", "svc_education"),
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
        r"(?:Information\s+(?:by|on)\s+(?:major\s+)?sectors?|"
        r"major\s+sectors?\s+(?:or|and)\s+type\s+of\s+counterparties?|"
        r"sectoral\s+concentration\s+of\s+(?:cash\s+)?loans?|"
        r"Önemli\s+Sektörlere|"
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
    if s in ("-", "—", "–", ""):
        return 0.0
    return parse_num(s)


# Three numbers in a row, separated by whitespace, optionally with commas
# inside numbers and an optional leading footnote ref like "(1)".
_THREE_NUMS_TAIL = re.compile(
    r"(?P<n1>(?:\(?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?\)?|-))"
    r"\s+"
    r"(?P<n2>(?:\(?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?\)?|-))"
    r"\s+"
    r"(?P<n3>(?:\(?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?\)?|-))"
    r"\s*$"
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
    if _NONCASH_HINTS.search(text):
        # Page is about non-cash loans, not what we want here.
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
    rep = LoansBySectorReport(pdf_path=pdf_path)
    for i, page in enumerate(pdf.pages, 1):
        if i <= skip_pages:
            continue
        text = page.extract_text() or ""
        if not _page_has_sector_heading(text):
            continue
        rep.rows.extend(_extract_section(i, text))
    # Dedupe: keep first occurrence of each (sector, period_type). When the
    # same table appears twice (consolidated reports sometimes do), the
    # first hit is the primary disclosure; later ones are usually sub-views.
    seen: set[tuple[str, str]] = set()
    deduped: list[SectorRow] = []
    for r in rep.rows:
        key = (r.sector, r.period_type)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    rep.rows = deduped
    return rep


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
