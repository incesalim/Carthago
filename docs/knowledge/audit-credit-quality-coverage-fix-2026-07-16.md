# Credit quality (IFRS-9 footnote) — 2 errors + 9 missing cleared, 8 N/A re-verified

**Date:** 2026-07-16, updated 2026-07-17 · **Status:** ✅ SHIPPED — live in D1 + R2
snapshot. **Both lanes COMPLETE:** `credit_quality` **1024 ok / 15 manual / 0 err
/ 0 miss / 11 n·a**, `stages` **1039 ok / 0 / 0 / 11**. Read the two *Follow-up*
sections at the bottom for the `stages` half · **Memory:**
[[project_credit_quality_floor_fix]], [[project_audit_npl_followups]],
[[reference_credit_quality_stage_columns]]

> The per-section tables below are kept as the record of each step; the header
> above is the current state. Section 1 ("Result") reports the state after the
> extractor fix only — Follow-ups 1 and 2 moved it on.

## What prompted it

The `/admin` coverage matrix row for **Credit quality (IFRS-9 footnote)**:
`ok=1031 · manual=– · error=2 · missing=9 · n/a=8` (1050 cells). Brief: fix the
errors and the missing, and re-check the N/A.

## Result

| | before | after |
|---|---|---|
| ok | 1031 | **1039** |
| error | 2 | **0** |
| missing | 9 | **0** |
| n/a | 8 | **11** |

Carried into the derived `stages` row: missing 14→5, ok 1021→1024, n/a 8→11,
error 7→10 (see *Known residue*).

## The 9 missing were ONE root cause: a ₺1bn floor, not 9 bank quirks

`_extract_loans_by_stage_from_page` gated every §7.2 Toplam row on
`vals[0] >= 1_000_000` (thousand TL ⇒ ₺1bn). Values are in thousand TL, so any
bank with a loan book under ₺1bn was silently invisible — the new digital banks.

The corpus showed the tell before a single PDF was opened. Extracted Stage-1
values **pile up immediately above the floor** — 1,008,524 / 1,011,126 /
1,041,456 / 1,103,350 / 1,259,669 — and the *same bank* appears only once it
grows across it:

| bank | out (below floor) | in (above floor) |
|---|---|---|
| COLENDI | 2025Q2 ₺37m · Q3 ₺252m · Q4 ₺610m | 2026Q1 ₺1,041m |
| TOMK | 2023Q3–2024Q2 (≤₺229m) | 2024Q4 ₺1,259m |
| ZIRAATD | every quarter (≤₺308m) | — (never crossed) |

That is a **data cliff, not a filter**: a truncated distribution, and the same
report shape passing or failing purely on the bank's size.

### What the floor was actually protecting (measured, not assumed)

Instrumenting the gate across 20 healthy banks: **no large bank has a single
below-floor candidate** — on AKBNK/TEB/YKBNK/ODEA/HSBC/ISCTR/GARAN/ZIRAAT the
floor rejects nothing. The other gates do that work (3–5 numeric columns;
Stage 1 > ΣStage 2, which kills the ECL and aging-analysis Toplam rows the code
comments cite).

It catches exactly **one** real false positive: **SKBNK 2024Q4 p89**, the §4
table *"Exposures provisioned against by major regions and sectors"*, whose
column header reads `Current Period Loans Under Follow-Up Stage 3 Provisions
Write-Offs`. It matches the loose Stage-2 phrase, carries `Total 893,026
622,569`, and sits **22 pages before** the real §7.2 table — so with first-wins
dedup, naively dropping the floor would replace SKBNK's ₺56bn Stage 1 with
₺893m. Silently.

### The fix: structure instead of magnitude

That §4 header names a *follow-up* portfolio but never a *standard-loan* one.
The real §7.2 title always names both:

- `7.2. Standart Nitelikli ve Yakın İzlemedeki (Birinci ve İkinci Grup Krediler)…`
- `b) Information on the standard and under the close monitoring loans…` (COLENDI, EN)

So `_S12_SECTION_TITLE` requires **both tokens on one line**, and a
document-level fallback re-scans anchored on that title with the floor dropped
(`min_stage1=1`). It runs **only when the strict pass found nothing anywhere** —
the same guard the existing `allow_total_drop` fallback uses — so any bank that
extracts today can never be overridden by it. The 'standard' token is
deliberately bare: COLENDI's title reads "the standard **and** under the close
monitoring loans", and its column header wraps `Standard` / `Cash Loans` onto
separate visual lines.

