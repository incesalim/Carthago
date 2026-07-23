---
name: audit-lane-fix
description: Re-extract or repair a bank_audit_* lane (oci, cash_flow, equity_change, npl_movement, loans_by_sector, credit_quality, stages, capital, liquidity, fx_position, repricing, bank_profile, audit_opinion). Use whenever a lane shows validation errors, a /admin coverage-matrix cell is red, an extractor fix needs re-running across the fleet, or the user says "re-extract", "backfill the lane", "fix <lane>", "this bank's <statement> is wrong". Encodes which workflow to dispatch, the only_failing-vs-force choice, and the rules that make a run non-destructive.
---

# Fixing an audit extraction lane

## Before touching anything

1. **Read the current state, not the older docs.** `docs/PROJECT_STATE.md`
   (per-lane pass rates) → `docs/AUDIT_BANK_CATALOG.md` (what each bank
   actually files) → `docs/AUDIT_EXTRACTION_GUIDE.md`. A lane doc written
   three fixes ago describes a world that no longer exists.
2. **Diagnose before re-running.** A red cell has four distinct causes and
   only one of them is an extractor bug:
   - the extractor mis-parses a layout it does see;
   - the page has **no text layer** — bitmap or vector-outlined glyphs.
     `get_text()` returning empty is *not* evidence the bank didn't
     disclose it. Render the page and look before concluding anything;
   - **the wrong PDF is in R2** — consolidated filed under the
     unconsolidated key or vice versa. `sync_audit_reports.py --verify-basis`
     is read-only and exits non-zero on a mismatch;
   - the bank genuinely does not disclose it → that is an `N/A` fact about
     the *filer*, and belongs in the expected-coverage spine, not in a
     re-extraction.

   Trust cross-references inside the filing over the absence of a number.

## Where the work runs

**Extraction runs in CI, never on this machine.** Local is for reading
code, writing the fix, and light checks. Two hard reasons, not preference:

- the corpus is large and the local box is not the place for it;
- any step that pulls or uploads the **R2 snapshot** must sit *between*
  the pull and the upload inside the workflow. Run it locally and you
  mutate a DB production never reads — the run "succeeds" and changes
  nothing.

## Choosing the vehicle

| Situation | Dispatch | Why |
|---|---|---|
| One lane, any number of banks/periods | `reextract-statement.yml` | ~6–10 min for an all-periods lane. **This is the default.** |
| Extractor rewrite affecting the whole report | `backfill-audit.yml` | Full re-extract. **Never `banks=ALL`** — it blows the 180-min job timeout mid-run. Dispatch ~5-bank chunks; the `bddk-audit` concurrency group queues them. |
| Curated cell correction, not an extraction problem | `apply_overrides.py` path | See below. |

### `reextract-statement.yml` inputs

- `only_failing=true` (the default) selects partitions where
  `checks_failed>0 OR checks_passed=0` — the second clause catches stale
  empties. The non-destructive guard skips already-passing partitions, so
  the run can only improve things.
- `force=true` overwrites passing partitions too. **Required when the
  defect is in a derived table** — e.g. `credit_quality` passes while the
  `bank_audit_stages` built from it fails, so `only_failing` would never
  select it. The `credit_quality` lane rebuilds `bank_audit_stages` after
  the run.
- Never `--force` a whole lane speculatively. Force is a targeted tool;
  used broadly it destroys good partitions to fix a few bad ones.

Dispatch inputs have a trap: `gh workflow run -f banks=` does **not**
arrive as an empty string — the workflow default wins. Use an explicit
`ALL`/`NONE` sentinel and echo the resolved scope in the job log.

## Rules that do not bend

- **Balance sheet and P&L are frozen.** Never re-extract them wholesale.
  A targeted fix goes through `reextract_statement.py --statement <X>`.
- **fitz / PyMuPDF only.** `pdfplumber` is removed and a CI gate blocks
  it returning. Garbled fitz output → check `page.rotation` first.
- **Never hand-list the audit tables** on a push. `--table-set audit`
  expands to every `bank_audit_*` table in `src/audit_reports/registry.py`.
  The hand-written list silently omitted two tables for weeks while the
  push exited 0.
- **`not_disclosed` never takes `"*"`.** List the lanes explicitly.
  Missing is a fact about *us*; N/A is a fact about the *filer*.
- **P&L roman ordinals are not fixed.** The compressed template some
  participation banks file puts pre-tax at XVI, not XVII. Anchor by
  label; consumers join `bank_audit_pl_roles` rather than hardcoding an
  ordinal.

## Overrides (curated cells, not extraction)

`apply_overrides.py` **overwrites local from the R2 snapshot** as its
first act. The order is fixed:

```
pull → overrides → cleanup → push → UPLOAD
```

Skip the upload and the next run reverts your work. `push_to_d1` never
issues a `DELETE`, so a curated row survives a later push — but the
coverage spine is full-rebuild, so **re-sync `bank_audit_coverage` after
applying overrides** or `/admin` reads the pre-fix matrix.

P&L override inserts need an `item_order`. An appended roman with no
order falls out of the spine and the identity check silently skips it.
`--dry-run` on this script is **not** read-only.

## Finishing

A lane fix is not done when the numbers are right. Also:

- re-sync the coverage matrix and confirm `/admin` shows it;
- update `docs/PROJECT_STATE.md` (the lane's pass rate) and
  `docs/OPERATIONS.md` if the run introduced or changed a workflow input;
- record the diagnosis — especially a *silent-wrong* class, where the
  validator passed but the number was wrong. Those are the ones that
  cost the most to rediscover.
