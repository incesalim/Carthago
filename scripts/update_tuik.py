"""Ingest the TÜİK Excel tables EVDS doesn't carry, into the shared
`evds_series` table (codes `TUIK.*`) so the /economy/economic-growth and
/economy/inflation pages can surface them.

Tables (discovered by name from the veriportali theme tree):
  - Household final consumption by durability (chain-vol index)  → Şekil 5
  - Gross fixed capital formation by type (chain-vol index)      → Şekil 4
  - Domestic PPI — Main Industrial Groupings (index, monthly)    → inflation MIG table
  - CPI COICOP main-group weights (annual)                       → context / future contributions

Runs in CI (the EVDS lane), NOT locally for the push — `--verify` only parses
and prints (the light local check). Default writes to data/bddk_data.db; the
existing push_to_d1.py then syncs evds_series to D1.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DB = ROOT / "data" / "bddk_data.db"

from src.tuik import parser as P  # noqa: E402
from src.tuik.client import get_client  # noqa: E402

# (download-name regex, exclude, parser, category)
TABLES = [
    (r"consumption by durability in chain linked", None,
     lambda df: P.parse_na_index(df, P.CONSUMPTION), "tuik_na"),
    (r"fixed capital formation in chain linked", None,
     lambda df: P.parse_na_index(df, P.GFCF), "tuik_na"),
    (r"Domestic Producer Price Index- Main Industrial Groupings \(2003", "Non-Domestic",
     P.parse_ppi_mig, "tuik_ppi"),
    (r"Weights for main groups and basic headings of consumer price", None,
     lambda df: P.parse_cpi_weights(df, datetime.now().year), "tuik_weight"),
]


def collect() -> list[P.Row]:
    client = get_client()
    all_rows: list[P.Row] = []
    for pattern, exclude, parse, _cat in TABLES:
        df = client.download_table(pattern, exclude)
        rows = parse(df)
        print(f"  [{pattern[:42]:42}] {len(rows):5} rows", flush=True)
        all_rows.append((rows, _cat))
    return all_rows


def write_db(blocks) -> int:
    conn = sqlite3.connect(str(DB))
    n = 0
    try:
        for rows, cat in blocks:
            conn.executemany(
                "INSERT OR REPLACE INTO evds_series(code, period_date, value, label, category) "
                "VALUES (?, ?, ?, ?, ?)",
                [(r.code, r.period_date, r.value, r.label, cat) for r in rows],
            )
            n += len(rows)
        conn.commit()
    finally:
        conn.close()
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true", help="parse + print latest values, no DB write")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    blocks = collect()
    flat = [r for rows, _ in blocks for r in rows]
    if not flat:
        print("no rows parsed — abort", file=sys.stderr)
        return 1

    if args.verify:
        # latest value per code, for eyeballing against the report
        latest: dict[str, P.Row] = {}
        for r in flat:
            if r.code not in latest or r.period_date > latest[r.code].period_date:
                latest[r.code] = r
        print("\nlatest value per code:")
        for code in sorted(latest):
            r = latest[code]
            print(f"  {code:30} {r.period_date}  {r.value:>12,.2f}")
        return 0

    written = write_db(blocks)
    print(f"\nTÜİK ingest: {written} rows across {len({r.code for r in flat})} codes → {DB.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
