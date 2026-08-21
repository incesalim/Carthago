#!/usr/bin/env python
"""The leverage-ratio graduation: BRSA's numbered 1-15 template, minted from
the document layer on the shared numbered-template machinery.

The narrow `bank_audit_liquidity` keeps ONE number of this disclosure
(`leverage_ratio`, row 15). The wide lane keeps all 15 rows — on-balance-
sheet exposure, derivatives, securities-financing, off-balance-sheet
conversions, Tier 1 capital, total exposure — in both printed columns
(current period and the prior year-end, side by side in one table).

Validators, dry-run (default): row 15's current column vs narrow
`leverage_ratio`; its prior column vs the prior YEAR-END's narrow row; and
the template's own identity, row 15 = Tier 1 (13) / total exposure (14),
which is point-in-time-tight (the rows are the same three-month averages the
ratio is computed from).

`--write` stores into bank_audit_leverage_full in data/bank_audit_tables.db
(local only; never the audit snapshot, not D1).
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.audit_reports import numbered_template as NT  # noqa: E402

TABLES_DB = REPO / "data" / "bank_audit_tables.db"
AUDIT_DB = REPO / "data" / "bank_audit.db"

_SIG = {
    13: re.compile(r"^ANA SERMAYE|^TIER (I|1) CAPITAL"),
    14: re.compile(r"TOPLAM RISK TUTARI|TOTAL (RISKS?|EXPOSURE)"),
    15: re.compile(r"KALDIRAC ORANI|LEVERAGE RATIO"),
}
ROLE_BY_ROW = {
    1: "on_balance_sheet_assets", 2: "tier1_deductions",
    3: "on_balance_sheet_exposure", 6: "derivatives_exposure",
    9: "sft_exposure", 12: "off_balance_sheet_exposure",
    13: "tier1_capital", 14: "total_exposure", 15: "leverage_ratio",
}

DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_leverage_full (
    bank_ticker  TEXT NOT NULL,
    period       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    period_label TEXT NOT NULL,
    row_order    INTEGER NOT NULL,
    template_row INTEGER,
    label        TEXT NOT NULL,
    row_role     TEXT,
    -- current period and the prior YEAR-END, the two printed columns.
    -- Canonical thousand TL, scaled at mint; row 15 is the percent, never
    -- scaled. NULL = the filing printed "-".
    amount       REAL,
    amount_prior REAL,
    page         INTEGER NOT NULL,
    block_id     INTEGER NOT NULL,
    source_unit  TEXT,
    PRIMARY KEY (bank_ticker, period, kind, period_label, row_order)
);
CREATE INDEX IF NOT EXISTS idx_leverage_full_row
  ON bank_audit_leverage_full(template_row);
"""


