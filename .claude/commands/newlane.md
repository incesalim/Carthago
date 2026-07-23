---
description: Scaffold a new data lane end-to-end — table, migration, ingest, validation, UI, workflow, docs — with the steps that get forgotten made explicit.
argument-hint: <lane name> [audit-statement | data-source]
---

## Current state

- Highest migration: !`ls web/migrations | tail -3`
- Audit table-set source of truth: `src/audit_reports/registry.py`
- Chart catalog: `web/app/lib/chart-specs.catalog.json`

## Task

Scaffold the lane described by `$ARGUMENTS`. Two shapes — pick from the
argument or infer, and say which you picked:

- **audit-statement** — a new `bank_audit_*` statement type extracted from
  the BRSA quarterly PDFs.
- **data-source** — a new external feed (EVDS / TÜİK / TBB / an API) landing
  in its own table.

Work through the checklist. Do not skip a step silently: if one doesn't
apply, say so and why.

---

### 1. Migration

Next number is one above the highest above — **numbers are unique, never
reused**, and `scripts/check_schema_naming.py` gates ≥ 0022 against
`docs/SCHEMA_CONVENTIONS.md`:

- per-bank key column is `bank_ticker` (never `ticker`, `bank`, `symbol`)
- foreign-currency amounts are `amount_fc`
- snake_case throughout, no SQL reserved words
- one `CREATE TABLE IF NOT EXISTS` per migration file

Migrations apply on a `web/**` push via `deploy-cloudflare.yml`. If the lane
needs the table before the next deploy, its workflow should run the DDL
against remote D1 itself (`build-products.yml` does this).

### 2. Ingest

**audit-statement:**
- Add a `StatementType(...)` to `REGISTRY` in `src/audit_reports/registry.py`.
  Get these right, they are load-bearing:
  - `section` — the report Bölüm ('2' primary statement, '5' note, '4' risk
    disclosure). This is **provenance**, and what the /admin matrix groups on.
  - `is_core` — **severity only**. True means "an empty lane here fails the
    whole report". OCI / equity-change / cash-flow / off-balance are §2
    primary statements deliberately marked `is_core=False`. Do not conflate
    the two flags; the matrix mislabelled four statements for months by
    grouping on `is_core`.
  - `annual_only` — disclosed only in the Q4 report → interim cells are N/A,
    not missing.
  - `conditional` — disclosed only when the bank holds one → empty means
    "no such item", also N/A.
- Extractor in `src/audit_reports/`. **fitz / PyMuPDF only** — a CI gate
  blocks `pdfplumber`. Garbled text → check `page.rotation` first. Empty
  `get_text()` means render the page and look; it is not evidence of
  non-disclosure.
- Anchor rows by **label**, never by roman ordinal. BRSA ordinals are not
  fixed across filers.

**data-source:**
- Scraper module under `src/scrapers/` (or its own package for a bigger feed).
- Make it idempotent — `INSERT OR REPLACE` on the natural key. Check the key
  really is unique: `other_data` collides on `item_order` alone and needs
  `item_name` too.
- Wire into `scripts/refresh.py`, or give it its own `update_*.py` if it has
  a different cadence.

### 3. Validation

- **audit-statement:** set `has_validator=True` + `validation_statement`,
  and add the structural checks. Validate by **reconciliation** (parent =
  Σ children, cross-statement identities), not by plausibility bands —
  bands pass silently-wrong numbers and reject legitimate new banks.
- **data-source:** if the lane feeds a chart, a `verify` block in the chart
  catalog (step 5) is the equivalent gate.

### 4. Push path

- Audit tables: covered automatically by `--table-set audit`, which expands
  from the registry. **Never hand-list tables** — the literal list that used
  to exist omitted two tables for weeks while the push exited 0.
- New non-audit table: confirm `push_to_d1.py` picks it up, and that the
  lane's workflow passes `--only-tables` where it should.
- Full-rebuild tables (`DELETE` + `INSERT`) are dangerous from a lane whose
  local copy is empty — that is how the coverage matrix got wiped. The guard
  skips a full-rebuild table when local is empty; don't defeat it.

### 5. UI

- Page or section under `web/app/`, following `web/DESIGN.md` ("The Desk").
- Chart colours from `app/lib/chart-theme.ts`, number formatting from
  `app/lib/chart-format.ts` (`nf`, `formatters`) — don't re-declare a local `nf`.
- **Add an entry to `web/app/lib/chart-specs.catalog.json`** with a `verify`
  block (series / date / value / tolerance). `scripts/verify_chart_spec.py`
  runs in the daily healthcheck and is what catches a silently-empty chart —
  a 0-row query renders a blank panel, not an error.
- Any sentence asserting a direction, level or ranking must be **computed**
  via `lib/prose.ts` (`direction()` / `claim()` / `seriesFinding()`), or it
  fails `scripts/check_prose_claims.py`.

### 6. Automation

- New workflow in `.github/workflows/`, or a step on an existing one.
- Add it to `web/app/lib/pipeline-graph.ts` — `check_pipeline_graph_sync.py`
  requires the topology and the workflow files to reference each other both
  ways.
- Dispatch inputs: `-f x=` does **not** arrive empty, the default wins. Use
  an explicit `ALL`/`NONE` sentinel and echo the resolved scope.

### 7. Docs — part of this change, not a follow-up

- `docs/PROJECT_STATE.md` — a row in the coverage table: source, range, what
  it actually contains, and any known defect.
- `docs/OPERATIONS.md` — the workflow, its schedule, **every** `secrets.*` /
  `vars.*` it reads. `check_docs_sync.py` fails otherwise, and an
  undocumented secret is a lane that dies silently on re-provision.
- `docs/ARCHITECTURE.md` if the shape of the system changed.
- `docs/CHANGELOG.md` — dated entry.

### 8. Gates

Run the CI set before committing (see `/ship`), then commit to `master`
staging explicit paths.

### 9. First run

Ingest runs in **CI, not locally** — and any step touching the R2 snapshot
must sit between the workflow's pull and upload, or it writes a DB
production never reads. Dispatch the workflow, read the log rather than
trusting the exit code, then confirm the data reached D1 and the page.
Public pages cache D1 reads, so allow for the lag or purge the cache.
