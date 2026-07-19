"""Rebuild `api_series` — the public API's catalog of addressable time series.

Our BDDK tables are stored LONG (period x dimension x item); nothing in them
names a *series*. This script enumerates every (dataset, item, bank type, value
column) tuple that actually carries data and gives it a stable dotted code:

    BDDK.<DATASET>.<ITEM>.<BANKTYPE>.<COL>
    BDDK.T01.I005.10001.TOT      monthly table 1, item 5, whole sector, total
    BDDK.T15.I003.10004.VAL      monthly table 15 (ratios), participation banks
    BDDK.WLOAN.I1_0_11.10001.TL  weekly loans, item 1.0.11, sector, TL leg

Modelled on EVDS's `TP.DK.USD.A`: opaque-but-stable, discovered via /serieList
rather than read by eye.

WHY THE CODES ARE STABLE
------------------------
Three of the four segments are keys BDDK itself assigns, so they cannot drift:
`T01..T17` are BDDK's own monthly table numbers and `10001..10010` its own bank
type codes. The item token is derived directly from the source table's natural
key wherever one exists -- item_order for the monthly statement tables, the
dotted outline id (`1.0.11` -> `I1_0_11`) for weekly.

`other_data` is the one exception: its item_order COLLIDES within table 12, so
its natural key is item_name -- a 300-char Turkish label, unusable in a code.
Those datasets get a catalog-assigned `I###` slot instead, and this script
carries existing assignments forward by item_name so a published code never
changes meaning. New items take the next free slot; nothing is ever renumbered.

Usage:
    python scripts/build_api_catalog.py            # rebuild into data/bddk_data.db
    python scripts/build_api_catalog.py --dry-run  # report only, write nothing

Push to D1 afterwards (api_series is a _FULL_REBUILD table, so it must be named
explicitly -- a routine daily push never touches it):
    python scripts/push_to_d1.py --only-tables api_series
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "bddk_data.db"
SCHEMA = ROOT / "web" / "migrations" / "0031_api_series_catalog.sql"

# ---------------------------------------------------------------------------
# Dataset specs. Each maps a BDDK table (or weekly category) to the physical
# columns a caller can address, under short tokens that mean the same thing
# across every dataset: TL = the lira leg, FX = the foreign-currency leg,
# TOT = both. Anything table-specific (maturity buckets, deposit brackets)
# gets its own token, documented in docs/API.md.

# (dataset, source_table, table_number, {COL_TOKEN: physical_column}, has_currency)
MONTHLY_SPECS: list[tuple[str, str, int, dict[str, str], bool]] = [
    ("T01", "balance_sheet", 1,
     {"TL": "amount_tl", "FX": "amount_fx", "TOT": "amount_total"}, True),
    ("T02", "income_statement", 2,
     {"TL": "amount_tl", "FX": "amount_fx", "TOT": "amount_total"}, True),
    ("T03", "loans", 3,
     {"STTL": "short_term_tl", "STFX": "short_term_fx", "STTOT": "short_term_total",
      "MLTL": "medium_long_tl", "MLFX": "medium_long_fx", "MLTOT": "medium_long_total",
      "TL": "total_tl", "FX": "total_fx", "TOT": "total_amount"}, True),
    ("T04", "loans", 4,
     {"TL": "total_tl", "FX": "total_fx", "TOT": "total_amount"}, True),
    ("T05", "loans", 5,
     {"TOT": "total_amount", "NPL": "npl_amount", "NONCASH": "non_cash_amount"}, True),
    ("T06", "loans", 6,
     {"TL": "total_tl", "FX": "total_fx", "TOT": "total_amount", "NPL": "npl_amount",
      "NONCASH": "non_cash_amount", "CUST": "customer_count"}, True),
    ("T07", "loans", 7,
     {"TL": "total_tl", "FX": "total_fx", "TOT": "total_amount"}, True),
    ("T09", "deposits", 9,
     {"B10K": "bracket_10k", "B50K": "bracket_50k", "B250K": "bracket_250k",
      "B1M": "bracket_1m", "B1MP": "bracket_over_1m", "TOT": "total_amount"}, True),
    ("T10", "deposits", 10,
     {"DEM": "demand", "M1": "maturity_1m", "M13": "maturity_1_3m",
      "M36": "maturity_3_6m", "M612": "maturity_6_12m",
      "M12P": "maturity_over_12m", "TOT": "total_amount"}, True),
    # financial_ratios has no currency column — ratios are unit-free.
    ("T15", "financial_ratios", 15, {"VAL": "ratio_value"}, False),
    ("T17", "financial_ratios", 17, {"VAL": "ratio_value"}, False),
]

# other_data stores its value dimension as ROWS (column_name), not columns, and
# keys items by item_name because item_order collides inside table 12.
# (dataset, table_number, {COL_TOKEN: column_name})
OTHER_SPECS: list[tuple[str, int, dict[str, str]]] = [
    ("T08", 8, {"TOT": "Toplam", "TL": "Tp", "FX": "Yp"}),
    ("T11", 11, {"D7": "YediGun", "M1": "BirAy", "M3": "UcAy",
                 "M12": "OnikiAy", "ALL": "TumVarlikYukumluluk"}),
    ("T12", 12, {"TOT": "Toplam"}),
    ("T13", 13, {"TOT": "Toplam"}),
    ("T14", 14, {"TOT": "Toplam", "TL": "Tp", "FX": "Yp"}),
    ("T16", 16, {"CNT": "Adet"}),
]

# weekly_series category -> dataset token. English mnemonics: the raw category
# slugs (bilanco_disi vs diger_bilanco) differ by two letters and would make
# near-identical codes that are easy to mistype and impossible to proofread.
WEEKLY_DATASETS: dict[str, str] = {
    "krediler": "WLOAN",
    "menkul_degerler": "WSEC",
    "mevduat": "WDEP",
    "takipteki_alacaklar": "WNPL",
    "bilanco_disi": "WOBS",
    "diger_bilanco": "WBAL",
    "yp_pozisyon_saklama": "WFX",
}
# weekly_series.currency IS the value leg (not a reporting basis, unlike the
# monthly tables), so it maps onto the same TL/FX/TOT tokens used everywhere.
WEEKLY_COLS: dict[str, str] = {"TL": "TL", "FX": "FX", "TOT": "TOTAL"}

WEEKLY_UNIT = "thousand TL"

# The monthly tables carry a `currency` dimension that is a PRESENTATION basis,
# not a value leg: the USD rows are the identical figures divided by one month's
# USD/TRY rate (verified — every line in 2025-12 is exactly TL/42.0).
#
# We exclude them. The USD basis was scraped exactly once, for 2025-12, in every
# table (1 period vs 76 for TL), so publishing it would add ~17,000 series that
# each hold a SINGLE observation — half the catalog, none of it a time series.
# A caller wanting USD is better served converting with a rate of their choosing
# and a date of their choosing than by a frozen one-month artifact of ours.
#
# Flip to True only once the USD basis is backfilled across the full history.
INCLUDE_USD_BASIS = False

# SQLite expression turning (year, month) into the period END date, which is what
# a BDDK monthly figure actually represents: a month-end stock, not a flow dated
# to the 1st.
MONTH_END = "date(printf('%04d-%02d-01', year, month), '+1 month', '-1 day')"

# Coverage the build deliberately drops, reported at the end. A catalog that
# silently omits series reads as "this is everything" when it isn't.
_skipped: dict[str, int] = {"usd": 0}


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create api_series locally from the same DDL that migrates D1."""
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))


