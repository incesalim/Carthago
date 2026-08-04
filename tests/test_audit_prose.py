"""Unit tests for the narrative-prose lane.

Everything here is a pure function over synthetic `Line` objects — no PDF, no
fitz — so it runs under CI's minimal deps. Each test pins a failure that was
measured on the corpus, not a hypothetical one; the docstrings name which.
"""
from src.audit_reports.prose import (
    Line,
    _fold,
    _mark_headings,
    _mark_tables,
    _marker_depth,
    _push_path,
    build_rows,
    declared_titles,
    detect_language,
    find_furniture,
    resolve_sections,
    role_from_title,
)
from src.audit_reports.validator import check_prose


def mkline(text: str, page: int = 1, order: int = 0, seq: int = 0,
           xs: list[tuple[float, float]] | None = None) -> Line:
    """A Line whose tokens are laid out left-to-right at normal word spacing
    unless explicit x-ranges are given."""
    words = text.split()
    if xs is None:
        xs, x = [], 50.0
        for w in words:
            xs.append((x, x + len(w) * 5.0))
            x += len(w) * 5.0 + 4.0
    tokens = [(a, b, w) for (a, b), w in zip(xs, words)]
    return Line(page=page, order=order, tokens=tokens, text=text, seq=seq)


# --- the table/prose boundary ----------------------------------------------

def test_sentence_quoting_a_figure_stays_prose():
    """The measured false positive: numeric-density classification filed
    '…kıdem tazminatı yükümlülüğü 29.447 TL'dir' under 'table'. It is a
    sentence stating a figure — the exact class the lane exists to capture."""
    page = [
        mkline("Varlik 1.000 2.000 3.000", page=1, order=0,
               xs=[(50, 90), (200, 240), (300, 340), (400, 440)]),
        mkline("Yukumluluk 4.000 5.000 6.000", page=1, order=1,
               xs=[(50, 95), (200, 240), (300, 340), (400, 440)]),
        mkline("Toplam 5.000 7.000 9.000", page=1, order=2,
               xs=[(50, 88), (200, 240), (300, 340), (400, 440)]),
        mkline("Bu tutar 31 Mart 2022 itibariyla Grup un kidem tazminati "
               "yukumlulugu 29.447 TL dir", page=1, order=3),
    ]
    _mark_tables(page)
    assert [ln.is_table for ln in page[:3]] == [True, True, True]
    assert page[3].is_table is False


def test_aligned_numeric_row_is_a_table():
    page = [
        mkline("Nakit 100 200", page=1, order=i,
               xs=[(50, 85), (300, 330), (400, 430)])
        for i in range(4)
    ]
    _mark_tables(page)
    assert all(ln.is_table for ln in page)


# --- language ---------------------------------------------------------------

def test_english_filing_is_detected():
    """32% of the corpus is an English convenience translation, and a
    Turkish-only pattern returns zero sections without erroring."""
    lines = [mkline("SECTION ONE GENERAL INFORMATION", page=1),
             mkline("SECTION TWO FINANCIAL STATEMENTS", page=1)]
    assert detect_language(lines) == "en"
    assert detect_language([mkline("BIRINCI BOLUM", page=1)]) == "tr"


def test_fold_handles_turkish_dotted_i():
    assert _fold("BİRİNCİ BÖLÜM") == "BIRINCI BOLUM"
    assert _fold("İKİNCİ") == _fold("ikinci")


# --- section resolution -----------------------------------------------------

def _seven_section_doc(extra: list[Line] | None = None) -> list[Line]:
    """A contents page listing all seven, then the seven real dividers."""
    names = ["BİRİNCİ", "İKİNCİ", "ÜÇÜNCÜ", "DÖRDÜNCÜ", "BEŞİNCİ", "ALTINCI",
             "YEDİNCİ"]
    lines = [mkline(f"{n} BÖLÜM - BASLIK {i}", page=2, order=i, seq=i)
             for i, n in enumerate(names)]
    seq = 100
    for i, n in enumerate(names):
        lines.append(mkline(f"{n} BÖLÜM", page=5 + i * 10, order=0, seq=seq))
        seq += 1
    return lines + (extra or [])


