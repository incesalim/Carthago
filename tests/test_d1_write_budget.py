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
