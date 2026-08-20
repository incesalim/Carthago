"""The derived per-table lane: section attribution and lossless grids.

What these pin: the sectioning tiers (the filing's own contents when its
numbers validate, body banners when they do not, honest NULLs when neither
does), the §6/§7 role rule (title first, printed position only as fallback),
and the conservation contract — the derived lane may hold no fewer in-block
cells than the ledger it summarises, with "-" staying text and deductions
staying signed.
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

_spec = importlib.util.spec_from_file_location(
    "build_document_tables", REPO / "scripts" / "build_document_tables.py")
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)

KEY = ("TESTBK", "2026Q1", "consolidated")

LEDGER_DDL = """
CREATE TABLE bank_audit_document_pages (
  bank_ticker TEXT, period TEXT, kind TEXT, page INTEGER,
  text_layer TEXT NOT NULL DEFAULT 'text');
CREATE TABLE bank_audit_document_blocks (
  bank_ticker TEXT, period TEXT, kind TEXT, page INTEGER, block_id INTEGER,
  n_cols INTEGER, heading TEXT, row_count INTEGER, cell_count INTEGER,
  col_labels_json TEXT);
CREATE TABLE bank_audit_document_lines (
  bank_ticker TEXT, period TEXT, kind TEXT, page INTEGER, line_order INTEGER,
  text TEXT, label TEXT, role TEXT, block_id INTEGER, logical_row INTEGER,
  markers_json TEXT);
CREATE TABLE bank_audit_document_cells (
  bank_ticker TEXT, period TEXT, kind TEXT, page INTEGER, line_order INTEGER,
  cell_index INTEGER, col_index INTEGER, text TEXT, is_numeric INTEGER,
  value REAL);
CREATE TABLE bank_audit_document_notes (
  bank_ticker TEXT, period TEXT, kind TEXT, page INTEGER, note_order INTEGER,
  marker TEXT, text TEXT, block_id INTEGER, linked_lines_json TEXT);
