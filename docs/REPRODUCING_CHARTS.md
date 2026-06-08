# Reproducing external charts

The repeatable loop for turning a chart from an external banking-sector report
(Garanti BBVA Research / IMF / OECD / TCMB) into a chart on our dashboard — and
keeping it correct forever.

The old way was bespoke every time: the `metric-finder` agent produced a prose
report, then a human re-typed it into `metrics.ts`, hand-coded transforms on a
page, eyeballed it once, and recorded a note in METRICS.md. Nothing re-checked
it, so a BDDK item rename or an EVDS breakage silently returned 0 rows and the
chart went blank (this happened to `/credit` and to the monthly EVDS series).

The new way makes a **machine-readable chart spec** the durable artifact, and a
**verification harness** the safety net.

## The artifacts

| File | Role |
|---|---|
| [`web/app/lib/chart-specs.catalog.json`](../web/app/lib/chart-specs.catalog.json) | **Canonical catalog** — one JSON array of specs. Read by both the harness and (Tier 2) the dashboard. |
| [`data/chart_specs/schema.json`](../data/chart_specs/schema.json) | JSON-Schema contract for a spec (reference for the agent + external validators). |
| [`scripts/verify_chart_spec.py`](../scripts/verify_chart_spec.py) | Resolves each spec against the DB, applies transforms, asserts the `verify[]` anchors. |
| [`scripts/_bank_types.py`](../scripts/_bank_types.py) | The monthly vs weekly bank-type code namespaces (mirror of `metrics.ts`). |
| [`.claude/agents/metric-finder.md`](../.claude/agents/metric-finder.md) | The research agent — emits a spec object you paste into the catalog. |

## A spec in one screen

```jsonc
{
  "id": "liquidity.net_cbrt_funding",          // dot-namespaced by dashboard tab
  "title": "Net CBRT Funding (TL bn) …",
  "source": { "report": "Garanti BBVA Research …", "page": "Liquidity", "as_of": "2026-03" },
  "placement": { "tab": "liquidity", "section": "CBRT Liquidity & Reserves" },
  "unit": "TL bn", "format": "bn", "decimals": 0, "chart": "TrendChart",
  "series": [
    { "key": "netfund", "label": "Net CBRT funding",
      "source": "evds", "locator": { "code": "TP.APIFON3", "years_back": 8 },
      "transform": [] }
  ],
  "verify": [
    { "series": "netfund", "date": "2026-03-31", "value": 892429.23,
      "tolerance": 2000, "tolerance_unit": "abs" }
  ],
  "registry_additions": [
    { "code": "TP.APIFON3", "label": "CBRT Net Funding (TL thousand)", "category": "cbrt", "freq": "daily" }
  ]
}
```

### Series locators (where the data is)

- **`evds`** → `{ code, years_back }`
- **`bddk_monthly`** → `{ table, item_name, column, currency, bank_types_named, table_number?, annualize? }`
  (tables: `balance_sheet` / `loans` / `deposits` / `financial_ratios`)
- **`bddk_weekly`** → `{ category, item_id, currency, bank_types_named }`
- **`derived`** → no locator; its values come entirely from a transform that
  references sibling series by `key`.

> **Bank-type codes — the footgun.** Monthly and weekly bulletins reuse the same
> numbers for *different* groups (e.g. `10004` = Dev&Inv monthly but State
> weekly). Specs therefore never write raw codes — use `bank_types_named`
> (`"SECTOR"`, `"PRIVATE"`, `"STATE"`, …). The resolver translates the name
> through the **monthly** namespace for `bddk_monthly` and the **weekly** one for
> `bddk_weekly`, chosen by `source`, so the collision is impossible to get wrong.
> A spec series must resolve to **one value per date** → exactly one bank type.

### Transforms (the math)

Applied in order. `ratio`/`sum_series`/`derive` reference sibling `key`s, which
must be **declared earlier** in the `series` list (forward refs / cycles raise).

