"""D1 bills ROWS WRITTEN — so writing a row that didn't change costs real money.

Cloudflare's Workers Paid plan includes 50 million rows written per month and
charges $1.00 per million after that, and `rowsWritten` counts DELETEs and index
maintenance as well as INSERTs (measured on this database: 392,363 rowsWritten
against 107,636 actual changes, a 3.6x multiplier). Rows READ are $0.001 per
million — a thousandth the price. The whole cost model therefore turns on one
question: *did this row actually change?*

Two places were answering "don't care", together ~21M rows/month of pure waste:

  1. `evds_scraper.fetch_one` re-fetched each series' entire history back to
     2018 on every run and `INSERT OR REPLACE`d all of it. `downloaded_at` is
     omitted from that statement, so every row took DEFAULT CURRENT_TIMESTAMP —
     and `push_to_d1` windows on exactly that column, so 52,828 of evds_series'
     53,521 rows looked new every day and were re-pushed with identical values.
  2. `push_to_d1` rebuilt every `_FULL_REBUILD` table unconditionally.
     `api_series` is 19,787 rows and the bulletin cron runs DAILY.

These tests pin the fixes. They are cost regressions, which is why they are worth
a test at all: nothing breaks when they regress, the bill just goes up.
"""

import sqlite3
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import push_to_d1 as P  # noqa: E402
# Pre-2026Q2 (`bin`) fixtures, so the canonical context is the honest one:
# factor 1, applied as a real multiply. The argument is REQUIRED with no
# default — a caller that forgets must fail loudly rather than silently
# store a Milyon filing unscaled.
from src.audit_reports.units import UnitContext  # noqa: E402


def fake_remote(rows_per_partition=0):
    """Deterministic stand-in for remote_partition_rows. Injected explicitly so
    no unit test can reach `npx wrangler` by omission."""
    def _f(table, parts):
        return {p: rows_per_partition for p in parts}
    return _f


# --- full-rebuild tables only rebuild when their content moved ---------------

def _catalog(rows=3, stamp="2026-01-01 00:00:00"):
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE api_series (series_code TEXT PRIMARY KEY, obs_count INT, "
              "built_at TIMESTAMP)")
    c.executemany("INSERT INTO api_series VALUES (?,?,?)",
                  [(f"S{i}", i, stamp) for i in range(rows)])
    c.commit()
    return c


def _emits_rebuild(block):
    return any(ln.startswith("DELETE") for ln in block)


def test_first_push_rebuilds():
    c = _catalog()
    assert _emits_rebuild(P.fetch_recent(c, "api_series", 30))


def test_unchanged_content_is_not_pushed_again():
    c = _catalog()
    P.record_hash(c, "api_series", P.content_hash(c, "api_series"))
    block = P.fetch_recent(c, "api_series", 30)
    assert not _emits_rebuild(block)
    assert "unchanged" in block[0]


def test_a_moved_build_stamp_alone_does_not_trigger_a_rebuild():
    """THE case that makes the skip worth having. build_api_catalog DELETEs and
    re-INSERTs without naming `built_at`, so it takes DEFAULT CURRENT_TIMESTAMP
    and every row differs on every run — while the catalogue is identical."""
    c = _catalog()
    P.record_hash(c, "api_series", P.content_hash(c, "api_series"))
    c.execute("UPDATE api_series SET built_at = '2026-06-06 06:06:06'")
    c.commit()
    assert not _emits_rebuild(P.fetch_recent(c, "api_series", 30))


def test_a_real_content_change_does_trigger_a_rebuild():
    c = _catalog()
    P.record_hash(c, "api_series", P.content_hash(c, "api_series"))
    c.execute("UPDATE api_series SET obs_count = obs_count + 1 WHERE series_code = 'S1'")
    c.commit()
    assert _emits_rebuild(P.fetch_recent(c, "api_series", 30))


def test_a_new_row_triggers_a_rebuild():
    c = _catalog()
    P.record_hash(c, "api_series", P.content_hash(c, "api_series"))
    c.execute("INSERT INTO api_series VALUES ('S99', 9, '2026-01-01 00:00:00')")
    c.commit()
    assert _emits_rebuild(P.fetch_recent(c, "api_series", 30))


def test_force_rebuild_bypasses_the_skip():
    """The escape hatch for drift: the skip trusts that the last successful push
    landed, so editing D1 directly needs a way to say 'push anyway'."""
    c = _catalog()
    P.record_hash(c, "api_series", P.content_hash(c, "api_series"))
    assert _emits_rebuild(P.fetch_recent(c, "api_series", 30, skip_unchanged=False))


def test_hash_is_insertion_order_independent():
    """Two databases holding the same catalogue must agree, or the skip never
    fires after a rebuild writes the rows in a different order."""
    a, b = _catalog(rows=0), _catalog(rows=0)
    for code in ("S1", "S2", "S3"):
        a.execute("INSERT INTO api_series VALUES (?,1,'t')", (code,))
    for code in ("S3", "S1", "S2"):
        b.execute("INSERT INTO api_series VALUES (?,1,'t')", (code,))
    a.commit(); b.commit()
    assert P.content_hash(a, "api_series") == P.content_hash(b, "api_series")


def test_the_empty_local_table_wipe_guard_still_holds():
    """The skip must not weaken the older guard: a full-rebuild table whose LOCAL
    copy is empty must never emit a bare DELETE, or a daily bulletin push wipes
    the audit coverage matrix it has no rows for."""
    c = _catalog(rows=0)
    block = P.fetch_recent(c, "api_series", 30)
    assert not _emits_rebuild(block)
    assert "refusing to wipe" in block[0]


def test_a_failed_push_is_not_remembered_as_done():
    """record_hash is called only after wrangler exits 0. If a hash were stored
    on a failed push the table would be skipped forever after — silently."""
    src = (REPO / "scripts" / "push_to_d1.py").read_text(encoding="utf-8")
    after_wrangler = src.split("rc = run_wrangler(sql_path)", 1)[1]
    assert "record_hash" in after_wrangler, "record_hash must run after the push"
    before = src.split("rc = run_wrangler(sql_path)", 1)[0]
    assert "record_hash(" not in before.split("def main(", 1)[-1], \
        "record_hash must NOT run before the push succeeds"


# --- EVDS writes only what changed ------------------------------------------

@pytest.fixture()
def evds(monkeypatch, tmp_path):
    pd = pytest.importorskip("pandas")
    from src.scrapers import evds_scraper as E
    db = tmp_path / "t.db"
    monkeypatch.setattr(E, "DB", db)
    conn = sqlite3.connect(db)
    E.init_schema(conn)
    conn.close()

    def feed(frame):
        monkeypatch.setattr(E.evds, "fetch_series",
                            lambda *a, **k: pd.DataFrame(frame))
    return E, db, feed, pd


def _series(E):
    return E.Series("TP.TEST", "Test series", "macro", E.evds.FREQ_DAILY)


def test_evds_writes_new_observations(evds):
    E, db, feed, _ = evds
    feed({"date": ["2026-01-01", "2026-01-02"], "value": [1.0, 2.0]})
    assert E.fetch_one(_series(E)) == 2


def test_evds_rewrites_nothing_when_the_history_is_identical(evds):
    """The bill. EVDS has no incremental endpoint, so the same history arrives
    every single day — it must not cost a single write."""
    E, db, feed, _ = evds
    feed({"date": ["2026-01-01", "2026-01-02"], "value": [1.0, 2.0]})
    E.fetch_one(_series(E))
    assert E.fetch_one(_series(E)) == 0


def test_evds_downloaded_at_does_not_move_on_an_unchanged_row(evds):
    """push_to_d1 windows on downloaded_at, so a moved stamp IS the re-push."""
    E, db, feed, _ = evds
    feed({"date": ["2026-01-01"], "value": [1.0]})
    E.fetch_one(_series(E))
    c = sqlite3.connect(db)
    before = c.execute("SELECT downloaded_at FROM evds_series").fetchone()[0]
    c.close()
    E.fetch_one(_series(E))
    c = sqlite3.connect(db)
    assert c.execute("SELECT downloaded_at FROM evds_series").fetchone()[0] == before
    c.close()


def test_evds_still_writes_a_revision(evds):
    """TCMB revises published figures. A changed value must always be written —
    the saving must never cost us a correction."""
    E, db, feed, _ = evds
    feed({"date": ["2026-01-01", "2026-01-02"], "value": [1.0, 2.0]})
    E.fetch_one(_series(E))
    feed({"date": ["2026-01-01", "2026-01-02"], "value": [1.0, 2.5]})
    assert E.fetch_one(_series(E)) == 1
    c = sqlite3.connect(db)
    assert c.execute("SELECT value FROM evds_series WHERE period_date='2026-01-02'"
                     ).fetchone()[0] == 2.5
    c.close()


def test_evds_writes_when_only_the_label_changes(evds):
    """A TUIK rebase changes the label without changing the value; the row still
    has to reach D1 or the page renders a stale legend."""
    E, db, feed, _ = evds
    s = _series(E)
    feed({"date": ["2026-01-01"], "value": [1.0]})
    E.fetch_one(s)
    relabelled = E.Series(s.code, "Test series (2025=100)", s.category, s.freq)
    assert E.fetch_one(relabelled) == 1


# --- apply_overrides pushes only the partitions that actually changed --------

def _audit_db():
    from src.audit_reports.schema import init_schema
    c = sqlite3.connect(":memory:")
    init_schema(c)
    return c


def _cap_row(c, bank="X", period="2024Q2", kind="consolidated",
             period_type="prior", cet1=270336.203):
    c.execute("INSERT INTO bank_audit_capital (bank_ticker, period, kind, period_type, "
              "cet1_capital, additional_tier1_capital, tier1_capital) VALUES (?,?,?,?,?,?,?)",
              (bank, period, kind, period_type, cet1, 5348088.0, 275684291.0))
    c.commit()


def test_partition_digest_ignores_timestamps():
    """extracted_at is exactly what apply_overrides bumps on purpose. If the
    digest saw it, every partition would look changed and the check would be
    worthless — the failure mode is silent and costs money, not correctness."""
    import apply_overrides as A
    c = _audit_db()
    _cap_row(c)
    d1 = A._partition_digest(c, "X", "2024Q2", "consolidated")
    c.execute("UPDATE bank_audit_capital SET extracted_at = '2099-01-01 00:00:00'")
    c.commit()
    assert A._partition_digest(c, "X", "2024Q2", "consolidated") == d1


def test_partition_digest_sees_a_value_change():
    import apply_overrides as A
    c = _audit_db()
    _cap_row(c)
    d1 = A._partition_digest(c, "X", "2024Q2", "consolidated")
    c.execute("UPDATE bank_audit_capital SET cet1_capital = 270336203.0")
    c.commit()
    assert A._partition_digest(c, "X", "2024Q2", "consolidated") != d1


def test_partition_digest_sees_a_removed_row():
    """Replace-type overrides delete rows. The digest must notice, or the D1
    partition-clear that makes a removal stick would be skipped."""
    import apply_overrides as A
    c = _audit_db()
    _cap_row(c)
    _cap_row(c, period_type="current", cet1=305357338.0)
    d1 = A._partition_digest(c, "X", "2024Q2", "consolidated")
    c.execute("DELETE FROM bank_audit_capital WHERE period_type='current'")
    c.commit()
    assert A._partition_digest(c, "X", "2024Q2", "consolidated") != d1


