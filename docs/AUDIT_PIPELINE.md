# Audit lane — pipeline & repair playbook

How BRSA quarterly audit reports become `bank_audit_*` rows in D1, and how to fix them.
The audit lane is independent (own staging DB `data/bank_audit.db`, own R2 snapshot
`state/bank_audit.db.gz`, own concurrency group `bddk-audit`) and writes a disjoint set of
D1 tables, so it can run in parallel with the bulletin lane. See
[`docs/ARCHITECTURE.md`](ARCHITECTURE.md) for the lane model and [`scripts/README.md`](../scripts/README.md)
for the full script index.

## The weekly path (`.github/workflows/refresh-audit.yml`, Sun 04:00 UTC)
1. **Pull snapshot** — download `state/bank_audit.db.gz` → `data/bank_audit.db`
   (first run only: `seed_audit_db.py` bootstraps from the bulletin snapshot).
2. **`sync_audit_reports.py`** — scrape any newly published PDFs to R2
   (`bddk-audit-reports/<ticker>/<TICKER>_<period>_<kind>.pdf`), then extract every PDF that
   isn't already in `bank_audit_extractions` → `bank_audit.db`. 49/52 weeks this is a cheap
   no-op. Flags: `--only-bank`, `--periods`, `--latest-period`, `--no-scrape`, `--workers`.
3. **`build_bank_audit_stages.py`** — roll the per-section `bank_audit_credit_quality` rows up
   into the derived `bank_audit_stages` view (S1/S2/S3 amounts + ECL + coverage).
4. **`check_audit_quality.py --alert`** — 8 alert-only anomaly checks (never blocks): stale
   period, balance, coverage, npl_drop, capital, liquidity, structure, ecl → Telegram/Discord.
5. **`sync_audit_expected.py`** — refresh the coverage spine (`bank_audit_expected`,
   `bank_audit_statement_types`, `bank_audit_coverage`) for the `/admin` matrix.
6. **`push_to_d1.py --db data/bank_audit.db --only-tables bank_audit_*`** — sync to D1.
7. **Snapshot** — VACUUM + gzip → upload `state/bank_audit.db.gz` (+ dated history, keep 7).

The R2 snapshot is **last-writer-wins**, so any out-of-band write must guard against a
concurrent CI run (`d1_sync._guard_against_ci_writers()`) and the manual lanes write D1 + the
local DB only where possible.

## Statement types (each is a registry entry — `src/audit_reports/registry.py`)
| Type | Table | Validator |
|---|---|---|
| Balance sheet — assets / liabilities / off-balance | `bank_audit_balance_sheet` (`statement` col) | structural (TL+FC=Total, parent=Σchildren, Σromans=TOTAL, assets=liab+equity) |
| Income statement (P&L) | `bank_audit_profit_loss` | structural identity chain + net = BS equity 16.6.2 / 14.6.2 |
| Credit quality / IFRS-9 stages | `bank_audit_credit_quality` → `bank_audit_stages` | plausibility (`check_audit_quality`) |
| Loans by sector | `bank_audit_loans_by_sector` | — |
| NPL movement | `bank_audit_npl_movement` | — |
| Capital adequacy (§4) | `bank_audit_capital` | plausibility |
| Liquidity (§4) | `bank_audit_liquidity` | plausibility |
| Bank profile (branches/personnel) | `bank_audit_profile` | — |

`bank_audit_extractions` logs one row per PDF (`success`, per-statement row counts, `note`,
`extracted_at`). `bank_audit_validation` stores per-statement check results
(`checks_passed/failed/skipped`, `failed_detail` JSON).

## Repair playbook
Use this when the cron extraction is wrong or a statement page is unreadable. Every path
**validates the partition to 0 before pushing** and clears the D1 partition before re-push.

1. **Diagnose** — `scripts/diagnostics/diag_partition.py BANK PERIOD KIND` dumps the stored
   rows + raw PDF lines and shows which identity breaks.
2. **Extractor bug (affects many partitions)** — fix the extractor, then gate the fix:
   - `scripts/fleet_evidence.py --only … --periods …` re-extracts to `fleet_scratch.db` and
     buckets improved/unchanged/**regressed**. Require `regressed: 0`.
   - `scripts/backfill_extraction.py --banks …` (or `backfill-audit.yml` in 5-bank chunks —
     never `banks=ALL`, it exceeds the 180-min job timeout) pushes the re-extracted rows.
3. **One partition's P&L is garbled (e.g. letter-spacing)** —
   `scripts/audit_correct.py reextract-pl --bank … --period … --kind …`.
4. **A few cells are wrong but the value is legible (OCR artifact / digit typo)** — add to
   `data/audit_overrides.json`, then `scripts/audit_correct.py override-cells` (forced by the
   report's own subtotals; supports positional insert for dropped rows).
5. **A statement PAGE is a scanned image (no text layer)** — hand-transcribe it into
   `data/manual_statements.json` (assets/liabilities/off_balance use `{h,name,tl,fc,total}`;
   P&L uses `{h,name,amount}`; include the `TOTAL` row), then
   `scripts/audit_correct.py overlay-statement --bank … --period … --kind …` — it re-extracts
   the text statements and overlays the manual ones. The balance sheet is validated to 0 and
   the P&L net is cross-checked to BS equity before push.
6. **Validator logic changed** — `scripts/revalidate_all.py` recomputes
   `bank_audit_validation` from stored rows (no re-extraction) and pushes validation only.

After any repair, confirm on D1: `bank_audit_validation` failing partitions and the
`/admin` coverage matrix should reflect the fix; `bank_audit_extractions.success` flips to 1
once assets/liabilities/P&L each have ≥20 rows.

## Genuinely unfixable inputs
Reports the bank publishes as scans with no text layer (or that don't foot in the source)
are tracked in [`docs/MISSING_AUDIT_DATA.md`](MISSING_AUDIT_DATA.md). Under the no-OCR rule
these are filled only by manual transcription (step 5) or left flagged.
