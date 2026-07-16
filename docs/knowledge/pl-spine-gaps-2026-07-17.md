# P&L roman-spine gaps: investigation

**Date:** 2026-07-17
**Status:** 🔍 INVESTIGATED. The live bug it surfaced is ✅ **FIXED** (`e72823f`,
verified live). The gap fixes themselves (items 2–4 below) are **not applied**.
**Follows:** [income-statement-errors-2026-07-16.md](income-statement-errors-2026-07-16.md)

## The question

66 identities across 59 partitions **skip** instead of running, because a roman
they depend on is missing from the spine. A skip is invisible — it never shows
red. Are these gaps hiding real values, or are they nil rows?

## Method

Rather than eyeball 59 PDFs, solve each gap arithmetically. For every skipping
identity with exactly one missing source, compute the value that roman *would
have to* contribute for the identity to foot:

```
need = target − Σ(known sources)      # sign-flipped if it sits in the deduction band
```

`need ≈ 0` ⇒ the gap is a nil row (harmless). `need ≠ 0` ⇒ a real value was lost.
Then confirm the non-zero ones against the source PDF.

## Result: 2 real losses out of 66

| Verdict | Count |
|---|---|
| Gap hides a **real value** | 5 → of which **3 already have the row** (see below) ⇒ **2 genuinely lost** |
| Gap is a **nil row** (identity foots with 0) | 55 |
| Unsolvable (3 missing sources — all XIV/XV/XVI) | 4 |

### The 2 genuinely lost values — both material, both the HAYATK bug class

| Partition | Roman | True value | Evidence |
|---|---|---|---|
| TSKB 2025Q2 unconsolidated | XIII (net operating income) | **7,107,832** | PDF p11: label wraps, `XIII. -XII)` at y=435.7, values at y=436.3. DB jumps XII→XIV. XVII = XIII + XV = 7,107,832 + 1,328,965 = 8,436,797 ✓ |
| ODEA 2023Q3 unconsolidated | XIII (net operating income) | **2,017,580** | PDF p12: label wraps over 3 lines, `XIII.` alone at y=472.6, values at y=469.1 (x=325 = the current column, matching VIII/IX/XI). DB jumps XII→XIV ✓ |

