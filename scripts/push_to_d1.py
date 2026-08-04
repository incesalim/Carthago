"""Push recent rows from local SQLite to Cloudflare D1.

Runs after `refresh.py` (in GitHub Actions or locally). For each table we sync,
pulls rows whose `downloaded_at` is within the last N hours (default 48) and
INSERT OR REPLACEs them into D1 via `wrangler d1 execute --remote --file=...`.

INSERT OR REPLACE is idempotent — re-running is safe; existing rows get
overwritten with identical data.

Usage:
    python scripts/push_to_d1.py             # default window 48h
    python scripts/push_to_d1.py --hours 168 # one week back

Env:
    CLOUDFLARE_API_TOKEN   (required) — wrangler picks this up automatically
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "bddk_data.db"
WEB = ROOT / "web"

sys.path.insert(0, str(ROOT))
from src.audit_reports.registry import AUDIT_TABLES as _AUDIT_TABLES    # noqa: E402
from src.audit_reports.schema import init_schema as _init_audit_schema  # noqa: E402
from src.earnings.schema import init_schema as _init_earnings_schema    # noqa: E402
from src.faaliyet.schema import init_schema as _init_faaliyet_schema    # noqa: E402
from src.kap.schema import init_schema as _init_kap_schema              # noqa: E402
from src.news._htmltext import fix_mojibake                            # noqa: E402
from src.news.schema import init_schema as _init_news_schema            # noqa: E402
from src.nonbank.schema import init_schema as _init_nonbank_schema      # noqa: E402
from src.products.schema import init_schema as _init_products_schema    # noqa: E402
from src.rates.schema import init_schema as _init_rates_schema          # noqa: E402
from src.tefas.schema import init_schema as _init_tefas_schema          # noqa: E402
from src.tkbb.schema import init_acquisition_schema as _init_tkbb_acq_schema  # noqa: E402
from src.tkbb.schema import init_schema as _init_tkbb_schema            # noqa: E402

# Tables whose text values get a final mojibake repair before D1 (Turkish text
# from scrapers / LLM; "Ã/Å/Ä" only ever appear there as mis-encoding).
_MOJIBAKE_TABLES = {"news_items", "regulation_briefings"}

# Tables to sync. Each entry: (table_name, has_downloaded_at)
# We only sync tables that have a `downloaded_at` column for incremental
# filtering. Reference tables (bank_types, table_definitions) rarely change
# and were loaded by the initial migration.
SYNC_TABLES = [
    "balance_sheet",
    "income_statement",
    "loans",
    "deposits",
    "financial_ratios",
    "other_data",
    "weekly_series",
    "nonbank_balance_sheet",
    "bank_audit_balance_sheet",
    "bank_audit_profit_loss",
    "bank_audit_oci",
    "bank_audit_cash_flow",
    "bank_audit_equity_change",
    "bank_audit_credit_quality",
    "bank_audit_profile",
    "bank_audit_loans_by_sector",
    "bank_audit_npl_movement",
    "bank_audit_opinion",
    "bank_audit_free_provision",
    "bank_audit_prose",
    "bank_audit_stages",
    "bank_audit_capital",
    "bank_audit_liquidity",
    "bank_audit_fx_position",
    "bank_audit_repricing",
    "bank_audit_validation",
    "bank_audit_extractions",
    "bank_audit_pl_roles",
    "evds_series",
    "news_items",
    "news_item_banks",
    "regulation_briefings",
    "bank_earnings",
    "bank_call_transcripts",
    "tbb_digital_stats",
    "tbb_acquisition_stats",
    "tkbb_digital_stats",
    "tkbb_acquisition_stats",
    "kap_ownership",
    "bank_advertised_rates",
    "product_attributes",
    "bank_products",
    "bank_product_profile",
    "release_calendar",
    "faaliyet_franchise",
    "faaliyet_extractions",
    "tefas_manager_daily",
    "tefas_category_daily",
    "tefas_allocation_daily",
    "tefas_top_funds",
    "bank_audit_expected",
    "bank_audit_statement_types",
    "bank_audit_coverage",
    "api_series",
]

# Precomputed rollups with no per-row timestamp: scripts/sync_audit_expected.py
# (and scripts/build_api_catalog.py for api_series) rebuild them wholesale, so
# the push clears the D1 table and re-inserts every row (a `--hours` window
# doesn't apply). Pushed only when named in --only-tables.
_FULL_REBUILD = {
    "bank_audit_expected",
    "bank_audit_statement_types",
    "bank_audit_coverage",
    "api_series",
}

# Named table groups for --table-set, so a caller can say "the audit lane's
# tables" instead of hand-listing them. The audit lane pushes all of its tables
# or none: a hand-written subset in a workflow is exactly how bank_audit_fx_position
# and bank_audit_repricing stopped reaching D1 while still being extracted,
# validated and snapshotted every quarter.
_TABLE_SETS: dict[str, list[str]] = {"audit": _AUDIT_TABLES}

# Full-rebuild tables emit `DELETE FROM t; INSERT …` for EVERY row, and D1 bills
# rows written — DELETEs included, index maintenance included (~3.6x per logical
# row measured on this database). `api_series` alone is 19,787 rows, rebuilt on
# the DAILY bulletin cron: ~40k logical writes a day for a catalogue that only
# changes when BDDK adds a series. `bank_audit_coverage` is 18,936 more on every
# audit and override run.
#
# So a full-rebuild table now carries a content hash. If the local rows hash to
# what was last pushed, the rebuild is skipped entirely. State lives in the
# STAGING db (which rides the R2 snapshot, pulled at the start of every workflow
# and uploaded at the end), so it persists across runs — and a fresh or reseeded
# staging db simply has no state and pushes once, which is the safe default.
_PUSH_STATE_DDL = """
CREATE TABLE IF NOT EXISTS d1_push_state (
    table_name   TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    pushed_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


# Columns that record WHEN a rebuild ran, not WHAT it produced. They must be
# excluded from the content hash or the skip can never fire: build_api_catalog
# does `DELETE FROM api_series` then re-INSERTs without naming `built_at`, so it
# takes DEFAULT CURRENT_TIMESTAMP and all 19,787 rows differ on every run even
# when the catalogue is identical. Excluding it is also the correct semantics —
# a moved build stamp is not a reason to rewrite a table in D1.
_BUILD_STAMP_COLUMNS = {"built_at", "downloaded_at", "generated_at", "synced_at"}


def content_hash(conn: sqlite3.Connection, table: str) -> str:
    """Order-independent digest of a table's meaningful contents.

    Sorted so two databases holding the same rows agree regardless of insert
    order — these rows are generated wholesale by a rebuild script and their
    physical order carries no meaning.
    """
    cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})")
            if c[1] not in _BUILD_STAMP_COLUMNS]
    if not cols:                      # a table of nothing but stamps: never skip
        return ""
    h = hashlib.sha256()
    h.update((",".join(cols) + "\n").encode())
    for row in sorted(conn.execute(f"SELECT {','.join(cols)} FROM {table}")):
        h.update(repr(row).encode())
        h.update(b"\n")
    return h.hexdigest()


