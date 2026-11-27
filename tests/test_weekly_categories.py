"""The weekly bulletin's tables 8 and 9 (2026-11-27), the columns each table
prints, and the unit the public API states for every weekly series.

Probed against BDDK on 2026-11-27: ten tables exist, category 8 (securities
held at banks, market value) prints 45 charts, category 9 (FX position) ten,
and category 10 has printed 0.0 for every cell since 11.12.2020.
"""
import json

import pytest

import update_weekly  # on sys.path via pyproject pythonpath
from scripts import build_api_catalog as catalog
from src.scrapers import weekly_api_scraper as w


# --- which tables, and which columns -----------------------------------------


def test_tables_eight_and_nine_are_read_and_ten_is_not():
    assert w.CATEGORY_NAMES[8] == "saklanan_menkul_degerler"
    assert w.CATEGORY_NAMES[9] == "yp_pozisyonu"
    assert 10 not in w.CATEGORY_NAMES


def test_the_fx_position_table_is_fetched_on_its_total_column_only():
    # Asked for sutun 1 or 2 it answers with a real title and a full series of
    # 0.0 — "this leg does not exist", not a disclosed zero.
    assert w.columns_for(9) == (3,)
    assert w.columns_for(8) == (1, 2, 3)
    assert w.columns_for(1) == (1, 2, 3)


def test_every_weekly_category_has_an_api_token():
    # A slug with no token is skipped by the catalog builder ("never invent a
    # code"), so a misspelling here would drop a whole table from /api/v1
    # without a failure anywhere.
    assert set(w.CATEGORY_NAMES.values()) == set(catalog.WEEKLY_DATASETS)
    assert len(set(catalog.WEEKLY_DATASETS.values())) == len(catalog.WEEKLY_DATASETS)


# --- the unit ----------------------------------------------------------------


def test_weekly_series_are_labelled_in_million_tl():
    # BDDK prints the weekly bulletin in million TL. /api/v1/series returned
    # sector TL loans of 18,523,337.66 on 2026-11-06 as "thousand TL": 18.5
    # billion lira, against 18.5 trillion.
    assert catalog.WEEKLY_UNIT == "million TL"


def test_weekly_catalog_rows_carry_the_unit(tmp_path):
    conn = _sqlite_with_weekly(
        ("yp_pozisyonu", "9.0.17", "10001", "TOTAL", 15191.896),
        ("krediler", "1.0.1", "10001", "TL", 18770097.13443),
    )
    rows = catalog.build_weekly(conn)
    assert {r["unit"] for r in rows} == {"million TL"}
    by_code = {r["series_code"]: r for r in rows}
    assert by_code["BDDK.WFXPOS.I9_0_17.10001.TOT"]["value_column"] == "TOTAL"
    assert by_code["BDDK.WLOAN.I1_0_1.10001.TL"]["item_name"]


# --- the catalogue probe -----------------------------------------------------


def _sqlite_with_weekly(*rows):
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.executescript(w.SCHEMA_SQL)
    for cat, item, bt, cur, val in rows:
        conn.execute(
            "INSERT INTO weekly_series (period_date, category, item_id, item_name, "
            "bank_type_code, currency, value) VALUES ('2026-11-20', ?, ?, 'x', ?, ?, ?)",
            (cat, item, bt, cur, val))
    conn.commit()
    return conn


def _response(title, values):
    return {"Baslik": f"{title} (TRY) [Toplam] [Sektör]",
            "XEkseni": ["20.11.2026"] * len(values), "YEkseni": values}


LIVE = _response("Yabancı Para Net Genel Pozisyonu (1+4)", [15191.896])
RETIRED = {"Baslik": "Bilanço İçi Yabancı Para Pozisyonu (2-3) (TRY)  [Sektör]",
           "XEkseni": [], "YEkseni": []}
UNDEFINED = {"Baslik": "Grafik Başlığı", "XEkseni": [], "YEkseni": []}
ALL_ZERO = _response("1 Aya Kadar", [0.0, 0.0])


@pytest.mark.parametrize("body,expected", [
    (LIVE, True),
    (RETIRED, False),      # a real title over empty axes
    (UNDEFINED, False),
    (ALL_ZERO, True),      # zeros are disclosed figures: KKM wound down to 0
    ({}, False),
])
def test_a_chart_is_live_when_it_returns_dates_zeros_included(body, expected):
    assert update_weekly._chart_is_live(body) is expected


def test_zero_charts_of_live_tables_are_not_retired():
    # Measured on BDDK on 2026-11-27: a "non-zero" test dropped 4.0.12 (KKM,
    # now zero across the window) and four charts of table 7.
    assert update_weekly._chart_is_live(_response("KKM", [0.0] * 12)) is True


class _Resp:
    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


