# A BRSA audit report, end to end — every table, every disclosure, and which engine should read it

**Date:** 2026-08-02 · **Status:** 📋 REFERENCE (inventory + routing rule; no code
changed) · **Memory:** [[reference_audit_report_full_structure]],
[[project_llm_vs_regex_unit_detection]], [[project_llm_vision_extractor_bench]]

Visual version (Turkish): <https://claude.ai/code/artifact/cd4649a2-4dd1-42d1-9ad1-b735089de9ae>

## What prompted it

Two questions in sequence: "list the tables in an audit report and mark if we
extract or not", then "what other information is available", then — given that
regex is working well on the structured tables — whether an LLM could earn a
place on everything else. This document is the answer to all three, verified
against `src/audit_reports/registry.py`, the index of a real filing
(`AKBNK_2025Q4_consolidated.pdf`, 132 pp), a §6 scan across 14 annual reports,
the local `bank_audit.db` snapshot, and our own two LLM benches.

## Bottom line

**The axis is not tables-versus-text.** Regex wins on the financial statements
because BRSA mandates a uniform chart of accounts — every filer prints the same
line items in the same order — not because the data sits in a grid. Once that is
the real reason, the routing rule follows: a model is admissible where the
*phrasing* is unbounded but the *answer set* is not, and where nothing it returns
is a figure.

Most of the un-extracted **tables** (fees & commissions, Pillar-3, insured
deposits, the §5-VIII branch table) still belong to a parser — they have mandated
captions and fixed row labels. The genuine LLM candidates are all in the
**narrative**: what a qualification is about, key-audit-matter topics,
subsequent-event type, the §6 ratings block.

## The four tests, in order

1. **Does the target have a fixed surface?** A mandated row label, a heading from
   a closed set, a formulaic sentence repeated fleet-wide → **regex**. Free,
   offline, reproducible, and it cannot half-read a value.
2. **Is the answer a figure that gets stored?** Then a validator must move when
   the value moves. Where nothing moves, **no model at any accuracy** — see the
   validator hole below.
3. **Is the answer a label from a closed set, over prose that varies bank to
   bank?** → **model**, with an enum-only schema and `reasoning.effort = none`.
   It returns a label, never a number.
4. **Is there a text layer at all?** Drawn or scanned pages are readable by
   **neither** engine. That is transcription work.

Architecture that follows: a model sits on the parser's `UNKNOWN` branch, never
in the default path. A disagreement between the two is a **human stop**, not a
stored value.

## The evidence (our own, 1–2 August 2026)

### Unit detection — regex 22/22, and the models never win

| arm | score | cost | latency |
|---|---|---|---|
| **regex** | **22/22** | $0 | offline, instant |
| `nemotron-3-super-120b:free`, tuned (enum-only + effort=none) | 22/22 | $0 | 0.6s |
| `deepseek-v4-flash-0731` | 19/22 | $0.012 | 6.2s |
| `nemotron-3-super-120b:free`, untuned | 16/22 | $0 | 7.2s |

**Not one miss was a comprehension failure.** Both models quoted the correct
phrase verbatim and then failed to *return* it — DeepSeek emitted an empty slot
with the right phrase in its evidence field; Nemotron narrated until
`finish_reason: length`. The LLM is not worse at reading, it is worse at
returning — which is the half a regex cannot get wrong.

### Per-lane accuracy of one free text model (same model, same settings)

statement rows **88%** · fx_position 71% · npl_movement 67% · loans_by_sector
60% · repricing 60% · credit_quality 20% · capital 0/5 · liquidity 0/2.

⚠️ The capital/liquidity zeros are **not yet a fair measurement** — much of what
we store there is derived rather than printed, so a faithful read scores wrong
against a reconciled value.

### The retrieval ceiling — measured with zero API calls

capital 91% · credit_quality 65% · npl_movement 14% · **49% aggregate**. Read
this *against* the per-lane scores above: credit_quality's 20% sits under a 65%
ceiling. **Six times running, a recorded "model limitation" turned out to be the
harness** — starved token budget, a label printed twice, the wrong page, the
wrong sub-table, the wrong row.

### Three findings that decide the architecture

