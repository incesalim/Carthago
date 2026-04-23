"""Chart helpers — BBVA-style: narrative-first, clean, direction-aware.

Every plot returns a ready `go.Figure`. Every KPI returns a Dash component.
"""

from __future__ import annotations

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from dash import html, dcc
import dash_bootstrap_components as dbc

from . import theme


# ---------------------------------------------------------------------------
# Number formatting
# ---------------------------------------------------------------------------
def fmt_tl(value: float) -> str:
    """Format a TL million amount as compact: 23.6T, 820B, 450M, 1.2M"""
    if value is None or pd.isna(value):
        return "—"
    # data is in millions TL
    abs_v = abs(value)
    if abs_v >= 1_000_000:       # >= 1 trillion TL
        return f"{value / 1_000_000:.2f}T TL"
    if abs_v >= 1_000:           # >= 1 billion TL
        return f"{value / 1_000:.1f}B TL"
    return f"{value:,.0f}M TL"


def fmt_pct(value: float, decimals: int = 1) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:.{decimals}f}%"


def fmt_bps(delta_pct: float) -> str:
    """Format a difference in percentage points as basis points."""
    if delta_pct is None or pd.isna(delta_pct):
        return "—"
    bps = round(delta_pct * 100)
    sign = "+" if bps > 0 else ""
    return f"{sign}{bps}bps"


def fmt_delta_pct(delta: float, decimals: int = 1) -> str:
    if delta is None or pd.isna(delta):
        return ""
    sign = "+" if delta > 0 else ""
    return f"{sign}{delta:.{decimals}f}%"


# ---------------------------------------------------------------------------
# Date range selector — inline preset buttons above the chart
# ---------------------------------------------------------------------------
MONTHLY_RANGE_BUTTONS = [
    dict(count=6,  label="6M",  step="month", stepmode="backward"),
    dict(count=1,  label="YTD", step="year",  stepmode="todate"),
    dict(count=1,  label="1Y",  step="year",  stepmode="backward"),
    dict(count=3,  label="3Y",  step="year",  stepmode="backward"),
    dict(count=5,  label="5Y",  step="year",  stepmode="backward"),
    dict(step="all", label="MAX"),
]

WEEKLY_RANGE_BUTTONS = [
    dict(count=1,  label="1M",  step="month", stepmode="backward"),
    dict(count=3,  label="3M",  step="month", stepmode="backward"),
    dict(count=6,  label="6M",  step="month", stepmode="backward"),
    dict(count=1,  label="YTD", step="year",  stepmode="todate"),
    dict(count=1,  label="1Y",  step="year",  stepmode="backward"),
    dict(count=3,  label="3Y",  step="year",  stepmode="backward"),
    dict(step="all", label="MAX"),
]


def add_range_selector(fig: go.Figure, granularity: str = "monthly") -> go.Figure:
    """Add a top-right preset date-filter bar (6M / YTD / 1Y / 3Y / 5Y / MAX).

    Call after `_apply_layout`. Requires a date-typed x-axis.
    """
    buttons = MONTHLY_RANGE_BUTTONS if granularity == "monthly" else WEEKLY_RANGE_BUTTONS
    fig.update_xaxes(
        rangeselector=dict(
            buttons=buttons,
            bgcolor=theme.NEUTRAL_100,
            activecolor=theme.ACCENT_TINT,
            bordercolor=theme.BORDER,
            borderwidth=1,
            font=dict(size=10, color=theme.LABEL, family=theme.FONT_FAMILY),
            x=1, xanchor="right", y=1.08, yanchor="bottom",
        ),
        rangeslider=dict(visible=False),
    )
    return fig


# ---------------------------------------------------------------------------
# Axis helpers
# ---------------------------------------------------------------------------
def _tl_tick_config(series_max: float) -> dict:
    """Build Y-axis ticks in trillions TL, ~5 gridlines."""
    if series_max <= 0:
        return dict(tickformat=",.0f")

    if series_max >= 1_000_000:  # >= 1T
        step = _nice_step(series_max / 5) / 1_000_000  # step in T
        max_t = np.ceil(series_max / 1_000_000 / step) * step
        tickvals = list(np.arange(0, max_t + step * 0.5, step) * 1_000_000)
        ticktext = [f"{v / 1_000_000:.1f}T".replace(".0T", "T") for v in tickvals]
        return dict(tickvals=tickvals, ticktext=ticktext)

    if series_max >= 1_000:  # >= 1B
        step = _nice_step(series_max / 5) / 1_000
        max_b = np.ceil(series_max / 1_000 / step) * step
        tickvals = list(np.arange(0, max_b + step * 0.5, step) * 1_000)
        ticktext = [f"{v / 1_000:.0f}B" for v in tickvals]
        return dict(tickvals=tickvals, ticktext=ticktext)

    return dict(tickformat=",.0f")