Regression across 20 healthy + 19 problem PDFs: **200 rows byte-identical, 6
new, 0 lost** — SKBNK 2024Q4 held at 56,256,422.

### The recovered rows foot to the balance sheet exactly

Independent confirmation — the §7.2 Toplam vs the BS `Krediler` / `Loans` line:

| cell | §7.2 total | BS loan line |
|---|---|---|
| COLENDI 2025Q2 | 37,808 | 37,808 ✓ |
| COLENDI 2025Q3 | 252,424 | 252,424 ✓ |
| COLENDI 2025Q4 | 610,484 + 1,576 = 612,060 | 612,060 ✓ |
| TOMK 2024Q2 | 229,268 + 1,792 = 231,060 | 83,255 + 147,805 = 231,060 ✓ |
| ZIRAATD 2025Q3 | 7,301 | 7,301 ✓ |
| ZIRAATD 2025Q4 | 308,232 + 248 = 308,480 | 308,480 ✓ |

## The 2 errors: a dash is not a zero

DUNYAK 2026Q1 (cons + unco), note **8.4** *Finansal kiralama alacaklarının
TFRS9'a göre karşılık değişimleri* (lease-receivable ECL):

```
                          1.Aşama  2.Aşama  3.Aşama  Toplam
Önceki dönem sonu bakiye    2.234    9.331     -     11.565
Dönem İçi İlave            15.289      760     -     16.049
1. Aşamaya Transfer        (7.432)   7.432     -       -
Dönem Sonu Bakiyesi        10.091   17.523     -       -    ← Toplam omitted
```

Every other row foots (2.234+9.331 = 11.565). The closing total should read
**27.614** = 10.091+17.523 = 11.565+16.049. The bank left the cell blank; the
extractor read the `-` faithfully, but `parse_num('-')` → `0.0`, so we stored
`total_amount = 0.0` — asserting *"the bank disclosed zero"*, which is false.
The validator then correctly failed `cq_section_total` (0 ≠ 27,614).

Fixed at the source of the falsehood, not the symptom: a nil total beside
non-nil stages is **arithmetically impossible**, so it is an omission → store
`None` ("not disclosed"). The validator skips (it needs all four non-null) and
the error clears honestly. We do **not** derive 27.614 — the source never
printed it. A dash total whose stages are *also* nil stays `0.0` (a genuine
zero, e.g. the transfer rows). Only 2 rows corpus-wide match this shape.

## The 8 N/A: all re-verified against the PDFs, all correct

Verified by scanning each PDF for every credit-quality anchor, not by trusting
the extractor's silence.

- **ICBCT 2023Q4 cons** (9 pages) and **TSKB 2026Q1 unco** (14 pages) — brief
  filings, **no anchors at all**. Correct.
- **FIBA ×6** (2022Q1 cons+unco, 2023Q3 cons, 2024Q1 cons, 2025Q3 cons+unco) —
  correct, but the old note understated the reason. The §5.2 **heading IS
  present**, which makes these look disclosed; underneath it there is no table,
  just:

  > *Bankalarca Kamuya Açıklanacak Finansal Tablolar … Tebliği'nin **25inci
  > maddesi uyarınca hazırlanmamıştır*** ("not prepared per Article 25")

  FIBA prints the §5 credit notes as a **skeleton of headings** in Q1/Q3 and
  declares non-preparation under the communiqué's interim exemption; it
  discloses the real table only in Q2/Q4 (cf. 2025Q2 §5.2 `Toplam 51.617.712 …`,
  which extracts cleanly). The Article-25 phrase appears 9–10× per report and
  governs several sections — its mere presence proves nothing; it has to be read
  against §5.2 specifically. Notes updated with the citation.

## The 3 newly-added N/A: TOMK had no loan book

TOMK 2023Q3 / 2023Q4 / 2024Q1 disclose no §7.2 table because there was nothing
to disclose. Four independent confirmations:

1. The asset-note numbering jumps **`2. Bankalar ve diğer mali kuruluşlara` →
   `4. Maddi duran varlıklara`** — note 3 (Krediler) does not exist.
