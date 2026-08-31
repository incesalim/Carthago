"""FX currency-table footnotes and split signs from 2026Q2 source filings."""
from types import SimpleNamespace

from src.audit_reports import fx_position
from src.audit_reports.fx_position import _ROW_RX, _row_values


def test_turkish_glued_footnotes_keep_hayat_gross_rows():
    by_field = dict(_ROW_RX)
    assert any(rx.match("Toplam Varlıklar2 4,269 2,929 2,253 9,451")
               for rx in by_field["on_bs_assets"])
    assert any(rx.match("Toplam Yükümlülükler2,3 3,389 2,778 533 6,700")
               for rx in by_field["on_bs_liab"])
    assert not any(rx.match("Toplam Varlıklardaki artış")
                   for rx in by_field["on_bs_assets"])


def test_tskb_detached_minus_rejoins_only_within_its_currency_cell():
    # Exact source x coordinates, TSKB 2026Q2 consolidated p36.
    tokens = [(57, "Net"), (71, "Bilanço"), (100, "Pozisyonu"),
              (312.67, "34.844"), (372.07, "-"), (376.63, "50.651"),
              (456.22, "47"), (508.42, "-15.760")]
    assert _row_values(tokens, 4) == ["34.844", "-50.651", "47", "-15.760"]
    # Prior total splits too, but OTHER is a genuine nil on the net-off row.
    prior = [(312.67, "40.218"), (373.75, "-58.514"), (456.22, "11"),
             (506.74, "-"), (511.30, "18.285")]
    assert _row_values(prior, 4) == ["40.218", "-58.514", "11", "-18.285"]
    nil = [(310.03, "-39.500"), (376.39, "57.340"), (463.06, "-"), (511.18, "17.840")]
    assert _row_values(nil, 4) == ["-39.500", "57.340", "-", "17.840"]


def test_overfull_fx_row_cannot_join_sign_across_a_currency_boundary():
    tokens = [(100, "20"), (150, "-"), (210, "10"), (270, "30"), (330, "60")]
    assert _row_values(tokens, 4) is None


def test_tskb_both_blocks_keep_source_rows_instead_of_false_positional_repair(monkeypatch):
    def row(label, values):
        return [(10, label), *zip((312.67, 376.63, 456.22, 511.18), values)]

    lines = [
        [(312.67, "EUR"), (376.63, "USD"), (456.22, "Diğer"), (511.18, "Toplam")],
        row("Toplam Varlıklar", ["144.905", "139.028", "50", "283.983"]),
        row("Toplam Yükümlülükler", ["110.061", "189.679", "3", "299.743"]),
        [(10, "Net Bilanço Pozisyonu"), (312.67, "34.844"), (372.07, "-"),
         (376.63, "50.651"), (456.22, "47"), (511.18, "-15.760")],
        row("Net Nazım Hesap Pozisyonu", ["-34.326", "49.506", "-23", "15.157"]),
        [(10, "Önceki Dönem")],
        row("Toplam Varlıklar", ["128.272", "126.941", "24", "255.237"]),
        row("Toplam Yükümlülükler", ["88.054", "185.455", "13", "273.522"]),
        [(10, "Net Bilanço Pozisyonu"), (312.67, "40.218"), (376.63, "-58.514"),
         (456.22, "11"), (506.74, "-"), (511.30, "18.285")],
        row("Net Nazım Hesap Pozisyonu", ["-39.500", "57.340", "-", "17.840"]),
    ]
    monkeypatch.setattr(fx_position, "_HAS_FITZ", True)
    monkeypatch.setattr(fx_position, "_SKIP_PAGES", 0)
    monkeypatch.setattr(fx_position, "_fitz_word_lines", lambda _: (
        [(0, lines)], SimpleNamespace(close=lambda: None)))
    report = fx_position.extract_from_pdf(pdf_path="TSKB_source_fixture.pdf")
    totals = {r.period_type: r for r in report.rows if r.currency == "TOTAL"}
    assert totals["current"].net_on_balance == -15760
    assert totals["current"].net_position == -603
    assert totals["prior"].on_bs_assets == 255237
    assert totals["prior"].net_on_balance == -18285
    assert totals["prior"].net_position == -445
