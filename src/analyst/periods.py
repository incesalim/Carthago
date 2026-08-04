"""Period arithmetic for the `YYYYQN` period strings used across the audit lane.

Periods carry NO hyphen (`2026Q1`, never `2026-Q1`) — a detector keyed on the
hyphenated form matches zero rows silently, which is exactly the failure mode
this package exists to catch elsewhere.
"""
from __future__ import annotations

import re

_PERIOD_RE = re.compile(r"^(\d{4})Q([1-4])$")


def parse(period: str) -> tuple[int, int]:
    """`'2026Q1'` → `(2026, 1)`. Raises ValueError on anything else."""
    m = _PERIOD_RE.match(period)
    if not m:
        raise ValueError(f"bad period {period!r} — expected YYYYQN like 2026Q1")
    return int(m.group(1)), int(m.group(2))


def fmt(year: int, q: int) -> str:
    return f"{year}Q{q}"


def prev_quarter(period: str) -> str:
    year, q = parse(period)
    return fmt(year - 1, 4) if q == 1 else fmt(year, q - 1)


def prior_year_end(period: str) -> str:
    """The prior column of the §4 lanes is the prior YEAR-END for every quarter
    of the year — `2026Q3` → `2025Q4` (the free 4-way anchor)."""
    year, _ = parse(period)
    return fmt(year - 1, 4)


def prior_year_same_quarter(period: str) -> str:
    """The equity-change prior block is the prior year's SAME quarter
    (verified on GARAN: the 2026Q1 prior block equals the 2025Q1 current one)."""
    year, q = parse(period)
    return fmt(year - 1, q)


def sort_key(period: str) -> tuple[int, int]:
    return parse(period)


def quarter_num(period: str) -> int:
    return parse(period)[1]
