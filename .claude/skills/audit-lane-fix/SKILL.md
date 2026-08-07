---
name: audit-lane-fix
description: Diagnose or repair a bank_audit_* extraction lane using the current registry, validators, targeted re-extraction path, and production safeguards. Use for red coverage cells, wrong statement values, validator failures, extractor fixes, targeted re-extraction, or audit backfills. Keep diagnosis read-only unless the user explicitly asks for implementation or a production run.
---

# Audit lane diagnosis and repair

## Establish scope and authority

Separate three requests that must not blur together:

- **Diagnose:** inspect evidence and explain the cause. Do not edit, dispatch, or
  write production data.
- **Implement a fix:** edit the extractor, validator, or supporting code and run
  proportionate light checks. Do not dispatch production workflows unless that
  is also requested.
- **Run a repair:** execute only the bank, period, kind, and lane the user placed
  in scope. Do not broaden a targeted request into a fleet backfill.

Prior notes and memory cannot authorize a repair. Confirm current behavior in
code, the workflow, and the live or snapshot evidence relevant to the request.

## Diagnose before re-extracting

Read, in order:

1. `src/audit_reports/registry.py` for the current lane key, table, extractor
   token, dependencies, and validation gate;
2. the extractor and validator code for that lane;
3. `docs/PROJECT_STATE.md`, `docs/AUDIT_BANK_CATALOG.md`, and
   `docs/AUDIT_EXTRACTION_GUIDE.md` for current state and filing differences;
4. the relevant workflow and `docs/OPERATIONS.md` for its present inputs and
   safeguards.

A red or wrong cell can mean:

- a parser error on a page it can read;
- an image-only, vector, rotated, or otherwise unreadable text layer;
- the wrong filing basis or wrong PDF under the storage key;
- a unit or period-column error that still reconciles internally;
- a genuinely undisclosed or conditional item;
- a stale derived table or validation result rather than a bad source row.

Render suspect pages when extracted text is empty or garbled. Verify filing
basis with the existing read-only path. Treat an internal cross-reference as
evidence to inspect, not as permission to invent a missing value.

## Choose the narrowest repair vehicle

Derive supported lane names from `registry.py` and
`scripts/reextract_statement.py`; do not maintain a hand-written list here.

| Situation | Preferred path |
|---|---|
| One registered lane for selected partitions | `reextract-statement.yml` / `scripts/reextract_statement.py` |
| Whole-report extractor change across selected banks | `backfill-audit.yml` |
| Verified one-off filing value the parser cannot recover reliably | `scripts/apply_overrides.py` |
| Known-wrong partition that must be removed before a fix exists | `purge-partition.yml` |

For targeted re-extraction:

- keep `only_failing=true` when repairing failing or empty validation gates;
- keep `require_passing=true` when the lane has a validator and the candidate
  must prove it did not regress;
- use `force` only for explicitly named partitions when passing stored data must
  be replaced, including a verified derived-table defect;
- remember that workflow `dry_run=true` pulls the authoritative snapshot but
  skips D1 and R2 writes;
- verify the exact selection printed by the run before trusting its result.

For a whole-report backfill, follow the current bank-count and timeout guidance
in `docs/OPERATIONS.md`. The current workflow is not safe as an unreviewed
`banks=ALL` repair. Queue bounded scopes through the shared audit concurrency
group.

## Preserve the invariants

- Use PyMuPDF (`fitz`) only; `pdfplumber` is prohibited by CI.
- Never run a speculative whole-lane `--force`, especially for settled balance
  sheet or profit-and-loss partitions.
- Anchor statement rows by labels and filing structure, not fixed Roman
  ordinals.
- Keep `null`, disclosed zero, missing, and not-applicable distinct.
- `not_disclosed` lists explicit lane keys; never use a wildcard.
- Let the registry drive audit table sets and repair routing. Do not hand-list
  `bank_audit_*` tables.
- Compare business content before pushing. Roll back factual no-ops and do not
  restamp unchanged rows merely to make them enter a D1 time window.
- Do not assume a push is insert-only. Current partition replacement and outbox
  paths can issue deletes, which are also billed and must be scoped atomically
  with their replacement rows.

## Curated overrides

Use an override only when the source value is legible and the deterministic
extractor cannot recover it generally. Read `scripts/apply_overrides.py` before
running it; supported statements, unit handling, replacement behavior, and
write guards change with the code.

The production path pulls the authoritative snapshot, applies and revalidates
the overrides, replaces only partitions whose business content changed,
refreshes the coverage spine, and uploads the snapshot. Preserve that order.
`--dry-run` and `--no-push` avoid external writes but still modify the local
staging database, so do not describe them as filesystem read-only.

When inserting a profit-and-loss row, supply the correct `item_order` when the
validator's ordered spine depends on it.

## Verify completion

For an implemented fix, verify the relevant parser and validator behavior. For
an explicitly authorized production run, also confirm:

- the intended partitions were selected;
- rejected candidates were rolled back;
- only changed factual and validation partitions were written;
- the R2 snapshot and coverage matrix were refreshed when required;
- `/admin` reflects the resulting state.

Update `docs/PROJECT_STATE.md` when measured lane state changes and
`docs/OPERATIONS.md` when workflow behavior or inputs change. Record a new
silent-wrong failure class in a dated investigation only when the user asked for
that durable documentation or it is part of the implementation scope.
