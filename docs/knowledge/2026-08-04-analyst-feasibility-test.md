# Can Carthago produce a working analyst? — feasibility test, 2026-08-04

> **Status: test complete, report only. No code, no data, no D1 write, no model.**
> Two credit memos written by hand from stored rows to answer one question: does
> the stored data support a real analyst product? Every figure below is derived
> from `data/bank_audit.db` (snapshot 2026-07-27) and `data/bddk_data.db`, unless
> marked otherwise. Amounts are **thousand TL** unless stated.

## Method

Two banks. **ALBRK as calibration** — its free-provision story is already
documented, so the test is whether the stored rows independently carry it.
**ŞEKERBANK blind** — chosen after ALBRK, from the 24 banks with a qualified
opinion, with no prior read of any analysis of it.

⚠️ **Calibration honesty:** the memory index already told me ALBRK had a
free-provision finding, so Case A is not a blind test of *me*. It is a valid test
of whether the **data** carries the fact and its magnitude without recourse to the
PDFs or the prior write-up. Case B is the blind one.

Conventions used, per the repo's own rules: total assets = `MAX(amount_total)`
across **both** balance-sheet legs; net profit via a **join on
`bank_audit_pl_roles`**, never a label match; ROE = TTM de-cumulated income ÷
5-point average equity, **not** YTD×(4/quarter); peers ranked within licence class.
CPI y/y at 2026-03 = **30.87%** (`TP.TUKFIY2025.GENEL`).

---

# Memo A — Albaraka Türk (ALBRK), 2026Q1

**Judgement: the reported profit history is not comparable to itself. A single
2025Q1 provision release of ₺7.0bn — which the auditor states was outside BRSA
rules — accounts for 89% of that quarter's printed profit, and it masked a
simultaneous collapse in the core margin. Read the underlying series, not the
printed one.**

**What it is.** Participation bank. **₺500.0bn** total assets at 2026Q1, **4th of
9** participation banks, **10.6%** of participation-sector assets — behind Kuveyt
Türk (₺1,477bn), Vakıf Katılım (₺889bn) and Ziraat Katılım (₺809bn). 226 branches,
2,787 staff. Assets **+43% y/y**, i.e. *below* 30.9% inflation-adjusted growth of
roughly +9% real.

**Capital.** CAR **15.77%**, CET1 **8.36%** (2026Q1). The headline sits 3.8pp above
BDDK's 12% target, but the composition is the story: the CAR–CET1 gap is **7.4pp**,
so nearly half of regulatory capital is non-core. CAR has fallen from **20.03%**
(2025Q1) as RWA grew from ₺172.3bn to ₺276.0bn (**+60%**) against total capital
+26%. CET1 at 8.36% is the binding constraint, not the 15.77% headline.

**Asset quality.** NPL **2.05%**, up from 1.41% at 2025Q1 — a steady four-quarter
rise (1.41 → 1.52 → 1.74 → 1.89 → 2.05). Stage 2 **6.1%** of the book. Stage 3
coverage **76.1%**, down from **85.7%** a year earlier. Rising NPL with falling
coverage is the direction that matters; the absolute level is still comfortable
against the participation peer group (Vakıf Katılım 4.48%, Ziraat Katılım 4.50%,
Kuveyt Türk 3.07%).

⚠️ *Comparability caveat:* these stage ratios are compared across banks whose Stage
2 definitions we do not hold. The accounting-policy notes that would make this
comparable are not extracted.

**Profitability.** TTM net income **₺6.24bn** over a 5-point average equity of
**₺22.07bn** → **ROE 28.3%**. Against 30.9% CPI that is **−2.0% in real terms** —
the bank is roughly holding its real capital, not building it.

**What the auditor said.** PwC, **qualified in every quarter held**, always over the
same thing. Verbatim, 2025Q1:

