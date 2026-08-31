"""Row-label taxonomy regression tests for the NPL movement extractor.

Guarded by importorskip: npl_movement imports fitz, which CI's minimal
dependency set omits. The label matcher itself is pure-stdlib.
"""
import pytest

pytest.importorskip("fitz")

from src.audit_reports.npl_movement import (  # noqa: E402
    _DATE_BALANCE_RX, _extract_from_block, _extract_with_sparse_columns, _match_row_label,
)


def test_date_balance_row_tolerates_glued_suffix():
    # ODEA glues the word to the year ("31 Aralık 2021Bakiyesi") with no space —
    # the opening balance row was missed (the \b fell between "1" and "B").
    assert _DATE_BALANCE_RX.match("31 Aralık 2021Bakiyesi 142.814 21.734 1.824.580")
    assert _DATE_BALANCE_RX.match("31 Mart 2022 Bakiyesi 117.728 32.155 1.731.331")  # spaced
    assert _DATE_BALANCE_RX.match("31 Aralık 2024 103,885 209,960 144,837")          # bare date


def test_opening_label_variants_map_to_opening():
    # BURGAN (cons, English) and EXIM (English) opening rows were unmatched →
    # the block started on Additions, nulling opening_balance (the roll-forward
    # then couldn't tie).
    assert _match_row_label("Ending Balance of Prior Period 25,581 413,818") == "opening_balance"
    assert _match_row_label("Balance at the End of the Previous Period 75.305 - 801.748") == "opening_balance"


def test_previous_period_opening_not_shadowed_by_closing():
    # The EXIM opening phrase is a superstring-prefix risk against the closing
    # "Balance at the End of the Period"; longest-first matching must keep them
    # distinct (opening vs closing), or the roll-forward double-reads.
    assert _match_row_label("Balance at the End of the Period 16.779 38.015 941.266") == "closing_balance"
    assert _match_row_label("Balance at the End of the Previous Period 75.305") == "opening_balance"


def test_specific_provision_maps_to_provision():
    # BURGAN heads the provision row "Specific Provision (-)" — doesn't start with
    # "provision", so the generic prefixes missed it.
    assert _match_row_label("Specific Provision (-) 7,246 210,343 379,789") == "provision"
    assert _match_row_label("Provisions (-) 16.779 38.015 941.266") == "provision"


@pytest.mark.parametrize(("label", "key"), [
    ("Balance at the end of period", "closing_balance"),  # COLENDI
    ("Transfers from other NPL categories", "transfers_in"),  # HALKB
    ("Transfers to other NPL categories", "transfers_out"),
    ("Diğer Donuk Alacak Hesaplarına Giriş", "transfers_in"),  # ING
    ("Diğer Donuk Alacak Hesaplarından Çıkış", "transfers_out"),
    ("Diğer Donuk.Alacak Hesaplarına Çıkış", "transfers_out"),  # ATBANK
    ("Aktiften Silinen", "write_offs"),  # KUVEYT, TFKB
    ("Write-off", "write_offs"),  # SKBNK
    ("Dispose of", "sold"),  # ALBRK
    ("Effect of changes in exchange rates", "fx_diff"),  # ISCTR
    ("Kur Değişimi Etkisi", "fx_diff"),
    ("Kura Göre Yapılan Düzeltmelerden Farklar", "fx_diff"),  # VAKBN
    ("Donuk alacaklara ilişkin kur farkları", "fx_diff"),  # TSKB
    ("Özel Karşılık", "provision"),  # ANADOLU, ATBANK, ODEA, TFKB
    ("Özel Kredi Karşılığı", "provision"),  # TOMK
    ("Beklenen Zarar Karşılığı", "provision"),  # ZIRAATK
])
def test_observed_disclosure_labels_retain_their_field(label, key):
    # Exercise the full reader, including signs and longest-prefix collisions.
    rows = _extract_from_block(1, "\n".join([
        "Opening balance 100 200 300", "Additions 1 2 3",
        f"{label} 5 10 15",
    ]))
    assert len(rows) == 3
    assert [getattr(row, key) for row in rows] == [5, 10, 15]
    assert all(row.opening_balance == value for row, value in zip(rows, (100, 200, 300)))


def test_halkb_sign_only_transfer_continuation_restores_rollforward():
    # HALKB 2026Q2 unconsolidated p.77; the label is above '(+) <three cells>'.
    # Without joining that continuation, III ties but IV/V miss 21,332/20,291.
    rows = _extract_from_block(77, "\n".join([
        "Prior period end balance 15.599 26.792 36.629",
        "Additions (+) 29.629 747 6.787",
        "Transfers from other categories of loans under non-performing",
        "(+) - 21.332 20.291",
        "Transfers to other categories of loans under non-performing (-) 22.080 19.543 -",
        "Collections (-) (*) 2.698 3.084 5.448",
        "Write-offs (-) - - 6",
        "Current period end balance 20.450 26.244 58.253",
        "Provision (-) 6.346 9.237 37.230",
        "Net balance on balance sheet 14.104 17.007 21.023",
    ]))
    assert [row.transfers_in for row in rows] == [0, 21332, 20291]
    for row in rows:
        assert (row.opening_balance + row.additions + row.transfers_in
                - row.transfers_out - row.collections - row.write_offs) == row.closing_balance
        assert row.closing_balance - row.provision == row.net_balance


