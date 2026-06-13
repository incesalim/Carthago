"""Parsers for the specific TÜİK Excel tables we ingest.

Each parser turns a raw header-less DataFrame (from `client.download_table`)
into a list of `Row(code, period_date, value, label)` destined for the shared
`evds_series` table (codes prefixed `TUIK.*`, so the whole dashboard access
path — evdsMulti, push_to_d1, the chart-spec verifier — works unchanged).

All series are stored as the raw index LEVEL (quarterly → quarter-start date,
monthly → month-start); the dashboard derives m/m, y/y, q/q. Verified against
the Albaraka GDP + inflation reports (see reference_tuik_data_access memory).
"""
from __future__ import annotations

from typing import NamedTuple

import pandas as pd


class Row(NamedTuple):
    code: str
    period_date: str
    value: float
    label: str


_MONTHS_TR = {
    "ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6,
    "temmuz": 7, "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12,
}


def _is_year(x) -> bool:
    try:
        return 1990 <= int(x) <= 2035
    except (ValueError, TypeError):
        return False


def _num(x) -> float | None:
    if isinstance(x, (int, float)) and pd.notna(x):
        return float(x)
    return None


def _quarter_dates(year: int) -> list[str]:
    return [f"{year}-01-01", f"{year}-04-01", f"{year}-07-01", f"{year}-10-01"]


# ---------------------------------------------------------------------------
# National accounts — quarterly chain-volume index, stacked component blocks.
# Layout (consumption T6 / GFCF T8): a block header row has the component name
# in col0 and the first year in col1; continuation rows carry the year in col0.
# After the year cell: 4 index columns (Q1-4) then 4 y/y columns. We keep the
# index. `components` maps an English name substring → (code, label).
# ---------------------------------------------------------------------------
def parse_na_index(df: pd.DataFrame, components: dict[str, tuple[str, str]]) -> list[Row]:
    """`components` is checked in order, first substring match wins — so list
    more specific names first (Semi-durable / Non-durable before Durable).
    The component name sits in col0 of a header row (may be NaN on continuation
    rows → `cur` persists); the year is in col1 (fallback col0); the 4 index
    columns follow the year cell, then 4 y/y columns we ignore."""
    rows: list[Row] = []
    cur: tuple[str, str] | None = None
    for i in range(len(df)):
        r = df.iloc[i]
        c0 = r[0]
        if isinstance(c0, str) and c0.strip() and not _is_year(c0):
            low = c0.lower()
            cur = next((tgt for sub, tgt in components.items() if sub.lower() in low), None)
        ypos = 1 if _is_year(r[1]) else (0 if _is_year(r[0]) else None)
        if cur is None or ypos is None:
            continue
        year = int(r[ypos])
        for d, col in zip(_quarter_dates(year), range(ypos + 1, ypos + 5)):
            v = _num(r[col]) if col < len(r) else None
            if v is not None:
                rows.append(Row(cur[0], d, v, cur[1]))
    return rows


# Order matters: specific names first (substring match, first wins).
CONSUMPTION = {
    "Semi-durable": ("TUIK.NA.CONS_SEMIDUR", "Consumption: semi-durable goods (chain vol.)"),
    "Non-durable": ("TUIK.NA.CONS_NONDUR", "Consumption: non-durable goods (chain vol.)"),
    "Durable goods": ("TUIK.NA.CONS_DURABLE", "Consumption: durable goods (chain vol.)"),
    "Services": ("TUIK.NA.CONS_SERVICES", "Consumption: services (chain vol.)"),
}
GFCF = {
    "Construction": ("TUIK.NA.GFCF_CONSTRUCTION", "Investment: construction (chain vol.)"),
    "Machinery and equipment": ("TUIK.NA.GFCF_MACHINERY", "Investment: machinery & equipment (chain vol.)"),
    "Other assets": ("TUIK.NA.GFCF_OTHER", "Investment: other assets (chain vol.)"),
}


# ---------------------------------------------------------------------------
# PPI Main Industrial Groupings — monthly index (sheet 18_t14).
# Layout: col0=year, col1=TR month, col2=EN month, col3-7 = 5 MIG columns.
# ---------------------------------------------------------------------------
_PPI_MIG = [
    (3, "TUIK.PPI.MIG_INTERMEDIATE", "PPI MIG: intermediate goods"),
    (4, "TUIK.PPI.MIG_DURABLE", "PPI MIG: durable consumer goods"),
    (5, "TUIK.PPI.MIG_NONDUR", "PPI MIG: non-durable consumer goods"),
    (6, "TUIK.PPI.MIG_ENERGY", "PPI MIG: energy"),
    (7, "TUIK.PPI.MIG_CAPITAL", "PPI MIG: capital goods"),
]


def parse_ppi_mig(df: pd.DataFrame) -> list[Row]:
    rows: list[Row] = []
    last_year: int | None = None
    for i in range(len(df)):
        r = df.iloc[i]
        if _is_year(r[0]):
            last_year = int(r[0])
        m = _MONTHS_TR.get(str(r[1]).strip().lower()) if len(r) > 1 else None
        if not m or last_year is None:
            continue
        d = f"{last_year}-{m:02d}-01"
        for col, code, label in _PPI_MIG:
            v = _num(r[col]) if col < len(r) else None
            if v is not None:
                rows.append(Row(code, d, v, label))
    return rows


# ---------------------------------------------------------------------------
# CPI COICOP main-group weights (sheet 17_t12) — flat: code | name(TR) |
# name(EN) | weight(%). Main groups have 2-digit codes 01..13. Stored at the
# year-start date so the dashboard can pick the weight in force.
# ---------------------------------------------------------------------------
def parse_cpi_weights(df: pd.DataFrame, year: int) -> list[Row]:
    import re

    rows: list[Row] = []
    for i in range(len(df)):
        code = str(df.iloc[i, 0]).strip()
        if re.fullmatch(r"0[1-9]|1[0-3]", code):
            w = _num(df.iloc[i, 3]) if df.shape[1] > 3 else None
            label_en = str(df.iloc[i, 2])[:40] if df.shape[1] > 2 else ""
            if w is not None:
                rows.append(Row(f"TUIK.WEIGHT.CPI_{code}", f"{year}-01-01", w, f"CPI weight {code} {label_en}"))
    return rows
