# Changelog

Dated history of pipeline and dashboard changes, newest first. For the
current state of the system see [PROJECT_STATE.md](PROJECT_STATE.md).

Last verified: 2026-06-19 — **/valuation tab: scenario projections & intrinsic valuation.** New
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
matches the 3-value pattern; accept `--` runs as nil; scan+parse with fitz (commit `bda5c2a`).
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
`reextract_statement.py`; commits `ac439fd`/`3f56200`. **Also moved the lane to FITZ** — it had been
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
gains a `cash_flow` lane (commit `c83eaaa`). **Re-extracted ALL periods fleet-wide
(2022Q1→2026Q1): OCI 62 → 881 / 975 pass; cash flow 802 → 813 / 975.** OCI's jump is because
~94% were broken across all years (same n_cols bug); CF moved little — already healthy, the +11
is recovered stale empties, its 135 fails are the dropped-sub-row tail. Also fixed `--only-failing`
(commit `3d028b0`): now means NOT-passing (`checks_failed>0 OR checks_passed=0`) so it catches the
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
guard still skips passing). Commits `cf5c4e7`, `8f320ce`. **Shipped to D1+R2 (run
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
flip). Commits `753d885`, `e0d301e`, `ec7f073`. **Self-validating loop:**
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
double-dash zeros + EMLAK 15→16 col mis-clamp (commits b8b1c51, 8a91444). Whole
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
