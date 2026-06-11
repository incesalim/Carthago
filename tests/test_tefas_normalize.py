"""Unit tests for TEFAS fund-name normalization (pure functions)."""
from __future__ import annotations

from src.tefas.normalize import (
    ALLOCATION_META_KEYS,
    ASSET_CLASSES,
    ASSET_ROLLUP,
    categorize_fund,
    extract_manager,
    tr_upper,
)


class TestTrUpper:
    def test_dotted_i(self):
        assert tr_upper("hisse senedi") == "HİSSE SENEDİ"

    def test_dotless_i(self):
        assert tr_upper("kıymetli maden") == "KIYMETLİ MADEN"


class TestExtractManager:
    def test_portfoy_prefix(self):
        assert extract_manager("AK PORTFÖY ÇOKLU VARLIK DEĞİŞKEN FON") == "AK PORTFÖY"

    def test_multiword_prefix(self):
        assert (
            extract_manager("YAPI KREDİ PORTFÖY BİRİNCİ FON SEPETİ FONU")
            == "YAPI KREDİ PORTFÖY"
        )

    def test_undotted_portfoy(self):
        assert extract_manager("İŞ PORTFOY PARA PİYASASI FONU") == "İŞ PORTFÖY"

    def test_lowercase_input(self):
        assert extract_manager("iş portföy para piyasası fonu") == "İŞ PORTFÖY"

    def test_emk_pension_company_with_as(self):
        assert (
            extract_manager(
                "ALLIANZ HAYAT VE EMEKLİLİK A.Ş. STANDART EMEKLİLİK YATIRIM FONU"
            )
            == "ALLIANZ HAYAT VE EMEKLİLİK A.Ş."
        )

    def test_emk_without_as_token(self):
        assert (
            extract_manager("ANADOLU HAYAT EMEKLİLİK ALTIN KATILIM EYF")
            == "ANADOLU HAYAT EMEKLİLİK"
        )

    def test_fallback_first_two_tokens(self):
        assert extract_manager("ACME VARLIK FONU") == "ACME VARLIK"

    def test_empty(self):
        assert extract_manager("") == "BİLİNMEYEN"
        assert extract_manager("   ") == "BİLİNMEYEN"


class TestCategorizeFund:
    def test_money_market(self):
        assert categorize_fund("AK PORTFÖY PARA PİYASASI FONU") == "money_market"

    def test_equity(self):
        assert categorize_fund("İŞ PORTFÖY HİSSE SENEDİ FONU") == "equity"

    def test_debt(self):
        assert categorize_fund("ZİRAAT PORTFÖY BORÇLANMA ARAÇLARI FONU") == "debt"

    def test_hedge(self):
        assert categorize_fund("X PORTFÖY SERBEST (TL) FON") == "hedge"

    def test_precious_metals(self):
        assert categorize_fund("QNB PORTFÖY ALTIN FONU") == "precious_metals"

    def test_participation_generic(self):
        assert categorize_fund("ZİRAAT PORTFÖY KATILIM FONU") == "participation"

    def test_katilim_equity_is_equity(self):
        # Specific keywords win over the generic KATILIM bucket.
        assert (
            categorize_fund("ZİRAAT PORTFÖY KATILIM HİSSE SENEDİ FONU") == "equity"
        )

    def test_mixed(self):
        assert categorize_fund("TEB PORTFÖY DEĞİŞKEN FON") == "mixed"

    def test_other(self):
        assert categorize_fund("GARANTİ PORTFÖY BİRİNCİ FON") == "other"


class TestAssetRollup:
    def test_all_values_are_known_classes(self):
        assert set(ASSET_ROLLUP.values()) <= set(ASSET_CLASSES)

    def test_meta_keys_not_in_rollup(self):
        assert not ALLOCATION_META_KEYS & set(ASSET_ROLLUP)

    def test_key_spot_checks(self):
        # Verified against tefas-crawler v0.5.0's legacy field legend.
        assert ASSET_ROLLUP["hs"] == "equity_tr"
        assert ASSET_ROLLUP["yhs"] == "equity_foreign"
        assert ASSET_ROLLUP["dt"] == "gov_debt_tr"
        assert ASSET_ROLLUP["kba"] == "gov_debt_fx"
        assert ASSET_ROLLUP["osdb"] == "corp_debt"
        assert ASSET_ROLLUP["vdm"] == "corp_debt"  # asset-backed, NOT a deposit
        assert ASSET_ROLLUP["tr"] == "money_market"
        assert ASSET_ROLLUP["yyf"] == "fund_units"
        assert ASSET_ROLLUP["kkstl"] == "participation"
