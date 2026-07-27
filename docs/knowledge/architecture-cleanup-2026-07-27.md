# Architecture cleanup — 2026-07-27

**Status: SHIPPED.** A follow-up to
[architecture-review-2026-07.md](architecture-review-2026-07.md) (report-only,
2026-07-02). That review's backlog was re-verified item by item; most of it had
already been closed in the intervening three weeks. This pass closed the rest of
what was worth closing, and found one live data defect on the way.

Unlike its predecessor, **this one changed code**.

---

## 1. What the 2026-07-02 backlog looks like today

| Item | Status |
|---|---|
| `PlSankeyChart.tsx` light-mode regression | **Moot** — the component no longer exists (Desk redesign) |
| Dependabot #90 lockfile | **Closed** — root cause was the Node 22/24 npm-lockfile pin, fixed in `ci.yml` |
| Off-theme chart palettes ×4 | **Closed** — the four files named are gone or re-themed |
| `audit.ts` uncached D1 reads on public pages | **Closed** — 20 `cachedAll` / 1 raw `getDB` |
| `sector/page.tsx` inline SQL | **Closed** — no page talks to D1 directly |
| `metrics.ts` god-module (1,222 LOC) | **Not split, deliberately** — see §5 |
| Zero data-layer tests | **Closed** — 5 → 28 web suites (426 tests), 51 → 53 Python |
| CI silently skipping the fitz test suite | **Closed** 2026-07-14 — `pymupdf`+`pandas` installed |
| `push_to_d1.py` 3-edit table registration | **Closed** for the audit lane 2026-07-14; **widened to all 54 tables today** — §3 |
| Dead code in `extractor.py` | **Closed** — all three helpers gone |
| pdfplumber outside the frozen path | **Closed** 2026-07-15 — fitz-only, CI-gated |
| Domain logic in `scripts/` | **Not moved, deliberately** — `scripts/README.md` classifies all 92 scripts and the classification is accurate |
| ~9 copy-pasted HTTP session+retry loops | **Still open, deliberately** — see §5 |
| `textops.py` / `locate.py` (Phase 5) | **Still open** — carried in PROJECT_STATE §Known issues |
| Stray `.next/` at repo root | **Closed** |

The verdict of the 2026-07-02 review still holds and is stronger: the
architecture is sound and the debt is concentrated. `scripts/README.md`
documents **100%** of the scripts; every historical doc carries a
"Historical — closed" banner. This is not a repo with diffuse rot.

---

## 2. The one live defect: `parse_num` read negative thousands 1000× too small

`src/audit_reports/extractor.py::parse_num` is the numeric primitive **eight**
audit extractors import. It had **no unit tests**.

```
parse_num('-319.110')   -> -319.11      WRONG (should be -319110)
parse_num('(319.110)')  -> -319110.0    ok
parse_num('-1.234.567') -> -1234567.0   ok
parse_num('319.110')    ->  319110.0    ok
```

The Turkish-vs-English format sniff is anchored — `^\d{1,3}(\.\d{3})+$` — and it
was applied to the **signed** string. A leading `-` failed the anchor, so the
value fell through to the English branch and its thousands separator was read as
a decimal point. Two groups survived on the separate `count('.') > 1` clause;
parenthesised negatives never reached the sniff. Hence the narrow, hard-to-spot
blast radius: single-group hyphen-negatives, which in this corpus means the §4
market-risk net-off and gap rows.

**Fix:** strip the sign before the sniff, so *a number's sign no longer changes
how its format is read*. `tests/test_parse_num.py` asserts every case against its
positive twin, which is the invariant rather than a list of examples.

Note the blast radius does **not** include stored BS/P&L rows: those are frozen
and never re-extracted, so the fix changes what future extractions produce, not
what is already in D1.

---

## 3. What the fix implies, and the guard it earned

### The sweep

