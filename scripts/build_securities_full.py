#!/usr/bin/env python
"""The securities graduation: the fourth NOTES-section family minted from the
document layer — BRSA's securities breakdown by instrument and listing (debt
securities / investment funds / share certificates, each quoted and unquoted;
impairment; total) x (current, prior), 381 captured tables across 18 banks.

The template prints once per measurement portfolio — fair value through
profit or loss, through other comprehensive income, amortised cost — so each
instance carries a `portfolio` context read off its block heading (and the
raw heading, for the ones the regexes cannot place).

Rows carry (group_role, item_role) because "quoted on a stock exchange"
repeats under every group. The mint gate is the template's arithmetic: each
group = quoted + unquoted where both print, and total = Σ groups -
impairment, checked on the current column. No narrow lane holds any of this.

`--write` stores into bank_audit_securities_full in data/bank_audit_tables.db
(local only; never the audit snapshot, not D1).
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.audit_reports import band_matrix as BM  # noqa: E402
from src.audit_reports import units as U  # noqa: E402
from src.audit_reports.numbered_template import absorb_inline, fold, num  # noqa: E402

TABLES_DB = REPO / "data" / "bank_audit_tables.db"

GROUPS: list[tuple[str, re.Pattern]] = [
    # not the capital note's "Debt instruments subject to / to be included in..."
    ("debt_securities", re.compile(r"^BORCLANMA SENETLERI|^DEBT SECURITIES|^DEBT INSTRUMENTS?( \(|$)")),
    ("investment_funds", re.compile(r"^YATIRIM FON|^INVESTMENT FUND|^MUTUAL FUND")),
    ("share_certificates", re.compile(r"^HISSE SENETLERI|^SHARE CERTIFICATES|^COMMON SHARES|"
                                      r"^EQUITY (SECURITIES|SHARES|INSTRUMENTS)|^SHARES$")),
    ("other", re.compile(r"^DIGER( \(|$)|^OTHER( \(|$)")),        # ISCTR / TSKB: an "Other" that enters the total
]
ITEMS: list[tuple[str, re.Pattern]] = [
    ("quoted", re.compile(r"^BORSADA ISLEM GOREN|^QUOTED|^LISTED")),
    ("unquoted", re.compile(r"^BORSADA ISLEM GORMEYEN|^UNQUOTED|^UNLISTED|^NOT.?(QUOTED|LISTED)")),
]
_IMPAIR = re.compile(r"^DEGER AZALMA|^DEGER AZALIS|^DEGER DUSUS|^IMPAIRMENT|^PROVISION FOR IMPAIRMENT|"
                     r"^EXPECTED (CREDIT )?LOSS|^BEKLENEN (KREDI )?ZARAR|^DEGER ARTIS|^VALUE INCREASE|"
                     r"^VALUATION (INCREASE|DIFFERENCE)|^DEGERLEME (ARTIS|FARK)|"
                     r"^ACCRUAL|^REESKONT|^TAHAKKUK|^FAIZ (VE GELIR )?REESKONT")      # SKBNK's accruals, as printed
# GARAN prints a signed "Value Increase/Impairment Loss" that ADDS; HAYATK
# prints its impairment already negative. The sign convention is read off the
# label and the value: a "(-)" deduction label with a positive figure is
# subtracted, anything else is applied as printed.
_DEDUCTION_LABEL = re.compile(r"\(-\)|AZALMA|DUSUS|IMPAIRMENT|PROVISION")
_VALUATION_LABEL = re.compile(r"DEGER ARTIS|VALUE INCREASE|VALUATION (INCREASE|DIFFERENCE)|DEGERLEME (ARTIS|FARK)|"
                              r"ACCRUAL|REESKONT|TAHAKKUK")
_TOTAL = re.compile(r"^TOPLAM|^TOTAL")
VALUES = ("current", "prior")
_PORTFOLIO = [
    ("fvtpl", re.compile(r"KAR.?ZARARA YANSITILAN|THROUGH PROFIT|TRADING|ALIM SATIM")),
    ("fvoci", re.compile(r"DIGER KAPSAMLI|OTHER COMPREHENSIVE|AVAILABLE.?FOR.?SALE|SATILMAYA HAZIR")),
    ("amortised_cost", re.compile(r"ITFA EDILMIS|AMORTI[SZ]ED COST|HELD.?TO.?MATURITY|VADEYE KADAR")),
]


def portfolio_of(heading: str | None, item_title: str | None) -> str:
    h = fold(heading) + " " + fold(item_title)
    for name, rx in _PORTFOLIO:
        if rx.search(h):
            return name
    return "unknown"


_TITLE_LINE = re.compile(r"ILISKIN BILGI|INFORMATION ON|FINANSAL VARLIK|FINANCIAL ASSETS|MENKUL|SECURITIES")
_GROUP_HEAD = re.compile(r"^BORCLANMA SENETLERI|^DEBT SECURITIES|^DEBT INSTRUMENTS?( \(|$)|"
                         r"^HISSE SENETLERI|^SHARE CERTIFICATES|^EQUITY (SECURITIES|SHARES|INSTRUMENTS)")


def portfolio_from_grid(grid: list[dict]) -> str:
    """The portfolio from a title line the capture left INSIDE the block.

    ALNTF prints "e. Gerçeğe uygun değer farkı diğer kapsamlı gelire
    yansıtılan..." as a valueless row two lines above its own table, in a
    block whose heading belongs to the country table above it. The ledger
    lookback cannot see that line — it is in the tables layer, not the lines
    layer — so it reached past it to the FVTPL note and filed 7,919,060, the
    balance sheet's FVOCI line to the lira, as fvtpl.

    Only what is printed ABOVE the table's first group row counts, and the
    nearest one wins."""
    seen = "unknown"
    for r in grid:
        label = fold(r.get("label") or "").strip()
        if _GROUP_HEAD.search(label) and any(c is not None for c in r.get("cells") or []):
            return seen
        if any(isinstance(c, (int, float)) for c in r.get("cells") or []):
            continue                      # a data row of some other table
        for name, rx in _PORTFOLIO:
            if rx.search(label):
                seen = name
                break
    return "unknown"


def portfolio_from_ledger(cap: sqlite3.Connection | None, key: tuple, page: int, block_id: int) -> str:
    """The portfolio from the nearest title paragraph above the block in the
    capture ledger — "b) Gerçeğe uygun değer farkı diğer kapsamlı gelire
    yansıtılan finansal varlıklara ilişkin bilgiler" sits between tables,
    where the tables layer keeps no text. Looks back up to 40 lines over
    the page and the one before; 'unknown' where nothing names one."""
    if cap is None:
        return "unknown"
    row = cap.execute("SELECT first_line FROM bank_audit_document_blocks WHERE bank_ticker=? AND period=? "
                      "AND kind=? AND page=? AND block_id=?", (*key, page, block_id)).fetchone()
    if row is None:
        return "unknown"
    lines = cap.execute(
        "SELECT page, line_order, text, role FROM bank_audit_document_lines WHERE bank_ticker=? AND period=? "
        "AND kind=? AND ((page=? AND line_order<?) OR page=?) ORDER BY page DESC, line_order DESC LIMIT 40",
        (*key, page, row[0], page - 1)).fetchall()
    for _pg, _lo, text, role in lines:
        f = fold(text)
        # the ledger files these title lines as paragraph, heading or footnote
        if role != "data" and _TITLE_LINE.search(f):
            for name, rx in _PORTFOLIO:
                if rx.search(f):
                    return name
    return "unknown"


DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_securities_full (
    bank_ticker  TEXT NOT NULL,
    period       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    instance_no  INTEGER NOT NULL,
    -- fvtpl / fvoci / amortised_cost / unknown, read off the block heading
    -- (kept alongside) and its contents item.
    portfolio    TEXT NOT NULL,
    heading      TEXT,
    row_order    INTEGER NOT NULL,
    label        TEXT NOT NULL,
    group_role   TEXT,
    item_role    TEXT,
    -- canonical thousand TL (scaled at mint). NULL = the filing printed "-".
    -- `current` and `prior` are the PERIOD totals: where the note splits the
    -- period into TL and FC columns (AKTIF, ALNTF, ZIRAAT…) they are the sum
    -- and the halves are kept beside them.
    current      REAL,
    prior        REAL,
    current_tl   REAL,
    current_fc   REAL,
    prior_tl     REAL,
    prior_fc     REAL,
    page         INTEGER NOT NULL,
    block_id     INTEGER NOT NULL,
    source_unit  TEXT,
    PRIMARY KEY (bank_ticker, period, kind, instance_no, row_order)
);
CREATE INDEX IF NOT EXISTS idx_securities_full_ctx
  ON bank_audit_securities_full(portfolio, group_role, item_role);
"""


