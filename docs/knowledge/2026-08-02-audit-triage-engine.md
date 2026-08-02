# Triaging the failing partitions mechanically — 2026-08-02

> **Status: SHIPPED.** `src/audit_reports/triage.py` + `scripts/triage_partitions.py`
> + `scripts/watch_cross_period.py` + `.github/workflows/audit-triage.yml`, pinned by
> `tests/test_triage.py` (22 cases). Read-only: no D1 write, no row update, no
> extractor edit, no model call. Findings below are measured against the
> 2026-07-27 local snapshot.

## The gap

`bank_audit_validation` records **which** identity broke. It has never recorded
**why**, and the why has always been found the same way: a human opens the PDF,
reads the page, and works out which of a small set of mechanical things went
wrong. Every write-up in this directory is that exercise done once. The set is
short and it recurs — a column the extractor never read, a row it never
extracted, a value taken from the wrong column, a cell word-wrapped out of
reach, a missed anchor, a drawn page, a rotated page, the wrong PDF, a unit
change, or a filing that genuinely does not foot.

All of it is decidable from the PDF plus the stored rows, so none of it needs a
model. The engine assigns the cause deterministically and attaches the evidence;
a human still decides what to act on.

## What it found

All **212** failing partitions, triaged in CI against the live R2 corpus
(run 30763530600, ~4 min):

| Cause | n | Meaning |
|---|--:|---|
| `column_slip` | 61 | right statement, wrong column |
| `dropped_cell` | 46 | a column the extractor never read, stored as `0` |
| `anchor_miss` | 45 | the value is in the filing, outside where we looked |
| `unclassified` | 26 | not decidable by this method — said so rather than guessed |
| `missing_row` | 26 | a printed row has no stored counterpart at all |
| `rotated_page` | 7 | `/Rotate` set; text comes out garbled unless normalised |
| `drawn_page` | 1 | no text layer; a human has to transcribe it |

| Lane | Partitions | Dominant cause |
|---|--:|---|
| equity_change | 126 | `column_slip` (53) |
| audit_opinion | 51 | `anchor_miss` (43) |
| capital | 19 | `dropped_cell` (9) |
| profile | 16 | `unclassified` (16) |

**`source_defect` is zero across the corpus.** After the rule was tightened (see
below) nothing here qualifies as "the bank's own statement does not foot" — every
failure is ours, or honestly undecidable. That is worth knowing before anyone
adds another entry to `revalidate_audit_db`'s skip-lists.

Three verified by hand, end to end:

- **EMLAK 2022Q1 capital** — `Tier1 = CET1 + AT1 [prior]` short by 2,359,569.
  That figure is printed on p32; the partition stores `0` in prior
  `additional_tier1_capital`. The §4 table spans pp31–33 (CET1, then AT1/Tier1,
  then RWA). Same shape across QNBFB 2022Q1–2023Q2 — **one extractor cause, six
  partitions.**
- **AKBNK 2026Q1 equity_change** — every stored figure is printed exactly as
  stored, and the chain still breaks: the closing row's label wrapped onto the
  end of the `11.3` row (`11.3Diğer … Dönem Sonu Ba`), leaving its 16 values on
  an unlabelled line that was never extracted. The validator then closed the
  chain on row XI and reported a mismatch describing nothing.
- **TEB 2023Q4 audit_opinion** — "auditor not captured". Deloitte is named on
  **p7**; `audit_opinion.extract_opinion_from_pdf` reads `max_pages=6`. A
  qualified opinion carries a Basis paragraph that pushes the signature past the
  window. **7 partitions, one integer.**

## What cost the most to get right

Six false-positive classes, each caught by hand-checking a verdict rather than
by reading aggregate counts. Every one produced a *confident wrong label*, which
is worse than no label.

1. **`failed_detail.expected` is DERIVED, not printed.** For `Total = A + B` it
   is A+B computed from stored rows. Pivoting the diagnosis on "is `expected` on
   the page?" marks every ordinary misread component as "the bank's statement
   does not foot", because a derived sum is normally absent from the page. The
   evidence base has to be the **stored** figures versus the print; `expected` is
   only a search hint.
2. **A statement spans pages.** Judging a partition against one best page marks
   two-thirds of its own figures absent and invents an extraction defect out of
   ordinary pagination. But the window cannot simply be "adjacent pages that
   score" either — neighbouring statements share figures (total equity is on the
   balance sheet too), so a page must carry a real *share* of the statement to
   join, or the window walks into the P&L and imports its row markers as missing.
3. **Presence-checking cannot see an absence.** A missing row and a cell stored
   as `0` are both invisible to "is this value printed?" — and between them they
   are the largest cause in the corpus. Both needed their own detector, and the
   `0` one is the only cause the filing can *prove*: the identity is short by D,
   D is printed, and we hold a `0` in a column it sums over.
