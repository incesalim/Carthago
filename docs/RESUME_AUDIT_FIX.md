# AUDIT BALANCE-SHEET FIX — FINAL STATE (2026-06-11, updated)

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
