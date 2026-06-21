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
  - capital adequacy (Tier1=CET1+AT1, Total=Tier1+Tier2; ratios=component/RWA)
  - liquidity ratios (plausibility bands)
  - credit quality per-section totals + cross-section (gross-prov=net removed: collective provisioning)
  - stages (total sums, coverage, NPL=100% fingerprint)
  - NPL movement (opening + flows = closing; skips rows with NULL write_offs/sold/transfers_out)
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

# Known false-positive capital banks (BRSA temporary-measure CARs):
# These banks' reported CAR systematically differs from Total_Capital/RWA*100
# because BRSA applied a regulatory floor override for an extended period.
# Skip capital validation for them entirely to avoid spurious red cells.
_CAP_SKIP_BANKS = frozenset({"ATBANK"})

# Known false-positive partitions (same reason, narrower scope):
_CAP_SKIP = frozenset({
    ("TEB", "2022Q1", "consolidated"),
    ("TEB", "2022Q2", "consolidated"),
    ("TEB", "2022Q3", "consolidated"),
    ("TEB", "2022Q4", "consolidated"),
})

# Known immaterial source defects in the PUBLISHED income statement — the bank's
# own printed P&L doesn't foot, so this is NOT a recoverable extraction error and
# no single cell is wrong (the data is stored faithfully to the PDF). Skip the
# pl_chain identity check for these to avoid a spurious red coverage cell.
_PL_SKIP = frozenset({
    # ICBCT 2023Q2 cons: printed VIII (2.823.764) is 358 (0.013%) above the sum of
    # its individually-correct components III–VII; the bank's chain foots from VIII
    # onward, so the inconsistency is a source rounding that can't be attributed to
    # any one line. Net profit (XXV 1.478.869) is self-consistent.
    ("ICBCT", "2023Q2", "consolidated"),
})

# A skip is ONLY justified when the data is verified faithful to the PDF and the
# SOURCE itself doesn't foot — never to hide a wrong/garbled/unverified extraction
# (that would bless a wrong number, the same failure as loosening a tolerance).
# TFKB's credit_quality was previously skipped here, but its loans_ecl is genuinely
# WRONG (cross-contaminated from adjacent ECL tables), so it must stay FLAGGED, not
# hidden — removed. Empty until a real source-defect case is verified.
_CQ_SKIP: frozenset = frozenset()

