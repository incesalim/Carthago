"""Full-document capture: geometry, roles, note linking and persistence.

The PDF-shaped assertions run against a synthetic document built with fitz, so
the suite needs no corpus file and stays deterministic in CI.
"""
from __future__ import annotations

import sqlite3

import pytest

from src.audit_reports import document_store as store
from src.audit_reports.document_capture import (
    ROLE_DATA,
    ROLE_FOOTNOTE,
    ROLE_PARAGRAPH,
    capture_document,
    parse_cell,
)

fitz = pytest.importorskip("fitz")


def _write_pdf(path, lines, rotate=0):
    """Render `lines` as [(x, y, text), …] onto one page."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    for x, y, text in lines:
        page.insert_text((x, y), text, fontsize=9)
    if rotate:
        page.set_rotation(rotate)
    doc.save(str(path))
    doc.close()


# A two-column table: a heading, four data rows (one carrying a marker), and a
# footnote that qualifies it.
_TABLE = [
    (60, 100, "Toplam Ozkaynak Kalemleri"),
    (60, 120, "Cekirdek Sermaye (*)"), (300, 120, "444.145"), (420, 120, "439.429"),
    (60, 135, "Katki Sermaye"), (300, 135, "147.663"), (420, 135, "138.736"),
    (60, 150, "Toplam Sermaye"), (300, 150, "591.806"), (420, 150, "578.162"),
    (60, 165, "Toplam Risk Agirlikli"), (300, 165, "3.154.771"), (420, 165, "2.645.600"),
    (60, 200, "(*) Cekirdek sermaye tutari indirimler sonrasi gosterilmistir."),
]


@pytest.fixture
def table_pdf(tmp_path):
    p = tmp_path / "AKBNK_2026Q1_consolidated.pdf"
    _write_pdf(p, _TABLE)
    return p


def test_detects_one_block_with_two_value_columns(table_pdf):
    cap = capture_document(table_pdf)
    page = cap.pages[0]
    assert len(page.blocks) == 1
    assert page.blocks[0].n_cols == 2
    assert page.blocks[0].row_count == 4


def test_every_printed_cell_is_captured(table_pdf):
    cap = capture_document(table_pdf)
    texts = {c.text for c in cap.pages[0].cells}
    assert {"444.145", "439.429", "147.663", "138.736",
            "591.806", "578.162", "3.154.771", "2.645.600"} <= texts
    # 4 rows x 2 columns, every one assigned to a column
    data_cells = [c for c in cap.pages[0].cells if c.col_index is not None]
    assert len(data_cells) == 8
    assert {c.col_index for c in data_cells} == {0, 1}


def test_footnote_is_a_note_not_a_row_and_links_to_its_marker(table_pdf):
    cap = capture_document(table_pdf)
    page = cap.pages[0]
    assert [n.marker for n in page.notes] == ["*"]
    note = page.notes[0]
    assert "indirimler sonrasi" in note.text
    linked = {ln.line_order for ln in page.lines if ln.line_order in note.linked_line_orders}
    assert linked, "the (*) note must link to the row printing (*)"
    labels = [ln.label for ln in page.lines if ln.line_order in linked]
    assert any("Cekirdek Sermaye" in x for x in labels)
    # and the footnote line itself is not counted as table data
    roles = {ln.role for ln in page.lines if "indirimler sonrasi" in ln.text}
    assert roles == {ROLE_FOOTNOTE}


def test_data_rows_carry_the_data_role(table_pdf):
    cap = capture_document(table_pdf)
    data = [ln for ln in cap.pages[0].lines if ln.role == ROLE_DATA]
    assert len(data) == 4


def _write_landscape_pdf(path, lines, width=842.0):
    """Render `lines` given in DISPLAY coordinates onto a /Rotate 90 page.

    Real landscape filings (the GARAN/AKBNK equity statement) author their
    content so that, in the page's UNROTATED space, one visual row is a
    constant-x vertical run — the /Rotate then stands it upright for the reader.
    A test that instead draws upright text and rotates the page afterwards
    produces genuinely sideways text and proves nothing about those filings, so
    the display→unrotated inverse of the rotation matrix is applied here:
    rotation_matrix maps (x, y) -> (width - y, x), hence the inverse below.
    """
    unrotated = [(y_disp, width - x_disp, text) for x_disp, y_disp, text in lines]
    doc = fitz.open()
    # Authored PORTRAIT so that /Rotate 90 DISPLAYS it landscape — the shape the
    # real filings have (mediabox 595x842, displayed rect 842x595). `width` is
    # the displayed width and so the constant in the rotation matrix.
    page = doc.new_page(width=595, height=int(width))
    for x, y, text in unrotated:
        # rotate=90 so each string ADVANCES along the display's x-axis. Drawn
        # upright it would advance down the display instead, interleaving
        # neighbouring rows — an artefact of the fixture, not of the parser.
        page.insert_text((x, y), text, fontsize=9, rotate=90)
    page.set_rotation(90)
    doc.save(str(path))
    doc.close()


def test_rotated_page_is_read_in_display_space(tmp_path):
    """A /Rotate 90 page must yield the SAME rows as its upright twin — the
    landscape equity statement (17 value columns) depends on this, and naive
    y-bucketing of unrotated words turns it into noise."""
    upright = tmp_path / "A_2026Q1_consolidated.pdf"
    rotated = tmp_path / "B_2026Q1_consolidated.pdf"
    _write_pdf(upright, _TABLE)
    _write_landscape_pdf(rotated, _TABLE)
    a, b = capture_document(upright), capture_document(rotated)
    assert b.pages[0].rotation == 90
    assert b.pages[0].blocks, "rotated page lost its table"
    assert b.pages[0].blocks[0].n_cols == a.pages[0].blocks[0].n_cols == 2
    assert b.pages[0].blocks[0].row_count == a.pages[0].blocks[0].row_count
    assert b.cell_count == a.cell_count
    # the note must survive rotation too, still bound to its marker row
    assert [n.marker for n in b.pages[0].notes] == ["*"]
    assert b.pages[0].notes[0].linked_line_orders


def test_pruning_a_phantom_column_costs_the_real_ones_nothing(tmp_path):
    """Dropping a phantom column must not unplace a single real figure.

    A column ONE row reaches is real often enough to keep by default — a
    footnote-reference column carries a value on 4 of 38 rows on TSKB's balance
    sheet — so the prune fires only on evidence that the cell was never a cell.
    Here the figure inside "Less than 1 Year" goes and all eight amounts stay.
    """
    p = tmp_path / "GARAN_2026Q1_consolidated.pdf"
    amounts = ["1,204,556", "2,305,118", "3,406,229", "4,507,330",
               "5,608,441", "6,709,552", "9,847,996", "6,172,133"]
    lines, k = [], 0
    for n, label in enumerate(["Less than 1 Year", "Between 1-5 Years",
                               "Longer than 5 Years", "Total"]):
        y = 100 + n * 15
        lines += [(60, y, label), (300, y, amounts[k]), (430, y, amounts[k + 1])]
        k += 2
    _write_pdf(p, lines)
    page = capture_document(p).pages[0]
    placed = {c.text for c in page.cells if c.col_index is not None}
    assert set(amounts) <= placed, f"real amounts unplaced: {set(amounts) - placed}"
    assert page.blocks[0].n_cols == 2, (
        f"phantom column survived: n_cols={page.blocks[0].n_cols}")
    # the label's own figure is still CAPTURED, just not in a column
    assert any(c.text == "1" and c.col_index is None for c in page.cells)


def test_a_figure_inside_a_row_label_does_not_mint_a_column(tmp_path):
    """A column no row fills is not a column.

    Maturity labels carry bare figures — "Less than 1 Year", "Longer than 5
    Years" — which cluster into an edge in the row-label region and mint a
    leading column that nothing can reach. Refusing the edge outright was
    measured and cost 9 blocks and 1,563 placed cells, because a narrow table
    sets adjacent figures closer than a channel; the empty column is dropped
    after cells are assigned instead, where nothing can be lost.
    """
    p = tmp_path / "GARAN_2026Q1_consolidated.pdf"
    _write_pdf(p, [
        (60, 100, "Less than 1 Year"), (300, 100, "3,055,202"), (430, 100, "1,893,439"),
        (60, 115, "Between 1-5 Years"), (300, 115, "5,103,480"), (430, 115, "3,221,992"),
        (60, 130, "Longer than 5 Years"), (300, 130, "1,689,314"), (430, 130, "1,056,702"),
        (60, 145, "Total"), (300, 145, "9,847,996"), (430, 145, "6,172,133"),
    ])
    page = capture_document(p).pages[0]
    block = page.blocks[0]
    filled = {c.col_index for c in page.cells if c.col_index is not None}
    assert filled == set(range(block.n_cols)), (
        f"column with no cells: n_cols={block.n_cols} filled={sorted(filled)}")


def test_a_header_belongs_to_its_own_table_not_the_one_above(tmp_path):
    """A header on the far side of ANOTHER table must not be mapped in.

    Garanti stacks four tables on one page, so the reach-back for a header
    finds the previous table's ("Current Period Prior Period" over four
    columns) as well as this table's own two-column one. Mapped together they
    produce fragments the plausibility filter discards, taking the correct
    header with them — and where both tables share a header, the result was a
    doubled "Current Period Current Period".
    """
    p = tmp_path / "GARAN_2026Q1_consolidated.pdf"
    _write_pdf(p, [
        # first table: four columns, its own header
        (60, 100, "Current Period"), (300, 100, "TL"), (370, 100, "FC"),
        (440, 100, "Prior Period"), (510, 100, "TL"),
        (60, 115, "Collateralised Assets"),
        (300, 115, "16,744"), (370, 115, "13,625"),
        (440, 115, "12,840"), (510, 115, "9,716"),
        (60, 130, "Repurchase Agreements"),
        (300, 130, "3,239"), (370, 130, "37,719"),
        (440, 130, "9,269"), (510, 130, "41,621"),
        # second table: two columns, its own header
        (60, 175, "Current Period"), (470, 175, "Prior Period"),
        (60, 190, "Debt Securities"), (430, 190, "334,377"), (540, 190, "173,139"),
        (60, 205, "Quoted at Exchange"), (430, 205, "334,377"), (540, 205, "173,139"),
        (60, 220, "Unquoted"), (430, 220, "1,204"), (540, 220, "2,305"),
    ])
    blocks = capture_document(p).pages[0].blocks
    last = blocks[-1]
    assert last.col_labels and any(last.col_labels), "header lost to the table above"
    joined = " ".join(last.col_labels)
    assert joined.count("Current Period") <= 1, f"doubled header: {last.col_labels}"


def test_a_label_may_wrap_over_a_line_carrying_no_figures(tmp_path):
    """A row's label can span three lines with the figures only on the last.

    Albaraka's exposure classes print "3 Receivables from" (the row number
    alone) / "administrative units and non-" / "commercial enterprises 68.234
    …". The column-completion walk stopped at the middle line because it
    carries no figures, leaving the head as a labelled row with none and the
    figures under a fragment. Only a LOWER-CASE line is stepped over — an
    upper-case one is the next row, not this row's continuation.
    """
    p = tmp_path / "ALBRK_2023Q4_consolidated.pdf"
    _write_pdf(p, [
        (60, 100, "3 Receivables from"),
        (60, 112, "administrative units and non-"),
        (60, 124, "commercial enterprises"),
        (300, 124, "68.234"), (430, 124, "26.711"),
        (60, 145, "4 Receivables from banks"),
        (300, 145, "7.113"), (430, 145, "1.274"),
        (60, 165, "5 Retail receivables"),
        (300, 165, "9.315"), (430, 165, "8.511"),
    ])
    page = capture_document(p).pages[0]
    groups = {}
    for ln in page.lines:
        if ln.block_id is not None:
            groups.setdefault(ln.logical_row, []).append(ln.label)
    joined = {" ".join(x for x in v if x).strip() for v in groups.values()}
    assert ("3 Receivables from administrative units and non- "
            "commercial enterprises") in joined, joined
    assert "4 Receivables from banks" in joined, joined


def test_the_first_row_of_a_table_may_also_wrap(tmp_path):
    """Row 1 wraps like every other row and must merge like every other row.

    A merge is barred from starting on a block's first line, because that line
    is usually the column header. BRSA risk-class tables open straight onto a
    wrapped data row — "1 Receivables from central" / "governments or central
    banks 34.833.367 …" — and because the row number is itself a cell, the
    cell-less wrap branch never sees the line either. Row 1 of every such table
    lost half its label while rows 2..n merged correctly. No header opens with
    a row marker AND is followed by a lower-case resume.
    """
    p = tmp_path / "ALBRK_2023Q4_consolidated.pdf"
    _write_pdf(p, [
        (60, 100, "1 Receivables from central"),
        (60, 112, "governments or central banks"),
        (300, 112, "34.833.367"), (430, 112, "480"),
        (60, 130, "2 Receivables from regional or"),
        (60, 142, "local governments"),
        (300, 142, "97.791"), (430, 142, "2.672"),
        (60, 160, "3 Receivables from banks"),
        (300, 160, "12.345"), (430, 160, "678"),
    ])
    page = capture_document(p).pages[0]
    groups = {}
    for ln in page.lines:
        if ln.block_id is not None:
            groups.setdefault(ln.logical_row, []).append(ln.label)
    joined = {" ".join(x for x in v if x).strip() for v in groups.values()}
    assert "1 Receivables from central governments or central banks" in joined, joined
    assert "2 Receivables from regional or local governments" in joined, joined


def test_a_label_printed_above_its_figures_binds_to_its_own_row(tmp_path):
    """A label on its own line belongs to the figures BELOW it, not above.

    Garanti's landscape deposit table prints every long label on its own line —
    "Public Sector Deposits" / figures / "Commercial Deposits" / figures — and
    the tail-binding rule attached each label to the row above it, so every
    row carried the previous row's name and the last figures had none. The
    genuine three-line wrap (label head / figures / label tail) must still
    bind, and the two are told apart by what follows: a new label is followed
    by its own figures, a tail is not.
    """
    p = tmp_path / "GARAN_2026Q1_consolidated.pdf"
    rows = [("Public Sector Deposits", "10,471,715", "13,745,165"),
            ("Commercial Deposits", "96,333,623", "698,788,306"),
            ("Precious Metal Deposits", "2,976,956", "50,450,946")]
    lines, y = [], 100
    for label, a, b in rows:
        lines.append((60, y, label))
        lines += [(300, y + 12, a), (430, y + 12, b)]
        y += 28
    _write_pdf(p, lines)
    page = capture_document(p).pages[0]
    by_row = {}
    for ln in page.lines:
        if ln.block_id is not None:
            by_row.setdefault(ln.logical_row, []).append(ln)
    named = {" ".join(x.label for x in v if x.label).strip() for v in by_row.values()}
    assert "Commercial Deposits" in named
    for v in by_row.values():
        labels = [x.label for x in v if x.label]
        assert len(labels) <= 1, f"two labels bound to one row: {labels}"


def test_a_note_on_a_tableless_page_still_links_to_what_it_marks(tmp_path):
    """A footnote that owns no table can still qualify a printed line.

    Every link was gated on the note having a block, so Garanti's ratings pages
    — "(*) Latest date in risk ratings or outlooks" under "MOODY'S (October
    2025) (*)", with no table anywhere on the page — recorded the relationship
    nowhere. Only star markers qualify: "(1)" and "(i)" are also legal
    citations, and linking those would invent a reference the filing never
    makes.
    """
    p = tmp_path / "GARAN_2026Q1_consolidated.pdf"
    _write_pdf(p, [
        (60, 100, "MOODY'S (October 2025) (*)"),
        (60, 115, "Long term rating Ba3"),
        (60, 140, "(*) Latest date in risk ratings or outlooks"),
    ])
    notes = capture_document(p).pages[0].notes
    star = next(n for n in notes if n.marker == "*")
    assert star.linked_line_orders, "note linked to nothing"
    assert star.block_id is None, "fixture should have no table"


def test_a_citation_in_prose_is_not_linked_as_a_footnote(tmp_path):
    """The control: "(1)" is how a filing cites a regulation, not only how it
    marks a footnote. Halkbank prints "Clause 2, Paragraph (1) and (2) of the
    Regulation" as ordinary text, so a numeric marker on a table-less page must
    stay unlinked rather than point at a coincidence."""
    p = tmp_path / "HALKB_2025Q4_consolidated.pdf"
    _write_pdf(p, [
        (60, 100, "Clause 2, Paragraph (1) and (2) of the Regulation"),
        (60, 140, "(1) Information about total consolidated equity items"),
    ])
    for n in capture_document(p).pages[0].notes:
        if n.marker == "1" and n.block_id is None:
            assert not n.linked_line_orders, "citation linked as a footnote"


def test_sideways_margin_text_is_kept_out_of_the_rows_it_crosses(tmp_path):
    """Rotated marginal text must not be dealt across the table's rows.

    Garanti prints "The accompanying notes are an integral part…" rotated 90°
    down the left margin of its landscape equity statement. Each word sits at
    its own y, so y-bucketing handed one to each row and the labels came out
    "accompanying VII. Capital Reserves…", "notes XI. Profit Distribution".
    The text is not discarded — Albaraka names the row groups of its ratings
    table the same way — it becomes its own line, read in its own direction.
    """
    p = tmp_path / "GARAN_2026Q1_consolidated.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    for n, (label, a, b) in enumerate([("VI. Capital Increase", "1.204", "2.305"),
                                       ("XI. Profit Distribution", "3.406", "4.507"),
                                       ("11.2 Transfers to Reserves", "5.608", "6.709"),
                                       ("11.3 Others", "7.810", "8.911")]):
        y = 120 + n * 20
        page.insert_text((60, y), label, fontsize=9)
        page.insert_text((300, y), a, fontsize=9)
        page.insert_text((420, y), b, fontsize=9)
    # rotate=90 makes each word advance DOWN the page at a constant x
    for n, word in enumerate(["The", "accompanying", "notes", "are", "integral"]):
        page.insert_text((30, 110 + n * 20), word, fontsize=9, rotate=90)
    doc.save(str(p))
    doc.close()

    cap = capture_document(p)
    page0 = cap.pages[0]
    rows = [ln for ln in page0.lines if ln.block_id is not None]
    assert rows, "table lost"
    for ln in rows:
        assert "accompanying" not in ln.label, f"margin text in row label: {ln.label!r}"
        assert "notes" not in ln.label
    assert any("accompanying" in ln.text for ln in page0.lines), "margin text discarded"


def test_a_numeric_header_row_still_names_its_columns(tmp_path):
    """A header can be numeric by nature and must not read as a data row.

    Halkbank names its risk-weight columns "0% 20% 50% 100%", each printed
    directly over the column it labels. The header test asked only whether a
    line had a figure aligned to a column — which this header does, by design —
    so the table rendered as "c0 c1 c2" with its header one line above.
    """
    p = tmp_path / "HALKB_2025Q4_consolidated.pdf"
    _write_pdf(p, [
        (60, 100, "Risk weight"), (300, 100, "0%"), (400, 100, "20%"), (500, 100, "50%"),
        (60, 115, "Claims on sovereigns"), (300, 115, "144.379"),
        (400, 115, "12.004"), (500, 115, "9.115"),
        (60, 130, "Claims on banks"), (300, 130, "233.870"),
        (400, 130, "18.221"), (500, 130, "7.443"),
        (60, 145, "Claims on corporates"), (300, 145, "512.006"),
        (400, 145, "44.190"), (500, 145, "1.228"),
    ])
    labels = capture_document(p).pages[0].blocks[0].col_labels
    assert any("%" in x for x in labels), f"numeric header lost: {labels}"


def test_a_text_column_is_captured_not_swallowed_into_the_label(tmp_path):
    """Columns holding TEXT must be captured too.

    Garanti's board table prints "Süleyman Sözen | Chairman | 29.05.1997 |
    University | 45 years" — five columns, every boundary a wide channel, of
    which only two hold figures. Clustering values alone saw two columns and
    dropped "Chairman" and "University" entirely; they survived only by being
    swallowed into an over-long row label, which read as the whole line.
    """
    p = tmp_path / "GARAN_2026Q1_consolidated.pdf"
    rows = [("Suleyman Sozen", "Chairman", "29.05.1997", "University", "45 years"),
            ("Jorge Saenz Carranza", "Deputy Chairman", "24.03.2016", "University", "32 years"),
            ("Mahmut Akten", "Member and CEO", "23.08.2024", "Master", "27 years"),
            ("Sait Ergun Ozen", "Member", "14.05.2003", "University", "39 years")]
    lines = []
    for n, (name, role, date, edu, exp) in enumerate(rows):
        y = 100 + n * 15
        lines += [(60, y, name), (200, y, role), (330, y, date),
                  (420, y, edu), (500, y, exp)]
    _write_pdf(p, lines)
    cap = capture_document(p)
    page = cap.pages[0]
    row = next(ln for ln in page.lines if "Sozen" in ln.text)
    assert row.label == "Suleyman Sozen", "label must be the first field only"
    texts = [c.text for c in page.cells if c.line_order == row.line_order]
    assert "Chairman" in texts and "University" in texts, "text columns dropped"
    assert "29.05.1997" in texts


def test_narrative_with_regular_dates_is_not_minted_into_a_table(tmp_path):
    """Turkish history prose must not become a table of days and years.

    Sentences opening "4 Mart 2003 tarihinde…" put the day at the left margin
    and the year at a near-constant x, because the month names are similar
    widths. That clusters into two clean columns and passes every other test —
    the run foots and its figures are substantial — so Fibabanka's corporate
    history was captured as a 4x2 grid of date fragments.
    """
    p = tmp_path / "FIBA_2022Q1_unconsolidated.pdf"
    _write_pdf(p, [
        (60, 100, "4 Mart 2003 tarihinde yapilan Genel Kurul toplantisinda unvani"),
        (60, 115, "28 Kasim 2006 tarihinde yapilan Olaganustu Genel Kurul kararindan"),
        (60, 130, "27 Aralik 2010 tarihi itibariyla Banka'nin bir istiraki olan Credit"),
        (60, 145, "25 Nisan 2011 tarihinde yapilan Olaganustu Genel Kurul kararinda"),
    ])
    assert capture_document(p).block_count == 0


def test_a_table_whose_every_figure_carries_a_unit_survives(tmp_path):
    """The control that a naive version of the rule failed.

    Akbank's FX valuation table prints "44,3961 TL   50,9294 TL" on every row,
    so judging a figure by the word that FOLLOWS it marks all of them as prose
    and deletes a real table. What separates them is the channel to the figure's
    LEFT — 88-237pt here against a 2-3pt word space in a sentence.
    """
    p = tmp_path / "AKBNK_2026Q1_consolidated.pdf"
    _write_pdf(p, [
        (60, 100, "Bilanco degerleme kuru"), (300, 100, "44,3961 TL"), (420, 100, "50,9294 TL"),
        (60, 115, "1. Gunun Cari Doviz Alis Kuru"), (300, 115, "44,3841 TL"), (420, 115, "51,0236 TL"),
        (60, 130, "2. Gunun Cari Doviz Alis Kuru"), (300, 130, "44,2887 TL"), (420, 130, "51,0150 TL"),
        (60, 145, "3. Gunun Cari Doviz Alis Kuru"), (300, 145, "44,1998 TL"), (420, 145, "50,9871 TL"),
    ])
    cap = capture_document(p)
    assert cap.block_count == 1, "real table deleted as prose"
    assert cap.pages[0].blocks[0].row_count == 4


def _write_drawn_table_pdf(path, word_lines, strokes):
    """A page whose table is PATHS, not text — what Fibabanka actually files.

    Its statements are typeset then converted to outlines, so the balance sheet
    renders perfectly and extracts as nothing. Only the running header survives
    as text. The fixture reproduces the two measurable properties the detector
    reads — a lot of path ink, very few words — without needing a corpus PDF.
    """
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    for x, y, text in word_lines:
        page.insert_text((x, y), text, fontsize=9)
    shape = page.new_shape()
    for i in range(strokes):
        x = 60 + (i % 40) * 12
        y = 200 + (i // 40) * 4
        shape.draw_line(fitz.Point(x, y), fitz.Point(x + 6, y + 2))
    shape.finish(width=0.3)
    shape.commit()
    doc.save(str(path))
    doc.close()


def test_a_table_drawn_as_outlines_is_reported_not_silently_missed(tmp_path):
    """A page whose glyphs are paths must be MARKED unreadable.

    This is the failure that hides: the capture succeeds, the filing reports a
    handful of tables, and nothing distinguishes it from a bank that files a
    short report. Fibabanka 2022Q1 captured 13 tables and 71 rows from 92 pages
    — its balance sheet, P&L and cash flow are all drawn — while its readable
    peers yield 1,200-2,500 rows.
    """
    p = tmp_path / "FIBA_2022Q1_consolidated.pdf"
    _write_drawn_table_pdf(p, [(60, 40, "FIBABANKA A.S. VE BAGLI ORTAKLIGI")], 2400)
    cap = capture_document(p)
    assert cap.pages[0].text_layer == "vector"
    assert cap.unreadable_page_count == 1
    # and it must be visible at the filing level, where the manifest reads it
    assert cap.status == "partial"


def test_a_readable_table_is_never_called_unreadable(table_pdf):
    """The control: a typed table must stay 'text'. Statement pages carry ruled
    borders and boxes, so ink alone cannot be the signal — it is ink PER WORD,
    and the corpus separates 0-1 (typed) from 54-2,050 (drawn)."""
    cap = capture_document(table_pdf)
    assert cap.pages[0].text_layer == "text"
    assert cap.unreadable_page_count == 0
    assert cap.status == "captured"


def test_a_near_blank_page_is_not_called_unreadable(tmp_path):
    """A section divider has few words and no ink. Dividing by its word count
    would make the ratio explode, so the rule also needs real ink to fire."""
    p = tmp_path / "C_2026Q1_consolidated.pdf"
    _write_pdf(p, [(60, 100, "DORDUNCU BOLUM")])
    cap = capture_document(p)
    assert cap.pages[0].blocks == []
    assert cap.pages[0].text_layer == "text"


def _write_imaged_page_pdf(path, word_lines, img_rect):
    """A page carrying an embedded raster image — what İş Bankası actually
    filed in 2025Q1/Q2: the statement BODY is a picture under a typed banner,
    with zero path ink, so only geometry can tell it from a cover page."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    for x, y, text in word_lines:
        page.insert_text((x, y), text, fontsize=9)
    pm = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 40), False)
    pm.clear_with(200)
    page.insert_image(fitz.Rect(*img_rect), pixmap=pm)
    doc.save(str(path))
    doc.close()


