# AUDIT BALANCE-SHEET FIX — COMPLETE (2026-06-12)

Production D1: **balance-sheet validation failures = 0 fleet-wide** (was 68),
`-6` ECL corruption = 0, **validation covers all 975 partitions**. The final
10 flagged partitions were each cleared by hand-transcribing the legible PDF
values into `data/audit_overrides.json` (user supplied screenshots; values
cross-checked against the report's own subtotals/column totals before writing).
Only the 49 off-balance-sheet truncated-label rows (DENIZ/HSBC/KUVEYT) remain —
display-only, validator doesn't cover them, low priority.

## The final 10 — what each actually was (all now 0 failures):
- **EXIM 2024Q4** — 3 published digit-typos pinned by footing: asset 1.3.2 TL
  746.469→796.469, asset V. TL 336.253→336.235, liab 16.4/XVI FC 4.374→4.473.
- **QNBFB 2022Q4** — XV. Other Liab TRY under-printed 19.501.461→19.815.961
  (FC + grand total correct; TL column short by 314.500).
- **ODEA 2023Q4** — 2.2 Lease Receivables: dipnot "I-10" leaked a phantom −10;
  deposit bank → true value 0.
- **TEB 2024Q4** (uncons) — V. Maddi Duran row dropped (roman marker absent in
  page text); re-inserted 3.043.626 at the right position.
- **BURGAN 2023Q2** — V. Tangible TL misparsed as decimal 2818.188 → 2.818.188.
- **TSKB 2025Q3** (uncons) — II. parent + 2.5 ECL value strings wrapped across
  columns; re-read from the (intact) text layer. NOT image-only after all.
- **KUVEYT 2022Q2 / 2025Q4** — VII. Lease (Net) rows were dipnot stubs
  (label "(Net) (5.2.6.)" wrapped → TL5/FC2/Total6); restored real lease figures.
- **YKBNK 2022Q3 / 2022Q4** — equity children garble: 2022Q3 fixed 7.2/16.3/16.4
  values; 2022Q4 the "16.3" row held 16.4's values (reset 16.3, inserted 16.4)
  and 7.2 was missing (inserted). XVI=Σ16.x and VII=7.1+7.2 now foot.

## Tooling added this pass
- `scripts/apply_overrides.py` gained **positional insert** (`item_order` field
  on an override) — shifts later rows via a negative-temp pass (a plain +1
  collides with the UNIQUE(item_order) index). Used for dropped-row re-inserts
  (TEB V., YKBNK 16.4 / 7.2).
- `data/audit_overrides.json` now holds 22 curated cell corrections, each noted
  with the evidence that fixes its partition to 0.

## Still open (separate from the 10, validator doesn't cover):
- 3 P&L footnote-leak rows: ISCTR 2024Q4 (×2), KUVEYT 2024Q4 — need P&L override.
- 49 off-balance truncated-label rows — cosmetic.
- FOLLOW-UP: make validation push always-full (the coverage-erosion bug).

---

# (prior) AUDIT BALANCE-SHEET FIX — FINAL STATE (2026-06-11, updated)

Production D1: BS validation failures **68 → 10**, `-6` corruption = 0,
261+ partitions corrected, 7 readable rows fixed via overrides + BURGAN 2025Q3
fixed via comma-marker normalization. **Validation now fully covers all 975
partitions** (an earlier bug: incremental `push_to_d1 --hours N` clears a
partition across all tables but only re-pushes rows inside the time window, so
repeated partition-pushes eroded bank_audit_validation coverage to 613, hiding
~4 bad partitions; fixed by wiping + full-pushing the validation table.
FOLLOW-UP: make validation push always full, or stop the clear from eroding it).

## The 10 still flagged (⚠ everywhere):
**6 genuine-source defects (PDF wrong/unreadable — OCR or reissue):**
EXIM 2024Q4, QNBFB 2022Q4, ODEA 2023Q4, TEB 2024Q4, BURGAN 2023Q2, TSKB 2025Q3.
**4 structural-hard:** KUVEYT 2022Q2/2025Q4 (lease value wrapped off label),
YKBNK 2022Q3/2022Q4 (bank's own equity children don't sum to parent).

---

# (prior) AUDIT BALANCE-SHEET FIX — FINAL STATE (2026-06-11)

Production D1: BS validation failures **68 → 11**, `-6` corruption eliminated,
261+ partitions corrected, 6 readable rows fixed via curated overrides
(scripts/apply_overrides.py + data/audit_overrides.json — no re-extraction).

## The 11 still flagged (⚠ on dashboard) — split by why:
**6 genuine-source defects (PDF itself wrong/unreadable — needs OCR or bank reissue):**
EXIM 2024Q4, QNBFB 2022Q4, ODEA 2023Q4, TEB 2024Q4, BURGAN 2023Q2, TSKB 2025Q3.

**5 structural-hard (fixable with real work, not a value transcription):**
- BURGAN 2025Q3 — whole statement uses comma markers ("1,1"); needs a
  comma-normalization parser pass + re-extract.
- KUVEYT 2022Q2 / 2025Q4 — lease (VII) value wrapped off its label line;
  total determinable, TL/FC split needs a careful read.
- YKBNK 2022Q3 / 2022Q4 — the bank's own equity children don't sum to the
  parent (97.8M vs 112.5M); needs source analysis, not a guess.

## Also outstanding (not in the 11 — P&L/off-balance, validator doesn't cover):
- 3 income-statement footnote-leak rows: ISCTR 2024Q4 (×2 — correct values
  −8,861,710 / −7,343,678), KUVEYT 2024Q4. (P&L override needs hierarchy-conflict
  handling vs the garbled rows.)
- 49 off-balance-sheet truncated-label rows (DENIZ/HSBC/KUVEYT) — separate statement.

## Fixed via override this pass (6):
EMLAK 2023Q2 (XIV equity), EMLAK 2022Q3 (1.1.4 ECL), EXIM 2023Q2 (XVI equity),
FIBA 2025Q4 + 2026Q1 (XII deferred tax), ATBANK 2022Q2 (16.7 minority interest).

---

# RESUME: audit balance-sheet fix push (paused 2026-06-11)

## State when paused
- **68 → ~16 failing partitions fixed in CODE** (committed to master, HEAD has
  11 identity-gated extractor fixes + regression fixes f3fcc74).
- **Production D1 NOT yet updated** — still has the pre-existing ~51 corrupted
  rows + 68 failing partitions. NOTHING corrupted; just not yet pushed.
- A clean evidence dry-run was mid-extraction (~150/500 PDFs) into
  `data/fleet_scratch.db` when paused. **Resumable — do NOT clear scratch.**

## To finish (resume sequence — NO full re-extraction)
1. **Resume extraction** (skips already-done PDFs, continues from ~150):
   ```
   python scripts/fleet_evidence.py --only ALNTF,ANADOLU,ATBANK,BURGAN,EMLAK,EXIM,FIBA,HSBC,ICBCT,ISCTR,KLNMA,KUVEYT,ODEA,PASHA,QNBFB,SKBNK,TEB,TSKB,VAKBN,YKBNK,ZIRAATK --workers 8
   ```
2. **Check** `data/backfill_evidence/report.md` — confirm `regressed: 0`
   (only the documented genuine-source survivors should remain in `investigate`).
3. **Push SAVED data to production (no re-extraction):**
   ```
   python scripts/push_from_scratch.py --banks ALNTF,ANADOLU,ATBANK,BURGAN,EMLAK,EXIM,FIBA,HSBC,ICBCT,ISCTR,KLNMA,KUVEYT,ODEA,PASHA,QNBFB,SKBNK,TEB,TSKB,VAKBN,YKBNK,ZIRAATK
   ```
4. **Revalidate + push flags:**
   ```
   python scripts/revalidate_audit_db.py
   python scripts/push_to_d1.py --db data/bank_audit.db --hours 1 --only-tables bank_audit_validation
   ```
5. Verify remote: `bank_audit_balance_sheet` has 0 rows with `amount_total=-6`
   or `item_name LIKE '%('`; failing partitions ≈ only the genuine-source set.

## Genuinely bad reports (cannot fix — flag only; see MISSING_AUDIT_DATA.md)
- Image-only / no text layer: ISCTR 2025Q1 cons; FIBA 2022Q1/2023Q3/2024Q1/2025Q3;
  TSKB 2025Q3 & 2026Q1 uncons.
- Source digits don't foot: EXIM 2024Q4; QNBFB 2022Q4; ODEA 2023Q4; TEB 2024Q4;
  BURGAN 2023Q2.
- No PDF published: KLNMA cons 2022Q1/2023Q1/2024Q1/2025Q1; ALNTF/EXIM/ISCTR 2026Q1.

## Remaining readable stragglers → use overrides (data/audit_overrides.json,
already seeded with EMLAK XIV / EMLAK cash ECL / BURGAN I). Loader override
support is NOT yet wired — that's the only code left to write for the readable
long tail; do it before step 3 if you want those included.