def stored_hash(conn: sqlite3.Connection, table: str) -> str | None:
    conn.executescript(_PUSH_STATE_DDL)
    row = conn.execute(
        "SELECT content_hash FROM d1_push_state WHERE table_name = ?", (table,)
    ).fetchone()
    return row[0] if row else None


def record_hash(conn: sqlite3.Connection, table: str, digest: str) -> None:
    """Called only AFTER wrangler reports success — a failed push must not be
    remembered as done, or the table silently never syncs again."""
    conn.executescript(_PUSH_STATE_DDL)
    conn.execute(
        "INSERT OR REPLACE INTO d1_push_state(table_name, content_hash, pushed_at) "
        "VALUES (?, ?, CURRENT_TIMESTAMP)", (table, digest))
    conn.commit()

# Ceiling on ESTIMATED billed rows for a single push, before it refuses to run.
#
# Sized to clear every legitimate push and stop a runaway. The largest routine
# campaign is a whole-audit-corpus re-push — 440,545 rows across the audit tables
# at a ~4x index factor ≈ 1.8M billed — and the pending one-off prose push is
# ~369k rows ≈ 1.1-1.5M. 2.5M clears both with headroom. For scale: July 2026's
# three campaign days billed 12.4M, 15.1M and 9.4M, every one of them silently.
#
# This is a floor on deliberateness, not a budget: a caller who genuinely needs
# more passes --max-billed-rows, and because that lands in the workflow file the
# number is reviewable in a diff rather than discovered on the invoice.
DEFAULT_MAX_BILLED_ROWS = 2_500_000

