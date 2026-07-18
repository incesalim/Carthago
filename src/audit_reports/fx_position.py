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
# A bare footnote reference marker "(n)" (1-2 digits) — distinct from a real
# parenthesised negative, which carries thousands separators / ≥3 digits.
_FOOTNOTE_RX = re.compile(r"^\(\d{1,2}\)$")
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
# A straight or curly quote (GARAN glues U+2018/U+2019 to "'On Balance Sheet'"),
# optional, so the net-position labels match with or without them.
_Q = r"[‘’‛'\"]?"
_ROWS: list[tuple[str, list[str]]] = [
    # `assets\d` catches HAYATK's footnote-glued "Total Assets2" ("Assets2" is one
    # word, so \b never fires between the word and the digit).
    ("on_bs_assets", [r"^Total\s+assets\b", r"^Total\s+assets\d\b",
                      r"^Toplam\s+Varlıklar\b", r"^Toplam\s+Aktifler\b"]),
    ("on_bs_liab", [r"^Total\s+liabilities\b", r"^Total\s+liabilities\d\b",
                    r"^Toplam\s+Yükümlülükler\b"]),
    ("net_on_balance", [r"^Net\s+(?:on[\s-]?)?balance\s+sheet\s+position\b",
                        rf"^Net\s*{_Q}\s*On\s+Balance\s+Sheet{_Q}\s+Position\b",
                        r"^Net\s+Bilanço\s+(?:İçi\s+)?Pozisyonu?\b"]),
    # `[\s‐-―\-]*` between "off" and "balance" tolerates ANY dash the
    # source glues in: TSKB's prior block prints "Net Off –Balance" (space + en-dash
    # U+2013) where the current block prints "Off-Balance" (ASCII hyphen), so the old
    # single-optional `[\s-]?` matched current but silently dropped the prior net-off
    # row. "Net bilanço dışı pozisyon" is KUVEYT's prior-block wording for the same
    # line (its current block says "Net nazım hesap pozisyonu") — a different Turkish
    # phrase for the off-balance position, distinct from the on-balance
    # "Net bilanço pozisyonu" (which carries no "dışı").
    ("net_off_balance", [r"^Net\s+off[\s‐-―\-]*balance\s+sheet\s+position\b",
                         rf"^Net\s*{_Q}\s*Off[\s‐-―\-]*Balance\s+Sheet{_Q}\s+Position\b",
                         r"^Net\s+Nazım\s+Hesap\s+Pozisyonu?\b", r"^Net\s+Nazim\b",
                         r"^Net\s+Bilanço\s+Dışı\s+Pozisyon"]),
    # GARAN prints "Derivative Assets", HAYATK "Financial derivative assets" — both
    # distinct from the existing "Derivative financial instruments assets".
    ("off_bs_receivable", [r"^Derivative\s+financial\s+instruments?\s+assets\b",
                           r"^Derivative\s+assets\b", r"^Financial\s+derivative\s+assets\b",
                           r"^Türev\s+Finansal\s+Araçlardan\s+Alacaklar\b"]),
    ("off_bs_payable", [r"^Derivative\s+financial\s+instruments?\s+liabilities\b",
                        r"^Derivative\s+liabilities\b", r"^Financial\s+derivative\s+liabilities\b",
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


def _row_values(tokens: list[tuple[float, str]], ncols: int) -> list[str] | None:
    """The line's value tokens normalized to exactly `ncols`, else None.

    A bare footnote marker "(2)" between the label and the figures is picked up by
    _NUM_TOKEN (parenthesised digits look like a negative), inflating the count by
    one — ZIRAAT/DENIZ/TEB space it off as its own token. Strip such markers ONLY
    when doing so lands the count exactly on ncols; real values (thousands
    separators, ≥3 digits) never match, and the repricing 7-column rows stay at
    7≠4 and remain correctly rejected."""
    vals = _value_tokens(tokens)
    if len(vals) > ncols:
        stripped = [x for x in vals if not _FOOTNOTE_RX.match(x)]
        if len(stripped) == ncols:
            vals = stripped
    return vals if len(vals) == ncols else None


def _label(tokens: list[tuple[float, str]]) -> str:
    return " ".join(t for _, t in tokens).strip()


_CCY_NONTOTAL = ("EUR", "USD", "GBP", "OTHER")


def _foots(entries: dict[str, dict[str, float | None]]) -> bool:
    """True iff a period's assembled rows satisfy the table's own identities:
    net_on == assets − liab (per column AND for TOTAL) and Σ(currencies) == TOTAL
    for assets / liab / net_on. Used to accept-or-reject a candidate row→field
    assignment: the shift-repair below only REPLACES the standard assignment when
    the standard one fails this and the positional one passes it, so a correctly
    parsed block is never touched and a coincidental wrong mapping can't slip
    through (the identity web is far too tight to satisfy by accident)."""
    t = entries.get("TOTAL")
    if not t:
        return False
    a, l, non = t.get("on_bs_assets"), t.get("on_bs_liab"), t.get("net_on_balance")
    if a is None or l is None or non is None or abs(non - (a - l)) >= 1.0:
        return False
    for f in entries.values():
        aa, ll, nn = f.get("on_bs_assets"), f.get("on_bs_liab"), f.get("net_on_balance")
        if None not in (aa, ll, nn) and abs(nn - (aa - ll)) >= 1.0:
            return False
    for fld in ("on_bs_assets", "on_bs_liab", "net_on_balance"):
        parts = [entries[c][fld] for c in _CCY_NONTOTAL
                 if c in entries and entries[c].get(fld) is not None]
        if parts and t.get(fld) is not None and abs(sum(parts) - t[fld]) >= 1.0:
            return False
    return True


def _positional(vrows: list[list[float | None]], cols: list[str],
                offset: int) -> dict[str, dict[str, float | None]]:
    """Map the figure rows (from `offset`) onto the canonical field order,
    column by column. `offset` skips a stray leading figure row that a shifted
    layout can strand on the "Prior Period" caption (the current block's last
    line printed one row low)."""
    pos: dict[str, dict[str, float | None]] = {}
    for k, fld in enumerate(_FIELDS):
        if offset + k < len(vrows):
            for code, val in zip(cols, vrows[offset + k]):
                pos.setdefault(code, {})[fld] = val
    return pos


def _net_off_corroborated(entries: dict[str, dict[str, float | None]]) -> bool:
    """TOTAL net_off equals the derivative legs netted (either sign convention:
    payables are parenthesised-negative for some banks, positive for others).
    Guards the net_off back-fill so a derivative-less table's non-cash-loans row
    can never be mistaken for the (absent) net-off row."""
    t = entries.get("TOTAL", {})
    no, dr, dp = (t.get("net_off_balance"), t.get("off_bs_receivable"),
                  t.get("off_bs_payable"))
    if no is None or dr is None or dp is None:
        return False
    return abs(no - (dr - dp)) < 1.0 or abs(no - (dr + dp)) < 1.0


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
        # Prior-block figure rows in printed order, collected INDEPENDENTLY of the
        # labels (see the shift-repair note after the loop).
        prior_vrows: list[list[float | None]] = []
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
                # Collect the prior block's full figure rows by VALUE, not by label,
                # so a source that vertically offsets its value column from its label
                # column (see the shift-repair note below) is still captured in the
                # right printed order. Stop at the footnotes (a "(n)" line-leader) and
                # once we have the six summary rows we care about.
                if period == "prior" and len(prior_vrows) < len(_FIELDS) \
                        and not _FOOTNOTE_RX.match(tokens[0][1]):
                    pv = _row_values(tokens, len(cols))
                    if pv is not None:
                        prior_vrows.append([parse_num(t) for t in pv])
                for fld, rxs in _ROW_RX:
                    if not any(rx.match(lab) for rx in rxs):
                        continue
                    # A second Total-assets block with no explicit "Prior Period"
                    # marker (BURGAN) is the prior-period comparative.
                    if fld == "on_bs_assets" and period == "current" \
                            and ("current", "TOTAL") in data \
                            and data[("current", "TOTAL")].get("on_bs_assets") is not None:
                        period = "prior"
                    vals = _row_values(tokens, len(cols))
                    if vals is None:
                        break  # column mismatch — skip (footing validator will flag)
                    for code, tok in zip(cols, vals):
                        data.setdefault((period, code), {})[fld] = parse_num(tok)
                    break
    finally:
        doc.close()

    # --- Shift-repair (prior column) --------------------------------------------
    # A handful of filings (ISCTR consolidated, QNBFB) print the prior block's VALUE
    # column vertically offset from its LABEL column, so the y-clustering glues each
    # figure row to the wrong label: "Total Assets" reads blank and every value lands
    # one field too high (liab←assets, net_on←liab, …); sometimes the current block's
    # last line is stranded on the "Prior Period" caption, pushing everything down one
    # more. The labels are fine and the figures are fine — only their pairing is. So
    # re-pair by taking the prior figure rows in printed order and mapping them
    # positionally onto the canonical field order, trying a small leading offset to
    # absorb a stranded caption row. Every candidate is accepted ONLY if it satisfies
    # the table's own identities (_foots), and the label-based parse is replaced only
    # when it does NOT foot and a positional one DOES — so correctly-parsed blocks
    # (the overwhelming majority) are never disturbed and a coincidental wrong mapping
    # cannot pass the identity web.
    prior = {ccy: f for (pt, ccy), f in data.items() if pt == "prior"}
    best = None
    for off in range(3):
        cand = _positional(prior_vrows, cols, off)
        if _foots(cand):
            best = cand
            break
    if best is not None:
        std_ok = _foots(prior)
        if not std_ok:
            # Label-based parse is broken (a genuine shift) — take the positional one.
            for key in [k for k in data if k[0] == "prior"]:
                del data[key]
            for ccy, fields in best.items():
                data[("prior", ccy)] = fields
        elif prior.get("TOTAL", {}).get("net_off_balance") is None \
                and best.get("TOTAL", {}).get("net_off_balance") is not None \
                and all(best.get(c, {}).get(f) == prior.get(c, {}).get(f)
                        for c in ("TOTAL",) for f in ("on_bs_assets", "on_bs_liab",
                                                      "net_on_balance")) \
                and _net_off_corroborated(best):
            # Label-based parse is right on the on-balance rows but dropped the net-off
            # row (QNBFB 2025Q3 prints its net-off figures 4px above the label, just
            # past the clustering threshold, orphaning them). The figures survive in
            # the positional map; fill net_off (and the derivative legs) from it, but
            # only once the derivative-leg identity corroborates that row really is the
            # net-off — a derivative-less table can never mis-fill from a non-cash row.
            for ccy, fields in best.items():
                data.setdefault(("prior", ccy), {}).update(fields)

    for (ptype, ccy), fields in data.items():
        # Derive a missing PRIOR net-on-balance from its own identity when the source
        # leaves that cell blank but prints assets and liabilities (QNBFB 2025Q2
        # prints only two of four net-balance columns, so the row is dropped for a
        # column-count mismatch). assets − liab is the figure the table itself would
        # print; we only ever FILL a gap, never overwrite a value that was read.
        # PRIOR only: a blank current net-balance is the sign of a shifted CURRENT
        # block (which we don't repair), and deriving it there would silently mask
        # that break — better to let the completeness validator fail loudly.
        if ptype == "prior" and fields.get("net_on_balance") is None \
                and fields.get("on_bs_assets") is not None \
                and fields.get("on_bs_liab") is not None:
            fields["net_on_balance"] = fields["on_bs_assets"] - fields["on_bs_liab"]
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
