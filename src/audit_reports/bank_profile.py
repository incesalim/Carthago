"""Bank profile extractor — branches + personnel from BRSA audit-report
qualitative section.

Every Turkish bank audit report opens with a 'Banka Hakkında Genel Bilgi'
(General Information About the Bank) section that discloses:
  - branches: domestic count, foreign count, total
  - personnel / employee count

These are useful size/operational indicators for a bank card. The format
varies slightly between banks and Turkish vs. English reports.

Patterns observed across 5+ banks:
  Turkish:
    "yurt çapında 646 şubesi ve yurtdışında 1 şubesi"     (AKBNK)
    "yurt içinde 1.745 şube, yurt dışında ... 24 şube ... 1.769 şube"  (ZIRAAT)
    "Banka'nın personel sayısı 12.591 kişidir"            (AKBNK)
    "personel sayısı 12.591 (31 Aralık 2024: 12.778)"     (AKBNK)
  English:
    "operates with a total of 1,092 branches consisting of 1,084 domestic
     and 8 foreign branches"                              (HALKB)
    "X employees" / "X personnel"

Extracted fields are stored in `bank_audit_profile`. One row per
(bank_ticker, period, kind), updated on each extraction.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .extractor import _HAS_FITZ, _fitz_page_count, _fitz_page_text

# Numbers in audit reports use either "." or "," as thousands separator.
# Some banks even mix conventions within the same document (Turkish text
# uses "." but personnel count uses "," — observed in VAKBN). Accept both.
_NUM = r"(\d{1,3}(?:[.,]\d{3})*|\d{1,6})"


def _parse_int(s: str) -> int | None:
    if not s:
        return None
    cleaned = s.replace(".", "").replace(",", "")
    try:
        return int(cleaned)
    except ValueError:
        return None


# --- Branch patterns -------------------------------------------------------

# Turkish — combined "yurt içinde X ve yurt dışında Y" (VAKBN, DENIZ).
_PAT_TR_COMBINED = re.compile(
    rf"yurt[\s-]?içi(?:nde|ndeki)?\s+(?:toplam\s+)?{_NUM}"
    rf"(?:\s*\([^)]*\))?\s*(?:ve|,)?\s*"  # optional "(prior period: X)" parens
    rf"yurt[\s-]?dışı(?:nda|ndaki)?\s+(?:toplam\s+)?{_NUM}",
    re.IGNORECASE | re.DOTALL,
)
# Turkish — AKBNK: "yurt çapında 646 şubesi ve yurtdışında 1 şubesi"
_PAT_TR_AKBNK = re.compile(
    rf"yurt\s+çapında\s+{_NUM}\s+şube.{{0,80}}yurt[\s-]?dışında\s+{_NUM}\s+şube",
    re.IGNORECASE | re.DOTALL,
)
# Turkish — domestic-only: "yurt içinde 35 şubesi" with NO "yurt dışında" clause
# (FIBA, ALNTF…). Tried after the combined pattern, so banks with both still get both.
_PAT_TR_DOMESTIC = re.compile(
    rf"yurt[\s-]?içi(?:nde|ndeki)?\s+(?:toplam\s+)?{_NUM}\s+şube",
    re.IGNORECASE,
)
# Turkish — bare total with no domestic/foreign split: "itibarıyla Grup 458 şubesi"
# (KUVEYT). Anchored on the date+subject context to avoid matching a stray "X şube".
_PAT_TR_SUBE_TOTAL = re.compile(
    rf"itibar[ıi]yla\s+(?:Banka|Grup|Bankas[ıi]|Katılım\s+Bankas[ıi])['’]?\s*\w*\s+{_NUM}\s+şube",
    re.IGNORECASE,
)
# Turkish — "genel toplamda X şubesi" / "toplam X şubesi" — explicit total
# (ZIRAAT writes both: "toplam 24 şube" (foreign-only count!) AND
# "genel toplamda 1.769 şubesinin", so "genel toplamda" must win).
_PAT_TR_GENEL_TOPLAM = re.compile(
    rf"genel\s+toplamda\s+{_NUM}\s+şube",
    re.IGNORECASE,
)
_PAT_TR_TOPLAM = re.compile(
    rf"olmak\s+üzere\s+toplam\s+{_NUM}\s+şube",
    re.IGNORECASE,
)

# English: "1.092 branches consisting of 1.084 domestic and 8 foreign"
_PAT_EN_TOTAL_DOM_FOR = re.compile(
    rf"{_NUM}\s+branches\s+consisting\s+of\s+{_NUM}\s+domestic\s+(?:and\s+)?{_NUM}\s+foreign",
    re.IGNORECASE | re.DOTALL,
)
# English: GARAN — "787 domestic branches, 7 foreign branches"
_PAT_EN_DOM_FOR = re.compile(
    rf"{_NUM}\s+domestic\s+branches?(?:\s*,\s*and\s*|\s*,\s*|\s+and\s+){_NUM}\s+foreign\s+branches?",
    re.IGNORECASE | re.DOTALL,
)

# --- Personnel patterns ----------------------------------------------------

# Turkish — "Banka'nın personel sayısı X (31 Aralık 2024: Y) kişidir"
_PAT_TR_PERSONNEL = re.compile(
    rf"personel\s+sayısı(?:\s+ise)?\s+{_NUM}",
    re.IGNORECASE,
)
# Turkish — "X personeli" (KUVEYT "7,565 personeli") and "X çalışan[ı]" (FIBA
# "toplam 1.571 çalışan") — number BEFORE the noun (so it can't catch the
# "PERSONEL GİDERLERİ <amount>" expense lines, where the number comes after).
_PAT_TR_PERSONELI = re.compile(rf"{_NUM}\s+personel(?:i|e)\b", re.IGNORECASE)
_PAT_TR_CALISAN = re.compile(rf"(?:toplam\s+)?{_NUM}\s+çalışan", re.IGNORECASE)
# Turkish — ZIRAAT split: "yurt içi çalışan sayısı 25.642, yurt dışı çalışan sayısı 101"
_PAT_TR_PERSONNEL_SPLIT = re.compile(
    rf"yurt\s+içi\s+çalışan\s+sayısı\s+{_NUM}.{{0,30}}yurt\s+dışı\s+çalışan\s+sayısı\s+{_NUM}",
    re.IGNORECASE | re.DOTALL,
)
# English: "X employees" / "X personnel"
_PAT_EN_PERSONNEL = re.compile(
    rf"\b{_NUM}\s+(?:employees|personnel|staff\s+members)\b",
    re.IGNORECASE,
)


@dataclass
class BankProfile:
    bank_ticker: str = ""
    period: str = ""
    kind: str = ""
    branches_domestic: int | None = None
    branches_foreign: int | None = None
    branches_total: int | None = None
    personnel: int | None = None

    def is_empty(self) -> bool:
        return all(v is None for v in (
            self.branches_domestic, self.branches_foreign,
            self.branches_total, self.personnel,
        ))


def extract_profile_from_pdf(
    pdf_path: str = "",
    max_pages: int = 25,
) -> BankProfile:
    """Scan the first `max_pages` pages of an audit report for branch +
    personnel disclosures. Returns a BankProfile (possibly partially-filled)."""
    profile = BankProfile()
    if not (pdf_path and _HAS_FITZ):
        return profile
    # Concatenate first N pages (qualitative section is always near the start) —
    # fitz text, same engine as every other lane (no pdfplumber).
    n = min(max_pages, _fitz_page_count(pdf_path) or 0)
    text = "".join(_fitz_page_text(pdf_path, i) + "\n" for i in range(n))
    if not text:
        return profile

    # --- Branches: try patterns in order of specificity --------------------

    # English "X branches consisting of Y domestic and Z foreign" (HALKB).
    m = _PAT_EN_TOTAL_DOM_FOR.search(text)
    if m:
        profile.branches_total = _parse_int(m.group(1))
        profile.branches_domestic = _parse_int(m.group(2))
        profile.branches_foreign = _parse_int(m.group(3))
    # English GARAN: "787 domestic branches, 7 foreign branches".
    if profile.branches_domestic is None:
        m = _PAT_EN_DOM_FOR.search(text)
        if m:
            profile.branches_domestic = _parse_int(m.group(1))
            profile.branches_foreign = _parse_int(m.group(2))
    # Turkish AKBNK: "yurt çapında 646 şubesi ve yurtdışında 1 şubesi".
    if profile.branches_domestic is None:
        m = _PAT_TR_AKBNK.search(text)
        if m:
            profile.branches_domestic = _parse_int(m.group(1))
            profile.branches_foreign = _parse_int(m.group(2))
    # Turkish combined: "yurt içinde X ... yurt dışında Y" (VAKBN, DENIZ, ZIRAAT).
    if profile.branches_domestic is None:
        m = _PAT_TR_COMBINED.search(text)
        if m:
            profile.branches_domestic = _parse_int(m.group(1))
            profile.branches_foreign = _parse_int(m.group(2))
    # Turkish domestic-only: "yurt içinde X şubesi" with no foreign clause (FIBA).
    if profile.branches_domestic is None:
        m = _PAT_TR_DOMESTIC.search(text)
        if m:
            profile.branches_domestic = _parse_int(m.group(1))

    # Total: prefer "genel toplamda" (ZIRAAT) > "olmak üzere toplam" (VAKBN).
    if profile.branches_total is None:
        m = _PAT_TR_GENEL_TOPLAM.search(text)
        if m:
            profile.branches_total = _parse_int(m.group(1))
    if profile.branches_total is None:
        m = _PAT_TR_TOPLAM.search(text)
        if m:
            profile.branches_total = _parse_int(m.group(1))
    # Bare total with no domestic/foreign split: "itibarıyla Grup 458 şubesi" (KUVEYT).
    if profile.branches_total is None and profile.branches_domestic is None:
        m = _PAT_TR_SUBE_TOTAL.search(text)
        if m:
            profile.branches_total = _parse_int(m.group(1))
    # Derive total if missing but both components present.
    if (profile.branches_total is None
            and profile.branches_domestic is not None
            and profile.branches_foreign is not None):
        profile.branches_total = profile.branches_domestic + profile.branches_foreign

    # Sanity: branches reasonable for a bank (1-9999).
    for attr in ("branches_domestic", "branches_foreign", "branches_total"):
        v = getattr(profile, attr)
        if v is not None and not (0 <= v <= 9999):
            setattr(profile, attr, None)

    # --- Personnel ---------------------------------------------------------

    # ZIRAAT-style split: "yurt içi çalışan sayısı X, yurt dışı çalışan sayısı Y".
    m = _PAT_TR_PERSONNEL_SPLIT.search(text)
    if m:
        dom = _parse_int(m.group(1))
        fgn = _parse_int(m.group(2))
        if dom is not None:
            profile.personnel = dom + (fgn or 0)
    # Standard Turkish "personel sayısı X".
    if profile.personnel is None:
        m = _PAT_TR_PERSONNEL.search(text)
        if m:
            profile.personnel = _parse_int(m.group(1))
    # Turkish "X personeli" (KUVEYT) / "X çalışan" (FIBA).
    if profile.personnel is None:
        m = _PAT_TR_PERSONELI.search(text)
        if m:
            profile.personnel = _parse_int(m.group(1))
    if profile.personnel is None:
        m = _PAT_TR_CALISAN.search(text)
        if m:
            profile.personnel = _parse_int(m.group(1))
    # English "X employees".
    if profile.personnel is None:
        m = _PAT_EN_PERSONNEL.search(text)
        if m:
            profile.personnel = _parse_int(m.group(1))

    # Sanity: personnel count must be plausible (>= 50, <= 500k).
    if profile.personnel is not None and not (50 <= profile.personnel <= 500_000):
        profile.personnel = None

    return profile


def upsert_profile(
    conn: sqlite3.Connection,
    bank_ticker: str,
    period: str,
    kind: str,
    profile: BankProfile,
) -> None:
    """Idempotently store one bank's profile row."""
    conn.execute(
        "INSERT OR REPLACE INTO bank_audit_profile "
        "(bank_ticker, period, kind, branches_domestic, branches_foreign, "
        " branches_total, personnel) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            bank_ticker, period, kind,
            profile.branches_domestic, profile.branches_foreign,
            profile.branches_total, profile.personnel,
        ),
    )
    conn.commit()


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    path = sys.argv[1] if len(sys.argv) > 1 else "data/_tmp_akbnk_2025q4.pdf"
    p = extract_profile_from_pdf(path)
    print(f"{Path(path).name}: domestic={p.branches_domestic} foreign={p.branches_foreign} "
          f"total={p.branches_total} personnel={p.personnel}")