# Cash-flow partitions whose roman chain (V=I+II+III+IV / VII=V+VI) doesn't foot
# because the PUBLISHED statement is internally inconsistent — data verified faithful
# to the PDF (a skip is NEVER for a wrong/unverified extraction).
_CF_SKIP = frozenset({
    # ALBRK 2023Q4 cons: RE-VERIFIED against the PDF — I 5.798.339 / II (6.523.592) /
    # III 16.952.152 / IV 2.150.135 sum to 18.377.034, but the bank prints V 18.477.034
    # (100.000 higher) and V+VI=VII holds with that printed V. Every cell matches the
    # PDF; the source itself doesn't foot. No single-cell fix reconciles both identities.
    ("ALBRK", "2023Q4", "consolidated"),
    # NOTE: TSKB 2022Q1 was removed — its V (5.027.208) doesn't reconcile and the IR host
    # was UNREACHABLE, so we never confirmed source-typo vs our misread. Skipping it would
    # have hidden a possibly-wrong number, so it stays FLAGGED until the PDF is read.
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


def _cf_rows(conn, bank, period, kind):
    if not _has_table(conn, "bank_audit_cash_flow"):
        return []
    return [dict(zip(("hierarchy", "item_name", "amount"), r))
            for r in conn.execute(
                "SELECT hierarchy, item_name, amount FROM bank_audit_cash_flow "
                "WHERE bank_ticker=? AND period=? AND kind=? ORDER BY item_order",
                (bank, period, kind))]


def _equity_rows(conn, bank, period, kind):
    if not _has_table(conn, "bank_audit_equity_change"):
        return []
    cols = (
        "hierarchy", "item_name", "period_type",
        "paid_in_capital", "share_premium", "share_cancellation_profits",
        "other_capital_reserves",
        "oci_not_reclassified_1", "oci_not_reclassified_2", "oci_not_reclassified_3",
        "oci_reclassified_1", "oci_reclassified_2", "oci_reclassified_3",
        "profit_reserves", "prior_period_profit_loss", "period_net_profit_loss",
        "total_equity", "minority_interest", "total_equity_incl_minority",
    )
    return [dict(zip(cols, r))
            for r in conn.execute(
                f"SELECT {','.join(cols)} FROM bank_audit_equity_change "
                "WHERE bank_ticker=? AND period=? AND kind=? ORDER BY period_type, item_order",
                (bank, period, kind))]


def _capital_rows(conn, bank, period, kind):
    if not _has_table(conn, "bank_audit_capital"):
        return []
    return [dict(zip(
        ("period_type", "cet1_capital", "additional_tier1_capital", "tier1_capital",
         "tier2_capital", "total_capital", "total_rwa",
         "cet1_ratio", "tier1_ratio", "capital_adequacy_ratio"), r))
            for r in conn.execute(
                "SELECT period_type, cet1_capital, additional_tier1_capital, tier1_capital, "
                "       tier2_capital, total_capital, total_rwa, "
                "       cet1_ratio, tier1_ratio, capital_adequacy_ratio "
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


def revalidate_partition(conn, bank: str, period: str, kind: str) -> dict[str, "v.ValidationResult"]:
    """Recompute ALL validation checks for one partition from its STORED rows
    (no PDF re-read). Returns the per-statement results dict — the caller persists
    it via `validator.upsert_validation`. Shared by the full revalidate pass and
    by reextract_statement.py's inline validation, so the two stay byte-identical."""
    assets = _bs_rows(conn, bank, period, kind, "assets")
    liab   = _bs_rows(conn, bank, period, kind, "liabilities")
    off_bs = _bs_rows(conn, bank, period, kind, "off_balance")
    pl     = _pl_rows(conn, bank, period, kind)
    oci    = _oci_rows(conn, bank, period, kind)
    cf     = _cf_rows(conn, bank, period, kind)
    eq     = _equity_rows(conn, bank, period, kind)

    pl_result = (_skip_result() if (bank, period, kind) in _PL_SKIP
                 else v.check_profit_loss(pl, liab))
    cf_result = (_skip_result() if (bank, period, kind) in _CF_SKIP
                 else v.check_cash_flow(cf))
    results: dict[str, v.ValidationResult] = {
        "assets":      v.validate_statement(assets),
        "liabilities": v.validate_statement(liab),
        "cross":       v.check_cross_statement(assets, liab),
        "profit_loss": pl_result,
        "off_balance": v.validate_off_balance(off_bs),
        "oci":         v.check_oci(oci, pl),
        "cash_flow":   cf_result,
        "equity_change": v.check_equity_change(eq, oci_rows=oci,
                                                liabilities=liab, period=period),
    }

    # Capital — skip known false-positive banks/partitions
    cap_rows = _capital_rows(conn, bank, period, kind)
    if bank in _CAP_SKIP_BANKS or (bank, period, kind) in _CAP_SKIP:
        results["capital"] = _skip_result()
    else:
        results["capital"] = v.check_capital(cap_rows)

    results["liquidity"]      = v.check_liquidity(_liquidity_rows(conn, bank, period, kind))
    cq_rows = _cq_rows(conn, bank, period, kind)
    results["credit_quality"] = (_skip_result() if (bank, period, kind) in _CQ_SKIP
                                 else v.check_credit_quality(cq_rows))
    results["stages"]         = v.check_stages(_stages_rows(conn, bank, period, kind))
    # The authoritative period-end NPL by BRSA group (III/IV/V), from the
    # credit-quality table, lets check_npl_movement skip (not fail) a roll-forward
    # that doesn't tie only because of an unmodeled flow — provided the movement
    # closing matches this gross. A mismatch is a real extraction error.
    _gross = next((r for r in cq_rows if r.get("section") == "npl_brsa_gross"
                   and r.get("period_type") == "current"), None)
    _gbg = ({"III": _gross.get("stage1_amount"), "IV": _gross.get("stage2_amount"),
             "V": _gross.get("stage3_amount")} if _gross else None)
    results["npl_movement"]   = v.check_npl_movement(
        _npl_movement_rows(conn, bank, period, kind), gross_by_group=_gbg)
    results["loans_by_sector"] = v.check_loans_by_sector(_loans_sector_rows(conn, bank, period, kind))
    return results


def revalidate_all(conn, progress: bool = False) -> tuple[int, int]:
    """Recompute + persist bank_audit_validation for EVERY partition from its stored
    data rows with the current validator code. Returns (n_partitions, n_failing).
    Shared by this script's CLI and by sync_audit_expected (so the coverage spine is
    always built from current-code verdicts, never the snapshot's frozen ones)."""
    # Union all table sources so even partitions without BS data get checked
    # (in practice all extracted partitions have BS rows, but be safe).
    parts_query = "SELECT DISTINCT bank_ticker, period, kind FROM bank_audit_balance_sheet"
    for tbl in ("bank_audit_credit_quality", "bank_audit_stages",
                "bank_audit_capital", "bank_audit_liquidity",
                "bank_audit_npl_movement", "bank_audit_loans_by_sector",
                "bank_audit_oci", "bank_audit_cash_flow", "bank_audit_equity_change"):
        if _has_table(conn, tbl):
            parts_query += f" UNION SELECT bank_ticker, period, kind FROM {tbl}"

    parts = conn.execute(parts_query).fetchall()
    failed_parts = 0
    for n, (bank, period, kind) in enumerate(sorted(parts), 1):
        results = revalidate_partition(conn, bank, period, kind)
        v.upsert_validation(conn, bank, period, kind, results)
        if any(r.failed for r in results.values()):
            failed_parts += 1
        if progress and n % 200 == 0:
            print(f"[revalidate] {n}/{len(parts)}", flush=True)
    conn.commit()
    return len(parts), failed_parts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(REPO / "data" / "bank_audit.db"))
    args = ap.parse_args()
    conn = sqlite3.connect(args.db)
    total, failed_parts = revalidate_all(conn, progress=True)
    print(f"[revalidate] {total} partitions revalidated; "
          f"{failed_parts} with failing identity checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
