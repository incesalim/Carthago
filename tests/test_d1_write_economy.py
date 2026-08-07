"""A re-fetched, UNCHANGED row must not move `downloaded_at`.

`push_to_d1` selects rows by `downloaded_at`, so any lane that re-fetches an
overlapping window and rewrites it with INSERT OR REPLACE re-sends every row in
that window to D1 carrying identical values. D1 bills rows written (~1000x the
price of a read, index maintenance counted), so that is pure cost — and it is
invisible: the run succeeds, the data is correct, only the bill moves.

Seven ingestion paths have carried this bug:
  - EVDS   (fixed 2026-07-27) — whole history re-fetched daily, ~17M rows/month
  - weekly (fixed 2026-08-04) — trailing 13-week window, ~26,600 rows a run,
                                of which only the newest week is ever new
  - TEFAS  (fixed 2026-08-04) — trailing 7-day window, re-fetched every day
  - TBB    (fixed 2026-08-06) — overlapping quarterly/cumulative workbooks
  - TKBB   (fixed 2026-08-06) — newest quarter + rolling 12-month window
  - TÜİK   (fixed 2026-08-06) — complete workbook history re-fetched weekly
  - KAP    (fixed 2026-08-06) — complete bank partitions re-fetched weekly

These tests are the gate. Each asserts that a second, identical ingest writes
nothing at all, and that a genuine revision still lands. Backdating the stamp
between the two calls is deliberate: CURRENT_TIMESTAMP has one-second
resolution, so comparing stamps written in the same second would pass even if
every row had been rewritten.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.scrapers.weekly_api_scraper import BDDKWeeklyAPIScraper  # noqa: E402
from src.tbb import loader as tbb_loader, schema as tbb_schema  # noqa: E402
from src.tbb.acquisition import AcqStat  # noqa: E402
from src.tbb.parser import TbbStat  # noqa: E402
from src.tefas.loader import upsert_day  # noqa: E402
from src.tefas.schema import init_schema as init_tefas_schema  # noqa: E402
from src.tkbb import loader as tkbb_loader, schema as tkbb_schema  # noqa: E402
from src.tkbb.acquisition import TkbbAcqStat  # noqa: E402
from src.tkbb.digital import TkbbStat  # noqa: E402

BACKDATE = "2020-01-01 00:00:00"


# --------------------------------------------------------------------------
# weekly_series — the BDDK weekly bulletin's trailing 13-week window
# --------------------------------------------------------------------------
def _payload(dates: list[str], values: list[float]) -> dict:
    return {
        "XEkseni": dates,
        "YEkseni": values,
        "Baslik": "Toplam Krediler (2+10) (TRY) [Toplam] [Sektör]",
    }


def _weekly(tmp_path, monkeypatch, payload):
    s = BDDKWeeklyAPIScraper(tmp_path / "w.db")
    s.open()
    monkeypatch.setattr(s, "_fetch", lambda *a, **k: payload)
    return s


def _stamps(conn: sqlite3.Connection) -> dict[str, str]:
    return {
        r[0]: r[1]
        for r in conn.execute("SELECT period_date, downloaded_at FROM weekly_series")
    }


def _backdate_weekly(conn: sqlite3.Connection) -> None:
    conn.execute("UPDATE weekly_series SET downloaded_at = ?", (BACKDATE,))
    conn.commit()


def test_weekly_first_fetch_writes_every_row(tmp_path, monkeypatch):
    s = _weekly(tmp_path, monkeypatch,
                _payload(["09.01.2026", "16.01.2026"], [100.5, 200.5]))
    assert s.fetch_and_store("1.0.1", "krediler", "16.01.2026", 1, "10001") == 2


def test_weekly_identical_refetch_writes_nothing(tmp_path, monkeypatch):
    """The 13-week window re-arrives unchanged: not one row may be rewritten."""
    s = _weekly(tmp_path, monkeypatch,
                _payload(["09.01.2026", "16.01.2026"], [100.5, 200.5]))
    s.fetch_and_store("1.0.1", "krediler", "16.01.2026", 1, "10001")
    _backdate_weekly(s.conn)

    assert s.fetch_and_store("1.0.1", "krediler", "16.01.2026", 1, "10001") == 0
    assert set(_stamps(s.conn).values()) == {BACKDATE}
    assert s.stats["rows_unchanged"] == 2


def test_weekly_revision_still_writes_only_the_revised_row(tmp_path, monkeypatch):
    """A restated figure must land — and must not drag its neighbours with it."""
    s = _weekly(tmp_path, monkeypatch,
                _payload(["09.01.2026", "16.01.2026"], [100.5, 200.5]))
    s.fetch_and_store("1.0.1", "krediler", "16.01.2026", 1, "10001")
    _backdate_weekly(s.conn)

    monkeypatch.setattr(
        s, "_fetch",
        lambda *a, **k: _payload(["09.01.2026", "16.01.2026"], [100.5, 999.0]))
    assert s.fetch_and_store("1.0.1", "krediler", "16.01.2026", 1, "10001") == 1

    stamps = _stamps(s.conn)
    assert stamps["2026-01-09"] == BACKDATE      # untouched
    assert stamps["2026-01-16"] != BACKDATE      # rewritten
    assert s.conn.execute(
        "SELECT value FROM weekly_series WHERE period_date = '2026-01-16'"
    ).fetchone()[0] == 999.0


def test_weekly_new_week_writes(tmp_path, monkeypatch):
    """The window slides: the one genuinely new week is the one that costs."""
    s = _weekly(tmp_path, monkeypatch,
                _payload(["09.01.2026", "16.01.2026"], [100.5, 200.5]))
    s.fetch_and_store("1.0.1", "krediler", "16.01.2026", 1, "10001")
    _backdate_weekly(s.conn)

    monkeypatch.setattr(
        s, "_fetch",
        lambda *a, **k: _payload(
            ["09.01.2026", "16.01.2026", "23.01.2026"], [100.5, 200.5, 300.5]))
    assert s.fetch_and_store("1.0.1", "krediler", "16.01.2026", 1, "10001") == 1


def test_weekly_null_value_roundtrips_as_unchanged(tmp_path, monkeypatch):
    """`null` is not `0` — and a stored NULL that comes back NULL is unchanged."""
    s = _weekly(tmp_path, monkeypatch, _payload(["09.01.2026"], [None]))
    assert s.fetch_and_store("1.0.1", "krediler", "09.01.2026", 1, "10001") == 1
    _backdate_weekly(s.conn)
    assert s.fetch_and_store("1.0.1", "krediler", "09.01.2026", 1, "10001") == 0
    assert set(_stamps(s.conn).values()) == {BACKDATE}


# --------------------------------------------------------------------------
# tefas_* — the fund lane's trailing 7-day window
# --------------------------------------------------------------------------
def _tefas_conn(tmp_path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "t.db")
    init_tefas_schema(conn)
    return conn


def _day(manager_aum: float = 1_000.0, top_aum: float = 500.0) -> dict:
    return {
        "tefas_manager_daily": [("2026-01-16", "YAT", "AK PORTFÖY", manager_aum, 12, 900)],
        "tefas_category_daily": [("2026-01-16", "YAT", "Hisse", 700.0, 5, 400)],
        "tefas_allocation_daily": [("2026-01-16", "YAT", "Hisse Senedi", 31.5, 700.0)],
        "tefas_top_funds": [
            ("2026-01-16", "YAT", "AFA", "Ak Portföy Hisse", "AK PORTFÖY", 1, top_aum,
             1.234, 300),
        ],
    }


def _backdate_tefas(conn: sqlite3.Connection) -> None:
    for t in ("tefas_manager_daily", "tefas_category_daily",
              "tefas_allocation_daily", "tefas_top_funds"):
        conn.execute(f"UPDATE {t} SET downloaded_at = ?", (BACKDATE,))
    conn.commit()


def _tefas_stamps(conn: sqlite3.Connection) -> set[str]:
    out: set[str] = set()
    for t in ("tefas_manager_daily", "tefas_category_daily",
              "tefas_allocation_daily", "tefas_top_funds"):
        out |= {r[0] for r in conn.execute(f"SELECT downloaded_at FROM {t}")}
    return out


def test_tefas_first_ingest_writes_every_row(tmp_path):
    conn = _tefas_conn(tmp_path)
    assert upsert_day(conn, _day()) == 4


def test_tefas_identical_reingest_writes_nothing(tmp_path):
    """The 7-day window re-arrives: six of seven days are always identical."""
    conn = _tefas_conn(tmp_path)
    upsert_day(conn, _day())
    _backdate_tefas(conn)

    assert upsert_day(conn, _day()) == 0
    assert _tefas_stamps(conn) == {BACKDATE}


def test_tefas_revision_writes_only_the_changed_table(tmp_path):
    conn = _tefas_conn(tmp_path)
    upsert_day(conn, _day())
    _backdate_tefas(conn)

    assert upsert_day(conn, _day(manager_aum=1_250.0)) == 1
    assert conn.execute(
        "SELECT aum_try FROM tefas_manager_daily"
    ).fetchone()[0] == 1_250.0
    # The three untouched tables keep their old stamp, so the push skips them.
    assert {r[0] for r in conn.execute(
        "SELECT downloaded_at FROM tefas_category_daily")} == {BACKDATE}


def test_tefas_dropped_top_fund_still_queues_its_delete(tmp_path):
    """The change-filter must not hide a fund that fell out of the top 15 —
    the stale sweep runs over the full incoming set, before the filter."""
    conn = _tefas_conn(tmp_path)
    upsert_day(conn, _day())

    replaced = _day()
    replaced["tefas_top_funds"] = [
        ("2026-01-16", "YAT", "TTE", "Test Portföy Hisse", "TEST PORTFÖY", 1, 500.0,
         1.234, 300),
    ]
    upsert_day(conn, replaced)

    assert {r[0] for r in conn.execute("SELECT fon_kodu FROM tefas_top_funds")} == {"TTE"}
    queued = [r[0] for r in conn.execute("SELECT sql FROM d1_pending_deletes")]
    assert len(queued) == 1
    assert "fon_kodu='AFA'" in queued[0]


# --------------------------------------------------------------------------
# Saturday catch-up sources - overlapping source files/windows
# --------------------------------------------------------------------------
def test_tbb_digital_identical_refetch_writes_nothing():
    conn = sqlite3.connect(":memory:")
    tbb_schema.init_schema(conn)
    stat = TbbStat(
        "2026-06", "digital", "total", "I", "Customers", "Active",
        "active", "persons_thousands", 42.0, "Digital",
    )
    assert tbb_loader.upsert_stats(conn, [stat]) == 1
    conn.execute("UPDATE tbb_digital_stats SET downloaded_at=?", (BACKDATE,))
    conn.commit()

    assert tbb_loader.upsert_stats(conn, [stat]) == 0
    assert conn.execute(
        "SELECT downloaded_at FROM tbb_digital_stats"
    ).fetchone()[0] == BACKDATE


def test_tbb_acquisition_revision_writes_only_when_value_moves():
    conn = sqlite3.connect(":memory:")
    tbb_schema.init_acquisition_schema(conn)
    first = AcqStat("2026-06", "individual", "branch", "Branch", 100.0)
    assert tbb_loader.upsert_acquisition(conn, [first]) == 1
    conn.execute("UPDATE tbb_acquisition_stats SET downloaded_at=?", (BACKDATE,))
    conn.commit()

    assert tbb_loader.upsert_acquisition(conn, [first]) == 0
    revised = AcqStat("2026-06", "individual", "branch", "Branch", 101.0)
    assert tbb_loader.upsert_acquisition(conn, [revised]) == 1
    assert conn.execute(
        "SELECT value FROM tbb_acquisition_stats"
    ).fetchone()[0] == 101.0


def test_tkbb_digital_identical_refetch_writes_nothing():
    conn = sqlite3.connect(":memory:")
    tkbb_schema.init_schema(conn)
    stat = TkbbStat(
        "2026-06", "active_customers", "total", "total", "", "persons",
        7_900_000.0, "2026 Q2", "DL-X",
    )
    assert tkbb_loader.upsert_stats(conn, [stat]) == 1
    conn.execute("UPDATE tkbb_digital_stats SET downloaded_at=?", (BACKDATE,))
    conn.commit()

    assert tkbb_loader.upsert_stats(conn, [stat]) == 0
    assert conn.execute(
        "SELECT downloaded_at FROM tkbb_digital_stats"
    ).fetchone()[0] == BACKDATE


def test_tkbb_acquisition_identical_refetch_writes_nothing():
    conn = sqlite3.connect(":memory:")
    tkbb_schema.init_acquisition_schema(conn)
    stat = TkbbAcqStat(
        "2026-06", "remote", "customers", "Customers", 200.0, "DL-A",
    )
    assert tkbb_loader.upsert_acquisition(conn, [stat]) == 1
    conn.execute("UPDATE tkbb_acquisition_stats SET downloaded_at=?", (BACKDATE,))
    conn.commit()

    assert tkbb_loader.upsert_acquisition(conn, [stat]) == 0
    assert conn.execute(
        "SELECT downloaded_at FROM tkbb_acquisition_stats"
    ).fetchone()[0] == BACKDATE


def test_tuik_identical_refetch_writes_nothing(tmp_path, monkeypatch):
    from scripts import update_tuik
    from src.scrapers.evds_scraper import init_schema as init_evds_schema
    from src.tuik.parser import Row

    db = tmp_path / "tuik.db"
    with sqlite3.connect(db) as conn:
        init_evds_schema(conn)
    monkeypatch.setattr(update_tuik, "DB", db)
    blocks = [([Row("TUIK.TEST", "2026-06-01", 100.0, "Test")], "tuik_test")]

    assert update_tuik.write_db(blocks) == 1
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE evds_series SET downloaded_at=?", (BACKDATE,))
        conn.commit()
    assert update_tuik.write_db(blocks) == 0
    with sqlite3.connect(db) as conn:
        assert conn.execute(
            "SELECT downloaded_at FROM evds_series"
        ).fetchone()[0] == BACKDATE