"""

BIN_DECL = "(Para birimi: Bin Türk Lirası olarak ifade edilmiştir.)"


class Filing:
    """Assemble a synthetic capture ledger line by line."""

    def __init__(self):
        self.lines, self.cells, self.blocks, self.notes = [], [], [], []
        self._lo: dict[int, int] = {}

    def line(self, pg, text, label=None, role="paragraph", block_id=None,
             logical_row=None, markers=()):
        lo = self._lo.get(pg, 0) + 1
        self._lo[pg] = lo
        self.lines.append((*KEY, pg, lo, text, label, role, block_id,
                           logical_row, json.dumps(list(markers))))
        return lo

    def cell(self, pg, lo, ci, col, text, isn, value):
        self.cells.append((*KEY, pg, lo, ci, col, text, isn, value))

    def block(self, pg, bid, n_cols, heading=None, row_count=0, cell_count=0,
              col_labels=()):
        self.blocks.append((*KEY, pg, bid, n_cols, heading, row_count,
                            cell_count, json.dumps(list(col_labels))))

    def note(self, pg, order, marker, text, block_id, linked):
        self.notes.append((*KEY, pg, order, marker, text, block_id,
                           json.dumps(list(linked))))

    def db(self, tmp: Path) -> sqlite3.Connection:
        c = sqlite3.connect(tmp / "cap.db")
        c.executescript(LEDGER_DDL)
        pages = sorted({ln[3] for ln in self.lines})
        c.executemany("INSERT INTO bank_audit_document_pages VALUES (?,?,?,?,'text')",
                      [(*KEY, p) for p in pages])
        c.executemany("INSERT INTO bank_audit_document_lines VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      self.lines)
        c.executemany("INSERT INTO bank_audit_document_cells VALUES (?,?,?,?,?,?,?,?,?,?)",
                      self.cells)
        c.executemany("INSERT INTO bank_audit_document_blocks VALUES (?,?,?,?,?,?,?,?,?,?)",
                      self.blocks)
        c.executemany("INSERT INTO bank_audit_document_notes VALUES (?,?,?,?,?,?,?,?,?)",
                      self.notes)
        c.commit()
        return c


def _build(tmp: Path, filing: Filing) -> sqlite3.Connection:
    cap = filing.db(tmp)
    out = sqlite3.connect(tmp / "out.db")
    out.executescript(B.DDL)
    B.build_partition(cap, out, KEY)
    out.commit()
    return out


def _contents_filing() -> Filing:
    """A filing whose contents validates: folios on every page, 22 items."""
    f = Filing()
    f.line(1, BIN_DECL)
    # The contents: two sections, items carrying their printed folio. Body
    # folios below run at pdf = printed + 4.
    f.line(2, "SECTION ONE")
    f.line(2, "General Information About the Bank")
    for i in range(1, 12):
        f.line(2, f"{['I','II','III','IV','V','VI','VII','VIII','IX','X','XI'][i-1]}. "
                  f"General item {i} {i}")
    f.line(3, "SECTION TWO")
    f.line(3, "Unconsolidated Financial Statements")
    for i in range(1, 12):
        f.line(3, f"{['I','II','III','IV','V','VI','VII','VIII','IX','X','XI'][i-1]}. "
                  f"Statement item {i} {11 + i}")
    # Body: printed folios 1..26 on pdf pages 5..30.
    for printed in range(1, 27):
        pg = printed + 4
        f.line(pg, f"body text on printed page {printed}")
        f.line(pg, str(printed))
    return f


def test_contents_sectioning_items_and_roles(tmp_path):
    f = _contents_filing()
    # A table on pdf p20 = printed 16 -> Section 2 (starts printed 12 = pdf 16),
    # under statement item 5 (printed 16).
    lo = f.line(20, "Aktifler 1.000 2.000", label="Aktifler", role="data",
                block_id=1, logical_row=0)
    f.cell(20, lo, 0, 0, "1.000", 1, 1000.0)
    f.cell(20, lo, 1, 1, "2.000", 1, 2000.0)
    f.block(20, 1, 2, heading="Aktif tablosu", row_count=1, cell_count=2,
            col_labels=("TP", "YP"))
    out = _build(tmp_path, f)
    secs = out.execute(
        "SELECT section_no, role, source, item_count, table_count "
        "FROM bank_audit_document_sections ORDER BY section_no").fetchall()
    assert [s[0] for s in secs] == [1, 2]
    assert secs[0][1] == "general_info"          # from the declared title
    assert secs[1][1] == "financial_statements"
    assert all(s[2] == "contents" for s in secs)
    assert secs[0][3] == 11 and secs[1][3] == 11
    assert secs[1][4] == 1                        # the table counted under §2
    t = out.execute(
        "SELECT section_no, section_role, item_title, declared_unit "
        "FROM bank_audit_document_tables").fetchone()
    assert t[0] == 2 and t[1] == "financial_statements"
    assert t[2].startswith("Statement item 5")
    assert t[3] == "bin"


def test_banner_fallback_when_contents_does_not_validate(tmp_path):
    f = Filing()
    f.line(1, BIN_DECL)
    # A contents-LIKE page listing two banners: excluded from starts.
    f.line(2, "SECTION ONE")
    f.line(2, "SECTION TWO")
    # Body banners, one per page, titles following. Too few folios for the
    # contents model, so this filing exercises the fallback.
    f.line(4, "SECTION ONE")
    f.line(4, "General Information")
    f.line(9, "SECTION TWO")
    f.line(9, "Financial Statements")
    f.line(14, "SECTION THREE")
    f.line(14, "Some Untitled Thing")           # role falls back to position
    lo = f.line(10, "Krediler 5.000", label="Krediler", role="data",
                block_id=1, logical_row=0)
    f.cell(10, lo, 0, 0, "5.000", 1, 5000.0)
    f.block(10, 1, 1, row_count=1, cell_count=1)
    out = _build(tmp_path, f)
    secs = {r[0]: r for r in out.execute(
        "SELECT section_no, role, source, page_start "
        "FROM bank_audit_document_sections")}
    assert set(secs) == {1, 2, 3}
    assert all(r[2] == "banner" for r in secs.values())
    assert secs[1][3] == 4 and secs[2][3] == 9    # the two-banner page excluded
    assert secs[2][1] == "financial_statements"
    # 2026Q1 is interim: positional fallback for the title that says nothing.
    assert secs[3][1] == "accounting_policies"
    t = out.execute("SELECT section_no, item_no FROM bank_audit_document_tables"
                    ).fetchone()
    assert t == (2, None)                         # section yes, item unknown


def test_no_sectioning_keeps_tables_with_honest_nulls(tmp_path):
    f = Filing()
    f.line(1, "just a page with a table, no structure at all")
    lo = f.line(1, "Toplam 9.000", label="Toplam", role="data",
                block_id=1, logical_row=0)
    f.cell(1, lo, 0, 0, "9.000", 1, 9000.0)
    f.block(1, 1, 1, row_count=1, cell_count=1)
    out = _build(tmp_path, f)
    assert out.execute("SELECT COUNT(*) FROM bank_audit_document_sections"
                       ).fetchone()[0] == 0
    t = out.execute("SELECT section_no, section_role, heading "
                    "FROM bank_audit_document_tables").fetchone()
    assert t[0] is None and t[1] is None


def test_grid_is_lossless_and_keeps_the_ledger_semantics(tmp_path):
    """One table exercising every conservation rule at once: a wrapped label,
    a signed deduction, a disclosed-nothing dash, an unplaced text cell, and a
    column collision — the derived cells must equal the ledger's, exactly."""
    f = Filing()
    f.line(1, BIN_DECL)
    lo1 = f.line(2, "Beklenen Zarar", label="Beklenen Zarar", role="data",
                 block_id=1, logical_row=0, markers=("*",))
    lo2 = f.line(2, "Karşılıkları (-) (1.234) -", label="Karşılıkları (-)",
                 role="data", block_id=1, logical_row=0)
    f.cell(2, lo2, 0, 0, "(1.234)", 1, -1234.0)
    f.cell(2, lo2, 1, 1, "-", 0, None)
    lo3 = f.line(2, "Chairman 45 7.000 8.000", label="Board row", role="data",
                 block_id=1, logical_row=1)
    f.cell(2, lo3, 0, None, "Chairman", 0, None)   # no inferred column
    f.cell(2, lo3, 1, 0, "7.000", 1, 7000.0)
    f.cell(2, lo3, 2, 0, "8.000", 1, 8000.0)       # collides with 7.000
    f.block(2, 1, 2, heading="Test", row_count=2, cell_count=5,
            col_labels=("Cari", "Önceki"))
    f.note(2, 0, "*", "(*) qualifies the wrapped row", 1, [lo1])
    out = _build(tmp_path, f)
    grid = json.loads(out.execute(
        "SELECT grid_json FROM bank_audit_document_tables").fetchone()[0])
    assert len(grid) == 2                          # the wrap merged into one row
    assert grid[0]["label"] == "Beklenen Zarar Karşılıkları (-)"
    assert grid[0]["cells"] == [-1234.0, "-"]      # signed; dash stays text
    assert grid[0]["markers"] == ["*"]
    assert grid[1]["cells"] == [7000.0, None]
    unplaced = json.loads(out.execute(
        "SELECT unplaced_json FROM bank_audit_document_tables").fetchone()[0])
    assert {"r": 1, "t": "Chairman"} in unplaced   # text kept, not just numbers
    assert {"r": 1, "v": 8000.0} in unplaced       # the collision loser kept
    placed = sum(1 for row in grid for c in row["cells"] if c is not None)
    assert placed + len(unplaced) == 5             # == ledger in-block cells
    notes = json.loads(out.execute(
        "SELECT notes_json FROM bank_audit_document_tables").fetchone()[0])
    assert notes == [{"marker": "*", "text": "(*) qualifies the wrapped row",
                      "rows": [0]}]                # linked line -> grid row 0
