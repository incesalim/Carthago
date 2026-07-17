"""Apply curated per-cell overrides to the production DB and push the affected
partitions to D1 — NO re-extraction. For balance-sheet/income-statement rows
the deterministic extractor can't recover (one-off OCR artifacts) but whose
correct values are legible in the PDF. Each override is transcribed by hand
into data/audit_overrides.json.

  python scripts/apply_overrides.py [--dry-run] [--no-push]

Override entry (data/audit_overrides.json "overrides" list):
  BS:  {bank_ticker, period, kind, statement: assets|liabilities|off_balance,
        hierarchy, item_name, amount_tl, amount_fc, amount_total, note}
  single-column statements — {bank_ticker, period, kind,
        statement: profit_loss|cash_flow|oci,
        hierarchy, item_name, amount, item_order?, note}
Matched by (bank, period, kind, statement, hierarchy); the row is UPDATED in
place, or INSERTED if the parser dropped it — at `item_order` when given (later
rows shift down), else appended at max item_order+1. Give `item_order` when
restoring a ROMAN row: all three are read by validator._pl_spine, whose spine is
an increasing-ordinal subsequence, so an appended roman falls out of it and its
identity skips instead of running.
Author multiple inserts into one partition tail-first (highest item_order
first) so each position stays valid as earlier rows shift.

  P&L hierarchy renames: {bank_ticker, period, kind, statement: "pl_rehier",
        renames: [{from, to, item_name}, ...], note}
For partitions where the extractor mis-assigned roman ordinals (AKBNK 2022
printed the "(XVII±XVIII)" subtotal under a second "XVIII." and shifted every
later roman by one). Amounts and labels are correct — only `hierarchy` moves.
Each rename matches (hierarchy=from AND item_name) exactly; author them
tail-first so no step leaves two rows on one ordinal.

  BS hierarchy renames: {bank_ticker, period, kind, statement: "bs_rehier",
        bs_statement: assets|liabilities|off_balance,
        renames: [{from, to, item_name, to_name?}, ...], note}
Same idea for a balance-sheet row the FILING mislabels — EXIM/VAKBN off-balance
stamp the Forward-FX Sell leg "3.2.2.2" (colliding with the Swap-Sell) instead of
"3.2.1.2"; a spliced column-header posts section A under a phantom "V" (HAYATK).
Match is (bs_statement, hierarchy=from trailing-dot-insensitive, item_name);
optional `to_name` strips a garbled label.
"""
from __future__ import annotations

import argparse
import gzip
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

from src.audit_reports import r2_storage  # noqa: E402
from src.audit_reports.schema import init_schema  # noqa: E402
from src.audit_reports.validator import validate_report  # noqa: E402
from scripts.audit_d1 import (  # noqa: E402
    AUDIT_TABLES, _ensure_d1_schema, _guard_against_ci_writers, _retry_wrangler,
)

DB = REPO / "data" / "bank_audit.db"
GZ = REPO / "data" / "bank_audit.db.gz"
OVR = REPO / "data" / "audit_overrides.json"
SNAP = "state/bank_audit.db.gz"

# Audit tables that carry their OWN extracted_at (not keyed off
# bank_audit_extractions) — push_to_d1 filters them on it directly, so the
# override push must bump it to keep them inside the --hours window.
_SELF_TS_TABLES = (
    "bank_audit_credit_quality", "bank_audit_profile", "bank_audit_loans_by_sector",
    "bank_audit_npl_movement", "bank_audit_stages", "bank_audit_capital",
    "bank_audit_liquidity",
)


def _has_col(conn: sqlite3.Connection, table: str, col: str) -> bool:
    return any(r[1] == col for r in conn.execute(f"PRAGMA table_info({table})"))