def test_partition_digest_is_row_order_independent():
    """A replace-type override reinserts the same rows in a different order;
    that is not a change and must not trigger a push."""
    import apply_overrides as A
    a, b = _audit_db(), _audit_db()
    for pt, v in (("current", 1.0), ("prior", 2.0)):
        _cap_row(a, period_type=pt, cet1=v)
    for pt, v in (("prior", 2.0), ("current", 1.0)):
        _cap_row(b, period_type=pt, cet1=v)
    assert (A._partition_digest(a, "X", "2024Q2", "consolidated")
            == A._partition_digest(b, "X", "2024Q2", "consolidated"))


def test_partition_digest_isolates_partitions():
    """A change in one bank must not mark a different one as changed."""
    import apply_overrides as A
    c = _audit_db()
    _cap_row(c, bank="X")
    _cap_row(c, bank="Y")
    dx = A._partition_digest(c, "X", "2024Q2", "consolidated")
    c.execute("UPDATE bank_audit_capital SET cet1_capital = 1 WHERE bank_ticker='Y'")
    c.commit()
    assert A._partition_digest(c, "X", "2024Q2", "consolidated") == dx


def test_reapplying_a_settled_override_is_a_no_op():
    """THE case. Every override is re-applied on every run to stay idempotent,
    so a partition fixed weeks ago is rewritten with the value it already holds.
    Before this check, all 214 named partitions were cleared from D1 and
    re-pushed regardless: ~632,000 rows written to correct five cells."""
    import apply_overrides as A
    c = _audit_db()
    _cap_row(c, cet1=270336203.0)          # already corrected by an earlier run
    ovr = {"bank_ticker": "X", "period": "2024Q2", "kind": "consolidated",
           "statement": "capital", "period_type": "prior",
           "fields": {"cet1_capital": 270336203}}
    before = A._partition_digest(c, "X", "2024Q2", "consolidated")
    A._apply_one(c, ovr, unit=UnitContext.canonical())
    c.commit()
    assert A._partition_digest(c, "X", "2024Q2", "consolidated") == before


def test_an_override_that_does_change_something_is_detected():
    import apply_overrides as A
    c = _audit_db()
    _cap_row(c, cet1=270336.203)           # still wrong
    ovr = {"bank_ticker": "X", "period": "2024Q2", "kind": "consolidated",
           "statement": "capital", "period_type": "prior",
           "fields": {"cet1_capital": 270336203}}
    before = A._partition_digest(c, "X", "2024Q2", "consolidated")
    A._apply_one(c, ovr, unit=UnitContext.canonical())
    c.commit()
    assert A._partition_digest(c, "X", "2024Q2", "consolidated") != before


# --- the pre-flight cost guard ----------------------------------------------
#
# The fixes above make the QUIET days cheap. They do nothing for a campaign: a
# backfill or a fleet re-extraction re-pushes whatever it touched, and July
# 2026's overage was three such days (12.4M + 15.1M + 9.4M billed rows) that
# each ran to completion without ever announcing what they were about to write.
# These tests pin the guard that makes that impossible to do by accident.

def _loans_db(tmp_path, rows: int, indexes: int = 0):
    """A staging DB holding `rows` freshly-downloaded rows of a windowed table."""
    p = tmp_path / "stage.db"
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE loans (year INT, month INT, item_order INT, "
              "amount_tl REAL, downloaded_at TIMESTAMP)")
    for i in range(indexes):
        c.execute(f"CREATE INDEX idx_loans_{i} ON loans(item_order, amount_tl)")
    c.executemany(
        "INSERT INTO loans VALUES (2026, 6, ?, ?, datetime('now'))",
        [(i, float(i)) for i in range(rows)],
    )
    c.commit()
    return p, c


def test_billed_estimate_counts_index_maintenance(tmp_path):
    """A row write is not one billed row: every index on the table is another."""
    _, c = _loans_db(tmp_path, rows=100, indexes=3)
    # 1 for the row itself + 3 indexes. (SQLite reports no implicit index for a
    # plain rowid table, so this is exactly the three we created.)
    assert P.billed_estimate(c, "loans", 100, full_rebuild=False) == 100 * 4


def test_billed_estimate_doubles_for_a_full_rebuild(tmp_path):
    """DELETE + INSERT — a rebuild pays for clearing the table as well."""
    _, c = _loans_db(tmp_path, rows=100, indexes=1)
    windowed = P.billed_estimate(c, "loans", 100, full_rebuild=False)
    assert P.billed_estimate(c, "loans", 100, full_rebuild=True) == 2 * windowed


def test_fetch_recent_reports_its_cost_when_asked(tmp_path):
    _, c = _loans_db(tmp_path, rows=50, indexes=2)
    counts: dict[str, int] = {}
    P.fetch_recent(c, "loans", 48, counts=counts)
    assert counts["loans"] == 50 * 3


def test_fetch_recent_still_works_without_the_counter(tmp_path):
    """`counts` is optional on purpose — other tests and callers pass three args."""
    _, c = _loans_db(tmp_path, rows=5)
    assert any(ln.startswith("INSERT") for ln in P.fetch_recent(c, "loans", 48))


def _run_main(monkeypatch, db_path, *extra):
    monkeypatch.setattr(
        sys, "argv",
        ["push_to_d1.py", "--db", str(db_path), "--hours", "48", "--dry-run", *extra])
    return P.main()


def test_push_refuses_when_it_would_write_more_than_the_cap(tmp_path, monkeypatch):
    """THE guard. A push over the cap must FAIL, not warn — a campaign that
    exits 0 is a campaign nobody reviews."""
    p, _ = _loans_db(tmp_path, rows=500, indexes=1)
    assert _run_main(monkeypatch, p, "--max-billed-rows", "100") == 3


def test_push_proceeds_when_the_cost_is_declared(tmp_path, monkeypatch):
    """Raising the cap is how a legitimate campaign says so — and because it
    lands in the workflow file, the number is reviewable in the diff."""
    p, _ = _loans_db(tmp_path, rows=500, indexes=1)
    assert _run_main(monkeypatch, p, "--max-billed-rows", "10000") == 0


def test_the_default_cap_clears_a_whole_audit_corpus():
    """The cap must not block legitimate work or it will be raised habitually
    and stop meaning anything. A whole-audit-corpus push is ~440k rows at a ~4x
    index factor; the pending one-off prose push is ~369k rows."""
    assert P.DEFAULT_MAX_BILLED_ROWS >= 440_545 * 4
    assert P.DEFAULT_MAX_BILLED_ROWS < 9_400_000   # July's smallest campaign day


# --- the cycle-aware layer ---------------------------------------------------
#
# The per-push cap bounds ONE invocation. It cannot bound a day, and July's
# campaign days were several pushes each — no single one would have tripped a
# 2.5M ceiling. So the cap also tightens once the cycle's allowance is spent.

import datetime as _dt

from src import d1_usage as U  # cycle reading lives here, stdlib-only


@pytest.mark.parametrize("today,expected", [
    ("2026-08-04", "2026-07-11"),   # before the 11th -> previous month's 11th
    ("2026-08-11", "2026-08-11"),   # the roll-over day itself
    ("2026-08-31", "2026-08-11"),
    ("2026-01-05", "2025-12-11"),   # across a year boundary
    ("2026-03-01", "2026-02-11"),   # across a short month
])
def test_billing_cycle_runs_the_11th_to_the_10th(today, expected):
    """NOT the calendar month. Cloudflare labels Jul 11 -> Aug 10 as 'Aug 2026';
    reading it as a calendar month has twice produced wrong days-remaining."""
    assert U.cycle_start(_dt.date.fromisoformat(today)) == _dt.date.fromisoformat(expected)


def test_headroom_left_leaves_the_declared_cap_alone():
    cap, why = P.effective_cap(P.DEFAULT_MAX_BILLED_ROWS, used=10_000_000)
    assert cap == P.DEFAULT_MAX_BILLED_ROWS
    assert "40,000,000" in why


def test_a_spent_cycle_tightens_the_cap_to_routine_size():
    """Campaigns wait for the roll-over; daily crons keep running. Freezing the
    whole pipeline was July's other mistake — four days unwatched for a bill the
    crons were not causing."""
    cap, why = P.effective_cap(P.DEFAULT_MAX_BILLED_ROWS, used=68_100_000)
    assert cap == P.EXHAUSTED_CYCLE_CAP
    assert "SPENT" in why
    # A daily cron still fits; a whole-corpus audit push does not.
    assert 50_000 < cap < 1_678_540


def test_a_spent_cycle_never_RAISES_a_lower_declared_cap():
    """min(), not replace — an operator who asked for a tighter cap keeps it."""
    cap, _ = P.effective_cap(1_000, used=68_100_000)
    assert cap == 1_000


def test_unobservable_usage_neither_tightens_nor_relaxes():
    """None means 'could not observe'. Treating it as zero would report a
    missing reading as plenty of headroom, which is the silent-wrong shape."""
    cap, why = P.effective_cap(P.DEFAULT_MAX_BILLED_ROWS, used=None)
    assert cap == P.DEFAULT_MAX_BILLED_ROWS
    assert "unknown" in why


def test_cycle_reading_returns_none_rather_than_raising(monkeypatch):
    """A dead analytics API must not take the push down with it."""
    def boom(*a, **k):
        raise OSError("network is down")
    monkeypatch.setattr(U.urllib.request, "urlopen", boom)
    assert U.cycle_rows_written("acct", "token") is None


# --- statements must fit D1's 100 KB ceiling --------------------------------
#
# The first push of bank_call_transcripts died on SQLITE_TOOBIG: one row is a
# WHOLE earnings call (median 30k chars, max 67,710 across the corpus) and the
# table had no BATCH_SIZE_PER_TABLE entry, so it batched at the default 100.
# The per-table row counts are a hand-tuned hint and a hand-tuned hint drifts;
# the batcher now flushes on BYTES too, so no table can reach that error.

def _fat_rows_db(tmp_path, rows: int, chars: int):
    p = tmp_path / "fat.db"
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE loans (year INT, month INT, item_order INT, "
              "item_name TEXT, downloaded_at TIMESTAMP)")
    c.executemany(
        "INSERT INTO loans VALUES (2026, 6, ?, ?, datetime('now'))",
        [(i, "x" * chars) for i in range(rows)],
    )
    c.commit()
    return c


def _insert_stmts(block):
    return [s for s in block if s.startswith("INSERT")]


def test_no_statement_exceeds_d1s_limit_even_at_the_default_batch(tmp_path):
    """30k-char rows at the default batch of 100 would be a 3 MB statement."""
    c = _fat_rows_db(tmp_path, rows=40, chars=30_000)
    stmts = _insert_stmts(P.fetch_recent(c, "loans", 48))
    assert stmts, "expected some INSERTs"
    assert max(len(s.encode("utf-8")) for s in stmts) <= P.D1_MAX_SQL_BYTES


