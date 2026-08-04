"""Task 1.3b — audit-opinion change detector.

Fires on what CHANGED between consecutive stored opinions, never on a steady
state: ALBRK qualified every quarter over the same free provision produces no
signal — a bank going clean → qualified, switching qualification category,
breaking the report-kind rhythm (Q4 = audit, Q1–Q3 = review, which holds
976/976 in the corpus), or rotating auditor does.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict

from .classify_basis import classify
from .periods import quarter_num, sort_key
from .signals import Signal


def _expected_report_kind(period: str) -> str:
    return "audit" if quarter_num(period) == 4 else "review"


def detect(conn: sqlite3.Connection, bank: str | None = None) -> list[Signal]:
    where, params = ("AND bank_ticker = ?", [bank]) if bank else ("", [])
    rows = conn.execute(
        "SELECT bank_ticker, period, kind, opinion_type, report_kind, auditor, basis_text "
        f"FROM bank_audit_opinion WHERE 1=1 {where}", params).fetchall()

    by_bank: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        by_bank[(r["bank_ticker"], r["kind"])].append(r)

    signals: list[Signal] = []
    for (ticker, kind), series in by_bank.items():
        series.sort(key=lambda r: sort_key(r["period"]))
        for r in series:
            # Rhythm check needs no prior row — the expectation is structural.
            if r["report_kind"] and r["report_kind"] != _expected_report_kind(r["period"]):
                signals.append(Signal(
                    signal_type="opinion_change", subtype="report_kind",
                    bank_ticker=ticker, period=r["period"], kind=kind,
                    severity="notice",
                    payload={"report_kind": r["report_kind"],
                             "expected": _expected_report_kind(r["period"])},
                ))
        for prev, cur in zip(series, series[1:]):
            period = cur["period"]
            if prev["opinion_type"] != cur["opinion_type"]:
                signals.append(Signal(
                    signal_type="opinion_change", subtype="type",
                    bank_ticker=ticker, period=period, kind=kind,
                    severity="alert",
                    payload={"prior_type": prev["opinion_type"],
                             "current_type": cur["opinion_type"],
                             "prior_period": prev["period"]},
                ))
            prev_cat = classify(prev["basis_text"]).category if prev["basis_text"] else None
            cur_cls = classify(cur["basis_text"]) if cur["basis_text"] else None
            cur_cat = cur_cls.category if cur_cls else None
            # Category change only when both sides are qualified WITH a basis —
            # clean→qualified is already the `type` signal above.
            if prev_cat and cur_cat and prev_cat != cur_cat:
                signals.append(Signal(
                    signal_type="opinion_change", subtype="category",
                    bank_ticker=ticker, period=period, kind=kind,
                    severity="alert",
                    payload={"prior_category": prev_cat, "current_category": cur_cat,
                             "prior_period": prev["period"],
                             "basis_text_excerpt": cur_cls.excerpt if cur_cls else None},
                ))
            if prev["auditor"] and cur["auditor"] and prev["auditor"] != cur["auditor"]:
                signals.append(Signal(
                    signal_type="opinion_change", subtype="auditor",
                    bank_ticker=ticker, period=period, kind=kind,
                    severity="notice",
                    payload={"prior_auditor": prev["auditor"],
                             "current_auditor": cur["auditor"],
                             "prior_period": prev["period"]},
                ))
    return signals