def _apply_one(conn: sqlite3.Connection, o: dict) -> str:
    b, p, k = o["bank_ticker"], o["period"], o["kind"]
    st = o["statement"]
    if st == "oci_replace":
        # Whole-table replacement for partitions where the OCI extractor captured
        # the WRONG statement (EXIM/etc. grabbed the equity statement + balance
        # sheet). Delete the garbage rows and insert the fitz-read OCI rows. `rows`
        # = [{hierarchy, item_name, amount}, ...] in statement order.
        conn.execute("DELETE FROM bank_audit_oci WHERE bank_ticker=? AND period=? AND kind=?",
                     (b, p, k))
        for i, r in enumerate(o["rows"], 1):
            conn.execute(
                "INSERT INTO bank_audit_oci (bank_ticker,period,kind,item_order,hierarchy,item_name,amount) "
                "VALUES (?,?,?,?,?,?,?)",
                (b, p, k, i, r["hierarchy"], r.get("item_name", r["hierarchy"]), r["amount"]))
        return f"OCI replace {b} {p} {k} ({len(o['rows'])} rows)"
    if st == "capital":
        # Per-column patch of the CURRENT-period §4 capital row. `fields` =
        # {column: value} for the dropped/column-slipped components (AT1, Tier2,
        # total, RWA, ratios). Columns whitelisted to the capital schema.
        allowed = {"cet1_capital", "additional_tier1_capital", "tier1_capital",
                   "tier2_capital", "total_capital", "total_rwa", "cet1_ratio",
                   "tier1_ratio", "capital_adequacy_ratio"}
        cols = [c for c in o["fields"] if c in allowed]
        if not cols:
            return f"capital SKIP {b} {p} {k} (no valid columns)"
        sets = ", ".join(f"{c}=?" for c in cols)
        vals = [o["fields"][c] for c in cols]
        conn.execute(
            f"UPDATE bank_audit_capital SET {sets} WHERE bank_ticker=? AND period=? "
            "AND kind=? AND period_type='current'", (*vals, b, p, k))
        return f"capital update {b} {p} {k} {dict((c, o['fields'][c]) for c in cols)}"
    if st == "credit_quality":
        # Upsert ONE section row of bank_audit_credit_quality (keyed by section +
        # period_type). Used for the Stage-3 (NPL) figure that a bank discloses as
        # PROSE instead of a table — "Donuk alacak tutarı 2 TL'dir" /
        # "Bulunmamaktadır" / "None" — which no table-anchored extractor can read.
        #
        # This is a SOURCED figure, never an inferred one: every entry quotes the
        # sentence (or the table row) it came from in `note`, and the new digital
        # banks' zeros are additionally corroborated by the balance-sheet
        # "Donuk Alacaklar" line. It matches check_stages' own stated contract —
        # "a genuine zero-NPL bank stores S3 = 0, not NULL" — which is exactly what
        # these banks mean and cannot express in a table they never print.
        #
        # `fields` = {column: value}; groups III/IV/V stay NULL when the bank gives
        # only a prose total (there is no split to record), so cq_section_total
        # correctly SKIPS rather than checking a fabricated decomposition.
        allowed = {"stage1_amount", "stage2_amount", "stage3_amount", "total_amount",
                   "heading_snippet", "source_page"}
        cols = [c for c in o["fields"] if c in allowed]
        if not cols:
            return f"credit_quality SKIP {b} {p} {k} (no valid columns)"
        sect, pt = o["section"], o.get("period_type", "current")
        row = conn.execute(
            "SELECT 1 FROM bank_audit_credit_quality WHERE bank_ticker=? AND period=? "
            "AND kind=? AND section=? AND period_type=?", (b, p, k, sect, pt)).fetchone()
        vals = [o["fields"][c] for c in cols]
        if row:
            sets = ", ".join(f"{c}=?" for c in cols)
            conn.execute(
                f"UPDATE bank_audit_credit_quality SET {sets} WHERE bank_ticker=? AND period=? "
                "AND kind=? AND section=? AND period_type=?", (*vals, b, p, k, sect, pt))
            verb = "update"
        else:
            names = ", ".join(cols)
            qs = ", ".join("?" for _ in cols)
            conn.execute(
                f"INSERT INTO bank_audit_credit_quality (bank_ticker,period,kind,section,"
                f"period_type,{names}) VALUES (?,?,?,?,?,{qs})", (b, p, k, sect, pt, *vals))
            verb = "insert"
        return (f"credit_quality {verb} {b} {p} {k} {sect}/{pt} "
                f"{dict((c, o['fields'][c]) for c in cols)}")
    if st == "pl_rehier":
        # Roman-ordinal renames for a tail the extractor shifted (amounts and
        # labels faithful — only the hierarchy column moves). Matched by exact
        # (hierarchy, item_name) so a duplicated ordinal ("XVIII." twice) is
        # unambiguous; a rename that matches nothing is reported, not silent.
        done, missed = [], []
        for r in o["renames"]:
            cur = conn.execute(
                "UPDATE bank_audit_profit_loss SET hierarchy=? WHERE bank_ticker=? "
                "AND period=? AND kind=? AND hierarchy=? AND item_name=?",
                (r["to"], b, p, k, r["from"], r["item_name"]))
            (done if cur.rowcount else missed).append(f"{r['from']}→{r['to']}")
        out = f"PL rehier {b} {p} {k}: {', '.join(done)}"
        return out + (f" (NO MATCH: {', '.join(missed)})" if missed else "")
    if st == "bs_rehier":
        # Balance-sheet hierarchy renames (mirror of pl_rehier) for a row the
        # FILING mislabels — e.g. EXIM/VAKBN off-balance stamp the Forward-FX
        # Sell leg "3.2.2.2" (colliding with the Swap-Sell) instead of "3.2.1.2"
        # (the sibling of the "3.2.1.1" Buy leg); or a spliced column-header posts
        # section A's aggregate under a phantom "V" (HAYATK). Values are faithful
        # — only `hierarchy` moves (with an optional `to_name` to strip a garbled
        # label). Matched by (bs_statement, hierarchy=from trailing-dot-insensitive,
        # item_name) exactly, so a duplicated key is unambiguous; a rename that
        # matches nothing is reported, not silent. `bs_statement` names the lane.
        done, missed = [], []
        bst = o["bs_statement"]
        for r in o["renames"]:
            sets, vals = "hierarchy=?", [r["to"]]
            if "to_name" in r:
                sets += ", item_name=?"
                vals.append(r["to_name"])
            cur = conn.execute(
                f"UPDATE bank_audit_balance_sheet SET {sets} WHERE bank_ticker=? "
                "AND period=? AND kind=? AND statement=? AND rtrim(hierarchy,'.')=rtrim(?,'.') "
                "AND item_name=?", (*vals, b, p, k, bst, r["from"], r["item_name"]))
            (done if cur.rowcount else missed).append(f"{r['from']}→{r['to']}")
        out = f"BS rehier {b} {p} {k} {bst}: {', '.join(done)}"
        return out + (f" (NO MATCH: {', '.join(missed)})" if missed else "")
    h = o["hierarchy"]
    # profit_loss / cash_flow / oci are the same shape — one single-column
    # (bank, period, kind, item_order, hierarchy, item_name, amount) table each —
    # and all three are read by validator._pl_spine, so the item_order rule below
    # applies identically to every one of them. One handler, three tables.
    _SINGLE_COL = {"profit_loss": ("bank_audit_profit_loss", "PL"),
                   "cash_flow":   ("bank_audit_cash_flow", "CF"),
                   "oci":         ("bank_audit_oci", "OCI")}
    if st in _SINGLE_COL:
        tbl, tag = _SINGLE_COL[st]
        row = conn.execute(
            f"SELECT item_order FROM {tbl} WHERE bank_ticker=? AND period=? "
            "AND kind=? AND hierarchy=?", (b, p, k, h)).fetchone()
        if row:
            conn.execute(
                f"UPDATE {tbl} SET amount=?, item_name=? "
                "WHERE bank_ticker=? AND period=? AND kind=? AND item_order=?",
                (o["amount"], o.get("item_name", h), b, p, k, row[0]))
            return f"{tag} update {b} {p} {k} {h}={o['amount']:,.0f}"
        # A restored roman MUST be slotted at its statement position, not appended:
        # _pl_spine takes the longest increasing-ordinal SUBSEQUENCE in item_order,
        # so a roman parked after the last row can never extend it and drops out of
        # the spine — the identity it was meant to satisfy then silently SKIPS
        # (ANADOLU 2022Q1's appended IV. leaves VIII=III+IV+V+VI+VII unchecked).
        if "item_order" in o:  # positional insert: shift later rows down
            # two-step via negatives — a plain +1 collides with the PK mid-update
            conn.execute(f"UPDATE {tbl} SET item_order=-(item_order+1) "
                         "WHERE bank_ticker=? AND period=? AND kind=? AND item_order>=?",
                         (b, p, k, o["item_order"]))
            conn.execute(f"UPDATE {tbl} SET item_order=-item_order "
                         "WHERE bank_ticker=? AND period=? AND kind=? AND item_order<0", (b, p, k))
            nxt = o["item_order"]
        else:
            nxt = (conn.execute(f"SELECT COALESCE(MAX(item_order),0)+1 FROM {tbl} "
                                "WHERE bank_ticker=? AND period=? AND kind=?", (b, p, k)).fetchone()[0])
        conn.execute(
            f"INSERT INTO {tbl} (bank_ticker,period,kind,item_order,hierarchy,item_name,amount) "
            "VALUES (?,?,?,?,?,?,?)", (b, p, k, nxt, h, o.get("item_name", h), o["amount"]))
        return f"{tag} insert {b} {p} {k} {h}={o['amount']:,.0f} @order{nxt}"
    # balance sheet. Match trailing-dot-insensitively: the loader normalises
    # "1.3.2." → "1.3.2" (see archive/normalize_hierarchy_keys.py), so an override
    # authored against the pre-normalisation key ("1.3.2.") would otherwise miss
    # the stored "1.3.2" row and INSERT a phantom duplicate — double-counting it
    # under its parent (the EXIM 2024Q4 1.3 hierarchy_sum break on re-apply).
    row = conn.execute(
        "SELECT item_order FROM bank_audit_balance_sheet WHERE bank_ticker=? AND period=? "
        "AND kind=? AND statement=? AND rtrim(hierarchy,'.')=rtrim(?,'.')", (b, p, k, st, h)).fetchone()
    if row:
        conn.execute(
            "UPDATE bank_audit_balance_sheet SET amount_tl=?, amount_fc=?, amount_total=?, item_name=? "
            "WHERE bank_ticker=? AND period=? AND kind=? AND statement=? AND item_order=?",
            (o["amount_tl"], o["amount_fc"], o["amount_total"], o.get("item_name", h), b, p, k, st, row[0]))
        return f"BS update {b} {p} {k} {st} {h}"
    if "item_order" in o:  # positional insert: shift later rows down, slot in at the right spot
        # two-step via negatives — a plain +1 collides with the UNIQUE(item_order) index mid-update
        conn.execute("UPDATE bank_audit_balance_sheet SET item_order=-(item_order+1) "
                     "WHERE bank_ticker=? AND period=? AND kind=? AND statement=? AND item_order>=?",
                     (b, p, k, st, o["item_order"]))
        conn.execute("UPDATE bank_audit_balance_sheet SET item_order=-item_order "
                     "WHERE bank_ticker=? AND period=? AND kind=? AND statement=? AND item_order<0",
                     (b, p, k, st))
        nxt = o["item_order"]
    else:
        nxt = (conn.execute("SELECT COALESCE(MAX(item_order),0)+1 FROM bank_audit_balance_sheet "
                            "WHERE bank_ticker=? AND period=? AND kind=? AND statement=?",
                            (b, p, k, st)).fetchone()[0])
    conn.execute(
        "INSERT INTO bank_audit_balance_sheet "
        "(bank_ticker,period,kind,statement,item_order,hierarchy,item_name,amount_tl,amount_fc,amount_total) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (b, p, k, st, nxt, h, o.get("item_name", h), o["amount_tl"], o["amount_fc"], o["amount_total"]))
    return f"BS insert {b} {p} {k} {st} {h} @order{nxt}"


def _revalidate_partition(conn, b, p, k):
    # Recompute ALL statement validations from stored rows, not just assets/
    # liabilities/cross. upsert_validation deletes the whole partition's
    # validation rows before re-inserting, so a partial dict would silently drop
    # off_balance / P&L / OCI / … rows — and an off_balance override (the first
    # of its kind) would never clear its own failure. Delegate to the shared
    # full revalidator so this stays byte-identical to the cron pass.
    from src.audit_reports import validator as v
    from scripts.revalidate_audit_db import revalidate_partition, _pl_rows
    res = revalidate_partition(conn, b, p, k)
    v.upsert_validation(conn, b, p, k, res)
    # Rebuild the derived P&L role map too. An override can MOVE which row is the
    # period-net (restoring a dropped roman re-anchors the template), and the D1
    # partition-clear below wipes every AUDIT_TABLES row for this partition —
    # including bank_audit_pl_roles. Without a fresh derived_at the windowed push
    # won't restore them and the partition silently loses its roles in D1 (the
    # same failure mode _SELF_TS_TABLES exists to prevent).
    v.upsert_pl_roles(conn, b, p, k, _pl_rows(conn, b, p, k))
    return sum(r.failed for r in res.values())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-push", action="store_true")
    args = ap.parse_args()

    overrides = json.loads(OVR.read_text(encoding="utf-8"))["overrides"]
    if not args.dry_run and not args.no_push:
        _guard_against_ci_writers()
        r2_storage.download_to(SNAP, GZ)
        with gzip.open(GZ, "rb") as s, open(DB, "wb") as d:
            shutil.copyfileobj(s, d)
        print(f"[ovr] pulled snapshot → {DB.stat().st_size/1e6:.1f} MB")

    parts = set()
    with sqlite3.connect(str(DB)) as conn:
        # The pulled snapshot predates any table added since it was written
        # (bank_audit_pl_roles, which _revalidate_partition writes below). All
        # CREATE ... IF NOT EXISTS, so this is idempotent.
        init_schema(conn)
        for o in overrides:
            print("  ", _apply_one(conn, o))
            parts.add((o["bank_ticker"], o["period"], o["kind"]))
        # re-validate each touched partition + bump every timestamp the narrow
        # --hours push keys off, so it re-ships EVERYTHING the D1 partition-clear
        # below removes. Without this the clear wipes the self-timestamped tables
        # (capital/liquidity/stages/…) from D1 — their extracted_at predates the
        # push window, so push_to_d1 won't restore them. The BS-family rides
        # bank_audit_extractions.extracted_at; validation rides validated_at
        # (refreshed inside _revalidate_partition).
        for b, p, k in sorted(parts):
            f = _revalidate_partition(conn, b, p, k)
            print(f"  revalidate {b} {p} {k}: {f} failures")
            conn.execute("UPDATE bank_audit_extractions SET extracted_at=CURRENT_TIMESTAMP "
                         "WHERE bank_ticker=? AND period=? AND kind=?", (b, p, k))
            for tbl in _SELF_TS_TABLES:
                if _has_col(conn, tbl, "extracted_at"):
                    conn.execute(f"UPDATE {tbl} SET extracted_at=CURRENT_TIMESTAMP "
                                 "WHERE bank_ticker=? AND period=? AND kind=?", (b, p, k))
        conn.commit()

    if args.dry_run or args.no_push:
        print("[ovr] local only — not pushing")
        return 0

    _ensure_d1_schema()
    stmts = []
    for tbl in AUDIT_TABLES:
        for b, p, k in parts:
            stmts.append(f"DELETE FROM {tbl} WHERE bank_ticker='{b}' AND period='{p}' AND kind='{k}';")
    sqlp = Path(tempfile.gettempdir()) / "d1_ovr_clear.sql"
    sqlp.write_text("\n".join(stmts) + "\n", encoding="utf-8")
    print(f"[ovr] clearing {len(parts)} partitions in D1")
    _retry_wrangler(sqlp, "D1 override clear")
    subprocess.run([sys.executable, str(REPO / "scripts" / "push_to_d1.py"),
                    "--db", str(DB), "--hours", "1", "--only-tables", ",".join(AUDIT_TABLES)], check=True)
    # Rebuild + push the coverage spine (bank_audit_coverage/expected/statement_types).
    # The /admin matrix reads its per-cell status from bank_audit_coverage — a rollup of
    # bank_audit_validation that's regenerated ONLY here and by the refresh-audit cron, not
    # by the table push above. Without this an override clears the validation failure but the
    # matrix keeps showing the stale error until the next cron. Runs before the snapshot so
    # the uploaded DB carries the fresh spine too.
    subprocess.run([sys.executable, str(REPO / "scripts" / "sync_audit_expected.py"),
                    "--db", str(DB), "--push"], check=True)
    with sqlite3.connect(str(DB)) as c:
        c.execute("VACUUM")
    with open(DB, "rb") as s, gzip.open(GZ, "wb", compresslevel=6) as d:
        shutil.copyfileobj(s, d)
    size = r2_storage.upload_file(GZ, SNAP)
    print(f"[ovr] uploaded snapshot ({size/1e6:.1f} MB)")
    print("[ovr] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
