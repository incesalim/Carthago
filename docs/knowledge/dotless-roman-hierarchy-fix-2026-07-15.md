# Dotless-roman hierarchy keys — root cause & durable fix

**Date:** 2026-07-15 · **Status:** FIXED (data backfilled to D1 + R2; canonicalizer patched) · **Memory:** `reference_trailing_dot_hierarchy` (GOTCHA 4), `reference_roe_ttm_definition`

## Trigger
"Why does Eximbank lack Cost/Income for some periods?" (asked right after Cost/Income
moved to a TTM basis — see `reference_roe_ttm_definition`).

## Root cause
The BRSA standard stores top-level P&L / balance-sheet lines under **dotted roman**
codes (`I.`, `VIII.`, `XI.`…). A handful of banks' source PDFs print a roman code
**without** its trailing dot, and the extractor captures it verbatim as `XI` / `I` /
`V`. The per-bank Financials table and the cross-bank heatmap (`web/app/lib/heatmap.ts`)
key on the **exact** dotted code, so a dotless roman silently drops out.

Two visible symptoms:
- **EXIM Cost/Income** — Personnel Expenses (`XI.`) was dotless (`XI`) for 2024Q2 &
  2024Q3, so `opex = MAX(XI.) + MAX(XII.)` read null. Because Cost/Income is now TTM,
  a single missing quarter blanks every trailing-twelve-month window that overlaps it
  → Cost/Income (and PPOP) blank across **2024Q2 → 2025Q3**, recovering 2025Q4.
- **ALNTF total_assets** — Financial Assets (`I.`, the largest asset line) was dotless
  (`I`) for **6 quarters** → dropped from `total_assets = Σ romans I.–X.` → assets
  **understated 40–51%** (a fake ~40% q/q crater; 2025Q4 read ₺83.5bn vs true ₺118.5bn).

This is exactly the failure GOTCHA 3 (VAKBN roman `VI`, 2026-07-04) warned about but
only patched at the pl-sankey read layer.

## Scope (fleet audit)
Pure-roman dotless rows in the catalog-displayed statements:
- **Balance sheet — 60 rows:** ALNTF assets `I` (Financial Assets), EMLAK assets
  `VIII` (Current Tax Asset), TOMK/ZIRAATK liabilities `X` (Deferred Tax Liability,
  participation catalog). All map cleanly; no collisions.
- **P&L — 329 rows across 14 banks:** `V` (Dividend Income ×142), `VI` (Net Trading),
  `XI` (Personnel), `XIV` (merger surplus), `XVIII` (Tax), `XXII/XXIII/XXIV`
  (discontinued-ops). Two **excluded**:
  - `X` (28 rows) — a post-merger income line mis-keyed `X` where the real `X.`
    (Other Provisions) already exists → **collision** (dotting would duplicate).
  - TOMK 2023Q3 `XI` (1 row) — content is *Other Operating Expenses* (semantically
    `XII.`), not personnel → **semantic mislabel**.
- **Safe set = 360 rows** (BS 60 + PL 300).

## Fix
1. **Durable (write-time):** `loader._canon_hier` now ADDS a trailing dot to a bare
   all-roman code (`_HIER_BARE_ROMAN = ^[IVXLCDM]+$`), the mirror of the existing
   numeric-dot strip. Only for `{assets, liabilities, profit_loss}`; off_balance /
   oci / cash_flow untouched. Unit-tested in `tests/test_canon_hier.py`.
2. **Backfill (existing data):** `scripts/normalize_roman_hierarchy.py` dots the safe
   set in the R2 master snapshot AND live D1 (idempotent, `--dry-run`). Two guards:
   a **collision** guard (skip when a dotted twin exists → excludes PL `X`) and a
   **semantic** guard (skip PL `XI` whose item name is Other Operating Expenses →
   excludes TOMK). Applied: 360 rows written.

Values are never touched — this is a KEY normalization, so it respects the
BS/PL-frozen rule (`feedback_bs_pl_frozen`).

## Verification
- Remaining bare-roman rows: PL 29 (28 `X` + 1 TOMK `XI`, correctly excluded), BS 0.
- EXIM `XI.` present for 2024Q2 (1,205,108) & 2024Q3 (1,858,128) → opex computes.
- ALNTF total_assets 2025Q4 = ₺118.5bn (was ₺83.5bn), matches filed "VARLIKLAR TOPLAMI".
- No new duplicate-hierarchy groups (collision guard + intra-set dups = 0).
- BS validation unaffected (parent=Σchildren reconciles on values, not the dotted
  key) → `/admin` coverage spine already correct, no re-sync needed.

## Duplicate / junk hierarchy rows — cleaned (follow-on, same day)

The dotless-roman audit surfaced a second class: **75 duplicate `(bank, period, kind,
hierarchy)` groups** (57 P&L + 18 BS). `scripts/dedup_hierarchy_rows.py` resolved them
(data-only; values deleted or KEY re-coded, never edited), verified by re-running the
validator on the corrected rows (all 7 previously-failing partitions flipped to PASS):

- **Header/placeholder JUNK — 59 P&L rows DELETED.** A statement title ("STATEMENT OF
  PROFIT OR LOSS", "KAR VEYA ZARAR TABLOSU") or a template placeholder
  ("…doldurulacaktır.)") mis-parsed as a data row with a garbage amount (≤202) on a real
  line's roman code. Tight title/placeholder match, `|amount| < 1000` guard; verified 0
  real values removed. (Benign for the heatmap — it used `MAX` — but wrong in the
  per-bank statement table.)
- **Mis-numbered real rows — 26 re-coded.** Two real lines collided on one code because
  the lower section was extracted a numeral short/shifted; the ARABIC sub-codes (18.1,
  20.1, 23.1…) + P&L arithmetic gave the true numbers. TSKB 2025Q1–Q3 Current Tax
  `VII.→VIII.`; TOMK 2025Q2/Q3 tax `XVII.→XVIII.` / disc-tax `XXII.→XXIII.`; DUNYAK
  2023Q4 shifted IX/XI/XII/XIII; TOMK 2023Q3 whole lower section `+1`. These were
  FAILING `pl_chain`; the recode **cleared real validation failures**.
- **NOT touched — EXIM/VAKBN off_balance (15 rows).** Forward-Sell `3.2.2.2` /
  "Diğer Cayılamaz Taahhütler" `2.1.12` — a known SOURCE typo in the filed PDFs,
  previously hand-checked and **deliberately leave-flagged** (fidelity to source; the
  off_balance validator already accepts it). Left as-is on purpose.

Result: P&L dups 57→0, BS dups 18→15 (the 15 = the left off_balance). Validation +
coverage spine refreshed via `sync_audit_expected.py --push`; D1 + R2 snapshot in sync.

## Follow-ups (NOT done)
- **KV cache lag:** heatmap queries are KV-cached ~12h (`cachedAll`); the UI reflects
  the fixes within ≤12h or on next deploy.
- **DUNYAK 2023Q4** still fails capital / liquidity / stages validators (pre-existing,
  unrelated to hierarchy dups — different check families).
