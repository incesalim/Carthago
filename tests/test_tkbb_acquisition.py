"""Unit tests for the TKBB monthly acquisition lane (no network)."""
from __future__ import annotations

from src.tkbb import acquisition, turboard


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get(self, url, timeout=None, params=None):
        self.calls.append((url, params))
        for marker, payload in self.routes.items():
            if marker in url or (params and params.get("id") == marker):
                return _FakeResponse(payload)
        raise AssertionError(f"unexpected GET {url} params={params}")


def _dashboard_payload(measure_aliases_by_dashlet):
    """Minimal dashboard JSON: dashlets + ordered dashletmeasures aliases."""
    included = []
    for dashlet_id, aliases in measure_aliases_by_dashlet.items():
        mids = [f"{dashlet_id}-m{i}" for i in range(len(aliases))]
        included.append({
            "type": "dashlets", "id": dashlet_id,
            "attributes": {"title": "Aylara Göre"},
            "relationships": {"measures": {"data": [{"id": m} for m in mids]}},
        })
        included.extend(
            {"type": "dashletmeasures", "id": mid, "attributes": {"alias": alias}}
            for mid, alias in zip(mids, aliases)
        )
    return {"data": {}, "included": included}


REMOTE, BRANCH = acquisition.DASHLETS["remote"], acquisition.DASHLETS["branch"]


def test_resolve_measures_from_aliases():
    dashboard = _dashboard_payload(
        {REMOTE: ["Başvuru Sayısı", "Kazanılan Müşteri Sayısı"]})
    resolved = acquisition.resolve_measures(dashboard, REMOTE)
    assert resolved == {"m0": ("applications", "Başvuru Sayısı"),
                        "m1": ("customers", "Kazanılan Müşteri Sayısı")}


def test_resolve_measures_unknown_alias_raises():
    dashboard = _dashboard_payload({REMOTE: ["Bilinmeyen Ölçü"]})
    try:
        acquisition.resolve_measures(dashboard, REMOTE)
    except turboard.TurboardError as exc:
        assert "matches no known measure" in str(exc)
    else:
        raise AssertionError("expected TurboardError")


def test_resolve_measures_duplicate_slug_raises():
    dashboard = _dashboard_payload(
        {REMOTE: ["Müşteri Sayısı", "Kazanılan Müşteri Sayısı"]})
    try:
        acquisition.resolve_measures(dashboard, REMOTE)
    except turboard.TurboardError as exc:
        assert "ambiguous" in str(exc)
    else:
        raise AssertionError("expected TurboardError")


def test_resolve_measures_missing_dashlet_raises():
    dashboard = _dashboard_payload({REMOTE: ["Başvuru Sayısı"]})
    try:
        acquisition.resolve_measures(dashboard, "DL-GONE")
    except turboard.TurboardError as exc:
        assert "DL-GONE" in str(exc)
    else:
        raise AssertionError("expected TurboardError")


def test_period_from_tarih():
    assert acquisition._period_from_tarih("2026-05-01") == "2026-05"
    assert acquisition._period_from_tarih("not a date") is None


def test_fetch_all_shape():
    dashboard = _dashboard_payload({
        REMOTE: ["Başvuru Sayısı", "Kazanılan Müşteri Sayısı"],
        BRANCH: ["Başvuru Sayısı", "Kazanılan Müşteri Sayısı"],
    })
    data = {"data": [{"type": "data", "id": "x", "attributes": {
        "rows": {"TARIH": ["2026-05-01", "2026-04-01"],
                 "m0": [286224.0, 216533.0],
                 "m1": [161095.0, 122861.0]},
        "is_warning": False, "meta": {}}}]}
    session = _FakeSession({"/api/v1/dashboardviews/": dashboard,
                            "/api/v1/data/": data})
    stats = acquisition.fetch_all(session=session)
    # 2 series x 2 measures x 2 months
    assert len(stats) == 8
    remote_customers = {
        s.period: s.value for s in stats
        if s.series == "remote" and s.measure == "customers"}
    assert remote_customers == {"2026-05": 161095.0, "2026-04": 122861.0}
    assert all(s.measure_tr for s in stats)


def test_upsert_acquisition_accumulates():
    import sqlite3

    from src.tkbb import loader, schema

    conn = sqlite3.connect(":memory:")
    schema.init_acquisition_schema(conn)
    older = acquisition.TkbbAcqStat("2025-07", "remote", "customers",
                                    "Kazanılan Müşteri Sayısı", 100.0, "DL-A")
    loader.upsert_acquisition(conn, [older])
    # A later run without 2025-07 in its window must not remove the old row.
    newer = acquisition.TkbbAcqStat("2026-05", "remote", "customers",
                                    "Kazanılan Müşteri Sayısı", 200.0, "DL-A")
    loader.upsert_acquisition(conn, [newer])
    count = conn.execute("SELECT COUNT(*) FROM tkbb_acquisition_stats").fetchone()[0]
    assert count == 2