# The per-push cap above bounds ONE invocation. It cannot bound a day: July's
# campaign days were several pushes each, and no single one of them would have
# tripped a 2.5M ceiling. So the cap also tightens when the cycle's allowance is
# already spent — read from Cloudflare's own analytics, not guessed.
#
# ⚠️ The billing cycle is the 11th → the 10th, NOT the calendar month. Reasoning
# off a calendar month has produced the wrong days-remaining twice.
D1_MONTHLY_ALLOWANCE = 50_000_000

# Once the allowance is gone every further row bills at $1/M. Routine lanes must
# keep running — freezing the whole pipeline was July's *other* mistake, and it
# cost four days of unwatched data for a bill the crons were not causing — but a
# campaign should wait for the cycle to roll over. This cap passes a daily cron
# (thousands of rows) and stops a backfill (millions).
EXHAUSTED_CYCLE_CAP = 250_000

BATCH_SIZE = 100  # rows per INSERT statement (default for skinny tables)
# news_items can carry multi-KB body_text per row — batch much smaller so a
# single INSERT statement stays under D1's SQLITE_TOOBIG limit (~1 MB).
BATCH_SIZE_PER_TABLE = {
    "news_items": 10,
    "regulation_briefings": 1,  # categories_json + raw_response are large per row
    "bank_audit_opinion": 20,  # basis_text is a multi-KB paragraph per modified row
    # A prose row IS a paragraph — ~350 rows/filing averaging 400 chars, and the
    # long ones run past 2 KB. Same SQLITE_TOOBIG reasoning as news_items.
    "bank_audit_prose": 20,
}

# Stand-in for newline chars in generated SQL literals (see fetch_recent).
# Must be a string that never occurs in real source text.
_NL_SENTINEL = "__D1_NL__"


def cycle_start(today: dt.date) -> dt.date:
    """First day of the D1 billing cycle containing `today`.

    The cycle runs the 11th → the 10th, so the period Cloudflare labels
    "Aug 2026" is Jul 11 → Aug 10. Reading it as a calendar month has twice
    produced the wrong days-remaining.
    """
    if today.day >= 11:
        return today.replace(day=11)
    prev = today.replace(day=1) - dt.timedelta(days=1)
    return prev.replace(day=11)


