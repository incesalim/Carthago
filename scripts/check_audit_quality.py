"""Post-extraction data-quality checks for the bank-audit tables.

Catches the kind of silent extraction error the Eximbank 3-period / 4-column
layout produced (the prior period stored as the current one), so a format change
on a bank's report pings us the same week instead of being found by hand months
later. Runs against the standalone audit SQLite after extraction.

Checks (each yields offending (bank, period, kind)):
  1. stale_period — a quarter whose balance-sheet line items are almost all
                    IDENTICAL to the immediately prior quarter. A real quarter
                    moves nearly every number; ~100% identical means the prior
                    period was stored as current (the exact Eximbank fingerprint).
                    Total-row-independent, so it's robust even for banks whose
                    grand-total row isn't cleanly captured.
  2. balance     — where both labelled grand totals are present: total assets
                    must equal total liabilities; >0.5% off is a column grab.
                    Skipped (not failed) when a total row isn't identifiable.
  3. coverage    — an extracted (bank, period, kind) missing assets /
                    liabilities / P&L rows (or far below a sane minimum).

Alert-only / non-blocking: prints a report and (with --alert) sends one
Telegram/Discord summary via scripts/notify.py, then always exits 0 so it never
stops the pipeline. --strict exits non-zero on anomalies (handy locally / tests).

  python scripts/check_audit_quality.py --db data/bank_audit.db
  python scripts/check_audit_quality.py --db data/bank_audit.db --alert
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")

BALANCE_TOL = 0.005       # 0.5%
DUP_FRACTION = 0.95       # >=95% of line items identical to prior quarter
DUP_MIN_ROWS = 15         # need enough comparable rows to trust the fraction
MIN_ASSET_ROWS = 15
MIN_PL_ROWS = 15

_TOT_ASSETS = re.compile(r"(TOPLAM\s+AKT[İI]F|AKT[İI]F\s+TOPLAM|VARLIKLAR\s+TOPLAM|TOPLAM\s+VARLIK|TOTAL\s+ASSETS)", re.I)
_TOT_LIAB = re.compile(r"(TOPLAM\s+PAS[İI]F|PAS[İI]F\s+TOPLAM|TOPLAM\s+KAYNAK|TOPLAM\s+Y[ÜU]K[ÜU]ML[ÜU]L[ÜU]K|TOTAL\s+LIABILITIES|TOTAL\s+EQUITY\s+AND\s+LIABILITIES|TOTAL\s+SHAREHOLDERS)", re.I)


def _stale_periods(conn: sqlite3.Connection) -> list[str]:
    out = []
    pairs = conn.execute(
        "SELECT DISTINCT bank_ticker, kind FROM bank_audit_balance_sheet").fetchall()
    for bank, kind in pairs:
        periods = [r[0] for r in conn.execute(
            "SELECT DISTINCT period FROM bank_audit_balance_sheet "
            "WHERE bank_ticker=? AND kind=? ORDER BY period", (bank, kind))]
        for p0, p1 in zip(periods, periods[1:]):
            prev = {(s, o): a for s, o, a in conn.execute(
                "SELECT statement, item_order, amount_total FROM bank_audit_balance_sheet "
                "WHERE bank_ticker=? AND kind=? AND period=?", (bank, kind, p0))}
            cur = {(s, o): a for s, o, a in conn.execute(
                "SELECT statement, item_order, amount_total FROM bank_audit_balance_sheet "
                "WHERE bank_ticker=? AND kind=? AND period=?", (bank, kind, p1))}
            comparable = matches = 0
            for k, pv in prev.items():
                if pv in (None, 0) or k not in cur or cur[k] is None:
                    continue
                comparable += 1
                if cur[k] == pv:
                    matches += 1
            if comparable >= DUP_MIN_ROWS and matches / comparable >= DUP_FRACTION:
                out.append(f"stale     {bank} {p1} {kind}: {matches}/{comparable} line items "
                           f"identical to {p0} — prior period likely stored as current")
    return out


def _grand_total(conn, bank, period, kind, statement, pat) -> float | None:
    """The statement's grand total — the LARGEST amount_total, but only when that
    max row carries a total label. This avoids two failure modes: a stray row
    whose label merely contains "total" (tiny value), and banks whose real total
    row isn't captured at all (then the max is a sub-line, not a total → skip)."""
    rows = [(n, a) for n, a in conn.execute(
        "SELECT item_name, amount_total FROM bank_audit_balance_sheet "
        "WHERE bank_ticker=? AND period=? AND kind=? AND statement=?",
        (bank, period, kind, statement)) if a is not None]
    if not rows:
        return None
    name, mx = max(rows, key=lambda x: x[1])
    return mx if pat.search(name or "") else None


