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
  4. npl_drop    — a quarter whose Stage-3 NPL ratio crashes from a real level
                    (>=1%) to ~0 (<0.1%). Fingerprint of the Stage-3 extractor
                    grabbing an FC-only / fragment sub-table instead of the
                    total III/IV/V NPL classification (the DENIZ/FIBA 2026Q1 bug).
  5. capital     — bank_audit_capital arithmetic: CET1<=Tier1<=Total Capital and
                    reported CAR must reconcile to Total Capital / RWA. A failure
                    is a parse error (missing label variant / wrong total row).
  6. liquidity   — bank_audit_liquidity plausibility bands (leverage <30%,
                    LCR/NSFR sane; a sub-50% LCR is a mis-grabbed value).
  7. structure   — bank_audit_validation partitions with failed internal-sum
                    identities (TL+FC=Total per row, parent=Σchildren,
                    TOTAL=Σromans, assets=liabilities+equity). Written at
                    extraction time by src/audit_reports/validator.py.
  8. ecl         — Expected Credit Losses balance-sheet rows: a truncated label
                    ("…Losses(") or a tiny |amount| on a large bank are
                    fingerprints of the dipnot-ref "(6)" being read as the value
                    (the ALBRK -6 bug); a quarter that LOSES its ECL rows while
                    the prior quarter had them is the row-drop variant.

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
# NPL-collapse check: a Stage-3 gross that falls from a real level to ~zero
# between consecutive quarters is the fingerprint of the extractor grabbing an
# FC-only / fragment sub-table instead of the total NPL classification (the
# DENIZ/FIBA 2026Q1 bug: ~5% NPL read as ~0%). Require the PRIOR quarter to be a
# genuine NPL so we never flag banks that are simply low-NPL every quarter
# (ATBANK/ICBCT sit at ~0% legitimately).
NPL_COLLAPSE_PRIOR_MIN = 0.01   # prior-quarter NPL ratio >= 1%
NPL_COLLAPSE_CUR_MAX = 0.001    # current-quarter NPL ratio < 0.1%

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


def _npl_collapse(conn: sqlite3.Connection) -> list[str]:
    """Flag a quarter whose Stage-3 NPL ratio crashes from a real level to ~0 —
    the signature of the Stage-3 extractor latching onto an FC-only / fragment
    sub-table instead of the total III/IV/V classification."""
    # bank_audit_stages may not exist on a freshly-seeded DB; degrade gracefully.
    have = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='bank_audit_stages'"
    ).fetchone()
    if not have:
        return []
    out = []
    banks = [r[0] for r in conn.execute(
        "SELECT DISTINCT bank_ticker FROM bank_audit_stages "
        "WHERE kind='unconsolidated' AND period_type='current'")]
    for bank in banks:
        rows = conn.execute(
            "SELECT period, CASE WHEN total_amount > 0 "
            "       THEN stage3_amount * 1.0 / total_amount END AS npl "
            "FROM bank_audit_stages "
            "WHERE bank_ticker=? AND kind='unconsolidated' AND period_type='current' "
            "ORDER BY period", (bank,)).fetchall()
        for (p0, n0), (p1, n1) in zip(rows, rows[1:]):
            if (n0 is not None and n1 is not None
                    and n0 >= NPL_COLLAPSE_PRIOR_MIN and n1 < NPL_COLLAPSE_CUR_MAX):
                out.append(
                    f"npl_drop  {bank} {p1} unconsolidated: NPL {n1*100:.3f}% "
                    f"collapsed from {n0*100:.2f}% at {p0} — Stage-3 likely an "
                    f"FC-only/fragment table, not the total NPL classification")
    return out


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


# Capital tolerance: 2% absorbs rounding and any sub-line the extractor missed.
CAP_REL_TOL = 0.02


def _capital_consistency(conn: sqlite3.Connection) -> list[str]:
    """Arithmetic sanity on bank_audit_capital (current period): the tier
    ordering must hold and the reported CAR must reconcile to capital / RWA.
    A failure is almost always a parse error — a missing label variant or the
    wrong 'Total Capital' line picked up — i.e. exactly what to fix next."""
    if not _has_table(conn, "bank_audit_capital"):
        return []
    out = []
    rows = conn.execute(
        "SELECT bank_ticker, period, kind, cet1_capital, tier1_capital, "
        "       total_capital, total_rwa, capital_adequacy_ratio "
        "FROM bank_audit_capital WHERE period_type='current'").fetchall()
    for bank, period, kind, cet1, t1, tc, rwa, car in rows:
        tag = f"capital   {bank} {period} {kind}:"
        if cet1 and t1 and cet1 > t1 * (1 + CAP_REL_TOL):
            out.append(f"{tag} CET1 {cet1:,.0f} > Tier1 {t1:,.0f}")
        if t1 and tc and t1 > tc * (1 + CAP_REL_TOL):
            out.append(f"{tag} Tier1 {t1:,.0f} > Total capital {tc:,.0f}")
        if tc and rwa and car:
            implied = tc / rwa * 100
            if abs(implied - car) > max(0.5, car * 0.05):
                out.append(f"{tag} CAR {car:.2f}% != capital/RWA {implied:.2f}%")
        if car is not None and not (5 <= car <= 80):
            out.append(f"{tag} CAR {car} out of plausible band")
    return out


