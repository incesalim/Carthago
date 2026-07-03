"""Lane A: TKBB quarterly digital-banking statistics.

Source dashboard: "Dijital Bankacılık İstatistikleri"
(https://tkbb.org.tr/veripetegi-detay/15 → Turboard ``db-a777d0et51c80tf``),
filtered by the quarterly "Dönem" merged filter. Values are stored RAW
(persons / transaction counts / TRY) — the web layer scales for display.

The dashlet ids are pinned in ``DASHLETS``; ``verify_dashboard`` cross-checks
them against the live dashboard definition and fails loudly if TKBB rebuilds
the dashboard (title drift only warns).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import requests

from src.tkbb import turboard

DASHBOARD_ID = "db-a777d0et51c80tf"
PERIOD_FILTER_ID = "dbmfl-hbs6a2o18k1e132"


@dataclass(frozen=True)
class DashletSpec:
    metric: str
    dashlet_id: str
    dashlet_type: str  # 'info_cell' | 'chart' | 'map'
    breakdown: str     # 'total' | 'channel_mix' | 'channel' | 'segment' | 'category' | 'province'
    unit: str          # 'persons' | 'count' | 'try'
    title_tr: str      # expected title, drift check only (contains-match)


DASHLETS: list[DashletSpec] = [
    DashletSpec("active_customers", "DL-0ED76DDS3C6FOA0", "info_cell", "total",
                "persons", "Aktif Dijital Bankacılık Müşteri Sayısı"),
    DashletSpec("txn_volume", "DL-8AFD2FEFENY1V0E", "info_cell", "total",
                "try", "Toplam İşlem Hacmi"),
    DashletSpec("txn_count", "DL-AFFDC1ZB1XZXN21", "info_cell", "total",
                "count", "Toplam İşlem Adedi"),
    DashletSpec("active_customers_mix", "DL-F11AD187SF9228O", "chart", "channel_mix",
                "persons", "Aktif Dijital Bankacılık Müşteri Sayısı"),
    DashletSpec("active_customers_province", "DL-5C0QC7E26427A0A", "map", "province",
                "persons", "İl Bazlı Aktif Dijital Bankacılık Müşteri Sayısı"),
    DashletSpec("txn_volume_category", "DL-811MA1BC6AB160C", "chart", "category",
                "try", "İşlem Hacimlerinin Dağılımı"),
    DashletSpec("txn_count_category", "DL-838RC491C6A631F", "chart", "category",
                "count", "İşlem Adetlerinin Dağılımı"),
    DashletSpec("txn_volume_channel", "DL-DBB6867CEC7B245", "chart", "channel",
                "try", "Dijital Bankacılık Kanallarına Göre İşlem Hacmi"),
    DashletSpec("txn_count_channel", "DL-1720EAN690AAAE3", "chart", "channel",
                "count", "Dijital Bankacılık Kanallarına Göre İşlem Adedi"),
    DashletSpec("txn_volume_segment", "DL-DVVC7C5D3AF2W2C", "chart", "segment",
                "try", "İşlem Hacmi"),
    DashletSpec("txn_count_segment", "DL-F0570C653K70731", "chart", "segment",
                "count", "İşlem Adedi"),
]
# "Detay" grid dashlets are drill-throughs that error without a parent context —
# intentionally not ingested.


@dataclass
class TkbbStat:
    period: str          # 'YYYY-MM' quarter-end
    metric: str
    breakdown: str
    dim_slug: str        # 'total' for scalars
    dim_tr: str          # '' for scalars
    unit: str
    value: float | None
    period_tr: str       # verbatim filter label
    source_dashlet: str

    def key(self) -> tuple[str, str, str, str]:
        return (self.period, self.metric, self.breakdown, self.dim_slug)


# "2025 4.Dönem" and "2020 1. Dönem" both appear — tolerate optional spacing.
_PERIOD_LABEL_RE = re.compile(r"^\s*(\d{4})\s+([1-4])\s*\.\s*Dönem\s*$")

_QUARTER_END = {1: 3, 2: 6, 3: 9, 4: 12}


def period_from_label(label: str) -> str | None:
    """``"2025 4.Dönem"`` / ``"2020 1. Dönem"`` → ``"2025-12"`` / ``"2020-03"``."""
    m = _PERIOD_LABEL_RE.match(str(label))
    if not m:
        return None
    year, quarter = int(m.group(1)), int(m.group(2))
    return f"{year:04d}-{_QUARTER_END[quarter]:02d}"


def slugify(text: str) -> str:
    """ASCII slug stable across Turkish spellings (same rules as src.tbb.parser)."""
    s = text.replace("İ", "i").replace("ı", "i").replace("ş", "s")
    s = s.replace("ğ", "g").replace("ç", "c").replace("ö", "o").replace("ü", "u")
    s = s.replace("Ş", "s").replace("Ğ", "g").replace("Ç", "c")
    s = s.replace("Ö", "o").replace("Ü", "u")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_").lower()
    return s or "value"


# Curated dimension slugs; anything unmatched falls back to slugify(label).
# channel_mix labels look like "Aktif müşteri sayısı-Sadece Mobil Bankacılık
# Kullanan" — matched on the normalized label via contains.
_CHANNEL_MIX_SLUGS = [
    ("sadece_mobil", "mobile_only"),
    ("sadece_internet", "internet_only"),
    ("hem_internet_hem_mobil", "both"),
]
_SEGMENT_SLUGS = {"bireysel": "individual", "kurumsal": "corporate"}


def dim_slug_for(breakdown: str, label: str) -> str:
    s = slugify(label)
    if breakdown == "channel_mix":
        for marker, slug in _CHANNEL_MIX_SLUGS:
            if marker in s:
                return slug
    elif breakdown == "segment":
        mapped = _SEGMENT_SLUGS.get(s)
        if mapped:
            return mapped
    return s


def verify_dashboard(session: requests.Session | None = None) -> list[str]:
    """Cross-check the pinned dashlet registry against the live dashboard.

    Missing dashlet id → ``TurboardError`` (fail loudly: TKBB rebuilt the
    dashboard and the registry must be re-pinned). Title drift → warning
    strings returned for logging.
    """
    dashboard = turboard.get_dashboard(DASHBOARD_ID, session=session)
    live = {
        d["id"]: d.get("attributes", {}).get("title", "")
        for d in turboard.included_by_type(dashboard, "dashlets")
    }
    warnings: list[str] = []
    missing = [spec.dashlet_id for spec in DASHLETS if spec.dashlet_id not in live]
    if missing:
        raise turboard.TurboardError(
            f"dashboard {DASHBOARD_ID}: pinned dashlets missing from live "
            f"definition: {missing} — registry needs re-pinning"
        )
    for spec in DASHLETS:
        title = live[spec.dashlet_id]
        if spec.title_tr not in title:
            warnings.append(
                f"{spec.dashlet_id}: title drift: expected ~'{spec.title_tr}', "
                f"live '{title}'"
            )
    return warnings


def _dim_key(rows: dict) -> str | None:
    """The single non-measure key of a ``rows`` dict (dimension column name)."""
    keys = [k for k in rows if not re.fullmatch(r"m\d+", k)]
    return keys[0] if len(keys) == 1 else None


def fetch_period(
    period_label: str, session: requests.Session | None = None
) -> list[TkbbStat]:
    """All pinned dashlets for one verbatim period label → tidy rows.

    A dashlet answering ``is_warning`` or with empty rows is skipped with a
    console note (the quarter may simply not be published yet for it).
    """
    period = period_from_label(period_label)
    if period is None:
        raise ValueError(f"unparseable period label: {period_label!r}")
    stats: list[TkbbStat] = []
    for spec in DASHLETS:
        try:
            attrs = turboard.get_data(
                spec.dashlet_id, spec.dashlet_type, DASHBOARD_ID,
                filter_id=PERIOD_FILTER_ID, filter_value=period_label,
                session=session,
            )
        except turboard.TurboardWarning as exc:
            print(f"  [skip] {spec.metric} @ {period_label}: {exc}")
            continue
        rows = attrs.get("rows") or {}
        if spec.dashlet_type == "info_cell":
            values = rows.get("m0") or []
            if not values or values[0] is None:
                print(f"  [skip] {spec.metric} @ {period_label}: empty")
                continue
            stats.append(TkbbStat(period, spec.metric, spec.breakdown, "total", "",
                                  spec.unit, float(values[0]), period_label,
                                  spec.dashlet_id))
        else:
            dim = _dim_key(rows)
            if dim is None or not rows.get(dim):
                print(f"  [skip] {spec.metric} @ {period_label}: no rows")
                continue
            for label, value in zip(rows[dim], rows.get("m0") or []):
                if value is None:
                    continue
                stats.append(TkbbStat(period, spec.metric, spec.breakdown,
                                      dim_slug_for(spec.breakdown, str(label)),
                                      str(label), spec.unit, float(value),
                                      period_label, spec.dashlet_id))
    _sanity_check(stats, period_label)
    return stats


def _sanity_check(stats: list[TkbbStat], period_label: str) -> None:
    """Σ(channel_mix) should reproduce the active_customers scalar (±1%)."""
    total = next((s.value for s in stats
                  if s.metric == "active_customers" and s.breakdown == "total"), None)
    mix = [s.value for s in stats if s.breakdown == "channel_mix" and s.value is not None]
    if total and mix:
        mix_sum = sum(mix)
        if abs(mix_sum - total) > 0.01 * total:
            print(f"  [warn] {period_label}: channel_mix sum {mix_sum:,.0f} "
                  f"deviates from total {total:,.0f} by >1%")
