# Changelog

Dated history of pipeline and dashboard changes, newest first. For the
current state of the system see [PROJECT_STATE.md](PROJECT_STATE.md).

Last verified: 2026-08-20.

2026-08-20 — **The fourth graduation (leverage), and the machinery became a
module.** Three numbered-template builders shared everything but the
template's facts, so `src/audit_reports/numbered_template.py` now holds the
shared mechanics — signature detection by printed row number, the per-block
column model, wrap adoption (a numbered row with no values takes the
unnumbered line above it, GARAN's leverage row 1), the instance split, and
a per-template percent-repair floor — and the LCR and NSFR builders run on it
with fleet output identical to the digit. `bank_audit_leverage_full` (rows
1–15, current + prior-year-end columns) followed as ~80 lines: 621
partitions / 8,177 rows, current anchor 99.8% vs narrow `leverage_ratio`,
prior 98.5%, identity 13/14 at 99.8%. The leverage floor is 1,000 — "9,127"
read as an integer is 9.127%, which the LCR's 10,000 floor would have missed.
Four lanes graduated so far (capital 75,111 rows · LCR 28,915 · NSFR 26,910 ·
leverage 8,177), all local, all anchored.

2026-08-20 — **The third graduation: the full NSFR template — and the wide
lane started auditing the narrow one.** `scripts/build_nsfr_full.py` mints
`bank_audit_nsfr_full` from the document layer (rows 1–34, four maturity
buckets + weighted total, current + prior-year-end instances): 435
partitions, local only. The per-block column model — rowno column by
majority, phantom all-None columns dropped, total ALWAYS rightmost — is
what fixed AKBNK's ratio landing in a bucket slot. Anchors: 96.8% current /
91.9% prior-year-end vs narrow `nsfr`; the asf/rsf identity holds at 99.1%
within 0.5 over 761 instances (a point calculation, so the tight band
applies, unlike the weekly-averaged LCR). The mismatches now indict the
NARROW lane: HALKB 2024Q3's wide 143.54 reproduces exactly from its own
ASF/RSF cells against narrow's 133.51, and HSBC 2024Q1 likewise — three
independent captured cells vs one. Four pinning tests.

2026-08-20 — **The second graduation: the full LCR template, and the
regulator did half the work.** BRSA numbers the LCR rows 1–23 and the
capture kept the numbers as cells, so `bank_audit_lcr_full` joins on
`template_row` across banks and languages — no label regex carries identity.
`scripts/build_lcr_full.py` assembles BOTH printed tables per filing (current
quarter and prior YEAR-END — the same BRSA prior-column convention the fx
lane documented; AKBNK's Q2–Q4 2022 filings all printing 203.49 is what
exposed it), splits instances on a number restart, scales money at mint,
never scales the percent row, and repairs ALBRK's three-decimal integer
misparse while leaving ENPARA's genuine 34,221.52% untouched (the decimals
are the discriminator). Fleet: 656 partitions / 28,915 rows, local only.
Anchors: current LCR 94.3%/94.8% vs the narrow pair, prior instance 93.3% vs
December's narrow row — with part of the residue indicting the NARROW lane
(ATBANK's stale-copy fingerprint). The 23≈21/22 identity reads 82.0% within
0.5 and 94.2% within 10, the wide band being the honest one: row 23 is the
average of weekly ratios, not the ratio of the averaged rows. Five pinning
tests; NSFR (rows 1–34) is the named next graduation.

2026-08-20 — **The first lane graduated from the document layer: the full
own-funds table.** The capital pilot proves the agreed architecture — new
analytical coverage minted from captured grids, never from a PDF.
`scripts/build_capital_full.py` assembles the Basel III own-funds template
(median 93 rows per filing vs the 9 fields `bank_audit_capital` serves) from
`bank_audit_tables.db`: seeded by the template's own opening row in either
dialect (the tasfiyesi opener, or YKBNK/ALBRK's bare header with a min-rows
guard), chained across contiguous pages, truncated at a second full-template
printing, money scaled declared_unit→bin at mint, ratios never scaled, "-"
kept NULL. Fleet: 873 partitions / 75,111 rows, local only. The narrow lane
is the external validator, and it agrees: cet1 99.5%, tier1 99.6%, tier2
99.5%, rwa 99.0%, ratios 98.6–99.2%, total 97.8% (that total row is one the
narrow lane itself stored inconsistently — sum for AKBNK, post-deduction
final for ANADOLU — so the wide lane keeps BOTH as separate roles);
tier1=cet1+at1 at 98.0%. The ~200 undetected-but-narrow-covered partitions
print only the ~10-row summary table — the older interim-disclosure regime —
so there is no full template there to graduate. Six pinning tests.

2026-08-20 — **The derived table lane survived four independent attacks, and
two of them drew blood first.** Before anything durable is saved from
`bank_audit_tables.db`, it was verified against evidence that never saw its
builder: (A) section starts vs the prose lane's independent engine — 97.7% of
6,993 role-starts within ±1 page over 1,040 filings, the tail adjudicated
against the filings themselves (GARAN prints "7 Interim Activity Report" on
p136, where this lane places it; prose's min-page takes a p6 stray on its
documented weak filer); (B) the validated balance-sheet + P&L figures found
inside the grids this lane calls `financial_statements` — median 100%,
p1 98.8% over 1,015 partitions, both sub-90% cases explained (a vector page;
ATBANK 2022Q2's placement tail); (C) notes 60,464/60,464 and links 70,497 of
70,515, the 18 being two marker lines of one wrapped row collapsing into its
single row; (D) the 2,906 role-less tables are the 24 honestly unsectioned
filings, TSKB's 14-page statements-only 2026Q2 among them. The blood: ISCTR's
inline-title banners ("SECTION ONE: GENERAL INFORMATION…") had the NEXT line —
the first item, "I. Explanations on…" — read as the title, relabelling §1 as
notes; and a note linked across blocks mapped into the wrong table's rows
because `logical_row` restarts per block (HALKB's "(1)" citations). Both fixed
with pinning tests; marker lines outside a grid now persist as `outside_lines`
instead of silently vanishing (13,461 notes had read as link-less). Still
local-only by explicit decision; D1/R2 remains open.

2026-08-20 — **The full-document capture became queryable table by table,
section by section.** The ledger proves what every filing printed but answers
no query without re-assembling grids by hand; `scripts/build_document_tables.py`
now derives `data/bank_audit_tables.db` (local, never the audit snapshot):
`bank_audit_document_sections` (the filing's own declared title + role + page
span, sourced from its folio-validated contents, its body banners, or honestly
NULL — 1,011 / 60 / 24 filings respectively), `bank_audit_document_items`
(57,131 contents entries), and `bank_audit_document_tables` (122,583 rows —
section context, declared unit, and the grid as JSON with labels, aligned
signed cells, "-" kept as text, the table's footnotes bound to their grid
rows, and every column-less cell preserved in `unplaced_json`).
Cell-conservation is exact fleet-wide: 8,392,845 derived cells equal the
ledger's in-block cells to the last one, and 97.6% of tables carry a section
role. The sectioning moved to `src/audit_reports/document_sections.py`, shared
with the HTML viewer (whose output is byte-identical after the refactor).
Nothing reaches D1 — that push is a named open decision, like the prose
corpus.

2026-08-19 — **A statement page filed as a picture can no longer pass as a
short filing, and the capture reconcile stopped diluting itself.** Both open
reconcile errors (FIBA 2023Q3; ISCTR 2025Q1, recorded "undiagnosed, a
different cause") were one bug: statement bodies embedded as raster images
under a typed banner carry zero path ink, so the vector-outline probe scored
them `text` and the capture silently kept ~3 cells per statement page.
`_raster_content` (document_capture.py) now reads geometry — a blockless page
with images ≥10% over the content band and ≤8 typed words inside it stamps
`raster` — every threshold in a measured gap (a cover's title sits INSIDE the
band, TSKB 2026Q2 p1; a divider's logo covers <5%). The silent class is fully
enumerated at 3 filings in 1,095; the third, ISCTR 2025Q2 unconsolidated,
surfaced only under the sharpened rate. Scanned auditor letters honestly
become `partial` now, made safe because the reconcile no longer skips a filing
wholesale over unreadable pages. `check_capture_reconcile.py` also stops
counting the three extractor-computed columns no filing prints
(`fx_position.net_position`, `repricing.cumulative_gap`,
`credit_quality.total_amount`) — fleet median 97.3% → 99.66% — and `MIN_RATE`
rises 0.85 → 0.95 inside the emptied band. Fleet verification: 1,050
partitions, 0 errors, 8 attributed `capture_incomplete` infos — the first
fully-explained fleet. `refresh-audit.yml` now captures each freshly extracted
filing (`--recent-hours 168`) and reconciles it alert-only in the same run, so
the external unit-scale anchor works the day a filing lands; migration `0044`
renames the manifest column to `unreadable_page_count`.

2026-08-16 — **A briefing bullet can no longer cite a release that does not
state its figures.** The repaired 13/13 briefing attributed the policy
corridor to the same-day Türkiye–Syria deposit-agreement release (zero
percentages in its body) — right numbers, wrong instrument, wrong date chip,
since the page keys each bullet's date and link on its cited id.
`src/news/briefing_citations.py`: a citation survives only if its body states
every percentage the bullet asserts as current (transition "down from X"
values excluded; `4%`/`37 percent` forms, calibrated against production D1
bodies). Repair is strip-then-ask, never auto-repoint: bad ids stripped, one
re-citation retry, then the bullet is dropped — the page refuses uncited
bullets anyway. `check_briefing_facts.py` audits the stored briefing against
the same shared feed and any miscited bullet fails the publication gate.
`docs/regulation_followups.md` §F.

2026-08-16 — **The regulation briefing's fact checklist became a publication
gate instead of a Telegram apology.** The morning's weekly run scored 69%
(9/13) — stored, pushed, live — because the checklist ran only after the
store, alert-only. Diagnosis against the live page split the four flagged
facts evenly: two checker bugs (`\bSME\b` cannot match "SMEs"; a bare `FX`
keyword read an RR bullet's "up to 1 month" as a superseded FX-loan cap) and
two real defects (January's overdraft cap printed beside May's; the repo-
auction suspension absent while a bullet called the repo rate "the main
policy instrument"). The in-run contradiction gate had missed the overdraft
pair because it compared raw value sets — the transition bullet {1,2}
intersects the stale-bare bullet {2} — and its regeneration retry was
provably a no-op at temperature 0 with a fixed seed. Now: `find_contradictions`
compares transition-aware CURRENT values; every regeneration carries an
addendum naming the defect; the checklist lives in `src/news/briefing_facts.py`
and gates generation (deterministic strip of superseded-value bullets, one
pointed retry per section naming rule + source but never the value); and the
workflow's `check_briefing_facts.py --fail-under 0.75` blocks the D1 push and
snapshot upload outright — a failing briefing evaporates with the runner and
the page keeps last week's verified text. The 2026-08-16 production bullets
are the regression fixtures. `docs/regulation_followups.md` §E.

2026-08-16 — **The bank Desk stopped crowning the free-float bucket as "owner"
and stopped telling Takasbank it never filed.** A page-by-page review of the
live site found three untrue sentences. (1) The Desk's identity strip picked
the largest KAP shareholder row as "Owner", and for any dispersed-ownership
bank the largest row is the "Diğer" residual — Akbank printed `OWNER DİĞER
59.3%` while Sabancı Holding sat one tab away at 40.8%. The pick now skips
free-float rows (`isFreeFloatHolder`, shared from `kap.ts`), prints the legal
name through `holderShortName`, and a bank with only a residual reads
`free float N%`. (2) The TTM engine gate reported "This bank has filed 0
quarters" for Takasbank — the panel it counts is the peer RANKING, which
excludes TAKAS by design, while the same page's Financials tab holds 17
audited quarters. `engineGate` now receives the bank's own filed-quarter
count plus the exclusion flag and says which of the three cases is true
(never filed / panel doesn't carry it / deliberately excluded), pinned by
tests. (3) Every bank page's analyst section still promised memos "when the
D1 write freeze lifts" — the freeze lifted 2026-08-07; the copy (and the
`/pipeline` transcripts sublabel) now state the actual gate: generation is a
dispatch-run workflow. `web/app/banks/[ticker]/`, `web/app/lib/bank-brief.ts`,
`web/app/lib/kap.ts`, `web/app/lib/bank-brief.test.ts`.

2026-08-12 — **A third of all Q4 filings were being judged "not a report".**
`report_validity` scanned the first **6** pages for a filing's structural
markers, and an ANNUAL report prints the full independent auditor's report
before the numbered Bölüm structure begins. Measured over 60 random Q4 filings
in R2: **19 of 60 (32%)** had their first marker on page 6–9, max 9, while a
non-Q4 sample never exceeded page 4. Nothing reported a wrong number — the cost
was permanent churn, because a stored PDF judged not-a-report sends the scraper
back to the bank's site on *every* run, so ~80 genuine filings were
re-downloaded from R2 and re-fetched from source daily. Where the source was
slow (AKTIF, COLENDI, VAKBN, EXIM) those became the `[FAIL]` timeouts that fired
the systemic alarm and stalled the audit lane for six days. The window is now
**16** pages, ~1.8× the observed tail; widening is bounded against false
positives by `_KAP_COVER_RX` (tested first) and the 40-page floor. Diffed at 6
vs 16 over 80 filings: **10 gained, 0 lost.** `scripts/sync_audit_reports.py`,
`tests/test_report_validity.py`.

2026-08-12 — **`backfill_extraction --latest-period` cleared one quarter and
re-extracted another.** The DELETE resolved "latest" as `MAX(period)` from
`bank_audit_extractions` while `extract_from_r2` resolved it from R2. Those
agree only while every acquired PDF has been extracted, so whenever R2 was ahead
— a live filing season, or any extraction stall — the clear took the older
quarter and the re-extract took the newer, leaving the older with no extraction
log row and nothing to rebuild it. Running `backfill-audit.yml` with
`latest_period=true` during the 08-08 → 08-12 stall would have deleted 2026Q1
for every named bank. Both sides now read R2 through one shared
`latest_period_in_r2()`, and an empty listing refuses rather than collapsing to
a WHERE that matches everything. `scripts/backfill_extraction.py`,
`tests/test_backfill_latest_period.py`.

2026-08-12 — **The audit scrape alarm stopped eating six days of extraction.**
`sync_audit_reports.py`'s systemic-failure guard fired on five consecutive
`refresh-audit.yml` runs (08-08 → 08-12) and each exited before the D1 push and
the snapshot upload, so the same eight 2026Q2 partitions were extracted and
thrown away every morning while 2026Q2 sat frozen at 12 partitions. Two defects:
the scrape ratio omitted `pending` from its denominator — a `not-a-report` is a
*successful* fetch, so with the corpus complete four dead bank URLs were 100% of
a "batch" of four (5/109 = 4.6% correctly, 5/5 = 100% as measured) — and the
alarm exited 1 mid-job, indistinguishable from a crash. It now exits
`EXIT_SYSTEMIC` (8); both workflows persist everything, then re-raise in a final
step so the job still goes red and still alerts, while any other nonzero code
still aborts immediately. 2026Q2 recovered 12 → 23 partitions.
`scripts/sync_audit_reports.py`, `refresh-audit.yml`, `acquire-audit.yml`,
`tests/test_sync_systemic_gate.py` (14 tests, fixtured on the real runs).

2026-08-12 — **The D1 write cost guard is removed.** No push is refused on cost
any more, at any size, in any lane. Gone: `--max-billed-rows` (the 2.5M per-push
ceiling that exited 3), the cycle-aware cap that tightened as the 50M allowance
filled, the `D1_RUN_LEDGER` that made both cumulative across a workflow run, and
`EXIT_BUDGET` with them. `--max-billed-rows` and `--no-cycle-check` are still
accepted and ignored so existing workflow files keep running; `EXIT_BUDGET`'s
exit code 3 is left unused rather than recycled.

Kept deliberately: the per-table billed-row **estimate still prints on every
push**, now marked advisory. Removing the refusal was the ask; removing the
number would only have made the spend invisible. Also unchanged — and now the
only things holding the bill down — the content-hash and partition-digest skips
that stop an unchanged row being generated at all, and `scripts/healthcheck.py`,
which still reads cycle usage but reports after the fact and stops nothing.

`audit_d1.TERMINAL_EXITS` collapses to `(EXIT_VALIDATION,)`, so a transport
failure (exit 4) is unconditionally retryable again: the ledger's book-before-write
had made a retried blip land on a cap it had already spent, turning a transient
into a permanent refusal. `push_to_d1.py`, `audit_d1.py`, five workflow files,
`tests/test_d1_write_budget.py`, `tests/test_write_amplification.py`; deleted
`tests/test_ledger_retry_semantics.py` and `tests/test_workflow_ledger_wiring.py`.

*(This supersedes an unreleased 2026-08-08 change that had raised the
exhausted-cycle floor from 250,000 to 1,000,000, after both BDDK lanes refused
two days running on the `api_series` rebuild's ~237,456 billed rows and shipped
no bulletin, EVDS or news rows either. That constant no longer exists.)*

2026-08-07 — **/admin now answers "who has published this quarter?" directly.**
A filing-season panel above the coverage matrix tracks the in-window quarter per
bank: extracted, acquired-awaiting-extraction, **results out but audit report
pending** (an independent KAP `results_filing` row exists in `bank_earnings`
while no BRSA PDF is in R2 — İş Bankası's exact 2026Q2 shape, which previously
had no surface anywhere), or no signal. Pure read-time derivation over existing
tables — no migration, no scraper, no schedule. Each bank's expected
unconsolidated/consolidated shape comes from its prior-period expected rows, so
banks that have filed nothing still appear; "no signal" is worded as absence of
evidence, never as proof of non-publication. Window model mirrors
`refresh-audit.yml` (Q4: Jan 20–Mar 15; Q1/Q2/Q3: 20th of month+1 → 20th of
month+2). `web/app/lib/filing-season.ts` + tests.

2026-08-07 — **Refreshes now poll on each source's cadence and stop writing the
moment nothing changed.** The BDDK monthly probe runs on the first/last five
days of the month instead of daily; the Saturday 02:00 weekly backstop is gone
(the 03:00 full refresh follows anyway); the daily EVDS lane polls only series
declared daily/workday and passes explicit `--skip-*` flags for every unrelated
loader. `refresh.py` hashes the SQLite file before and after (`--change-file`)
and defers VACUUM/gzip to the workflow (`--defer-packaging`), so a quiet run
performs no Node setup, no D1 push and no R2 upload. Four more Saturday-path
writers — TBB, TKBB, TÜİK and KAP — now compare the stored tuple before writing,
so identical re-fetches no longer refresh `downloaded_at` and the no-change gate
can actually fire (`tests/test_d1_write_economy.py`, `tests/test_refresh_cadence.py`).

Same day — **the audit lane owns its arrival path.** `refresh-audit.yml` is
scheduled daily during the quarterly filing windows (Jan 20–end Feb, Mar 1–15,
Apr/Jul/Oct 20 → May/Aug/Nov 20) and carries a valid new PDF from discovery
through extraction, validation, coverage and **one** `--table-set audit-refresh`
D1 batch to the snapshot; a quiet check stops after discovery and writes
nothing. `acquire-audit.yml` loses its Sunday cron and becomes a manual
acquisition-only diagnostic.

Same day — **a lane's verdict is now the whole relationship, not one row.**
`registry.validation_gate()` encodes the dependency graph — either balance-sheet
side requires `assets`+`liabilities`+`cross`, credit-quality and derived stages
require each other — and coverage, loader overwrite protection, targeted-repair
acceptance and the admin drawer all consume the same gate (migration `0041`).
Targeted re-extraction rebuilds stages inside the candidate's savepoint, judges
the full gate, and rolls source, derived and validation rows back together on
rejection; unchanged tables are restored byte-exact so nothing is re-stamped.
`free_provision` gains a real per-partition validator (range, prior-year chain,
audit-opinion recall/precision cross-checks) — conditional absence stays N/A
only while no independent evidence contradicts it.

Same day — **eight normalized/summary lanes carry source-completeness evidence.**
`source_capture.py` re-locates each disclosure with parser-independent anchors,
stores every physical source line in the local/R2 snapshot
(`bank_audit_source_lines`, never D1), and writes one compact
`bank_audit_capture_manifest` row per filing/lane to D1 (migration `0042`).
Near-full lanes (`equity_change`, `loans_by_sector`, `npl_movement`) fail on an
unmapped numeric source row; selected-summary lanes count their intentionally
omitted detail instead. Capture rides the normal extraction transaction; the
historical corpus stays grandfathered until `backfill-audit-source-capture.yml`
(new, dispatch-only) reaches it. At commit time the migrations are unapplied and
the backfill undispatched — production statuses move only after the deploy and
the normal revalidation workflow.

2026-08-05 — **Admin traffic now queries the site it actually measures.**
Cloudflare Web Analytics exposes a `site_tag` for GraphQL and a separate
`site_token` for the browser beacon. The original wiring put the token in both
places; Cloudflare accepted that query but returned an empty dataset. The Worker
now carries separate `CF_ANALYTICS_SITE_TAG` and `CF_ANALYTICS_SITE_TOKEN` vars,
the admin query returns live page views/visits/paths, and the manual beacon uses
the token (with Cloudflare's current `type="module"` embed shape).

2026-08-05 — **A campaign now costs what it changed, not what it touched.** Each
`(bank_audit_* table, bank·period·kind)` partition carries a digest in
`d1_pushed_partitions`, and an unchanged partition is not pushed at all.

The cap shipped yesterday made a campaign *declared*; this makes it *cheap*. The
windowed audit tables key on the extraction stamp, so re-running the fleet after
an extractor fix re-shipped every partition it touched — including all the ones
the fix did not alter. Measured on the real balance-sheet corpus (1,050
partitions / 182,141 rows): a re-extraction that changes nothing goes from
182,141 rows to **0**, and one that corrects a single cell goes to **181**.

Safety is the whole design, because the mirror image of the saving is rows that
silently never arrive. A partition with no stored digest is always sent (missing
state means "send it"); digests are recorded only after wrangler succeeds; stamp
columns are excluded or nothing would ever match; a partition that *lost* a row
counts as changed; `--force-partitions` resends everything. `bank_audit_extractions`
is exempt outright — it is the log that records that an extraction ran, so
skipping it would freeze the audit trail while the rows it describes had genuinely
been re-extracted.

Also: `healthcheck.py` now alerts at **80%** of the cycle's write allowance
rather than leaving the bill unwatched — July's 18.1M overage was discovered on
the invoice. It stays silent when the reading is unavailable, because an alert
that fires on its own blindness gets muted. Shared reader in `src/d1_usage.py`,
stdlib-only so the minimal-deps job can import it. Live at time of writing:
62,626,854 rows this cycle, 12.6M over, ~$12.63.

2026-08-04 — **Campaign pushes now have to declare what they cost.**
`push_to_d1.py` prices every push before running it, prints the estimate with a
per-table breakdown, and **fails (exit 3) rather than warning** when it exceeds
`--max-billed-rows` (default 2,500,000).

The scraper fixes earlier today made the quiet days cheap and did nothing for the
days that actually blew the allowance. July's overage was three campaign days —
12.4M, 15.1M and 9.4M billed rows — and every one ran to completion without ever
saying what it was about to write. The default cap is sized to clear real work
and stop a runaway: a whole-audit-corpus push estimates 1,678,540 and the pending
prose push 1,110,204, while the smallest of those three days does not fit. Raising
it is fine, and lands the number in the workflow file where a diff shows it.

A second layer reads rows-written for the **current cycle** (the 11th → the 10th,
not the calendar month) from `d1AnalyticsAdaptiveGroups`. Once the 50M allowance
is spent the cap drops to 250,000: routine crons keep running, campaigns wait for
the roll-over. Freezing everything was July's other mistake — four days with
nothing watching the data, for a bill the crons were not causing. An unreadable
API returns `None` and changes nothing in either direction; treating a missing
reading as "plenty of headroom" is the silent-wrong shape this repo keeps meeting.

Measured live while testing: the Jul 11 → Aug 10 cycle stands at **62,621,752
rows written against the 50,000,000 included** — 12.6M over, so the tightened cap
is what is in force today.

2026-08-04 — **The EVDS write bug was never EVDS-specific: found it twice more,
in the weekly bulletin and TEFAS.** `weekly_api_scraper.fetch_and_store` and
`tefas.loader.upsert_day` now compare the stored tuple before writing, the same
fix EVDS got on 2026-07-27. Gate: `tests/test_d1_write_economy.py`.

The pattern is a property of the *source*, not of any one scraper: an upstream
that only serves a trailing window forces a re-fetch of data already held, and
`INSERT OR REPLACE` then re-stamps `downloaded_at` on every row of it. Since
`push_to_d1` windows on exactly that column, the whole window re-ships to D1
carrying identical values. Nothing looks wrong — the run succeeds, the data is
correct, only the bill moves.

- **weekly** — the BDDK weekly API serves a trailing **13-week** window, so
  ~26,600 rows were rewritten per run and only the newest week (~2,080) was ever
  new. At 4 runs/week (Fri ×2, Sat ×2) that is **~1.5M billed writes a month**
  for data that had not moved. `weekly_series` is the largest table in the
  database (711,777 rows), which is why it was the most expensive place to have
  this bug and the least visible.
- **TEFAS** — `update_tefas.py` re-fetches a trailing **7-day** window daily;
  6 of 7 days came back identical. ~**0.2M billed writes a month**.

⚠️ **This does not fix the overage, and it was not meant to.** Both lanes live in
the flat quiet-day baseline (~487k rows/day, ~14.6M/month); together the fixes
take ~1.7M/month off it. The 50M allowance is blown by **campaign days** —
2026-07-15 (12.4M), 07-17 (15.1M) and 07-26 (9.4M) were 36.9M of July's 68.1M
between them. Backfills, re-extractions and override pushes are the cost centre;
scrapers are the rounding error that happens to be free to fix.

The weekly scraper's stats now print `same=` beside `rows=`, so the saving is
readable in the Actions log and a collapse to `same≈0` — upstream restating the
whole window, or the comparison breaking — is visible rather than silent.

2026-08-04 — **Earnings-call transcripts: 144 calls, and a "no free feed exists"
claim that had stopped being true.** `bank_call_transcripts` (migration 0036,
`src/transcripts/`), an "Earnings calls" block on `/banks/[ticker]`, and a reader
at `/banks/[ticker]/calls/[period]`.

PROJECT_STATE had ruled the lane out: *"no free, deterministic feed exists for
Turkish banks … out of scope given the no-paid-vendor / no-LLM-API constraints."*
Every leg of that had failed. AlphaSpread serves the full body and Q&A as
server-rendered HTML for eight of the eleven listed banks, ungated, with
`robots.txt` allowing all agents — and the archive **enumerates itself**: each
bank's index page lists every call as a `q<N>-<YYYY>` slug, so unlike the
presentation lane there is no filename skeleton to learn and no quarter can be
lost to a URL nobody added. The LLM half of the constraint had already been
reversed on 2026-08-03, and no model is involved here anyway.

Ingested 2026-08-04: **734,412 words across 3,831 speaker turns**, AKBNK 33 calls
back to 2018Q1, GARAN 31, HALKB 22, ISCTR 21, VAKBN 20, ALBRK 8, YKBNK 7, TSKB 2.
SKBNK, ICBCT and QNBFB hold no call at all — an absence at the source, so the
block does not render for them rather than showing a permanent empty state.

Two things the lane records about itself rather than letting a reader assume:

- **Attribution is the weak axis, not content.** Against Investing.com's version
  of the same call (AKBNK 2026Q1) the body matches — 4,582 words vs 4,875, both
  ending on "Bye for now" — but the operator naming a Turkish analyst often lands
  as `[indiscernible]`, which also strips that turn's `role='analyst'` tag. 522
  markers corpus-wide, stored per call in `indiscernible_count` and printed in the
  reader. Analyst identity is not something to key on.
- **The figures in a transcript are transcription, not extraction** — spoken
  aloud and written down as heard ("TRY 51.7 billion, 5-1-0.7"). The reader links
  back to the audited numbers instead of inviting the comparison silently.

The ingest is one fat row per call with the turns as JSON, not a per-turn table:
a call is only ever read whole and D1 bills rows written, so this is ~1/25th the
write cost. **The workflow ships with no `schedule:`** — the freeze is enforced by
`gh workflow disable`, which leaves no trace in git, so a new workflow with a cron
would be born enabled and become the one lane writing to D1 during it. Its `push`
input defaults to false for the same reason. Both flip when the freeze lifts.

Also: the source rate-limits. A first run at 1 req/s tripped 429 around page 70
and stayed tripped, costing five banks their *index* fetch and so their whole
archive; the fetcher now backs off (10s → 30s → 90s, honouring `Retry-After`) and
paces at 3s.

2026-07-30 — **A native app, and the rule that keeps it from disagreeing with
the website.** `mobile/` — Expo SDK 57 / React Native 0.86 / expo-router, four
tabs (Overview, Banks, Economy, News) plus a per-bank detail screen. Built and
verified locally; **not submitted to either store.**

The expensive part was never the UI. The website's data layer is server
components reading D1 directly, and the only public JSON surface was `/api/v1` —
the EVDS-shaped series catalog, which deliberately exposes no per-bank data. So
a native client needed a read API that did not exist.

It is `/api/app/v1`, and it is **private on purpose**: `/api/v1` is a documented
contract third parties build against, so its shapes can only be added to, while
this one is the wire format between our own Worker and our own client and can be
reshaped whenever a screen is. Separate kill switch (`APP_API_DISABLED`) for the
same reason — taking down third-party load in an incident must not black out
every installed app at the same moment.

The rule that makes a second client safe: **no metric is derived in the app.**
Every route handler calls the same `web/app/lib` function the website renders
from — `ratioCar`, `heatmapPanel`, `realRate`, `cpiFromIndex`, `overviewInsights`
— so the two surfaces cannot print different values for one metric. The client
formats and writes copy; it never does arithmetic. A new figure goes into
`app/lib` first.

Three things the port surfaced:

- **The categorical chart ramp fails colorblind separation.** Validating the six
  `--chart-*` tokens against their own surfaces: in dark mode `--chart-2` vs
  `--chart-1` scores ΔE 6.1 for *normal* vision (floor 15), and `--chart-6` vs
  `--chart-5` drops to 5.3 under protanopia; in light mode `--chart-3` and
  `--chart-6` sit at ~2.37:1 against the sheet. The website is partly covered by
  its direct-labelled `ChartFoot`, which is the documented relief for a
  borderline pair — but that is relief, not a fix. **Not acted on**: re-stepping
  a CI-gated ramp is a system-wide decision across ~40 charts. The app sidesteps
  it by plotting single series in `--data` only. Logged in PROJECT_STATE.md.
- **Two copies of a colour system drift silently.** React Native cannot read a
  CSS custom property, so `mobile/src/theme/tokens.ts` is a hand-copy of
  `globals.css`. `mobile/scripts/check-tokens.mjs` re-reads the CSS and diffs it
  in CI — mutation-tested by flipping one hex and confirming it fails.
- **`tsc` is not proof a React Native app builds.** It is happy with imports
  Metro cannot resolve. CI runs `npx expo export` for that; it also caught that
  the Google-Fonts package root pulls every weight and italic (~2.5MB of TTFs
  for five faces), fixed with per-weight subpath imports.

2026-07-27 — **Half of every section-4 capital cell was never validated.**
`check_capital` took `next(r for r in rows if r["period_type"] == "current")` and
that was all it ever looked at. `Tier1 = CET1 + AT1` — the identity that refutes
the ISCTR CET1 defect on sight — has existed since the lane shipped; it simply
never ran on the prior column, which is where the defect was. The lesson is not
"add a validator": the validator was there. An identity applied to half a table
is an identity you do not have.

Now run over both columns, failures tagged `[prior]` so a red cell names its
table. The COMPLETENESS fails (cap_rwa_missing / cap_car_missing) stay
current-only on purpose — a bank reprinting a partial prior column is ordinary
and not our defect. Calibrated over the corpus: **21 partitions fail on the prior
column**, all pre-existing (EMLAK x4, ICBCT x1, ISCTR x4, QNBFB x11, SKBNK x1).

**3 corrected, from evidence.** ISCTR 2024Q1 consolidated prior was a column
SLIP the fractional sweep is structurally blind to — every value a whole number,
only the assignment wrong. Its 2024Q1 **English** filing prints the section-4
labels one row off their values ("Total Deductions from Common Equity Tier 1
294,633,433 270,336,203" IS the CET1 row), so the extractor matched labels
literally and put Tier 1's value in AT1. Four fields re-read from the PDF.
ICBCT 2026Q1 and SKBNK 2025Q4 each proven by two independent derivations
agreeing exactly. All six affected rows now close CET1 + AT1 = Tier1 in D1.

**18 remain, with one shared signature** — `additional_tier1_capital` or
`tier2_capital` stored as 0.0 where the value is non-zero, the truth always
being `t1 - cet1` or `tc - t1`. That is one extractor defect in the prior-column
parse, not 18 data errors; 5 of them have no in-corpus anchor at all (their
prior column is a 2021 year-end, before the corpus starts).

**A method note worth keeping.** The first correction set replaced each failing
row's flagged fields with the year-end anchor's values and checked the identity
closed. It closed for 9 of 11 — and the number was meaningless: substituting a
whole row from a self-consistent source and then testing self-consistency proves
only that the source was self-consistent. The honest test derives each field
from the STORED row's own identity and requires the anchor to agree
independently. Under it, 9 collapsed to 2.

Also settled at source: DENIZ 2023Q4's prior `stage1_amount`, left flagged
earlier, is **not** an error — p112 prints 1.248.122 and the bank restated it.
The same page confirms the stage-2 fix, printing `-535.779` with a hyphen while
the current column uses `(2.386.482)` parens: exactly why the parse bug bit one
column and not the other.

2026-07-27 — **The two mis-read amounts, corrected — and the repair tool
could not name the cell.** Both figures the amount-integrity sweep found sit in
a *prior* column, and `apply_overrides`' capital handler hardcoded
`period_type='current'`. Authored naively, the ISCTR override would have
silently patched the CORRECT current row and left the wrong one exactly where it
was — a repair that makes the corpus worse and reports success. The handler takes
an optional `period_type` now (default `current`, so the 54 existing capital
overrides behave identically) and returns NO MATCH when the UPDATE touches zero
rows. Four tests pin the default, the prior path, the no-match signal and the
credit-quality equivalent.

`bank_audit_capital.cet1_capital` ISCTR 2024Q2 consolidated prior:
270336.203 -> 270,336,203. A section-4 prior column re-prints the prior
year-end, so the cell is 31-Dec-2023 — and beyond the three filings that agree,
the row carries its own proof: CET1 + AT1 = Tier1 closes exactly at
270,336,203 + 5,348,088 = 275,684,291 and misses by 1000x with the old value.
An identity the row already holds beats any number of agreeing neighbours.

`bank_audit_credit_quality.stage2_amount` DENIZ 2023Q4 consolidated prior:
-535.779 -> -535,779. DENIZ's unconsolidated 2023Q4 prior is byte-identical to
its 2022Q4 unconsolidated current, establishing that the bank restates nothing
here. Left alone deliberately: that row's stage1_amount still differs from
2022Q4 current by 4,003 — no 1000x signature and no evidence which filing is the
mis-read, so it stays flagged rather than guessed.

Verified in live D1; `check_amount_integrity` is now clean on the separator
class. Found on the way and still open: **ISCTR 2024Q1 consolidated prior is a
column SLIP** — Tier1's value in `additional_tier1_capital`, Total capital's in
`tier2_capital`, `cet1`/`tier1` NULL. Every value is a whole number, so the
sweep is structurally blind to it: nothing about the numbers' shape is wrong,
only their assignment.

2026-07-27 — **A number's sign changed how its format was read.**
`extractor.parse_num` — the numeric primitive eight audit extractors share, and
the one with no tests — decided Turkish-vs-English thousands notation with an
anchored regex applied to the *signed* string. A leading `-` failed the anchor, so
a hyphen-negative with exactly one thousands group fell through to the English
branch and its separator was read as a decimal point: `-319.110` came back as
`-319.11`, a silent 1000x error. Two groups survived on a separate clause and
parenthesised negatives never reached the sniff, which is why it only ever bit the
section-4 market-risk net-off and gap rows. Sign is now stripped first;
`tests/test_parse_num.py` asserts every case against its positive twin.

The invariant it earned: **BRSA prints whole thousands of TL, so a fractional
amount is a number we mis-read.** `scripts/check_amount_integrity.py` sweeps all
67 amount columns (ratio columns excluded by name, list derived from
`registry.py`) and runs daily in `healthcheck.yml`. No internal identity can see
this class — they compare figures to each other, so a uniform scaling error
cancels on both sides (that is how TEB's 2026Q2 unit switch validated green).
This asks instead whether a stored number has a shape the source could not have
printed, which needs no anchor and no peer.

First sweep: **67 fractional values — 2 wrong numbers, 65 leaked non-values.**
`bank_audit_capital.cet1_capital` ISCTR 2024Q2 consolidated reads `270336.203`
where ISCTR's own 2024Q3 *and* 2024Q4 filings print `270336203`;
`bank_audit_credit_quality.stage2_amount` DENIZ 2023Q4 prior reads `-535.779`
where DENIZ 2022Q4 current carries `-535779`. Both flagged, neither corrected —
the call is whether to override or re-extract. The other 65 are hierarchy markers
and sector numbering parked in amount columns (equity_change 44, loans_by_sector
18), reported but not alerted: they belong to the known column-alignment tails.

Same pass: the `push_to_d1` routing guard widened from the 27 audit tables to all
54 `SYNC_TABLES` (schema built from `web/migrations/*.sql`, so the baseline
tables are covered too); ruff widened from five rules to full pyflakes, 18
findings cleared; `_parse_amount` de-duplicated into `extractor.parse_amount`;
and 74 over-broad exports in `web/app/lib` reduced to module-private or deleted —
37 confirmed unused by tsc + ESLint, orphaning 7 more helpers, net -538 lines
(`metrics.ts` 1,263 -> 974). Four stale claims in METRICS.md that named deleted
helpers were corrected. Full record:
[knowledge/architecture-cleanup-2026-07-27.md](knowledge/architecture-cleanup-2026-07-27.md).

2026-07-25 — **A feature that could not be found on a phone.** The chart
export/copy controls were `opacity-0` revealed on `group-hover`. There is no hover
on a touch device, so on every phone and tablet they were permanently invisible —
shipped, working, and undiscoverable. The reveal now applies under
`@media (hover: hover)` only; touch gets them visible, desktop is unchanged.

The same finding's other half: `overflow-x-auto` is invisible on touch. The
`/cross-bank` scorecard is **820px wide inside a 390px viewport** — two thirds
off-screen with nothing to suggest it. New `ScrollX` (`components/ui/scroll-x.tsx`)
adds an edge fade **per side, removed on arrival**, so "there is a fade" always
means "there is more that way"; a permanent gradient is a texture the eye learns
to ignore. It also makes the region keyboard-operable (`tabIndex` + `role="region"`
+ a required label — WCAG 2.1.1: a scrollable region has to be reachable without a
mouse), and re-measures on resize as well as scroll, because the same table is
scrollable on a phone and not on a desktop.

Applied to the four widest surfaces a reader actually meets: the Compare
scorecard, the market-share league, the bank register (940px) and the sources
table on `/methodology`. The other `overflow-x-auto` containers are narrower and
left for a follow-up sweep.

2026-07-25 — **/about and /methodology — the rest of the trust layer.** With
`/privacy`, that closes the 2026-07-12 evaluation's finding 4: a financial-data
product with no public statement of what it is, who makes it, or how a figure is
computed.

`/methodology` is the one that earns its place. Sources and cadences; coverage and
why Takasbank is carried but excluded from every peer statistic; **the basis
problem** — that sector CAR, loan-to-deposit and the rest legitimately exist in
several definitions, and the site names which one it used rather than picking a
winner; the computation rules the code actually enforces (exact Fisher, not
g−π; YTD de-cumulated before it is read as a quarter; TTM ROE over average equity;
Σ/Σ over the same reporting population; growth paired by date so a source gap
renders as a gap); what runs before anything publishes; and a plain list of what
the site is not.

Both pages **read their counts from the data**. `check_prose_claims.py` R3 fails a
hardcoded universe count in rendered text — the universe has been 31, 37 and 38
inside a year — so the coverage sentences restate themselves rather than rotting.
One `prose-ok` suppression was added, for a static section heading that R2 reads as
an assertion: there is no series on the page to compute it against, and the
suppression prints on every run rather than hiding.

Also measured while looking for a performance win, and worth writing down because
it is a dead end: **the 101KB Recharts chunk loads on pages with no charts**,
`/privacy` among them. Fixing that helps only the light pages; the heavy ones
(`/banks/…`, `/cross-bank`, `/economy`) genuinely need the library, so the real
LCP lever is deferring or replacing Recharts *there* — a decision about how charts
appear, not a bundling tweak. Left open deliberately.

2026-07-25 — **The heaviest page on the site was the only one not using the
cache.** `db.ts` states the rule in its own docstring: *"Dashboard pages should
keep using `cachedAll`: their query set is small, fixed, and repeated on every
page view."* `audit.ts` — which powers `/banks/[ticker]` — called `getDB()`
directly in **12 of its 15** query functions. A single bank-page view therefore
re-queried D1 for the balance sheet, the P&L, both multi-period pivots, the cash
flow, the line names, the profile, the stages and the extraction log, per
visitor, while every other page on the site read from KV.

All fifteen now go through `cachedAll`. The key space is what makes this correct
rather than merely faster: ticker (38) × kind (2) × the periods a reader actually
opens — bounded, which is precisely the distinction `allDirect` exists to draw
for the public API's unbounded one.

Measured before the change: TTFB 0.65–0.95s across `/`, `/banks/AKBNK`,
`/cross-bank` and `/economy`.

Two things the measurement corrected, both worth recording because they were
assumptions inherited from the 2026-07-12 evaluation rather than facts:

- **The 40KB polyfills chunk is not waste.** It ships with `noModule`, so every
  modern browser skips it. The report implied otherwise; the HTML says no.
- **JS, not server time, is what costs 2.6s on a bank page.** 338KB compressed
  across 19 chunks, of which a single **101KB chunk is Recharts**. Caching D1
  improves TTFB, and TTFB was never the 4.1s LCP. The chart-library weight is the
  real lever and is untouched here — deferring or replacing Recharts is a
  separate piece of work, not a token change.

2026-07-25 — **The quietest text on the site was 2.43:1.** WCAG AA asks 4.5:1
for normal text. `--faint` sat at **2.43:1** on the white sheet — and it carries
8–10px type across **210 call sites**: captions, record lines, chart axis ticks,
every colophon. The 2026-07-12 evaluation scored accessibility 6.5/10 and named
this as the cause. It is the oldest known defect on the site and the easiest to
keep not-fixing, because a contrast ratio is arithmetic nobody re-runs after
nudging a hex by eye.

So the fix is a **gate first**: `scripts/check_contrast.py` computes every
`text-*` token against every surface it can sit on — the sheet, the ground, and
the muted row fill, which is the darkest surface and the pairing that fails first
— in both themes. It also has an inventory half, like `check_docs_sync`: a colour
used as text with no declared background fails, so nobody can introduce one
without deciding where it sits. **66 pairs, 4.5:1 floor, stdlib only.**

Running it found more than the evaluation did:

  --faint         2.43:1 -> 5.13  (light)   2.43 was the headline number
  --faint         3.64:1 -> 4.96  (dark)    also short, on a darker sheet
  --warning       3.27:1 -> 5.18  (light)   26 text uses
  --negative      4.33:1 -> 4.55  (on muted rows)
  --context       1.69:1            used as TEXT in 6 places on /cross-bank
  --chart-4       3.27:1            used as chip TEXT on /regulation
  --chart-2       4.42:1            used as tag TEXT in news-tags.ts
  chart axis tick 2.43:1            chart-theme.ts's copy of --faint

Two consequences worth stating, because both were design decisions rather than
arithmetic. **Raising `faint` squeezed it against `muted-foreground` (5.02:1) —
two tiers with no gap** — so the secondary tier moved darker as well, and the
ordering `ink > secondary > quiet` with a real gap between the last two is now
asserted in a test. The Desk is built on three quiet tiers; making one legible
must not collapse two. And **a chart series colour is no longer allowed to be a
label colour**: rather than distort a tuned 6-colour palette, the amber chip
keeps its coloured border and takes ink for the word. Marks answer to a different
rule (3:1, WCAG 1.4.11) and were left alone.

`chart-theme.ts` can't read CSS variables, so its `axis` (tick labels) and
`inkMuted` are copies of text tokens — the gate now requires them to be EQUAL,
not merely similar, which is the lockstep rule DESIGN.md always stated but
nothing enforced.

One bug found on the way, by the repo's own guard: the patch script that wrote
the gate put a literal `0x08` where a regex `` was meant, and the check
silently matched nothing. `tests/test_docs_sync.py::test_no_control_chars_in_source`
exists because this exact thing once made a briefing fact read PASS.

2026-07-25 — **Analytics ran for two days with no notice and no choice.** GA4
shipped on the 23rd. The site had no privacy page, no consent bar, and no way to
say no — on a product whose entire pitch is that its claims are checkable. Both
halves fixed together, because either alone is half a fix: a notice nobody can act
on, or a switch nobody can find.

`/privacy` states what is collected against what the code does, and every claim in
it names the file that implements it — the repository is public, so a reader can
check the page the same way they can check a bank figure. It is linked from the
Colophon on **every** page, outside the `children ??` fallback so a page that
passes its own colophon text still carries it.

GA4 is now opt-IN: `gtag.js` is not requested until the visitor accepts, so
declining means Google never sees the request — nothing set and deleted
afterwards. **Decline, or ignore the bar, and the site sets no cookies at all.**
Cloudflare Web Analytics stays ungated and is named as such: it is cookieless and
keeps no per-visitor identifier, so it cannot single anyone out. Accept and decline
are the same size and weight; a decline that is harder to find than accept is not a
choice.

Three implementation notes worth keeping. The preference is an **external store**,
not derived state — `useSyncExternalStore` (`lib/use-consent.ts`) reads it during
render, which both satisfies `react-hooks/set-state-in-effect` and keeps the banner
out of the server HTML; a consent bar that flashes during hydration is one that gets
dismissed by accident. Every failure path reads as **refusal**: no stored value,
an unrecognised value, storage disabled, SSR — all return null, and null means off
(8 unit tests pin exactly that, including that `"true"` and `"yes"` are not
consent). And the notice documents the **Telegram bot honestly**, which retains
more than the website does: question text plus a non-reversible chat hash, the raw
chat id in the rate-limit counter, and the question going to a third-party model
provider.

Contact is a real address, not a form: incesalim10@gmail.com.

2026-07-25 — **The landing page computed "real" the one way its own library
forbids.** `series.ts` exports `deflate()` and says so in the docstring: exact
Fisher, not the g−π shortcut. `/credit`, `/deposits` and `/asset-quality` obey it.
`/` subtracted — on the two figures it leads with. At a ~32% CPI that is not a
rounding difference: **ROE real printed −7.3pp where the true figure is −5.5%,
and credit real +5.4pp against +4.1%**. It also made the landing page's "credit in
real terms" disagree with `/credit`'s own line for the same quantity.

`real-terms.realRate()` is now the scalar twin of `deflate()`, unit-tested against
the series form so the two cannot drift apart. Three sites on `/` use it: ROE real,
credit real, and the "≈ flat in real terms" band on assets.

Both CPI bases were kept and each surface now prints which it used — a y/y growth
rate is deflated by spot y/y CPI, a return earned across the year by the 12m
average. The defect was the subtraction, not the base choice.

The unit had to follow the arithmetic: `g − π` yields percentage POINTS, Fisher
yields a real RATE. So `signedPct` joins `signedPp` in `prose.ts`, the transmission
item's unit goes pp → %, and the flag's printed rule becomes
`(1+roe)/(1+cpi_12m_avg) − 1 < 0`. A page that prints its own rule cannot quietly
change the maths underneath it.

That closes every Tier-1 and Tier-2 finding of the 2026-07-13 sector-page audit.
Its hygiene tier — one shared `fmtPct`/`fmtTrn`, `CAR_MIN` from one place,
date-pairing everywhere — is still open.

2026-07-25 — **Two pages arguing with themselves on one screen.** The last of the
sector-page audit's on-screen contradictions.

`/capital`: the capital-composition chart titled itself off `hybrids > buffer` —
the **bulletin** buffer — while the flag directly above it tested the identical
claim against `auditBuffer`, and the chart's own data is audited. Live today:
audited CAR (peers) 16.07 → 4.07pp buffer, against hybrids of 4.26pp (AT1 1.73 +
Tier-2 2.53), so the flag fires "Hybrid-funded buffer" — but measured against the
bulletin's 16.34 the buffer is 4.34pp, so the chart underneath printed the neutral
"Capital composition". One word, and the page stops contradicting itself. The
comment three lines above the flag had already written down why the audited basis
is the right one; the chart title simply never got the memo.

`/asset-quality`: the "Cover on the problem book" vital printed provisions ÷ the
problem book — a ratio in the 70s — over a sparkline of the **Stage-2 share of
gross loans**, around 10%. Different quantity, different axis, so the trend a
reader took from the mark was not the trend of the number above it. New
`credit-risk.problemCoverageSeries()` (pure, unit-tested) supplies the real
series. It gates on `total` even though the ratio never divides by it, purely so
its filter matches `stageLadder`'s — diverging filters would put a different
quarter at the end of the sparkline than in the headline, which is the same bug
wearing a smaller hat.

Remaining from that audit: `/` still uses the `g − π` shortcut where `series.ts`
mandates Fisher `deflate()`, plus the hygiene tier.

2026-07-24 — **"Loan / deposit" was three different numbers wearing one label.**
`/deposits` printed BDDK's published TL+FC monthly ratio — ~91%, no flag.
`/liquidity`, one click away and linked from that page's own Takeaway, printed a
computed TL-only weekly ratio for private banks — ~97%, flagged. Both correct;
neither label said which quantity it was, so they read as one metric disagreeing
with itself. `/` and the PDF deck were printing the bare label too, which the
2026-07-13 sector-page audit (local archive, not versioned) had not caught. Nine
printed surfaces in the end, not the three it found — `/` alone had four (vital,
movers row, by-group table, flag), and the first sweep missed two of them until
the deployed HTML was read back.

`web/app/lib/ldr.ts` now owns the family: three bases, each carrying its label,
its source-and-cadence note, its threshold, and a pointer to where the reader
meets the sibling figure. Every surface imports rather than retypes, so a label
cannot drift back to a bare "Loan / deposit". The differing thresholds were kept
and made legible instead of unified — the TL book is where funding pressure shows
first, so it is judged at 95 while the TL+FC blend is judged at 100, and each flag
now prints which basis its rule tests. `ldr.test.ts` fails a label with no
currency scope, a basis with no cadence, or a cross-reference pointing at its own
page. The rule is now in DESIGN.md beside the CAR case it generalizes.

One thing deliberately NOT written: the note first read "the TL-only book runs
hotter", which is true today and computed nowhere. Replaced with the structural
fact — that it is tested against a tighter line — which the unit test guarantees.

2026-07-24 — **A clearing house was inside the sector's market-risk numbers.**
`PEER_EXCLUDED_TICKERS = {TAKAS}` has existed since Takasbank was onboarded, and
`heatmap.ts` / `market-share.ts` enforce it. Three other aggregators never
imported it, so the CCP sat inside the audited sector ratios: `audit-ratios.ts`
(`/capital`, `/liquidity`), `credit-risk.ts` (`/asset-quality`) — both named by
the 2026-07-13 sector-page audit (local archive, not versioned)
— and `market-risk.ts`, which that audit missed and which held by far the
largest error. At 2026Q1 the published **cumulative ≤1y repricing gap read 1.71%
of rate-sensitive assets against a true 1.09%** — 57% overstated — and ΔNII at
+500bp read −₺101.5bn against −₺114.2bn. ~94% of Takasbank's balance sheet is
cash and placements that reprice inside a year against no matching liability:
the same structural fact that makes it not a bank. Smaller elsewhere but the
same category error — NSFR 123.27% → 123.52%, CAR 16.10% → 16.07%, CET1 11.86% →
11.82%, `/asset-quality`'s reporting-bank count 38 → 37.

Two helpers now sit beside the list in `bank_names.ts` — `peersOnly(rows)` where
TypeScript aggregates, `peerExclusionSql()` where D1 does (bound params, never an
interpolated ticker) — so the next aggregator has something to reach for instead
of re-deriving the filter. The filter goes at the point rows become one published
number, deliberately NOT in the row-fetchers: the same rows feed `/banks/TAKAS`,
where the CCP's own ladder is exactly what the reader asked for, and that page is
unchanged. Stage-2/3 shares didn't move — the per-column `CASE` guards already
dropped a filer with no Stage-2 book, so the CCP was only inflating `n` and the
ECL stock. Pinned by `bank_names.test.ts` (7 new cases) and an `aggregateCapital`
case that fails if a peer-excluded row reaches the sector ratio.

2026-07-24 — **Every page threw a ReferenceError before paint.** The theme
initializer was bundled with a helper it could not take with it. Wrangler
bundles the OpenNext worker with esbuild `keepNames: true` by default, which
rewrites `function f(){}` to `function f(){} __name(f,"f")` so `fn.name`
survives minification. That is harmless for code that RUNS in the worker — but
next-themes ships its no-flash initializer by **stringifying** a function into
an inline `<script>` (`(${script.toString()})(…)`), and the injected
`__name(k2,"k2")` travelled into the string, into a scope where no such helper
exists. The script threw at that line — which sits *above* the `if (d2) k2(d2)`
that reads localStorage and applies the stored theme — so the pre-hydration pass
never ran and the theme only landed once React hydrated. Every route flashed the
wrong theme. Fixed with `"keep_names": false` in `web/wrangler.jsonc`: this
bundle is not minified, so keepNames was preserving nothing.

The instructive part is why it survived three weeks after being written up. It
builds clean, type-checks clean, deploys clean, and the site *looks* fine once
hydrated — the only place the defect exists is the served HTML of a live
request. Same class as the Turbopack chunk-name regression that returns 500 on
every page while CI reports success. The standing check is now in PROJECT_STATE:
after any wrangler or OpenNext bump, `curl -s https://carthago.app/ | grep -c
__name` must be 0.

Also cleared today: the Dependabot PRs open since 2026-07-01. #89 (boto3) merged
as-is. The web-deps group had spent three weeks failing `npm ci` with
`Missing: esbuild@0.28.1 from lock file` — which reads as a stale lockfile a
rebase would fix, and is not. **CI pinned Node 22 (npm 10) while every lockfile
that reaches it is written by npm 11**: esbuild 0.28's platform packages carry a
`libc` field and nest under `node_modules/wrangler/node_modules/`, and npm 10
reports that tree as missing. Dependabot uses npm 11, so the group was
unmergeable by construction — #90 and #92 died the same death three weeks apart,
and so did the first hand-made attempt here (reproduced locally: `npm@10.9.4 ci
--dry-run` fails on the identical lockfile that npm 11 accepts). `ci.yml` and
`deploy-cloudflare.yml` now use Node 24; the other 18 workflows stay on 22,
where node only runs `npx wrangler`. The bumps were then taken directly on
master with a real install — next 16.2.11, react 19.2.8, recharts
3.10.0, @xyflow/react, lucide-react, @opennextjs/cloudflare 1.20.2, eslint
9.39.5 + eslint-config-next, vitest 4.1.10, wrangler 4.114.0; lint, tsc and 379
tests green. **typescript ^6 → ^7 was dropped**, and majors are now ignored for
it in `dependabot.yml` alongside eslint: typescript-eslint 8.x declares
`peer typescript >=4.8.4 <6.1.0`, and eslint-config-next pulls typescript-eslint
transitively, so every `npm ci` would resolve through an overridden peer. Same
trap as eslint 10, one layer down.

Dependabot then reopened the remainder against the new master — all of them still
branched off the old Node 22 pin, so all of them still failed. Taken directly too:
actions/setup-node v7 (merged as #94), actions/setup-python v7 across 21
workflows, selenium 4.46.0 / pandas 3.0.5 / numpy 2.5.1 / boto3 1.43.55, and
tailwind 4.3.3 (lockfile only). **Open PRs and remote branches: zero.**

Two stale PROJECT_STATE entries retired: the market-risk D1 reconciliation
(re-verified against remote D1 — fx_position 8,208 rows / 590 partitions,
repricing 12,064 / 455, AKBNK 2026Q1 present; the 2026-07-18/19 lane passes had
already closed it) and the `PlSankeyChart.tsx` light-mode regression, whose
component the Desk redesign deleted.

2026-07-23 — **The bot prompt typed the universe size.** Fixing the graph gate
(below) let the Python job reach the prose gate for the first time in days, and
it found seven hardcoded "38 banks" in `bot-schema.ts` — the schema reference
handed to the Telegram bot's LLM. The universe has been 31, 37 and 38, so a
typed denominator becomes a wrong denominator in an answer. The five live
coverage claims now interpolate `BANK_COUNT`; the two that were frozen
anecdotes about a past defect ("returned 36 of 38 banks") were rewritten to
drop a count they never needed — the point was the silence, not the arithmetic.

2026-07-23 — **CI red since 2026-07-19: the graph gate had no room for a scratch
lane.** `check_pipeline_graph_sync` asserts every `.github/workflows/*.yml` is a
node on the `/pipeline` lineage graph, so landing the manual OpenRouter bench
(`test-openrouter.yml`) failed the Python job on every commit afterwards —
unrelated to whatever was being pushed. Drawing the node was the wrong fix: the
bench is read-only on production and feeds nothing, so a node would make the
public graph claim lineage that doesn't exist. The gate now takes a named
`SCRATCH_WORKFLOWS` exemption with a written reason, and checks the exemption
too — naming a workflow that no longer exists fails CI, so the list is deleted
along with the lane. Both "delete this scratch lane" checklists (OPERATIONS,
PROJECT_STATE) now name the exemption.

2026-07-23 — **Product-shelf benchmark is now a page: `/products`.** The pipeline
measured what banks earn; nothing measured what they sell. The frozen 32-bank ×
100-attribute research snapshot (`data/product_benchmark/`) is now a lane:
`src/products/` (schema + deterministic builder), migration `0034`, three D1
tables (`product_attributes` / `bank_products` / `bank_product_profile`), and an
English `/products` page — a two-layer Desk view with an interactive
cell→evidence / bank→profile matrix. Column labels and per-bank prose are
hand-authored English (`src/products/labels_en.py`, `profiles_en.json`); the
four states are encoded by both shape and colour. Seeded by `build-products.yml`
(idempotent; snapshots accrete like `bank_advertised_rates`). Refresh automation
is **designed but not built** — two variants (free-model lane / scheduled agent
routine) over a shared change-detector + evidence-QC + flip-diff spine, written
up in [knowledge/turkish-bank-product-benchmark-2026-07-22.md](knowledge/turkish-bank-product-benchmark-2026-07-22.md) §5.

2026-07-19 — **Repricing: the prior column was structurally invisible.**
check_repricing read the current period only, so a wrong comparative cell could
not be caught by construction — and the cross-period anchor didn't cover it
either, since that compares totals and the totals were right. A sweep of prior-
block footing found 9 partitions that had never shown as anything but green.

The footing block now runs over the prior column too, with an escape for filer
typos. It flags exactly those 9, no false positives.

8 were our own misreads, each corrected from a value printed elsewhere on the
same page rather than inferred from the footing identity (which would have made
the check vacuously pass). TAKAS x6 lose a digit two different ways: in 2023 fitz
drops the final glyph of a printed 2,373,311, while in 2024 the PDF content
stream itself holds only "895,18" — the filer's Word-to-PDF export clipped the
trailing zero where a bold total overflowed its cell, so the page is visually
defective and fitz is faithful. ISCTR 2025Q2 lost a sign, not a digit: the text
layer emits "(452,169,857" with the closing parenthesis clipped, and a paren-
negative needs a balanced pair. ICBCT 2024Q4 consolidated is the instructive one
— its liabilities row was verbatim the long-position row, because that page
prints every value line ABOVE its label and the extractor bound the line below.
It footed internally, so no footing check would ever have found it; only reading
the page did.

The remaining 2 are genuine filer typos, stored faithfully and skipped with
citations: TSKB 2022Q1 (its own Q2-Q4 filings reprint the same ladder with the
corrected figure) and ANADOLU 2026Q1 consolidated (its four component rows give
the true bucket). Detail in docs/knowledge/audit-repricing-lane-2026-07-18.md.

2026-07-18 — **Interest-rate repricing lane → 0/0.** 5 err + 26 miss, plus
66 green-but-incomplete the strengthened validator surfaced, all resolved.

The validator only checked internal footing (Σ buckets = total; total RSA = RSL),
both of which skip an absent field — so 70 partitions read green while the extractor
had dropped a whole column (the liabilities row, or the position/gap row), most of
them the non-standard-bucket banks ZIRAAT/KLNMA. Added a completeness check
(rp_liab_missing / rp_gap_missing) on the total row; calibrated to flag exactly 66,
zero false positives. Cross-period is already clean here (0/584 — unlike fx, the
prior column is faithful).

The b1..b8 fallback that dropped those columns was a symptom: footnote markers like
(1)/(5) matched the number-token regex and inflated the column count. Six extractor
fixes cleared ~76 partitions — drop the markers; add Turkish "Net pozisyon" (TAKAS
×14 were missing entirely); gate the prior-period flip until the current total is
read (ISCTR/ENPARA were losing their current table to an FX table's header); borrow
a split label row's values from the next line; tolerate "Total Liabalities"; un-glue
a fused Faizsiz|Total column.

The rest was hand-read: FIBA ×6 (vector-only tables, transcribed from renders, both
periods), and 9 source-read residuals — a source-clipped ISCTR cell, a QNBFB gap
printed without its parentheses, EXIM/ZIRAATD dropped gap rows, two TAKAS mis-parses
(one locked to a shared FX table, one a stray "f" glyph), and COLENDI ×3 whose
ladder IS disclosed but whose wrapped "Non-Interest Bearing" header defeats the
locator. ICBCT's ₺7k gap-rounding is a source artifact → skipped, faithfully stored.

A second pass then hardened all five brittleness classes those hand-fixes had
exposed, so 7 of the 15 overrides could be retired — those partitions now come
from source (and TAKAS/EXIM/ZIRAATD return both periods, where the override held
only one). The method is x-coordinate column reconstruction: keep each token's
right edge (bucket columns are right-aligned), rebuild a header split across word
lines, read column anchors per page off one fully-populated row, then map values
to columns by position — scanning the lines above as well as below a label, and
tolerating one empty cell. What makes a positional guess safe is the acceptance
test: the reconstruction is used only if the values FOOT. 0 regression across 10
controls. The 8 overrides that remain are source defects no extractor can fix —
FIBA's vector-drawn tables, a clipped digit in ISCTR's PDF, and a QNBFB gap the
source prints without its parentheses. Detail in
docs/knowledge/audit-repricing-lane-2026-07-18.md.

2026-07-18 — **Wrong-PDF guard at acquisition time.** After the fx anchor
caught two partitions whose R2 object was the wrong report entirely, added a
consolidation-basis check so the class can't recur silently.

sync_audit_reports now reads each fetched PDF's own front matter and refuses to
store it under a key whose kind it contradicts — a "…Unconsolidated…" URL that
actually serves the consolidated report is blocked, not saved. The classifier keys
on the DECLARATIVE title phrase ("Konsolide [Olmayan] Finansal …" / "[Un]consolidated
Financial …"), not raw "konsolide" mention counts. Getting that right needed two
normalisations the first cut missed — and the --verify-basis sweep caught it on the
live archive by false-flagging 14 correct unconsolidated reports: Turkish uppercase
İ (U+0130) lower()s to i + a combining dot, so ALL-CAPS "KONSOLİDE OLMAYAN" scored
zero against "konsolide" (PASHA/TAKAS ×9); and an unconsolidated report that names
its consolidated group in the notes out-counted its own title (ODEA/TFKB). A
second sweep pass then caught a subtler one: a bank WITH subsidiaries (TSKB)
references its separately-published consolidated statements enough that a 10-page
window flips its unconsolidated report to "consolidated" (pg1-3 unco=2/conso=0 but
pg1-10 unco=6/conso=7). Fix: read only the first 3 pages (cover + auditor's-report
header, before the notes), where the two bases separate perfectly. --verify-basis
sweeps the existing archive (the scrape guard only sees new fetches; keys already in
R2 are skipped); after the fixes it finds zero wrong-basis PDFs beyond the two
already re-acquired. Pure-text unit tests (incl. both regressions); basis read with
fitz, no pdfplumber.

2026-07-18 — **FX net position: the false-NEGATIVE sweep — 79 wrong greens → 0.**
The first pass (below) cleared every RED cell. This one attacked the greens, and
they were hiding as much as the reds were.

The lane's checks were all internal — Σ currencies = TOTAL, assets−liab = net
balance, net balance + net off = net position — and every one skips an absent
field. So a filing that dropped its Net Off-Balance row still footed on the
columns that survived and read a flawless green, while net_position (the figure
/market-risk actually shows) quietly became net_on only. The net+off=position
check was the worst offender: it "verified" a number the extractor itself
computed. Nothing internal can see a dropped row.

The anchor that can: a quarterly filing's prior column re-prints the prior
YEAR-END unchanged, so it must equal that year-end's independently-extracted
current column. Across the corpus, 88 pairs disagreed. A new `fx_cross_period`
check codifies the comparison; two symmetric completeness checks catch a field
dropped from either column. Together they flagged 79 greens.

53 were systematic extractor drops, recovered from source: a prior net-off row
whose label varied between the two columns (an en-dash, or a different Turkish
phrase — BURGAN even switched English→Turkish mid-series and dropped the row from
both columns), a value block printed offset from its labels so each figure glued
to the wrong row (re-paired positionally, accepted only when it satisfies the
table's own identities and the label parse doesn't), and a couple of gap-fills.

4 were genuine value errors the source contradicts itself on — a derivative leg
added instead of subtracted, a sign flipped, a dropped liability, a lost negative
— each corrected from the table's own sub-rows and confirmed by the neighbouring
filing, then overridden. 8 were real restatements or defective/blank prior
columns the filers themselves printed → curated cross-period skips (footing stays
live). And 2 were whole misfiled PDFs the anchor exposed for free: GARAN's 2023Q4
"unconsolidated" slot held the consolidated report, KUVEYT's 2026Q1
"consolidated" held the unconsolidated one — the entire partition was another
basis's numbers. Both re-acquired the same day: the registry URLs were wrong
(GARAN's English "Unconsolidated" URL is poisoned at source — the correct file is
the Turkish "Konsolide Olmayan" original; KUVEYT had the unconsolidated file
listed under both keys, the real consolidated is a different id), corrected in
audit_report_urls.json, re-fetched to R2, and both partitions re-extracted across
all 17 lanes. They now reconcile through the anchor with no skip — proof it works:
GARAN 2024Q1-Q4's prior column and the corrected 2023Q4 current agree to the lira.

Cross-period divergence fell 88 → 14 pairs, all 14 documented. The lesson worth
keeping: an internal identity that skips NULLs verifies nothing about what's
missing, and never repair a cell from the value the check compares it against —
that just makes the check pass by construction. Detail in
docs/knowledge/audit-fx-cross-period-false-negatives-2026-07-18.md.

2026-07-18 — **FX net open position: 21 errors + 66 missing → 0/0.**
Two extractor fixes recovered most of it; the rest was hand-read from source.

52 of the 66 missing were a two-line header fix. The currency-column parser
under-counted columns for two big banks: TSKB files "US Dollar" in English, which
tokenizes to `US` + `Dollar` and matched neither USD pattern; YKBNK's
unconsolidated "Other FC" header wraps so only `FC` reaches the header line. With
a currency column dropped, every row failed the column-count check and nothing
was stored. Adding `US`→USD and `FC`→OTHER recovered all 51 (plus BURGAN),
verified against Turkish and consolidated controls with zero regression.

13 of the errors were a period mis-tag: HAYATK and ISCTR print a currency
*sensitivity* sub-table above the position table whose header names both periods,
and the prior-period detector fired on that caption, tagging the entire current
table as prior — so the validator found no current rows and skipped everything.
Guarding the flip to ignore a line that also names the current period fixed it.

The 8 footing errors split cleanly: 4 were real extraction bugs (a `parse_num`
miss where a hyphen-prefixed thousands group like "-319.110" reads as -319.11, and
dropped closing parens that flipped QNBFB's signs positive) → overrides; 4 were
genuine typos in the filings themselves (a dropped leading digit, a malformed
number, a sign error) where the printed table doesn't foot → skipped, storing the
faithful printed value.

Verifying the last 14 missing found zero genuine non-disclosure. Eight were a
second header-split cause — the Turkish "ABD Doları"/"Diğer YP" cells splitting
across physical lines — hand-overridden from the printed tables. Six are FIBA,
which prints the currency-risk table as a bitmap or vector graphic; those were
hand-transcribed from renders, each cross-checked against the report's own "net
yabancı para pozisyon" prose sentence.

Worth flagging beyond this lane: `parse_num('-319.110')` returning -319.11 is a
shared-parser bug — it only bit two fx cells here, but it could silently corrupt
any hyphen-negative thousands value across every statement lane, so it deserves a
corpus-wide check. All 18 hand-read cells read `manual`. Detail in PROJECT_STATE's
market-risk note.

2026-07-17 — **Liquidity: 24 errors + 1 missing → 0/0. Most of it was
bands calibrated for established banks, false-firing on new ones.** A
newly-licensed bank is almost entirely equity-funded, so its leverage ratio runs
30–97% (HAYATK 97%, ENPARA 95%, TOMK 93%), each confirmed against Tier1/total
assets — so the (0,30) leverage band was widened to (0,100), the real ceiling
since Tier1 can't exceed total exposure. That cleared 18 cells with no data
change.

The LCR upper bound (2000%) was removed outright. BDDK's LCR is the average of
the quarter's weekly ratios, so a bank with near-zero net cash outflows genuinely
prints LCRs in the thousands to millions of percent — COLENDI 2025Q2 prints
2,316,303%, ENPARA 34,221%, DUNYAK 17,858%, all pixel-verified against the printed
row. And a misread HQLA amount overlaps that range exactly (COLENDI's real
weekly-max LCR was 9,878,895%), so no ceiling can tell a genuine huge ratio from
an amount — a coverage ratio simply has no upper limit. Confirmed no established
bank has an LCR over 2000%, so nothing real is now hidden.

Takasbank's sub-100% NSFR turned out to be legitimate: development and investment
banks are exempt from the 100% floor (cited in the report), and it discloses no
LCR at all. So the <50% "implausibly low" heuristic false-flags it — curated as a
liquidity skip. Its two mis-stored quarters (both holding the stale 31-Dec-2023
prior-period value 38.39) were corrected to 49.16 and 54.72.

The only real LCR bug was TOMK 2023Q4 — a comma-as-decimal misparse that read
"3,768" as 3.768 instead of 3768.83. And HAYATK 2023Q2 (missing) got its leverage
filled at 97.5%; its LCR and NSFR are genuinely N/A because the bank "has not yet
commenced banking activities". All four override cells read `manual`. Detail in
PROJECT_STATE's liquidity row.

2026-07-17 — **Capital adequacy: 26 errors → 0, fixed from the printed
§4 tables.** Two shapes: 13 real failures (a dropped RWA, tier1, or ratio; a
misread total) and 13 zero-pass cells where tier1 and the ratios were both
dropped so the validator could verify nothing. Every fix is read off the PDF and
pixel-verified.

TOMK ×10 dropped `total_rwa` from 2024Q1 on — its own label changed to lowercase
"Risk ağırlıklı Tutarlar" and the anchor missed it — plus a 2024Q1 Tier-2 the
filing misprints as a dash on its own subtotal line. HAYATK ×10 dropped Tier 1
(= CET1, AT1 is nil) and all three ratios. ISCTR 2024Q1's value column printed
shifted up one row, so Tier 1 got stored as AT1 and total equity as Tier 2 — a
full rewrite. DUNYAK 2023Q4 inverted my premise: its total was correct (a real
₺500m sukuk Tier-2 instrument), and the wrong cell was Tier 2 itself, which the
filing's own subtotals drop while its headline equity row and CAR include it.

Two things that weren't data errors. ENPARA 2025Q4's composition gap is a printed
BDDK forbearance add-back ("other accounts determined by the Board"), with no
schema column to hold it — curated as a forbearance skip. And the CAR
plausibility band [5,80] was simply too tight for newly-licensed banks: they hold
capital far above their tiny risk-weighted assets, so ZIRAATD's 85%, and TOMK's
93.75% and 138%, are all genuine and reconcile to Total/RWA exactly. The band now
defers to that reconciliation — a CAR that ties to its own capital and RWA is
verified, so the band only guards a ratio it can't reconcile — which cleared those
without touching the data.

Every §4 capital-override cell now reads `manual` rather than a machine `ok`
(`_STMT_TO_KEY` learned "capital", 54 cells), since a human stands behind each
recovered figure. Detail:
[docs/knowledge/audit-loans-by-sector-lane-to-zero-2026-07-17.md] covers the
sibling lanes; this one is recorded in PROJECT_STATE's capital row.

2026-07-17 — **Loans-by-sector: 6 errors + 7 missing → 0/0, and 6 cells
that read a flawless `ok` were silently wrong.** TAKAS ×4 stored an average
**Value-at-Risk** (`Toplam Riske Maruz Değer`) as a loan sector total — the
heading regex matched the note that answers *itself* "Bulunmamaktadır", found no
table, and the split-table retry wandered onto the next page's market-risk table.
Fixed by skipping a sector note that declares itself nil, proven neutral on six
varied banks (the extractor with-and-without the change extracts identical
counts). TOMK 2024Q4 is a genuine source defect (the bank prints its own services
subtotal as a dash while a child carries ₺85m) → skip-listed.

The seven "missing" are all genuinely N/A now, each with a verbatim citation —
and **four of these banks turned out to be TFRS-9 non-appliers** (DUNYAK,
ZIRAATD, COLENDI, plus the known TOMK), each wording the art. 9/6 exemption
differently, which is why earlier probes missed them.

**The ALNTF N/A was false and is the headline correction.** It discloses
stage-by-sector in all eight reports; the column captions are the legacy
*Değer Kaybına Uğramış / Tahsili gecikmiş*, but the numbers *are* the stages —
the sector total equals the report's own *Yakın İzlemedeki / Takipteki* stage
note to the lira, and ALNTF states it applies TFRS 9. So the legacy-schema
detector fires correctly but its premise is wrong: legacy captions don't imply
legacy data. Those cells now read honest `missing`.

Two new zero-false-positive checks. **`loans_sector_year_swap`** catches what
footing structurally can't — a wholesale year-swap foots perfectly against
itself. ICBCT stacks two *dated* tables on one page (never "Cari/Önceki Dönem"),
so the period never flips and dropped current rows get backfilled from last year;
its 2023Q4 unconsolidated cell was reading a flawless `ok` while storing its own
2022 total, Stage 3 understated 3.1×. Calibrated 2/236, both ICBCT.
**`loans_sector_child_exceeds_parent`** is a mathematical invariant — a child
sector can't exceed its group total — that surfaced eight merged-label
corruptions the footing check is blind to (e.g. ICBCT stored a ₺635m fishery
exposure that was really the prior year's Sanayi total).

Nine partitions (ICBCT ×7, AKTIF ×2) were hand-transcribed off the printed page,
every cell 7–13× pixel-verified and foot-checked, via a new
`loans_by_sector_replace` override; they read `manual`. The root cause is the
shared y-bucketing text reader (`int(round(y0))` aliasing a 3.4pt intra-row
offset), which can't be touched without disturbing every frozen statement lane —
hence overrides rather than an extractor rewrite. One process note: a whole-lane
`--force` re-extract regressed AKBNK and DENIZ mid-way and was reverted from the
R2 snapshot — `--force` runs current code over rows frozen by older code, so it's
never a clean isolation. Detail:
[docs/knowledge/audit-loans-by-sector-lane-to-zero-2026-07-17.md](knowledge/audit-loans-by-sector-lane-to-zero-2026-07-17.md).

2026-07-17 — **NPL movement: 13 errors + 43 missing → 0/0. The entire
error lane was one missing string.** HAYATK prints its closing row, in bold, in
all 13 reports as `"Ending balance of the current period"` — the one "ending
balance …" word order `_ROW_LABELS` never learned. The list already had BURGAN's
`"ending balance of prior period"` → *opening*; the closing mirror was simply
never added, and `startswith()` matching made it unreachable from every other
entry. The article is load-bearing: `"ending balance of current period"` would
still have missed. The natural experiment settles it — 2025Q2 consolidated is
HAYATK's only **Turkish** report and the only consolidated period that passed;
the 12 failures are exactly the English ones.

Values are **transcribed, not derived**. `closing_balance` was over-determined
three ways (roll-forward; `net + |provision|`; prior-closing == current-opening),
so filling it from our own arithmetic would have made the roll-forward check pass
**by construction** — the same circular-validation flaw the robustness audit
found in fx `net_position`. The extractor now reads the printed number, so the
check stays a real test. 13/13 match the page; the derivation agreed on 39/39,
but agreement was the check, not the source. It also ties to a *different* note
and to the balance sheet: printed closing III+IV+V 506,844 = `npl_brsa_gross`
506,844; stage1 13,072,410 + stage2 193,657 + NPL = 13,772,911 = BS 2.1.
ZIRAATD 2026Q1 is the mirror — *opening* NULL on its first-ever NPL quarter,
where the cells are printed genuinely blank; its 0 is sourced from prose
("31 Aralık 2025: Bulunmamaktadır"), not inferred.

**43 missing → 42 N/A + 1 real gap**, each N/A carrying a verbatim citation
(TAKAS's *"Toplam donuk alacak hareketlerine ilişkin bilgiler: Bulunmamaktadır"*
in all 16 quarters, DUNYAK ×8, HAYATK ×5, TOMK ×5, ENPARA ×3, COLENDI ×3,
ZIRAATD ×2). **The TAKAS story we brought was false, and the citation caught
it:** a CCP's *Krediler* are NOT money-market placements — they earn loan
interest (491,308 against 0 from money markets), are 100% *Mali Kesime Verilen
Krediler*, and ₺6.58bn of ₺9.63bn is lent to its own clearing-member
shareholders. Real credit that simply never defaults. Right verdict, fictional
reasoning — which is exactly why an N/A needs a citation and not a plausible
story.

The one real gap is **COLENDI 2026Q1** — its first NPL (₺26,725, 2.50% of the
book), printed at p49 and hidden by **three** independent defects: the heading
reads "Information related **to** non-performing loans" (no "movement", so the
page is never parsed); the text layer is **cell-per-line**, so the row matcher
finds zero rows even with the gate bypassed (it needs x-coordinate assembly); and
the closing label lacks a "the". Curated for now — it recurs every quarter until
the second is fixed.

Also: `_STMT_TO_KEY` learned `npl_movement`, so 9 hand-read cells (FIBA ×6 out of
bitmaps and vector outlines, COLENDI, ZIRAATD, AKTIF) stop reading as
machine-extracted `ok` and now read **manual**. Detail:
[docs/knowledge/audit-npl-movement-lane-to-zero-2026-07-17.md](knowledge/audit-npl-movement-lane-to-zero-2026-07-17.md).

2026-07-17 — **/credit's bridge prose read the nominal at the wrong week — the
sentence stopped adding up to its own chart.** `creditBridge` computed
`nominalAtReal` (the nominal read at the week the *real* legs end, so a CPI lag
can't mix a July nominal with a June real) and then **discarded it**, returning
only `nominal` at the latest week. `Bridge.tsx` worked around the gap by
reconstructing the start bar from the legs (`realFxAdj + inflationPp +
currencyPp`), so the chart stayed correct — but the prose beside it had no such
workaround and printed `bridge.nominal`. Live, that read **"Nominal credit grew
36.2%"** next to a chart bar reading **36.4%**, and the paragraph's own
arithmetic broke: 36.2 − 7.1 − 31.4 = −2.3, while it concluded the book shrank
**2.1%**. Exactly the failure `credit.ts`'s own comment says the design guards
against — the guard reached `currencyPp` and the chart, never the sentence. Fix:
expose `nominalAtReal` on `CreditBridge`; the chart now reads it instead of
re-deriving it, and the prose starts from it. `nominal` stays the vitals'
headline (latest week), which is correct for the Vitals + Attribution sections.
The bug was invisible to tests because the fixture held nominal **flat**, so both
fields coincided — and the reconciliation test hardcoded `36.6` rather than
reading the field it stood for. The fixture now moves the last week, and three
tests pin the split. Widened by the weekly refresh (real legs sit at W/E 26 Jun
until July CPI prints ~3 Aug, so the gap grows a week every Friday).

2026-07-17 — **IFRS-9 stages: 12 errors → 0, and two "the bank didn't disclose
it" notes were false claims about the bank.** The new `stages_bs_loans`
reconciliation (stages total ⋈ balance-sheet loans 2.1) flagged 9 cells, **6 of
which passed every other check** — the internal identity `total = S1+S2+S3`
cannot see an error that preserves the sum, so only a cross-source anchor could.
SKBNK 2025Q4 was publishing an **NPL of 39.51% against a truth of 1.29%**: the
extractor had grabbed the §4 NPL-by-sector table, and its `1,003,122` was
**synthesised** (Stage-3 Provisions + Write-Offs) — a number appearing nowhere in
the PDF. FIBA ×9 had three causes, incl. reading the **collateral-type**
breakdown (mixing current and prior periods across two portfolios: `18,574,043 +
3,248,468 + 3,540,679 = 25,363,190`, exact) and falling through a
**vector-outlined** §5.2 onto a **day-count ageing** table. Proven not by a band
but by a closed identity — **S1+S2+S3 − faktoring = BS 2.1, exact to the lira**
on all nine, which *predicted S3 before the page was rendered* on four; FIBA's
own printed ratios agree (%1,68 → 1.68%, %1,09 → 1.09%).

**N/A 11 → 3.** ICBCT 2023Q4 cons and TSKB 2026Q1 unco were curated "not
disclosed" on an empty text layer; both banks had filed in full. We had
configured ICBC's IR-page `Mali Tablo` (tables-only, 9pp) link instead of its
`Dipnotlar` link — the real report is **108pp**, and our copy's own balance sheet
carried a `Dipnot / (Beşinci Bölüm)` column with **39 cross-references** into a
section it didn't contain. R2's TSKB object was a **KAP XBRL rendering**, not the
report; PwC's opinion *inside our own copy* cites *"beşinci bölüm"* and
*"ilişikte yedinci bölümde"*, and the URL already in the config served the real
**100pp**. Both re-fetched and re-extracted — every §4/§5 lane populated, stages
reconciling at ratio **1.0000**. The surviving 3 (TOMK) are confirmed on a
*positive* citation: a BDDK-approved **TFRS-9 non-applier** runs no ECL model, so
no stage table can exist.

Found on the way: `build_bank_audit_stages.py`'s comment said *"when all three
present"* while the code said **`any`** — with S1 and S2 absent the sum collapsed
to S3 alone and the row asserted **every lira lent was non-performing**. **161 of
836 prior rows**, now 0. Latent, not live (no `current` row affected; all
consumers filter `period_type='current'`) — but `bot-sql.ts` lets an LLM write
its own SQL, so it was one forgotten `WHERE` from being quoted as fact. Also
mirrored D1 migration `0030` into `schema.py`'s `_COLUMN_MIGRATIONS`:
`section`/`section_rank` were declared only in the `CREATE TABLE`, so any DB
restored from the R2 snapshot crashed `sync_audit_expected` on `no such column:
section`. Detail:
[docs/knowledge/audit-stages-lane-to-zero-2026-07-17.md](knowledge/audit-stages-lane-to-zero-2026-07-17.md).

2026-07-17 — **The /admin coverage matrix called four primary statements
"footnotes". Fixed.** OCI, statement of changes in equity, cash flow and
off-balance sheet were grouped under a heading reading *"Footnotes & §4"*. All
four are **§2 primary statements**: TAS 1 requires OCI, changes-in-equity and
cash-flow in any complete set of financial statements, and off-balance (*Nazım
Hesaplar Tablosu*) is a BRSA addition **printed on the balance-sheet page**, not
in the notes. Only credit-quality/stages/sector/NPL (§5), capital/liquidity/FX/
repricing (§4), profile (§1) and the opinion (§7) are genuinely outside §2.
Cause: `CoverageMatrix.tsx` split its two groups on `registry.is_core` — but
`is_core` is a **severity** flag ("an empty lane here means the extraction
failed, fail the whole report"), true for exactly BS assets / BS liabilities /
P&L. The four are `is_core=False` so that one unreadable note-page can't discard
a good BS+P&L extraction — *not* because they're notes. The view borrowed a
pipeline gate as an accounting taxonomy. The misconception was in the source of
truth too: `registry.py`'s own header comment read "core financials first, then
footnote/§4 tables". Nothing was wrong with the data — only with what the
operator was told it was. Fix: a new **`section`** field on the registry (the
bare Bölüm number `1`/`2`/`4`/`5`/`7`; the `§` is typography and stays in the
view) carrying report **provenance**, mirrored to D1 via migration **0030**
(+`section_rank` from `registry.SECTION_ORDER` for display order — primary
statements lead, *not* the filing's own §1→§7, which would open the matrix on
branches/personnel). The matrix now renders five honest groups and no longer
reads `is_core` at all — it's dropped from the client's `TypeRow`, so it can't
be misused again. 0030 **backfills** the live rows: deploy applies migrations but
doesn't re-run `sync_audit_expected.py`, so without it the matrix would show one
blank heading until the next audit refresh. `tests/test_registry_sections.py`
pins section-vs-is_core and diffs the hand-written SQL backfill against the
registry (mutation-tested: drifting the backfill, refiling OCI as §5, and
"promoting" OCI to `is_core` each fail). `is_core` still gates `success` for
exactly the same three lanes — no extraction behaviour changed. While here,
`AUDIT_PIPELINE.md`'s statement table gained the four lanes it never listed
(fx_position, repricing, audit_opinion, free_provision) and lost a stale claim
that `profile` writes no validation row.

2026-07-17 — **DUNYAK's net profit was reading 0 on the dashboard. Fixed.** The
2026-07-16 validator fix taught the *validator* that BRSA roman ordinals aren't fixed;
`heatmap.ts` never got the message and made the identical mistake in SQL:
`net_profit = COALESCE(XXV., XIX.)` and `opex = XI. + XII.`. For the compressed template
those romans are different lines — DUNYAK's period-net is **XXIV**, so `XXV.` is NULL and
the COALESCE fell through to `XIX.` = *discontinued-operations income* = 0. Verified in
production D1 before the fix: 2024Q4/2025Q1/2025Q2 all read **0** against true
1,353,642 / 360,967 / 676,596. `net_profit` feeds **ROE**, and DUNYAK is not
peer-excluded, so it rendered. `opex` was wrong on 9 partitions (DUNYAK ×8, TOMK 2023Q4)
— `XI.+XII.` summed other-opex plus net operating *profit* — feeding **Cost/Income** and
**PPOP**. It survived because the template varies **by period within one bank** (DUNYAK
2024Q1/Q2 use the XIX/XXV variant and read correctly). Found while investigating the P&L
spine gaps ([knowledge write-up](knowledge/pl-spine-gaps-2026-07-17.md)).
Fix: a new derived table **`bank_audit_pl_roles`** (migration 0029) tags each P&L row
with what it IS — `period_net`, `gross`, `opex_personnel`, `opex_other`, … — resolved
against the filer's own numbering by `validator.pl_roles()` and rebuilt from stored rows
beside the validation, so the two can never disagree. `heatmap.ts` joins it instead of
guessing. The resolution stays in Python deliberately: re-deriving it in SQL means
`UPPER()` (ASCII-only — "Dönem net karı" never folds) plus hand-cut wildcards over **79**
distinct period-net labels, and a second copy to drift. `III.`/`VIII.`/`IX.`/`1.1`/`2.1`
stay ordinal-keyed on purpose — verified stable in 1050/1050 partitions, not assumed.
Opex falls back to the last two rows of the deduction band when labels are unreadable
(AKBNK 2022Q4/2026Q1 print the P&L with EMPTY item_names); the fallback agrees with the
label match on all 1,046 partitions that have labels. Old-vs-new over the whole corpus:
**9 rows changed, 0 regressions, row set identical**.

2026-07-16 — **Income statement: 13 failing partitions → 0.** Only 4 were data errors;
9 were the validator being wrong about how those banks number their own statement.
`check_pl_chain` hardcoded the standard ordinals (gross VIII / net-op XIII / pre-tax XVII /
tax XVIII / cont-net XIX / period-net XXV) and the deduction band `{9,10,11,12}`, but the
**compressed template** some participation banks file drops an opex roman and shifts
everything after it — net-op XII, pre-tax XVI, tax XVII, then cont-net XVIII + period-net
XXIV (DUNYAK), or cont-net XIX with **no XVIII at all** (TOMK). Each report states its own
numbering in the formula it prints ("XVI. …VERGİ ÖNCESİ K/Z (XII+...+XV)") and foots under
it, so the check was comparing those banks' TAX row against the pre-tax sum — 9 permanent
false failures on correct data, and no real validation of their chain. The chain is now
assembled **per-partition from anchor rows found by label** (folded Turkish→ASCII,
uppercased, whitespace-stripped, since the extractor emits both "DÖNEM NET KARI" and
"DÖNEMNETKARI/ZARARI"), with the deduction band derived from the anchors. Every anchor
falls back to its standard ordinal when its label is unreadable, and the template reverts
to standard wholesale unless the anchors come out strictly increasing → unreadable
partitions behave exactly as before. Corpus diff over all 1050: pass 6205→6227, fail 21→5,
skip 74→68 — **0 newly failing, 9 fixed, coverage UP** (the identities these banks were
never really checked on now run); every other lane byte-identical. The 4 real defects, each
hand-transcribed from the PDF into `audit_overrides.json`: **TAKAS** 2023Q2/Q3+2024Q3 print
XXIV as a copy of net profit though XX–XXIII are nil → 0 (extraction faithful to a source
copy-down artifact; ODEA precedent); **HAYATK** 2024Q2 pre-tax captured the dipnot ref
"(4.9.)" as its value (4.9), with XVIII and XV dropped by the same wrapped label →
−400.486 / 174.727 / 0; **TOMK** 2023Q4 read every "(81)" cell as a dipnot ref → IV + 4.2 +
4.2.2 restored (VIII now foots to the printed 425.825). `apply_overrides` P&L inserts now
accept `item_order`: a restored roman appended after XXV falls out of the increasing-
subsequence spine and its identity silently **skips** — ANADOLU 2022Q1's appended IV. has
left VIII=III+IV+V+VI+VII unchecked since it was authored. Full write-up:
[docs/knowledge/income-statement-errors-2026-07-16.md](knowledge/income-statement-errors-2026-07-16.md).
Open: 66 partitions have gaps in the roman spine (a dropped row makes its identity skip
silently) — not investigated.

2026-07-15 — **pdfplumber removed entirely — every PDF extractor is now fitz (PyMuPDF) only.**
The last three holdouts moved off pdfplumber: (1) the frozen BS/P&L `_parse_page` /
`_detect_pl_ncols` in `extractor.py` — they had run BOTH engines and picked whichever
found more rows (tie → pdfplumber, the proven baseline); now they read `_fitz_page_text`
directly, whose coordinate reconstruction (y-bucketing word boxes + split-digit merge +
`/Rotate 90` rotation-matrix mapping) is a **strict superset** of the old pdfplumber
layout-repair and never shatters a value the way pdfplumber's letter-spaced text did.
(2) `profiler.py` — rewired to `_locate_pages(pdf_path)` + `_fitz_page_text`; this also
**fixes a latent bug** where it passed a pdfplumber PDF object to the now-path-based
`_locate_pages`, which silently returned `{}` (so every profile lost its section pages).
(3) `src/faaliyet/extractor.py` — Pass A now reads fitz page text via a single-open
helper. Also deleted the dead `_n_pages` / `_safe_repaired_text` / `_run_with_timeout` /
`_PDFPLUMBER_POISON` / `_page_text` / `extract_page_text_repaired` block (zero call sites,
flagged by the 2026-07-14 arch check), the pdfminer poison-PDF watchdog, and the two
remaining script users (`diag_partition.py`, `catalog_audit_templates.py`,
`ingest_policy_baseline.py`). `pdfplumber` dropped from `requirements.txt` and `ci.yml`;
the 10 `pytest.importorskip("pdfplumber")` guards flipped to `"fitz"`. **No production
data re-extracted** — the change is code-only; already-extracted rows are untouched and
only *future* extractions use the fitz-only path. Full unit suite green (389 passed).

2026-07-15 — **New brand mark: the Carthago compass.** The logo is a navy→blue gradient
compass — an open "C" ring, a pointer needle, a centre hub, two orbital dots reading as
an "i", and a lower swoosh — replacing the blue hatched disc. It is the supplied artwork
keyed to transparency and committed once at `scripts/brand/carthago-mark.png`; every
asset (favicon, app icons, social cards, `public/logo.png`) is **composited from that one
PNG** by `scripts/make_brand_assets.py`, so the mark cannot drift between uses — to change
the logo, replace that PNG and re-run. Everything is transparent so the mark blends with
whatever is behind it (browser tab bar, paper ground, graphite nav) rather than sitting
in a box. The compass has navy elements that sink into the dark sheet, so the nav swaps to
a tonally-lifted variant (`public/logo-dark.png` — same mark, lightness raised toward white
with hue preserved) in dark mode. `apple-icon.png` is the only opaque asset — iOS renders
transparency as black.
The social card is the mark + Instrument-Sans wordmark on the light brand ground with the
"Turkish banking data" tagline. Brand palette + the replace-and-regenerate rule are
recorded in `web/DESIGN.md`.

2026-07-14 — **Market-risk data was extracted for weeks and never pushed to D1.**
`refresh-audit.yml` — the lane that ingests every new quarter — hand-listed 14 of the
16 audit tables in `--only-tables`, omitting `bank_audit_fx_position` and
`bank_audit_repricing`. Both were extracted, validated and written to the R2 snapshot
on every run, and silently never reached D1: `push_to_d1`'s `--only-tables` was an
unvalidated filter over `SYNC_TABLES`, so a forgotten table matched nothing and the
push still exited 0. `/market-risk` was frozen at the 2026-06-29 manual backfill while
every other audit page advanced. Fixed at the root rather than by adding two names:
the table list is now **derived** from `src/audit_reports/registry.py` (registering a
statement type is the only step), workflows pass `--table-set audit`, `push_to_d1`
**hard-errors** on a table it cannot sync, and `tests/test_audit_tables_sync.py` fails
if any workflow hand-lists `bank_audit_*` again. Related: `seed_audit_db` no longer
seeds the extraction log (it would have made a DR restore permanently skip the
re-extraction it exists to trigger); `check_docs_sync` now guards ARCHITECTURE and
PROJECT_STATE, not just OPERATIONS; `check_pipeline_graph_sync` now fails on a page
node whose `href` 404s; and CI installs pdfplumber/pymupdf/pandas, so the 13 test
files that were passing-by-skipping (86 tests) actually run. Audit:
[knowledge/2026-07-14-architecture-and-docs-check.md](knowledge/2026-07-14-architecture-and-docs-check.md).

2026-07-12 — **Franchise tab unpublished (archived, not deleted).** `/franchise` was
pulled: the extractor samples stray numbers out of surrounding prose, so **~75% of
non-ATM values are wrong** (Akbank's 6,210 ATMs read as 202; TSKB, with no ATM network,
read as 8) and the per-cell confidence flags do not correlate with correctness, so they
can't be used to filter. Code preserved un-routed under `web/app/_franchise/` (same
Next.js private-folder treatment as `_valuation`); nav link and sitemap entry removed.
The ingestion lane still runs. Re-shipping needs a rebuilt extractor behind a validation
gate (branch reconciliation vs `bank_audit_profile` + YoY sanity), **not** more per-bank
URL curation — curating URLs would only publish the wrong numbers faster.

2026-07-10 — **Valuation tab hidden (archived, not deleted).** The `/valuation`
tab was removed from the site at the user's request. Its code is preserved
intact and un-routed under `web/app/_valuation/` (Next.js private folder — opts
the whole subtree out of routing, so `/valuation` no longer serves, but the
files stay in-tree and typechecked). The nav link (`web/app/components/Nav.tsx`)
and the sitemap entry (`web/app/sitemap.ts`) were removed. Supporting libs
(`valuation.ts`, `valuation-data.ts`, `valuation-presets.ts`) stay in
`web/app/lib/`. Revival steps are in `web/app/_valuation/README.md`. The separate
"Market & Valuation" panel on each bank's own page (`bistValuation`) is unaffected.

2026-07-07 — **SEO / discoverability: the dashboard is now crawlable.**
On-page work only. `web/app/robots.ts` + `web/app/sitemap.ts` expose a crawlable route list;
every route gained `metadata` (title, description, `alternates.canonical`); JSON-LD structured
data added to `layout.tsx` + `page.tsx`. Rationale, the manual Google Search Console / Bing
verification steps (they can't be automated from CI), and the ranking strategy are recorded in
`docs/knowledge/seo-and-search-console.md`. Off-page — backlinks — is the actual ranking lever
and remains unstarted; the strategic review names distribution as the project's biggest gap.
(Follow-up, found 2026-07-08: `/franchise`'s new metadata described market share + HHI, which
live on `/cross-bank`; corrected to the operational-footprint copy the page actually renders.)

2026-07-05 — **Public Telegram Q&A bot: text-to-SQL over D1, rebuilt as a self-correcting agent loop.**
Shipped as a two-call pipeline (`7b79755`: question → SQL → rows → summary) and replaced the same day
by `runAgent` (`f98f203`), a loop of at most 6 query/refine rounds in which the model sees each
result — or the SQL error, or `0 rows` — and self-corrects before answering. Runs inside the existing
Worker; no new service. Migration **0020** adds `bot_usage` (per-chat + global daily caps).
Every query passes `bot-sql.ts` (single `SELECT`/`WITH`, row-capped, writes/DDL/multi-statement
rejected — 29 vitest cases), so a prompt-injected write is impossible.
The hard problem was *ungrounded figures*, fixed in layers: a `gotData` guard rejects any answer
stating a 4+ digit number or a `{placeholder}` before a query has returned rows and pushes the model
back to querying (`8aea015`, `6d0b346`); grouped-number separators are stripped **before** that test
so `43.520.620` still trips it (`6fb49ba`, `7d0df6c`); amounts are then re-grouped deterministically
by `groupThousands()` rather than by the model, with lookarounds that spare years, periods, decimals
and Turkish decimal commas (`c45c7a8`, `ca1c218`). Also: answer in the question's language
(`9615a1c`); never guess the reporting quarter — `SELECT` it (`32079f1`); replies are plain prose,
the SQL and raw table demoted to diagnostics (`7a9296e`, `6b28fdd`, `5c3c27d`).
Provider chain flipped to **Groq-first** (`bc6e6a9`) — same `gpt-oss-120b` model, far higher free-tier
rate limit, which matters because the loop makes several calls per question; this intentionally
diverges from the Cerebras-first Python reads lane. Schema-prompt corrections along the way: SQLite
has no `ILIKE` (`36bd208`); net profit anchors on the (XIX+XXIV) formula, not fragile text
(`6414343`); per-bank loans come from `bank_audit_stages.total_amount` (`abab75f`); deposits live on
the liabilities side (`41e676d`); grand totals via `MAX(amount_total)`, not label matching (`c483b92`).
Webhook can self-register from `/admin` (`13b1016`); the CLI prompts for token/secret on hidden input
(`2211978`). Setup + architecture: `docs/TELEGRAM_BOT.md`.

2026-07-05 — **"The Read": LLM-rewritten headline per dashboard tab.**
New weekly lane (`generate-reads.yml`, Sun 07:30 UTC) → `read_headlines` → D1. Live on the Overview
first (`b6c3ce3`), then all 8 tabs (`b8c313a`). Free providers only, no paid API. Hardening: retry the
*same* provider on a 429 before failing over, so the primary stays primary (`6fd8e0c`); per-family
pacing to respect Cerebras' ~5 req/min (`05667fb`); a magnitude-matching number validator so a
sign-flip isn't scored as an invented figure (`83f158e`); fall back to the prod URL when `SITE_URL`
is the empty string, not merely unset (`9db7f7c`); Telegram notification per run (`5e2479b`).
The gemma tier was dropped once both providers served the same `gpt-oss-120b` (`c5c221c`); the chain
now falls back to a deterministic template rather than a weaker model. Provider selection was decided
by a throwaway bake-off, kept as `docs/knowledge/free-model-eval*.md` and then deleted from the tree
(`d4e456a` … `ebcdd78`); Gemini was dropped for refusing to serve within a free cap (`11daf7b`).

2026-07-05 — **Presentation deck generator + banks dimension + schema-naming CI gate.**
(a) One-command sector deck: reads → HTML → PDF (`27b2396`), an `/admin` "Generate presentation"
button and deck route (`8bd3069`), then a designed layout with KPI vitals and per-section trend
charts (`f63a701`). Source of truth is `/api/presentation`, which reuses `metrics.ts` — so the deck
cannot drift from the dashboard.
(b) Migration **0021** adds a `banks` dimension table + cross-lane alias views (`f2a93cb`).
(c) New CI gate `scripts/check_schema_naming.py` + `docs/SCHEMA_CONVENTIONS.md` (`8edcc7c`): migrations
**≥ 0022** must use `bank_ticker` / `amount_fc` / snake_case / no reserved words / unique number.
Existing tables are grandfathered, so it currently enforces on zero files and emits drift notes only.
Also `e073815`: register `generate-reads.yml` in the pipeline graph, which its own CI guard demanded.

2026-07-05 — **Cloudflare Web Analytics — beacon injected manually, because the edge won't.**
Wired the analytics tags for the `/admin` traffic panel (`01fe505`), then found RUM stuck at 0: the
beacon was absent from the live HTML because Cloudflare's *automatic* edge injection does not fire on
the OpenNext Worker response. Fixed by rendering the snippet ourselves in
`web/app/components/Beacon.tsx` (`e7222a1`). At the time this treated Cloudflare's
site token and site tag as one identifier; the 2026-08-05 fix above split them after
the GraphQL query was found to return an empty dataset. The beacon renders nothing
when unset, so `next dev` never pollutes production analytics.
Also `5b348de`: real per-bank brand logos on `/banks` (static PNGs + `fetch_bank_logos.py`).

2026-07-04 — **Audit / financials: five dropped P&L lines recovered, cash-flow signs normalized, P&L flow now reconciles exactly.**
`56a296d` recovers 5 dropped/misread P&L lines, after which the whole fleet reconciles. The P&L flow
Sankey now **requires exact reconciliation** and treats deductions sign-aware (`dd218b7`), with
consistent signed negatives for deduction lines (`cbeb39c`); cash-flow outflow lines are
sign-normalized fleet-wide (`05dd1d9`). Two rendering defects behind the same surface: VAKBN's P&L
flow was blank because its hierarchy prints a **dotless** roman VI (`5788b90`), and the `1.1.3 Money
Market Placements` row was missing entirely (`e9baaed`).

2026-07-04 — **Liquidity: IMF-template reserve lines + six more BBVA charts.**
Net-reserves-excluding-swaps was computed off the wrong swap series; switched to the IMF-template
forward/swap position (`7e9b55c`) and added it as a third reserve line (`6045c67`). Six further charts
from the BBVA liquidity section rendered (`6f04bf2`), taking that section to 13 of 17 reproducible.

2026-07-04 — **`/sector/ratios` retired; Overview Snapshot and Ratios merged into one switchable scorecard.**
The standalone ratios page's only distinct value was the bank-**type** filter (a dashboard-audit
"clarify_purpose" item), so it folded into the Overview (`869d5b8`, `550daae`) and now redirects.
This removed a public route — noted here because nothing else records it. Also `d5b99bc`: fill the
last "The Read" grid row so no blank cell shows.

2026-07-03 — **`ensure_d1_schema` is now column-aware — D1 can no longer drift behind the snapshot schema.**
Root cause of the 2026-07-02 override-push failure: `schema.py` evolves existing tables via `_COLUMN_MIGRATIONS`
(+`init_schema`), which every LOCAL snapshot gets — but the D1-side `ensure_d1_schema` only applied the
`CREATE TABLE IF NOT EXISTS` DDL, which cannot add columns, so remote `bank_audit_extractions` was missing the
2026-06-27 market-risk counters (`rows_fx_position`/`rows_repricing`) and `push_to_d1` died mid-flight AFTER the
partition clear. Now `ensure_d1_schema` realises the canonical schema (DDL **+** `_COLUMN_MIGRATIONS`) in a
scratch in-memory SQLite, probes remote columns with one batched `PRAGMA table_info` wrangler call (`--command`,
not `--file` — a file import returns one summary object, not per-statement results), and applies **add-only**
`ALTER TABLE ADD COLUMN` for the gaps (never drops/retypes; non-constant defaults like `CURRENT_TIMESTAMP` are
legal in a CREATE but not in an ALTER, so they're dropped from the added column). A probe/mapping failure aborts
BEFORE any partition clear — strictly safer than the old mid-push death. Pure diff logic unit-tested
(`tests/test_audit_d1_schema.py`, incident-shaped regression); verified live: probe parsed all 19 tables,
remote reported in sync after the incident's two manual ALTERs.

2026-07-02 — **BS/P&L validator audit: two silent coverage holes closed, two data defects fixed, one new corpus check.**
A recompute-from-stored-rows corpus audit confirmed the BS/P&L validators sound (3900/3900 statement results
match a current-code recompute; the checks demonstrably catch prior-year-column capture and dropped romans on
a stale sandbox DB) but found the strongest P&L cross-check silently skipping 21% of the corpus. Fixes:
(1) `check_pl_bottomline` now finds the net-profit row by **hierarchy** (spine roman XXV + group-share 25.1)
in addition to the label regex, which missed the English template ("NET PROFIT/LOSS" — GARAN/YKBNK/TSKB/EXIM/
SKBNK/BURGAN), the participation word-order ("NET DÖNEM KARI/ZARARI" — ZIRAATK/ALBRK) and empty-label rows
(AKBNK 2026Q1): never-ran 209→0, ~230 newly-run checks pass. (2) `_pl_spine` now takes the longest increasing
**subsequence** of roman ordinals (was: longest contiguous run), so one misparsed roman (HSBC "XIV." stored as
hierarchy "X", 28 partitions) no longer severs the XV–XXV tail from the chain (≤4-identity partitions 35→8).
(3) The widened checks surfaced AKBNK 2022Q1–Q3 uncon P&L tails shifted one roman (net income on "XXIV.", no
XXV — the XIX identity and the /banks Financials net-profit line both blank) → new `pl_rehier` override type
renames the seven tail rows (amounts untouched; stored net ties BS 16.6.2 exactly), and TSKB 2022Q1 uncon whose
PDF prints P&L net 605,861 but BS 16.6.2 605,673 (both extracted faithfully; source self-inconsistent) → new
granular `_PL_BOTTOMLINE_SKIP` (chain identities stay guarded). Fleet after: P&L 974 pass / 0 fail / 1 skip;
assets/liabilities/cross 975/0/0. (4) New alert-only `check_audit_quality` check `pl_sign`: P&L deduction romans
(II, IX–XII) whose stored sign flips within a bank/kind series (19 standing series — BURGAN/DENIZ/QNBFB/TEB/
TFKB/ICBCT/ALNTF era-style convention changes; baselined via the R2 anomaly delta). The per-partition chain
check accepts either sign convention BY DESIGN, so flips are invisible to it, but they corrupt YTD
de-cumulation: `heatmap.ts` cost-of-risk took `Math.abs` only AFTER the TTM difference, mixing conventions
inside any window spanning a flip (BURGAN 2025Q2, DENIZ 2025Q1, QNBFB 2024Q1) → now normalises |IX.| at the
YTD snapshot (as opex already did). Also recorded: local `data/bddk_data.db` audit tables are a stale May-2026
sandbox (empty validation table) — probe against the pulled R2 snapshot (`data/bank_audit.db`), never it.

2026-07-02 — **Repo housekeeping after the folder-organization audit (no behaviour change).**
Four dead one-off scripts moved to `scripts/archive/` (`_eq_failreport.py`, `ocr_statement.py`,
`normalize_hierarchy_keys.py`, `load_partitions_batch.py` — referenced only in this changelog's history);
`scripts/README.md` index reconciled with disk (added the missing `check_pipeline_graph_sync`,
`metric_knowledge`, `update_nonbank`/`update_tbb_acquisition`/`update_tuik`/`update_faaliyet`/
`update_presentations`, `load_partition`/`apply_overrides`, and diagnostics
`validate_presentation_discovery` rows); vestigial `data/processed/` removed (no code references it;
`data/raw/` kept — still a diagnostic default path); the five unused create-next-app starter SVGs deleted
from `web/public/` (only `logo.png` is referenced); `docs/METRICS.md` no longer links the gitignored
`scripts/_weekly_catalogue.json` as if committed. Audit verdict recorded in
[knowledge/architecture-review-2026-07.md](knowledge/architecture-review-2026-07.md): tracked tree clean;
the clutter was gitignored working-directory scratch.

2026-06-28 — **pdfplumber removed from EVERY audit lane except the frozen BS/P&L `_parse_page`.**
The loader opened `pdfplumber.open()` for every partition (shared with BS/P&L) and equity/OCI/etc. carried
pdfplumber "fallbacks" that ran regardless — so a single-statement re-extract still loaded pdfplumber. Now every
non-BS/P&L lane reads via fitz off `pdf_path`: the three page locators, npl_movement, loans_by_sector,
credit_quality, fx_position, repricing, bank_profile, OCI (the GARAN/AKBNK fallback was the `/Rotate 90` issue the
rotation-aware `_fitz_page_text` already fixes), cash flow, and **capital + liquidity** (fitz flat-text primary —
the direct analog of pdfplumber's `extract_text` the parsers were tuned on — plus the clustered-line fill for
letter-spaced pages and capital's window fallback). The loader no longer calls `pdfplumber.open()`; pdfplumber now
runs ONLY inside `_parse_page` (BS/P&L) and `_detect_pl_ncols` (P&L), both untouched. Verified full-fleet
(2024Q4+2026Q1 dry-run vs prod): BS/P&L raw extraction byte-identical, OCI/cash-flow/NPL 0 diffs, loans_by_sector
behaviour-neutral; capital/liquidity clean apart from a handful of per-bank cells — TFKB LCR is a **correction**
(prod stored the prior-period "Önceki Dönem" table as current; the report's "%17.4 azalış" prose confirms
166.8→137.76), and ICBCT AT1 / QNBFB tier2 are the existing AT1/Tier2-drop class `apply_overrides` already handles.
Code-level change only — existing prod data (correctly extracted) is untouched; future extractions are fitz-only.

2026-06-27 — **equity_change is now fitz-only (pdfplumber removed); rotation was the real GARAN/AKBNK blocker.**
The equity extractor kept pdfplumber purely as the reader for GARAN/AKBNK, whose "wide interleaved table only
pdfplumber's x-clustering separates". The actual cause: those banks render the equity statement on a **`/Rotate 90`
landscape page**, and `fitz.get_text("words")` returns word bboxes in the page's UN-rotated space — so the visual
columns share a y and y-bucketing scrambles the table into garbage (duplicated values, headers merged into value
rows). pdfplumber applied the rotation; fitz (as used) didn't. Fix: map each word bbox through `page.rotation_matrix`
into display space in `_fitz_page_text` before y-bucketing (identity when rotation==0, so upright pages are
byte-for-byte unchanged). Then dropped pdfplumber from the equity path entirely — the `pp_text` reconstruction, the
`_safe_repaired_text` marker/n_cols reads, the `pdf.pages` fallbacks, the import, and the dead `pdf` parameter
(`extract_from_pdf`/`_locate_equity_pages` now take only `pdf_path`). Verified: **GARAN/AKBNK rotated pages recover
to 34 rows, 41/0 pass** (were 0 rows under naive fitz-only); a 11-bank × 4-quarter `--force` sample shows **0 clean
regressions**; the shared `_fitz_page_text` rotation change leaves NPL (and other fitz consumers) unaffected (6/6
pass). Removes the pdfminer poison-PDF watchdog from the equity lane. (OCI still uses a pdfplumber GARAN/AKBNK
fallback — same rotation root cause — left for a follow-up.) **Applied to prod (91→85).** A full `--force`
re-extract converged the real failures (91→85) but also over-extracted ISCTR's letter-spacing-corrupted image-only
quarters into partial-failing rows (transient 118 — `--force` re-ran them where `--only-failing`+skip-if-passing
would have excluded them). Followed with a **<14-row incomplete-parse guard** (complete statements carry ≥22 rows
across two periods; the broken parses top out at 9 — a clean gap) so a corrupted/incomplete parse stays empty/skip
instead of emitting wrong rows → ISCTR back to skip-passing, equity 85, verified live.

Prior: 2026-06-27 — **equity_change round 3: mid-split chaining + n-2 column recovery (107 → ~91).**
Two more residual causes after rounds 1–2 (343→107 in prod). (a) **Mid-page-split swap the year heuristic missed:**
ANADOLU prints both period tables on one page in prior-then-current order, but the period year appears only in the page
header — `_block1_period_for_split` looks for the latest year *after* the closing row, finds none, and defaults to
"current", swapping the periods. Fix: a value-based order signal — in prior-then-current order block1 (prior) CLOSES
where block2 (current) OPENS, so `block1.closing == block2.opening`; two years of movement separate them under the
standard order, so it never false-fires. ANADOLU current closing went 4,407,500 (prior year) → 6,903,091 (= BS equity).
(b) **n-2 dropped column:** ANADOLU's consolidated comprehensive-income row IV renders two component columns fully blank
(14 tokens in a 16-col table), so `_try_fit` dropped it and its total fell out of Σromans (`eq_col_chain` fail).
Extended `_try_fit` to insert two 0.0s, gated by the dual row-gate (Σcomponents==total AND total+minority==grand).
Decisive testing on the correct round-2 base (an earlier attempt was confounded by a pre-round-2 base): **+16 cleared
(ANADOLU, TSKB, …), 0 clean-data regressions.** The n-2 search *can* mis-recover ISCTR's letter-spacing-corrupted
image-only quarters (sparse, ~2 rows), but those are F=0/"passing" and so excluded by `--only-failing` + the
non-destructive skip-if-passing guard — n-2 only ever runs on a partition deliberately re-extracted. Applied to prod
via the reextract-statement CI lane. Remaining ~91 are genuine per-bank column misalignment / sub-1% chain near-misses
(TSKB) / image-only quarters.

Prior: 2026-06-27 — **equity_change round 2: two more period-assignment bugs (168 → ~98).**
After the prior-first "Önceki Dönem" fix (below, 343→168), the next-biggest offenders were still period swaps from two
other causes. (a) **Current page mislabeled prior:** the current matrix's header says "Cari Dönem" but its OPENING row
reads "Önceki Dönem Sonu Bakiyesi" (prior-period END = this table's opening); the marker test checked `_PRIOR_RX`
FIRST, so the current page matched prior and swapped (TSKB). Fix: check CURRENT first — only the current page header
carries "Cari Dönem"; the prior page never does. This also closes a latent regression the "Önceki" fix introduced for
current-first banks with that opening label. (b) **Marker-less pages:** ALNTF prints bare date-keyed rows with no
Cari/Önceki word at all, and prior-first order, so the positional default swapped them. Fix: a year-based tiebreaker —
the current table closes on the later period-end date, so the page with the larger max-year is current. Result:
**ALNTF 32→0, TSKB 33→15, ICBCT 17→6 — +70 partitions cleared, 0 clean-data regressions** (verified `--force` on
GARAN/DENIZ/YKBNK/VAKBN full-data partitions all still pass; the only `--force` fail was a near-empty image-only ISCTR
partition that `--only-failing` skips). The cross-checks reconcile to BS equity, so the passes are genuine. Remaining
~98 are genuine per-bank column misalignment / dropped roman rows / image-only quarters (ANADOLU 12, TSKB 15, …).

Prior: 2026-06-27 — **equity_change: halved the failing tail with one fix (period swap on prior-first banks).**
The `equity_change` lane had 343 failing partitions (the deferred tail from the sweep below). Re-extracting did NOT
help — until the root cause surfaced: `_PRIOR_RX` (the current/prior page-marker regex) matched "Önce/Öncesi Dönem"
but **not "Önceki Dönem"**, the standard BRSA term. Banks that print their prior-period matrix FIRST (HSBC: the 2023
page before the 2024 page) therefore had that page default to `current`; the enforce-distinct fallback then assigned
the two periods positionally and **swapped them** — so the stored "current" matrix was actually the prior year (closing
≠ BS equity, OCI row ≠ the OCI statement → both cross-checks failed on every period). Grounded on HSBC 2024Q4: stored
closing 11,536,971 = the 2023 year-end, not the 2024 BS equity 16,974,242. One-line regex fix
(`[OÖ]NCE(?:K[İI]|S[İI]?)?\s*D[OÖ]NEM`) → **HSBC 34/34 pass, and 184 of 352 failing partitions clear fleet-wide
(~52%), 0 regressions** (28/28 sampled passing partitions still pass; `--only-failing` never touches passing data).
Applied to D1 via the reextract-statement CI lane. The remaining ~168 are other issues (dropped roman rows / blank
closing-row totals — e.g. ZIRAAT 2023Q1 `eq_col_chain`), still open.

Prior: 2026-06-27 — **Audit data-integrity sweep: drove the non-equity anomaly backlog to 0.**
`check_audit_quality.py` flagged 374 anomalies; 343 are the known-open `equity_change` vertical-chain tail (left
as-is), and the remaining **31 non-equity ones were root-caused and fixed end-to-end** (D1 + R2). Five distinct
bugs: **(1) `_parse_ratio` TR-thousands** — `1.158,00` (an FC LCR of 1158%) was read as `1.158` because the parser
assumed EN format when both separators were present; now the rightmost separator is the decimal (fixed FIBA `lcr_fc`
2024Q1/Q2, 3 partitions). **(2) capital CAR-reconcile was forbearance-blind** — banks publishing a BDDK
transitional-adjusted CAR (ATBANK: printed capital/RWA 17.35% ≠ reported 18.92%) false-failed the `tc/RWA==CAR`
check every quarter (8 partitions); replaced with a reported-ratios-mutually-consistent check (the RWA each implies
must agree) at an 8% band, which tolerates forbearance but still catches column-slips. **(3) `npl_movement` opening
dropped** — BURGAN-cons "Ending Balance of Prior Period", EXIM "Balance at the End of the Previous Period", ODEA
date-glued "31 Aralık 2021Bakiyesi", and QNBFB's closing/provision + transfers_in label-wraps were unmatched, so the
roll-forward couldn't tie (14 partitions); added the label variants + extended the wrapped-label merge + relaxed the
date regex. **(4) `_statement_total` roman-ordinal collision** — a stray bank-name header captured as hierarchy `5`
displaced the real section V from ISCTR 2025Q4 off_balance's Σromans; now the larger-magnitude row per ordinal wins.
**(5) curated overrides** for EMLAK 2022Q1 AT1 (dropped Türkiye-Varlık-Fonu instrument), EMLAK 2025Q1 capital
column-slip (RWA read into total_capital), ATBANK 2025Q4 off_balance dropped section I, EMLAK 2022Q4 off_balance
mis-captured grand total — all PDF-verified. Also hardened `apply_overrides` to match BS rows
trailing-dot-insensitively (`rtrim`), fixing a latent phantom-duplicate (EXIM 2024Q4 `1.3.2.` vs normalized `1.3.2`)
that double-counted on re-apply. All five verified against a fresh prod snapshot (0 non-equity anomalies, no
collateral) before the live push; +13 guard tests.

Prior: 2026-06-27 — **Added the Faaliyet-raporları (bank annual report) franchise lane + `/franchise` tab.**
A new, fully separate ingestion lane (`src/faaliyet/`) that deterministically extracts the operational statistics the
audited statements don't carry — ATM / POS / merchant / customer / card counts — from banks' annual-report PDFs (the
same IR pages the audit lane already tracks). Branches & employees stay sourced from the audit reports'
`bank_audit_profile`, so this lane has no overlap with them. No LLM: a prose-regex pass plus a word-coordinate anchor
pass for infographic tiles, with suffix-aware number parsing (the `1.769` vs `1,769` trap) and per-metric sanity
bands + confidence flags — the audit/BS/P&L tables stay frozen. Stores a tall `faaliyet_franchise` fact table + a
`faaliyet_extractions` coverage log (migration `0014`), pushed to D1 via `push_to_d1` and refreshed incrementally
(non-critical) by `refresh.py`; the fleet backfill is `backfill-faaliyet.yml` (resumable, 5-bank push chunks). Wired
into the `/pipeline` graph + status, the metric-knowledge registry (new `faaliyet` source on 11 franchise metrics,
bumped `no`→`partial`), and a new `/franchise` dashboard tab. Ships with offline extractor unit tests.
**Not yet live:** the per-bank annual-report URLs in `data/banks/faaliyet_report_urls.json` are an empty skeleton
(seeded with IR pages) — curating them + applying migration `0014` + dispatching the backfill populates the tab.

Prior: 2026-06-27 — **Fixed the pinned header colliding with the per-bank section-nav.**
The 2026-06-26 header pin (below) made `PageHeader` sticky at `lg:top-0`, but `/banks/[ticker]` already pins its
in-page section-nav (`BankSectionNav`) at `lg:top-0` (z-30) — so on scroll both grabbed the same slot and the
higher-z nav painted over the top of the header, clipping the ticker eyebrow + bank-name title. Now the header and
section-nav are wrapped in one `lg:sticky` group so they pin **stacked** (header on top, nav directly below, flush —
no overlap). `PageHeader` gains a `sticky` prop (default true) that gates only its self-pinning, keeping its frosted
band so it still works inside a parent sticky group; `BankSectionNav` switches `lg:top-0` → `lg:static` (mobile
`top-14` sticky unchanged). Verified live on ISCTR (computed geometry: header y0–100, nav y100–152, wrapper pinned).

Prior: 2026-06-26 — **Pinned the page header (chart date-range selector) on scroll.**
The global 1Y/3Y/5Y/YTD/All chart-range control lives in the page header (`web/app/components/ui/page-header.tsx`),
which scrolled off the top on long chart pages. The header is now `position: sticky` at `top-0` on `lg+`, with a
frosted band (`bg/90` + `backdrop-blur`) that bleeds to the content gutter so charts scroll cleanly underneath.
Scoped to `lg+` on purpose — below `lg` the mobile nav bar owns `top-0`, so a sticky header there would collide.

Prior: 2026-06-24 — **Seeking-Alpha-style statement viewer — Cash Flow tab, standardized statements, YoY + TTM.**
The `/banks/[ticker]` Financials section now reads like Seeking Alpha's statement viewer. All server-rendered via URL
params (`statement=bs|is|cf`, `mode=abs|yoy`), no new client component; TL only (no currency selector, no inline
sparklines — explicitly out of scope).
- *Cash Flow tab + view toggles (`page.tsx`, `audit.ts`, `period-math.ts`):* a new **Cash Flow** tab alongside
  Balance Sheet / Income Statement, an **Absolute / YoY Growth** toggle (YoY compares each cell to the same quarter
  a year earlier on the displayed YTD values), and a **TTM** column for the income statement + cash flow (quarterly
  view only — suppressed in annual, where TTM == the Q4 YTD column; de-cumulated). De-cumulation/TTM/YoY math
  extracted to a shared, unit-tested `web/app/lib/period-math.ts` (`ordOf`, `periodFromOrd`, `singleQuarter`,
  `ttmEndingAt`, `yoyPct`); `bank-fundamentals.ts` now imports it. `cashFlowMultiPeriod` in `audit.ts` is
  try/catch-guarded so a missing/un-migrated CF table never 500s.
- *Cash Flow standardized (`standard_lines.ts`):* CF now renders from a canonical `CF_LINES` catalog — official BRSA
  English labels keyed by hierarchy code (sourced from GARAN, an English filer; Islamic dual-labels for participation
  banks) — exactly like the Balance Sheet and Income Statement, so the raw per-bank `item_name` is no longer shown and
  banks are comparable line-for-line. A D1 audit confirmed the CF hierarchy codes (1.1.x / 1.2.x / 2.x / 3.x detail +
  I.–VII. roman section totals) are consistent across all 31 banks; only labels varied. The verbatim render path was
  dropped; `cashFlowMultiPeriod` strips trailing dots (KUVEYT-class) at read time to match the catalog. Reconciles
  exactly for AKBNK + ALBRK (participation): I+II+III+IV = V, V+VI = VII.
- *P&L Sankey moved below the table (`page.tsx`):* the Income-Statement-view Sankey now renders beneath the
  standardized table instead of above it — table first, flow diagram second.

Prior: 2026-06-24 — **Per-bank balance sheet: uniform layout, single ECL, durable trailing-dot key fix, bold top-level rows.**
KUVEYT's amortized-cost sub-items rendered blank because its source PDF prints sub-item hierarchy codes with a
trailing dot ("1.1." vs the standard "1.1"), and the Financials table + cross-bank heatmap key on the EXACT code.
Four fixes, all deployed + verified live:
- *Uniform amortized-cost layout (`standard_lines.ts`, `page.tsx`):* every bank now renders the same rows — Loans,
  Lease, Factoring, **Securities at Amortized Cost**, Other, Expected Credit Losses — blank where a bank lacks a line.
  Replaces the per-bank relabeling (`resolveBsLineLabel`, dropped) that made labels inconsistent and produced a
  duplicate "--" ECL row for participation banks + Garanti (their code 2.4 IS the ECL, already shown via the 2.ecl
  remap). Both Factoring and Securities are always present; the one not applicable to a bank renders blank.
- *Durable trailing-dot normalization (`loader._canon_hier` + `scripts/normalize_hierarchy_keys.py`):* the loader now
  strips a trailing dot from multi-level numeric codes on every write — but ONLY for the catalog-displayed statements
  (assets, liabilities, profit_loss). off_balance is excluded (its sub-items are dotted as a convention across ~19
  banks / 24k rows, not UI-keyed, indentation derives from the code); oci/cash_flow untouched. The script backfilled
  the existing R2 snapshot + live D1 identically (idempotent). Fixed KUVEYT plus ALBRK, EXIM, KLNMA, ICBCT, which had
  the same defect partially. Values never touched, only the key string. D1 now 0 dotted assets/liab/PL, off_balance
  23,120 preserved.
- *Bold top-level rows (`page.tsx`):* a top-level BRSA Roman BS row is now always bold (section-header styling), so
  leaf top-level items — Held-for-Sale (III.), PPE (V.), Intangibles (VI.), tax assets, Other (X.) — no longer fold
  into the section above them. Sub-items stay indented. P&L unchanged (catalog/divider-driven).

Prior: 2026-06-22 — **Validator blind-spot audit — hardened 3 more lanes against silently-dropped columns.**
After the stages fix, audited every validator for the same skip-on-null pattern (a missing number `add_skip()`'d, so
the cell passed green `ok`). Three more lanes had it; cash_flow/P&L/OCI are safe (interlocked, cross-anchored chains)
and BS is triangulated, so they were left alone.
- *npl_movement:* a group reported with movement flows but opening/closing balance NULL → roll-forward skipped. Now
  FAILS `npl_movement_balance_missing`. Extractor (+121/−18): English balance labels ("Balance at the End of the
  Period"), date-keyed balance rows ("31 Aralık 2024 Bakiyesi" → position-assigned), scoped wrapped-transfer merge,
  bare-digit token. Filled ~86 of ~100 cells (ALNTF/AKBNK fully; EXIM 17→3, ODEA 17→1, BURGAN unco fully).
- *capital:* total_rwa/CAR NULL on a present §4 table → every reconcile skipped. Now FAILS `cap_rwa_missing` (RWA is
  the non-derivable denominator); `cap_car_missing` only when CAR is *also* non-derivable (RWA+total_capital absent) —
  a derivable CAR stays `ok`. Extractor (+109/−29): fitz line fallback (gated on RWA-absent → passing banks untouched)
  + CAR derivation. Filled 54 of 55 RWA cells (EMLAK/TFKB/TEB/FIBA/VAKBN/ANADOLU/ATBANK/HSBC).
- *loans_by_sector:* sector rows present but TOTAL row or all sector amount columns dropped → footing skipped. Now
  FAILS `loans_sector_total_missing` / `loans_sector_columns_missing`. Extractor (+88): ATBANK discloses per-sector
  stages correctly (fixed a Stage-3 wrapped-header bug) but genuinely has NO total → `_LBS_SKIP` verified-N/A; ALNTF
  uses the legacy pre-IFRS-9 schema (no per-sector stages — the old code FABRICATED stage3 from the row index) →
  detect + store 0 rows + not_disclosed. 0 errors.
Net: ~170 cells filled, matrix now reflects "every column populated". Honestly-flagged residual tail (long-tail
interim-format variants, now visible as `error` instead of hidden): npl_movement 14 (BURGAN cons interim Q1/Q2/Q3
'23-'25, EXIM unco recent interim, ODEA 2022Q1, QNBFB 2025Q3), capital 3 (EMLAK CET1 underread 2022Q1, total/RWA
column-swap 2025Q1). Guard tests added for all three checks.

Prior: 2026-06-22 — **NPL/Stage-3 blind spot closed — the matrix stops hiding dropped columns.**
Spotted via the Compare heatmap: EMLAK's NPL ratio was blank for 10 straight quarters (2023Q4→2026Q1) while
its `stages` cells read green `ok`. Root cause was two-layered:
- *Validator blind spot:* `check_stages` **skipped** every Stage-3 check when `stage3` was null, so a silently-
  dropped NPL column still passed (S1+S2=total foots) and the coverage rollup turned "no failures" into `ok`.
  Hardened it to **fail** on the dropped-column signature — S1/S2 present but S3 null — distinguishing it from a
  genuine zero-NPL bank (which stores S3 = 0, not null). Guard tests added. The matrix now shows these as `error`
  instead of green.
- *Extractor gaps (npl_brsa → Stage-3), four distinct causes:* EMLAK 2023Q4+ (a populated FC-only sub-table
  escaped `_is_fc_only_block`, so the template path emitted a tiny FC row and suppressed the correct regex);
  ODEA 2025Q4 ("III. Aşama" header vs "Grup"); VAKIFK 2023Q2 (source text-layer split the provision row);
  BURGAN cons 2022Q1/Q2 (a stray trailing `.`/`,` after the middle "Group IV" numeral failed the whole-page
  header match). All 20 cells (EMLAK 16, ODEA 1, VAKIFK 1, BURGAN 2) now capture a sane Stage-3 (gross=net+prov
  holds); re-extracted via reextract-statement.yml (force, derived-stages rebuild); no-regression verified
  byte-identical. Heatmap NPL-blanks 14 → 3, the 3 remaining all verified not-disclosed (FIBA 2022Q1/2025Q3,
  TSKB 2026Q1 interim). Lesson: the coverage matrix tracks "a present, self-consistent statement", NOT "every
  column populated" — a check that skips on null can't see a column that should have been there.

Prior: 2026-06-22 — **Coverage matrix: ALL non-profile/non-equity cells now 0 missing.** The image-only
tail (27 cells across 11 partitions) was cleared by **OCR transcription** — these statement pages are disclosed,
just scanned, so they're transcribed, never marked N/A:
- Built `scripts/ocr_statement.py` (easyocr CPU; clusters rows by y, aligns numbers to value-column x; col0 =
  current period) + `scripts/load_partitions_batch.py` (pull snapshot once → overlay manual statements for many
  partitions → revalidate each → push + sync + upload once).
- **Every transcribed value is cross-checked against the statement's own arithmetic identities** (OCI I+II=III,
  II=2.1+2.2; cash_flow I=1.1+1.2, V=I+II+III+IV, VII=V+VI; off_balance A=I+II+III, B=IV+V+VI, TOPLAM=A+B) and
  re-read on any mismatch — nothing is stored blind. The identities caught real errors: FIBA 2023Q3 off_balance
  had been read off the prior-period column; ISCTR's scanned image content is offset from the page text-title
  layer; an OCR digit-slip on a CF sub-item. off_balance is stored Total-column-only (tl/fc null; ≥10 rows incl
  sub-items per the lane's present_min_rows).
- Done in parallel by per-partition subagents: FIBA 2022Q1 c/u, 2023Q3 c, 2024Q1 c, 2025Q3 c/u (oci+cash_flow+
  off_balance); ISCTR 2025Q1 c, 2025Q2 u (oci+cash_flow); TFKB 2022Q3 c; ALBRK 2025Q4 c cash_flow; ATBANK
  2025Q4 c off_balance. ALBRK/ATBANK/TFKB turned out to be TEXT pages the locator had missed (ALBRK's English CF
  page header-bleeds "STATEMENT OF CHANGES IN EQUITY"). Loaded cells show as 'manual'.
- *loans_by_sector — ISCTR wrong-table fix (6 annual partitions):* the corpus re-validation surfaced Σ sectors
  ≈ 2× total because ISCTR's English reports carry two same-taxonomy sector tables and the parser grabbed the
  credit-risk-class "Risk Profile by Sectors or Counterparties" matrix (TL/FC/Total cols, no stages) instead of
  the genuine "Major Sectors" Stage-2/Stage-3/ECL table. `_WRONG_TABLE_HINTS` extended to skip "Risk Profile …
  by sectors" (EN+TR); GARAN/AKBNK/YKBNK/VAKBN verified non-regressed.
- Remaining matrix gaps: **profile 389** (deferred to last) and **equity_change 42** (out of scope).

Prior: 2026-06-22 — **Coverage matrix: capital, liquidity, npl_movement, loans_by_sector, stages,
credit_quality all driven to 0 missing.** A lane-by-lane push of real extractor fixes (no skips hiding wrong
data; everything validated, no regressions):
- *capital 47→0:* end-marker gated on a component being read first (ALNTF intro line); fitz wide-table fallback
  with a y-window so values offset from wrapped labels still pair (FIBA); `\s*` start anchor + fitz locator
  fallback + digit-split repair on the fitz value window + a field-merge whitelist {cet1/tier1/rwa/ratios}
  (ANADOLU/TFKB squished interim).
- *liquidity 30→0:* whole-report fallback when the LCR table header is absent (AKTIF prose LCR); Turkish
  İ→i / I→ı folding (TFKB UPPERCASE labels); fitz wide-table + nil-row skip + per-ratio gap-fill; a prose
  leverage fallback anchored on "itibarıyla %…" (older FIBA states leverage only in a sentence).
- *npl_movement 131→0:* plural "Movements of…" + ALBRK label variants; ALNTF opening-less table (start on
  additions, outflows stored as positive magnitudes); TSKB unco "Information on TOTAL non-performing loans";
  ODEA "III./IV./V. Aşama" groups.
- *loans_by_sector 58→0:* bare-number sector strip ("1 Tarım"); non-cash exclusion gated on the cash stage
  columns (ANADOLU); heading variants (ISCTR/SKBNK/EMLAK/ALBRK); "Industry"→mfg_total; GARAN unco split-page.
- *stages + credit_quality:* the residuals were all FIBA Q1/Q3 interim, which (verified) omit the III/IV/V
  NPL-movement AND IFRS-9 stage tables entirely (prose only — FIBA prints them only in Q2/Q4).
Added **data/audit_not_disclosed.json** (+ sync support, statement may be a list) so verified-not-disclosed
cells show as N/A, never to hide a printed-but-unextracted table. Remaining non-equity tail: cash_flow 26,
oci 10, off_balance 8 (each ≈6 are FIBA Q1/Q3 image-only STATEMENT pages — disclosed but scanned — plus a few
scattered per-bank extractor gaps), 3 stray BS/PL, and profile 389 (deferred to last).

Prior: 2026-06-21 — **loans_by_sector 21→0 — coverage matrix now clean except equity_change.** Rewrote
the sector parse to x-coordinate column alignment (`_extract_section_xy`): align each row's numbers to the
Stage 2 / Stage 3 header columns by word x-position, so it reads a gross-Loans column before the stages and
provision/ECL columns after (QNBFB's 5-column table where "3 trailing numbers" grabbed the dash/ECL cols),
recognises "(Second/Third Stage)" + Turkish İkinci/Üçüncü, and `_pick_total` keeps the total that foots when a
page carries two tables (ICBCT). The extractor now keeps whichever parse (aligned vs legacy text) FOOTS better,
so it can't regress a bank the old parser read right (verified on AKBNK/GARAN/HALKB/DENIZ/TSKB). Plus sector
wordings (Hotel/Real-estate-renting/Education/Independent-business, Manufacturing-Industry→production), the
"unconsolidated investments" wrong-table exclusion, and a `\d{1,4}` leading group for the "1466,551" typo.
Re-extracted YKBNK+QNBFB+EXIM+ICBCT+BURGAN+KLNMA; YKBNK interim-unco stale rows cleared. **With this, every
audit lane is 0 except equity_change (340).**

Prior: 2026-06-21 — **capital 26→0, cash_flow 1→0, loans_by_sector 36→21.** *capital:* apply_overrides
now patches `bank_audit_capital`; the 26 §4 mis-extractions were recovered from the capital identities (the
passing ratio checks pin the kept components, so the missing one is exactly the gap) and PDF-confirmed — AT1
dropped→Tier1−CET1, Tier2 dropped/slipped→Total−Tier1, AKTIF total→Tier1+Tier2, ISCTR 2025Q1/Q2 RWA
column-slip→real RWA (2,724,016,639 from the §4 table) + recomputed ratios. *cash_flow:* TSKB 2022Q1 cons
`_CF_SKIP` — PDF read confirms every roman matches the print but the source's V line is a typo (V 5,027,208 ≠
I+II+III+IV 5,011,183; VII foots with the derived V). *loans_by_sector:* YKBNK (22) extracted the WRONG table
(capital/equity rows) — the locator missed "Information ACCORDING TO sectors and counterparties" and
false-matched the risk-profile + investments tables; fixed locator + YKBNK sector wordings, re-extracted
(annual-cons cleared). Remaining 21 are per-bank multi-column structures (QNBFB 5-col dash layout, YKBNK
unco gaps, EXIM/ICBCT/BURGAN/KLNMA) needing x-coordinate column alignment — the lowest-priority lane.
**Only non-equity_change errors left: loans_by_sector 21.**

Prior: 2026-06-21 — **off_balance 17→0 and OCI 19→0 (coverage matrix: those two lanes cleared).**
*off_balance:* curated per-cell overrides (no re-extraction) — TEB's `(III-2)` cross-reference letter-spacing
truncated the III. derivatives TL/FC to junk across 8 quarters (restored from the 3.1+3.2 children); BURGAN/
EMLAK/ISCTR single garbled cells; and ALNTF's cross-ref-annotated rows (`III-a-3,i`) that the pdfplumber
off_balance parser mis-aligns — fitz-read the correct TL/FC/Total for every flagged row off the off_balance
page, Total-cross-checked, 89 rows over 6 partitions. *OCI:* `check_oci` now drops the noisy deep `2.1.x/2.2.x`
sum (net-of-tax rounding + omitted immaterial lines — the cash_flow lesson) and keeps the reliable roman chain
III=I+II + section sums (I=Σ1.x, II=Σ2.x) + OCI.I==P&L-net cross; `apply_overrides` gained `oci`/`oci_replace`
support; EXIM/FIBA/QNBFB had the WRONG statement captured (equity stmt + balance sheet) → full fitz re-read;
KLNMA read II/2.1 from the prior column (correct II = III−I = 33,128); ISCTR 2025Q2 wrong-table + PDF now 404
→ removed (no valid OCI → skipped); ATBANK 2023Q4 `_OCI_SKIP` (source sign typo: prints III `(307.687)` vs
I+II `+307.687`). Five audit lanes now 0 in D1: assets/liabilities aside, **credit_quality, stages,
npl_movement, off_balance, OCI all clear**.

Prior: 2026-06-21 — **npl_movement: PASHA roll-forward ties once outflow columns are magnitudes
(fixes the last 10).** PASHA prints the always-outflow rows in parentheses — `Tahsilat (-) (8.115)` — which the
extractor stores as −8.115, so the validator's `− collections` became `− (−8.115)` = +8.115 (double negative)
and the roll-forward didn't tie (it then failed the gross cross-check too, because PASHA's gross is separately
stale). Fix: `check_npl_movement` now takes `abs()` of the four always-outflow columns (transfers_out,
collections, write_offs, sold) — positive values are unchanged so banks that already tie are unaffected; PASHA
now ties (33.610 + 17 − 19.031 − 8.115 = 6.481 = closing). Sample: 75 pass / **0 fail** / 65 skip, 170 tests
pass. **This closes npl_movement: 126 → 0 across the session (FX row + closing-vs-gross cross-check + HALKB
total-block + PASHA outflow-magnitude).**

Prior: 2026-06-21 — **npl_movement: HALKB reads the correct total closing (fixes 15).** HALKB's English
movement table carries the prior-period close at the TOP under the same "Current period end balance" label as
the closing, so the extractor read it as a closing and skipped the real total block — grabbing a later
loans-by-borrower SUB-category (closing 9,440,946 vs the correct total 16,582,889 = gross). Fix: in
`_extract_from_block`, an English "…period end balance" row with no active block STARTS the block as its
opening. Restricted to the English phrase on purpose — Turkish reports label their opening "Önceki Dönem Sonu
Bakiyesi" (already handled) and reuse a bare "Dönem Sonu Bakiyesi" across many sub-tables (matching that
regressed AKTIF). HALKB now reads 16,582,889/27,051,112/37,919,856 (= gross) → cross-check SKIPs; AKTIF still
passes (3/3), 170 tests pass, sample clean. **Remaining: PASHA (10) — its npl_brsa_GROSS gIV is stuck at
33,610 for 5 quarters (2024Q4→2025Q4), a stale credit_quality value the cross-check correctly surfaces while
the movement varies and ties internally; the root issue is the gross, not the movement — separate fix.**

Prior: 2026-06-21 — **npl_movement: cross-check the closing against npl_brsa_gross instead of trusting
the flow roll-forward (clears faithful TEB/PASHA).** Going one-by-one through the residual, TEB's table turned
out to be FAITHFULLY extracted — its movement closing equals the authoritative npl_brsa_gross exactly
(1,879,803 / 1,475,189 / 976,947) — but the flow roll-forward doesn't tie because the source carries an
unmodeled "Diğer" (other-movements) flow and a Satılan sub-breakdown that doesn't foot to its own total. PASHA
is the same (closing matches gross, flows mis-scaled from a stacked sub-table). The flow roll-forward is simply
unreliable for these banks (the cash_flow lesson again). Changed `check_npl_movement` to take the period-end
`gross_by_group` (from credit_quality, supplied by `revalidate_partition`): when all flow columns are present
and the roll-forward still doesn't tie, SKIP if the closing matches the gross (bottom line correct, residual is
an unmodeled flow) and FAIL only if the closing ALSO disagrees (HALKB reads a loans-by-borrower sub-category,
not the total — a real error). The change is MONOTONIC — it can only turn fails into skips, never create new
failures. 63 validator tests pass. HALKB/KLNMA (genuine closing errors) still flagged — next.

Prior: 2026-06-21 — **npl_movement: map the consolidated "Kur farkı" FX-translation row (fixes DENIZ
+ similar).** The NPL roll-forward (opening + flows = closing) failed for many CONSOLIDATED partitions because
those reports add a currency-translation flow row the solo reports omit, and the extractor's `fx_diff` labels
only matched "Foreign currency differences" / "Yabancı para çevrim farkları" — not the common "Kur farkı" /
"Kur farkları" (DENIZ/TEB). Added those + "Kur değişiminin etkisi" / "Exchange rate differences". DENIZ 2025Q4
cons now ties exactly (gIII Kur farkı 416.936 closed the −416.936 gap; gIV 341.136). Validated across the
sample: 0 FX-involved new-fails (the row is only added where it genuinely exists, so it can't un-tie a bank
that already balanced). 170 tests pass. Remaining npl_movement reds are separate issues (HALKB cons reads a
loans-by-borrower SUB-category not the total — same multi-table class as its npl_brsa; PASHA garbled tiny
closings; TEB gV residual) — to be worked next.

Prior: 2026-06-21 — **Fixed a regression I introduced: FIBA total-column drop broke TEB/ODEA/HSBC/ISCTR
loans_by_stage (stages 9→12).** The earlier FIBA fix dropped a trailing Toplam-total column unconditionally;
that *rescued* previously-rejected rows, and an earlier wrong sub-table then won the dedup over the real §7.2
table (TEB Stage-2 amount fell 26,235,157 → 1,415,068 → coverage >1). My 53-PDF sample didn't include the
regressed banks. Fix: the total-column drop is now OFF by default and runs only as a DOCUMENT-LEVEL fallback in
`extract_from_pdf` — re-scanning with the drop enabled ONLY when the strict pass found no `loans_by_stage`
anywhere (so it can never override a bank that already has a valid table). FIBA still reads (1,008,524 /
629,760) via the fallback; TEB back to (307,188,304 / 26,235,157). The ECL filter relaxation (ICBCT/PASHA/
ATBANK) was NOT the cause and is kept — it only affects tiny-S2 banks and can't produce coverage>1. 170 tests
pass. Lesson: validate extractor changes against the actual failing partitions, not just a convenience sample.

Prior: 2026-06-21 — **Fixed HALKB consolidated NPL (2 cells) + ICBCT 2024Q3 ECL (2 cells).** HALKB
cons NPL gross was stuck at 32,415,173 because its template `gross_label "Current period end balance"` matches
a loans-to-individuals/corporates SUB-category, not total NPL — and HALKB has no explicit total-gross row (only
"Current period (Net)" + "Provisions"). Removed HALKB's `npl_movement` template so the regex path's
gross=provision+net identity computes the correct total (Q4 81,553,857 = 41,218,767 + 40,335,090; Q3
72,347,865). ICBCT 2024Q3 §7.2 is a 4-col [curr-S1, curr-S2, prior-S1, prior-S2] layout; its tiny current S2
ECL ("…Önemli Artış - 55 - 209.830") was skipped by the `_parse_first_nonzero` ≥1000 footnote filter, so the
parser fell through to the prior-period 209.830 → coverage 413. Relaxed the filter to also accept a bare ≥10
non-parenthesised value (footnote refs stay parenthesised); ICBCT S2 ECL now 55 (cov 0.108), and it also
recovers ATBANK 2022Q2's S2 ECL 691 (was dropped). 170 tests pass, 53-PDF sample diff = only those 3 (all
improvements). Session arc on `stages`: 19 → 1. **Last remaining: PASHA 2024Q4 — source PDF URL is dead (cons
URL literally "consolidated", uncons 404s); can't download to verify whether its cov 1.18 is a genuine tiny-S2
over-provision or a mis-extraction. Blocked on data availability, not extraction.**

Prior: 2026-06-21 — **Fixed AKBNK consolidated ECL (3 cells) + FIBA npl100 (1 cell).** AKBNK cons
showed a *negative* Stage-1 ECL (−336,199) because its §7.2 balance table wraps the label across two lines
(`12 Aylık Beklenen Zarar` / `Karşılığı 9.108.092 …`), so the per-line anchor missed it and the extractor fell
to the p82 P&L *charge* table (Stage-1 net is negative). Added a targeted label-unwrap in
`_extract_stage12_ecl_from_page` (re-join `…Zarar` + `Karşılığı …`); cons now reads the real balance
(9.1M/9.2M/12.4M across 2024Q1/Q2/2026Q1), uncons unchanged. FIBA looked 100% NPL because its §7.2 Toplam is
`[S1, S2, Total]` (1,008,524 / 629,760 / **1,638,284**=S1+S2) and `loans_by_stage` counted the Total as another
Yakın sub-column → S2>S1 → table dropped → no Stage-1/2 amounts. Now drops a trailing column equal to S1+Σ(prior
cols); FIBA reads S1=1,008,524 / S2=629,760. 170 tests pass, 53-PDF sample clean. Session arc: `stages` 19→~5.
**Genuinely hard/blocked tail (3 banks, documented not forced):** ICBCT 2024Q3 — §7.2 is a 4-col
[curr-S1,curr-S2,prior-S1,prior-S2] layout the "sum-after-S1" model misreads (per-bank column-model change,
high regression risk); HALKB consolidated — multi-table NPL with no explicit gross row (gross = "Current period
(Net)" 40,335,090 + "Provisions" 41,218,767 = 81,553,857, but a 32.4M sub-table on an earlier page wins the
dedup — ALBRK/QNBFB class); PASHA 2024Q4 — source PDF URL is dead (cons URL literally "consolidated", uncons
404), can't download to fix, and cov 1.18 may be a genuine tiny-S2 over-provision.

Prior: 2026-06-21 — **Fixed TEB `loans_by_stage` wrong-table grab (6 `stages` cells).** TEB's
Stage-1 amount equalled its Stage-2 amount (e.g. 2,124,190 == 2,124,190) → coverage >1. Cause: the
`loans_by_stage` sanity gate allowed `stage1 == stage2`, so a total-first AGING-analysis Toplam row on an
earlier page (TEB p80 `Toplam 2,124,190 946,654 1,177,536`, where 2,124,190 = 946,654+1,177,536) passed and,
being earlier, won the dedup over the real §7.2 table on p100. A real Stage-1 (standard) portfolio is always
≫ Stage-2 (watch), never equal — tightened the gate to STRICT `stage1 > stage2`. TEB now reads the correct
S1=302,536,751 / S2=25,869,678 (uncons). 170 tests pass; sample re-checked (all real tables keep S1>S2, no
regressions). Remaining `stages` reds after this + re-extract are harder/ambiguous, left documented: AKBNK
consolidated Stage-1 ECL prints `(336.199)` negative and the stages FOOT to total (faithful to PDF, but the
unconsolidated is +8.7M → likely a net-change/wrong cons table); ICBCT 2024Q3 garbage S2 amount (image-heavy);
HALKB consolidated multi-table NPL (ALBRK/QNBFB class); PASHA/FIBA singletons.

Prior: 2026-06-21 — **Fixed `_merge_split_digits` over-merge (ALNTF negative-NPL + ICBCT garble).**
While checking the `stages` matrix cells, found ALNTF 2023Q4 uncons had a *negative* NPL gross (−729,420):
the extractor read the net row `13 11,390 20,218` as `131 / 1,390` because `_merge_split_digits` fused the
two separate Group-III/IV values `13 11,390` → `1311,390` (an invalid 4-digit leading group). With net wrong,
the closing balance stopped footing `gross=prov+net`, the identity override skipped, and largest-magnitude
grabbed the `Tahsilat (−)` collections row. Fix: only merge a split digit when the combined leading group
stays ≤3 digits — a true split (`3 34,098`→`334,098`) always does, fusing two values overflows. Now ALNTF
reads gross 398,935 / net 31,621 (foots), and it ALSO fixes ICBCT 2023Q2 (provision `25 127,385`→garbled
`251/27,385` → correct `25/127,385`) and likely other banks fleet-wide. 170 tests pass; sample re-checked
(TFKB true-splits still merge, no regressions). NOT applied to stored data until a re-extract. Separately
confirmed the other `stages` reds are PRE-EXISTING, not from the prior re-extract (HALKB consolidated picks
the wrong one of several III/IV/V sub-tables — same hard multi-table class as ALBRK/QNBFB, left documented).

Prior: 2026-06-21 — **credit_quality extractor is now fitz-only (~30× faster) + fixed a CI regression
I'd missed.** Replaced pdfplumber with fitz (PyMuPDF) in `credit_quality.py`: `extract_from_pdf` opens the PDF
itself via fitz and reconstructs each row by y-clustering `get_text("words")` at 5.5px (`_fitz_clustered_lines`,
which subsumes the old column-split coordinate fallback), feeding the SAME pdfplumber-tuned parsers unchanged.
Per-PDF credit-quality extraction drops from ~16s to ~0.5–1.3s; the `extract(only={credit_quality})` re-extract
path is ~0.8s/PDF (pdfplumber.open was 0.1s anyway). Validated fitz vs pdfplumber on 40 PDFs: identical on the
primary sections for ~all banks, and fitz **recovers data pdfplumber couldn't** — most importantly it reads
**TFKB's tables** I'd wrongly called "image-only" (loans_ecl garbage `1475` → correct `501475`), so TFKB will
extract on re-extract, not stay flagged. Divergences are confined to a secondary section (`loans_ecl_brsa`)
and genuinely hard multi-table layouts (ALBRK/QNBFB), where neither engine is clearly right — not regressions.
Also fixed **CI red since 1e099c3**: the `stage_columns_are_brsa_groups` guard test imports `credit_quality`
(PDF engine, absent from CI's minimal deps); added `pytest.importorskip("pdfplumber"/"fitz")` per the existing
pattern. Code stored unchanged until a re-extract. 170 tests pass.

Prior: 2026-06-21 — **Fixed the NPL gross-row extractor (the İntikal mis-grab); rejected a noisy
validator after verifying it would false-positive.** Root cause of DENIZ 2025Q4: `_extract_npl_brsa_from_page`
collects gross candidates above the "Karşılık (-)" provision row and picks the **largest magnitude** (a
heuristic for ISCTR's customer-segment sub-rows). In DenizBank's NPL *movement* table the "Dönem İçinde
İntikal" inflow (63.4bn) outweighs the "Dönem Sonu Bakiyesi" closing balance (55.0bn), so largest-magnitude
grabbed the flow. Fix: after computing net, **prefer the gross candidate that foots `gross = provision + net`
within 1%** (the closing balance is the only row that does; a movement row doesn't) and fall back to
largest-magnitude otherwise. Verified on the PDFs: DENIZ now extracts the 55.0bn closing (was 63.4bn);
**ISCTR is byte-identical** (no regression on the sub-row case). I then drafted a `gross = provision + net`
validator to catch the mis-grab corpus-wide, measured it, and **rejected it** — it flags ~200 partitions
including AKBNK 2024Q4 whose gross is *correct* (it sits 4% above prov+net because BRSA provision/net bundle
general/collateral reserves; the identity is genuinely noisy, exactly why it was removed historically). No
reliable corpus-wide NPL-gross check exists; the mis-grab is prevented at extraction and cross-checked (where
`loans_amounts` exists) by `cq_cross_amounts`. Code-only — DB unchanged until a re-extract.

Prior: 2026-06-21 — **Audited my own curated skips: un-skipped the ones hiding wrong/unverified data.**
Prompted by the DENIZ mis-diagnosis, re-examined every validator skip added this session against one rule —
a skip is justified ONLY when the data is verified faithful to the PDF and the SOURCE itself doesn't foot,
NEVER to hide a wrong/garbled/unverified extraction. Removed: **`_CQ_SKIP` (TFKB ×3)** — its `loans_ecl` is
genuinely garbled (cross-contaminated from adjacent ECL tables), so it must stay FLAGGED; and **`_CF_SKIP`
TSKB 2022Q1** — its V doesn't reconcile and the IR host was unreachable, so the skip rested on an unverified
reconstruction. Kept (re-verified against the PDF, every cell matches, source genuinely doesn't foot):
**`_CF_SKIP` ALBRK 2023Q4** (V 18.477.034 vs ΣI..IV 18.377.034, V+VI=VII holds) and **`_PL_SKIP` ICBCT
2023Q2** (VIII 358 above ΣIII..VII). Net: credit_quality flags 5 (DENIZ ×2 extraction bug + TFKB ×3 garbled),
cash_flow flags TSKB. Matrix shows more errors — all genuine; nothing wrong is hidden.

Prior: 2026-06-21 — **CORRECTION: DENIZ 2025Q4 `npl_brsa_gross` is a real extraction bug, not a
"definitional gap" — reverted the tolerance I wrongly widened.** Earlier today I attributed DENIZ 2025Q4's
`cq_cross_amounts` failure to IFRS-stage-3 ≠ BRSA-NPL and widened the band 0.5%→1.5%. That was wrong: the
stored `npl_brsa_gross` (III 25,450,423 / IV 17,601,970 / V 18,396,348 = 61.4bn) is the **"Dönem İçinde
İntikal (+)"** row of the NPL *movement* table — period inflows, a FLOW — not the **"Dönem Sonu Bakiyesi"**
closing balance (15,094,901 / 17,730,782 / 19,458,398 = **52,284,081**), which equals the IFRS Stage-3 figure
exactly. So there is no gap; the extractor grabbed the wrong row on this long roll-forward layout (provision
and net rows are correct). Reverted the band to 0.5% so the bug stays flagged. `npl_brsa_gross` for DENIZ
2025Q4 (cons + uncons) is overstated and feeds an overstated NPL-gross metric; the derived `bank_audit_stages`
Stage-3 is unaffected (it prefers `loans_amounts.S3`). OPEN: fix the extractor's gross-row selection (anchor
the closing-balance row immediately above provision, not an earlier movement row) + re-extract the affected
credit_quality. Clean detector (`gross ≈ loans_amounts.S3`) flags only these 2; broader scope unverified.

Prior: 2026-06-21 — **Credit-quality column-semantics trap documented + test-locked.** The
`bank_audit_credit_quality` table reuses three positional columns `stage1/2/3_amount` whose meaning is
*section-dependent*: for most sections they are IFRS-9 Stage 1/2/3, but for the **`npl_brsa_*` sections they
are BRSA NPL groups III/IV/V** (substandard/doubtful/loss) — all sub-buckets of IFRS Stage 3, so reading
`npl_brsa_gross.stage1_amount` as "Stage 1" would be wrong. Audited every consumer and confirmed **none**
does: `build_bank_audit_stages` takes Stage 3 from `npl_brsa_gross.total_amount`, `compute_bank_metrics`
reads the split but labels it `npl_group3/4/5`, the validator checks III+IV+V=total, and the web reads only
the derived `bank_audit_stages`. Made the convention explicit and durable rather than renaming the shared
columns (which would mislabel the loan sections): added `NPL_GROUP_SECTIONS` + `stage_columns_are_brsa_groups()`
in `credit_quality.py`, a schema comment, a `compute_bank_metrics` pointer, and two guard tests that lock
"derived Stage-3 = npl_brsa TOTAL, never Group III". Docs/tests only — no data or schema change.

Prior: 2026-06-21 — **Credit-quality coverage matrix: 5 → 0 errors.** Two distinct causes.
**DENizBank 2025Q4 (cons + uncons), `cq_cross_amounts`**: the check `loans_amounts.total ≈ loans_by_stage(S1+S2)
+ npl_brsa_gross(S3)` is a CROSS-FRAMEWORK approximation — it assumes IFRS-9 stage-3 loans ≈ BRSA NPL gross,
but those legitimately diverge (DENIZ's stage-3 55.0bn vs NPL 63.4bn, both verified in the PDF, a 0.7–0.9%
gap; every other partition ≤0.15%). Widened the band 0.5% → 1.5% (a mis-extracted table is off by far more,
so only definitional false reds drop). **TFKB 2023Q4 + 2025Q4 (cons + uncons), `cq_section_total`**: the
`loans_ecl` stage breakdown is garbled — the IFRS-9 footnote is image-heavy and the extractor
cross-contaminated it from adjacent ECL tables (stored S2 = `loans_ecl_brsa` S2, S3 = `npl_brsa_provision`
total; the real movement-table total is 2.917bn, not the stored 3.349bn). Recovering it needs manual
transcription + credit_quality override support (disproportionate for a small-bank footnote), so added a
documented `_CQ_SKIP` to revisit on re-extract. Verified live: `credit_quality` 5 → 0; total matrix 584 → 579.

Prior: 2026-06-21 — **Cash-flow coverage matrix: 135 → 0 errors (validator hardened).** All 135
`cash_flow` failures were the generic `hierarchy_sum` (parent = Σ direct children) check, which is the
wrong tool for cash flow: the period-header line ("1 OCAK – 31 MART") is captured as a stray hierarchy
"1" that collides with roman "I." at path (1,); banks variously omit or relabel the 1.1/1.2 subtotal rows
(DenizBank prints 1.1 on the "A." section header); and the sign convention isn't label-derivable (DENIZ
stores "Ödenen Faizler (-)" as a positive magnitude but "Personele … Yapılan Nakit" — also a payment — as
a positive with no "(-)", so neither raw nor contra summing foots the section). Rewrote `check_cash_flow`
to the **roman bottom-line chain only** — `V = I+II+III+IV` and `VII = V+VI` — which is sign-agnostic, holds
for every bank, and still surfaces a wrong *section total* (it breaks V). Corpus test: **133 cleared, 0
regressions**, leaving 2 genuine roman-chain breaks now in a curated `_CF_SKIP` (mirrors `_PL_SKIP`):
**ALBRK 2023Q4 cons** (the PDF itself prints V 100.000 above I+II+III+IV — every cell matches the PDF, no
single-cell fix reconciles V *and* VII=V+VI) and **TSKB 2022Q1 cons** (V is 16.025 above ΣI..IV; the
reconciling V=5.011.183 is over-determined but the TSKB host was unreachable to confirm typo-vs-misread —
recover the value once readable). Verified live: `cash_flow` matrix errors 135 → 0; total matrix errors
719 → 584 (remaining are equity_change 340, npl_movement 126, …). **Spine-revert root-cause fix**: the
coverage matrix reads the `bank_audit_coverage` rollup, derived from `bank_audit_validation` — which is a
*cache* of (validator code × data), carried frozen in the R2 snapshot. Any process that rebuilt the rollup
from a pulled snapshot's stored verdicts resurrected failures already fixed by a validator-code change; the
`acquire-audit` cron did exactly that and snapped cash_flow back to 135 a few hours after the fix. Rather
than make every caller remember to revalidate first, `sync_audit_expected.py` now **recomputes validation
from the stored data rows with the current code before building the spine** (extracted
`revalidate_audit_db.revalidate_all`) and pushes the fresh `bank_audit_validation` alongside the coverage
tables — so the matrix is correct *by construction* for every caller (acquire-audit, reextract,
apply_overrides, manual). Proven with a fault-injection test (corrupt the stored verdicts → sync self-heals
the spine to 0). Removed the now-redundant per-workflow revalidate steps.

Prior: 2026-06-21 — **P&L coverage matrix now 0 errors: the last 2 resolved.** Closed the two
`profit_loss` failures previously left flagged. **QNBFB 2023Q1 uncons was recoverable after all**: the
period net profit `6.632.553` had been misplaced into the XX (discontinued-income) row while XIX held
garbage `(4.678.663)` and XXV was blank — the **statement of changes in equity** (`period_net_profit_loss`
on the Total-Comprehensive-Income row, reconciling 6.632.553 − OCI 1.764.044 = TCI 4.868.509) gave the
authoritative net, confirming no discontinued ops and that XIX = XVII+|XVIII| (the tax is a benefit). Fixed
with 3 `profit_loss` overrides (XIX `6.632.553`, XX `0`, XXV `6.632.553`); the prior period shows the same
misplacement, corroborating. **ICBCT 2023Q2 cons is a genuine immaterial source defect** (printed VIII is
358 / 0.013% above the sum of its individually-correct components; the bank's chain foots from VIII on, so
no cell is wrong) — added a curated `_PL_SKIP` exception in `revalidate_audit_db.py` (mirrors the existing
`_CAP_SKIP`), keeping the data faithful to the PDF while suppressing the spurious red cell. Verified live:
`profit_loss` matrix errors **2→0** (core statements assets/liabilities/P&L all clean); the remaining 719
errors are all non-core footnote statements (equity_change 340, cash_flow 135, npl_movement 126, …).

Prior: 2026-06-21 — **P&L coverage-matrix errors: 8 of 10 fixed via overrides; 2 are genuine
source defects.** All 10 `profit_loss` failures were the `pl_chain` roman-identity check. Triaged each
against its PDF: **8 partitions / 10 cells** were recoverable single-cell extraction artifacts, fixed
with `profit_loss` overrides (chain-forced + PDF-verified): **AKTIF 2023Q3 & 2025Q2** dividend row V
(extractor grabbed the 2nd period column — `325→3.194`, `661→1.015` — the real value had leaked into
the label); **KUVEYT 2022Q3** row X (dipnot `5.4.7` leaked as `7` → `532.730`); **ODEA 2022Q4 &
2023Q4** row XXIV (source copy-down artifact: prints net profit in XXIV though discontinued XX–XXIII
all nil → `0`); **TSKB 2025Q3** XIX (`2.372.570→9.285.218`, forced by XVII−XVIII and = the
net-vs-equity-verified XXV); **YKBNK 2022Q2 & 2023Q4** XVII/XVIII (current-period cells garbled, prior
column leaked into label → `24.519.994`/`5.338.991`, `85.028.901`/`17.018.737`). Verified live:
P&L failures **10→2**. The remaining two are **genuine source inconsistencies** no single-cell fix can
reconcile, so they stay flagged: **ICBCT 2023Q2** (printed VIII is 358 above the sum of its
individually-correct components — moving it just relocates the gap to XIII) and **QNBFB 2023Q1**
(printed XIX `(4.678.663)` doesn't reconcile with XVII±XVIII `3.084.793`, and the discontinued-ops
section is internally broken). **Also closed a stale-matrix gap**: the `/admin` coverage matrix reads
per-cell status from the `bank_audit_coverage` rollup (a roll-up of `bank_audit_validation` rebuilt
only by `sync_audit_expected.py` in the cron), which `apply_overrides.py` never refreshed — so an
override cleared the validation failure but the matrix kept the stale `error` until the next cron.
`apply_overrides.py` now rebuilds + pushes the coverage spine after its table push (overridden cells
become `manual`/`ok` immediately). Ran it for the live fix: P&L matrix errors **10→2**, and the
KUVEYT off-balance cell finally flips error→manual.

Prior: 2026-06-20 — **KUVEYT off-balance B-row fix + apply_overrides D1-wipe footgun guarded.**
KUVEYT 2025Q1 unconsolidated **off-balance** showed red in the coverage matrix: the
`B. EMANET VE REHİNLİ KIYMETLER (IV+V+VI)` subtotal row was column-shifted (a spurious
`1.147.624.728` in the TL slot pushed TP→FC and YP→Total, dropping the printed Total + label) so
`TL+FC≠Total` failed `validate_off_balance`. The data was otherwise fully present and correct
(grand total `12.244.706.334` and every section I–VI footed). Fixed with the **first off_balance
entry** in `data/audit_overrides.json` (TP `4.727.468.981` / YP `6.748.778.307` / Total
`11.476.247.288`, verified against the PDF + grand-total−A). Applying it exposed two latent
`scripts/apply_overrides.py` bugs the BS-only overrides never hit: (1) `_revalidate_partition`
recomputed only assets/liabilities/cross, but `upsert_validation` deletes the whole partition's
validation rows first — so it silently dropped off_balance/P&L/OCI/… and the override never cleared
its own failure; now delegates to `revalidate_audit_db.revalidate_partition` (all statements,
cron-identical). (2) The broad D1 partition-clear spans all 14 audit tables, but the narrow
`--hours 1` re-push only ships tables it timestamp-bumped — the self-`extracted_at` tables
(capital/liquidity/stages/credit_quality/loans_by_sector/npl_movement/profile, whose §4 data
predates the window) were **deleted from D1 and not restored**; now their `extracted_at` is bumped
per touched partition. Verified live: off_balance `66/0` green, capital/liquidity/stages intact.

Prior: 2026-06-19 — **/valuation tab: scenario projections & intrinsic valuation.** New
standalone top-level tab (no changes to `/banks` or `/cross-bank`) that values the listed banks with
the equity-side models appropriate for banks (DCF/FCF is wrong — bank leverage is regulated):
**residual income** `V₀ = B₀ + Σ PV[(ROEₜ − COE)·Bₜ₋₁] + PV(terminal)` with a linear ROE fade and a
Gordon (ω=0) or Ohlson-decay (ω>0) terminal, a **two-stage DDM**, and the **justified P/B** identity
`(ROE − g)/(COE − g)`. Cost of equity is CAPM, **nominal TRY**: `rf + β·ERP + CRP`, with β from weekly
bank-vs-XU100 returns (`bist_prices`, ≥30 obs else a sector-default 1.0) and rf a CBRT funding-rate
proxy (`evds_series` TP.APIFON4). All maths live in a pure, unit-tested module
(`web/app/lib/valuation.ts`, 19 vitest cases) so the page **recomputes live in the browser** as the
user edits sliders — Base/Bull/Bear presets seed editable assumptions. The server pre-fetches a compact
per-bank "seed" (`web/app/lib/valuation-data.ts`: book + TTM ROE on the heatmap basis, market, β, rf)
for all listed banks at once, so the bank selector swaps with zero round-trips. Also a cross-bank
**P/B-vs-ROE regression scatter** + justified-vs-actual ranking (client-side, under a scenario toggle).
Prominent TAS-29 hyperinflation caveat: the model is nominal; the durable driver is the real (ROE−COE)
spread. Reuses `bankFundamentals`/`bistValuation`/`bist_prices` read-only. Nav gains one "Valuation"
entry; existing tabs untouched.

Prior: 2026-06-15 — **audit validators hardened + NPL=100% fixed end-to-end (43/45);
coverage-matrix wipe footgun guarded.** Audited every §4/§5 validator (a green check ≠ correct
data): `check_capital` rewritten to **reconcile the table** — composition `Tier1=CET1+AT1`,
`Total=Tier1+Tier2` + sub-ratios `CET1/Tier1/CAR = component÷RWA` — surfacing **26** real
AT1/Tier2-dropped / total↔Tier2 / RWA↔total column-slip mis-extractions the old orderings-only
check passed silently. `check_stages` NPL=100% fingerprint now fires on **NULL** stage1/2 (the
actual broken shape, which had been scoring green) — surfacing **45** partitions. Liquidity &
off-balance get **within-bank time-series outlier** checks in `check_audit_quality.py`
(`_liquidity_outliers` ≥8×, covers `lcr_fc`; `_off_balance_consistency` TOTAL/Σromans) since their
per-partition validators are band-only / horizontal-only. Then **root-caused and fixed the
NPL=100% data**: `credit_quality` missed the §7.2 Stage-1/2 `loans_by_stage` table on
column-split / no-space layouts (İşbank EN coordinate-rebuild; ANADOLU wrapped header → anchor on
the Stage-2 header; TSKB ~4px label/number y-offset → 5.5px cluster). `credit_quality` wired into
`reextract_statement.py` (rebuilds the **derived** `bank_audit_stages` + a `force` input for
derived-table defects); CI run repaired **43/45** (npl100 45→2; FIBA + TFKB image-only remain).
**Infra:** `push_to_d1` now refuses to emit a wiping `DELETE` for a full-rebuild spine table when
the local copy is empty — the daily news/EVDS push from `bddk_data.db` (empty spine) had been
blanking the /admin coverage matrix; restored to 13,650 cells. **Web:** coverage matrix bank/date
filters + cons/unco "both" mode; removed the redundant Audit-extraction & Structural-validation
admin panels (folded into the matrix); per-bank ⚠ scoped to the displayed statement; per-bank
default → **Quarterly**, controls moved above the table, `scroll={false}`; pl-sankey reads the real
roman subtotal (ZIRAAT/BURGAN stray "=1" fragment). Docs + `ARCHITECTURE.md` refreshed (the
two-DB / spine-guard footgun); `data/albaraka_*` gitignored, `prof_test.html` removed.

Prior: 2026-06-14 — **loans-by-sector fixed: 99 → 135 pass.** The sector breakdown
is an **annual-only disclosure** for most banks (absent from interim reports — confirmed: FIBA
2026Q1 has no sector heading on any page, both engines; every interim quarter is ~all-empty in
D1). So "99/975" was misleading — the real target is the ~310 Q4 partitions; the ~665 interim
empties are genuine. The Q4 fail bug (e.g. FIBA 2025Q4): an all-nil sub-sector row
("Balıkçılık -- -- --") has no DIGITS, so `_merge_wrapped_labels` treated it as a label-head and
merged it with the next line ("Sanayi 787.928…" = the manufacturing TOTAL), giving fishery the
wrong sector's value → Σ ≠ total → fail (and wrong data). Fixes: don't merge a line that already
matches the 3-value pattern; accept `--` runs as nil; scan+parse with fitz (commit `5f49eee`).
Shipped the 4 Q4 quarters (interim has no table to re-extract): each now ~33–35/58. 99 → **135**
pass, no pass→fail regressions. Remaining Q4 fails (~5/quarter) are per-bank layout/disclosure.
`loans_by_sector` wired into `reextract_statement.py` (5th lane).

Prior: 2026-06-14 — **NPL-movement extraction fixed fleet-wide: 195 → 515 / 974 pass.** NPL movement (`bank_audit_npl_movement`, regex footnote extractor) was
195/974. A 2025Q4-vs-2026Q1 diagnostic found three GENERIC bugs (not per-bank work): (1)
`skip_pages=60` hid the table in shorter interim reports (FIBA 2026Q1 at p56 < 60) — added a
low-floor (25) retry that only runs when the deep pass finds nothing (strict superset); (2)
`_THREE_NUMS_TAIL`/`_parse_amount` rejected `--` (double-dash nil) — a trailing `--` dropped the
whole `transfers_out` row → NULL column → validator skipped an otherwise-balancing roll-forward;
(3) **`check_npl_movement` rewritten**: it blanket-skipped on NULL write_offs/sold/transfers_out,
but many banks simply OMIT a genuinely-zero row (KUVEYT has no write-offs) — now treats NULL flow
columns as 0 and PASSES only when the roll-forward TIES (a missed NON-zero column won't tie → stays
SKIP; never a false pass/fail). Two-quarter D1: 2025Q4 17→32, 2026Q1 11→32; no pass→fail regressions
(one skip→fail, DENIZ, is a real non-reconciling roll-forward surfaced). npl_movement wired into
`reextract_statement.py`; commits `3d23513`/`ef30db3`. **Also moved the lane to FITZ** — it had been
scanning every page with pdfplumber's `extract_text` (~17× slower; an all-periods run was ~80 min and
risked the 120-min timeout). Now scans+parses with fitz like the statement locators (verified
strictly ≥ pdfplumber across 23 local PDFs — even recovers ISCTR/TFKB rows pdfplumber drops); an
all-periods re-extract is now ~6 min. **All periods re-extracted (only_failing): 195 → 515 / 974
pass.** Remaining tail (no generic fix reaches it): 126 genuine non-reconciling roll-forwards
(TEB/KLNMA/PASHA/HALKB…) + 334 empty/skip = image-only stubs (ALBRK/ALNTF/EXIM/ODEA/TSKB, like OCI/CF)
+ has-rows-but-don't-tie column skips (per-bank Phase-2 taxonomy, deferred).

Prior: 2026-06-14 — **Engine strategy is now per-statement: fitz-only for OCI +
cash flow, multi-engine kept for equity.** Measured that the multi-engine model
(read a page with pdfplumber AND fitz) costs a full PDF re-open (~225 ms/page, ~60× the
fitz-only cost) + the poison-PDF hang risk. It only earns that on EQUITY — pdfplumber's
x-clustering uniquely separates the wide interleaved-footnote banks (GARAN/AKBNK → 0 rows
fitz-only). On OCI + cash flow (narrow tables) pdfplumber adds **zero** accuracy: verified
via `--force` re-extract on 2026 — OCI fitz-only **17/19 == multi-engine** (only ALBRK
fails, under both engines), CF fitz-only **15/23** with the 8 fails pre-existing
dropped-sub-row banks (FIBA/KUVEYT/SKBNK/TEB) AND **AKBNK recovered from empty**. So OCI
(`oci.py`) drops its pdfplumber candidates (keeps the validation-guided n-template select;
pdfplumber only as a no-fitz fallback) and the CF block (`extractor.py`) parses with fitz,
falling back to the both-engines parser only if fitz yields 0 rows. `reextract_statement.py`
gains a `cash_flow` lane (commit `9884b40`). **Re-extracted ALL periods fleet-wide
(2022Q1→2026Q1): OCI 62 → 881 / 975 pass; cash flow 802 → 813 / 975.** OCI's jump is because
~94% were broken across all years (same n_cols bug); CF moved little — already healthy, the +11
is recovered stale empties, its 135 fails are the dropped-sub-row tail. Also fixed `--only-failing`
(commit `5b51d96`): now means NOT-passing (`checks_failed>0 OR checks_passed=0`) so it catches the
stale empties (was failed-only, which skipped them) → a fleet re-extract downloads only the bad
partitions (CF: 173 not 975); workflow defaults it true. Remaining tail — OCI 78 / CF 135 fails +
~16/27 empties — is the dropped-sub-row issue (ALBRK OCI 2.2.2 / the CF banks' 2.2 — shared
`_parse_rows`, engine-independent) plus image-only/no-PDF partitions.

Prior: 2026-06-14 — **OCI ("Diğer Kapsamlı Gelir") extraction fixed with the
validation-guided approach.** OCI was barely extracted (53 of 55 2026 partitions had
ZERO rows): the P&L-tuned column detector reads a 2-column interim OCI page as 4
columns, so the shared `_parse_page` returned 0 / garbage rows. New
`src/audit_reports/oci.py` mirrors the equity "new approach" — read the located OCI
page with pdfplumber + fitz at n∈{detected,2,4} and keep the reconstruction whose
**roman chain validates** (III = I + II) rather than the most-rows one. n=2 wins for
interim; multi-engine recovers banks one engine fragments (TEB needs fitz). Sample of
14 (empties + partials): **12/14 now pass `check_oci`, up from ~0** (the locator was
already fine post-fitz-changes — the DB's "empties" were stale). Strictly ADDITIVE:
never touches the frozen `_parse_page`/`_detect_pl_ncols`; the `extract()` call-site
swap is isolated to the OCI block (BS/P&L/equity/CF byte-unchanged). `reextract_statement.py`
gains an `oci` lane; new `.github/workflows/reextract-statement.yml` (workflow_dispatch)
ships it (statement=oci, periods=2026Q1, only_failing OFF — empties are
`checks_failed=0`/skipped, so `--only-failing` would miss them; the non-destructive
guard still skips passing). Commits `c87afec`, `a7199c4`. **Shipped to D1+R2 (run
27500669011): 55 OCI partitions → 52 pass, was ~1.** Tail of 3: ALBRK cons+uncons
(chain validates but drops the wrapped sub-row 2.2.2 → hierarchy sub-tree short) and
TSKB uncons (P&L page is image-only → `pl=None` → no OCI page → empty; genuine
OCR/manual gap). OPEN: those 3, and extend OCI to pre-2026 periods.

Prior: 2026-06-14 — **re-extraction is now NON-DESTRUCTIVE: it can never
overwrite correct data.** `loader.upsert_report` skips writing any statement whose
stored data already PASSES validation (`bank_audit_validation`: `checks_failed=0 &
checks_passed>0`) — assets+liabilities protected as a pair (they cross-check),
every other statement per-statement; failing/missing statements are still re-extracted.
So a plain re-run, a `--force` re-extract, OR a full backfill can only *improve* the
DB, never regress a validated partition. Escape hatch: `force=True`
(`sync_audit_reports.py --force-overwrite`, `reextract_statement.py --force`). Bonus —
`upsert_report` now records validation by **revalidating from the STORED rows**
(`revalidate_partition`, all 14 statement types) instead of the in-memory report
(which covered only 8), so the recorded verdict always matches what's in the DB.
Regression test `tests/test_upsert_guard.py`; touched `loader.py`, `validator.py`
(`statement_passes`), `reextract_statement.py`, `sync_audit_reports.py`. Separately,
re-pushed the `/admin` coverage matrix: the D1 spine tables
(`bank_audit_expected`/`_statement_types`/`_coverage`) had silently gone to 0 again
(a `sync_audit_expected.py --push` D1 write that didn't land — the full-rebuild
clears-then-inserts and prints "done" regardless), now 975/14/13650 + R2 refreshed.

Prior: 2026-06-14 — **equity_change 2025/26 hardened (fails 205 → 79) +
self-validating fast iterate loop; committed to fitz.** (1) A few BRSA PDFs (e.g.
VAKBN 2025Q4: 159 pages, 273 `/ObjStm`) made pdfplumber's page-tree resolution hang
~2 min — the equity re-extract wedged on it. Locators now take page COUNT + text from
**fitz** (30 ms vs 2 min); `extract()` shuts the stream instead of `pdf.close()` (which
re-enumerates pages). VAKBN equity-only: **124 s hang → 0.7 s.** (2) Equity parse keeps
the reconstruction whose **column chain VALIDATES** among pdfplumber + 2 fitz engines
(validation-guided, not max-rows), with a both-template (14/16) retry gated to failing
pages. (3) `n_cols` detected from pdfplumber text (fitz over-counts → AKBNK/BURGAN uncons
1→17 rows). (4) mid-page split closing must follow the table body (fixed VAKBN current↔prior
flip). Commits `4177a52`, `6f6c37c`, `5f85616`. **Self-validating loop:**
`reextract_statement.py` validates each partition INLINE (factored `revalidate_partition`),
prints live `[vFAIL]`, pushes `bank_audit_validation`; new `--only-failing` re-extracts ONLY
the failing set → edit→measure dropped ~10 min → ~2 min. **2025/26 equity: 206/285 clean
(shipped D1+R2), 79 flagged** as a per-bank follow-up. OCR/table-tool exploration done (OCR
*does* recover the corrupted text — letter-spacing/numbers clean — but feeding our column
parser needs a grid-reconstruction layer; `pdfplumber.extract_tables` ~4 min/page) →
**committed to fitz** (already primary: fitz locators + 2 of 3 equity candidates; pdfplumber
stays a thin fallback for interleaved-footnote banks GARAN/AKBNK + BS/P&L). The 79 split
into corrupted-text (OCR), clean-but-mis-gridded (grid), and genuine gaps (HSBC, BS-side, no
tool fixes); `scripts/_eq_failreport.py` lists them.

**Prior: 2026-06-13 — equity/CF deep-fixed + full fleet re-extracted +
coverage matrix restored.** Post-backfill diagnosis found the earlier "two bug"
fix was a band-aid; the real root causes were: (1) the equity-page **locator
gated on a fragile title anchor** → missed ODEA (image-only title) / Ziraat
("ÖZKAYNAKLAR DEĞİŞİM") — now detects by the wide-table fingerprint (≥3 lines
≥10 tokens); (2) **cash flow used the P&L column detector** → misread annual CF
date-headers as 4 cols → 0 CF rows fleet-wide — now pinned to 2 cols; (3) mid-page
split missed TEB (no closing row) — added roman-restart split; (4) DENIZ `--`
double-dash zeros + EMLAK 15→16 col mis-clamp (commits 7322fb3, c62057b). Whole
fleet (31 banks, 975 PDFs) re-extracted **sequentially** (never concurrent — that
races the R2 snapshot), 11 manual image-only partitions restored + 25 overrides
re-applied, revalidated, pushed, snapshot uploaded. Result: **CF 0 contamination
fleet-wide** (was 14 banks), CF 839/975 pass; DENIZ 0→1152 / EMLAK 0→1085 equity
rows; **coverage matrix RESTORED** (D1 spine tables had been 0 rows — sync had never
run post-schema-work). OPEN follow-ups (non-core): equity_change **vertical-chain**
~732 fails (PRE-EXISTING; validated `_try_fit` n−1-token insertion fix recovers most
banks but GARAN-class closing-row issue remains; needs a re-extract to apply);
136 CF cf_chain fails; FIBA 2023Q3 cons manual-P&L transcription typo (unpushed).
**Prior: 2026-06-12 — cash flow + equity-change extractors added**:
14 statement types in the registry (2 new: `cash_flow` sort_order=38,
`equity_change` sort_order=36). Both `is_core=False` with structural validators
(CF roman chain V=I+II+III+IV / VII=V+VI; equity row-sum + col-chain + OCI cross
+ BS equity cross).
**Prior state (2026-06-12):** audit validator fleet complete across 12 types;
975 partitions revalidated; coverage matrix 11 700 cells: 8 696 ok / 42 manual /
225 error / 2 737 missing.