def test_contents_page_is_never_a_section_start():
    """First-match resolution puts all seven sections on the contents page."""
    starts, _seq = resolve_sections(_seven_section_doc(), "tr")
    assert starts == {1: 5, 2: 15, 3: 25, 4: 35, 5: 45, 6: 55, 7: 65}


def test_cross_reference_does_not_anchor_a_section():
    """'…yedinci bölümde yer verilen ara dönem faaliyet raporu…' is a sentence,
    not a heading. Last-match resolution scored 1/10 on this."""
    noise = [mkline("Sinirli denetimimiz sonucunda ilisikte yedinci bolumde yer "
                    "verilen ara donem faaliyet raporu incelenmistir",
                    page=90, order=0, seq=900)]
    assert resolve_sections(_seven_section_doc(noise), "tr")[0][7] == 65


def test_two_sections_sharing_the_last_page_both_resolve():
    """In an ANNUAL filing §6 and §7 both open on the final page. A
    strictly-increasing-PAGE chain takes only one, which made every annual
    report resolve to six sections."""
    names = ["BİRİNCİ", "İKİNCİ", "ÜÇÜNCÜ", "DÖRDÜNCÜ", "BEŞİNCİ"]
    lines = [mkline(f"{n} BÖLÜM", page=5 + i * 10, order=0, seq=i)
             for i, n in enumerate(names)]
    lines.append(mkline("ALTINCI BÖLÜM", page=60, order=3, seq=50))
    lines.append(mkline("YEDİNCİ BÖLÜM", page=60, order=9, seq=51))
    starts, seq = resolve_sections(lines, "tr")
    assert seq[6] < seq[7]   # same page, different lines — both must get rows
    assert starts[6] == 60 and starts[7] == 60
    assert len(starts) == 7


# --- roles ------------------------------------------------------------------

def test_activity_report_is_not_read_as_an_audit_report():
    """Both titles end in 'RAPORU'. Testing the audit rule first labels every
    interim §7 an audit report."""
    assert role_from_title("Ara Dönem Faaliyet Raporu") == "interim_activity_report"
    assert role_from_title("Sınırlı Denetim Raporu") == "audit_report"


def test_other_disclosures_is_not_read_as_notes():
    """ALNTF titles §6 'Diğer Açıklama ve Dipnotlar' — singular, so it misses
    'DİĞER AÇIKLAMALAR' and would fall through to the notes rule."""
    assert role_from_title("Diğer Açıklama ve Dipnotlar") == "other_explanations"


def test_garanti_footnotes_title_is_notes():
    """'Disclosures and Footnotes on Unconsolidated Financial Statements' has
    no 'explanations and notes' in it and fell through to the statements rule."""
    assert role_from_title(
        "Disclosures and Footnotes on Unconsolidated Financial Statements"
    ) == "notes"


def test_declared_titles_ignore_the_contents_column_header():
    """GARANTİ's next-line fallback picked up 'Page No'."""
    lines = [
        mkline("BİRİNCİ BÖLÜM", page=1, order=0, seq=0),
        mkline("Page No", page=1, order=1, seq=1),
        mkline("İKİNCİ BÖLÜM", page=1, order=2, seq=2),
        mkline("Konsolide Finansal Tablolar", page=1, order=3, seq=3),
        mkline("ÜÇÜNCÜ BÖLÜM", page=1, order=4, seq=4),
        mkline("Muhasebe Politikaları", page=1, order=5, seq=5),
    ]
    titles = declared_titles(lines, "tr")
    assert 1 not in titles
    assert titles[3] == "Muhasebe Politikaları"


# --- furniture and blocks ---------------------------------------------------

def test_running_headers_are_stripped():
    lines = [mkline("BANKA A.S.", page=p) for p in range(1, 11)]
    lines += [mkline("gercek bir cumle burada yer almaktadir", page=1)]
    assert "BANKA A.S." in find_furniture(lines, 10)


def test_blocks_carry_their_heading_and_section():
    lines = [
        mkline("I. Muhasebe politikalarina iliskin aciklamalar:", page=5, seq=0),
        mkline("Finansal tablolar tarihi maliyet esasina gore hazirlanmistir ve "
               "bu esas her donem tutarli sekilde uygulanmaktadir", page=5, seq=1),
    ]
    _mark_headings(lines)
    rows = build_rows(lines, {3: 0}, "tr", {3: "accounting_policies"})
    assert len(rows) == 1
    assert rows[0].section == 3
    assert rows[0].section_role == "accounting_policies"
    assert rows[0].heading_path == "3.I"   # section-rooted full path
    assert rows[0].text.startswith("Finansal tablolar")