def cycle_rows_written(account_tag: str, token: str,
                       today: dt.date | None = None) -> int | None:
    """Rows written account-wide so far this billing cycle, or None if unknown.

    None means "could not observe" — no credentials, no network, an API change.
    The caller must treat that as unknown rather than as zero: reporting a
    missing reading as "plenty of headroom" is exactly the silent-wrong shape
    this repo keeps getting bitten by.

    ⚠️ Account-wide, not per-database. `gazelhan` is a second D1 database on this
    account and is NOT this project — it was 9.5M of July's 68.1M. That makes
    this reading conservative, which is the right direction for a spend guard.
    """
    today = today or dt.date.today()
    query = (
        "query($acc:String!,$start:Date!,$end:Date!){viewer{accounts(filter:{accountTag:$acc})"
        "{d1AnalyticsAdaptiveGroups(limit:10000,filter:{date_geq:$start,date_leq:$end})"
        "{sum{rowsWritten}}}}}"
    )
    body = json.dumps({
        "query": query,
        "variables": {"acc": account_tag,
                      "start": str(cycle_start(today)), "end": str(today)},
    }).encode()
    req = urllib.request.Request(
        "https://api.cloudflare.com/client/v4/graphql", data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.load(resp)
        groups = payload["data"]["viewer"]["accounts"][0]["d1AnalyticsAdaptiveGroups"]
    except Exception:
        return None
    return sum(g["sum"]["rowsWritten"] for g in groups)


def effective_cap(declared: int, used: int | None) -> tuple[int, str]:
    """(cap, why) — the declared cap, tightened when the cycle is spent.

    `used is None` leaves the declared cap alone: an unobservable cycle must not
    silently relax OR tighten the rule, or the guard's behaviour depends on
    whether an API answered.
    """
    # ASCII only in these strings: they reach stderr on the refusal path, and
    # stderr is NOT reconfigured to UTF-8 (only stdout is, at the top of this
    # file), so a dash here mojibakes on a Windows console. Same reason as the
    # note in resolve_tables.
    if used is None:
        return declared, "cycle usage unknown - per-push cap only"
    headroom = D1_MONTHLY_ALLOWANCE - used
    if headroom > 0:
        return declared, f"{headroom:,} rows of allowance left this cycle"
    return (min(declared, EXHAUSTED_CYCLE_CAP),
            f"allowance SPENT ({used:,}/{D1_MONTHLY_ALLOWANCE:,}) - "
            f"campaign-sized pushes are held until the cycle rolls over")


def index_count(conn: sqlite3.Connection, table: str) -> int:
    """Number of indexes SQLite maintains for `table` (0 if it is unknown here)."""
    try:
        return len(list(conn.execute(f"PRAGMA index_list({table})")))
    except sqlite3.Error:
        return 0


def billed_estimate(conn: sqlite3.Connection, table: str, rows: int,
                    full_rebuild: bool) -> int:
    """Estimate the rows D1 will BILL for writing `rows` logical rows.

    Billed rows are not logical rows. D1 counts index maintenance, and a
    full-rebuild table pays twice: once for the DELETE of what is there, once
    for the INSERT. Estimated structurally from the staging DB's own indexes,
    which is why it is an estimate and not an invoice — the D1 schema comes from
    `web/migrations/`, not from this file, so the two can differ. The measured
    whole-push multiplier on this database is ~3.6x (OPERATIONS.md, D1 write
    budget) and this lands in that range for the usual table mix.

    Used ONLY to decide whether a human authorised this much writing. Never
    reported as actual spend — read that from the Cloudflare analytics query.
    """
    per_row = 1 + index_count(conn, table)
    return rows * per_row * (2 if full_rebuild else 1)


def fetch_recent(conn: sqlite3.Connection, table: str, hours: int,
                 skip_unchanged: bool = True,
                 counts: dict[str, int] | None = None) -> list[str]:
    """Return SQL statements (INSERT OR REPLACE) for rows updated in last `hours`.

    Tables with a `downloaded_at` column are filtered by it.
    bank_audit_* tables don't have one — they're filtered by extracted_at
    in bank_audit_extractions (the parent log table).

    `counts`, when given, is populated with {table: estimated billed rows} so the
    caller can price the push before running it. Optional because the signature
    is load-bearing for tests that call this directly.
    """
    # A table absent from THIS staging DB is not an error. The two DBs hold
    # disjoint sets (see docs/OPERATIONS.md §Two staging DBs), and `api_series`
    # is built by build_api_catalog.py in the refresh lane only — it is a
    # _FULL_REBUILD table, pushed solely when named in --only-tables, so a
    # general `--hours` push has no business reading it at all. Before this
    # guard, its absence raised OperationalError and took the whole push down:
    # that is what failed the regulation briefing on 2026-07-19. Noisy, not
    # silent — an unexpectedly missing table should still be visible in the log.
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (table,)
    ).fetchone():
        print(f"  [skip] {table}: not present in this staging DB", flush=True)
        return [f"-- {table}: not present locally — skip"]

    cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})")]
    col_list = ",".join(cols)

    # Full-rebuild rollups: push every row, prefixed by a DELETE so D1 can't keep
    # rows for partitions that are no longer expected (idempotent re-sync).
    full_rebuild = table in _FULL_REBUILD
    if full_rebuild:
        where = ""
        # Cheapest possible push: none at all. Hash the local rows against what
        # was last pushed and bail if nothing moved. Costs one local table scan
        # and saves a DELETE + INSERT of every row (api_series: 19,787 rows a
        # DAY on the bulletin cron; bank_audit_coverage: 18,936 on every audit
        # run) — D1 bills all of it, DELETEs and index writes included.
        if skip_unchanged:
            digest = content_hash(conn, table)
            # `digest` is falsy only for a table with nothing but build stamps —
            # there is no content to compare, so never skip on it.
            if digest and digest == stored_hash(conn, table):
                print(f"  [skip] {table}: unchanged since last push "
                      f"({digest[:12]}…)", flush=True)
                return [f"-- {table}: full rebuild skipped — content unchanged"]
    elif "downloaded_at" in cols:
        where = f"WHERE downloaded_at >= datetime('now', '-{hours} hours')"
    elif table in ("news_items", "news_item_banks", "bank_earnings",
                   "bank_call_transcripts", "regulation_briefings"):
        where = f"WHERE fetched_at >= datetime('now', '-{hours} hours')"
    elif table == "bank_audit_extractions":
        where = f"WHERE extracted_at >= datetime('now', '-{hours} hours')"
    elif table == "bank_audit_validation":
        where = f"WHERE validated_at >= datetime('now', '-{hours} hours')"
    elif table == "bank_audit_pl_roles":
        # Derived alongside validation (revalidate_audit_db / apply_overrides
        # rebuild both for a partition together), so it windows on its own stamp.
        where = f"WHERE derived_at >= datetime('now', '-{hours} hours')"
    elif table in (
        "bank_audit_credit_quality",
        "bank_audit_profile",
        "bank_audit_opinion",
        "bank_audit_free_provision",
        "bank_audit_prose",
        "bank_audit_loans_by_sector",
        "bank_audit_npl_movement",
        "bank_audit_stages",
        "bank_audit_capital",
        "bank_audit_liquidity",
        "bank_audit_fx_position",
        "bank_audit_repricing",
        "faaliyet_franchise",
        "faaliyet_extractions",
    ):
        # These tables have their own extracted_at column (the
        # corresponding extractor writes here without touching
        # bank_audit_extractions). Filter on the local timestamp directly.
        where = f"WHERE extracted_at >= datetime('now', '-{hours} hours')"
    elif table in ("bank_audit_balance_sheet", "bank_audit_profit_loss",
                   "bank_audit_oci", "bank_audit_cash_flow", "bank_audit_equity_change"):
        # Pull rows whose (bank_ticker, period, kind) was extracted recently
        where = (
            "WHERE (bank_ticker, period, kind) IN ("
            f"  SELECT bank_ticker, period, kind FROM bank_audit_extractions "
            f"  WHERE extracted_at >= datetime('now', '-{hours} hours'))"
        )
    else:
        return [f"-- {table}: no time column, skipped"]

    n = conn.execute(f"SELECT COUNT(*) FROM {table} {where}").fetchone()[0]
    if n == 0:
        # Never emit a bare DELETE for a full-rebuild table when the LOCAL copy is
        # empty — that WIPES D1. The daily crons push from data/bddk_data.db, where
        # the bank_audit_* spine tables (coverage/expected/statement_types) exist
        # but are empty (only the audit pipeline's bank_audit.db populates them via
        # sync_audit_expected). Without this guard a daily news/EVDS push DELETEs
        # the whole coverage matrix and inserts nothing.
        return [f"-- {table}: 0 local rows — skip"
                + (" (full-rebuild: refusing to wipe D1)" if full_rebuild
                   else f" in last {hours}h")]

    if counts is not None:
        counts[table] = billed_estimate(conn, table, n, full_rebuild)

    if full_rebuild:
        out: list[str] = [f"-- {table}: full rebuild, {n} rows", f"DELETE FROM {table};"]
    else:
        out = [f"-- {table}: {n} rows from last {hours}h"]
    batch: list[str] = []
    batch_size = BATCH_SIZE_PER_TABLE.get(table, BATCH_SIZE)
    repair = table in _MOJIBAKE_TABLES
    rows_iter = conn.execute(f"SELECT {col_list} FROM {table} {where}")
    for r in rows_iter:
        vals = []
        for v in r:
            if v is None:
                vals.append("NULL")
                continue
            if isinstance(v, (int, float)):
                vals.append(str(v))
                continue
            s = fix_mojibake(str(v)) if repair else str(v)
            if "\n" in s or "\r" in s:
                # Don't embed raw newlines in the generated SQL: wrangler's
                # --file parser collapses consecutive blank lines, so '\n\n'
                # in a body (the blank line between a paragraph and a Markdown
                # table) would reach D1 as a single '\n' and the UI could no
                # longer tell blocks apart. Replace newlines with a sentinel
                # (keeps the literal single-line, so nothing collapses) and
                # rebuild them with ONE replace() call — char(10) concatenation
                # would instead blow past SQLite's 100-deep expression limit.
                s = s.replace("\r\n", "\n").replace("\r", "\n")
                s = s.replace("'", "''").replace("\n", _NL_SENTINEL)
                vals.append(f"replace('{s}', '{_NL_SENTINEL}', char(10))")
            else:
                vals.append("'" + s.replace("'", "''") + "'")
        batch.append("(" + ",".join(vals) + ")")
        if len(batch) >= batch_size:
            out.append(
                f"INSERT OR REPLACE INTO {table}({col_list}) VALUES\n"
                + ",\n".join(batch)
                + ";"
            )
            batch = []
    if batch:
        out.append(
            f"INSERT OR REPLACE INTO {table}({col_list}) VALUES\n"
            + ",\n".join(batch)
            + ";"
        )
    return out


