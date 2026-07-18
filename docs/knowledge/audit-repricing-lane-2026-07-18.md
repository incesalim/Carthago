# Interest-rate repricing lane → 0 error / 0 missing

**Status: COMPLETE 2026-07-18.** Coverage `788 ok / 15 manual / 247 N/A / 0 err / 0 miss`
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

## Overrides (15, `repricing_replace` + per-cell `repricing`)

**FIBA ×6** (2022Q1 cons/unco, 2023Q3 con, 2024Q1 con, 2025Q3 cons/unco) — vector-only tables (fitz
get_text empty); hand-transcribed from renders, both periods, every block foots.

**9 residual** (source-read):
- ISCTR 2025Q4 con — 3-12M assets clipped in the source (`1.056.377.15`→1,056,377,153) + non_sensitive
  gap a misread nil (`-` alone in the cell → 0, true −1,153,771,067).
- QNBFB 2026Q1 — 1-3M gap printed WITHOUT parentheses (source error) → −7,296,167.
- EXIM 2025Q3, ZIRAATD 2025Q4 — gap row values sit above the label / a blank 5y cell drops a token.
- TAKAS 2023Q1 (ncols locked to the shared FX table = 4), 2023Q3 (a stray `f` glyph glued to a cell).
- COLENDI 2025Q2/Q3/Q4 — the "Non-Interest Bearing" header wraps across 3 word-lines so `_NONINT_RX`
  never fires; the ladder IS disclosed (NOT N/A). 2025Q4 current == 2026Q1 prior, exactly.

**1 skip** (`_RP_SKIP`): ICBCT 2024Q1 — the printed gap buckets sum to ₺7k vs a printed 0 (RSA=RSL to
the rupee); a source rounding, faithfully stored.

## Follow-ups (extractor brittleness classes, not yet hardened — overrides used instead)
The residual overrides each expose a general weakness worth a code fix if these recur: values-above-
label, blank-cell token-count, wrong-table `ncols` lock on a shared page, stray-glyph token rejection,
and the single-line-only non-interest header match (COLENDI — future COLENDI quarters will miss until
`_NONINT_RX` tolerates a wrapped header). See [[project_market_risk_lane]].
