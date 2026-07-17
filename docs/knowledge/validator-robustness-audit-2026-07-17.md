# Validator robustness audit — all 18 audit lanes

**Date:** 2026-07-17
**Status:** TIERS 1 AND 2 SHIPPED (same day). Every detection recommendation in §6 that earned a
measured zero false-positive rate is live — see "What shipped". **Tier 3 (the actual data
repairs) is OPEN**. The P&L deduction sign — which §3 called MIXED and I twice called
"undetectable" — is FIXED (`95632b1`); see "The sign claim was wrong" below.
**Scope:** every validator behind the `/admin` coverage matrix: `src/audit_reports/validator.py`,
`scripts/check_audit_quality.py`, `scripts/sync_audit_expected.py::_cell_status`,
`src/audit_reports/registry.py`.
**Question asked:** are the validators strong enough to catch errors, without labelling correct
data as an error?

## Answer in one line

**Precision is excellent — strength is not.** Almost every "error" the matrix reports is a real
defect (the sole false-positive cluster is 17 band-driven liquidity flags). But the green is
much weaker than it looks: **9 confirmed live-wrong NPL figures sit on cells scoring flawless
green**, and the checks that would catch them already exist in the database, unused.

## Method

Mutation testing against the real corpus (`data/bank_audit.db`, 1,050 partitions). For each lane:
take currently-PASSING partitions, apply one realistic extraction corruption, re-run the real
validator function, record CAUGHT (`checks_failed` 0→>0) vs MISSED. ~40 corruption classes,
~25,000 mutations. This distinguishes the two explanations for "0 errors" that a coverage matrix
cannot: *precise* vs *not looking*.

Scripts in the session scratchpad (`bs_mutate.py`, `mutate2.py`, `eq_mutate.py`,
`cqstages_mutate.py`, `nplsector_mutate.py`, `mutate.py`, `recon.py`, `bs_recon.py`).

---

## 1. The live-wrong numbers (all on green cells)

### 1.1 NPL denominators — a fragment table read as the loan book

`stages.total_amount` vs the balance-sheet loans line (`2.1`) is near-exact corpus-wide
(median 1.000, p95 1.046) and flags exactly 6 partitions. Each row is internally consistent, so
all 6 score **6 passed / 0 failed / 0 skipped**:

| Bank | Period | Dashboard NPL | Truth | Ratio to BS loans |
|---|---|---|---|---|
| SKBNK | 2025Q4 unco | **39.51%** | ~1.33% | 0.033× |
| SKBNK | 2025Q4 cons | **38.68%** | ~1.4% | 0.037× |
| SKBNK | 2024Q4 cons | **36.40%** | ~1.49% | 0.045× |
| SKBNK | 2022Q4 cons/unco | **26.5 / 26.4%** | ~3.3% | 0.157× / 0.149× |
| FIBA | 2025Q2 cons | **49.04%** | ~2.2% | 0.054× |

SKBNK 2025Q4 has `S1 == S3 == 1,713,917` — a literally duplicated column — and still passes
everything. SKBNK 2023Q4 is clean (2.17%), so this is layout-specific, not "every Q4".

### 1.2 NPL numerators — vs `npl_movement.closing_balance`

Three are unambiguous, each bracketed by its own neighbouring quarters:

| Bank | Period | Dashboard | Movement says | Neighbours |
|---|---|---|---|---|
| ISCTR | 2025Q2 unco | **0.36%** | 2.57% | Q1 2.38%, Q3 2.67% |
| QNBFB | 2025Q3 unco | **0.59%** | 3.67% | Q2 3.38%, Q4 3.76% |
| FIBA | 2025Q4 cons | **0.03%** | 4.63% | Q1 2.21%, 2026Q1 4.48% |

Independently, `credit_quality` and `stages` agree exactly with each other and both disagree with
`npl_movement` on **19 of 986** partitions — two references against one; the movement table is the
outlier. All 19 green. FIBA 2025Q4 cons reads "3 checks passed" while its NPL is **145×** the
authoritative figure.

### 1.3 Other confirmed live-wrong values

