"""Free-provision (serbest karşılık) extractor — the discretionary "rainy-day"
reserve at the centre of the ALBRK Q1-2025 case.

A free provision is a cushion a bank sets aside from profit at management's own
discretion — *outside* the BRSA provisioning rules. Auditors qualify over it (see
[audit_opinion]); when a bank releases it, the release lands in profit. It is the
single most load-bearing "quality of earnings" number in Turkish bank accounts,
and we held it nowhere. This lane captures the STOCK per (bank, period, kind).

It is NOT in any statement we already extract. The figure lives only in the
"Other provisions" liability note (BRSA Note II.5.b, or a dedicated
"Muhtemel riskler için ayrılan serbest karşılık" sub-note), disclosed in one of
several prose/table forms — deposit vs participation banks, English convenience
translations vs Turkish originals.

The extraction hazard (the /franchise trap): free-provision *flows* are quoted
all over the report — "TL 7,000,000 … is reversed", "iptal edilen 11,000,000 TL".
Grabbing one of those instead of the stock is the obvious failure. Two defences:
  1. Anchor on the STOCK disclosure, which uniquely carries a parenthetical
     prior-period comparison — "(December 31, 2024: TL 7.300.000)" / "(31 Aralık
     2024: 15,000,000 TL)". A flow mention almost never does.
  2. Reject any candidate whose amount sits next to a reversal/allocation verb
     (reversed / cancelled / iptal / ilave … ayrılmıştır).
The parenthetical also hands us the prior figure for free — a built-in
longitudinal check (this report's prior == last report's current).

Deterministic, fitz-only. Stored in `bank_audit_free_provision`.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

# A monetary amount in thousand-TL: must carry a thousands group (so we never
# match a footnote marker, a year, or a one/two-digit stray). Accepts "." or ","
# as the separator (reports mix both, sometimes within one document).
_NUM = r"\d{1,3}(?:[.,]\d{3})+"

# "free provision" / "serbest karşılık" — the subject. `serbest kar[sş]ıl` also
# folds the diacritic-dropped text layer some PDFs produce.
_SUBJ_EN = r"free\s+provision"
_SUBJ_TR = r"serbest\s+kar[şs][ıi]l[ıi]k"

# Prior-period parenthetical: "(December 31, 2024: TL 7.300.000)" /
# "(31 Aralık 2024: 15,000,000 TL)" / "(31 December 2024: TL 701,889)". The value
# may be an amount or a "none" word.
# The amount must sit CLOSE to the date inside the parenthetical (≤40 chars) —
# a clean "(December 31, 2024: TL 7.300.000)" pairs them tightly, whereas a
# number buried deep in prose parentheses is not reliably the prior stock. Better
# to return None than a wrong prior, so keep this tight.
_PRIOR = re.compile(
    r"\(\s*(?:31\s+(?:Aral[ıi]k|December)|December\s+31)[^)]{0,40}?"
    r"(?:TL\s*)?(" + _NUM + r"|[Bb]ulunmamaktad[ıi]r|[Nn]one|[Yy]oktur)",
    re.I,
)

# Flow verbs — if one hugs the matched amount, that amount is a reversal or
# allocation (a P&L flow), not the stock. Checked in a tight window around the
# amount so a "cancelled" clause about a DIFFERENT number can't veto the stock.
_FLOW = re.compile(r"revers|cancel|iptal|ilave|is\s+reversed|expense|gider", re.I)

# Explicit "the bank holds none". `.` (no DOTALL) allows the "." thousands
# separator but stays on the logical line.
_NONE = re.compile(
    _SUBJ_TR + r".{0,60}?[Bb]ulunmamaktad[ıi]r"
    r"|" + _SUBJ_EN + r".{0,40}?(?::\s*)?[Nn]one\b",
    re.I,
)

# STOCK-amount patterns. Applied to full page text — the connectors use `.`
# (newline-bounded, NOT `[^.\n]`) so a "300.000" is never cut at its separator.
# Each captures the amount in group 1.
_STOCK_PATTERNS = [
    # EN — "free provision … amounting to/of (thousand) TL 300.000"
    re.compile(_SUBJ_EN + r".{0,80}?amount(?:ing)?\s+(?:to|of)\s+(?:thousand\s+)?TL\s*(" + _NUM + r")", re.I),
    # EN — "free provision at an amount of thousand TL 6.600.000"
    re.compile(_SUBJ_EN + r"\s+at\s+an\s+amount\s+of\s+(?:thousand\s+)?TL\s*(" + _NUM + r")", re.I),
    # EN — "includes a free provision of TL 1.650.000"
    re.compile(r"includes?\s+a\s+" + _SUBJ_EN + r"\s+(?:of\s+)?(?:thousand\s+)?TL\s*(" + _NUM + r")", re.I),
    # EN — amount BEFORE subject: "amounting to TL 546,889 (…) for free provision"
    re.compile(r"amount(?:ing)?\s+(?:to|of)\s+(?:thousand\s+)?TL\s*(" + _NUM + r").{0,80}?for\s+" + _SUBJ_EN, re.I),
    # TR — "serbest karşılık tutarı 4,000,000 TL"
    re.compile(_SUBJ_TR + r"\s+tutar[ıi]\s+(" + _NUM + r")\s*(?:bin\s+)?TL", re.I),
    # TR — "9.000.000 TL tutarında(ki) … serbest karşılık"
    re.compile(r"(" + _NUM + r")\s*(?:bin\s+)?TL\s+tutar[ıi]nda(?:ki)?.{0,60}?" + _SUBJ_TR, re.I),
    # TR — "serbest karşılık … 9.000.000 TL … yer almaktadır"
    re.compile(_SUBJ_TR + r".{0,60}?(" + _NUM + r")\s*(?:bin\s+)?TL.{0,40}?yer\s+almaktad[ıi]r", re.I),
]


def _parse_amt(s: str) -> int | None:
    if not s:
        return None
    cleaned = s.replace(".", "").replace(",", "")
    return int(cleaned) if cleaned.isdigit() else None


def _parse_prior(tok: str) -> int | None:
    """Prior-parenthetical token → amount (0 for a 'none' word)."""
    if re.fullmatch(r"[Bb]ulunmamaktad[ıi]r|[Nn]one|[Yy]oktur", tok):
        return 0
    return _parse_amt(tok)


@dataclass
class FreeProvision:
    free_provision: int | None = None        # current-period stock; 0 = explicit none
    free_provision_prior: int | None = None  # prior period (Dec 31), from the parenthetical
    disclosed: bool = False                   # did the bank disclose a free provision at all?
    source_page: int | None = None
    snippet: str = ""                         # matched context, for audit/debug

    def is_empty(self) -> bool:
        return not self.disclosed


def classify_free_provision(pages: list[str]) -> FreeProvision:
    """Given the report's pages (as text), find the free-provision STOCK.

    Pure over already-extracted text so it is unit-testable without fitz. Pages
    are 0-indexed; the auditor's report (pages 0-~4) tends to state flows, so a
    balance-sheet note page ranks above an auditor-page match for the same signal.

    Ranking (higher wins): note page (+2) · amount found (+2) · prior
    parenthetical present (+2). An explicit "none" outranks nothing found."""
    res = FreeProvision()
    best_rank = -1

    for i, text in enumerate(pages):
        low = text.lower()
        # Pre-filter only — the patterns do the real work. Check "free" (not
        # "free provision"): the reader can split the phrase as "free\nprovision"
        # across a line box, and \s+ in the patterns spans that newline.
        if "serbest" not in low and "free" not in low:
            continue
        page_rank = 2 if i >= 5 else 0

        # Every stock-amount candidate on the page.
        for pat in _STOCK_PATTERNS:
            for m in pat.finditer(text):
                amt = _parse_amt(m.group(1))
                if amt is None:
                    continue
                # Flow veto: a reversal/allocation verb near the amount marks it
                # a P&L flow, not the stock. Reach further BEFORE (to catch
                # "free provision EXPENSE … amounting to TL X") than AFTER (so a
                # later "… of which X was cancelled" clause can't veto the stock).
                if _FLOW.search(text[max(0, m.start(1) - 55): m.end(1) + 20]):
                    continue
                prior = _PRIOR.search(text[m.start(): m.start() + 400])
                rank = page_rank + 2 + (2 if prior else 0)
                if rank > best_rank:
                    best_rank = rank
                    res.disclosed = True
                    res.free_provision = amt
                    res.free_provision_prior = _parse_prior(prior.group(1)) if prior else None
                    res.source_page = i
                    res.snippet = re.sub(r"\s+", " ", text[m.start(): m.start() + 140]).strip()

        # Explicit "none" — beats "nothing found", loses to any real amount.
        if best_rank < page_rank and _NONE.search(text):
            best_rank = page_rank
            res.disclosed = True
            res.free_provision = 0
            res.source_page = i
            nm = _NONE.search(text)
            res.snippet = re.sub(r"\s+", " ", text[nm.start(): nm.start() + 120]).strip()

    return res


def extract_free_provision_from_pdf(pdf_path: str = "") -> FreeProvision:
    """Read every page and classify the free-provision stock. fitz-only."""
    from .extractor import _fitz_page_count, _fitz_page_text, _HAS_FITZ

    if not (pdf_path and _HAS_FITZ):
        return FreeProvision()
    n = _fitz_page_count(pdf_path) or 0
    pages = [_fitz_page_text(pdf_path, i) for i in range(n)]
    return classify_free_provision(pages)


def upsert_free_provision(
    conn: sqlite3.Connection,
    bank_ticker: str,
    period: str,
    kind: str,
    fp: FreeProvision,
) -> int | None:
    """Store one bank's free-provision row. Skip-if-empty (no disclosure found),
    so a failed re-extract can't wipe a captured value — same rule as profile."""
    if fp is None or fp.is_empty():
        return None
    conn.execute(
        "INSERT OR REPLACE INTO bank_audit_free_provision "
        "(bank_ticker, period, kind, free_provision, free_provision_prior, "
        " source_page, source_text) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (bank_ticker, period, kind, fp.free_provision, fp.free_provision_prior,
         fp.source_page, (fp.snippet or "")[:300]),
    )
    conn.commit()
    return 1


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.stdout.reconfigure(encoding="utf-8")
    path = sys.argv[1] if len(sys.argv) > 1 else ""
    r = extract_free_provision_from_pdf(path)
    print(f"{Path(path).name}: stock={r.free_provision} prior={r.free_provision_prior} "
          f"disclosed={r.disclosed} p{r.source_page}")
    print("  snippet:", r.snippet)
