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
| `docs/` | Canonical docs; `docs/knowledge/` holds dated investigation write-ups |
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

**`null` is not `0`.** A disclosure a bank never made and a figure it disclosed as
zero are different facts, and every layer — extractor, validator, API, both UIs —
keeps them apart. Rendering `null` as `0` invents data.

**No LLM sets a number.** Model output is editorial only; every figure on the site
is computed from stored rows. `scripts/check_prose_claims.py` enforces that a
printed claim is backed by a computation.

**New D1 migrations follow [docs/SCHEMA_CONVENTIONS.md](docs/SCHEMA_CONVENTIONS.md)**
(`bank_ticker`, `amount_fc`, snake_case), CI-gated. `web/migrations/` is the
schema source of truth — hand-authored, never generated from a live database.

**`docs/OPERATIONS.md` must name every workflow, secret and env key** the code
reads; `check_docs_sync.py` diffs it against `.github/workflows/` and
`web/cloudflare-env.d.ts`. Add the doc line in the same change as the secret.

## Working style

- Solo repo — commit to `master` directly and leave no stale branches behind.
- Docs are part of "done": a change that moves the system's state updates
  `PROJECT_STATE.md` / `OPERATIONS.md` / `ADMIN.md` in the same commit.
- Investigation write-ups go in `docs/knowledge/`, dated and status-marked.
- The **code** is AGPL-3.0. The **data** is not ours to relicense — BDDK, TCMB,
  TBB, KAP, TEFAS and BIST each carry their own terms, and redistribution
  (including via `/api/v1`) stays subject to them.
