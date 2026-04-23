"""Deposits & Liquidity — level, composition (TL/FX, maturity), LDR."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from dash import html
import dash_bootstrap_components as dbc

from src.analytics import data_store
from src.dashboard import charts as C, theme
from src.analytics import metrics_ext as M


SECTOR = "10001"
OWNERSHIP = ["10003", "10004", "10005", "10006", "10007"]


def _panel_level_growth():
    deposits = data_store.get("total_deposits")
    yoy = M.yoy_growth(deposits)

    level = C.chart_panel(
        C.trend_chart(deposits, "Total Deposits — Level",
                      value_format="tl", bank_types=[SECTOR], height=280),
        caption=C.caption_level(deposits, "Total deposits", SECTOR),
    )
    growth = C.chart_panel(
        C.zero_line_trend_chart(yoy, "Deposit Growth — YoY (%)",
                                bank_types=[SECTOR] + OWNERSHIP, height=280),
        caption=C.caption_growth(yoy, "Deposit growth", SECTOR),
    )
    bar = C.chart_panel(
        C.bar_chart_by_bank(M.latest_snapshot(yoy),
                            "Deposit Growth YoY by Bank Type",
                            value_format="pct", height=280),
        caption=C.caption_comparison(M.latest_snapshot(yoy),
                                      "Deposit growth", "pct"),
    )

    return html.Div([
        C.section_header(
            "Deposits — Level & Growth",
            "Deposit dynamics across the sector and by ownership type.",
        ),
        dbc.Row([
            dbc.Col(level, md=4),
            dbc.Col(growth, md=4),
            dbc.Col(bar, md=4),
        ], className="g-3"),
    ])


def _panel_currency():
    tl = data_store.get("total_deposits_tl")
    fx = data_store.get("total_deposits_fx")
    fx_share = data_store.get("fx_deposit_share")

    tl_c = C.chart_panel(
        C.trend_chart(tl, "TL Deposits — Level", value_format="tl",
                      bank_types=[SECTOR], height=260),
        caption=C.caption_level(tl, "TL deposits", SECTOR),
    )
    fx_c = C.chart_panel(
        C.trend_chart(fx, "FX Deposits — Level (TL equivalent)",
                      value_format="tl", bank_types=[SECTOR], height=260),
        caption=C.caption_level(fx, "FX deposits", SECTOR),
    )
    share_c = C.chart_panel(
        C.trend_chart(fx_share, "FX Share of Total Deposits (%)",
                      value_format="pct",
                      bank_types=[SECTOR] + OWNERSHIP, height=260),
        caption=C.caption_comparison(M.latest_snapshot(fx_share),
                                      "FX deposit share", "pct"),
    )

    return html.Div([
        C.section_header(
            "Currency Breakdown — Dollarization",
            "TL vs FX deposits. FX share is the residents' dollarization gauge.",
        ),
        dbc.Row([
            dbc.Col(tl_c, md=4),
            dbc.Col(fx_c, md=4),
            dbc.Col(share_c, md=4),
        ], className="g-3"),
    ], className="mt-4")


def _panel_maturity_liquidity():
    # Maturity composition stacked area
    mix = M.get_deposit_maturity_mix(SECTOR)
    mat_fig = C.stacked_area(mix, "Deposit Maturity Composition (Sector)",
                             height=280, value_format="tl")

    # Demand deposit share
    demand = M.ratio_demand_share([SECTOR] + OWNERSHIP)
    demand_fig = C.trend_chart(demand, "Demand Deposit Share (%)",
                                value_format="pct",
                                bank_types=[SECTOR] + OWNERSHIP, height=280)

    # LDR (published)
    ldr = M.ratio_ldr([SECTOR] + OWNERSHIP)
    ldr_fig = C.trend_chart(ldr, "Loan-to-Deposit Ratio (%)",
                             value_format="pct",
                             bank_types=[SECTOR] + OWNERSHIP, height=280)

    return html.Div([
        C.section_header(
            "Maturity & Liquidity",
            "Maturity mix, demand-deposit share, and loan-funding balance.",
        ),
        dbc.Row([
            dbc.Col(C.chart_panel(
                mat_fig,
                caption="Deposits are heavily tilted to short maturities; "
                        "demand and ≤1m together dominate the funding base.",
            ), md=4),
            dbc.Col(C.chart_panel(
                demand_fig,
                caption=C.caption_comparison(M.latest_snapshot(demand),
                                              "Demand-deposit share", "pct"),
            ), md=4),
            dbc.Col(C.chart_panel(
                ldr_fig,
                caption=C.caption_comparison(M.latest_snapshot(ldr),
                                              "LDR", "pct"),
            ), md=4),
        ], className="g-3"),
    ], className="mt-4")


def build_deposits():
    return dbc.Container([
        _panel_level_growth(),
        _panel_currency(),
        _panel_maturity_liquidity(),
        html.Div(style={"height": "24px"}),
    ], fluid=True)
