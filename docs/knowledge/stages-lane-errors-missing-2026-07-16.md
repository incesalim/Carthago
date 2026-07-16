# IFRS-9 stages lane — the 7 errors + 14 missing, root-caused against the PDFs

**Date:** 2026-07-16 · **Status:** 🔎 DIAGNOSIS — handover, NO code change made ·
**Memory:** [[project_cashflow_and_lane_coverage]]

## Why this doc exists

"Fix errors and missing" on the `/admin` matrix row **IFRS-9 stages (derived)**
(1021 ok · 7 error · 14 missing · 8 N/A). Diagnosis got as far as ground truth
per partition; **a concurrent session was found actively editing
`src/audit_reports/credit_quality.py`** (mtime 16 s before inspection, plus new
commit `5749ce2`) on the *same* problem, so no code was written here — see
*Handover* at the bottom. This is the evidence that session needs.

## Bottom line

All 21 flagged partitions belong to the **6 new-entrant digital / participation
banks** (COLENDI, DUNYAK, ENPARA, HAYATK, TOMK, ZIRAATD). None is a
disclosure gap — **every figure is printed in the PDF**. There are three
distinct root causes, and they split cleanly:

| # | Root cause | Affects | Fix owner |
|---|---|---|---|
| 1 | **₺1bn `min_stage1` floor** drops small loan books → no `loans_by_stage` | the 14 *missing* | ✅ concurrent session (already works) |
| 2 | **Stage 3 is disclosed as PROSE** ("Bulunmamaktadır" / "None"), not a table → S3 stays NULL | DUNYAK 25Q1/Q2, + the S1/S2 rescues above | ❌ open |
| 3 | **No template** for these 6 banks → `npl_brsa` falls to the regex path | DUNYAK 23Q4 (**wrong number**), TOMK 24Q4 | ❌ open |

`stages` is **derived** (`scripts/build_bank_audit_stages.py`) from
`bank_audit_credit_quality`; it has no extractor. Every fix lands upstream.

## ⚠️ Cause 3 is live WRONG DATA, not a gap

**DUNYAK 2023Q4** currently stores `npl_brsa_gross.total_amount = 6,077` as the
Stage-3 **stock**. Page 58 shows 6,077 is *"Dönem İçinde Tahsilat (-)"* — a
**collections flow**:

```
Önceki Dönem Sonu Bakiyesi      -   -   6.075
Dönem İçinde İntikal (+)        -   -       2
Dönem İçinde Tahsilat (-)       -   -   6.077   ← extracted as the NPL stock
Dönem Sonu Bakiyesi             -   -       -   ← the truth: 0
```

6,075 + 2 − 6,077 = **0**, and the by-group gross/net table's *Cari Dönem*
column is all dashes. **True Stage 3 = 0.** The `stages_npl100` validator fired
correctly — it caught a real extraction bug. This one is worth fixing even if
nothing else is: it is a wrong figure in production, not a blank cell.

## Ground truth, per partition

Verified by reading the R2 PDF (`fitz`) unless marked *inferred*.

### The 7 errors

| Bank | Period | Kind | Check that fires | What the PDF says | True S3 |
|---|---|---|---|---|---|
| DUNYAK | 2023Q4 | unc | `stages_npl100` | 6,077 = collections flow; period-end = — | **0** |
| DUNYAK | 2025Q1 | unc | `stages_stage3_missing` | "j. Donuk alacaklara ilişkin bilgiler (net): **Bulunmamaktadır**" | **0** |
| DUNYAK | 2025Q1 | cons | `stages_stage3_missing` | *inferred* (same filing) | 0 |
| DUNYAK | 2025Q2 | unc / cons | `stages_stage3_missing` | *inferred* | 0 |
| TOMK | 2024Q3 | unc | `stages_stage3_missing` | *inferred* (PDF not pulled) | ? |
| TOMK | 2024Q4 | unc | `stages_stage3_missing` | **real NPL** — p68 "Temerrüt (Üçüncü Aşama) 177.537" | **177,537** |

DUNYAK 2025Q1 cross-foots exactly: S1 25,523,178 + S2 82,945 = 25,606,123 =
the disclosed *"Yurtiçi Krediler / Toplam"*. S3 = 0 is the only consistent
reading.

**TOMK 2024Q4 is the one genuine Stage-3 extraction gap.** The NPL is captured
as `npl_brsa_net` (177,537, p99) but **no `npl_brsa_gross` row** — and the
builder reads Stage 3 from `npl_brsa_gross` only, so S3 lands NULL.

### The 14 missing

`credit_quality` upstream: **ok but useless** for ENPARA/HAYATK (they hold only
`loans_ecl_expense`, which the builder does not read), **0 rows** for the rest.

| Bank | Periods | Loans printed? | NPL note |
|---|---|---|---|
| COLENDI | 2025Q2/Q3/Q4 | ✅ S1 = 37,808 (p46, Q2) | "Stage 3: **None**" / "non-performing loans: **None**" |
| ENPARA | 2024Q4, 2025Q1/Q2 | ✅ S1 = 17 (p52) | "temerrüt (Üçüncü Aşama) karşılıkları: **Bulunmamaktadır**" |
| HAYATK | 2023Q1/Q2 | ✅ table on p39 (EN) | "Gross and net amounts of NPL…: **None**" |
| TOMK | 2023Q3/Q4, 2024Q1/Q2 | ✅ S1 = 229,268 S2 = 1,792 (p61, 24Q2) | 24Q2: "Donuk alacak tutarı **2 TL**'dir" |
| ZIRAATD | 2025Q3/Q4 | ✅ S1 = 7,301 (p53) | "(Üçüncü Aşama): **Bulunmamaktadır**" |

