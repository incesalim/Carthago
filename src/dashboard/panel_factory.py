"""Config-driven panel factory.

Most dashboard panels follow one of a handful of shapes. Instead of
writing 50–80 lines of Plotly boilerplate per panel, declare a panel as
a dict and `render(spec)` produces the Dash component.

Supported panel kinds:

  "evds_trend"       — one or more EVDS series, line chart
  "evds_daily_step"  — step-function daily series (corridor rates)
  "evds_stacked_bar" — stacked bars from EVDS series (sterilization)
  "bddk_ratio_trend" — Table-15 published ratio by bank type
  "derived_spread"   — EVDS series A − series B, line chart
  "html_card"        — wrap any go.Figure in a chart panel

Example spec:

    {"kind": "evds_trend",
     "title": "CBRT Policy Rate",
     "series": [{"key": "policy_rate", "color": "#1e3a8a"}],
     "start": "2024-01-01",
     "height": 280,
     "caption": "Latest {policy_rate:.1f}%"}

The `key` field always resolves through `series.get()` — raw codes are
rejected (see docstring of `src/dashboard/series.py`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import plotly.graph_objects as go

from src.dashboard import charts as C, theme, evds, series as S


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def _today() -> str:
    return datetime.today().strftime("%Y-%m-%d")


def _fetch(key: str, start: str, end: str) -> pd.DataFrame:
    spec = S.get(key)
    src = spec["source"]
    if src == "evds":
        df = evds.fetch_series(spec["code"], start, end)
        # Apply unit_scale if defined (e.g. thousand TL → bn TL)
        scale = spec.get("unit_scale")
        if scale and not df.empty:
            df = df.assign(value=df["value"] / scale)
        return df
    raise NotImplementedError(f"Factory does not yet handle source={src!r}")


def _endpoint_annotation(fig: go.Figure, df: pd.DataFrame,
                          color: str, fmt: str = "{:.1f}") -> None:
    if df is None or df.empty:
        return
    last = df.iloc[-1]
    fig.add_annotation(
        x=last["date"], y=last["value"],
        text=fmt.format(last["value"]), showarrow=False,
        xanchor="left", xshift=6,
        font=dict(color=color, size=10, family=theme.FONT_FAMILY),
    )


def _ffill_daily(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    df = df.drop_duplicates(subset="date").set_index("date").sort_index()
    idx = pd.date_range(start=start, end=end, freq="D")
    return df.reindex(idx).ffill().dropna(subset=["value"]) \
             .rename_axis("date").reset_index()


# ---------------------------------------------------------------------------
# Renderers by kind
# ---------------------------------------------------------------------------
def _render_evds_trend(spec: dict) -> Any:
    start = spec.get("start", "2024-01-01")
    end = spec.get("end") or _today()
    height = spec.get("height", 280)

    fig = go.Figure()
    latest: dict[str, float] = {}
    for s in spec["series"]:
        key = s["key"]
        color = s.get("color") or theme.CATEGORICAL[
            len(latest) % len(theme.CATEGORICAL)
        ]
        df = _fetch(key, start, end)
        if df.empty:
            continue
        label = s.get("label") or S.get(key).get("label", key)
        fig.add_trace(go.Scatter(
            x=df["date"], y=df["value"], mode="lines",
            name=label,
            line=dict(color=color, width=spec.get("line_width", 2.2)),
            hovertemplate=f"<b>{label}</b><br>%{{x|%d %b %Y}}<br>"
                          f"%{{y:{spec.get('hover_fmt', '.2f')}}}"
                          f"{spec.get('unit_suffix', '')}<extra></extra>",
        ))
        latest[key] = float(df.iloc[-1]["value"])
        if spec.get("endpoint_labels", True):
            _endpoint_annotation(fig, df, color,
                                  fmt=spec.get("endpoint_fmt", "{:.1f}%"))

    C._apply_layout(fig, spec.get("title"), height=height)
    fig.update_xaxes(tickformat=spec.get("x_tick_format", "%b %y"))
    yfmt = spec.get("y_tick", {})
    if yfmt:
        fig.update_yaxes(**yfmt)

    if spec.get("zero_line"):
        fig.add_hline(y=0, line=dict(color=theme.MUTED, width=1, dash="dot"))

    caption = _format_caption(spec.get("caption"), latest)
    return C.chart_panel(fig, caption=caption)


def _render_evds_daily_step(spec: dict) -> Any:
    """Step-function daily series (e.g. policy corridor)."""
    start = spec.get("start", "2024-01-01")
    end = spec.get("end") or _today()
    height = spec.get("height", 320)

    fig = go.Figure()
    latest: dict[str, float] = {}
    for s in spec["series"]:
        key = s["key"]
        color = s.get("color")
        shape = s.get("shape", "hv")    # "hv" = step, "linear" for market
        df = _fetch(key, start, end)
        df = _ffill_daily(df, start, end)
        if df.empty:
            continue
        label = s.get("label") or S.get(key).get("label", key)
        fig.add_trace(go.Scatter(
            x=df["date"], y=df["value"], mode="lines",
            name=label,
            line=dict(color=color, width=2.2, shape=shape),
            connectgaps=True,
            hovertemplate=f"<b>{label}</b><br>%{{x|%d %b %Y}}<br>"
                          "%{y:.2f}%<extra></extra>",
        ))
        latest[key] = float(df.iloc[-1]["value"])
        _endpoint_annotation(fig, df, color, fmt="{:.1f}%")

    C._apply_layout(fig, spec.get("title"), height=height)
    fig.update_yaxes(ticksuffix="%", tickformat=".0f")
    fig.update_xaxes(tickformat=spec.get("x_tick_format", "%b %y"))

    caption = _format_caption(spec.get("caption"), latest)
    return C.chart_panel(fig, caption=caption)


def _render_evds_stacked_bar(spec: dict) -> Any:
    """Stacked bars from EVDS series (e.g. sterilization volume)."""
    start = spec.get("start", "2020-01-01")
    end = spec.get("end") or _today()
    height = spec.get("height", 340)

    fig = go.Figure()
    total_by_date: dict[Any, float] = {}
    for s in spec["series"]:
        key = s["key"]
        color = s.get("color") or theme.CATEGORICAL[0]
        df = _fetch(key, start, end)
        if df.empty:
            continue
        label = s.get("label") or S.get(key).get("label", key)
        fig.add_trace(go.Bar(
            x=df["date"], y=df["value"],
            name=label, marker_color=color,
            hovertemplate=f"<b>{label}</b><br>%{{x|%d %b %Y}}<br>"
                          "%{y:,.0f}<extra></extra>",
        ))
        for d, v in zip(df["date"], df["value"]):
            total_by_date[d] = total_by_date.get(d, 0) + v

    fig.update_layout(barmode="stack", bargap=spec.get("bargap", 0.05))
    C._apply_layout(fig, spec.get("title"), height=height)
    fig.update_xaxes(tickformat=spec.get("x_tick_format", "%b %y"))
    fig.update_yaxes(tickformat=",.0f")

    latest_total = total_by_date[max(total_by_date)] if total_by_date else None
    caption = _format_caption(spec.get("caption"),
                               {"total": latest_total or 0})
    return C.chart_panel(fig, caption=caption)


def _render_derived_spread(spec: dict) -> Any:
    """Show series A − series B as a line chart."""
    start = spec.get("start", "2024-01-01")
    end = spec.get("end") or _today()
    height = spec.get("height", 280)

    fig = go.Figure()
    latest: dict[str, float] = {}
    for s in spec["lines"]:
        a = _fetch(s["minuend"], start, end)
        b = _fetch(s["subtrahend"], start, end)
        if a.empty or b.empty:
            continue
        m = pd.merge(a.rename(columns={"value": "a"}),
                      b.rename(columns={"value": "b"}),
                      on="date").sort_values("date")
        m["value"] = m["a"] - m["b"]
        color = s.get("color") or theme.CATEGORICAL[len(latest)]
        label = s["label"]
        fig.add_trace(go.Scatter(
            x=m["date"], y=m["value"], mode="lines",
            name=label, line=dict(color=color, width=2.2),
            hovertemplate=f"<b>{label}</b><br>%{{x|%d %b %Y}}<br>"
                          "%{y:+.2f} pp<extra></extra>",
        ))
        latest[label] = float(m.iloc[-1]["value"])
        _endpoint_annotation(fig, m[["date", "value"]], color, fmt="{:+.1f}pp")

    fig.add_hline(y=0, line=dict(color=theme.MUTED, width=1, dash="dot"))
    C._apply_layout(fig, spec.get("title"), height=height)
    fig.update_yaxes(ticksuffix="pp", tickformat=".0f")
    fig.update_xaxes(tickformat=spec.get("x_tick_format", "%b %y"))

    caption = _format_caption(spec.get("caption"), latest)
    return C.chart_panel(fig, caption=caption)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
_RENDERERS = {
    "evds_trend":       _render_evds_trend,
    "evds_daily_step":  _render_evds_daily_step,
    "evds_stacked_bar": _render_evds_stacked_bar,
    "derived_spread":   _render_derived_spread,
}


def render(spec: dict) -> Any:
    """Render a single panel from its config spec."""
    kind = spec.get("kind")
    if kind not in _RENDERERS:
        raise ValueError(
            f"Unknown panel kind {kind!r}. Valid: {list(_RENDERERS)}"
        )
    return _RENDERERS[kind](spec)


def render_all(specs: list[dict]) -> list[Any]:
    """Render a list of specs in order."""
    return [render(s) for s in specs]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _format_caption(template: str | None, values: dict) -> str | None:
    """Caption templates use Python .format() with `values` as kwargs.
    Missing keys are replaced with an em-dash silently."""
    if not template:
        return None
    try:
        return template.format(**values)
    except (KeyError, IndexError):
        return template
