"""Offline unit tests for the bank-profile extractor (branches + personnel).

Text fixtures only — no fitz, no PDFs, no network — so the suite runs in CI's
minimal-deps job. Every fixture is a verbatim snippet from a real BRSA audit
report's "Banka Hakkında Genel Bilgi" section (2026Q1), so the tests double as a
regression corpus for the phrasings the fleet actually uses.

The two structural traps this module exists to survive get dedicated tests:
  * "current (prior) noun" — the parenthetical prior-period figure must NOT be
    read as the current one;
  * first-match-then-give-up — "TMS 19 Çalışanlara" must not yield 19 personnel
    and stop; a later valid figure has to win.
"""
from __future__ import annotations

import sqlite3

from src.audit_reports.bank_profile import (
    BankProfile,
    _extract_branches,
    _extract_personnel,
    upsert_profile,
)


def _branches(text: str) -> tuple[int | None, int | None, int | None]:
    p = BankProfile()
    _extract_branches(" ".join(text.split()), p)
    return p.branches_domestic, p.branches_foreign, p.branches_total


def _personnel(text: str) -> int | None:
    p = BankProfile()
    _extract_personnel(" ".join(text.split()), p)
    return p.personnel


# --- Branches: Turkish -----------------------------------------------------

def test_tr_combined_domestic_foreign():
    # TEB — "şubesi" sits between the number and the connector.
    d, f, t = _branches(
        "31 Mart 2026 tarihi itibarıyla Banka'nın yurt içinde 422 şubesi ve "
        "yurt dışında 4 şubesi bulunmaktadır (31 Aralık 2025: 422 yurt içi, 4 "
        "yurt dışı şube).")
    assert (d, f, t) == (422, 4, 426)


def test_tr_combined_with_prior_parens_between_number_and_noun():
    # DENIZ — prior-period parens between each number and "şubesi"; the current
    # figures (576, 2) must win, not the parenthetical priors (574, 2).
    d, f, t = _branches(
        "yurt içindeki 576 (31 Aralık 2025: 574) ve yurt dışındaki 2 "
        "(31 Aralık 2025: 2) şubesi ile hizmet vermekte olan Banka")
    assert (d, f, t) == (576, 2, 578)


def test_tr_domestic_only_paren_fills_total():
    # BURGAN — one domestic figure, paren before "şube"; total mirrors domestic
    # (the UI keys the branch chip off branches_total only), foreign stays NULL.
    d, f, t = _branches(
        "yurt içinde 28 (31 Aralık 2025: 28) şube ile kurumsal ve ticari "
        "bankacılık hizmeti vermektedir")
    assert (d, f, t) == (28, None, 28)


def test_tr_domestic_only_no_space_yurticinde():
    # HSBC — "yurtiçinde" written without a space.
    assert _branches("Banka'nın yurtiçinde 36 şubesi bulunmaktadır "
                     "(31 Aralık 2025: 36 yurtiçinde şube).") == (36, None, 36)


def test_tr_bare_total_verb_anchored():
    # TFKB — "224 (…) şubesi ve …"; DUNYAK — "25 şubesi ve …"; KLNMA — "1 …
    # bulunmaktadır". No domestic/foreign split, so it is stored as the total.
    assert _branches("31 Mart 2026 tarihi itibarıyla 224 (31 Aralık 2025: 224) "
                     "şubesi ve 3,013 personeli ile hizmet vermektedir.") == (None, None, 224)
    assert _branches("Banka 31 Mart 2026 tarihi itibarıyla 25 şubesi ve 540 "
                     "personeli ile faaliyet göstermektedir.") == (None, None, 25)
    assert _branches("Banka'nın Ankara'da faaliyet gösteren 1 şubesi "
                     "bulunmaktadır (31 Aralık 2025: 1 şube).") == (None, None, 1)


def test_tr_total_word_and_derive_foreign():
    # ANADOLU — "olmak üzere toplam 96 şubesi".
    assert _branches("42'si İstanbul'da olmak üzere toplam 96 şubesi ve 1,535 "
                     "personeli bulunmaktadır") == (None, None, 96)
    # ZIRAATK — domestic 231 AND an explicit "toplam 233 şube" ⇒ foreign = 2.
    d, f, t = _branches(
        "Banka, 31 Mart 2026 tarihi itibarıyla yurt içinde 231 şube, yurtdışında "
        "ise faaliyetlerine başlayan Sudan şubesi ve Somali şubesi ile birlikte "
        "toplam 233 şube (31 Aralık 2025: 225 yurt içi, 2 yurtdışı) olarak "
        "faaliyet göstermektedir.")
    assert (d, f, t) == (231, 2, 233)


def test_tr_foreign_date_not_read_as_branch_count():
    # The "27 Ağustos" date after "yurtdışında" must not become 27 foreign
    # branches — the foreign number must sit directly before "şube".
    d, f, t = _branches(
        "yurt içinde 231 şube, yurtdışında ise 27 Ağustos 2020 tarihinde "
        "açılan Sudan şubesi ile faaliyet göstermektedir")
    assert (d, t) == (231, 231) and f is None