def test_the_probe_reads_each_table_and_stops_after_consecutive_misses(monkeypatch):
    calls = []

    def answer(payload):
        cid = payload["id"]
        calls.append(cid)
        cat, _, item = cid.split(".")
        if cat == "9":
            # 1-10 are the retired numbering, 11-20 the live one.
            return _Resp(LIVE if 11 <= int(item) <= 20 else RETIRED)
        if cat == "8" and int(item) <= 3:
            return _Resp(LIVE)
        return _Resp(UNDEFINED)

    class _Session:
        headers = {}

        def post(self, url, data=None, timeout=None):
            return answer(data)

    import requests
    monkeypatch.setattr(requests, "Session", _Session)
    monkeypatch.setattr(update_weekly.time, "sleep", lambda s: None)
    monkeypatch.setattr(update_weekly, "PROBE_ITEM_LIMIT", 400)
    monkeypatch.setattr(update_weekly, "CATEGORY_NAMES", {8: "eight", 9: "nine"})

    cat = update_weekly._probe_catalogue()

    assert [c for c, _ in cat[8]] == ["8.0.1", "8.0.2", "8.0.3"]
    assert [c for c, _ in cat[9]] == [f"9.0.{i}" for i in range(11, 21)]
    # 3 hits then 40 misses in table 8; 10 misses, 10 hits, then 40 misses in 9.
    assert len(calls) == 43 + 60
    assert all(not c.startswith("10.") for c in calls)
    assert cat[9][0][1] == "Yabancı Para Net Genel Pozisyonu (1+4)"


def test_a_cache_that_predates_a_table_is_regenerated(monkeypatch, tmp_path):
    stale = tmp_path / "cat.json"
    stale.write_text(json.dumps({"1": [["1.0.1", "Toplam Krediler"]]}), encoding="utf-8")
    monkeypatch.setattr(update_weekly, "CATALOGUE_FILE", stale)
    monkeypatch.setattr(update_weekly, "CATEGORY_NAMES", {1: "krediler", 9: "yp_pozisyonu"})
    fresh = {1: [("1.0.1", "Toplam Krediler")], 9: [("9.0.11", "Bilanço İçi")]}
    probed = []
    monkeypatch.setattr(update_weekly, "_probe_catalogue", lambda: probed.append(1) or fresh)

    cat = update_weekly._ensure_catalogue()
    assert probed == [1]
    assert cat == {1: [("1.0.1", "Toplam Krediler")], 9: [("9.0.11", "Bilanço İçi")]}
    # …and the regenerated cache is trusted on the next call.
    assert update_weekly._ensure_catalogue() == cat
    assert probed == [1]


def test_a_complete_cache_is_not_reprobed(monkeypatch, tmp_path):
    cache = tmp_path / "cat.json"
    cache.write_text(json.dumps({"1": [["1.0.1", "Toplam Krediler"]]}), encoding="utf-8")
    monkeypatch.setattr(update_weekly, "CATALOGUE_FILE", cache)
    monkeypatch.setattr(update_weekly, "CATEGORY_NAMES", {1: "krediler"})
    monkeypatch.setattr(update_weekly, "_probe_catalogue",
                        lambda: pytest.fail("a complete cache must not be re-probed"))
    assert update_weekly._ensure_catalogue() == {1: [("1.0.1", "Toplam Krediler")]}


# --- fetching ----------------------------------------------------------------


def _scraper_with(db_path, responses):
    s = w.BDDKWeeklyAPIScraper(db_path)
    s.open()
    s._fetch = lambda chart_id, tarih, sutun, taraf_weekly: responses[(chart_id, sutun, taraf_weekly)]
    return s


def test_an_fx_position_chart_stores_one_total_row(tmp_path):
    s = _scraper_with(tmp_path / "w.db", {
        ("9.0.17", 3, "10001"): {"Baslik": "Yabancı Para Net Genel Pozisyonu (1+4) (TRY) [Toplam] [Sektör]",
                                 "XEkseni": ["20.11.2026"], "YEkseni": [15191.896]}})
    assert s.fetch_and_store("9.0.17", w.CATEGORY_NAMES[9], "27.11.2026", 3, "10001") == 1
    rows = s.conn.execute(
        "SELECT period_date, category, item_id, item_name, bank_type_code, currency, value "
        "FROM weekly_series").fetchall()
    assert rows == [("2026-11-20", "yp_pozisyonu", "9.0.17",
                     "Yabancı Para Net Genel Pozisyonu (1+4)", "10001", "TOTAL", 15191.896)]
    s.close()


def test_backfill_counts_the_columns_each_table_prints(tmp_path):
    seen = []
    s = w.BDDKWeeklyAPIScraper(tmp_path / "w.db")
    s.open()
    s.fetch_and_store = lambda cid, slug, tarih, sutun, taraf: seen.append((cid, sutun, taraf)) or 0
    import datetime as dt
    s.backfill({8: [("8.0.1", "a")], 9: [("9.0.17", "b")]},
               dt.date(2026, 11, 20), dt.date(2026, 11, 20), bank_codes_weekly=["10001"])
    assert seen == [("8.0.1", 1, "10001"), ("8.0.1", 2, "10001"), ("8.0.1", 3, "10001"),
                    ("9.0.17", 3, "10001")]
    s.close()
