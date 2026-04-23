"""Rates section — weekly flow interest rates and monetary policy context.

Data source: TCMB EVDS (evds3.tcmb.gov.tr). See src/dashboard/evds.py.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
from dash import html, dcc
import dash_bootstrap_components as dbc

from src.dashboard import charts as C, theme, evds


# ---------------------------------------------------------------------------
# Weekly TL loan & deposit rates (matches BBVA's "TL LOAN & DEPOSIT RATES" chart)
# ---------------------------------------------------------------------------
RATE_SERIES = {
    "Consumer loan":               "TP.KTFTUK",
    "Consumer loan (incl. overdraft)": "TP.KTFTUK01",
    "Commercial (ex cards & overdraft)": "TP.KTF18",
    "Deposit (total TL)":          "TP.TRY.MT06",
}
RATE_COLORS = {
    "Consumer loan":                     "#1e3a8a",   # dark navy
    "Consumer loan (incl. overdraft)":   "#60a5fa",   # light blue
    "Commercial (ex cards & overdraft)": "#22c55e",   # green
    "Deposit (total TL)":                "#f59e0b",   # orange
}


def _panel_tl_rates():
    today = datetime.today().strftime("%Y-%m-%d")
    start = "2024-01-01"
    df = evds.fetch_many(RATE_SERIES, start, today)
    if df.empty:
        return C.chart_panel(C._empty_fig("EVDS unavailable"),
                              caption="Could not reach TCMB EVDS.")

    fig = go.Figure()
    for label, color in RATE_COLORS.items():
        sub = df[df["label"] == label].sort_values("date")
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["date"], y=sub["value"], mode="lines",
            name=label, line=dict(color=color, width=2.2),
            hovertemplate=f"<b>{label}</b><br>%{{x|%d %b %Y}}<br>" + "%{y:.2f}%<extra></extra>",
        ))
        # Endpoint label
        last = sub.iloc[-1]
        fig.add_annotation(
            x=last["date"], y=last["value"],
            text=f"{last['value']:.1f}%",
            showarrow=False, xanchor="left", xshift=6,
            font=dict(color=color, size=10, family=theme.FONT_FAMILY),
        )

    C._apply_layout(fig, "TL Loan & Deposit Rates (Weekly, Flow, Sector)", height=360)
    fig.update_yaxes(ticksuffix="%", tickformat=".0f")
    fig.update_xaxes(tickformat="%b %y")

    # Narrative caption from latest data
    latest = (
        df.sort_values("date").groupby("label").tail(1).set_index("label")["value"].to_dict()
    )
    spread = None
    if "Consumer loan" in latest and "Deposit (total TL)" in latest:
        spread = latest["Consumer loan"] - latest["Deposit (total TL)"]
    caption_parts = [
        f"Consumer {latest.get('Consumer loan', 0):.1f}%",
        f"Commercial {latest.get('Commercial (ex cards & overdraft)', 0):.1f}%",
        f"Deposit {latest.get('Deposit (total TL)', 0):.1f}%",
    ]
    caption = " · ".join(caption_parts)
    if spread is not None:
        caption += f" · Consumer-vs-deposit spread {spread:+.1f}pp."

    return C.chart_panel(fig, caption=caption)


CORRIDOR_SERIES = {
    "Policy Rate":        ("TP.PY.P02.1H",       "#1e3a8a"),  # dark navy — 1-week repo quotation OFFER
    "ON Lending":         ("TP.PY.P02.ON",       "#60a5fa"),  # light blue — overnight OFFER (upper corridor)
    "ON Borrowing":       ("TP.PY.P01.ON",       "#22c55e"),  # green — overnight BID (lower corridor)
    "BIST TRY REF":       ("TP.BISTTLREF.ORAN",  "#f59e0b"),  # orange — actual interbank O/N market rate
}


def _ffill_daily(df: "pd.DataFrame", start: str, end: str) -> "pd.DataFrame":
    """Reindex to calendar days and forward-fill — corridor rates are
    step-functions (policy, O/N quotations). Weekends and missing-publication
    days carry the last observed value."""
    import pandas as pd
    if df is None or df.empty:
        return df
    df = df.drop_duplicates(subset="date").set_index("date").sort_index()
    idx = pd.date_range(start=start, end=end, freq="D")
    out = df.reindex(idx).ffill()
    out = out.dropna(subset=["value"]).rename_axis("date").reset_index()
    return out


def _panel_corridor():
    import pandas as pd
    today = datetime.today().strftime("%Y-%m-%d")
    start = "2024-01-01"

    fig = go.Figure()
    latest = {}
    for label, (code, color) in CORRIDOR_SERIES.items():
        df = evds.fetch_series(code, start, today)
        if df.empty:
            continue
        df = _ffill_daily(df, start, today)
        fig.add_trace(go.Scatter(
            x=df["date"], y=df["value"], mode="lines",
            name=label, line=dict(color=color, width=2.2,
                                  shape="hv" if label != "BIST TRY REF" else "linear"),
            connectgaps=True,
            hovertemplate=f"<b>{label}</b><br>%{{x|%d %b %Y}}<br>" + "%{y:.2f}%<extra></extra>",
        ))
        last = df.iloc[-1]
        latest[label] = last["value"]
        fig.add_annotation(
            x=last["date"], y=last["value"],
            text=f"{last['value']:.1f}%", showarrow=False,
            xanchor="left", xshift=6,
            font=dict(color=color, size=10, family=theme.FONT_FAMILY),
        )

    C._apply_layout(fig, "CBRT Interest Rate Corridor & ON TRY Ref Rate (%)", height=360)
    fig.update_yaxes(ticksuffix="%", tickformat=".0f")
    fig.update_xaxes(tickformat="%b %y")

    caption_parts = []
    if "Policy Rate" in latest:
        caption_parts.append(f"Policy {latest['Policy Rate']:.1f}%")
    if "ON Lending" in latest and "ON Borrowing" in latest:
        width = latest["ON Lending"] - latest["ON Borrowing"]
        caption_parts.append(f"corridor {latest['ON Borrowing']:.1f}–{latest['ON Lending']:.1f}% ({width:.1f}pp wide)")
    if "BIST TRY REF" in latest:
        caption_parts.append(f"market O/N {latest['BIST TRY REF']:.1f}%")
    caption = " · ".join(caption_parts) + "."

    return C.chart_panel(fig, caption=caption)


def _panel_cbrt_reserves(start_date: str = "2022-01-01"):
    """CBRT International Reserves — gross, gold, and derived net.

    BBVA's net reserves chart comes from proprietary derivation. Our
    'Net (derived)' line is built from the weekly CBRT balance sheet:
        Net FX position ≈ Total FX Assets (TP.BL054) − Total FX Liabilities (TP.BL122)
    converted to USD via TP.DK.USD.A. Approximation — differs from BoP-defined
    Net International Reserves (which excludes certain FX claims on banks).
    """
    import pandas as pd
    today = datetime.today().strftime("%Y-%m-%d")
    start = start_date

    # Official reserves — already in million USD
    gross = evds.fetch_series("TP.AB.TOPLAM", start, today)
    gold  = evds.fetch_series("TP.AB.C1",     start, today)

    # Derive net: (BL054 − BL122) in thousand TL, divide by USD/TRY, then /1e6 → bn USD
    a_fx  = evds.fetch_series("TP.BL054", start, today)
    l_fx  = evds.fetch_series("TP.BL122", start, today)
    usd   = evds.fetch_series("TP.DK.USD.A", start, today)

    gross_bn = gross.assign(value=gross["value"] / 1000)  # million → billion USD
    gold_bn  = gold.assign(value=gold["value"] / 1000)

    net_df = pd.DataFrame()
    if not a_fx.empty and not l_fx.empty and not usd.empty:
        bs = pd.merge(a_fx.rename(columns={"value": "a"}),
                       l_fx.rename(columns={"value": "l"}), on="date", how="inner")
        bs["net_tl_thousands"] = bs["a"] - bs["l"]
        # Align USD/TRY — use most recent <= that Friday
        usd_s = usd.set_index("date")["value"].sort_index()
        bs["usd_try"] = bs["date"].map(lambda d: usd_s.loc[:d].iloc[-1] if (usd_s.index <= d).any() else float("nan"))
        bs["value"] = bs["net_tl_thousands"] / bs["usd_try"] / 1e6   # bn USD
        net_df = bs[["date", "value"]].dropna()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=gross_bn["date"], y=gross_bn["value"], mode="lines",
        name="Gross Reserves", line=dict(color=theme.DATA_4, width=2.2),  # slate blue
        hovertemplate="<b>Gross Reserves</b><br>%{x|%d %b %Y}<br>$%{y:.1f} bn<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=gold_bn["date"], y=gold_bn["value"], mode="lines",
        name="Gold", line=dict(color=theme.DATA_3, width=2.2),  # ochre
        hovertemplate="<b>Gold</b><br>%{x|%d %b %Y}<br>$%{y:.1f} bn<extra></extra>",
    ))
    if not net_df.empty:
        fig.add_trace(go.Scatter(
            x=net_df["date"], y=net_df["value"], mode="lines",
            name="Net (derived)", line=dict(color=theme.DATA_5, width=2.2, dash="dot"),  # olive dotted
            hovertemplate="<b>Net (derived)</b><br>%{x|%d %b %Y}<br>$%{y:.1f} bn<extra></extra>",
        ))

    # Endpoint labels
    for df_, color, label in [(gross_bn, theme.DATA_4, "Gross"),
                               (gold_bn,  theme.DATA_3, "Gold"),
                               (net_df,   theme.DATA_5, "Net")]:
        if df_ is None or df_.empty:
            continue
        last = df_.iloc[-1]
        fig.add_annotation(
            x=last["date"], y=last["value"],
            text=f"${last['value']:.0f}bn", showarrow=False,
            xanchor="left", xshift=6,
            font=dict(color=color, size=10, family=theme.FONT_FAMILY),
        )

    C._apply_layout(fig, "CBRT International Reserves (US$ bn)", height=340)
    fig.update_xaxes(tickformat="%b %y")
    fig.update_yaxes(tickformat=",.0f")

    latest_gross = gross_bn.iloc[-1]["value"] if not gross_bn.empty else None
    latest_net   = net_df.iloc[-1]["value"]   if not net_df.empty   else None
    caption_bits = []
    if latest_gross is not None:
        caption_bits.append(f"Gross ${latest_gross:.0f}bn")
    if latest_net is not None:
        caption_bits.append(f"Net (derived) ~${latest_net:.0f}bn")
    caption_bits.append(
        "Net is derived from the CBRT weekly balance sheet (Assets FX − "
        "Liabilities FX, converted at USD/TRY); differs from BoP-defined NIR "
        "but captures the broad trend."
    )
    return C.chart_panel(fig, caption=" · ".join(caption_bits))


def _panel_cbrt_sterilization(start_date: str = "2020-01-01"):
    """CBRT sterilization volume — stacked bar: TL depos + Quotation + Liq bills.

    Replicates BBVA's Figure 5. Defaults to 6-year view so the 2020 peak
    (~1.8T TL daily) and the current regime are both visible.
    """
    end = datetime.today().date()
    start = datetime.strptime(start_date, "%Y-%m-%d").date()

    SERIES_DEFS = [
        ("TL depos",       "TP.APIFON2.IHA", theme.DATA_1),   # oxblood — dominant
        ("Quotation",      "TP.APIFON2.KOT", theme.DATA_4),   # slate blue — tiny
        ("Liquidity bills","TP.APIFON2.LIK", theme.DATA_5),   # olive — new 2025+
    ]

    fig = go.Figure()
    total_by_date = {}
    for label, code, color in SERIES_DEFS:
        df = evds.fetch_series(code, start.strftime("%Y-%m-%d"),
                                end.strftime("%Y-%m-%d"))
        if df.empty:
            continue
        df = df.copy()
        df["bn_tl"] = df["value"] / 1e3
        df = df.dropna(subset=["bn_tl"])
        if df.empty:
            continue
        fig.add_trace(go.Bar(
            x=df["date"], y=df["bn_tl"],
            name=label, marker_color=color,
            hovertemplate=f"<b>{label}</b><br>%{{x|%d %b %Y}}<br>" + "%{y:,.0f} bn TL<extra></extra>",
        ))
        for d, v in zip(df["date"], df["bn_tl"]):
            total_by_date[d] = total_by_date.get(d, 0) + v

    fig.update_layout(barmode="stack", bargap=0.05)
    C._apply_layout(fig, "CBRT Sterilization Volume (TL bn)", height=340)
    fig.update_xaxes(tickformat="%b %y")
    fig.update_yaxes(tickformat=",")

    # Caption — latest composition
    if total_by_date:
        last_date = max(total_by_date.keys())
        latest_total = total_by_date[last_date]
        caption = (f"Latest total sterilization {latest_total:,.0f} bn TL "
                   f"({last_date:%d %b %Y}). BBVA Figure 5 replicated — "
                   "TL deposits dominate; liquidity bills introduced March 2025.")
    else:
        caption = "Data unavailable."
    return C.chart_panel(fig, caption=caption)


def _panel_cbrt_bond_share():
    """CBRT TRY Sovereign Bond Holdings / Total Assets — replicates BBVA's chart."""
    import pandas as pd
    from src.dashboard import series
    today = datetime.today().strftime("%Y-%m-%d")
    start = "2015-01-01"

    sec_spec = series.get("cbrt_gov_securities")
    tot_spec = series.get("cbrt_total_assets")
    sec = evds.fetch_series(sec_spec["code"], start, today)
    tot = evds.fetch_series(tot_spec["code"], start, today)
    if sec.empty or tot.empty:
        return C.chart_panel(C._empty_fig("EVDS unavailable"), caption="")

    df = pd.merge(sec.rename(columns={"value": "sec"}),
                   tot.rename(columns={"value": "tot"}),
                   on="date").sort_values("date")
    df["ratio"] = df["sec"] / df["tot"] * 100

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["ratio"], mode="lines",
        line=dict(color="#1e3a8a", width=1.6),
        hovertemplate="<b>%{x|%d %b %Y}</b><br>%{y:.2f}%<extra></extra>",
        showlegend=False,
    ))
    last = df.iloc[-1]
    fig.add_annotation(
        x=last["date"], y=last["ratio"],
        text=f"{last['ratio']:.1f}%", showarrow=False,
        xanchor="left", xshift=6,
        font=dict(color="#1e3a8a", size=11, family=theme.FONT_FAMILY),
    )
    C._apply_layout(fig, "CBRT TRY Sovereign Bond Holdings / Assets (%)", height=320)
    fig.update_yaxes(ticksuffix="%", tickformat=".0f")
    fig.update_xaxes(tickformat="%b %y")

    peak_idx = df["ratio"].idxmax()
    peak = df.loc[peak_idx]
    caption = (f"Latest {last['ratio']:.1f}% ({last['date']:%d %b %Y}). "
               f"Peak {peak['ratio']:.1f}% on {peak['date']:%b %Y} (COVID-era purchases). "
               f"Ratio shows CBRT's outright holdings of TRY government securities "
               f"relative to its total balance-sheet footprint.")
    return C.chart_panel(fig, caption=caption)