# the same fifteen rows by label, for the banks that print the template
# without its numbers (BURGAN, ING, ZIRAAT, ANADOLU...) or split it over two
# blocks (HALKB: rows 13-15 in the block after)
_R = re.compile
_BY_LABEL: list[tuple[int, re.Pattern]] = [
    (3, _R(r"^BILANCO ICI VARLIKLARA ILISKIN TOPLAM|^TOTAL ON.?BALANCE SHEET EXPOSURE|^TOTAL ON.BALANCE|"
           r"^TOTAL RISK AMOUNT RELATED TO ASSETS ON BALANCE")),
    (1, _R(r"^BILANCO ICI VARLIKLAR \(|^ON.?BALANCE SHEET (ASSETS|ITEMS|EXPOSURES?) \(|^ON.?BALANCE SHEET ASSETS$|"
           r"^ASSETS ON BALANCE SHEET")),
    (2, _R(r"^\(?ANA SERMAYEDEN INDIRILEN|^\(?ASSETS (AMOUNTS? )?(THAT ARE )?DEDUCTED|^\(?DEDUCTIONS FROM TIER")),
    (6, _R(r"^TUREV FINANSAL ARACLAR ILE KREDI TUREVLERINE ILISKIN TOPLAM|^(THE )?TOTAL (AMOUNT OF )?(RISKS? (ON|OF|RELATED TO) )?DERIVATIVE|"
           r"^TOTAL DERIVATIVE|^TOTAL RISK AMOUNT RELATED TO DERIVATIVE")),
    (4, _R(r"YENILEME MALIYET|^(THE )?REPLACEMENT COST")),
    (5, _R(r"POTANSIYEL KREDI RISK|^(THE )?POTENTIAL (AMOUNT OF )?(CREDIT )?RISK|^POTENTIAL FUTURE")),
    (9, _R(r"^MENKUL KIYMET VEYA EMTIA TEMINATLI FINANSMAN ISLEMLERINE ILISKIN TOPLAM|"
           r"^(THE )?TOTAL (RISKS? )?(AMOUNT )?(RELATED TO |RELATED WITH |OF |ON )?(SECURITIES|INVESTMENT SECURITIES|SFT|FINANCIAL TRANSACTIONS HAVING)")),
    (8, _R(r"^ARACILIK EDILEN|^(THE )?(RISK AMOUNT OF |AMOUNT OF RISK (FROM |OF )?)?(EXCHANGE )?BROKERAGE|^AGENT TRANSACTION|"
           r"^RISKS? (FROM|OF) AGENT|^RISK AMOUNT SOURCING FROM TRANSACTIONS MEDIATED|INTERMEDIAT")),
    (7, _R(r"^(MENKUL )?KIYMET VEYA EMTIA TEMINATLI FINANSMAN ISLEMLERININ|^(THE )?(AMOUNT OF )?RISK (AMOUNT )?(OF |FOR )?(INVESTMENT )?SECURITIES|"
           r"^SECURITIES OR COMMODITY|^SFT (ASSETS|EXPOSURE)|^RISK AMOUNT OF FINANCIAL TRANSACTIONS HAVING SECURITY")),
    (12, _R(r"^BILANCO DISI ISLEMLERE ILISKIN TOPLAM|^(THE )?TOTAL (RISKS? OF |AMOUNT OF |)OFF.?BALANCE|^TOTAL OFF.?BALANCE|"
            r"^TOTAL RISK (AMOUNT )?(RELATED TO |OF )?OFF.?BALANCE")),
    (10, _R(r"^BILANCO DISI ISLEMLERIN BRUT|^GROSS (NOTIONAL|NOMINAL)|^OFF.?BALANCE SHEET (ITEMS|EXPOSURES?) (AT |WITH )?GROSS")),
    (11, _R(r"^\(?KREDIYE DONUSTURME|^\(?ADJUSTMENTS? (AMOUNT )?(FOR|OF|SOURCING)")),
    (13, _R(r"^ANA SERMAYE$|^ANA SERMAYE \(|^TIER (I|1) CAPITAL|^CORE CAPITAL")),
    (14, _R(r"^TOPLAM RISK TUTARI|^TOTAL (RISKS?|EXPOSURES?)( AMOUNT)?$|^TOTAL (RISKS?|EXPOSURES?) \(|^AMOUNT OF TOTAL RISK")),
    (15, _R(r"^KALDIRAC ORANI|^(FINANCIAL )?LEVERAGE RATIO")),
]


def _template_row(label: str) -> int | None:
    f = NT.fold(label).strip()
    f = re.sub(r"^\d{1,2}[.)]?\s*", "", f)           # "3. Total on-balance..." numbered after all
    for n, rx in _BY_LABEL:
        if rx.search(f):
            return n
    return None


def _unnumbered_gate(rows: list[dict]) -> bool:
    """The template's own arithmetic on the current column: 15 = 13 / 14
    (within 0.06 pp), or 14 = 3 + 6 + 9 + 12 where the ratio is absent."""
    by = {x["template_row"]: x for x in rows}
    t1, ex, r = (by.get(n, {}).get("amount") for n in (13, 14, 15))
    if None not in (t1, ex, r) and ex:
        return abs(t1 / ex * 100 - r) <= 0.06
    parts = [by.get(n, {}).get("amount") for n in (3, 6, 9, 12)]
    if ex is not None and parts[0] is not None:
        return abs(sum(v or 0.0 for v in parts) - ex) <= max(2.0, 1e-4 * abs(ex))
    return False


