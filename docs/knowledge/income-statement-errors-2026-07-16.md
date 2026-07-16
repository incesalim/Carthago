# Income-statement errors: 13 flags → 0

**Date:** 2026-07-16
**Status:** ✅ DONE — shipped and live in D1 (verified: 0 failing P&L partitions of 1050)
**Commits:** `dd4eea9` (data overrides + positional P&L insert), `34ef3bc` (template-aware chain)

## What was asked

"Manually fix the income statement errors in audit reports." The `profit_loss`
lane was showing **13 failing partitions**.

## What they actually were

Only 4 of the 13 were data errors. The rest were the validator being wrong about
how these banks number their own statement.

| Class | Partitions | Verdict | Fix |
|---|---|---|---|
| Compressed template | DUNYAK ×8, TOMK ×1 | **Not an error** — data correct, validator wrong | template-aware chain |
| Source misprint | TAKAS 2023Q2/Q3, 2024Q3 | Extraction faithful; the *filing* is wrong | override XXIV→0 |
| Note-ref-as-value | HAYATK 2024Q2 | Real extraction error | override ×3 rows |
| Note-ref-as-value | TOMK 2023Q4 | Real extraction error (separate from its false flag) | override ×3 rows |

Every verdict was checked against the source PDF pulled from R2, not inferred
from the DB.

## 1. The validator bug (9 of 13)

`check_pl_chain` hardcoded the standard BRSA ordinals:

```
gross VIII · net-operating XIII · pre-tax XVII · tax XVIII · cont-net XIX · period-net XXV
deductions = {2, 9, 10, 11, 12}
```

But the ordinals are **not fixed across the corpus**. The compressed template
some participation banks file drops an opex roman, shifting everything after it:

| | gross | net-op | pre-tax | tax | cont-net | disc-net | period-net |
|---|---|---|---|---|---|---|---|
| Standard (TAKAS, HAYATK, most) | VIII | XIII | XVII | XVIII | XIX | XXIV | XXV |
| DUNYAK | VIII | **XII** | **XVI** | **XVII** | **XVIII** | XXIII | **XXIV** |
| TOMK | VIII | **XII** | **XVI** | **XVII** | **XIX** (no XVIII) | XXIV | XXV |

This is not a parse artifact — each report **states its own numbering in the
formula it prints**, and foots under it:

```
DUNYAK 2025Q1 p12:  XVI.  SÜRDÜRÜLEN FAALİYETLER VERGİ ÖNCESİ K/Z (XII+...+XV)   472.173
                    XVII. SÜRDÜRÜLEN FAALİYETLER VERGİ KARŞILIĞI (±)             111.206
                    XVIII.SÜRDÜRÜLEN FAALİYETLER DÖNEM NET K/Z (XVI±XVII)        360.967
```