def _nice_step(approx: float) -> float:
    """Round a desired step to a 'nice' number: 1,2,2.5,5,10 * 10^k"""
    if approx <= 0:
        return 1
    mag = 10 ** np.floor(np.log10(approx))
    norm = approx / mag
    if norm < 1.5:
        step = 1
    elif norm < 2.25:
        step = 2
    elif norm < 3.5:
        step = 2.5
    elif norm < 7.5:
        step = 5
    else:
        step = 10
    return step * mag


# ---------------------------------------------------------------------------
# Layout application
# ---------------------------------------------------------------------------
def _apply_layout(fig: go.Figure, title: str = None, height: int = 320,
                  subtitle: str = None, date_range = "monthly") -> go.Figure:
    """Apply Meridian layout defaults.

    `date_range`: 'monthly' | 'weekly' | False. When truthy, adds the
    preset date-filter bar (6M/YTD/1Y/3Y/5Y/MAX) above the chart. Pass
    False for non-date axes (bar charts, categorical)."""
    defaults = dict(theme.PLOTLY_LAYOUT_DEFAULTS)
    if title:
        defaults["title"] = dict(
            text=f"<b>{title}</b>",
            x=0, xanchor="left", y=0.97, yanchor="top",
            font=dict(size=14, color=theme.TEXT, family=theme.FONT_FAMILY),
            pad=dict(b=6),
        )
    defaults["height"] = height
    fig.update_layout(**defaults)

    if subtitle:
        fig.add_annotation(
            text=subtitle, xref="paper", yref="paper",
            x=0, xanchor="left", y=1.02, yanchor="bottom",
            showarrow=False,
            font=dict(size=11, color=theme.MUTED, family=theme.FONT_FAMILY),
        )

    # Dates/categories in sans; numeric y-ticks in mono
    fig.update_xaxes(
        showgrid=False, showline=False, zeroline=False,
        tickfont=dict(size=11, color=theme.LABEL, family=theme.FONT_FAMILY),
    )
    fig.update_yaxes(
        gridcolor=theme.BORDER, gridwidth=1,
        showline=False, zeroline=False,
        tickfont=dict(size=10, color=theme.LABEL, family=theme.FONT_MONO),
    )

    if date_range:
        add_range_selector(fig, granularity=date_range)
    return fig


def _empty_fig(message: str = "No data available") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, xref="paper", yref="paper",
                       x=0.5, y=0.5, showarrow=False,
                       font=dict(color=theme.MUTED, size=12))
    _apply_layout(fig, date_range=False)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


