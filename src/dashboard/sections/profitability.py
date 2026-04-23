"""Profitability — ROE / ROA / NIM / cost efficiency.

BDDK Table 15 publishes income-based ratios as year-to-date (cumulative
Jan..month). For readability we annualize linearly (value × 12 / month),
which assumes roughly even monthly accrual. December values are unchanged.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from dash import html
import dash_bootstrap_components as dbc

from datetime import datetime

from src.analytics import data_store
from src.dashboard import charts as C, theme
from src.analytics import metrics_ext as M
from src.dashboard import evds


SECTOR = "10001"
OWNERSHIP = ["10003", "10004", "10005", "10006", "10007"]


def _panel_roe_roa():
    roe = M.annualize_ytd(M.ratio_roe_ytd([SECTOR] + OWNERSHIP))
    roa = M.annualize_ytd(M.ratio_roa_ytd([SECTOR] + OWNERSHIP))

    roe_chart = C.chart_panel(
        C.zero_line_trend_chart(roe, "ROE — Annualized (%)",
                                bank_types=[SECTOR] + OWNERSHIP, height=280),
        caption=C.caption_comparison(M.latest_snapshot(roe),
                                      "ROE", "pct"),
    )
    roa_chart = C.chart_panel(
        C.zero_line_trend_chart(roa, "ROA — Annualized (%)",
                                bank_types=[SECTOR] + OWNERSHIP, height=280),
        caption=C.caption_comparison(M.latest_snapshot(roa),
                                      "ROA", "pct"),
    )

    return html.Div([
        C.section_header(
            "Returns — Annualized",
            "Return on equity and assets, YTD values scaled to annual.",
        ),
        dbc.Row([
            dbc.Col(roe_chart, md=6),
            dbc.Col(roa_chart, md=6),
        ], className="g-3"),
    ])


def _panel_margin():
    nim = M.annualize_ytd(M.ratio_nim_ytd([SECTOR] + OWNERSHIP))
    interest_income = M.annualize_ytd(M.get_published_ratio(
        "Toplam Faiz Gelirleri / Faiz Getirili Aktifler Ortalaması%",
        bank_types=[SECTOR] + OWNERSHIP,
    ))
    interest_cost = M.annualize_ytd(M.get_published_ratio(
        "Toplam Faiz Giderleri / Faiz Maliyetli Pasifler Ortalaması%",
        bank_types=[SECTOR] + OWNERSHIP,
    ))

    nim_chart = C.chart_panel(
        C.zero_line_trend_chart(nim, "Net Interest Margin — Annualized (%)",
                                bank_types=[SECTOR] + OWNERSHIP, height=280),
        caption=C.caption_comparison(M.latest_snapshot(nim),
                                      "NIM", "pct"),
    )

    # Spread = interest yield - interest cost (both annualized)
    spread = pd.merge(
        interest_income[["period", "bank_type_code", "bank_type", "value"]],
        interest_cost[["period", "bank_type_code", "value"]],
        on=["period", "bank_type_code"], suffixes=("_yld", "_cost"),
    )
    spread["value"] = spread["value_yld"] - spread["value_cost"]
    spread["year"] = spread["period"].dt.year
    spread["month"] = spread["period"].dt.month

    spread_chart = C.chart_panel(
        C.zero_line_trend_chart(spread, "Interest Yield − Cost (pp, annualized)",
                                bank_types=[SECTOR] + OWNERSHIP, height=280),
        caption="Positive = earning more on assets than paying on funding.",
    )

    return html.Div([
        C.section_header(
            "Margins",
            "Net interest margin and yield-cost spread (annualized from Table 15 YTD).",
        ),
        dbc.Row([
            dbc.Col(nim_chart, md=6),
            dbc.Col(spread_chart, md=6),
        ], className="g-3"),
    ], className="mt-4")


def _panel_efficiency():
    # OPEX is a flow-over-stock ratio (YTD) → annualize.
    # Fees/Total Income and NI-income/NI-expense are ratios of flows within
    # the same YTD window → already comparable across months without rescaling.
    opex = M.annualize_ytd(M.get_published_ratio(
        "İşletme Giderleri / Ortalama Toplam Aktifler%",
        bank_types=[SECTOR] + OWNERSHIP,
    ))
    fees_ratio = M.get_published_ratio(
        "Ücret, Komisyon ve Bankacılık Hizmetleri Gelirleri / Toplam Gelirler%",
        bank_types=[SECTOR] + OWNERSHIP,
    )
    non_interest_cover = M.get_published_ratio(
        "Faiz Dışı Gelirler / Faiz Dışı Giderler%",
        bank_types=[SECTOR] + OWNERSHIP,
    )

    opex_chart = C.chart_panel(
        C.trend_chart(opex, "OPEX / Avg Assets (annualized %)",
                      value_format="pct",
                      bank_types=[SECTOR] + OWNERSHIP, height=280),
        caption=C.caption_comparison(M.latest_snapshot(opex),
                                      "OPEX intensity", "pct"),
    )
    fees_chart = C.chart_panel(
        C.trend_chart(fees_ratio,
                      "Fees & Commissions / Total Income (%)",
                      value_format="pct",
                      bank_types=[SECTOR] + OWNERSHIP, height=280),
        caption=C.caption_comparison(M.latest_snapshot(fees_ratio),
                                      "Fee income share", "pct"),
    )
    cover_chart = C.chart_panel(
        C.trend_chart(non_interest_cover,
                      "Non-Interest Income / Non-Interest Expense (%)",
                      value_format="pct",
                      bank_types=[SECTOR] + OWNERSHIP, height=280),
        caption="Above 100% = non-interest income covers OPEX (+ other fee-driven items).",
    )

    return html.Div([
        C.section_header(
            "Cost Efficiency & Non-Interest Income",
            "Operating cost intensity and fee-driven income contribution.",
        ),
        dbc.Row([
            dbc.Col(opex_chart, md=4),
            dbc.Col(fees_chart, md=4),
            dbc.Col(cover_chart, md=4),
        ], className="g-3"),
    ], className="mt-4")


def _panel_revenue_composition():
    """Three time-series: NII/Revenue, Trading&FX/Revenue, Fees YoY (BBVA 66/68/61)."""
    # NII / Revenue and Trading / Revenue: need items 24, 34, 46, 47, 50
    nii  = M.get_income_item(24, [SECTOR] + OWNERSHIP)
    inc34 = M.get_income_item(34, [SECTOR] + OWNERSHIP)
    inc50 = M.get_income_item(50, [SECTOR] + OWNERSHIP)
    trd  = M.get_income_item(46, [SECTOR] + OWNERSHIP)
    fx   = M.get_income_item(47, [SECTOR] + OWNERSHIP)

    def _ratio(num_df, den_frames, pct=True):
        import pandas as pd
        if num_df.empty: return pd.DataFrame()
        total_rev = den_frames[0][["year","month","bank_type_code","value"]].copy()
        total_rev = total_rev.rename(columns={"value":"rev"})
        for f in den_frames[1:]:
            total_rev = pd.merge(total_rev,
                f[["year","month","bank_type_code","value"]].rename(columns={"value":"add"}),
                on=["year","month","bank_type_code"])
            total_rev["rev"] = total_rev["rev"] + total_rev["add"]
            total_rev = total_rev.drop(columns=["add"])
        m = pd.merge(num_df[["year","month","bank_type_code","value","period","bank_type"]],
                     total_rev[["year","month","bank_type_code","rev"]],
                     on=["year","month","bank_type_code"])
        m["value"] = (m["value"] / m["rev"] * (100 if pct else 1)).where(m["rev"] != 0)
        return m.dropna(subset=["value"])

    nii_share = _ratio(nii, [nii, inc34, inc50])
    # Trading&FX = item_46 + item_47 numerator
    import pandas as pd
    trd_fx = pd.merge(trd[["year","month","bank_type_code","value","period","bank_type"]].rename(columns={"value":"t"}),
                       fx[["year","month","bank_type_code","value"]].rename(columns={"value":"f"}),
                       on=["year","month","bank_type_code"])
    trd_fx["value"] = trd_fx["t"] + trd_fx["f"]
    trd_share = _ratio(trd_fx, [nii, inc34, inc50])

    # Fees YoY — (item_27 + item_31) / same_YTD_12m_ago − 1
    fees = M.sum_income_items([27, 31], [SECTOR] + OWNERSHIP)
    fees_yoy = []
    for code in [SECTOR] + OWNERSHIP:
        sub = fees[fees["bank_type_code"] == code].sort_values(["year","month"]).copy()
        sub["value"] = sub["value"] / sub.groupby("month")["value"].shift(1) - 1
        sub["value"] = sub["value"] * 100
        fees_yoy.append(sub)
    fees_yoy_df = pd.concat(fees_yoy, ignore_index=True).dropna(subset=["value"])

    nii_chart = C.chart_panel(
        C.trend_chart(nii_share, "NII / Total Revenue (%)",
                      value_format="pct", bank_types=[SECTOR] + OWNERSHIP, height=280),
        caption=C.caption_comparison(M.latest_snapshot(nii_share), "NII share", "pct"),
    )
    trd_chart = C.chart_panel(
        C.zero_line_trend_chart(trd_share, "Trading + FX / Total Revenue (%)",
                                bank_types=[SECTOR] + OWNERSHIP, height=280),
        caption=C.caption_comparison(M.latest_snapshot(trd_share), "Trading+FX share", "pct"),
    )
    fees_chart = C.chart_panel(
        C.zero_line_trend_chart(fees_yoy_df, "Fees & Commissions — YoY growth (%)",
                                bank_types=[SECTOR] + OWNERSHIP, height=280),
        caption=C.caption_comparison(M.latest_snapshot(fees_yoy_df),
                                      "Fees YoY", "pct"),
    )

    return html.Div([
        C.section_header("Revenue Composition",
                         "Income-mix indicators derived from BDDK Table 2 "
                         "(income_statement). BBVA Charts 61, 66, 68."),
        dbc.Row([
            dbc.Col(nii_chart, md=4),
            dbc.Col(trd_chart, md=4),
            dbc.Col(fees_chart, md=4),
        ], className="g-3"),
    ], className="mt-4")


def _panel_roe_with_cpi():
    """ROE annualized + CPI 12m-avg overlay (BBVA Chart 51)."""
    import pandas as pd
    roe = M.annualize_ytd(M.ratio_roe_ytd([SECTOR, "10003", "10004"]))
    # CPI 12m average
    cpi_raw = evds.fetch_series("TP.FG.J0", "2020-01-01",
                                  datetime.today().strftime("%Y-%m-%d"),
                                  frequency=evds.FREQ_MONTHLY)
    cpi_avg = pd.DataFrame()
    if not cpi_raw.empty:
        s = cpi_raw.sort_values("date").copy()
        s["yoy"] = s["value"] / s["value"].shift(12) - 1
        s["value"] = s["yoy"].rolling(12).mean() * 100
        cpi_avg = s[["date","value"]].dropna()

    fig = go.Figure()
    for code, color, name in [(SECTOR, theme.NEUTRAL_700, "Sector"),
                               ("10003", theme.DATA_1, "Private Deposit"),
                               ("10004", theme.DATA_2, "State Deposit")]:
        sub = roe[roe["bank_type_code"] == code].sort_values("period")
        if sub.empty: continue
        fig.add_trace(go.Scatter(
            x=sub["period"], y=sub["value"], mode="lines",
            name=name, line=dict(color=color, width=2.2),
            hovertemplate=f"<b>{name}</b><br>%{{x|%b %Y}}<br>%{{y:.1f}}%<extra></extra>",
        ))
    if not cpi_avg.empty:
        fig.add_trace(go.Scatter(
            x=cpi_avg["date"], y=cpi_avg["value"], mode="lines",
            name="CPI 12m avg", line=dict(color=theme.DATA_3, width=1.8, dash="dash"),
            hovertemplate="<b>CPI 12m avg</b><br>%{x|%b %Y}<br>%{y:.1f}%<extra></extra>",
        ))
    C._apply_layout(fig, "ROE vs CPI 12-month average (%)", height=320)
    fig.update_yaxes(ticksuffix="%", tickformat=".0f")
    fig.update_xaxes(tickformat="%b %y")
    caption = "ROE annualized (YTD × 12/month). CPI 12m avg is trailing-12-month average of YoY CPI."
    return C.chart_panel(fig, caption=caption)


def _panel_roe_components(bank_type_code: str = "10002"):
    """ROE component decomposition (BBVA Charts 56-58).

    Uses Deposit Banks (10002) by default — matches BBVA's "deposit banks"
    panel per METRICS.md §12. Shows last 3 month-ends stacked-bar.
    """
    import pandas as pd
    # Fetch needed items
    items_needed = {
        "NII":         [24],
        "Fees":        [27, 31],
        "Trading":     [46],
        "Other NII":   [30, 32, 33, 47, 48, 49],
        "OPEX":        [35, 42, 43, 44],
        "Provisions":  [25, 36, 38, 39, 40],
        "Other/tax":   [52],
    }
    eq_bs = M.get_balance_item("%TOPLAM ÖZKAYN%", [bank_type_code])
    eq_bs = eq_bs.sort_values("period").copy()
    # 13-point TTM average of equity
    eq_bs["avg_eq"] = eq_bs["value"].rolling(13, min_periods=6).mean()

    # Fetch each component, compute TTM, divide by rolling avg equity
    buckets = {}
    for name, orders in items_needed.items():
        raw = M.sum_income_items(orders, [bank_type_code])
        if raw.empty:
            continue
        ttm = M.ttm_from_ytd(raw)
        if ttm.empty:
            continue
        m = pd.merge(
            ttm[["period","value","bank_type_code"]],
            eq_bs[["period","avg_eq"]], on="period", how="left",
        )
        m["pct"] = (m["value"] / m["avg_eq"] * 100).where(m["avg_eq"] > 0)
        buckets[name] = m.dropna(subset=["pct"])[["period","pct"]]

    if not buckets:
        return C.chart_panel(C._empty_fig("Insufficient income-statement history"), caption="")

    # Last 3 available periods
    all_periods = sorted(
        set(p for df in buckets.values() for p in df["period"].tolist())
    )[-6:]
    periods = all_periods[-3:]

    fig = go.Figure()
    colors = {
        "NII": theme.DATA_1, "Fees": theme.DATA_2, "Trading": theme.DATA_3,
        "Other NII": theme.DATA_4, "OPEX": theme.DATA_6, "Provisions": theme.DATA_7,
        "Other/tax": theme.MUTED,
    }
    for name, df in buckets.items():
        sub = df[df["period"].isin(periods)].sort_values("period")
        if sub.empty: continue
        fig.add_trace(go.Bar(
            x=[p.strftime("%b %y") for p in sub["period"]],
            y=sub["pct"], name=name,
            marker_color=colors.get(name, theme.MUTED),
            hovertemplate=f"<b>{name}</b><br>%{{x}}<br>%{{y:+.1f}}%<extra></extra>",
        ))
    # Total ROE marker
    roe_totals = {}
    for p in periods:
        total = sum(df[df["period"] == p]["pct"].iloc[0]
                    for df in buckets.values()
                    if not df[df["period"] == p].empty)
        roe_totals[p.strftime("%b %y")] = total
    fig.add_trace(go.Scatter(
        x=list(roe_totals.keys()), y=list(roe_totals.values()),
        mode="markers+text", name="ROE",
        marker=dict(color=theme.TEXT, size=10, symbol="diamond"),
        text=[f"{v:.1f}%" for v in roe_totals.values()],
        textposition="top center",
        textfont=dict(family=theme.FONT_MONO, size=10),
        hovertemplate="<b>ROE total</b><br>%{x}<br>%{y:.1f}%<extra></extra>",
    ))
    fig.update_layout(barmode="relative")
    C._apply_layout(fig,
                    f"ROE Components — TTM, % of avg equity ({bank_type_code})",
                    height=320)
    fig.update_yaxes(ticksuffix="%", tickformat=".0f")
    fig.add_hline(y=0, line=dict(color=theme.MUTED, width=1))
    caption = (
        "Decomposition: NII + Fees + Trading + Other NII + Dividend = revenue; "
        "OPEX + Provisions + Tax = costs. Sum ≈ ROE marker. "
        "FX gains (item 47) are in 'Other NII', not 'Trading', per BBVA convention."
    )
    return C.chart_panel(fig, caption=caption)


def build_profitability():
    return dbc.Container([
        html.Div(
            "Income-based ratios from BDDK Table 15 are published year-to-date. "
            "Values below are annualized (YTD × 12/month), assuming even "
            "monthly accrual. December values are unchanged.",
            style={
                "fontSize": "0.75rem", "color": theme.MUTED,
                "backgroundColor": "#fffbeb", "border": f"1px solid #fcd34d",
                "padding": "8px 12px", "borderRadius": "6px", "marginBottom": "14px",
            },
        ),
        _panel_roe_roa(),
        _panel_roe_with_cpi(),
        _panel_roe_components(),
        _panel_revenue_composition(),
        _panel_margin(),
        _panel_efficiency(),
        html.Div(style={"height": "24px"}),
    ], fluid=True)
