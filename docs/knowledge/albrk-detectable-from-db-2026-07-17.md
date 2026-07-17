# Could the database alone have caught ALBRK 2025Q1? — 2026-07-17

Re-test of the [2026-07-14 free-provision finding](2026-07-14-albrk-2025q1-free-provision-reversal.md)
under one constraint: **`data/bank_audit.db` only. No PDF, no R2, no prose.**

> **Status: FINDING — no code changed.** The screens below are reproducible from the DB
> today and **none of them are built**. Verdict: the data is sufficient; the pipeline
> does not look.

**Answer: yes — decisively, and today the DB also names the cause.**
The anomaly is detectable from the balance sheet and P&L alone (signals 1–3, all
available since before the finding). The *cause* is nameable because the two lanes the
finding provoked — `bank_audit_opinion` and `bank_audit_free_provision`, both built
2026-07-15 — now carry it as data (signals 4–5). On 2026-07-14 the DB would have
flagged the anomaly and been unable to explain it. That gap is closed.

---

## Signal 1 — profit-vs-equity divergence (the decisive one)

`bank_audit_profit_loss` (role `period_net` via `bank_audit_pl_roles`) vs
`bank_audit_balance_sheet` (liabilities-side roman equity line).

§7.1 of the finding doc proposed: flag **any bank-quarter** where
`|net_profit − Δequity| > 0.25 × opening_equity`, **with OCI and dividends netted out**.

**Run as written — all four quarters, YTD de-cumulated for Q2–Q4 (the `heatmap.ts`
`ttmRoe` pattern) — the screen fires twice in 449 bank-quarters, 2023Q1–2026Q1:**

| period | bank | q profit | Δ equity | gap / opening equity | verdict |
|---|---|---|---|---|---|
| 2025Q1 | **ALBRK** | 7,846,456 | 153,848 | **41.7%** | **the finding** |
| 2025Q2 | TAKAS | 3,194,229 | −944,100 | 25.4% | dividend artifact |

**TAKAS is not a false positive of the idea — it is a false positive of skipping the
netting step.** `bank_audit_equity_change` carries `Dağıtılan temettü = −4,136,976` for
TAKAS 2025Q2; 3,194,229 − 4,136,976 = −942,747 against an observed Δequity of −944,100.
The gap *is* the dividend, to within ₺1.4m of OCI. Net dividends out as §7.1 said and it
vanishes. TAKAS is also a CCP already in `PEER_EXCLUDED_TICKERS` (it pays out nearly all
earnings), so it leaves the screen twice over. Its other appearances — 2024Q2 at 20.4%,
2023Q3 at 15.6% — are the same line, every year.

**Among lending banks, on §7.1's own rule, the screen fires exactly once in
2023Q1–2026Q1, and the hit is ALBRK 2025Q1.** One join, no new extraction, and the
netting leg is one more join to a table we already have.

**Sign matters.** Positive gap = profit that never became equity (the interesting
direction). Negative gap = equity without profit (capital injection — ATBANK 2025Q1 at
−41.1% is benign). Screen the positive tail only; `|abs|` as §7.1 wrote it doubles the
noise for nothing.

**Q1 is the cleanest window, and that is not a coincidence.** Noise by quarter (gap
distribution, all banks):

| quarter | n | median | p95 | max |
|---|---|---|---|---|
| Q1 | 136 | +0.82% | +7.77% | +41.7% (ALBRK) |
| Q2 | 104 | −0.12% | +8.63% | +25.4% (TAKAS) |
| Q3 | 105 | −0.59% | +3.10% | +15.6% (TAKAS) |
| Q4 | 104 | −1.40% | +2.50% | +6.7% |

Turkish AGMs sit in March, so payouts land in **Q2** — which is why an un-netted screen
is quiet at Q1 and noisy at Q2/Q3, and why every TAKAS hit is a Q2 or Q3. A Q1-only
screen needs no netting; an any-quarter screen needs §7.1's netting exactly as specified.

## Signal 2 — other operating income as a share of gross operating income

2025Q1, unconsolidated: **ALBRK 77.1%**, then SKBNK 19.0%, BURGAN 18.8%, GARAN 18.3%,
TSKB 17.2%, YKBNK 15.6%. A lone outlier at 4× the fleet. Matches the finding doc exactly.

(Only 12 banks resolve — the `item_name` matcher misses Turkish-language filings.
See "Gotchas" below.)

## Signal 3 — the sukuk, visible without the prose

`bank_audit_capital`, 2024Q4 → 2025Q1, unconsolidated:

| bank | Δ CAR | Δ CET1 | AT1 change |
|---|---|---|---|
| **ALBRK** | **+2.88pp** | **−0.62pp** | **+891%** |

CAR up while CET1 down is already a contradiction worth a flag. An AT1 line moving
+891% in one quarter is the sukuk remeasurement, and no other bank in the fleet shows
anything like it. The DB does not know *why* (BRSA letter no. 9196) — but it knows
*that*, and it knows the direction is impossible to explain with earnings.

## Signal 4 — `bank_audit_free_provision` names the number

ALBRK unconsolidated: **2024Q4 = 7,300,000 → 2025Q1 = 300,000.** A ₺7.0bn release,
exactly the qualified amount, straight out of the lane. Build-up is equally legible:
200,000 (2022Q1) → 1,800,000 → 5,213,000 → 7,300,000 → 300,000.

## Signal 5 — `bank_audit_opinion` carries the qualification

ALBRK is `qualified` / `is_modified=1` / PwC in **every period 2022Q2–2026Q1**.