# --- Branches: English -----------------------------------------------------

def test_en_total_consisting_of():
    # HALKB.
    assert _branches("the Bank operates with a total of 1.112 branches "
                     "consisting of 1.104 domestic and 8 foreign branches") == (1104, 8, 1112)


def test_en_domestic_foreign_and_local_variant():
    # GARAN ("domestic … foreign") and ALBRK ("local … foreign", with priors).
    assert _branches("provides banking services through 789 domestic branches, "
                     "5 foreign branches and 1 representative office abroad") == (789, 5, 794)
    assert _branches("operating through 223 (December 31, 2025: 223) local "
                     "branches and 3 (December 31, 2025: 2) foreign branches") == (223, 3, 226)


def test_en_turkiye_and_overseas():
    # YKBNK.
    assert _branches("the Bank has 740 branches operating in Türkiye and 1 branch "
                     "in overseas (December 31, 2025 - 739 branches operating in "
                     "Türkiye, 1 branch in overseas)") == (740, 1, 741)


def test_en_domestic_only_and_qnbfb_delayed_branch_word():
    # SKBNK — "239 domestic branches"; QNBFB — "415 domestic (…) … branches".
    assert _branches("As of 31 March 2026, the Bank has 239 domestic branches "
                     "and 3,329 employees") == (239, None, 239)
    assert _branches("the Bank operates through 415 domestic (December 31, 2025 – "
                     "416) and 1 Atatürk Airport Free Trade Zone (December 31, "
                     "2025 – 1) branches") == (415, None, 415)


# --- Personnel -------------------------------------------------------------

def test_ps_personel_sayisi_with_prior_paren():
    # BURGAN — "personel sayısı 1.333 (31 Aralık 2025: 1.335) kişidir".
    assert _personnel("Banka'nın personel sayısı 1.333 (31 Aralık 2025: 1.335) "
                      "kişidir.") == 1333


def test_ps_calisan_sayisi():
    # KLNMA / ZIRAATD — "çalışan sayısı X kişidir".
    assert _personnel("Banka'nın çalışan sayısı 403 kişidir (31 Aralık 2025: 401 "
                      "kişi).") == 403
    assert _personnel("Banka'nın çalışan sayısı 126 kişidir (31 Aralık 2025: "
                      "126).") == 126


def test_ps_number_before_noun_with_prior_paren():
    # VAKIFK — "3.121 (…) personeli"; EMLAK — "1.961 (…) personeli". The current
    # figure wins over the parenthetical prior.
    assert _personnel("3.121 (31 Aralık 2025: 3.103) personeli ile hizmet "
                      "vermektedir") == 3121
    assert _personnel("Banka, 31 Mart 2026 tarihi itibarıyla 1.961 (31 Aralık "
                      "2025: 1.916) personeli ile hizmet vermektedir.") == 1961


def test_ps_calisani_not_tripped_by_tms19_or_toc():
    # FIBA — "toplam 1.631 çalışanı" must be found even though "TMS 19 Çalışanlara"
    # and a TOC line "22 Çalışanların" appear first. 19 and 22 are out-of-band and
    # must be skipped, not accepted-and-stopped.
    assert _personnel(
        "XV. Çalışanların haklarına ilişkin açıklamalar 22 ... TMS 19 "
        "Çalışanlara Sağlanan Faydalar ... 31 Mart 2026 tarihi itibarıyla Banka, "
        "yurt içinde 35 şubesi ve toplam 1.631 çalışanı ile hizmet vermektedir.") == 1631


def test_ps_split_domestic_foreign_sum():
    # ZIRAATK — "yurtiçi çalışan sayısı 3.140 …, yurtdışı çalışan sayısı 15" ⇒ 3155.
    assert _personnel("Banka'nın yurtiçi çalışan sayısı 3.140 (31 Aralık 2025: "
                      "3.140), yurtdışı çalışan sayısı 15'dir.") == 3155


def test_ps_english_employees_with_prior_paren():
    # QNBFB — "10,339 (…) employees" must yield 10339, not the prior 10,413.
    assert _personnel("the Bank has 10,339 (December 31, 2025 – 10,413) "
                      "employees.") == 10339
    # YKBNK.
    assert _personnel("the Bank has 14.653 employees (December 31, 2025 - "
                      "14.637 employees).") == 14653


def test_ps_small_startup_count_label_pattern():
    # ENPARA (brand-new bank) — "personel sayısı 24 (…) kişidir". The anchored
    # label pattern trusts a sub-50 count; a loose number-before would not.
    assert _personnel("31 Aralık 2024 tarihi itibarıyla Banka personel sayısı 24 "
                      "(31 Aralık 2023 – 16) kişidir.") == 24
    assert _personnel("Banka'nın 30 Haziran 2025 tarihi itibarıyla şubesi "
                      "bulunmamaktadır. 30 Haziran 2025 tarihi itibarıyla Banka "
                      "personel sayısı 48 (31 Aralık 2024 – 24) kişidir.") == 48