# ---------------------------------------------------------------------------
# Line / trend chart
# ---------------------------------------------------------------------------
def trend_chart(
    df: pd.DataFrame,
    title: str = None,
    value_format: str = "tl",     # 'tl' | 'pct' | 'number'
    bank_types: list[str] = None, # bank_type_code filter
    height: int = 300,
    hero_code: str = None,        # if set, that series is accented; others go muted
    subtitle: str = None,
    date_range: bool = True,      # show preset date-range buttons
    granularity: str = "monthly", # 'monthly' | 'weekly'
) -> go.Figure:
    """One line per bank_type_code with end-of-line labels (no bottom legend).

    If `hero_code` is passed, that series is drawn thick in its bank color while
    all others fall back to a muted neutral, creating clear narrative focus.
    Expects columns: period, bank_type_code, bank_type, value.
    """
    if df is None or df.empty:
        return _empty_fig()

    codes = bank_types or list(df["bank_type_code"].unique())
    fig = go.Figure()

    max_val = 0.0
    endpoints = []  # (y, name, color, is_hero) — for end-of-line labels
    for code in codes:
        sub = df[df["bank_type_code"] == code].sort_values("period").dropna(subset=["value"])
        if sub.empty:
            continue
        bank_color = theme.BANK_COLORS.get(code, theme.MUTED)
        name = theme.BANK_SHORT.get(sub["bank_type"].iloc[0], sub["bank_type"].iloc[0])

        if hero_code is None:
            color, width = bank_color, 1.5
            is_hero = True
        elif code == hero_code:
            color, width = bank_color, 2.4
            is_hero = True
        else:
            color, width = theme.NEUTRAL_300, 1.2
            is_hero = False

        if value_format == "pct":
            hover = [f"<b>{name}</b><br>{d.strftime('%b %Y')}<br>{v:.2f}%"
                     for d, v in zip(sub["period"], sub["value"])]
        elif value_format == "tl":
            hover = [f"<b>{name}</b><br>{d.strftime('%b %Y')}<br>{fmt_tl(v)}"
                     for d, v in zip(sub["period"], sub["value"])]
        else:
            hover = [f"<b>{name}</b><br>{d.strftime('%b %Y')}<br>{v:,.0f}"
                     for d, v in zip(sub["period"], sub["value"])]

        fig.add_trace(go.Scatter(
            x=sub["period"], y=sub["value"], mode="lines",
            name=name,
            line=dict(color=color, width=width),
            hovertext=hover, hoverinfo="text",
            showlegend=False,
        ))
        if not sub["value"].isna().all():
            max_val = max(max_val, float(sub["value"].max()))

        last = sub.iloc[-1]
        endpoints.append((last["period"], last["value"], name, color, is_hero))

    _apply_layout(fig, title, height=height, subtitle=subtitle,
                  date_range=granularity if date_range else False)
    fig.update_layout(showlegend=False)

    # End-of-line labels — color-matched, nudged right of the last point
    for x, y, name, color, is_hero in endpoints:
        fig.add_annotation(
            x=x, y=y, text=name, showarrow=False,
            xanchor="left", xshift=6,
            font=dict(color=color, size=10, family=theme.FONT_FAMILY),
            opacity=1.0 if is_hero else 0.75,
        )

    if value_format == "pct":
        fig.update_yaxes(ticksuffix="%", tickformat=".0f")
    elif value_format == "tl":
        fig.update_yaxes(**_tl_tick_config(max_val))

    fig.update_xaxes(tickformat="%b %y")
    return fig


def zero_line_trend_chart(
    df: pd.DataFrame,
    title: str = None,
    bank_types: list[str] = None,
    height: int = 300,
    hero_code: str = None,
    subtitle: str = None,
    date_range: bool = True,
    granularity: str = "monthly",
) -> go.Figure:
    """Trend chart for growth rates: includes zero reference line, pct formatting."""
    fig = trend_chart(df, title=title, value_format="pct",
                      bank_types=bank_types, height=height,
                      hero_code=hero_code, subtitle=subtitle,
                      date_range=date_range, granularity=granularity)
    fig.add_hline(y=0, line=dict(color=theme.BORDER_STRONG, width=1, dash="dot"))
    return fig


# ---------------------------------------------------------------------------
# Bar chart (cross-sectional — one period, multiple bank types)
# ---------------------------------------------------------------------------
def bar_chart_by_bank(
    df: pd.DataFrame,
    title: str = None,
    value_format: str = "pct",
    height: int = 280,
) -> go.Figure:
    """Expects a DataFrame with one row per bank_type_code (e.g. latest period)."""
    if df is None or df.empty:
        return _empty_fig()

    df = df.copy().sort_values("value", ascending=False)
    labels = [theme.BANK_SHORT.get(n, n) for n in df["bank_type"]]
    colors = [theme.BANK_COLORS.get(c, theme.MUTED) for c in df["bank_type_code"]]

    if value_format == "pct":
        texts = [fmt_pct(v) for v in df["value"]]
        hover = [f"<b>{n}</b><br>{fmt_pct(v, 2)}" for n, v in zip(df["bank_type"], df["value"])]
    elif value_format == "tl":
        texts = [fmt_tl(v) for v in df["value"]]
        hover = [f"<b>{n}</b><br>{fmt_tl(v)}" for n, v in zip(df["bank_type"], df["value"])]
    else:
        texts = [f"{v:,.0f}" for v in df["value"]]
        hover = [f"<b>{n}</b><br>{v:,.0f}" for n, v in zip(df["bank_type"], df["value"])]

    fig = go.Figure(go.Bar(
        x=labels, y=df["value"], marker_color=colors,
        text=texts, textposition="outside", cliponaxis=False,
        textfont=dict(size=11, color=theme.TEXT, family=theme.FONT_MONO),
        width=0.62,
        hovertext=hover, hoverinfo="text",
    ))
    _apply_layout(fig, title, height=height, date_range=False)
    fig.update_layout(showlegend=False, bargap=0.35)
    if value_format == "pct":
        fig.update_yaxes(ticksuffix="%", tickformat=".0f")
        fig.add_hline(y=0, line=dict(color=theme.BORDER_STRONG, width=1))
    elif value_format == "tl":
        fig.update_yaxes(**_tl_tick_config(df["value"].max()))
    fig.update_xaxes(tickangle=0,
                     tickfont=dict(size=11, color=theme.TEXT, family=theme.FONT_FAMILY))
    return fig