# --- the validator ----------------------------------------------------------

def _rows(sections):
    return [{"section": s, "section_role": r, "page_start": p}
            for s, r, p in sections]


def test_validator_accepts_a_clean_filing():
    res = check_prose(_rows([
        (1, "general_info", 5), (2, "financial_statements", 7),
        (3, "accounting_policies", 15), (4, "risk", 29), (5, "notes", 58),
        (6, "audit_report", 84), (7, "interim_activity_report", 85)]))
    assert res.failed == 0 and res.passed > 0


def test_validator_catches_a_missing_section():
    res = check_prose(_rows([
        (1, "general_info", 5), (3, "accounting_policies", 15),
        (4, "risk", 29), (5, "notes", 58)]))
    checks = {f["check"] for f in res.failures}
    assert "sections_missing" in checks
    assert "sections_not_contiguous" in checks


def test_validator_catches_sections_out_of_order():
    res = check_prose(_rows([
        (1, "general_info", 50), (2, "financial_statements", 7),
        (3, "accounting_policies", 15), (4, "risk", 29), (5, "notes", 58),
        (6, "audit_report", 84), (7, "interim_activity_report", 85)]))
    assert "sections_out_of_order" in {f["check"] for f in res.failures}


def test_validator_checks_roles_not_section_numbers():
    """§6/§7 swap between annual and interim, so a NUMBER-based check passes on
    a mislabelled filing. The role check is what catches it."""
    res = check_prose(_rows([
        (1, "general_info", 5), (2, "financial_statements", 7),
        (3, "accounting_policies", 15), (4, "financial_statements", 29),
        (5, "notes", 58), (6, "audit_report", 84),
        (7, "interim_activity_report", 85)]))
    fails = [f for f in res.failures if f["check"] == "role_missing"]
    assert len(fails) == 1 and "risk" in fails[0]["node"]


def test_validator_skips_when_there_are_no_rows():
    res = check_prose([])
    assert res.checked == 0 and res.skipped == 1


def test_validator_accepts_an_addendum_after_the_closing_sections():
    """İŞ BANKASI resolves a clean 1–8 whose §6/§7 are the review and activity
    reports and whose §8 this classifier has no rule for. Requiring the LAST
    section to carry a closing role red-flags a filing that ended correctly."""
    res = check_prose(_rows([
        (1, "general_info", 7), (2, "financial_statements", 11),
        (3, "accounting_policies", 18), (4, "risk", 31), (5, "notes", 55),
        (6, "review_report_pointer", 88), (7, "interim_activity_report", 90),
        (8, "unknown", 91)]))
    assert "sections_truncated" not in {f["check"] for f in res.failures}


def test_validator_catches_a_filing_truncated_at_the_notes():
    """KUVEYT resolved a clean, contiguous, in-order 1–5 and stopped at the
    notes. No count or ordering test sees that."""
    res = check_prose(_rows([
        (1, "general_info", 5), (2, "financial_statements", 7),
        (3, "accounting_policies", 15), (4, "risk", 27), (5, "notes", 49),
        (6, "notes", 60)]))
    assert "sections_truncated" in {f["check"] for f in res.failures}


def test_section5_is_notes_however_the_bank_phrases_it():
    """§2 and §5 are both '…financial statements'. What separates them is the
    disclosure word, not the noun — matching only 'notes'/'footnotes' left 23
    filings (EXIM, QNBFB, SKBNK, TSKB, PASHA) reading §5 as a second §2."""
    for title in (
        "Explanations and Disclosures on Unconsolidated Financial Statements",
        "INFORMATION AND DISCLOSURES RELATED TO UNCONSOLIDATED FINANCIAL STATEMENTS",
        "Konsolide Finansal Tablolara İlişkin Açıklama ve Dipnotlar",
        "Disclosures and Footnotes on Unconsolidated Financial Statements",
    ):
        assert role_from_title(title) == "notes", title
    # …and the statements themselves must still classify as the statements.
    for title in ("Konsolide Olmayan Finansal Tablolar",
                  "Unconsolidated Interim Financial Statements"):
        assert role_from_title(title) == "financial_statements", title
    # Neighbours that also carry disclosure words keep their own roles.
    assert role_from_title("Other Explanations") == "other_explanations"
    assert role_from_title("Muhasebe Politikalarına İlişkin Açıklamalar") == \
        "accounting_policies"


