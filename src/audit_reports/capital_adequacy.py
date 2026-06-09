"""Capital-adequacy extractor — BRSA §4.1 "Total capital" table.

Every BRSA audit report carries a capital-adequacy disclosure with two numeric
columns (Current Period | Prior Period) and clearly-labelled total rows:

    Total Common Equity Tier I Capital ............ 444,145,526  439,429,164
    Total Tier I Capital .......................... 444,145,526  439,429,164
    Total Tier II Capital ......................... 147,663,444  138,736,242
    Total Capital ( Total of Tier I and Tier II ).. 591,806,874  578,162,530
    Total Risk Weighted Assets .................... 3,154,771,905 2,645,600,330
    CET1 Capital Ratio (%) ........................ 14.08  16.61
    Tier I Capital Ratio (%) ...................... 14.08  16.61
    Capital Adequacy Ratio (%) .................... 18.76  21.85

This is the same deterministic approach as loans_by_sector.py / npl_movement.py:
locate the section by heading anchors, then pull each metric's value off its
labelled row. Amounts are kept in the report's native unit (thousand TRY);
ratios are stored as percentages (18.76 = 18.76%). Two rows are emitted per
report: period_type 'current' and 'prior'.

Arithmetic sanity (CET1<=Tier1<=Total, CAR≈capital/RWA) is checked downstream in
scripts/check_audit_quality.py, consistent with the other audit tables.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

from .extractor import parse_num


# ---------------------------------------------------------------------------
# Metric label registry. Ordered so the first matching field wins on a line.
# Each entry: (field, is_ratio, [regex variants]). Regexes are matched
# case-insensitively against the line's leading label. Turkish variants cover
# Turkish-language reports (the English ones are convenience translations).
# ---------------------------------------------------------------------------
# Banks label these rows in English ("Tier I" roman OR "Tier 1" digit) or in
# Turkish, and mix number formats (TR: 1.234.567 / 16,79 ; EN: 1,234,567 / 16.79).
# `_TI` / `_TII` absorb the roman-vs-digit variation everywhere.
_TI = r"Tier\s*(?:I|1)"
_TII = r"Tier\s*(?:II|2)"
_KON = r"(?:Konsolide\s+)?"      # TR consolidated-report label prefix (VAKIFK)
_CONS = r"(?:Consolidated\s+)?"  # EN equivalent
_FIELDS: list[tuple[str, bool, list[str]]] = [
    ("cet1_capital", False, [
        rf"^Total\s+Common\s+Equity\s+{_TI}\s+Capital\b",
        rf"^Common\s+Equity\s+{_TI}\s+[Cc]apital\s*\(\s*CET\s*1\s*\)",
        r"^Çekirdek\s+Sermaye\s+Toplamı\b",
    ]),
    ("additional_tier1_capital", False, [
        rf"^Total\s+Additional\s+(?:{_TI}|Core)\s+[Cc]apital\b",
        r"^İlave\s+Ana\s+Sermaye\s+Toplamı\b",
    ]),
    ("tier1_capital", False, [
        rf"^Total\s+{_TI}\s+[Cc]apital\b(?!\s*(?:Ratio|Adequacy))",
        r"^Ana\s+Sermaye\s+Toplamı\b",
    ]),
    ("tier2_capital", False, [
        rf"^Total\s+{_TII}\s+[Cc]apital\b",
        r"^Katkı\s+Sermaye\s+Toplamı\b",
    ]),
    ("total_capital", False, [
        r"^Total\s+Capital\b",
        r"^Total\s+Own\s+Funds\b",
        r"^Toplam\s+Özkaynak\b",
        # EXIM words the current-period total differently from the prior table:
        # "Total Equity (Total Tier I and Tier II Capital)" /
        # "The sum of Tier I Capital and Tier II Capital (Total Capital)".
        rf"^Total\s+Equity\s*\(\s*Total\s+(?:of\s+)?{_TI}\s+and\s+{_TII}",
        rf"^The\s+sum\s+of\s+{_TI}\s+Capital\s+and\s+{_TII}\s+Capital",
    ]),
    ("total_rwa", False, [
        r"^Total\s*Risk[\s-]?Weighted\s*(?:Assets|Amount|Items)",
        r"^Toplam\s+Risk\s+Ağırlıklı\s+(?:Tutar|Varlık)",
    ]),
    # Ratio labels use \s* between words: pdfplumber sometimes drops the space
    # between words in these rows (EXIM: "Capital AdequacyRatio (%)").
    # Consolidated reports may prefix the labels (VAKIFK: "Konsolide Sermaye
    # Yeterliliği Oranı") — _KON/_CONS absorb that.
    ("cet1_ratio", True, [
        rf"^{_CONS}CET\s*1\s*Capital\s*(?:Adequacy\s*)?Ratio",
        rf"^{_CONS}Common\s*Equity\s*{_TI}\s*Capital\s*(?:Adequacy\s*)?Ratio",
        rf"^{_CONS}Core\s*Capital\s*(?:Adequacy\s*)?Ratio",
        rf"^{_KON}Çekirdek\s+Sermaye\s+Yeterlili[ğg]i\s+Oranı",
    ]),
    ("tier1_ratio", True, [
        rf"^{_CONS}{_TI}\s*Capital\s*(?:Adequacy\s*)?Ratio",
        rf"^{_KON}Ana\s+Sermaye\s+Yeterlili[ğg]i\s+Oranı",
    ]),
    ("capital_adequacy_ratio", True, [
        rf"^{_CONS}Capital\s*Adequacy\s*(?:Standard\s*)?Ratio",
        rf"^{_KON}Sermaye\s+Yeterlili[ğg]i\s+(?:Standart\s+)?Oranı",
    ]),
]
_FIELD_RX = [(f, is_ratio, [re.compile(p, re.IGNORECASE) for p in pats])
             for f, is_ratio, pats in _FIELDS]

# Section anchors (where the §4.1 capital table starts / ends). The start is the
# "before deductions" CET1 line, which sits at the top of the components table.
_START_RX = [re.compile(p, re.IGNORECASE) for p in [
    rf"Common\s+Equity\s+{_TI}\s+[Cc]apital\s+[Bb]efore",
    r"İndirimler\s+Öncesi\s+Çekirdek\s+Sermaye",
    r"Components\s+of\s+(?:the\s+)?total\s+capital",
]]
_END_RX = [re.compile(p, re.IGNORECASE) for p in [
    r"Capital\s+Adequacy\s+(?:Standard\s+)?Ratio\s*\(\s*%",
    r"^Sermaye\s+Yeterlili[ğg]i\s+(?:Standart\s+)?Oranı",
]]
_SKIP_PAGES = 12          # clear cover / auditor / TOC / statements front matter
_MAX_SECTION_PAGES = 8    # how far past the start we keep scanning


# A numeric token: 1,234.56 / 1.234,56 / (1,208) / 14.08 / 16,79 / 11,71% / %5.50 / - (nil)
# Allows a leading OR trailing '%' (Turkish reports often write "%5.50").
_NUM_TOKEN = re.compile(r"^%?\(?-?\d[\d.,]*%?\)?$")
_NIL = {"-", "—", "–"}
# Superscript footnote markers rendered inline, e.g. ATBANK's
# "Sermaye Yeterliliği Oranı (%) (2) 17.77" — "(2)" is a note reference, not a
# value. A real negative amount always carries separators/decimals.
_FOOTNOTE = re.compile(r"^\(\d\)$")
# Capital ratios are percentages well under 100; anything outside the band is a
# parse artefact (e.g. the year "2021." off a wrapped narrative sentence).
_RATIO_BAND = (0.0, 100.0)

# TFKB-class text damage: the PDF text layer detaches the leading digit of
# every number ("Toplam Özkaynak 1 1,372,338 1 0,094,760" = 11,372,338 and
# 10,094,760; "Oranı (%) 2 0.20 1 7.85" = 20.20 and 17.85). Rejoin a lone digit
# to the numeric/decimal fragment that follows. Values on the rows we read are
# never genuine bare single digits, so the join is unambiguous in practice.
_SPLIT_SEP = re.compile(r"(\d)\s+([.,]\d)")               # "7 ,348,196" / "2 .500"
_SPLIT_DIGIT = re.compile(r"\b(\d)\s+(?=\d[\d.,]*(?:\s|$))")  # "2 0.20" / "1 1,372,338"


def _repair_split_digits(line: str) -> str:
    line = _SPLIT_SEP.sub(r"\1\2", line)
    return _SPLIT_DIGIT.sub(r"\1", line)


def _parse_ratio(tok: str) -> float | None:
    """Parse a percentage token, tolerant of TR (16,79) and EN (16.79) decimals.
    Ratios are small (<~100), so a lone comma is always the decimal separator."""
    t = tok.strip().strip("%").strip("()").strip()
    if t in _NIL or not t:
        return None
    if "," in t and "." not in t:
        t = t.replace(",", ".")            # 16,79 -> 16.79
    elif "," in t and "." in t:
        t = t.replace(",", "")             # 1,016.79 -> 1016.79 (EN thousands)
    try:
        return float(t)
    except ValueError:
        return None


@dataclass
class CapitalRow:
    period_type: str  # 'current' | 'prior'
    cet1_capital: float | None = None
    additional_tier1_capital: float | None = None
    tier1_capital: float | None = None
    tier2_capital: float | None = None
    total_capital: float | None = None
    total_rwa: float | None = None
    cet1_ratio: float | None = None
    tier1_ratio: float | None = None
    capital_adequacy_ratio: float | None = None


@dataclass
class CapitalReport:
    pdf_path: str = ""
    source_page: int | None = None
    rows: list[CapitalRow] = field(default_factory=list)


def _trailing_two_tokens(line: str) -> list[str]:
    """Return the last two numeric tokens on a line, left-to-right [current,
    prior]. Walks right-to-left and stops at the first non-numeric token, so
    digits embedded in labels (the '1' in 'CET1') are ignored."""
    collected: list[str] = []
    for tok in reversed(line.split()):
        if _FOOTNOTE.match(tok):
            continue
        if tok in _NIL or _NUM_TOKEN.match(tok):
            collected.append(tok)
            if len(collected) == 2:
                break
        else:
            break
    collected.reverse()
    return collected


def extract_from_pdf(pdf: pdfplumber.PDF, pdf_path: str = "") -> CapitalReport:
    rep = CapitalReport(pdf_path=pdf_path)
    n = len(pdf.pages)
    # Locate the section start.
    start = None
    for i in range(min(_SKIP_PAGES, n), n):
        if any(rx.search(pdf.pages[i].extract_text() or "") for rx in _START_RX):
            start = i
            break
    if start is None:
        return rep
    rep.source_page = start + 1

    current: dict[str, float | None] = {}
    prior: dict[str, float | None] = {}
    # `total_capital` can appear twice (an intermediate "sum of Tier I+II" line
    # plus the final own-funds line before RWA, e.g. QNBFB). Collect all and pick
    # the largest — the regulatory total capital is the final, largest figure.
    tc_candidates: list[tuple[float, float | None]] = []
    end_seen = False
    for i in range(start, min(n, start + _MAX_SECTION_PAGES)):
        text = pdf.pages[i].extract_text() or ""
        for raw in text.splitlines():
            ln = _repair_split_digits(raw.strip())
            if not ln:
                continue
            for fld, is_ratio, rxs in _FIELD_RX:
                if fld != "total_capital" and fld in current:
                    continue  # first occurrence wins (except total_capital)
                if any(rx.match(ln) for rx in rxs):
                    toks = _trailing_two_tokens(ln)
                    if not toks:
                        continue
                    parse = _parse_ratio if is_ratio else parse_num
                    cur = parse(toks[0])
                    if cur is None:
                        continue
                    if is_ratio and not (_RATIO_BAND[0] < cur < _RATIO_BAND[1]):
                        continue  # year/footnote artefact; let a real row match later
                    pri = parse(toks[1]) if len(toks) > 1 else None
                    if (is_ratio and pri is not None
                            and not (_RATIO_BAND[0] < pri < _RATIO_BAND[1])):
                        pri = None
                    if fld == "total_capital":
                        tc_candidates.append((cur, pri))
                    else:
                        current[fld] = cur
                        prior[fld] = pri
                    break
            if any(rx.search(ln) for rx in _END_RX):
                end_seen = True
        if end_seen:
            break

    if tc_candidates:
        best_cur, best_pri = max(tc_candidates, key=lambda t: t[0])
        current["total_capital"] = best_cur
        prior["total_capital"] = best_pri

    # SKBNK-class row shift: the labelled Tier1 row can carry a neighbouring
    # row's value (usually the AT1 amount). Tier1 = CET1 + AT1 by definition,
    # so a Tier1 below CET1 is always a misread — rebuild from the identity,
    # picking the candidate that best matches the reported Tier1 ratio × RWA
    # when both are available (SKBNK 2022Q4: misread 16,233 IS the AT1 →
    # 4,502,933; 2025Q4: misread 8,585,373 IS the AT1 → 21,144,203).
    for vals in (current, prior):
        cet1, t1 = vals.get("cet1_capital"), vals.get("tier1_capital")
        if cet1 is None or t1 is None or t1 >= cet1:
            continue
        cands = [cet1 + (vals.get("additional_tier1_capital") or 0), cet1 + t1]
        ratio, rwa = vals.get("tier1_ratio"), vals.get("total_rwa")
        if ratio and rwa:
            target = ratio * rwa / 100.0
            vals["tier1_capital"] = min(cands, key=lambda c: abs(c - target))
        else:
            vals["tier1_capital"] = cands[0]

    if current:
        rep.rows.append(CapitalRow(period_type="current", **current))
    if any(v is not None for v in prior.values()):
        rep.rows.append(CapitalRow(period_type="prior", **prior))
    return rep


def extract(pdf_path: str | Path) -> CapitalReport:
    pdf_path = str(pdf_path)
    with pdfplumber.open(pdf_path) as pdf:
        return extract_from_pdf(pdf, pdf_path)


# ---------------------------------------------------------------------------
# DB loader
# ---------------------------------------------------------------------------
_VALUE_COLS = [
    "cet1_capital", "additional_tier1_capital", "tier1_capital", "tier2_capital",
    "total_capital", "total_rwa", "cet1_ratio", "tier1_ratio", "capital_adequacy_ratio",
]


def upsert(
    conn: sqlite3.Connection,
    bank_ticker: str,
    period: str,
    kind: str,
    rep: CapitalReport,
) -> int:
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM bank_audit_capital WHERE bank_ticker=? AND period=? AND kind=?",
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
            f"INSERT INTO bank_audit_capital ({', '.join(cols)}) VALUES ({ph})", rows
        )
    conn.commit()
    return len(rows)


def summarize(rep: CapitalReport) -> str:
    if not rep.rows:
        return f"{Path(rep.pdf_path).name}\n  (no capital table found)"
    lines = [f"{Path(rep.pdf_path).name}  (page {rep.source_page})"]
    for r in rep.rows:
        def f(v):
            return f"{v:,.0f}" if v is not None and abs(v) >= 1000 else (
                f"{v}" if v is not None else "-")
        lines.append(
            f"  {r.period_type:<7} CET1={f(r.cet1_capital):>16} T1={f(r.tier1_capital):>16} "
            f"T2={f(r.tier2_capital):>16} TC={f(r.total_capital):>16} RWA={f(r.total_rwa):>18} "
            f"| CET1%={r.cet1_ratio} T1%={r.tier1_ratio} CAR%={r.capital_adequacy_ratio}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    path = sys.argv[1] if len(sys.argv) > 1 else \
        "data/raw/_diag/GARAN_2026Q1_unconsolidated.pdf"
    print(summarize(extract(path)))