# ---------------------------------------------------------------------------
# Stacked composition (for breakdown views — e.g. consumer mix)
# ---------------------------------------------------------------------------
def stacked_area(
    series: dict[str, pd.DataFrame],   # {label: df(period, value)}
    title: str = None,
    height: int = 300,
    value_format: str = "tl",
    date_range: bool = True,
    granularity: str = "monthly",
) -> go.Figure:
    if not series:
        return _empty_fig()

    fig = go.Figure()
    max_total = 0.0
    for i, (label, df) in enumerate(series.items()):
        if df is None or df.empty:
            continue
        color = theme.CATEGORICAL[i % len(theme.CATEGORICAL)]
        fig.add_trace(go.Scatter(
            x=df["period"], y=df["value"],
            mode="lines", name=label, stackgroup="one",
            line=dict(width=0.5, color=color),
            fillcolor=color,
            hovertemplate=f"<b>{label}</b><br>%{{x|%b %Y}}<br>"
                          + ("%{y:.1f}%" if value_format == "pct"
                             else "%{y:,.0f} M TL") + "<extra></extra>",
        ))
    _apply_layout(fig, title, height=height,
                  date_range=granularity if date_range else False)
    fig.update_xaxes(tickformat="%b %y")
    if value_format == "pct":
        fig.update_yaxes(ticksuffix="%")
    return fig


# ---------------------------------------------------------------------------
# KPI cards — direction aware
# ---------------------------------------------------------------------------
def kpi_card(
    label: str,
    value,
    delta=None,
    unit: str = "",
    direction: str = "up_good",   # 'up_good' | 'up_bad' | 'neutral'
    period: str = None,
    help_text: str = None,
):
    """Render a KPI card. `delta` is the MoM change in the metric's own unit
    (pp for %, % for absolute). `direction` controls color semantics."""
    # Format value
    if isinstance(value, (int, float)) and not pd.isna(value):
        if unit == "%":
            val_str = fmt_pct(value, decimals=2)
        elif unit == "T TL":
            val_str = fmt_tl(value)
        else:
            val_str = f"{value:,.1f}"
            if unit:
                val_str = f"{val_str} {unit}"
    else:
        val_str = "—"

    # Format + color the delta
    delta_el = html.Span("")
    if delta is not None and not pd.isna(delta):
        if unit == "%":
            delta_str = fmt_bps(delta)
            is_positive = delta > 0
        else:
            delta_str = fmt_delta_pct(delta)
            is_positive = delta > 0

        if direction == "up_good":
            color = theme.POS_COLOR if is_positive else theme.NEG_COLOR if delta < 0 else theme.NEUTRAL_COLOR
        elif direction == "up_bad":
            color = theme.NEG_COLOR if is_positive else theme.POS_COLOR if delta < 0 else theme.NEUTRAL_COLOR
        else:
            color = theme.NEUTRAL_COLOR

        arrow = "↑" if (delta or 0) > 0 else "↓" if (delta or 0) < 0 else "→"
        delta_el = html.Div(
            f"{arrow} {delta_str} MoM",
            className="md-kpi-delta",
            style={"color": color, "marginTop": "4px"},
        )

    return dbc.Card(
        dbc.CardBody([
            html.Div([
                html.Div(label, className="md-kpi-label"),
                html.Div(period or "",
                         style={"fontSize": "11px", "color": theme.PLACEHOLDER,
                                "fontFamily": theme.FONT_MONO}) if period else html.Span(),
            ], style={"display": "flex", "justifyContent": "space-between",
                      "alignItems": "baseline", "marginBottom": "8px"}),
            html.Div(val_str, className="md-kpi-value"),
            delta_el,
            html.Div(help_text,
                     style={"fontSize": "11px", "color": theme.MUTED,
                            "marginTop": "6px", "lineHeight": 1.4})
            if help_text else html.Span(),
        ], style={"padding": "18px"}),
        className="h-100",
    )