def _panel_usdtry():
    df = evds.fetch_series("TP.DK.USD.A", "2024-01-01",
                           datetime.today().strftime("%Y-%m-%d"))
    if df.empty:
        return C.chart_panel(C._empty_fig(), caption="")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["value"], mode="lines",
        name="USD/TRY",
        line=dict(color="#7c3aed", width=2.4),
        hovertemplate="<b>USD/TRY</b><br>%{x|%d %b %Y}<br>" + "%{y:.3f}<extra></extra>",
    ))
    last = df.iloc[-1]
    fig.add_annotation(
        x=last["date"], y=last["value"],
        text=f"{last['value']:.2f}",
        showarrow=False, xanchor="left", xshift=6,
        font=dict(color="#7c3aed", size=10, family=theme.FONT_FAMILY),
    )
    C._apply_layout(fig, "USD/TRY — Buying Rate", height=280)
    fig.update_xaxes(tickformat="%b %y")
    fig.update_layout(showlegend=False)

    first, last = df.iloc[0], df.iloc[-1]
    chg = (last["value"] / first["value"] - 1) * 100
    caption = (f"USD/TRY at {last['value']:.2f} "
               f"({chg:+.1f}% since {first['date']:%b %Y}).")
    return C.chart_panel(fig, caption=caption)


