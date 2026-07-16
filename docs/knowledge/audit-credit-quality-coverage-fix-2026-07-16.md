# Credit quality (IFRS-9 footnote) — 2 errors + 9 missing cleared, 8 N/A re-verified

**Date:** 2026-07-16 · **Status:** ✅ FIXED (extractor + curated N/A; D1 push pending a clean tree) · **Memory:** [[project_audit_npl_followups]], [[reference_credit_quality_stage_columns]]

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