def _sec_role(label: str) -> str | None:
    f = fold(label).strip()
    for name, rx in GROUPS + ITEMS:
        if rx.search(f):
            return name
    if _IMPAIR.search(f):
        return "impairment"
    if _TOTAL.search(f):
        return "total"
    return None


def _normalise(grid: list[dict]) -> list[dict]:
    """The grid from its first debt-securities row to its first total: the
    date row the capture puts above it ("30 Haziran 2026 | 2026 | 2025" —
    BURGAN, AKBNK, ICBCT, HSBC...) and a note title are dropped, and so is
    the movement table the capture glues on below (AKTIF, ALNTF, VAKBN)."""
    first = next((i for i, r in enumerate(grid) if _sec_role(r["label"] or "") == "debt_securities"), None)
    if first is None:
        return grid
    grid = grid[first:]
    total = next((i for i, r in enumerate(grid) if _sec_role(r["label"] or "") == "total"), None)
    return grid if total is None else grid[:total + 1]


_TL_FC_HEADER = re.compile(r"\b(TP|TL)\b.{0,6}\b(YP|FC|FX)\b.{0,12}\b(TP|TL)\b.{0,6}\b(YP|FC|FX)\b")


# The same four-way header as it survives in COLUMN LABELS, where the
# capture splits "Current Period TL / FC" across the cells and the gaps run
# longer: EXIM's read ["Current TL", "Period FC", "Prior TL", "Period FC"].
_TL_FC_COLS = re.compile(r"\b(TP|TL)\b.{0,12}\b(YP|FC|FX)\b.{0,16}\b(TP|TL)\b.{0,12}\b(YP|FC|FX)\b")


