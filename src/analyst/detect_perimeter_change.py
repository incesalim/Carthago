"""Task 1.4 — perimeter-change detector.

Three ways a bank's reporting perimeter can move under a QoQ comparison:

- `cons_gap` — the consolidated/unconsolidated total-assets gap jumps (a
  subsidiary bought, sold, or newly consolidated). 28 banks file both kinds.
- `discontinued_ops` — the `disc_net` P&L role exists as a printed row in
  1,039/1,050 partitions, so the ROW appearing is meaningless; the AMOUNT
  turning material is the event (real cases in the corpus: GARAN 2026Q1
  consolidated +₺400m appearing from zero, DENIZ 2023Q4 −₺149m one quarter).
  A materiality floor keeps ALBRK's persistent ₺-thousand-scale noise out.
- `line_item_change` — the pl_roles role-set itself changes between quarters
  (income-statement structure moved: new business line or reclassification).
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict

from .periods import sort_key
from .signals import Signal
from .snapshot import total_assets

# |cons − unco| / unco moving between quarters. The plan's first draft said
# 20pp — the largest move in the stored corpus is 12.7pp (ANADOLU 2024Q2), so
# 20pp is a detector that can never fire. 3pp captures the nine real perimeter
# moves (ANADOLU's swings, DENIZ 2022Q3, ISCTR 2024Q1, SKBNK 2022Q4) and
# nothing else out of 428 stored quarter-pairs.
CONS_GAP_MOVE = 0.03
# ₺50m (in ₺000) — DENIZ (−148,670) and GARAN (+399,875) clear it; ALBRK's
# persistent −305…−1,982 rump line stays silent.
DISC_NET_FLOOR = 50_000.0


def _cons_gap(conn: sqlite3.Connection, bank: str | None) -> list[Signal]:
    totals = total_assets(conn, bank)
    per_bank: dict[str, dict[str, dict[str, float]]] = defaultdict(dict)
    for (ticker, kind), by_period in totals.items():
        per_bank[ticker][kind] = by_period

    signals: list[Signal] = []
    for ticker, kinds in per_bank.items():
        cons, unco = kinds.get("consolidated"), kinds.get("unconsolidated")
        if not cons or not unco:
            continue  # single-kind filer — no gap to compare
        gaps: dict[str, float] = {}
        for period in sorted(set(cons) & set(unco), key=sort_key):
            if unco[period]:
                gaps[period] = abs(cons[period] - unco[period]) / unco[period]
        ordered = sorted(gaps, key=sort_key)
        for prev_p, cur_p in zip(ordered, ordered[1:]):
            move = gaps[cur_p] - gaps[prev_p]
            if abs(move) <= CONS_GAP_MOVE:
                continue
            signals.append(Signal(
                signal_type="perimeter_change", subtype="cons_gap",
                bank_ticker=ticker, period=cur_p, kind="consolidated",
                severity="alert",
                payload={"gap_now": round(gaps[cur_p], 4),
                         "gap_prior": round(gaps[prev_p], 4),
                         "move": round(move, 4), "prior_period": prev_p},
            ))
    return signals


def _discontinued_ops(conn: sqlite3.Connection, bank: str | None) -> list[Signal]:
    where, params = ("AND r.bank_ticker = ?", [bank]) if bank else ("", [])
    rows = conn.execute(
        "SELECT r.bank_ticker, r.period, r.kind, p.amount "
        "FROM bank_audit_pl_roles r "
        "JOIN bank_audit_profit_loss p ON p.bank_ticker = r.bank_ticker "
        "  AND p.period = r.period AND p.kind = r.kind AND p.hierarchy = r.hierarchy "
        f"WHERE r.role = 'disc_net' {where}", params).fetchall()
    by_bank: dict[tuple[str, str], dict[str, float | None]] = defaultdict(dict)
    for r in rows:
        by_bank[(r["bank_ticker"], r["kind"])][r["period"]] = r["amount"]

    signals: list[Signal] = []
    for (ticker, kind), by_period in by_bank.items():
        ordered = sorted(by_period, key=sort_key)
        for prev_p, cur_p in zip(ordered, ordered[1:]):
            prev_amt = by_period[prev_p] or 0.0   # NULL and 0 both mean "no discontinued line
            cur_amt = by_period[cur_p] or 0.0     # in effect" for THIS transition test only
            prev_mat = abs(prev_amt) >= DISC_NET_FLOOR
            cur_mat = abs(cur_amt) >= DISC_NET_FLOOR
            if prev_mat == cur_mat:
                continue
            signals.append(Signal(
                signal_type="perimeter_change", subtype="discontinued_ops",
                bank_ticker=ticker, period=cur_p, kind=kind,
                severity="alert",
                payload={"prior_period": prev_p,
                         "prior_amount": by_period[prev_p],
                         "current_amount": by_period[cur_p],
                         "direction": "appeared" if cur_mat else "ceased"},
            ))
    return signals


def _line_item_change(conn: sqlite3.Connection, bank: str | None) -> list[Signal]:
    where, params = ("AND bank_ticker = ?", [bank]) if bank else ("", [])
    rows = conn.execute(
        "SELECT bank_ticker, period, kind, role FROM bank_audit_pl_roles "
        f"WHERE 1=1 {where}", params).fetchall()
    role_sets: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for r in rows:
        role_sets[(r["bank_ticker"], r["kind"])][r["period"]].add(r["role"])

    signals: list[Signal] = []
    for (ticker, kind), by_period in role_sets.items():
        ordered = sorted(by_period, key=sort_key)
        for prev_p, cur_p in zip(ordered, ordered[1:]):
            added = sorted(by_period[cur_p] - by_period[prev_p])
            removed = sorted(by_period[prev_p] - by_period[cur_p])
            if not added and not removed:
                continue
            signals.append(Signal(
                signal_type="perimeter_change", subtype="line_item_change",
                bank_ticker=ticker, period=cur_p, kind=kind,
                severity="notice",
                payload={"prior_period": prev_p, "roles_added": added,
                         "roles_removed": removed},
            ))
    return signals


def detect(conn: sqlite3.Connection, bank: str | None = None) -> list[Signal]:
    return (_cons_gap(conn, bank)
            + _discontinued_ops(conn, bank)
            + _line_item_change(conn, bank))