def run_wrangler(sql_path: Path) -> int:
    """Execute the SQL file against the remote D1 database."""
    cmd = [
        "npx",
        "--yes",
        "wrangler",
        "d1",
        "execute",
        "bddk-data",
        "--remote",
        f"--file={sql_path}",
    ]
    print(f"$ {' '.join(cmd)}", flush=True)
    res = subprocess.run(cmd, cwd=str(WEB), shell=os.name == "nt")
    return res.returncode


def resolve_tables(only_tables: str | None, table_set: str | None) -> set[str] | None:
    """Resolve --only-tables / --table-set into an allow-list (None = every table).

    Raises ValueError on a name this script cannot sync. That check is the whole
    point: the filter used to be a silent intersection over SYNC_TABLES, so a
    misspelled — or simply forgotten — table pushed nothing and still exited 0.
    That is why nobody noticed refresh-audit.yml had dropped bank_audit_fx_position
    and bank_audit_repricing from its list: the rows were extracted and stored,
    the push reported success, and D1 never saw them.
    """
    if table_set and only_tables:
        raise ValueError("pass --table-set or --only-tables, not both")
    if table_set:
        return set(_TABLE_SETS[table_set])
    if not only_tables:
        return None
    names = {t.strip() for t in only_tables.split(",") if t.strip()}
    unknown = sorted(names - set(SYNC_TABLES))
    if unknown:
        # ASCII only: this goes to stderr, which (unlike stdout, line 28) is not
        # reconfigured to UTF-8, so a dash here mojibakes on a Windows console.
        raise ValueError(
            "--only-tables names table(s) this script cannot sync: "
            + ", ".join(unknown)
            + ". Fix the name, or add the table to SYNC_TABLES. A table that is "
              "not in SYNC_TABLES is NEVER pushed to D1."
        )
    return names


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=48,
                        help="Sync rows updated in the last N hours (default 48)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Generate SQL file but don't execute it")
    parser.add_argument("--force-rebuild", action="store_true",
                        help="Push full-rebuild tables (bank_audit_coverage, "
                             "api_series, …) even when their content hash says "
                             "nothing changed. Use after editing D1 directly, or "
                             "to repair drift between the staging DB and D1 — "
                             "the skip trusts that the last successful push "
                             "landed.")
    parser.add_argument("--only-tables", type=str, default=None,
                        help="Comma-separated table allow-list. "
                             "E.g. --only-tables=bank_audit_balance_sheet,bank_audit_extractions "
                             "to push just BS data when other tables (e.g. credit_quality) need a migration first.")
    parser.add_argument("--table-set", choices=sorted(_TABLE_SETS), default=None,
                        help="Push a named group instead of hand-listing tables. "
                             "'audit' = every bank_audit_* table the audit lane writes, "
                             "derived from src/audit_reports/registry.py — so a new "
                             "statement type is pushed the moment it is registered.")
    parser.add_argument("--max-billed-rows", type=int, default=DEFAULT_MAX_BILLED_ROWS,
                        help="Refuse the push if the estimated BILLED rows exceed "
                             "this (default %(default)s). Billed != logical: D1 "
                             "counts index maintenance, and a full rebuild pays for "
                             "its DELETE as well. The default clears every routine "
                             "lane and a whole-audit-corpus push, and stops a "
                             "runaway campaign. Raise it deliberately, in the "
                             "workflow file, so the cost is reviewable in the diff.")
    parser.add_argument("--no-cycle-check", action="store_true",
                        help="Skip reading this cycle's rows-written from Cloudflare. "
                             "The per-push cap still applies. Use when the analytics "
                             "API is unavailable and the push is known-small; the "
                             "reading is skipped automatically anyway when "
                             "CLOUDFLARE_API_TOKEN / CF_ACCOUNT_TAG are absent.")
    parser.add_argument("--db", type=str, default=str(DB),
                        help="SQLite staging DB to push from (default data/bddk_data.db). "
                             "The audit pipeline passes data/bank_audit.db so it can sync "
                             "the bank_audit_* tables from its own standalone snapshot.")
    args = parser.parse_args()

    db = Path(args.db)
    if not db.exists():
        print(f"ERROR: {db} not found", file=sys.stderr)
        return 1
    if not (WEB / "wrangler.jsonc").exists():
        print(f"ERROR: {WEB}/wrangler.jsonc not found", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = OFF")
    # The R2 snapshot may predate recent schema additions (new bank_audit_*
    # tables, regulation_briefings). The daily news / EVDS workflows don't
    # run any extractor that would call init_schema, so without this they
    # crash when SYNC_TABLES lists a table that's not in the snapshot. All
    # DDL is `CREATE … IF NOT EXISTS`, so it's a no-op once snapshot is current.
    _init_audit_schema(conn)
    _init_news_schema(conn)
    _init_kap_schema(conn)
    _init_tefas_schema(conn)
    _init_nonbank_schema(conn)
    _init_faaliyet_schema(conn)
    _init_earnings_schema(conn)
    _init_tkbb_schema(conn)
    _init_tkbb_acq_schema(conn)
    _init_rates_schema(conn)
    _init_products_schema(conn)

    try:
        allowed_tables = resolve_tables(args.only_tables, args.table_set)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    lines: list[str] = ["-- incremental D1 push", f"-- window: last {args.hours} hours", ""]
    if allowed_tables:
        # Echo the resolved set: the Actions log is where you confirm a lane is
        # pushing every table it extracts.
        print(f"table filter ({len(allowed_tables)}): {','.join(sorted(allowed_tables))}")
        lines.append(f"-- table filter: {sorted(allowed_tables)}")
        lines.append("")

    # Replay queued partition-shrink deletes (d1_pending_deletes outbox —
    # written by lanes whose runs replace whole partitions, e.g. KAP
    # ownership) BEFORE the inserts, so D1 can't keep orphan rows that the
    # INSERT OR REPLACE sync would never touch.
    pending = conn.execute(
        "SELECT rowid, sql FROM d1_pending_deletes ORDER BY rowid"
    ).fetchall()
    if pending:
        lines.append(f"-- d1_pending_deletes outbox: {len(pending)} statements")
        lines.extend(stmt for _, stmt in pending)
        lines.append("")

    total_inserts = 0
    rebuilt: list[str] = []   # full-rebuild tables actually emitted this run
    billed: dict[str, int] = {}
    for tbl in SYNC_TABLES:
        if allowed_tables is not None and tbl not in allowed_tables:
            continue
        block = fetch_recent(conn, tbl, args.hours,
                             skip_unchanged=not args.force_rebuild,
                             counts=billed)
        lines.extend(block)
        lines.append("")
        n_ins = sum(1 for ln in block if ln.startswith("INSERT"))
        total_inserts += n_ins
        if tbl in _FULL_REBUILD and n_ins:
            rebuilt.append(tbl)

    if total_inserts == 0 and not pending:
        print(f"no new rows in last {args.hours}h — nothing to push")
        return 0

    # Price the push BEFORE running it, and print the number every time — a cost
    # nobody sees is a cost nobody manages. July 2026 went 18.1M rows over the
    # 50M monthly allowance and the whole overage was three campaign days
    # (12.4M + 15.1M + 9.4M); none of those runs announced what they were about
    # to write, and nothing stopped them.
    est_total = sum(billed.values())

    # Second layer: what is left of THIS cycle's allowance. The per-push cap
    # cannot see that a day has already run eight pushes; this can.
    used = None
    if not args.no_cycle_check:
        acct = os.environ.get("CF_ACCOUNT_TAG") or os.environ.get("R2_ACCOUNT_ID")
        tok = os.environ.get("CLOUDFLARE_API_TOKEN")
        if acct and tok:
            used = cycle_rows_written(acct, tok)
    cap, why = effective_cap(args.max_billed_rows, used)

    print(f"\nestimated billed rows: {est_total:,}   (cap {cap:,} — {why})")
    for tbl, n in sorted(billed.items(), key=lambda kv: -kv[1])[:8]:
        if n:
            print(f"   {n:>10,}  {tbl}")
    if est_total > cap:
        print(
            f"\nREFUSING TO PUSH: estimated {est_total:,} billed rows exceeds the "
            f"{cap:,} cap.\n"
            f"  ({why})\n"
            f"  D1 bills rows WRITTEN at $1.00/M after 50M a cycle, counts index\n"
            f"  maintenance, and a full rebuild pays for its DELETE too.\n"
            f"  If this much writing is intended, say so explicitly:\n"
            f"    --max-billed-rows {est_total + est_total // 10}\n"
            f"  Putting the number in the workflow file makes the cost reviewable\n"
            f"  in the diff instead of discovered on the invoice. Cheaper first:\n"
            f"  narrow --hours, narrow --only-tables, or wait for the cycle to\n"
            f"  roll over on the 11th.",
            file=sys.stderr)
        return 3

    sql_path = Path(tempfile.gettempdir()) / "d1_incremental.sql"
    sql_path.write_text("\n".join(lines), encoding="utf-8")
    size_mb = sql_path.stat().st_size / 1024 / 1024
    print(f"generated {sql_path} ({total_inserts} INSERT batches, {size_mb:.2f} MB)")

    if args.dry_run:
        print("dry-run — skipping wrangler execute")
        return 0

    rc = run_wrangler(sql_path)
    if rc != 0:
        print(f"wrangler failed with exit code {rc}", file=sys.stderr)
        return rc
    if pending:
        conn.executemany(
            "DELETE FROM d1_pending_deletes WHERE rowid = ?",
            [(rid,) for rid, _ in pending],
        )
        conn.commit()
        print(f"cleared {len(pending)} replayed outbox deletes")
    # Only now — a failed push must not be remembered as done, or the table
    # would be skipped forever after.
    for tbl in rebuilt:
        record_hash(conn, tbl, content_hash(conn, tbl))
    print("D1 push complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
