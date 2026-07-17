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
`bank_audit_balance_sheet` (liabilities-side roman equity line), Q1 only — Q1 profit is
YTD=quarterly and Δequity is clean off the audited Q4 close.

Rule from §7.1 of the finding doc: flag `(net_profit − Δequity) > 0.25 × opening_equity`.

**Fired once in 136 bank-Q1s across 2023Q1–2026Q1. The one hit is ALBRK 2025Q1.**

| period | bank | net profit | Δ equity | gap / opening equity |
|---|---|---|---|---|
| 2025Q1 | **ALBRK** | 7,846,456 | 153,848 | **41.7%** |

Fire rate 0.74%. The runner-up in the same quarter is HSBC at 9.4%; next legitimate
band is 0–5% (dividends + OCI). ALBRK separates from the fleet by ~4×.

The screen is one join and no new extraction. It needs no threshold tuning: at any
cut between 12% and 41% it returns ALBRK 2025Q1 and nothing else.

**Sign matters.** Positive gap = profit that never became equity (the interesting
direction). Negative gap = equity without profit (capital injection — ATBANK 2025Q1 at
−41.1% is benign). Screen the positive tail only.

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

- **Signal 1 is worth building** — 0.74% fire rate, no tuning, no new extraction.
  Proposed home: a validator lane check, surfaced as a flag on `/banks/[ticker]`.
- **VAKBN's continuous smoothing reserve is unexamined**, and signal 1 is structurally
  blind to it. A release-vs-*profit* screen (not vs equity) would catch both.
- Fix the Turkish `item_name` matcher wherever a fleet screen keys off English line names.