# ---------------------------------------------------------------------------
# Section / panel wrappers
# ---------------------------------------------------------------------------
def section_header(title: str, subtitle: str = None):
    return html.Div([
        html.Div(title, className="md-section-title",
                 style={"fontSize": "14px"}),
        html.Div(subtitle, className="md-section-sub") if subtitle else html.Span(),
    ])


def chart_panel(figure, caption: str = None, height: int = None):
    """Card wrapper around a chart + auto-generated caption."""
    graph = dcc.Graph(figure=figure, config=theme.GRAPH_CONFIG,
                      style={"height": f"{height}px"} if height else {})
    children = [graph]
    if caption:
        children.append(html.P(caption, className="caption"))
    return dbc.Card(children, className="h-100")


def narrative_card(title: str, body: str, accent: str = None):
    """Meridian-style main-message card with a left accent rail."""
    return dbc.Card(
        dbc.CardBody([
            html.Div([
                html.Div(style={
                    "width": "3px", "backgroundColor": accent or theme.ACCENT,
                    "borderRadius": "2px", "marginRight": "14px",
                    "alignSelf": "stretch",
                }),
                html.Div([
                    html.Div(title, className="caps",
                             style={"marginBottom": "8px"}),
                    html.P(body, style={
                        "color": theme.TEXT, "fontSize": "13px",
                        "lineHeight": 1.5, "margin": 0,
                    }),
                ], style={"flex": 1}),
            ], style={"display": "flex"})
        ], style={"padding": "18px"}),
        className="h-100",
    )


# ---------------------------------------------------------------------------
# Caption generators — turn deltas into readable sentences
# ---------------------------------------------------------------------------
def caption_growth(
    df: pd.DataFrame,
    metric_label: str,
    bank_type_code: str = "10001",
) -> str:
    """E.g., 'Sector-wide growth accelerated to +43.6% YoY in Jan-26 (+1.9pp MoM).'"""
    if df is None or df.empty:
        return ""
    sub = df[df["bank_type_code"] == bank_type_code].sort_values("period")
    if len(sub) < 2:
        return ""
    latest, prev = sub.iloc[-1], sub.iloc[-2]
    delta_pp = latest["value"] - prev["value"]
    period_label = latest["period"].strftime("%b %y")
    direction = "accelerated" if delta_pp > 0.1 else "eased" if delta_pp < -0.1 else "held"
    return (f"{metric_label} {direction} to {latest['value']:+.1f}% in {period_label} "
            f"({delta_pp:+.1f}pp MoM).")


def caption_level(
    df: pd.DataFrame,
    metric_label: str,
    bank_type_code: str = "10001",
    unit: str = "tl",
) -> str:
    """E.g., 'Total loans reached 24.2T TL in Jan-26, up 2.0% MoM.'"""
    if df is None or df.empty:
        return ""
    sub = df[df["bank_type_code"] == bank_type_code].sort_values("period")
    if len(sub) < 2:
        return ""
    latest, prev = sub.iloc[-1], sub.iloc[-2]
    mom = (latest["value"] - prev["value"]) / prev["value"] * 100 if prev["value"] else None
    fmt = fmt_tl if unit == "tl" else (lambda v: f"{v:,.0f}")
    period_label = latest["period"].strftime("%b %y")
    mom_str = f", {fmt_delta_pct(mom)} MoM." if mom is not None else "."
    return f"{metric_label} reached {fmt(latest['value'])} in {period_label}{mom_str}"


def caption_comparison(
    df: pd.DataFrame,
    metric_label: str,
    unit: str = "pct",
) -> str:
    """Compare latest values across bank types."""
    if df is None or df.empty:
        return ""
    latest = df[df["period"] == df["period"].max()]
    if latest.empty:
        return ""
    leader = latest.sort_values("value", ascending=False).iloc[0]
    laggard = latest.sort_values("value", ascending=True).iloc[0]
    if unit == "pct":
        return (f"{theme.BANK_SHORT.get(leader['bank_type'], leader['bank_type'])} leads at "
                f"{leader['value']:.1f}%, "
                f"{theme.BANK_SHORT.get(laggard['bank_type'], laggard['bank_type'])} at "
                f"{laggard['value']:.1f}%.")
    return (f"{theme.BANK_SHORT.get(leader['bank_type'], leader['bank_type'])} leads at "
            f"{fmt_tl(leader['value'])}.")
