"""Compute per-bank KPI snapshot from BRSA audit-report extracts.

For each (bank_ticker, period, kind), pulls the canonical hierarchy rows from
bank_audit_balance_sheet / bank_audit_profit_loss / bank_audit_credit_quality
and derives:

  Stocks (balance-sheet):
    total_assets        — Σ Roman I.-X. on the assets statement
    gross_loans         — hierarchy "2.1" (verified: BRSA template's "Krediler" is gross,
                          a separate -ECL line sits at 2.5)
    total_ecl           — hierarchy "2.5" (Expected Credit Loss Provisions, abs value)
    deposits            — hierarchy "I." on the liabilities statement
    equity              — hierarchy "XVI." on the liabilities statement

  Flow (income statement, YTD for the period):
    net_income          — hierarchy "XXV." (Net Period Profit total),
                          falls back to "XIX." (continuing-ops) when XXV. is missing

  Credit quality (from BRSA j.2 NPL classification footnote):
    npl_gross           — npl_brsa_gross.total_amount (current period)
    npl_provision       — npl_brsa_provision.total_amount (current period)
    npl_net             — npl_brsa_net.total_amount     (current period)

  Derived ratios:
    npl_ratio       = npl_gross / gross_loans
    coverage_ratio  = npl_provision / npl_gross
    roa             = net_income / total_assets        (NB: YTD income, not annualized)
    roe             = net_income / equity              (idem)
    ldr             = gross_loans / deposits           (loan-to-deposit)
    ecl_ratio       = total_ecl / gross_loans          (overall provisioning ratio)

Usage:
  python scripts/compute_bank_metrics.py                           # 2025Q4 unconsolidated, all banks
  python scripts/compute_bank_metrics.py --period 2024Q4
  python scripts/compute_bank_metrics.py --ticker AKBNK            # one bank, all periods
  python scripts/compute_bank_metrics.py --format json > out.json  # JSON dump
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "data" / "bddk_data.db"
sys.stdout.reconfigure(encoding="utf-8")

# Hierarchy codes follow the BRSA template; see web/app/lib/standard_lines.ts
# for the cross-checked canonical list.
ASSET_ROMAN = ["I.", "II.", "III.", "IV.", "V.", "VI.", "VII.", "VIII.", "IX.", "X."]
LIAB_DEPOSITS = "I."
LIAB_EQUITY = "XVI."
ASSET_GROSS_LOANS = "2.1"
ASSET_ECL = "2.5"
PL_NET_INCOME_PRIMARY = "XXV."
PL_NET_INCOME_FALLBACK = "XIX."


@dataclass
class BankMetrics:
    bank_ticker: str
    period: str
    kind: str
    # Stocks
    total_assets: float | None
    gross_loans: float | None
    total_ecl: float | None
    deposits: float | None
    equity: float | None
    # Flow
    net_income: float | None
    # Credit quality
    npl_gross: float | None
    npl_provision: float | None
    npl_net: float | None
    # Stage 3 composition (Group III / IV / V)
    npl_group3: float | None
    npl_group4: float | None
    npl_group5: float | None
    # Derived ratios (all in fraction form — multiply by 100 for %)
    npl_ratio: float | None
    coverage_ratio: float | None
    roa: float | None
    roe: float | None
    ldr: float | None
    ecl_ratio: float | None


def _safe_div(a: float | None, b: float | None, eps: float = 1e-3) -> float | None:
    """Divide a/b returning None when either side is missing or the denominator
    is effectively zero. Without the eps guard, banks that don't take deposits
    (development / investment banks: KLNMA, EXIM, TSKB, ICBCT, PASHA, ALNTF)
    were producing nonsensical LDR like 1,275,092,820%."""
    if a is None or b is None or abs(b) < eps:
        return None
    return a / b


def _hier_sum(rows: list[tuple], statement: str, hierarchies: list[str]) -> float | None:
    """Sum amount_total for rows matching any hierarchy in the list."""
    matches = [
        a for (s, h, _n, a) in rows
        if s == statement and h in hierarchies and a is not None
    ]
    return sum(matches) if matches else None


def _hier_one(rows: list[tuple], statement: str, hierarchy: str) -> float | None:
    """Pull a single hierarchy's amount_total. Returns None if missing.

    When multiple rows share the same hierarchy on the same statement
    (extraction noise: occasionally the page header gets captured as a phantom
    Roman row alongside the real row), pick the one with the largest absolute
    value — phantom rows from page headers carry tiny date-stamp values like
    31 or 5; real BS line items are always orders of magnitude larger."""
    candidates = [a for (s, h, _n, a) in rows
                  if s == statement and h == hierarchy and a is not None]
    if not candidates:
        return None
    return max(candidates, key=abs)


# Item-name patterns for the BS "grand total" lines. Some banks' extractions
# don't carry a hierarchy code on these rows (TSKB's "TOTAL ASSETS"); using
# the item name lets us recover them.
import re as _re
_TOTAL_ASSETS_NAME = _re.compile(
    r"^\s*(?:AKTİF\s+TOPLAMI|BİLANÇO\s+TOPLAMI|TOPLAM\s+AKTİF|TOTAL\s+ASSETS)\s*$",
    _re.IGNORECASE,
)
_TOTAL_LIAB_NAME = _re.compile(
    r"^\s*(?:PASİF\s+TOPLAMI|TOPLAM\s+PASİF|TOTAL\s+LIABILITIES\s+AND\s+(?:SHAREHOLDERS'?\s+)?EQUITY)\s*$",
    _re.IGNORECASE,
)


def _named_total(rows: list[tuple], statement: str, pat: _re.Pattern) -> float | None:
    """Find a 'total' row by item-name pattern. Picks the LARGEST matching
    amount when multiple rows match (some banks emit duplicate totals)."""
    matches = [
        a for (s, _h, n, a) in rows
        if s == statement and pat.match(n or "") and a is not None
    ]
    return max(matches) if matches else None


def compute_one(
    conn: sqlite3.Connection,
    bank_ticker: str,
    period: str,
    kind: str = "unconsolidated",
) -> BankMetrics:
    # Balance-sheet rows
    bs = conn.execute(
        """SELECT statement, hierarchy, item_name, amount_total
           FROM bank_audit_balance_sheet
           WHERE bank_ticker=? AND period=? AND kind=?""",
        (bank_ticker, period, kind),
    ).fetchall()

    # Total Assets: prefer the explicit "AKTİF TOPLAMI / TOTAL ASSETS" row
    # (some banks like TSKB emit it without a hierarchy code, so a Roman-numeral
    # sum alone misses these). Fall back to the Roman sum.
    total_assets = _named_total(bs, "assets", _TOTAL_ASSETS_NAME)
    if total_assets is None:
        total_assets = _hier_sum(bs, "assets", ASSET_ROMAN)
    gross_loans = _hier_one(bs, "assets", ASSET_GROSS_LOANS)
    total_ecl_raw = _hier_one(bs, "assets", ASSET_ECL)
    # ECL is reported as a negative deduction line — take abs for the ratio.
    total_ecl = abs(total_ecl_raw) if total_ecl_raw is not None else None
    deposits = _hier_one(bs, "liabilities", LIAB_DEPOSITS)
    equity = _hier_one(bs, "liabilities", LIAB_EQUITY)

    # Net income — prefer hierarchy XXV. (total incl. discontinued ops); fall
    # back to XIX. (continuing ops only) when XXV. row isn't populated.
    ni = conn.execute(
        """SELECT amount FROM bank_audit_profit_loss
           WHERE bank_ticker=? AND period=? AND kind=? AND hierarchy IN (?, ?)
           ORDER BY CASE hierarchy WHEN ? THEN 0 ELSE 1 END LIMIT 1""",
        (bank_ticker, period, kind,
         PL_NET_INCOME_PRIMARY, PL_NET_INCOME_FALLBACK, PL_NET_INCOME_PRIMARY),
    ).fetchone()
    net_income = ni[0] if ni else None

    # Credit-quality rows for current period.
    cq = conn.execute(
        """SELECT section, stage1_amount, stage2_amount, stage3_amount, total_amount
           FROM bank_audit_credit_quality
           WHERE bank_ticker=? AND period=? AND kind=? AND period_type='current'""",
        (bank_ticker, period, kind),
    ).fetchall()
    cq_by_section = {r[0]: r for r in cq}

    g = cq_by_section.get("npl_brsa_gross")
    p = cq_by_section.get("npl_brsa_provision")
    n = cq_by_section.get("npl_brsa_net")

    npl_gross = g[4] if g else None
    npl_provision = p[4] if p else None
    npl_net = n[4] if n else None
    npl_group3 = g[1] if g else None
    npl_group4 = g[2] if g else None
    npl_group5 = g[3] if g else None

    return BankMetrics(
        bank_ticker=bank_ticker,
        period=period,
        kind=kind,
        total_assets=total_assets,
        gross_loans=gross_loans,
        total_ecl=total_ecl,
        deposits=deposits,
        equity=equity,
        net_income=net_income,
        npl_gross=npl_gross,
        npl_provision=npl_provision,
        npl_net=npl_net,
        npl_group3=npl_group3,
        npl_group4=npl_group4,
        npl_group5=npl_group5,
        npl_ratio=_safe_div(npl_gross, gross_loans),
        coverage_ratio=_safe_div(npl_provision, npl_gross),
        roa=_safe_div(net_income, total_assets),
        roe=_safe_div(net_income, equity),
        ldr=_safe_div(gross_loans, deposits),
        ecl_ratio=_safe_div(total_ecl, gross_loans),
    )


def all_tickers(conn: sqlite3.Connection, period: str, kind: str) -> list[str]:
    return [r[0] for r in conn.execute(
        """SELECT DISTINCT bank_ticker FROM bank_audit_extractions
           WHERE period=? AND kind=? AND success=1 ORDER BY bank_ticker""",
        (period, kind),
    )]


def _fmt_bn(v: float | None) -> str:
    """Format a TL-thousands value into billion TL with 1dp."""
    if v is None:
        return "    n/a"
    return f"{v / 1e6:>7.1f}B"


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "  n/a"
    return f"{v * 100:>5.2f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default="2025Q4", help="reporting period (default 2025Q4)")
    ap.add_argument("--kind", default="unconsolidated",
                    choices=["unconsolidated", "consolidated"])
    ap.add_argument("--ticker", help="single ticker; default = all banks")
    ap.add_argument("--format", default="table", choices=["table", "json", "csv"])
    args = ap.parse_args()

    with sqlite3.connect(str(DB_PATH)) as conn:
        if args.ticker:
            tickers = [args.ticker.upper()]
        else:
            tickers = all_tickers(conn, args.period, args.kind)
        results = [compute_one(conn, t, args.period, args.kind) for t in tickers]

    if args.format == "json":
        print(json.dumps([asdict(r) for r in results], indent=2, default=str))
        return
    if args.format == "csv":
        cols = list(asdict(results[0]).keys()) if results else []
        print(",".join(cols))
        for r in results:
            d = asdict(r)
            print(",".join("" if d[c] is None else str(d[c]) for c in cols))
        return

    # Table format
    print(f"\n{args.period} {args.kind} — {len(results)} banks (values in TL million)\n")
    print(
        f"{'Bank':<8} {'Assets':>10} {'Loans':>10} {'Deposits':>10} {'Equity':>10} "
        f"{'NetInc':>10}  {'NPL':>7}  {'Cov':>7}  {'ROA':>7}  {'ROE':>7}  {'LDR':>7}  {'ECL%':>7}"
    )
    print("-" * 140)
    for r in sorted(results, key=lambda x: (x.total_assets or 0), reverse=True):
        print(
            f"{r.bank_ticker:<8} "
            f"{_fmt_bn(r.total_assets)} "
            f"{_fmt_bn(r.gross_loans)} "
            f"{_fmt_bn(r.deposits)} "
            f"{_fmt_bn(r.equity)} "
            f"{_fmt_bn(r.net_income)}  "
            f"{_fmt_pct(r.npl_ratio)}  "
            f"{_fmt_pct(r.coverage_ratio)}  "
            f"{_fmt_pct(r.roa)}  "
            f"{_fmt_pct(r.roe)}  "
            f"{_fmt_pct(r.ldr)}  "
            f"{_fmt_pct(r.ecl_ratio)}"
        )


if __name__ == "__main__":
    main()
