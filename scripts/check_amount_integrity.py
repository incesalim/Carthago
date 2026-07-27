#!/usr/bin/env python3
"""Guard: no amount in the audit corpus may carry a fractional part.

BRSA financial reports print every figure as a whole number of **thousands of
Turkish lira**. The ratio disclosures (CAR, LCR, NSFR, stage coverage) are the
only fractional quantities in the lane, and they live in named ratio columns.
So in an amount column, a value like `-319.11` is not a small number — it is a
NUMBER WE MIS-READ, and by a factor of 1000.

That is not hypothetical. `extractor.parse_num` decided Turkish-vs-English
thousands notation with an anchored regex (`^\\d{1,3}(\\.\\d{3})+$`) applied to
the SIGNED string. A leading '-' failed the anchor, so a hyphen-negative with
exactly one thousands group fell through to the English branch and its '.' was
read as a decimal point:

    parse_num('-319.110')  ->  -319.11      (should be -319110)

Two groups survived on a separate clause and parenthesised negatives never
reached the sniff, which is why this only ever bit single-group
hyphen-negatives — the section-4 market-risk net-off and gap rows. Fixed
2026-07-27; this script is the invariant that would have caught it, and will
catch the next parser of its kind.

**Why an invariant and not a one-off sweep.** Every structural validator in
`src/audit_reports/validator.py` is an INTERNAL identity — assets = liabilities,
subtotal = sum of children, closing = opening + flows. A 1000x error on one cell
breaks those, but a 1000x error applied UNIFORMLY does not (that is the TEB
2026Q2 unit switch, which validated green across the board). This check does not
compare figures to each other at all: it asks whether a stored number has a
shape the source could not have printed. That is a different question, and it is
answerable per-cell with no cross-reference.

Read-only. Never writes, never re-extracts, never touches R2.

Usage:
    python scripts/check_amount_integrity.py                  # remote D1
    python scripts/check_amount_integrity.py --db data/bank_audit.db
    python scripts/check_amount_integrity.py --alert          # + Telegram/Discord

Env: CLOUDFLARE_API_TOKEN (wrangler picks it up) for the default D1 mode.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
# stderr too, not just stdout: the failure report goes to stderr and carries an
# em dash. Elsewhere in scripts/ that was handled by keeping stderr ASCII-only —
# reconfiguring is the actual fix, and costs nothing.
sys.stderr.reconfigure(encoding="utf-8")

from src.audit_reports.registry import AUDIT_TABLES  # noqa: E402
from src.audit_reports.schema import init_schema     # noqa: E402

# Columns that are legitimately fractional: they hold a RATIO or a PERCENTAGE,
# not an amount. Everything else typed REAL in an audit table is thousands of
# TL and must be integral. Keep this list exhaustive and explicit — a new ratio
# column that is NOT listed here will show up as a false positive on the first
# run after it ships, which is the failure mode we want (loud, once) rather than
# a silent widening of what the check tolerates.
RATIO_COLUMNS: dict[str, set[str]] = {
    "bank_audit_capital": {"cet1_ratio", "tier1_ratio", "capital_adequacy_ratio"},
    "bank_audit_liquidity": {"leverage_ratio", "lcr_total", "lcr_fc", "nsfr"},
    "bank_audit_stages": {"stage1_coverage", "stage2_coverage", "stage3_coverage"},
}

# A stored double never lands exactly on an integer after arithmetic, so compare
# with a tolerance. 1e-6 is far below one thousand TL (the unit) and far above
# double-rounding noise on values up to ~1e12.
TOLERANCE = 1e-6

# Pairs per generated query. D1 has a statement-size limit and a per-query time
# budget; ~70 (table, column) pairs in one UNION ALL is asking for trouble.
CHUNK = 10

# A fractional amount has exactly two causes, and they need different responses:
#
#   MIS-READ THOUSANDS SEPARATOR — "270.336.203" arriving as "270336.203", or
#     "-535.779" read down the English branch. The value is a REAL FIGURE stored
#     1000x too small, and nothing on the page or in any internal identity says
#     so. A wrong number. This alerts.
#   LEAKED NON-VALUE — a hierarchy marker, sector numbering or dipnot reference
#     ("11.3", "4.5", "1.01") that landed in an amount column. Junk, but junk
#     that reads as junk: orders of magnitude from any real figure, and no total
#     foots to it. Reported and counted, but it does not alert — it belongs to
#     the known column-alignment tails in the equity_change and loans_by_sector
#     lanes (docs/PROJECT_STATE.md), and daily-paging a backlog nobody is
#     clearing this week only teaches everyone to mute the channel.
#
# Two independent signals, either of which is enough:
#
#   (a) a 3-digit fraction — the shape of a thousands group read as decimals.
#   (b) an integer part >= 100 — BRSA hierarchy markers, sector numbering and
#       dipnot refs top out around 30 ("16.5.4", "11.3", "2.1"), so a fractional
#       value with three or more integer digits is not a marker.
#
# (a) alone is not enough, and this is the trap: a separator misread ending in
# zero ("-319.110") is stored as the double -319.11, and the trailing zero is
# gone for good — arithmetic cannot recover it, so ~10% of the class would be
# misfiled as leaks. (b) catches those, because 319 >= 100. Verified against the
# whole corpus 2026-07-27: the OR splits 67 findings 2 / 65, same as (a) alone,
# and additionally catches the trailing-zero shape (a) misses.
SEPARATOR_FRACTION_DIGITS = 3
MARKER_MAX_INTEGER_PART = 100


def fraction_digits(value: float) -> int:
    """Digits after the decimal point, noise-trimmed. .6f caps the precision so
    a double's representation error can't inflate the count."""
    return len(f"{abs(value):.6f}".rstrip("0").split(".")[1])


def is_misread_separator(value: float) -> bool:
    """True when a fractional amount looks like a real figure stored 1000x too
    small, rather than a marker that leaked into the column."""
    return (fraction_digits(value) == SEPARATOR_FRACTION_DIGITS
            or abs(value) >= MARKER_MAX_INTEGER_PART)


def amount_columns() -> list[tuple[str, str]]:
    """(table, column) for every REAL column in the audit lane that holds an
    amount. Derived from the schema, so a new statement type is swept the moment
    it is registered — never hand-listed."""
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    out: list[tuple[str, str]] = []
    for table in sorted(AUDIT_TABLES):
        skip = RATIO_COLUMNS.get(table, set())
        for row in conn.execute(f"PRAGMA table_info({table})"):
            name, decl = row[1], (row[2] or "").upper()
            if decl == "REAL" and name not in skip:
                out.append((table, name))
    conn.close()
    return out


# --- the two backends ------------------------------------------------------

def _d1(sql: str) -> list[dict]:
    """One read-only query against remote D1.

    Flattened to a single line: wrangler on Windows aborts with a libuv
    assertion when --command carries newlines. shell=True is required on Windows
    (npx is a .cmd) and must NOT be set on POSIX, where it would run `sh -c npx`
    and discard the argument list.
    """
    proc = subprocess.run(
        ["npx", "wrangler", "d1", "execute", "bddk-data", "--remote", "--json",
         "--command", " ".join(sql.split())],
        cwd=WEB, capture_output=True, text=True, encoding="utf-8",
        shell=(os.name == "nt"),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"d1 query failed: {proc.stderr[-400:]}")
    m = re.search(r"\[[\s\S]*\]", proc.stdout)
    if not m:
        raise RuntimeError(f"unparseable d1 output: {proc.stdout[:300]}")
    return json.loads(m.group(0))[0]["results"]


def _local(conn: sqlite3.Connection, sql: str) -> list[dict]:
    cur = conn.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


# --- the sweep -------------------------------------------------------------

def _fraction_predicate(col: str) -> str:
    return f"{col} IS NOT NULL AND ABS({col} - ROUND({col})) > {TOLERANCE}"


def count_offenders(query, pairs: list[tuple[str, str]]) -> dict[tuple[str, str], int]:
    """Rows with a fractional amount, per (table, column). Zero-count pairs are
    dropped so the caller only sees what is wrong."""
    found: dict[tuple[str, str], int] = {}
    for i in range(0, len(pairs), CHUNK):
        chunk = pairs[i:i + CHUNK]
        sql = " UNION ALL ".join(
            f"SELECT '{t}' AS tbl, '{c}' AS col, COUNT(*) AS n FROM {t} "
            f"WHERE {_fraction_predicate(c)}"
            for t, c in chunk
        )
        for row in query(sql):
            if int(row["n"]) > 0:
                found[(row["tbl"], row["col"])] = int(row["n"])
    return found


def fetch_offenders(query, table: str, col: str, limit: int) -> list[dict]:
    """The offending rows for one column, largest magnitude first."""
    return query(
        f"SELECT bank_ticker, period, kind, {col} AS value FROM {table} "
        f"WHERE {_fraction_predicate(col)} "
        f"ORDER BY ABS({col}) DESC LIMIT {int(limit)}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", type=str, default=None,
                    help="Sweep this local SQLite snapshot instead of remote D1 "
                         "(e.g. data/bank_audit.db).")
    ap.add_argument("--limit", type=int, default=200,
                    help="Max offending rows fetched per column (default 200). "
                         "A column with more says so in the output — it is never "
                         "truncated silently.")
    ap.add_argument("--alert", action="store_true",
                    help="Send a Telegram/Discord alert on a mis-read separator.")
    ap.add_argument("--strict", action="store_true",
                    help="Also fail on leaked non-values (the 1-2 digit class), "
                         "not just on mis-read separators.")
    args = ap.parse_args()

    if args.db:
        path = Path(args.db)
        if not path.exists():
            print(f"ERROR: {path} not found", file=sys.stderr)
            return 2
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        have = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        source = str(path)

        def query(sql: str) -> list[dict]:
            return _local(conn, sql)
    else:
        have = None  # remote: every registered table is expected to exist
        source = "remote D1 (bddk-data)"
        query = _d1

    pairs = amount_columns()
    if have is not None:
        # A snapshot legitimately predates a new table; D1 does not.
        pairs = [(t, c) for t, c in pairs if t in have]
    print(f"sweeping {len(pairs)} amount columns across "
          f"{len({t for t, _ in pairs})} tables in {source}…", flush=True)

    found = count_offenders(query, pairs)
    if not found:
        print("\nOK — every audit amount is a whole number of thousands of TL")
        return 0

    separators: list[str] = []   # wrong NUMBERS — 1000x too small
    leaks: dict[str, int] = {}   # non-values parked in an amount column
    truncated: list[str] = []
    for (table, col), n in sorted(found.items(), key=lambda kv: -kv[1]):
        rows = fetch_offenders(query, table, col, args.limit)
        if n > len(rows):
            truncated.append(f"{table}.{col}: showing {len(rows)} of {n}")
        for row in rows:
            value = float(row["value"])
            where = (f"{table}.{col}  {row['bank_ticker']:<8} {row['period']:<7} "
                     f"{row['kind']:<15} {value}")
            if is_misread_separator(value):
                separators.append(where)
            else:
                leaks[f"{table}.{col}"] = leaks.get(f"{table}.{col}", 0) + 1

    if leaks:
        print(f"\n{sum(leaks.values())} leaked non-value(s) — a marker, sector "
              f"numbering or dipnot reference stored as an amount. Not a wrong "
              f"figure; a column-alignment tail:")
        for key, n in sorted(leaks.items(), key=lambda kv: -kv[1]):
            print(f"  {key}: {n}")
    for note in truncated:
        print(f"  [truncated] {note}")

    if not separators:
        if args.strict:
            print("\n--strict: leaked non-values present", file=sys.stderr)
            return 1
        print("\nOK — no mis-read thousands separator "
              "(run with --strict to fail on the leaks above too)")
        return 0

    report = (f"{len(separators)} mis-read thousands separator(s) — the stored "
              f"figure is 1000x too small:\n" + "\n".join(f"  {s}" for s in separators))
    print("\n" + report, file=sys.stderr)
    print("\nEach is a real figure the parser read down the wrong branch. Verify "
          "against the source PDF cell (and the same figure's prior-period twin "
          "in the adjacent filing) before changing any data.", file=sys.stderr)

    if args.alert:
        sys.path.insert(0, str(ROOT / "scripts"))
        from notify import notify  # stdlib-only helper
        notify(("❌ Audit amount integrity — " + report)[:1500])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