> "a portion of the free provision amounting to TL 7,000,000 thousand is reversed
> in the current period out of the total free provision of TL 7,300,000 thousand,
> which was provided by the Bank management in prior years **outside of the
> requirements of BRSA Accounting and Financial Reporting Legislation**"

**The one thing to know.** The printed 2025Q1 net profit was **₺7.846bn**. The
auditor states ₺7.0bn of it was a reversal of a provision that should not have been
there. Ex-release, the quarter earned **₺0.846bn** — against ₺0.614bn in 2024Q1, so
underlying growth was ~38%, not the ~1,180% the printed figures show.

The consequence runs forward. 2026Q1 printed **₺0.904bn**, which against the
printed 2025Q1 reads as an **88% collapse** — and against the underlying ₺0.846bn
is **+7%**. Any screen ranking banks on reported earnings growth has ALBRK
catastrophically wrong in both directions, a year apart.

And the release concealed something real: net profit-share income fell from
**₺2.22bn** (2024Q1) to **₺1.10bn** (2025Q1) — the core margin halved in the same
quarter the release flattered the bottom line. It has since rebuilt to **₺3.20bn**
(2026Q1), which is the genuinely good news in this filing and is invisible in the
headline series.

---

# Memo B — Şekerbank (SKBNK), 2026Q1 — blind

**Judgement: two headline ratios both flatter. A 22.1% capital ratio conceals CET1
of 8.6%, and a 1.33% NPL ratio conceals coverage that has fallen by 44% in two
years. The bank is growing its balance sheet at 85% a year while destroying real
equity at ~10%.**

**What it is.** Deposit bank. **₺235.2bn** assets at 2026Q1, **+85% y/y** — roughly
**+41% real** against 30.9% CPI. 239 branches, 3,329 staff. Equity **₺13.93bn**, so
equity/assets is **5.9%**.

**Capital — the finding.** CAR **22.13%** would place it among the better-capitalised
banks in the system on a screen. CET1 is **8.64%**. The gap is **13.5pp**, meaning
**61% of regulatory capital is non-core**.

| | 2024Q1 | 2024Q4 | 2025Q2 | 2025Q3 | 2025Q4 | 2026Q1 |
|---|--:|--:|--:|--:|--:|--:|
| CET1 | 15.25 | 16.94 | 12.92 | 11.46 | 11.01 | **8.64** |
| CAR | 22.12 | 23.25 | 17.87 | 24.18 | 22.49 | 22.13 |
| gap | 6.87 | 6.31 | 4.95 | **12.72** | 11.48 | **13.49** |

CET1 has almost halved in eight quarters while CAR is flat. The step is visible at
**2025Q3**, where CAR jumps 17.87 → 24.18 *while CET1 falls* 12.92 → 11.46, and the
leverage ratio jumps 6.67 → 10.54 — the signature of a large Tier 2 or AT1 issuance
plugging a core-capital hole. On current trajectory CET1 crosses below 8% within
two to three quarters.

**Asset quality — the second flatter.** NPL **1.33%** and falling every quarter
(1.70 → 1.45 → 1.34 → 1.30 → 1.33). Stage 2 **2.6%**, also falling. Both read
excellent. Stage 3 coverage over the same window: **86.2% → 48.3%**.

⚠️ **Corrected 2026-08-04.** The first version of this memo said the fall was
"consistent with covered NPLs leaving the book via write-off or sale". **That is
refuted by `bank_audit_npl_movement`: write-offs and sales are ZERO in every period
held.** The real decomposition, 2024Q4 → 2026Q1 (69.7% → 48.3%, −21.4pp):

| | Group III | Group IV | Group V | total |
|---|--:|--:|--:|--:|
| share of NPL, 2024Q4 | 17.9% | 14.4% | **67.7%** | 100% |
| share of NPL, 2026Q1 | 24.8% | 28.5% | **46.7%** | 100% |
| coverage, 2024Q4 | 25.8% | 27.9% | 90.2% | 69.7% |
| coverage, 2026Q1 | 21.8% | 24.9% | 76.7% | 48.3% |

