---
description: Run every CI gate locally, update the docs that must move with the change, then commit and push to master.
argument-hint: [optional commit subject]
allowed-tools: Bash(git status:*), Bash(git diff:*), Bash(git log:*)
---

## Current state

- Branch/status: !`git status --short --branch`
- Staged + unstaged diff: !`git diff HEAD --stat`
- Recent commits (for message style): !`git log --oneline -8`

## Task

Ship the working-tree change. `$ARGUMENTS` — if provided — is the intended
commit subject; otherwise derive one from the diff.

### 1. Run the gates that CI will run

These are the exact steps in `.github/workflows/ci.yml`. Run them locally so
CI is a formality, not a discovery mechanism. Stop at the first failure and
fix it rather than reporting a red gate as "expected".

Python:
```
ruff check .
python scripts/check_pipeline_graph_sync.py
python scripts/check_docs_sync.py
python scripts/check_schema_naming.py
python scripts/check_no_pdfplumber.py
python scripts/check_calendar_fresh.py
python scripts/check_prose_claims.py
pytest
```

Web — only if the change touches `web/**`:
```
cd web && npm run lint && npx tsc --noEmit && npm run test
```

Skip a gate only when it cannot apply to this diff, and say which and why.

### 2. Docs are part of the change, not a follow-up

Before committing, check each and update in the **same** commit:

- **`docs/PROJECT_STATE.md`** — did coverage, a row count, a pass rate, or a
  known issue change? Update the "Last verified" date if you touched it.
- **`docs/OPERATIONS.md`** — `check_docs_sync.py` fails unless it names every
  workflow, every `secrets.*` / `vars.*` a workflow reads, and every
  `CloudflareEnv` key. A new secret or workflow input must be documented here
  or the gate is red.
- **`docs/ADMIN.md`** — did anything on `/admin` move?
- **`docs/CHANGELOG.md`** — dated entry for a user-visible or pipeline change.
- **`docs/SCHEMA_CONVENTIONS.md`** — new migration ≥ 0022 must conform
  (`bank_ticker` / `amount_fc` / snake_case / unique number).

### 3. Commit and push

Solo repo, work happens on `master` — commit and push there directly, no
branch, no PR.

**Stage explicit paths, never `git add -A`.** A concurrent session commits in
this same worktree; a blanket add sweeps up its in-progress work.

Write the message in the style of the recent commits above —
`type(scope): imperative subject`, lowercase, no trailing period. Body only
when the *why* isn't obvious from the diff. End with:

```
Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

Then push to `master`.

### 4. Report

State what shipped, which gates passed, which docs moved, and anything you
deliberately left out. If a gate failed and you could not fix it, say so
plainly with the output — do not push over it.
