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
from src.audit_reports.schema import init_schema  # noqa: E402

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

# Same class, narrower blast radius: the P&L chain foots but the printed BS
# equity line disagrees with the printed P&L net — skip ONLY the net=equity
# cross-check (check_pl_bottomline), keeping the chain identities guarded.
_PL_BOTTOMLINE_SKIP = frozenset({
    # TSKB 2022Q1 unc: PDF p8 P&L prints XIX = XXV = 605.861 (XVII 821.861 −
    # XVIII 216.000 foots exactly); PDF p6 BS prints 16.6 = 16.6.2 = 605.673.
    # Both statements extracted faithfully; the SOURCE disagrees with itself by
    # 188 and no single-cell fix reconciles both sides. (Same report carries the
    # confirmed cash-flow source typo in _CF_SKIP.)
    ("TSKB", "2022Q1", "unconsolidated"),
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
    # TSKB 2022Q1 cons: NOW CONFIRMED against the PDF (p18) — every roman matches the
    # printed statement (I 7.717.884 / II (1.406.045) / III (1.462.683) / IV 162.027 /
    # V 5.027.208 / VI 3.661.118 / VII 8.672.302). I+II+III+IV = 5.011.183 ≠ the printed
    # V 5.027.208 (off 16.025), and VII = 8.672.302 foots with the DERIVED V (5.011.183),
    # not the printed one — a source typo on the V line. Faithful extraction, source
    # doesn't foot; no single-cell fix reconciles both identities. (Earlier left flagged
    # because the IR host was unreachable; the PDF is now read and confirms the typo.)
    ("TSKB", "2022Q1", "consolidated"),
})

# OCI partitions whose roman chain III=I+II doesn't foot because the PUBLISHED
# statement is internally inconsistent — data verified faithful to the PDF.
_OCI_SKIP = frozenset({
    # ATBANK 2023Q4 unconsolidated: the real OCI statement is extracted faithfully
    # (I 156.657 / II 151.030, every 2.x line matches the PDF), but the bank PRINTS
    # "III. TOPLAM KAPSAMLI GELİR (I+II) (307.687)" — parenthesised NEGATIVE — while
    # I+II = +307.687. A source sign typo on the total line; no cell fix reconciles it.
    ("ATBANK", "2023Q4", "unconsolidated"),
})

# loans-by-sector partitions whose Σ-sectors=total footing is GENUINELY uncheckable
# because of how the bank discloses the table — verified against the PDF (a skip is
# NEVER for a dropped/wrong extraction). ATBANK prints the IFRS-9 sector table
# (Stage-2 "İkinci Aşama" / Stage-3 "Üçüncü Aşama" columns, faithfully extracted per
# sector) but omits the closing "Toplam" row entirely — the table ends at "Diğer" and
# the next page goes straight to the provision-movement note — so there is no total to
# foot against. (ALNTF, the other gap, uses the legacy past-due schema with NO
# Stage-2/Stage-3 by sector; the extractor now skips that page, leaving 0 rows → the
# validator skips naturally and the cell is marked not_expected in
# data/audit_not_disclosed.json. So ALNTF needs no entry here.)
_LBS_SKIP = frozenset({
    ("ATBANK", "2022Q4", "consolidated"), ("ATBANK", "2022Q4", "unconsolidated"),
    ("ATBANK", "2023Q4", "consolidated"), ("ATBANK", "2023Q4", "unconsolidated"),
    ("ATBANK", "2024Q4", "consolidated"), ("ATBANK", "2024Q4", "unconsolidated"),
    ("ATBANK", "2025Q4", "consolidated"), ("ATBANK", "2025Q4", "unconsolidated"),
})


def curated_skips() -> set[tuple[str, str, str, str]]:
    """(bank, period, kind, statement_type_key) for every partition a human has
    deliberately excused from a check.

    These produce a `_skip_result()` — zero checks passed — which is
    INDISTINGUISHABLE from "the validator had nothing to check" if you only look
    at the counts. The two mean opposite things: an accidental zero-pass is an
    unverified cell, while a curated skip is a cell someone read the PDF for and
    established that the SOURCE doesn't foot (see the per-list comments above; the
    rule at the top of this module is that a skip is never for a wrong
    extraction). The coverage spine needs to tell them apart before it can treat
    zero-pass as an error — otherwise this curation reads as 53 red cells.

    _PL_BOTTOMLINE_SKIP is deliberately absent: it suppresses only the bottom-line
    cross-check and leaves the roman chain running, so those partitions still pass
    real checks and never look unverified.
    """
    out: set[tuple[str, str, str, str]] = set()
    for bank, period, kind in _CAP_SKIP:
        out.add((bank, period, kind, "capital"))
    for bank, period, kind in _PL_SKIP:
        out.add((bank, period, kind, "profit_loss"))
    for bank, period, kind in _CF_SKIP:
        out.add((bank, period, kind, "cash_flow"))
    for bank, period, kind in _OCI_SKIP:
        out.add((bank, period, kind, "other_comprehensive_income"))
    for bank, period, kind in _LBS_SKIP:
        out.add((bank, period, kind, "loans_by_sector"))
    for bank, period, kind in _CQ_SKIP:
        out.add((bank, period, kind, "credit_quality"))
    return out