2. `Standart Nitelikli` / `Yakın İzlemedeki` appear **nowhere** in the document.
3. The balance sheet: `Krediler` = **0** at 2023Q3 and 2023Q4 (₺5.3m at 2024Q1 —
   immaterial, still unnoted).
4. The 2024Q2 report's own prior-period column (31 Aralık 2023) is **all dashes**.

The loans note first appears in 2024Q2 and now extracts.

## Reconciliation with `stages-lane-errors-missing-2026-07-16.md`

A concurrent session diagnosed the derived `stages` row at the same time, spotted
this session mid-edit in `credit_quality.py`, and stopped at diagnosis — its doc
is the handover. It independently reached the same root cause (the ₺1bn floor)
and verified this fallback works. Two points need settling between the docs:

1. **It says "N/A would be wrong here … the §7.2 table is printed in every one of
   these", listing TOMK 2023Q3/Q4 + 2024Q1. That is over-generalised** — its only
   citation is `p61` of the **2024Q2** report, and the earlier quarters were
   inferred from it, not read. Read directly, those three PDFs contain **zero**
   occurrences of `Yakın İzleme` and `Birinci ve İkinci` — the Stage-2 column
   header and half the section title, without which the table cannot exist. Their
   `Standart` hits are *standart yaklaşım* (the capital-risk standard approach),
   and their only `Kredilere ilişkin` hits are the **gayrinakdi** (non-cash) and
   related-party notes, both "Bulunmamaktadır". Plus: note 3 is missing from the
   numbering, BS `Krediler` = 0 / 0 / ₺5.3m, and 2024Q2's own prior column is all
   dashes. The N/A entries are correct — `audit_not_disclosed.json`'s rule
   ("never hide an extraction gap for data that IS printed") is respected,
   because for these three quarters nothing is printed. Its 2024Q2 row is right,
   and 2024Q2 is fixed by extraction, not by an N/A entry.
2. **Its "the two halves must land together" warning is real, and its prediction
   was too narrow.** It expected only TOMK 2024Q2 to flip missing ➜ error
   (reasoning COLENDI/ZIRAATD rescue to S2 = NULL and skip the check). That holds
   for the quarters it sampled (COLENDI 2025Q2/Q3, ZIRAATD 2025Q3 — all now
   green), but **COLENDI 2025Q4 (S2 = 1,576) and ZIRAATD 2025Q4 (S2 = 248)** have
   a non-null S2 and flip too. So **3** cells, not 1. See *Known residue*.