def test_a_row_near_the_ceiling_gets_its_own_statement(tmp_path):
    c = _fat_rows_db(tmp_path, rows=5, chars=80_000)
    stmts = _insert_stmts(P.fetch_recent(c, "loans", 48))
    assert len(stmts) == 5                       # one row apiece
    assert max(len(s.encode("utf-8")) for s in stmts) <= P.D1_MAX_SQL_BYTES


def test_skinny_rows_still_batch_together(tmp_path):
    """Byte-sizing must not defeat batching — that would be 1 statement/row for
    every table and a far larger SQL file for no reason."""
    c = _fat_rows_db(tmp_path, rows=250, chars=10)
    stmts = _insert_stmts(P.fetch_recent(c, "loans", 48))
    assert len(stmts) == 3                       # 250 rows at the default 100


def test_transcripts_batch_one_row_at_a_time():
    """Belt and braces: the byte guard makes this table safe anyway, but the
    explicit entry documents WHY one call per statement is the right shape."""
    assert P.BATCH_SIZE_PER_TABLE["bank_call_transcripts"] == 1


# --- partition-level skip: campaigns cost what they CHANGED -------------------
#
# The guard above makes a campaign declared. This makes it cheap. The windowed
# audit tables key on the extraction stamp, so re-running the fleet after an
# extractor fix re-pushes every partition it TOUCHED, not the ones it changed —
# and July's overage was campaigns. Each partition now carries a digest.
#
# The danger is the mirror image of the saving: a wrong skip means rows silently
# never reach D1. These tests pin the safe defaults. (The clear-then-push callers
# these once had to defend against are gone — every repair tool now goes through
# audit_d1.replace_partitions, one atomic guarded call.)

def _audit_partition_db(tmp_path):
    p = tmp_path / "audit.db"
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE bank_audit_capital (bank_ticker TEXT, period TEXT, "
              "kind TEXT, item TEXT, value REAL, extracted_at TIMESTAMP)")
    rows = [("AKBNK", "2026Q1", "consolidated", "cet1", 100.0),
            ("AKBNK", "2026Q1", "consolidated", "tier1", 200.0),
            ("GARAN", "2026Q1", "consolidated", "cet1", 300.0)]
    c.executemany(
        "INSERT INTO bank_audit_capital VALUES (?,?,?,?,?,datetime('now'))", rows)
    # The extraction log. It is the only record that a partition was touched
    # which survives that partition losing all of its rows.
    c.execute("CREATE TABLE bank_audit_extractions (bank_ticker TEXT, period TEXT, "
              "kind TEXT, success INT, extracted_at TIMESTAMP)")
    c.executemany("INSERT INTO bank_audit_extractions VALUES (?,?,?,1,datetime('now'))",
                  [("AKBNK", "2026Q1", "consolidated"),
                   ("GARAN", "2026Q1", "consolidated")])
    c.commit()
    return c


def _push3(c, **kw):
    """(block, digests, rowcounts) — the three out-params main() threads through."""
    kw.setdefault("skip_partitions", True)
    kw.setdefault("remote_rows", fake_remote())
    d: dict = {}
    rc: dict = {}
    block = P.fetch_recent(c, "bank_audit_capital", 48, digests=d, rowcounts=rc, **kw)
    return block, d, rc


def _push(c, **kw):
    """The skip is OPT-IN, so these tests ask for it explicitly. Default-off is
    the whole point: several callers clear the partitions in D1 before invoking
    the push, and a skip after such a clear would leave them empty."""
    kw.setdefault("skip_partitions", True)
    kw.setdefault("remote_rows", fake_remote())
    d: dict = {}
    _push.rowcounts = rc = {}
    block = P.fetch_recent(c, "bank_audit_capital", 48, digests=d, rowcounts=rc, **kw)
    return block, d


def _emitted_values(block):
    return [ln for ln in block if ln.startswith("INSERT")]


def test_first_push_sends_every_partition(tmp_path):
    c = _audit_partition_db(tmp_path)
    block, d = _push(c)
    assert _emitted_values(block)
    assert set(d["bank_audit_capital"]) == {
        "AKBNK|2026Q1|consolidated", "GARAN|2026Q1|consolidated"}


def test_a_reextraction_that_changed_nothing_pushes_nothing(tmp_path):
    """THE case. The extractor re-ran, bumped extracted_at on every row, and
    produced byte-identical values — the window says 'touched', the digest says
    'unchanged', and D1 should receive nothing at all."""
    c = _audit_partition_db(tmp_path)
    _, d = _push(c)
    P.record_partition_digests(c, "bank_audit_capital", d["bank_audit_capital"],
                               rows=_push.rowcounts.get("bank_audit_capital"))

    c.execute("UPDATE bank_audit_capital SET extracted_at = datetime('now','+1 hour')")
    c.commit()
    block, _ = _push(c)
    assert not _emitted_values(block)
    assert "none changed" in " ".join(block)


def test_only_the_partition_that_moved_is_pushed(tmp_path):
    c = _audit_partition_db(tmp_path)
    _, d = _push(c)
    P.record_partition_digests(c, "bank_audit_capital", d["bank_audit_capital"],
                               rows=_push.rowcounts.get("bank_audit_capital"))

    c.execute("UPDATE bank_audit_capital SET value = 999.0 "
              "WHERE bank_ticker='GARAN'")
    c.commit()
    block, d2 = _push(c)
    sql = " ".join(_emitted_values(block))
    assert "GARAN" in sql and "AKBNK" not in sql
    assert set(d2["bank_audit_capital"]) == {"GARAN|2026Q1|consolidated"}


def test_a_partition_never_pushed_is_always_sent(tmp_path):
    """Missing state must mean 'send it', never 'assume it landed'. A reseeded
    staging DB has no digests at all and must push everything once."""
    c = _audit_partition_db(tmp_path)
    _, d = _push(c)
    P.record_partition_digests(c, "bank_audit_capital", d["bank_audit_capital"],
                               rows=_push.rowcounts.get("bank_audit_capital"))

    c.execute("INSERT INTO bank_audit_capital VALUES "
              "('ISCTR','2026Q1','consolidated','cet1',500.0,datetime('now'))")
    c.commit()
    block, _ = _push(c)
    assert "ISCTR" in " ".join(_emitted_values(block))


def test_the_skip_is_off_unless_asked_for(tmp_path):
    """THE safety default, and it outlived the bug that motivated it. Those
    callers no longer clear-then-push — they go through replace_partitions — but
    a plain windowed push is still upsert-only, so silently skipping partitions
    for any caller that did not ask remains the wrong default. Opting in is what
    makes the self-contained DELETE+INSERT path apply."""
    c = _audit_partition_db(tmp_path)
    _, d = _push(c)
    P.record_partition_digests(c, "bank_audit_capital", d["bank_audit_capital"],
                               rows=_push.rowcounts.get("bank_audit_capital"))
    block, _ = _push(c, skip_partitions=False)
    assert _emitted_values(block), "default must resend everything in the window"


def test_digests_ignore_the_extraction_stamp(tmp_path):
    """extracted_at is what a re-extraction bumps on purpose; in the digest it
    would make every partition look changed and defeat the whole mechanism."""
    c = _audit_partition_db(tmp_path)
    before = P.partition_digests(c, "bank_audit_capital", "")
    c.execute("UPDATE bank_audit_capital SET extracted_at = '2099-01-01'")
    c.commit()
    assert P.partition_digests(c, "bank_audit_capital", "") == before


def test_a_deleted_row_still_counts_as_a_change(tmp_path):
    """A partition that LOST a row must re-push — the digest covers row count,
    not just values."""
    c = _audit_partition_db(tmp_path)
    _, d = _push(c)
    P.record_partition_digests(c, "bank_audit_capital", d["bank_audit_capital"],
                               rows=_push.rowcounts.get("bank_audit_capital"))
    c.execute("DELETE FROM bank_audit_capital WHERE bank_ticker='AKBNK' "
              "AND item='tier1'")
    c.commit()
    block, _ = _push(c)
    assert "AKBNK" in " ".join(_emitted_values(block))


def test_the_extraction_log_is_never_partition_skipped(tmp_path):
    """bank_audit_extractions exists to record THAT an extraction ran, and
    extracted_at — the fact it carries — is excluded from every digest. Skipping
    it would freeze D1's audit trail while the rows it describes were genuinely
    re-extracted: the log quietly disagreeing with the audit."""
    p = tmp_path / "log.db"
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE bank_audit_extractions (bank_ticker TEXT, period TEXT, "
              "kind TEXT, success INT, extracted_at TIMESTAMP)")
    c.execute("INSERT INTO bank_audit_extractions VALUES "
              "('AKBNK','2026Q1','consolidated',1,datetime('now'))")
    c.commit()

    d: dict = {}
    first = P.fetch_recent(c, "bank_audit_extractions", 48, digests=d)
    assert any(ln.startswith("INSERT") for ln in first)
    assert "bank_audit_extractions" not in d, "must not record a partition digest"

    # Re-extraction bumps the stamp and changes nothing else: still pushed.
    c.execute("UPDATE bank_audit_extractions SET extracted_at = datetime('now','+1 hour')")
    c.commit()
    again = P.fetch_recent(c, "bank_audit_extractions", 48, digests={})
    assert any(ln.startswith("INSERT") for ln in again)


# --- the spend alert: hear about it before 100%, not on the invoice -----------

def _spend(used):
    import importlib.util
    spec = importlib.util.spec_from_file_location("hc", REPO / "scripts" / "healthcheck.py")
    hc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hc)
    return hc.d1_spend_problem(used=used)


def test_quiet_below_the_warn_line():
    assert _spend(30_000_000) is None          # 60%


def test_warns_before_the_allowance_is_gone():
    """80%, not 100% — at 100% the only choices left are stop or pay."""
    msg = _spend(41_000_000)
    assert msg and "82%" in msg and "headroom" in msg


def test_reports_the_overage_and_its_cost():
    msg = _spend(68_100_000)                   # July's actual month-to-date
    assert msg and "18,100,000 OVER" in msg and "$18.10" in msg


def test_silent_when_the_reading_is_unavailable(monkeypatch):
    """An alert that fires on its own blindness gets muted, and a muted alert is
    worse than none. The push guard is the enforcing half regardless."""
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("CF_ACCOUNT_TAG", raising=False)
    monkeypatch.delenv("R2_ACCOUNT_ID", raising=False)
    assert _spend(None) is None


# --- convergence: does the emitted SQL make the REMOTE match local? -----------
#
# Every test above asks "was an INSERT emitted". That is not the question. The
# question is whether replaying the emitted SQL against a copy of D1 leaves it
# equal to the staging table — and it did not: a changed partition emitted only
# INSERT OR REPLACE, so a row that re-extraction REMOVED survived remotely, and
# its digest was then recorded as synced so every later push skipped it.
#
# These replay the generated statements against a simulated remote and compare.

def _remote_from(local: sqlite3.Connection) -> sqlite3.Connection:
    """A 'D1' seeded with the same rows the staging table currently holds."""
    remote = sqlite3.connect(":memory:")
    remote.execute("CREATE TABLE bank_audit_capital (bank_ticker TEXT, period TEXT, "
                   "kind TEXT, item TEXT, value REAL, extracted_at TIMESTAMP)")
    remote.executemany("INSERT INTO bank_audit_capital VALUES (?,?,?,?,?,?)",
                       list(local.execute("SELECT * FROM bank_audit_capital")))
    remote.commit()
    return remote


