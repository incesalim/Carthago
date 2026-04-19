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
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap",
    ],
    suppress_callback_exceptions=True,
    title="Türkiye Banking Sector — BDDK Dashboard",
)

app.index_string = """<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>
            body { font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
                   background-color: #f8fafc; color: #0f172a; }
            .nav-tabs .nav-link { border: none !important; color: #64748b;
                                  font-weight: 500; padding: 10px 16px; }
            .nav-tabs .nav-link:hover { color: #0f172a; }
            .nav-tabs .nav-link.active { border: none !important;
                                         border-bottom: 2px solid #0f172a !important;
                                         color: #0f172a !important;
                                         font-weight: 600; background: transparent !important; }
            .nav-tabs { border-bottom: 1px solid #e2e8f0 !important; padding-left: 16px; }
            .card { transition: box-shadow 0.15s ease; }
            .card:hover { box-shadow: 0 2px 8px rgba(15,23,42,.08) !important; }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>"""


# =============================================================================
# LAYOUT
# =============================================================================
app.layout = dbc.Container([
    # Header
    html.Div([
        html.Div([
            html.H3("Türkiye Banking Sector", style={
                "color": T.HEADER_FG, "margin": 0, "fontWeight": 700,
                "letterSpacing": "-0.01em",
            }),
            html.P("Sector outlook · BDDK monthly data",
                   style={"color": "rgba(241,245,249,0.65)", "margin": "2px 0 0 0",
                          "fontSize": "0.82rem", "fontWeight": 500}),
        ], style={"display": "flex", "flexDirection": "column"}),
        html.Div(id="data-as-of", style={
            "color": "rgba(241,245,249,0.7)", "fontSize": "0.78rem",
            "fontWeight": 500, "alignSelf": "center",
        }),
    ], style={
        "backgroundColor": T.HEADER_BG,
        "padding": "20px 28px",
        "marginLeft": "-12px", "marginRight": "-12px",
        "marginBottom": "18px",
        "display": "flex", "justifyContent": "space-between",
    }),

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
