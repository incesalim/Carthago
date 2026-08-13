"""Persistence for full-document table capture.

Two destinations, deliberately separated by cost:

* **`data/bank_audit_capture.db`** — the raw ledger (pages, blocks, lines,
  cells, notes). 5.4M lines and 11.2M cells across the corpus (measured, not
  projected: the fleet run of 2026-08-13), so it gets its
  own SQLite file for the same reason `bank_audit_prose.db` does: every workflow
  downloads the main audit snapshot, and a ~1 GB attachment to it would tax runs
  that have nothing to do with capture.
* **`bank_audit_document_manifest`** in the MAIN audit DB — one compact row per
  filing (counts + hashes). That is the only thing that reaches D1, where
  written rows are the cost centre.

Plus an optional per-partition JSONL export under `data/audit_capture/`, so one
report's capture can be read, grepped and diffed without SQL.

Every write is content-compared first: an unchanged partition is not restamped,
because a restamp is a billable no-op the moment the manifest reaches D1.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .document_capture import DocumentCapture

# The raw ledger's own database. Never attached to the audit snapshot and never
# pushed to D1 — see the module docstring.
CAPTURE_DB = Path("data") / "bank_audit_capture.db"
EXPORT_DIR = Path("data") / "audit_capture"

LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_document_pages (
    bank_ticker TEXT NOT NULL,
    period      TEXT NOT NULL,
    kind        TEXT NOT NULL,
    page        INTEGER NOT NULL,
    rotation    INTEGER NOT NULL DEFAULT 0,
    width       REAL,
    height      REAL,
    line_count  INTEGER NOT NULL DEFAULT 0,
    cell_count  INTEGER NOT NULL DEFAULT 0,
    note_count  INTEGER NOT NULL DEFAULT 0,
    block_count INTEGER NOT NULL DEFAULT 0,
    -- 'text' | 'vector'. 'vector' means the page yielded no table and carries
    -- heavy path ink: its tables are drawn as glyph outlines, legible on screen
    -- and unreadable to any extractor. Typed prose on the same page is still
    -- captured — Fibabanka p.29 has real narrative above two drawn tables — so
    -- this marks the page's TABLES as lost, not its every word. Recorded per
    -- page so the gap is a stated fact, not a small row count nobody questions.
    text_layer  TEXT NOT NULL DEFAULT 'text',
    PRIMARY KEY (bank_ticker, period, kind, page)
);

-- One printed table. `col_x_json` is the inferred right-edge of each column, so
-- a consumer can re-derive the grid (or check ours) without re-reading the PDF.
CREATE TABLE IF NOT EXISTS bank_audit_document_blocks (
    bank_ticker TEXT NOT NULL,
    period      TEXT NOT NULL,
    kind        TEXT NOT NULL,
    page        INTEGER NOT NULL,
    block_id    INTEGER NOT NULL,
    first_line  INTEGER NOT NULL,
    last_line   INTEGER NOT NULL,
    n_cols      INTEGER NOT NULL DEFAULT 0,
    col_x_json  TEXT NOT NULL DEFAULT '[]',
    col_labels_json TEXT NOT NULL DEFAULT '[]',
    heading     TEXT,
    row_count   INTEGER NOT NULL DEFAULT 0,
    cell_count  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (bank_ticker, period, kind, page, block_id)
);

-- One physical text line. `logical_row` groups the lines of one PRINTED row
-- when a wrapped label pushed its figures onto a continuation line.
CREATE TABLE IF NOT EXISTS bank_audit_document_lines (
    bank_ticker   TEXT NOT NULL,
    period        TEXT NOT NULL,
    kind          TEXT NOT NULL,
    page          INTEGER NOT NULL,
    line_order    INTEGER NOT NULL,
    y             REAL,
    x0            REAL,
    x1            REAL,
    text          TEXT NOT NULL,
    label         TEXT,
    role          TEXT NOT NULL,
    block_id      INTEGER,
    logical_row   INTEGER,
    numeric_count INTEGER NOT NULL DEFAULT 0,
    markers_json  TEXT NOT NULL DEFAULT '[]',
    line_hash     TEXT NOT NULL,
    shape_hash    TEXT NOT NULL,
    PRIMARY KEY (bank_ticker, period, kind, page, line_order)
);

CREATE INDEX IF NOT EXISTS idx_doc_lines_role
  ON bank_audit_document_lines(role, block_id);

-- One printed cell. `col_index` is its column in the block's grid; NULL means
-- the cell sits outside any inferred column (a stray figure in prose).
CREATE TABLE IF NOT EXISTS bank_audit_document_cells (
    bank_ticker TEXT NOT NULL,
    period      TEXT NOT NULL,
    kind        TEXT NOT NULL,
    page        INTEGER NOT NULL,
    line_order  INTEGER NOT NULL,
    cell_index  INTEGER NOT NULL,
    col_index   INTEGER,
    x0          REAL,
    x1          REAL,
    text        TEXT NOT NULL,
    is_numeric  INTEGER NOT NULL DEFAULT 0,
    value       REAL,
    PRIMARY KEY (bank_ticker, period, kind, page, line_order, cell_index)
);

-- A footnote, and the rows it qualifies. `linked_lines_json` holds the
-- line_orders in the same block whose label printed this note's marker.
CREATE TABLE IF NOT EXISTS bank_audit_document_notes (
    bank_ticker       TEXT NOT NULL,
    period            TEXT NOT NULL,
    kind              TEXT NOT NULL,
    page              INTEGER NOT NULL,
    note_order        INTEGER NOT NULL,
    marker            TEXT,
    text              TEXT NOT NULL,
    block_id          INTEGER,
    linked_lines_json TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (bank_ticker, period, kind, page, note_order)
);
"""

