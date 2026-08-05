"""Push recent rows from local SQLite to Cloudflare D1.

Runs after `refresh.py` (in GitHub Actions or locally). For each table we sync,
pulls rows whose `downloaded_at` is within the last N hours (default 48) and
INSERT OR REPLACEs them into D1 via `wrangler d1 execute --remote --file=...`.

INSERT OR REPLACE is idempotent — re-running is safe; existing rows get
overwritten with identical data. Upsert alone cannot DELETE, so the audit lane's
targeted repairs use --replace-partitions: an explicit (bank|period|kind) list
whose scoped DELETEs and current rows travel in ONE guarded file, replacing the
old "clear D1, then push" two-step that stranded partitions when the second call
did not happen.

Usage:
    python scripts/push_to_d1.py             # default window 48h
    python scripts/push_to_d1.py --hours 168 # one week back

Env:
    CLOUDFLARE_API_TOKEN   (required) — wrangler picks this up automatically
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "bddk_data.db"
WEB = ROOT / "web"

sys.path.insert(0, str(ROOT))
from src.audit_reports.registry import AUDIT_TABLES as _AUDIT_TABLES    # noqa: E402
# Cycle usage lives in its own stdlib-only module so scripts/healthcheck.py can
# read it too without pulling this file's whole import chain into the
# minimal-deps health-check job.
from src.d1_usage import (  # noqa: E402
    D1_MONTHLY_ALLOWANCE,
    cycle_rows_written,
)
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
    # The analyst lane's staging tables. They live in their own DB
    # (data/analyst.db, which rides R2 as state/analyst.db.gz), so a push names
    # them with --db data/analyst.db; every other staging DB simply reports them
    # "not present" and skips.
    "analyst_signals",
    "analyst_basis_metadata",
    "analyst_notes",
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
    # Derived wholesale by scripts/analyst/detect.py from the audit corpus on
    # every run — there is no "recent row" to window on, and a signal that
    # stopped firing must disappear from D1 rather than linger. Small (455 + 1,050
    # rows today), so the content hash makes a re-run free.
    "analyst_signals",
    "analyst_basis_metadata",
    "analyst_notes",
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

# The same idea one level finer, for the windowed audit tables.
#
# The content hash above is all-or-nothing per table, which suits a small rollup
# and is useless for bank_audit_balance_sheet. Those tables are windowed on the
# extraction stamp, so a re-extraction re-pushes every row of every partition it
# touched — whether or not the extractor produced anything different. That is
# what makes a campaign expensive: re-running the fleet after an extractor fix
# re-ships partitions the fix did not change, and July's overage was campaigns.
#
# So each (table, bank_ticker|period|kind) carries a digest of its own rows, and
# a partition whose digest is unchanged is not emitted at all. State lives in the
# STAGING db, which rides the R2 snapshot, exactly like d1_push_state.
# `row_count` is what the partition held when we last pushed it. It exists so a
# SHRINKING or EMPTIED partition can price its own remote DELETE: the local rows
# are gone, so nothing else remembers how many rows D1 still holds. Legacy state
# written before this column falls back to a conservative estimate.
_PARTITION_STATE_DDL = """
CREATE TABLE IF NOT EXISTS d1_pushed_partitions (
    table_name TEXT NOT NULL,
    part_key   TEXT NOT NULL,
    digest     TEXT NOT NULL,
    row_count  INTEGER,
    PRIMARY KEY (table_name, part_key)
);
"""

# Columns recording WHEN a row was written rather than WHAT it says. Excluded
# from the partition digest for the same reason apply_overrides excludes them
# (_STAMP_COLUMNS there): a re-extraction bumps them on purpose, so including
# them would make every partition look changed and defeat the whole check.
_ROW_STAMP_COLUMNS = {"extracted_at", "validated_at", "derived_at", "downloaded_at"}

_PART_KEY = ("bank_ticker", "period", "kind")

# Tables the partition skip must NOT apply to.
#
# `bank_audit_extractions` is the extraction LOG: its job is to record that an
# extraction ran, and `extracted_at` is the fact it exists to carry. That column
# is excluded from every digest (it is what a re-extraction bumps on purpose), so
# skipping this table would leave D1's log frozen at the previous run while the
# rows it describes had genuinely been re-extracted — the audit trail quietly
# disagreeing with the audit. It is 1,050 rows; pushing it always is cheap and
# correct. `/admin` reads MAX(extracted_at) from it for the audit panel's age.
_NO_PARTITION_SKIP = {"bank_audit_extractions"}


# Columns that record WHEN a rebuild ran, not WHAT it produced. They must be
# excluded from the content hash or the skip can never fire: build_api_catalog
# does `DELETE FROM api_series` then re-INSERTs without naming `built_at`, so it
# takes DEFAULT CURRENT_TIMESTAMP and all 19,787 rows differ on every run even
# when the catalogue is identical. Excluding it is also the correct semantics —
# a moved build stamp is not a reason to rewrite a table in D1.
#
# `fired_at` is here for exactly the same reason and it is the easiest to miss:
# detect.py's INSERT OR REPLACE omits the column, so every re-run takes DEFAULT
# CURRENT_TIMESTAMP on every signal even when the detector found precisely what
# it found yesterday. Left in the hash, the analyst tables would rebuild daily
# forever — the EVDS bug in miniature. Excluding it also gives D1's `fired_at`
# the better meaning: when this signal FIRST fired, not when the detector last ran.
_BUILD_STAMP_COLUMNS = {"built_at", "downloaded_at", "generated_at", "synced_at",
                        "fired_at"}


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
# off a calendar month has produced the wrong days-remaining twice. The allowance
# and the reading itself live in src/d1_usage.py, imported above.

# Once the allowance is gone every further row bills at $1/M. Routine lanes must
# keep running — freezing the whole pipeline was July's *other* mistake, and it
# cost four days of unwatched data for a bill the crons were not causing — but a
# campaign should wait for the cycle to roll over. This cap passes a daily cron
# (thousands of rows) and stops a backfill (millions).
EXHAUSTED_CYCLE_CAP = 250_000

# D1 rejects any SQL statement over 100,000 bytes with SQLITE_TOOBIG. We build
# multi-row INSERTs, so the batcher flushes on BYTES as well as on row count and
# keeps a margin: a statement is measured before D1 sees it, but the margin
# covers the difference between our accounting and the server's.
D1_MAX_SQL_BYTES = 100_000
_SAFE_STMT_BYTES = 90_000

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
    # One row is a WHOLE earnings call: median 30k chars, max 67,710 measured
    # over the 144-call corpus. D1's maximum SQL statement is 100,000 bytes, so
    # anything above a batch of one risks SQLITE_TOOBIG — and at the default 100
    # it is certain, which is how the first push of this lane failed. One row per
    # statement still leaves ~30% headroom on the largest call for quote-doubling
    # and the newline sentinel.
    "bank_call_transcripts": 1,
}

# Stand-in for newline chars in generated SQL literals (see fetch_recent).
# Must be a string that never occurs in real source text.
_NL_SENTINEL = "__D1_NL__"


def has_partition_key(conn: sqlite3.Connection, table: str) -> bool:
    cols = {c[1] for c in conn.execute(f"PRAGMA table_info({table})")}
    return set(_PART_KEY) <= cols


def partition_digests(conn: sqlite3.Connection, table: str,
                      where: str) -> dict[str, str]:
    """{`bank|period|kind`: digest} over the rows this push would send.

    One streaming pass that builds only hashes — no row text — so memory is a few
    dozen bytes per partition regardless of how many rows are in the window.
    """
    cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})")
            if c[1] not in _ROW_STAMP_COLUMNS]
    key = ", ".join(_PART_KEY)
    out: dict[str, hashlib._Hash] = {}
    # ORDER BY the key so a partition's rows arrive together; the digest is order
    # sensitive within a partition, which is fine — these rows are written by one
    # extractor pass and re-read in the same order.
    for row in conn.execute(
        f"SELECT {key}, {', '.join(cols)} FROM {table} {where} ORDER BY {key}"
    ):
        part = "|".join("" if v is None else str(v) for v in row[:3])
        h = out.get(part)
        if h is None:
            h = out[part] = hashlib.sha256()
            h.update((",".join(cols) + "\n").encode())
        h.update(repr(row[3:]).encode())
        h.update(b"\n")
    return {k: v.hexdigest() for k, v in out.items()}


def partition_deletes(table: str, parts: list[str]) -> list[str]:
    """Scoped DELETEs for `parts`, chunked to stay under D1's statement limit.

    One statement per push would be simpler and is fine today — 1,050 partitions
    is 38 KB against a 100,000-byte ceiling. But the fleet gains 76 partitions
    every quarter (38 banks x 2 bases), so a single statement crosses the limit
    in a few years and would fail exactly the way the transcripts push did:
    remotely, with a bare SQLITE_TOOBIG. Chunking now costs nothing.
    """
    key = ", ".join(_PART_KEY)
    head = f"DELETE FROM {table} WHERE ({key}) IN (VALUES "
    out: list[str] = []
    batch: list[str] = []
    size = len(head.encode("utf-8"))
    for p in parts:
        tup = "(" + ",".join("'" + f.replace("'", "''") + "'"
                             for f in p.split("|")) + ")"
        b = len(tup.encode("utf-8")) + 2
        if batch and size + b > _SAFE_STMT_BYTES:
            out.append(head + ", ".join(batch) + ");")
            batch, size = [], len(head.encode("utf-8"))
        batch.append(tup)
        size += b
    if batch:
        out.append(head + ", ".join(batch) + ");")
    return out


def _ensure_partition_state(conn: sqlite3.Connection) -> None:
    conn.executescript(_PARTITION_STATE_DDL)
    # State written before row_count existed: add it rather than rebuild, so a
    # staging DB carrying digests keeps them (rebuilding would re-push everything).
    cols = {c[1] for c in conn.execute("PRAGMA table_info(d1_pushed_partitions)")}
    if "row_count" not in cols:
        conn.execute("ALTER TABLE d1_pushed_partitions ADD COLUMN row_count INTEGER")
        conn.commit()


def stored_partition_digests(conn: sqlite3.Connection, table: str) -> dict[str, str]:
    _ensure_partition_state(conn)
    return {
        r[0]: r[1] for r in conn.execute(
            "SELECT part_key, digest FROM d1_pushed_partitions WHERE table_name = ?",
            (table,))
    }


def stored_partition_rows(conn: sqlite3.Connection, table: str) -> dict[str, int]:
    """{partition: rows D1 holds for it}. Missing/legacy entries are absent, and
    callers must fall back conservatively rather than treat them as zero."""
    _ensure_partition_state(conn)
    return {
        r[0]: r[1] for r in conn.execute(
            "SELECT part_key, row_count FROM d1_pushed_partitions "
            "WHERE table_name = ? AND row_count IS NOT NULL", (table,))
    }


def record_partition_digests(conn: sqlite3.Connection, table: str,
                             digests: dict[str, str],
                             rows: dict[str, int] | None = None,
                             dropped: list[str] | None = None) -> None:
    """Called only AFTER wrangler reports success — a remembered-but-failed push
    would skip those partitions forever, which is the silent-wrong failure this
    whole mechanism has to avoid being.

    `dropped` are partitions the push DELETED and did not re-insert (they now hold
    no rows locally). Their state is removed, not rewritten: keeping a digest for
    a partition that no longer exists would resurrect it as "unchanged" forever.
    """
    _ensure_partition_state(conn)
    rows = rows or {}
    conn.executemany(
        "INSERT OR REPLACE INTO d1_pushed_partitions"
        "(table_name, part_key, digest, row_count) VALUES (?, ?, ?, ?)",
        [(table, k, d, rows.get(k)) for k, d in digests.items()])
    if dropped:
        conn.executemany(
            "DELETE FROM d1_pushed_partitions WHERE table_name = ? AND part_key = ?",
            [(table, k) for k in dropped])
    conn.commit()


# A queued outbox statement is only safe to price as one row if it can be PROVEN
# to touch at most one. `WHERE` alone proves nothing: `DELETE FROM t WHERE 1=1`
# has a WHERE and empties the table, and it was accepted and priced at 3.
_OUTBOX_DELETE_RX = re.compile(
    r"^\s*DELETE\s+FROM\s+([A-Za-z_][A-Za-z0-9_]*)\s+WHERE\s+(.+?)\s*;?\s*$",
    re.I | re.S)
_EQ_TERM_RX = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*('(?:[^']|'')*'|-?\d+(?:\.\d+)?)\s*$")


def outbox_delete_rows(conn: sqlite3.Connection, stmt: str) -> tuple[str, int] | None:
    """(table, 1) if `stmt` provably deletes at most one row, else None.

    The consumer must fail closed rather than trust producers. Today's three
    (`news.bank_tagger`, `tefas.loader`, `update_kap_ownership`) each emit one
    full-primary-key DELETE per statement, but nothing enforced that, and an
    unbounded statement would blow the budget while the guard priced it as one
    row. Proof requires: exactly one DELETE, a table that exists, and every
    primary-key column pinned by `col = <literal>` with nothing but AND between
    them — no OR, no ranges, no unparsed syntax.
    """
    body = stmt.strip()
    if body.count(";") > (1 if body.endswith(";") else 0):
        return None                                   # more than one statement
    m = _OUTBOX_DELETE_RX.match(body)
    if not m:
        return None
    table, where = m.group(1), m.group(2)
    if re.search(r"\bOR\b|\bIN\b|\bLIKE\b|\bNOT\b|--|/\*|\(|\)|<|>|!", where, re.I):
        return None
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (table,)).fetchone():
        return None
    pinned = set()
    for term in re.split(r"\bAND\b", where, flags=re.I):
        t = _EQ_TERM_RX.match(term)
        if not t:
            return None
        pinned.add(t.group(1))
    pk = {c[1] for c in conn.execute(f"PRAGMA table_info({table})") if c[5]}
    if not pk or not pk <= pinned:
        return None                                   # partial key: many rows
    return table, 1


def remote_partition_rows(table: str, parts: list[str]) -> dict[str, int] | None:
    """Ask D1 how many rows it holds for each partition, or None if it cannot say.

    Needed only when a partition must be DELETED remotely and nothing local can
    say how big it is — an emptied partition whose stored state predates
    `row_count`. Guessing there is not acceptable: the guard would price a
    100-row delete as one row. Rows READ are a thousandth the price of rows
    written, so asking is always cheaper than being wrong about writing.

    Returns None on any failure; the caller must refuse rather than assume.
    """
    if not parts:
        return {}
    keys = ", ".join(
        "(" + ",".join("'" + f.replace("'", "''") + "'" for f in p.split("|")) + ")"
        for p in parts)
    sql = (f"SELECT bank_ticker || '|' || period || '|' || kind AS p, "
           f"COUNT(*) AS n FROM {table} "
           f"WHERE ({', '.join(_PART_KEY)}) IN (VALUES {keys}) GROUP BY p")
    cmd = ["npx", "--yes", "wrangler", "d1", "execute", "bddk-data", "--remote",
           "--json", "--command", sql]
    try:
        res = subprocess.run(cmd, cwd=str(WEB), shell=os.name == "nt",
                             capture_output=True, text=True, timeout=120)
        if res.returncode != 0:
            return None
        m = re.search(r"\[\s*\{.*\}\s*\]", res.stdout, re.S)
        rows = json.loads(m.group(0))[0]["results"]
    except Exception:
        return None
    counts = {r["p"]: r["n"] for r in rows}
    # A partition D1 does not know about holds nothing — that is an answer.
    return {p: counts.get(p, 0) for p in parts}


def touched_partitions(conn: sqlite3.Connection, hours: int) -> set[str] | None:
    """Partitions re-extracted inside the window, from the lane's own log.

    This is the ONLY reliable way to see a partition that now holds ZERO rows:
    it has nothing left in its own table to be found by, so a comparison against
    rows currently present can never notice it. Scoping to the log's window is
    what keeps that safe — comparing every stored key against a windowed view of
    the table would delete historical partitions that are simply out of window.

    None when the log is absent (a non-audit staging DB): the caller then skips
    emptied-partition detection entirely rather than guessing.
    """
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='bank_audit_extractions'"
    ).fetchone():
        return None
    return {
        "|".join("" if v is None else str(v) for v in r)
        for r in conn.execute(
            "SELECT bank_ticker, period, kind FROM bank_audit_extractions "
            f"WHERE extracted_at >= datetime('now', '-{hours} hours')")
    }


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
    if headroom <= 0:
        return (min(declared, EXHAUSTED_CYCLE_CAP),
                f"allowance SPENT ({used:,}/{D1_MONTHLY_ALLOWANCE:,}) - "
                f"campaign-sized pushes are held until the cycle rolls over")
    # Positive headroom is not a blank cheque. Returning the full declared cap
    # here let a 2.5M push through on 100k of remaining allowance and sail 2.4M
    # past it — the guard would have "passed" the very run that blew the budget.
    # The floor keeps routine lanes working when headroom is nearly gone, which
    # is the same trade EXHAUSTED_CYCLE_CAP makes: crons run, campaigns wait.
    cap = min(declared, max(headroom, EXHAUSTED_CYCLE_CAP))
    if cap < declared:
        return cap, (f"only {headroom:,} rows of allowance left this cycle - "
                     f"cap tightened from {declared:,}")
    return declared, f"{headroom:,} rows of allowance left this cycle"


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
                 counts: dict[str, int] | None = None,
                 digests: dict[str, dict[str, str]] | None = None,
                 skip_partitions: bool = False,
                 resend: bool = False,
                 rowcounts: dict[str, dict[str, int]] | None = None,
                 dropped: dict[str, list[str]] | None = None,
                 replace: set[str] | None = None,
                 remote_rows: Callable[[str, list[str]], dict[str, int] | None]
                 | None = None) -> list[str]:
    """Return SQL statements (INSERT OR REPLACE) for rows updated in last `hours`.

    Tables with a `downloaded_at` column are filtered by it.
    bank_audit_* tables don't have one — they're filtered by extracted_at
    in bank_audit_extractions (the parent log table).

    `counts`, when given, is populated with {table: estimated billed rows} so the
    caller can price the push before running it. `digests`, when given, collects
    {table: {partition: digest}} for the partitions actually emitted, so main()
    can record them AFTER wrangler succeeds. Both are optional because this
    signature is load-bearing for tests that call it with three arguments.
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
    # `_NO_PARTITION_SKIP` suppresses the digest SKIP, never explicit selection:
    # a caller naming AKBNK must not have GARAN's extraction-log row swept in by
    # the time window, nor that table left without a scoped DELETE.
    exempt_from_skip = table in _NO_PARTITION_SKIP and replace is None
    partition_mode = ((skip_partitions or replace is not None)
                      and not full_rebuild and digests is not None
                      and not exempt_from_skip
                      and has_partition_key(conn, table))
    if replace is not None and partition_mode:
        # Explicit selection replaces the time window outright: the caller says
        # which partitions it owns, so a row whose stamp falls outside the window
        # is still part of the partition being replaced.
        keys = ", ".join(
            "(" + ",".join("'" + f.replace("'", "''") + "'" for f in p.split("|")) + ")"
            for p in sorted(replace))
        where = f"WHERE ({', '.join(_PART_KEY)}) IN (VALUES {keys})"
        n = conn.execute(f"SELECT COUNT(*) FROM {table} {where}").fetchone()[0]
    # A partition emptied by re-extraction has NO rows left, so `n` can be 0 while
    # D1 still holds everything it used to. Returning here would strand it, which
    # is exactly what happened before: the log even printed "none changed".
    if n == 0 and not partition_mode:
        # Never emit a bare DELETE for a full-rebuild table when the LOCAL copy is
        # empty — that WIPES D1. The daily crons push from data/bddk_data.db, where
        # the bank_audit_* spine tables (coverage/expected/statement_types) exist
        # but are empty (only the audit pipeline's bank_audit.db populates them via
        # sync_audit_expected). Without this guard a daily news/EVDS push DELETEs
        # the whole coverage matrix and inserts nothing.
        return [f"-- {table}: 0 local rows — skip"
                + (" (full-rebuild: refusing to wipe D1)" if full_rebuild
                   else f" in last {hours}h")]

    # Drop partitions whose rows are byte-identical to what we last pushed. This
    # is what makes a re-extraction campaign cost what it actually changed rather
    # than what it touched: the window says "this partition was re-extracted",
    # the digest says whether the re-extraction produced anything different.
    part_delete: list[str] | None = None
    del_rows = 0
    if partition_mode:
        current = partition_digests(conn, table, where)
        stored = stored_partition_digests(conn, table)
        stored_rows = stored_partition_rows(conn, table)
        # A partition we have never pushed has no stored digest and is therefore
        # always sent — the safe default when the state is missing or reseeded.
        changed = {k: v for k, v in current.items()
                   if resend or replace is not None or stored.get(k) != v}
        # Digest equality is the ONLY licence to treat the local row count as the
        # remote one. A 100-row partition shrunk to 1 has a DIFFERENT digest, so
        # its single local row says nothing about what D1 still holds.
        digest_matched = {k for k, v in current.items() if stored.get(k) == v}

        if replace is not None:
            # EXPLICIT REPLACEMENT. The caller named the partitions, so selection
            # does not go through the window or the extraction log at all — a
            # partition is replaced because it was asked for, including one that
            # now holds zero rows locally and one the log has never heard of.
            emptied = sorted(p for p in replace if p not in current)
        else:
            # Partitions the log says were re-extracted, which now hold NO rows:
            # D1 still has their old contents and nothing local can point at
            # them. Scoped to the window via the log, so historical partitions
            # that are merely out of window are never touched.
            touched = touched_partitions(conn, hours)
            emptied = sorted(
                k for k in stored
                if k not in current and (touched is None or k in touched)
            ) if touched is not None else []

        if not changed and not emptied:
            print(f"  [skip] {table}: {len(current)} partition(s) in window, "
                  f"none changed", flush=True)
            return [f"-- {table}: {len(current)} partitions in window, "
                    f"none changed — nothing to push"]

        # Every partition the push is about to replace or remove. Deleting only
        # the changed ones would leave an emptied partition's rows in D1 forever.
        to_delete = sorted(set(changed) | set(emptied))
        if len(changed) < len(current) or emptied:
            print(f"  [part] {table}: {len(changed)}/{len(current)} changed"
                  + (f", {len(emptied)} emptied" if emptied else ""), flush=True)
        if changed:
            keys = ", ".join(
                "(" + ",".join("'" + p.replace("'", "''") + "'"
                               for p in k.split("|")) + ")"
                for k in sorted(changed))
            where += f" AND ({', '.join(_PART_KEY)}) IN (VALUES {keys})"
        else:
            where += " AND 1 = 0"          # delete-only push: insert nothing
        n = conn.execute(f"SELECT COUNT(*) FROM {table} {where}").fetchone()[0]

        # DELETE the affected partitions in the SAME statement file as their
        # INSERTs. Without this the push only ever upserts, so a row the
        # re-extraction REMOVED survives in D1 — and then its partition's digest
        # is recorded as synced, so every later push skips a partition that has
        # silently diverged. Emitting the delete here also means the push is
        # self-contained: wrangler runs the file as one unit and rolls the whole
        # thing back on failure, so a partition is never left cleared-but-empty.
        part_delete = partition_deletes(table, to_delete)
        # What D1 will actually delete — the rows it HOLDS, not the rows we hold.
        # A shrinking or emptied partition has fewer (or none) locally, so pricing
        # off the local count understates the bill.
        #
        # Three sources, in order of trust:
        #   1. the recorded row_count from the last push;
        #   2. the LOCAL count, when the partition still has rows AND its digest
        #      matched — digest equality means local and remote agree, so the
        #      local count is the remote count. This backfills legacy state
        #      without a network call;
        #   3. D1 itself, for a partition being deleted whose size nothing local
        #      knows — an emptied partition recorded before row_count existed.
        # There is deliberately no fourth. Assuming a number here is how a 100-row
        # delete gets priced as one row, and the guard then waves through the very
        # push it exists to stop.
        # Probing is part of PRICING and nothing else. When no estimate was
        # requested there is nothing to price, so no remote call is made — that
        # is what keeps the unit suite offline. `remote_rows` is injected rather
        # than reached for directly, so a test cannot launch npx by omission.
        if counts is not None:
            local_rows = {
                k: conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE "
                    + " AND ".join(f"{c} = ?" for c in _PART_KEY), k.split("|")
                ).fetchone()[0] for k in to_delete
            }
            unknown = [k for k in to_delete
                       if k not in stored_rows and k not in digest_matched]
            if unknown:
                probed = remote_rows(table, unknown) if remote_rows else None
                if probed is None:
                    raise RuntimeError(
                        f"{table}: cannot price the DELETE of {len(unknown)} "
                        f"partition(s) — no recorded row_count, no digest proving "
                        f"the local count matches D1, and no usable remote reader. "
                        f"Refusing rather than guessing; a wrong guess defeats the "
                        f"cost guard. No flag bypasses this: the number is unknown, "
                        f"not merely large. Retry when D1 is reachable, or record "
                        f"the sizes by pushing once with --resend-partitions."
                    )
                stored_rows = {**stored_rows, **probed}
            del_rows = sum(
                stored_rows[k] if k in stored_rows else local_rows.get(k, 0)
                for k in to_delete)
        digests[table] = changed
        if rowcounts is not None:
            rowcounts[table] = {
                k: conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE "
                    + " AND ".join(f"{c} = ?" for c in _PART_KEY), k.split("|")
                ).fetchone()[0] for k in changed
            }
        if dropped is not None and emptied:
            dropped[table] = emptied

    if counts is not None:
        # Skip mode emits DELETE *and* INSERT, and D1 bills both (plus index
        # maintenance on each). Pricing only the insert side understated a
        # partition replacement by half, and an emptied partition — all delete,
        # no insert — priced at zero.
        counts[table] = billed_estimate(conn, table, n + del_rows, full_rebuild)

    if full_rebuild:
        out: list[str] = [f"-- {table}: full rebuild, {n} rows", f"DELETE FROM {table};"]
    elif part_delete:
        out = [f"-- {table}: {n} rows in {len(digests[table])} changed partition(s)",
               *part_delete]
        if not n:
            return out          # delete-only: an emptied partition, nothing to insert
    else:
        out = [f"-- {table}: {n} rows from last {hours}h"]
    batch: list[str] = []
    batch_size = BATCH_SIZE_PER_TABLE.get(table, BATCH_SIZE)
    header = f"INSERT OR REPLACE INTO {table}({col_list}) VALUES\n"
    header_bytes = len(header.encode("utf-8"))
    batch_bytes = header_bytes

    def flush() -> None:
        nonlocal batch, batch_bytes
        if batch:
            out.append(header + ",\n".join(batch) + ";")
            batch = []
            batch_bytes = header_bytes

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
        row_sql = "(" + ",".join(vals) + ")"
        row_bytes = len(row_sql.encode("utf-8")) + 2   # + the ",\n" separator

        # Flush BEFORE adding a row that would carry the statement past D1's hard
        # limit. The per-table row counts above are a hint tuned by hand, and a
        # hand-tuned hint drifts: bank_call_transcripts had none, so it batched
        # at the default 100 with a MEDIAN row of 30k chars and the lane's first
        # push died on SQLITE_TOOBIG. Sizing the batch by bytes handles every
        # table, including ones not listed above — EXCEPT a single row that is
        # itself over the ceiling, which no batch size can fix and which the
        # check below rejects explicitly rather than shipping a doomed file.
        if batch and batch_bytes + row_bytes > _SAFE_STMT_BYTES:
            flush()
        # A single row can exceed the ceiling on its own, and flushing cannot
        # help — the batch is already empty. D1 caps a STATEMENT at 100,000 bytes
        # while allowing a 2 MB row, so a value in between simply cannot travel
        # in a VALUES statement. Emitting it anyway produced a doomed file that
        # failed remotely with a bare SQLITE_TOOBIG naming neither table nor row.
        # Fail here instead, pointing at the offending row.
        if not batch and header_bytes + row_bytes > D1_MAX_SQL_BYTES:
            key = ", ".join(
                f"{c}={v!r}" for c, v in zip(cols, r)
                if c in _PART_KEY or c.endswith("_id") or c == "period_date")
            raise ValueError(
                f"{table}: one row is {row_bytes:,} bytes of SQL, over D1's "
                f"{D1_MAX_SQL_BYTES:,}-byte statement limit, so it cannot be sent "
                f"in an INSERT ... VALUES at any batch size. Row: {key or r[:3]!r}. "
                f"Store the oversized value in R2 and keep a reference in D1, or "
                f"split the column."
            )
        batch.append(row_sql)
        batch_bytes += row_bytes
        if len(batch) >= batch_size:
            flush()
    flush()
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
    parser.add_argument("--skip-unchanged-partitions", action="store_true",
                        help="Skip partitions whose rows are byte-identical to what "
                             "was last pushed (a fleet re-extraction then costs what "
                             "it CHANGED, not what it touched). OFF BY DEFAULT and "
                             "deliberately so: several callers clear the partitions "
                             "in D1 BEFORE invoking this script, and a skip after "
                             "such a clear would leave them empty. Only pass it "
                             "where nothing else mutates D1 first — the push then "
                             "emits its own scoped DELETE and owns the partition "
                             "end to end.")
    parser.add_argument("--resend-partitions", action="store_true",
                        help="Resend every partition in the window and leave the "
                             "digest state current — the deliberate-repair mode, "
                             "for when D1 was edited by hand. Implies the "
                             "self-contained DELETE+INSERT path, so unlike simply "
                             "omitting --skip-unchanged-partitions it does not "
                             "leave the next opt-in run re-pushing everything.")
    parser.add_argument("--replace-partitions", type=str, default=None,
                        help="Path to a file of `bank|period|kind` lines. Those "
                             "partitions are REPLACED: one scoped DELETE plus the "
                             "current local rows, in a single guarded wrangler "
                             "file. Selection is explicit — the time window and "
                             "the extraction log are not consulted — so a "
                             "partition that now holds zero rows is still cleared "
                             "remotely. This is the interface every targeted "
                             "correction tool uses INSTEAD of clearing D1 itself "
                             "and then pushing, which left the rows gone whenever "
                             "the second call did not happen.")
    parser.add_argument("--check-only", action="store_true",
                        help="Generate the SQL and apply the cost guard, then exit "
                             "WITHOUT executing: 0 if the push would be affordable, "
                             "3 if it would be refused. Callers that DELETE "
                             "partitions in D1 before pushing must run this first, "
                             "or a refusal lands after the rows are already gone.")
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

    replace: set[str] | None = None
    if args.replace_partitions:
        replace = {
            ln.strip() for ln in
            Path(args.replace_partitions).read_text(encoding="utf-8").splitlines()
            if ln.strip()
        }
        if not replace:
            print("no partitions listed to replace — nothing to push")
            return 0
        bad = sorted(p for p in replace if len(p.split("|")) != 3)
        if bad:
            print(f"ERROR: malformed partition key(s), expected bank|period|kind: "
                  f"{bad[:5]}", file=sys.stderr)
            return 2
        print(f"replacing {len(replace)} partition(s)")
        # Replacement MUST name its tables. Without a filter the main loop walks
        # every sync table, and the ones without (bank_ticker, period, kind)
        # quietly keep their ordinary window or full-rebuild behaviour — an
        # AKBNK replacement emitted an unrelated recent `loans` row that way.
        # "Replace these partitions" has to mean only that.
        if allowed_tables is None:
            print("ERROR: --replace-partitions requires an explicit table scope "
                  "(--only-tables or --table-set). Without one this would also "
                  "push every other table's ordinary window.", file=sys.stderr)
            return 2
        probe = sqlite3.connect(str(db))
        try:
            missing, unsupported = [], []
            for t in sorted(allowed_tables):
                if t in _FULL_REBUILD:
                    unsupported.append(t)
                elif not probe.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (t,)).fetchone():
                    missing.append(t)
                elif not has_partition_key(probe, t):
                    unsupported.append(t)
        finally:
            probe.close()
        # A table absent from the staging DB is fine for a WINDOWED push — the
        # two staging DBs hold disjoint sets — but in replacement mode it means
        # the repair silently did nothing. Reproduced: replacing into an empty
        # DB logged "not present in this staging DB" and exited 0, a successful
        # repair that repaired nothing. A PRESENT but empty partition-capable
        # table is different and stays valid: that is a DELETE-only replacement.
        if missing:
            print(f"ERROR: these tables are not in {db} and cannot be replaced: "
                  f"{missing}. Replacement names what it owns, so a missing table "
                  f"is an error, not a skip — otherwise the run reports success "
                  f"having done nothing. Check --db and the table scope.",
                  file=sys.stderr)
            return 2
        if unsupported:
            print(f"ERROR: these tables cannot honour partition replacement: "
                  f"{unsupported}. A full-rebuild rollup has no partition key and "
                  f"a table without (bank_ticker, period, kind) cannot be scoped, "
                  f"so both would silently fall back to window or full-rebuild "
                  f"behaviour. Drop them from the table scope.", file=sys.stderr)
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
    billed_pending: dict[str, int] = {}
    # Explicit replacement replays NOTHING from the outbox: those entries belong
    # to other lanes and other partitions, and smuggling them into a targeted
    # repair is the opposite of explicit scope. They stay queued for their lane.
    pending = [] if replace is not None else conn.execute(
        "SELECT rowid, sql FROM d1_pending_deletes ORDER BY rowid"
    ).fetchall()
    if pending:
        # These execute, so they must be priced. The outbox contract is one
        # PK-scoped row per statement (tefas_top_funds queues a fund code that
        # dropped out of the top 15); an unbounded DELETE would blow the budget
        # while the guard printed zero, so refuse rather than replay one.
        for _, stmt in pending:
            proven = outbox_delete_rows(conn, stmt)
            if proven is None:
                print(f"ERROR: cannot prove this queued outbox statement deletes "
                      f"at most one row, so it cannot be priced or replayed: "
                      f"{stmt[:160]!r}.\n"
                      f"  The outbox contract is ONE DELETE per statement with "
                      f"every primary-key column pinned by equality, ANDed. "
                      f"`WHERE 1=1` satisfies 'has a WHERE' and empties the "
                      f"table, which is why that is no longer the test.",
                      file=sys.stderr)
                return 2
            tbl, rows = proven
            billed_pending[tbl] = billed_pending.get(tbl, 0) + \
                billed_estimate(conn, tbl, rows, False)
        lines.append(f"-- d1_pending_deletes outbox: {len(pending)} statements")
        lines.extend(stmt for _, stmt in pending)
        lines.append("")

    total_inserts = 0
    total_deletes = 0
    rebuilt: list[str] = []   # full-rebuild tables actually emitted this run
    billed: dict[str, int] = {}
    digests: dict[str, dict[str, str]] = {}
    rowcounts: dict[str, dict[str, int]] = {}
    dropped: dict[str, list[str]] = {}
    for tbl in SYNC_TABLES:
        if allowed_tables is not None and tbl not in allowed_tables:
            continue
        block = fetch_recent(conn, tbl, args.hours,
                             skip_unchanged=not args.force_rebuild,
                             counts=billed, digests=digests,
                             skip_partitions=(args.skip_unchanged_partitions
                                              or args.resend_partitions),
                             resend=args.resend_partitions,
                             rowcounts=rowcounts, dropped=dropped,
                             replace=replace,
                             remote_rows=remote_partition_rows)
        lines.extend(block)
        lines.append("")
        n_ins = sum(1 for ln in block if ln.startswith("INSERT"))
        total_inserts += n_ins
        total_deletes += sum(1 for ln in block if ln.startswith("DELETE"))
        if tbl in _FULL_REBUILD and n_ins:
            rebuilt.append(tbl)

    # A push can legitimately be DELETE-only: a partition emptied by re-extraction
    # has nothing left to insert, and discarding the run here would strand its
    # rows in D1 exactly as the missing detection did.
    if total_inserts == 0 and total_deletes == 0 and not pending:
        print(f"no new rows in last {args.hours}h — nothing to push")
        return 0

    # Price the push BEFORE running it, and print the number every time — a cost
    # nobody sees is a cost nobody manages. July 2026 went 18.1M rows over the
    # 50M monthly allowance and the whole overage was three campaign days
    # (12.4M + 15.1M + 9.4M); none of those runs announced what they were about
    # to write, and nothing stopped them.
    est_total = sum(billed.values()) + sum(billed_pending.values())
    for t, v in billed_pending.items():
        billed[t] = billed.get(t, 0) + v

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

    if args.check_only:
        print("check-only: this push would be accepted")
        return 0

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
    # Only now — a failed push must not be remembered as done, or the table (or
    # partition) would be skipped forever after.
    for tbl in rebuilt:
        record_hash(conn, tbl, content_hash(conn, tbl))
    for tbl in set(digests) | set(dropped):
        record_partition_digests(conn, tbl, digests.get(tbl, {}),
                                 rows=rowcounts.get(tbl),
                                 dropped=dropped.get(tbl))
    print("D1 push complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