# ---------------------------------------------------------------------------
def build_rates():
    return dbc.Container([
        html.Div(
            "Interest rates and key macro series from TCMB EVDS (weekly flow rates, "
            "sector-average, not adjusted for required-reserve cost).",
            style={
                "fontSize": "0.75rem", "color": theme.MUTED,
                "backgroundColor": "#f0f9ff", "border": "1px solid #bae6fd",
                "padding": "8px 12px", "borderRadius": "6px", "marginBottom": "14px",
            },
        ),
        C.section_header(
            "CBRT Interest Rate Corridor",
            "Policy rate (1-week repo quotation), the overnight corridor, and "
            "the BIST TLREF market rate. Gaps between policy and TLREF show "
            "how far effective funding diverges from the announced stance.",
        ),
        dbc.Row([dbc.Col(_panel_corridor(), md=12)], className="g-3"),
        html.Div(style={"height": "8px"}),
        C.section_header(
            "Lending & Funding Rates",
            "Weekly flow rates published by TCMB — headline indicator for monetary transmission.",
        ),
        dbc.Row([dbc.Col(_panel_tl_rates(), md=12)], className="g-3"),
        html.Div(style={"height": "8px"}),
        C.section_header(
            "CBRT Balance Sheet",
            "CBRT's exposure to TRY government bonds, as a share of its total "
            "balance-sheet assets. Rises during large-scale outright purchases.",
        ),
        dbc.Row([dbc.Col(_panel_cbrt_bond_share(), md=12)], className="g-3"),
        html.Div(style={"height": "8px"}),
        C.section_header(
            "CBRT Sterilization",
            "Daily volume of TL liquidity absorbed by CBRT — a direct read on "
            "how aggressively the bank tightens beyond the announced policy rate.",
        ),
        dbc.Row([dbc.Col(_panel_cbrt_sterilization(), md=12)], className="g-3"),
        html.Div(style={"height": "8px"}),
        C.section_header(
            "CBRT International Reserves",
            "Gross reserves, gold component, and a derived net position — "
            "how much real FX liquidity CBRT commands.",
        ),
        dbc.Row([dbc.Col(_panel_cbrt_reserves(), md=12)], className="g-3"),
        html.Div(style={"height": "8px"}),
        C.section_header(
            "Currency",
            "USD/TRY buying rate.",
        ),
        dbc.Row([
            dbc.Col(_panel_usdtry(), md=12),
        ], className="g-3"),
        html.Div(style={"height": "24px"}),
    ], fluid=True)
