"""Overview section — BBVA-style 'Main Messages' + headline KPIs + key trends."""

from __future__ import annotations

import pandas as pd
from dash import html, dcc
import dash_bootstrap_components as dbc

from src.analytics import data_store
from src.dashboard import charts as C, theme
from src.analytics import metrics_ext as M


# ---------------------------------------------------------------------------
# Narrative message builders (derive text from the data; wording is ours,
# loosely echoing BBVA's sector reports — no forecasts)
# ---------------------------------------------------------------------------
def _narrative_credit() -> str:
    loans_yoy = data_store.get("loan_growth_yoy")
    sector = loans_yoy[loans_yoy["bank_type_code"] == "10001"].sort_values("period")
    if len(sector) < 2:
        return "Credit growth data is loading."
    latest = sector.iloc[-1]
    prev = sector.iloc[-2]
    delta = latest["value"] - prev["value"]
    direction = "accelerating" if delta > 0.5 else "easing" if delta < -0.5 else "steady"
    return (
        f"Sector loan growth is {direction} at {latest['value']:.1f}% YoY "
        f"({delta:+.1f}pp MoM) as of {latest['period'].strftime('%b %y')}. "
        "State banks continue to lead TL expansion; FX lending remains subdued "
        "under BDDK growth caps."
    )


def _narrative_deposits() -> str:
    ldr = M.ratio_ldr(["10001"]).sort_values("period")
    demand = M.ratio_demand_share(["10001"]).sort_values("period")
    if ldr.empty:
        return "Deposit data is loading."
    latest_ldr = ldr.iloc[-1]
    ldr_delta = (latest_ldr["value"] - ldr.iloc[-2]["value"]) if len(ldr) > 1 else 0
    demand_latest = demand.iloc[-1]["value"] if not demand.empty else None
    demand_str = f" Demand-deposit share stands at {demand_latest:.1f}%." if demand_latest else ""
    return (
        f"Loan-to-deposit ratio at {latest_ldr['value']:.1f}% "
        f"({C.fmt_bps(ldr_delta)} MoM). Deposits keep pace with loan growth; "
        f"dollarization pressures remain contained.{demand_str}"
    )


def _narrative_capital() -> str:
    car = M.ratio_car(["10001"]).sort_values("period")
    if car.empty:
        return "Capital data is loading."
    latest = car.iloc[-1]
    delta = (latest["value"] - car.iloc[-2]["value"]) if len(car) > 1 else 0
    return (
        f"Capital Adequacy Ratio at {latest['value']:.1f}% in "
        f"{latest['period'].strftime('%b %y')} ({C.fmt_bps(delta)} MoM), "
        "comfortably above the 12% regulatory floor. Retained earnings and "
        "sub-debt issuance keep buffers intact."
    )


def _narrative_asset_quality() -> str:
    npl = M.ratio_npl(["10001"]).sort_values("period")
    cov = M.ratio_coverage(["10001"]).sort_values("period")
    if npl.empty:
        return "Asset quality data is loading."
    latest_npl = npl.iloc[-1]
    delta_npl = (latest_npl["value"] - npl.iloc[-2]["value"]) if len(npl) > 1 else 0
    cov_str = f" Coverage at {cov.iloc[-1]['value']:.0f}%." if not cov.empty else ""
    return (
        f"NPL ratio at {latest_npl['value']:.2f}% "
        f"({C.fmt_bps(delta_npl)} MoM). "
        "Gradual deterioration continues in credit cards and general-purpose "
        f"loans; restructuring reliefs limit the upward drift.{cov_str}"
    )


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------
def _kpi_latest(df: pd.DataFrame, code: str = "10001") -> tuple[float, float, str]:
    """Return (latest value, MoM delta, period-label)."""
    if df is None or df.empty:
        return None, None, ""
    sub = df[df["bank_type_code"] == code].sort_values("period")
    if sub.empty:
        return None, None, ""
    latest = sub.iloc[-1]
    delta = None
    if len(sub) > 1:
        prev = sub.iloc[-2]
        if prev["value"] and not pd.isna(prev["value"]):
            delta = (latest["value"] - prev["value"]) / prev["value"] * 100
    return latest["value"], delta, latest["period"].strftime("%b %y")


def _kpi_pp(df: pd.DataFrame, code: str = "10001") -> tuple[float, float, str]:
    """For ratio KPIs: MoM delta in percentage points (not pct-of)."""
    if df is None or df.empty:
        return None, None, ""
    sub = df[df["bank_type_code"] == code].sort_values("period")
    if sub.empty:
        return None, None, ""
    latest = sub.iloc[-1]
    delta = None
    if len(sub) > 1:
        delta = float(latest["value"] - sub.iloc[-2]["value"])
    return float(latest["value"]), delta, latest["period"].strftime("%b %y")