BRSA reports print every figure as a whole number of **thousands of TL**. Ratio
disclosures (CAR / LCR / NSFR / stage coverage) are the only fractional
quantities in the lane and they live in named ratio columns. So in an amount
column, a fractional value is not a small number — it is a number we mis-read.

`scripts/check_amount_integrity.py` sweeps all **67 amount columns across 13
tables** (column list derived from `registry.py`, ratio columns excluded by name)
and found **67 fractional values**, which split cleanly in two. Run against both
the R2 snapshot and **live D1** — identical findings, so this is the serving
database, not a stale local copy:

**Mis-read separators — 2. Real figures stored 1000× too small:**

| Table.column | Bank | Period | Stored | Should be | Corroboration |
|---|---|---|---|---|---|
| `bank_audit_capital.cet1_capital` | ISCTR | 2024Q2 cons (prior col) | `270336.203` | `270336203` | ISCTR's **own 2024Q3 and 2024Q4** filings print the same prior figure, both extracted as `270336203` |
| `bank_audit_credit_quality.stage2_amount` | DENIZ | 2023Q4 cons (prior col) | `-535.779` | `-535779` | DENIZ **2022Q4 current** carries the same figure as `-535779` |

Both are in the *prior* column, and in both cases the adjacent filing's
independently-extracted **current** column is the anchor that confirms it — the
same mechanism `fx_cross_period` uses.

**Both CORRECTED the same day** via `data/audit_overrides.json` +
`scripts/apply_overrides.py`, verified in live D1; the sweep is now clean on this
class. Two things that pass came out of doing it:

- **The ISCTR case is provable, not merely corroborated.** `CET1 + AT1 = Tier1`
  closes exactly at 270,336,203 + 5,348,088 = 275,684,291 and misses by 1000×
  with the stored value. Worth remembering when judging a candidate correction:
  an identity the row already carries beats any number of agreeing neighbours.
- **What was left alone.** DENIZ's 2023Q4 prior `stage1_amount` differs from its
  2022Q4 current by 4,003. No 1000× signature, and no evidence which of the two
  filings is the mis-read — so it stays flagged rather than guessed. The point of
  a sourced override is that it is *sourced*.

### The trap: `period_type`

Both defects sit in the **prior** column, and `apply_overrides`' `capital`
handler hardcoded `period_type='current'`. Authored naively, the ISCTR override
would have silently patched the CORRECT current row and left the wrong one
exactly where it was — a repair that makes the corpus worse and reports success.
The handler now takes an optional `period_type` (defaulting to `current`, so the
54 pre-existing capital overrides behave identically) and returns **NO MATCH**
when the UPDATE touches zero rows, instead of exiting 0 on a no-op.
`tests/test_apply_overrides.py` pins the default, the prior path, the no-match
signal and the credit-quality equivalent.

Generalisable: a per-cell repair tool has to be able to name **which** cell, and
has to say so when it names one that does not exist.

### The bigger finding: half of every §4 capital cell was never validated

`check_capital` reads the row list and takes
`next(r for r in rows if r["period_type"] == "current")`. That is all it ever
looked at. `Tier1 = CET1 + AT1` — the identity that refutes the ISCTR CET1
defect instantly — **has existed since the lane shipped**; it simply never ran on
the prior column, which is where the defect was.

Extended to both columns (failures tagged `[prior]` so a red cell names its
table; the *completeness* fails stay current-only, because a bank reprinting a
partial prior column is ordinary and not our defect). Calibrated over the
corpus: **21 partitions fail** — all pre-existing, none new. Three are corrected
below; the other 18 share one signature (`at1` or `t2` stored `0.0` where the
value is non-zero, the truth always being `t1 − cet1` or `tc − t1`), which is one
extractor defect in the prior-column parse rather than 18 data errors.

The lesson is not "add a validator" — the validator was there. It is that **an
identity applied to half a table is an identity you do not have.** Worth checking
the other lanes for the same shape: `check_liquidity` takes the identical
`period_type == "current"` line.

### A method note: the circular proof

