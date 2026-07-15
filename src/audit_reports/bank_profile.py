"""Bank profile extractor — branches + personnel from BRSA audit-report
qualitative section.

Every Turkish bank audit report opens with a 'Banka Hakkında Genel Bilgi'
(General Information About the Bank) section that usually discloses, in one
sentence, the bank's operating footprint:
  - branches: domestic count, foreign count, total
  - personnel / employee count

These are useful size/operational indicators for a bank card. The wording
varies bank-to-bank and Turkish-vs-English, so extraction is a set of ordered,
sanity-banded regex patterns over the first pages' text (fitz, no pdfplumber).

Two traps every pattern here must survive, learned from the fleet:

  1. The "current (prior) noun" form. Most banks write the figure as
     ``223 (December 31, 2025: 216) branches`` / ``3.121 (31 Aralık 2025:
     3.103) personeli`` — a prior-period comparison in parentheses sits
     BETWEEN the current number and its noun. A naive ``<number> <noun>`` grabs
     the *prior* number inside the parens. Every number-before-noun pattern
     therefore allows an optional parenthetical (`_PAREN`) before the noun and
     captures the number *before* it.

  2. First-match-then-give-up. ``çalışan`` also appears in the table of
     contents line ``XV. Çalışanların hakları 22`` and in ``TMS 19 Çalışanlara``
     — a bare ``<number> çalışan`` would match ``19 Çalışanlara`` first, get 19,
     fail the sanity band, and the bank ends up with no personnel. So we
     ``finditer`` every pattern and take the first match whose value is IN the
     plausible band, not merely the first match.

Phrasings covered (one representative bank each):
  Branches — TR combined  "yurt içinde 422 şubesi ve yurt dışında 4 şubesi"  (TEB)
             TR domestic   "yurt içinde bulunan 54 adet şubesi"              (ING)
             TR bare-total "224 (…) şubesi ve … personeli ile"              (TFKB)
             TR total word "genel toplamda 1.769 şube" / "toplam 96 şubesi"  (ZIRAAT/ANADOLU)
             EN total      "1.112 branches consisting of 1.104 domestic and 8 foreign" (HALKB)
             EN dom/for    "789 domestic branches, 5 foreign branches"       (GARAN)
             EN local/for  "223 (…) local branches and 3 (…) foreign branches" (ALBRK)
             EN türkiye/os "740 branches operating in Türkiye and 1 branch in overseas" (YKBNK)
             EN dom-only   "239 domestic branches"                           (SKBNK/QNBFB)
  Personnel — TR "personel sayısı 1.333 (…) kişidir"                         (BURGAN)
              TR "çalışan sayısı 403 kişidir"                                (KLNMA/ZIRAATD)
              TR split "yurtiçi çalışan sayısı 3.140 … yurtdışı … 15"        (ZIRAAT/ZIRAATK)
              TR "3.121 (…) personeli" / "1.631 çalışanı"                    (VAKIFK/FIBA)
              EN "3,329 employees" / "10,339 (…) employees"                  (SKBNK/QNBFB)
              EN "with 2.787 (…) staff"                                      (ALBRK)
              EN "the number of our employee is 129"                        (COLENDI)

A handful of banks (İşbank, Aktifbank, Arap Türk, TSKB, Eximbank) state no
headline branch/personnel figure in the interim audit report at all — that is a
source-availability gap, not an extractor gap, and those rows stay NULL.

Extracted fields are stored in `bank_audit_profile`. One row per
(bank_ticker, period, kind), updated on each extraction.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .extractor import _HAS_FITZ, _fitz_page_count, _fitz_page_text

# A count: digits grouped by "." or "," (banks even mix conventions within one
# document). Non-capturing so it can be embedded with explicit named groups.
_D = r"\d{1,3}(?:[.,]\d{3})*|\d{1,6}"
# Optional prior-period comparison in parens sitting between a figure and its
# noun: "(31 Aralık 2025: 217)" / "(December 31, 2025 – 416)". Single level.
_PAREN = r"(?:\s*\([^()]*\))?"

# Plausible bands (a value outside is discarded, and matching continues).
_BR_LO, _BR_HI = 1, 9999          # branches for one bank
_PS_LO, _PS_HI = 50, 500_000      # personnel — loose (number-before) patterns
# The anchored "... sayısı N" / "number of ... is N" patterns are specific enough
# to trust a small count, so a brand-new bank (ENPARA filed "personel sayısı 24")
# isn't dropped by the 50 floor the looser patterns need against stray hits.
_PS_LABEL_LO = 5


def _parse_int(s: str) -> int | None:
    if not s:
        return None
    cleaned = s.replace(".", "").replace(",", "")
    try:
        return int(cleaned)
    except ValueError:
        return None


def _find(pattern: re.Pattern, text: str, lo: int, hi: int,
          group: str | int = "n") -> int | None:
    """First value of `group` across all matches of `pattern` that falls in
    [lo, hi]. Iterating (not just `.search`) is what lets a later, valid match
    win over an earlier out-of-band one (e.g. TOC/boilerplate noise)."""
    for m in pattern.finditer(text):
        v = _parse_int(m.group(group))
        if v is not None and lo <= v <= hi:
            return v
    return None


def _c(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE | re.DOTALL)


# --- Branch patterns -------------------------------------------------------
# Combined domestic + foreign (fill both). The foreign number must sit directly
# before "şube" (only "adet"/parens allowed between) so a stray date like
# "yurtdışında ise 27 Ağustos …" (ZIRAATK) can't be read as 27 foreign branches.
_BR_TR_COMBINED = _c(
    rf"yurt[\s-]*içi(?:nde|ndeki)?\s+(?:bulunan\s+)?(?:toplam\s+)?(?P<dom>{_D})"
    rf"(?:\s*adet)?\s*(?:şube\w*)?{_PAREN}\s*(?:ve|,|\s)\s*"
    rf"yurt[\s-]*dışı(?:nda|ndaki)?\s+(?:bulunan\s+)?(?:toplam\s+)?(?P<for>{_D})"
    rf"(?:\s*adet)?\s*{_PAREN}\s*şube")
# AKBNK: "yurt çapında 646 şubesi ve yurtdışında 1 şubesi".
_BR_TR_AKBNK = _c(
    rf"yurt\s+çapında\s+(?P<dom>{_D})\s+şube.{{0,80}}"
    rf"yurt[\s-]?dışında\s+(?P<for>{_D})\s+şube")
# Domestic-only: "yurt içinde (bulunan) X (adet) şube" with no foreign clause.
_BR_TR_DOMESTIC = _c(
    rf"yurt[\s-]*içi(?:nde|ndeki)?\s+(?:bulunan\s+)?(?:toplam\s+)?(?P<n>{_D})"
    rf"(?:\s*adet)?\s*{_PAREN}\s*şube")
# Bare total, verb-anchored: "224 (…) şubesi ve …", "219 şubesi (…) ve …",
# "25 şubesi ve …", "15 şubesi bulunmakta", "1 şubesi bulunmaktadır". Only run
# when no domestic/foreign split was found, so it can't grab a "yurt dışında N
# şubesi bulunmaktadır" foreign clause as the total.
_BR_TR_BARE = _c(
    rf"(?P<n>{_D})\s*{_PAREN}\s*şube\w*\s*{_PAREN}\s+(?:ve\b|ile\b|bulunmakta)")
# Explicit total words. "genel toplamda" must beat a bare "toplam 24 şube"
# (ZIRAAT writes its foreign-only count that way), so it is tried first.
_BR_TR_GENEL = _c(rf"genel\s+toplamda\s+(?P<n>{_D})\s*{_PAREN}\s*şube")
_BR_TR_TOPLAM = _c(
    rf"(?:olmak\s+üzere\s+|birlikte\s+)?toplam\s+(?P<n>{_D})\s*{_PAREN}\s*şube")
# Subject-anchored bare total (KUVEYT "itibarıyla Grup 458 şubesi").
_BR_TR_SUBJECT = _c(
    rf"itibar[ıi]yla\s+(?:Banka|Grup|Bankas[ıi]|Katılım\s+Bankas[ıi])['’]?\s*\w*\s+"
    rf"(?:faaliyet\s+gösteren\s+)?(?P<n>{_D})\s*şube")

# English combined / split.
_BR_EN_TOTAL = _c(
    rf"(?P<tot>{_D})\s*{_PAREN}\s*branches\s+consisting\s+of\s+(?P<dom>{_D})"
    rf"\s*{_PAREN}\s*domestic\s+(?:and\s+)?(?P<for>{_D})\s*{_PAREN}\s*foreign")
_BR_EN_DOM_FOR = _c(
    rf"(?P<dom>{_D})\s*{_PAREN}\s*(?:domestic|local)\s+branches?"
    rf"(?:\s*,\s*and\s*|\s*,\s*|\s+and\s+)(?P<for>{_D})\s*{_PAREN}\s*foreign\s+branches?")
_BR_EN_TR_OS = _c(
    rf"(?P<dom>{_D})\s*{_PAREN}\s*branches?\s+operating\s+in\s+T[üu]rkiye\s+and\s+"
    rf"(?P<for>{_D})\s*{_PAREN}\s*branch(?:es)?\s+(?:in\s+)?overseas")
# Domestic-only in English. "domestic"/"local" needn't be immediately followed by
# "branch" — QNBFB writes "415 domestic (December 31, 2025 – 416) and 1 … branches"
# — so a lookahead just requires "branch" later in the same sentence.
_BR_EN_DOM = _c(rf"(?P<n>{_D})\s*{_PAREN}\s*(?:domestic|local)\b(?=[^.]*\bbranch)")

# --- Personnel patterns ----------------------------------------------------
# Split first: "yurtiçi çalışan sayısı 3.140 (…), yurtdışı çalışan sayısı 15"
# (note ZIRAATK writes "yurtiçi" with no space).
_PS_TR_SPLIT = _c(
    rf"yurt\s*içi\s+çalışan\s+say[ıi]s[ıi]\s+(?P<dom>{_D}).{{0,40}}?"
    rf"yurt\s*dışı\s+çalışan\s+say[ıi]s[ıi]\s+(?P<for>{_D})")
# Label-before: "personel sayısı 1.333 (…)", "çalışan sayısı 403 (…)".
_PS_TR_LABEL = _c(rf"(?:personel|çalışan)\s+say[ıi]s[ıi](?:\s+ise)?\s+(?P<n>{_D})")
# Number-before: "3.121 (…) personeli", "toplam 1.631 çalışanı".
_PS_TR_PERSONELI = _c(rf"(?P<n>{_D})\s*{_PAREN}\s+personel(?:i|e)?\b")
_PS_TR_CALISAN = _c(rf"(?:toplam\s+)?(?P<n>{_D})\s*{_PAREN}\s+çalışan(?:ı|ları)?\b")
# English.
_PS_EN_COUNT = _c(rf"\b(?P<n>{_D})\s*{_PAREN}\s+(?:employees|personnel|staff\s+members)\b")
_PS_EN_WITH_STAFF = _c(rf"with\s+(?P<n>{_D})\s*{_PAREN}\s+staff\b")
_PS_EN_NUMBER_OF = _c(rf"number\s+of\s+(?:our\s+)?employees?\s+is\s+(?P<n>{_D})")


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


def _extract_branches(text: str, profile: BankProfile) -> None:
    """Fill branches_{domestic,foreign,total} from the qualitative text."""
    # 1) domestic + foreign together — try each combined pattern in order.
    for pat, dg, fg in (
        (_BR_EN_TOTAL, "dom", "for"),
        (_BR_EN_DOM_FOR, "dom", "for"),
        (_BR_EN_TR_OS, "dom", "for"),
        (_BR_TR_AKBNK, "dom", "for"),
        (_BR_TR_COMBINED, "dom", "for"),
    ):
        for m in pat.finditer(text):
            dom = _parse_int(m.group(dg))
            fgn = _parse_int(m.group(fg))
            if dom is not None and _BR_LO <= dom <= _BR_HI:
                profile.branches_domestic = dom
                if fgn is not None and 0 <= fgn <= _BR_HI:
                    profile.branches_foreign = fgn
                break
        if profile.branches_domestic is not None:
            break
    # explicit total sometimes carried by the EN "consisting of" form.
    if profile.branches_total is None:
        m = _BR_EN_TOTAL.search(text)
        if m:
            profile.branches_total = _parse_int(m.group("tot"))

    # 2) domestic-only.
    if profile.branches_domestic is None:
        profile.branches_domestic = _find(_BR_TR_DOMESTIC, text, _BR_LO, _BR_HI)
    if profile.branches_domestic is None:
        profile.branches_domestic = _find(_BR_EN_DOM, text, _BR_LO, _BR_HI)

    # 3) total (explicit words win; bare/subject only if no split found).
    if profile.branches_total is None:
        profile.branches_total = _find(_BR_TR_GENEL, text, _BR_LO, _BR_HI)
    if profile.branches_total is None:
        profile.branches_total = _find(_BR_TR_TOPLAM, text, _BR_LO, _BR_HI)
    if profile.branches_total is None and profile.branches_domestic is None:
        profile.branches_total = _find(_BR_TR_BARE, text, _BR_LO, _BR_HI)
    if profile.branches_total is None and profile.branches_domestic is None:
        profile.branches_total = _find(_BR_TR_SUBJECT, text, _BR_LO, _BR_HI)

    # 4) reconcile total ⇄ components. Derive foreign FIRST — only from an
    #    EXPLICIT total (e.g. ZIRAATK "231 yurt içi … toplam 233 şube" ⇒ 2
    #    foreign); a domestic-only disclosure has no explicit total here, so
    #    foreign stays NULL rather than a fabricated 0.
    if (profile.branches_foreign is None
            and profile.branches_total is not None
            and profile.branches_domestic is not None
            and profile.branches_total >= profile.branches_domestic):
        profile.branches_foreign = profile.branches_total - profile.branches_domestic
    # Then fill total. A domestic-only disclosure ("yurt içinde 35 şube", no
    #    foreign clause) means total == domestic — and the UI keys the branch
    #    chip and "assets per branch" off branches_total ONLY, so a captured
    #    domestic count is invisible unless total is set.
    if profile.branches_total is None and profile.branches_domestic is not None:
        profile.branches_total = profile.branches_domestic + (profile.branches_foreign or 0)

    # sanity clamp.
    for attr in ("branches_domestic", "branches_foreign", "branches_total"):
        v = getattr(profile, attr)
        if v is not None and not (0 <= v <= _BR_HI):
            setattr(profile, attr, None)


def _extract_personnel(text: str, profile: BankProfile) -> None:
    """Fill personnel from the qualitative text."""
    # Split (domestic + foreign staff) → sum. Anchored → low floor.
    m = _PS_TR_SPLIT.search(text)
    if m:
        dom = _parse_int(m.group("dom"))
        fgn = _parse_int(m.group("for"))
        if dom is not None:
            total = dom + (fgn or 0)
            if _PS_LABEL_LO <= total <= _PS_HI:
                profile.personnel = total
    # (pattern, floor): the "... sayısı N" / "number of ... is N" anchors trust a
    # small startup count; number-before / bare-noun patterns keep the 50 floor.
    for pat, lo in ((_PS_TR_LABEL, _PS_LABEL_LO),
                    (_PS_EN_NUMBER_OF, _PS_LABEL_LO),
                    (_PS_TR_PERSONELI, _PS_LO),
                    (_PS_TR_CALISAN, _PS_LO),
                    (_PS_EN_COUNT, _PS_LO),
                    (_PS_EN_WITH_STAFF, _PS_LO)):
        if profile.personnel is not None:
            break
        profile.personnel = _find(pat, text, lo, _PS_HI)


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
    # fitz text, same engine as every other lane (no pdfplumber). Collapse runs
    # of spaces so a wrapped "current (prior)" phrase stays matchable.
    n = min(max_pages, _fitz_page_count(pdf_path) or 0)
    text = "".join(_fitz_page_text(pdf_path, i) + "\n" for i in range(n))
    if not text:
        return profile
    text = re.sub(r"[ \t]+", " ", text)

    _extract_branches(text, profile)
    _extract_personnel(text, profile)
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
