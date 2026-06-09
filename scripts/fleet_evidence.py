"""Fleet dry-run + evidence report (rework plan Phase 2). NO production writes.

Re-extracts the whole corpus from R2 into a SCRATCH SQLite (never
data/bank_audit.db, never D1, never the R2 snapshot), runs the structural
validator over both the scratch and the current production-state DB, and
writes an old-vs-new evidence report. Phase 3 (actual repair) only happens
after a human reviews this report.

Buckets per (bank, period, kind):
  regressed    — new is worse: fewer rows (>2), totals changed where old
                 validated clean, or more identity failures
  investigate  — new still fails identity checks (old did too), or totals
                 differ and neither side validates clean
  improved     — identity failures reduced (best: to zero) or rows recovered
                 with totals intact
  unchanged    — same rows, same totals, same validation outcome

  python scripts/fleet_evidence.py                  # full fleet (~3-5 h)
  python scripts/fleet_evidence.py --only EMLAK --periods 2026Q1   # smoke
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

from src.audit_reports import validator as v  # noqa: E402

PROD_DB = REPO / "data" / "bank_audit.db"
SCRATCH_DB = REPO / "data" / "fleet_scratch.db"
OUT_DIR = REPO / "data" / "backfill_evidence"


def _rows(conn, bank, period, kind, stmt):
    return [dict(zip(("hierarchy", "item_name", "amount_tl", "amount_fc", "amount_total"), r))
            for r in conn.execute(
                "SELECT hierarchy, item_name, amount_tl, amount_fc, amount_total "
                "FROM bank_audit_balance_sheet WHERE bank_ticker=? AND period=? "
                "AND kind=? AND statement=? ORDER BY item_order",
                (bank, period, kind, stmt))]


def _partition_stats(conn, bank, period, kind) -> dict | None:
    a = _rows(conn, bank, period, kind, "assets")
    li = _rows(conn, bank, period, kind, "liabilities")
    if not a and not li:
        return None
    npl = conn.execute(
        "SELECT COUNT(*) FROM bank_audit_profit_loss WHERE bank_ticker=? AND period=? AND kind=?",
        (bank, period, kind)).fetchone()[0]
    ni = conn.execute(
        "SELECT amount FROM bank_audit_profit_loss WHERE bank_ticker=? AND period=? AND kind=? "
        "ORDER BY item_order DESC LIMIT 1", (bank, period, kind)).fetchone()
    ra, rl = v.validate_statement(a), v.validate_statement(li)
    rc = v.check_cross_statement(a, li)
    a_total, a_romans = v._statement_total(a)
    return {
        "rows_assets": len(a), "rows_liab": len(li), "rows_pl": npl,
        "total_assets": a_total if a_total is not None else a_romans,
        "net_income": ni[0] if ni else None,
        "val_failed": ra.failed + rl.failed + rc.failed,
        "val_passed": ra.passed + rl.passed + rc.passed,
        "failures": (ra.failures + rl.failures + rc.failures)[:8],
    }


def _bucket(old: dict | None, new: dict | None) -> tuple[str, str]:
    if new is None:
        return "regressed", "partition missing in re-extraction"
    if old is None:
        return "improved", "new partition (was missing)"
    notes = []
    rows_old = old["rows_assets"] + old["rows_liab"] + old["rows_pl"]
    rows_new = new["rows_assets"] + new["rows_liab"] + new["rows_pl"]
    if rows_new < rows_old - 2:
        return "regressed", f"rows {rows_old}→{rows_new}"
    ta_old, ta_new = old["total_assets"], new["total_assets"]
    totals_differ = (ta_old is not None and ta_new is not None
                     and ta_old != 0 and abs(ta_new - ta_old) / abs(ta_old) > 1e-3)
    if totals_differ and old["val_failed"] == 0:
        return "regressed", f"total assets changed {ta_old:,.0f}→{ta_new:,.0f} though old validated clean"
    if new["val_failed"] > old["val_failed"]:
        return "regressed", f"identity failures {old['val_failed']}→{new['val_failed']}"
    if new["val_failed"] > 0:
        return "investigate", f"still {new['val_failed']} identity failure(s) (was {old['val_failed']})"
    if totals_differ:
        notes.append(f"total assets {ta_old:,.0f}→{ta_new:,.0f}")
    if new["val_failed"] < old["val_failed"]:
        notes.append(f"identity failures {old['val_failed']}→0")
    if rows_new > rows_old:
        notes.append(f"rows {rows_old}→{rows_new}")
    if notes:
        return "improved", "; ".join(notes)
    return "unchanged", ""


def compare(prod_db: Path, scratch_db: Path,
            only: set[str] | None = None, periods: set[str] | None = None) -> dict:
    po = sqlite3.connect(str(prod_db))
    pn = sqlite3.connect(str(scratch_db))
    parts = {(b, p, k) for b, p, k in po.execute(
        "SELECT DISTINCT bank_ticker, period, kind FROM bank_audit_balance_sheet")}
    parts |= {(b, p, k) for b, p, k in pn.execute(
        "SELECT DISTINCT bank_ticker, period, kind FROM bank_audit_balance_sheet")}
    # Scoped runs (--only/--periods) only judge the partitions they re-extracted;
    # the full fleet run keeps the union so a PDF gone from R2 still surfaces.
    if only:
        parts = {(b, p, k) for (b, p, k) in parts if b.upper() in only}
    if periods:
        parts = {(b, p, k) for (b, p, k) in parts if p.upper() in periods}
    out: dict[str, dict] = {}
    for n, (b, p, k) in enumerate(sorted(parts), 1):
        old = _partition_stats(po, b, p, k)
        new = _partition_stats(pn, b, p, k)
        bucket, note = _bucket(old, new)
        out[f"{b}|{p}|{k}"] = {"bucket": bucket, "note": note, "old": old, "new": new}
        if n % 100 == 0:
            print(f"  [compare] {n}/{len(parts)}", flush=True)
    return out


def render_report(results: dict) -> str:
    counts = Counter(r["bucket"] for r in results.values())
    by_bank: dict[str, Counter] = defaultdict(Counter)
    for key, r in results.items():
        by_bank[key.split("|")[0]][r["bucket"]] += 1
    L: list[str] = []
    L.append("# Fleet re-extraction evidence report (Phase 2 — dry run, nothing pushed)")
    L.append("")
    L.append("Old = current production-state DB (data/bank_audit.db). "
             "New = scratch re-extraction with the current extractor. "
             "Buckets: see scripts/fleet_evidence.py.")
    L.append("")
    L.append("## Summary")
    L.append("")
    for b in ("improved", "unchanged", "investigate", "regressed"):
        L.append(f"- **{b}**: {counts.get(b, 0)}")
    L.append("")
    L.append("## Per bank")
    L.append("")
    L.append("| Bank | improved | unchanged | investigate | regressed |")
    L.append("|---|---|---|---|---|")
    for bank in sorted(by_bank):
        c = by_bank[bank]
        L.append(f"| {bank} | {c.get('improved', 0)} | {c.get('unchanged', 0)} | "
                 f"{c.get('investigate', 0)} | {c.get('regressed', 0)} |")
    for bucket in ("regressed", "investigate"):
        keys = [k for k, r in results.items() if r["bucket"] == bucket]
        L.append("")
        L.append(f"## {bucket.capitalize()} ({len(keys)})")
        L.append("")
        for k in sorted(keys):
            r = results[k]
            L.append(f"- **{k.replace('|', ' ')}** — {r['note']}")
            for f in ((r["new"] or {}).get("failures") or [])[:3]:
                L.append(f"    - {f['check']}: {f['node'][:70]} "
                         f"exp={f['expected']:,.0f} act={f['actual']:,.0f}")
    L.append("")
    L.append("## Improved (notes)")
    L.append("")
    for k in sorted(k for k, r in results.items() if r["bucket"] == "improved"):
        L.append(f"- {k.replace('|', ' ')} — {results[k]['note']}")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--only", type=str, default="")
    ap.add_argument("--periods", type=str, default="")
    ap.add_argument("--scratch", type=str, default=str(SCRATCH_DB))
    ap.add_argument("--skip-extract", action="store_true",
                    help="reuse the existing scratch DB; only compare+report")
    args = ap.parse_args()

    scratch = Path(args.scratch)
    only = ({t.strip().upper() for t in args.only.split(",") if t.strip()}
            or None)
    periods = ({p.strip().upper() for p in args.periods.split(",") if p.strip()}
               or None)
    if not args.skip_extract:
        from scripts.sync_audit_reports import extract_from_r2
        counts = extract_from_r2(workers=args.workers, db_path=scratch,
                                 only=only, periods=periods)
        print(f"[evidence] re-extract: {counts}")

    results = compare(PROD_DB, scratch, only=only, periods=periods)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "evidence.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT_DIR / "report.md").write_text(render_report(results), encoding="utf-8")
    counts = Counter(r["bucket"] for r in results.values())
    print(f"[evidence] {dict(counts)} → {OUT_DIR / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
