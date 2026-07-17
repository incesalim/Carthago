# Loans-by-sector lane → 0 errors, 0 spurious missing

**Date:** 2026-07-17 · **Status:** COMPLETE — shipped, live in D1 · **Lane:** `loans_by_sector` (§5, annual-only)

| | before | after |
|---|---|---|
| errors | 6 | **0** |
| missing | 7 | **8** (ALNTF — see below; the original 7 became N/A) |
| ok | 236 | 223 |
| manual | 0 | **9** (hand-transcribed) |
| N/A | 807 | **810** |
| silent-wrong `ok` cells corrected | — | **6** |

Companion to [audit-stages-lane-to-zero](audit-stages-lane-to-zero-2026-07-17.md) and
[audit-npl-movement-lane-to-zero](audit-npl-movement-lane-to-zero-2026-07-17.md). The lane models the
IFRS-9 **Stage-2 / Stage-3 (+ECL) split by sector** — 35 of 38 banks disclose it; it is annual-only
(zero interim rows corpus-wide, so 799 interim N/A are the registry's `annual_only` rule, not curation).

## The 6 errors

### TAKAS ×4 — a Value-at-Risk table stored as a loan sector total

Every TAKAS annual cell stored one row: `Toplam Riske Maruz Değer` — the **Total Value at Risk** line
from the §III market-risk table. Mechanism: TAKAS prints *"Önemli Sektörlere veya Karşı Taraf Türüne
Göre Muhtelif Bilgiler: **Bulunmamaktadır**"* — a heading that answers itself nil. The heading regex
matched it, the page had no rows, and the GARAN-split retry appended the **next page** (market risk),
where `startswith("toplam")` matched `Toplam Riske Maruz Değer`.

**Fix:** `_is_nil_declared_note` — a sector heading whose next ~120 chars carry a nil word
(Bulunmamaktadır/None/Yoktur) and no numeric tail is skipped, so the retry never fires.
**Proven neutral**, not just calibrated: the extractor was run **with and without** the change on six
varied banks (AKBNK, YKBNK, DENIZ, EXIM, QNBFB, KUVEYT) — identical row counts. It does exactly one
thing: TAKAS → 0 rows → N/A with the `Bulunmamaktadır` citation.

⚠️ **The plausible CCP story was wrong; the citation is what makes TAKAS N/A** — see
[audit-npl-movement-lane-to-zero](audit-npl-movement-lane-to-zero-2026-07-17.md). TAKAS also prints a
*different* sector table ("Sektörlere göre nakdi kredi dağılımı", Toplam ₺470bn) whose columns are
14 credit-risk-classes, not stages — not this lane's data.

### TOMK 2024Q4 — a source defect

p43 literally prints `Hizmetler  -` while its only child `Mali Kuruluşlar` carries `85.003`, and the
bank's own `Toplam 308.533` **includes** it (= Diğer 223.530 + 85.003). So the filer left its own
services subtotal blank. `_resolved_top_level` prefers a present parent over its children, so the
printed dash displaces the real 85,003 and the footing can never tie. Not fixable by data (85,003 is
not printed on the subtotal line) → added to `_LBS_SKIP`, the "verified faithful, source doesn't
foot" list (alongside ATBANK ×8).

### ICBCT 2023Q4 consolidated — the year-swap (see below)

## The 7 missing → all N/A, with citations

Verified by a language-agnostic full-document sweep + bitmap/vector detector; no missed table exists.
**Four are TFRS-9 non-appliers** — DUNYAK, ZIRAATD, COLENDI (+ the known TOMK) — each wording the
BDDK art. 9/6 exemption differently (DUNYAK cites an *approval letter* "3 Ekim 2017… E.81", COLENDI in
English "the sixth paragraph of the ninth article"), which is why naive probes returned 0. A
non-applier runs no ECL model, so an IFRS-9 stage-by-sector table cannot exist. The rest (ENPARA,
HAYATK, plus DUNYAK 2023Q4's *legacy-schema* table) print a nil or non-stage disclosure.

## ⚠️ The ALNTF N/A was FALSE — the headline correction

ALNTF was curated N/A on the reasoning "legacy past-due schema, no Stage-2/Stage-3 by sector". **It
discloses stage-by-sector in all 8 annual reports.** The captions are legacy (*Değer Kaybına Uğramış*
/ *Tahsili gecikmiş*), but the **numbers are the stages**, proven against the report's own note:

```
2025Q4 unco sector TOPLAM  Değer Kaybına Uğramış 6,189,164 / Tahsili gecikmiş 672,853
report's own stage note    Yakın İzlemedeki      6,189,164 / Takipteki       672,853
```

Exact on 7 of 8 cells. And ALNTF states it **applies** TFRS 9 (*"Banka 1 Ocak 2018 tarihinden
itibaren … TFRS 9 hükümlerine uygun olarak ayırmaya başlamıştır"*), so there is no exemption to lean
on. `_is_legacy_pastdue_table()` fires correctly — the captions genuinely lack "İkinci/Üçüncü Aşama" —
but its **premise is false: legacy captions do not imply legacy data.**

**The sharp line:** ALNTF *applies* TFRS 9 → legacy captions hide real stages → N/A false → `missing`.
DUNYAK is a *non-applier* → its legacy table has no stages to hide → N/A true.

The 8 false N/A entries are removed; the cells now read honest `missing` (disclosed, our extractor
skips legacy-caption tables). **Follow-up:** teach the extractor to parse ALNTF positionally (column
order already matches peers, S2 then S3) when the bank is a TFRS-9 applier — but map `Karşılıklar` →
Stage-3 provisions, NOT total ECL (peers' ECL column is total). A rushed transcription risks that
column-semantics trap, so it's left as a scoped enhancement.

## Two new zero-false-positive checks

### `loans_sector_year_swap` — footing is blind to a wholesale year-swap

A year-swap foots perfectly, because last year's table foots against last year's total. Only a
cross-period identity sees it. **ICBCT** stacks two tables on one page captioned `31 Aralık 2023` /
`31 Aralık 2022` — never "Cari Dönem"/"Önceki Dönem" — so the period never flips, both tag `current`,
and `_dedupe`'s first-wins backfills dropped 2023 rows from the 2022 table. 2023Q4 unconsolidated
became almost entirely the 2022 table: stored `1,749,577 / 41,860`, byte-identical to its own 2022Q4,
**Stage 3 understated 3.1×** — and read a flawless `ok` for as long as the lane has existed.
**Check:** this year's total must not equal the prior annual report's total on both stage columns to
the lira (nil-on-nil excluded — the one honest repeat). **Calibrated 2/236, both ICBCT, zero FP.**

### `loans_sector_child_exceeds_parent` — a mathematical invariant

A group total is the sum of its non-negative children, so no child can exceed its parent. A child >
parent is a merged-label corruption footing misses (because `_resolved_top_level` sums the *parent*,
ignoring the corrupt child). Zero FP by construction. Surfaced **8 partitions** — e.g. ICBCT 2022Q4
`agri_fishery` 635,214 (the prior-year Sanayi total, y-bucketed onto nil Balıkçılık) against
`agri_total` 0; ICBCT 2025Q4 `svc_education` 1,448,401 (belongs to Sağlık).

## The extractor bug, and why the fix is overrides

Root cause is upstream in **`_fitz_page_text`** — "the single text reader for every audit-statement
parser". It buckets words by `int(round(y0))` then chain-merges buckets `<= 3` apart. In ICBCT's
table each row's numbers sit **3.36pt above** their label, so a bucket rounds to 3 (merge) or 4
(split) on sub-pixel jitter — dropping ~7 rows per table, which `_dedupe` then backfills from the
adjacent year. Fixing it means touching the reader that BS/P&L/OCI/cash-flow all pass through — every
frozen, passing lane. **Out of scope for a footnote lane**, so the 9 corrupt partitions (ICBCT ×7,
AKTIF ×2) were **hand-transcribed** off the printed page, every cell 7–13× pixel-verified, each table
foot-checked before write, via a new `loans_by_sector_replace` whole-partition override. They read
`manual` (new `_STMT_TO_KEY` entry), not a machine `ok`.

Two footing caveats in the transcriptions are **real source artifacts**, pixel-verified, stored as
printed: ICBCT 2024Q4 cons ECL grand total is 1 low (88,149 vs Σ 88,150); ICBCT 2022Q4 cons ECL
parent subtotals over-state their children (Sanayi 158,120 vs Σ138,117) while the grand total ties to
the leaves. Both foot on Stage 2/Stage 3, which is what the check uses (ECL is excluded).

## ⚠️ Process note — the `--force` mistake

Mid-session I ran `reextract_statement --statement loans_by_sector --banks ALL --force` as a
"calibration". It **regressed AKBNK ×4 and DENIZ** from passing to failing, because `--force`
re-extracts under *current* code over rows frozen by *older* code — so the diff measured every
accumulated extractor change at once, not my one edit. Reverted by restoring only
`bank_audit_loans_by_sector` from the R2 snapshot. **Lesson:** never `--force` a whole lane to isolate
one change; run the extractor **with vs without** the change on the same PDFs instead (that's how the
nil-predicate was proven neutral).

## Open / follow-ups

* **ALNTF ×8 `missing`** — disclosed under legacy captions; needs the positional-parse-when-applier
  extractor change (map `Karşılıklar` → Stage-3 provisions, not total ECL), or a careful
  8-partition transcription.
* **The `_fitz_page_text` y-bucketing** (`int(round(y0))` + chained `<=3`) aliases sub-pixel offsets —
  the shared root cause. A cluster-on-interval rewrite would fix ICBCT-class tables across every lane
  but is high-risk (167 partitions rely on the current caption-defaults-to-current behaviour); gate any
  attempt on a corpus-wide re-extract + total-row diff.
* **Period-tagging by printed date** (not just "Cari/Önceki Dönem") is the contained partial fix for
  the ICBCT stacked-table family — converts a silent year-swap into a visible footing failure — but
  doesn't recover the y-bucket-dropped rows, so it needs the reader fix too.
