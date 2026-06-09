# Audit-report extraction rework — plan

> Status: **approved direction, not yet implemented** (planned 2026-06-10 after
> the ECL/-6 incident, see PROJECT_STATE.md). Implement top-to-bottom; each
> phase is independently shippable and ends with docs updated.

## Why (the lesson this plan encodes)

The ECL bug corrupted 17 banks for ~4 years of quarters and was found by a
human comparing a screenshot to a PDF. The same dipnot-as-value bug had
already been found and fixed in `capital_adequacy.py` (see ATBANK in
AUDIT_BANK_CATALOG.md) but was never checked in the balance-sheet extractor.
Root cause wasn't a regex — it was working without a structural model of the
documents: no profile of how each bank files, and none of the BRSA statements'
internal arithmetic used as validation.

Principles adopted:

1. **Understand before parsing.** Profile the corpus programmatically; the
   catalogue is the working reference, consulted and updated with every
   extractor change.
2. **Identities over fingerprints.** BRSA tables are self-validating
   (TP+YP=Toplam; parent=Σchildren with "(-)" rows subtracting; TOTAL=Σromans;
   assets=liabilities+equity). Validate these at extraction time, every
   partition, forever — instead of writing a new fingerprint check after each
   incident.
3. **Profiles observe, identities gate.** Profiles are per-(bank, period)
   *observations* used for drift detection — they never drive parsing (a
   format change must degrade to an alert, not a hard dependency). If a bank
   suddenly changes format: either parsing still succeeds → sums pass → at
   most an informational drift note; or it misparses → sums fail → alert that
   week naming bank+quarter.
4. **Bank types are first-class.** Deposit / participation / dev-investment
   banks file different template variants (Toplanan Fonlar vs Mevduat, equity
   at XIV. vs XVI., no deposits at dev banks). The fleet is N template
   variants, not one template plus patches.
5. **The dashboard table stays constant (superset).** Every canonical line
   renders for every bank. Three distinguishable cell states: filed zero
   (`0`), line not in this bank's template variant (`—`), extraction/
   validation problem (`⚠`).
6. **Production history is repaired batchwise with evidence**, never in one
   `ALL` shot: dry-run → per-partition diff + validator report → user review →
   small batches, each verified, stop on regression.
7. **Build for the next extractor.** The same infra (profiling, anchors, text
   ops, identities, validation rows, catalogue entry) must be reusable for §5
   footnote extraction, which is the next goal.

---

## Phase 0 — Corpus census (read-only; no production writes)

**Goal:** machine-generated profile of every (bank, period, kind) PDF.

- New `src/audit_reports/profiler.py`: for each PDF in R2 record
  - document: language (TR/EN), page count, located section pages (§2 BS-A,
    BS-L, off-BS, P&L; §4.1/§4.6/§4.7; §5 footnote anchors), kind;
  - per statement: column structure (6 / 9 multi-period / P&L 2 vs 4), text
    class (spaced / squished), wrapped-row class, dipnot style (`(6)` /
    `(I-5)` / bare `5` / `5.1.5`), sign convention (paren-negative values?),
    roman inventory (which I.–XVI. present; equity numeral), grand-total row
    present + label, row count;
  - bank-type classification by template fingerprint (TOPLANAN FONLAR →
    participation; no deposit row → dev/investment), hand-verified once
    against a curated list in the catalogue;
  - **§5 footnote inventory** (forward-looking): which footnote tables exist
    per report (credit quality, loans by sector, NPL movement, FX position,
    maturity, fees, …) with page numbers — the map later footnote extractors
    start from.
- Output: `data/audit_profiles.json` (keyed bank|period|kind) + a generated
  census section in `docs/AUDIT_BANK_CATALOG.md` (script-regenerated between
  markers; rest of the file stays hand-curated).
- Profiling only locates pages + scans them (no full extraction) — fleet sweep
  is ~1–2 h at 8 workers.

**Done when:** census table in the catalogue covers all ~975 PDFs; bank-type
list verified; §5 inventory exists.

## Phase 1 — Structural validator (extraction-time, persisted)

**Goal:** every extraction validates the internal sums and stores the result.

