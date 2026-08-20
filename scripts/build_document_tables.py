#!/usr/bin/env python
"""Derive the queryable per-table lane from the full-document capture ledger.

The ledger (`data/bank_audit_capture.db`) is page-scoped evidence: 5.5M line
rows and 11.4M cell rows that prove what each filing printed, but answering
"show me every §4 currency-risk table across the fleet" from it means
re-assembling grids by hand every time. This builds that assembly ONCE, into
its own DB (`data/bank_audit_tables.db`, never the audit snapshot):

  bank_audit_document_sections   one row per section per filing — number, the
                                 filing's own declared title, `role` (the
                                 meaning: §6/§7 swap between annual and
                                 interim, so the number is never the join key),
                                 page span, table count, and `source` — how the
                                 sectioning was read ('contents' folio-validated
                                 / 'banner' body fallback / 'none')
  bank_audit_document_items      one row per contents item (Section 2 /
                                 "III. Konsolide gelir tablosu" / p.10) —
                                 only where the contents validated
  bank_audit_document_tables     one row per captured table: section context +
                                 the grid itself as JSON (logical rows with
                                 labels, cells aligned to the block's columns,
                                 markers), the notes qualifying it with the
                                 grid rows they attach to, and any in-table
                                 figures that matched no column (`unplaced` —
                                 kept so the derived lane loses nothing the
                                 ledger holds)

Grid cells carry the parsed VALUE for numeric cells (signed — a deduction
printed "(125.021.409)" is -125021409.0) and the raw text otherwise, "-"
included: a disclosed-nothing stays "-", never 0 and never dropped. Exact
glyphs remain the ledger's job; this lane is for querying.

Values are as PRINTED — not scaled to the canonical unit. `declared_unit` on
each table row (read by `units.regex_unit` off the captured front pages, the
same reading the reconcile trusts) is what a consumer multiplies through.

Read-only on the ledger; per-partition DELETE+INSERT on the output (local
writes are free — this DB never reaches D1 unless that decision is taken
explicitly).

  python scripts/build_document_tables.py                      # whole ledger
  python scripts/build_document_tables.py --bank AKBNK --period 2026Q1
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.audit_reports import units as U  # noqa: E402
from src.audit_reports.document_sections import (  # noqa: E402
    body_section_starts, document_contents)
from src.audit_reports.prose import (  # noqa: E402
    SECTION_ROLES_ANNUAL, SECTION_ROLES_INTERIM, role_from_title)

DEFAULT_CAPTURE = REPO / "data" / "bank_audit_capture.db"
DEFAULT_OUT = REPO / "data" / "bank_audit_tables.db"

DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_document_sections (
    bank_ticker TEXT NOT NULL,
    period      TEXT NOT NULL,
    kind        TEXT NOT NULL,
    section_no  INTEGER NOT NULL,
    title       TEXT,
    role        TEXT,
    page_start  INTEGER NOT NULL,
    page_end    INTEGER NOT NULL,
    item_count  INTEGER NOT NULL DEFAULT 0,
    table_count INTEGER NOT NULL DEFAULT 0,
    source      TEXT NOT NULL,
    PRIMARY KEY (bank_ticker, period, kind, section_no)
);
CREATE INDEX IF NOT EXISTS idx_doc_sections_role
  ON bank_audit_document_sections(role);

CREATE TABLE IF NOT EXISTS bank_audit_document_items (
    bank_ticker TEXT NOT NULL,
    period      TEXT NOT NULL,
    kind        TEXT NOT NULL,
    section_no  INTEGER NOT NULL,
    item_no     INTEGER NOT NULL,
    title       TEXT,
    page        INTEGER NOT NULL,
    PRIMARY KEY (bank_ticker, period, kind, section_no, item_no)
);

CREATE TABLE IF NOT EXISTS bank_audit_document_tables (
    bank_ticker   TEXT NOT NULL,
    period        TEXT NOT NULL,
    kind          TEXT NOT NULL,
    page          INTEGER NOT NULL,
    block_id      INTEGER NOT NULL,
    section_no    INTEGER,
    section_role  TEXT,
    item_no       INTEGER,
    item_title    TEXT,
    heading       TEXT,
    declared_unit TEXT,
    n_cols        INTEGER NOT NULL,
    row_count     INTEGER NOT NULL,
    cell_count    INTEGER NOT NULL,
    col_labels_json TEXT NOT NULL DEFAULT '[]',
    grid_json     TEXT NOT NULL,
    notes_json    TEXT NOT NULL DEFAULT '[]',
    unplaced_json TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (bank_ticker, period, kind, page, block_id)
);
CREATE INDEX IF NOT EXISTS idx_doc_tables_section
  ON bank_audit_document_tables(section_role);
"""

