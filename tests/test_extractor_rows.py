"""Regression tests for _parse_rows over real-world phantom/garbage lines.

Skipped under CI's minimal deps (extractor imports pdfplumber at module
level); runs locally and in any env with full requirements.
"""
import pytest

pytest.importorskip("pdfplumber")

from src.audit_reports.extractor import _parse_rows  # noqa: E402

VALUES_6 = "123.456 789 124.245 100.000 500 100.500"


def test_qnbfb_squished_page_header_rejected():
    # The two dates fragment into 6 numeric tokens; before the BALANCE\s*SHEET
    # filter this line was admitted as a roman-I data row with garbage values.
    text = "I. BALANCESHEET-ASSETS CurrentPeriod PriorPeriod 31.12.2023 31.12.2022"
    assert _parse_rows(text, 6) == []
    text2 = "I. CONSOLIDATEDBALANCESHEET–ASSETS CurrentPeriod PriorPeriod 31.12.2023 31.12.2022"
    assert _parse_rows(text2, 6) == []


def test_skbnk_leading_dipnot_with_dashes_not_stored_as_value():
    # 5 dashes + the "(14)" dipnot = 6 tokens; (14) used to become tl=-14.
    # After the dipnot drop the row recovers as a genuine zero row (identity
    # 0+0=0 holds) — never as -14.
    text = "VII. INVESTMENT PROPERTY (Net) (14) - - - - -"
    rows = _parse_rows(text, 6)
    assert len(rows) == 1 and rows[0][1][:3] == [0.0, 0.0, 0.0]
    assert -14.0 not in rows[0][1]


def test_leading_dipnot_with_full_columns_kept():
    text = f"VII. INVESTMENT PROPERTY (Net) (14) {VALUES_6}"
    rows = _parse_rows(text, 6)
    assert len(rows) == 1
    label, vals = rows[0]
    assert vals[0] == 123456.0 and -14 not in vals


def test_ecl_row_with_dipnot_still_parses():
    text = "2.4 Expected Credit Losses (-) (6) 3.901.206 2.639.305 6.540.511 3.514.226 2.543.524 6.057.750"
    rows = _parse_rows(text, 6)
    assert len(rows) == 1
    _, vals = rows[0]
    assert vals[2] == 6540511.0 and vals[5] == 6057750.0


def test_plain_row_unaffected():
    text = f"1.1.2 Banks {VALUES_6}"
    rows = _parse_rows(text, 6)
    assert len(rows) == 1 and rows[0][1][2] == 124245.0


def test_short_row_recovered_when_current_triplet_validates():
    # SKBNK 16.5.4: prior-period dash lost → 5 tokens; the current triplet is
    # intact and TL+FC=Total confirms it.
    text = "16.5.4 Other Profit Reserves 239,160 - 239,160 159,400 159,400"
    rows = _parse_rows(text, 6)
    assert len(rows) == 1
    assert rows[0][1][:3] == [239160.0, 0.0, 239160.0]
    assert rows[0][1][3:] == [None, None, None]


def test_short_row_recovered_by_zero_insertion():
    # ICBCT 16.4-style: the TL dash lost entirely → triplet completes with 0.
    text = "16.4 Birikmis Diger Kapsamli Gelirler 151.096 151.094 140.000"
    rows = _parse_rows(text, 6)
    assert len(rows) == 1
    assert rows[0][1][:3] == [0.0, 151096.0, 151094.0]


def test_short_dash_row_recovered_as_zeros():
    text = "VII. INVESTMENT PROPERTY (Net) (14) - - - - -"
    rows = _parse_rows(text, 6)
    assert len(rows) == 1 and rows[0][1][:3] == [0.0, 0.0, 0.0]


def test_short_row_not_recovered_when_identity_fails():
    # 5 tokens but no interpretation satisfies TL+FC=Total → still skipped.
    text = "2.3 Securities 100.000 50.000 800.000 70.000 90.000"
    assert _parse_rows(text, 6) == []


