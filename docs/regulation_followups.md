# Regulation tab — scheduled follow-ups & operational notes

_Last updated: 2026-07-19_

## FIXED (A): the weekly briefing was running with **no baseline**

**Status:** fixed 2026-07-19. Kept here because the *shape* of this bug —
shipped code path, un-shipped data pin, silent degradation — is the reusable
lesson.

**The fix, as shipped:**

1. `summarize-regulations.yml` gained optional `baseline_url` / `baseline_year`
   dispatch inputs, and runs `ingest_policy_baseline.py` **between** the R2
   snapshot pull and the snapshot upload. That placement is the whole point (see
   the trap below). Re-running with the same PDF is a content-hash no-op.
2. `summarize_regulations.py --require-baseline` (passed by the weekly run) now
   **fails** instead of generating an ungrounded briefing.
3. The workflow gained the standard Telegram failure alert; it previously had
   none, which is the other half of why this stayed invisible.

**Annual procedure** (TCMB publishes in late December): dispatch
`summarize-regulations.yml` with `baseline_year=YYYY` and `baseline_url` set to
the *Monetary Policy for YYYY* PDF. 2026's pin:
`https://www.tcmb.gov.tr/wps/wcm/connect/c2ac62b6-3112-4f33-a6ad-3817defff0be/December28.pdf?MOD=AJPERES&CACHEID=ROOTWORKSPACE-c2ac62b6-3112-4f33-a6ad-3817defff0be-pJACiUd`

**Measured effect** on the same 87-item feed: context ~32k → ~44.6k tokens, and
26 → **30** bullets across the five sections (an earlier attempt produced 32 —
run-to-run LLM variance, so read the direction, not the digit). The gains landed
where theory said they would: the *cumulative* regimes, whose rules are in force
but were not re-announced during the window — **TL Deposit Share 1 → 3**, **Loan
Growth Caps 5 → 7**. The newsy sections (Monetary Policy Stance, Other Actions)
barely moved, which is the expected signature: they were already well served by
the feed alone.

Live in D1 as of `generated_at 2026-07-19T19:31:17Z`.

### What actually went wrong (keep this)

**Status when found:** live degradation since **2026-05-29** — the day the
feature landed (f04778b). Not a regression: the baseline was **never once**
populated in production. Verified across every run from 2026-05-29 to
2026-07-19, all logging:

```
[briefing] WARNING: no baseline — run scripts/ingest_policy_baseline.py
```

**The trap that made it stick:** `ingest_policy_baseline.py` writes to the local
staging DB, but the briefing reads the **R2 snapshot**, and only
`summarize-regulations.yml` pulls that snapshot and uploads it back. So the
documented command — run locally, exactly as the docstring showed — produced a
database nothing in production ever read. It looked done and wasn't.

**Why nobody noticed for seven weeks:** the run warned and carried on, and an
ungrounded briefing still reads plausibly — it is only missing rules that were
never re-announced, which is invisible unless you know what should be there. A
warning nobody is paged for is not a guard.

**Found** while benchmarking DeepSeek on this task — an unrelated errand; see
[knowledge/openrouter-deepseek-eval-2026-07-19.md](knowledge/openrouter-deepseek-eval-2026-07-19.md).

Every production run logs:

```
[briefing] WARNING: no baseline — run scripts/ingest_policy_baseline.py
```

Confirmed on the live weekly runs of **2026-07-05, 2026-07-12 and 2026-07-19**
(`summarize-regulations.yml`), so it is not a one-off.

**What's broken:** `fetch_baseline()` reads `regulation_baseline` from the local
staging DB, and that table is **empty in the R2 snapshot** the workflow pulls.
So `build_context()` omits the BASELINE block entirely and every per-category
call sees only the dated press-release feed.

**Why it matters:** the grounding scaffold introduced in f04778b — the TCMB
annual *Monetary Policy for YYYY* document, whose annex tables list every rule
in force at year start — is the thing the per-category prompts are designed to
build **on top of**. Without it each section is reconstructed from ~330 days of
press releases alone, so any rule that was in force but not re-announced during
the window is invisible. The sections most exposed are the ones whose regime is
cumulative rather than newsy (RRs, TL deposit share, loan-growth caps).

**Fix:** run `scripts/ingest_policy_baseline.py`, confirm `regulation_baseline`
has the current year's row, and make sure the populated DB reaches the R2
snapshot (the summarize workflow re-uploads it; a local-only run does not).
Then re-check that the warning is gone in the next weekly log.

**Worth adding after the fix:** the run is *silently* degraded — it warns and
carries on, and the briefing still looks plausible. A missing baseline should
either fail the job or alert, the same way `check_calendar_fresh.py` guards the
hand-typed MPC dates.

Found while benchmarking DeepSeek on this task; see
[knowledge/openrouter-deepseek-eval-2026-07-19.md](knowledge/openrouter-deepseek-eval-2026-07-19.md).

