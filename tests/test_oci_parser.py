"""OCI validation-guided scorer (src/audit_reports/oci.py): the chain identity
III = I + II is the tier-1 signal, with a degenerate guard on row I (net profit,
never ~0) so a near-empty 0==0 parse can't win."""
import pytest

pytest.importorskip("fitz")  # CI installs minimal deps; oci/extractor need fitz (PyMuPDF)

from src.audit_reports.extractor import StatementRow  # noqa: E402
from src.audit_reports.oci import _oci_candidate_score, _oci_chain_closes, _oci_romans  # noqa: E402


def _row(order: int, h: str, name: str, amt: float) -> StatementRow:
    return StatementRow(order=order, hierarchy=h, name=name, footnote=None, cur_amount=amt)


def _valid_rows() -> list[StatementRow]:
    # I + II = III (1000 + -300 = 700); the 2.2 sub-tree foots (-300 == -300)
    return [
        _row(1, "I.", "current period profit", 1000.0),
        _row(2, "II.", "other comprehensive income", -300.0),
        _row(3, "2.1", "not to be recycled", 0.0),
        _row(4, "2.2", "to be recycled", -300.0),
        _row(5, "2.2.1", "fx differences", -300.0),
        _row(6, "III.", "total comprehensive income", 700.0),
    ]


def test_romans_spine():
    assert _oci_romans(_valid_rows()) == {1: 1000.0, 2: -300.0, 3: 700.0}


def test_chain_closes_on_valid():
    assert _oci_chain_closes(_valid_rows())


def test_chain_fails_when_total_wrong():
    rows = _valid_rows()
    rows[-1] = _row(6, "III.", "total", 9999.0)
    assert not _oci_chain_closes(rows)


def test_degenerate_zero_profit_rejected():
    # I ~ 0 → reject (a 0==0 parse must not be treated as a valid chain)
    rows = [_row(1, "I.", "p", 0.0), _row(2, "II.", "o", 0.0), _row(3, "III.", "t", 0.0)]
    assert not _oci_chain_closes(rows)


def test_chain_needs_all_three_romans():
    assert not _oci_chain_closes([_row(1, "I.", "p", 1000.0), _row(3, "III.", "t", 1000.0)])


def test_score_tier1_for_validating():
    s = _oci_candidate_score(_valid_rows())
    assert s[0] == 1


def test_score_tier0_for_empty():
    assert _oci_candidate_score([]) == (0, 0, 0, 0)


def test_score_tier0_when_too_few_real_rows():
    # chain closes but only 2 rows carry a real (>1) amount → below the floor
    rows = [_row(1, "I.", "p", 1000.0), _row(2, "II.", "o", 0.0), _row(3, "III.", "t", 1000.0)]
    assert _oci_candidate_score(rows)[0] == 0


def test_small_negative_recovery_validates_only_the_oci_template():
    from src.audit_reports.oci import _drop_offtemplate, _parse_oci_with

    # ALNTF 2026Q2 p13: the IV page title/date header is not an OCI row and
    # cannot veto the otherwise fully reconciling small parenthesized amounts.
    rows = _drop_offtemplate(_parse_oci_with("\n".join([
        "IV. KAR VEYA ZARAR VE DİĞER KAPSAMLI GELİR TABLOSU",
        "30 Haziran 2026 30 Haziran 2025",
        "I. DÖNEM KARI/ZARARI 691 1,067",
        "II. DİĞER KAPSAMLI GELİRLER (49) 151",
        "2.1 Kar veya Zararda Yeniden Sınıflandırılmayacaklar (5) 94",
        "2.2 Kar veya Zararda Yeniden Sınıflandırılacaklar (44) 57",
        "III. TOPLAM KAPSAMLI GELİR (I+II) 642 1,218",
    ]), 2))
    assert _oci_romans(rows) == {1: 691, 2: -49, 3: 642}
    assert {r.hierarchy: r.cur_amount for r in rows}["2.1"] == -5


