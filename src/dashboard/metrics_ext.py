"""Extra metric queries and transformations the dashboard needs on top of
the shared data_store. Pulls directly from SQLite where appropriate.

Every function here returns a DataFrame with the standard shape:
  columns = [year, month, period, bank_type_code, bank_type, value]
"""

from __future__ import annotations

import sqlite3
import pandas as pd
from pathlib import Path

from src.analytics.metrics_catalog import BANK_TYPES, PRIMARY_BANK_TYPES


DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "bddk_data.db"


# ---------------------------------------------------------------------------
def _query(sql: str, params: tuple = ()) -> pd.DataFrame:
    with sqlite3.connect(DB_PATH) as con:
        df = pd.read_sql_query(sql, con, params=params)
    if not df.empty and "year" in df.columns and "month" in df.columns:
        df["period"] = pd.to_datetime(
            df["year"].astype(str) + "-" + df["month"].astype(str).str.zfill(2) + "-01"
        )
        if "bank_type_code" in df.columns:
            df["bank_type"] = df["bank_type_code"].map(
                lambda c: BANK_TYPES.get(c, {}).get("name", c)
            )
    return df


# ---------------------------------------------------------------------------
# SME / commercial segments (loans tables 6 and 4)
# ---------------------------------------------------------------------------
def get_sme_loans(bank_types: list[str] = None) -> pd.DataFrame:
    """Total SME loans (Toplam KOBİ Kredileri) from Table 6."""
    bt = bank_types or PRIMARY_BANK_TYPES
    q = f"""
    SELECT year, month, bank_type_code, SUM(total_amount) AS value
    FROM loans
    WHERE table_number = 6
      AND item_name LIKE 'Toplam KOBİ Kredileri%'
      AND bank_type_code IN ({_in(bt)})
    GROUP BY year, month, bank_type_code
    ORDER BY year, month, bank_type_code
    """
    return _query(q)


def get_sme_breakdown(bank_type_code: str = "10001") -> dict[str, pd.DataFrame]:
    """Micro / Small / Medium breakdown for one bank type."""
    segments = {
        "Micro": "Mikro İşletmelere%",
        "Small": "Küçük İşletmelere%",
        "Medium": "Orta Büyüklükteki İşletmelere%",
    }
    out = {}
    for label, pattern in segments.items():
        q = """
        SELECT year, month, bank_type_code, SUM(total_amount) AS value
        FROM loans
        WHERE table_number = 6 AND item_name LIKE ? AND bank_type_code = ?
        GROUP BY year, month, bank_type_code
        ORDER BY year, month
        """
        out[label] = _query(q, (pattern, bank_type_code))
    return out


def get_consumer_mix(bank_type_code: str = "10001") -> dict[str, pd.DataFrame]:
    """Consumer credit mix for stacked-area chart."""
    segments = {
        "Housing": "Tüketici Kredileri - Konut",
        "Auto": "Tüketici Kredileri - Taşıt",
        "General Purpose": "Tüketici Kredileri - İhtiyaç",
        "Retail Cards": "Bireysel Kredi Kartları (10+11)%",
    }
    out = {}
    for label, pattern in segments.items():
        q = """
        SELECT year, month, bank_type_code, SUM(total_amount) AS value
        FROM loans
        WHERE table_number = 4 AND item_name LIKE ? AND bank_type_code = ?
        GROUP BY year, month, bank_type_code
        ORDER BY year, month
        """
        out[label] = _query(q, (pattern, bank_type_code))
    return out


# ---------------------------------------------------------------------------
# Published ratios (Table 15 — BDDK's official Rasyolar)
# ---------------------------------------------------------------------------
def get_published_ratio(
    name_like: str,
    bank_types: list[str] = None,
    table_number: int = 15,
) -> pd.DataFrame:
    bt = bank_types or PRIMARY_BANK_TYPES
    q = f"""
    SELECT year, month, bank_type_code, ratio_value AS value, item_name
    FROM financial_ratios
    WHERE table_number = {table_number}
      AND item_name LIKE ?
      AND bank_type_code IN ({_in(bt)})
    ORDER BY year, month, bank_type_code
    """
    return _query(q, (name_like,))