def _chain_rows(chain: list[tuple], unit) -> list[dict]:
    from src.audit_reports import band_matrix as BM
    factor = NT.U.UNIT_SCALE.get(unit)
    grid = [r for _pg, _bid, r, _n in chain]
    live = BM.live_value_columns(grid)
    cols = live[-2:] if len(live) >= 2 else [len(grid[0]["cells"]) - 2, len(grid[0]["cells"]) - 1]
    rows = []
    for pg, bid, r, n in chain:
        cells = r["cells"]
        vals = [NT.num(cells[c]) if 0 <= c < len(cells) else None for c in cols]
        if n == 15:
            vals = NT.repair_percent(vals, 1000)
        elif factor is not None:
            vals = [NT.U.scale_amount(v, factor) for v in vals]
        rows.append({"template_row": n, "label": (r["label"] or "").strip(), "role": ROLE_BY_ROW.get(n),
                     "page": pg, "block_id": bid, "amount": vals[0], "amount_prior": vals[1]})
    return rows


def assemble_unnumbered(tab: sqlite3.Connection, key: tuple) -> dict | None:
    """The fifteen rows by label: a chain of template rows in template order,
    continued over adjacent blocks (ING, HALKB split it), closed on row 15
    or on the first block that does not continue it. The chain must open
    on rows 1-3 (the capital note's "Tier I capital" rows cannot start one)
    and pass the template's own arithmetic."""
    chain: list[tuple] = []
    unit = None
    last = (-1, -1)
    found: list[tuple[list, str | None]] = []

    def close():
        nonlocal chain
        if chain and any(n in (1, 3) for *_x, n in chain) and chain[-1][3] >= 14 and len(chain) >= 8:
            found.append((chain, unit))
        chain = []

    for pg, bid, grid, u in NT.partition_blocks(tab, key):
        # sub-headers ("Bilanço içi varlıklar", "On-balance sheet assets") print
        # no cells at all; only rows with cells take a template row
        tagged = [(r, _template_row(r["label"] or "") if any(c is not None for c in r["cells"]) else None)
                  for r in grid]
        nums = [n for _r, n in tagged if n]
        adjacent = (pg == last[0] and bid == last[1] + 1) or (pg == last[0] + 1 and bid == 1)
        if not nums:
            if chain and not adjacent:
                close()
            continue
        continues = bool(chain) and adjacent and min(nums) > chain[-1][3]
        if not continues:
            close()
            unit = u
        for r, n in tagged:
            if n and (not chain or n > chain[-1][3]):
                if not chain and n not in (1, 2, 3):
                    continue                          # a chain opens on the on-balance-sheet rows
                chain.append((pg, bid, r, n))
        last = (pg, bid)
        if chain and chain[-1][3] == 15:
            close()
    close()
    for chain, u in found:
        rows = _chain_rows(chain, u)
        if _unnumbered_gate(rows):
            return {"unit": u, "instances": {"current": rows}}
    return None