The prose "none" is **both languages**: TR `Bulunmamaktadır`, EN
`None (31 December 2024: None)`. These are 1–3-year-old banks that genuinely
have no NPL yet — an explicit, *sourced* zero, not an absence.

**N/A would be wrong here.** `data/audit_not_disclosed.json` states the rule:
"never used to hide an extraction gap for data that IS printed". The §7.2 table
is printed in every one of these. (Contrast the legitimate FIBA precedent, where
the table genuinely is not in the document.)

## The concurrent session's fix — verified working

Re-running `extract_from_pdf` against its in-flight working tree (an earlier run
predating its 23:34:05 edit returned 0 rows):

| Bank | `loans_by_stage` now | PDF |
|---|---|---|
| COLENDI 2025Q2 | S1 = 37,808 | ✅ |
| ZIRAATD 2025Q3 | S1 = 7,301 | ✅ |
| TOMK 2024Q2 | S1 = 229,268 · S2 = 1,792 | ✅ |
| ENPARA 2025Q1 | S1 = 17 | ✅ |
| DUNYAK 2025Q1 | unchanged (25,523,178 / 82,945) | ✅ no regression |

Its `require_section_title` + `min_stage1=1` fallback (anchored on
`_S12_SECTION_TITLE`, gated on "found nothing") resolves **cause 1** — the 14
missing. That half is done.

## ⚠️ The two halves must land together

Fixing S1/S2 alone will convert some *missing* cells into **errors**.
`check_stages` fires `stages_stage3_missing` when S3 is NULL **and both S1 and
S2 are non-NULL**. Today those partitions escape only because S2 is NULL too.

- **TOMK 2024Q2** — the rescue yields S1 = 229,268 **and** S2 = 1,792 → both
  present, S3 NULL → **`stages_stage3_missing` fires** → missing ➜ error.
- COLENDI / ZIRAATD / ENPARA rescue to S2 = NULL, so they skip the check and go
  green — but on a *partial* row, which is luck, not correctness.

So cause 2 (prose-zero → S3 = 0) is a **prerequisite** for shipping cause 1
cleanly, not a follow-up.

## Recommended fixes (not implemented)

1. **Prose-zero detector** (cause 2) — when the §5 NPL / Stage-3 note is present
   and explicitly declares none (`Bulunmamaktadır` | `Yoktur` | `None`) with no
   table beneath, emit `npl_brsa_gross.total_amount = 0` (+ `npl_brsa_provision
   = 0`) for `period_type='current'`. That is a *sourced* zero and matches the
   validator's own stated contract: *"A genuine zero-NPL bank stores S3 = 0, not
   NULL"*. Must NOT fire where a real table exists (TOMK 2024Q4; DUNYAK 2023Q4
   p58 carries **both** a "Bulunmamaktadır" line *and* a real movement table —
   naive matching mis-fires there).
2. **Templates for the 6 banks** (cause 3) in `data/banks/audit_templates.json`
   — the registry covers only the original 31, so these banks fall to the
   regex `npl_brsa` path that misread DUNYAK 2023Q4's flow row. A template
   anchored on `Dönem Sonu Bakiyesi` (gross) reads the stock correctly.
3. **TOMK 2024Q4** — capture `npl_brsa_gross` (177,537), not just `npl_brsa_net`.
4. Re-extract the 21 partitions (`reextract_statement.py --statement
   credit_quality`), re-run `build_bank_audit_stages.py`, push, then
   `sync_audit_expected.py --push` ([[reference_overrides_coverage_spine]]).

Prefer a detector over per-cell overrides: these banks will keep filing
"Bulunmamaktadır" every quarter until their first default, so overrides would
need topping up forever.

## Corrections to prior notes

- [[project_cashflow_and_lane_coverage]] says the new-bank credit_quality/stages
  gaps "need templates not overrides". **Half right.** Templates fix the
  `npl_brsa` misreads (cause 3), but the 14 *missing* were never a template
  problem at all — they were the ₺1bn `min_stage1` floor (cause 1), and the
  Stage-3 NULLs are a prose-vs-table problem (cause 2). Templates alone would
  have fixed neither.

## Handover

Working tree at diagnosis time (do **not** stage these — not mine):
`src/audit_reports/credit_quality.py`, `data/audit_overrides.json`,
`data/manual_statements.json`, `scripts/apply_overrides.py`
([[reference_shared_worktree_commits]]).

Reproduction (read-only, ~8 PDFs from R2, local creds):

```python
from src.audit_reports.credit_quality import extract_from_pdf
rep = extract_from_pdf(pdf_path=".../DUNYAK_2023Q4_unconsolidated.pdf")
# NOTE: first positional arg is `pdf` and is IGNORED — pass pdf_path= by keyword,
# or you get a silent empty report.
```

D1 query behind the matrix row:

```sql
SELECT bank_ticker, period, kind, status, row_count, checks_failed
FROM bank_audit_coverage
WHERE statement_type='stages' AND status IN ('error','missing');
```
