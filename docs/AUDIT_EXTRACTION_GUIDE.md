# Adding or changing an audit-report extractor — the checklist

> The durable lessons from the 2026-06 ECL incident and the audit rework
> (AUDIT_REWORK_PLAN.md). Follow this for every §5 footnote table we add and
> every change to the existing §2/§4 extractors. The pattern is: understand →
> identities first → extract → validate → evidence → repair.

## Before writing any code

1. **Read `AUDIT_BANK_CATALOG.md`** — the format census (auto-generated from
   `data/audit_profiles.json`) tells you each bank's language, text class
   (spaced/squished), dipnot style (`(6)` / `(I-5)` / `(5.1.5)` / bare), sign
   convention (paren-negative banks store contra values negative), column
   layout (EXIM 9-col), and which §4/§5 tables exist per report with page
   numbers (`anchors` in the profiles JSON).
2. **Profile the target table across the fleet** before assuming a layout:
   `scripts/profile_audit_corpus.py` records where each anchor appears; for a
   new footnote table, add its anchor needles to
   `src/audit_reports/profiler.py:FOOTNOTE_ANCHORS` and re-run the sweep —
   that yields coverage (which banks/quarters have it) and page locations for
   free, before any parsing exists.
3. **Write the table's identities FIRST.** Every BRSA table has internal
   arithmetic. Balance sheet: TL+FC=Total per row, parent = Σ direct children
   ("(-)" rows contribute −|x|), TOTAL = Σ romans, assets = liabilities +
   equity. Credit-quality stages: S1+S2+S3 = Total. NPL movement: opening +
   inflows − outflows = closing. Sector table: Σ sectors = total row. If you
   can't state the identities, you don't understand the table yet — stop and
   read more filings (one per bank type: deposit, participation,
   dev/investment).

## Implementation rules

4. Parse with anchors + labels, never positions alone; numerals shift across
   bank types and when banks omit template rows.
5. Number tokens: reuse `extractor.NUM_PAT` and its helpers — they already
   handle TR/EN formats, standalone dashes vs `(-)` label decorations,
   hierarchy-marker exclusion and dipnot refs. **Never count footnote refs or
   the row's own numbering as values** (the −6 bug, twice).
6. A row you can't parse confidently is **skipped, not guessed** — better
   lost (the parent's sum check flags it) than corrupted (nothing flags it).
7. Wire validation: extend `src/audit_reports/validator.py` with the new
   table's identity checks, persist to `bank_audit_validation` via the loader,
   and let `check_audit_quality.py --alert` carry it (`structure` check).
8. Tests: fixture-based, including **must-fail fixtures** (a corrupted row the
   validator must catch), importable under CI's minimal deps (no top-level
   pdfplumber in test modules — `pytest.importorskip`).
9. New table = four registrations in the same change:
   `schema.py` DDL + `web/migrations/000X.sql` + `push_to_d1.SYNC_TABLES` +
   `backfill_extraction.AUDIT_TABLES` (catalogue failure-mode #6).

## Shipping

10. **Evidence before production**: `scripts/fleet_evidence.py` re-extracts
    into a scratch DB and buckets every partition
    improved/unchanged/investigate/regressed vs production. The user reviews
    `data/backfill_evidence/report.md` before any push.
11. **Repair batchwise**: `scripts/run_phase3_batches.py` (3–5 banks per
    batch, verification gate between batches, abort on regression). Protect
    unextractable partitions with `backfill_extraction.py --skip
    BANK:PERIOD:KIND`.
12. Update `AUDIT_BANK_CATALOG.md` quirks + regenerate the census in the same
    change; update PROJECT_STATE.md. Docs are part of "done".

## Known traps (each cost us once)

- Dipnot refs `(6)` parse as −6; hierarchy tokens `1.1.4.` fragment into
  numbers; dates `31.12.2023` fragment into 3 tokens (QNBFB phantom header).
- Squished text layers drop ALL spaces (TSKB/QNBFB/ALBRK some quarters) —
  match with `\s*`, anchor on `_norm()` (A–Z only, Turkish-folded, digits
  stripped — "Tier 1"/"Tier I" both → TIER).
- Split-digit text layers detach leading digits ("5 86.339.528"); repaired in
  `extract_page_text_repaired`, but TSKB 2025 quarters are still damaged.
- Some PDFs have **no text layer** at all on statement pages (ISCTR 2025Q1
  consolidated) — unextractable without OCR; protect with `--skip`.
- FC-only sub-tables shadow the total table (the NPL Stage-3 bug) — always
  check whether a matched block is a currency-restricted fragment.
- Prior-period columns may live in a separate table (EXIM §4) or as extra
  triplets on the same row (EXIM §2, first-triplets rule).