def _split_by_currency(grid: list[dict], live: list[int],
                       col_labels: list | None = None) -> bool:
    """True where the note prints TP YP TP YP — four columns, the period
    split by currency — rather than current and prior. Read off a header
    row inside the grid, or off the column labels: taking TL for "current"
    and FC for "prior" halved every figure against the balance sheet.

    EXIM's amortised-cost note totals 3,694,986 TL + 6,133,573 FC =
    9,828,559, the balance sheet's line to the lira, and the lane was
    storing the 3,694,986."""
    if len(live) != 4:
        return False
    for r in grid:
        if any(c is not None for c in r["cells"]):
            continue
        if _TL_FC_HEADER.search(fold(r["label"] or "")):
            return True
    if col_labels and _TL_FC_COLS.search(fold(" ".join(str(c or "") for c in col_labels))):
        return True
    return False


def _value_columns(grid: list[dict], raw: list[dict] | None = None,
                   col_labels: list | None = None) -> list[int]:
    """(current, prior) cell indexes, or four when the period is split by
    currency: the first live columns — VAKBN parks the figures in columns 4
    and 8 of a nine-cell row."""
    live = BM.live_value_columns(grid)
    if _split_by_currency(raw if raw is not None else grid, live, col_labels):
        return live
    if len(live) >= 2:
        return live[:2]
    if len(live) == 1:
        return [live[0], -1]
    n = max((len(r["cells"]) for r in grid), default=0)
    return [n - 2, n - 1]


