"""Unit tests for the audit-opinion classifier.

Pure text in, structured verdict out — no PDF, no fitz — so these run under CI's
minimal deps (ruff/pytest + stdlib). The fixtures are trimmed but faithful
renderings of the auditor's-report front matter across the four report shapes we
actually see: English/Turkish × audit/review, clean and modified.
"""
from src.audit_reports.audit_opinion import classify_opinion

# --- English, clean --------------------------------------------------------

CLEAN_AUDIT_EN = """
INDEPENDENT AUDITOR'S REPORT
To the General Assembly of Sample Bank A.S.
A. Audit of the Unconsolidated Financial Statements
Opinion
We have audited the accompanying unconsolidated financial statements of Sample
Bank. In our opinion, the accompanying unconsolidated financial statements
present fairly, in all material respects, the financial position of the Bank as
at 31 December 2024 in accordance with the BRSA Accounting Legislation.
Basis for Opinion
We conducted our audit in accordance with the Standards on Independent Auditing.
Güney Bağımsız Denetim ve SMMM A.Ş. — member firm of Ernst & Young.
"""

CLEAN_REVIEW_EN = """
AUDITOR'S REVIEW REPORT ON INTERIM FINANCIAL INFORMATION
Introduction
We have reviewed the unconsolidated balance sheet of Sample Bank at 31 March 2025.
Scope of Review
We conducted our review in accordance with SRE 2410. A review is substantially
less in scope than an audit. Consequently, a review does not provide assurance
that we would become aware of all significant matters. Accordingly, we do not
express an opinion.
Conclusion
Based on our review, nothing has come to our attention that causes us to believe
that the accompanying interim financial information is not prepared, in all
material respects, in accordance with the BRSA Accounting Legislation.
"""

# --- English, qualified ----------------------------------------------------

# ALBRK Q1-2025: a limited-review report with a qualified CONCLUSION. Note the
# review boilerplate "we do not express an opinion" — must NOT read as disclaimer.
QUALIFIED_REVIEW_EN = """
AUDITOR'S REVIEW REPORT ON INTERIM FINANCIAL INFORMATION
We have reviewed the unconsolidated balance sheet at 31 March 2025.
Scope of Review
A review is substantially less in scope than an audit. Accordingly, we do not
express an opinion.
Basis for the Qualified Conclusion
As explained in Section Five Part II.5.b of the Explanations and Notes to the
Unconsolidated Financial Statements, a portion of the free provision amounting to
TL 7,000,000 thousand is reversed in the current period, which was provided by
the Bank management in prior years outside of the requirements of BRSA
Accounting and Financial Reporting Legislation.
Qualified Conclusion
Based on our review, except for the effects of the matter described above,
nothing has come to our attention.
PwC Bağımsız Denetim.
"""

# Annual audit with a qualified OPINION. The phrase "Basis for Qualified Opinion"
# appears twice — once as an in-sentence cross-reference and once as the heading.
QUALIFIED_AUDIT_EN = """
INDEPENDENT AUDITOR'S REPORT
Qualified Opinion
We have audited the accompanying financial statements. In our opinion, except
for the effect of the matter described in the Basis for Qualified Opinion section
below, the accompanying financial statements present fairly, in all material
respects, the financial position of the Bank.
Basis for Qualified Opinion
The Bank reclassified the government bonds cost amounting to TRY 18,965,006
thousand, previously classified under financial assets at fair value.
KPMG — Akis Bağımsız Denetim.
"""

# --- Turkish ---------------------------------------------------------------

CLEAN_AUDIT_TR = """
BAĞIMSIZ DENETÇİ RAPORU
Örnek Bankası A.Ş. Genel Kurulu'na
Olumlu Görüş
Örnek Bankası'nın konsolide olmayan finansal tablolarını denetledik. Görüşümüze
göre, ilişikteki konsolide olmayan finansal tablolar Banka'nın finansal durumunu
tüm önemli yönleriyle gerçeğe uygun bir biçimde sunmaktadır.
"""

# VAKBN Q1-2025 style: qualified review conclusion — "Sınırlı Olumlu Sonuç"
# (limited-positive = qualified), with its "...Dayanağı" basis section.
QUALIFIED_REVIEW_TR = """
SINIRLI DENETİM RAPORU
Ara dönem konsolide olmayan finansal bilgileri sınırlı denetime tabi tuttuk.
Bir bağımsız denetim görüşü bildirmemekteyiz.
Sınırlı Olumlu Sonucun Dayanağı
Konsolide Olmayan Finansal Tablolara İlişkin Açıklama ve Dipnotlar Beşinci Bölüm
II.7'de belirtildiği üzere, serbest karşılık tutarı iptal edilmiştir.
Sınırlı Olumlu Sonuç
Sınırlı denetimimize göre, yukarıda belirtilen husus hariç olmak üzere.
Güney Bağımsız Denetim.
"""