def test_no_recovery_for_two_nonzero_tokens():
    # A bare pair of coincidentally-equal numbers must not fabricate a row.
    text = "5.1 Some Note 5 5"
    assert _parse_rows(text, 6) == []


def test_pl_rows_never_recovered():
    # P&L (2-col) has no internal identity — short rows stay skipped.
    assert _parse_rows("1.1 Interest on Loans 123.456", 2) == []


def test_tskb_split_digit_join_recovers_row():
    # TSKB 2025Q2 line I.: "16. 462.594" is one number split in two; the join
    # is accepted because BOTH triplets then satisfy TL+FC=Total.
    text = ("I. FINANCIAL ASSETS (Net) 27.225.645 20.209.649 47.435.294 "
            "16. 462.594 18.808.018 35.270.612")
    rows = _parse_rows(text, 6)
    assert len(rows) == 1
    assert rows[0][1] == [27225645.0, 20209649.0, 47435294.0,
                          16462594.0, 18808018.0, 35270612.0]


def test_split_digit_chain_join_three_fragments():
    # TSKB also splits one number into THREE fragments: "5. 219 . 274".
    text = "4.2 Subsidiaries (Net) (8) 6.310.323 - 6.310.323 5. 219 . 274 - 5.219.274"
    rows = _parse_rows(text, 6)
    assert len(rows) == 1
    assert rows[0][1] == [6310323.0, 0.0, 6310323.0, 5219274.0, 0.0, 5219274.0]


def test_split_digit_join_rejected_when_identity_fails():
    # Same shape but numbers that don't add up — no join, falls back to
    # last-6 (and the validator flags the row downstream).
    text = ("I. FINANCIAL ASSETS (Net) 27.225.645 20.209.649 99.999.999 "
            "16. 462.594 18.808.018 35.270.612")
    rows = _parse_rows(text, 6)
    assert len(rows) == 1
    assert rows[0][1][2] != 99999999.0 or rows[0][1][0] != 27225645.0


def test_bare_roman_without_dot_recovered():
    # ALNTF prints its first section header with no trailing dot:
    # "I FİNANSAL VARLIKLAR (Net) <6 numbers>". Must parse as a roman row.
    text = f"I FİNANSAL VARLIKLAR (Net) {VALUES_6}"
    rows = _parse_rows(text, 6)
    assert len(rows) == 1
    assert rows[0][0].startswith("I FİNANSAL")
    assert rows[0][1][2] == 124245.0


def test_bare_letter_without_dot_not_a_marker():
    # A lone non-roman uppercase word must NOT be treated as a hierarchy marker
    # (only I/V/X romans get the dotless treatment).
    text = f"A FOO BAR {VALUES_6}"
    rows = _parse_rows(text, 6)
    # admitted only if it looks like a total; "A FOO BAR" is neither roman nor total
    assert rows == [] or not rows[0][0].startswith("A ")