def _apply(remote: sqlite3.Connection, block: list[str]) -> None:
    for stmt in block:
        if stmt.startswith(("INSERT", "DELETE")):
            remote.executescript(stmt)
    remote.commit()


def _rows(conn: sqlite3.Connection) -> set:
    return set(conn.execute(
        "SELECT bank_ticker, period, kind, item, value FROM bank_audit_capital"))


def test_removing_a_row_locally_removes_it_remotely(tmp_path):
    """THE convergence case. Upsert-only left the removed row behind for good."""
    c = _audit_partition_db(tmp_path)
    block, d = _push(c)
    remote = _remote_from(c)
    P.record_partition_digests(c, "bank_audit_capital", d["bank_audit_capital"],
                               rows=_push.rowcounts.get("bank_audit_capital"))

    c.execute("DELETE FROM bank_audit_capital WHERE bank_ticker='AKBNK' AND item='tier1'")
    c.commit()
    block, _ = _push(c)
    _apply(remote, block)
    assert _rows(remote) == _rows(c)


def test_emptying_a_partition_entirely_converges_remotely(tmp_path):
    """A partition that lost EVERY row — the case the first version could not
    see. With no rows left it is absent from the window and from any comparison
    keyed on rows currently present, so D1 kept its contents forever while the
    log cheerfully printed "none changed". The extraction log is what makes it
    findable. This deletes ALL of AKBNK, not one item of it: the earlier test
    claimed to empty the partition and left `cet1` behind, so it never exercised
    this path at all."""
    c = _audit_partition_db(tmp_path)
    _, d, rc = _push3(c)
    remote = _remote_from(c)
    P.record_partition_digests(c, "bank_audit_capital", d["bank_audit_capital"],
                               rows=rc.get("bank_audit_capital"))

    c.execute("DELETE FROM bank_audit_capital WHERE bank_ticker='AKBNK'")
    c.commit()
    assert not list(c.execute(
        "SELECT 1 FROM bank_audit_capital WHERE bank_ticker='AKBNK'")), "must be empty"

    block, _, _ = _push3(c)
    assert [ln for ln in block if ln.startswith("DELETE")], "no DELETE emitted"
    _apply(remote, block)
    assert _rows(remote) == _rows(c)
    assert not list(remote.execute(
        "SELECT 1 FROM bank_audit_capital WHERE bank_ticker='AKBNK'"))


def test_only_changed_partitions_are_deleted(tmp_path):
    """The scoped DELETE must not sweep partitions the push is not resending."""
    c = _audit_partition_db(tmp_path)
    _, d = _push(c)
    P.record_partition_digests(c, "bank_audit_capital", d["bank_audit_capital"],
                               rows=_push.rowcounts.get("bank_audit_capital"))

    c.execute("UPDATE bank_audit_capital SET value = 999 WHERE bank_ticker='GARAN'")
    c.commit()
    block, _ = _push(c)
    dels = [ln for ln in block if ln.startswith("DELETE")]
    assert len(dels) == 1
    assert "GARAN" in dels[0] and "AKBNK" not in dels[0]


def test_an_unchanged_partition_emits_no_delete(tmp_path):
    """Nothing changed ⇒ nothing emitted at all. A DELETE here would clear a
    partition the push then declines to re-insert."""
    c = _audit_partition_db(tmp_path)
    _, d = _push(c)
    P.record_partition_digests(c, "bank_audit_capital", d["bank_audit_capital"],
                               rows=_push.rowcounts.get("bank_audit_capital"))
    block, _ = _push(c)
    assert not [ln for ln in block if ln.startswith(("DELETE", "INSERT"))]


def test_a_failed_push_does_not_advance_digest_state(tmp_path):
    """Digests are recorded by main() only after wrangler exits 0. Generating the
    SQL must not itself persist anything, or a failed push would be remembered as
    done and the partition skipped forever."""
    c = _audit_partition_db(tmp_path)
    _push(c)                                   # generate, never "execute"
    assert P.stored_partition_digests(c, "bank_audit_capital") == {}


# --- the cycle cap must respect what is actually left ------------------------

def test_positive_but_insufficient_headroom_still_tightens_the_cap():
    """49.9M of 50M used: a 2.5M push must not be waved through to land 2.4M
    past the allowance. The guard would have 'passed' the run that blew it."""
    cap, why = P.effective_cap(P.DEFAULT_MAX_BILLED_ROWS, used=49_900_000)
    assert cap == P.EXHAUSTED_CYCLE_CAP        # floor keeps routine lanes alive
    assert cap < P.DEFAULT_MAX_BILLED_ROWS
    assert "only 100,000 rows" in why


def test_headroom_between_the_floor_and_the_cap_is_the_cap():
    cap, _ = P.effective_cap(P.DEFAULT_MAX_BILLED_ROWS, used=49_000_000)
    assert cap == 1_000_000                    # exactly the remaining headroom


def test_ample_headroom_leaves_the_declared_cap_intact():
    cap, _ = P.effective_cap(P.DEFAULT_MAX_BILLED_ROWS, used=10_000_000)
    assert cap == P.DEFAULT_MAX_BILLED_ROWS


# --- a single row over the statement ceiling -------------------------------

def test_a_row_over_the_statement_limit_fails_loudly(tmp_path):
    """No batch size can send it: D1 allows a 2 MB row but caps a STATEMENT at
    100,000 bytes. Emitting it produced a doomed file that failed remotely with a
    bare SQLITE_TOOBIG naming neither table nor row."""
    c = _fat_rows_db(tmp_path, rows=1, chars=150_000)
    with pytest.raises(ValueError, match="over D1's .* statement limit"):
        P.fetch_recent(c, "loans", 48)


def test_the_oversized_check_does_not_fire_on_a_batchable_row(tmp_path):
    """80k is under the ceiling on its own — it must get its own statement, not
    an exception."""
    c = _fat_rows_db(tmp_path, rows=3, chars=80_000)
    stmts = [s for s in P.fetch_recent(c, "loans", 48) if s.startswith("INSERT")]
    assert len(stmts) == 3


def test_the_partition_delete_is_chunked_under_the_limit():
    """The fleet gains 76 partitions a quarter, so a single DELETE eventually
    crosses D1's statement ceiling and fails remotely with a bare SQLITE_TOOBIG.
    Every chunk must fit, and together they must name every partition."""
    parts = [f"BANK{i:04d}|2026Q1|consolidated" for i in range(20_000)]
    stmts = P.partition_deletes("bank_audit_capital", parts)
    assert len(stmts) > 1
    assert max(len(s.encode("utf-8")) for s in stmts) <= P.D1_MAX_SQL_BYTES
    joined = " ".join(stmts)
    assert all(f"'BANK{i:04d}'" in joined for i in (0, 9_999, 19_999))


def test_a_small_partition_set_is_one_delete():
    stmts = P.partition_deletes("bank_audit_capital", ["AKBNK|2026Q1|consolidated"])
    assert len(stmts) == 1 and stmts[0].endswith(");")


# --- --check-only: price a push without executing it -------------------------
#
# This began as a preflight for the clear-then-push callers, so a refusal could
# land before the DELETE rather than after it. That sequence is gone — every
# repair tool now goes through audit_d1.replace_partitions, one atomic guarded
# call — and a preflight could never have made two remote calls atomic anyway.
# The flag survives as an operator affordance: ask what a push would cost, and
# get exit 3 if it would be refused, without executing anything.

def test_check_only_refuses_without_generating_a_push(tmp_path, monkeypatch):
    p, _ = _loans_db(tmp_path, rows=500, indexes=1)
    monkeypatch.setattr(sys, "argv",
                        ["push_to_d1.py", "--db", str(p), "--hours", "48",
                         "--check-only", "--max-billed-rows", "100"])
    assert P.main() == 3


def test_check_only_accepts_an_affordable_push(tmp_path, monkeypatch):
    p, _ = _loans_db(tmp_path, rows=500, indexes=1)
    monkeypatch.setattr(sys, "argv",
                        ["push_to_d1.py", "--db", str(p), "--hours", "48",
                         "--check-only", "--max-billed-rows", "100000"])
    assert P.main() == 0