Holding 2026Q1 balances at 2024Q4 within-bucket rates gives 56.5%, so **13.2pp of
the fall is mix and 8.2pp is genuine within-bucket erosion**. The mix shift is not
disposal — it is **new NPL formation**: additions to Group III ran ₺301m (2024Q4),
₺928m (2025Q4) and ₺391m in 2026Q1 alone. The book is filling with fresh NPL that
carries light provisions.

**Forward:** ₺981m sits in Groups III+IV at ~23% coverage. Seasoning into Group V
at ~77% implies roughly **₺530m of further provision** — about a quarter of TTM net
income — already committed by loans that have gone bad but not yet been
reclassified. **Falsifier:** Group III additions falling below ~₺200m/quarter, or
Group V coverage stabilising above 80%.

**Profitability.** TTM net income **₺2.21bn** on 5-point average equity **₺12.45bn**
→ **ROE 17.7%**. Against 30.9% CPI: **−10.1% real**. The bank is shrinking in real
terms while its balance sheet grows 85% nominally — profit +25% y/y in Q1 against
assets +85% means each new lira of assets earns materially less than the existing
book.

**What the auditor said.** Deloitte, qualified. Verbatim, 2025Q4:

> "…include a free provision that does not meet the requirements of BRSA Accounting
> and Financial Reporting Legislation of which **TL 350,000 thousand is recognized
> as income** … As of 31 December 2025, the total free provision is TL 1,000,000
> thousand"

So **₺350m of the ₺2.078bn full-year 2025 profit — 17% — was a free-provision
release**, the same mechanism as ALBRK at one-twentieth the scale.

**The one thing to know.** Nothing in the headline ratios shows the problem. A
screen on CAR ranks this bank top-decile; a screen on NPL ranks it top-decile. The
three things that matter — core capital halving, coverage halving, real ROE at −10%
— are all one derivation below the surface.

---

# Verdict

## 1. Could the memo be written? Yes, with one exception.

| Section | Verdict |
|---|---|
| Identity, size, peer rank | ✅ complete |
| Capital, trajectory, composition | ✅ complete, and the CET1/CAR split was the strongest finding in Case B |
| Asset quality levels + trend | ✅ complete |
| Asset quality **comparability** | ❌ **cannot be written** — stage definitions are not extracted |
| Profitability, real terms, FP-adjusted | ✅ complete |
| What the auditor said | ✅ complete — and better than expected (see below) |
| The judgement | ✅ both memos reach a non-obvious, defensible one |

## 2. Case A: pass, decisively.

The stored rows carry the ALBRK fact **and its exact magnitude** without touching a
PDF. `bank_audit_free_provision` shows 7,300,000 → 300,000; `pl_roles`-joined net
profit shows ₺7.846bn; and `basis_text` states "TL 7,000,000 thousand is reversed"
in the auditor's own words. Three independent stored sources agree.

**More than that — the data supported a finding I did not previously hold:** the
release coincided with the core margin halving (₺2.22bn → ₺1.10bn net profit-share
income), and the subsequent recovery to ₺3.20bn is invisible in the headline
series. That is the analyst's job, and the data did it.

## 3. Case B: pass, and it is the more important result.

Blind, from rows alone, the memo surfaced three things no headline ratio shows:
CET1 halving behind a flat CAR, a 44% collapse in NPL coverage behind a falling NPL
ratio, and −10% real ROE behind 85% nominal asset growth. None required a PDF.

## 4. The gap list — the build spec, derived from doing the work

1. **Stage-definition comparability is the missing half of asset quality.** Both
   memos had to disclaim their own peer comparison. This is the single highest-value
   gap and it maps exactly to the untaken §3 accounting-policy notes.
2. **`basis_text` is more useful than its 65% truncation implies.** The qualification
   is at the *start* of the field; the over-run is downstream. For a reader, the
   leading ~600 chars were sufficient in every case examined here. The truncation
   blocks *classification*, not *reading*.
