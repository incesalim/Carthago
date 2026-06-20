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

### Modelling the "not structured" metrics

For the non-financial families (`franchise`, `market_position`, `esg`) the
interesting knowledge isn't a value — it's *why* the metric resists comparison and
*where* it surfaces. Three fields capture that as structured, queryable data rather
than buried prose:

| Field | What it captures |
|---|---|
| **nonstandard_reasons** | The structured taxonomy of *why* it isn't comparable: `definition_varies`, `window_varies` (e.g. "active" = last 3m vs 12m), `peer_set_varies` (market-share denominator), `methodology_varies`, `provider_varies`, `cadence_irregular`, `scope_varies` (solo vs consolidated), `not_disclosed`. Only attached when `standard_across_banks` is false. |
| **disclosure_channels** | *Where* it tends to be published: `investor_deck`, `earnings_press`, `sustainability_report`, `annual_report`, `kap`, `third_party` (rating agency / BKM / Dealogic), `regulatory`, `none`. |
| **definition_variants** | Free-text: concrete examples of how the definition/label differs across banks (the human detail behind `nonstandard_reasons`). |

So "which customer metrics are non-comparable because each bank picks its own
*active* window, and where do they show up?" becomes a query
(`--reason window_varies`, `--channel investor_deck`) instead of folklore. These are
**knowledge-only** — no per-bank values are harvested; `examples` stay reserved for
the few figures we've cross-checked.

## Querying it

```bash
python scripts/metric_knowledge.py                    # group × reproducibility matrix
python scripts/metric_knowledge.py --audit            # reproducible from the audit reports
python scripts/metric_knowledge.py --not-reproducible # what we genuinely can't get, and why
python scripts/metric_knowledge.py --group asset_quality
python scripts/metric_knowledge.py --reproducible direct,derived
python scripts/metric_knowledge.py --source bddk_weekly
python scripts/metric_knowledge.py --framework ifrs9  # by definitional framework
python scripts/metric_knowledge.py --unstructured     # non-comparable metrics + why (reasons tally)
python scripts/metric_knowledge.py --reason window_varies   # by reason it isn't standard
python scripts/metric_knowledge.py --channel sustainability_report  # by where it's disclosed
python scripts/metric_knowledge.py --show active_digital_customers  # full knowledge dump
python scripts/metric_knowledge.py --tree roe         # decomposition tree
python scripts/metric_knowledge.py --validate         # integrity check (CI-friendly)
```

`--tree roe` prints the DuPont bridge; `--tree net_income` walks revenue → NII →
interest income/expense, opex, provisions and tax. `--unstructured` lists every
non-comparable metric with its reason codes and a tally; `--show <id>` dumps one
metric's full knowledge (definition, variants, reasons, channels, examples).

Current snapshot (v5, **153 metrics** across 13 groups): **82 / 153** reproducible
from audit reports. The metrics we still can't get at all cluster in **valuation**
(P/B, P/E, market cap, EPS, dividend yield — need BIST price data), **franchise /
customer** (active/registered digital customers, NPS, payroll, cards, ATM/POS,
merchant, SME/agri customers — bank-defined, no fixed cadence) and **esg**
(third-party ratings, financed emissions, net-zero targets, gender). The
non-financial families are now modelled with `nonstandard_reasons` /
`disclosure_channels` (see above) so the *reason* they're non-comparable is itself
queryable. Run `--not-reproducible` or `--unstructured` for the full list with the
reason on each.

## How it was seeded & how to extend it

Seeded by classifying the Akbank 1Q26 consolidated earnings presentation against
our holdings, broadened to the canonical universe a bank-sector analyst tracks
(v2), then enriched by reading the **Garanti BBVA, Yapı Kredi, İşbank and Halkbank**
1Q26 decks (v3) — which added naming-variant `aliases` (ROAE/RoTE/RoAA, PPP, "Net
Cost of Risk excl. currency", SICR…), nine bank-disclosed metrics (real ROE, core
NIM, core revenue, cost of funding, free funds, net NPL formation, FX capital
sensitivity, securities MtM, loans/assets), and **cross-bank `examples`** verified
against our `compute_bank_metrics` output — e.g. YKBNK total assets 3,760bn and
equity 271bn match the deck exactly; ROE/ROA match within ~0.2pp for HALKB & YKBNK.
The same `examples` also expose where a metric is *not* comparable: active digital
customers reads 15.5 / 16.8 / 15.9 / 7.5 mn across four banks on four definitions.

**v5 (knowledge-only, no data harvested):** deepened the non-financial families.
`franchise` grew 9 → 20 (added registered digital customers, ATM / POS-terminal /
total / credit / debit cards, merchant count, mobile-app rating, employee count,
SME & agri customers) and `esg` 5 → 8 (women on board, net-zero target, ESG-linked
loans). Every voluntary, non-comparable franchise / market-position / esg metric now
carries `nonstandard_reasons` + `disclosure_channels` + `definition_variants`, so the
non-standardisation is structured rather than free-text. No per-bank `examples` were
added (deliberately knowledge-only). A `test_unstructured_metrics_are_documented`
guard keeps the coverage honest.

To extend: add an entry to `registry.json` conforming to `schema.json`, run
`python scripts/metric_knowledge.py --validate`, link `spec_ids` if it maps to a
reproduced chart, and `decomposes_into` / `related` to wire it into the graph.
Keep the helper's `ENUMS` in sync with the schema —
`tests/test_metric_knowledge.py::test_enum_parity_with_schema` enforces it (it reads
`mk.ARRAY_ENUMS` for the array-typed enums).

> **Open follow-up — valuation:** the 8 `valuation` entries still say
> `reproducible: no` / `source: external`, but the **BIST lane** (`bist_prices` +
> audited equity) now makes market cap / P-B / P-E / dividend yield derivable. A
> refresh there needs a new `bist` value in the `source_datasets` enum and an update
> to `test_breadth_and_new_groups_present` (which currently pins valuation to
> `reproducible == "no"`). Left out of the v5 non-financial pass on purpose.

> **Done (§4 extractors merged):** per-bank capital/liquidity is now extracted into
> `bank_audit_capital` (cet1/tier1/tier2/total capital, total_rwa, cet1/tier1/CAR
> ratios) and `bank_audit_liquidity` (leverage, LCR total/FC, NSFR). The `capital`
> (CAR, CET1, Tier1/Tier2, AT1, RWA, RWA density/growth, leverage ratio) and
> `liquidity_funding` (LCR, NSFR) entries were upgraded from `partial`/`no` to
> `direct`/`derived` with `bank_audit` as a source. Still out: HQLA stock and the
> capital buffers/excess (the regulatory requirement isn't stored).