def assemble(tab: sqlite3.Connection, key: tuple) -> dict | None:
    got = NT.assemble(
        tab, key, sig=_SIG, max_row=15, bottom_row=14, n_values=2,
        percent_rows={15}, role_of=lambda n, _label: ROLE_BY_ROW.get(n),
        value_names=("amount", "amount_prior"),
        # a leverage ratio is single digits; "9,127" read as 9127 is 9.127%
        percent_repair_floor=1000)
    return got if got is not None else assemble_unnumbered(tab, key)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tables-db", default=str(TABLES_DB))
    ap.add_argument("--audit-db", default=str(AUDIT_DB))
    ap.add_argument("--bank")
    ap.add_argument("--period")
    ap.add_argument("--kind")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    tab = sqlite3.connect(f"file:{args.tables_db}?mode=ro", uri=True)
    aud = sqlite3.connect(f"file:{args.audit_db}?mode=ro", uri=True)
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

    def narrow(key):
        return [v for (v,) in aud.execute(
            "SELECT leverage_ratio FROM bank_audit_liquidity WHERE bank_ticker=? "
            "AND period=? AND kind=?", key) if v is not None]

    narrow_parts = {tuple(r) for r in aud.execute(
        "SELECT DISTINCT bank_ticker, period, kind FROM bank_audit_liquidity "
        "WHERE leverage_ratio IS NOT NULL")}

    detected = written = 0
    inst_count: Counter = Counter()
    rows_per: list[int] = []
    cur_a, pri_a, ident = [0, 0], [0, 0], [0, 0, 0]
    mism = []
    for key in keys:
        got = assemble(tab, key)
        if got is None:
            continue
        detected += 1
        inst_count[len(got["instances"])] += 1
        for lab, inst in got["instances"].items():
            rows_per.append(len(inst))
            by_row = {x["template_row"]: x for x in inst}
            for col in ("amount", "amount_prior"):
                t1 = by_row.get(13, {}).get(col)
                ex = by_row.get(14, {}).get(col)
                r = by_row.get(15, {}).get(col)
                if None not in (t1, ex, r) and ex:
                    d = abs(t1 / ex * 100 - r)
                    ident[2] += 1
                    ident[0] += int(d <= 0.05)
                    ident[1] += int(d <= 0.5)
        cur = {x["template_row"]: x for x in got["instances"].get("current", [])}
        wide = cur.get(15, {}).get("amount")
        have = narrow(key)
        if wide is not None and have:
            cur_a[1] += 1
            ok = any(abs(wide - v) <= 0.06 for v in have)
            cur_a[0] += int(ok)
            if not ok and len(mism) < 10:
                mism.append((key, wide, sorted(set(have))))
        pwide = cur.get(15, {}).get("amount_prior")
        phave = narrow((key[0], NT.prior_year_end(key[1]), key[2]))
        if pwide is not None and phave:
            pri_a[1] += 1
            pri_a[0] += int(any(abs(pwide - v) <= 0.06 for v in phave))
        if args.verbose:
            print(f"{' '.join(key)}: instances={list(got['instances'])} "
                  f"rows={[len(v) for v in got['instances'].values()]}")
        if out is not None:
            out.execute("DELETE FROM bank_audit_leverage_full WHERE bank_ticker=? "
                        "AND period=? AND kind=?", key)
            for lab, inst in got["instances"].items():
                out.executemany(
                    "INSERT INTO bank_audit_leverage_full VALUES "
                    "(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(*key, lab, i, x["template_row"], x["label"], x["role"],
                      x["amount"], x["amount_prior"], x["page"], x["block_id"],
                      got["unit"]) for i, x in enumerate(inst)])
                written += len(inst)
            out.commit()

    import statistics
    both = [k for k in keys if k in narrow_parts]
    print(f"\npartitions: {len(keys)} scanned | detected {detected} | "
          f"narrow leverage present locally {len(both)}")
    if rows_per:
        print(f"instances per filing: {dict(sorted(inst_count.items()))}; "
              f"rows per instance: median {statistics.median(rows_per):.0f}")
    for name, b in (("current leverage vs narrow", cur_a),
                    ("prior column vs prior-YEAR-END narrow", pri_a)):
        print(f"  {name:38} {b[0]:4}/{b[1]:4}"
              + (f"  {b[0] / b[1]:6.1%}" if b[1] else ""))
    if ident[2]:
        print(f"  identity 15 = 13/14: within 0.05: {ident[0]}/{ident[2]} "
              f"({ident[0] / ident[2]:.1%})   within 0.5: {ident[1]}/{ident[2]} "
              f"({ident[1] / ident[2]:.1%})")
    for key, wide, vals in mism:
        print(f"    {' '.join(key):32} wide={wide} narrow={vals}")
    if out is not None:
        print(f"\nwrote {written:,} rows to bank_audit_leverage_full")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
