"""Liquidity & leverage extractor — BRSA §4.6 (LCR, NSFR) and §4.7 (leverage).

Three headline ratios, each on its own labelled data row (label + percentage
values), e.g. (GARAN 2026Q1):

    Liquidity Coverage Ratio (%) ...... 144.86  313.04   # total(TL+FC), FC-only
    Net Stable Funding Ratio (%) ...... 127.25            # current; prior on next table
    Leverage ratio .................... 5.71    5.96      # current, prior

Same deterministic approach as capital_adequacy.py: scan the risk-management
pages for each metric's data row (the `(%)` + trailing numbers distinguish a
real table row from the policy prose that also names these ratios), and parse
the trailing values. The first LCR row gives the current period's total / FC
LCR; NSFR's first/second occurrences are current/prior; the leverage row carries
current+prior in two columns. All values are percentages.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

from .capital_adequacy import _parse_ratio, _repair_split_digits, _trailing_two_tokens
from .extractor import _HAS_FITZ

_SKIP_PAGES = 12
_MAX_SCAN_FROM_START = 26   # pages to scan once the LCR section begins; the
#                            leverage table (§4.7) can sit well below the LCR one.

# Data-row anchors. Each requires the "(%)" header (or, for leverage, the bare
# label) so policy prose that merely mentions the ratio name is not matched.
# `_RN` absorbs an optional leading row number in any form: "34 ", "15.", "15." glued.
_RN = r"(?:\d+\.?\s*)?"
# Turkish dotted/dotless-I casing: İ→i, I→ı (then .lower() handles Ş/Ç/… and ASCII)
# so UPPER-CASE labels (TFKB) fold to the same form the patterns use.
_TR_LOWER = str.maketrans("İI", "iı")
# Prose leverage (older FIBA): "…kaldıraç oranı <date> itibarıyla %6,06…".
_PROSE_LEV_RX = re.compile(
    r"kaldıraç\s+oran[ıi][^.]{0,110}?itibar[ıi]yla\s*%\s*([\d.,]+)", re.IGNORECASE)
# EN labels use \s* between words: TSKB's 2023–2024 squished text layer drops
# inter-word spaces ("LiquidityCoverageRatio(%)") — same class capital_adequacy
# handles. Turkish squish has not been observed; TR patterns keep \s+.
_LCR_RX = [re.compile(p, re.IGNORECASE) for p in [
    rf"^{_RN}Liquidity\s*Coverage\s*Ratio\s*\(\s*%\s*\)",
    rf"^{_RN}Likidite\s+Kar[şs]ılama\s+Oranı\s*\(\s*%\s*\)",
]]
# NSFR: banks vary wording (Ratio/Rate), drop the "(%)" (DENIZ), or file in
# Turkish ("Net İstikrarlı Fonlama Oranı", with i/İ/ı variants). The leading ^
# anchor + a trailing number keeps prose mentions out even without the "(%)".
_NSFR_RX = [re.compile(p, re.IGNORECASE) for p in [
    rf"^{_RN}Net\s*Stable\s*Funding\s*(?:Ratio|Rate)\b",
    rf"^{_RN}Net\s+[Iİiı]stikrarl[ıi]\s+Fonlama\s+Oran",
]]
# Leverage: optional "Financial " (QNBFB) / "Finansal " prefix; EN or TR label.
_LEV_RX = [re.compile(p, re.IGNORECASE) for p in [
    rf"^{_RN}(?:Financial\s*)?Leverage\s*[Rr]atio\b",
    rf"^{_RN}(?:Finansal\s+)?Kaldıraç\s+[Oo]ran[ıi]\b",
]]
# Where the §4.6/4.7 section begins — table-specific phrasing (not policy prose).
_START_RX = [re.compile(p, re.IGNORECASE) for p in [
    r"High[\s-]?Quality\s*Liquid\s*Assets",
    r"Yüksek\s+Kaliteli\s+Likit",
    r"leverage\s*ratio\s*table\s*prepared",
]]


@dataclass
class LiquidityRow:
    period_type: str  # 'current' | 'prior'
    leverage_ratio: float | None = None
    lcr_total: float | None = None
    lcr_fc: float | None = None
    nsfr: float | None = None


@dataclass
class LiquidityReport:
    pdf_path: str = ""
    source_page: int | None = None
    rows: list[LiquidityRow] = field(default_factory=list)


def _fitz_lines(pdf_path: str, page_idx: int, ytol: float = 4.0) -> list[str]:
    """Page text reconstructed from fitz words, clustered into lines so a
    right-aligned value offset a few px from its label (TFKB's LCR/NSFR rows)
    still lands on the same line that pdfplumber split apart."""
    if not _HAS_FITZ:
        return []
    import fitz
    try:
        doc = fitz.open(pdf_path)
        words = sorted(doc[page_idx].get_text("words"), key=lambda w: (w[1], w[0]))
        doc.close()
    except Exception:
        return []
    lines: list[list[tuple[float, str]]] = []
    cur: list[tuple[float, str]] = []
    base: float | None = None
    for w in words:
        if base is None or w[1] - base <= ytol:
            cur.append((w[0], w[4]))
            base = w[1] if base is None else base
        else:
            lines.append(cur)
            cur = [(w[0], w[4])]
            base = w[1]
    if cur:
        lines.append(cur)
    return [" ".join(t for _, t in sorted(c)) for c in lines]


def _scan(get_lines, scan_start: int, scan_end: int) -> tuple[list, list, list]:
    """Walk pages [scan_start, scan_end) reading the LCR / NSFR / leverage rows.
    `get_lines(i)` supplies page i's lines (pdfplumber or fitz fallback)."""
    lcr: list[list[str]] = []
    nsfr: list[list[str]] = []
    lev: list[list[str]] = []
    def _add(lst, toks):
        # Skip a row whose current value is nil ("-") — TFKB prints a placeholder
        # "Kaldıraç oranı - -" above the real "15 Kaldıraç oranı 5.53 5.92".
        if toks and not all(c in "-—– " for c in toks[0]):
            lst.append(toks)

    for i in range(scan_start, scan_end):
        for raw in get_lines(i):
            # Turkish-aware lower-casing: TFKB prints the labels in UPPER CASE
            # ("LİKİDİTE KARŞILAMA ORANI (%)"), and Python's IGNORECASE does NOT
            # fold İ→i or I→ı, so the mixed-case patterns miss them.
            ln = _repair_split_digits(raw.strip().translate(_TR_LOWER).lower())
            if not ln:
                continue
            if _match(_LCR_RX, ln):
                _add(lcr, _trailing_two_tokens(ln))
            elif _match(_NSFR_RX, ln):
                _add(nsfr, _trailing_two_tokens(ln))
            elif _match(_LEV_RX, ln):
                _add(lev, _trailing_two_tokens(ln))
        if lcr and nsfr and lev:  # have current values for all three → done
            break
    return lcr, nsfr, lev


def _match(rxs, line: str) -> bool:
    return any(rx.match(line) for rx in rxs)


def extract_from_pdf(pdf: pdfplumber.PDF, pdf_path: str = "") -> LiquidityReport:
    rep = LiquidityReport(pdf_path=pdf_path)
    n = len(pdf.pages)
    # Find where the liquidity section starts so we don't scan the whole report.
    start = None
    for i in range(min(_SKIP_PAGES, n), n):
        if any(rx.search(pdf.pages[i].extract_text() or "") for rx in _START_RX):
            start = i
            break
    # Fallback: AKTIF (and other small banks) disclose the LCR as PROSE — there's
    # no "Yüksek Kaliteli Likit Varlıklar" table header for _START_RX to find —
    # but they still print the leverage / LCR / NSFR data rows. Rather than give
    # up, scan the whole footnote range for the (specific, "(%)"-/number-gated)
    # data-row anchors.
    fallback = start is None
    scan_start = min(_SKIP_PAGES, n) if fallback else start
    scan_end = n if fallback else min(n, start + _MAX_SCAN_FROM_START)
    rep.source_page = None if fallback else start + 1

    lcr, nsfr, lev = _scan(lambda i: (pdf.pages[i].extract_text() or "").splitlines(),
                           scan_start, scan_end)
    # Wide-table fallback: TFKB renders the LCR/NSFR rows so the value is offset
    # from the (right-aligned) label and pdfplumber drops the label onto a
    # value-less line — re-scan off fitz words clustered into lines and FILL only
    # the ratios pdfplumber missed (TFKB interim yields NSFR but not LCR/leverage).
    if not (lcr and nsfr and lev) and pdf_path and _HAS_FITZ:
        flcr, fnsfr, flev = _scan(lambda i: _fitz_lines(pdf_path, i), scan_start, scan_end)
        lcr, nsfr, lev = (lcr or flcr), (nsfr or fnsfr), (lev or flev)
    # Prose fallback (older FIBA): the §4.7 table lists only the leverage exposure
    # components, and the ratio itself is stated in a sentence — "…hesaplamış
    # olduğu konsolide kaldıraç oranı 31 Mart 2022 itibarıyla %6,06…". Anchor on
    # "itibarıyla %…" so the regulatory "%3" minimum ("oranını %3 olarak") is not
    # matched.
    if not lev:
        prose = " ".join(pdf.pages[i].extract_text() or "" for i in range(scan_start, scan_end))
        m = _PROSE_LEV_RX.search(prose)
        if m:
            lev = [[m.group(1)]]

    cur = LiquidityRow(period_type="current")
    pri = LiquidityRow(period_type="prior")
    if lcr:
        cur.lcr_total = _parse_ratio(lcr[0][0])
        cur.lcr_fc = _parse_ratio(lcr[0][1]) if len(lcr[0]) > 1 else None
    if nsfr:
        cur.nsfr = _parse_ratio(nsfr[0][0])
        if len(nsfr) > 1:
            pri.nsfr = _parse_ratio(nsfr[1][0])
    if lev:
        cur.leverage_ratio = _parse_ratio(lev[0][0])
        if len(lev[0]) > 1:
            pri.leverage_ratio = _parse_ratio(lev[0][1])

    if any(v is not None for v in (cur.lcr_total, cur.nsfr, cur.leverage_ratio)):
        rep.rows.append(cur)
    if any(v is not None for v in (pri.lcr_total, pri.nsfr, pri.leverage_ratio)):
        rep.rows.append(pri)
    return rep


def extract(pdf_path: str | Path) -> LiquidityReport:
    pdf_path = str(pdf_path)
    with pdfplumber.open(pdf_path) as pdf:
        return extract_from_pdf(pdf, pdf_path)


# ---------------------------------------------------------------------------
# DB loader
# ---------------------------------------------------------------------------
_VALUE_COLS = ["leverage_ratio", "lcr_total", "lcr_fc", "nsfr"]


def upsert(
    conn: sqlite3.Connection,
    bank_ticker: str,
    period: str,
    kind: str,
    rep: LiquidityReport,
) -> int:
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM bank_audit_liquidity WHERE bank_ticker=? AND period=? AND kind=?",
        (bank_ticker, period, kind),
    )
    cols = ["bank_ticker", "period", "kind", "period_type", *_VALUE_COLS, "source_page"]
    ph = ", ".join("?" for _ in cols)
    rows = [(
        bank_ticker, period, kind, r.period_type,
        *[getattr(r, c) for c in _VALUE_COLS],
        rep.source_page,
    ) for r in rep.rows]
    if rows:
        cur.executemany(
            f"INSERT INTO bank_audit_liquidity ({', '.join(cols)}) VALUES ({ph})", rows
        )
    conn.commit()
    return len(rows)


def summarize(rep: LiquidityReport) -> str:
    if not rep.rows:
        return f"{Path(rep.pdf_path).name}\n  (no liquidity table found)"
    lines = [f"{Path(rep.pdf_path).name}  (page {rep.source_page})"]
    for r in rep.rows:
        lines.append(
            f"  {r.period_type:<7} LCR={r.lcr_total} LCR_FC={r.lcr_fc} "
            f"NSFR={r.nsfr} Leverage={r.leverage_ratio}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    path = sys.argv[1] if len(sys.argv) > 1 else \
        "data/raw/_diag/GARAN_2026Q1_unconsolidated.pdf"
    print(summarize(extract(path)))