def curated_skip_banks() -> set[tuple[str, str]]:
    """(bank, statement_type_key) skipped for EVERY period — currently just
    ATBANK's capital lane (a BRSA regulatory-floor CAR that never reconciles)."""
    return {(bank, "capital") for bank in _CAP_SKIP_BANKS}


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
    # provision + net_balance were stored but never SELECTed, so the table's own
    # second identity (closing − |provision| = net) was unavailable to the
    # validator — free coverage on 2,097/2,097 rows, left on the floor.
    return [dict(zip(
        ("group_code", "period_type", "opening_balance", "additions",
         "transfers_in", "transfers_out", "collections", "write_offs",
         "sold", "fx_diff", "closing_balance", "provision", "net_balance"), r))
            for r in conn.execute(
                "SELECT group_code, period_type, opening_balance, additions, "
                "       transfers_in, transfers_out, collections, write_offs, "
                "       sold, fx_diff, closing_balance, provision, net_balance "
                "FROM bank_audit_npl_movement WHERE bank_ticker=? AND period=? AND kind=?",
                (bank, period, kind))]


def _profile_rows(conn, bank, period, kind):
    if not _has_table(conn, "bank_audit_profile"):
        return []
    return [dict(zip(("branches_domestic", "branches_foreign", "branches_total",
                      "personnel"), r))
            for r in conn.execute(
                "SELECT branches_domestic, branches_foreign, branches_total, personnel "
                "FROM bank_audit_profile WHERE bank_ticker=? AND period=? AND kind=?",
                (bank, period, kind))]


def _opinion_rows(conn, bank, period, kind):
    if not _has_table(conn, "bank_audit_opinion"):
        return []
    return [dict(zip(("opinion_type", "is_modified", "report_kind", "basis_text",
                      "auditor"), r))
            for r in conn.execute(
                "SELECT opinion_type, is_modified, report_kind, basis_text, auditor "
                "FROM bank_audit_opinion WHERE bank_ticker=? AND period=? AND kind=?",
                (bank, period, kind))]


def _loans_sector_rows(conn, bank, period, kind):
    if not _has_table(conn, "bank_audit_loans_by_sector"):
        return []
    return [dict(zip(("sector", "period_type", "stage2_amount", "stage3_amount", "ecl_amount"), r))
            for r in conn.execute(
                "SELECT sector, period_type, stage2_amount, stage3_amount, ecl_amount "
                "FROM bank_audit_loans_by_sector WHERE bank_ticker=? AND period=? AND kind=?",
                (bank, period, kind))]


def _fx_position_rows(conn, bank, period, kind):
    if not _has_table(conn, "bank_audit_fx_position"):
        return []
    return [dict(zip(
        ("period_type", "currency", "on_bs_assets", "on_bs_liab",
         "net_on_balance", "net_off_balance", "off_bs_receivable",
         "off_bs_payable", "net_position"), r))
            for r in conn.execute(
                "SELECT period_type, currency, on_bs_assets, on_bs_liab, "
                "       net_on_balance, net_off_balance, off_bs_receivable, "
                "       off_bs_payable, net_position "
                "FROM bank_audit_fx_position WHERE bank_ticker=? AND period=? AND kind=?",
                (bank, period, kind))]


