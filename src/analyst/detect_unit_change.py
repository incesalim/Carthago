"""Task 1.1 — reporting-unit change detector.

A balance sheet does not move 50× in a quarter. When the QoQ ratio of total
assets leaves [0.02, 50], the filing switched reporting units (the TEB 2026Q2
case: ₺799bn printed in thousands → ~₺841m printed in millions, ratio ~0.00105)
— or the extraction is broken at the same magnitude, which deserves the same
alarm.

This is the detector whose absence blocks 2026Q2: the sector switched Bin →
Milyon and `triage.py`'s in-filing vote cannot see a sector-wide switch. Only
a cross-filing comparison can.
"""
from __future__ import annotations

import sqlite3

from .periods import prev_quarter
from .signals import Signal
from .snapshot import total_assets

# A genuine bank quarter stays well inside these bounds — the fastest growers
# in the corpus run ~2×/year. 1000× (a Bin→Milyon switch) is unmistakable;
# the wide bounds keep the detector silent on everything that is merely fast.
RATIO_HIGH = 50.0
RATIO_LOW = 0.02


def detect(conn: sqlite3.Connection, bank: str | None = None) -> list[Signal]:
    signals: list[Signal] = []
    for (ticker, kind), by_period in sorted(total_assets(conn, bank).items()):
        for period, current in sorted(by_period.items()):
            prior_period = prev_quarter(period)
            prior = by_period.get(prior_period)
            # A missing adjacent quarter (new entrant, filing gap) is not
            # comparable — skip, never interpolate across the gap.
            if prior is None or prior <= 0 or current is None or current <= 0:
                continue
            ratio = current / prior
            if RATIO_LOW <= ratio <= RATIO_HIGH:
                continue
            signals.append(Signal(
                signal_type="unit_change",
                subtype="",
                bank_ticker=ticker,
                period=period,
                kind=kind,
                severity="critical",
                payload={
                    "prior_period": prior_period,
                    "prior_total": prior,
                    "current_total": current,
                    "ratio": round(ratio, 6),
                },
            ))
    return signals