def test_detached_minus_is_joined_within_a_cell_but_not_across_columns(monkeypatch):
    from src.audit_reports import oci

    monkeypatch.setattr(oci, "_fitz_page_line_tokens", lambda *_: [
        [(30, 50, "2.1.3"), (60, 320, "Planları"), (712, 715, "-"), (808, 813, "6")],
        [(30, 50, "2.1.5"), (60, 320, "Vergiler"), (696, 699, "-"), (701, 716, "165"),
         (793, 796, "-"), (798, 813, "141")],
        [(30, 50, "2.2"), (60, 320, "Sınıflandırılacaklar"), (695, 698, "-"),
         (700, 716, "480"), (803, 813, "36")],
    ])
    assert oci._signed_oci_text("synthetic.pdf", 1).splitlines() == [
        "2.1.3 Planları - 6", "2.1.5 Vergiler -165 -141", "2.2 Sınıflandırılacaklar -480 36",
    ]


def test_oci_locator_skips_circumflex_profit_share_income_page(monkeypatch):
    from src.audit_reports import extractor

    pages = {
        10: "I. KÂR PAYI GELİRLERİ 4.836\nII. KÂR PAYI GİDERLERİ 2.944\n"
            "1.5.2 Gerçeğe Uygun Değer Farkı Diğer Kapsamlı Gelire Yansıtılanlar 217",
        11: "DİĞER KAPSAMLI GELİR TABLOSU\nI. DÖNEM KARI/ZARARI 3.237 746\n"
            "II. DİĞER KAPSAMLI GELİRLER 63 4\nIII. TOPLAM KAPSAMLI GELİR 3.300 750",
    }
    monkeypatch.setattr(extractor, "_fitz_page_count", lambda _: 20)
    monkeypatch.setattr(extractor, "_fitz_page_text", lambda _, i: pages.get(i, ""))
    assert extractor._locate_oci_page("synthetic.pdf", 10) == 12


def test_oci_locator_accepts_small_million_amounts_and_excludes_plural_equity(monkeypatch):
    from src.audit_reports import extractor

    pages = {
        13: "DİĞER KAPSAMLI GELİR TABLOSU\nI. DÖNEM KARI/ZARARI 90 (76) 55 20\n"
            "II. DİĞER KAPSAMLI GELİRLER (37) (1) 21 20\nIII. TOPLAM KAPSAMLI GELİR 53 (77) 76 40",
        14: "ÖZKAYNAKLAR DEĞİŞİM TABLOSU\nDiğer Kapsamlı Gelirler\n"
            "I. Önceki Dönem Sonu Bakiyesi 4500 3928\nIII. Yeni Bakiye 4500 3928",
    }
    monkeypatch.setattr(extractor, "_fitz_page_count", lambda _: 20)
    monkeypatch.setattr(extractor, "_fitz_page_text", lambda _, i: pages.get(i, ""))
    assert extractor._locate_oci_page("synthetic.pdf", 13) == 14
    pages.pop(13)
    assert extractor._locate_oci_page("synthetic.pdf", 13) is None


def test_four_column_oci_keeps_cumulative_amount_when_both_period_pairs_foot(monkeypatch):
    from src.audit_reports import oci

    # HAYATK 2026Q2 p14: 90-37=53 YTD and 55+21=76 quarter-only are BOTH valid.
    # A two-column parser takes the last pair and silently changes period basis.
    text = "\n".join([
        "I. DÖNEM KARI/ZARARI 90 (76) 55 20",
        "II. DİĞER KAPSAMLI GELİRLER (37) (1) 21 20",
        "2.1 Kâr veya Zararda Yeniden Sınıflandırılmayacaklar - - - -",
        "2.2 Kâr veya Zararda Yeniden Sınıflandırılacaklar (37) (1) 21 20",
        "2.2.2 Değerleme Gelirleri/Giderleri (52) (2) 30 28",
        "2.2.6 Gelire İlişkin Vergiler 15 1 (9) (8)",
        "III. TOPLAM KAPSAMLI GELİR (I+II) 53 (77) 76 40",
    ])
    monkeypatch.setattr(oci, "_detect_pl_ncols", lambda *_: 4)
    monkeypatch.setattr(oci, "_fitz_page_text", lambda *_: text)
    rows = oci.extract_oci("synthetic.pdf", 14).rows
    assert _oci_romans(rows) == {1: 90, 2: -37, 3: 53}
