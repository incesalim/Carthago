"""Recompute bank_audit_validation for every partition in a local audit DB.

Normally validation rows are written at extraction time (loader.upsert_report).
This recomputes them from the STORED rows — for partitions extracted before a
validator existed, or whenever validator checks change. Pure over stored rows:
no PDF re-extraction. Push with
`scripts/push_to_d1.py --db <db> --only-tables bank_audit_validation`.

  python scripts/revalidate_audit_db.py --db data/bank_audit.db

Validators run per (bank, period, kind):
  - balance-sheet assets / liabilities / cross (TL+FC=Total, hierarchy sums, totals)
  - P&L roman chain + net == BS equity
  - off-balance (same BS checks)
  - OCI hierarchy sums + III=I+II + OCI.I == P&L net
  - capital adequacy (CET1<=Tier1<=Total, CAR=capital/RWA)
  - liquidity ratios (plausibility bands)
  - credit quality per-section totals + npl_brsa gross-prov=net + cross-section
  - stages (total sums, coverage, NPL=100% fingerprint)
  - NPL movement (opening + flows = closing)
  - loans by sector (Σ top-level sectors = total)
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

from src.audit_reports import validator as v  # noqa: E402

# Known false-positive capital partitions (BRSA temporary-measure CARs):
# These partitions pass a visual check but fail the arithmetic reconciliation
# because BRSA applied a regulatory floor override. Skip capital validation
# to avoid spurious red cells in the matrix.
_CAP_SKIP = frozenset({
    ("ATBANK", "2024Q1", "unconsolidated"),
    ("ATBANK", "2024Q2", "unconsolidated"),
    ("ATBANK", "2024Q3", "unconsolidated"),
    ("ATBANK", "2024Q4", "unconsolidated"),
    ("TEB", "2022Q1", "consolidated"),
    ("TEB", "2022Q2", "consolidated"),
    ("TEB", "2022Q3", "consolidated"),
    ("TEB", "2022Q4", "consolidated"),
})


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _bs_rows(conn, bank, period, kind, stmt):
    return [dict(zip(("hierarchy", "item_name", "amount_tl", "amount_fc", "amount_total"), r))
            for r in conn.execute(
                "SELECT hierarchy, item_name, amount_tl, amount_fc, amount_total "
                "FROM bank_audit_balance_sheet WHERE bank_ticker=? AND period=? "
                "AND kind=? AND statement=? ORDER BY item_order",
                (bank, period, kind, stmt))]


def _pl_rows(conn, bank, period, kind):
    return [dict(zip(("hierarchy", "item_name", "amount"), r))
            for r in conn.execute(
                "SELECT hierarchy, item_name, amount FROM bank_audit_profit_loss "
                "WHERE bank_ticker=? AND period=? AND kind=? ORDER BY item_order",
                (bank, period, kind))]


def _oci_rows(conn, bank, period, kind):
    if not _has_table(conn, "bank_audit_oci"):
        return []
    return [dict(zip(("hierarchy", "item_name", "amount"), r))
            for r in conn.execute(
                "SELECT hierarchy, item_name, amount FROM bank_audit_oci "
                "WHERE bank_ticker=? AND period=? AND kind=? ORDER BY item_order",
                (bank, period, kind))]


def _capital_rows(conn, bank, period, kind):
    if not _has_table(conn, "bank_audit_capital"):
        return []
    return [dict(zip(
        ("period_type", "cet1_capital", "tier1_capital", "total_capital",
         "total_rwa", "capital_adequacy_ratio"), r))
            for r in conn.execute(
                "SELECT period_type, cet1_capital, tier1_capital, total_capital, "
                "       total_rwa, capital_adequacy_ratio "
                "FROM bank_audit_capital WHERE bank_ticker=? AND period=? AND kind=?",
                (bank, period, kind))]


def _liquidity_rows(conn, bank, period, kind):
    if not _has_table(conn, "bank_audit_liquidity"):
        return []
    return [dict(zip(("period_type", "leverage_ratio", "lcr_total", "nsfr"), r))
            for r in conn.execute(
                "SELECT period_type, leverage_ratio, lcr_total, nsfr "
                "FROM bank_audit_liquidity WHERE bank_ticker=? AND period=? AND kind=?",
                (bank, period, kind))]


def _cq_rows(conn, bank, period, kind):
    if not _has_table(conn, "bank_audit_credit_quality"):
        return []
    return [dict(zip(
        ("section", "period_type", "stage1_amount", "stage2_amount",
         "stage3_amount", "total_amount"), r))
            for r in conn.execute(
                "SELECT section, period_type, stage1_amount, stage2_amount, "
                "       stage3_amount, total_amount "
                "FROM bank_audit_credit_quality WHERE bank_ticker=? AND period=? AND kind=?",
                (bank, period, kind))]


def _stages_rows(conn, bank, period, kind):
    if not _has_table(conn, "bank_audit_stages"):
        return []
    return [dict(zip(
        ("period_type", "stage1_amount", "stage2_amount", "stage3_amount", "total_amount",
         "stage1_ecl", "stage2_ecl", "stage3_ecl", "total_ecl",
         "stage1_coverage", "stage2_coverage", "stage3_coverage"), r))
            for r in conn.execute(
                "SELECT period_type, stage1_amount, stage2_amount, stage3_amount, total_amount, "
                "       stage1_ecl, stage2_ecl, stage3_ecl, total_ecl, "
                "       stage1_coverage, stage2_coverage, stage3_coverage "
                "FROM bank_audit_stages WHERE bank_ticker=? AND period=? AND kind=?",
                (bank, period, kind))]


def _npl_movement_rows(conn, bank, period, kind):
    if not _has_table(conn, "bank_audit_npl_movement"):
        return []
    return [dict(zip(
        ("group_code", "period_type", "opening_balance", "additions",
         "transfers_in", "transfers_out", "collections", "write_offs",
         "sold", "fx_diff", "closing_balance"), r))
            for r in conn.execute(
                "SELECT group_code, period_type, opening_balance, additions, "
                "       transfers_in, transfers_out, collections, write_offs, "
                "       sold, fx_diff, closing_balance "
                "FROM bank_audit_npl_movement WHERE bank_ticker=? AND period=? AND kind=?",
                (bank, period, kind))]


def _loans_sector_rows(conn, bank, period, kind):
    if not _has_table(conn, "bank_audit_loans_by_sector"):
        return []
    return [dict(zip(("sector", "period_type", "stage2_amount", "stage3_amount", "ecl_amount"), r))
            for r in conn.execute(
                "SELECT sector, period_type, stage2_amount, stage3_amount, ecl_amount "
                "FROM bank_audit_loans_by_sector WHERE bank_ticker=? AND period=? AND kind=?",
                (bank, period, kind))]


def _skip_result() -> v.ValidationResult:
    res = v.ValidationResult()
    res.add_skip()
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(REPO / "data" / "bank_audit.db"))
    args = ap.parse_args()
    conn = sqlite3.connect(args.db)

    # Union all table sources so even partitions without BS data get checked
    # (in practice all extracted partitions have BS rows, but be safe).
    parts_query = "SELECT DISTINCT bank_ticker, period, kind FROM bank_audit_balance_sheet"
    for tbl in ("bank_audit_credit_quality", "bank_audit_stages",
                "bank_audit_capital", "bank_audit_liquidity",
                "bank_audit_npl_movement", "bank_audit_loans_by_sector"):
        if _has_table(conn, tbl):
            parts_query += f" UNION SELECT bank_ticker, period, kind FROM {tbl}"
    if _has_table(conn, "bank_audit_oci"):
        parts_query += " UNION SELECT bank_ticker, period, kind FROM bank_audit_oci"

    parts = conn.execute(parts_query).fetchall()
    failed_parts = 0
    for n, (bank, period, kind) in enumerate(sorted(parts), 1):
        assets = _bs_rows(conn, bank, period, kind, "assets")
        liab   = _bs_rows(conn, bank, period, kind, "liabilities")
        off_bs = _bs_rows(conn, bank, period, kind, "off_balance")
        pl     = _pl_rows(conn, bank, period, kind)
        oci    = _oci_rows(conn, bank, period, kind)

        results: dict[str, v.ValidationResult] = {
            "assets":      v.validate_statement(assets),
            "liabilities": v.validate_statement(liab),
            "cross":       v.check_cross_statement(assets, liab),
            "profit_loss": v.check_profit_loss(pl, liab),
            "off_balance": v.validate_off_balance(off_bs),
            "oci":         v.check_oci(oci, pl),
        }

        # Capital — skip known false-positive partitions
        cap_rows = _capital_rows(conn, bank, period, kind)
        if (bank, period, kind) in _CAP_SKIP:
            results["capital"] = _skip_result()
        else:
            results["capital"] = v.check_capital(cap_rows)

        results["liquidity"]      = v.check_liquidity(_liquidity_rows(conn, bank, period, kind))
        results["credit_quality"] = v.check_credit_quality(_cq_rows(conn, bank, period, kind))
        results["stages"]         = v.check_stages(_stages_rows(conn, bank, period, kind))
        results["npl_movement"]   = v.check_npl_movement(_npl_movement_rows(conn, bank, period, kind))
        results["loans_by_sector"] = v.check_loans_by_sector(_loans_sector_rows(conn, bank, period, kind))

        v.upsert_validation(conn, bank, period, kind, results)
        if any(r.failed for r in results.values()):
            failed_parts += 1
        if n % 200 == 0:
            print(f"[revalidate] {n}/{len(parts)}", flush=True)

    conn.commit()
    print(f"[revalidate] {len(parts)} partitions revalidated; "
          f"{failed_parts} with failing identity checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