- **The model does not signal doubt.** Three confidently wrong figures in 80
  calls, all in P&L, all with `found=true`: 6,632,553 → 0; 0 → 2,260,614;
  449 → 175,010. There is no confidence signal to gate on.
- **⚠️ The validator gate has a hole.** Substituting those wrong figures into
  stored rows and re-running the real validators: 2 caught by `pl_chain`,
  **1 escaped with zero new failures**. `check_profit_loss` deliberately omits
  `check_hierarchy_sums` (P&L "(-)" labels carry additive signs and would
  false-fail), so **a P&L leaf is constrained by nothing**. The balance sheet
  *does* run hierarchy sums, so BS leaves are covered. An LLM fallback is
  therefore safe **per cell, never per lane**.
- **A free endpoint does not repeat itself.** Byte-identical config at
  temperature 0 with a fixed seed, calls spaced 2s: 22, 21, 20 and 17 out of 22.
  One benchmark run supports any conclusion.

### Vision: answered, no

Best 53% of rows exact where 100% is required, and the failure is *inconsistent*:
one filing matched 46/47 row names but 9 amounts, an adjacent one matched 5 names
and 25 amounts. No error model to guard against. The 59 hand-typed statements
stay hand-typed.

**⚠️ A page is unreadable two ways, and the second is invisible to
`get_images()`:** FIBA 2025Q1 p11 = 368 embedded images; FIBA 2022Q1 pp10–16 =
**zero images and 848–1,775 vector drawings**, every glyph a path.

### Where the manual work actually is

457 hand fixes: `off_balance` 105, `credit_quality` 100, `capital` 58,
`fx_position` 33, `profit_loss` 30, `npl_movement` 27, `oci` 22 — **balance sheet
only 35** across both halves. The lanes needing help are the ones the model scores
*worst* on. That is why the map below sends almost every figure to a parser.

## The report, §1–§7

Legend: ✅ in D1 today · ❌ not taken. Engine: **REGEX** / **HYBRID** (parser
locates, model normalises) / **MODEL** / **NEITHER**.

### Front matter (before §1)

| Item | Have | Engine | Note |
|---|---|---|---|
| **Reporting-unit declaration** | ❌ | REGEX | In the header of *every* note page. `thousand TRY` is a hard assumption in `schema.py`, never read from the filing. Needs a ≥22-page window — Q4 annuals hide it on p7–p17. |
| Bank, period, consolidated/solo | ✅ | REGEX | From discovery, not parsed from the PDF |
| Address, phone, website, contact person | ❌ | REGEX | Fixed labels, fixed block |
| Consolidated subsidiaries / associates / JVs | ❌ | HYBRID | Column count varies; ownership already from the KAP scrape |
| Signatories — chair, audit committee, GM, CFO | ❌ | HYBRID | Name/title pairs the text layer interleaves |
| Report publication date | ❌ | REGEX | |

### The independent auditor's report (printed at the front, cross-referenced §7)

| Item | Have | Engine | Note |
|---|---|---|---|
| Opinion type | ✅ | REGEX | Mandated headings, closed set. **552 qualified / 424 clean** in the local snapshot |
| Audit firm | ✅ | REGEX | **931/976** filled: PwC 337, EY 269, Deloitte 198, KPMG 127 |
| Audit vs limited review | ✅ | REGEX | 234 audits / 742 reviews |
| Basis-for-qualification paragraph | ✅ | REGEX | Stored verbatim on 545 modified opinions |
| **What the qualification is _about_** | ❌ | MODEL | We hold the paragraph, classify none of it |
| **Audit report date + city** | ❌ | REGEX | Restated in the §7 body in a near-identical sentence fleet-wide → filing lag |
| **Signing partner** | ❌ | REGEX | "Sorumlu Denetçi: `<name>`" → partner rotation |
| **Key audit matters** | ❌ | MODEL | AKBNK 2025: TFRS-9 loan impairment, pension obligation, IT audit |
| Responsibilities boilerplate, TTK 402/4 | ❌ | NEITHER | Identical in every filing |

### §1 General information (7 sub-items)