472.173 − 111.206 = 360.967 ✓. The hardcoded chain instead compared `amt[17]`
(DUNYAK's **tax** row) against the sum XIII+XIV+XV+XVI (its **pre-tax** band) —
hence "expected 111206, actual 472173". The data was never wrong, and the chain
was never really checking these banks.

### The fix

The chain is now assembled per-partition from **anchor rows located by label**
(gross / net-operating / pre-tax / tax / cont-net / period-net), with the
deduction band derived from the anchors (`{2} ∪ (gross, net_op)`) instead of a
literal. `disc_net` is `period_net − 1` — it holds in every variant filed, and
its label mirrors the XX/XXI income+expense rows too closely to anchor on safely.

Anchors match a **folded** label: Turkish glyphs → ASCII, uppercased, all
whitespace stripped — the extractor emits both `DÖNEM NET KARI` and the
space-collapsed `DÖNEMNETKARI/ZARARI` (TOMK), which a spaced pattern misses.
The `none-of` exclusion lists do the real work: the discontinued block mirrors
the continuing block almost word for word, and every subtotal from XIX down
carries some form of "DÖNEM NET"/"NET PROFIT".

### Safety (this touches all 1050 partitions)

Two independent fallbacks, because a mis-read anchor would be worse than the bug:

1. Each anchor **falls back to its standard ordinal** when its label is
   unreadable. HAYATK 2024Q2's wrapped labels leave XIX as `OPERATIONS (XV±XVI)` —
   no anchor to read, so it uses 19, which is correct for that filing.
2. The template **reverts to standard wholesale** unless the anchors come out
   strictly increasing (`3 < gross < net_op < pre-tax < tax < cont < disc < period`).

A partition whose labels we can't read behaves exactly as it did before.

### Measured blast radius (old vs new, all 1050 partitions)

```
pass 6205 → 6227   fail 21 → 5   skip 74 → 68
0 partitions newly failing · 9 fixed (DUNYAK ×8, TOMK ×1)
```

**Coverage goes up, not down** — the identities these banks were never really
checked on now run. Every other lane's failure count is byte-identical to the
baseline (equity_change 104, liquidity 24, capital 13, …), confirming the change
touched only the P&L.

The 5 "remaining" in that diff are not open items: 4 are the TAKAS/HAYATK data
defects fixed by the overrides below, and 1 is ICBCT 2023Q2 cons, a **known,
documented `_PL_SKIP`** (its printed VIII is 358 / 0.013% above its own
components — a source rounding not attributable to any cell). The standalone
diff bypassed that allowlist, which is why it showed up.

## 2. The 4 real data defects

All transcribed by hand from the PDF into `data/audit_overrides.json`.

**TAKAS 2023Q2 / 2023Q3 / 2024Q3 — XXIV → 0.** The source prints the
discontinued-ops net as a verbatim copy of net profit even though XX–XXIII are
all nil, so `XXV = XIX + XXIV` would double-count. Confirmed at coordinate level
that the value really is on the XXIV line (y=608.79, same x as XXV's) — our
extraction is faithful; the *filing* is wrong. XXV = XIX proves XXIV = 0. Same
class as the existing ODEA 2022Q4/2023Q4 overrides.

**HAYATK 2024Q2 — XVII = −400,486; XVIII = 174,727; XV = 0.** Two-line wrapped
labels split the rows: the pre-tax cell captured the dipnot ref `(4.9.)` as its
**value** (stored `4.9`), and the tax row detached entirely. Both identities now
foot: XVII = XIII+XIV+XV+XVI = −400,486, and XIX = XVII + XVIII = −225,759.
(XVIII is a tax *benefit* — deferred tax income 184,596 less expense 9,869.)

**TOMK 2023Q4 — IV = −81, plus children 4.2 / 4.2.2.** Every `(81)` cell was read
as a dipnot ref and dropped. VIII now foots: 134.955 − 81 + 0 + 290.951 + 0 =
425.825 = printed VIII.

### A trap worth remembering

P&L overrides that *insert* a roman must specify `item_order`. `_pl_spine` takes
the longest **increasing-ordinal subsequence**, so a roman appended after XXV can
never extend it — it drops out of the spine and the identity it was meant to
satisfy silently **skips** instead of running. ANADOLU 2022Q1's appended `IV.`
has left `VIII=III+IV+V+VI+VII` unchecked ever since it was authored (passed=6,
skipped=1). `apply_overrides` P&L inserts now accept `item_order`, mirroring what
the BS branch already did. Author multiple inserts **tail-first**.

Also note `apply_overrides --dry-run` is **not** read-only: it applies to the
local DB and commits, and only skips the D1 push. That's by design (the policy
doc verifies overrides by dry-run), and the local DB is a derived artifact — a
real run re-pulls the R2 snapshot.

## 3. Open / not done

- **66 partitions have gaps in the P&L roman spine** — a dropped row makes its
  identity silently SKIP rather than fail, so it is invisible. Biggest clusters:
  HSBC missing XIV across 24 periods (a known parse quirk), ANADOLU/ZIRAATK
  dropping whole discontinued-ops blocks, COLENDI ×3 missing XX. Most are
  probably genuine `-`/zero rows, but each gap is an unvalidated identity.
  **Not investigated** — parked at the user's call.
- The `profit_loss` skip=1 is ICBCT 2023Q2 cons (documented source rounding).

## Verification

- 89/89 `test_audit_validator.py` pass; 516 tests pass overall (the 2 TBB
  collection errors are a pre-existing local numpy/pandas binary mismatch).
- 5 new tests cover both compressed variants, the unreadable-label fallback, the
  discontinued-block anchor trap, and that a *real* break in a compressed
  template still fails. The three compressed-template tests were confirmed to
  **fail against the old validator** — they genuinely guard the fix.
- Live in production D1: `pl_failing = 0` of 1050; TAKAS 2024Q3 XXIV = 0 (was
  6,064,906); HAYATK 2024Q2 XVII = −400,486 (was 4.9).