def test_a_statement_body_filed_as_an_image_is_reported(tmp_path):
    """İş Bankası 2025Q1 consolidated prints its balance sheet as ONE embedded
    image under a typed banner — ~40 words of caption and footer, zero path
    items. The vector probe scores 0 ink per word, which is how the filing sat
    in the ledger stamped 'text' with 3 cells per statement page until the
    reconcile caught it at 61%. Words confined to the margin bands with the
    image over the content zone is what identifies it."""
    p = tmp_path / "ISCTR_2025Q1_consolidated.pdf"
    _write_imaged_page_pdf(
        p,
        [(60, 40, "TURKIYE IS BANKASI A.S."), (60, 52, "KONSOLIDE BILANCO"),
         (60, 64, "(Tutarlar Bin Turk Lirasi olarak ifade edilmistir.)"),
         (290, 820, "7")],
        (60, 160, 540, 640))            # ~44% of the page, mid-zone
    cap = capture_document(p)
    assert cap.pages[0].text_layer == "raster"
    assert cap.unreadable_page_count == 1
    assert cap.status == "partial"


def test_a_cover_page_with_artwork_is_not_called_unreadable(tmp_path):
    """The control that almost false-fired: TSKB 2026Q2 p1 carries full-page
    artwork AND ~25 title words in the middle of the page. Words inside the
    content zone are what separate a cover from a rasterized statement — a
    cover's title IS its content, and it is typed."""
    p = tmp_path / "TSKB_2026Q2_consolidated.pdf"
    words = [(60, 40, "TSKB")]
    words += [(60 + 44 * (i % 5), 300 + 24 * (i // 5), f"kapak{i}")
              for i in range(15)]
    _write_imaged_page_pdf(p, words, (0, 0, 595, 842))
    cap = capture_document(p)
    assert cap.pages[0].text_layer == "text"
    assert cap.status == "captured"


def test_a_divider_logo_is_not_called_unreadable(tmp_path):
    """A small logo on an otherwise typed divider covers a few percent of the
    page; rasterized statements measure 17-48%. The coverage floor keeps the
    ordinary case out."""
    p = tmp_path / "C2_2026Q1_consolidated.pdf"
    _write_imaged_page_pdf(p, [(60, 100, "DORDUNCU BOLUM")], (500, 30, 560, 70))
    cap = capture_document(p)
    assert cap.pages[0].text_layer == "text"
    assert cap.status == "captured"


def test_wrapped_label_rows_merge_into_one_logical_row(tmp_path):
    """A label that wraps, pushing its figures onto the next physical line, is
    one printed row — and the continuation must supply exactly the missing
    columns, so an adjacent independent row is never absorbed."""
    p = tmp_path / "C_2026Q1_consolidated.pdf"
    _write_pdf(p, [
        (60, 100, "Likidite Tablosu"),
        (60, 120, "1 Yuksek kaliteli likit"), (300, 120, "726.198"), (420, 120, "342.037"),
        (60, 135, "2 Gercek kisi mevduat ve perakende"),
        (60, 148, "mevduat disinda kalan"), (300, 148, "788.693"), (420, 148, "250.383"),
        (60, 163, "3 Operasyonel mevduat"), (300, 163, "3.604"), (420, 163, "901"),
    ])
    page = capture_document(p).pages[0]
    groups: dict[int, list] = {}
    for ln in page.lines:
        if ln.block_id is not None:
            groups.setdefault(ln.logical_row, []).append(ln)
    merged = [v for v in groups.values() if len(v) > 1]
    assert len(merged) == 1
    assert "Gercek kisi" in merged[0][0].label
    assert "disinda kalan" in merged[0][1].label


def test_mid_sentence_enumeration_is_not_mistaken_for_a_footnote(tmp_path):
    """BRSA filings enumerate clauses inside a sentence — "…çerçevesinde (1) …
    veya (2) Banka'nın…". When such a sentence wraps, a line STARTS with "(2)"
    without being a footnote. Since a note also terminates the table above it,
    treating that as one both invents a note and truncates a real table."""
    p = tmp_path / "D_2026Q1_consolidated.pdf"
    _write_pdf(p, [
        (60, 100, "Sermaye Kalemleri"),
        (60, 120, "Cekirdek Sermaye"), (300, 120, "444.145"), (420, 120, "439.429"),
        (60, 135, "Katki Sermaye"), (300, 135, "147.663"), (420, 135, "138.736"),
        (60, 150, "Toplam Sermaye"), (300, 150, "591.806"), (420, 150, "578.162"),
        # a wrapped sentence, not a footnote: no row above prints "(2)"
        (60, 185, "Bankacilik Kanunu cerceresinde (1) faaliyet izninin"),
        (60, 198, "(2) Bankanin hissedarlarinin ortaklik haklari devredilir."),
    ])
    page = capture_document(p).pages[0]
    # The contract is that no NOTE is invented and the line is not given the
    # footnote role. Which non-footnote role it lands in depends on how close
    # the sentence sits to the table, which is layout, not meaning.
    assert [n.marker for n in page.notes] == [], "invented a footnote from a clause"
    roles = {ln.role for ln in page.lines if ln.text.startswith("(2)")}
    assert ROLE_FOOTNOTE not in roles
    assert roles <= {ROLE_DATA, ROLE_PARAGRAPH}


def test_numbered_footnote_is_kept_when_a_row_prints_its_marker(tmp_path):
    """The converse: a numbered marker IS a footnote once some table row
    actually carries it — the guard must not throw real notes away."""
    p = tmp_path / "E_2026Q1_consolidated.pdf"
    _write_pdf(p, [
        (60, 100, "Sermaye Kalemleri"),
        (60, 120, "Cekirdek Sermaye (2)"), (300, 120, "444.145"), (420, 120, "439.429"),
        (60, 135, "Katki Sermaye"), (300, 135, "147.663"), (420, 135, "138.736"),
        (60, 150, "Toplam Sermaye"), (300, 150, "591.806"), (420, 150, "578.162"),
        (60, 185, "(2) Indirimler sonrasi gosterilmistir."),
    ])
    page = capture_document(p).pages[0]
    assert [n.marker for n in page.notes] == ["2"]
    assert page.notes[0].linked_line_orders, "real numbered note lost its row link"


@pytest.mark.parametrize("token,expected", [
    ("1.234.567", 1234567.0),      # TR thousands
    ("1,234,567", 1234567.0),      # EN thousands
    ("16,79", 16.79),              # TR decimal
    ("16.79", 16.79),              # EN decimal
    ("1.158,00", 1158.0),          # TR mixed
    ("1,016.79", 1016.79),         # EN mixed
    ("(149.216)", -149216.0),      # parenthesised negative
    ("-", None),                   # nil is not zero
    ("—", None),
])
def test_parse_cell_handles_both_conventions(token, expected):
    assert parse_cell(token) == expected


def test_ledger_and_manifest_round_trip(table_pdf, tmp_path):
    cap = capture_document(table_pdf)
    ledger = sqlite3.connect(tmp_path / "cap.db")
    main = sqlite3.connect(tmp_path / "main.db")
    store.init_ledger(ledger)
    store.init_manifest(main)

    written = store.upsert_ledger(ledger, "AKBNK", "2026Q1", "consolidated", cap)
    assert written == (cap.page_count + cap.block_count + cap.line_count
                       + cap.cell_count + cap.note_count)
    assert store.upsert_manifest(main, "AKBNK", "2026Q1", "consolidated", cap) is True
    # Re-writing identical content must NOT restamp — the manifest reaches D1,
    # where a no-op write is still billed.
    assert store.upsert_manifest(main, "AKBNK", "2026Q1", "consolidated", cap) is False

    n = ledger.execute("SELECT COUNT(*) FROM bank_audit_document_cells").fetchone()[0]
    assert n == cap.cell_count
    # A re-run replaces the partition rather than duplicating it.
    store.upsert_ledger(ledger, "AKBNK", "2026Q1", "consolidated", cap)
    assert ledger.execute(
        "SELECT COUNT(*) FROM bank_audit_document_cells").fetchone()[0] == n


def test_manifest_table_is_registered_for_d1(table_pdf):
    from src.audit_reports import registry
    assert "bank_audit_document_manifest" in registry.AUDIT_TABLES


def test_jsonl_export_is_one_object_per_page_plus_manifest(table_pdf, tmp_path):
    import json
    cap = capture_document(table_pdf)
    path = store.export_jsonl(cap, "AKBNK", "2026Q1", "consolidated", tmp_path)
    records = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    assert records[0]["type"] == "manifest"
    assert records[0]["bank_ticker"] == "AKBNK"
    pages = [r for r in records if r["type"] == "page"]
    assert len(pages) == cap.page_count
    # cells are nested inside the line they belong to
    cells = sum(len(ln["cells"]) for p in pages for ln in p["lines"])
    assert cells == cap.cell_count
