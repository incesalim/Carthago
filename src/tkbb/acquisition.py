"""Lane B: TKBB monthly remote-vs-branch customer acquisition.

Source dashboard: "Uzaktan Müşteri Edinim İstatistikleri"
(https://tkbb.org.tr/veripetegi-detay/16 → Turboard ``db-a7npycau1cr5aff``).
No dashboard filter exists; the two monthly column dashlets are hard-limited
to a rolling last-12-months window (``limit_to: 12``), so history accumulates
run over run — rows must never be deleted.

Each dashlet carries TWO measures (``m0``/``m1``) whose meaning is resolved
from the measure aliases in the live dashboard definition — never assumed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import requests

from src.tkbb import turboard
from src.tkbb.digital import slugify

DASHBOARD_ID = "db-a7npycau1cr5aff"

# series slug → monthly column dashlet ("Aylara Göre …" charts)
DASHLETS = {
    "remote": "DL-9A6Y7LY530Y0PFU",   # Aylara Göre Uzaktan Müşteri Kazanımı
    "branch": "DL-FL11DAB934FRFCB",   # Aylara Göre Şubeden Müşteri Kazanımı
}

# normalized-contains marker → measure slug
_MEASURE_SLUGS = [
    ("basvuru", "applications"),
    ("musteri", "customers"),
]


@dataclass
class TkbbAcqStat:
    period: str        # 'YYYY-MM'
    series: str        # 'remote' | 'branch'
    measure: str       # 'applications' | 'customers'
    measure_tr: str    # alias verbatim from the dashboard definition
    value: float | None
    source_dashlet: str

    def key(self) -> tuple[str, str, str]:
        return (self.period, self.series, self.measure)


def resolve_measures(dashboard: dict, dashlet_id: str) -> dict[str, tuple[str, str]]:
    """``{"m0": (slug, alias_tr), "m1": …}`` for one dashlet.

    Aliases come from the ``dashletmeasures`` included objects, in dashlet
    order. Unknown or duplicate mappings raise — measure semantics must never
    be guessed.
    """
    dashlet = next(
        (d for d in turboard.included_by_type(dashboard, "dashlets")
         if d["id"] == dashlet_id),
        None,
    )
    if dashlet is None:
        raise turboard.TurboardError(
            f"dashboard {DASHBOARD_ID}: dashlet {dashlet_id} missing from live "
            f"definition — registry needs re-pinning"
        )
    measure_ids = [
        ref["id"]
        for ref in (dashlet.get("relationships", {})
                    .get("measures", {}).get("data") or [])
    ]
    measures = {
        m["id"]: m for m in turboard.included_by_type(dashboard, "dashletmeasures")
    }
    resolved: dict[str, tuple[str, str]] = {}
    seen: set[str] = set()
    for i, mid in enumerate(measure_ids):
        attrs = measures.get(mid, {}).get("attributes", {})
        alias = attrs.get("alias") or attrs.get("column_name") or ""
        norm = slugify(alias)
        slug = next((s for marker, s in _MEASURE_SLUGS if marker in norm), None)
        if slug is None:
            raise turboard.TurboardError(
                f"dashlet {dashlet_id}: measure alias {alias!r} matches no "
                f"known measure — mapping needs updating"
            )
        if slug in seen:
            raise turboard.TurboardError(
                f"dashlet {dashlet_id}: two measures map to {slug!r} "
                f"(alias {alias!r}) — mapping is ambiguous"
            )
        seen.add(slug)
        resolved[f"m{i}"] = (slug, alias)
    if not resolved:
        raise turboard.TurboardError(f"dashlet {dashlet_id}: no measures found")
    return resolved


_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-\d{2}$")


def _period_from_tarih(raw: str) -> str | None:
    """``"2026-05-01"`` → ``"2026-05"``."""
    m = _DATE_RE.match(str(raw).strip())
    return f"{m.group(1)}-{m.group(2)}" if m else None


def fetch_all(session: requests.Session | None = None) -> list[TkbbAcqStat]:
    """Both series' rolling windows → tidy rows (measure names from live aliases)."""
    dashboard = turboard.get_dashboard(DASHBOARD_ID, session=session)
    stats: list[TkbbAcqStat] = []
    for series, dashlet_id in DASHLETS.items():
        measure_map = resolve_measures(dashboard, dashlet_id)
        attrs = turboard.get_data(dashlet_id, "chart", DASHBOARD_ID, session=session)
        rows = attrs.get("rows") or {}
        dates = rows.get("TARIH") or []
        if not dates:
            print(f"  [skip] {series}: no TARIH rows")
            continue
        for m_key, (measure, alias) in measure_map.items():
            values = rows.get(m_key) or []
            for raw_date, value in zip(dates, values):
                period = _period_from_tarih(raw_date)
                if period is None or value is None:
                    continue
                stats.append(TkbbAcqStat(period, series, measure, alias,
                                         float(value), dashlet_id))
    return stats
