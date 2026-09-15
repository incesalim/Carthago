"""Explicit serving-table ownership; audit groups derive from the statement registry."""
from src.audit_reports.registry import AUDIT_TABLES

AUDIT_REFRESH_TABLES = list(dict.fromkeys(AUDIT_TABLES + [
    "bank_audit_expected", "bank_audit_statement_types", "bank_audit_coverage",
]))
BULLETIN_TABLES = ['balance_sheet', 'income_statement', 'loans', 'deposits', 'financial_ratios', 'other_data', 'weekly_series', 'nonbank_balance_sheet', 'evds_series', 'news_items', 'news_item_banks', 'regulation_briefings', 'bank_earnings', 'bank_call_transcripts', 'tbb_digital_stats', 'tbb_acquisition_stats', 'tkbb_digital_stats', 'tkbb_acquisition_stats', 'kap_ownership', 'bank_advertised_rates', 'product_attributes', 'bank_products', 'bank_product_profile', 'release_calendar', 'faaliyet_franchise', 'faaliyet_extractions', 'tefas_manager_daily', 'tefas_category_daily', 'tefas_allocation_daily', 'tefas_top_funds', 'api_series']
ANALYST_TABLES = ["analyst_signals", "analyst_basis_metadata", "analyst_notes"]
LANES = {"bulletin": set(BULLETIN_TABLES), "audit": set(AUDIT_REFRESH_TABLES),
         "analyst": set(ANALYST_TABLES)}
SYNC_TABLES = BULLETIN_TABLES + AUDIT_REFRESH_TABLES + ANALYST_TABLES
TABLE_SETS = {
    "audit": AUDIT_TABLES, "audit-refresh": AUDIT_REFRESH_TABLES,
    "bulletin": BULLETIN_TABLES, "analyst": ANALYST_TABLES,
    "evds": ["evds_series"],
    "news": ["news_items", "news_item_banks", "bank_earnings"],
    "bddk": ["balance_sheet", "income_statement", "loans", "deposits",
             "financial_ratios", "other_data", "weekly_series", "api_series"],
    "regulations": ["regulation_briefings"],
}


def owner(tables: set[str], lane: str | None = None) -> str:
    """Infer only from an explicit table scope, never from snapshot contents."""
    matches = [name for name, owned in LANES.items() if tables and tables <= owned]
    if len(matches) != 1 or (lane is not None and lane != matches[0]):
        raise ValueError("table scope crosses lanes or does not belong to the declared lane")
    return matches[0]