| Item | Have | Engine | Note |
|---|---|---|---|
| Branch & personnel counts | ✅ | HYBRID | ~15 hand-written patterns; **906/981** branches, **887/981** personnel. The residue is the textbook UNKNOWN-branch case |
| II. Capital structure, controlling shareholders | ❌ | HYBRID | KAP covers ownership; the value here is the narrative of intra-year changes |
| III. Board & management, their shareholdings | ❌ | HYBRID | Consistent record shape, inconsistent typesetting |
| IV. Qualified shareholders | ❌ | REGEX | Small fixed table |
| I / V / VI / VII. History, business lines, consolidation method, transfer impediments | ❌ | MODEL | VII is a reasoned yes/no |

### §2 Financial statements — the parser's heartland

| Item | Have | Engine | Note |
|---|---|---|---|
| Balance sheet — assets, liabilities, off-balance | ✅ | REGEX | Hierarchy sums run; a wrong leaf is caught |
| Income statement (P&L) | ✅ | REGEX | Model scored 88% here — and produced the 3 silent errors. Closed to a model regardless of score (no identity constrains a leaf) |
| OCI, changes in equity, cash flow | ✅ | REGEX | Three of the five primary statements TAS 1 requires |
| **Profit distribution (Kâr Dağıtım Tablosu)** | ❌ | REGEX | §2-VII. Same table grammar as its neighbours — the only §2 table we don't take |
| Statement pages with no text layer | ❌ | NEITHER | 10 reports have no locatable balance sheet |

### §3 Accounting policies — 28 sub-notes, none taken

| Item | Have | Engine | Note |
|---|---|---|---|
| ECL methodology | ❌ | MODEL | Not purely qualitative: DPD thresholds and forward-looking scenario weights sit inside sentences. Reading aid only — nothing it surfaces is stored |
| The other 27 policy notes | ❌ | MODEL | Presentation basis, derivatives, leases, tax, segment policy, EPS… editorial value |

### §4 Financial structure & risk — 13 sub-sections, 5 taken

| Item | Have | Engine | Note |
|---|---|---|---|
| I. Capital · III. Currency risk · IV. Interest-rate risk · VI. Liquidity/LCR/NSFR · VII. Leverage | ✅ | REGEX | Capital reconciles internally, which is what makes it validatable |
| II. Credit risk detail — geography, sector, counterparty, **securities by Moody's band** | ❌ | REGEX | Fixed row labels (Aaa, Aa1–Aa3, …, unrated) |
| **X. Risk management — the Basel Pillar-3 block** | ❌ | REGEX | RWA by risk type, CCR, securitisation, market risk, operational risk. ~18 pp of standard templates. `fn_market_risk` ~100% and the **only rate-risk line both bank types print** (repricing ladder is conventional-only, 81%) |
| V. Equity-position risk · VIII. Fair-value hierarchy · IX. Fiduciary · XIII. Segments | ❌ | REGEX | All mandated-caption tables. Segments 89%, maturity ladder 99% |
| XI. Hedge accounting · XII. Remuneration policy | ❌ | MODEL | Narrative; remuneration is qualitative by design |

### §5 Notes to the statements — the largest section

| Item | Have | Engine | Note |
|---|---|---|---|
| Credit quality, IFRS-9 stages, NPL movement, loans by sector, free provision | ✅ | REGEX | 233 of the 457 hand fixes live here. Stage columns are section-dependent — the ambiguity that sank the model to 20% |
| Reserve requirements · deposits by maturity · **insured vs uninsured deposits** · funds borrowed · tax · paid-in capital · securities revaluation fund | ❌ | REGEX | Mandated captions, fixed labels. Nobody else publishes the insured-deposit split per bank |
| Interest income/expense by source · **fee & commission detail** | ❌ | REGEX | Fees in **100%** of reports — the highest-coverage table we don't take |
| **Senior management compensation** (§5-VII.5) | ❌ | REGEX | Formulaic sentence + one figure. AKBNK 2025: ₺1,216,239k vs ₺888,704k prior. Being a figure, needs a band/prior check |
| **Branch table** (§5-VIII) | ❌ | REGEX | Richer than the sentence we parse: domestic branches + employees, foreign branches with country/total assets/legal capital, openings and closings |
| Subsequent events (§5-IX) | ❌ | HYBRID | Parser finds the note; the event *type* is a closed-set label |