def _is_family(grid: list[dict]) -> bool:
    if not 4 <= len(grid) <= 14:
        return False
    first = fold(grid[0]["label"] or "").strip()
    return any(rx.search(first) for _g, rx in GROUPS[:1]) and any(
        _TOTAL.search(fold(r["label"] or "").strip()) for r in grid)


def _rows_of(grid: list[dict], pg: int, bid: int, factor, raw: list[dict] | None = None,
             col_labels: list | None = None) -> list[dict]:
    rows, group = [], None
    # the TP YP TP YP header sits above the first debt-securities row, which
    # `_normalise` cuts away — so the split is read off the RAW grid
    idx = _value_columns(grid, raw if raw is not None else grid, col_labels)
    split = len(idx) == 4
    for r in grid:
        label = (r["label"] or "").strip()
        if not label:
            continue
        f = fold(label)
        g = next((name for name, rx in GROUPS if rx.search(f)), None)
        item = None
        if g:
            group = g
            item_role = "group"
        elif _IMPAIR.search(f):
            group = None
            item_role = "valuation" if _VALUATION_LABEL.search(f) else "impairment"
        elif _TOTAL.search(f):
            group, item_role = None, "total"
        else:
            item = next((name for name, rx in ITEMS if rx.search(f)), None)
            item_role = item
        cells = r["cells"]
        got = [num(cells[i]) if 0 <= i < len(cells) else None for i in idx]
        if factor is not None:
            got = [U.scale_amount(v, factor) for v in got]
        if split:
            ctl, cfc, ptl, pfc = got

            def _sum(a, b):
                return None if a is None and b is None else (a or 0.0) + (b or 0.0)
            vals = [_sum(ctl, cfc), _sum(ptl, pfc)]
            parts = [ctl, cfc, ptl, pfc]
        else:
            vals = got[:2]
            parts = [None, None, None, None]
        row = {"label": label, "group_role": group if item_role in ("group", "quoted", "unquoted") else None,
               "item_role": item_role, "page": pg, "block_id": bid}
        row.update(zip(VALUES, vals))
        row.update(zip(("current_tl", "current_fc", "prior_tl", "prior_fc"), parts))
        rows.append(row)
    return rows


def _identity_holds(inst: list[dict]) -> bool:
    heads = {}
    children: dict[str, list] = {}
    adjust = 0.0
    total = None
    for x in inst:
        if x["item_role"] == "group":
            heads[x["group_role"]] = x["current"]
        elif x["item_role"] in ("quoted", "unquoted") and x["group_role"]:
            children.setdefault(x["group_role"], []).append(x["current"])
        elif x["item_role"] in ("impairment", "valuation") and x["current"] is not None:
            v = x["current"]
            lab = fold(x["label"])
            if x["item_role"] == "impairment" and v > 0 and _DEDUCTION_LABEL.search(lab):
                adjust -= v                  # "(-)" label, positive figure
            else:
                adjust += v                  # already signed, or a valuation
        elif x["item_role"] == "total":
            total = x["current"]
    if total is None or not heads:
        return False
    for g, head in heads.items():
        kids = [v for v in children.get(g, []) if v is not None]
        if head is not None and len(children.get(g, [])) >= 2 and kids \
                and abs(sum(kids) - head) > max(2.0, 1e-5 * abs(head)):
            return False
    # a group head printed "-" (or not at all) contributes its children instead
    expect = 0.0
    for g in set(heads) | set(children):
        head = heads.get(g)
        kids = [v for v in children.get(g, []) if v is not None]
        expect += head if head is not None else sum(kids)
    expect += adjust
    return abs(expect - total) <= max(2.0, 1e-5 * abs(total))


