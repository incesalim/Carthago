"""Unit tests for the TKBB quarterly digital lane (no network)."""
from __future__ import annotations

import requests

from src.tkbb import digital, turboard


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class _FakeSession:
    """Records every GET; answers from a {url_substring: payload} table."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get(self, url, timeout=None, params=None):
        self.calls.append((url, params))
        for marker, payload in self.routes.items():
            if marker in url:
                return _FakeResponse(payload)
        raise AssertionError(f"unexpected GET {url}")


def _data_payload(rows, is_warning=False):
    return {"data": [{"type": "data", "id": "DL-X",
                      "attributes": {"rows": rows, "is_warning": is_warning,
                                     "meta": {}}}]}


# ---------------------------------------------------------------------------
# period_from_label — both label spacings observed live must parse
# ---------------------------------------------------------------------------

def test_period_from_label_spacing_variants():
    assert digital.period_from_label("2026 1.Dönem") == "2026-03"
    assert digital.period_from_label("2020 1. Dönem") == "2020-03"
    assert digital.period_from_label("2025 4.Dönem") == "2025-12"
    assert digital.period_from_label(" 2023 3 . Dönem ") == "2023-09"


def test_period_from_label_rejects_garbage():
    assert digital.period_from_label("Mart 2026") is None
    assert digital.period_from_label("2026 5.Dönem") is None
    assert digital.period_from_label("") is None


# ---------------------------------------------------------------------------
# filters double encoding — inner quote here, requests encodes once more
# ---------------------------------------------------------------------------

def test_get_data_double_encodes_filter_value():
    session = _FakeSession({"/api/v1/data/": _data_payload({"m0": [1.0]})})
    turboard.get_data("DL-X", "info_cell", "db-Y",
                      filter_id="dbmfl-hbs6a2o18k1e132",
                      filter_value="2025 4.Dönem", session=session)
    _, params = session.calls[0]
    assert params["filters"] == "dbmfl-hbs6a2o18k1e132=2025%204.D%C3%B6nem"
    # After requests' own encoding pass the wire format is double-encoded:
    prepared = requests.Request(
        "GET", turboard.BASE + "/api/v1/data/", params=params
    ).prepare()
    assert "filters=dbmfl-hbs6a2o18k1e132%3D2025%25204.D%25C3%25B6nem" in prepared.url


# ---------------------------------------------------------------------------
# fetch_period — the three response shapes (info_cell / pie / map)
# ---------------------------------------------------------------------------

def _fetch_one(monkeypatch, spec, rows):
    """Run fetch_period with only ``spec`` pinned and one canned response."""
    monkeypatch.setattr(digital, "DASHLETS", [spec])
    session = _FakeSession({"/api/v1/data/": _data_payload(rows)})
    return digital.fetch_period("2025 4.Dönem", session=session)


def test_fetch_period_info_cell_scalar(monkeypatch):
    spec = digital.DASHLETS[0]  # active_customers info_cell
    stats = _fetch_one(monkeypatch, spec, {"m0": [7879396.0]})
    assert len(stats) == 1
    s = stats[0]
    assert (s.period, s.metric, s.breakdown, s.dim_slug) == \
        ("2025-12", "active_customers", "total", "total")
    assert s.value == 7879396.0
    assert s.unit == "persons"
    assert s.period_tr == "2025 4.Dönem"


def test_fetch_period_pie_dimensions(monkeypatch):
    spec = next(s for s in digital.DASHLETS if s.metric == "txn_volume_segment")
    rows = {"MÜŞTERİ SEGMENTİ": ["Kurumsal", "Bireysel"],
            "m0": [4484121775617.0, 3420478669008.0]}
    stats = _fetch_one(monkeypatch, spec, rows)
    assert {(s.dim_slug, s.value) for s in stats} == {
        ("corporate", 4484121775617.0), ("individual", 3420478669008.0)}
    assert all(s.breakdown == "segment" and s.unit == "try" for s in stats)


def test_fetch_period_map_provinces(monkeypatch):
    spec = next(s for s in digital.DASHLETS if s.breakdown == "province")
    rows = {"İLLER": ["İstanbul", "Şanlıurfa"], "m0": [2500000.0, 180000.0]}
    stats = _fetch_one(monkeypatch, spec, rows)
    assert {s.dim_slug for s in stats} == {"istanbul", "sanliurfa"}
    assert {s.dim_tr for s in stats} == {"İstanbul", "Şanlıurfa"}


def test_fetch_period_skips_warning_and_empty(monkeypatch):
    spec = digital.DASHLETS[0]
    monkeypatch.setattr(digital, "DASHLETS", [spec])
    session = _FakeSession(
        {"/api/v1/data/": _data_payload({"m0": [1.0]}, is_warning=True)})
    assert digital.fetch_period("2025 4.Dönem", session=session) == []
    stats = _fetch_one(monkeypatch, spec, {})
    assert stats == []


# ---------------------------------------------------------------------------
# dimension slug mapping
# ---------------------------------------------------------------------------

def test_channel_mix_slugs():
    f = digital.dim_slug_for
    assert f("channel_mix",
             "Aktif müşteri sayısı-Sadece Mobil Bankacılık Kullanan") == "mobile_only"
    assert f("channel_mix",
             "Aktif müşteri sayısı-Sadece İnternet Bankacılığı Kullanan") == "internet_only"
    assert f("channel_mix",
             "Aktif müşteri sayısı-Hem İnternet Hem Mobil Bankacılık Kullanan") == "both"


def test_segment_slugs_and_fallback():
    assert digital.dim_slug_for("segment", "Bireysel") == "individual"
    assert digital.dim_slug_for("segment", "Kurumsal") == "corporate"
    # unmatched labels fall back to plain slugify
    assert digital.dim_slug_for("category", "Para Transferleri") == "para_transferleri"
    assert digital.dim_slug_for("segment", "Öteki") == "oteki"


# ---------------------------------------------------------------------------
# verify_dashboard — raise on missing id, warn on title drift
# ---------------------------------------------------------------------------

def _dashboard_payload(dashlets):
    return {"data": {}, "included": [
        {"type": "dashlets", "id": did, "attributes": {"title": title}}
        for did, title in dashlets
    ]}


def test_verify_dashboard_ok_and_drift(monkeypatch):
    live = [(s.dashlet_id, s.title_tr) for s in digital.DASHLETS]
    session = _FakeSession({"/api/v1/dashboardviews/": _dashboard_payload(live)})
    assert digital.verify_dashboard(session=session) == []

    drifted = [(d, "Yeni Başlık") if d == digital.DASHLETS[0].dashlet_id else (d, t)
               for d, t in live]
    session = _FakeSession({"/api/v1/dashboardviews/": _dashboard_payload(drifted)})
    warnings = digital.verify_dashboard(session=session)
    assert len(warnings) == 1 and "title drift" in warnings[0]


def test_verify_dashboard_missing_id_raises():
    live = [(s.dashlet_id, s.title_tr) for s in digital.DASHLETS[1:]]
    session = _FakeSession({"/api/v1/dashboardviews/": _dashboard_payload(live)})
    try:
        digital.verify_dashboard(session=session)
    except turboard.TurboardError as exc:
        assert digital.DASHLETS[0].dashlet_id in str(exc)
    else:
        raise AssertionError("expected TurboardError")


# ---------------------------------------------------------------------------
# loader idempotency
# ---------------------------------------------------------------------------

def test_upsert_stats_idempotent():
    import sqlite3

    from src.tkbb import loader, schema

    conn = sqlite3.connect(":memory:")
    schema.init_schema(conn)
    stat = digital.TkbbStat("2025-12", "active_customers", "total", "total", "",
                            "persons", 7879396.0, "2025 4.Dönem", "DL-X")
    loader.upsert_stats(conn, [stat])
    stat.value = 7900000.0  # revision overwrites in place
    loader.upsert_stats(conn, [stat])
    rows = conn.execute(
        "SELECT COUNT(*), MAX(value) FROM tkbb_digital_stats").fetchone()
    assert rows == (1, 7900000.0)