Same root cause as HAYATK 2024Q2: a **two-line wrapped label** detaches the
hierarchy from its values and the row is dropped. That bug has now produced
three separate defects (HAYATK's `(4.9.)`, plus these two), so it is a pattern,
not a one-off.

**Materiality:** no live surface reads roman XIII (`heatmap.ts` / `pl-sankey.ts`
read I, III, VIII, IX, XI, XII, XIX, XXV). So no dashboard number is wrong
because of these — the cost is data completeness plus an unvalidated XVII
identity on those two partitions.

### The 3 that already have the row — the appended-override trap, confirmed live

ANADOLU 2022Q1 `IV.`=84,249 · ANADOLU 2022Q2 `IV.`=176,594 · QNBFB 2022Q2
`VI.`=−115,160.

The solver derived these values independently — and they are **exactly** the
values already sitting in `audit_overrides.json`. The rows exist, with the right
numbers. They're just parked at `item_order` 65 (appended at `max+1`), so the
increasing-subsequence spine drops them and `VIII = III+IV+V+VI+VII` **has never
run** on those three partitions despite being "fixed".

This is the trap documented on 2026-07-16, now measured. `apply_overrides` gained
`item_order` for P&L inserts; these three entries predate it and still need
re-slotting. Note a plain re-author is not enough: the row now EXISTS, so the
override takes the UPDATE path, which ignores `item_order` and won't move it —
the branch needs a "move when `item_order` differs" step.

### The 55 nil gaps

| Cluster | n | What it is |
|---|---|---|
| HSBC XIV | 28 | Extractor split the PDF's **intact** `XIV.` token into hierarchy `X` + label `IV. BİRLEŞME…`. Value 0.0 present and correct. Pattern is 100% uniform across all 28 (same label, same amount). |
| ANADOLU XXIV | 6 | discontinued-ops net, nil |
| AKBNK / DUNYAK XIV, HSBC XXIV | 6 | nil |
| singles (ALNTF, ICBCT, ISCTR, PASHA, QNBFB, ZIRAATK, HAYATK, FIBA…) | 15 | nil |

Two notes:

- **HSBC is not corrupted.** It carries both a real `X.` (DİĞER KARŞILIK
  GİDERLERİ = 108,416) and the stray `X` fragment (0.0). The spine's
  longest-increasing-subsequence correctly keeps the real one and drops the
  stray — exactly what `_pl_spine`'s docstring claims. Only the XVII identity
  skips. The stored key is still wrong, though, and `pl_rehier` is the tool for
  it (it would need a `to_name`, which `bs_rehier` has and `pl_rehier` lacks).
- **DUNYAK 2023Q4 `X` / TOMK 2023Q3 `X`** are missing *by design*:
  `dedup_hierarchy_rows.py` (4cd7014) deleted them as junk placeholders
  ("…doldurulacaktır.)" parsed as a data row). True value nil. But note its
  docstring claims the recode "CLEARS the failure" — for DUNYAK 2023Q4 it
  converted a **fail into a skip**, which is not the same thing.

The 4 unsolvable ones (ANADOLU 2023Q3/2024Q3/2025Q1 cons, ICBCT 2024Q2 cons) are
all missing XIV+XV+XVI together. PDF-verified for ANADOLU 2023Q3: XVII = XIII =
3,102,728 ⇒ all three nil.

**Conclusion on the gaps themselves: the skip-on-missing behaviour is correct and
should stay.** Defaulting a missing roman to 0 would have silently swallowed
TSKB's ₺7.1bn and ODEA's ₺2.0bn. The gaps are 96% noise — but the 4% is exactly
what the conservative design is for.

---

## ⚠️ The real find: the same bug is LIVE on the read side

Chasing what consumes these romans surfaced a **user-visible wrong number**.
`heatmap.ts` hardcodes the standard ordinals — the identical mistake
`check_pl_chain` made, on the query side:

```sql
COALESCE(MAX(CASE WHEN hierarchy = 'XXV.' THEN amount END),
         MAX(CASE WHEN hierarchy = 'XIX.' THEN amount END))  AS net_profit,
MAX(CASE WHEN hierarchy = 'XI.'  THEN amount END)
  + MAX(CASE WHEN hierarchy = 'XII.' THEN amount END)        AS opex,
```

For the compressed template those romans are **different lines**:

**net_profit reads 0.** DUNYAK's period-net is XXIV, not XXV. `XXV.` is NULL, so
the COALESCE falls through to `XIX.` — which in DUNYAK's numbering is
*DURDURULAN FAALİYETLERDEN GELİRLER* (discontinued-ops income) = 0.

Verified against **production D1**:

| DUNYAK (unconsolidated) | dashboard reads | true period-net |
|---|---|---|
| 2024Q4 | **0** | 1,353,642 |
| 2025Q1 | **0** | 360,967 |
| 2025Q2 | **0** | 676,596 |

6 partitions affected (2024Q3, 2024Q4, 2025Q1 cons+unc, 2025Q2 cons+unc).
`net_profit` feeds **ROE** (heatmap.ts:508) — so DUNYAK's ROE is computed off a
zero numerator. DUNYAK is **not** peer-excluded (only TAKAS is), so this renders.

Not every DUNYAK quarter is hit: 2024Q1/Q2 use the XIX/XXV variant and read
correctly. The template varies **by period within one bank**, which is why this
survived.

**opex is wrong for 9 partitions** (DUNYAK ×8, TOMK 2023Q4). The real deduction
band is IX+X+XI; `XI.+XII.` picks up other-opex plus *net operating profit*:

| | dashboard opex | true opex |
|---|---|---|
| DUNYAK 2025Q1 | 713,144 | 790,846 |
| DUNYAK 2025Q2 unc | 1,300,867 | 1,755,433 |
| TOMK 2023Q4 | 254,357 | 298,699 |

`opex` feeds **Cost/Income** and **PPOP/assets**.

### ✅ FIXED 2026-07-17 (`e72823f`, live)

A derived table **`bank_audit_pl_roles`** (migration 0029) now tags each P&L row
with what it IS — `period_net`, `gross`, `opex_personnel`, `opex_other`, … —
resolved by `validator.pl_roles()` and rebuilt from stored rows beside the
validation, so the two can never disagree. `heatmap.ts` joins it instead of
guessing. Old-vs-new over the corpus: **9 rows changed, 0 regressions, row set
identical**. DUNYAK's ROE now renders **40.1%** live (numerator was 0).

### Original proposal (kept for the reasoning)

The lesson from the validator fix transfers directly: **key by label, not by
numeral.** Options, cheapest first:

1. Resolve the romans per (bank, period) from the same anchor logic the validator
   now uses, and have `heatmap.ts` select on that — a shared source of truth so
   the two can't drift again.
2. Failing that, select `net_profit` by label (`DÖNEM NET KARI` excluding
   SÜRDÜRÜLEN/DURDURULAN) and `opex` as the gross→net-operating band.

`pl-sankey.ts` reads the same hardcoded romans and needs the same audit — its
975/975 exact gate covers 975 of 1050 partitions, so the compressed-template
banks may simply be outside it.

## Recommended work order

1. ~~**`heatmap.ts` ordinal fix**~~ — ✅ done (`e72823f`, live).
2. **`pl-sankey.ts` + `standard_lines.ts` (`PL_LINES`)** — the same hardcoded spec
   (`XII.` = Other Operating Expenses *contra*, `XIII.` = net operating profit), so
   for DUNYAK it would render net operating PROFIT as an expense. **Unaudited** —
   the surface is tab-gated (not in the initial payload, so curl can't settle it)
   and its exact gate covers 975 of 1050 partitions, so the compressed-template
   banks may fall outside it. `bank_audit_pl_roles` is already there to join.
3. **TSKB 2025Q2 + ODEA 2023Q3 XIII overrides** — 2 real values, ~₺9bn combined.
4. **Re-slot the 3 appended overrides** (needs the move-on-`item_order` step).
5. **HSBC `X` → `XIV.` ×28** via `pl_rehier` + a `to_name` — mechanical; fixes 28
   wrong keys and lets 28 XVII identities run.
6. Leave the remaining ~24 verified-nil gaps skipping. Restoring them buys
   trivially-true identities.