# --- Edge headings ---------------------------------------------------------

UNQUALIFIED_HEADING = """
INDEPENDENT AUDITOR'S REPORT
Unqualified Opinion
We have audited the financial statements and in our opinion they present fairly.
"""

ADVERSE_EN = """
INDEPENDENT AUDITOR'S REPORT
Adverse Opinion
In our opinion, because of the significance of the matter, the financial
statements do not present fairly the financial position of the Bank.
Basis for Adverse Opinion
The Bank has not consolidated a subsidiary it controls.
"""

DISCLAIMER_EN = """
INDEPENDENT AUDITOR'S REPORT
Disclaimer of Opinion
We were engaged to audit the financial statements. We do not express an opinion
because we were unable to obtain sufficient appropriate audit evidence.
"""


def test_clean_audit_en():
    r = classify_opinion(CLEAN_AUDIT_EN, "2024Q4")
    assert r.opinion_type == "clean"
    assert r.report_kind == "audit"
    assert not r.is_modified
    assert r.basis_text is None
    assert r.language == "en"


def test_clean_review_en_is_not_a_disclaimer():
    # "Consequently ... we do not express an opinion" is review boilerplate.
    r = classify_opinion(CLEAN_REVIEW_EN, "2025Q1")
    assert r.opinion_type == "clean", "review boilerplate misread as disclaimer"
    assert r.report_kind == "review"
    assert not r.is_modified


def test_qualified_review_en_captures_free_provision_basis():
    r = classify_opinion(QUALIFIED_REVIEW_EN, "2025Q1")
    assert r.opinion_type == "qualified"
    assert r.report_kind == "review"
    assert r.is_modified
    assert r.basis_text and "free provision" in r.basis_text
    assert r.auditor == "PwC"


def test_qualified_audit_en_basis_is_the_heading_not_the_crossref():
    r = classify_opinion(QUALIFIED_AUDIT_EN, "2024Q4")
    assert r.opinion_type == "qualified"
    assert r.report_kind == "audit"
    # The basis must be the real paragraph (government bonds), NOT the Opinion
    # paragraph's "…present fairly…" that merely references the basis section.
    assert r.basis_text and "government bonds" in r.basis_text
    assert "present fairly" not in r.basis_text
    assert r.auditor == "KPMG"


def test_clean_audit_tr():
    r = classify_opinion(CLEAN_AUDIT_TR, "2024Q4")
    assert r.opinion_type == "clean"
    assert r.report_kind == "audit"
    assert r.language == "tr"


def test_qualified_review_tr_sinirli_olumlu():
    r = classify_opinion(QUALIFIED_REVIEW_TR, "2025Q1")
    assert r.opinion_type == "qualified"
    assert r.report_kind == "review"
    assert r.is_modified
    assert r.basis_text  # the Turkish basis paragraph was captured


def test_unqualified_heading_is_clean_not_qualified():
    # Regression: "Unqualified Opinion" must not match the "qualified" anchor.
    r = classify_opinion(UNQUALIFIED_HEADING, "2024Q4")
    assert r.opinion_type == "clean"


def test_adverse():
    r = classify_opinion(ADVERSE_EN, "2024Q4")
    assert r.opinion_type == "adverse"
    assert r.is_modified


def test_disclaimer_by_explicit_heading():
    r = classify_opinion(DISCLAIMER_EN, "2024Q4")
    assert r.opinion_type == "disclaimer"
    assert r.is_modified


def test_empty_is_unknown():
    for junk in ("", "   ", "no auditor section here at all"):
        r = classify_opinion(junk, "2025Q1")
        assert r.opinion_type == "unknown"
        assert r.is_empty()


def test_period_tiebreaker_when_text_is_ambiguous():
    # No audit/review verb — fall back to the period quarter.
    ambiguous = "Opinion\nThe financial statements present fairly, in all material respects."
    assert classify_opinion(ambiguous, "2024Q4").report_kind == "audit"
    assert classify_opinion(ambiguous, "2025Q1").report_kind == "review"