def test_ps_loose_pattern_keeps_high_floor():
    # A bare "<n> personeli" with a tiny number must NOT be captured (the loose
    # number-before patterns keep the 50 floor against stray small hits).
    assert _personnel("beher çalışma yılı için 30 personeli") is None


def test_ps_english_with_staff_and_number_of():
    # ALBRK — "with 2.787 (…) staff"; COLENDI — "number of our employee is 129".
    assert _personnel("and with 2.787 (December 31, 2025: 2.815) staff as of "
                      "March 31, 2026") == 2787
    assert _personnel("As of 31 March 2026, the number of our employee is 129 "
                      "(31 December 2025: 98).") == 129


def test_activity_report_isbank_en():
    # İşbank's interim activity report: "a total of 1,019 branches and 20,630
    # employees. Of the 1,019 branches, 997 are domestic and 22 are overseas."
    d, f, t = _branches(
        "3. Information about Branches and Personnel: As of 31 March 2026, the Bank "
        "has a total of 1,019 branches and 20,630 employees. Of the 1,019 branches, "
        "997 are domestic and 22 are overseas. Of the overseas branches, 15 operate "
        "in the TRNC; İşbank AG operates with 8 branches in Germany.")
    assert (d, f, t) == (997, 22, 1019)          # subsidiary "8 branches" ignored
    assert _personnel("the Bank has a total of 1,019 branches and 20,630 "
                      "employees.") == 20630


def test_activity_report_kpi_table_tr():
    # AKTIF / DENIZ KPI table: "Şube Sayısı 16 Personel Sayısı 745" (current first).
    assert _branches("Kaldıraç Oranı 7.29 Şube Sayısı 16 Personel Sayısı 745 "
                     "Dönem İçerisinde")[2] == 16
    assert _personnel("Şube Sayısı 578 576 Personel Sayısı 12.050 11.972 ATM "
                      "Sayısı 3.011") == 12050


def test_activity_report_exim_points_and_dunyak():
    # Eximbank: "32 different points, 25 of which are branches and 7 liaison offices".
    assert _branches("provides Banking services at 32 different points, 25 of which "
                     "are branches and 7 liaison offices")[2] == 25
    # DUNYAK: "toplam şube sayısı 1, toplam personel sayısı ise 171".
    assert _branches("31 Mart 2024 itibarıyla Banka'nın toplam şube sayısı 1, "
                     "toplam personel sayısı ise 171'dir.")[2] == 1
    assert _personnel("toplam şube sayısı 1, toplam personel sayısı ise "
                      "171'dir.") == 171


def test_note8_branch_table_header_anchored():
    # Note-VIII "Number/Employees" table: İşbank (EN) and AKTIF (TR). First number
    # = branches, second = staff. Present in year-end PDFs the prose omits.
    d, f, t = _branches("REPRESENTATIVE OFFICES Number Employees Domestic Branches "
                        "(*) 997 20,246 Country of Incorporation Foreign 1 3")
    assert t == 997
    assert _personnel("Number Employees Domestic Branches (*) 997 20,246 Country "
                      "of Incorporation") == 20246
    assert _branches("temsilciliklerine ilişkin açıklamalar Sayı Çalışan sayısı "
                     "Yurtiçi şube 16 747 Bulunduğu ülke")[2] == 16
    assert _personnel("Sayı Çalışan sayısı Yurtiçi şube 16 747 Bulunduğu") == 747


def test_note8_requires_header_no_junk_match():
    # A bare "Domestic Branches N M" WITHOUT the "Number Employees" header (e.g. a
    # loan/geography table row) must NOT be read as a branch/staff count.
    assert _branches("Loans to Domestic Branches 212 606 837 within maturity")[2] is None
    assert _personnel("Residents Abroad Domestic Branches 212 606 total") is None


def test_ps_bbva_group_headcount_not_captured():
    # GARAN — "more than 127 thousand employees" describes the BBVA group, not
    # Garanti; the "thousand" between number and noun blocks the match.
    assert _personnel("operates in more than 25 countries with more than 127 "
                      "thousand employees") is None


# --- Round-trip ------------------------------------------------------------

def test_upsert_roundtrip_and_idempotent():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE bank_audit_profile (bank_ticker TEXT, period TEXT, kind TEXT, "
        "branches_domestic INT, branches_foreign INT, branches_total INT, "
        "personnel INT, PRIMARY KEY (bank_ticker, period, kind))")
    p = BankProfile(branches_domestic=789, branches_foreign=5,
                    branches_total=794, personnel=None)
    upsert_profile(conn, "GARAN", "2026Q1", "unconsolidated", p)
    upsert_profile(conn, "GARAN", "2026Q1", "unconsolidated", p)  # idempotent
    rows = conn.execute(
        "SELECT branches_domestic, branches_foreign, branches_total, personnel "
        "FROM bank_audit_profile").fetchall()
    assert rows == [(789, 5, 794, None)]


def test_is_empty():
    assert BankProfile().is_empty()
    assert not BankProfile(personnel=100).is_empty()
