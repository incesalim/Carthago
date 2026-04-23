"""Asset Quality — NPL levels, ratio, coverage, segment breakdown."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from dash import html
import dash_bootstrap_components as dbc

from src.analytics import data_store
from src.dashboard import charts as C, metrics_ext as M, theme


SECTOR = "10001"
OWNERSHIP = ["10003", "10004", "10005", "10006", "10007"]


def _panel_npl_ratio():
    npl = M.ratio_npl([SECTOR] + OWNERSHIP)

    trend = C.chart_panel(
        C.zero_line_trend_chart(npl, "NPL Ratio (%) — Trend",
                                bank_types=[SECTOR] + OWNERSHIP, height=280),
        caption=C.caption_comparison(M.latest_snapshot(npl),
                                      "NPL ratio", "pct"),
    )
    bar = C.chart_panel(
        C.bar_chart_by_bank(M.latest_snapshot(npl),
                            "NPL Ratio by Bank Type — Latest",
                            value_format="pct", height=280),
        caption="State banks sit well below sector average; "
                "participation and dev-inv typically carry the highest.",
    )

    return html.Div([
        C.section_header(
            "Non-Performing Loans",
            "Gross NPL / cash loans. BDDK-published (Table 15).",
        ),
        dbc.Row([
            dbc.Col(trend, md=8),
            dbc.Col(bar, md=4),
        ], className="g-3"),
    ])


def _panel_coverage_npl_level():
    cov = M.ratio_coverage([SECTOR] + OWNERSHIP)
    npl_amount = M.get_balance_item("%Takipteki Alacak%", [SECTOR])

    cov_chart = C.chart_panel(
        C.trend_chart(cov, "Provisions / Gross NPL (%)",
                      value_format="pct",
                      bank_types=[SECTOR] + OWNERSHIP, height=280),
        caption=C.caption_comparison(M.latest_snapshot(cov),
                                      "Coverage", "pct"),
    )
    level_chart = C.chart_panel(
        C.trend_chart(npl_amount, "Gross NPL — Level",
                      value_format="tl", bank_types=[SECTOR], height=280),
        caption=C.caption_level(npl_amount, "Gross NPL", SECTOR),
    )

    return html.Div([
        C.section_header(
            "Provisioning & NPL Stock",
            "Coverage (loan-loss reserves over gross NPL) and absolute NPL level.",
        ),
        dbc.Row([
            dbc.Col(cov_chart, md=7),
            dbc.Col(level_chart, md=5),
        ], className="g-3"),
    ], className="mt-4")


def _panel_consumer_npl():
    segs = M.get_consumer_npl_segments(SECTOR)
    # Stacked area composition
    comp = C.stacked_area(segs, "Consumer NPL — Composition (Sector)",
                          height=280, value_format="tl")

    # YoY growth per segment
    fig = go.Figure()
    for i, (label, df) in enumerate(segs.items()):
        if df is None or df.empty:
            continue
        yoy = M.yoy_growth(df)
        sub = yoy[yoy["bank_type_code"] == SECTOR].sort_values("period")
        fig.add_trace(go.Scatter(
            x=sub["period"], y=sub["value"], mode="lines",
            name=label,
            line=dict(color=theme.CATEGORICAL[i % len(theme.CATEGORICAL)], width=2.2),
            hovertemplate=f"<b>{label}</b><br>%{{x|%b %Y}}<br>" + "%{y:.1f}%<extra></extra>",
        ))
    fig.add_hline(y=0, line=dict(color=theme.MUTED, width=1, dash="dot"))
    C._apply_layout(fig, "Consumer NPL Growth YoY (%)", height=280)
    fig.update_yaxes(ticksuffix="%", tickformat=".0f")
    fig.update_xaxes(tickformat="%b %y")

    return html.Div([
        C.section_header(
            "Consumer NPL Breakdown",
            "Where deterioration is concentrated: credit cards and GPL.",
        ),
        dbc.Row([
            dbc.Col(C.chart_panel(
                comp,
                caption="Retail credit cards and GPL dominate consumer NPL stock.",
            ), md=6),
            dbc.Col(C.chart_panel(
                fig,
                caption="Credit-card delinquencies grow fastest; "
                        "housing NPL remains negligible.",
            ), md=6),
        ], className="g-3"),
    ], className="mt-4")


def _panel_consumer_npl_ratios():
    """NPL ratios for consumer sub-segments (BBVA Chart 44). Monthly, Sector."""
    segs = [
        ("GPL",           "Takipteki İhtiyaç Kredileri",      "Tüketici Kredileri - İhtiyaç",     theme.DATA_1),
        ("Retail Cards",  "Takipteki Bireysel Kredi Kartları","Bireysel Kredi Kartları (10+11)%", theme.DATA_4),
        ("Housing",       "Takipteki Konut Kredileri",        "Tüketici Kredileri - Konut",       theme.DATA_2),
        ("Auto",          "Takipteki Taşıt Kredileri",        "Tüketici Kredileri - Taşıt",       theme.DATA_3),
    ]
    fig = go.Figure()
    latest = {}
    for label, num, den, color in segs:
        # Denominator wildcard-matching items already use LIKE — switch helper here
        if "%" in den:
            import sqlite3, pandas as pd
            with sqlite3.connect(M.DB_PATH) as con:
                n = pd.read_sql_query(
                    "SELECT year, month, SUM(total_amount) AS n FROM loans "
                    "WHERE table_number=4 AND item_name=? AND bank_type_code='10001' AND currency='TL' "
                    "GROUP BY year, month", con, params=(num,))
                d = pd.read_sql_query(
                    "SELECT year, month, SUM(total_amount) AS d FROM loans "
                    "WHERE table_number=4 AND item_name LIKE ? AND bank_type_code='10001' AND currency='TL' "
                    "GROUP BY year, month", con, params=(den,))
            df = pd.merge(n, d, on=["year","month"])
            df["period"] = pd.to_datetime(df["year"].astype(str) + "-" + df["month"].astype(str).str.zfill(2) + "-01")
            df["value"] = (df["n"] / df["d"] * 100).where(df["d"] > 0)
            df = df[["period","value"]].dropna().sort_values("period")
        else:
            df = M.npl_ratio_from_table4(num, den, "10001")
        if df.empty:
            continue
        fig.add_trace(go.Scatter(
            x=df["period"], y=df["value"], mode="lines",
            name=label, line=dict(color=color, width=2.2),
            hovertemplate=f"<b>{label}</b><br>%{{x|%b %Y}}<br>%{{y:.2f}}%<extra></extra>",
        ))
        last = df.iloc[-1]; latest[label] = last["value"]
        fig.add_annotation(
            x=last["period"], y=last["value"],
            text=f"{last['value']:.1f}%", showarrow=False,
            xanchor="left", xshift=6,
            font=dict(color=color, size=10, family=theme.FONT_FAMILY),
        )
    C._apply_layout(fig, "Consumer NPL Ratio by Product (%, Sector)", height=320)
    fig.update_yaxes(ticksuffix="%", tickformat=".1f")
    fig.update_xaxes(tickformat="%b %y")
    caption = " · ".join(f"{k}: {v:.2f}%" for k, v in latest.items())
    return C.chart_panel(fig, caption=caption)


def _panel_commercial_npl_ratios():
    """NPL ratios for commercial sub-segments (BBVA Charts 45, 47). Weekly + Monthly."""
    import pandas as pd
    fig = go.Figure()
    latest = {}

    # Weekly-derived ratios: SME, Commercial (all), Non-SME
    for label, num_id, den_id, color in [
        ("SME",           "2.0.4", "1.0.11", theme.DATA_1),
        ("Commercial",    "2.0.5", "1.0.12", theme.DATA_2),
    ]:
        df = M.npl_ratio_from_weekly(num_id, den_id, "10001", "TOTAL")
        if df.empty: continue
        df = df.copy()
        df["period"] = pd.to_datetime(df["period"])
        fig.add_trace(go.Scatter(
            x=df["period"], y=df["value"], mode="lines",
            name=label, line=dict(color=color, width=2.2),
            hovertemplate=f"<b>{label}</b><br>%{{x|%b %Y}}<br>%{{y:.2f}}%<extra></extra>",
        ))
        last = df.iloc[-1]; latest[label] = last["value"]
        fig.add_annotation(x=last["period"], y=last["value"],
            text=f"{last['value']:.1f}%", showarrow=False,
            xanchor="left", xshift=6,
            font=dict(color=color, size=10, family=theme.FONT_FAMILY))

    # Non-SME: (commercial − SME) / (commercial_loans − SME_loans)
    import sqlite3
    with sqlite3.connect(M.DB_PATH) as con:
        q = """
        SELECT period_date AS period, item_id, value
        FROM weekly_series
        WHERE item_id IN ('1.0.11','1.0.12','2.0.4','2.0.5')
          AND bank_type_code='10001' AND currency='TOTAL'
        """
        raw = pd.read_sql_query(q, con)
    if not raw.empty:
        w = raw.pivot_table(index="period", columns="item_id", values="value", aggfunc="sum").reset_index()
        w["period"] = pd.to_datetime(w["period"])
        w["num"] = w.get("2.0.5", 0) - w.get("2.0.4", 0)
        w["den"] = w.get("1.0.12", 0) - w.get("1.0.11", 0)
        w["value"] = (w["num"] / w["den"] * 100).where(w["den"] > 0)
        w = w[["period","value"]].dropna().sort_values("period")
        if not w.empty:
            fig.add_trace(go.Scatter(
                x=w["period"], y=w["value"], mode="lines",
                name="Non-SME", line=dict(color=theme.DATA_4, width=2.2, dash="dot"),
                hovertemplate="<b>Non-SME</b><br>%{x|%b %Y}<br>%{y:.2f}%<extra></extra>",
            ))
            last = w.iloc[-1]; latest["Non-SME"] = last["value"]
            fig.add_annotation(x=last["period"], y=last["value"],
                text=f"{last['value']:.1f}%", showarrow=False,
                xanchor="left", xshift=6,
                font=dict(color=theme.DATA_4, size=10, family=theme.FONT_FAMILY))

    # Monthly Table-4 derived: Installment Commercial + Corporate Cards
    for label, num, den, color in [
        ("Installment Commercial", "Takipteki Taksitli Ticari Krd. (32+33+34)",
                                   "Taksitli Ticari Krediler (20+21+22)*", theme.DATA_5),
        ("Corporate Cards",        "Takipteki Kurumsal Kredi Kartları",
                                   "Kurumsal Kredi Kartları (28+29)**",    theme.DATA_7),
    ]:
        df = M.npl_ratio_from_table4(num, den, "10001")
        if df.empty: continue
        fig.add_trace(go.Scatter(
            x=df["period"], y=df["value"], mode="lines",
            name=label, line=dict(color=color, width=2.0, dash="dash"),
            hovertemplate=f"<b>{label}</b><br>%{{x|%b %Y}}<br>%{{y:.2f}}%<extra></extra>",
        ))
        last = df.iloc[-1]; latest[label] = last["value"]
        fig.add_annotation(x=last["period"], y=last["value"],
            text=f"{last['value']:.1f}%", showarrow=False,
            xanchor="left", xshift=6,
            font=dict(color=color, size=10, family=theme.FONT_FAMILY))

    C._apply_layout(fig, "Commercial NPL Ratio by Segment (%, Sector)", height=320)
    fig.update_yaxes(ticksuffix="%", tickformat=".1f")
    fig.update_xaxes(tickformat="%b %y")
    caption = " · ".join(f"{k}: {v:.2f}%" for k, v in latest.items())
    return C.chart_panel(fig, caption=caption)


def build_asset_quality():
    return dbc.Container([
        _panel_npl_ratio(),
        _panel_coverage_npl_level(),
        _panel_consumer_npl(),
        html.Div(style={"height": "8px"}),
        C.section_header("NPL Ratios by Sub-segment",
                         "Derived from BDDK Table 4 (consumer) and weekly bulletin "
                         "(SME / Commercial). Shows where delinquency concentrates."),
        dbc.Row([
            dbc.Col(_panel_consumer_npl_ratios(), md=6),
            dbc.Col(_panel_commercial_npl_ratios(), md=6),
        ], className="g-3"),
        html.Div(style={"height": "24px"}),
    ], fluid=True)