- **İşbank renders "1 branch".** ISCTR consolidated Q4, 2022–2025: `branches_total = 1` while the
  *same quarter's* unconsolidated row says 1,110. The UI keys off `branches_total` only. 4 green cells.
- **EXIM 2024Q2 equity:** ₺35.7bn of paid-in capital filed under `share_premium` (BS 16.1 proves it).
  TFKB's entire 54-page series is shifted one column right. **63 "ok" cells carry a column shift.**
- **BURGAN 2023Q1–2024Q1:** 10 free-provision cells read **N/A** while each carries a qualified
  opinion over exactly that reserve (up to ₺1.87bn). The value sits in `bank_audit_opinion.basis_text`
  — a neighbouring column of the same DB — for 8 of the 10.
- **HAYATK 2023Q3 unco:** `lcr_fc = 679,668.29%` in a cell the matrix calls ok. No per-partition
  check reads that column.
- **75 "ok" profile cells have `branches_total` NULL** — the exact field the UI reads. GARAN and
  HALKB have `personnel` NULL in all 34 quarters each. DENIZ 2024Q1/Q2: `personnel == branches_total`
  exactly (a column slip, ~20× wrong).

---

## 2. The three structural defects above any single validator

### 2.1 "ok" never requires that anything passed

`sync_audit_expected.py:207` — `_cell_status` returns `ok` when `rows >= min_rows and
checks_failed == 0`. It never reads `checks_passed`. A partition where every check *skipped* reads
green: **262 cells (1.9% of 14,150)**. They cluster by bank, not at random — ANADOLU's NPL movement,
ATBANK's capital, DUNYAK/COLENDI's credit quality and stages, HAYATK's FX position.

`validator.py:740`'s `statement_passes()` — the gate protecting good data from re-extraction —
*does* require `checks_passed > 0`. The two definitions of "passing" disagree.

### 2.2 A check cannot detect the loss of its own input

Every identity skips when a source row is absent, so **dropping a row removes its own constraint**
and the partition stays green. Measured:

| Lane | Drop-a-row detection |
|---|---|
| off_balance, whole B block | **0/259** |
| cash_flow, any roman I–VII | **0/300** |
| OCI, a roman | **0/296** |
| P&L, a roman | 10/300 (3%) |
| credit_quality, `npl_brsa_gross` section | **0/997** |

**V6 is broken at its stated purpose.** Its docstring claims dropping the whole custody block
"shows up only as A+B ≠ total". It does not — removing B flips V6 from RUN to SKIP on **887/887**
partitions. Its docstring is also already stale ("889 reconcile / 160 skip"; actual 887/163),
which proves the drift is real and unreported.

### 2.3 Circular validation — checking arithmetic we performed ourselves

- `fx_position.py:218` **computes** `net_position = net_on_balance + net_off_balance`;
  `check_fx_position` then "verifies" that identity. Fails **0/6,772** rows and contributes
  **29.4%** of the lane's passes.
- `repricing.py:182` recomputes `cumulative_gap` while **discarding the value the BRSA table prints**.
  `cumulative_gap = Σ gap` holds 715/715 — necessarily.
- `stage*_coverage` is stored-but-derived (3,516/3,516 rows have `coverage == ecl/amount` exactly).
- `capital_adequacy.py:449-463` rebuilds `tier1 := cet1+at1` when `t1 < cet1` or `t1 is None`,
  making `cap_composition` non-falsifiable for those partitions.

---

## 3. Per-lane verdict

