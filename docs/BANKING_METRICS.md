# Banking-metric knowledge

Our stored knowledge *about* banking metrics — not the values, but what kind of
metric each one is: whether it's disclosed at all, defined consistently across
banks, reported on a regular cadence, and whether **we** can reproduce it from
the data we hold (especially the BRSA quarterly audit reports in `bank_audit_*`).

This is the layer that answers "**can we actually show metric X for bank Y, and
is it comparable to its peers?**" before anyone tries to build a chart.

## Where it lives

| File | Role |
|---|---|
| [`data/metric_knowledge/registry.json`](../data/metric_knowledge/registry.json) | The registry — one entry per metric, classified on every axis. **Source of truth.** |
| [`data/metric_knowledge/schema.json`](../data/metric_knowledge/schema.json) | JSON-Schema contract for an entry. |
| [`scripts/metric_knowledge.py`](../scripts/metric_knowledge.py) | Loader / validator / query CLI. |
| [`tests/test_metric_knowledge.py`](../tests/test_metric_knowledge.py) | Integrity + enum-parity guard. |

It sits **above** the other two metric artifacts:
- [`METRICS.md`](METRICS.md) — definitions of the *sector* metrics we already chart.
- [`chart-specs.catalog.json`](../web/app/lib/chart-specs.catalog.json) — specific *reproduced charts*, machine-verified ([REPRODUCING_CHARTS.md](REPRODUCING_CHARTS.md)).

A registry entry can point at the chart-specs that operationalize it (`spec_ids`).

## The classification axes

Every metric is tagged on these, so we can filter and reason about a whole class
of metrics at once:

| Axis | Values | What it tells you |
|---|---|---|
| **group** | profitability · income · balance_sheet · growth · asset_quality · capital · liquidity_funding · efficiency · valuation · franchise · market_position · esg · macro | Metric family. |
| **level** | bank · group · sector · macro | Unit of observation. |
| **availability** | `mandatory` · `voluntary` · `third_party` · `none` | How it's disclosed: a required regulatory line item; a management/IR figure the bank defines itself; an external provider's number; or not public. |
| **cadence** | daily … quarterly · annual · `adhoc` · `none` | Reporting frequency. `adhoc` = irregular / only when the bank chooses. |
| **standard_across_banks** | true / false | Is it comparable like-for-like across banks? |
| **reproducible** | `direct` · `derived` · `partial` · `no` | Can *we* produce it from our data? A stored field; a formula over stored fields; only approximable (wrong level/cadence); or not at all. |
| **source_datasets** | bank_audit · bddk_monthly · bddk_weekly · evds · tbb_digital · external · none | Which of our datasets carry it. |

A derived convenience flag, **`reproducible_from_audit`**, is true when a metric
is cleanly (direct/derived) reproducible specifically from the `bank_audit_*`
reports.

### The relationship / framework layer

Beyond the classification axes, entries carry **structure** so the project
understands how metrics connect, not just a flat list:

| Field | What it captures |
|---|---|
| **formula** | Concise math expression (distinct from the prose `definition` and the `derivation` over our data). |
| **frameworks** | Definitional origin: `basel_iii` (capital/liquidity), `ifrs9` (staging/ECL), `tfrs` (Turkish IFRS accounting), `brsa` (BDDK regulatory ratio), `market` (equity-market), `management` (bank-defined), `none`. |
| **decomposes_into** | Child metric ids forming a decomposition tree, e.g. `roe → [roa, equity_multiplier]` (DuPont) and `net_income → [operating_revenue, opex_total, provision_expense, tax_expense]`. |
| **related** | Loosely linked metric ids (drivers, numerator/denominator, peers). |

All `decomposes_into` / `related` / `frameworks` references are integrity-checked
(must resolve to a known id / valid framework; the decomposition graph is asserted
acyclic) by `tests/test_metric_knowledge.py`.

## The core distinction this captures

The reason this layer exists (the point that prompted it):

- **Financial-statement metrics** — ROE, total assets, NPL ratio, NII — are
  `mandatory` · `standard_across_banks: true` · `quarterly` · reproducible from
  audit. They form clean, comparable time series.
- **Customer / franchise metrics** — "active digital customers", restructured-loan
  ratio, subsidiary AuM — are `voluntary` · `standard_across_banks: false` ·
  `adhoc` · `reproducible: no`. Banks define them differently (or don't disclose
  them on a schedule), so they are **not** comparable across banks and **not**
  reproducible from the audit reports, even when a single bank's deck shows them.

The registry makes that difference queryable instead of tribal knowledge.

## Querying it

```bash
python scripts/metric_knowledge.py                    # group × reproducibility matrix
python scripts/metric_knowledge.py --audit            # reproducible from the audit reports
python scripts/metric_knowledge.py --not-reproducible # what we genuinely can't get, and why
python scripts/metric_knowledge.py --group asset_quality
python scripts/metric_knowledge.py --reproducible direct,derived
python scripts/metric_knowledge.py --source bddk_weekly
python scripts/metric_knowledge.py --framework ifrs9  # by definitional framework
python scripts/metric_knowledge.py --tree roe         # decomposition tree
python scripts/metric_knowledge.py --validate         # integrity check (CI-friendly)
```

`--tree roe` prints the DuPont bridge; `--tree net_income` walks revenue → NII →
interest income/expense, opex, provisions and tax.

Current snapshot (v2, **130 metrics** across 13 groups): **66 / 130** reproducible
from audit reports. The 32 we can't get at all cluster in **valuation** (P/B, P/E,
market cap, EPS, dividend yield — need BIST price data), **franchise/customer**
(active digital customers, NPS, payroll/POS — bank-defined, no fixed cadence),
regulatory liquidity (LCR, NSFR — footnote-only), and **esg** (third-party
ratings, financed emissions). Run `--not-reproducible` for the full list with the
reason on each.

## How it was seeded & how to extend it

Seeded by classifying the Akbank 1Q26 consolidated earnings presentation against
our holdings, then broadened to the canonical universe a bank-sector analyst
tracks (v2). Several entries carry a verified `examples` cross-check — e.g. ROE
25.3%, Stage 2+3 11.4%, both matching our `compute_bank_metrics` output for AKBNK
2026Q1 consolidated.

To extend: add an entry to `registry.json` conforming to `schema.json`, run
`python scripts/metric_knowledge.py --validate`, link `spec_ids` if it maps to a
reproduced chart, and `decomposes_into` / `related` to wire it into the graph.
Keep the helper's `ENUMS` in sync with the schema —
`tests/test_metric_knowledge.py::test_enum_parity_with_schema` enforces it.

> **Coordination note:** per-bank `capital_adequacy` and `liquidity` extractors are
> in progress on another branch. When they merge, the `capital` (CAR/CET1/Tier1)
> and `liquidity_funding` (LCR/NSFR/HQLA) entries currently marked `partial`/`no`
> should be upgraded toward `derived`/`direct`.
