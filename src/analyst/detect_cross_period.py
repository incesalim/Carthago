"""Task 1.2 — cross-period discontinuity detector.

Each filing restates history: the §4 lanes carry a PRIOR column (= prior
YEAR-END, so all four quarters of year Y anchor against the stored Y−1 Q4
current column), the equity-change statement carries a prior-year SAME-QUARTER
block, and the NPL movement is YTD (its opening balance is the start of year =
prior year-end closing). When the stored prior disagrees with what the earlier
filing itself reported, either the bank restated or an extraction broke.

Balance sheet and P&L store no prior column at all — their continuity check is
the QoQ ratio in `detect_unit_change`.

Relationship to the validators is deliberately inverted: `validator.py`
SUPPRESSES known restatements via skip-lists (`_FX_XPERIOD_SKIP` et al. in
`scripts/revalidate_audit_db.py`) so lanes stay green. This detector FIRES on
exactly those — a restatement is a fact the memo must carry, not an error to
hide. Matches are marked `documented: true` in the payload.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict

from .periods import prior_year_end, prior_year_same_quarter
from .signals import Signal

# Relative mismatch that counts as a break. 1–5% mismatches in the corpus are
# genuine restatements; ~1000× is a unit switch. Below 1% is print rounding.
REL_TOL = 0.01
# Ignore comparisons where both sides are numerically tiny (₺000 scale) — a
# ₺40k vs ₺45k prior is print noise, not a restatement.
ABS_FLOOR = 1_000.0

# Mirror of the validator's documented-restatement skip-lists
# (scripts/revalidate_audit_db.py: _FX_XPERIOD_SKIP at :308, plus _RP_SKIP /
# _RP_PRIOR_SKIP). Kept as a literal so this package stays importable without
# the scripts/ path hacks; tests assert the mirror stays in sync.
KNOWN_RESTATEMENTS: frozenset[tuple[str, str, str]] = frozenset({
    ("HALKB", "2025Q3", "unconsolidated"),
    ("HALKB", "2025Q4", "unconsolidated"),
    ("ALBRK", "2023Q1", "consolidated"),
    ("TOMK", "2024Q1", "unconsolidated"),
    ("TOMK", "2024Q2", "unconsolidated"),
    ("TOMK", "2024Q3", "unconsolidated"),
    ("TOMK", "2024Q4", "unconsolidated"),
    ("ALNTF", "2023Q1", "unconsolidated"),
    ("ICBCT", "2024Q1", "unconsolidated"),
    ("TSKB", "2022Q1", "unconsolidated"),
    ("ANADOLU", "2026Q1", "consolidated"),
})


def _mismatch(stored_prior: float | None, reference: float | None) -> float | None:
    """Relative difference, or None when not comparable. NULL is not 0 —
    a missing side means no comparison, never a zero. A literal 0.0 against a
    large reference is ALSO not a restatement: it is the dash→0.0 extraction
    artifact (SKBNK's 2023–2024 capital priors) — a bank cannot restate its
    total capital to zero. Skip rather than report a fiction."""
    if stored_prior is None or reference is None:
        return None
    if (stored_prior == 0) != (reference == 0):
        return None
    if abs(stored_prior) < ABS_FLOOR and abs(reference) < ABS_FLOOR:
        return None
    base = max(abs(stored_prior), abs(reference))
    if base == 0:
        return None
    return abs(stored_prior - reference) / base


def _severity(stored_prior: float, reference: float) -> str:
    """~1000× breaks (unit switches) are critical; restatement-scale is alert."""
    hi, lo = max(abs(stored_prior), abs(reference)), min(abs(stored_prior), abs(reference))
    if lo > 0 and hi / lo > 100:
        return "critical"
    return "alert"


def _emit(signals: list[Signal], lane: str, ticker: str, period: str, kind: str,
          metric: str, stored_prior: float | None, reference: float | None,
          reference_period: str) -> None:
    diff = _mismatch(stored_prior, reference)
    if diff is None or diff <= REL_TOL:
        return
    signals.append(Signal(
        signal_type="cross_period_mismatch",
        subtype=f"{lane}.{metric}",
        bank_ticker=ticker,
        period=period,
        kind=kind,
        severity=_severity(stored_prior, reference),
        payload={
            "lane": lane,
            "metric": metric,
            "stored_prior": stored_prior,
            "reference_value": reference,
            "reference_period": reference_period,
            "pct_diff": round(diff * 100, 2),
            "documented": (ticker, period, kind) in KNOWN_RESTATEMENTS,
        },
    ))


def _year_end_anchor(conn: sqlite3.Connection, signals: list[Signal], bank: str | None,
                     table: str, lane: str, metrics: list[str]) -> None:
    """§4-style lanes: one row per (bank, period, kind, period_type); the prior
    row anchors against the prior year-end's current row."""
    where, params = ("WHERE bank_ticker = ?", [bank]) if bank else ("", [])
    rows = conn.execute(
        f"SELECT bank_ticker, period, kind, period_type, {', '.join(metrics)} "
        f"FROM {table} {where}", params).fetchall()
    current: dict[tuple, sqlite3.Row] = {}
    prior: dict[tuple, sqlite3.Row] = {}
    for r in rows:
        key = (r["bank_ticker"], r["period"], r["kind"])
        (current if r["period_type"] == "current" else prior)[key] = r
    for (ticker, period, kind), pr in prior.items():
        ref_period = prior_year_end(period)
        ref = current.get((ticker, ref_period, kind))
        if ref is None:
            continue  # anchor filing genuinely absent (new entrant, gap)
        for m in metrics:
            _emit(signals, lane, ticker, period, kind, m, pr[m], ref[m], ref_period)


def _fx_anchor(conn: sqlite3.Connection, signals: list[Signal], bank: str | None) -> None:
    """FX position: TOTAL-row net position, prior vs prior year-end current —
    the same comparison `fx_cross_period` runs, reported instead of skipped."""
    where, params = ("AND bank_ticker = ?", [bank]) if bank else ("", [])
    rows = conn.execute(
        "SELECT bank_ticker, period, kind, period_type, net_position "
        f"FROM bank_audit_fx_position WHERE currency = 'TOTAL' {where}", params).fetchall()
    current, prior = {}, {}
    for r in rows:
        key = (r["bank_ticker"], r["period"], r["kind"])
        (current if r["period_type"] == "current" else prior)[key] = r["net_position"]
    for (ticker, period, kind), pr in prior.items():
        ref_period = prior_year_end(period)
        key = (ticker, ref_period, kind)
        if key not in current:
            continue
        _emit(signals, "fx_position", ticker, period, kind, "net_position",
              pr, current[key], ref_period)


def _npl_anchor(conn: sqlite3.Connection, signals: list[Signal], bank: str | None) -> None:
    """NPL movement is YTD: every quarter's opening balance is the start of
    year, i.e. the prior year-end filing's closing balance, per BRSA group."""
    where, params = ("AND bank_ticker = ?", [bank]) if bank else ("", [])
    rows = conn.execute(
        "SELECT bank_ticker, period, kind, group_code, opening_balance, closing_balance "
        f"FROM bank_audit_npl_movement WHERE period_type = 'current' {where}",
        params).fetchall()
    opening: dict[tuple, float | None] = {}
    closing: dict[tuple, float | None] = {}
    for r in rows:
        key = (r["bank_ticker"], r["period"], r["kind"], r["group_code"])
        opening[key] = r["opening_balance"]
        closing[key] = r["closing_balance"]
    for (ticker, period, kind, group), open_bal in opening.items():
        ref_period = prior_year_end(period)
        ref_key = (ticker, ref_period, kind, group)
        if ref_key not in closing:
            continue
        _emit(signals, "npl_movement", ticker, period, kind, f"opening_group_{group}",
              open_bal, closing[ref_key], ref_period)


def _equity_anchor(conn: sqlite3.Connection, signals: list[Signal], bank: str | None) -> None:
    """Equity change: the prior block's closing total_equity anchors against the
    prior year SAME quarter's current closing (verified on GARAN)."""
    where, params = ("AND bank_ticker = ?", [bank]) if bank else ("", [])
    rows = conn.execute(
        "SELECT bank_ticker, period, kind, period_type, item_order, total_equity "
        "FROM bank_audit_equity_change "
        f"WHERE hierarchy = '' AND total_equity IS NOT NULL {where}", params).fetchall()
    # The closing row is the LAST hierarchy='' row of its block.
    best: dict[tuple, tuple[int, float]] = {}
    for r in rows:
        key = (r["bank_ticker"], r["period"], r["kind"], r["period_type"])
        if key not in best or r["item_order"] > best[key][0]:
            best[key] = (r["item_order"], r["total_equity"])
    for (ticker, period, kind, ptype), (_, closing) in best.items():
        if ptype != "prior":
            continue
        ref_period = prior_year_same_quarter(period)
        ref = best.get((ticker, ref_period, kind, "current"))
        if ref is None:
            continue
        _emit(signals, "equity_change", ticker, period, kind, "closing_total_equity",
              closing, ref[1], ref_period)


# credit_quality is DELIBERATELY not anchored. Its prior columns were never
# validated (the §4 lanes validated only the current column for years) and a
# corpus run fires 235 times — dominated by wrong-cell prior reads (YKBNK
# 2025Q1 loans_by_stage prior prints ₺7.2bn against a ₺1.2tn reference), not
# restatements. Anchor it only after the prior-column repair lands.


def _validation_failing(conn: sqlite3.Connection) -> set[tuple[str, str, str, str]]:
    """(bank, period, kind, statement) whose stored rows are ALREADY failing
    the lane validator — a cross-period hit there reads as extraction defect
    first, restatement second, and the payload says so."""
    return {
        (r["bank_ticker"], r["period"], r["kind"], r["statement"])
        for r in conn.execute(
            "SELECT bank_ticker, period, kind, statement FROM bank_audit_validation "
            "WHERE checks_failed > 0")
    }


# lane name → the `statement` key its validator writes in bank_audit_validation.
_LANE_VALIDATION = {
    "capital": "capital",
    "liquidity": "liquidity",
    "fx_position": "fx_position",
    "npl_movement": "npl_movement",
    "equity_change": "equity_change",
}


def detect(conn: sqlite3.Connection, bank: str | None = None) -> list[Signal]:
    signals: list[Signal] = []
    _year_end_anchor(conn, signals, bank, "bank_audit_capital", "capital",
                     ["total_capital", "total_rwa", "cet1_ratio", "capital_adequacy_ratio"])
    _year_end_anchor(conn, signals, bank, "bank_audit_liquidity", "liquidity",
                     ["leverage_ratio", "lcr_total", "lcr_fc", "nsfr"])
    _fx_anchor(conn, signals, bank)
    _npl_anchor(conn, signals, bank)
    _equity_anchor(conn, signals, bank)

    failing = _validation_failing(conn)
    flagged: list[Signal] = []
    for s in signals:
        stmt = _LANE_VALIDATION.get(s.payload.get("lane", ""))
        if stmt and (s.bank_ticker, s.period, s.kind, stmt) in failing:
            flagged.append(Signal(
                s.signal_type, s.subtype, s.bank_ticker, s.period, s.kind,
                s.severity, {**s.payload, "lane_validation_failing": True}))
        else:
            flagged.append(s)
    return flagged


def summarize(signals: list[Signal]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for s in signals:
        counts[s.payload.get("lane", s.subtype)] += 1
    return dict(counts)