def load_existing_slots(conn: sqlite3.Connection) -> dict[tuple[str, str], str]:
    """Existing (dataset, item_key) -> I### slot, so codes survive a rebuild.

    Only other_data datasets need this — everywhere else the slot is derived
    from the source table's own key and is stable by construction.
    """
    try:
        rows = conn.execute(
            "SELECT dataset, item_key, series_code FROM api_series"
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    out: dict[tuple[str, str], str] = {}
    for dataset, item_key, code in rows:
        # segment 2 of BDDK.<DS>.<ITEM>.<BT>.<COL>
        parts = code.split(".")
        if len(parts) != 5:
            continue
        # A USD-reported dataset (T08U) shares its item slots with the TL one
        # (T08) — they are the same lines, reported on a different basis. Key
        # both to the base so a USD-only series still reuses the right slot.
        base = dataset[:-1] if dataset.endswith("U") else dataset
        out[(base, item_key)] = parts[2]
    return out


def item_token_monthly(item_order: int) -> str:
    return f"I{int(item_order):03d}"


def item_token_weekly(item_id: str) -> str:
    """`1.0.11` -> `I1_0_11`. Dots are the code's separator, so they can't survive."""
    return "I" + str(item_id).replace(".", "_")


def latest_names(conn: sqlite3.Connection, table: str, where: str,
                 key_col: str, params: tuple) -> dict:
    """Map key -> the item_name from the MOST RECENT period.

    Labels get revised (translation fixes, BDDK re-wordings); the newest filing
    is the one a caller will recognise, so it wins.
    """
    sql = f"""
        SELECT {key_col}, item_name FROM (
            SELECT {key_col}, item_name,
                   ROW_NUMBER() OVER (
                       PARTITION BY {key_col} ORDER BY year DESC, month DESC
                   ) AS rn
            FROM {table} {where}
        ) WHERE rn = 1
    """
    return {r[0]: r[1] for r in conn.execute(sql, params)}


def build_monthly(conn: sqlite3.Connection, units: dict[int, str]) -> list[dict]:
    out: list[dict] = []
    for dataset, table, tno, cols, has_currency in MONTHLY_SPECS:
        # loans/deposits/ratios/other partition one physical table by table_number;
        # balance_sheet and income_statement are whole tables of their own.
        filtered = table in ("loans", "deposits", "financial_ratios")
        where = "WHERE table_number = ?" if filtered else ""
        params: tuple = (tno,) if filtered else ()

        names = latest_names(conn, table, where, "item_order", params)
        cur_expr = "currency" if has_currency else "'TL'"

        for token, phys in cols.items():
            sql = f"""
                SELECT {cur_expr} AS cur, bank_type_code, item_order,
                       COUNT({phys}) AS n,
                       MIN(CASE WHEN {phys} IS NOT NULL THEN {MONTH_END} END) AS d0,
                       MAX(CASE WHEN {phys} IS NOT NULL THEN {MONTH_END} END) AS d1
                FROM {table} {where}
                GROUP BY cur, bank_type_code, item_order
                HAVING n > 0
            """
            for cur, bt, item_order, n, d0, d1 in conn.execute(sql, params):
                if cur == "USD" and not INCLUDE_USD_BASIS:
                    _skipped["usd"] += 1
                    continue
                # USD-reported rows are a separate dataset namespace, not a 6th
                # code segment: keeping every code exactly 5 segments makes the
                # grammar parseable without lookahead.
                ds = dataset + ("U" if cur == "USD" else "")
                out.append({
                    "series_code": f"BDDK.{ds}.{item_token_monthly(item_order)}.{bt}.{token}",
                    "dataset": ds,
                    "frequency": "monthly",
                    "source_table": table,
                    "table_number": tno,
                    "category": None,
                    "item_key": str(item_order),
                    "item_name": names.get(item_order, f"item {item_order}"),
                    "bank_type_code": bt,
                    "report_currency": cur,
                    "value_column": phys,
                    "unit": units.get(tno),
                    "start_date": d0,
                    "end_date": d1,
                    "obs_count": n,
                })
    return out


def build_other(conn: sqlite3.Connection, units: dict[int, str],
                slots: dict[tuple[str, str], str]) -> list[dict]:
    """other_data datasets — the ones needing catalog-assigned item slots."""
    out: list[dict] = []
    for dataset, tno, cols in OTHER_SPECS:
        # Allocate slots over the FULL item set for this table, sorted
        # deterministically, so a rebuild on unchanged data is a no-op.
        items = [r[0] for r in conn.execute(
            "SELECT item_name FROM other_data WHERE table_number = ? "
            "GROUP BY item_name ORDER BY MIN(item_order), item_name",
            (tno,),
        )]

        used = {slot for (ds, _k), slot in slots.items() if ds == dataset}
        next_slot = 1
        assign: dict[str, str] = {}
        for name in items:
            existing = slots.get((dataset, name))
            if existing:
                assign[name] = existing
                continue
            while f"I{next_slot:03d}" in used:
                next_slot += 1
            assign[name] = f"I{next_slot:03d}"
            used.add(assign[name])
            next_slot += 1

        for token, colname in cols.items():
            sql = f"""
                SELECT currency, bank_type_code, item_name,
                       COUNT(value_numeric) AS n,
                       MIN(CASE WHEN value_numeric IS NOT NULL THEN {MONTH_END} END) AS d0,
                       MAX(CASE WHEN value_numeric IS NOT NULL THEN {MONTH_END} END) AS d1
                FROM other_data
                WHERE table_number = ? AND column_name = ?
                GROUP BY currency, bank_type_code, item_name
                HAVING n > 0
            """
            for cur, bt, name, n, d0, d1 in conn.execute(sql, (tno, colname)):
                if cur == "USD" and not INCLUDE_USD_BASIS:
                    _skipped["usd"] += 1
                    continue
                ds = dataset + ("U" if cur == "USD" else "")
                out.append({
                    "series_code": f"BDDK.{ds}.{assign[name]}.{bt}.{token}",
                    "dataset": ds,
                    "frequency": "monthly",
                    "source_table": "other_data",
                    "table_number": tno,
                    "category": None,
                    "item_key": name,
                    "item_name": name,
                    "bank_type_code": bt,
                    "report_currency": cur,
                    "value_column": colname,
                    "unit": units.get(tno),
                    "start_date": d0,
                    "end_date": d1,
                    "obs_count": n,
                })
    return out


def build_weekly(conn: sqlite3.Connection) -> list[dict]:
    out: list[dict] = []
    names = {
        (c, i): n for c, i, n in conn.execute(
            """
            SELECT category, item_id, item_name FROM (
                SELECT category, item_id, item_name,
                       ROW_NUMBER() OVER (
                           PARTITION BY category, item_id ORDER BY period_date DESC
                       ) AS rn
                FROM weekly_series
            ) WHERE rn = 1
            """
        )
    }
    sql = """
        SELECT category, item_id, bank_type_code, currency,
               COUNT(value) AS n, MIN(period_date), MAX(period_date)
        FROM weekly_series
        GROUP BY category, item_id, bank_type_code, currency
        HAVING n > 0
    """
    rev = {v: k for k, v in WEEKLY_COLS.items()}
    for cat, item_id, bt, cur, n, d0, d1 in conn.execute(sql):
        ds = WEEKLY_DATASETS.get(cat)
        token = rev.get(cur)
        if not ds or not token:
            continue  # unknown category / currency leg — never invent a code
        out.append({
            "series_code": f"BDDK.{ds}.{item_token_weekly(item_id)}.{bt}.{token}",
            "dataset": ds,
            "frequency": "weekly",
            "source_table": "weekly_series",
            "table_number": None,
            "category": cat,
            "item_key": str(item_id),
            "item_name": names.get((cat, item_id), str(item_id)),
            "bank_type_code": bt,
            "report_currency": None,
            "value_column": cur,
            "unit": WEEKLY_UNIT,
            "start_date": d0,
            "end_date": d1,
            "obs_count": n,
        })
    return out


COLUMNS = ["series_code", "dataset", "frequency", "source_table", "table_number",
           "category", "item_key", "item_name", "bank_type_code",
           "report_currency", "value_column", "unit", "start_date", "end_date",
           "obs_count"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="report the catalog that WOULD be written; change nothing")
    args = ap.parse_args()

    if not DB.exists():
        print(f"ERROR: {DB} not found", file=sys.stderr)
        return 1

    conn = sqlite3.connect(DB)
    ensure_schema(conn)

    units = {r[0]: r[1] for r in
             conn.execute("SELECT table_number, unit FROM table_definitions")}
    slots = load_existing_slots(conn)

    series = build_monthly(conn, units) + build_other(conn, units, slots) \
        + build_weekly(conn)

    # A duplicate code would silently shadow a series. It means a spec is wrong
    # (two tokens mapped to one column, or a slot reused) — fail, never guess.
    seen: dict[str, dict] = {}
    dupes = []
    for s in series:
        if s["series_code"] in seen:
            dupes.append(s["series_code"])
        seen[s["series_code"]] = s
    if dupes:
        print(f"ERROR: {len(dupes)} duplicate series codes, e.g. {dupes[:5]}",
              file=sys.stderr)
        return 1

    by_ds: dict[str, int] = {}
    for s in series:
        by_ds[s["dataset"]] = by_ds.get(s["dataset"], 0) + 1
    print(f"catalog: {len(series)} series across {len(by_ds)} datasets")
    for ds in sorted(by_ds):
        print(f"  {ds:8} {by_ds[ds]:6,}")
    if _skipped["usd"]:
        print(f"  excluded: {_skipped['usd']:,} USD-basis series "
              f"(single period only — see INCLUDE_USD_BASIS)")

    # Codes that existed before but no longer resolve: the underlying series went
    # away (a table BDDK stopped filing, an item retired). Report loudly — a
    # published code disappearing is a breaking change for callers.
    prior = {r[0] for r in conn.execute("SELECT series_code FROM api_series")}
    gone = prior - set(seen)
    if gone:
        print(f"WARNING: {len(gone)} previously published codes no longer resolve, "
              f"e.g. {sorted(gone)[:5]}")

    if args.dry_run:
        print("dry-run — nothing written")
        return 0

    conn.execute("DELETE FROM api_series")
    conn.executemany(
        f"INSERT INTO api_series ({','.join(COLUMNS)}) "
        f"VALUES ({','.join('?' * len(COLUMNS))})",
        [tuple(s[c] for c in COLUMNS) for s in series],
    )
    conn.commit()
    print(f"wrote {len(series)} rows to {DB}:api_series")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