# Pre-wired common ratios from Table 15
def ratio_npl(bank_types=None):
    return get_published_ratio("Takipteki Alacaklar (Brüt) / Toplam Nakdi Krediler%", bank_types)


def ratio_ldr(bank_types=None):
    """Loans / Deposits — excluding development & investment banks (sector LDR)."""
    return get_published_ratio(
        "Toplam Nakdi Krediler / Toplam Mevduat (Kalkınma ve Yatırım Bankaları Hariç)%",
        bank_types,
    )


def ratio_coverage(bank_types=None):
    """NPL coverage (loan-loss provisions / gross NPL)."""
    return get_published_ratio(
        "Takipteki Alacaklar Karşılığı / Brüt Takipteki Alacaklar%", bank_types
    )


def ratio_car(bank_types=None):
    """Capital Adequacy Ratio (Yasal Özkaynak / Risk Ağırlıklı Kalemler Toplamı)."""
    return get_published_ratio(
        "Yasal Özkaynak / Risk Ağırlıklı Kalemler Toplamı%", bank_types
    )


def ratio_roa_ytd(bank_types=None):
    """YTD ROA (Net Income / Avg Total Assets) — period-to-date, not annualized."""
    return get_published_ratio(
        "Dönem Net Kârı (Zararı) / Ortalama Toplam Aktifler%", bank_types
    )


def ratio_roe_ytd(bank_types=None):
    """YTD ROE (Net Income / Avg Equity) — period-to-date, not annualized."""
    return get_published_ratio(
        "Dönem Net Kârı (Zararı) / Ortalama Özkaynaklar%", bank_types
    )


def ratio_nim_ytd(bank_types=None):
    """YTD NIM proxy (Net Interest Income / Avg Total Assets)."""
    return get_published_ratio(
        "Net Faiz Geliri (Gideri) / Ortalama Toplam Aktifler%", bank_types
    )


def ratio_demand_share(bank_types=None):
    return get_published_ratio("Vadesiz Mevduat / Toplam Mevduat%", bank_types)


# ---------------------------------------------------------------------------
# Generic growth transforms — MoM and MoM annualized
# ---------------------------------------------------------------------------
def mom_growth(df: pd.DataFrame) -> pd.DataFrame:
    """Compute month-over-month % growth per bank_type_code."""
    if df is None or df.empty:
        return df
    out = []
    for code, sub in df.sort_values("period").groupby("bank_type_code"):
        sub = sub.copy()
        sub["value"] = sub["value"].pct_change() * 100
        out.append(sub)
    return pd.concat(out, ignore_index=True).dropna(subset=["value"])


def mom_annualized(df: pd.DataFrame) -> pd.DataFrame:
    """(1 + MoM%/100)^12 - 1, expressed as %."""
    if df is None or df.empty:
        return df
    out = []
    for code, sub in df.sort_values("period").groupby("bank_type_code"):
        sub = sub.copy()
        r = sub["value"].pct_change()
        sub["value"] = ((1 + r) ** 12 - 1) * 100
        out.append(sub)
    return pd.concat(out, ignore_index=True).dropna(subset=["value"])


def annualize_ytd(df: pd.DataFrame) -> pd.DataFrame:
    """Annualize BDDK Table 15 income-based ratios.

    Table 15 publishes cumulative year-to-date ratios: for month m the
    numerator covers Jan..m of the calendar year. Multiplying by 12/m
    gives a first-order annualized figure (assumes income accrues ~linearly
    over the year). December values are unchanged (12/12 = 1).
    """
    if df is None or df.empty:
        return df
    out = df.copy()
    out["value"] = out["value"] * 12.0 / out["month"].astype(float)
    return out


