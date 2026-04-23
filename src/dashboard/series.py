"""Canonical series registry — single source of truth for every time series
used by the dashboard.

Rules of the road:
  - Every chart, KPI, and caption references series by **key** (e.g.
    "policy_rate"), NEVER by raw code. If you find yourself typing
    TP.PY.P02.1H in a section file, stop and add/update an entry here.
  - Every entry declares its `source`. Dashboard code dispatches on source
    to pick the right fetcher.
  - Add liberally. Removing later is cheap; re-hunting a series code is not.

Sources:
  - evds        : TCMB EVDS v3 — fetched via src/dashboard/evds.py
  - bddk_weekly : weekly_series table — fetched via weekly_ext.get_series
  - bddk_ratio  : financial_ratios (Table 15) — metrics_ext.get_published_ratio
  - bddk_bs     : balance_sheet — metrics_ext.get_balance_item
  - computed    : derived from other series (growth transforms etc.)
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# EVDS — CBRT interest-rate corridor
# ---------------------------------------------------------------------------
EVDS_CORRIDOR = {
    "policy_rate":      {"source": "evds", "code": "TP.PY.P02.1H",      "label": "Policy Rate",       "kind": "step",
                         "note": "1-week repo OFFER quotation — the MPC-set announced policy rate."},
    "on_lending":       {"source": "evds", "code": "TP.PY.P02.ON",      "label": "ON Lending",        "kind": "step",
                         "note": "Overnight OFFER quotation — corridor upper bound."},
    "on_borrowing":     {"source": "evds", "code": "TP.PY.P01.ON",      "label": "ON Borrowing",      "kind": "step",
                         "note": "Overnight BID quotation — corridor lower bound."},
    "bist_tlref":       {"source": "evds", "code": "TP.BISTTLREF.ORAN", "label": "BIST TRY REF",      "kind": "daily",
                         "note": "BIST TLREF — actual interbank overnight reference rate."},
    "cbrt_funding_cost":{"source": "evds", "code": "TP.APIFON4",        "label": "Effective Funding Cost", "kind": "daily",
                         "note": "CBRT Weighted Avg Cost of Funding. Operational indicator, not the policy rate."},
    "week_auction_avg": {"source": "evds", "code": "TP.PY.P06.1HI",     "label": "1-Week Auction Avg", "kind": "daily",
                         "note": "Realized weighted avg of 1-week deposit auction (sterilisation)."},
}

# ---------------------------------------------------------------------------
# EVDS — TL flow rates (bie_kt100h / bie_mt100h)
# ---------------------------------------------------------------------------
EVDS_TL_RATES = {
    "rate_consumer":           {"source": "evds", "code": "TP.KTFTUK",   "label": "Consumer loan",                "kind": "weekly"},
    "rate_consumer_incl_od":   {"source": "evds", "code": "TP.KTFTUK01", "label": "Consumer loan (incl. overdraft)", "kind": "weekly"},
    "rate_commercial":         {"source": "evds", "code": "TP.KTF18",    "label": "Commercial (ex cards & OD)",   "kind": "weekly"},
    "rate_commercial_all":     {"source": "evds", "code": "TP.KTF17",    "label": "Commercial Loans (all)",       "kind": "weekly"},
    "rate_personal":           {"source": "evds", "code": "TP.KTF10",    "label": "Personal loans",               "kind": "weekly"},
    "rate_vehicle":            {"source": "evds", "code": "TP.KTF11",    "label": "Vehicle loans",                "kind": "weekly"},
    "rate_housing":            {"source": "evds", "code": "TP.KTF12",    "label": "Housing loans",                "kind": "weekly"},
    "rate_deposit_total_tl":   {"source": "evds", "code": "TP.TRY.MT06", "label": "Deposit (total TL)",           "kind": "weekly"},
    "rate_deposit_1m":         {"source": "evds", "code": "TP.TRY.MT01", "label": "Deposit ≤1m",                  "kind": "weekly"},
    "rate_deposit_3m":         {"source": "evds", "code": "TP.TRY.MT02", "label": "Deposit ≤3m",                  "kind": "weekly"},
    "rate_deposit_6m":         {"source": "evds", "code": "TP.TRY.MT03", "label": "Deposit ≤6m",                  "kind": "weekly"},
    "rate_deposit_12m":        {"source": "evds", "code": "TP.TRY.MT04", "label": "Deposit ≤1y",                  "kind": "weekly"},
    "rate_deposit_over_12m":   {"source": "evds", "code": "TP.TRY.MT05", "label": "Deposit >1y",                  "kind": "weekly"},
    # FC loan/deposit rates (Chart 23)
    "rate_fc_loan_usd":        {"source": "evds", "code": "TP.KTF17.USD","label": "Commercial Loan (USD)",        "kind": "weekly"},
    "rate_fc_loan_eur":        {"source": "evds", "code": "TP.KTF17.EUR","label": "Commercial Loan (EUR)",        "kind": "weekly"},
    "rate_fc_dep_usd":         {"source": "evds", "code": "TP.USD.MT06", "label": "Total USD Deposit",            "kind": "weekly"},
    "rate_fc_dep_eur":         {"source": "evds", "code": "TP.EUR.MT06", "label": "Total EUR Deposit",            "kind": "weekly"},
}

# ---------------------------------------------------------------------------
# EVDS — FX / macro context
# ---------------------------------------------------------------------------
EVDS_MACRO = {
    "usd_try":             {"source": "evds", "code": "TP.DK.USD.A", "label": "USD/TRY (buying)",       "kind": "daily"},
    "eur_try":             {"source": "evds", "code": "TP.DK.EUR.A", "label": "EUR/TRY (buying)",       "kind": "daily"},
    # ⚠ TP.AB.N01 unit scaling is off by ~1000× vs BBVA's NIR — do NOT wire
    # as "Net Intl Reserves" until investigated (see METRICS.md Appendix A).
    "net_reserves_raw":    {"source": "evds", "code": "TP.AB.N01",   "label": "Net Intl Reserves (raw, suspect)", "kind": "weekly"},
    # CPI (TurkStat via CBRT mirror) — monthly index, 2003=100
    "cpi_index":           {"source": "evds", "code": "TP.FG.J0",    "label": "CPI (2003=100)",         "kind": "monthly"},
    # Residents' FC deposits (weekly, bie_hpbitablo4, million USD)
    "fc_dep_residents":      {"source": "evds", "code": "TP.HPBITABLO4.2", "label": "Residents total FC deposits", "kind": "weekly"},
    "fc_dep_households":     {"source": "evds", "code": "TP.HPBITABLO4.3", "label": "Households total FC",          "kind": "weekly"},
    "fc_dep_hh_usd":         {"source": "evds", "code": "TP.HPBITABLO4.4", "label": "Households USD",               "kind": "weekly"},
    "fc_dep_hh_eur":         {"source": "evds", "code": "TP.HPBITABLO4.5", "label": "Households EUR (in USD eq)",   "kind": "weekly"},
    "fc_dep_hh_pm":          {"source": "evds", "code": "TP.HPBITABLO4.7", "label": "Households Precious Metals",   "kind": "weekly"},
    # Expectations — Market Participants Survey (monthly)
    "mps_cpi_curr_ye":     {"source": "evds", "code": "TP.PKAUO.S01.D.U", "label": "CPI Exp, current year-end",    "kind": "monthly"},
    "mps_cpi_next_ye":     {"source": "evds", "code": "TP.PKAUO.S01.I.U", "label": "CPI Exp, next year-end",       "kind": "monthly"},
    "mps_cpi_12m":         {"source": "evds", "code": "TP.PKAUO.S01.E.U", "label": "CPI Exp, 12m ahead",           "kind": "monthly"},
    "mps_policy_12m":      {"source": "evds", "code": "TP.PKAUO.S04.D.U", "label": "Policy Rate Exp, 12m ahead",   "kind": "monthly"},
    "hh_inflation_12m":    {"source": "evds", "code": "TP.HANEBEK.HAN14A","label": "Household 12m CPI Expectation","kind": "monthly"},
}

# ---------------------------------------------------------------------------
# EVDS — CBRT Analytical Balance Sheet (daily, bie_abanlbil)
# ---------------------------------------------------------------------------
EVDS_CBRT_BALANCE = {
    "cbrt_total_assets":     {"source": "evds", "code": "TP.AB.A01",  "label": "CBRT Total Assets",          "kind": "daily",
                              "note": "A. TOTAL ASSETS — daily CBRT analytical balance sheet."},
    "cbrt_foreign_assets":   {"source": "evds", "code": "TP.AB.A02",  "label": "CBRT Foreign Assets",        "kind": "daily"},
    "cbrt_domestic_assets":  {"source": "evds", "code": "TP.AB.A03",  "label": "CBRT Domestic Assets",       "kind": "daily"},
    "cbrt_gov_securities":   {"source": "evds", "code": "TP.AB.A051", "label": "CBRT Domestic Securities",   "kind": "daily",
                              "note": "A.2Aa1 — CBRT's holdings of TRY government bonds (outright + legacy)."},
    # Sterilization — unit: thousand TL (divide by 1e6 to get bn TL)
    "cbrt_steril_total":     {"source": "evds", "code": "TP.APIFON2.TOP", "label": "Total Sterilization",    "kind": "daily",
                              "unit_scale": 1e3,  "note": "B. Total sterilization (B1+B2+B3). Raw in thousand TL → /1e3 = bn TL."},
    "cbrt_steril_auction":   {"source": "evds", "code": "TP.APIFON2.IHA", "label": "TL Deposits (auction)",  "kind": "daily",
                              "unit_scale": 1e3,  "note": "B1. Sterilization via TL deposit auction."},
    "cbrt_steril_quotation": {"source": "evds", "code": "TP.APIFON2.KOT", "label": "Quotation",              "kind": "daily",
                              "unit_scale": 1e3,  "note": "B2. Sterilization via quotation."},
    "cbrt_steril_liqbills":  {"source": "evds", "code": "TP.APIFON2.LIK", "label": "Liquidity Bills",        "kind": "daily",
                              "unit_scale": 1e3,  "note": "B3. Sterilization via liquidity bills (new 2025-03+)."},

    # CBRT Net Funding — `TP.APIFON3` is already `APIFON1 − APIFON2` at source.
    "cbrt_net_funding":      {"source": "evds", "code": "TP.APIFON3",  "label": "CBRT Net Funding",          "kind": "daily",
                              "unit_scale": 1e3, "note": "Positive = CBRT net funding market (excess TL liquidity); negative = CBRT net absorbing."},

    # Gold in TONS — BL0021 is in grams (÷1e9 = tons)
    "cbrt_gold_total_tons":  {"source": "evds", "code": "TP.BL0021",   "label": "CBRT Gold Assets (tons)",   "kind": "weekly",
                              "unit_scale": 1e9, "note": "A11 Int'l Standard Gold (net gram); ÷1e9 → tons."},
    "cbrt_gold_banks_tons":  {"source": "evds", "code": "TP.BL0891",   "label": "Banks' Gold at CBRT (tons)","kind": "weekly",
                              "unit_scale": 1e9},

    # International Reserves (weekly Friday, million USD directly)
    "cbrt_gross_reserves":   {"source": "evds", "code": "TP.AB.TOPLAM", "label": "Gross Reserves",            "kind": "weekly",
                              "note": "Official Total International Reserves (gold + FX) in million USD."},
    "cbrt_reserves_gold":    {"source": "evds", "code": "TP.AB.C1",     "label": "Gold Reserves",             "kind": "weekly"},
    "cbrt_reserves_fx":      {"source": "evds", "code": "TP.AB.C2",     "label": "FX Reserves",               "kind": "weekly"},

    # Weekly CBRT balance sheet (raw in thousand TL — use USD/TRY to convert)
    "cbrt_bs_fx_assets":     {"source": "evds", "code": "TP.BL054",     "label": "Total FX Assets (BS)",      "kind": "weekly",
                              "note": "bie_mbblnch P54 — weekly CBRT balance sheet, thousand TL."},
    "cbrt_bs_fx_liabs":      {"source": "evds", "code": "TP.BL122",     "label": "Total FX Liabilities (BS)", "kind": "weekly",
                              "note": "Used with FX assets to derive Net FX position."},
}

# ---------------------------------------------------------------------------
# BDDK weekly bulletin — weekly_series table
#   Chart IDs follow {category}.0.{item} from KiyaslamaJsonGetir.
#   See docs/METRICS.md §10 for the full 124-item catalogue.
# ---------------------------------------------------------------------------
BDDK_WEEKLY = {
    # Category 1 — Krediler (Loans)
    "w_total_loans":       {"source": "bddk_weekly", "item_id": "1.0.1",  "label": "Total Loans"},
    "w_consumer_cards":    {"source": "bddk_weekly", "item_id": "1.0.2",  "label": "Consumer + Retail Cards"},
    "w_consumer":          {"source": "bddk_weekly", "item_id": "1.0.3",  "label": "Consumer Loans"},
    "w_housing":           {"source": "bddk_weekly", "item_id": "1.0.4",  "label": "Housing"},
    "w_auto":              {"source": "bddk_weekly", "item_id": "1.0.5",  "label": "Auto"},
    "w_gpl":               {"source": "bddk_weekly", "item_id": "1.0.6",  "label": "General Purpose (GPL)"},
    "w_retail_cards":      {"source": "bddk_weekly", "item_id": "1.0.8",  "label": "Retail Credit Cards"},
    "w_sme_info":          {"source": "bddk_weekly", "item_id": "1.0.11", "label": "SME (Bilgi)"},
    "w_commercial":        {"source": "bddk_weekly", "item_id": "1.0.12", "label": "Commercial & Other"},
    "w_fx_indexed":        {"source": "bddk_weekly", "item_id": "1.0.22", "label": "FX-Indexed Loans (Bilgi)"},
    # Category 2 — Takipteki Alacaklar (NPL)
    "w_npl_total":         {"source": "bddk_weekly", "item_id": "2.0.1",  "label": "Gross NPL"},
    "w_npl_consumer":      {"source": "bddk_weekly", "item_id": "2.0.2",  "label": "NPL — Consumer"},
    "w_npl_cards":         {"source": "bddk_weekly", "item_id": "2.0.3",  "label": "NPL — Retail Cards"},
    "w_npl_sme":           {"source": "bddk_weekly", "item_id": "2.0.4",  "label": "NPL — SME (Bilgi)"},
    "w_npl_commercial":    {"source": "bddk_weekly", "item_id": "2.0.5",  "label": "NPL — Commercial"},
    # Category 3 — Securities
    "w_securities_total":  {"source": "bddk_weekly", "item_id": "3.0.1",  "label": "Total Securities"},
    # Category 4 — Deposits
    "w_deposits_total":    {"source": "bddk_weekly", "item_id": "4.0.1",  "label": "Total Deposits"},
    "w_deposits_indiv":    {"source": "bddk_weekly", "item_id": "4.0.2",  "label": "Individual Deposits"},
    "w_deposits_demand":   {"source": "bddk_weekly", "item_id": "4.0.3",  "label": "Demand (Individual)"},
    "w_deposits_time":     {"source": "bddk_weekly", "item_id": "4.0.4",  "label": "Time (Individual)"},
    "w_deposits_kkm":      {"source": "bddk_weekly", "item_id": "4.0.12", "label": "KKM (FX-Protected)"},
}

# ---------------------------------------------------------------------------
# BDDK published ratios — financial_ratios Table 15
#   Use SQL LIKE patterns (match the Turkish item_name exactly).
# ---------------------------------------------------------------------------
BDDK_RATIOS = {
    "r_npl_ratio":      {"source": "bddk_ratio", "like": "Takipteki Alacaklar (Brüt) / Toplam Nakdi Krediler%",
                         "label": "NPL Ratio",          "kind": "stock", "direction": "up_bad"},
    "r_coverage":       {"source": "bddk_ratio", "like": "Takipteki Alacaklar Karşılığı / Brüt Takipteki Alacaklar%",
                         "label": "NPL Coverage",       "kind": "stock", "direction": "up_good"},
    "r_car":            {"source": "bddk_ratio", "like": "Yasal Özkaynak / Risk Ağırlıklı Kalemler Toplamı%",
                         "label": "Capital Adequacy",   "kind": "stock", "direction": "up_good"},
    "r_ldr":            {"source": "bddk_ratio", "like": "Toplam Nakdi Krediler / Toplam Mevduat (Kalkınma ve Yatırım Bankaları Hariç)%",
                         "label": "LDR (ex Dev&Inv)",   "kind": "stock", "direction": "neutral"},
    "r_demand_share":   {"source": "bddk_ratio", "like": "Vadesiz Mevduat / Toplam Mevduat%",
                         "label": "Demand-Deposit Share", "kind": "stock", "direction": "neutral"},
    "r_roa_ytd":        {"source": "bddk_ratio", "like": "Dönem Net Kârı (Zararı) / Ortalama Toplam Aktifler%",
                         "label": "ROA (YTD)",          "kind": "ytd",   "direction": "up_good"},
    "r_roe_ytd":        {"source": "bddk_ratio", "like": "Dönem Net Kârı (Zararı) / Ortalama Özkaynaklar%",
                         "label": "ROE (YTD)",          "kind": "ytd",   "direction": "up_good"},
    "r_nim_ytd":        {"source": "bddk_ratio", "like": "Net Faiz Geliri (Gideri) / Ortalama Toplam Aktifler%",
                         "label": "NIM (YTD)",          "kind": "ytd",   "direction": "up_good"},
    "r_opex":           {"source": "bddk_ratio", "like": "İşletme Giderleri / Ortalama Toplam Aktifler%",
                         "label": "OPEX / Avg Assets",  "kind": "ytd",   "direction": "up_bad"},
    "r_fees_share":     {"source": "bddk_ratio", "like": "Ücret, Komisyon ve Bankacılık Hizmetleri Gelirleri / Toplam Gelirler%",
                         "label": "Fees / Total Income","kind": "stock", "direction": "up_good"},
    "r_leverage":       {"source": "bddk_ratio", "like": "Yabancı Kaynaklar / Toplam Özkaynaklar%",
                         "label": "Leverage",           "kind": "stock", "direction": "neutral"},
    "r_rwa_net_gross":  {"source": "bddk_ratio", "like": "Risk Ağırlıklı Kalemler Toplamı (Net) / Risk Ağırlıklı Kalemler Toplamı (Brüt)%",
                         "label": "RWA Net / Gross",    "kind": "stock", "direction": "neutral"},
}

# ---------------------------------------------------------------------------
# BDDK monthly balance-sheet items (via item_name LIKE)
# ---------------------------------------------------------------------------
BDDK_BS = {
    "bs_total_assets":      {"source": "bddk_bs", "like": "%TOPLAM AKT%",          "label": "Total Assets"},
    "bs_total_loans":       {"source": "bddk_bs", "like": "Krediler%",              "label": "Total Loans"},
    "bs_total_deposits":    {"source": "bddk_bs", "like": "%Mevduat%Fon%",          "label": "Total Deposits"},
    "bs_total_equity":      {"source": "bddk_bs", "like": "%TOPLAM ÖZKAYN%",        "label": "Total Equity"},
    "bs_total_liabilities": {"source": "bddk_bs", "like": "%TOPLAM YABANCI KAYN%",  "label": "Total Liabilities"},
    "bs_gross_npl":         {"source": "bddk_bs", "like": "%Takipteki Alacak%",     "label": "Gross NPL (stock)"},
}

# ---------------------------------------------------------------------------
# Merge into one registry
# ---------------------------------------------------------------------------
SERIES: dict[str, dict] = {
    **EVDS_CORRIDOR,
    **EVDS_TL_RATES,
    **EVDS_MACRO,
    **EVDS_CBRT_BALANCE,
    **BDDK_WEEKLY,
    **BDDK_RATIOS,
    **BDDK_BS,
}


def get(key: str) -> dict:
    """Look up a series spec. Raises KeyError if missing (catches typos early)."""
    try:
        return SERIES[key]
    except KeyError:
        raise KeyError(
            f"Unknown series key {key!r}. "
            f"Did you mean one of: {', '.join(sorted(SERIES)[:5])}…?"
        )


def by_source(source: str) -> dict[str, dict]:
    """All entries for a given source (handy when wiring a fetcher)."""
    return {k: v for k, v in SERIES.items() if v.get("source") == source}