def assemble(tab: sqlite3.Connection, key: tuple, cap: sqlite3.Connection | None = None) -> dict | None:
    blocks = tab.execute(
        "SELECT page, block_id, heading, item_title, grid_json, declared_unit, col_labels_json "
        "FROM bank_audit_document_tables WHERE bank_ticker=? AND period=? "
        "AND kind=? ORDER BY page, block_id", key).fetchall()
    found = []
    cols_of: dict[tuple, list] = {}
    for pg, bid, h, it, g, unit, cl in blocks:
        cols_of[(pg, bid)] = json.loads(cl or "[]")
        raw = json.loads(g)                 # before absorb_inline: it drops the "TP YP TP YP" header
        grid = _normalise(absorb_inline(raw, _sec_role))
        if _is_family(grid):
            found.append((pg, bid, h, it, grid, unit, raw))
    if not found:
        return None
    unit = found[0][5]
    factor = U.UNIT_SCALE.get(unit)
    instances = []
    for pg, bid, h, it, grid, _u, raw in found:
        portfolio = portfolio_of(h, it)
        if portfolio == "unknown":
            # the block's own title line first: it is the only evidence that
            # is certainly about THIS table
            portfolio = portfolio_from_grid(raw)
        if portfolio == "unknown":
            portfolio = portfolio_from_ledger(cap, key, pg, bid)
        instances.append({"portfolio": portfolio, "heading": h,
                          "rows": _rows_of(grid, pg, bid, factor, raw, cols_of[(pg, bid)])})
    return {"unit": unit, "instances": instances}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tables-db", default=str(TABLES_DB))
    ap.add_argument("--capture-db", default=str(REPO / "data" / "bank_audit_capture.db"),
                    help="the capture ledger, for the portfolio title paragraphs between tables")
    ap.add_argument("--bank")
    ap.add_argument("--period")
    ap.add_argument("--kind")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    tab = sqlite3.connect(f"file:{args.tables_db}?mode=ro", uri=True)
    cap = (sqlite3.connect(f"file:{args.capture_db}?mode=ro", uri=True)
           if Path(args.capture_db).exists() else None)
    out = None
    if args.write:
        out = sqlite3.connect(args.tables_db)
        out.executescript(DDL)

    where, params = [], []
    for col, val in (("bank_ticker", args.bank), ("period", args.period),
                     ("kind", args.kind)):
        if val:
            where.append(f"{col}=?")
            params.append(val.upper() if col != "kind" else val)
    keys = [tuple(r) for r in tab.execute(
        "SELECT DISTINCT bank_ticker, period, kind FROM bank_audit_document_tables"
        + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY 1,2,3",
        params)]

    detected = written = gated = 0
    per_filing: Counter = Counter()
    portfolios: Counter = Counter()
    for key in keys:
        got = assemble(tab, key, cap)
        if got is None:
            continue
        detected += 1
        kept = [i for i in got["instances"] if _identity_holds(i["rows"])]
        gated += len(got["instances"]) - len(kept)
        if not kept:
            continue
        per_filing[len(kept)] += 1
        for i in kept:
            portfolios[i["portfolio"]] += 1
        if args.verbose:
            print(f"{' '.join(key)}: {[i['portfolio'] for i in kept]}")
        if out is not None:
            out.execute("DELETE FROM bank_audit_securities_full WHERE bank_ticker=? "
                        "AND period=? AND kind=?", key)
            for n, i in enumerate(kept):
                out.executemany(
                    "INSERT INTO bank_audit_securities_full VALUES "
                    "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(*key, n, i["portfolio"], i["heading"], k, x["label"],
                      x["group_role"], x["item_role"], x["current"], x["prior"],
                      x.get("current_tl"), x.get("current_fc"),
                      x.get("prior_tl"), x.get("prior_fc"),
                      x["page"], x["block_id"], got["unit"])
                     for k, x in enumerate(i["rows"])])
                written += len(i["rows"])
            out.commit()

    print(f"\npartitions: {len(keys)} scanned | detected {detected} | "
          f"instances gated out by the identities: {gated}")
    if per_filing:
        print(f"instances per filing kept: {dict(sorted(per_filing.items()))}")
        print(f"portfolios: {dict(portfolios.most_common())}")
    if out is not None:
        print(f"\nwrote {written:,} rows to bank_audit_securities_full")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
