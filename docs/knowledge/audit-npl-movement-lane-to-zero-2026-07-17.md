# NPL-movement lane → 0 errors, 0 missing

**Date:** 2026-07-17 · **Status:** COMPLETE — shipped, live in D1 · **Lane:** `npl_movement` (§5)

| | before | after |
|---|---|---|
| errors | 13 | **0** |
| missing | 43 | **0** |
| ok | 992 | 999 |
| manual | 0 | **9** (were reading `ok`) |
| N/A | 2 | **42** (each with a verbatim citation) |
| fleet errors | 288 | **275** |

Companion to [audit-stages-lane-to-zero-2026-07-17](audit-stages-lane-to-zero-2026-07-17.md).

## The 13 errors — one bank, one missing string

**HAYATK ×12.** The closing row is printed, in bold, in every report:

> **`Ending balance of the current period`**

`_match_row_label` does `lower.startswith(lbl)`, and that word order is the one `"ending balance …"`
variant `_ROW_LABELS` never learned. The list already carried BURGAN's
`("ending balance of prior period", "opening_balance")` — the **opening** mirror, added 2026-06-27.
Its closing counterpart was never added. Nothing else could reach it: every other closing entry
starts with a different word (`current period ending balance`, `balance at the end of the period`,
`closing balance`, `dönem sonu bakiyesi`, `period end balance`), and the bare
`("current period", "closing_balance")` fallback can't either — the line *contains* "current period"
but doesn't **start** with it.

**The article is load-bearing.** HAYATK writes "of **the** current period"; adding
`"ending balance of current period"` would still have missed.

The row reached the parser intact — all three group numbers on one reconstructed line. Only the
taxonomy lookup failed:

```
[opening_balance |NUM] Ending balance of prior period 169,394 22,037 -
[additions       |NUM] Additions in the current period (+) 394,203 484 47
[None            |NUM] Ending balance of the current period 104,149 237,329 165,366   <-- dropped
[provision       |NUM] Provisions (-) (31,938) (48,093) (16,494)
[net_balance     |NUM] Net balances on balance sheet 72,211 189,236 148,872
```

**The natural experiment.** 2025Q2 consolidated is HAYATK's only report filed in **Turkish**
(`Dönem Sonu Bakiyesi`) — and the only consolidated period that passed. The 12 failures are exactly
the English reports. HAYATK was also the entire corpus story: 66 rows / 12 partitions, while all
4,281 other rows already had `closing_balance`.

### Transcribed, not derived — and why that mattered

`closing_balance` was over-determined **three** ways, all agreeing to the lira:
1. roll-forward: `opening + additions + transfers_in − transfers_out − collections − write_offs − sold`
2. `net_balance + |provision|`
3. prior closing == current opening

**Filling it from our own arithmetic would have made the roll-forward check
`closing == opening + flows` TAUTOLOGICAL** — passing by construction and verifying nothing. That is
precisely the circular-validation flaw the robustness audit found in fx `net_position` (29.4%
tautological). So the extractor now reads the printed number and the check stays a real test.
**13/13 partitions match the page.** The derivation agreed on 39/39 group-cells — but agreement was
the *check*, not the source.

Corroborated against a **different note** and the **balance sheet** (2025Q4 unco):

```
NPL gross III+IV+V (printed closing)      =    506,844
npl_brsa_gross total (separate note)      =    506,844   MATCH
stage1 13,072,410 + stage2 193,657 + NPL  = 13,772,911
BS assets 2.1 "Loans"                     = 13,772,911   MATCH
stage1+2 ECL 27,092 + stage3 prov 96,525  =    123,617
BS assets 2.4 "Expected Credit Loss (-)"  =    123,617   MATCH
```

`fx_diff` NULL is **faithful, not a bug**: HAYATK prints no FX row (0 hits for
`kur fark|çevrim|foreign currency|exchange rate` across all 14 pages). cons ≡ unco in every period.