### §6 Other explanations

| Item | Have | Engine | Note |
|---|---|---|---|
| **Agency credit-ratings summary** | ❌ | HYBRID | Mandated but **bank-dependent**: of 14 annuals scanned, ALNTF and ANADOLU print a full block (agency, date, FC/LC long & short, national, support, viability, outlook); AKBNK, ALBRK, AKTIF print "Bulunmamaktadır". Agencies and grades are closed sets; the layout is not |
| Whatever else a bank puts here | ❌ | MODEL | Some file subsequent events here instead of §5-IX. The one section with no mandated shape |

### §7 Explanations on the auditor's report

| Item | Have | Engine | Note |
|---|---|---|---|
| Firm name + pointer to the report at the front | ✅ | REGEX | Two or three sentences, near-identical fleet-wide; the report date sits here |
| §7-II other notes prepared by the auditor | ❌ | NEITHER | Almost always "Bulunmamaktadır" |

## Where a model earns its place — six candidates

All share one shape: unbounded phrasing, bounded answer set, nothing returned is
a figure.

1. **What a qualification is about** — 545 basis paragraphs stored, none classified.
2. **Key audit matter topics** — the only place the auditor says what worried them.
3. **Subsequent-event type** — capital action / rating action / acquisition / legal.
4. **The §6 ratings block** — grades are a closed set per agency, so a value
   outside the set is rejected outright. **The enum is the validator.**
5. **Branch & personnel, on the UNKNOWN branch only** — the model never sees the 906.
6. **ECL policy as a reading aid** — surfaces where two banks stage differently.
   Nothing it produces is stored.

**Call shape**, settled by the unit bench: enum-only response schema,
`reasoning.effort = none` (output 13,852 → 205 tokens, latency 6.6s → 0.6s, no
loss), and **no free-text evidence field** — that field was the actual cause of
both failure modes. Free tier suffices: Cerebras `gpt-oss-120b`, Groq same-model
failover, keys already CI secrets ([[project_free_model_lane]]).

## Rules that don't bend

1. **No model sets a figure.** `check_prose_claims.py` already enforces this on
   the editorial layer; extraction is held to the same line
   ([[feedback_extractors_no_api]]).
2. **Per cell, never per lane** — eligible only where a validator moves when the
   value moves.
3. **Disagreement is a human stop** — not a tie-break, not an average.
4. **Free tier only.** No paid API in the extraction path.
5. **Measure the ceiling before blaming the model**
   ([[reference_deterministic_probes_before_llm]]).
6. **Never trust one run of a free endpoint,** and re-score any detector on a
   random draw across the full history — the unit regex scored 22/22 twice while
   silently failing 18 of 200 Q4 filings, because the *window*, not the pattern,
   had been fitted to the sample.

## Corrections to `audit-extraction-coverage-2026-07-15.md`

That doc was the previous coverage snapshot and is stale on two points, corrected
here:

1. **The registry now holds 18 statement types, not 17.** `profile`,
   `audit_opinion` and `free_provision` are all registered (the older doc lists
   them as "screens not in registry"). Still 16 D1 tables — assets, liabilities
   and off-balance share `bank_audit_balance_sheet`.
2. **`bank_audit_opinion` stores more than the opinion type.** It also holds
   `auditor` (931/976 filled), `basis_text` (545), `report_kind`, `language` and
   `source_page`. The audit firm is *not* an extraction gap.

Also refined: the §6 ratings summary is **bank-dependent**, not uniformly present
— and the "ratings table" in §4-II is a different thing (the securities portfolio
bucketed by Moody's grade).

## Related

- `src/audit_reports/registry.py` — the authoritative list of what we extract
- `docs/AUDIT_BANK_CATALOG.md` — per-bank quirks + the §4/§5 anchor census
- `docs/knowledge/2026-08-01-llm-vs-regex-unit-detection.md` — the unit bench
- `docs/knowledge/2026-08-02-llm-extractor-vs-manual-corrections.md` — the extractor bench
- `docs/knowledge/audit-extraction-coverage-2026-07-15.md` — prior snapshot (see corrections above)
