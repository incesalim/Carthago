"""Offline tests for the KAP *disclosure* scraper (no network).

The lane matched a disclosure to a bank on `stockCodes` alone, and KAP leaves
that field empty for a member with no listed shares. So 23 of our 38 banks were
invisible to it — including every unlisted bank whose 2026Q2 filing the audit
pipeline went on to miss. Measured 2026-08-16: 35 of 38 banks had filed on KAP,
this lane could see 12 of them.

Two properties, and nothing wider:
  1. a financial report from an unlisted member resolves to our ticker;
  2. nothing else from an unlisted member enters the news lane.
"""
from __future__ import annotations

from src.news.sources import kap


def _row(**kw):
    row = {
        "disclosureIndex": 1,
        "stockCodes": "",
        "kapTitle": "",
        "subject": "",
        "publishDate": "13.08.2026 18:30:00",
        "disclosureCategory": "FR",
    }
    row.update(kw)
    return row


# --- title normalisation -----------------------------------------------------

def test_turkish_dotted_i_folds_to_one_key():
    """`'İŞ'.upper()` is already upper; the dotted forms must fold explicitly or
    `TÜRKİYE İŞ BANKASI` never matches the map key built from the same string."""
    assert kap._normalise_title("TÜRKİYE İŞ BANKASI A.Ş.") == "TURKIYE IS BANKASI AS"


def test_punctuation_does_not_decide_a_match():
    assert kap._normalise_title("T.O.M. KATILIM BANKASI A.Ş.") == \
        kap._normalise_title("TOM KATILIM BANKASI A.Ş.")


def test_the_map_covers_the_unlisted_banks_that_file():
    m = kap._member_title_map()
    for title, ticker in [
        ("TÜRKİYE İŞ BANKASI A.Ş.", "ISCTR"),
        ("KUVEYT TÜRK KATILIM BANKASI A.Ş.", "KUVEYT"),
        ("VAKIF KATILIM BANKASI A.Ş.", "VAKIFK"),
        ("HAYAT FİNANS KATILIM BANKASI A.Ş.", "HAYATK"),
        ("DÜNYA KATILIM BANKASI A.Ş.", "DUNYAK"),
        ("T.O.M. KATILIM BANKASI A.Ş.", "TOMK"),
        ("ZİRAAT DİNAMİK BANKA A.Ş.", "ZIRAATD"),
    ]:
        assert m.get(kap._normalise_title(title)) == ticker, title


# --- what the second pass admits ---------------------------------------------

def _tickers(rows, monkeypatch):
    """Run fetch()'s matching over `rows` without touching the network."""
    monkeypatch.setattr(kap, "_post_window", lambda *a, **k: rows)
    return [i.ticker for i in kap.fetch(days_back=1)]


def test_an_unlisted_members_financial_report_is_matched(monkeypatch):
    rows = [_row(kapTitle="KUVEYT TÜRK KATILIM BANKASI A.Ş.",
                 subject="Finansal Rapor")]
    assert _tickers(rows, monkeypatch) == ["KUVEYT"]


def test_an_unlisted_members_other_disclosures_stay_out(monkeypatch):
    """Narrowed on purpose: an unlisted member's bond paperwork is not news, and
    `bank_earnings` only needs the filing."""
    rows = [_row(kapTitle="KUVEYT TÜRK KATILIM BANKASI A.Ş.",
                 subject="Pay Dışında Sermaye Piyasası Aracı İşlemlerine İlişkin Bildirim")]
    assert _tickers(rows, monkeypatch) == []


def test_a_subsidiary_with_a_similar_name_is_not_the_bank(monkeypatch):
    """Exact title, not substring: the leasing and portfolio arms file their own
    financial reports on the same days as the bank."""
    rows = [_row(kapTitle="QNB FİNANSAL KİRALAMA A.Ş.", subject="Finansal Rapor"),
            _row(disclosureIndex=2, kapTitle="KUVEYT TÜRK PORTFÖY YÖNETİMİ A.Ş.",
                 subject="Finansal Rapor")]
    assert _tickers(rows, monkeypatch) == []


def test_a_listed_bank_still_matches_on_its_ticker(monkeypatch):
    """Pass 1 is untouched — a listed bank keeps every disclosure kind."""
    rows = [_row(stockCodes="GARAN", kapTitle="TÜRKİYE GARANTİ BANKASI A.Ş.",
                 subject="Kredi Derecelendirmesi")]
    assert _tickers(rows, monkeypatch) == ["GARAN"]


def test_a_non_bank_member_is_still_dropped(monkeypatch):
    rows = [_row(kapTitle="KOTON MAĞAZACILIK TEKSTİL SAN. VE TİC. A.Ş.",
                 subject="Finansal Rapor")]
    assert _tickers(rows, monkeypatch) == []


# --- the 2000-row cap --------------------------------------------------------
#
# byCriteria answers with at most 2000 rows and says nothing about it. A 30-day
# window in filing season asks for ~8,400 and is served a week's worth, so any
# query that wants real history — this lane's backfill, and the filing-season
# comparison — was reading a truncated list and could not tell.

def test_the_window_is_paged_rather_than_asked_for_at_once(monkeypatch):
    calls = []

    def _post(from_date, to_date, *a, **k):
        calls.append((from_date, to_date))
        return []

    monkeypatch.setattr(kap, "_post_window", _post)
    kap.fetch(days_back=30)
    assert len(calls) >= 10, f"30 days must not be one request: {calls}"
    spans = {(t - f).days + 1 for f, t in calls}
    assert max(spans) <= kap._CHUNK_DAYS
    # contiguous and gapless, or a filing lands in the seam
    for (_, prev_to), (next_from, _) in zip(calls, calls[1:]):
        assert (next_from - prev_to).days == 1, (prev_to, next_from)


def test_rows_repeated_across_slices_are_not_duplicated(monkeypatch):
    """Every slice returns the same disclosure; it must be stored once."""
    monkeypatch.setattr(
        kap, "_post_window",
        lambda *a, **k: [_row(disclosureIndex=99, stockCodes="AKBNK",
                              subject="Finansal Rapor")])
    assert [i.ticker for i in kap.fetch(days_back=30)] == ["AKBNK"]
