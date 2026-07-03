"""Minimal client for the Turboard BI JSON:API behind TKBB's Veri Peteği.

Turboard (https://veri-petegi.tkbb.org.tr) serves public dashboards whose REST
API needs no authentication. Three endpoints cover ingestion:

- ``GET /api/v1/dashboardviews/{db_id}/`` — dashboard definition; ``included``
  carries the dashlets (id/title/type), their dimensions/measures, and the
  merged-filter definitions.
- ``GET /api/v1/dashboardmergedfilters/{dbmfl_id}/`` — the verbatim value list
  of a dashboard filter (``data.attributes.info.values``).
- ``GET /api/v1/data/?id=…&type=…&refresh_cache=false&dashboard=…[&filters=…]``
  — one dashlet's data: ``data[0].attributes.rows`` maps each dimension name to
  a list of labels plus ``m0``/``m1``/… measure columns.

Filter-encoding gotcha: the value inside the ``filters`` query param is itself
URL-encoded once more than the outer parameter (verified against the live app),
so ``filters=dbmfl-…%3D2025%25204.D%25C3%25B6nem`` decodes to
``dbmfl-…=2025 4.Dönem``. ``get_data`` builds this by quoting the value before
handing the pair to ``requests`` (which encodes the whole param once more).
"""
from __future__ import annotations

import urllib.parse

import requests

BASE = "https://veri-petegi.tkbb.org.tr"

_HEADERS = {
    # Same convention as src/tbb/client.py: present a browser UA.
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


class TurboardError(RuntimeError):
    """HTTP failure or unexpected response shape from the Turboard API."""


class TurboardWarning(TurboardError):
    """The API answered with ``is_warning: true`` for a dashlet."""


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(_HEADERS)
    return s


def _get_json(url: str, session: requests.Session | None = None, **kwargs) -> dict:
    s = session or _session()
    resp = s.get(url, timeout=60, **kwargs)
    if resp.status_code != 200:
        raise TurboardError(f"GET {url} -> HTTP {resp.status_code}")
    try:
        payload = resp.json()
    except ValueError as exc:
        raise TurboardError(f"GET {url} -> non-JSON response") from exc
    if isinstance(payload, dict) and payload.get("errors"):
        raise TurboardError(f"GET {url} -> API error: {payload['errors']}")
    return payload


def get_dashboard(db_id: str, session: requests.Session | None = None) -> dict:
    """Full dashboard-definition JSON (``data`` + ``included``)."""
    return _get_json(f"{BASE}/api/v1/dashboardviews/{db_id}/", session=session)


def get_filter_values(dbmfl_id: str, session: requests.Session | None = None) -> list[str]:
    """Verbatim value list of a dashboard merged filter (e.g. period labels).

    Labels must always be taken from here, never constructed — TKBB's labels
    are inconsistently spaced ("2020 1. Dönem" vs "2026 1.Dönem").
    """
    payload = _get_json(
        f"{BASE}/api/v1/dashboardmergedfilters/{dbmfl_id}/", session=session
    )
    try:
        values = payload["data"]["attributes"]["info"]["values"]
    except (KeyError, TypeError) as exc:
        raise TurboardError(f"merged filter {dbmfl_id}: no info.values") from exc
    return list(values)


def get_data(
    dashlet_id: str,
    dashlet_type: str,
    dashboard_id: str,
    *,
    filter_id: str | None = None,
    filter_value: str | None = None,
    session: requests.Session | None = None,
) -> dict:
    """One dashlet's data ``attributes`` dict (``rows`` + ``meta`` …).

    Raises ``TurboardWarning`` when the API flags the response, so callers can
    skip that dashlet without treating it as a transport failure. Response ids
    come back suffixed for info_cells (``DL-…-dm-…``) — never match on them.
    """
    params: dict[str, str] = {
        "id": dashlet_id,
        "type": dashlet_type,
        "refresh_cache": "false",
        "dashboard": dashboard_id,
    }
    if filter_id and filter_value is not None:
        # Inner encode; requests encodes the assembled pair once more.
        params["filters"] = f"{filter_id}={urllib.parse.quote(filter_value, safe='')}"
    payload = _get_json(f"{BASE}/api/v1/data/", session=session, params=params)
    try:
        attrs = payload["data"][0]["attributes"]
    except (KeyError, IndexError, TypeError) as exc:
        raise TurboardError(f"dashlet {dashlet_id}: unexpected data shape") from exc
    if attrs.get("is_warning"):
        raise TurboardWarning(f"dashlet {dashlet_id}: is_warning=true")
    return attrs


def included_by_type(dashboard: dict, obj_type: str) -> list[dict]:
    """All ``included`` objects of one JSON:API type from a dashboard payload."""
    return [o for o in dashboard.get("included", []) if o.get("type") == obj_type]
