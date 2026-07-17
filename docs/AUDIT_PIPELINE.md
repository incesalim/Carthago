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
   **Delta-based:** it diffs the current anomaly set against a baseline in R2
   (`state/audit_anomaly_baseline.json`) and pings ONLY on new/resolved anomalies — so a
   routine run or a single-cell re-extract that changes nothing stays silent (the standing
   backlog isn't re-blasted). First run seeds the baseline quietly; an R2 error falls back
   to a full-list alert.
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

Two independent fields, routinely confused — keep them apart:

- **`section`** — which Bölüm of the filing the table is printed in. Pure provenance,
  and the only field that says *primary statement* vs *note*. The /admin matrix groups
  its lanes on this.
- **`is_core`** — a **severity** flag: "an empty lane here means the extraction failed,
  so fail the whole report". It gates `bank_audit_extractions.success` and nothing else.
  True for exactly three lanes (BS assets, BS liabilities, P&L). `is_core=False` types
  surface `error`/`missing` cells in the matrix but never flip `success`.

`is_core=False` is **not** a demotion to footnote status. OCI, changes-in-equity,
cash-flow and off-balance are all §2 primary statements — TAS 1 requires the first three
in any complete set, and off-balance ("Nazım Hesaplar Tablosu") prints on the
balance-sheet page — but one unreadable note-page shouldn't discard a good BS+P&L
extraction, so none of them gates `success`. Grouping the matrix on `is_core` is what
labelled those four "Footnotes & §4" until 2026-07-17 (`section` was added to fix it).

All types with `has_validator=True` write a `bank_audit_validation` row keyed by their
`validation_statement`.

| Type | Table | `section` | `is_core` | Validator (`validation_statement`) |
|---|---|---|---|---|
| Balance sheet — assets | `bank_audit_balance_sheet` (statement='assets') | §2 | ✓ | structural: TL+FC=Total, parent=Σchildren, Σromans=TOTAL, assets=liab+equity (`assets`) |
| Balance sheet — liabilities | `bank_audit_balance_sheet` (statement='liabilities') | §2 | ✓ | structural: TL+FC=Total, parent=Σchildren, Σromans=TOTAL; A=L+E cross-check (`liabilities`) |
| Off-balance sheet | `bank_audit_balance_sheet` (statement='off_balance') | §2 | — | TL+FC=Total row triplets only; hierarchy-sum skipped (off-balance uses I./II./III. top-level with non-contiguous 1.x sub-items) (`off_balance`) |
| Income statement (P&L) | `bank_audit_profit_loss` | §2 | ✓ | identity chain + net = BS equity 16.6.2 / 14.6.2 (`profit_loss`) |
| Other comprehensive income (OCI) | `bank_audit_oci` | §2 | — | `III = I + II`; 2.x subtree sums; **OCI row I = P&L net** (`oci`) |
| Statement of changes in equity | `bank_audit_equity_change` | §2 | — | row-sum (total_equity≈Σ13 cols); col chain III=I+II, closing=III+IV+…+XI; OCI cross (IV.total==OCI.III); BS equity cross (0.5% tol); opening==prior-closing Q4 only (`equity_change`) |
| Cash flow statement | `bank_audit_cash_flow` | §2 | — | hierarchy subtree sums; roman chain **V=I+II+III+IV**, **VII=V+VI** (`cash_flow`) |
| Credit quality / IFRS-9 | `bank_audit_credit_quality` | §5 | — | per-section total=S1+S2+S3; coverage∈[0,1]; cross-section reconciliations (`credit_quality`) — note: gross−prov=net check removed (BRSA provision rows include collective reserves) |
| IFRS-9 stages (derived) | `bank_audit_stages` | §5 | — | total_ecl=ΣSx_ecl; coverage∈[0,1]; **stage3==total fingerprint** (`stages`) |
| Loans by sector | `bank_audit_loans_by_sector` | §5 | — | Σ top-level sectors ≈ total row; falls back to sub-sector sums when group aggregate (agri_total/mfg_total/svc_total) is absent (`loans_by_sector`) |
| NPL movement | `bank_audit_npl_movement` | §5 | — | opening±flows=closing (0.2% + 100 tol); row skipped when write_offs/sold/transfers_out is NULL (column not extracted) (`npl_movement`) |
| Free provision (serbest karşılık) | `bank_audit_free_provision` | §5 | — | none per-partition **by design** — `conditional=True` routes an empty partition to `not_expected` before any verdict is read, so its checks are corpus-wide and live in `check_audit_quality._free_provision` |
| Capital adequacy (§4) | `bank_audit_capital` | §4 | — | CET1≤Tier1≤Total; CAR=capital/RWA ±2pp; band [5,80] (`capital`) |
| Liquidity (§4) | `bank_audit_liquidity` | §4 | — | leverage∈(0,30); LCR/NSFR∈(0,2000); LCR≥50 (`liquidity`) |
| FX net open position (§4) | `bank_audit_fx_position` | §4 | — | current period only: Σ per-currency rows = TOTAL (assets, liab, net BS, net off, net position); net BS = assets−liab; net position = net BS + net off (`fx_position`) |
| Interest-rate repricing gap (§4) | `bank_audit_repricing` | §4 | — | Σ per-bucket rows = total (RSA, RSL, gap); **total RSA = total RSL** (the schedule foots to the BS); skips for participation banks that don't disclose it (`repricing`) |
| Bank profile (branches/personnel) | `bank_audit_profile` | §1 | — | no footing exists in a table of counts, so the checks are cross-kind/cross-field: **cons ≥ unco** on branches+personnel (a group contains its parent — arithmetic, not heuristic), branches-split vs the counterpart, personnel≠branches column-slip, row non-empty (`profile`) |
| Audit opinion | `bank_audit_opinion` | §7 | — | definitional, not arithmetic: auditor name present (every BRSA report is signed); ISA 705 "Basis for Qualified Opinion" present whenever the opinion is modified (`audit_opinion`) |

**Known false-positive skip-list** (stored in `revalidate_audit_db.py`):
`_CAP_SKIP_BANKS` — ATBANK (all periods/kinds): systematic BRSA regulatory-floor CAR override.
`_CAP_SKIP` — TEB 2022Q1–Q4 consolidated: same reason, narrower scope.
Capital validation is **skipped** (not red) for these entries.

`bank_audit_extractions` logs one row per PDF (`success`, per-statement row counts, `note`,
`extracted_at`). `bank_audit_validation` stores per-statement check results
(`checks_passed/failed/skipped`, `failed_detail` JSON).

## Repair playbook
Use this when the cron extraction is wrong or a statement page is unreadable. Every path
**validates the partition to 0 before pushing** and clears the D1 partition before re-push.
A worked example of the manual-transcription path at scale is the 2026-06-12 balance-sheet
ECL fix, recorded in [RESUME_AUDIT_FIX.md](RESUME_AUDIT_FIX.md).

The quickest entry for a single bad cell is the **/admin coverage matrix**: click the cell
→ **Force re-extract this cell** dispatches `reextract-statement.yml` for just that
`(bank, period, kind, statement)` with `--force` — it overwrites that one statement even if
it currently passes, while broad/fleet re-extracts keep the non-destructive guard. It's the
UI form of step 2's targeted re-extract. For a deterministic BS/P&L Δ, prefer step 4 (cell
override): a re-extract reproduces the same rows, so it won't move the discrepancy.

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
   `bank_audit_validation` from stored rows (all 12 statement types, no re-extraction); push
   with `scripts/push_to_d1.py --db <db> --hours 9999 --only-tables bank_audit_validation`.

After any repair, confirm on D1: `bank_audit_validation` failing partitions and the
`/admin` coverage matrix should reflect the fix; `bank_audit_extractions.success` flips to 1
once assets/liabilities/P&L each have ≥20 rows.

## Genuinely unfixable inputs
Reports the bank publishes as scans with no text layer (or that don't foot in the source)
are tracked in [`docs/MISSING_AUDIT_DATA.md`](MISSING_AUDIT_DATA.md). The no-OCR rule binds
the **automated extractors** — they stay deterministic and never guess. Such reports are
filled out-of-band by manual transcription (step 5) into `data/manual_statements.json`, which
*may* use OCR as an authoring aid (`scripts/archive/ocr_statement.py`) because a human
validates every figure before it lands; or they are left flagged. Cells the bank genuinely
doesn't disclose belong in `data/audit_not_disclosed.json` (rendered N/A), not here.