def test_turkiye_finans_accrual_is_signed_and_distinct_from_currency():
    # TFKB 2026Q2 consolidated p.67, source million TL.
    rows = _extract_from_block(67, "\n".join([
        "Önceki Dönem Sonu Bakiyesi 753 662 983",
        "Dönem İçinde İntikal (+) (*) 1,036 36 227",
        "Diğer Donuk Alacak Hesaplarından Giriş (+) - 1,135 545",
        "Diğer Donuk Alacak Hesaplarına Çıkış (-) (1,135) (545) -",
        "Dönem İçinde Tahsilat (-) (120) (66) (112)",
        "Aktiften Silinen (-) (**) - - (361)",
        "Donuk Alacak Reeskontları (4) 34 44",
        "Dönem Sonu Bakiyesi (***) 530 1,256 1,326",
        "Özel Karşılık (-) (285) (808) (1,023)",
        "Bilançodaki Net Bakiyesi 245 448 303",
    ]))
    assert [row.accrual_movement for row in rows] == [-4, 34, 44]
    assert all(row.fx_diff is None and row.sold is None for row in rows)
    for row in rows:
        assert (row.opening_balance + row.additions + row.transfers_in
                - row.transfers_out - row.collections - row.write_offs
                + row.accrual_movement) == row.closing_balance
        assert row.closing_balance - row.provision == row.net_balance


def _isctr_sparse_tokens():
    # ISCTR 2026Q1 consolidated p.72, source thousand TL. Token positions mirror
    # its right-aligned three columns; the missing cells are physically blank.
    def line(label, values):
        return [(56.0, 250.0, label), *[
            (300.0 + col * 100, 340.0 + col * 100, value)
            for col, value in values.items()
        ]]

    return [
        line("Group III Group IV Group V", {}),
        line("Prior Period Ending Balance", {0: "29,807,986", 1: "23,586,039", 2: "32,262,813"}),
        line("Additions", {0: "24,474,591", 1: "219,860", 2: "285,440"}),
        line("Transfers from Other NPL Categories (+)", {1: "24,750,027", 2: "10,142,506"}),
        line("Transfers to Other NPL Categories (-)", {0: "24,750,027", 1: "10,142,506"}),
        line("Collections", {0: "4,428,403", 1: "2,435,146", 2: "1,820,522"}),
        line("Write-offs", {0: "301", 1: "91", 2: "733"}),
        line("Debt Sale (-) (1)", {2: "3,776,218"}),
        line("Effect of Changes in Exchange Rates", {0: "531", 1: "320", 2: "19,105"}),
        line("Current Period Ending Balance", {0: "25,104,377", 1: "35,978,503", 2: "37,112,391"}),
        line("Specific Provisions (-)", {0: "13,439,483", 1: "21,055,790", 2: "25,485,708"}),
        line("Net Balance on Balance Sheet", {0: "11,664,894", 1: "14,922,713", 2: "11,626,683"}),
    ]


def _parse_sparse(tokens):
    text = "\n".join(" ".join(token for _, _, token in row) for row in tokens)
    return _extract_with_sparse_columns(72, text, tokens)


def test_sparse_flows_recovered_only_from_aligned_cells_and_both_identities():
    rows = _parse_sparse(_isctr_sparse_tokens())
    assert [r.transfers_in for r in rows] == [0, 24750027, 10142506]
    assert [r.transfers_out for r in rows] == [24750027, 10142506, 0]
    assert [r.sold for r in rows] == [0, 0, 3776218]
    assert all(r.accrual_movement is None for r in rows)  # undisclosed row stays NULL


@pytest.mark.parametrize("defect", ["geometry", "movement", "net", "anchors"])
def test_sparse_flow_recovery_abstains_on_uncertain_evidence(defect):
    tokens = _isctr_sparse_tokens()
    if defect == "geometry":
        x0, x1, value = tokens[7][-1]
        tokens[7][-1] = (x0 - 20, x1 - 20, value)
    elif defect == "movement":
        x0, x1, _ = tokens[7][-1]
        tokens[7][-1] = (x0, x1, "3,776,000")
    elif defect == "net":
        x0, x1, _ = tokens[-1][-1]
        tokens[-1][-1] = (x0, x1, "11,626,000")
    else:
        tokens = tokens[:-2]  # no provision/net anchors or independent net identity
    rows = _parse_sparse(tokens)
    assert all(r.transfers_in is None and r.transfers_out is None and r.sold is None for r in rows)
