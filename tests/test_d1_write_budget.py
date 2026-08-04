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
    A._apply_one(c, ovr)
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
    A._apply_one(c, ovr)
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
# never reach D1. These tests pin the safe defaults.

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
    c.commit()
    return c


def _push(c, **kw):
    d: dict = {}
    block = P.fetch_recent(c, "bank_audit_capital", 48, digests=d, **kw)
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
    P.record_partition_digests(c, "bank_audit_capital", d["bank_audit_capital"])

    c.execute("UPDATE bank_audit_capital SET extracted_at = datetime('now','+1 hour')")
    c.commit()
    block, _ = _push(c)
    assert not _emitted_values(block)
    assert "none changed" in " ".join(block)


def test_only_the_partition_that_moved_is_pushed(tmp_path):
    c = _audit_partition_db(tmp_path)
    _, d = _push(c)
    P.record_partition_digests(c, "bank_audit_capital", d["bank_audit_capital"])

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
    P.record_partition_digests(c, "bank_audit_capital", d["bank_audit_capital"])

    c.execute("INSERT INTO bank_audit_capital VALUES "
              "('ISCTR','2026Q1','consolidated','cet1',500.0,datetime('now'))")
    c.commit()
    block, _ = _push(c)
    assert "ISCTR" in " ".join(_emitted_values(block))


def test_force_partitions_overrides_the_skip(tmp_path):
    c = _audit_partition_db(tmp_path)
    _, d = _push(c)
    P.record_partition_digests(c, "bank_audit_capital", d["bank_audit_capital"])
    block, _ = _push(c, skip_partitions=False)
    assert _emitted_values(block), "--force-partitions must resend everything"


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
    P.record_partition_digests(c, "bank_audit_capital", d["bank_audit_capital"])
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
