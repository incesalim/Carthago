"""Per-report format profiling of BRSA audit PDFs (rework plan Phase 0).

Observes HOW each (bank, period, kind) report is formatted — it never parses
values and never drives extraction (profiles validate and inform; parsing
stays anchor/label-based, so a sudden format change degrades to a drift alert
instead of a hard failure). Observations per report:

  - language, page count, located statement pages (§2) and §4/§5 anchors
  - per balance-sheet statement: text class (spaced/squished), dipnot style,
    sign convention (paren-negative values), modal value-column count,
    roman-section inventory, equity numeral, hierarchy row count
  - bank-type fingerprint: participation (TOPLANAN FONLAR) / deposit
    (MEVDUAT / DEPOSITS) / dev_investment (neither)
  - §5 footnote-table inventory with first page seen — the map future
    footnote extractors start from

Output is consumed by scripts/generate_audit_census.py (census + drift
sections of docs/AUDIT_BANK_CATALOG.md).
"""
from __future__ import annotations

import re

import pdfplumber

from .extractor import (
    HIERARCHY_PAT,
    _count_values,
    _locate_pages,
    _norm,
    extract_page_text_repaired,
)

# §4 + §5 anchor inventory, matched on _norm()-folded page text (A-Z only).
FOOTNOTE_ANCHORS: dict[str, list[str]] = {
    # digit-insensitive: _norm strips digits, so "Tier 1" and "Tier I" both
    # reduce to TIER
    "s4_capital": ["INDIRIMLERONCESICEKIRDEK", "COMMONEQUITYTIER"],
    "s4_liquidity": ["YUKSEKKALITELILIKIT", "HIGHQUALITYLIQUIDASSET"],
    "s4_leverage": ["KALDIRACORANI", "LEVERAGERATIO"],
    "fn_credit_stages": ["BEKLENENZARARKARSILIG", "EXPECTEDCREDITLOSS"],
    "fn_loans_by_sector": ["ONEMLISEKTORLERE", "MAJORSECTORS", "KARSITARAFTUR"],
    "fn_npl_movement": ["DONUKALACAKHAREKET", "MOVEMENTOFNONPERFORMING"],
    "fn_fx_position": ["KURRISKI", "CURRENCYRISK", "YABANCIPARAPOZISYON"],
    "fn_interest_rate_risk": ["FAIZORANIRISKI", "INTERESTRATERISK"],
    "fn_liquidity_maturity": [
        "KALANVADELERINEGORE", "REMAININGMATURIT", "LIKIDITERISKI", "LIQUIDITYRISK",
    ],
    "fn_fees_commissions": ["UCRETVEKOMISYON", "FEESANDCOMMISSION"],
    "fn_related_party": ["ILISKILITARAF", "RELATEDPART"],
    "fn_segment": ["FAALIYETBOLUM", "BOLUMLEREGORERAPOR", "SEGMENTREPORT", "OPERATINGSEGMENT"],
}

_TR_MARKERS = ["VARLIKLAR", "NAKIT", "TOPLAM", "KREDILER", "OZKAYNAK", "DONEM"]
_EN_MARKERS = ["ASSETS", "CASH", "TOTAL", "LOANS", "EQUITY", "PERIOD"]

# Dipnot (footnote-ref) styles next to row labels.
_DIPNOT_STYLES = [
    ("roman_paren", re.compile(r"\(\s*[IVX]+-[\d,.\s-]+\)")),     # (I-5), (I-6,7)
    ("section_ref", re.compile(r"\(\s*5\.\d[\d.]*\s*\)")),         # (5.1.5)
    ("paren_int", re.compile(r"\(\s*\d{1,2}\s*\)")),               # (6)
]
_PAREN_NEG = re.compile(r"\(\d{1,3}(?:[.,]\d{3})+\)")             # (6.633.015)
_SQUISH = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşü]{22,}")


def _profile_statement_text(text: str) -> dict:
    lines = text.split("\n")
    hier_lines = [ln.strip() for ln in lines if HIERARCHY_PAT.match(ln.strip())]
    ncols: dict[int, int] = {}
    romans: set[str] = set()
    equity_numeral = None
    for ln in hier_lines:
        n = _count_values(ln)
        if n >= 2:
            ncols[n] = ncols.get(n, 0) + 1
        m = re.match(r"^([IVX]+)\.", ln)
        if m:
            romans.add(m.group(1))
            nl = _norm(ln)
            if "OZKAYNAK" in nl or "SHAREHOLDERSEQUITY" in nl:
                equity_numeral = m.group(1)
    dipnots = [name for name, rx in _DIPNOT_STYLES if rx.search(text)]
    return {
        "rows": len(hier_lines),
        "ncols_modal": max(ncols, key=ncols.get) if ncols else None,
        "text_class": "squished" if _SQUISH.search(text) else "spaced",
        "dipnot_styles": dipnots,
        "sign_convention": "paren_negative" if _PAREN_NEG.search(text) else "plain",
        "romans": sorted(romans),
        "equity_numeral": equity_numeral,
    }


def _language(text: str) -> str:
    norm = _norm(text)
    tr = sum(norm.count(m) for m in _TR_MARKERS)
    en = sum(norm.count(m) for m in _EN_MARKERS)
    return "tr" if tr > en else "en"


def _bank_type(liab_text: str) -> str:
    norm = _norm(liab_text)
    if "TOPLANANFONLAR" in norm or "FUNDSCOLLECTED" in norm:
        return "participation"
    if "MEVDUAT" in norm or "DEPOSITS" in norm:
        return "deposit"
    return "dev_investment"


def profile_pdf(pdf_path: str) -> dict:
    """One report's format observations. Page-scan only — no value parsing."""
    out: dict = {"pdf": pdf_path}
    with pdfplumber.open(pdf_path) as pdf:
        out["pages"] = len(pdf.pages)
        loc = _locate_pages(pdf)
        out["section_pages"] = dict(loc)
        # §4/§5 tables always come after the financial statements; starting
        # the anchor scan there skips the cover/TOC pages (which list the
        # section names and would record phantom early hits).
        scan_from = max(loc.values()) + 1 if loc else 8
        anchors: dict[str, int] = {}
        for i, page in enumerate(pdf.pages, 1):
            if i < scan_from:
                continue
            try:
                norm = _norm(page.extract_text() or "")
            except Exception:
                continue
            for key, needles in FOOTNOTE_ANCHORS.items():
                if key not in anchors and any(n in norm for n in needles):
                    anchors[key] = i
        out["anchors"] = anchors
        for stmt, key in (("assets", "bs_assets"), ("liabilities", "bs_liab")):
            if key not in loc:
                out[stmt] = None
                continue
            text = extract_page_text_repaired(pdf.pages[loc[key] - 1])
            out[stmt] = _profile_statement_text(text)
            if stmt == "assets":
                out["language"] = _language(text)
            else:
                out["bank_type"] = _bank_type(text)
    return out