**ZIRAATD 2026Q1 ×1 — the mirror.** `opening_balance` NULL, not closing. Its first-ever NPL quarter,
and the opening row's three cells are printed **genuinely blank — not even the '-' every other row
carries**, so `_THREE_NUMS_TAIL` finds no numeric tail, the row is skipped, and the block starts on
`additions` via `start_as_flow`. `opening = 0` is **sourced**: the report discloses the prior period
in prose — *"(31 Aralık 2025: Bulunmamaktadır)"* — the bank positively stating it held no NPL at
31.12.2025. `closing` (52) stays as extracted, so the roll-forward runs as a real test and ties:
`0 + 52 = 52`; `net 42 + provision 10 = 52`.
Fixed by **override, not code**, on purpose: the blank-opening shape only occurs in a bank's
first-ever NPL quarter (from 2026Q2 ZIRAATD's opening carries 52 and extracts normally), and
`npl_movement.py:358` records that a broad "numberless opening row → 0" merge **corrupts GARAN/TSKB**.

## The 43 missing — 42 N/A, 1 real gap

All verified 2026-07-17 by a **language-agnostic full-document sweep** plus a bitmap/vector/low-text
detector on every page — not a keyword probe. No bitmaps, no vector outlines, no wrong-PDF cases.
Every N/A carries a **verbatim citation**; the extractor returns 0 rows because no table exists.

| bank | cells | citation |
|---|---|---|
| TAKAS | 16 | *"i.2) Toplam donuk alacak hareketlerine ilişkin bilgiler: **Bulunmamaktadır**"* — all 16 checked mechanically |
| DUNYAK | 8 | *"j. Donuk alacaklara ilişkin bilgiler (net): **Bulunmamaktadır**"* |
| HAYATK | 5 | *"Information on the movement of total non-performing loans — **None**"* |
| TOMK | 5 | 3 with no loans note at all; 2 prose-only (below) |
| ENPARA | 3 | *"Donuk alacaklara ilişkin bilgiler (Net): **Bulunmamaktadır**"* |
| COLENDI | 3 | *"h.2) Information related on non-performing loans: **None**"* |
| ZIRAATD | 2 | *"7.8.2. Toplam Donuk Alacak Hareketlerine İlişkin Bilgiler **Bulunmamaktadır**"* |

**⚠️ The TAKAS story I brought was FALSE — the citation saved it.** The intuitive hypothesis ("a CCP's
*Krediler* are money-market/clearing placements, not credit") is wrong: TAKAS's loans **earn loan
interest** (*Kredilerden Alınan Faizler* 491,308 vs *Para Piyasası İşlemlerinden* **0**), are booked
as loans, are 100% *"Mali Kesime Verilen Krediler"*, all Standart Nitelikli with nothing in Yakın
İzleme — and ₺6.58bn of 2026Q1's ₺9.63bn is *"Banka ortaklarına verilen doğrudan krediler"*: its own
clearing members are its shareholders. It is **real credit exposure that never goes non-performing**.
The verdict was right; the reasoning would have been fiction. This is why N/A needs a citation and
not a plausible story.
**Near-miss:** TAKAS 2023Q4 p91 *does* print a nil III/IV/V-style table — but at `h)`, the NPL
**stock** by group (all '–'), while `i.2)` (the **movement** note) still reads Bulunmamaktadır. N/A
stands for this lane; that nil stock table is a sourced zero for a *different* one.

**TOMK 2024Q2/Q3 — the judgment call.** The note **is** printed and **carries a figure**; it just
isn't a roll-forward: *"30 Eylül 2024 tarihi itibarıyla Donuk alacak tutarı **4.406 TL**'dir (31
Aralık 2023: Bulunmamaktadır). … cari dönem içerisinde donuk alacaktan yapılan bir tahsilat
bulunmamaktadır."* (Q2: 2 TL.) N/A is correct for **this** lane only because the lane *is* the
III/IV/V table and TOMK files none — its note numbering carries no such table until **2024Q4**,
exactly the first period this lane extracts. It is **not** a claim that TOMK disclosed nothing: the
stock is captured, from this same prose, in `credit_quality`/`stages`.
Deliberately **not** stored as a synthesised roll-forward: the prose almost yields one (opening nil +
collections nil + closing 4,406 ⇒ additions 4,406; note `e)` even splits the provision by group,
Group III = 882) — but `additions` would then be **our arithmetic**, and it would make
`npl_closing_vs_gross` tautological against a `credit_quality` figure read from the **same sentence**.

### The one real gap — COLENDI 2026Q1 (curated; extractor fix still OPEN)

COLENDI's first-ever NPL (₺26,725 = **2.50%** of its ₺1,068,515 book). The roll-forward **is**
printed at p49. **Three independent defects hide it — fixing only the first would not recover it:**

1. **`_HEADING_RX` fails** — COLENDI heads it *"Information **related to** non-performing loans"*;
   the word *movement* never appears, so the page is never parsed. (`_GROUPS_RX` passes.)
2. **THE REAL BLOCKER — the text layer is CELL-PER-LINE.** Label and each of the three group values
   land on separate lines. `_THREE_NUMS_TAIL` needs `label num num num` on one reconstructed line, so
   it matches **zero** rows even with the heading gate bypassed (verified). Needs **x-coordinate row
   assembly** — the same class as the known `loans_by_stage` §7.2 column-split gap.
3. **Missing row label** — closing reads *"Balance at the end of period"*; `_ROW_LABELS` has only
   *"balance at the end of **the** period"*.

Curated by override. **⚠️ This recurs every quarter**: COLENDI now originates NPL and uses this
wording each time (2025Q2–Q4 *"related **on**"*, 2026Q1 *"related **to**"* — neither matches).
Reconciles three ways: closing 26,725 == its own Stage-3; provision 5,345 == note `g)`; net 21,380 =
26,725 − 5,345.

## Honesty fix — `_STMT_TO_KEY` learned `npl_movement`

9 partitions carry hand-read `npl_movement` cells (FIBA ×6 out of bitmaps/vector outlines, COLENDI,
ZIRAATD, AKTIF 2023Q3's two-page current/prior mix-up) and every one read a **machine-extracted
`ok`** — exactly what the map's `credit_quality` comment warns about. They now read **manual**.

## Method notes worth keeping

* **A missing label is invisible to every value check.** The row parsed fine; only the taxonomy
  lookup failed. Nothing about the *numbers* was wrong — so no arithmetic identity could have found
  it. The `npl_movement_balance_missing` drop-detector (added 2026-07-17) is what surfaced it.
* **Language is the confounder, twice.** HAYATK and COLENDI file in **English**, so a Turkish
  *"donuk alacak"* probe returns zero hits on reports that plainly print the note — the exact shape
  of the five earlier wrong "not disclosed" calls. Always sweep language-agnostically.
* **Zero is not the question — "is the note PRINTED?" is.** Here the rule produced no extra `missing`
  cells: none of the 42 prints a nil *roll-forward table*; each prints a heading + an explicit nil
  declaration.

## Open / follow-ups

* **COLENDI `npl_movement` extractor — defects 1–3 above.** Recurs quarterly. Defect 2 (cell-per-line
  x-coord assembly) is the real work.
* **`source_page` is 1-BASED in `npl_movement`** while `audit_opinion.py:122` documents 0-indexed.
  **No consumer reads it** (no web references), so it's a latent inconsistency, not a live bug.
* **6 phantom HAYATK 2024Q2/Q3 `prior` rows** — the bare `("prior period", "opening_balance")`
  fallback matched *"Prior period (Net)"* in the **user-groups sub-table** further down the same page
  and started a spurious block. Values inert (flows and closing NULL; the validator reads `current`
  only), but they are junk rows. Narrowing the fallback risks YKBNK, which is why it exists.
* **`_STMT_TO_KEY` still misses `capital` (29 overrides), `oci_replace` (20), `bs_rehier` (6),
  `pl_rehier` (3)** — same class as the `npl_movement` gap just closed: hand-curated cells reading a
  machine-extracted `ok`. Each needs its own verification before flipping, so not done here.
* **Sourced zeros the `stages` lane could store:** DUNYAK 2024Q1–Q4, HAYATK 2023Q4/2024Q1, COLENDI
  2025Q2/Q3, ZIRAATD 2025Q3, TOMK 2024Q1 don't have *unknown* Stage-3 — the filers **positively
  declare NPL nil**.
