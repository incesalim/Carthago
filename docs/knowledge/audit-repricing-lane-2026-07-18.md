# Interest-rate repricing lane → 0 error / 0 missing

**Status: COMPLETE 2026-07-18.** Coverage `787 ok / 16 manual / 247 N/A / 0 err / 0 miss`
(from 5 err + 26 miss, plus 66 green-but-incomplete the strengthened validator surfaced).

## Validator strength (the first question)

`check_repricing` had two INTERNAL identities — `rp_footing` (Σ buckets = total, for RSA/RSL/gap)
and `rp_balance` (total RSA = total RSL, which holds because equity sits in the non-sensitive
liability bucket) — both of which **skip an absent field**. Assessment:

- **Stronger than fx's old check.** A dropped bucket *row* breaks Σ=total → caught (it flagged
  the 5 real errors). `gap` is a separately-reported figure, NOT RSA−RSL (AKBNK's bucket gap ≠
  RSA−RSL), so a per-bucket gap=RSA−RSL check would false-fail — not added.
- **Cross-period is clean: 0 mismatch / 584 pairs.** Repricing's prior column is faithfully
  extracted (prior total = prior year-end everywhere), so a cross-period anchor finds nothing.
- **Blind spot: 70 green partitions had a dropped whole COLUMN** — the extractor never matched the
  liabilities row (59) or the position/gap row (7), so the footing checks silently skipped them and
  the partition read green on the assets footing alone (ATBANK's entire gap column NULL, yet green).
  Concentrated in the non-standard-bucket banks (ZIRAAT 34, KLNMA 18, stored `b1..b8`).

**Fix:** a completeness check `rp_liab_missing` / `rp_gap_missing` guards the TOTAL row (assets
present but liab/gap NULL = a dropped row). Calibrated to flag exactly 66, zero false positives.

## Extractor — 8 failure modes fixed (`repricing.py`)

The `b1..b8` fallback was a *symptom*: footnote markers `(1)`/`(5)` matched `_NUM_TOKEN` and
inflated the column count, so the row was one value short and the liabilities/position rows dropped.

| Fix | Change | Cleared |
|---|---|---|
| A | drop footnote-marker tokens `^\(\d{1,2}\)$` from `_value_tokens` | ZIRAAT 34 / KLNMA 18 / ZIRAATD (the b1..b8 root cause) |
| B | gap pattern `^Net\s+Pozisyon\b` (re.I) | TAKAS ×14 (were MISSING — the locator never fired) |
| E | gate the prior-period flip until the current total is recorded | ISCTR/ENPARA (lost current to the FX-table's "Prior Period" header) |
| D | borrow values from the next word-line when a label sits alone | ATBANK ×5 (split position row) |
| G | typo-tolerant liabilities `^Total\s+Liab[a-z]+\b` | QNBFB ×7 ("Total Liabalities") |
| C | un-glue a token with a >3-digit interior group | HALKB 2025Q1 con (fused Faizsiz\|Total) |

Verified on representatives + controls, foot-checked, no regression on the 772 passing partitions.
Re-extraction cleared **~76** of the 71 failing + missing.

## Overrides — 15 initially, 7 retired after hardening (8 remain)

**FIBA ×6** (2022Q1 cons/unco, 2023Q3 con, 2024Q1 con, 2025Q3 cons/unco) — vector-only tables (fitz
get_text empty); hand-transcribed from renders, both periods, every block foots.

**9 residual** (source-read). ✅ = still an override (a SOURCE defect); ♻️ = RETIRED by the second-pass
hardening below, now extracted from source:
- ✅ ISCTR 2025Q4 con — 3-12M assets clipped in the source (`1.056.377.15`→1,056,377,153) + non_sensitive
  gap a misread nil (`-` alone in the cell → 0, true −1,153,771,067).
- ✅ QNBFB 2026Q1 — 1-3M gap printed WITHOUT parentheses (source error) → −7,296,167.
- ♻️ EXIM 2025Q3, ZIRAATD 2025Q4 — gap row values sit above the label / a blank 5y cell drops a token.
- ♻️ TAKAS 2023Q1 (ncols locked to the shared FX table = 4), 2023Q3 (a stray `f` glyph glued to a cell).
- ♻️ COLENDI 2025Q2/Q3/Q4 — the "Non-Interest Bearing" header wraps across 3 word-lines so `_NONINT_RX`
  never fires; the ladder IS disclosed (NOT N/A). 2025Q4 current == 2026Q1 prior, exactly.

**1 skip** (`_RP_SKIP`): ICBCT 2024Q1 — the printed gap buckets sum to ₺7k vs a printed 0 (RSA=RSL to
the rupee); a source rounding, faithfully stored.

## Third pass — the PRIOR block was structurally invisible (2026-07-19)

`check_repricing` read the **current period only**, so a wrong cell in the comparative
column was unverifiable by construction — and nothing else covered it either: the
cross-period anchor compares *totals*, and the totals were right. A fleet sweep of prior-block
footing found **9 partitions**, none of which had ever shown as anything but green.

**Fix:** the footing block now also runs over the prior column (`rp_prior_footing`), with a
`check_prior=False` escape for filer typos. Calibrated: flags exactly the 9, zero false positives.

**8 were OUR misreads → corrected from source** (every value printed elsewhere on the same page;
none inferred from the footing identity, which would make the check vacuously pass):
- **TAKAS 2023Q1/Q2/Q3** — prior 3-12M assets `237,331`; the page prints **2,373,311** (detail row
  and Net pozisyon both), liab=0 there so gap=assets. fitz lost the final glyph (bbox wider than text).
- **TAKAS 2024Q1/Q2/Q3** — prior 3-12M assets `89,518`; true **895,180**. Deeper than a fitz failure:
  the PDF **content stream itself holds only `8 9 5 , 1 8`** — the filer's Word→PDF export clipped the
  trailing 0 where the bold total overflowed its cell. Printed in full twice in the same column.
- **ISCTR 2025Q2** — prior lt_1m gap **sign only**: the text layer emits `(452,169,857` with the
  closing paren clipped, and the paren-negative rule needs a balanced pair → true **−452,169,857**
  (BS Short 462,398,818 + Off-BS Long 10,228,961). The stored Σ was off by exactly 2×.
- **ICBCT 2024Q4 cons** — the prior liab row was verbatim the *Bilançodaki Uzun Pozisyon* row: this
  page prints every value line **ABOVE** its label (label y=394.2, values y=390.8) and the extractor
  bound the line below, landing one row down. ⚠️ It **footed internally**, so the footing sweep never
  saw it — only reading the page did. Its gap total prints `–` = nil (0).

**2 are FILER typos → `_RP_PRIOR_SKIP`** (stored faithfully; prior check suppressed, current checks
still run). Each located from the table's own component rows, then cross-checked against another filing:
- **TSKB 2022Q1** — prior non-interest assets prints `3.602.833`; that column's four detail rows sum to
  **3,062,833** (0↔6 transposition). TSKB's own 2022Q2/Q3/Q4 reprint the same 31.12.2021 ladder with
  3.062.833 — the filer silently corrected it.
- **ANADOLU 2026Q1 cons** — prior gap 1-5Y prints `(6.959.075)`; its four component rows give
  **(6,956,075)** and each foots across all 7 columns. The row total (136,804) is right.

**Lesson:** a validator scoped to one period leaves the other structurally unverifiable — and
"cross-period reconciles" is not the same guarantee, because it only compares totals. Also: ICBCT
shows a defect can foot internally and still be wrong, so footing alone is a floor, not a proof.

## The 247 N/A — re-verified from source (2026-07-18)

The lane's 247 `not_expected` cells are 9 participation banks (ALBRK/EMLAK/KUVEYT/TFKB/VAKIFK/
ZIRAATK ×34, HAYATK 18, DUNYAK 14, TOMK 11), nilled by blanket `kind:"*"` entries in
`audit_not_disclosed.json` on the premise "interest-free → no repricing ladder". That premise
deserved re-checking: the same crude fingerprint had already produced FALSE N/A for TAKAS and
COLENDI, and participation banks report a *profit-share-rate* (kâr payı oranı) ladder whose
non-rate column is "Kâr Payı Getirmeyen", which `_NONINT_RX` (Faiz-only) would never match.

**Verdict: the N/A is GENUINE.** Checked all 9 banks at both ends of the corpus (2022Q1/2022Q4/
2023Q4 and 2025Q4/2026Q1): none prints a bucketed ladder.

**The test that settles it** — require the FULL table signature on one page: all three summary
rows (`Toplam Varlıklar` AND `Toplam Yükümlülükler` AND `Toplam/Net Pozisyon`) **plus ≥3 maturity
buckets** (`1 Aya Kadar`/`1-3 Ay`/`3-12 Ay`/`1-5 Yıl`/`5 Yıl ve Üzeri`). ⚠️ A one-row fingerprint
("has a Toplam Pozisyon row", or "mentions kâr payı oranı riski") **false-matches**: KUVEYT
2025Q4 p38 is the internal-capital narrative listing risks, and TFKB 2024Q4 p113 is the
*borrowings* maturity table — both looked like hits until rendered. That is exactly how the
original N/A fingerprint went wrong on TAKAS/COLENDI, in the other direction.

**One real defect found: DUNYAK.** Its `"*"` note claimed "no interest-rate repricing ladder …
verified against the 2026Q1 PDF", but **2023Q4 genuinely prints a conventional Faizsiz ladder**
(p44 — it extracts, 14 rows, and correctly reads `ok`, so no cell was wrongly nilled). DUNYAK used
the conventional interest template in that one quarter and switched to the no-ladder participation
format from 2024Q1 (confirmed per-quarter 2024Q1→2026Q1: none). Note corrected in
`audit_not_disclosed.json`. **Lesson: a `"*"` wildcard asserts a fact about EVERY period; verify it
per-quarter, or scope it** — see [[reference_not_disclosed_wildcard]].

## Second pass — the 5 brittleness classes HARDENED (overrides retired)

The residual overrides each exposed a general weakness. All five are now fixed in the extractor, so
those partitions come from SOURCE and **7 of the 15 overrides were retired** (`manual` 15 → 8,
`ok` 788 → 795). The approach is x-coordinate column reconstruction, gated on footing:

- `_fitz_word_lines` now keeps each token's **right edge** (`x1`) — bucket columns are right-aligned,
  so x1 identifies which column a cell sits under when a row can't be read by token count alone.
- **`_x_columns` / `_nonint_line`** — group tokens into columns by x-interval overlap, so a
  non-interest header split across word-lines is rebuilt from its fragments (COLENDI's wrapped
  "Non-Interest Bearing" — the locator now fires).
- **`_col_anchors` / `_page_anchors`** — bucket-column right edges read off one fully-populated row,
  **per page** (a page-2 prior table's columns don't line up with page-1's). Trusted only when that
  row holds exactly one raw token per column — if any cell needed un-gluing or de-straying the
  anchors no longer map 1:1, so the fallback stays off. This also stops the `ncols` lock latching
  onto a *different* table sharing the page (TAKAS 2023Q1's currency-risk tail).
- **`_row_by_columns`** — maps values to their bucket column by x-position, scanning the lines
  directly above AND below the label (EXIM's values-above-label), rejoining fragments that land in
  the same column, and tolerating at most one empty column (ZIRAATD's genuinely blank 5y cell).
  ⚠️ **It is accepted only if the reconstructed values FOOT** — that test is what makes a
  positional guess safe, the same guard the fx lane's row-shift repair uses.
- **`_destray`** — strips ONE stray alpha glyph fused to a numeric cell (TAKAS 2023Q3's
  `3,768,782f`), only when what remains carries a thousands separator (a real label never survives).

**Verified:** all 7 targets recover from source and match the hand-read values exactly (TAKAS/EXIM/
ZIRAATD now return BOTH periods — 14 rows — where the override held only 7); **0 regression across
10 controls** (AKBNK/ISCTR/GARAN/ZIRAAT/KLNMA/TAKAS/ATBANK/HALKB/QNBFB/COLENDI).

**The 8 overrides that remain are genuine SOURCE defects no extractor can fix** — re-tested against
the hardened extractor and still unrecoverable: FIBA ×6 (vector-drawn, 0 rows), ISCTR 2025Q4 con
(the PDF itself clips `1.056.377.15`, and a lone `-` in the gap cell), QNBFB 2026Q1 (the source
prints the 1-3M gap without its parentheses). See [[project_market_risk_lane]].