| Lane | Precision | Strength | The number |
|---|---|---|---|
| assets / liabilities | STRONG | STRONG | V1 181,807 comparisons, ~0% skip; V2 constrains 88.4% of rows; 99%+ detection on 8/14 classes |
| cross (V4) | — | **WEAK** | Real data ties at **exactly 0.00% on 1050/1050**; the 0.5% band tolerates median ₺1.11bn, max ₺48.2bn. Infinitely too loose. **Reaches no matrix cell** (`cross` maps to no lane) |
| off_balance | STRONG | **WEAK at top of tree** | V3 never runs (0/1050); V6 skips 15.5% and is blind to its own target |
| profit_loss | STRONG (94.4% run all 6 identities) | MIXED → improved | roman corruption 99% caught; ~~deduction sign free in 91%~~ **FIXED, now 100% (`95632b1`)**; tax sign flip 0/297 but **inert** (its only consumer abs()es it); same-band swap 0/299; 60.5% of rows unchecked |
| oci | STRONG (10 of 11 errors real) | ADEQUATE | **hardcoded `.get(25)`** disables the only cross-check on 6 DUNYAK partitions |
| cash_flow | — | **WEAK** | only 16.0% of 45,714 rows touched; drop/leaf-shift 0/300 |
| equity_change | **STRONG — ~100 of 104 errors are real** | **WEAK on components** | reads only `total_equity` and the *sum*; every sum-preserving component error **0/296** |
| credit_quality | STRONG (no FPs, `_CQ_SKIP` empty) | **WEAK** | **54.2% skip**; 99.5% of passes are one sum identity; the only cross-section check runs on **16/1024 (1.6%)** |
| stages | STRONG | **WEAK** | **0 cross-table checks**; consistent-wrong 0/1000; stage swap 0/993 |
| npl_movement | 13/13 errors real | **BROKEN** | roll-forward has **never failed once**: 2,262 tie / 558 excused / 138 rescued / **0 fail** |
| loans_by_sector | 5/5 real | NARROW | validates 2 of 3 columns, 33% of sector rows; move-between-sectors 0/217 |
| capital | 11/13 real | ADEQUATE | 2pp CAR tolerance = **median ₺2.73bn, max ₺133.7bn**; CAR +1.5pp missed **360/371** |
| liquidity | **17 of 24 are FALSE POSITIVES** | **WEAKEST** | **3/3 checks are bands, 0 reconciliations**; plausible wrong LCR missed **353/353** |
| fx_position | 8/8 real | STRONGEST | only lane surviving move-between-rows (94.7%) — but 29.4% of passes are a tautology |
| repricing | 2/3 real | ADEQUATE | bucket dimension rests **entirely** on Σ=TOTAL: move-between-buckets **0/400** |
| profile | — | **NONE** | 980 green cells asserting `row_count >= 1` |
| audit_opinion | — | **NONE** | 976 green cells asserting `row_count >= 1`; all **73 "missing" are extraction failures** (`pdf_present=1`, `success=1`) |
| free_provision | — | **NONE** | 581 green cells; `conditional=True` auto-relabels 469 empties **N/A** — absence is never a gap |

**The bands-vs-reconciliation principle is confirmed in both directions simultaneously:** liquidity's
bands miss real errors (353/353) *and* produce 100% of the audit's false positives (17/17 — every
one a de-novo bank whose genuinely-high leverage trips a band; corroborated against equity/assets
from the BS: ENPARA 94.84 vs 94.90, HAYATK 97.00 vs 97.43).

**The structurally undetectable class:** `total = S1+S2+S3` is one equation in four unknowns. Any
redistribution at constant sum, any scaling of the whole row, any numerator+total moved together is
invisible by construction. This is why all 9 confirmed errors are consistency-preserving — only
cross-source reconciliation sees them.

---

## 4. The matrix is green for data D1 doesn't have

Local vs D1 (`bddk-data`, queried remote):

| Lane | local | D1 | short |
|---|---|---|---|
| fx_position | 7,683 | 6,967 | **−716** |
| repricing | 11,013 | 9,910 | **−1,103** |

**89 fx_position + 78 repricing cells are `status='ok'` in D1's own coverage table while D1 holds
ZERO rows for them.** The coverage rows record the `row_count` they expected (8 / 14), proving they
were computed against the local DB and pushed without the underlying rows. Worst hit are the largest
banks: QNBFB (12+12), TEB (9+9), AKBNK (7+7), ISCTR (6+6), EXIM (6+6), ALNTF (6+6), YKBNK, VAKBN;
2022Q1–2026Q1. This is the ⚠️ in `project_architecture_docs_check` — live.

## 5. The UI overstates assurance

