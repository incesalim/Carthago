"""Dashboard theme — Meridian Banking Dashboard Design System.

Mirrors the CSS tokens defined in `assets/meridian.css` for use in Python
chart code (Plotly layouts, KPI cards, narrative cards). If you change a
token here, change it in the CSS too.
"""

# ---------------------------------------------------------------------------
# Neutrals (warm, OKLCH-derived)
# ---------------------------------------------------------------------------
NEUTRAL_0   = "#FFFFFF"
NEUTRAL_50  = "#FAFAF7"   # page surface
NEUTRAL_100 = "#F3F2EC"
NEUTRAL_200 = "#E7E5DC"   # hairlines
NEUTRAL_300 = "#D5D2C6"
NEUTRAL_400 = "#A9A59A"   # placeholders
NEUTRAL_500 = "#7C7972"   # secondary text
NEUTRAL_600 = "#55524D"
NEUTRAL_700 = "#35332F"
NEUTRAL_800 = "#1E1D1B"
NEUTRAL_900 = "#0E1116"   # ink (primary text)

# ---------------------------------------------------------------------------
# Semantic surfaces (light mode)
# ---------------------------------------------------------------------------
BG         = NEUTRAL_50
CARD_BG    = NEUTRAL_0
BORDER     = NEUTRAL_200
BORDER_STRONG = NEUTRAL_300
GRID       = NEUTRAL_100
TEXT       = NEUTRAL_900
MUTED      = NEUTRAL_500
LABEL      = NEUTRAL_600
PLACEHOLDER= NEUTRAL_400

# ---------------------------------------------------------------------------
# Brand accent — oxblood
# ---------------------------------------------------------------------------
ACCENT        = "#7A1D2B"
ACCENT_HOVER  = "#641722"
ACCENT_PRESS  = "#4F121B"
ACCENT_TINT   = "#F5E5E7"

# For back-compat with existing files that import HEADER_* names
HEADER_BG = CARD_BG     # top bar is light in Meridian (was dark before)
HEADER_FG = TEXT

# ---------------------------------------------------------------------------
# Status (never decorative)
# ---------------------------------------------------------------------------
POS_COLOR = "#1F7A4C"
NEG_COLOR = "#B42E1A"
WARN_COLOR = "#A86B12"
INFO_COLOR = "#2C5E8F"
NEUTRAL_COLOR = NEUTRAL_500

# ---------------------------------------------------------------------------
# Data palette — desaturated categorical
# ---------------------------------------------------------------------------
DATA_1 = "#7A1D2B"   # oxblood
DATA_2 = "#2F5D62"   # ink teal
DATA_3 = "#B8872E"   # ochre
DATA_4 = "#4A5D8F"   # slate blue
DATA_5 = "#6B7A3E"   # olive
DATA_6 = "#9C4A2E"   # muted rust
DATA_7 = "#5E4B7A"   # muted plum
DATA_8 = "#2E7A6B"   # muted emerald

CATEGORICAL = [DATA_1, DATA_2, DATA_3, DATA_4, DATA_5, DATA_6, DATA_7, DATA_8]

# Bank-type palette — Sector neutral (grey), ownership types take signature hues
BANK_COLORS = {
    "10001": NEUTRAL_700,  # Sector — strong neutral (anchor)
    "10003": DATA_1,       # Private Deposit — oxblood
    "10004": DATA_2,       # State Deposit  — ink teal
    "10005": DATA_3,       # Foreign Deposit — ochre
    "10006": DATA_5,       # Participation   — olive
    "10007": DATA_7,       # Dev & Investment — muted plum
    "10008": DATA_1,
    "10009": DATA_2,
    "10010": DATA_3,
}

BANK_SHORT = {
    "Sector": "Sector",
    "Private Deposit Banks": "Private",
    "State Deposit Banks": "State",
    "Foreign Deposit Banks": "Foreign",
    "Participation Banks": "Participation",
    "Dev & Investment Banks": "Dev & Inv",
}

# ---------------------------------------------------------------------------
# Typography
# ---------------------------------------------------------------------------
FONT_FAMILY = "'Inter Tight', -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
FONT_MONO   = "'JetBrains Mono', ui-monospace, SF Mono, Menlo, Consolas, monospace"

# ---------------------------------------------------------------------------
# Plotly layout defaults
# ---------------------------------------------------------------------------
PLOTLY_LAYOUT_DEFAULTS = dict(
    font=dict(family=FONT_FAMILY, size=12, color=TEXT),
    plot_bgcolor=CARD_BG,
    paper_bgcolor=CARD_BG,
    margin=dict(l=56, r=72, t=44, b=40),
    hoverlabel=dict(
        bgcolor=NEUTRAL_900,
        bordercolor=NEUTRAL_900,
        font=dict(color=NEUTRAL_50, family=FONT_FAMILY, size=11),
    ),
    legend=dict(
        orientation="h",
        yanchor="top", y=-0.18, xanchor="center", x=0.5,
        font=dict(size=11, color=MUTED, family=FONT_FAMILY),
    ),
)

GRAPH_CONFIG = {
    "displaylogo": False,
    "displayModeBar": False,
}