def test_no_migrated_caller_issues_a_standalone_remote_delete(monkeypatch, tmp_path):
    """THE architectural guarantee. Every audit repair tool used to run a remote
    DELETE and then launch push_to_d1 as a second process; any refusal, SQL
    error, network blip or cancelled runner in between left the partitions gone
    with nothing local aware they needed restoring. A preflight could not fix
    that — two remote calls cannot be made atomic, and the guard reads cycle
    usage independently in each, so an accepted check could still be followed by
    a refused push AFTER the delete.

    Now there is exactly one remote call, carrying DELETEs and INSERTs together.
    This asserts the shape: replace_partitions shells out to push_to_d1 with
    --replace-partitions and never issues a wrangler DELETE of its own.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("ad", REPO / "scripts" / "audit_d1.py")
    ad = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ad)

    wrangler_calls: list = []
    pushes: list[list[str]] = []
    monkeypatch.setattr(ad, "retry_wrangler",
                        lambda *a, **k: wrangler_calls.append(a))
    monkeypatch.setattr(ad, "ensure_d1_schema", lambda *a, **k: None)
    monkeypatch.setattr(ad.subprocess, "run",
                        lambda cmd, *a, **k: (pushes.append(cmd),
                                              type("R", (), {"returncode": 0})())[1])

    ad.replace_partitions([("AKBNK", "2026Q1", "consolidated")], tmp_path / "x.db")

    assert wrangler_calls == [], "no standalone remote DELETE may be issued"
    assert len(pushes) == 1, "exactly one remote operation"
    assert "--replace-partitions" in pushes[0]


def test_every_audit_repair_tool_routes_through_replace_partitions():
    """A future edit must not reintroduce clear-then-push by hand. These five
    were the callers that had it; none may build its own DELETE + push pair."""
    for name in ("apply_overrides", "load_partition", "reextract_pl",
                 "push_from_scratch", "backfill_extraction"):
        src = (REPO / "scripts" / f"{name}.py").read_text(encoding="utf-8")
        assert "replace_partitions" in src or "clear_d1_partitions" in src, name
        # The tell-tale of the old shape: building DELETE text AND launching the
        # pusher as a separate step.
        assert not ("DELETE FROM {tbl} WHERE bank_ticker=" in src
                    and "push_to_d1.py" in src), f"{name} still clears then pushes"


# --- delete-only work, pricing, and deliberate resend -------------------------

def test_a_delete_only_push_is_not_discarded_as_no_work(tmp_path, monkeypatch):
    """total_inserts == 0 used to mean 'nothing to push'. An emptied partition
    has nothing to insert and everything to delete."""
    c = _audit_partition_db(tmp_path)
    _, d, rc = _push3(c)
    P.record_partition_digests(c, "bank_audit_capital", d["bank_audit_capital"],
                               rows=rc.get("bank_audit_capital"))
    c.execute("DELETE FROM bank_audit_capital WHERE bank_ticker='AKBNK'")
    c.commit()
    block, _, _ = _push3(c)
    assert sum(1 for ln in block if ln.startswith("INSERT")) == 0
    assert sum(1 for ln in block if ln.startswith("DELETE")) == 1


def test_replacing_a_partition_prices_both_sides(tmp_path):
    """Skip mode emits DELETE *and* INSERT and D1 bills both. Pricing only the
    insert side understated a replacement by half."""
    c = _audit_partition_db(tmp_path)
    _, d, rc = _push3(c)
    P.record_partition_digests(c, "bank_audit_capital", d["bank_audit_capital"],
                               rows=rc.get("bank_audit_capital"))
    c.execute("UPDATE bank_audit_capital SET value = 999 WHERE bank_ticker='AKBNK'")
    c.commit()
    counts: dict = {}
    P.fetch_recent(c, "bank_audit_capital", 48, digests={}, rowcounts={},
                   counts=counts, skip_partitions=True)
    # AKBNK holds 2 rows: 2 deleted remotely + 2 re-inserted.
    assert counts["bank_audit_capital"] == 4


def test_resend_leaves_digest_state_current(tmp_path):
    """A deliberate repair must not cost a second full push on the next opt-in
    run. --resend-partitions resends everything AND records the state."""
    c = _audit_partition_db(tmp_path)
    _, d, rc = _push3(c)
    P.record_partition_digests(c, "bank_audit_capital", d["bank_audit_capital"],
                               rows=rc.get("bank_audit_capital"))

    block, d2, rc2 = _push3(c, resend=True)
    assert _emitted_values(block), "resend must send everything"
    assert set(d2["bank_audit_capital"]) == set(d["bank_audit_capital"])
    P.record_partition_digests(c, "bank_audit_capital", d2["bank_audit_capital"],
                               rows=rc2.get("bank_audit_capital"))

    block, _, _ = _push3(c)                 # normal opt-in run right after
    assert not _emitted_values(block), "resend left state stale"


def test_historical_partitions_outside_the_window_are_never_deleted(tmp_path):
    """The emptied check compares stored keys against the LOG's window, not
    against every stored key — otherwise every partition older than the window
    would look 'missing' and be deleted from D1."""
    c = _audit_partition_db(tmp_path)
    _, d, rc = _push3(c)
    P.record_partition_digests(c, "bank_audit_capital", d["bank_audit_capital"],
                               rows=rc.get("bank_audit_capital"))
    # An old partition we pushed long ago: in the digest state, not in the window.
    P.record_partition_digests(c, "bank_audit_capital",
                               {"ISCTR|2019Q1|consolidated": "old"}, rows={})
    dropped: dict = {}
    blk = P.fetch_recent(c, "bank_audit_capital", 48, digests={}, rowcounts={},
                         dropped=dropped, skip_partitions=True)
    assert "ISCTR" not in " ".join(blk)
    assert not dropped.get("bank_audit_capital")


# --- explicit replacement: the interface that retired clear-then-push ---------

def _replace(c, parts, **kw):
    d: dict = {}
    rc: dict = {}
    dr: dict = {}
    cnt: dict = {}
    kw.setdefault("remote_rows", fake_remote())
    block = P.fetch_recent(c, "bank_audit_capital", 48, digests=d, rowcounts=rc,
                           dropped=dr, counts=cnt, replace=set(parts), **kw)
    return block, d, rc, dr, cnt


def test_explicit_replacement_converges_for_a_shrinking_partition(tmp_path):
    c = _audit_partition_db(tmp_path)
    block, d, rc, _, _ = _replace(c, ["AKBNK|2026Q1|consolidated",
                                      "GARAN|2026Q1|consolidated"])
    remote = _remote_from(c)
    P.record_partition_digests(c, "bank_audit_capital", d["bank_audit_capital"],
                               rows=rc.get("bank_audit_capital"))

    c.execute("DELETE FROM bank_audit_capital WHERE bank_ticker='AKBNK' AND item='tier1'")
    c.commit()
    block, _, _, _, _ = _replace(c, ["AKBNK|2026Q1|consolidated"])
    _apply(remote, block)
    assert _rows(remote) == _rows(c)


def test_explicit_replacement_clears_a_partition_with_no_local_rows(tmp_path):
    """Selection is explicit, so a partition is replaced because it was ASKED
    for — not because a timestamp or the extraction log happened to mention it.
    A partition with zero local rows must still be cleared remotely."""
    c = _audit_partition_db(tmp_path)
    block, d, rc, _, _ = _replace(c, ["AKBNK|2026Q1|consolidated",
                                      "GARAN|2026Q1|consolidated"])
    remote = _remote_from(c)
    P.record_partition_digests(c, "bank_audit_capital", d["bank_audit_capital"],
                               rows=rc.get("bank_audit_capital"))

    c.execute("DELETE FROM bank_audit_capital WHERE bank_ticker='AKBNK'")
    # deliberately no extraction-log row and no local rows: only the caller knows
    c.execute("DELETE FROM bank_audit_extractions WHERE bank_ticker='AKBNK'")
    c.commit()
    block, _, _, dr, _ = _replace(c, ["AKBNK|2026Q1|consolidated"])
    assert [ln for ln in block if ln.startswith("DELETE")]
    _apply(remote, block)
    assert not list(remote.execute(
        "SELECT 1 FROM bank_audit_capital WHERE bank_ticker='AKBNK'"))
    assert dr["bank_audit_capital"] == ["AKBNK|2026Q1|consolidated"]


def test_explicit_replacement_touches_nothing_it_was_not_given(tmp_path):
    c = _audit_partition_db(tmp_path)
    block, _, _, _, _ = _replace(c, ["GARAN|2026Q1|consolidated"])
    sql = " ".join(block)
    assert "GARAN" in sql and "AKBNK" not in sql


def test_replacement_prices_the_delete_and_the_insert(tmp_path):
    c = _audit_partition_db(tmp_path)
    _, d, rc, _, _ = _replace(c, ["AKBNK|2026Q1|consolidated"])
    P.record_partition_digests(c, "bank_audit_capital", d["bank_audit_capital"],
                               rows=rc.get("bank_audit_capital"))
    _, _, _, _, cnt = _replace(c, ["AKBNK|2026Q1|consolidated"])
    assert cnt["bank_audit_capital"] == 4        # 2 deleted + 2 inserted


def test_a_legacy_emptied_partition_is_never_priced_as_one_row(tmp_path, monkeypatch):
    """origin/master already holds digest rows with a NULL row_count. Emptying
    such a 100-row partition once priced its DELETE as a single logical row — 2
    billed instead of 200 — so the guard waved through the very push it exists
    to stop. With nothing local able to say how big it is, D1 is asked."""
    c = _audit_partition_db(tmp_path)
    c.executemany("INSERT INTO bank_audit_capital VALUES "
                  "('ISCTR','2026Q1','consolidated',?,?,datetime('now'))",
                  [(f"i{i}", float(i)) for i in range(100)])
    c.execute("INSERT INTO bank_audit_extractions VALUES "
              "('ISCTR','2026Q1','consolidated',1,datetime('now'))")
    c.commit()
    _, d, _ = _push3(c)
    # Legacy state: digest recorded, row_count NULL (rows= omitted entirely).
    P.record_partition_digests(c, "bank_audit_capital", d["bank_audit_capital"])
    assert P.stored_partition_rows(c, "bank_audit_capital") == {}

    c.execute("DELETE FROM bank_audit_capital WHERE bank_ticker='ISCTR'")
    c.commit()
    counts: dict = {}
    P.fetch_recent(c, "bank_audit_capital", 48, digests={}, rowcounts={},
                   dropped={}, counts=counts, skip_partitions=True,
                   remote_rows=fake_remote(100))
    # The fixture table carries no indexes, so the factor is 1: the estimate is
    # the row count itself. What matters is that it reflects the 100 rows D1
    # actually holds and not the 1 the old fallback assumed.
    assert counts["bank_audit_capital"] == 100


def test_it_refuses_rather_than_guess_when_d1_cannot_be_asked(tmp_path, monkeypatch):
    """No fourth source. Assuming a number is how the guard gets defeated."""
    c = _audit_partition_db(tmp_path)
    _, d, _ = _push3(c)
    # LEGACY state on purpose: digest recorded, row_count NULL. That is what
    # origin/master already holds, and it is the only case where nothing local
    # can say how many rows D1 still has.
    P.record_partition_digests(c, "bank_audit_capital", d["bank_audit_capital"])
    c.execute("DELETE FROM bank_audit_capital WHERE bank_ticker='AKBNK'")
    c.commit()
    with pytest.raises(RuntimeError, match="cannot price the DELETE"):
        P.fetch_recent(c, "bank_audit_capital", 48, digests={}, rowcounts={},
                       dropped={}, counts={}, skip_partitions=True,
                       remote_rows=lambda t, parts: None)


def test_state_advances_only_after_the_push_succeeds():
    """Both the digest and the row_count are written by main() after wrangler
    exits 0 — generating the SQL persists nothing."""
    src = (REPO / "scripts" / "push_to_d1.py").read_text(encoding="utf-8")
    after = src.split("rc = run_wrangler(sql_path)", 1)[1]
    assert "record_partition_digests" in after
    before = src.split("rc = run_wrangler(sql_path)", 1)[0]
    assert "record_partition_digests(" not in before.split("def main(", 1)[-1]


# --- main()-level: explicit scope, and the whole file priced ------------------
#
# Everything above drives fetch_recent. These drive main(), because the gaps
# found next lived BETWEEN the two: a replacement with no table filter fell
# through to every other table's ordinary window, and queued outbox DELETEs
# executed without ever entering the estimate.

def _audit_db_file(tmp_path, extra_loans=True):
    p = tmp_path / "stage.db"
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE bank_audit_capital (bank_ticker TEXT, period TEXT, "
              "kind TEXT, item TEXT, value REAL, extracted_at TIMESTAMP, "
              "PRIMARY KEY (bank_ticker, period, kind, item))")
    c.executemany("INSERT INTO bank_audit_capital VALUES (?,?,?,?,?,datetime('now'))",
                  [("AKBNK", "2026Q1", "consolidated", "cet1", 1.0),
                   ("GARAN", "2026Q1", "consolidated", "cet1", 2.0)])
    c.execute("CREATE TABLE bank_audit_extractions (bank_ticker TEXT, period TEXT, "
              "kind TEXT, success INT, extracted_at TIMESTAMP)")
    c.executemany("INSERT INTO bank_audit_extractions VALUES (?,?,?,1,datetime('now'))",
                  [("AKBNK", "2026Q1", "consolidated"),
                   ("GARAN", "2026Q1", "consolidated")])
    if extra_loans:
        c.execute("CREATE TABLE loans (year INT, month INT, item_order INT, "
                  "amount_tl REAL, downloaded_at TIMESTAMP)")
        c.execute("INSERT INTO loans VALUES (2026,6,1,5.0,datetime('now'))")
    c.commit()
    c.close()
    return p


def _run(monkeypatch, db, *extra, remote=0):
    """Drive main() with a deterministic fake remote reader.

    main() resolves `remote_partition_rows` as a module global at call time, so
    replacing it here keeps even the orchestration tests offline. Without this
    they shell out to `npx wrangler --remote`, which is exactly the defect these
    tests exist to prevent — and which passed locally only because this machine
    happens to hold Cloudflare credentials."""
    monkeypatch.setattr(P, "remote_partition_rows", fake_remote(remote))
    monkeypatch.setattr(sys, "argv",
                        ["push_to_d1.py", "--db", str(db), "--dry-run",
                         "--no-cycle-check", *extra])
    return P.main()


def _generated_sql() -> str:
    import tempfile as _t
    return (Path(_t.gettempdir()) / "d1_incremental.sql").read_text(encoding="utf-8")


def _listing(tmp_path, *parts):
    f = tmp_path / "parts.txt"
    f.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return f


def test_replace_mode_refuses_without_an_explicit_table_set(tmp_path, monkeypatch):
    """Reproduced: an AKBNK replacement also emitted an unrelated recent `loans`
    row. With no filter the loop walks every sync table, and the ones without a
    partition key silently keep their ordinary window behaviour."""
    db = _audit_db_file(tmp_path)
    lst = _listing(tmp_path, "AKBNK|2026Q1|consolidated")
    assert _run(monkeypatch, db, "--replace-partitions", str(lst)) == 2


def test_replace_mode_rejects_a_table_that_cannot_be_scoped(tmp_path, monkeypatch):
    db = _audit_db_file(tmp_path)
    lst = _listing(tmp_path, "AKBNK|2026Q1|consolidated")
    assert _run(monkeypatch, db, "--replace-partitions", str(lst),
                "--only-tables", "bank_audit_capital,loans") == 2


def test_replace_mode_rejects_a_full_rebuild_table(tmp_path, monkeypatch):
    db = _audit_db_file(tmp_path)
    lst = _listing(tmp_path, "AKBNK|2026Q1|consolidated")
    assert _run(monkeypatch, db, "--replace-partitions", str(lst),
                "--only-tables", "bank_audit_capital,api_series") == 2


def test_replacing_akbnk_never_emits_garan_anywhere(tmp_path, monkeypatch):
    """Including bank_audit_extractions. It sits in _NO_PARTITION_SKIP, which
    used to switch OFF partition mode entirely — so during an explicit
    replacement it fell back to the time window, emitted GARAN's log row and
    produced no scoped DELETE. The exemption must suppress the digest skip, not
    the selection."""
    db = _audit_db_file(tmp_path)
    lst = _listing(tmp_path, "AKBNK|2026Q1|consolidated")
    rc = _run(monkeypatch, db, "--replace-partitions", str(lst),
              "--only-tables", "bank_audit_capital,bank_audit_extractions")
    assert rc == 0
    sql = _generated_sql()
    assert "AKBNK" in sql
    assert "GARAN" not in sql
    assert sql.count("DELETE FROM bank_audit_extractions") == 1


def test_a_legacy_100_to_1_shrink_prices_the_remote_delete(tmp_path, monkeypatch):
    """Reproduced at 4 billed rows instead of 202. The local count is the remote
    count ONLY when the digest matched; a shrunk partition's digest differs, so
    its one remaining row says nothing about the 100 D1 still holds. Because a
    row remained, the remote probe was never reached."""
    db = tmp_path / "shrink.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE bank_audit_capital (bank_ticker TEXT, period TEXT, "
              "kind TEXT, item TEXT, value REAL, extracted_at TIMESTAMP)")
    c.execute("CREATE INDEX ix ON bank_audit_capital(bank_ticker)")
    c.executemany("INSERT INTO bank_audit_capital VALUES "
                  "('AKBNK','2026Q1','consolidated',?,?,datetime('now'))",
                  [(f"i{i}", float(i)) for i in range(100)])
    c.execute("CREATE TABLE bank_audit_extractions (bank_ticker TEXT, period TEXT, "
              "kind TEXT, success INT, extracted_at TIMESTAMP)")
    c.execute("INSERT INTO bank_audit_extractions VALUES "
              "('AKBNK','2026Q1','consolidated',1,datetime('now'))")
    c.commit()
    d: dict = {}
    P.fetch_recent(c, "bank_audit_capital", 48, digests=d, skip_partitions=True)
    # Legacy state on purpose: digest, no row_count.
    P.record_partition_digests(c, "bank_audit_capital", d["bank_audit_capital"])
    c.execute("DELETE FROM bank_audit_capital WHERE item != 'i0'")
    c.commit()
    assert c.execute("SELECT COUNT(*) FROM bank_audit_capital").fetchone()[0] == 1

    probed: list = []

    def _probe(t, parts):
        probed.append(list(parts))
        return {p: 100 for p in parts}
    counts: dict = {}
    P.fetch_recent(c, "bank_audit_capital", 48, digests={}, rowcounts={},
                   dropped={}, counts=counts, skip_partitions=True,
                   remote_rows=_probe)
    assert probed, "a shrunk partition with no recorded count must ask D1"
    # 100 deleted + 1 inserted, at (1 row + 1 index) each = 202.
    assert counts["bank_audit_capital"] == 202


def test_a_nonempty_partition_with_no_stored_digest_is_probed(tmp_path, monkeypatch):
    """A missing or stale digest is not 'matched'. Nothing then licenses the
    local count as the remote one either."""
    c = _audit_partition_db(tmp_path)
    P.record_partition_digests(c, "bank_audit_capital",
                               {"AKBNK|2026Q1|consolidated": "stale-digest"})
    probed: list = []

    def _probe(t, parts):
        probed.append(list(parts))
        return {p: 50 for p in parts}
    P.fetch_recent(c, "bank_audit_capital", 48, digests={}, rowcounts={},
                   dropped={}, counts={}, skip_partitions=True, remote_rows=_probe)
    assert any("AKBNK|2026Q1|consolidated" in p for p in probed)


def test_queued_outbox_deletes_are_priced(tmp_path, monkeypatch):
    """Reproduced: a queued DELETE executed while the guard printed 0."""
    db = _audit_db_file(tmp_path, extra_loans=False)
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE d1_pending_deletes (sql TEXT)")
    c.execute("INSERT INTO d1_pending_deletes VALUES (?)",
              ("DELETE FROM bank_audit_capital WHERE bank_ticker='X' "
               "AND period='Y' AND kind='Z' AND item='cet1';",))
    c.commit()
    c.close()
    assert _run(monkeypatch, db, "--only-tables", "bank_audit_capital",
                "--max-billed-rows", "1") == 3


def test_an_unbounded_queued_delete_is_refused(tmp_path, monkeypatch):
    """The outbox contract is one PK-scoped row per statement. A bare DELETE
    would blow the budget while the guard priced it as a single row."""
    db = _audit_db_file(tmp_path, extra_loans=False)
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE d1_pending_deletes (sql TEXT)")
    c.execute("INSERT INTO d1_pending_deletes VALUES (?)",
              ("DELETE FROM bank_audit_capital;",))
    c.commit()
    c.close()
    assert _run(monkeypatch, db, "--only-tables", "bank_audit_capital") == 2


def test_replacement_does_not_replay_unrelated_outbox_entries(tmp_path, monkeypatch):
    """Another lane's queued delete must not be smuggled into a targeted repair."""
    db = _audit_db_file(tmp_path, extra_loans=False)
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE d1_pending_deletes (sql TEXT)")
    c.execute("INSERT INTO d1_pending_deletes VALUES (?)",
              ("DELETE FROM tefas_top_funds WHERE date='2026-01-01' "
               "AND fon_tipi='YAT' AND fon_kodu='AFA';",))
    c.commit()
    c.close()
    lst = _listing(tmp_path, "AKBNK|2026Q1|consolidated")
    assert _run(monkeypatch, db, "--replace-partitions", str(lst),
                "--only-tables", "bank_audit_capital") == 0
    assert "tefas_top_funds" not in _generated_sql()