The first correction set I built took each failing row, replaced the flagged
fields with the year-end anchor's values, and checked the identity closed. It
closed for 9 of 11 — and that number was meaningless. Substituting a whole row
from a self-consistent source and then testing self-consistency proves only that
the source was self-consistent.

The honest test derives each field from **the stored row's own** identity and
requires the anchor to agree *independently*. Two derivations, no shared input.
Under it, 9 of 11 collapsed to **2**. Both were applied; the other 9 were not.

### Found on the way and FIXED: ISCTR 2024Q1 prior was a column SLIP

Same 31-Dec-2023 column, different defect class:

| Field | Stored | Correct (per the other three filings) |
|---|---|---|
| `cet1_capital` | NULL | 270,336,203 |
| `additional_tier1_capital` | 275,684,291 ← Tier 1's value | 5,348,088 |
| `tier1_capital` | NULL | 275,684,291 |
| `tier2_capital` | 332,475,371 ← Total capital's value | 56,791,080 |
| `total_capital` | 332,472,141 | 332,475,371 |
| `total_rwa` | 1,673,761,385 ✓ | 1,673,761,385 |

**The amount-integrity sweep is structurally blind to this** — every stored value
is a whole number, so nothing about its *shape* is wrong; only the assignment is.
It is a row-label matching failure, not a parse failure.

Cause, read from the PDF: ISCTR's 2024Q1 is an **English** filing whose §4 labels
print one row off their values. p37 reads *"Total Deductions from Common Equity
Tier 1  294,633,433  270,336,203"* — that IS the CET1 row; *"Total Additional
Tier I Capital  311,532,076  275,684,291"* is Tier 1; and so on down the table.
The extractor matched each label literally, so `cet1`/`tier1` came back NULL
while AT1 took Tier 1's value and Tier 2 took Capital's. **Corrected from source**
(four fields), and the row now closes `CET1 + AT1 = Tier1` exactly.

**Leaked non-values — 65.** A hierarchy marker, sector numbering or dipnot ref
parked in an amount column: `equity_change.paid_in_capital` (44, all GARAN
`11.2`/`11.3` on rows labelled "Transfers to Reserves"/"Others" with
`total_equity = 0`), `loans_by_sector` stage2/stage3 (18, ALBRK + ANADOLU sector
numbering repeating identically across four year-ends), and three singletons.
Junk, but junk that reads as junk — orders of magnitude from any real figure, and
no total foots to it. These belong to the known `eq_col_chain` /
column-alignment tails already tracked in PROJECT_STATE.

### Telling the two apart

Two independent signals, either sufficient:

- a **3-digit fraction** — the shape of a thousands group read as decimals;
- an **integer part ≥ 100** — BRSA markers, sector numbering and dipnot refs top
  out around 30, so three integer digits is not a marker.

The second is not redundant, and this is the trap worth recording: a separator
misread that *ends in zero* (`-319.110`) becomes the double `-319.11` the moment
it is parsed. **The trailing zero is unrecoverable** — arithmetic cannot tell it
from a genuine two-digit fraction — so the fraction-length signal alone misfiles
roughly one in ten of the class. The magnitude signal catches those. Pinned by
`tests/test_amount_integrity.py::test_a_separator_misread_ending_in_zero_is_still_caught`.

Only the separator class alerts. Daily-paging a 65-item backlog nobody is
clearing this week only teaches everyone to mute the channel.

### A D1 shape lesson worth keeping

The sweep's first CI run died before reading a row. The obvious query shape —
one `COUNT(*) … WHERE <col> is fractional` per column, `UNION ALL`'d — makes
**every branch its own full scan**, so 67 columns meant 67 scans over tables up
to ~200k rows and D1 refused the statement. The identical sweep over the local
SQLite snapshot ran fine, because SQLite does not care. Rewritten as **one query
per table** with conditional aggregation (`SUM(CASE WHEN … THEN 1 ELSE 0 END)`
per column), it is 13 scans regardless of column count, and returns the same
answer. Generalisable: on D1, fan columns out inside one scan, never fan scans
out inside one statement.