Its causes 2 and 3 (prose-zero → S3 = 0; templates for the 6 new banks; TOMK
2024Q4's `npl_brsa_gross`) remain open and unowned.

## Known residue (deliberate, not overlooked)

`stages` error 7→10: COLENDI 2025Q4, TOMK 2024Q2, ZIRAATD 2025Q4 now trip
`stages_stage3_missing` (S1/S2 captured, S3 NULL). They are newly **visible**,
not newly broken — previously they were 'missing' with no rows at all — and they
join an existing class (DUNYAK 2025Q1/Q2, TOMK 2024Q3/Q4).

The check's premise is *"a genuine zero-NPL bank stores S3 = 0, not NULL"*,
which assumes the bank prints a zeroed NPL table. These banks print **no III/IV/V
table at all**: ZIRAATD's BS `Donuk Alacaklar` = 0 exactly, TOMK 2024Q2's = ₺2
thousand. Defaulting S3 to 0 when no NPL table exists would rebuild precisely the
blind spot that hid EMLAK's missing NPL for 10 quarters behind a green cell, so
they stay flagged. **Open call:** whether "no NPL table filed" should resolve to
S3 = 0 or to N/A — it needs its own change and its own verification.

Also unchanged (out of scope): `npl_movement` is 'missing' on the same
new-bank cells for the same underlying reason (no NPL → no movement table). It is
a separate extractor and needs its own PDF verification before any N/A entry.

## Files

- `src/audit_reports/credit_quality.py` — `_S12_SECTION_TITLE`, the
  `require_section_title` / `min_stage1` params + small-bank fallback, `_is_dash`
- `data/audit_not_disclosed.json` — TOMK ×3 added; FIBA ×6 notes strengthened
- `tests/test_credit_quality_extract.py` — 7 tests locking both fixes, incl. the
  SKBNK §4 false positive and the all-nil-total case

---

## Follow-up 2026-07-17 — the `stages` half closed (10 errors → 0)

The *Known residue* above is resolved. `stages` now reads **1034 ok / 0 error /
5 missing / 11 n·a**; `credit_quality` reads **1029 ok / 10 manual / 0 / 0 / 11**.

**Root cause of all 10: Stage 3 is disclosed as PROSE, not a table.** These banks
have no NPL to tabulate, so instead of a III/IV/V table they print a sentence —
`Donuk alacaklara ilişkin bilgiler (net): Bulunmamaktadır` / `Information on
non-performing loans (Net): None` / `Donuk alacak tutarı 2 TL'dir`. No
table-anchored extractor can read that, so S3 stayed NULL and
`stages_stage3_missing` fired. The zero is **stated**, not absent — which is
exactly what `check_stages`' own contract ("a genuine zero-NPL bank stores S3 =
0, not NULL") asks for, and what these banks cannot express in a table they never
print.

Fixed by curation, not by a detector: a new `credit_quality` override type in
`apply_overrides.py` upserts the `npl_brsa_gross` row. Chosen over the
prose-zero detector that `stages-lane-errors-missing-2026-07-16.md` recommends
because the detector must NOT fire where a real table exists (DUNYAK 2023Q4
carries *both* a "Bulunmamaktadır" line and a real movement table), and 10 cells
did not justify that risk. If these banks keep filing prose every quarter the
detector becomes the right call — the overrides are the interim.

Every figure is sourced from the sentence AND cross-checked against the balance
sheet's `Donuk Alacaklar` line — two independent reads:

| cell | S3 | source | BS check |
|---|---|---|---|
| COLENDI 2025Q4 | 0 | p65 "…non-performing loans (Net): None" | — |
| DUNYAK 2025Q1 cons/unco | 0 | p56/p55 "Bulunmamaktadır" | — |
| DUNYAK 2025Q2 cons/unco | 0 | p68/p69 "Bulunmamaktadır" | — |
| TOMK 2024Q2 | 2 | p64 "Donuk alacak tutarı **2 TL**'dir" | 2 ✓ |
| TOMK 2024Q3 | 4,406 | p53 "…**4.406 TL**'dir" | 4.406 ✓ |
| TOMK 2024Q4 | 177,537 | p98 "Dönem Sonu Bakiyesi - - **177.537**" (real table) | 177.537 ✓ |
| ZIRAATD 2025Q4 | 0 | p85 §7.8.1–7.8.4 all "Bulunmamaktadır" | 0 ✓ |

Units: TOMK's "2 TL" is **thousand** TL — the report abbreviates *Bin Türk Lirası*
as "TL". Where a bank gives only a prose total the III/IV/V groups stay **NULL**
(no split is disclosed), so `cq_section_total` correctly skips instead of
checking a fabricated decomposition.

### `stages_npl100` earned its keep — DUNYAK 2023Q4 was live wrong data

Not a blank cell: `npl_brsa_gross.total_amount = 6,077` was being served as the
Stage-3 **stock**. p58 shows 6,077 is `Dönem İçinde Tahsilat (-)` — a collections
**flow**. The table foots to zero and says so:

```
Önceki Dönem Sonu Bakiyesi   -  -  6.075
Dönem İçinde İntikal (+)     -  -      2
Dönem İçinde Tahsilat (-)    -  -  6.077   ← was stored as the NPL stock
Dönem Sonu Bakiyesi          -  -      -   ← the truth: 0
```

6.075 + 2 − 6.077 = 0, and the balance sheet agrees — `2.5 Donuk Alacaklar`'s
CURRENT column is dashes (the 6.075 sits in the PRIOR column only). Corrected to
0/0/0. Credit for finding it: `stages-lane-errors-missing-2026-07-16.md`.

### These cells read `manual`, not `ok`

`sync_audit_expected._STMT_TO_KEY` learned `credit_quality`, so the 10 curated
cells land in the matrix's **Manual** column. A figure a human transcribed out of
a sentence must not present as machine-extracted — that distinction is the whole
point of the column.

### Still open

- The **prose-zero detector** (preferred long-term over per-quarter overrides).
- **Templates** for the 6 new banks' `npl_brsa` regex path — the misread that put
  a flow row in the stock field is still possible for any bank without one.
- `stages` **5 missing** = ENPARA/HAYATK, which hold only `loans_ecl_expense` —
  a section the stages builder does not read. Untouched.

## Follow-up 2 — the last 5 `stages` missing (ENPARA / HAYATK): lane complete

`stages` **1039 ok / 0 err / 0 miss / 11 n·a**; `credit_quality` **1024 ok /
15 manual / 0 / 0 / 11**. Both rows clean.

These 5 held only `loans_ecl_expense` — a section the stages builder does not
read — so `credit_quality` showed a green **ok** while carrying nothing usable.
Worth remembering: *a green cell is not the same as a useful one.* The row count
gate (`present_min_rows=1`) can't tell the difference.

Two distinct causes:

**ENPARA 2025Q1/Q2 — the floor fix already worked; it just never ran.** These
partitions already PASSED credit_quality validation, so the non-destructive
upsert ([[reference_nondestructive_upsert]]) skipped them and `--only-failing`
never selected them. Needed `--force`. Extraction then yields S1 = 17 (2025Q1)
and S1+S2 = 245+2 = 247 (2025Q2), tying BS `2.1 Krediler` = 17 / 247 EXACTLY.
**Lesson: a fix to an extractor does not reach cells that are already "passing"
on partial data.** After changing an extractor, re-check the passing cells too,
not just the failing ones.

**ENPARA 2024Q4 + HAYATK 2023Q1/Q2 — no loan book at all.** Every loan note reads
`Bulunmamaktadır` / `None`:

```
ENPARA 2024Q4 p68 — b.1) Standart Nitelikli ve Yakın İzlemedeki krediler ...
                    Bulunmamaktadır. (31 Aralık 2023 Bulunmamaktadır).
HAYATK 2023Q1 p39 — 1.5.2 Information on standard loans, loans under close
                    monitoring ...: None (31 December 2022 – None).
```

BS confirms `2.1 Krediler`/`Loans` = 0 in all three, and both banks start lending
right after (ENPARA 2025Q1 = 17; HAYATK 2023Q3 = 76,342). Recorded as a SOURCED
zero (S1=S2=S3=0), consistent with the Stage-3 treatment in Follow-up 1.

**The N/A-vs-zero line, stated once:** *is the note printed?*
- Note **absent** → nothing is disclosed → **N/A** (TOMK 2023Q3–2024Q1: the
  asset-note numbering skips Krediler entirely).
- Note **present, says "none"** → the zero IS disclosed → **0** (ENPARA 2024Q4,
  HAYATK 2023Q1/Q2, and every Stage-3 in Follow-up 1).

That is the same rule both ways, and it keeps
`audit_not_disclosed.json`'s contract intact ("never used to hide an extraction
gap for data that IS printed").

### Correcting the handover doc a second time

`stages-lane-errors-missing-2026-07-16.md` lists these 5 under "**every figure is
printed in the PDF**", citing "ENPARA ✅ S1 = 17 (p52)" for *2024Q4, 2025Q1/Q2*
together and "HAYATK ✅ table on p39 (EN)". Read directly: the S1 = 17 is
**2025Q1's** figure (ENPARA 2024Q4 has no loans and says so), and **p39 is not a
table** — it is the 1.5.2 heading followed by "None". Same failure mode as its
TOMK row (Follow-up 1): one PDF read, the neighbouring quarters inferred from it.
Its diagnosis of the *causes* was sound and its DUNYAK 2023Q4 catch was real —
but its per-cell "printed?" column was inferred, not verified, in three places.

### Still open

- The **prose-zero detector** — now 18 curated cells across 6 banks. Every new
  quarter these banks file with no NPL needs another entry, so the detector's
  case strengthens with each one.
- **Templates** for the 6 new banks' `npl_brsa` regex path (the DUNYAK 2023Q4
  flow-vs-stock misread class).
- `credit_quality`'s `present_min_rows=1` gate counts `loans_ecl_expense` as
  presence. Consider gating on a section the builder actually reads, so
  "ok but useless" cannot recur silently.