---

## The finding this re-test produced: qualified is the norm, not the signal

**16 of 36 banks carry a MODIFIED opinion at 2025Q1** — ALBRK, VAKBN, HALKB, ZIRAAT,
DENIZ, QNBFB, TEB, TSKB, EMLAK, ICBCT, FIBA, BURGAN, AKTIF, SKBNK, TFKB, VAKIFK, across
all four audit firms. **The opinion field alone is not a discriminator.** It is a filter
that removes 20 banks, not an alarm. The free-provision practice is widespread enough in
Turkish banking that being qualified over it is unremarkable; what was remarkable about
ALBRK was the *size relative to its own equity*. Signal 1 is what isolates it — the
opinion field corroborates.

**VAKBN did the same thing at 1/8 the relative scale, and no screen would have caught it.**
Fleet-wide free-provision release at 2025Q1, against opening equity:

| bank | 2024Q4 | 2025Q1 | release | % of opening equity |
|---|---|---|---|---|
| ALBRK | 7,300,000 | 300,000 | 7,000,000 | **38.0%** |
| VAKBN | 15,000,000 | 4,000,000 | **11,000,000** | 5.0% |
| FIBA | 828,000 | 778,000 | 50,000 | 0.3% |

VAKBN released **more in absolute terms than ALBRK** (₺11bn vs ₺7bn) in the same quarter,
under a qualified EY opinion — and it never trips signal 1 because its equity base is
~12× ALBRK's. Its stock swings constantly: 19,000,000 (2022Q4) → 7,000,000 → 11,000,000
→ 8,500,000 → 15,000,000 → 4,000,000 → 8,000,000 (2025Q4). That is a smoothing reserve
operated continuously, not once. **Not investigated — flagged here as the next thread.**

---

## What the database can *not* give you

The DB detects and quantifies. It does not explain. Absent from every table and
recoverable only from the PDF prose:

- **BRSA letter 10-Feb-2025 no. 9196** and the instrument (`Bereket One Ltd.`, USD 205m
  perpetual AT1) — the reason the equity charge exists.
- **The causal link between the two events.** The DB shows a ₺7.0bn release and a
  ₺7.74bn equity charge in one quarter; that they plug each other is inference a human
  draws, and the bank never states it.
- **The auditor's clean number (₺846mn).** Derivable by subtraction once you have the
  release — but only because the lane now carries it.
- **The press release inverting the causality.** Not a data field at all.

So: the DB gets you to "this profit is not real, it is a ₺7.0bn free-provision release,
the auditor qualified it, and the capital move is a sukuk." It does not get you to *why
it was worth doing*. That last step was, and remains, reading the report.

---

## Gotchas found while running this

1. **The equity line is Turkish for most of the fleet.** Matching `'%EQUITY%'` resolves
   10 of 36 banks; the rest report `ÖZKAYNAKLAR`. Any fleet screen must match
   `upper(item_name) like '%ZKAYNAK%'` **or** `'%SHAREHOLDER%'+'%EQUITY%'`, and the
   roman is `XVI.` for deposit banks / `XIV.` for participation banks — anchor on the
   name, not the ordinal. Same trap as [reference_participation_equity_hierarchy].
   Signal 2's 12/36 resolution is this bug, unfixed.
2. **`kind` filter, again.** Querying `bank_audit_equity_change` without
   `kind='unconsolidated'` returns consolidated + unconsolidated rows that look like
   duplicate `Others Changes` lines (−7,725,585 and −7,739,022). Not a data defect —
   a query defect. Exactly the hazard [reference_audit_backfill_and_quality] warns about.
3. **Free-provision coverage is thin at any single period.** Only **5 banks** have an
   explicit determination at *both* 2024Q4 and 2025Q1. The other 31 are silent, and
   silence is not zero — see the ABSENT≠ZERO note in [project_albrk_free_provision_finding].
   A release screen is therefore a *corroborator*, not a primary detector.
4. **`PYTHONIOENCODING=utf-8` is required** to print any of these rows on this Windows
   console; without it `ÖZKAYNAKLAR` / `İ` raise `UnicodeEncodeError` from cp1252.

## Reproduction

Scripts used are ad-hoc; the three that matter are inlined above as SQL shape. The
divergence screen in full:

```python
# net profit: bank_audit_profit_loss JOIN bank_audit_pl_roles ON role='period_net'
# equity:     bank_audit_balance_sheet, statement='liabilities',
#             (item_name LIKE '%ZKAYNAK%' OR (LIKE '%SHAREHOLDER%' AND LIKE '%EQUITY%')),
#             hierarchy GLOB '[IVXL]*'
# flag Q1 where (net_profit - (eq[yQ1] - eq[y-1 Q4])) > 0.25 * eq[y-1 Q4]
# kind='unconsolidated' throughout, or every figure double-counts
```

## Next

- **Signal 1 is worth building** — 1 hit / ~436 lending-bank-quarters, no new extraction.
  Proposed home: a validator lane check, surfaced as a flag on `/banks/[ticker]`.
  Build it as §7.1 specified: net dividends out of Δequity via `bank_audit_equity_change`
  (`Dağıtılan temettü` / `Dividends Paid`), or restrict to Q1 and skip the netting.
  Do **not** ship the un-netted any-quarter version — it reports TAKAS every summer.
- **VAKBN's continuous smoothing reserve is unexamined**, and signal 1 is structurally
  blind to it. A release-vs-*profit* screen (not vs equity) would catch both.
- Fix the Turkish `item_name` matcher wherever a fleet screen keys off English line names.