`CoverageMatrix.tsx` renders two green ✓ glyphs per row. Line 269 (next to the label) is correctly
gated on `has_validator`. **Line 289 (the Coverage column) is gated on `problems === 0` and never
consults `has_validator`.** So `profile` (980/0/0/0) and `free_provision` (581/0/0/0) earn it plus a
100%-green HealthBar — while **8 of the 15 validated lanes lose it for finding real errors**.

Running a validator can only cost you the tick; having none guarantees it. The legend says
"✓ = has validator", which makes the identical-looking second ✓ actively misleading.
`CoverageDrawer.tsx:193` silently omits the validation block for unvalidated lanes — no notice, just absence.

---

## What shipped (tier 1, 2026-07-17)

Seven changes. Every new check was calibrated against a **copy** of the corpus before landing,
and the predicted flag count was committed to in advance — the gate was "ship only if the flagged
set matches the prediction; an unpredicted flag is a false positive, stop and diagnose".

| Check | Predicted | Actual | Runs (passed) |
|---|---|---|---|
| `stages_bs_loans` — stages total ⋈ BS 2.1, band [0.8, 1.3] | 9 | **9** ✓ | 1,024 |
| `off_balance_b_block` (V7) — B = Σ IV+V+VI | 0 | **0** ✓ | **1,046** |
| `npl_provision_net` — closing − \|provision\| = net | 0 | **0** ✓ | **2,097** |
| `cq_loans_by_stage_total` — total = S1+S2 | 0 | **0** ✓ | **996** |
| `npl_closing_vs_gross` + `cq_gross_vs_movement` | ~34 partitions | **34** ✓ | — |
| `check_oci` — resolved period-net ordinal | 6 skips → 6 passes | **6** ✓ | — |

The "runs" column is the point: a 0 is only meaningful next to the number of times the check
actually fired. All three zero-failure checks run on ~1,000+ real partitions.

**Two things changed during implementation, both from evidence:**

1. **The gross reconciliation is raised on BOTH lanes, not just npl_movement.** The audit's
   claim that "credit_quality and stages agree, so npl_movement is the outlier" is **unsound** —
   `bank_audit_stages` is DERIVED from `bank_audit_credit_quality` by `build_bank_audit_stages.py`.
   They are one source, not two. On inspection credit_quality is usually the *defective* side:
   ICBCT's gross freezes at 127,385 through 2024Q1/Q2 (a stale repeat of 2023Q4) and at 28,118
   across 2025Q2–Q4, while the movement closing tracks quarter by quarter. So it is a
   **disagreement detector** — it does not say which side is wrong — and flagging only one lane
   would leave the wrong number protected from re-extraction by `statement_passes()`.
2. **Curated skips must be exempt from the zero-pass rule.** The first calibration run turned
   **53 curated cells red** — ATBANK's regulatory-floor CAR (34) and total-less sector table (8),
   TEB's 2022 CARs (4), ALBRK/TSKB's cash-flow source typos (2), ICBCT's rounding (1), ATBANK's
   OCI sign typo (1). Those partitions have `checks_passed == 0` too, but it means the opposite:
   a human read the PDF and established the *source* doesn't foot. `revalidate_audit_db.curated_skips()`
   now exposes the lists and `_cell_status` exempts them. Caught by the calibration gate.

**Net effect: 77 cells ok → error**, every one a real defect: credit_quality 31 + npl_movement 31
(the two sides of each disagreement — ICBCT 17, PASHA 10, AKTIF/FIBA/ISCTR/QNBFB), stages 9
(SKBNK 5, FIBA 3, EMLAK 1 — exactly the predicted set), capital/fx/repricing 6 (genuine zero-pass:
ISCTR, TSKB). ANADOLU's 147 zero-pass npl_movement cells did **not** turn red — the new checks gave
them real passes, which is why checks landed before the status rule.

Also: `cross` (assets = liabilities + equity) now folds into both balance-sheet cells — it
previously mapped to no lane and could have failed unseen; the Coverage ✓ is now gated on
`has_validator` (it inverted: the three lanes with no validator earned it while 8 validated lanes
lost it); and the drawer states "not validated" explicitly instead of rendering nothing.

## What shipped in tier 2 (same day)

Same gate throughout: predict the flag set, calibrate on a DB copy, ship only a measured 0 FP.