# Lives in the MAIN audit DB (and from there in D1) — counts and hashes only.
MANIFEST_DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_document_manifest (
    bank_ticker       TEXT NOT NULL,
    period            TEXT NOT NULL,
    kind              TEXT NOT NULL,
    page_count        INTEGER NOT NULL DEFAULT 0,
    table_page_count  INTEGER NOT NULL DEFAULT 0,
    block_count       INTEGER NOT NULL DEFAULT 0,
    line_count        INTEGER NOT NULL DEFAULT 0,
    cell_count        INTEGER NOT NULL DEFAULT 0,
    note_count        INTEGER NOT NULL DEFAULT 0,
    linked_note_count INTEGER NOT NULL DEFAULT 0,
    -- Pages whose glyphs are drawn outlines, so nothing on them could be read.
    -- Without this a filing that lost its statements to a vector text layer is
    -- indistinguishable from one that simply prints fewer tables.
    vector_page_count INTEGER NOT NULL DEFAULT 0,
    content_hash      TEXT NOT NULL,
    shape_hash        TEXT NOT NULL,
    grid_hash         TEXT NOT NULL,
    capture_status    TEXT NOT NULL,
    captured_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind)
);

CREATE INDEX IF NOT EXISTS idx_doc_manifest_status
  ON bank_audit_document_manifest(capture_status);
