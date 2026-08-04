"""Task 1.3a — deterministic classifier for qualified-opinion basis paragraphs.

545 of the 552 modified opinions carry a `basis_text`. Each row is stored in
the FILING'S OWN language (`language` = tr|en) — there is no TR/EN pair — so
the patterns cover both languages.

Two structural facts shape the matching:

- The qualification sits at the START of the field; the known `_BASIS_END`
  defect means the tail can over-run into Key Audit Matters. Classification
  therefore reads only the leading `LEAD_CHARS`.
- Uppercase Turkish destroys naive lowercasing (`I`.casefold() → `i`, never
  `ı`), so every pattern spells dotted/dotless positions as `[iı]` classes.

Categories are a closed set. `free_provision` covers the discretionary-reserve
mechanism under all its printed names — "free provision", "serbest karşılık",
and BURGAN's "general reserve / general provision" wording — because the
auditor's objection is the same in each: a reserve outside BRSA requirements.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

LEAD_CHARS = 800

CATEGORIES = ("free_provision", "bond_reclassification", "other")

_FP = [
    re.compile(r"free\s+provision", re.I),
    re.compile(r"general\s+(?:reserve|provision)", re.I),
    # [kğ]: Turkish suffixation mutates the final k (karşılık → karşılığın).
    re.compile(r"serbest\s+karş[iı]l[iı][kğ]", re.I),
    re.compile(r"genel\s+karş[iı]l[iı][kğ]", re.I),
]
_BOND = [
    re.compile(r"reclassif", re.I),
    re.compile(r"yeniden\s+s[iı]n[iı]fland[iı]r", re.I),
    re.compile(r"menkul\s+k[iı]ymet.{0,120}s[iı]n[iı]fland[iı]r", re.I | re.S),
]


@dataclass(frozen=True)
class BasisClass:
    category: str
    pattern: str | None    # the regex that decided it (None for `other`)
    excerpt: str           # leading text, whitespace-collapsed, for the memo


def classify(basis_text: str) -> BasisClass:
    lead = basis_text[:LEAD_CHARS]
    excerpt = re.sub(r"\s+", " ", lead[:300]).strip()
    for rx in _FP:
        if rx.search(lead):
            return BasisClass("free_provision", rx.pattern, excerpt)
    for rx in _BOND:
        if rx.search(lead):
            return BasisClass("bond_reclassification", rx.pattern, excerpt)
    return BasisClass("other", None, excerpt)


def classify_all(conn: sqlite3.Connection,
                 bank: str | None = None) -> dict[tuple[str, str, str], BasisClass]:
    """`{(bank, period, kind): BasisClass}` for every non-empty basis_text."""
    where, params = ("AND bank_ticker = ?", [bank]) if bank else ("", [])
    rows = conn.execute(
        "SELECT bank_ticker, period, kind, basis_text FROM bank_audit_opinion "
        f"WHERE basis_text IS NOT NULL AND basis_text != '' {where}", params).fetchall()
    return {(r["bank_ticker"], r["period"], r["kind"]): classify(r["basis_text"])
            for r in rows}