## Scheduled follow-up (B): add BDDK Tebliğ source for CAR + Credit Card rules

**Status:** scheduled / not started.

**Why:** The `/regulation` "Current Regulatory Snapshot" (generated by
`scripts/summarize_regulations.py`, per-category architecture) currently
**skips** two BBVA-style sections — **"Regulations for CARs"** and
**"Regulations on Credit Cards"** — via the constant `UNSOURCED_CATEGORIES`
in `scripts/summarize_regulations.py`.

They are skipped because their rules are **not in any feed we scrape**:
- Our news scrapers cover TCMB press releases (`src/news/sources/tcmb.py`) and
  BDDK Duyuru announcements (`src/news/sources/bddk.py`).
- Capital-Adequacy forbearances / risk-weights and **post-2023** credit-card
  maximum-interest-rate / limit rules are published in **BDDK Tebliğ /
  Resmî Gazete**, which we do not ingest.
- When forced to produce those sections, the LLM leaked reserve-requirement
  rules into CARs or fabricated credit-card tier tables. Skipping is the honest
  interim behaviour.

**Goal:** add a source for that data so both sections can be re-enabled with
real, source-cited content.

**Suggested approach:**
1. Find the authoritative source:
   - Credit-card max interest rates: TCMB publishes the periodic card rate
     table (`tcmb.gov.tr`, "azami faiz oranları"); also BDDK Tebliğ.
   - CAR: BDDK capital-adequacy communiqués (sermaye yeterliliği), incl. the
     FX-rate-fixing forbearances and HTC&S treatment.
2. Add a scraper mirroring `src/news/sources/` (body extraction via
   `src/news/_htmltext.extract_body`), **or** extend the baseline ingestion
   (`scripts/ingest_policy_baseline.py`) to also pin these documents.
3. Ensure the extracted rules reach the summarizer context (as feed
   `news_items` or as additional baseline content).
4. Re-enable: remove the two names from `UNSOURCED_CATEGORIES` (or run with
   `--include-unsourced`), regenerate via the `summarize-regulations.yml`
   workflow, and verify on the live page that the sections show real,
   source-cited rules — not leaked RR rules or invented numbers.

**Validate against:** BBVA Research's "Monetary stance … macro-prudential
measures" page — `data/external_reports/Turkiye_Banking_Sector_Outlook_April26.pdf`
(page 4) — which has the correct current CAR + Credit Card content.

**Testing note:** the briefing LLM (Kimi) runs only in CI via
`.github/workflows/summarize-regulations.yml` (`KIMI_API_TOKEN` secret); there
is **no local key**, so test by dispatching that workflow and inspecting the
`regulation_briefings` row in D1 / the live page.

---

## Operational notes (current design)

### Cadence / automation
| Pipeline | Workflow | Schedule |
|---|---|---|
| Raw feed (scrape TCMB/BDDK + bodies) | `refresh-news-daily.yml` | Daily, 04:00 UTC |
| Snapshot summary | `summarize-regulations.yml` | Weekly, Sun 06:00 UTC |

- The summary **skips regeneration when its inputs are unchanged** (hash of
  feed items + baseline + `PROMPT_VERSION`, stored in the local-only
  `briefing_input_state` table). Quiet weeks = no Kimi calls.
- Force a run with `python scripts/summarize_regulations.py --force` or by
  bumping `PROMPT_VERSION` (which busts the hash).

### Yearly manual step — re-pin the annual baseline
The snapshot is grounded on TCMB's annual **"Monetary Policy for YYYY"** PDF
(its annex tables = the regime at year start). Auto-discovery isn't reliable
(the doc isn't in any scrapable feed/index), so each **December** when TCMB
publishes the new year's document, run:

```
python scripts/ingest_policy_baseline.py --year <YYYY> --url "<PDF URL>"
# then re-upload the R2 snapshot, or let the next pipeline run carry it
python scripts/ingest_policy_baseline.py --list   # verify
```

Idempotent (skips if the content hash is unchanged). The 2026 baseline is
already ingested.

### Where things live
- Summarizer: `scripts/summarize_regulations.py` (per-category calls, grounded
  on baseline, `UNSOURCED_CATEGORIES` gate, input-hash skip guard).
- Baseline ingest: `scripts/ingest_policy_baseline.py`; table `regulation_baseline`.
- Body/table/list extraction: `src/news/_htmltext.py`.
- Schema: `src/news/schema.py` (`news_items`, `regulation_briefings`,
  `regulation_baseline`, `briefing_input_state`).
- UI: `web/app/regulation/page.tsx` (snapshot + chips) and
  `web/app/regulation/RawFeeds.tsx` (sidebar drawer with table/list rendering).
- `regulation_baseline` and `briefing_input_state` are **Python-only** — not in
  `push_to_d1.py` SYNC_TABLES, so they travel only in the R2 SQLite snapshot.
</content>
