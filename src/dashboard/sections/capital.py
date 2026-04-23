"""Capital Adequacy — CAR, equity, leverage, risk-weighted assets."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from dash import html
import dash_bootstrap_components as dbc

from src.analytics import data_store
from src.dashboard import charts as C, metrics_ext as M, theme


SECTOR = "10001"
OWNERSHIP = ["10003", "10004", "10005", "10006", "10007"]
REGULATORY_FLOOR = 12.0   # BDDK minimum Capital Adequacy Ratio


def _panel_car():
    car = M.ratio_car([SECTOR] + OWNERSHIP)

    trend = C.zero_line_trend_chart(car, "Capital Adequacy Ratio (%)",
                                     bank_types=[SECTOR] + OWNERSHIP,
                                     height=280)
    # Add regulatory floor
    trend.add_hline(y=REGULATORY_FLOOR,
                    line=dict(color=theme.NEG_COLOR, width=1.2, dash="dash"),
                    annotation_text="Regulatory floor (12%)",
                    annotation_position="bottom right",
                    annotation_font=dict(color=theme.NEG_COLOR, size=10))

    bar = C.bar_chart_by_bank(M.latest_snapshot(car),
                               "CAR by Bank Type — Latest",
                               value_format="pct", height=280)

    return html.Div([
        C.section_header(
            "Capital Adequacy",
            f"Legal equity over risk-weighted assets. Regulatory floor: {REGULATORY_FLOOR:.0f}%.",
        ),
        dbc.Row([
            dbc.Col(C.chart_panel(trend,
                                   caption=C.caption_comparison(
                                       M.latest_snapshot(car), "CAR", "pct"),
                                   ), md=8),
            dbc.Col(C.chart_panel(bar,
                                   caption="Development & investment banks "
                                           "typically show the highest CAR "
                                           "(niche business model, low RWA)."),
                    md=4),
        ], className="g-3"),
    ])


def _panel_equity():
    equity = M.get_balance_item("%TOPLAM ÖZKAYN%", [SECTOR] + OWNERSHIP)
    yoy = M.yoy_growth(equity)

    level = C.chart_panel(
        C.trend_chart(equity, "Total Equity — Level",
                      value_format="tl", bank_types=[SECTOR], height=280),
        caption=C.caption_level(equity, "Total equity", SECTOR),
    )
    growth = C.chart_panel(
        C.zero_line_trend_chart(yoy, "Equity Growth YoY (%)",
                                bank_types=[SECTOR] + OWNERSHIP, height=280),
        caption=C.caption_growth(yoy, "Equity growth", SECTOR),
    )

    # Leverage ratio: total liabilities / total equity (from Table 15)
    leverage = M.get_published_ratio(
        "Yabancı Kaynaklar / Toplam Özkaynaklar%",
        bank_types=[SECTOR] + OWNERSHIP,
    )
    leverage_chart = C.chart_panel(
        C.trend_chart(leverage, "Liabilities / Equity (%)",
                      value_format="pct",
                      bank_types=[SECTOR] + OWNERSHIP, height=280),
        caption=C.caption_comparison(M.latest_snapshot(leverage),
                                      "Leverage", "pct"),
    )

    return html.Div([
        C.section_header(
            "Equity & Leverage",
            "Equity base growth and balance-sheet leverage.",
        ),
        dbc.Row([
            dbc.Col(level, md=4),
            dbc.Col(growth, md=4),
            dbc.Col(leverage_chart, md=4),
        ], className="g-3"),
    ], className="mt-4")


def _panel_rwa():
    """Risk-weighted assets (net / gross) — a view on risk calibration."""
    rwa = M.get_published_ratio(
        "Risk Ağırlıklı Kalemler Toplamı (Net) / Risk Ağırlıklı Kalemler Toplamı (Brüt)%",
        bank_types=[SECTOR] + OWNERSHIP,
    )
    chart = C.chart_panel(
        C.trend_chart(rwa, "RWA Net / Gross (%)",
                      value_format="pct",
                      bank_types=[SECTOR] + OWNERSHIP, height=280),
        caption="Lower ratio = heavier RWA reduction via credit-mitigation.",
    )
    return html.Div([
        C.section_header(
            "Risk-Weighted Assets",
            "RWA calibration — net-to-gross captures credit-risk mitigation.",
        ),
        dbc.Row([dbc.Col(chart, md=12)], className="g-3"),
    ], className="mt-4")


def _panel_cet1():
    """CET 1 Ratio — BDDK other_data Table 12. BBVA Charts 69 + 71."""
    cet1 = M.ratio_cet1([SECTOR] + OWNERSHIP)
    car = M.ratio_car([SECTOR] + OWNERSHIP)

    trend = C.trend_chart(cet1, "CET 1 Ratio (%)",
                          value_format="pct",
                          bank_types=[SECTOR] + OWNERSHIP,
                          height=280)
    # Regulatory minimums
    trend.add_hline(y=8.5,
                    line=dict(color=theme.NEG_COLOR, width=1.0, dash="dash"),
                    annotation_text="CET1 min 8.5%",
                    annotation_position="bottom right",
                    annotation_font=dict(color=theme.NEG_COLOR, size=10))
    trend.add_hline(y=12.0,
                    line=dict(color=theme.WARN_COLOR, width=1.0, dash="dot"),
                    annotation_text="Local min 12%",
                    annotation_position="top right",
                    annotation_font=dict(color=theme.WARN_COLOR, size=10))

    # Side-by-side with CAR for context
    bar = C.bar_chart_by_bank(M.latest_snapshot(cet1),
                               "CET 1 by Bank Type — Latest",
                               value_format="pct", height=280)

    return html.Div([
        C.section_header("CET 1 — Core Tier 1 Capital Ratio",
            "From BDDK Table 12 (other_data). Values stored as integers; for "
            "2-decimal precision re-parse the raw JSON cache."),
        dbc.Row([
            dbc.Col(C.chart_panel(trend,
                caption=C.caption_comparison(M.latest_snapshot(cet1), "CET 1", "pct")),
                md=8),
            dbc.Col(C.chart_panel(bar,
                caption="Sector ~13%, well above 8.5% regulatory minimum."),
                md=4),
        ], className="g-3"),
    ], className="mt-4")


def build_capital():
    return dbc.Container([
        _panel_car(),
        _panel_cet1(),
        _panel_equity(),
        _panel_rwa(),
        html.Div(style={"height": "24px"}),
    ], fluid=True)
