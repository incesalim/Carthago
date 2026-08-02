#!/usr/bin/env python3
"""Turn a wall of validator failures into a ranked list of CAUSES. Read-only.

`bank_audit_validation` says which identities broke. It does not say why, and
every repair in this repo's history has started with a human opening the PDF to
find out. That step is mechanical — see src/audit_reports/triage.py — so this
runs it over the whole failing set and reports the distribution:

    212 failing partitions → 96 anchor_miss, 61 column_slip, 44 source_defect …

which is the shape every past fix actually had. "50 errors, 44 of them one
cause" is a day of work; "50 errors" is a week.

Writes nothing but its own report: no D1, no row updates, no extractor edits.
The verdicts are hypotheses with evidence attached, for a human to act on.

  python scripts/triage_partitions.py --limit 20
  python scripts/triage_partitions.py --statement capital --render
  python scripts/triage_partitions.py --bank AKBNK --period 2022Q4 --render

PDFs come from data/_bench/ when cached, else R2 (needs R2 credentials). With
--offline, uncached partitions are skipped rather than downloaded — which is
what the local machine should do, since the full corpus is a heavy pull.
"""
from __future__ import annotations

import argparse
import collections
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

from src.audit_reports import registry as reg          # noqa: E402
from src.audit_reports import triage                   # noqa: E402

CACHE = REPO / "data" / "_bench"
DEFAULT_OUT = REPO / "docs" / "knowledge" / "triage"

# bank_audit_validation.statement values that are not registry keys.
_EXTRA = {
    "cross": ("bank_audit_balance_sheet", None),
    "pl_chain": ("bank_audit_profit_loss", None),
}


def lane_table(statement: str) -> tuple[str, str | None] | None:
    """(table, statement-column value) for a validation statement."""
    for st in reg.REGISTRY:
        if st.validation_statement == statement:
            return st.table, st.statement
    return _EXTRA.get(statement)


def pdf_for(bank: str, period: str, kind: str, offline: bool) -> Path | None:
    """Cached PDF, else pull it from R2 into the same cache."""
    local = CACHE / f"{bank}_{period}_{kind}.pdf"
    if local.exists():
        return local
    if offline:
        return None
    try:
        from src.audit_reports import r2_storage
        key = r2_storage.make_key(bank, period, kind)
        CACHE.mkdir(parents=True, exist_ok=True)
        r2_storage.download_to(key, local)
        return local if local.exists() else None
    except Exception as e:                     # noqa: BLE001 - report, never abort the sweep
        print(f"  ! {bank} {period} {kind}: R2 fetch failed ({e})")
        return None


def select(conn: sqlite3.Connection, args) -> list[sqlite3.Row]:
    sql = ("SELECT bank_ticker, period, kind, statement, checks_failed, failed_detail "
           "FROM bank_audit_validation WHERE checks_failed > 0")
    params: list = []
    for col, val in (("statement", args.statement), ("bank_ticker", args.bank),
                     ("period", args.period), ("kind", args.kind)):
        if val:
            sql += f" AND {col}=?"
            params.append(val)
    sql += " ORDER BY statement, bank_ticker, period"
    if args.limit:
        sql += f" LIMIT {int(args.limit)}"
    return conn.execute(sql, params).fetchall()