def test_the_npl_history_backfill_cannot_push_unguarded():
    """It built DELETE+INSERT files and handed them straight to run_wrangler —
    an explicitly high-volume audit backfill with no billed-row guard and no
    partition digest state."""
    src = (REPO / "scripts" / "backfills" / "backfill_npl_history.py").read_text(
        encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    assert "run_wrangler(" not in code, "must not push outside the guarded path"
    assert "import run_wrangler" not in code
    assert "replace_partitions(" in code


# --- the suite must stay OFFLINE ---------------------------------------------
#
# A fresh partition with no stored digest went straight into the "unknown" set
# and called remote_partition_rows, which shells out to `npx wrangler ... --remote`.
# Ordinary tests did that. Locally it SUCCEEDED because this machine has
# Cloudflare credentials — so the suite was making live D1 reads while being
# reported as offline verification, and in CI (no Node, no credentials) it would
# have failed closed. Probing is now part of pricing only, and the resolver is
# injected, so reaching the network by omission is impossible.

def test_pytest_never_shells_out(tmp_path, monkeypatch):
    """THE sentinel. Any subprocess launch from a unit path is a bug: it makes
    the suite depend on credentials CI does not have, and can spend real money."""
    calls: list = []
    monkeypatch.setattr(P.subprocess, "run",
                        lambda *a, **k: calls.append(a) or (_ for _ in ()).throw(
                            AssertionError("unit test tried to launch a subprocess")))
    c = _audit_partition_db(tmp_path)
    # A first push: every partition is fresh, none has a digest or a row_count.
    P.fetch_recent(c, "bank_audit_capital", 48, digests={}, rowcounts={},
                   dropped={}, skip_partitions=True)
    assert calls == []


def test_pricing_without_a_remote_reader_refuses_rather_than_shelling_out(tmp_path):
    """No resolver injected means no remote reader — refuse, never reach for one."""
    c = _audit_partition_db(tmp_path)
    with pytest.raises(RuntimeError, match="cannot price the DELETE"):
        P.fetch_recent(c, "bank_audit_capital", 48, digests={}, rowcounts={},
                       dropped={}, counts={}, skip_partitions=True)


def test_no_estimate_requested_means_no_remote_call(tmp_path):
    """Probing exists to price. Without `counts` there is nothing to price."""
    c = _audit_partition_db(tmp_path)
    block = P.fetch_recent(c, "bank_audit_capital", 48, digests={}, rowcounts={},
                           dropped={}, skip_partitions=True)   # no counts, no remote_rows
    assert any(ln.startswith("INSERT") for ln in block)


def test_the_wrangler_json_parser_handles_a_captured_response(monkeypatch):
    """The parse path of remote_partition_rows, exercised against a static
    captured response instead of a live call."""
    captured = (
        'Some wrangler preamble\n'
        '[\n {\n  "results": [\n'
        '    {"p": "AKBNK|2026Q1|consolidated", "n": 181},\n'
        '    {"p": "GARAN|2026Q1|consolidated", "n": 12}\n'
        '  ],\n  "success": true\n }\n]\n')
    monkeypatch.setattr(
        P.subprocess, "run",
        lambda *a, **k: type("R", (), {"returncode": 0, "stdout": captured})())
    out = P.remote_partition_rows(
        "bank_audit_balance_sheet",
        ["AKBNK|2026Q1|consolidated", "GARAN|2026Q1|consolidated",
         "ISCTR|2026Q1|consolidated"])
    assert out == {"AKBNK|2026Q1|consolidated": 181,
                   "GARAN|2026Q1|consolidated": 12,
                   # absent from the response = D1 holds nothing, which is an answer
                   "ISCTR|2026Q1|consolidated": 0}


def test_the_wrangler_parser_returns_none_on_a_bad_response(monkeypatch):
    monkeypatch.setattr(
        P.subprocess, "run",
        lambda *a, **k: type("R", (), {"returncode": 1, "stdout": ""})())
    assert P.remote_partition_rows("bank_audit_capital", ["A|B|C"]) is None


# --- replacement must reject a table it cannot actually replace ---------------

def test_replace_mode_rejects_a_table_missing_from_the_staging_db(tmp_path, monkeypatch):
    """Reproduced: replacing into a DB without the table logged 'not present in
    this staging DB' and exited 0 — a successful repair that repaired nothing.
    Absence is fine for a windowed push (the staging DBs hold disjoint sets); in
    replacement mode the caller named the table, so absence is an error."""
    db = tmp_path / "empty.db"
    sqlite3.connect(db).close()
    lst = _listing(tmp_path, "AKBNK|2026Q1|consolidated")
    assert _run(monkeypatch, db, "--replace-partitions", str(lst),
                "--only-tables", "balance_sheet") == 2


def test_a_present_but_empty_partition_capable_table_is_valid(tmp_path, monkeypatch):
    """The distinction that matters: present-and-empty is a legitimate
    DELETE-only replacement, not a missing table."""
    db = tmp_path / "empty_table.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE bank_audit_capital (bank_ticker TEXT, period TEXT, "
              "kind TEXT, item TEXT, value REAL, extracted_at TIMESTAMP)")
    c.execute("CREATE TABLE bank_audit_extractions (bank_ticker TEXT, period TEXT, "
              "kind TEXT, success INT, extracted_at TIMESTAMP)")
    c.commit()
    c.close()
    lst = _listing(tmp_path, "AKBNK|2026Q1|consolidated")
    rc = _run(monkeypatch, db, "--replace-partitions", str(lst),
              "--only-tables", "bank_audit_capital")
    assert rc == 0
    assert "DELETE FROM bank_audit_capital" in _generated_sql()


