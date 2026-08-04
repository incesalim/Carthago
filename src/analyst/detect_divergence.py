"""Task 1.8 — headline-conceals-composition divergence detectors.

The feasibility verdict's "two missing derivations": each is two stored series
and a subtraction, and either would have caught the Şekerbank case
automatically. Nothing else in the system computes them.

1.8a capital composition — a screen on CAR ranks SKBNK top-decile at 22.13%
while CET1 sits at 8.64%: 61% of regulatory capital is non-core. Fires on the
level (non-core share ≥ 40% of CAR) and on the Tier-issuance signature (gap
widening ≥ 3pp QoQ while CAR holds or rises — SKBNK 2025Q3: CAR 17.87 → 24.18
while CET1 *fell*).

1.8b NPL-vs-coverage — an NPL ratio falling every quarter while Stage 3
coverage collapses (SKBNK: 1.70 → 1.33 against 86.2% → 48.3%). Invisible to
any single-series screen; correctly silent when NPL is *rising* (ALBRK — the
deterioration is already in the headline).
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict

from .periods import sort_key
from .signals import Signal

# 1.8a — thresholds tuned on the 2026Q1 fleet (66 partitions): non-core ≥ 40%
# fires on 12, incl. SKBNK (61%) and ALBRK (47%); the fleet median sits far
# below. Widening ≥ 3pp with CAR flat/up catches SKBNK 2025Q3 (+7.8pp gap,
# CAR +6.3pp) and the ICBCT/VAKIFK issuance quarters.
NONCORE_SHARE = 0.40
GAP_WIDEN_PP = 3.0
CAR_HOLD_PP = -0.5

# 1.8b — trailing 4-quarter window: NPL drift ≤ +0.15pp counts as flat/falling,
# coverage drop ≥ 10pp counts as material. At 5pp the corpus fires 138 times
# across 23 banks — a description of the 2022–26 dilution cycle, not a signal;
# at 10pp it is 71 over a real outlier set. SKBNK 2026Q1: NPL −0.12pp,
# coverage −19.0pp → fires (alert: coverage < 60%). ALBRK: NPL +0.64pp →
# silent — its deterioration is already in the headline.
NPL_FLAT_PP = 0.15
COVERAGE_DROP_PP = 10.0
LOOKBACK_QUARTERS = 4
# Severity split: a mild-but-real divergence is a notice; collapsed coverage
# (< 60%) or a 15pp+ fall is the memo-driving alert.
COVERAGE_ALERT_LEVEL = 60.0
COVERAGE_ALERT_DROP = 15.0


def _capital_composition(conn: sqlite3.Connection, bank: str | None) -> list[Signal]:
    where, params = ("AND bank_ticker = ?", [bank]) if bank else ("", [])
    rows = conn.execute(
        "SELECT bank_ticker, period, kind, cet1_ratio, capital_adequacy_ratio "
        "FROM bank_audit_capital WHERE period_type = 'current' "
        f"AND cet1_ratio IS NOT NULL AND capital_adequacy_ratio IS NOT NULL {where}",
        params).fetchall()
    by_bank: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        by_bank[(r["bank_ticker"], r["kind"])].append(r)

    signals: list[Signal] = []
    for (ticker, kind), series in by_bank.items():
        series.sort(key=lambda r: sort_key(r["period"]))
        for i, r in enumerate(series):
            car, cet1 = r["capital_adequacy_ratio"], r["cet1_ratio"]
            if car <= 0:
                continue
            gap = car - cet1
            noncore = gap / car
            level_hit = noncore >= NONCORE_SHARE
            widen_hit = False
            widen_pp = car_move = None
            if i > 0:
                prev = series[i - 1]
                prev_gap = prev["capital_adequacy_ratio"] - prev["cet1_ratio"]
                widen_pp = round(gap - prev_gap, 2)
                car_move = round(car - prev["capital_adequacy_ratio"], 2)
                widen_hit = widen_pp >= GAP_WIDEN_PP and car_move >= CAR_HOLD_PP
            if not (level_hit or widen_hit):
                continue
            signals.append(Signal(
                signal_type="divergence",
                subtype="capital_composition",
                bank_ticker=ticker,
                period=r["period"],
                kind=kind,
                severity="alert",
                payload={
                    "car": car,
                    "cet1": cet1,
                    "gap_pp": round(gap, 2),
                    "noncore_share": round(noncore, 3),
                    "level_hit": level_hit,
                    "widening_hit": widen_hit,
                    "gap_widen_pp": widen_pp,
                    "car_move_pp": car_move,
                },
            ))
    return signals


def _npl_coverage(conn: sqlite3.Connection, bank: str | None) -> list[Signal]:
    where, params = ("AND bank_ticker = ?", [bank]) if bank else ("", [])
    rows = conn.execute(
        "SELECT bank_ticker, period, kind, stage3_amount, total_amount, stage3_coverage "
        "FROM bank_audit_stages WHERE period_type = 'current' "
        "AND stage3_amount IS NOT NULL AND total_amount IS NOT NULL "
        f"AND stage3_coverage IS NOT NULL AND total_amount > 0 {where}",
        params).fetchall()
    by_bank: dict[tuple[str, str], dict[str, tuple[float, float]]] = defaultdict(dict)
    for r in rows:
        npl_pct = 100.0 * r["stage3_amount"] / r["total_amount"]
        cov_pct = 100.0 * r["stage3_coverage"]  # stored as a FRACTION, unlike capital ratios
        by_bank[(r["bank_ticker"], r["kind"])][r["period"]] = (npl_pct, cov_pct)

    signals: list[Signal] = []
    for (ticker, kind), by_period in by_bank.items():
        ordered = sorted(by_period, key=sort_key)
        for i, period in enumerate(ordered):
            if i < LOOKBACK_QUARTERS:
                continue
            ref = ordered[i - LOOKBACK_QUARTERS]
            npl_now, cov_now = by_period[period]
            npl_ref, cov_ref = by_period[ref]
            npl_drift = npl_now - npl_ref
            cov_drop = cov_ref - cov_now
            if npl_drift > NPL_FLAT_PP or cov_drop < COVERAGE_DROP_PP:
                continue
            severity = ("alert" if cov_now < COVERAGE_ALERT_LEVEL
                        or cov_drop >= COVERAGE_ALERT_DROP else "notice")
            signals.append(Signal(
                signal_type="divergence",
                subtype="npl_coverage",
                bank_ticker=ticker,
                period=period,
                kind=kind,
                severity=severity,
                payload={
                    "window_start": ref,
                    "npl_pct": round(npl_now, 2),
                    "npl_pct_window_start": round(npl_ref, 2),
                    "npl_drift_pp": round(npl_drift, 2),
                    "coverage_pct": round(cov_now, 1),
                    "coverage_pct_window_start": round(cov_ref, 1),
                    "coverage_drop_pp": round(cov_drop, 1),
                },
            ))
    return signals


def detect(conn: sqlite3.Connection, bank: str | None = None) -> list[Signal]:
    return _capital_composition(conn, bank) + _npl_coverage(conn, bank)