def test_section_ref_masked_not_read_as_value():
    # ICBCT held-for-sale: long label wraps, all-dash columns interleave around
    # the "(5.I.16)" footnote ref → its 5/16 used to land in the value slots.
    text = ("III. SATIŞ AMAÇLI ELDE TUTULAN VE DURDURULAN FAALİYETLERE İLİŞKİN "
            "- - - DURAN VARLIKLAR (Net) (5.I.16) - - -")
    rows = _parse_rows(text, 6)
    assert len(rows) == 1
    assert rows[0][1] == [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


def test_section_ref_digit_only_masked():
    text = f"III. Held for Sale (5.1.14) {VALUES_6}"
    rows = _parse_rows(text, 6)
    assert len(rows) == 1 and rows[0][1][0] == 123456.0  # 5,1,14 not leaked


def test_wrapped_marker_only_row_kept():
    # KUVEYT: the "1.2." parent's label wrapped to adjacent lines, leaving just
    # the marker + 6 numbers. Must be kept with hierarchy="1.2.", name empty.
    text = "1.2. 3.272.959 14.626.860 17.899.819 1.233.834 10.951.814 12.185.648"
    rows = _parse_rows(text, 6)
    assert len(rows) == 1
    assert rows[0][1][:3] == [3272959.0, 14626860.0, 17899819.0]


def test_dup_digit_artifact_repaired():
    # ANADOLU: prior-period "21,817,92727" (=21,817,927 with last 2 digits
    # duplicated) shifts the window; repaired so the current triplet balances.
    text = ("VARLIKLAR TOPLAMI 24,847,702 21,817,927 46,665,629 "
            "19,894,088 14,790,92727 34,685,073")
    rows = _parse_rows(text, 6)
    assert len(rows) == 1
    assert rows[0][1][:3] == [24847702.0, 21817927.0, 46665629.0]


def test_roman_footnote_with_glued_note_number_masked():
    # ANADOLU: "V-II-9" / "V-I-15" footnote refs leak their note number.
    z = _parse_rows("XIV. SERMAYE BENZERİ BORÇLANMA ARAÇLARI V-II-9 - - - - - -", 6)
    assert len(z) == 1 and z[0][1][:3] == [0.0, 0.0, 0.0]
    v = _parse_rows("IX. ERTELENMİŞ VERGİ VARLIĞI V-I-15 276.268 - 276.268 532.041 - 532.041", 6)
    assert len(v) == 1 and v[0][1][:3] == [276268.0, 0.0, 276268.0]


def test_parenthesized_roman_footnote_masked():
    # TEB/EXIM dipnot column "(I-10)" leaked "-10" as a value and truncated the
    # label; must be masked so the row's real values parse.
    text = "4.3 Birlikte Kontrol Edilen Ortaklıklar (Net) (I-10) 5 - 5 5 - 5"
    rows = _parse_rows(text, 6)
    assert len(rows) == 1 and rows[0][1][:3] == [5.0, 0.0, 5.0]


def test_dotless_roman_does_not_eat_split_VARLIKLAR_header():
    # ATBANK's column-header word "VARLIKLAR" (ASSETS) splits as "V ARLIKLAR";
    # the dotless-roman rule must NOT treat it as roman V.
    assert _parse_rows("V ARLIKLAR (Beşinci Bölüm-I) 1 2 3 4 5 6", 6) == []
    # ...while a genuine dotless roman section header still parses.
    rows = _parse_rows("I FİNANSAL VARLIKLAR (Net) 100 50 150 90 40 130", 6)
    assert len(rows) == 1 and rows[0][0].startswith("I FİNANSAL")


def test_tr_number_not_treated_as_bare_marker():
    # EXIM's grand-total line wraps its label away, leaving "37.239.656 …" —
    # a TR-format number must NOT be admitted as a hierarchy marker / bogus row.
    line = "37.239.656 305.395.566 342.635.222 24.983.265 297.394.215 322.377.480 The accompanying notes"
    assert _parse_rows(line, 6) == []
    # ...while a genuine wrapped marker "1.2." still parses.
    assert len(_parse_rows("1.2. 3.272.959 14.626.860 17.899.819 1.233.834 10.951.814 12.185.648", 6)) == 1


def test_squished_off_balance_rows_survive_header_filter():
    # ISCTR off-balance: real data rows that contain "BALANCESHEET" squished —
    # the header filter must not eat them (it did, briefly, between the QNBFB
    # fix and the Phase-3 batch-3 gate catching a 12-row loss).
    a = f"A. OFF-BALANCESHEETCONTINGENCIESandCOMMITMENTS(I+II+III) V-III {VALUES_6}"
    total = f"TOTALOFF-BALANCESHEETCOMMITMENTS(A+B) {VALUES_6}"
    tr = f"A. BİLANÇO DIŞI YÜKÜMLÜLÜKLER (I+II+III) {VALUES_6}"
    assert len(_parse_rows(a, 6)) == 1
    assert len(_parse_rows(total, 6)) == 1
    assert len(_parse_rows(tr, 6)) == 1
    # …while the page header stays rejected
    hdr = "I. BALANCESHEET-ASSETS CurrentPeriod PriorPeriod 31.12.2023 31.12.2022"
    assert _parse_rows(hdr, 6) == []
