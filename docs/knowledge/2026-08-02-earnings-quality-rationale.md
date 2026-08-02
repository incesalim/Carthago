# Earnings quality — editorial rationale — 2026-08-02

The "why" layer for an earnings-quality surface, written **before** any chart, per the
house order. Extends [`sector-story-spine.md`](sector-story-spine.md) and uses its
vocabulary (S# story sequence · T# priority tier · CAMELS · FSR · FSI · BBVA · the §5
chart rubric).

> **Status: RATIONALE — no code changed, nothing built.** This document decides *what
> question the surface answers, where it sits, and what the data can honestly carry.*
> Chart selection and implementation are a later pass, gated on §8 below.

Direct precursors: [2026-07-14 ALBRK free-provision finding](2026-07-14-albrk-2025q1-free-provision-reversal.md)
· [2026-07-17 could the DB alone have caught it](albrk-detectable-from-db-2026-07-17.md).
This doc is the answer to that second doc's closing line — *"the data is sufficient; the
pipeline does not look."*

---

## 1. The guiding question

> **How much of a bank's reported profit is the business, and how much is the
> management's discretion?**

One sentence, per the spine's own test. Everything below either serves that question or
is out of scope.

It is *not* "is this bank profitable" (that is S7/`/profitability`, built) and *not* "is
this bank's auditor unhappy" (that is a binary with a 57% base rate — see §4.3).

## 2. Why the spine needs it — CAMELS **M** has no direct evidence

The spine's own validation check #1 records the weakness:

> *"CAMELS completeness — every letter C/A/M/E/L/S maps to ≥1 tab. Today: S is unhomed
> (P0); **M is an external proxy via Ownership**."*

**M (Management) is currently inferred from who owns the bank.** That is a structural
proxy, not evidence of managerial conduct. Earnings quality is the first *direct*
M evidence our data can carry: it measures a discretionary act by management, dated,
quantified, and independently attested by the auditor.

This is the same class of finding as "S is unhomed" — the spine names a gap and the data
to close it already exists. It is arguably a stronger case, because S needed new
extraction (`fx_position`, `repricing`) whereas **M needs none**.

| Axis | Placement | Reasoning |
|---|---|---|
| Story sequence | **S7** (within Profitability) | It qualifies the earnings number the FSR profitability chapter reports. It is not a new chapter; it is a caveat on an existing one. |
| Priority tier | **T1** | Core CAMELS spine. Same weight as Profitability itself, because it modifies Profitability's headline. |
| CAMELS | **M** primary, **E** secondary | The measured object is managerial discretion; the affected metric is earnings. |
| FSR chapter | Profitability | The FSR discusses provisioning policy under profitability, not as its own chapter. |
| IMF FSI | none — *and that is the point* | No FSI captures discretionary reserving. The FSI core set standardizes ROA/ROE **without** asking whether they are real. This surface is a deliberate step beyond the comparability standard, so it must carry a methodology note rather than an FSI badge. |
| BBVA emphasis | real ROE (adjacent) | BBVA leads with *real* (inflation-adjusted) ROE. Discretion-adjusted ROE is the orthogonal correction: BBVA deflates the currency, this deflates the accounting. |

## 3. Why this is defensible to publish

Three properties, all rare:

1. **It is not an accusation.** Free provisioning (*serbest karşılık*) is legal,
   disclosed, and near-universal in Turkish banking. The surface reports a
   *magnitude*, not a verdict. The editorial frame is "how much discretion is in this
   number", never "this bank is cooking the books."
2. **The auditor already said it, in writing.** 552 of 976 filings carry a modified
   opinion and 545 carry the basis paragraph. We are structuring a disclosure the banks
   themselves published, not inferring a hidden one.
3. **Nobody publishes it.** A sector-wide free-provision series does not exist in public
   form. This is the single most differentiated thing in the database.

## 4. The architecture — three layers, because the naive version does not survive the data

The obvious build — *"rank all 38 banks by discretionary share of ROE"* — **fails on
coverage**, and failing quietly is the dangerous kind. The layers below are ordered by
data density, densest first.

### 4.1 Layer 1 — the reconciliation screen (primary detector, dense)

Profit that never became equity is the model-free signal. It needs no free-provision
disclosure at all.

```
gap = quarterly_net_profit − Δequity, net of dividends and OCI
flag when gap > 0.25 × opening_equity        (positive tail only)
```

Sources: `bank_audit_profit_loss` ⋈ `bank_audit_pl_roles` (role `period_net`) ·
`bank_audit_balance_sheet` (equity) · `bank_audit_equity_change` (dividends) ·
`bank_audit_oci` — which, note, is currently read by **nothing but the bot schema**, so
this layer gives the OCI lane its first analytical consumer.

Already measured (2026-07-17): **fires once in ~436 lending-bank-quarters, and the hit is
ALBRK 2025Q1 at 41.7%.** A precision of 1/436 is the whole argument for putting this
first — it is a screen an analyst can trust to be quiet.