def test_disclosure_variants_keep_their_own_roles():
    """Broadening `notes` to any disclosure word regressed GARANTİ's §6 'Other
    Disclosures on Activities' into a second §5; and PASHA's §5 title is
    captured truncated at '…TABLOLARA İLİŞKİN', where the Turkish dative is the
    whole discriminator."""
    assert role_from_title("Other Disclosures on Activities") == "other_explanations"
    assert role_from_title("KONSOLİDE OLMAYAN FİNANSAL TABLOLARA İLİŞKİN") == "notes"
    assert role_from_title(
        "Consolidated Financial Position and Results of Operations and Risk Management"
    ) == "risk"


# --- heading hierarchy ------------------------------------------------------

def test_heading_path_is_the_full_path_not_the_leaf():
    """A bare "1" cannot say whether the block sits under I.a or under II.d, and
    two sibling "1."s in different parents were indistinguishable."""
    stack: list[str] = []
    assert _push_path(stack, "I", 5) == ["I"]
    assert _push_path(stack, "a", 5) == ["I", "a"]
    assert _push_path(stack, "1", 5) == ["I", "a", "1"]
    # A sibling at letter depth truncates the deeper levels.
    assert _push_path(stack, "b", 5) == ["I", "b"]
    assert _push_path(stack, "II", 5) == ["II"]


def test_absolute_note_numbering_is_not_re_prefixed():
    """GARANTİ numbers its notes '4.2.7', '5.6.6' — the leading component IS the
    section, so nesting it under the stack would yield '4.4.2.7'."""
    stack = ["II", "c"]
    assert _push_path(stack, "4.2.7", 4) == ["2", "7"]


def test_single_letters_that_look_roman_are_letters():
    """'C.' is the third item of a lettered list far more often than 100."""
    assert _marker_depth("I") == 1
    assert _marker_depth("VIII") == 1
    assert _marker_depth("C") == 2
    assert _marker_depth("D") == 2
    assert _marker_depth("a") == 2
    assert _marker_depth("7") == 3


def test_abbreviations_do_not_disqualify_a_heading():
    """The run-on guard counted '. ' as a sentence break, so 'T.C.' looked like
    two sentences — and Turkish bank filings are full of 'T.C.' and 'A.Ş.'.
    This suppressed a whole level of headings fleet-wide."""
    lines = [mkline("a. Nakit degerler ve T.C. Merkez Bankasi Hesabi ile T.C. "
                    "Merkez Bankasi hesabi icerigine iliskin bilgiler:")]
    _mark_headings(lines)
    assert lines[0].is_heading and lines[0].marker == "a"
    # A genuine run-on is still not a heading.
    runon = [mkline("1. Banka faaliyetlerine devam etmektedir. Ayrica donem "
                    "icinde herhangi bir degisiklik olmamistir")]
    _mark_headings(runon)
    assert not runon[0].is_heading


def test_decimal_marker_without_a_trailing_period_is_a_heading():
    """GARANTİ prints '4.2.7 Movements in value adjustments' with no trailing
    period, which left 340 of its 478 blocks with no heading at all."""
    lines = [mkline("4.2.7 Movements in value adjustments and provisions")]
    _mark_headings(lines)
    assert lines[0].is_heading and lines[0].marker == "4.2.7"


def test_a_date_does_not_open_a_heading():
    """Relaxing the trailing period for decimals made '31.12.2024 Toplam …' a
    heading, and the date became four levels of hierarchy."""
    lines = [mkline("31.12.2024 Toplam varliklar tutari asagida sunulmustur")]
    _mark_headings(lines)
    assert not lines[0].is_heading
    # A bare year must not open one either.
    year = [mkline("2024 yilinda Banka faaliyetlerine devam etmistir")]
    _mark_headings(year)
    assert not year[0].is_heading