# --- the outbox must PROVE one row, not assume it ----------------------------

def _outbox_conn():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE bank_audit_capital (bank_ticker TEXT, period TEXT, "
              "kind TEXT, item TEXT, value REAL, "
              "PRIMARY KEY (bank_ticker, period, kind, item))")
    c.execute("CREATE TABLE tefas_top_funds (date TEXT, fon_tipi TEXT, fon_kodu TEXT, "
              "aum_try REAL, PRIMARY KEY (date, fon_tipi, fon_kodu))")
    return c


def test_a_full_primary_key_delete_is_provably_one_row():
    c = _outbox_conn()
    assert P.outbox_delete_rows(c, "DELETE FROM tefas_top_funds WHERE date='2026-01-01' "
                                  "AND fon_tipi='YAT' AND fon_kodu='AFA';") \
        == ("tefas_top_funds", 1)


def test_where_1_equals_1_is_refused():
    """It has a WHERE and it empties the table. Reproduced as accepted and
    priced at 3 billed rows."""
    c = _outbox_conn()
    assert P.outbox_delete_rows(c, "DELETE FROM bank_audit_capital WHERE 1=1;") is None


def test_a_partial_key_delete_is_refused():
    c = _outbox_conn()
    assert P.outbox_delete_rows(
        c, "DELETE FROM bank_audit_capital WHERE bank_ticker='X' AND period='Y';") is None


def test_an_or_clause_is_refused():
    c = _outbox_conn()
    assert P.outbox_delete_rows(
        c, "DELETE FROM tefas_top_funds WHERE date='a' AND fon_tipi='b' "
           "AND fon_kodu='c' OR 1=1;") is None


def test_two_statements_are_refused():
    c = _outbox_conn()
    assert P.outbox_delete_rows(
        c, "DELETE FROM tefas_top_funds WHERE date='a' AND fon_tipi='b' AND "
           "fon_kodu='c'; DROP TABLE tefas_top_funds;") is None


def test_an_unparseable_statement_is_refused():
    c = _outbox_conn()
    assert P.outbox_delete_rows(c, "DELETE FROM tefas_top_funds") is None
    assert P.outbox_delete_rows(c, "UPDATE tefas_top_funds SET aum_try=1 WHERE date='a';") is None


def test_an_unknown_table_is_refused():
    c = _outbox_conn()
    assert P.outbox_delete_rows(
        c, "DELETE FROM not_a_table WHERE a='1';") is None


def test_a_table_without_a_primary_key_is_refused():
    """Without a PK nothing can prove the predicate selects one row."""
    c = _outbox_conn()
    c.execute("CREATE TABLE loose (a TEXT, b TEXT)")
    assert P.outbox_delete_rows(c, "DELETE FROM loose WHERE a='1' AND b='2';") is None


def test_todays_producers_all_emit_provable_statements():
    """news.bank_tagger, tefas.loader and update_kap_ownership each queue one
    full-primary-key DELETE. The consumer fails closed regardless, but their
    current output must keep working."""
    c = _outbox_conn()
    c.execute("CREATE TABLE news_item_banks (source TEXT, external_id TEXT, "
              "ticker TEXT, PRIMARY KEY (source, external_id, ticker))")
    c.execute("CREATE TABLE kap_ownership (bank_ticker TEXT, item TEXT, "
              "PRIMARY KEY (bank_ticker, item))")
    for stmt in (
        "DELETE FROM tefas_top_funds WHERE date='2026-01-01' AND fon_tipi='YAT' "
        "AND fon_kodu='AFA';",
        "DELETE FROM news_item_banks WHERE source='kap' AND external_id='1' "
        "AND ticker='AKBNK';",
        "DELETE FROM kap_ownership WHERE bank_ticker='AKBNK' AND item='sermaye';",
    ):
        assert P.outbox_delete_rows(c, stmt) is not None, stmt


# --- ownership is judged BEFORE the schema initialisers run -------------------
#
# main() calls _init_audit_schema() and friends, which CREATE the whole
# bank_audit_* set. A presence check made after that passes for a table the
# staging DB never held — so replacing into a wrong or empty snapshot emitted a
# scoped DELETE with no INSERT and would have erased the partition remotely.
# Reproduced at exit 0 with 543 billed rows. The earlier test used
# `balance_sheet`, which no initialiser creates, so it passed for the wrong
# reason and never covered the production audit path.

def test_a_missing_audit_table_is_rejected_despite_schema_init(tmp_path, monkeypatch):
    db = tmp_path / "empty.db"
    sqlite3.connect(db).close()
    lst = _listing(tmp_path, "AKBNK|2026Q1|consolidated")
    rc = _run(monkeypatch, db, "--replace-partitions", str(lst),
              "--only-tables", "bank_audit_capital", remote=181)
    assert rc == 2, "an audit table the snapshot never held must be rejected"


def test_a_precreated_empty_audit_table_is_still_a_valid_delete_only_replace(
        tmp_path, monkeypatch):
    """The distinction the check must preserve: explicitly present-and-empty is a
    legitimate DELETE-only replacement, not a missing table."""
    db = tmp_path / "present_empty.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE bank_audit_capital (bank_ticker TEXT, period TEXT, "
              "kind TEXT, item TEXT, value REAL, extracted_at TIMESTAMP)")
    c.commit()
    c.close()
    lst = _listing(tmp_path, "AKBNK|2026Q1|consolidated")
    rc = _run(monkeypatch, db, "--replace-partitions", str(lst),
              "--only-tables", "bank_audit_capital", remote=7)
    assert rc == 0
    sql = _generated_sql()
    assert "DELETE FROM bank_audit_capital" in sql
    assert "INSERT" not in sql


# --- the remote reader must not read failure as zero -------------------------

def _stdout(payload):
    return type("R", (), {"returncode": 0, "stdout": payload})()


def test_a_failed_d1_result_is_not_zero_rows(monkeypatch):
    """wrangler exits 0 while reporting a failed query; empty `results` then
    reads as 'every partition holds nothing' and prices the DELETE at zero."""
    monkeypatch.setattr(P.subprocess, "run", lambda *a, **k: _stdout(
        '[{"results":[],"success":false,"errors":[{"message":"boom"}]}]'))
    assert P.remote_partition_rows("bank_audit_capital", ["A|B|C"]) is None


def test_a_malformed_results_payload_returns_none(monkeypatch):
    monkeypatch.setattr(P.subprocess, "run", lambda *a, **k: _stdout(
        '[{"results":"not-a-list","success":true}]'))
    assert P.remote_partition_rows("bank_audit_capital", ["A|B|C"]) is None


def test_invalid_counts_return_none(monkeypatch):
    for bad in ('[{"results":[{"p":"A|B|C","n":-1}],"success":true}]',
                '[{"results":[{"p":"A|B|C","n":"12"}],"success":true}]',
                '[{"results":[{"p":123,"n":4}],"success":true}]'):
        monkeypatch.setattr(P.subprocess, "run",
                            (lambda _b: lambda *a, **k: _stdout(_b))(bad))
        assert P.remote_partition_rows("bank_audit_capital", ["A|B|C"]) is None


def test_a_successful_response_still_parses(monkeypatch):
    monkeypatch.setattr(P.subprocess, "run", lambda *a, **k: _stdout(
        '[{"results":[{"p":"A|B|C","n":9}],"success":true}]'))
    assert P.remote_partition_rows("t", ["A|B|C", "D|E|F"]) == {
        "A|B|C": 9, "D|E|F": 0}


def test_failed_remote_pricing_refuses_rather_than_assuming_zero(tmp_path, monkeypatch):
    c = _audit_partition_db(tmp_path)
    monkeypatch.setattr(P.subprocess, "run", lambda *a, **k: _stdout(
        '[{"results":[],"success":false}]'))
    with pytest.raises(RuntimeError, match="cannot price the DELETE"):
        P.fetch_recent(c, "bank_audit_capital", 48, digests={}, rowcounts={},
                       dropped={}, counts={}, skip_partitions=True,
                       remote_rows=P.remote_partition_rows)


# --- a non-owning push must not leave stale state behind ---------------------

def test_a_plain_upsert_reports_the_partitions_it_did_not_own(tmp_path):
    """A windowed push is upsert-only: it touches partitions without owning
    them, so any recorded digest/row_count stops describing D1 the moment it
    lands. It must be reported for invalidation."""
    c = _audit_partition_db(tmp_path)
    stale: dict = {}
    P.fetch_recent(c, "bank_audit_capital", 48, stale=stale)   # no skip, no replace
    assert set(stale["bank_audit_capital"]) == {
        "AKBNK|2026Q1|consolidated", "GARAN|2026Q1|consolidated"}


