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
   `scripts/diagnostics/profile_audit_corpus.py` records where each anchor appears; for a
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
9. New table = **six** registrations in the same change:
   `schema.py` DDL + `web/migrations/000X.sql` + `push_to_d1.SYNC_TABLES` +
   **`push_to_d1.fetch_recent` time-column mapping** +
   `backfill_extraction.AUDIT_TABLES` (catalogue failure-mode #6 — the
   missing time-column mapping silently skipped bank_audit_validation in
   every Phase-3 push: "no time column, skipped") + the naming rules in
   [SCHEMA_CONVENTIONS.md](SCHEMA_CONVENTIONS.md), enforced by CI's
   `scripts/check_schema_naming.py` for migrations ≥ 0022.

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

> **Engine:** new and changed extractors are **fitz (PyMuPDF) only** — ~60–85× faster
> per page. `pdfplumber` survives in exactly three places: the frozen balance-sheet /
> P&L `extractor.py`, `profiler.py`, and `src/faaliyet/extractor.py`. Don't extend it.
> Several lanes still carry *comments* mentioning pdfplumber artifacts (split digits,
> collapsed spaces); the repairs remain useful, the attribution is historical.

- **`/Rotate 90` pages garble everything — check `page.rotation` FIRST.** On a rotated
  page (GARAN/AKBNK landscape statements) fitz reports word bboxes in the page's
  **un-rotated** space, so y-clustering shreds the table into garbage and the text
  "looks corrupt" for no visible reason. Map each bbox through `page.rotation_matrix`
  into display space before clustering (`rotation_matrix` is the identity when
  `rotation == 0`, so the passing fleet pays nothing). See `extractor.py` (~L829) and
  `equity_change.py`. Diagnose this *before* suspecting the text layer.
- Dipnot refs `(6)` parse as −6; hierarchy tokens `1.1.4.` fragment into
  numbers; dates `31.12.2023` fragment into 3 tokens (QNBFB phantom header).
- Squished text layers drop ALL spaces (TSKB/QNBFB/ALBRK some quarters) —
  match with `\s*`, anchor on `_norm()` (A–Z only, Turkish-folded, digits
  stripped — "Tier 1"/"Tier I" both → TIER).
- **Column-split layouts** (a wide footnote table rendered so each *cell* lands
  on its own line in `extract_text()`, and the Total label sits a few px above
  its numbers — İşbank EN report, also ANADOLU/TSKB `loans_by_stage`). Line-mode
  text then yields a "Total" row with too few numbers and the row parser rejects
  it. Fix: **rebuild visual rows from word coordinates** — cluster fitz's
  `page.get_text("words")` (→ `x0, y0, x1, y1, word, block, line, word_no`) by the
  y-coordinate within a tolerance (~5–6px, under the row
  pitch) and feed the reassembled lines through the *same* parser as a fallback,
  only on a page carrying the table's anchor that parsed empty (the passing fleet
  pays nothing). Anchor on the table-specific header (the Stage-2 "Yakın
  İzlemedeki" / "Loans Under Close Monitoring" — the Stage-1 header often wraps
  and won't match). Pattern: `credit_quality._coord_clustered_lines` +
  `_extract_loans_by_stage_from_page`.
- Split-digit text layers detach leading digits ("5 86.339.528"); repaired in
  `extract_page_text_repaired`, but TSKB 2025 quarters are still damaged.
- Some PDFs have **no text layer** at all on statement pages (ISCTR 2025Q1
  consolidated) — unextractable by the deterministic pipeline; protect with `--skip`.
  These are then filled **out-of-band**: hand-transcribe via `scripts/load_partition.py`
  into `data/manual_statements.json` (56 overlays today; each BS validated to 0, each
  P&L cross-checked to BS equity). Cells the bank simply doesn't disclose go to
  `data/audit_not_disclosed.json` and render N/A. Census: [MISSING_AUDIT_DATA.md](MISSING_AUDIT_DATA.md).
- FC-only sub-tables shadow the total table (the NPL Stage-3 bug) — always
  check whether a matched block is a currency-restricted fragment.
- Prior-period columns may live in a separate table (EXIM §4) or as extra
  triplets on the same row (EXIM §2, first-triplets rule).