def yoy_growth(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = []
    for code, sub in df.sort_values("period").groupby("bank_type_code"):
        sub = sub.copy()
        sub["value"] = (sub["value"] / sub["value"].shift(12) - 1) * 100
        out.append(sub)
    return pd.concat(out, ignore_index=True).dropna(subset=["value"])


# ---------------------------------------------------------------------------
# Deposits composition (Table 10: TOPLAM MEVDUAT with maturity split)
# ---------------------------------------------------------------------------
def get_deposit_maturity_mix(bank_type_code: str = "10001") -> dict[str, pd.DataFrame]:
    """Return the maturity composition of TOPLAM MEVDUAT for stacked-area."""
    buckets = {
        "Demand": "demand",
        "≤ 1m": "maturity_1m",
        "1–3m": "maturity_1_3m",
        "3–6m": "maturity_3_6m",
        "6–12m": "maturity_6_12m",
        "> 12m": "maturity_over_12m",
    }
    out = {}
    for label, col in buckets.items():
        q = f"""
        SELECT year, month, bank_type_code, SUM({col}) AS value
        FROM deposits
        WHERE table_number = 10
          AND item_name = 'TOPLAM MEVDUAT'
          AND bank_type_code = ?
        GROUP BY year, month, bank_type_code
        ORDER BY year, month
        """
        out[label] = _query(q, (bank_type_code,))
    return out


def get_domestic_fx_deposits(bank_types: list[str] = None) -> pd.DataFrame:
    """Domestic residents' FX-denominated deposits (DTH)."""
    bt = bank_types or PRIMARY_BANK_TYPES
    q = f"""
    SELECT year, month, bank_type_code, SUM(total_amount) AS value
    FROM deposits
    WHERE table_number = 10
      AND item_name = 'Döviz Tevdiat Hesabı / Katılım Fonları - Yurt İçi Yerleşik'
      AND bank_type_code IN ({_in(bt)})
    GROUP BY year, month, bank_type_code
    ORDER BY year, month, bank_type_code
    """
    return _query(q)


def get_domestic_tl_deposits(bank_types: list[str] = None) -> pd.DataFrame:
    """Domestic residents' TL deposits."""
    bt = bank_types or PRIMARY_BANK_TYPES
    q = f"""
    SELECT year, month, bank_type_code, SUM(total_amount) AS value
    FROM deposits
    WHERE table_number = 10
      AND item_name = 'TP Mevduat / Katılım Fonları - Yurt İçi Yerleşik'
      AND bank_type_code IN ({_in(bt)})
    GROUP BY year, month, bank_type_code
    ORDER BY year, month, bank_type_code
    """
    return _query(q)


# ---------------------------------------------------------------------------
# Balance-sheet direct queries (for equity, NPL amount, etc.)
# ---------------------------------------------------------------------------
def get_balance_item(name_like: str, bank_types: list[str] = None, currency: str = "TOTAL") -> pd.DataFrame:
    bt = bank_types or PRIMARY_BANK_TYPES
    col = {"TL": "amount_tl", "FX": "amount_fx", "TOTAL": "amount_total"}[currency]
    q = f"""
    SELECT year, month, bank_type_code, SUM({col}) AS value
    FROM balance_sheet
    WHERE item_name LIKE ? AND bank_type_code IN ({_in(bt)})
    GROUP BY year, month, bank_type_code
    ORDER BY year, month, bank_type_code
    """
    return _query(q, (name_like,))


# ---------------------------------------------------------------------------
# Consumer NPL segments (Table 4 Takipteki items)
# ---------------------------------------------------------------------------
def get_consumer_npl_segments(bank_type_code: str = "10001") -> dict[str, pd.DataFrame]:
    segments = {
        "Housing": "Takipteki Konut Kredileri",
        "Auto": "Takipteki Taşıt Kredileri",
        "GPL": "Takipteki İhtiyaç Kredileri",
        "Retail Cards": "Takipteki Bireysel Kredi Kartları",
    }
    out = {}
    for label, name in segments.items():
        q = """
        SELECT year, month, bank_type_code, SUM(total_amount) AS value
        FROM loans
        WHERE table_number = 4 AND item_name = ? AND bank_type_code = ?
        GROUP BY year, month, bank_type_code
        ORDER BY year, month
        """
        out[label] = _query(q, (name, bank_type_code))
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _in(codes: list[str]) -> str:
    return ",".join(f"'{c}'" for c in codes)


# ---------------------------------------------------------------------------
# Loans Table 4 — NPL sub-segment ratios
# ---------------------------------------------------------------------------
def _get_loans4_series(item_name: str, bank_type_code: str = "10001",
                       currency: str = "TL") -> pd.DataFrame:
    q = """
    SELECT year, month, bank_type_code, SUM(total_amount) AS value
    FROM loans
    WHERE table_number = 4 AND item_name = ?
      AND bank_type_code = ? AND currency = ?
    GROUP BY year, month, bank_type_code
    ORDER BY year, month
    """
    return _query(q, (item_name, bank_type_code, currency))


def npl_ratio_from_table4(num_item: str, den_item: str,
                          bank_type_code: str = "10001") -> pd.DataFrame:
    """Compute NPL ratio for a sub-segment from Table 4 time series.
    Returns df with columns [period, value] (ratio in %)."""
    num = _get_loans4_series(num_item, bank_type_code)
    den = _get_loans4_series(den_item, bank_type_code)
    if num.empty or den.empty:
        return pd.DataFrame(columns=["period", "value"])
    m = pd.merge(num.rename(columns={"value":"n"}),
                  den.rename(columns={"value":"d"}),
                  on=["year","month","bank_type_code"])
    m["period"] = pd.to_datetime(
        m["year"].astype(str) + "-" + m["month"].astype(str).str.zfill(2) + "-01"
    )
    m["value"] = (m["n"] / m["d"] * 100).where(m["d"] > 0)
    return m[["period","value"]].dropna().sort_values("period").reset_index(drop=True)


def npl_ratio_from_weekly(num_item_id: str, den_item_id: str,
                          bank_type_code: str = "10001",
                          currency: str = "TOTAL") -> pd.DataFrame:
    """NPL ratio derived from weekly_series (for SME/Commercial where
    monthly Table 4 doesn't split by SME)."""
    q = """
    SELECT period_date, value, item_id
    FROM weekly_series
    WHERE item_id IN (?, ?) AND bank_type_code = ? AND currency = ?
    ORDER BY period_date
    """
    df = _query(q, (num_item_id, den_item_id, bank_type_code, currency))
    if df.empty:
        return pd.DataFrame(columns=["period", "value"])
    wide = df.pivot_table(index="period_date", columns="item_id",
                          values="value", aggfunc="sum").reset_index()
    if num_item_id not in wide or den_item_id not in wide:
        return pd.DataFrame(columns=["period", "value"])
    wide = wide.rename(columns={"period_date": "period"})
    wide["value"] = (wide[num_item_id] / wide[den_item_id] * 100).where(wide[den_item_id] > 0)
    return wide[["period","value"]].dropna().sort_values("period").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Income statement — BDDK Table 2 line-item aggregator
# ---------------------------------------------------------------------------
def get_income_item(item_order: int, bank_types: list[str] = None) -> pd.DataFrame:
    """Return YTD values for a specific income_statement line (by item_order)."""
    bt = bank_types or PRIMARY_BANK_TYPES
    q = f"""
    SELECT year, month, bank_type_code, SUM(amount_total) AS value, item_name
    FROM income_statement
    WHERE item_order = ?
      AND bank_type_code IN ({_in(bt)})
    GROUP BY year, month, bank_type_code
    ORDER BY year, month, bank_type_code
    """
    return _query(q, (item_order,))


def sum_income_items(orders: list[int], bank_types: list[str] = None) -> pd.DataFrame:
    """Sum multiple income-statement line-items together (YTD)."""
    frames = [get_income_item(o, bank_types) for o in orders]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame()
    out = frames[0][["year","month","period","bank_type_code","bank_type","value"]].copy()
    for f in frames[1:]:
        out = pd.merge(
            out, f[["year","month","bank_type_code","value"]],
            on=["year","month","bank_type_code"], suffixes=("","_add"),
        )
        out["value"] = out["value"] + out["value_add"]
        out.drop(columns=["value_add"], inplace=True)
    return out


def annualize_ytd_flow(df: pd.DataFrame) -> pd.DataFrame:
    """YTD flow values × 12/month to annualize."""
    if df is None or df.empty:
        return df
    out = df.copy()
    out["value"] = out["value"] * 12.0 / out["month"].astype(float)
    return out


# ---------------------------------------------------------------------------
# other_data lookup (Table 12 — capital adequacy detail)
# ---------------------------------------------------------------------------
def get_other_data_item(table_number: int, item_name_like: str,
                        bank_types: list[str] = None) -> pd.DataFrame:
    """Return a specific metric from `other_data` (stored as value_numeric)."""
    bt = bank_types or PRIMARY_BANK_TYPES
    q = f"""
    SELECT year, month, bank_type_code, value_numeric AS value
    FROM other_data
    WHERE table_number = ? AND item_name LIKE ?
      AND bank_type_code IN ({_in(bt)})
    ORDER BY year, month, bank_type_code
    """
    return _query(q, (table_number, item_name_like))


def ratio_cet1(bank_types=None):
    """CET 1 Ratio from BDDK Table 12 (other_data).

    Note: value_numeric is stored as integer — for decimal precision
    re-parse value_text or the raw JSON cache.
    """
    return get_other_data_item(
        12,
        "Çekirdek Sermaye Yeterliliği Rasyosu%",
        bank_types,
    )


# ---------------------------------------------------------------------------
# TTM (trailing twelve months) helper for YTD flow series
# ---------------------------------------------------------------------------
def ttm_from_ytd(df: pd.DataFrame) -> pd.DataFrame:
    """Convert monthly YTD values into TTM (rolling 12-month) flow.

    Formula per bank_type_code:
        TTM[y,m] = YTD[y,m] + (YTD_fullyear[y-1] - YTD[y-1,m])
    When YTD[y,m] is December of year y, TTM equals the full-year YTD.
    """
    if df is None or df.empty:
        return df
    df = df.sort_values(["bank_type_code","year","month"]).copy()

    def _apply(g):
        g = g.copy().reset_index(drop=True)
        out = []
        # build YTD dict and full-year dict for quick lookup
        ytd = {(r.year, r.month): r.value for r in g.itertuples()}
        fy = {r.year: r.value for r in g.itertuples() if r.month == 12}
        for r in g.itertuples():
            prev_fy = fy.get(r.year - 1)
            prev_ytd_sm = ytd.get((r.year - 1, r.month))
            if prev_fy is not None and prev_ytd_sm is not None:
                out.append(r.value + prev_fy - prev_ytd_sm)
            elif r.month == 12:
                out.append(r.value)           # full-year YTD = TTM
            else:
                out.append(None)              # insufficient history
        g["value"] = out
        return g

    return df.groupby("bank_type_code", group_keys=False).apply(_apply).dropna(subset=["value"])


def latest_snapshot(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    return df[df["period"] == df["period"].max()].copy()


def filter_from(df: pd.DataFrame, start_period: str) -> pd.DataFrame:
    """Trim a time-series df to period >= start_period (e.g. '2024-01')."""
    if df is None or df.empty:
        return df
    cutoff = pd.to_datetime(start_period + "-01") if len(start_period) == 7 else pd.to_datetime(start_period)
    return df[df["period"] >= cutoff]