_TABLES = ("bank_audit_document_sections", "bank_audit_document_items",
           "bank_audit_document_tables")


def _declared_unit(cap: sqlite3.Connection, key: tuple) -> str | None:
    """The filing's reporting unit off the captured text — the reconcile's own
    reading (`regex_unit` wants the front pages untruncated; 25 are passed)."""
    by_page: dict[int, list[str]] = {}
    for pg, txt in cap.execute(
            "SELECT page,text FROM bank_audit_document_lines WHERE bank_ticker=? "
            "AND period=? AND kind=? AND page<=25 ORDER BY page,line_order", key):
        by_page.setdefault(pg, []).append(txt or "")
    return U.regex_unit([" ".join(v) for _pg, v in sorted(by_page.items())])


def _cell_value(text: str, is_numeric: int, value):
    if is_numeric and value is not None:
        return value
    return text


def build_partition(cap: sqlite3.Connection, out: sqlite3.Connection,
                    key: tuple) -> dict:
    bank, period, kind = key
    lines = cap.execute(
        "SELECT page,line_order,text,label,role,block_id,logical_row,markers_json "
        "FROM bank_audit_document_lines WHERE bank_ticker=? AND period=? AND kind=? "
        "ORDER BY page,line_order", key).fetchall()
    blocks = cap.execute(
        "SELECT page,block_id,n_cols,heading,row_count,cell_count,col_labels_json "
        "FROM bank_audit_document_blocks WHERE bank_ticker=? AND period=? AND kind=? "
        "ORDER BY page,block_id", key).fetchall()
    cells = cap.execute(
        "SELECT page,line_order,cell_index,col_index,text,is_numeric,value "
        "FROM bank_audit_document_cells WHERE bank_ticker=? AND period=? AND kind=? "
        "ORDER BY page,line_order,cell_index", key).fetchall()
    notes = cap.execute(
        "SELECT page,block_id,marker,text,linked_lines_json "
        "FROM bank_audit_document_notes WHERE bank_ticker=? AND period=? AND kind=? "
        "ORDER BY page,note_order", key).fetchall()

    max_page = max((ln[0] for ln in lines), default=0)

    # --- sectioning: contents first, body banners second, honest NULLs last --
    contents = document_contents(lines)
    items_rows: list[tuple] = []
    sec_start: dict[int, int] = {}
    sec_title: dict[int, str] = {}
    if contents:
        source = "contents"
        for pg, s, sname, i, title in contents:
            sec_start.setdefault(s, pg)
            if sname:
                sec_title.setdefault(s, sname)
            items_rows.append((bank, period, kind, s, i, title, pg))
    else:
        banner = body_section_starts(lines)
        if banner:
            source = "banner"
            for n, (pg, title) in banner.items():
                sec_start[n] = pg
                if title:
                    sec_title[n] = title
        else:
            source = "none"

    annual = period.upper().endswith("Q4")
    fallback = SECTION_ROLES_ANNUAL if annual else SECTION_ROLES_INTERIM
    sec_role = {n: (role_from_title(sec_title.get(n)) or fallback.get(n))
                for n in sec_start}
    bounds = sorted(sec_start.items(), key=lambda kv: (kv[1], kv[0]))

    def _section_of(pg: int) -> int | None:
        cur = None
        for n, start in bounds:
            if start <= pg:
                cur = n
            else:
                break
        return cur

    # Contents items in page order, for "which subject is this table under".
    item_seq = sorted(((pg, s, i, title) for pg, s, _sn, i, title in (
        (pg, s, sname, i, title) for pg, s, sname, i, title in (contents or []))),
        key=lambda t: t[0])

    def _item_of(pg: int) -> tuple[int | None, str | None]:
        cur: tuple[int | None, str | None] = (None, None)
        for ipg, _s, i, title in item_seq:
            if ipg <= pg:
                cur = (i, title)
            else:
                break
        return cur

    # --- grid assembly ------------------------------------------------------
    cells_at: dict[tuple[int, int], list] = defaultdict(list)
    for pg, lo, ci, col, txt, isn, val in cells:
        cells_at[(pg, lo)].append((ci, col, txt, isn, val))
    block_lines: dict[tuple[int, int], list] = defaultdict(list)
    # (page, line_order) -> (block_id, row-group key). The block_id HAS to ride
    # along: logical_row restarts per block, so a bare row key collides across
    # blocks on the same page — HALKB links its "(1)" marker across blocks, and
    # without the block check those lines mapped into the WRONG table's rows.
    lr_of: dict[tuple[int, int], tuple[int, object]] = {}
    for pg, lo, txt, lab, role, bid, lr, mk in lines:
        if bid is not None:
            block_lines[(pg, bid)].append((lo, lab or "", lr, mk))
            lr_of[(pg, lo)] = (bid, lr if lr is not None else -lo)

    unit = _declared_unit(cap, key)
    table_rows: list[tuple] = []
    sec_tables: dict[int, int] = defaultdict(int)
    for pg, bid, n_cols, heading, row_count, cell_count, col_labels_json in blocks:
        groups: dict[object, list] = defaultdict(list)
        for lo, lab, lr, mk in block_lines[(pg, bid)]:
            groups[lr if lr is not None else -lo].append((lo, lab, mk))
        grid, unplaced = [], []
        row_index_of: dict[object, int] = {}
        for gkey in sorted(groups, key=lambda g: min(x[0] for x in groups[g])):
            parts = groups[gkey]
            label = " ".join(p[1] for p in parts if p[1]).strip()
            markers = sorted({m for _lo, _lab, mk in parts
                              for m in json.loads(mk or "[]")})
            aligned: list = [None] * n_cols
            extra: list[dict] = []
            for lo, _lab, _mk in parts:
                for _ci, col, txt, isn, val in cells_at[(pg, lo)]:
                    v = _cell_value(txt, isn, val)
                    # EVERY in-block cell survives: one with no inferred column
                    # (the board-table text class), one whose column another
                    # cell of the same printed row already holds, and one past
                    # the grid all land in `unplaced` rather than vanishing —
                    # the derived lane must not hold fewer cells than the
                    # ledger it summarises.
                    if col is None or not 0 <= col < n_cols \
                            or aligned[col] is not None:
                        # Keyed by what the cell HOLDS, not by the ledger's
                        # numeric flag: a flagged-numeric cell whose value did
                        # not parse carries text, and a consumer reading "v"
                        # must be able to do arithmetic on it.
                        extra.append({"v": v} if isinstance(v, (int, float))
                                     else {"t": v})
                    else:
                        aligned[col] = v
            if not label and all(c is None for c in aligned) and not extra:
                continue
            idx = len(grid)
            row_index_of[gkey] = idx
            unplaced.extend({"r": idx, **x} for x in extra)
            row: dict = {"label": label, "cells": aligned}
            if markers:
                row["markers"] = markers
            grid.append(row)

        tnotes = []
        for npg, nbid, marker, text, linked_json in notes:
            if (npg, nbid) != (pg, bid):
                continue
            linked = json.loads(linked_json or "[]")
            rows, outside = set(), []
            for lo in linked:
                got = lr_of.get((pg, lo))
                if got is not None and got[0] == bid \
                        and got[1] in row_index_of:
                    rows.add(row_index_of[got[1]])
                else:
                    # The ledger links a note to EVERY line printing its
                    # marker — a heading above the table ("Risk Grubu (*)"),
                    # a period caption, another footnote citing it. Those are
                    # not grid rows, but dropping them made the derived lane
                    # lossy (13,461 notes read as link-less in the first
                    # cross-check). Kept as ledger line_orders, which is the
                    # lane's stated join key back to the evidence.
                    outside.append(lo)
            note: dict = {"marker": marker, "text": text, "rows": sorted(rows)}
            if outside:
                note["outside_lines"] = outside
            tnotes.append(note)

        s = _section_of(pg)
        item_no, item_title = _item_of(pg) if contents else (None, None)
        if s is not None:
            sec_tables[s] += 1
        table_rows.append((
            bank, period, kind, pg, bid, s, sec_role.get(s), item_no, item_title,
            heading, unit, n_cols, len(grid), cell_count,
            col_labels_json or "[]",
            json.dumps(grid, ensure_ascii=False, separators=(",", ":")),
            json.dumps(tnotes, ensure_ascii=False, separators=(",", ":")),
            json.dumps(unplaced, ensure_ascii=False, separators=(",", ":"))))

    sec_rows = []
    for pos, (n, start) in enumerate(bounds):
        end = bounds[pos + 1][1] - 1 if pos + 1 < len(bounds) else max_page
        sec_rows.append((bank, period, kind, n, sec_title.get(n) or None,
                         sec_role.get(n), start, max(start, end),
                         len({r[4] for r in items_rows if r[3] == n}),
                         sec_tables.get(n, 0), source))

    for t in _TABLES:
        out.execute(f"DELETE FROM {t} WHERE bank_ticker=? AND period=? AND kind=?",
                    key)
    out.executemany(
        "INSERT INTO bank_audit_document_sections VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        sec_rows)
    # OR IGNORE: a filing can index the same (section, item) twice — a repeated
    # contents line, or an item listed for both language halves. The first
    # occurrence (the earlier page) is the one kept; table attribution below
    # walks the full sequence either way.
    out.executemany(
        "INSERT OR IGNORE INTO bank_audit_document_items VALUES (?,?,?,?,?,?,?)",
        items_rows)
    out.executemany(
        "INSERT INTO bank_audit_document_tables VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", table_rows)
    return {"source": source, "sections": len(sec_rows), "items": len(items_rows),
            "tables": len(table_rows)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--capture-db", default=str(DEFAULT_CAPTURE))
    ap.add_argument("--out-db", default=str(DEFAULT_OUT))
    ap.add_argument("--bank")
    ap.add_argument("--period")
    ap.add_argument("--kind")
    args = ap.parse_args()

    if not Path(args.capture_db).exists():
        print(f"no capture ledger at {args.capture_db} — run "
              f"scripts/backfill_document_capture.py first", file=sys.stderr)
        return 2
    cap = sqlite3.connect(f"file:{args.capture_db}?mode=ro", uri=True)
    out = sqlite3.connect(args.out_db)
    out.executescript(DDL)

    where, params = [], []
    for col, val in (("bank_ticker", args.bank), ("period", args.period),
                     ("kind", args.kind)):
        if val:
            where.append(f"{col}=?")
            params.append(val.upper() if col != "kind" else val)
    keys = cap.execute(
        "SELECT DISTINCT bank_ticker,period,kind FROM bank_audit_document_pages"
        + (" WHERE " + " AND ".join(where) if where else "")
        + " ORDER BY 1,2,3", params).fetchall()
    if not keys:
        print("no captured partitions matched", file=sys.stderr)
        return 2

    by_source: dict[str, int] = defaultdict(int)
    tot_tables = 0
    for n, key in enumerate(keys, start=1):
        r = build_partition(cap, out, tuple(key))
        out.commit()
        by_source[r["source"]] += 1
        tot_tables += r["tables"]
        if n % 100 == 0 or n == len(keys):
            print(f"[{n}/{len(keys)}] {' '.join(key)}: {r['tables']} tables "
                  f"[{r['source']}]", flush=True)
    out.close()
    print(f"\n{len(keys)} partitions -> {tot_tables:,} table rows in {args.out_db}")
    print("sectioning: " + "  ".join(f"{k}={v}" for k, v in sorted(by_source.items())))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