| op | meaning |
|---|---|
| `{ "op": "scale", "factor": 0.001 }` | multiply (e.g. thousand → bn) |
| `{ "op": "sum_series", "keys": ["a","b"] }` | element-wise sum by date |
| `{ "op": "ratio", "numerator": "n", "denominator": "d", "scale": 100 }` | `n/d*scale` |
| `{ "op": "growth", "window": 13, "mode": "annualized" }` | rolling growth (`yoy` = simple; `annualized` = `(v/prev)^(52/window)−1`) |
| `{ "op": "derive", "formula": <AST> }` | safe arithmetic AST (below) |

`derive` is a **JSON AST, never an eval'd string** — leaves are `{"ref": "<key>"}`
or `{"const": <n>}`; nodes are `{"op": "add|sub|mul|div", "args": [node, node]}`.
Example, net reserves `(BL054 − BL122) / USD / 1e6`:

```jsonc
{ "op": "div", "args": [
    { "op": "div", "args": [
        { "op": "sub", "args": [ {"ref":"bl054"}, {"ref":"bl122"} ] },
        { "ref": "usd" } ]},
    { "const": 1000000 } ] }
```

### `verify[]` — the regression contract

The single visible values the metric-finder reads off the source chart, expressed
in the **stored DB unit** (before any display formatter — so `892429.23`, the raw
`evds_series` value, not the `892` bn the chart shows). A point resolving to 0
rows is always a failure: that is the silent-blank detector.

`tolerance_unit`: `abs` (absolute), `pp` (percentage points), `pct` (relative %).
Defaults to `pp` when `format` is `pct`, else `abs`. `date` is a prefix match —
use a full `YYYY-MM-DD` for daily series; the harness picks the last point in the
matched window.

## The loop

1. **Research** — run the `metric-finder` agent on the chart image. It identifies
   each series, finds it in EVDS / the BDDK DB, derives any formula, sanity-checks
   one value, and emits a spec object.
2. **Add the spec** to `web/app/lib/chart-specs.catalog.json`.
3. **Register any missing EVDS series** (the spec's `registry_additions`): add
   them to the `SERIES` list in [`src/scrapers/evds_scraper.py`](../src/scrapers/evds_scraper.py),
   then populate + push:
   ```bash
   python -m src.scrapers.evds_scraper        # → local data/bddk_data.db
   python scripts/push_to_d1.py               # → remote D1 (evds_series)
   ```
   (Monthly/weekly bulletin items are already in D1 — no registration needed.)
4. **Verify**:
   ```bash
   python scripts/verify_chart_spec.py --db data/bddk_data.db   # fast, offline
   python scripts/verify_chart_spec.py                          # against remote D1
   ```
   Both anchors should PASS. A `WARN … MISSING from evds_series` means step 3
   isn't done yet.
5. **(Tier 2) Render** — once `specSeries(id)` lands in `metrics.ts`, drop the
   chart on its tab with one call (see that helper's doc). Until then, wire the
   page by hand as usual; the spec + harness already protect it.

From then on the daily `healthcheck.yml` cron runs
`verify_chart_spec.py --alert`, so if the chart ever breaks you get a
Telegram/Discord alert instead of a silently blank panel.

## Harness reference

```
python scripts/verify_chart_spec.py [--db PATH] [--only ID] [--alert] [--strict]
```

- no `--db` → queries **remote D1** via wrangler (needs `CLOUDFLARE_API_TOKEN`).
- `--db data/bddk_data.db` → queries a **local** SQLite snapshot.
- `--alert` → sends a summary via `scripts/notify.py` when any point fails.
- exits 0 by default (the alert is the signal, matching `check_audit_quality.py`);
  `--strict` exits nonzero on any failure (used as a CI gate).

Unit tests: [`tests/test_verify_chart_spec.py`](../tests/test_verify_chart_spec.py).
The transform engine is mirrored in Python (here) and — once Tier 2 lands — in
TypeScript (`metrics.ts`); the shared `verify[]` anchors keep the two honest.