| Check | Flags | FP | Note |
|---|---|---|---|
| `eq_paid_in_capital` — closing paid-in ⋈ BS S.1 | 52 (32 green) | **0/52** | EXIM 2024Q2: BS says ₺35.7bn, equity statement says **0** |
| `cf_chain` sum-surviving + `cf_roman_missing` | 8 | **0** | drop-detection **0% → 99.9%**; KUVEYT's ₺36.5bn roman IV |
| `oci_roman_missing` + III = Σ surviving | 5 | **0** | ISCTR 2025Q4 cons lost a ~₺90bn roman I |
| `pl_roman_missing` (anchors, not disc_net) | 2 | **0** | ODEA/TSKB wrapped-label XIII |
| `cross_statement` 0.5% → flat ±10k TL | 0 | **0** | corpus max deviation is **exactly 0.000000** |
| `check_profile` — cons ⋈ unco (NEW lane) | 16 | **0** | İşbank's "1 branch"; TSKB same Q4 fingerprint |
| `check_audit_opinion` (NEW lane) | 50 | **0** | 45 missing auditors, all Q4 annuals |
| free-provision recall LIKE widened | 8 | **0** | BURGAN's ₺1.87bn, ~~10~~ **8** cells |

**Cumulative: 117 cells ok → error across the two tiers, plus 66 on the two newly-validated
lanes.** `profile` and `audit_opinion` now have `has_validator=True` — 1,956 cells that asserted
only "a row exists" are now checked. **17 of 18 lanes have a validator.**

**The generalizable finding.** §2.2's "a check cannot detect the loss of its own input" is now
FIXED for cash_flow, OCI and P&L — but *not* by requiring rows. Requiring all seven cash-flow
romans flags 10 partitions and **2 are faithful** (ZIRAATD 2025Q3, DUNYAK 2024Q1 foot to gap = 0
without the absent roman). The fix is `check_b_block`'s shape: sum whichever sources SURVIVE and
check the target you don't need present — it reads the absent slot's *value*, not its presence,
which is the only way to distinguish nil from dropped. A presence rule structurally cannot.

**Corrections to this document, from evidence gathered while implementing:**
- §1.3's "63 shifted cells" counted **pages**, not partitions. It is **34** (32 green).
- §6.4's proposal to anchor equity components was right for `paid_in_capital` only.
  `share_premium` adds 0 flags; `other_capital_reserves` produces **4 FPs** (EMLAK ties on
  total, paid-in AND premium — its ₺98,418 of OCR simply sits in a different column of the other
  statement: a classification difference between two disclosures, not a defect).
- §6.9's "the extractor already handles the synonym (SKBNK proves it)" is **REFUTED**.
  `free_provision.py:51` matches only `free\s+provision` / `serbest\s+kar[şs][ıi]l[ıi]k`; SKBNK
  has rows because its text literally says "free provision". The extractor has the SAME blind
  spot — the widened LIKE raises the alarm correctly, but the data fix needs the extractor too.
- §6.7's `net_off_balance = off_bs_receivable − off_bs_payable` is **NOT shippable**: the 86
  failures are a storage-convention split (DENIZ stores the payable parenthesised-negative in
  102/102 rows), not defects. Sign-aware reaches 99.68%, but the residual 7 rows are either
  already caught by `fx_footing` (EMLAK ×3, a real thousands-separator-as-decimal bug) or
  unverified (TOMK 2025Q1, TAKAS 2023Q1 need a PDF read). Not circular, though — those three
  columns are independently parsed; only `net_position` is derived.
- §6 did not anticipate that **`free_provision` must NOT get `has_validator=True`**:
  `conditional=True` routes an empty cell to `not_expected` before any verdict is read, so a
  per-partition validator can never see the 469 N/A cells — the only ones with a problem.