Two rules that are not optional, both established by that run:
- **Positive tail only.** Negative gap = capital injection, benign (ATBANK 2025Q1 at
  −41.1%). Screening `|abs|` doubles the noise for nothing.
- **Net dividends out, or restrict to Q1.** Turkish AGMs sit in March, payouts land in
  Q2, and the un-netted any-quarter version reports TAKAS every summer.

### 4.2 Layer 2 — the discretion decomposition (corroborator, sparse)

Where the free provision *is* disclosed, name the amount and its contribution:

```
discretion_flow  = FP_stock(t) − FP_stock(t−1)        build (+) / release (−)
discretion_share = −discretion_flow / pretax_profit   share of profit that is discretion
```

**The denominator must be profit, not equity.** This is the correction the prior doc
demanded and it is load-bearing: VAKBN released **₺11bn at 2025Q1 — more in absolute
terms than ALBRK's ₺7bn** — under a qualified EY opinion, and Layer 1 is structurally
blind to it because VAKBN's equity base is ~12× larger (5.0% vs 38.0% of opening equity).
Against *profit*, both appear. VAKBN's stock swings continuously —
19.0 → 7.0 → 11.0 → 8.5 → 15.0 → 4.0 → 8.0 (₺bn, 2022Q4→2025Q4) — which is a smoothing
reserve operated as policy, not a one-off event. **That is the more important story than
ALBRK**, and it has never been examined.

⚠️ **The existing `roeAdjusted` is a different, weaker thing.** `heatmap.ts:587` computes
adjusted TTM net income = reported + (FP_now − FP_4q_ago), over average equity, and it
ships on `/banks/[ticker]` as a single stat. It requires **both** endpoints non-null, four
quarters apart. That is correct as far as it goes and must not be loosened — but it is a
per-bank stat, not an analysis, and the 4-quarter endpoint requirement is exactly what
makes it print for almost nobody.

### 4.3 Layer 3 — the opinion, as a taxonomy and not as an alarm

**This is where the naive read goes wrong.** 552 of 976 filings are modified — **16 of 36
banks at 2025Q1 alone**, across all four audit firms. A modified-opinion badge would light
up on nearly half the fleet and mean nothing.

> **The correct editorial treatment: `is_modified` is a *filter that removes ~40% of
> banks*, not an alarm that fires on 57%.**

The value is in `basis_text` — **545 captured paragraphs, read by nothing**. Classified
into *what the qualification is about* (free provision · bond/security reclassification ·
consolidation scope · other), a useless binary becomes the only structured map of what
Turkish auditors actually object to. State banks qualify over bond reclassifications;
participation and private banks over free provisions. That distinction is currently
invisible and it is the difference between two entirely different risks.

The classifier must be **deterministic** (regex/keyword over the paragraph, the same
construction as `src/audit_reports/audit_opinion.py`), consistent with *no LLM sets a
number* and with [[feedback_extractors_no_api]].

## 5. What the data will and will not support

Honest arithmetic, because the surface's credibility is the whole product.

| Lane | Coverage | Consequence for the surface |
|---|---|---|
| `bank_audit_opinion` | 976 / 1,050 partitions (**93%**); basis 545/552 modified | Dense. Layer 3 is safe fleet-wide. |
| `bank_audit_free_provision` | 581 explicit determinations / 1,050 partitions (**~55%**) — 503 holding, 78 explicit zero | Layer 2 is a corroborator, never a league table. |
| paired endpoints at one boundary | **5 banks** have an explicit determination at *both* 2024Q4 and 2025Q1 | A "who released this quarter" ranking would be computed on 5 of 38 banks. **Do not build it.** |
| Layer 1 inputs (P&L, BS, equity change, OCI) | ~100% | Dense. This is why it is the primary. |

**Three hard constraints:**

1. **ABSENT ≠ ZERO, and this has already burned us once.** Treating a missing
   free-provision row as zero fabricated a ₺9bn ZIRAAT release out of a period we simply
   never extracted, and printed it as a −1.41pp ROE haircut **on the live page**. The
   guard in `heatmap.ts` (both endpoints must carry an explicit determination, else null)
   is the correct pattern and every new consumer must repeat it. See
   [[reference_brsa_dash_three_tier_rule]].
2. **One mitigation is available and unused.** `bank_audit_free_provision.free_provision_prior`
   carries the prior stock from the note's own parenthetical comparison. Where present it
   yields a build/release from a **single row**, no paired endpoint needed. It is
   best-effort and may be NULL, but it should be the first fallback before declaring a
   period unknown — this may materially raise Layer 2's usable coverage, and **measuring
   that is the first task**, not writing the chart.
3. **`kind='unconsolidated'` throughout, or every figure double-counts.** Same trap the
   2026-07-17 run hit.

Two known bugs that this surface must not inherit:

- **The equity line is Turkish for most of the fleet.** `LIKE '%EQUITY%'` resolves 10 of
  36 banks; the rest report `ÖZKAYNAKLAR`. Match `'%ZKAYNAK%'` OR
  `'%SHAREHOLDER%'+'%EQUITY%'`, and anchor on the **name, not the roman** (XVI. deposit
  banks / XIV. participation). Layer 1 depends on this being right.