3. **Free provision needs to be a first-class adjustment, not a footnote.** It moved
   89% of one quarter's profit at ALBRK and 17% of a year at ŞEKERBANK. Any earnings
   comparison that ignores it is wrong, and both banks are qualified over it every
   quarter.
4. **Nothing in the stored data flags "the headline conceals the composition."** The
   CAR/CET1 gap and the NPL/coverage divergence are both two-series derivations that
   no lane computes. These are cheap, deterministic and would have caught Case B
   automatically.
5. **CPI joins are manual.** Real-terms conversion needed a second database and a
   hand-picked series code. An analyst layer needs one deflator call.
6. **`nsfr` is null before 2024Q1** for both banks; `lcr` is null for SKBNK-adjacent
   partitions and for ALBRK 2025Q3. Sparse, but did not block a judgement.

## 5. Defects found on the way — filed, not queued

- **`_BASIS_END` has no Turkish next-headings** (`audit_opinion.py:103-110`) — only
  bare `Sonu[çc]`/`Görü[sş]`, missing *Kilit Denetim Konuları*, *Yönetimin …
  Sorumluluğu*, *Bağımsız Denetçinin Sorumlulukları*, *Diğer Husus*. This is why TR
  truncates 320/325 and EN only 33/220, and why the over-run content is Key Audit
  Matters.
- **The `matches[-1]` fallback returns the wrong paragraph** (`:189-192`) — ~5 rows
  hold clean-Conclusion wording. It should fail closed and return NULL.
- **`bank_audit_prose` cannot supply the qualification text** — prose emits nothing
  before §1 (`prose.py:586-591`, `:617-618`) and the auditor's report is front
  matter. `section_role='audit_report'` returns a ~363-char pointer block.
- **Hierarchy carries a trailing dot** — `hierarchy NOT LIKE '%.%'` returns zero P&L
  romans. The working form is the bot prompt's:
  `hierarchy GLOB '[IVX]*.' AND hierarchy NOT GLOB '*.*.*'`.

## 6. Screening note vs analyst — the distance, measured

⚠️ **The memos above, as first written, were screening notes, not analyst memos.**
They reported levels, trends and divergences. An analyst additionally (a) asks
*why*, (b) commits to a forward view, (c) quantifies what it costs, (d) says what
would falsify it, and (e) decides.

The distance was closed by **one query**, not by a model. `bank_audit_npl_movement`
turned "Şekerbank's coverage is falling" into: it is falling because NPL formation
is accelerating and new NPL lands in lightly-provisioned buckets; 13.2pp of the
21.4pp fall is mix and 8.2pp is erosion; write-offs are zero so nothing is being
cleared; ₺981m will season into a ~₺530m provision, a quarter of TTM income; and
here is what would prove it wrong.

That is the actual finding of this test. **The analyst gap is not reasoning
capacity — it is the number of questions asked of data already held.** My first
pass stopped at the first question and published a causal guess that the second
question refuted.

The same move applies to the rest: `kap_ownership` answers "who stands behind this
bank", `/regulation` answers "what changed in the regime this quarter", and the
untaken §3 notes answer "is this comparable to its peers". None needs a model.

## 7. The answer

**Yes — Carthago can produce a working analyst,** and the ceiling is higher than
the first pass suggested. Both memos are publishable, the blind case found more
than the calibrated one, and the second-question test showed the data supports
causal explanation and a quantified forward view, not just description.

The binding constraint is not plumbing, model or tool layer. It is:

1. **one missing dataset** — stage definitions, so peer comparison stops needing a
   disclaimer;
2. **two missing derivations** — CAR-vs-CET1 and NPL-vs-coverage divergence, each
   two series and a subtraction, neither computed anywhere today;
3. **a habit** — asking the second question. Every genuine insight in this test
   came from the follow-up query, not the first one.