- New `src/audit_reports/validator.py` (pure functions over extracted rows —
  importable without pdfplumber so CI's minimal-deps job can test it):
  - **V1 row**: cur_tl + cur_fc = cur_total (and prior triplet), tolerance
    ±2 thousand for rounding; skipped when components missing.
  - **V2 hierarchy**: parent = Σ children, "(-)"-labelled children subtract
    (sign-aware: paren-negative banks like ING/KLNMA already store negatives —
    then they add). Each parent: pass / fail / skipped (no children captured).
  - **V3 statement**: TOTAL row = Σ romans (when total row present).
  - **V4 cross-statement**: total assets = total liabilities + equity (≤0.5%).
  - P&L identities deferred to a later pass (sign conventions messier; start
    with the balance sheet where the incident happened).
- New table `bank_audit_validation` (bank, period, kind, statement,
  checks_passed/failed/skipped, failed_detail JSON, validated_at):
  `schema.py` + D1 migration + `push_to_d1.SYNC_TABLES` + `--only-tables` +
  `backfill_extraction.AUDIT_TABLES` (catalogue failure-mode #6 — all four
  places, same change).
- Wire into the extraction pipeline (`loader.upsert_report`) so cron and
  backfill both produce validation rows. `check_audit_quality.py` gains a
  `structure` check that alerts on failed partitions; existing fingerprint
  checks stay.
- **Drift check**: compare this quarter's profile vs the bank's previous
  quarter (language, ncols, dipnot style, text class, row-count band) →
  info-level list in the same alert.
- Tests: validator unit tests over JSON row fixtures (recorded from real
  extractions: ALBRK clean, the old corrupted ALBRK rows as a must-fail case,
  ING paren-negative, EXIM multi-period).

**Done when:** a local full-DB validation run reports pass/fail per partition
and the known-bad cases fail loudly while clean banks pass.

## Phase 2 — Fleet dry-run + evidence report (still no production writes)

- Re-extract ALL banks locally (`backfill_extraction.py --dry-run` semantics)
  with the fixed extractor; for each partition produce old-vs-new: row counts,
  grand totals, net income, validator pass-rate, changed line items.
- Calibrate validator tolerances on the real corpus (expected discoveries:
  TSKB split-digit damage, AKBNK detached liabilities total, EXIM prior-period
  nulls — all should land in "needs investigation", not crash).
- Output `data/backfill_evidence/` (JSON + a readable report.md) bucketing
  partitions: **improved / unchanged / regressed / investigate**.
- **User reviews the report and approves batches.** Nothing is pushed in this
  phase.

## Phase 3 — Batchwise history repair (production, gated)

- Push approved banks in batches of 3–5 via `backfill_extraction.py --banks`
  (R2 snapshot history backup before each batch; D1 partition-clear semantics
  already exist).
- After each batch: remote D1 spot-verification (targeted queries + quality
  checks incl. `structure`) appended to the evidence report. **Stop on any
  regression.**
- Order: the ~15 corrupted banks first (clear improvement), then row-recovery
  banks (GARAN-class), TSKB last (needs its own fix first).
- CI alternative: `backfill-audit.yml` in 5-bank chunks (ALL exceeds the
  180-min job limit — already documented in the catalogue).

## Phase 4 — Dashboard mapping + display states

- `web/app/lib/standard_lines.ts`: per-bank-type template maps become explicit
  (asset variants too if the census shows any, alongside the existing
  participation liabilities variant); matching prefers labels with numeral
  fallback (extends the #57/#50 direction).
- Cell states in the constant table: `0` = filed zero; `—` = line absent from
  this bank's template variant (known from the census/type, not guessed);
  `⚠` = the partition (or line) failed validation — tooltip with the failed
  identity, data from `bank_audit_validation` in D1. This closes the
  "dashboard shows corrupted quarters identically to clean ones" gap.
- `/admin`: per-bank validation pass-rate table.
- ECL sign normalization at display: contra-asset "(-)" lines render with a
  consistent sign convention regardless of how the bank prints them (storage
  stays faithful to the filing).

## Phase 5 — Reusable foundation for §5 footnote extraction

- Mechanical refactor (after history repair, so the ground is stable):
  shared `textops.py` (page-text repair, squish handling, NUM_PAT + dipnot
  token rules, wrapped-row merging) and `locate.py` (anchor-based section
  location) extracted from `extractor.py`; section extractors import them
  instead of carrying copies — so a bug fixed once is fixed everywhere
  (the lesson of the dipnot bug existing in two extractors).
- New-extractor checklist documented in `docs/AUDIT_EXTRACTION_GUIDE.md` (the
  durable reasoning output):
  1. read the catalogue; 2. profile the target table across the fleet
  (census-style sweep of §5 anchors); 3. write the table's identities FIRST
  (every footnote table has them: stages sum to totals, sector rows sum,
  NPL movement opening+inflows−outflows=closing); 4. extractor; 5. validator
  wiring; 6. tests incl. must-fail fixtures; 7. catalogue + census update;
  8. history backfill through the Phase-2/3 evidence flow.

---

## Cross-cutting rules

- Catalogue/docs updated in the same change as any extractor work.
- Validator/profiler test modules must import under CI's minimal deps (no
  top-level pdfplumber imports in anything tests touch).
- Every phase lands on master as its own commit series; production data is
  only touched in Phase 3 and only batchwise with the evidence report.

## Open decisions (flag during implementation)

- Tolerances: ±2 thousand absolute vs 0.1% relative for V2/V3 — calibrate in
  Phase 2, record chosen values in the catalogue.
- Whether `⚠` badges show at period (column) level only, or per cell when the
  failed identity implicates a specific line.
- Where profiles live long-term: `data/audit_profiles.json` snapshot vs a D1
  table (D1 needed only if the dashboard reads them; start with JSON).
