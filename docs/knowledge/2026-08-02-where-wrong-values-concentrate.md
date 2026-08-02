# Where the wrong values concentrate — 2026-08-02

> **Status: measured, report only. No code or data changed.** Two questions, kept
> apart on purpose: where the failures we can SEE sit, and where a wrong figure
> could sit and nothing would notice. The second is the one that matters, and the
> answer is not where the first points.

## 1. Known-wrong: 212 of 18,900 validated partitions (1.1%)

Spread, not concentrated. **31 of 38 banks** carry at least one failure, and the
worst rate is TFKB at 5.4% (33/612); the median failing bank is nearer 1%. That
shape argues these are systematic extractor behaviours, not a handful of awkward
banks — consistent with the triage, which grouped all 212 into a handful of
mechanical causes ([2026-08-02-audit-triage-engine.md](2026-08-02-audit-triage-engine.md)).

**Q4 filings fail 2.3× more than interim ones** — 1.97% vs 0.86%, every year:

| | 2022Q4 | 2023Q4 | 2024Q4 | 2025Q4 | vs typical Q2/Q3 |
|---|--:|--:|--:|--:|--:|
| failure rate | 2.6% | 1.9% | 1.9% | 1.5% | 0.4–1.0% |

⚠️ **That whole spike is one bug.** Excluding `audit_opinion`, the ratio drops to
**1.20×** — flat. 45 of 51 opinion failures are Q4, because Q4 is a full audit
whose "Basis for Qualified Opinion" paragraph pushes the signature past the
extractor's 6-page window, while Q1–Q3 are short limited reviews. Annual filings
are not intrinsically harder to extract; one integer makes them look that way.

## 2. Unseen-wrong: where a corrupted cell passes silently

The above only counts what a validator can flag. The useful question is coverage:
corrupt one stored cell (×1.5) and re-run every check that lane actually gets —
does anything notice? 30–40 partitions sampled per lane.

| Lane | Cells tested | **Missed** | Where the misses sit |
|---|--:|--:|---|
| Balance sheet (assets) | 2,500 | **0.0%** | — |
| P&L | 1,291 | **38.7%** | depth-2 sub-items (`1.1`, `2.3`) |
| OCI | 293 | **52.6%** | depth-3 sub-items |
| Cash flow | 1,047 | **79.9%** | depth-3, then depth-2 |

**The balance sheet is airtight** — every cell participates in TL+FC=Total, a
hierarchy sum, or the statement total, so no single-cell corruption survives. The
lanes downstream of it are not, and it inverts the intuition: the failures we see
cluster in equity_change and audit_opinion, but the exposure sits in **cash flow
and the P&L sub-item level**, which are currently quiet.

Why the P&L gap exists is documented and deliberate, not an oversight —
`validator.py:913` states that BS parent=Σchildren is not applied at the P&L roman
level because deduction lines carry `(-)` labels with additive signs and several
romans are net rather than additive, which would false-fail. `check_pl_subitem_sums`
covers part of the depth, and the 39% is what it does not reach.

⚠️ **Methodology warning.** The first run of this measurement reported the balance
sheet at **67.5% missed** — because it ran `check_hierarchy_sums` alone instead of
the full set the lane actually gets. The true figure is 0.0%. A blind-spot number
is only meaningful against *every* check that really runs; measuring one check and
calling it the lane's coverage produces a false alarm on the single best-guarded
lane in the corpus.

## 3. The structural gaps, separately

- **`free_provision` has no validator at all** — 580 green cells, 3.5% of the
  matrix, unconstrained by construction. Every other lane has one.
- **Ratio-only identities can't be checked by presence.** The capital lane's
  `cap_ratio_reconcile` failures are undecidable from the page, which is why 26 of
  212 triage verdicts are honestly `unclassified` (all 16 profile partitions
  among them — branch counts are too short to verify).
- **52 stored rows carry a figure's digits fused into `item_name`** (strict
  definition: a 5+ digit run after stripping footnote refs). Concentrated in
  **OCI, 32 of 52** — the same lane that is 53% blind. Top banks ALNTF 14,
  QNBFB 8, FIBA 7.

## What follows

1. Fix the opinion window (`max_pages` 6 → 10). It removes 43 failures and the
   entire apparent Q4 effect.
2. Treat **cash flow** as the highest-exposure lane, not the calmest one. 80%
   of its cells can be wrong without any check objecting, and it currently shows
   zero failures — those two facts belong together.
3. Before trusting any coverage figure here, re-run it against the full check set
   for that lane. See the warning above.