def test_an_owning_push_reports_nothing_stale(tmp_path):
    """Replacement and the opt-in skip DO own their partitions and record fresh
    state, so nothing there is stale."""
    c = _audit_partition_db(tmp_path)
    stale: dict = {}
    P.fetch_recent(c, "bank_audit_capital", 48, digests={}, rowcounts={},
                   dropped={}, skip_partitions=True, stale=stale,
                   remote_rows=fake_remote())
    assert stale == {}


def test_invalidation_clears_only_the_named_partitions(tmp_path):
    c = _audit_partition_db(tmp_path)
    P.record_partition_digests(c, "bank_audit_capital",
                               {"AKBNK|2026Q1|consolidated": "d1",
                                "GARAN|2026Q1|consolidated": "d2"},
                               rows={"AKBNK|2026Q1|consolidated": 2,
                                     "GARAN|2026Q1|consolidated": 1})
    P.invalidate_partition_state(c, "bank_audit_capital",
                                 ["AKBNK|2026Q1|consolidated"])
    assert set(P.stored_partition_digests(c, "bank_audit_capital")) == {
        "GARAN|2026Q1|consolidated"}


def test_a_plain_upsert_then_a_replacement_does_not_trust_the_old_count(
        tmp_path, monkeypatch):
    """THE reproduction: own a 2-row partition (row_count=2), add a third row,
    push it the plain upsert-only way, then replace. Trusting the stored 2
    underpriced the remote DELETE (15 billed against a correct 18)."""
    db = tmp_path / "stale.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE bank_audit_capital (bank_ticker TEXT, period TEXT, "
              "kind TEXT, item TEXT, value REAL, extracted_at TIMESTAMP)")
    c.execute("CREATE INDEX ix1 ON bank_audit_capital(bank_ticker)")
    c.execute("CREATE INDEX ix2 ON bank_audit_capital(period)")
    c.executemany("INSERT INTO bank_audit_capital VALUES "
                  "('AKBNK','2026Q1','consolidated',?,?,datetime('now'))",
                  [("cet1", 1.0), ("tier1", 2.0)])
    c.execute("CREATE TABLE bank_audit_extractions (bank_ticker TEXT, period TEXT, "
              "kind TEXT, success INT, extracted_at TIMESTAMP)")
    c.execute("INSERT INTO bank_audit_extractions VALUES "
              "('AKBNK','2026Q1','consolidated',1,datetime('now'))")
    c.commit()
    c.close()

    # 1. own it: digest + row_count=2 recorded.
    c = sqlite3.connect(db)
    d: dict = {}
    rc: dict = {}
    P.fetch_recent(c, "bank_audit_capital", 48, digests=d, rowcounts=rc,
                   skip_partitions=True, remote_rows=fake_remote())
    P.record_partition_digests(c, "bank_audit_capital", d["bank_audit_capital"],
                               rows=rc["bank_audit_capital"])
    assert P.stored_partition_rows(c, "bank_audit_capital") == {
        "AKBNK|2026Q1|consolidated": 2}
    # 2. a third row lands.
    c.execute("INSERT INTO bank_audit_capital VALUES "
              "('AKBNK','2026Q1','consolidated','tier2',3.0,datetime('now'))")
    c.commit()
    c.close()

    # 3. the supported plain windowed push, through main() so invalidation runs.
    monkeypatch.setattr(P, "run_wrangler", lambda path: 0)
    monkeypatch.setattr(P, "remote_partition_rows", fake_remote(3))
    monkeypatch.setattr(sys, "argv",
                        ["push_to_d1.py", "--db", str(db), "--no-cycle-check",
                         "--only-tables", "bank_audit_capital"])
    assert P.main() == 0

    # 4. the stale count must be gone, so a replacement prices against truth.
    c = sqlite3.connect(db)
    assert P.stored_partition_rows(c, "bank_audit_capital") == {}, \
        "an upsert-only push must not leave a row_count claiming to describe D1"
    counts: dict = {}
    P.fetch_recent(c, "bank_audit_capital", 48, digests={}, rowcounts={},
                   dropped={}, counts=counts, replace={"AKBNK|2026Q1|consolidated"},
                   remote_rows=fake_remote(3))
    # 3 deleted + 3 inserted. The factor is read from the table rather than
    # hardcoded: main()'s schema initialisers add their own index, so a literal
    # here would pin the wrong number for the wrong reason.
    factor = 1 + P.index_count(c, "bank_audit_capital")
    assert counts["bank_audit_capital"] == 6 * factor
    assert counts["bank_audit_capital"] != 5 * factor, \
        "pricing must not use the stale row_count of 2"


def test_state_is_never_mutated_during_generation_or_a_dry_run(tmp_path, monkeypatch):
    """Invalidation belongs after a successful wrangler execute — never during
    SQL generation, --check-only or --dry-run."""
    c = _audit_partition_db(tmp_path)
    P.record_partition_digests(c, "bank_audit_capital",
                               {"AKBNK|2026Q1|consolidated": "d"}, rows={})
    P.fetch_recent(c, "bank_audit_capital", 48, stale={})     # generation only
    assert P.stored_partition_digests(c, "bank_audit_capital")

    db = tmp_path / "audit.db"
    monkeypatch.setattr(P, "remote_partition_rows", fake_remote())
    monkeypatch.setattr(sys, "argv",
                        ["push_to_d1.py", "--db", str(db), "--dry-run",
                         "--no-cycle-check", "--only-tables", "bank_audit_capital"])
    P.main()
    c2 = sqlite3.connect(db)
    assert P.stored_partition_digests(c2, "bank_audit_capital"), \
        "a dry run must not touch recorded state"


def test_invalidation_is_wired_after_the_wrangler_call():
    src = (REPO / "scripts" / "push_to_d1.py").read_text(encoding="utf-8")
    after = src.split("rc = run_wrangler(sql_path)", 1)[1]
    assert "invalidate_partition_state" in after
    before = src.split("rc = run_wrangler(sql_path)", 1)[0]
    assert "invalidate_partition_state(" not in before.split("def main(", 1)[-1]


# --- a refusal must not defeat itself on retry -------------------------------
#
# The ownership check ran AFTER the schema initialisers, so the refusal itself
# created the table it was refusing. Reproduced: attempt 1 exit 2 with
# bank_audit_capital now present, attempt 2 exit 0 emitting a scoped DELETE and
# no INSERT. And nobody had to do that by hand — audit_d1.replace_partitions
# retried every nonzero child exit, so the second attempt was automatic.

def test_a_refused_replacement_leaves_the_table_absent(tmp_path, monkeypatch):
    db = tmp_path / "empty.db"
    sqlite3.connect(db).close()
    lst = _listing(tmp_path, "AKBNK|2026Q1|consolidated")
    rc = _run(monkeypatch, db, "--replace-partitions", str(lst),
              "--only-tables", "bank_audit_capital", remote=181)
    assert rc == P.EXIT_VALIDATION
    present = sqlite3.connect(db).execute(
        "SELECT 1 FROM sqlite_master WHERE name='bank_audit_capital'").fetchone()
    assert not present, "the refusal created the very table it refused"


def test_an_identical_second_invocation_is_refused_too(tmp_path, monkeypatch):
    """The retry must see exactly what the first attempt saw."""
    db = tmp_path / "empty.db"
    sqlite3.connect(db).close()
    lst = _listing(tmp_path, "AKBNK|2026Q1|consolidated")
    args = ("--replace-partitions", str(lst), "--only-tables", "bank_audit_capital")
    assert _run(monkeypatch, db, *args, remote=181) == P.EXIT_VALIDATION
    assert _run(monkeypatch, db, *args, remote=181) == P.EXIT_VALIDATION


def test_validation_runs_before_any_staging_db_mutation(tmp_path, monkeypatch):
    """Not just for the audit tables: NOTHING may be written before the scope is
    known good. The file's mtime and table set must be untouched."""
    db = tmp_path / "empty.db"
    sqlite3.connect(db).close()
    before = db.stat().st_mtime_ns, db.stat().st_size
    lst = _listing(tmp_path, "AKBNK|2026Q1|consolidated")
    _run(monkeypatch, db, "--replace-partitions", str(lst),
         "--only-tables", "bank_audit_capital", remote=181)
    assert (db.stat().st_mtime_ns, db.stat().st_size) == before


def _audit_d1():
    import importlib.util
    spec = importlib.util.spec_from_file_location("ad", REPO / "scripts" / "audit_d1.py")
    ad = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ad)
    return ad


def _count_child_calls(ad, monkeypatch, rc):
    calls: list = []

    def _run_child(cmd, *a, **k):
        calls.append(cmd)
        return type("R", (), {"returncode": rc})()
    monkeypatch.setattr(ad.subprocess, "run", _run_child)
    monkeypatch.setattr(ad, "ensure_d1_schema", lambda *a, **k: None)
    monkeypatch.setattr(ad.time, "sleep", lambda *_: None)
    return calls


def test_replace_partitions_does_not_retry_a_validation_refusal(tmp_path, monkeypatch):
    """THE second layer. Retrying a deterministic refusal is how the first layer
    got bypassed automatically."""
    ad = _audit_d1()
    calls = _count_child_calls(ad, monkeypatch, ad.EXIT_VALIDATION)
    with pytest.raises(SystemExit):
        ad.replace_partitions([("AKBNK", "2026Q1", "consolidated")], tmp_path / "x.db")
    assert len(calls) == 1, "a validation refusal must not be retried"


def test_replace_partitions_does_not_retry_a_budget_refusal(tmp_path, monkeypatch):
    ad = _audit_d1()
    calls = _count_child_calls(ad, monkeypatch, ad.EXIT_BUDGET)
    with pytest.raises(SystemExit):
        ad.replace_partitions([("AKBNK", "2026Q1", "consolidated")], tmp_path / "x.db")
    assert len(calls) == 1, "a budget refusal must not be retried"


def test_replace_partitions_still_retries_a_transport_failure(tmp_path, monkeypatch):
    """The retry loop exists for real transients (D1_RESET_DO, fetch failed) —
    those must keep retrying."""
    ad = _audit_d1()
    calls = _count_child_calls(ad, monkeypatch, ad.EXIT_PUSH_FAILED
                               if hasattr(ad, "EXIT_PUSH_FAILED") else 4)
    with pytest.raises(SystemExit):
        ad.replace_partitions([("AKBNK", "2026Q1", "consolidated")], tmp_path / "x.db")
    assert len(calls) == ad.D1_RETRIES


def test_the_push_wrapper_also_treats_refusals_as_terminal(tmp_path, monkeypatch):
    ad = _audit_d1()
    calls = _count_child_calls(ad, monkeypatch, ad.EXIT_BUDGET)
    with pytest.raises(SystemExit):
        ad.push_to_d1(tmp_path / "x.db", 24, ["bank_audit_capital"])
    assert len(calls) == 1


def test_a_wrangler_failure_cannot_masquerade_as_a_deterministic_exit():
    """wrangler's own code could be 2 or 3. Remapped, so callers branch on
    meaning rather than on whatever the tool happened to return."""
    src = (REPO / "scripts" / "push_to_d1.py").read_text(encoding="utf-8")
    after = src.split("rc = run_wrangler(sql_path)", 1)[1].split("\n\n", 1)[0]
    assert "EXIT_PUSH_FAILED" in after
    assert "return rc" not in after
