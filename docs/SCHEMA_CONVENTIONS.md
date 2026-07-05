# D1 schema naming conventions

**Status:** adopted 2026-07-05 · enforced by `scripts/check_schema_naming.py`
(CI, Python job) for migrations numbered **≥ 0022**. Existing tables are
grandfathered — see [Deliberate exceptions](#deliberate-exceptions).

## Why this exists

The schema grew one lane at a time across 20+ migrations, each authored in
isolation and often mirroring its *source's* vocabulary. Nothing in SQLite/D1
enforces consistency, so the same concept drifted into several spellings:

- **bank identifier** → `bank_ticker` (audit / kap / faaliyet lanes), `ticker`
  (news, earnings), `symbol` (bist lanes)
- **fx amount leg** → `amount_fc`, `amount_fx`, `amount_yp`
- **period** → `year`+`month`, `period` (`'YYYYQn'` / `'YYYY-MM'`), `period_date`,
  `date`, `fiscal_year`
- **ingest timestamp** → `downloaded_at`, `extracted_at`, `fetched_at`

The problem is a *latent defect*: the naming decision is made while shipping lane
N, but the cost is paid much later — a cross-lane join, or the text-to-SQL bot
picking the wrong column. This doc + the linter move that cost forward to PR time.

## Canonical names

Decide once; copy from here instead of inventing per table.

| Concept | Column | Notes |
|---|---|---|
| Bank identifier (fact tables) | `bank_ticker` TEXT | The internal code (`GARAN`, `ANADOLU`). Same value everywhere; only the name was drifting. |
| Bank identifier (the `banks` dimension PK) | `ticker` TEXT | The one exception — a bare-noun dimension key. Join `banks.ticker = fact.bank_ticker`. |
| BIST market symbol | `bist_symbol` TEXT | Only where a table is genuinely about the traded instrument. |
| Quarterly period | `period` TEXT `'YYYYQn'` | e.g. `'2026Q1'`. The audit lane. |
| Sub-annual period | `period` TEXT `'YYYY-MM'` | Quarter/month-end series (tbb, tkbb). |
| Daily period | `period_date` DATE `'YYYY-MM-DD'` | Market/EVDS/weekly series. |
| Annual period | `fiscal_year` INTEGER | FY-ending-31-Dec tables (faaliyet). |
| Current-vs-prior discriminator | `period_type` TEXT | `'current'` \| `'prior'`. |
| TL amount leg | `amount_tl` REAL | |
| FX amount leg | `amount_fc` REAL | **Not** `amount_fx`. (Source-mirrored TP/YP tables keep `amount_yp` — see exceptions.) |
| Total amount | `amount_total` REAL | |
| Ingest timestamp | `downloaded_at` (scraped/API) · `extracted_at` (PDF) · `fetched_at` (http/news) | Pick by source type. TEXT/TIMESTAMP `DEFAULT CURRENT_TIMESTAMP`. |
| Boolean flag | INTEGER `0`/`1` | SQLite has no bool; don't use `BOOLEAN`. |
| Money / ratios | REAL | Not `DECIMAL(…)` / `FLOAT`. |
| Provenance | `source_page`, `raw_snippet`, `confidence` | Where a value is extracted from a document. |

## Rules (enforced ≥ 0022)

1. **snake_case** identifiers: `^[a-z][a-z0-9_]*$`. No camelCase, no capitals
   (SQLite identifiers are case-*insensitive* — `Ticker` and `ticker` collide).
2. **No SQLite reserved words** as table/column names (`order`, `group`, `check`,
   `references`, `index`, `default`, `values`, `key`, `column`, …). Rename, don't
   quote-around-it.
3. **Bank id = `bank_ticker`** in every table except the `banks` dimension.
4. **FX leg = `amount_fc`**, never `amount_fx`.
5. **One migration number = one file.** `NNNN_snake_desc.sql`, strictly
   increasing. (`0007` is a grandfathered duplicate; no new dups.)

## Keys, integrity & idempotency

- **D1 does not enforce foreign keys** — relationships are by convention. So the
  join key *must be named identically* across tables (that's what makes rule 3
  matter). A canonical dimension (`banks`) is the anchor.
- Give each table a **composite PRIMARY KEY on its natural key**; that key is also
  the dedupe/upsert key. Writers use `INSERT OR REPLACE` — **ingestion must be
  idempotent** (re-running a period is a no-op, never a dup-accumulate).
- **Additive migrations only:** `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE … ADD
  COLUMN`. SQLite's in-place `ALTER` is limited — to rename/retype a column, add a
  new one and backfill; don't rewrite a live column.
- **Mirror the Python DDL** (`src/*/schema.py` / the scraper) for any table the
  pipeline writes, so local SQLite staging and D1 agree (`push_to_d1` relies on it).

## Deliberate exceptions

Grandfathered / intentional — the linter does not flag these:

- **Legacy BDDK "star"** (`balance_sheet`, `loans`, `deposits`, `income_statement`,
  `financial_ratios`, `other_data`): `year`+`month` split period, `DECIMAL`,
  `BOOLEAN`, `amount_fx`. Predates this doc; not retrofitted (churn > benefit).
- **Source-mirrored columns** kept for provenance: `amount_tp`/`amount_yp`
  (nonbank), `fon_tipi`/`fon_kodu` (tefas), `dim_tr`/`period_tr` (tkbb). Faithful
  to the upstream vocabulary on purpose.
- **`banks.ticker`** — the dimension's bare-noun PK (rule 3 exemption).

## How it's enforced

`scripts/check_schema_naming.py` (stdlib-only) runs in the CI Python job and via
`pytest` (`tests/test_schema_naming.py`). It reports current drift as
informational notes and *fails* only on a rule violation in a migration numbered
≥ 0022. Bump `FIRST_ENFORCED` in the script if the baseline ever moves.
