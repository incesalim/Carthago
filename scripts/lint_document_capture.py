#!/usr/bin/env python
"""Strict per-table lint over a captured filing.

`view_document_capture.py` shows what was captured; this says what is WRONG with
it. The bar is that every table reads as the filing prints it: every row keeps
its whole label, every column is real and named where the filing names it, and
every note is attached to the table it qualifies and to the rows carrying its
marker.

Read-only against `data/bank_audit_capture.db`.

  python scripts/lint_document_capture.py --bank TSKB --period 2026Q1 --kind unconsolidated
  python scripts/lint_document_capture.py --all --summary
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

DEFAULT_DB = REPO / "data" / "bank_audit_capture.db"

# A label that opens a statement row — mirrors document_capture._ROW_OPENER.
# A row label that OPENS a row. Besides roman/numeric markers this includes the
# lettered sub-rows BRSA uses for capital buffers — "a) Sermaye koruma tamponu
# oranı (%)" is its own row, not a wrapped continuation, even though it starts
# with a lower-case letter.
_OPENER = re.compile(r"^(?:[IVXLCDM]+\.|\d+(?:\.\d+)*\.?|[a-zA-Z][).])(?:\s|$)")
_MARKER = re.compile(r"\((\*{1,6}|\d{1,2}|[a-zA-Z])\)")
# A period caption ("Önceki Dönem - 31 Aralık 2025") separates the current and
# prior halves of a table. It carries no figures BY DESIGN, so it is structure,
# not a lost row.
_PERIOD_ROW = re.compile(
    r"^\s*(cari\s+dönem|önceki\s+dönem|geçmiş\s+dönem|current\s+period|"
    r"prior\s+period|previous\s+period)\b", re.IGNORECASE)
# Sentence-shaped text: long and closing like prose.
_SENTENCE_MIN = 90
# A monetary amount: a thousands group. An index ("3") or a year ("2026") is
# not one, which is how a row identified by its first cell is told apart from
# a row whose label was lost.
_AMOUNT = re.compile(r"\d[.,]\d{3}")
# A date is not an amount, however much it looks like one: "30.09.2023"
# contains "0.092" and so matched _AMOUNT, which made every row of an FX-rate
# table — identified by its date, exactly as the filing prints it — read as a
# row that had lost its label.
_DATE_CELL = re.compile(r"^\d{1,2}[./]\d{1,2}[./]\d{2,4}$")


def _rows(conn, key):
    lines = conn.execute(
        "SELECT page,line_order,text,label,role,block_id,logical_row,markers_json "
        "FROM bank_audit_document_lines WHERE bank_ticker=? AND period=? AND kind=? "
        "ORDER BY page,line_order", key).fetchall()
    cells = conn.execute(
        "SELECT page,line_order,col_index,text,is_numeric FROM bank_audit_document_cells "
        "WHERE bank_ticker=? AND period=? AND kind=?", key).fetchall()
    blocks = conn.execute(
        "SELECT page,block_id,n_cols,heading,row_count,col_labels_json "
        "FROM bank_audit_document_blocks WHERE bank_ticker=? AND period=? AND kind=? "
        "ORDER BY page,block_id", key).fetchall()
    notes = conn.execute(
        "SELECT page,block_id,marker,text,linked_lines_json,note_order "
        "FROM bank_audit_document_notes WHERE bank_ticker=? AND period=? AND kind=? "
        "ORDER BY page,note_order", key).fetchall()
    try:
        unreadable = conn.execute(
            "SELECT page,text_layer FROM bank_audit_document_pages WHERE "
            "bank_ticker=? AND period=? AND kind=? AND text_layer!='text' "
            "ORDER BY page", key).fetchall()
    except sqlite3.OperationalError:
        unreadable = []      # ledger predates the text_layer column
    return lines, cells, blocks, notes, unreadable


def lint(conn, bank, period, kind) -> tuple[list[dict], dict]:
    key = (bank, period, kind)
    lines, cells, blocks, notes, unreadable = _rows(conn, key)
    if not lines:
        sys.exit(f"no capture stored for {bank} {period} {kind}")

    cell_at = defaultdict(list)
    for pg, lo, ci, txt, isnum in cells:
        cell_at[(pg, lo)].append((ci, txt, isnum))
    by_block = defaultdict(list)
    for pg, lo, txt, lab, role, bid, lr, mk in lines:
        if bid is not None:
            by_block[(pg, bid)].append((lo, txt, lab or "", lr, json.loads(mk or "[]")))
    # Markers printed on a page by something OTHER than a footnote line. A "(*)"
    # that appears only in the note itself has nothing to link to — the note
    # qualifies the whole table — so counting it made every such note look like
    # a missed link.
    page_markers = defaultdict(set)
    for pg, lo, txt, lab, role, bid, lr, mk in lines:
        if role == "footnote":
            continue
        page_markers[pg].update(m.group(1) for m in _MARKER.finditer(txt))

    findings: list[dict] = []
    tally: Counter = Counter()

    def add(pg, bid, code, detail):
        findings.append({"page": pg, "block": bid, "code": code, "detail": detail})
        tally[code] += 1

    for pg, bid, ncols, heading, row_count, col_labels_json in blocks:
        col_labels = json.loads(col_labels_json or "[]")
        blines = by_block[(pg, bid)]
        # group physical lines into printed rows
        groups = defaultdict(list)
        for lo, txt, lab, lr, mk in blines:
            groups[lr if lr is not None else -lo].append((lo, txt, lab, mk))
        colfill = Counter()
        for lo, txt, lab, lr, mk in blines:
            for ci, ctxt, isnum in cell_at[(pg, lo)]:
                if ci is not None:
                    colfill[ci] += 1

        # --- columns -------------------------------------------------------
        for c in range(ncols):
            # Only a column nothing lands in is wrong. A sparsely-filled column
            # is usually REAL — the footnote-reference column of a statement
            # carries a value on the handful of rows that cite a note (4/38 on
            # TSKB's balance sheet), and flagging that buried the true defects.
            if colfill[c] == 0:
                add(pg, bid, "dead_column", f"c{c} has no cell in any row")
            elif colfill[c] < 2:
                add(pg, bid, "weak_column",
                    f"c{c} filled in only {colfill[c]}/{row_count} rows")
        if ncols and not col_labels:
            add(pg, bid, "no_column_headers", f"{ncols} columns, none named")

        # --- rows ----------------------------------------------------------
        first_row = min(groups) if groups else None
        for lr in sorted(groups):
            parts = groups[lr]
            lab = " ".join(p[2] for p in parts if p[2]).strip()
            filled = sum(1 for lo, _t, _l, _m in parts
                         for ci, _c, _n in cell_at[(pg, lo)] if ci is not None)
            first_cell = next((t for lo, _t, _l, _m in parts
                               for ci, t, _n in cell_at[(pg, lo)] if ci == 0), "")
            # A row can be identified by its FIRST CELL rather than by text: the
            # associates tables number their rows "1, 2, 3", and a maturity
            # ladder labels them by year ("2026", "2027"). That is how the
            # filing prints them, not a lost label. Only a row whose first cell
            # is a real amount has genuinely lost its label.
            identified = bool(first_cell) and (
                _DATE_CELL.match(first_cell.strip()) or not _AMOUNT.search(first_cell))
            if filled and not lab and not identified:
                add(pg, bid, "row_without_label",
                    f"line {parts[0][0]} has {filled} cells, no label")
            elif lab[:1].islower() and len(parts) == 1 and not _OPENER.match(lab):
                add(pg, bid, "fragment_label",
                    f"line {parts[0][0]}: {lab[:70]!r} starts lower-case "
                    "(unmerged continuation?)")
            # A long label ending in a full stop is not enough. BRSA writes
            # capital-deduction rows as whole sentences — "Investments of Bank
            # to Banks that invest in Bank's additional equity … compatible
            # with Article 7." — and those are rows, with their figures in
            # columns beside them. What marks a row as narrative is that its
            # figures are INSIDE the sentence rather than beside it, which is
            # the same inline-versus-channel distinction the capture uses.
            # Measured over the holdout: 24 rows matched the length-and-period
            # test, of which 16 were real rows and only 8 were prose.
            if lab and len(lab) >= _SENTENCE_MIN and lab.rstrip().endswith((".", ":")):
                figs = [t for lo, _t, _l, _m in parts
                        for ci, t, _n in cell_at[(pg, lo)] if ci is not None]
                inside = sum(1 for t in figs if t and len(t) > 1 and t in lab)
                if figs and inside * 2 > len(figs):
                    add(pg, bid, "prose_row_in_table",
                        f"line {parts[0][0]}: {lab[:70]!r}…")
            # A cell-less FIRST row is the table's printed caption ("Balance
            # Sheet (Statement of Financial Position)…"), not a lost data row.
            # Every later cell-less row is a genuine problem.
            if not filled and lr != first_row and not _PERIOD_ROW.match(lab):
                add(pg, bid, "empty_row", f"line {parts[0][0]}: {lab[:60]!r}")

        # --- table shape ----------------------------------------------------
        # Two rows is a real table — BRSA prints two-row aging analyses
        # ("1-30 Gün / 31 Gün ve Üzeri / Toplam") as standalone disclosures.
        # Only a single-row "table" is suspect.
        if row_count < 2:
            add(pg, bid, "tiny_table", f"{row_count} rows")

    # --- notes --------------------------------------------------------------
    for pg, bid, marker, text, linked_json, note_order in notes:
        linked = json.loads(linked_json or "[]")
        # A note with no table is only wrong when the page HAS one. Narrative
        # pages (the CEO's message, the unit caption in §7) carry footnotes with
        # nothing to attach them to, and that is the filing's own structure.
        if bid is None and any(b[0] == pg for b in blocks):
            add(pg, None, "note_without_table", f"({marker}) {text[:60]}…")
        if marker and not linked and marker in page_markers[pg]:
            # the marker IS printed on this page but we linked nothing
            add(pg, bid, "note_link_missed",
                f"({marker}) printed on page but linked to no row")
        if text and len(text) < 25:
            add(pg, bid, "note_truncated", f"({marker}) {text!r}")

    # A page we could not read at all outranks every formatting defect below:
    # those describe a table we captured imperfectly, this one is a table that
    # is not here. Reported per page so the gap can be quantified, not guessed.
    for pg, layer in unreadable:
        add(pg, None, "unreadable_page",
            "glyphs are drawn outlines, not text — no table on this page was captured"
            if layer == "vector" else
            "content is an embedded image, not text — no table on this page was captured")

    stats = {
        "tables": len(blocks),
        "unreadable_pages": len(unreadable),
        "rows": sum(b[4] for b in blocks),
        "notes": len(notes),
        "findings": len(findings),
        "clean_tables": len(blocks) - len({(f["page"], f["block"]) for f in findings
                                           if f["block"] is not None}),
        "by_code": dict(tally),
    }
    return findings, stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--bank")
    ap.add_argument("--period")
    ap.add_argument("--kind", default="consolidated")
    ap.add_argument("--all", action="store_true", help="lint every captured partition")
    ap.add_argument("--summary", action="store_true", help="counts only")
    ap.add_argument("--code", help="show only this finding code")
    ap.add_argument("--limit", type=int, default=40)
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    targets = []
    if args.all:
        targets = conn.execute(
            "SELECT DISTINCT bank_ticker,period,kind FROM bank_audit_document_pages "
            "ORDER BY 1,2,3").fetchall()
    else:
        if not (args.bank and args.period):
            ap.error("--bank and --period required (or --all)")
        targets = [(args.bank.upper(), args.period.upper(), args.kind)]

    grand: Counter = Counter()
    for bank, period, kind in targets:
        findings, stats = lint(conn, bank, period, kind)
        grand.update(stats["by_code"])
        head = (f"{bank} {period} {kind}: {stats['tables']} tables, "
                f"{stats['rows']} rows, {stats['notes']} notes — "
                f"{stats['clean_tables']}/{stats['tables']} clean, "
                f"{stats['findings']} findings")
        if stats["unreadable_pages"]:
            head += f"  ⚠ {stats['unreadable_pages']} UNREADABLE pages"
        print(head)
        if not args.summary:
            shown = [f for f in findings if not args.code or f["code"] == args.code]
            for f in shown[: args.limit]:
                loc = f"p.{f['page']}" + (f" #{f['block']}" if f["block"] else "")
                print(f"   {loc:>10}  {f['code']:<20} {f['detail']}")
            if len(shown) > args.limit:
                print(f"   … {len(shown) - args.limit} more")
        if stats["by_code"]:
            print("   " + "  ".join(f"{k}={v}" for k, v in
                                    sorted(stats["by_code"].items(), key=lambda x: -x[1])))
        print()
    if len(targets) > 1:
        print("TOTAL " + "  ".join(f"{k}={v}" for k, v in
                                   sorted(grand.items(), key=lambda x: -x[1])))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
