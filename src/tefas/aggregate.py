"""Aggregate raw per-fund TEFAS rows into the lane's daily tables.

Per-fund rows are never persisted (they would dwarf the R2 snapshot); each
fetch window carries every fund for the dates it covers, so per-date
aggregates computed here are always complete. Allocation percentages are
AUM-weighted over the funds that have both an info row (AUM > 0) and an
allocation row that day.
"""
from __future__ import annotations

from collections import defaultdict

from src.tefas.normalize import (
    ALLOCATION_META_KEYS,
    ASSET_ROLLUP,
    categorize_fund,
    extract_manager,
)

TOP_N = 15


def aggregate_day(
    fon_tipi: str,
    day: str,
    info_rows: list[dict],
    alloc_rows: list[dict],
) -> dict[str, list[tuple]]:
    """Aggregate one (fon_tipi, date). ``info_rows``/``alloc_rows`` are the raw
    API dicts for that date only. Returns rows keyed by table name, tuples in
    each table's column order (see ``schema.py``)."""
    managers: dict[str, list] = defaultdict(lambda: [0.0, 0, 0])  # aum, funds, investors
    categories: dict[str, list] = defaultdict(lambda: [0.0, 0, 0])
    aum_by_fund: dict[str, float] = {}

    for row in info_rows:
        aum = row.get("portfoyBuyukluk")
        investors = row.get("kisiSayisi") or 0
        key_m = extract_manager(row.get("fonUnvan") or "")
        key_c = categorize_fund(row.get("fonUnvan") or "")
        for bucket in (managers[key_m], categories[key_c]):
            if aum is not None:
                bucket[0] += aum
            bucket[1] += 1
            bucket[2] += investors
        if aum is not None and aum > 0:
            aum_by_fund[row["fonKodu"]] = aum

    # AUM-weighted allocation over funds covered by both endpoints.
    weighted: dict[str, float] = defaultdict(float)
    unknown_weight: dict[str, float] = defaultdict(float)
    aum_base = 0.0
    for row in alloc_rows:
        aum = aum_by_fund.get(row.get("fonKodu"))
        if not aum:
            continue
        aum_base += aum
        mapped_total = 0.0
        for key, val in row.items():
            if key in ALLOCATION_META_KEYS or val is None:
                continue
            cls = ASSET_ROLLUP.get(key)
            if cls is None:
                cls = "other"
                unknown_weight[key] += aum * float(val)
            weighted[cls] += aum * float(val)
            mapped_total += float(val)
        residual = 100.0 - mapped_total
        if residual > 0:
            weighted["other"] += aum * residual

    allocation_rows = [
        (day, fon_tipi, cls, total / aum_base, aum_base)
        for cls, total in sorted(weighted.items())
    ] if aum_base > 0 else []

    if unknown_weight and aum_base > 0:
        for key, w in sorted(unknown_weight.items(), key=lambda kv: -kv[1]):
            print(f"    [tefas] unknown allocation key {key!r} on {day} {fon_tipi}: "
                  f"{w / aum_base:.2f}% of covered AUM → other", flush=True)

    top = sorted(
        (r for r in info_rows if r.get("portfoyBuyukluk")),
        key=lambda r: r["portfoyBuyukluk"],
        reverse=True,
    )[:TOP_N]

    return {
        "tefas_manager_daily": [
            (day, fon_tipi, m, v[0], v[1], v[2]) for m, v in sorted(managers.items())
        ],
        "tefas_category_daily": [
            (day, fon_tipi, c, v[0], v[1], v[2]) for c, v in sorted(categories.items())
        ],
        "tefas_allocation_daily": allocation_rows,
        "tefas_top_funds": [
            (day, fon_tipi, r["fonKodu"], r.get("fonUnvan"),
             extract_manager(r.get("fonUnvan") or ""), rank,
             r["portfoyBuyukluk"], r.get("fiyat"), r.get("kisiSayisi"))
            for rank, r in enumerate(top, start=1)
        ],
    }
