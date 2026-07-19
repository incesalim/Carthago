# Can we run our crons on Cloudflare instead of GitHub Actions? — 2026-07-19

**Status: FINDINGS, NOT ACTED ON.** User declined a trial. No code written, no
workflow changed. Cloudflare limits below were verified against
`developers.cloudflare.com` on 2026-07-19; re-check before acting, they move.

## Question

We schedule everything on GitHub Actions. Could Cloudflare run these instead?

## Verdict

**Cloudflare has cron triggers, but not a home for our pipeline.** The only
Cloudflare product that could run our Python stack is Containers, and moving
there costs more than the problem is worth. The motivating complaint —
GitHub's cron delay, `docs/OPERATIONS.md` "Cron didn't run on Saturday" — is
**not documented as fixed** by Cloudflare either.

## Why Workers can't host the pipeline

All 11 scheduled workflows share one shape:

```
pull data/bddk_data.db.gz from R2 → run Python → push_to_d1.py → re-upload snapshot
```

Two hard blockers:

1. **The snapshot is 498 MB** (`bddk_data.db`; `bank_audit.db` another 80 MB).
   A Worker has ~128 MB memory and no filesystem. Nowhere to put it, no
   `sqlite3` to read it.
2. **Native C extensions** — `pymupdf`, `pandas`, `lxml`. Workers run Pyodide
   (WASM in a V8 isolate); C extensions need Emscripten wheels.

Python Workers are **not** the escape hatch:

- Still **open beta** (`python_workers` compat flag).
- Pyodide *does* have pandas, numpy, lxml, scipy.
- **PyMuPDF does not fit.** Its only Emscripten wheel
  (`pymupdf-1.28.0-...-pyemscripten_2025_0_wasm32.whl`) is **18.4 MB** against a
  Worker size limit of **3 MB Free / 10 MB Paid** — adverse by ~2x even on Paid.
- `requests` is present but unusable for HTTP; only `aiohttp`/`httpx` work.
- No native-extension escape hatch on Workers. The documented path for
  arbitrary binaries is Containers.

Ties into [[feedback_never_pdfplumber]] / [[feedback_extractors_no_api]]: fitz is
non-negotiable, so any host that can't load fitz can't host extraction.

## The limits that decide the shape

| | Free | Paid |
|---|---|---|
| Cron triggers **per account** (not per Worker) | **5** | 250 |
| CPU per cron invocation | **10 ms** | 30 s (<1 h interval) / 15 min (≥1 h) |
| Wall clock per cron | 15 min | 15 min |

- The old "3 Cron Triggers per Worker" cap was **removed 2023-10-18**; the limit
  is now account-wide. (The Durable Objects Alarms doc still repeats the stale
  3-per-Worker claim — the changelog supersedes it.)
- Paid CPU is keyed to the *cron interval*: sub-hourly crons get 30 s, not 15 min.
- Wall clock is a **stricter** limit for crons than for HTTP Workers, which have
  no hard duration limit.

**We have 14 cron expressions** across 11 workflows (`refresh-bddk-bulletins.yml`
alone has 4). Free's account-wide cap of 5 does not cover that.

## Cloudflare Containers — the one option that would work

- **GA 2026-04-13**, Workers Paid. Official cron pattern exists:
  `triggers.crons` → `scheduled()` → `getContainer(env.CRON_CONTAINER).start()`.
- Arbitrary Docker image. Up to **4 vCPU / 12 GiB memory / 20 GB disk**.
  Our 498 MB snapshot and the full `requirements.txt` fit comfortably.
- Pricing: billed per 10 ms actively running; 25 GiB-hr memory + 375 vCPU-min
  included; memory/disk billed on *provisioned*, CPU on *actual use*.
- Docs don't state a max run duration for the cron→container pattern.

**Why we're not doing it:** we'd lose the Actions UI, logs, artifacts, and the
`workflow_dispatch` path that `/admin`'s Pipeline panel depends on
([[project_open_prs_admin_audit]]) — for a reliability win the docs won't confirm.

## The idea worth keeping on the shelf

Keep every Python script on GitHub; let a small Worker be the **alarm clock**
that pokes GitHub on time. The plumbing already exists:

- `web/app/lib/github.ts:176` — `dispatchWorkflow(file, {ref, inputs})`, allow-listed.
- The Worker already holds `GITHUB_DISPATCH_TOKEN` (fine-grained PAT, Actions r/w).

A dispatch is pure I/O, so **10 ms CPU is ample** — this works on Free. To beat
the 5-cron account cap: **one hourly trigger + a schedule table in the Worker**
that decides which workflow to fire this hour, collapsing 14 crons into 1. The
table would sit next to the `WORKFLOWS` allow-list, so the schedule stays in one
readable place.

Wrinkle: OpenNext owns `.open-next/worker.js`, so adding a `scheduled` handler
means threading it through the OpenNext entry. A standalone dispatcher Worker is
likely cleaner than touching the site build.

## The caveat that undercuts the whole motive

**Cloudflare documents no delivery guarantee, SLA, retry policy, or expected
delay for Cron Triggers.** The only timing statement is that scheduled Workers
"run on underutilized machines to make the best use of Cloudflare's capacity" —
opportunistic scheduling, the same *class* of behaviour as the GitHub delay,
just unquantified. `scheduled()` documents no retry-on-failure.

By contrast, **Durable Object Alarms carry an explicit at-least-once guarantee**
with exponential backoff (2 s, up to 6 retries), and **Workflows** (GA
2025-04-07) give durable multi-step execution with *unlimited per-step wall
clock* — the real escape from the 15-min cron cap. If we ever need a documented
guarantee for scheduled work, those are the primitives, not Cron Triggers.

There is no Cloudflare analog to GitHub's 60-day-inactivity auto-disable.

## If this is ever revisited

Don't migrate on a hunch. Shadow one workflow — Cloudflare cron dispatching it
in parallel with the existing GitHub schedule — for two weeks and compare actual
start times. That converts the guess into data for ~30 lines of reversible code.
