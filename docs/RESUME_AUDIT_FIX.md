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
