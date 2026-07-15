"""Targeted single-statement fleet re-extraction.

Re-parses ONLY the requested statement from each PDF — `extract(only={statement})`
skips the six slow deep-scan extractors — then upserts just that one table and
pushes just that one table to D1. This lets a one-lane extractor fix be applied
across the fleet without re-running all 14 extractors per PDF (the difference
between minutes-to-an-hour and ~3.5 hrs).

  python scripts/reextract_statement.py --statement equity_change --banks ALL
  python scripts/reextract_statement.py --statement equity_change --banks AKBNK,GARAN --dry-run
  # fast iterate loop — re-extract only what's failing, validate inline:
  python scripts/reextract_statement.py --statement equity_change --only-failing --dry-run

Validation is computed INLINE per partition by default (recomputes the whole
partition from stored rows, persists bank_audit_validation, prints live [vFAIL]
lines) — so a separate revalidate_audit_db.py pass is NOT needed for touched
partitions. Pass --no-inline-validate to skip it (then run revalidate_audit_db.py
→ push_to_d1 --only-tables bank_audit_validation → sync_audit_expected.py --push).
The non-dry-run push includes bank_audit_validation when validated inline; run
sync_audit_expected.py --push afterward to refresh the coverage matrix.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

from src.audit_reports import r2_storage  # noqa: E402
from src.audit_reports import validator as _validator  # noqa: E402
from src.audit_reports.extractor import extract  # noqa: E402
from src.audit_reports.equity_change import (  # noqa: E402
    EquityChangeReport, upsert as _upsert_equity,
)
from src.audit_reports.oci import OCIReport, upsert as _upsert_oci  # noqa: E402
from src.audit_reports.npl_movement import NplMovementReport, upsert as _upsert_npl  # noqa: E402
from src.audit_reports.loans_by_sector import (  # noqa: E402
    LoansBySectorReport, upsert as _upsert_lbs,
)
from src.audit_reports.bank_profile import upsert_profile as _upsert_bp  # noqa: E402
from src.audit_reports.audit_opinion import upsert_opinion as _upsert_op  # noqa: E402
from src.audit_reports.free_provision import upsert_free_provision as _upsert_fp  # noqa: E402
from src.audit_reports.credit_quality import (  # noqa: E402
    CreditQualityReport, upsert as _upsert_cq,
)
from src.audit_reports.capital_adequacy import (  # noqa: E402
    CapitalReport, upsert as _upsert_cap,
)
from src.audit_reports.liquidity import LiquidityReport, upsert as _upsert_liq  # noqa: E402
from src.audit_reports.fx_position import FxReport, upsert as _upsert_fx  # noqa: E402
from src.audit_reports.repricing import RepricingReport, upsert as _upsert_rp  # noqa: E402
from src.audit_reports.schema import init_schema  # noqa: E402
from scripts.revalidate_audit_db import revalidate_partition  # noqa: E402
from scripts.sync_audit_reports import list_r2_pdfs, _restrict_to_latest_period  # noqa: E402
from scripts.audit_d1 import DB, pull_snapshot, push_partitions, push_snapshot  # noqa: E402

# statement key (extractor `only=` token) → its D1/SQLite table.
STATEMENT_TABLE = {
    "equity_change": "bank_audit_equity_change",
    "oci": "bank_audit_oci",
    "cash_flow": "bank_audit_cash_flow",
    "npl_movement": "bank_audit_npl_movement",
    "loans_by_sector": "bank_audit_loans_by_sector",
    "bank_profile": "bank_audit_profile",
    # audit_opinion has no validator (like bank_profile) — re-extract by --banks
    # --force, not --only-failing.
    "audit_opinion": "bank_audit_opinion",
    "free_provision": "bank_audit_free_provision",  # no validator; --banks --force
    # credit_quality feeds the DERIVED bank_audit_stages table — re-extracting it
    # requires a build_bank_audit_stages.py rebuild + stages revalidation after the
    # run (see below). Target by --banks --force, not --only-failing: the broken
    # partitions FAIL on `stages`, not `credit_quality`.
    "credit_quality": "bank_audit_credit_quality",
    # §4 ratio tables.
    "capital": "bank_audit_capital",
    "liquidity": "bank_audit_liquidity",
    # §4 market-risk (CAMELS "S").
    "fx_position": "bank_audit_fx_position",
    "repricing": "bank_audit_repricing",
    # Core statements — used by the single-cell re-extract (the /admin per-cell
    # button forces just this one table; broad/fleet runs keep the guard). assets,
    # liabilities and off_balance share one table, keyed by the `statement` column.
    "bs_assets": "bank_audit_balance_sheet",
    "bs_liabilities": "bank_audit_balance_sheet",
    "off_balance": "bank_audit_balance_sheet",
    "profit_loss": "bank_audit_profit_loss",
}

# UI / registry statement-type key → the extractor `only=` token above, so the
# /admin coverage matrix (and the reextract-statement workflow) can pass its own
# keys. `stages` is derived from credit_quality — re-extracting credit_quality
# rebuilds it (see the stages-rebuild block in main()).
ALIASES = {
    "other_comprehensive_income": "oci",
    "profile": "bank_profile",
    "balance_sheet_assets": "bs_assets",
    "balance_sheet_liabilities": "bs_liabilities",
    "stages": "credit_quality",
}

# token → the name used in bank_audit_validation.statement (differs only for BS).
VALIDATOR_NAME = {"bs_assets": "assets", "bs_liabilities": "liabilities"}


def _worker(args):
    """Pickleable worker: download one PDF, extract ONLY the requested statement,
    return its rows. Upsert happens in the parent (single DB connection)."""
    ticker, period, kind, key, statement, tmp_dir = args
    t0 = time.time()
    dest = Path(tmp_dir) / f"{ticker}_{period}_{kind}.pdf"
    try:
        r2_storage.download_to(key, dest)
    except Exception as e:  # noqa: BLE001
        return (ticker, period, kind, False, 0, time.time() - t0,
                f"r2:{type(e).__name__}", None, str(dest))
    try:
        rep = extract(str(dest), only={statement})
    except Exception as e:  # noqa: BLE001
        return (ticker, period, kind, False, 0, time.time() - t0,
                f"extract:{type(e).__name__}:{str(e)[:60]}", None, str(dest))
    if statement == "oci":
        n = len(getattr(rep, "other_comprehensive_income", []) or [])
    elif statement == "cash_flow":
        n = len(getattr(rep, "cash_flow", []) or [])
    elif statement == "npl_movement":
        n = len(getattr(rep, "npl_movement", []) or [])
    elif statement == "loans_by_sector":
        n = len(getattr(rep, "loans_by_sector", []) or [])
    elif statement == "bank_profile":
        bp = getattr(rep, "bank_profile", None)
        n = 0 if (bp is None or bp.is_empty()) else 1
    elif statement == "audit_opinion":
        op = getattr(rep, "audit_opinion", None)
        n = 0 if (op is None or op.is_empty()) else 1
    elif statement == "free_provision":
        fpr = getattr(rep, "free_provision", None)
        n = 0 if (fpr is None or fpr.is_empty()) else 1
    elif statement == "credit_quality":
        n = len(getattr(rep, "credit_quality", []) or [])
    elif statement == "bs_assets":
        n = len(getattr(rep, "bs_assets", []) or [])
    elif statement == "bs_liabilities":
        n = len(getattr(rep, "bs_liabilities", []) or [])
    elif statement == "off_balance":
        n = len(getattr(rep, "off_balance", []) or [])
    elif statement == "profit_loss":
        n = len(getattr(rep, "profit_loss", []) or [])
    elif statement == "capital":
        n = 0 if getattr(rep, "capital", None) is None else 1
    elif statement == "liquidity":
        n = 0 if getattr(rep, "liquidity", None) is None else 1
    elif statement == "fx_position":
        fx = getattr(rep, "fx_position", None)
        n = len(fx.rows) if fx and getattr(fx, "rows", None) else 0
    elif statement == "repricing":
        rp = getattr(rep, "repricing", None)
        n = len(rp.rows) if rp and getattr(rp, "rows", None) else 0
    else:
        eq = getattr(rep, "equity_change", None)
        n = len(eq.rows) if eq and getattr(eq, "rows", None) else 0
    return (ticker, period, kind, True, n, time.time() - t0, "", rep, str(dest))


def _upsert(conn, statement, bank, period, kind, rep) -> int:
    if statement == "equity_change":
        report = getattr(rep, "equity_change", None) or EquityChangeReport(pdf_path=rep.pdf_path)
        return _upsert_equity(conn, bank, period, kind, report)
    if statement == "oci":
        report = OCIReport(pdf_path=rep.pdf_path,
                           rows=getattr(rep, "other_comprehensive_income", []) or [])
        return _upsert_oci(conn, bank, period, kind, report)
    if statement == "cash_flow":
        rows = getattr(rep, "cash_flow", []) or []
        conn.execute('DELETE FROM bank_audit_cash_flow WHERE bank_ticker=? AND period=? AND kind=?',
                     (bank, period, kind))
        if rows:
            conn.executemany(
                'INSERT INTO bank_audit_cash_flow '
                '(bank_ticker, period, kind, item_order, hierarchy, item_name, footnote, amount) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                [(bank, period, kind, r.order, r.hierarchy, r.name, r.footnote, r.cur_amount)
                 for r in rows])
        return len(rows)
    if statement == "npl_movement":
        report = NplMovementReport(pdf_path=rep.pdf_path,
                                   rows=getattr(rep, "npl_movement", []) or [])
        return _upsert_npl(conn, bank, period, kind, report)
    if statement == "loans_by_sector":
        report = LoansBySectorReport(pdf_path=rep.pdf_path,
                                     rows=getattr(rep, "loans_by_sector", []) or [])
        return _upsert_lbs(conn, bank, period, kind, report)
    if statement == "bank_profile":
        bp = getattr(rep, "bank_profile", None)
        # Mirror the loader's skip-if-empty: don't write an all-NULL row for a bank
        # that doesn't disclose (it stays 'missing'). bank_profile has no validator,
        # so --only-failing can't select it — re-extract by --banks instead.
        if bp is None or bp.is_empty():
            return 0
        _upsert_bp(conn, bank, period, kind, bp)
        return 1
    if statement == "audit_opinion":
        op = getattr(rep, "audit_opinion", None)
        # Skip-if-empty, like bank_profile: an 'unknown' classification must not
        # overwrite a stored verdict. upsert_opinion returns None when empty.
        return _upsert_op(conn, bank, period, kind, op) or 0
    if statement == "free_provision":
        fpr = getattr(rep, "free_provision", None)
        # Skip-if-empty: no disclosure found must not wipe a captured value.
        return _upsert_fp(conn, bank, period, kind, fpr) or 0
    if statement == "credit_quality":
        report = CreditQualityReport(pdf_path=rep.pdf_path,
                                     rows=getattr(rep, "credit_quality", []) or [])
        return _upsert_cq(conn, bank, period, kind, report)
    if statement == "capital":
        report = getattr(rep, "capital", None) or CapitalReport(pdf_path=rep.pdf_path)
        return _upsert_cap(conn, bank, period, kind, report)
    if statement == "liquidity":
        report = getattr(rep, "liquidity", None) or LiquidityReport(pdf_path=rep.pdf_path)
        return _upsert_liq(conn, bank, period, kind, report)
    if statement == "fx_position":
        report = getattr(rep, "fx_position", None) or FxReport(pdf_path=rep.pdf_path)
        return _upsert_fx(conn, bank, period, kind, report)
    if statement == "repricing":
        report = getattr(rep, "repricing", None) or RepricingReport(pdf_path=rep.pdf_path)
        return _upsert_rp(conn, bank, period, kind, report)
    if statement in ("bs_assets", "bs_liabilities", "off_balance"):
        # assets / liabilities / off_balance share bank_audit_balance_sheet, keyed by
        # the `statement` column — delete + insert only this one. Mirrors loader.py.
        stmt_name = {"bs_assets": "assets", "bs_liabilities": "liabilities",
                     "off_balance": "off_balance"}[statement]
        attr = {"bs_assets": "bs_assets", "bs_liabilities": "bs_liabilities",
                "off_balance": "off_balance"}[statement]
        rows = getattr(rep, attr, None) or []
        conn.execute(
            "DELETE FROM bank_audit_balance_sheet "
            "WHERE bank_ticker=? AND period=? AND kind=? AND statement=?",
            (bank, period, kind, stmt_name))
        if rows:
            conn.executemany(
                "INSERT INTO bank_audit_balance_sheet "
                "(bank_ticker, period, kind, statement, item_order, hierarchy, item_name, "
                " footnote, amount_tl, amount_fc, amount_total) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(bank, period, kind, stmt_name, r.order, r.hierarchy, r.name, r.footnote,
                  r.cur_tl, r.cur_fc, r.cur_total) for r in rows])
        return len(rows)
    if statement == "profit_loss":
        rows = getattr(rep, "profit_loss", []) or []
        conn.execute("DELETE FROM bank_audit_profit_loss "
                     "WHERE bank_ticker=? AND period=? AND kind=?", (bank, period, kind))
        if rows:
            conn.executemany(
                "INSERT INTO bank_audit_profit_loss "
                "(bank_ticker, period, kind, item_order, hierarchy, item_name, footnote, amount) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(bank, period, kind, r.order, r.hierarchy, r.name, r.footnote, r.cur_amount)
                 for r in rows])
        return len(rows)
    raise ValueError(f"upsert not wired for statement {statement!r}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--statement", required=True,
                    choices=list(STATEMENT_TABLE) + list(ALIASES))
    ap.add_argument("--banks", default="ALL", help="ALL or comma-separated tickers")
    ap.add_argument("--periods", default="", help="comma-separated YYYYQn (optional)")
    ap.add_argument("--kind", default="", choices=["", "consolidated", "unconsolidated"],
                    help="restrict to one kind (default: both) — used by the single-cell path")
    ap.add_argument("--workers", type=int, default=min(8, (os.cpu_count() or 4)))
    ap.add_argument("--latest-period", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="re-extract + upsert LOCAL db only; no D1 push / snapshot")
    ap.add_argument("--only-failing", action="store_true",
                    help="re-extract ONLY partitions NOT currently passing this statement's "
                         "validation — i.e. failing (checks_failed>0) OR empty/un-validated "
                         "(checks_passed=0, e.g. 0 rows → validation skipped). Reads "
                         "bank_audit_validation in the LOCAL db. Skips the proven-passing rest.")
    ap.add_argument("--no-inline-validate", action="store_true",
                    help="skip inline per-partition validation (fall back to the separate "
                         "revalidate_audit_db.py step)")
    ap.add_argument("--force", action="store_true",
                    help="overwrite even partitions whose stored data already PASSES this "
                         "statement's validation (default: leave correct data untouched)")
    args = ap.parse_args()
    statement = ALIASES.get(args.statement, args.statement)
    table = STATEMENT_TABLE[statement]
    vname = VALIDATOR_NAME.get(statement, statement)  # name in bank_audit_validation
    kind = args.kind.strip() or None
    banks = (None if args.banks.strip().upper() == "ALL"
             else {b.strip().upper() for b in args.banks.split(",") if b.strip()})
    periods = {p.strip().upper() for p in args.periods.split(",") if p.strip()} or None

    if not args.dry_run:
        pull_snapshot(guard=True)

    # Ensure any newly-added audit tables exist on the pulled snapshot DB. The
    # R2 snapshot predates a new statement (e.g. fx_position/repricing), so the
    # upsert's DELETE/INSERT would hit "no such table". init_schema is all
    # CREATE ... IF NOT EXISTS (idempotent) — mirrors sync_audit_reports.py.
    with sqlite3.connect(str(DB)) as _c:
        init_schema(_c)

    pdfs = list_r2_pdfs()
    if banks:
        pdfs = [(t, p, k, key) for (t, p, k, key) in pdfs if t.upper() in banks]
    if periods:
        pdfs = [(t, p, k, key) for (t, p, k, key) in pdfs if p.upper() in periods]
    if kind:
        pdfs = [(t, p, k, key) for (t, p, k, key) in pdfs if k == kind]
    if args.latest_period:
        pdfs = _restrict_to_latest_period(pdfs)
    if args.only_failing:
        # Intersect with the partitions NOT currently passing this statement's
        # validation = failing (checks_failed>0) OR empty/un-validated
        # (checks_passed=0 — e.g. 0 rows extracted → validation skipped). The
        # latter is essential: a broadly-empty statement (OCI/CF stale empties)
        # has checks_failed=0, so a failed-only filter would skip exactly the
        # partitions that most need re-extracting. Proven-passing partitions
        # (checks_failed=0 AND checks_passed>0) are left out.
        with sqlite3.connect(str(DB)) as _c:
            todo = {(t.upper(), p.upper(), k) for (t, p, k) in _c.execute(
                "SELECT bank_ticker, period, kind FROM bank_audit_validation "
                "WHERE statement=? AND (checks_failed>0 OR checks_passed=0)", (vname,))}
        pdfs = [(t, p, k, key) for (t, p, k, key) in pdfs
                if (t.upper(), p.upper(), k) in todo]
        print(f"[reext] --only-failing -> {len(pdfs)} not-passing {statement} partition(s)",
              flush=True)
    print(f"[reext] statement={statement} table={table} pdfs={len(pdfs)} "
          f"workers={args.workers}{' (dry-run)' if args.dry_run else ''}", flush=True)
    if not pdfs:
        print("[reext] nothing to do"); return 0

    touched: list[tuple[str, str, str]] = []
    counts = {"ok": 0, "fail": 0, "rows": 0, "vok": 0, "vfail": 0, "keep": 0}
    inline = not args.no_inline_validate
    with tempfile.TemporaryDirectory(prefix="bddk_reext_") as td:
        work = [(t, p, k, key, statement, td) for (t, p, k, key) in pdfs]
        # NOTE: no max_tasks_per_child — on Windows it can DEADLOCK the pool at a
        # recycle boundary (hung a fleet run at ~task 400). Single-statement
        # extraction is light (the six deep-scan extractors are skipped), so worker
        # memory doesn't grow enough to need recycling anyway.
        with sqlite3.connect(str(DB)) as conn, \
             ProcessPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(_worker, w) for w in work]
            done = 0
            for fut in as_completed(futs):
                t, p, k, ok, n, secs, err, rep, path = fut.result()
                done += 1
                if not ok:
                    counts["fail"] += 1
                    print(f"  [FAIL] {t:<8} {p} {k:<14} {err}", flush=True)
                    continue
                # Non-destructive: never overwrite data that already validates
                # (--only-failing already excludes these, but the guard makes a
                # plain re-extract safe too). --force overrides.
                if not args.force and _validator.statement_passes(conn, t, p, k, vname):
                    counts["keep"] += 1
                    continue
                _upsert(conn, statement, t, p, k, rep)
                conn.execute(
                    "UPDATE bank_audit_extractions SET extracted_at=CURRENT_TIMESTAMP "
                    "WHERE bank_ticker=? AND period=? AND kind=?", (t, p, k))
                touched.append((t, p, k))
                counts["ok"] += 1
                counts["rows"] += n
                # Inline validation: recompute the WHOLE partition from stored rows
                # (the just-upserted statement + the others already in the db) and
                # persist it, so failures surface DURING the run and the separate
                # revalidate_audit_db.py pass is unnecessary for touched partitions.
                if inline:
                    results = revalidate_partition(conn, t, p, k)
                    _validator.upsert_validation(conn, t, p, k, results)
                    eqr = results.get(vname)
                    if eqr is not None and eqr.failed:
                        counts["vfail"] += 1
                        chk = eqr.failures[0].get("check", "?") if eqr.failures else "?"
                        print(f"  [vFAIL] {t:<8} {p} {k:<14} {statement} "
                              f"P{eqr.passed}/F{eqr.failed}/S{eqr.skipped} {chk}", flush=True)
                    elif eqr is not None:
                        counts["vok"] += 1
                if done % 50 == 0:
                    conn.commit()
                    tally = f" vpass={counts['vok']} vfail={counts['vfail']}" if inline else ""
                    print(f"  [{done}/{len(work)}] last {t} {p} {k} rows={n} ({secs:.0f}s){tally}",
                          flush=True)
                try:
                    Path(path).unlink()
                except OSError:
                    pass
            conn.commit()
    vtally = f" | validated: pass={counts['vok']} FAIL={counts['vfail']}" if inline else ""
    keptt = f" kept={counts['keep']}" if counts['keep'] else ""
    print(f"[reext] ok={counts['ok']} fail={counts['fail']}{keptt} rows={counts['rows']}{vtally}",
          flush=True)

    # Push the validation rows too when computed inline, so the dashboard/matrix
    # reflect the fresh pass/fail without a separate revalidate+push.
    push_tables = [table] + (["bank_audit_validation"] if inline else [])
    # credit_quality feeds the DERIVED bank_audit_stages table. Rebuild it from the
    # fresh rows, then re-validate the touched partitions so `stages` reflects the
    # new loans_by_stage (the inline pass above saw the pre-rebuild stages). Done
    # before the dry-run return so a dry-run still verifies the stages locally.
    if statement == "credit_quality" and touched:
        subprocess.run(
            [sys.executable, str(REPO / "scripts" / "build_bank_audit_stages.py"),
             "--db", str(DB)], check=True)
        with sqlite3.connect(str(DB)) as conn:
            for t, p, k in touched:
                _validator.upsert_validation(conn, t, p, k, revalidate_partition(conn, t, p, k))
            conn.commit()
        push_tables.append("bank_audit_stages")
        print(f"[reext] rebuilt bank_audit_stages + revalidated {len(touched)} partition(s)",
              flush=True)

    if args.dry_run:
        print("[reext] dry-run — no D1 push / snapshot", flush=True)
        return 0
    push_partitions(touched, db_path=DB, window_hours=24, tables=push_tables)
    push_snapshot(DB)
    print("[reext] done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
