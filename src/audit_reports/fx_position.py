"""FX net-open-position extractor — BRSA §4 "Currency risk" footnote table.

Almost every BRSA audit report (99% of the corpus) carries a currency-risk
table that lays the bank's foreign-currency balance sheet out by currency
column (EUR / USD / Other FC / Total) with summary rows:

    Total assets                       235,557,420  493,993,295   35,873,202  765,423,917
    Total liabilities                  175,490,165  538,632,437  152,553,427  866,676,029
    Net balance sheet position          60,067,255  (44,639,142) (116,680,225) (101,252,112)
    Net off-balance sheet position     (45,014,786)  45,384,156  117,025,604  117,394,974
    Derivative financial instr. assets  65,091,688  246,708,134  141,731,757  453,531,579
    Derivative financial instr. liab.  110,106,474  201,323,978   24,706,153  336,136,605

A "Prior Period" block repeats the summary rows under the same columns. Reports
come in Turkish ("Toplam Varlıklar … Net Bilanço Pozisyonu … EURO USD Diğer YP
Toplam") and English; participation banks word balance lines as profit-sharing
accounts but keep the same summary-row labels.

We do NOT parse every line item — only the labelled summary rows, whose values
sit on one baseline in column order, so we read the trailing value tokens in
left-to-right order and zip them to the currency columns parsed from the header.
The bank's overall FX net open position ("YP net genel pozisyon") is
net_on_balance + net_off_balance.

Amounts in the report's native unit (thousand TRY). Negatives are parenthesised.
Two period blocks emitted: period_type 'current' | 'prior', one row per currency
(EUR/USD/OTHER/TOTAL). Footing identities are checked in validator.py /
check_audit_quality.py.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from .extractor import _HAS_FITZ, parse_num

# fitz-only: the §4 currency-risk table is a single narrow footnote — fitz word
# clustering reads it faithfully and is far cheaper than pdfplumber per page,
# which adds no accuracy here (per the project's per-statement engine strategy).

# A numeric token (TR/EN, parenthesised negatives, leading/trailing %): mirrors
# capital_adequacy._NUM_TOKEN. Nil dashes are kept as 0.0 (parse_num maps them).
_NUM_TOKEN = re.compile(r"^%?\(?-?\d[\d.,]*%?\)?$")
_NIL = {"-", "—", "–", "--", "---"}

# Currency-column header tokens → canonical code. Matched against the FIRST token
# of each header cell ("Other FC(*)" → Other; "Diğer YP" → Diğer; "ABD Doları" →
# ABD; "Avro" → EUR). Turkish reports name them Avro/ABD Doları/Diğer YP.
_CCY_HEAD = [
    ("EUR", re.compile(r"^(EUR(O)?|Avro)$", re.I)),
    # "US" catches TSKB's English "US Dollar" — fitz tokenises the cell to
    # [US, Dollar] and the parser keys on the first token, which is "US", not "USD".
    ("USD", re.compile(r"^(USD|US|ABD)$", re.I)),
    ("GBP", re.compile(r"^GBP$", re.I)),
    # "FC" catches YKBNK-unconsolidated's WRAPPED "Other FC" header: "Other" clusters
    # onto the line above, leaving only "FC(4)" → "FC" on the header baseline. The
    # header gate still requires TOTAL + a hard currency, and _parse_header_columns'
    # `code not in cols` guard dedupes when both "Other" and "FC" appear.
    ("OTHER", re.compile(r"^(Other|Diğer|Diger|FC)$", re.I)),
    ("TOTAL", re.compile(r"^(Total|Toplam)$", re.I)),
]
_HARD_CCY = {"EUR", "USD", "GBP"}

# Summary rows we keep (field, [label regexes], bilingual). Matched on the
# line's leading label (case-insensitive).
_ROWS: list[tuple[str, list[str]]] = [
    ("on_bs_assets", [r"^Total\s+assets\b", r"^Toplam\s+Varlıklar\b", r"^Toplam\s+Aktifler\b"]),
    ("on_bs_liab", [r"^Total\s+liabilities\b", r"^Toplam\s+Yükümlülükler\b"]),
    ("net_on_balance", [r"^Net\s+(?:on[\s-]?)?balance\s+sheet\s+position\b",
                        r"^Net\s+Bilanço\s+(?:İçi\s+)?Pozisyonu?\b"]),
    ("net_off_balance", [r"^Net\s+off[\s-]?balance\s+sheet\s+position\b",
                         r"^Net\s+Nazım\s+Hesap\s+Pozisyonu?\b", r"^Net\s+Nazim\b"]),
    ("off_bs_receivable", [r"^Derivative\s+financial\s+instruments?\s+assets\b",
                           r"^Türev\s+Finansal\s+Araçlardan\s+Alacaklar\b"]),
    ("off_bs_payable", [r"^Derivative\s+financial\s+instruments?\s+liabilities\b",
                        r"^Türev\s+Finansal\s+Araçlardan\s+Borçlar\b"]),
]
_ROW_RX = [(f, [re.compile(p, re.I) for p in pats]) for f, pats in _ROWS]
_FIELDS = [f for f, _ in _ROWS]

_PRIOR_RX = re.compile(r"\b(Prior\s+Period|Önceki\s+Dönem|Geçmiş\s+Dönem)\b", re.I)
# The genuine prior-period BLOCK is introduced by a standalone prior caption. But
# HAYATK and ISCTR (English) print a "Sensitivity to currency risk" sub-table
# ABOVE the position table whose column header carries BOTH periods —
# "Current Period Prior Period Current Period Prior Period" — and _PRIOR_RX.search
# would fire on that, flipping to 'prior' before the real current rows are read
# (so every current row is stored as prior and then overwritten → 0 current rows).
# A line that names the CURRENT period too is a dual-period header, not a block
# marker, so it must NOT trigger the flip.
_CURRENT_RX = re.compile(r"\b(Current\s+Period|Cari\s+Dönem)\b", re.I)
_SECTION_RX = re.compile(r"(currency\s+risk|kur\s+riski(ne)?)", re.I)
# A line is the column header when it carries Total/Toplam plus ≥1 other currency.
_SKIP_PAGES = 20          # clear front matter / statements / capital section
_MAX_SECTION_PAGES = 4


@dataclass
class FxRow:
    period_type: str               # 'current' | 'prior'
    currency: str                  # 'EUR' | 'USD' | 'OTHER' | 'GBP' | 'TOTAL'
    on_bs_assets: float | None = None
    on_bs_liab: float | None = None
    net_on_balance: float | None = None
    net_off_balance: float | None = None
    off_bs_receivable: float | None = None
    off_bs_payable: float | None = None
    net_position: float | None = None   # net_on_balance + net_off_balance


@dataclass
class FxReport:
    pdf_path: str = ""
    source_page: int | None = None
    rows: list[FxRow] = field(default_factory=list)


def _fitz_word_lines(pdf_path: str):
    """Yield (page_index, [(x0, text), ...]) lines rebuilt from fitz words by
    tight y-clustering (≤3px), so a summary row's label and its column figures
    land on one line in x-order. Returns (lines, doc) — caller closes doc."""
    import fitz
    doc = fitz.open(pdf_path)
    pages: list[tuple[int, list[list[tuple[float, str]]]]] = []
    for i in range(len(doc)):
        words = doc[i].get_text("words")
        rows: list[tuple[float, list[tuple[float, str]]]] = []
        for w in sorted(words, key=lambda w: (w[1], w[0])):
            if rows and w[1] - rows[-1][0] <= 3.0:
                rows[-1][1].append((w[0], w[4]))
            else:
                rows.append((w[1], [(w[0], w[4])]))
        pages.append((i, [sorted(toks) for _, toks in rows]))
    return pages, doc


def _parse_header_columns(tokens: list[tuple[float, str]]) -> list[str] | None:
    """From a header line's (x, text) tokens, return the currency codes in
    left-to-right order if it looks like the currency-column header (has Total
    /Toplam and ≥1 other currency). Else None."""
    cols: list[str] = []
    for _, raw in tokens:
        # Strip a trailing footnote marker glued to the header cell
        # ("Diğer(4)" → "Diğer", "FC(*)" → "FC").
        t = re.sub(r"\(.*\)$", "", raw)
        for code, rx in _CCY_HEAD:
            if rx.match(t):
                if code not in cols:
                    cols.append(code)
                break
    # A genuine currency header carries Total/Toplam AND ≥1 hard currency, so we
    # don't false-match the credit-risk RWA or maturity tables (which also have a
    # Total column but no EUR/USD).
    if "TOTAL" in cols and any(c in _HARD_CCY for c in cols):
        return cols
    return None


def _value_tokens(tokens: list[tuple[float, str]]) -> list[str]:
    """Numeric/nil tokens on a line, in x-order."""
    return [t for _, t in tokens if t in _NIL or _NUM_TOKEN.match(t)]


def _label(tokens: list[tuple[float, str]]) -> str:
    return " ".join(t for _, t in tokens).strip()


def extract_from_pdf(pdf: object = None, pdf_path: str = "") -> FxReport:
    # `pdf` (a pdfplumber handle) is accepted for signature parity with the audit
    # lane but unused — parsing is fitz-only via pdf_path.
    rep = FxReport(pdf_path=pdf_path)
    if not pdf_path or not _HAS_FITZ:
        return rep
    _assets_rx = _ROW_RX[0][1]  # on_bs_assets label patterns
    pages, doc = _fitz_word_lines(pdf_path)
    try:
        n = len(pages)
        # Locate the currency-risk TABLE: the first page (past front matter) that
        # carries a currency-column header AND a Total-assets row — robust to the
        # banks that wrap or reword the net-position label.
        start = None
        for i in range(min(_SKIP_PAGES, n), n):
            lns = pages[i][1]
            has_header = any(_parse_header_columns(t) for t in lns)
            has_assets = any(any(rx.match(_label(t)) for rx in _assets_rx) for t in lns)
            if has_header and has_assets:
                start = i
                break
        if start is None:
            return rep
        rep.source_page = start + 1

        cols: list[str] | None = None
        # (period_type, currency) -> {field: value}
        data: dict[tuple[str, str], dict[str, float | None]] = {}
        period = "current"
        for i in range(start, min(n, start + _MAX_SECTION_PAGES)):
            for tokens in pages[i][1]:
                lab = _label(tokens)
                if not lab:
                    continue
                hc = _parse_header_columns(tokens)
                if hc:
                    cols = hc          # re-read header each block (column set is stable)
                if _PRIOR_RX.search(lab) and not _CURRENT_RX.search(lab):
                    period = "prior"
                if cols is None:
                    continue
                for fld, rxs in _ROW_RX:
                    if not any(rx.match(lab) for rx in rxs):
                        continue
                    # A second Total-assets block with no explicit "Prior Period"
                    # marker (BURGAN) is the prior-period comparative.
                    if fld == "on_bs_assets" and period == "current" \
                            and ("current", "TOTAL") in data \
                            and data[("current", "TOTAL")].get("on_bs_assets") is not None:
                        period = "prior"
                    vals = _value_tokens(tokens)
                    if len(vals) != len(cols):
                        break  # column mismatch — skip (footing validator will flag)
                    for code, tok in zip(cols, vals):
                        data.setdefault((period, code), {})[fld] = parse_num(tok)
                    break
    finally:
        doc.close()

    for (ptype, ccy), fields in data.items():
        row = FxRow(period_type=ptype, currency=ccy, **fields)
        non = row.net_on_balance
        noff = row.net_off_balance
        if non is not None or noff is not None:
            row.net_position = (non or 0.0) + (noff or 0.0)
        rep.rows.append(row)
    # Deterministic order: current before prior, TOTAL last.
    _ccy_ord = {"EUR": 0, "USD": 1, "GBP": 2, "OTHER": 3, "TOTAL": 9}
    rep.rows.sort(key=lambda r: (r.period_type != "current", _ccy_ord.get(r.currency, 5)))
    return rep


def extract(pdf_path: str | Path) -> FxReport:
    return extract_from_pdf(None, str(pdf_path))


# ---------------------------------------------------------------------------
# DB loader
# ---------------------------------------------------------------------------
_VALUE_COLS = [
    "on_bs_assets", "on_bs_liab", "net_on_balance", "net_off_balance",
    "off_bs_receivable", "off_bs_payable", "net_position",
]


def upsert(conn: sqlite3.Connection, bank_ticker: str, period: str, kind: str,
           rep: FxReport) -> int:
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM bank_audit_fx_position WHERE bank_ticker=? AND period=? AND kind=?",
        (bank_ticker, period, kind),
    )
    cols = ["bank_ticker", "period", "kind", "period_type", "currency",
            *_VALUE_COLS, "source_page"]
    ph = ", ".join("?" for _ in cols)
    rows = [(
        bank_ticker, period, kind, r.period_type, r.currency,
        *[getattr(r, c) for c in _VALUE_COLS], rep.source_page,
    ) for r in rep.rows]
    if rows:
        cur.executemany(
            f"INSERT INTO bank_audit_fx_position ({', '.join(cols)}) VALUES ({ph})", rows
        )
    conn.commit()
    return len(rows)


def summarize(rep: FxReport) -> str:
    if not rep.rows:
        return f"{Path(rep.pdf_path).name}\n  (no currency-risk table found)"
    lines = [f"{Path(rep.pdf_path).name}  (page {rep.source_page})"]
    for r in rep.rows:
        def f(v):
            return f"{v:,.0f}" if v is not None else "-"
        lines.append(
            f"  {r.period_type:<7} {r.currency:<6} A={f(r.on_bs_assets):>16} "
            f"L={f(r.on_bs_liab):>16} netBS={f(r.net_on_balance):>15} "
            f"netOff={f(r.net_off_balance):>15} NOP={f(r.net_position):>15}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    path = sys.argv[1] if len(sys.argv) > 1 else \
        "data/eye/AKBNK_2024Q4_unconsolidated.pdf"
    print(summarize(extract(path)))
