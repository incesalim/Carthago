---
description: Verify the intended working-tree change, update required docs, commit explicit paths, and push master.
argument-hint: [optional commit subject]
---

Ship the intended working-tree change. `$ARGUMENTS`, when provided, is the
intended commit subject; otherwise derive one from the reviewed diff.

Invoking `/ship` authorizes the in-scope commit and push described here. It does
not authorize staging unrelated work, deploying manually, dispatching data
workflows, or mutating production data.

## 1. Establish exactly what belongs to this change

- Read the root `AGENTS.md` and nested instructions for every touched area.
- Inspect branch, status, staged and unstaged diffs, and recent commit style.
- Identify files that belong to this request versus pre-existing or concurrent
  work. Shared-worktree changes belong to their author unless proven otherwise.
- Review the actual diff, including generated files and migrations, before
  staging anything.

If ownership or scope cannot be resolved safely, stop before staging and ask.

## 2. Run the current required checks

Read `.github/workflows/ci.yml` and the applicable `AGENTS.md` files at execution
time. Run the commands they require now; do not rely on a copied checklist in
this command.

Cover every applicable CI job, including Python gates and tests, web lint/type
checks/tests, and mobile lint/type/token/bundle checks. Use focused checks first
when they shorten the feedback loop, then run the required full set before
pushing.

Stop on a real failure, fix it within scope, and rerun the affected check. If a
required check needs unavailable credentials, network access, or an environment
that cannot be reproduced locally, name it precisely and do not call it passed.
Do not push past an unresolved required check unless the user explicitly accepts
that risk after seeing the limitation.

## 3. Keep documentation synchronized

Update only the documents whose current contract changed:

- `docs/PROJECT_STATE.md` for deployed or measured state, coverage, counts,
  pass rates, and known defects;
- `docs/OPERATIONS.md` for workflows, schedules, inputs, secrets, variables,
  environment keys, and runbooks;
- `docs/ADMIN.md` for `/admin` behavior;
- `docs/ARCHITECTURE.md` for system topology;
- `docs/CHANGELOG.md` for a user-visible or pipeline change;
- `docs/SCHEMA_CONVENTIONS.md` only when the convention itself changes.

Do not claim a production state change merely because code for it was committed.

## 4. Commit safely

- Recheck status after validation because another session may have changed the
  worktree.
- Stage explicit paths only. Never use `git add -A`, `git add .`, or another
  blanket add.
- Inspect the staged diff and staged file list before committing.
- Use the repository's current message style: `type(scope): imperative subject`,
  lowercase, no trailing period unless recent history shows otherwise.
- Add a co-author trailer only when a real co-author and the user explicitly
  require it. Never hard-code a model name or version into attribution.

Commit on `master` as required by the repository instructions, then push the
current `master` commit to its configured remote. Do not create a branch or pull
request unless the user asks or the repository instructions change.

## 5. Verify and report

After the push, verify the remote accepted the intended commit. Report:

- the commit and what shipped;
- every check that passed;
- any check not run or limitation explicitly accepted by the user;
- documentation updated;
- unrelated files deliberately left unstaged;
- any separate deployment or data workflow still required.