def write_report(notes: list[triage.TriageNote], out_dir: Path, rendered: dict[str, str],
                 skipped: int) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    by_verdict: collections.Counter = collections.Counter(n.verdict for n in notes)
    # A cause that spans many banks is one extractor fix; one that hits a single
    # bank is a filing quirk. That split is the whole point of the rollup.
    banks_per: dict[str, set] = collections.defaultdict(set)
    for n in notes:
        banks_per[n.verdict].add(n.bank)

    md = [f"# Audit triage — {today}",
          "",
          "> **Status: generated, read-only.** `scripts/triage_partitions.py` over",
          "> `bank_audit_validation`. Every verdict is a deterministic hypothesis with",
          "> its evidence — no model was consulted, no number was produced, nothing was",
          "> written to D1. Confirm against the PDF before acting.",
          "",
          f"{len(notes)} failing partitions triaged"
          + (f", {skipped} skipped (no PDF available)" if skipped else "") + ".",
          "",
          "## Causes",
          "",
          "| Cause | Partitions | Banks | What it means |",
          "|---|--:|--:|---|"]
    for verdict, n in by_verdict.most_common():
        md.append(f"| `{verdict}` | {n} | {len(banks_per[verdict])} | "
                  f"{triage.REMEDY.get(verdict, '')} |")

    md += ["", "## By lane", "", "| Lane | Partitions | Dominant cause |", "|---|--:|---|"]
    by_lane: dict[str, list] = collections.defaultdict(list)
    for n in notes:
        by_lane[n.statement].append(n.verdict)
    for lane, verdicts in sorted(by_lane.items(), key=lambda kv: -len(kv[1])):
        top, cnt = collections.Counter(verdicts).most_common(1)[0]
        md.append(f"| {lane} | {len(verdicts)} | `{top}` ({cnt}) |")

    md += ["", "## Partitions", ""]
    for n in sorted(notes, key=lambda x: (x.verdict, x.statement, x.bank, x.period)):
        md.append(f"### {n.partition} — `{n.verdict}`")
        md.append("")
        if n.error:
            md += [f"_{n.error}_", ""]
            continue
        pages = f"anchor p{n.anchor_page or '?'}"
        if n.best_page and n.best_page != n.anchor_page:
            pages += f", best-scoring p{n.best_page}"
        if n.window:
            pages += f", statement window p{n.window[0]}–p{n.window[-1]}"
        md.append(f"_{pages}, {n.pdf_pages}-page filing._")
        md.append("")
        for f in n.findings:
            md.append(f"- **{f.label}** ({f.confidence}"
                      + (f", p{f.page}" if f.page else "") + f") — {f.detail}")
            for ev in f.evidence:
                md.append(f"  - {ev}")
        key = f"{n.bank}_{n.period}_{n.kind}_{n.statement}"
        if key in rendered:
            md += ["", f"![{n.partition}]({rendered[key]})"]
        md.append("")

    path = out_dir / f"{today}-audit-triage.md"
    path.write_text("\n".join(md), encoding="utf-8")
    (out_dir / f"{today}-audit-triage.json").write_text(
        json.dumps([n.to_dict() for n in notes], indent=2, ensure_ascii=False),
        encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(REPO / "data" / "bank_audit.db"))
    ap.add_argument("--statement", help="one validation lane, e.g. capital")
    ap.add_argument("--bank")
    ap.add_argument("--period")
    ap.add_argument("--kind", choices=["consolidated", "unconsolidated"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--radius", type=int, default=6,
                    help="pages either side of the anchor to search before sweeping")
    ap.add_argument("--render", action="store_true",
                    help="rasterise the best-scoring page next to each note")
    ap.add_argument("--offline", action="store_true",
                    help="use only cached PDFs; never pull from R2")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"no audit DB at {db_path}")
        return 1
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    rows = select(conn, args)
    print(f"{len(rows)} failing partitions selected\n")
    out_dir = Path(args.out)
    notes: list[triage.TriageNote] = []
    rendered: dict[str, str] = {}
    skipped = 0

    for r in rows:
        bank, period, kind = r["bank_ticker"], r["period"], r["kind"]
        lane = lane_table(r["statement"])
        if not lane:
            print(f"  ? {bank} {period} {kind} {r['statement']}: no table mapping")
            skipped += 1
            continue
        table, db_stmt = lane
        pdf = pdf_for(bank, period, kind, args.offline)
        if pdf is None:
            skipped += 1
            continue
        note = triage.triage_partition(
            conn, pdf, bank, period, kind, r["statement"], table,
            r["failed_detail"], db_statement=db_stmt, radius=args.radius)
        notes.append(note)
        print(f"  {note.verdict:24} {note.partition}")
        if args.render and note.best_page and not note.error:
            img_dir = out_dir / "pages"
            name = f"{bank}_{period}_{kind}_{r['statement']}_p{note.best_page}.png"
            if triage.render_page(pdf, note.best_page, img_dir / name):
                rendered[f"{bank}_{period}_{kind}_{r['statement']}"] = f"pages/{name}"

    conn.close()
    if not notes:
        print("\nnothing triaged (no PDFs available?)")
        return 0

    path = write_report(notes, out_dir, rendered, skipped)
    counts = collections.Counter(n.verdict for n in notes)
    print(f"\n{'cause':26} {'n':>5}")
    print("-" * 33)
    for verdict, n in counts.most_common():
        print(f"{verdict:26} {n:5d}")
    try:
        shown = path.relative_to(REPO)
    except ValueError:
        shown = path
    print(f"\nreport → {shown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