def _liquidity_bands(conn: sqlite3.Connection) -> list[str]:
    """Plausibility bands on bank_audit_liquidity (current period). Ratios are
    percentages; banks must run LCR/NSFR >= 100% in steady state, so a very low
    LCR is the fingerprint of a mis-grabbed value."""
    if not _has_table(conn, "bank_audit_liquidity"):
        return []
    out = []
    rows = conn.execute(
        "SELECT bank_ticker, period, kind, leverage_ratio, lcr_total, nsfr "
        "FROM bank_audit_liquidity WHERE period_type='current'").fetchall()
    for bank, period, kind, lev, lcr, nsfr in rows:
        tag = f"liquidity {bank} {period} {kind}:"
        if lev is not None and not (0 < lev < 30):
            out.append(f"{tag} leverage {lev} out of band")
        for nm, v in (("LCR", lcr), ("NSFR", nsfr)):
            if v is not None and not (0 < v < 2000):
                out.append(f"{tag} {nm} {v} out of band")
        if lcr is not None and lcr < 50:
            out.append(f"{tag} LCR {lcr}% implausibly low — likely a mis-grabbed value")
    return out


# ECL sanity: corrupted parses show up as values like -6 / 63 / 89 (the dipnot
# ref "(6)" read as a value). Real ECL on a bank with a >10bn-TL balance sheet
# is never under 100 thousand TL.
ECL_TINY_MAX = 100            # thousand TL
ECL_MIN_BANK_TOTAL = 10_000_000  # only apply the tiny test to large banks


def _ecl_sanity(conn: sqlite3.Connection) -> list[str]:
    """Fingerprints of the ECL parse bug (ALBRK -6 / row-drop class):
       a) truncated label '…Losses(' — the label boundary landed inside '(-)';
       b) ALL of a large bank's ECL rows implausibly tiny — dipnot ref read as
          value (covers -6). Per-row tiny is normal: the cash-section 1.1.4 ECL
          is legitimately ~tens of TL-thousands (BURGAN prints "77") — only a
          partition whose LARGEST |ECL| is tiny is corrupt. Sign is never
          flagged: some banks print the value itself in parens, so a large
          negative ECL is the faithful reading (ING/KLNMA/PASHA/TFKB);
       c) a quarter whose ECL rows vanish while the prior quarter had them —
          the silent row-drop variant."""
    out = []
    rows = conn.execute(
        "SELECT bank_ticker, period, kind, item_name, amount_total "
        "FROM bank_audit_balance_sheet WHERE statement='assets' AND ("
        "  replace(upper(item_name),' ','') LIKE '%EXPECTEDCREDITLOSS%'"
        "  OR replace(upper(item_name),' ','') LIKE '%BEKLENENZARAR%')"
    ).fetchall()
    totals: dict[tuple, float] = {}

    def bank_total(bank: str, period: str, kind: str) -> float:
        key = (bank, period, kind)
        if key not in totals:
            v = conn.execute(
                "SELECT MAX(amount_total) FROM bank_audit_balance_sheet "
                "WHERE bank_ticker=? AND period=? AND kind=? AND statement='assets'",
                key).fetchone()[0]
            totals[key] = v or 0
        return totals[key]

    ecl_periods: dict[tuple, set] = {}
    partition_max: dict[tuple, float] = {}
    for bank, period, kind, name, amt in rows:
        ecl_periods.setdefault((bank, kind), set()).add(period)
        tag = f"ecl       {bank} {period} {kind}:"
        if (name or "").rstrip().endswith("("):
            out.append(f"{tag} truncated label {name!r} (amount {amt}) — parse error")
            continue
        if amt is None:
            continue
        key = (bank, period, kind)
        partition_max[key] = max(partition_max.get(key, 0.0), abs(amt))
    for (bank, period, kind), mx in partition_max.items():
        if 0 < mx < ECL_TINY_MAX and bank_total(bank, period, kind) > ECL_MIN_BANK_TOTAL:
            out.append(f"ecl       {bank} {period} {kind}: largest ECL only "
                       f"{mx:,.0f} — dipnot ref likely read as the value")
    # c) ECL rows vanished vs the prior quarter (needs enough asset rows that
    #    the quarter isn't just a failed extraction — coverage flags those).
    for (bank, kind), have in ecl_periods.items():
        periods = [r[0] for r in conn.execute(
            "SELECT DISTINCT period FROM bank_audit_balance_sheet "
            "WHERE bank_ticker=? AND kind=? AND statement='assets' ORDER BY period",
            (bank, kind))]
        for p0, p1 in zip(periods, periods[1:]):
            if p0 in have and p1 not in have:
                n = conn.execute(
                    "SELECT COUNT(*) FROM bank_audit_balance_sheet WHERE bank_ticker=? "
                    "AND period=? AND kind=? AND statement='assets'",
                    (bank, p1, kind)).fetchone()[0]
                if n >= MIN_ASSET_ROWS:
                    out.append(f"ecl       {bank} {p1} {kind}: ECL rows present at {p0} "
                               f"but missing here — row likely dropped by the parser")
    return out


def _structure(conn: sqlite3.Connection) -> list[str]:
    """Partitions whose extraction-time identity validation failed (see
    src/audit_reports/validator.py). Summarized per partition — the per-check
    detail lives in bank_audit_validation.failed_detail."""
    if not _has_table(conn, "bank_audit_validation"):
        return []
    out = []
    rows = conn.execute(
        "SELECT bank_ticker, period, kind, statement, checks_passed, checks_failed "
        "FROM bank_audit_validation WHERE checks_failed > 0 "
        "ORDER BY bank_ticker, period, kind, statement").fetchall()
    for bank, period, kind, stmt, ok, bad in rows:
        out.append(f"structure {bank} {period} {kind}: {stmt} — {bad} identity "
                   f"check(s) failed ({ok} passed)")
    return out


def check(db: Path) -> list[str]:
    conn = sqlite3.connect(str(db))
    try:
        return (_stale_periods(conn) + _balance(conn) + _coverage(conn)
                + _npl_collapse(conn) + _capital_consistency(conn)
                + _liquidity_bands(conn) + _structure(conn) + _ecl_sanity(conn))
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