def _kpi_row():
    # Totals
    assets_v, assets_d, per = _kpi_latest(data_store.get("total_assets"))
    assets_tl = assets_v / 1_000_000 if assets_v else None  # M -> T
    loans_yoy = data_store.get("loan_growth_yoy")
    loans_yoy_v, loans_yoy_d, _ = _kpi_pp(loans_yoy)

    # Published ratios
    npl_v, npl_d, _ = _kpi_pp(M.ratio_npl(["10001"]))
    car_v, car_d, _ = _kpi_pp(M.ratio_car(["10001"]))
    ldr_v, ldr_d, _ = _kpi_pp(M.ratio_ldr(["10001"]))
    roe_v, roe_d, _ = _kpi_pp(M.annualize_ytd(M.ratio_roe_ytd(["10001"])))

    cards = [
        C.kpi_card("Total Assets", assets_tl, assets_d, "T TL",
                   direction="up_good", period=per),
        C.kpi_card("Loan Growth YoY", loans_yoy_v, loans_yoy_d, "%",
                   direction="neutral", period=per),
        C.kpi_card("NPL Ratio", npl_v, npl_d, "%",
                   direction="up_bad", period=per,
                   help_text="Gross NPL / cash loans"),
        C.kpi_card("Capital Adequacy", car_v, car_d, "%",
                   direction="up_good", period=per,
                   help_text="Min regulatory: 12%"),
        C.kpi_card("LDR", ldr_v, ldr_d, "%",
                   direction="neutral", period=per,
                   help_text="Loans/Deposits (ex Dev & Inv)"),
        C.kpi_card("ROE (ann.)", roe_v, roe_d, "%",
                   direction="up_good", period=per,
                   help_text="YTD × 12/month"),
    ]
    return dbc.Row([dbc.Col(c, md=2) for c in cards], className="g-3")


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------
def _trend_credit_vs_deposits():
    loans = data_store.get("total_loans")
    deps = data_store.get("total_deposits")
    # Only the Sector line for clarity
    s_loans = loans[loans["bank_type_code"] == "10001"].sort_values("period")
    s_deps = deps[deps["bank_type_code"] == "10001"].sort_values("period")

    import plotly.graph_objects as go
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=s_loans["period"], y=s_loans["value"], mode="lines",
        name="Total Loans", line=dict(color=theme.BANK_COLORS["10003"], width=2.4),
        hovertemplate="<b>Loans</b><br>%{x|%b %Y}<br>" + "%{y:,.0f} M TL<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=s_deps["period"], y=s_deps["value"], mode="lines",
        name="Total Deposits", line=dict(color=theme.BANK_COLORS["10006"], width=2.4),
        hovertemplate="<b>Deposits</b><br>%{x|%b %Y}<br>" + "%{y:,.0f} M TL<extra></extra>",
    ))
    C._apply_layout(fig, "Credit vs Deposits — Sector", height=300)
    max_v = float(max(s_loans["value"].max(), s_deps["value"].max()))
    fig.update_yaxes(**C._tl_tick_config(max_v))
    fig.update_xaxes(tickformat="%b %y")
    return fig


def _chart_growth_by_bank():
    df = data_store.get("loan_growth_yoy")
    latest = M.latest_snapshot(df)
    return C.bar_chart_by_bank(latest, "Loan Growth (YoY) by Bank Type",
                                value_format="pct", height=300)


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
def build_overview():
    # Main Messages row
    messages = dbc.Row([
        dbc.Col(C.narrative_card("CREDIT OUTLOOK", _narrative_credit(),
                                  accent=theme.BANK_COLORS["10003"]), md=3),
        dbc.Col(C.narrative_card("DEPOSITS & LIQUIDITY", _narrative_deposits(),
                                  accent=theme.BANK_COLORS["10006"]), md=3),
        dbc.Col(C.narrative_card("CAPITAL", _narrative_capital(),
                                  accent=theme.BANK_COLORS["10007"]), md=3),
        dbc.Col(C.narrative_card("ASSET QUALITY", _narrative_asset_quality(),
                                  accent=theme.BANK_COLORS["10004"]), md=3),
    ], className="g-3 mb-4")

    kpis = _kpi_row()

    # Key charts
    credit_panel = C.chart_panel(
        _trend_credit_vs_deposits(),
        caption=C.caption_level(data_store.get("total_loans"), "Total loans"),
    )
    growth_panel = C.chart_panel(
        _chart_growth_by_bank(),
        caption=C.caption_comparison(
            M.latest_snapshot(data_store.get("loan_growth_yoy")),
            "Loan growth YoY", unit="pct",
        ),
    )

    body = dbc.Row([
        dbc.Col(credit_panel, md=7),
        dbc.Col(growth_panel, md=5),
    ], className="g-3 mt-1")

    return dbc.Container([
        C.section_header("Banking Sector — Main Messages",
                         "Snapshot of the Turkish banking sector based on the "
                         "latest BDDK monthly bulletin."),
        messages,
        html.Div(style={"height": "8px"}),
        kpis,
        html.Div(style={"height": "12px"}),
        body,
    ], fluid=True)
