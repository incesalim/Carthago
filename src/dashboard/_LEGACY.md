# Legacy: Render Dash dashboard

This is the Python/Plotly Dash dashboard deployed at
https://turkish-banking-sector.onrender.com

Status: **legacy**. Active work is on the Next.js dashboard at
`web/` (deployed to Cloudflare Workers). This module stays alive
until full feature parity is reached on the new stack — most
notably the FCI engine and weekly transforms.

When all sections are ported to `web/`, this folder + Render
deployment + the `bddk_data.db.gz` snapshot in git can be removed.

Pages still living here that haven't been ported:
- FCI (Financial Conditions Index) — composite z-score
- Weekly trends with 4w/13w/YoY transforms (`weekly_ext.py`)
- Rates / EVDS macro panels (live API)