- **`TAKAS` is peer-excluded.** Apply `peersOnly()` / `peerExclusionSql()` at the point
  rows become one published number, never at the fetch.

## 6. Where it lives — a section, not a tab

**Recommendation: a section on `/profitability` (S7 · T1), plus a per-bank flag on
`/banks/[ticker]`. Not a new tab.**

| Option | Verdict |
|---|---|
| New `/earnings-quality` tab | **No.** Layer 2 is ~55% covered and Layer 1 fires once in 436 quarters. A tab that is mostly empty and mostly quiet reads as broken, not as rigorous. It would also orphan the metric from the ROE it corrects. |
| Section on `/profitability` | **Yes.** The surface's job is to qualify a number that tab already publishes. Placing the correction beside the claim is the honest IA — and the spine already marks Profitability `merge`. |
| Per-bank flag on `/banks/[ticker]` | **Yes, additionally.** Layer 1 is a per-bank event. The 2026-07-17 doc proposed exactly this home ("a validator lane check, surfaced as a flag") and it remains right. |
| A screen on `/cross-bank` | **Later.** Only after §8's coverage measurement says Layer 2 clears a quorum. |

Under the spine's §5 rubric, the anticipated classes — to be scored properly at chart time,
not asserted now:

- **Headline (≤1 here):** discretion-adjusted vs reported ROE, per bank, latest quarter.
  Question-fit 2, decision-relevance 2. Prints only where both endpoints are explicit.
- **Supporting:** the free-provision stock time series per bank (the VAKBN smoothing
  pattern is legible only as a series, never as a point).
- **Supporting:** modified-opinion composition by *basis category* — the Layer 3 taxonomy.
- **Depth:** the Layer 1 reconciliation table, all flagged bank-quarters, with the
  netting shown.

## 7. Registry gaps this exposes

`data/metric_knowledge/registry.json` (162 metrics) has **no free-provision metric and no
`roe_adjusted`** — despite `roeAdjusted` shipping on `/banks/[ticker]` today. **A metric
prints on the live site and the registry does not know it exists**, which breaks the
knowledge triangle the spine describes. Proposed entries, to be added with the build:

| id | group | level | reproducible | source |
|---|---|---|---|---|
| `free_provision_stock` | asset_quality | bank | direct | bank_audit |
| `free_provision_flow` | asset_quality | bank | derived | bank_audit |
| `roe_adjusted` | profitability | bank | derived | bank_audit |
| `discretion_share` | profitability | bank | derived | bank_audit |
| `profit_equity_gap` | profitability | bank | derived | bank_audit |
| `opinion_modified` | — (governance) | bank | direct | bank_audit |

Note `opinion_modified` has no home group — the registry's `group` axis has no
`governance` value. Adding one is the registry-side counterpart of CAMELS-M having no
tab, and the same argument applies.

## 8. What would make this wrong — the gates before any chart

In priority order. **Each is a measurement, not an opinion:**

1. **Measure Layer 2's true coverage with `free_provision_prior` as fallback.** If paired
   coverage stays near 5 banks/quarter, Layer 2 is per-bank commentary only and the
   headline chart in §6 does not exist. *This gate decides the shape of the whole surface.*
2. **Re-run Layer 1 with the Turkish equity matcher fixed.** The 1-in-436 precision was
   measured on a matcher that resolves 10 of 36 banks for signal 2; confirm the
   reconciliation leg was not similarly narrowed before trusting the number.
3. **Classify a sample of the 545 basis paragraphs by hand** before writing the classifier,
   to establish the real category set. Do not invent the taxonomy from the two examples
   we happen to know.
4. **Confirm no D1 write is required.** Every layer computes in the read path from stored
   rows. If any step wants a materialized table it becomes a recorded proposal, not a
   build — [[feedback_no_d1_writes_standing]].

## 9. Out of scope, deliberately

- **Any inference of intent.** The DB shows a release and a charge in one quarter; that
  they plug each other is a human inference the bank never states. The surface stops at
  magnitude.
- **The reasons that live only in prose** — BRSA letter 9196, the Bereket One AT1 sukuk,
  the auditor's clean ₺846mn. Not fields; not recoverable by any screen.
- **Cross-bank ranking by discretion** until gate 1 passes.
- **Extending to 2026Q2.** The unit switch (Bin→Milyon) is unresolved and extraction of
  further Q2 filings is frozen. This surface is built against 2022Q1–2026Q1.

## 10. Next

1. Gate 1 — coverage measurement (read-only SQL, local, cheap). **Start here.**
2. Gates 2–3 in parallel with it.
3. Only then: chart selection, scored against the §5 rubric, and a
   `data/dashboard_rationale/rationale.json` entry for the new section.
4. `VAKBN's continuous smoothing reserve` remains the most interesting unexamined thread
   in the database, and Layer 2 is the thing that would examine it.