**Rejected with the killing number** (recorded so they aren't re-proposed): the longitudinal
"fewer identities ran than this bank's median" alternative (10 CF flags vs 8; the 2 extra are
exactly the faithful ZIRAATD and DUNYAK — it sees only that an identity didn't run, never the
value); P&L sum-surviving (detection 4% → 60% but 3 FPs whose amounts are CORRECT at
`item_order = MAX`, the known `reference_pl_override_item_order` defect — fix item_order first);
`personnel >= branches` (0 flags in 811, and it passes DENIZ at exactly 1.00 — the very defect);
`opinion_type ∈ {clean, qualified}` (a closed 2-value enum cannot be violated); `basis_text ⇒
is_modified` (0 violations AND circular — is_modified is perfectly collinear with opinion_type);
bare `branches_total IS NOT NULL` (48% FP — 36 of 75 nulls are branchless digital banks).

## The sign claim was wrong (`95632b1`)

This report said the P&L deduction sign was free in 91% of identities, and I twice concluded from
that it was **"not cleanly fixable — the corpus genuinely mixes conventions within single
statements, so no per-partition check resolves it."** The mixing is real. The conclusion was not.

**The convention is derivable from the chain on 1048/1048 partitions.** The validator was never
defeated by ambiguity — it was discarding an answer it already had.

The mechanism, precisely: a deduction identity passes if EITHER `Σ|v| == D` (subtract the
magnitudes) or `Σv == D` (subtract the stored values) foots. The first reading is **sign-blind by
construction** — flipping a line's sign leaves its magnitude untouched — so the chain sails
through. That is the whole 91%.

The fix is to test the SIGNED block sum against `±(base − target)`: one convention per block,
which the chain determines uniquely. `check_pl_deduction_convention` — 2098 pass / 0 fail / 2
skip of 2100 possible, 0 FP. A flipped deduction sign: **12% → 100%** caught end-to-end.

**Independently corroborated:** the convention this derives agrees with `pl-sankey.ts`'s own
anchor heuristic (personnel XI., else II., else XII.) on **1048/1048**. The UI has been guessing
right for the whole corpus; the guess is now checkable instead of assumed.

**Faithful reversals still pass**, which is why the constraint is on the block TOTAL and not on
each line's sign: a released provision (BURGAN's ECL release, DENIZ's write-back) stores negative
inside a positive-convention block and reduces `Σv` by exactly as much as it reduces the net
deduction `D`, so `Σv == D` still holds. A per-line sign rule would have condemned every genuine
reversal — and `pl-sankey.ts:150-168` records that abs()-ing them once made the VIII→XIII
identity fail by ~190%.

**What actually remains uncovered** — narrower than this report claimed:
- Only the block's SUM is constrained, so moving value between two lines of one block is
  invisible (the same-band swap, 0/299).
- **The tax sign is free but INERT.** The chain pins `|tax|` via `cont_net = pretax ± tax` and
  genuinely cannot pick the side — tax is an expense in most quarters and a benefit in some, and
  both readings foot. It doesn't matter: `pl-sankey.ts:220` does `Math.abs(...)` and is the only
  consumer that reads it. Nothing downstream can be corrupted by it. "0/297 caught" is a
  non-finding, not a hole.
- `_pl_sign_convention` (alert-only, baseline-suppressed) reports 19 within-series flips. Those
  are now explained rather than mysterious — a flip is a genuine reversal quarter, and
  `check_pl_deduction_convention` is what proves the block still foots around it.

**The lesson worth keeping:** "the sources disagree, so nothing can be checked" was wrong twice in
one day — here, and in the `npl_closing_vs_gross` case where stages turned out to be derived from
credit_quality. Both times the reconciliation existed and was simply not being consulted. Prefer
measuring over concluding.

## 6. The fixes are already in the database (not applied)

Ranked by value; each is a reconciliation against a source we already hold, with a measured
false-positive rate of zero:

1. **`stages.total` vs BS loans line 2.1** — median 1.000; a [0.8, 1.3] band catches all 6
   denominator errors with **0 FPs**.
2. **Make the `npl_movement` closing-vs-gross comparison unconditional** instead of a last-resort
   rescue. `gross_by_group` is wired and available for **998/999** partitions. Would give all 147
   currently-unverified partitions a real check and flag all 19 hidden errors. Today the
   `else: add_fail` is dead code (138 rescues, 0 fails).
3. **`B = IV+V+VI` on off_balance** — holds **1,046/1,046 (100%)**, closes the dropped-section hole
   and guards the largest unconstrained number in the corpus (VAKBN's ₺92.7trn guarantees row).
4. **Anchor equity components to BS 16.1/16.2.1/16.2.3** — catches the EXIM/TFKB column shifts.
5. **`loans_by_stage.total = S1+S2`** — holds **983/983**; currently skipped because the identity
   demands all four non-null and `stage3_amount` is NULL by design in 1,036/1,036 rows.
6. **`closing − |provision| = net_balance`** on npl_movement — holds 2,097/2,097; testable on 100 of
   the 147 zero-check partitions.
7. **`net_off_balance = off_bs_receivable − off_bs_payable`** — holds 2,106/2,192 (96.1%); puts the
   two unchecked fx columns under a real check.
8. **`check_oci`: replace `.get(25)`** with the resolved `_pl_template(...)["period_net"]` — 6 skips
   become 6 passes. Same class as the heatmap.ts bug fixed in e72823f.
9. **Free-provision recall: widen the `basis_text` LIKE** beyond "free provision"/"serbest kar" to
   "general reserve"/"general provision". The extractor already handles the synonym (SKBNK
   2022Q1–Q3); only the check's LIKE doesn't.
10. **`_cell_status`: require `checks_passed > 0`** for `ok` — align it with `statement_passes()`.
11. **Map `cross` to a matrix lane**; **tighten V4** from 0.5% toward 1e-6.
12. **`_npl_collapse` covers `kind='unconsolidated'` only** — 455 consolidated cells get no
    corpus-level NPL check at all. It currently fires on 0 partitions and misses all 3 numerator errors.

**One stale rejection worth revisiting:** `check_credit_quality`'s docstring rejects a
`gross = provision + net` check as "genuinely noisy (~30% fail, ~200 flagged, many correct)" and
cites AKBNK 2024Q4 as "4% above". Measured on current data: **AKBNK 2024Q4 deviation = 0.000%**;
corpus median 0.000%; only **22/963 (2.3%)** fail at 1% — and those 22 concentrate on the same
ICBCT/PASHA/ISCTR partitions the independent reconciliation flagged. It **would have caught ISCTR
2025Q2**. (Caveat: partly enforced at extraction time, so the pass rate is somewhat tautological —
but the failures are diagnostic.) The rejection looks stale, not wrong in principle.

## 7. Findings retracted after checking (recorded so they aren't re-raised)

- **equity_change's 104 errors are NOT false positives** — the opening hypothesis was refuted.
  ~100 are real; the `is not None` component filter is dead code (0 NULL components in 33,384 rows).
  `eq_bs_cross` runs on 95.4%, and the participation-bank XIV concern is a non-issue (matched by
  label, not ordinal).
- **`check_pl_bottomline` is not 21%-skipped** — that docstring note is historical; it runs 1050/1050.
- **ZIRAAT ≠ ZIRAATK.** Ziraat Bankası 1,751–1,782 branches ✓; Ziraat Katılım 125–233 ✓. Both correct.
- **The 56.6% qualified-opinion rate is real**, not a misclassification (480/552 qualify over free
  provisions — the known BDDK-vs-IFRS artifact).
- **TOMK's compressed template ends at XXV**, so it is unaffected by the hardcoded-25 bug — memory's
  "DUNYAK/TOMK" is only half right for this one.
- **`_ecl_sanity` TOMK 2024Q2** is a false positive of the quality layer: the ECL row was always 0.0
  and V2 proves the section foots.
- **loans_by_sector has no dashboard consumer** (only `bot-schema.ts`) — memory's "page removed" confirmed.
- **stages/cq prior-period rows** (834 + 3,238) are validated by nothing and replay 386 failures, but
  all dashboard consumers filter `period_type='current'` — DB/bot-reachable only, not live.

## Related

`project_stages_lane_diagnosis`, `project_credit_quality_floor_fix`,
`project_off_balance_validator_strengthened`, `project_architecture_docs_check`,
`feedback_verify_validators_against_data`, `reference_pl_compressed_template`,
`project_heatmap_hardcoded_romans`