(Second thing that run taught: **wrangler writes its error body to stdout**, not
stderr. Reporting only `proc.stderr` produced `d1 query failed:` with nothing
after it. `_d1` now falls back to stdout — worth copying into the other probes
that share this helper.)

### Why a new kind of check, not another validator

Every structural check in `validator.py` is an **internal identity** — assets =
liabilities, subtotal = Σchildren, closing = opening + flows. Those compare
figures to each other, which means:

- a scaling error on one cell is invisible unless that cell is in an identity;
- a **uniform** scaling error is invisible to *all* of them, because it cancels
  on both sides — that is exactly how TEB's 2026Q2 Bin→Milyon unit switch
  validated green across the entire partition.

This check asks a different question, per cell and with no cross-reference:
**does the stored number have a shape the source could not have printed?** It
needs no anchor, no peer and no prior period, which is why it can see what the
identity web structurally cannot. It runs daily in `healthcheck.yml`.

---

## 4. The rest of the pass

**`push_to_d1` routing guard widened to all 54 tables.** `fetch_recent` routes
each table to its timestamp column through a hand-maintained if/elif ladder; a
table matching no branch returns `"no time column, skipped"` — 0 INSERTs, exit 0.
That is the second half of the fx_position/repricing incident, and it was pinned
for the 27 audit tables only. The other 27 (bulletin, EVDS, news, TEFAS, BIST,
TBB/TKBB, KAP, rates, products, calendar, faaliyet, api_series) had no guard.
The new tests build the schema from `web/migrations/*.sql` — the canonical D1
definition, and the only place the baseline tables are declared — and assert both
that every `SYNC_TABLES` name exists and that none hits the skip branch. Green
today; a pure regression guard against the next new table.

**ruff widened from 5 rules to full pyflakes** (`select = ["E9", "F"]`). Cost:
18 findings across ~22k LOC — 11 unused imports, 7 dead locals, most in the
frozen `scripts/archive/`. It paid for itself immediately: swapping
`loans_by_sector`/`npl_movement` onto the shared `extractor.parse_amount` left
`parse_num` imported and unused in both, and F401 is what said so. Not enabled:
`E` (1,161 `E501` — the long explanatory comments here are the point) or `I`
(77 unsorted imports in files doing the `sys.path.insert` + `# noqa: E402` dance).

**74 over-broad exports in `web/app/lib`.** Method: drop `export` from all 74,
then let `tsc --noEmit` and ESLint's `no-unused-vars` produce a *tool-verified*
delete list rather than a grep-verified one. tsc stayed clean (nothing outside
those modules used any of them); ESLint named **37** as now-unused, and deleting
those orphaned a second wave of 7 private helpers whose only callers were the
deleted functions. Net **−538 lines**, 28 files, `metrics.ts` 1,263 → 974.
The other 37 stay as module-private internals — `bot-sql.ts`'s SQL-gate helpers
and the `reads.ts` computers reached through `READ_COMPUTERS` are code, just not
public code.

The deletions turned out to be *residue of changes already made and already
documented*: `docs/CHANGELOG.md:1208` records `resolveBsLineLabel` as "dropped"
while the export was still in the file, and `docs/METRICS.md` claimed
`web/app/credit/page.tsx` "calls `tlLoans` + `fxLoans`" — functions with no
caller at all. Four such claims in METRICS.md were corrected to match what the
pages actually do.

**`_parse_amount` de-duplicated.** Byte-identical in `loans_by_sector.py` and
`npl_movement.py`; promoted to `extractor.parse_amount` beside `parse_num`, where
both lanes already import from.

---

## 5. Deliberately not done

Recorded so they are not re-proposed as oversights:

- **Splitting `metrics.ts`.** Cleanly banded by sub-domain, server-side, tree-shaken.
  Churn, not optimisation. (It shrank 23% here anyway, as a side effect.)