"""

_LEDGER_TABLES = (
    "bank_audit_document_pages", "bank_audit_document_blocks",
    "bank_audit_document_lines", "bank_audit_document_cells",
    "bank_audit_document_notes",
)

_MANIFEST_COLUMNS = (
    "page_count", "table_page_count", "block_count", "line_count",
    "cell_count", "note_count", "linked_note_count", "vector_page_count",
    "content_hash", "shape_hash", "grid_hash", "capture_status",
)


def _add_missing_columns(conn: sqlite3.Connection, table: str,
                         columns: dict[str, str]) -> None:
    """Bring an already-created local table up to the current DDL.

    `CREATE TABLE IF NOT EXISTS` is a no-op on a database that predates a new
    column, so a ledger captured by an older build would fail every insert. The
    D1 side gets a real numbered migration; these two SQLite files are local
    scratch and can simply grow the column in place.
    """
    have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    if not have:
        return
    for name, decl in columns.items():
        if name not in have:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def init_ledger(conn: sqlite3.Connection) -> None:
    conn.executescript(LEDGER_DDL)
    _add_missing_columns(conn, "bank_audit_document_pages",
                         {"text_layer": "TEXT NOT NULL DEFAULT 'text'"})
    conn.commit()


def init_manifest(conn: sqlite3.Connection) -> None:
    conn.executescript(MANIFEST_DDL)
    _add_missing_columns(conn, "bank_audit_document_manifest",
                         {"vector_page_count": "INTEGER NOT NULL DEFAULT 0"})
    conn.commit()


def _rows(cap: DocumentCapture, bank: str, period: str, kind: str) -> dict[str, list[tuple]]:
    key = (bank, period, kind)
    pages, blocks, lines, cells, notes = [], [], [], [], []
    for p in cap.pages:
        pages.append((*key, p.page, p.rotation, p.width, p.height,
                      len(p.lines), len(p.cells), len(p.notes), len(p.blocks),
                      p.text_layer))
        for b in p.blocks:
            blocks.append((*key, p.page, b.block_id, b.first_line, b.last_line,
                           b.n_cols, json.dumps([round(x, 2) for x in b.col_x],
                                                separators=(",", ":")),
                           json.dumps(list(b.col_labels), ensure_ascii=False,
                                      separators=(",", ":")),
                           b.heading, b.row_count, b.cell_count))
        for ln in p.lines:
            lines.append((*key, p.page, ln.line_order, round(ln.y, 2),
                          round(ln.x0, 2), round(ln.x1, 2), ln.text, ln.label,
                          ln.role, ln.block_id, ln.logical_row, ln.numeric_count,
                          json.dumps(list(ln.markers), ensure_ascii=False,
                                     separators=(",", ":")),
                          ln.line_hash, ln.shape_hash))
        for c in p.cells:
            cells.append((*key, p.page, c.line_order, c.cell_index, c.col_index,
                          round(c.x0, 2), round(c.x1, 2), c.text,
                          int(c.is_numeric), c.value))
        for n in p.notes:
            notes.append((*key, p.page, n.note_order, n.marker, n.text, n.block_id,
                          json.dumps(list(n.linked_line_orders), separators=(",", ":"))))
    return {"bank_audit_document_pages": pages,
            "bank_audit_document_blocks": blocks,
            "bank_audit_document_lines": lines,
            "bank_audit_document_cells": cells,
            "bank_audit_document_notes": notes}


_INSERTS = {
    "bank_audit_document_pages":
        "INSERT INTO bank_audit_document_pages (bank_ticker,period,kind,page,rotation,"
        "width,height,line_count,cell_count,note_count,block_count,text_layer) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
    "bank_audit_document_blocks":
        "INSERT INTO bank_audit_document_blocks (bank_ticker,period,kind,page,block_id,"
        "first_line,last_line,n_cols,col_x_json,col_labels_json,heading,row_count,cell_count) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
    "bank_audit_document_lines":
        "INSERT INTO bank_audit_document_lines (bank_ticker,period,kind,page,line_order,"
        "y,x0,x1,text,label,role,block_id,logical_row,numeric_count,markers_json,"
        "line_hash,shape_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
    "bank_audit_document_cells":
        "INSERT INTO bank_audit_document_cells (bank_ticker,period,kind,page,line_order,"
        "cell_index,col_index,x0,x1,text,is_numeric,value) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
    "bank_audit_document_notes":
        "INSERT INTO bank_audit_document_notes (bank_ticker,period,kind,page,note_order,"
        "marker,text,block_id,linked_lines_json) VALUES (?,?,?,?,?,?,?,?,?)",
}


def manifest_values(cap: DocumentCapture) -> tuple:
    linked = sum(1 for p in cap.pages for n in p.notes if n.linked_line_orders)
    return (cap.page_count, cap.table_page_count, cap.block_count, cap.line_count,
            cap.cell_count, cap.note_count, linked, cap.vector_page_count,
            cap.content_hash(), cap.shape_hash(), cap.grid_hash(), cap.status)


def load_manifest(conn: sqlite3.Connection, bank: str, period: str,
                  kind: str) -> tuple | None:
    row = conn.execute(
        "SELECT " + ",".join(_MANIFEST_COLUMNS) +
        " FROM bank_audit_document_manifest WHERE bank_ticker=? AND period=? AND kind=?",
        (bank, period, kind)).fetchone()
    return tuple(row) if row else None


def upsert_manifest(conn: sqlite3.Connection, bank: str, period: str, kind: str,
                    cap: DocumentCapture) -> bool:
    """Write the compact manifest. Returns True only when a VALUE changed — an
    unchanged partition is left alone so a refresh cannot bill D1 for a no-op."""
    desired = manifest_values(cap)
    if load_manifest(conn, bank, period, kind) == desired:
        return False
    cols = ",".join(_MANIFEST_COLUMNS)
    ph = ",".join("?" for _ in _MANIFEST_COLUMNS)
    updates = ",".join(f"{c}=excluded.{c}" for c in _MANIFEST_COLUMNS)
    conn.execute(
        f"INSERT INTO bank_audit_document_manifest (bank_ticker,period,kind,{cols}) "
        f"VALUES (?,?,?,{ph}) "
        "ON CONFLICT(bank_ticker,period,kind) DO UPDATE SET "
        f"{updates},captured_at=CURRENT_TIMESTAMP",
        (bank, period, kind, *desired))
    return True


def upsert_ledger(conn: sqlite3.Connection, bank: str, period: str, kind: str,
                  cap: DocumentCapture) -> int:
    """Replace this partition's raw ledger. Returns rows written.

    Partition-scoped DELETE + INSERT rather than row-level diffing: the ledger
    is local-only, so its writes are free, and a whole-partition replace is the
    only shape that cannot leave orphaned lines behind when a filing is restated
    with fewer pages."""
    payload = _rows(cap, bank, period, kind)
    for table in _LEDGER_TABLES:
        conn.execute(
            f"DELETE FROM {table} WHERE bank_ticker=? AND period=? AND kind=?",
            (bank, period, kind))
    written = 0
    for table in _LEDGER_TABLES:
        rows = payload[table]
        if rows:
            conn.executemany(_INSERTS[table], rows)
            written += len(rows)
    return written


def export_jsonl(cap: DocumentCapture, bank: str, period: str, kind: str,
                 out_dir: Path | str = EXPORT_DIR, gzipped: bool = False) -> Path:
    """Write one partition's capture as JSONL: a manifest object, then one
    object per page with its blocks, notes and lines (cells nested in the line
    they belong to). Page-per-record keeps a table's row and its cells on a
    single greppable line while staying diffable across quarters.

    `gzipped` trades that grep-ability for ~85% less disk; the corpus export is
    ~2.5 GB plain. `zgrep`/`zcat` still read it.
    """
    import gzip

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"{bank}_{period}_{kind}.jsonl" + (".gz" if gzipped else "")
    path = out_dir / name
    mv = dict(zip(_MANIFEST_COLUMNS, manifest_values(cap)))
    opener = (lambda: gzip.open(path, "wt", encoding="utf-8", compresslevel=6)) \
        if gzipped else (lambda: path.open("w", encoding="utf-8"))
    with opener() as fh:
        fh.write(json.dumps({"type": "manifest", "bank_ticker": bank,
                             "period": period, "kind": kind,
                             "pdf": Path(cap.pdf_path).name, **mv},
                            ensure_ascii=False) + "\n")
        for p in cap.pages:
            cells_by_line: dict[int, list[dict]] = {}
            for c in p.cells:
                cells_by_line.setdefault(c.line_order, []).append({
                    "i": c.cell_index, "col": c.col_index, "text": c.text,
                    "value": c.value, "numeric": c.is_numeric,
                    "x0": round(c.x0, 2), "x1": round(c.x1, 2)})
            fh.write(json.dumps({
                "type": "page", "page": p.page, "rotation": p.rotation,
                "blocks": [{"block_id": b.block_id, "heading": b.heading,
                            "first_line": b.first_line, "last_line": b.last_line,
                            "n_cols": b.n_cols, "rows": b.row_count,
                            "cells": b.cell_count, "col_labels": list(b.col_labels),
                            "col_x": [round(x, 2) for x in b.col_x]}
                           for b in p.blocks],
                "notes": [{"note_order": n.note_order, "marker": n.marker,
                           "block_id": n.block_id, "text": n.text,
                           "linked_lines": list(n.linked_line_orders)}
                          for n in p.notes],
                "lines": [{"line_order": ln.line_order, "role": ln.role,
                           "block_id": ln.block_id, "logical_row": ln.logical_row,
                           "label": ln.label, "text": ln.text,
                           "markers": list(ln.markers),
                           "cells": cells_by_line.get(ln.line_order, [])}
                          for ln in p.lines],
            }, ensure_ascii=False) + "\n")
    return path