def _balance(conn) -> list[str]:
    out = []
    keys = conn.execute(
        "SELECT DISTINCT bank_ticker, period, kind FROM bank_audit_balance_sheet").fetchall()
    for bank, period, kind in keys:
        a = _grand_total(conn, bank, period, kind, "assets", _TOT_ASSETS)
        liab = _grand_total(conn, bank, period, kind, "liabilities", _TOT_LIAB)
        if a and liab and a > 0 and abs(a - liab) / a > BALANCE_TOL:
            out.append(f"balance   {bank} {period} {kind}: assets {a:,.0f} != "
                       f"liabilities {liab:,.0f} ({abs(a-liab)/a*100:.1f}% off)")
    return out


def _coverage(conn) -> list[str]:
    out = []
    for bank, period, kind in conn.execute(
            "SELECT bank_ticker, period, kind FROM bank_audit_extractions WHERE success=1"):
        na = conn.execute("SELECT COUNT(*) FROM bank_audit_balance_sheet WHERE bank_ticker=? "
                          "AND period=? AND kind=? AND statement='assets'",
                          (bank, period, kind)).fetchone()[0]
        nl = conn.execute("SELECT COUNT(*) FROM bank_audit_balance_sheet WHERE bank_ticker=? "
                          "AND period=? AND kind=? AND statement='liabilities'",
                          (bank, period, kind)).fetchone()[0]
        npl = conn.execute("SELECT COUNT(*) FROM bank_audit_profit_loss WHERE bank_ticker=? "
                           "AND period=? AND kind=?", (bank, period, kind)).fetchone()[0]
        if na < MIN_ASSET_ROWS or nl < MIN_ASSET_ROWS or npl < MIN_PL_ROWS:
            out.append(f"coverage  {bank} {period} {kind}: rows assets={na} liab={nl} pl={npl}")
    return out


def check(db: Path) -> list[str]:
    conn = sqlite3.connect(str(db))
    try:
        return _stale_periods(conn) + _balance(conn) + _coverage(conn)
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(REPO / "data" / "bank_audit.db"))
    ap.add_argument("--alert", action="store_true", help="send a Telegram/Discord summary on anomalies")
    ap.add_argument("--strict", action="store_true", help="exit non-zero on anomalies")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        print(f"[quality] no DB at {db}; skipping")
        return 0
    anomalies = check(db)
    if not anomalies:
        print("[quality] OK — no audit data-quality anomalies")
        return 0

    print(f"[quality] {len(anomalies)} anomaly(ies):")
    for a in anomalies:
        print("  -", a)
    if args.alert:
        head = anomalies[:20]
        more = f"\n…and {len(anomalies)-20} more" if len(anomalies) > 20 else ""
        msg = f"⚠️ Audit data-quality: {len(anomalies)} anomaly(ies)\n" + "\n".join(head) + more
        try:
            subprocess.run([sys.executable, str(REPO / "scripts" / "notify.py"), msg], check=False)
        except Exception as e:  # noqa: BLE001
            print(f"[quality] notify failed: {e}", file=sys.stderr)
    return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
