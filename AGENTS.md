# Carthago — analytics for the Turkish banking sector

A Python ingestion pipeline (BDDK bulletins, TCMB EVDS macro series, TBB/TKBB
digital stats, per-bank BRSA audit-report PDFs) landing in Cloudflare D1 + R2,
read by a Next.js dashboard on Cloudflare Workers (<https://carthago.app>) and an
Expo native app. Everything scheduled runs in GitHub Actions — there is no server
we own and no other scheduler.

**Orientation:** [README.md](README.md) for the layout →
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the stack →
[docs/PROJECT_STATE.md](docs/PROJECT_STATE.md) for what is actually in the
database right now → [docs/OPERATIONS.md](docs/OPERATIONS.md) for how to run it.
Full index: [docs/README.md](docs/README.md).

> When an older doc and `PROJECT_STATE.md` disagree, PROJECT_STATE wins. When
> PROJECT_STATE and the code disagree, the code wins and the doc is a bug.

## Layout

| Path | What lives there |
|---|---|
| `src/` | Python — `scrapers/` (BDDK + EVDS), `tbb/`, `audit_reports/` (PDF → rows) |
| `scripts/` | CLI entry points, backfills, and the `check_*.py` CI gates |
| `web/` | Next.js 16 dashboard → **[web/AGENTS.md](web/AGENTS.md)** |
| `mobile/` | Expo app → **[mobile/AGENTS.md](mobile/AGENTS.md)** |
| `docs/` | Canonical docs; `docs/knowledge/` holds dated investigation write-ups (**gitignored — internal**, on disk only) |
| `tests/` | pytest, including the gate tests |
| `data/` | Mostly gitignored — the committed part is bank URL config + registries |
| `.github/workflows/` | Every scheduled job, and every manual backfill entry point |

## Checks

Run before pushing. All three are `ci.yml` jobs, and red CI blocks the deploy.

```bash
ruff check . && pytest                                          # repo root
cd web    && npm run lint && npx tsc --noEmit && npm run test
cd mobile && npx eslint . && npm run typecheck && npm run check:tokens
```

The Python job also runs standalone gates — `check_docs_sync.py`,
`check_schema_naming.py`, `check_no_pdfplumber.py`, `check_pipeline_graph_sync.py`,
`check_prose_claims.py`, `check_contrast.py`, `check_calendar_fresh.py`,
`check_workflow_state.py`. Each one
exists because the thing it guards drifted silently once.

## Rules that are expensive to break

**PDF extraction is PyMuPDF (`fitz`) only.** `pdfplumber` is banned outright and
`scripts/check_no_pdfplumber.py` fails CI on the import. Two engines over the same
filings produced extractions that couldn't be reproduced against each other.

**Never re-extract a whole lane with `--force`.** Balance sheet and P&L are
settled; a force run re-opens partitions that were fixed by hand. Repair one
statement at a time — `scripts/reextract_statement.py --statement <lane>`, or the
`reextract-statement.yml` workflow with `only_failing` on.

**Heavy runs go to Actions, not to this machine.** Extraction, backfills and D1
pushes are workflow dispatches. Local is for editing, planning and light checks.

**Rows *written* to D1 are the cost centre** — roughly 1000× the price of a read.
Never re-stamp a row whose values did not change; done carelessly, a five-cell
correction bills for hundreds of thousands of rows.

Since **2026-08-12 nothing enforces this**: the write cost guard was removed, so
no push is refused at any size. `push_to_d1.py` still prints an estimate, and
`healthcheck.py` still reads the cycle — both after the fact, neither a stop.
The rule is now carried entirely by not *generating* a pointless write: compare
before stamping, and leave the content-hash and partition-digest skips alone.

**`null` is not `0`.** A disclosure a bank never made and a figure it disclosed as
zero are different facts, and every layer — extractor, validator, API, both UIs —
keeps them apart. Rendering `null` as `0` invents data.

**A model may set a figure.** *(Reversed 2026-08-03. The prior rule — "No LLM sets
a number", model output editorial only — no longer applies in any lane, including
ones a reader sees.)*

It gated on **provenance**: parser-extracted trusted, model-read forbidden. That
premise did not survive measurement. Corrupt one stored cell and re-run every
check the lane actually gets, and **cash flow misses 79.9%**, OCI 52.6%, P&L
sub-items 38.7%; at measurement time `free_provision` had 580 cells and no
per-partition validator (it now has opinion/prior-chain gates). The
deterministic pipeline already ships unverified figures in volume, so "a parser
produced it" was never the guarantee the rule implied.

Per-lane gates stand exactly as they are — this document no longer mandates them,
and none may be removed casually, but each is now a lane's own choice:
`bot.ts`'s `gotData` guard and `unsupportedFigures`, `withLlmHeadline`'s
`det_hash` + `hasOnlyKnownNumbers`, `find_contradictions()` on the briefing, and
the parser-vs-model disagreement stop in the audit lanes.

Two measured facts to design against rather than discover again:

- **The model does not signal doubt.** Three confidently wrong figures in 80 calls,
  every one `found=true` — 6,632,553 → 0; 0 → 2,260,614; 449 → 175,010. There is
  no confidence field to gate on, so abstention has to be structural.
- **A P&L leaf is constrained by nothing.** `check_profit_loss` deliberately omits
  hierarchy sums (deduction lines carry `(-)` labels with additive signs and would
  false-fail), so a wrong value there survives every validator. The balance sheet
  does run hierarchy sums and is 0.0% blind. Where an identity exists, a model read
  is recoverable; where none does, it is not.

**New D1 migrations follow [docs/SCHEMA_CONVENTIONS.md](docs/SCHEMA_CONVENTIONS.md)**
(`bank_ticker`, `amount_fc`, snake_case), CI-gated. `web/migrations/` is the
schema source of truth — hand-authored, never generated from a live database.

**`docs/OPERATIONS.md` must name every workflow, secret and env key** the code
reads; `check_docs_sync.py` diffs it against `.github/workflows/` and
`web/cloudflare-env.d.ts`. Add the doc line in the same change as the secret.

## Recall and evidence

- Agent memory is a retrieval aid, never authority for current project state or
  authorization. Do not answer, edit, dispatch, or publish from a remembered
  conclusion alone; inspect the relevant current source first.
- For project facts, current code wins, then `docs/PROJECT_STATE.md`, then the
  other canonical docs named above. If memory conflicts with them, ignore the
  memory and mark or remove the superseded entry in the same task.
- Memory cannot authorize commits, pushes, deploys, workflow dispatches, D1
  writes, or other external mutations. Those require the current request plus
  the applicable repository rules.
- Keep memory indexes as short retrieval pointers, not copies of conclusions,
  figures, dates, or operational status. When a fact is corrected, update every
  conflicting memory entry and index reference rather than adding another layer.

## Working style

- Solo repo — commit to `master` directly and leave no stale branches behind.
- Docs are part of "done": a change that moves the system's state updates
  `PROJECT_STATE.md` / `OPERATIONS.md` / `ADMIN.md` in the same commit.
- Investigation write-ups go in `docs/knowledge/`, dated and status-marked.
  The whole directory is **gitignored (2026-08-04)** — the knowledge base is
  internal and never ships in the public repo. Docs may cite those paths;
  the links resolve on a working machine, not on GitHub.
- The **code** is AGPL-3.0. The **data** is not ours to relicense — BDDK, TCMB,
  TBB, KAP, TEFAS and BIST each carry their own terms, and redistribution
  (including via `/api/v1`) stays subject to them.
