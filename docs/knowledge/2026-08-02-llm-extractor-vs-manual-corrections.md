# Can an LLM extractor replace the manual corrections?

**Date:** 2026-08-02 · **Status:** SPLIT VERDICT.
**Vision** (Part 1) — no. Best 53% of rows exact where 100% is required; the 59
hand transcriptions stay manual.
**Text** (Part 2) — promising. 88% on the per-cell corrections outside the
balance sheet, but three confidently-wrong figures in 80 calls keep it out of
anything that writes a number.
**Architecture** (Part 3) — the validator gate holds for identity-covered rows
and **does not exist for P&L leaves**, where a wrong figure passes silently.
Per-lane accuracy runs 88% down to 0. Viable only cell-by-cell, never globally.
**Evidence:** `scripts/scratch_bench_vision_extract.py` via `test-openrouter.yml`
task=`vision`, runs [30718532267](https://github.com/incesalim/Carthago/actions/runs/30718532267),
[30718799791](https://github.com/incesalim/Carthago/actions/runs/30718799791),
[30720123896](https://github.com/incesalim/Carthago/actions/runs/30720123896),
[30720892768](https://github.com/incesalim/Carthago/actions/runs/30720892768).

## Where the manual work actually is

Unit detection is solved by a regex ([2026-08-01](2026-08-01-llm-vs-regex-unit-detection.md)),
so the open question is the rest of the corpus. Two bodies of manual work exist,
and they are different problems:

**457 per-cell overrides** (`data/audit_overrides.json`) — the text is present,
the layout defeats the anchors. **The balance sheet is among the least affected:**

| lane | fixes | lane | fixes |
|---|---:|---|---:|
| `off_balance` | 105 | `fx_position` | 33 |
| `credit_quality` | 100 | `profit_loss` | 30 |
| `capital` | 58 | `npl_movement` | 27 |
| **`assets` + `liabilities`** | **35** | `oci` | 22 |

By bank: ALNTF 91, FIBA 70, ICBCT 31, HAYATK 29, QNBFB 26. So "which table needs
help" is **off-balance and credit quality**, not the balance sheet — which is
consistent with the balance sheet being the lane with the most identity checks
and the longest history of repair.

**59 hand-transcribed whole statements** (`data/manual_statements.json`) — the
page is not text at all, so no anchor work could ever recover it. This is the
only part of the pipeline whose cost is a person's afternoon, and therefore the
only place an LLM could add capability rather than duplicate it.

## ⚠️ An unreadable page has TWO mechanisms, and one of them is invisible

This cost a full bench iteration and is worth stating plainly:

| filing | pages | `get_images()` | `get_drawings()` | text |
|---|---|---:|---:|---:|
| FIBA 2025Q1 uncon | p11 (liabilities) | **368** | — | 267 |
| FIBA 2022Q1 uncon | p10–p16 (whole block) | **0** | **848–1,775** | ~270 |

FIBA 2022Q1 has **zero embedded images**. Its statements are drawn as **vector
paths** — every glyph is a path — so a check like `len(page.get_images()) > 40`
sees nothing wrong and reports the page as fine. The reliable test is
**low text length AND many marks of either kind**:

```python
marks = len(pg.get_drawings()) + len(pg.get_images())
drawn = len(pg.get_text().strip()) < 400 and marks > 200
```

Note `_locate_pages()` returns `{}` for these filings — it anchors on text, and
there is none. The drawn statement pages form one consecutive run in the fixed
BRSA order (assets, liabilities, off-balance, P&L, OCI, equity, cash-flow), which
is how the bench addresses them: verified p10/11/12/13/14/16 for FIBA 2022Q1.

## The result

`nvidia/nemotron-nano-12b-v2-vl:free`, page rendered at 120dpi JPEG, strict
`json_schema`, `reasoning.effort=none`, scored against the human transcript:

| statement | by name | **by position** | TOTAL row |
|---|---|---|---|
| FIBA 2025Q1 uncon liabilities | 5/47 (11%) | **25/47 (53%)** | OK |
| FIBA 2022Q1 uncon liabilities | 5/47 (11%) | 16/47 (34%) | OK |
| FIBA 2022Q1 uncon assets | 9/47 (19%) | 11/47 (23%) | **WRONG** |
| FIBA 2025Q2 uncon liabilities | TRUNCATED | — | — |

**Best case 53% of rows exactly right.** A balance sheet needs 100%: at 53%, ~22
of 47 rows are wrong, every identity check (TL+FC=Total, parent=Σchildren,
Σromans=TOTAL) fails, and the assets case got the **TOTAL row wrong**, which is
fatal however good the rest looks.

Score by position, not by name — the model reads `68.752.573` correctly and then
writes the label as `ALİNAN KREĞLER` or `PARA PIYASAİLARİNA BORŞLAR`. Turkish
diacritics are mangled and a spurious header row shifts everything by one, so
name-matching scored 13.5% when the digits were substantially better than that.
Position is also how the deterministic extractor aligns rows, the chart of
accounts being uniform.

**The failure is not consistent, which is worse than being bad.** FIBA 2022Q1
assets matched 46/47 names but only 9 amounts; FIBA 2025Q1 liabilities matched 5
names and got 25 amounts. Labels right / numbers wrong and numbers right /
labels wrong, from the same model on adjacent pages. There is no error model here
to build a guard against.

## Operational notes on the free VL endpoint

- `max_tokens` 8000 → **"Upstream idle timeout exceeded" (504) on every call**;
  4000 → truncated mid-table. 12000 with 5xx retry still truncated 1 in 4.
  Turkish row names tokenize badly enough that 47 rows exceed a naive estimate.
- A single 47-row page takes **minutes**; a 4-statement sweep cancelled a
  20-minute job. The job timeout is now 45.
- JPEG@120dpi is ~178KB base64 vs ~357KB for PNG@150 — worth halving, though the
  504s were generation speed, not payload.

## What this does and does not settle

**Settled:** the free `nemotron-nano-12b-v2-vl` cannot replace the hand
transcriptions. The 59 statements stay manual.

**Not tested:** a larger or paid vision model. This bench was scoped to Nemotron
by request, and a 12B "nano" is the small end of the range — a stronger VL model
is the obvious next probe, and the harness now takes `--model`.

**Not tested:** the 457 per-cell overrides with a *text* LLM. Those pages DO have
a text layer, so they are a different and much easier problem than this one — the
model would be re-reading text `fitz` already extracted, not doing OCR. That is
the more promising branch and it is untouched.

If any of this is ever promoted: the model returned figures here, which
`AGENTS.md` forbids in production. Nothing from these runs was written to D1, R2
or the snapshot, and a transcription that disagrees with an identity check must
stop for a human rather than be stored.

---

# Part 2 — a TEXT LLM on the per-cell corrections

**Status:** PROMISING — 88% on cells a human had to fix, 75% on a control set,
and most of the misses are my retrieval rather than the model. Not shippable as
written; worth a second look.
**Evidence:** `scripts/scratch_bench_text_cells.py` via task=`cells`, runs
[30736535192](https://github.com/incesalim/Carthago/actions/runs/30736535192) (18+18),
[30736676671](https://github.com/incesalim/Carthago/actions/runs/30736676671) (40+40).
Model: `nvidia/nemotron-3-ultra-550b-a55b:free` — the **largest** free Nemotron,
against the 12B nano that failed the vision half.

These pages **have a text layer**. `fitz` read them fine; the anchor logic put
the number in the wrong place. So the model re-reads text we already hold rather
than deciphering an image — a different and much easier problem than Part 1, and
the reason the result is different. **Balance-sheet lanes excluded by design.**

| set | n | match | differ | no answer |
|---|---:|---:|---:|---:|
| **repair** (extractor wrong, human fixed) | 40 | **35 (88%)** | 3 | 2 |
| **control** (already stored + validated) | 40 | 30 (75%) | 5 | 5 |

The control set exists because a repair rate alone is not interpretable — a model
that fixes broken cells while quietly breaking good ones is worse than useless.

**Read the control number carefully: it is mostly my harness.** Of its 10
non-matches, 4 are `found=false` on a page my crude label-search picked wrongly
(it landed on p2), and 5 are "label not found on any page" — see below. Only
**one** control cell is a genuine confident-wrong answer.

**The genuine model errors, and they are the ones that matter:**

| cell | want | got |
|---|---|---|
| QNBFB 2023Q1 uncon `profit_loss` | 6,632,553 | 0 |
| QNBFB 2023Q1 uncon `profit_loss` (control) | 449 | 175,010 |
| TAKAS 2023Q3 uncon `profit_loss` | 0 | 2,260,614 |

Three wrong figures in 80 calls, all `profit_loss`, and all **confidently wrong**
— a plausible number returned with `found=true`. That is the same shape as the
`v6_schema_effort` failure in the unit bench: the model does not signal doubt. Any
production use needs the answer checked against an identity, never stored on the
model's say-so.

## ⚠️ Accidental finding: 202 stored rows have figures fused into the label

The "label not found on any page" failures were not the model. They are stored
`item_name` values that carry digit fragments, so nothing matches them:

```
'Teminat Mektupları III-a-2,ii 105,,025544,,157'
'Dış Ticaret İşlemleri Dolayısıyla Verilenler 54,9 21'
'Cayılamaz Taahhütler 1,732 , 30'
'Menkul Kıymetler 100,1 06,'
```

Counted over the snapshot: **202 rows**, ALNTF 118, YKBNK 74, TEB 8, ATBANK 2,
in `off_balance` (128) and `assets` (74). The label has picked up digits from
neighbouring cells — `'Cayılamaz Taahhütler 1,732 , 30'` sits next to a TL amount
of 1,610,374 while the row above has 1,732,301.

**The amounts look sound** — 145 of 188 checked are non-zero and plausible — so
this reads as a label defect, not a figure defect. But it is not cosmetic: the
UI prints these names, and **any consumer joining on `item_name` silently misses
these rows**. Worth a separate look; not touched here (no D1 writes this session).

## Verdict on Part 2

Unlike the vision arm, this is not a no. 88% on exactly the cells the
deterministic extractor got wrong is a real signal, and the harness — not the
model — accounts for most of the rest.

What it is **not** is shippable. Three confidently-wrong `profit_loss` figures in
80 calls is disqualifying on its own for anything that writes a number. The
shape that would work is the same one the unit bench pointed at: **the model as a
second opinion that must agree with an identity check, with disagreement stopping
for a human** — never as the thing that sets the value.

Before any of that, the retrieval step needs to be real. Searching page text for
the row label is fine for a bench and is the binding constraint on these numbers;
a production version would use each lane's own page locator.

---

# Part 3 — every other table, and does the validator gate hold?

**Evidence:** `cells` run [30737545371](https://github.com/incesalim/Carthago/actions/runs/30737545371),
`scripts/scratch_bench_validator_gate.py` (local, read-only).

## The proposed architecture

> regex to its fullest → LLM where regex fails → validators ensure no wrong
> number passes → hand-fix what survives.

Parts 1–2 measured the middle step. This measures the rest.

## Accuracy is extremely uneven across lanes

The §4 / note lanes are a different shape from statement rows — a *named* metric
in a table — and they carry `source_page`, so retrieval is exact rather than a
label search. Same model, same settings:

| lane | LLM correct |
|---|---|
| statement rows (`off_balance`, `profit_loss`, `cash_flow`, `oci`) | **35/40 (88%)** |
| `fx_position` | 10/14 (71%) |
| `npl_movement` | 6/9 (67%) |
| `loans_by_sector` | 3/5 (60%) |
| `repricing` | 3/5 (60%) |
| `credit_quality` | 1/5 (20%) |
| `capital` | **0/5 (0%)** |
| `liquidity` | **0/2 (0%)** |

**Do not read capital/liquidity 0% as "the model cannot read capital tables."**
A large share of the stored values in those lanes are *derived*, not printed —
the override notes say so outright ("derived from identities (ratios reconcile
the kept components)", and TOMK's `lcr_total` 3768.83 was reconstructed from
HQLA ÷ net outflows). A model reading the page faithfully returns the printed
figure and is scored wrong against a reconciled one. The lanes need a bench with
printed-value ground truth before any claim about them is safe. What the table
does establish is that **per-lane accuracy varies from 88% to near zero, so a
single "LLM fallback" switch across all lanes is not a real option.**

## ⚠️ The validator gate holds for identity-covered rows, and NOT for leaves

The decisive test: substitute the model's wrong figure into the stored rows,
re-run the real lane validator, see whether failures rise.

| cell | truth | model said | validator |
|---|---|---|---|
| QNBFB 2023Q1 `XIX. NET OPERATING PROFIT/LOSS` | 6,632,553 | 0 | **CAUGHT** (`pl_chain`, 2 new failures) |
| TAKAS 2023Q3 `XXIV. DURDURULAN FAALİYETLER` | 0 | 2,260,614 | **CAUGHT** (`pl_chain` roman 25) |
| QNBFB 2023Q1 `4.2.1 Non-cash loans` | 449 | 175,010 | **ESCAPED** — zero new failures |

The mechanism is explicit in the code. `check_profit_loss` is
`check_pl_chain` + `check_pl_deduction_convention` + `check_pl_bottomline`, and
its own docstring says the parent=Σchildren machinery is **deliberately not
used** — P&L deduction lines carry "(-)" labels with additive signs and would
false-fail it. `validate_statement` (balance sheet) *does* run
`check_hierarchy_sums`, so BS leaves are covered.

**So: a P&L decimal leaf like `4.2.1` is constrained by nothing.** An LLM error
there is silent, reaches the database, and prints on the site. The gate is real
for romans, subtotals and spine rows; it does not exist for leaves in the one
lane whose validator drops the sum check.

## What this means for the architecture

The design is sound **where an identity covers the cell**, which is most of the
balance sheet and every roman in the P&L. It is not sound as a blanket rule.

Two concrete conditions before an LLM fallback could write anything:

1. **Only for cells an identity actually constrains.** That set is computable
   today — a row is eligible if some check would move when its value moves. A
   cheap implementation is exactly the mutation test in
   `scratch_bench_validator_gate.py`: perturb the cell, see if any validator
   notices. If nothing notices, the LLM must not be trusted there.
2. **Per-lane, not global.** 88% on statement rows and 0/5 on capital are not the
   same decision, and the capital number is not even measuring the right thing
   yet.

Everything else stays as it is: regex first, hand-fix what survives. The LLM's
value is highest not as a writer but as a **detector** — it disagrees with the
stored figure on a real error far more often than at random, and a disagreement
is a cheap signal to send a human to a partition.

---

# Part 4 — closing the validator hole, and tuning

## The hole is closed (shipped)

`check_pl_subitem_sums` — see `src/audit_reports/validator.py`. Depth>=3 decimals
only, and the restriction is measured over all 1,050 partitions:

| level | holds | usable? |
|---|---:|---|
| roman = Σ(its decimals) | 82.11% | **no** — roman IV is `4.1 received − 4.2 paid`, XVIII nets tax |
| depth>=3 parent = Σ(children) | **99.94%** (3142/3144) | yes |

Corpus impact: 3,144 new checks, **2 partitions newly failing** — FIBA 2023Q3
consolidated `4.1` off by 600, ODEA 2023Q3 unconsolidated `1.5` off by 24,659.
Both genuine. The gate test now catches **3 of 3, zero escaped**.

## ⚠️ Three of the four "model failures" were the harness

This is the load-bearing lesson of the whole investigation. Each of these was
first recorded as a model limitation and each turned out to be mine:

| symptom | apparent conclusion | actual cause |
|---|---|---|
| 8/22 on unit detection | "the model can't read a declaration" | `max_tokens: 200` starved a reasoning model |
| wrong figure for P&L `4.2.1` | "confidently wrong, unusable" | prompt passed a label printed TWICE (4.1.1 and 4.2.1) |
| `capital` 0/5, `liquidity` 0/2 | "can't read §4 tables" | fed the wrong page — `source_page` is where the SECTION starts |
| gate reported ESCAPED | "validators don't cover it" | mutation keyed on name, so it patched 4.1.1 not 4.2.1 |

Only the fourth changed a real conclusion; the first three each cost a full
round. **Before recording an LLM limitation here, verify the model was given the
question you think it was given.**

## Tuning results

Two fixes, measured on the same bench:

1. **Pass the hierarchy marker, not just the label.** Control-set *wrong answers*
   went **5 → 0**; the remaining control misses are retrieval, not bad figures.
2. **Read a 3-page window from `source_page`.** `source_page` marks the section
   start and §4 tables span pages — VAKBN's capital section starts p41 while
   "Toplam Risk Ağırlıklı Tutarlar 2,483,897,695" prints on p42.

| lane | before | after |
|---|---:|---:|
| `capital` | 0/5 (0%) | **3/3 (100%)** |
| `liquidity` | 0/2 (0%) | **1/1 (100%)** |
| `repricing` | 3/5 (60%) | **4/4 (100%)** |
| `credit_quality` | 1/5 (20%) | 3/5 (60%) |
| `npl_movement` | 6/9 (67%) | 5/9 (56%) |
| `fx_position` | 10/14 (71%) | 6/11 (55%) |
| `loans_by_sector` | 3/5 (60%) | 1/3 (33%) |
| **all named metrics** | **47%** | **64%** |

Repair and control both 6/6 on the latest draw (small samples — the field lanes
carry the signal).

**`fx_position` went DOWN, and that is informative.** Its errors are sign flips
and cross-currency bleed (want 899,389, got −4,958,766), so a wider window gives
it more neighbouring currency blocks and period columns to confuse. Retrieval
width is not monotonically good: the right window is per-lane, and for
fx_position it should probably narrow to the one currency block, not widen.

## Settled numbers (n=120) — and a correction on method

⚠️ **The per-lane figures above came from samples of 3–14 and should not have
been read as movement.** `loans_by_sector` "unchanged at 33%" was 1/3 versus 1/3.
Only the large mechanical jumps (capital 0% → 100%, caused by a page bug) were
ever safely real. Re-run at **n=120**, after all tuning, with
`nemotron-3-ultra-550b-a55b:free`:

| lane | n | accuracy |
|---|---:|---:|
| `capital` | 13 | **92%** |
| `repricing` | 15 | 80% |
| `npl_movement` | 29 | 76% |
| `liquidity` | 4 | 75% |
| `fx_position` | 27 | 67% |
| `credit_quality` | 15 | 53% |
| `loans_by_sector` | 17 | **35%** |
| **all named metrics** | **120** | **68%** |

`loans_by_sector` at 6/17 is now real: naming the row by its printed Turkish
label (`raw_label`, e.g. "Çiftçilik ve Hayvancılık" rather than `agri_farming`)
did **not** rescue it. That lane and `credit_quality` are the two genuinely weak
ones; `capital` is genuinely strong once it is handed the right pages.

## Cross-family model comparison, same cells

| | `nemotron-3-ultra:free` | `gpt-oss-20b:free` |
|---|---:|---:|
| overall | **29/42 (69%)** | 24/42 (57%) |
| `fx_position` | **11/14 (79%)** | 5/14 (36%) |
| `capital` | 3/5 | **4/5** |
| wall clock | **~5 min** | ~30 min |

Nemotron wins on both axes. The speed gap is structural, not incidental:
gpt-oss-20b answers `400 "Reasoning is mandatory for this endpoint and cannot be
disabled"`, so `reasoning.effort=none` — the single largest tuning win — is
unavailable there. **Model choice matters (69 vs 57), but far less than fixing
how the question is asked (47 → 68).**

## ⚠️ BRSA filings print the same label twice, with DIFFERENT figures

Three independent instances now, and it is the single most common cause of a
wrong cell:

| filing | label printed twice | values |
|---|---|---|
| QNBFB 2023Q1 P&L | `Non-cashloans` | 4.1.1 = 175,010 (fees received) / 4.2.1 = 449 (paid) |
| VAKBN 2025Q4 capital, **same page** | `Toplam Özkaynak (...)` | 479,407,722 / 479,398,199 |
| every `loans_by_sector` page | sector names | one block per period, repeated |

The VAKBN case is the sharpest: page 46 prints
`Toplam özkaynak (Ana Sermaye ve Katkı Sermaye Toplamı) 479,407,722` and
`Toplam Özkaynak(Ana sermaye ve katkı sermaye toplamı) 479,398,199` — differing
by 9,523. The extractor takes the first by anchor order; the model took the
second and was scored wrong.

**This weakens the "LLM as detector" hypothesis for these lanes.** A
disagreement is not evidence of a stored error — most of the ones inspected are
the model resolving an ambiguous label differently from the extractor's anchor
order. A detector built on raw disagreement would generate mostly false alarms;
it would need the disagreement to also break an identity before it is worth a
human's time, which is the same per-cell gate the validator work already points
to.