4. **"Every stored figure is printed" does not mean the source is at fault.** A
   figure lifted from the wrong line is still a figure on the page. `source_defect`
   now additionally requires that the figure the identity *needs* is printed
   nowhere nearby — which demoted both surviving candidates (EMLAK 2025Q1,
   ISCTR 2025Q1) to the slips they actually are.
5. **Ratio identities are undecidable this way.** Percentages and counts are too
   short to presence-check (a page prints hundreds of short numbers), so
   `cap_ratio_reconcile` gets `unclassified` with the reason stated. ISCTR 2025Q1's
   real defect — prior `total_rwa` holding a figure from the total-capital row —
   needs ratio arithmetic, not presence.
6. **Mixed `I.` / `2.1` markers are the normal BRSA convention**, not a hierarchy
   defect. The real defect is the same node stored under two spellings. The first
   rule fired on healthy equity statements across the corpus.

A seventh was caught only *after* the first full-corpus run, by spot-checking one
of the 83 `dropped_cell` verdicts it produced rather than reading its counts:
**when the stored side of an identity is `0`, the shortfall equals the figure the
identity wants**, so "the shortfall is printed" restates the premise and proves
nothing — and the zeros it named as the culprit were whatever the partition
happened to hold (`minority_interest`) rather than the column the identity sums
over. Zeros are now matched against the node text and the circular case is
refused. That single correction moved 46 partitions off `dropped_cell`
(92 → 46, with `column_slip` 27 → 61 and `missing_row` 14 → 26) — a reminder that
a plausible aggregate is not evidence, and only opening one case is.

Two smaller ones, both silent: an `except ImportError` around the auditor lookup
swallowed a wrong symbol name (`extract` vs `extract_opinion_from_pdf`) and
turned every opinion partition into a plausible-looking `unclassified`; and the
row-marker regex demanded whitespace after `I.`, while fitz emits
`I.Önceki Dönem Sonu Bakiyesi` — so it matched almost nothing on a real page.
Marker reading now goes through the extractor's own `_fitz_page_text`, so triage
and the code being diagnosed are looking at the same document.

## The cross-period watch

Every structural validator in this repo argues *inside* one filing, and each is a
ratio of figures sharing a scale. When the sector went Bin TL → Milyon TL in
2026Q2, all eleven filings stayed internally perfect while every stored figure
was wrong by 1000×. **No in-filing check could have caught it, and the in-filing
unit detector here cannot either** — if we ingest what the filing prints, the
stored figure matches the page exactly. That is a property of the problem, not a
gap in the implementation.

`scripts/watch_cross_period.py` is the instrument that can: same bank, one
quarter earlier, asking what moved by a clean power of ten, what went missing,
and what appeared. Pure SQL over the snapshot — **14,452 seams across every
validated lane, 1,225 raising something, 0 reporting-unit changes**, in seconds.

⚠️ **Not validated against the real event.** The 2026-07-27 snapshot stops at
2026Q1, so the Bin→Milyon seam is not in the data; the detector is covered by a
synthetic test only. Re-run it against a snapshot containing 2026Q2 to confirm.

One tuning note worth keeping: the row key must be **structural**
(`hierarchy` / `currency` / `sector`), never `item_name`. Labels drift — a bank
rewords a line, a footnote marker survives one quarter and not the next — and
keying on them reports the same row as both "newly absent" and "newly present",
burying the signal under matched pairs of noise (104 → 73 seams on the fix, with
the paired counts gone).

## Limits

- Numeric only. Text fields have one bespoke detector (the auditor signature);
  `basis_text` and the profile lane's branch/personnel counts are not covered.
- `unclassified` is a real answer, not a failure — 26 of 212, and all 16 profile
  partitions (branch/personnel counts are too short to presence-check). Prefer
  growing that number over widening a detector until it guesses.
- Verdicts are hypotheses. `confirmed` means the PDF demonstrates it; `likely`
  means it was inferred. Confirm before acting.

## Next, if it earns it

- `max_pages` in `audit_opinion.extract_opinion_from_pdf`: 6 → 10. Cheapest fix
  in the backlog, 7 partitions, guarded by the existing opinion tests.
- The `dropped_cell` cluster (EMLAK + QNBFB capital) points at one prior-column
  read in the §4 extractor. That is a code fix, not a re-extraction campaign.
- `column_slip` on equity_change (53) is the largest single cell in the matrix and
  has not been opened yet. Start there, and open a case before trusting the count
  — that is exactly how the `dropped_cell` over-claim was found.
- 7 `rotated_page` partitions were invisible in the local cache and only appeared
  in the CI run. `/Rotate` normalisation is a known extractor gap
  (`docs/knowledge` — the equity/CF `/Rotate 90` work), so these are likely one fix.
