# Audit lane — pipeline & repair playbook

How BRSA quarterly audit reports become `bank_audit_*` rows in D1, and how to fix them.
The audit lane is independent (own staging DB `data/bank_audit.db`, own R2 snapshot
`state/bank_audit.db.gz`, own concurrency group `bddk-audit`) and writes a disjoint set of
D1 tables, so it can run in parallel with the bulletin lane. See
[`docs/ARCHITECTURE.md`](ARCHITECTURE.md) for the lane model and [`scripts/README.md`](../scripts/README.md)
for the full script index.

## Two lanes: ACQUISITION is automated, EXTRACTION is managed by hand
Only **acquisition** (getting new PDFs into R2) runs on a schedule. **Extraction** (turning
PDFs into `bank_audit_*` rows) is triggered manually from `/admin` — review the coverage matrix
after. Both share the `bddk-audit` concurrency group, so they never run at the same time.

### Acquisition (`.github/workflows/acquire-audit.yml`, Sun 04:00 UTC)
1. **Pull snapshot, read-only** — download `state/bank_audit.db.gz` → `data/bank_audit.db`
   (first run: `seed_audit_db.py` bootstraps from the bulletin snapshot). Needed only so the
   coverage refresh below has accurate row counts; this job **never re-uploads the snapshot**.
2. **`sync_audit_reports.py --no-extract`** — discover + scrape any newly published PDFs to R2
   (`<ticker>/<TICKER>_<period>_<kind>.pdf`), via `audit_report_urls.json` + live
   `discover_targets()`. No extraction. `--new-count-file` records how many were new.
3. **`sync_audit_expected.py --push`** — rebuild the coverage spine so freshly-acquired PDFs
   appear in the matrix as **missing + pdf_present** ("acquired, not yet extracted"). The
   expected universe is `audit_profiles.json` **∪ the R2 PDF list**, so a brand-new quarter
   shows up even before the profile census is regenerated.
4. **Notify** — if any new PDFs landed, ping Telegram so an admin knows to extract them.

### Extraction (`.github/workflows/refresh-audit.yml`, dispatch-only)
Triggered from `/admin` (Pipeline "Extract audit reports" card, or the coverage matrix's
per-cell **Re-extract**). No schedule.
1. **Pull/seed snapshot** → `data/bank_audit.db`.
2. **`sync_audit_reports.py`** — extract PDFs from R2 not already in `bank_audit_extractions`
   (or a forced re-extract). Flags: `--only-bank`, `--periods`, `--latest-period`,
   `--no-scrape`, `--force`, `--workers`. The matrix's per-cell re-extract dispatches
   `bank` + `period` → `--periods YYYYQn --force --no-scrape` (re-runs one quarter).
3. **`build_bank_audit_stages.py`** — derive the `bank_audit_stages` view (S1/S2/S3 + ECL).
4. **`revalidate_audit_db.py`** — recompute `bank_audit_validation` corpus-wide from stored
   rows so the matrix + `/banks` badges reflect the current validator everywhere.
5. **`check_audit_quality.py --alert`** — alert-only anomaly checks → Telegram/Discord.
6. **`push_to_d1.py --only-tables bank_audit_*`** — windowed sync of the row tables +
   `bank_audit_validation` to D1.
7. **`sync_audit_expected.py --push`** — rebuild the coverage spine (full D1 push, no R2 write).
8. **Snapshot** — VACUUM + gzip → upload `state/bank_audit.db.gz` (+ dated history, keep 7).
   This is the **only** job that writes the snapshot.

A `missing` matrix cell with a PDF present is told apart in the drawer by whether the partition
has any `bank_audit_extractions` row: **none** → "acquired, not yet extracted" (click
Re-extract); **present but this statement empty** → likely a scanned-image page (hand-transcribe
via `audit_correct.py overlay-statement`).

The R2 snapshot is **last-writer-wins**, so any out-of-band write must guard against a
concurrent CI run (`scripts/audit_d1.guard_against_ci_writers()`) and the manual lanes write D1 + the
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
6. **Validator logic changed** — `scripts/revalidate_audit_db.py --db <db>` recomputes
   `bank_audit_validation` from stored rows (balance sheet + P&L, no re-extraction); push
   with `scripts/push_to_d1.py --db <db> --only-tables bank_audit_validation`.

After any repair, confirm on D1: `bank_audit_validation` failing partitions and the
`/admin` coverage matrix should reflect the fix; `bank_audit_extractions.success` flips to 1
once assets/liabilities/P&L each have ≥20 rows.

## Genuinely unfixable inputs
Reports the bank publishes as scans with no text layer (or that don't foot in the source)
are tracked in [`docs/MISSING_AUDIT_DATA.md`](MISSING_AUDIT_DATA.md). Under the no-OCR rule
these are filled only by manual transcription (step 5) or left flagged.