- **Merging `_merge_wrapped_labels`** (loans_by_sector / npl_movement). Same name,
  genuinely different logic: one gates on `≤80 chars` + no terminating period, the
  other on `_TRANSFER_WRAP_HEAD_RX` plus a three-key closing/provision/net
  allowlist. A shared version would be a false abstraction over two banks' quirks —
  and this codebase's history is a long argument that lane-specific parsing quirks
  should stay lane-specific.
- **Merging `_fitz_word_lines` / `_value_tokens`** (fx_position / repricing).
  Repricing's carry `x1` right-edges and run `_unglue`/`_destray`. Not the same
  function.
- **The shared HTTP session+retry helper.** Real duplication (6 `_session()`
  factories, 4 retry loops), but each backoff is tuned to a specific flaky source.
  Worth doing deliberately, with the per-source policy preserved — not as part of
  a cleanup sweep.
- **`textops.py` / `locate.py`** (Phase 5). Still carried in PROJECT_STATE
  §Known issues. Worth noting the situation is better than that entry implies:
  `extractor.py` *is* already the de-facto shared module — every lane imports
  `_fitz_page_text` / `_fitz_page_count` / `parse_num` / `NUM_PAT` from it — so
  there is one source of truth today. What remains is that those shared primitives
  live in a 1,337-line module under private `_`-prefixed names imported across
  module boundaries. That is a naming and packaging problem, not the
  duplicated-logic problem the ECL bug came from.

---

## 6. Open, needing a decision

1. **18 §4 capital partitions failing on the prior column** (EMLAK ×4, ISCTR ×2,
   QNBFB ×11, +1). One shared signature — `at1`/`t2` stored `0.0` where the value
   is non-zero — so the fix belongs in `capital_adequacy.py`'s prior-column
   parse, not in 18 overrides. 5 of them have no in-corpus anchor (their prior
   column is a 2021 year-end, before the corpus starts) and need the source PDF.
   A full `revalidate_audit_db.py` pass is what surfaces them in `/admin`.
2. **`check_liquidity` has the same `period_type == "current"` line** as
   `check_capital` did. Its prior column has never been validated either. Worth
   the same treatment, and the same calibration before shipping.
3. **The 65 leaked non-values.** Root causes now identified, both extractor-side:
   *equity_change* leaks a footnote/section reference into `paid_in_capital`
   (GARAN 38 rows carry 11.1/11.2/11.3, EXIM 6 carry 10.2 — and EXIM's stored
   label `"Capital Increase in Cash (."` is the smoking gun, truncated at the
   opening paren of its own `(10.2)` ref); *loans_by_sector* leaks the sector
   NUMBERING as a value on a wrapped Turkish label (ANADOLU "Madencilik ve" →
   `stage2 = 2.1`), and on ALBRK 2025Q4 prior it is worse than junk — `raw_label`
   holds *'Farming and stockbreeding 44.417 25.470 22.851'* while `stage3` got
   the sector number and `ecl` was dropped, so 10 sectors lost two real columns.
   Three further rows are pure **phantoms**: a page header parsed as a cash-flow
   row (QNBFB 2022Q2), a header fragment as a P&L row (QNBFB 2024Q2), and a
   truncated label fragment in YKBNK 2022Q3 liabilities.
4. **9 stale overrides** that match nothing on every run (AKBNK `pl_rehier` ×3,
   EXIM/VAKBN/HAYATK `bs_rehier` ×6) — the extractor fixes they compensated for
   have landed. Dead config, and they make a real `NO MATCH` harder to spot.
5. **Local `pytest` cannot run two TBB test files** — `numpy.dtype size changed`,
   a numpy/pandas ABI mismatch in the local venv. Pre-existing (reproduced on a
   clean `git stash`), unrelated to this change, and not present in CI, which
   installs fresh wheels. Worth a `pip install -U numpy pandas` locally.

**Done since first writing:** the two mis-read amounts (§3).
