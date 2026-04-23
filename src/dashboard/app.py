"""BDDK Banking Sector Dashboard — entry + layout + routing.

All tab content lives in src/dashboard/sections/*.py. Charts, theme, and
extra metric helpers live in their sibling modules.
"""

import os
import sys
import gzip
import shutil
from pathlib import Path

# Allow `src.*` imports when launched directly.
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

# On first start (e.g. Render deploy) the SQLite DB may not exist yet —
# decompress the shipped snapshot if present.
_DB_PATH = ROOT / "data" / "bddk_data.db"
_DB_GZ = ROOT / "data" / "bddk_data.db.gz"
if not _DB_PATH.exists() and _DB_GZ.exists():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"Decompressing {_DB_GZ.name} → {_DB_PATH.name} …", flush=True)
    with gzip.open(_DB_GZ, "rb") as src, open(_DB_PATH, "wb") as dst:
        shutil.copyfileobj(src, dst)
    print("DB ready.", flush=True)

import dash
from dash import html, Input, Output, callback
import dash_bootstrap_components as dbc

from src.analytics import data_store
from src.dashboard import theme as T
from src.dashboard.sections.overview import build_overview
from src.dashboard.sections.credit import build_credit
from src.dashboard.sections.deposits import build_deposits
from src.dashboard.sections.capital import build_capital
from src.dashboard.sections.asset_quality import build_asset_quality
from src.dashboard.sections.profitability import build_profitability
from src.dashboard.sections.rates import build_rates
from src.dashboard.sections.weekly_trends import build_weekly_trends


# =============================================================================
# DATA STORE
# =============================================================================
print("Loading dashboard data...")
data_store.initialize()
print("Dashboard data loaded.")


# =============================================================================
# DASH APP
# =============================================================================
app = dash.Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        # Meridian fonts
        "https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap",
    ],
    suppress_callback_exceptions=True,
    title="Türkiye Banking Sector — Meridian",
)
# Meridian tokens and component CSS are auto-loaded from
# src/dashboard/assets/*.css by Dash.


# =============================================================================
# LAYOUT
# =============================================================================
app.layout = dbc.Container([
    # Meridian-style top bar: hairline bottom, oxblood brand glyph
    html.Div([
        html.Div([
            html.Span(className="md-brand-glyph"),
            html.Div([
                html.Div("Türkiye banking sector", className="md-topbar-title"),
                html.Div("Sector outlook · BDDK monthly & weekly data",
                         className="md-topbar-sub"),
            ]),
        ], style={"display": "flex", "alignItems": "center"}),
        html.Div(id="data-as-of", className="md-topbar-meta"),
    ], className="md-topbar",
       style={"marginLeft": "-12px", "marginRight": "-12px",
              "marginBottom": "16px"}),

    # Tabs
    dbc.Tabs([
        dbc.Tab(label="Overview", tab_id="overview"),
        dbc.Tab(label="Credit", tab_id="credit"),
        dbc.Tab(label="Deposits & Liquidity", tab_id="deposits"),
        dbc.Tab(label="Capital", tab_id="capital"),
        dbc.Tab(label="Asset Quality", tab_id="asset_quality"),
        dbc.Tab(label="Profitability", tab_id="profitability"),
        dbc.Tab(label="Weekly Trends", tab_id="weekly"),
        dbc.Tab(label="Rates", tab_id="rates"),
    ], id="tabs", active_tab="overview", className="mb-3"),

    html.Div(id="tab-content"),

    # Footer
    html.Hr(style={"borderColor": T.BORDER, "marginTop": "28px"}),
    html.P(
        "Data source: BDDK (Banking Regulation and Supervision Agency of Turkey) · "
        "Monthly bulletin (BültenAylık) · "
        "All ratios published in Table 15 (Rasyolar). YTD ratios are "
        "cumulative year-to-date, not annualized.",
        style={"color": T.MUTED, "fontSize": "0.72rem",
               "textAlign": "center", "marginBottom": "24px"},
    ),
], fluid=True)


# =============================================================================
# CALLBACKS
# =============================================================================
TAB_BUILDERS = {
    "overview": build_overview,
    "credit": build_credit,
    "deposits": build_deposits,
    "capital": build_capital,
    "asset_quality": build_asset_quality,
    "profitability": build_profitability,
    "weekly": build_weekly_trends,
    "rates": build_rates,
}


@callback(Output("tab-content", "children"), Input("tabs", "active_tab"))
def render_tab(active_tab):
    builder = TAB_BUILDERS.get(active_tab)
    return builder() if builder else html.Div("Select a tab")


@callback(Output("data-as-of", "children"), Input("tabs", "active_tab"))
def render_data_as_of(_):
    y, m = data_store.get_latest_period()
    if not y:
        return ""
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"Data as of {months[m - 1]} {y}"


# =============================================================================
# RUN
# =============================================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    app.run_server(debug=False, host="0.0.0.0", port=port)


# Expose the underlying Flask server so Render/Gunicorn can pick it up
# via `gunicorn src.dashboard.app:server`.
server = app.server
