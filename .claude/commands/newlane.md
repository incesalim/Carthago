---
description: "Scaffold a new data lane end to end: schema, ingestion, validation, UI, automation, and documentation."
argument-hint: <lane name> [audit-statement | data-source]
---

Scaffold the lane described by `$ARGUMENTS`. State whether it is an
`audit-statement` or `data-source` lane. If the choice cannot be inferred without
materially changing the design, ask before implementing it.

This command authorizes the scoped repository implementation. It does not by
itself authorize a commit, push, deployment, workflow dispatch, D1/R2 write, or
cache purge. Leave those for an explicit request such as `/ship` or a requested
first production run.

## 1. Inspect current sources of truth

Read the root `AGENTS.md` and any nested instructions for touched directories.
Then inspect:

- `src/audit_reports/registry.py` for audit lane topology;
- `web/migrations/` and `docs/SCHEMA_CONVENTIONS.md` for schema conventions;
- `scripts/refresh.py`, relevant update scripts, and current workflows for
  ingestion topology;
- `web/app/lib/chart-specs.catalog.json` for chart contracts;
- `.github/workflows/ci.yml` for the checks that exist now.

Do not copy a lane shape from memory. Recheck the highest migration number
immediately before creating the migration because other sessions share this
worktree.

## 2. Add the schema

- Use the next unused migration number; never reuse a number.
- Follow `docs/SCHEMA_CONVENTIONS.md`, including `bank_ticker`, `amount_fc`,
  snake_case names, natural keys, and current migration structure.
- Keep `null`, disclosed zero, missing, and not-applicable semantically distinct.
- If a workflow must run before the normal deploy applies the migration, use an
  existing reviewed remote-DDL pattern and document it. Do not execute it now
  unless production execution was explicitly requested.

## 3. Build ingestion

For an audit statement:

- Add its `StatementType` to the registry with correct section provenance,
  severity, annual-only, conditional, table, re-extraction, and validation
  metadata.
- Add the extractor under `src/audit_reports/` using PyMuPDF (`fitz`) only.
- Anchor by labels and filing structure, not fixed Roman ordinals.
- Render pages when text extraction is empty or garbled before classifying a
  disclosure as absent.

For an external data source:

- Add the scraper in the established package and connect it to the appropriate
  refresh cadence.
- Define and enforce the true natural key.
- Compare fetched business values with stored values and write only new or
  changed rows. `INSERT OR REPLACE` by itself is not cost-safe idempotence
  because unchanged rows are still billed when pushed to D1.
- Preserve corrected vintages without restamping settled rows.

## 4. Add validation and push routing

- Prefer structural reconciliation, source anchors, and cross-statement
  identities over plausibility bands.
- For an audit lane, register the validator and dependencies so repair routing,
  coverage, and `--table-set audit` derive from the registry. Never hand-list
  audit tables.
- For a non-audit table, add the narrow push route and confirm its workflow names
  the intended table.
- Review full-rebuild and partition-replacement behavior carefully. An empty
  local source must not erase valid remote data, and deletes must be atomic with
  replacement rows.

## 5. Add the product surface

- Follow `web/AGENTS.md` and `web/DESIGN.md` for dashboard work.
- Reuse shared chart colors and number formatters.
- Add a chart catalog entry with an authoritative verification date, value, and
  tolerance for every new quantitative chart.
- Generate prose claims from data through the existing prose helpers rather
  than hard-coding changing directions, rankings, or levels.
- If the mobile app changes, follow `mobile/AGENTS.md` and its token rules.

## 6. Add automation and documentation

- Add or update the appropriate workflow without silently enabling a schedule.
- Keep `web/app/lib/pipeline-graph.ts` synchronized with workflow topology.
- Use explicit input sentinels where an empty dispatch value would resolve to a
  default, and print the resolved production scope.
- Update `docs/PROJECT_STATE.md`, `docs/OPERATIONS.md`,
  `docs/ARCHITECTURE.md`, `docs/ADMIN.md`, and `docs/CHANGELOG.md` only where the
  change affects their stated contract.
- Document every workflow, secret, variable, environment key, schedule, and
  manual input introduced by the lane.

## 7. Verify and hand off

Run the checks required by the current root and nested instructions, scoped to
the files changed, unless the user explicitly opts out. Read the current CI
workflow rather than relying on a copied gate list. Include focused tests for
the new natural key, no-op write behavior, null-versus-zero handling, validator,
and chart verification as applicable.

Report what was implemented, which checks ran, what did not run, and the exact
production action still required. Do not commit or run the first ingestion
unless the current request explicitly asks for it. When a production run is
authorized, use GitHub Actions for heavy work, inspect per-series or
per-partition logs, and verify the resulting rows rather than trusting exit
status alone.
