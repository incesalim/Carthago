"""Unit tests for the advertised-rates lane (src/rates/scraper.py).

Pure parsing + name-resolution only — no network, so these run under CI's
minimal deps (ruff/pytest/lxml/requests).
"""
from __future__ import annotations

import json

from src.rates.scraper import (
    parse_doviz_loans,
    parse_hangikredi_deposits,
    parse_int,
    parse_pct,
    resolve_ticker,
)


class TestParsePct:
    def test_turkish_decimal_comma(self):
        assert parse_pct("%5,06") == 5.06

    def test_interest_free_campaign(self):
        # doviz renders 0% campaigns as "%0 (Faizsiz)" — must be 0.0, not None.
        assert parse_pct("%0 (Faizsiz)") == 0.0

    def test_dot_decimal(self):
        assert parse_pct("%12.5") == 12.5

    def test_thousands_dot_with_decimal_comma(self):
        assert parse_pct("1.234,56") == 1234.56

    def test_none_and_garbage(self):
        assert parse_pct(None) is None
        assert parse_pct("—") is None


class TestParseInt:
    def test_months_and_days(self):
        assert parse_int("12 Ay") == 12
        assert parse_int("400 Gün") == 400

    def test_none(self):
        assert parse_int(None) is None
        assert parse_int("Vade") is None


class TestResolveTicker:
    def test_plain_names_via_news_aliases(self):
        assert resolve_ticker("Akbank") == "AKBNK"
        assert resolve_ticker("Garanti BBVA") == "GARAN"
        assert resolve_ticker("Yapı Kredi") == "YKBNK"
        assert resolve_ticker("İş Bankası") == "ISCTR"

    def test_new_entrant_banks_are_not_their_former_parent(self):
        # Regression guard: migration 0022 licensed these as banks in their own
        # right. Mapping them to the ex-parent would silently mis-attribute a
        # whole bank's advertised rates.
        assert resolve_ticker("Enpara") == "ENPARA"        # NOT QNBFB
        assert resolve_ticker("Ziraat Dinamik") == "ZIRAATD"  # NOT ZIRAAT
        assert resolve_ticker("Hayat Finans") == "HAYATK"

    def test_digital_subbrands_map_to_parent(self):
        # These are marketing brands with no separate licence.
        assert resolve_ticker("CEPTETEB") == "TEB"
        assert resolve_ticker("ON Dijital") == "ODEA"
        assert resolve_ticker("Odea") == "ODEA"

    def test_outside_universe_resolves_to_none(self):
        assert resolve_ticker("getirfinans") is None
        assert resolve_ticker("Türk Ticaret Bankası") is None


DOVIZ_HTML = """
<html><body><table>
  <thead><tr><th>Banka</th><th>Kredi Adı</th><th>Faiz Oranı</th>
    <th>En Düşük Vade</th><th>En Yüksek Vade</th></tr></thead>
  <tbody>
    <tr><td>Halkbank</td><td>Hızlı Kredi</td><td>%5,06</td><td>1 Ay</td><td>12 Ay</td></tr>
    <tr><td>Enpara</td><td>İhtiyaç Kredisi</td><td>%2,99</td><td>3 Ay</td><td>36 Ay</td></tr>
  </tbody>
</table></body></html>
"""


class TestParseDovizLoans:
    def test_parses_point_rates(self):
        rows = parse_doviz_loans(DOVIZ_HTML, "http://x", "loan_consumer")
        assert len(rows) == 2
        hb = rows[0]
        assert hb["raw_bank_name"] == "Halkbank"
        assert hb["bank_ticker"] == "HALKB"
        assert hb["product_name"] == "Hızlı Kredi"
        assert hb["rate"] == 5.06
        assert hb["rate_basis"] == "monthly"
        assert (hb["term_min"], hb["term_max"], hb["term_unit"]) == (1, 12, "months")
        # A point rate carries no band.
        assert hb["rate_min"] is None and hb["rate_max"] is None
        assert rows[1]["bank_ticker"] == "ENPARA"

    def test_header_row_is_skipped(self):
        rows = parse_doviz_loans(DOVIZ_HTML, "http://x", "loan_consumer")
        assert all(r["raw_bank_name"] != "Banka" for r in rows)

    def test_no_table_returns_empty(self):
        assert parse_doviz_loans("<html><body>no table</body></html>", "u", "loan_consumer") == []


def _next_data(entries: list[dict]) -> str:
    payload = {"props": {"pageProps": {"deposit": {
        "interestRateTable": {"interestRates": entries}}}}}
    return (
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(payload)
        + "</script></body></html>"
    )


class TestParseHangikrediDeposits:
    def test_parses_bands_and_skips_fx(self):
        html = _next_data([
            {"bankName": "Akbank", "currencyId": 1, "minimumRate": 2,
             "maximumRate": 42, "minimumMaturity": 1, "maximumMaturity": 400,
             "minimumAmount": 1000, "maximumAmount": 10000000},
            # currencyId 2 = FX — out of scope this pass, must be skipped.
            {"bankName": "Akbank", "currencyId": 2, "minimumRate": 1,
             "maximumRate": 3, "minimumMaturity": 1, "maximumMaturity": 400,
             "minimumAmount": 1000, "maximumAmount": 10000000},
        ])
        rows = parse_hangikredi_deposits(html, "http://y")
        assert len(rows) == 1
        r = rows[0]
        assert r["bank_ticker"] == "AKBNK"
        assert (r["rate_min"], r["rate_max"]) == (2, 42)
        assert r["rate_basis"] == "annual"
        assert (r["term_min"], r["term_max"], r["term_unit"]) == (1, 400, "days")
        assert (r["amount_min"], r["amount_max"]) == (1000, 10000000)
        # A band carries no point rate.
        assert r["rate"] is None

    def test_missing_next_data_returns_empty(self):
        assert parse_hangikredi_deposits("<html></html>", "u") == []