def _repricing_rows(conn, bank, period, kind):
    if not _has_table(conn, "bank_audit_repricing"):
        return []
    return [dict(zip(
        ("period_type", "bucket", "rate_sensitive_assets", "rate_sensitive_liab",
         "gap", "cumulative_gap"), r))
            for r in conn.execute(
                "SELECT period_type, bucket, rate_sensitive_assets, rate_sensitive_liab, "
                "       gap, cumulative_gap "
                "FROM bank_audit_repricing WHERE bank_ticker=? AND period=? AND kind=?",
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
                 else v.check_profit_loss(
                     pl, None if (bank, period, kind) in _PL_BOTTOMLINE_SKIP else liab))
    cf_result = (_skip_result() if (bank, period, kind) in _CF_SKIP
                 else v.check_cash_flow(cf))
    results: dict[str, v.ValidationResult] = {
        "assets":      v.validate_statement(assets),
        "liabilities": v.validate_statement(liab),
        "cross":       v.check_cross_statement(assets, liab),
        "profit_loss": pl_result,
        "off_balance": v.validate_off_balance(off_bs),
        "oci":         (_skip_result() if (bank, period, kind) in _OCI_SKIP
                        else v.check_oci(oci, pl)),
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
    cq_rows  = _cq_rows(conn, bank, period, kind)
    npl_rows = _npl_movement_rows(conn, bank, period, kind)
    results["credit_quality"] = (_skip_result() if (bank, period, kind) in _CQ_SKIP
                                 else v.check_credit_quality(cq_rows, npl_rows))
    # `assets` carries the balance sheet's own loan book (row 2.1) — the only
    # independent read on the IFRS-9 stage table's denominator. Already in scope,
    # so no extra query; same shape as check_equity_change's `liabilities=liab`.
    results["stages"]         = v.check_stages(
        _stages_rows(conn, bank, period, kind), bs_loans=assets)
    # The authoritative period-end NPL by BRSA group (III/IV/V), from the
    # credit-quality table. check_npl_movement uses it two ways: to skip (not
    # fail) a roll-forward that doesn't tie only because of an unmodeled flow,
    # and — unconditionally — to reconcile the movement closing against it.
    _gross = next((r for r in cq_rows if r.get("section") == "npl_brsa_gross"
                   and r.get("period_type") == "current"), None)
    _gbg = ({"III": _gross.get("stage1_amount"), "IV": _gross.get("stage2_amount"),
             "V": _gross.get("stage3_amount")} if _gross else None)
    results["npl_movement"]   = v.check_npl_movement(npl_rows, gross_by_group=_gbg)
    results["loans_by_sector"] = (
        _skip_result() if (bank, period, kind) in _LBS_SKIP
        else v.check_loans_by_sector(_loans_sector_rows(conn, bank, period, kind)))
    results["fx_position"]    = v.check_fx_position(_fx_position_rows(conn, bank, period, kind))
    results["repricing"]      = v.check_repricing(_repricing_rows(conn, bank, period, kind))
    # The bank's OTHER filing for the same quarter. A consolidated group contains
    # the parent, so cons >= unco on branches and staff is arithmetic, not a
    # heuristic — and it is the only independent read this lane has (there is no
    # footing in a table of counts). Same shape as bs_loans=assets above.
    _other = "unconsolidated" if kind == "consolidated" else "consolidated"
    results["profile"] = v.check_profile(
        _profile_rows(conn, bank, period, kind),
        counterpart=_profile_rows(conn, bank, period, _other), kind=kind)
    results["audit_opinion"] = v.check_audit_opinion(
        _opinion_rows(conn, bank, period, kind))
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
                "bank_audit_fx_position", "bank_audit_repricing",
                "bank_audit_npl_movement", "bank_audit_loans_by_sector",
                "bank_audit_oci", "bank_audit_cash_flow", "bank_audit_equity_change"):
        if _has_table(conn, tbl):
            parts_query += f" UNION SELECT bank_ticker, period, kind FROM {tbl}"

    parts = conn.execute(parts_query).fetchall()
    failed_parts = 0
    for n, (bank, period, kind) in enumerate(sorted(parts), 1):
        results = revalidate_partition(conn, bank, period, kind)
        v.upsert_validation(conn, bank, period, kind, results)
        # The derived P&L role map rides along: same stored rows, same pass, so
        # bank_audit_pl_roles can never disagree with the validation about which
        # row is the period-net. Consumers join it instead of hardcoding an
        # ordinal (see schema.py).
        v.upsert_pl_roles(conn, bank, period, kind, _pl_rows(conn, bank, period, kind))
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
    # A snapshot pulled from R2 predates any table added since it was written —
    # bank_audit_pl_roles is written below, so make sure it exists first. The DDL
    # is all CREATE ... IF NOT EXISTS, so this is idempotent.
    init_schema(conn)
    total, failed_parts = revalidate_all(conn, progress=True)
    print(f"[revalidate] {total} partitions revalidated; "
          f"{failed_parts} with failing identity checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
