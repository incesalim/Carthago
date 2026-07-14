# ALBRK 2025Q1 — the ₺7.85bn profit that wasn't — 2026-07-14

Ad-hoc investigation of an unusual movement in Albaraka Türk's (ALBRK) Q1 2025
results. Every figure below is from the **primary audited source** — the BRSA
report pulled from R2 (`albrk/ALBRK_2025Q1_unconsolidated.pdf`) — cross-checked
against `data/bank_audit.db`.

> **Status: FINDING — no code changed.** The data is correct; the bank is the
> story. Two dashboard screens are proposed in §7 and are **NOT built**.

**Headline:** ALBRK reported ₺7.85bn of net profit in Q1 2025 — 12.8× the prior-year
quarter and 1.8× its *entire* FY2024 profit — while shareholders' equity rose
₺154m (+0.8%) and operating cash flow before working capital was **negative**.
The profit is a **₺7.0bn free-provision reversal that PwC qualified its audit
opinion over**. It was released in the same quarter that a BRSA letter forced a
USD 205m perpetual sukuk out of equity, blowing a ₺7.74bn hole in CET1. The
reversal plugged the hole. Net capital created: none. Net cash: none.

All amounts are TL thousands unless stated, unconsolidated basis.

---

## 1. The anomaly, in three statements

| | 2024Q1 | 2024Q4 (FY) | **2025Q1** |
|---|---|---|---|
| Net profit (P&L XXV.) | 614,006 | 4,310,448 | **7,846,456** |
| Other operating income (P&L VII.) | 1,225,095 | 3,258,001 | **9,398,703** |
| — as % of total operating income | 35% | 18% | **77%** |
| Shareholders' equity | — | 18,428,944 | **18,582,792** (+0.8%) |
| Cash: operating profit pre-working-capital | — | — | **(399,811)** |

A ₺7.85bn profit that produces no equity and no cash is not a profit. Strip the
other-operating-income line and Q1 2025 is a **pre-tax loss of ₺1,396,955**.

**Peer context (2025Q1, other op. income as % of total op. income):** ALBRK 77.1%,
next highest SKBNK 19.0%, GARAN 18.3%, YKBNK 15.6%, ISCTR 12.7%. It is a lone outlier.

---

## 2. Event A — the profit: a ₺7.0bn free-provision reversal

**Note IV.6, Other operating income** (p.75):

> Reversal of prior year provisions (\*) **9,087,977** … Total **9,398,703**
> *(\*) TL 7.000.000 of the related amount is due to the reversal of **free provisions
> for possible risks in previous periods** (31.03.2024: None).*

**Note II.5.b, Other provisions** (p.66) — the liability side:

> Free provisions allocated for possible losses(\*) **300.000** | (Dec 31, 2024: **7.300.000**)
> *(\*) …provided by the Bank management in prior years **outside of the requirements
> of BRSA Accounting and Financial Reporting Legislation**.*

Of the ₺9.40bn headline, ₺9.09bn is prior-year provision reversals (₺7.0bn free
provisions + ~₺2.09bn other, including the performance-bonus provision falling
1,200,000 → 238,091). Genuinely operating items — fund management fees, operating
lease income, cheque charges — total ~₺0.31bn.

### PwC qualified the opinion. Twice, in opposite directions.

**Q1 2025 review report, "Basis for the Qualified Conclusion"** (p.2):

> *"…a portion of the free provision amounting to **TL 7,000,000 thousand is reversed
> in the current period** out of the total free provision of TL 7,300,000 thousand,
> which was provided by the Bank management in prior years **outside of the requirements
> of BRSA Accounting and Financial Reporting Legislation**… If the mentioned free
> provision had not been provided in prior years and had not been reversed in the
> current period… **net profit… would have decreased by TL 7,000,000 thousand**…"*

**FY2024 audit report, "Basis for Qualified Opinion"** (p.3) — the same reserve, on the way *up*:

> *"…a free provision under other provisions amounting to TL 7.300.000 thousand which
> consist of TL 5.213.000 thousand provided in prior years and TL 2.087.000 thousand
> recognized in the current year by the Bank management **which is not within the
> requirements of BRSA Accounting and Financial Reporting Legislation**."*

The auditor objected when the reserve was **built** and again when it was **released**.
Management used a reserve PwC never accepted to smooth two years of earnings in
opposite directions.

**The auditor's own clean number: ₺7,846,456 − ₺7,000,000 = ₺846mn** underlying Q1-25
profit, vs ₺614mn in Q1-24 — **+38% nominal, i.e. roughly flat in real terms.**

---

## 3. Event B — the equity charge: the AT1 sukuk was ordered out of equity

The Statement of Changes in Equity carries a line **"X. Others Changes" = (7,739,022)**
— against a typical quarter of ~(120,000). Split:

| | ₺k |
|---|---|
| Other capital reserves (2,665,252 → 10,232) | (2,655,020) |
| Prior years' retained earnings | (5,084,002) |
| **Total** | **(7,739,022)** |

The equity statement gives no footnote. **Note II.10.ğ** (p.69) does:

> *"As of December 31, 2024, the Bank has been monitoring the **Tier 1 sukuk transaction
> amounting to USD 205.000.000** under **"other capital reserves" in equity at historical
> cost**, but after **February 24, 2025**, based on the approval of the BRSA, the Bank
> started to monitor it **in foreign currency under the Subordinated Loan item under
> liabilities**."*

**Note II.8** (p.68) identifies the instrument and the order:

> A **USD 205,000,000 perpetual (undated) Basel-III AT1 sukuk**, issued through the
> structured entity **"Bereket One Ltd."**, listed on the Irish Stock Exchange,
> BRSA-approved into Additional Tier 1 on **20 February 2018**. Coupon 11.422%
> (10% p.a. for the first 5 years). Reclassified per **BRSA letter dated
> 10 February 2025, no. 9196**.

Under **TAS 32** it was a non-monetary item → equity. The BRSA letter reversed that.

**Arithmetic proof:** ₺7,739,022 ÷ USD 205,000 = **37.75 TL/USD** — the Q1-2025 rate.
The sukuk was derecognised from equity at its current FX value, with the debit split
across its historical carrying amount and the accumulated FX difference in retained
earnings. Corroborated on the liability side: subordinated loans 14,007,315 →
23,016,597 (**+9,009,282**).

---

## 4. Why it was worth doing — the regulatory capital payoff

Because the sukuk sat in equity **at historical cost**, ALBRK's regulatory AT1 credit
for a USD 205m instrument was frozen at the **February-2018** exchange rate:

> **₺775,720 ÷ USD 205,000 = 3.78 TL/USD** — precisely the Feb-2018 rate, and precisely
> the AT1 line in the 2024 capital table.

Seven years of lira depreciation (3.78 → ~37.5) had silently shrunk the instrument's
regulatory value to roughly a **tenth** of its economic worth. Remeasuring it as an FX
liability restores it:

| | 2024Q4 | 2025Q1 | Δ |
|---|---|---|---|
| Additional Tier 1 capital | 775,720 | **7,689,550** | **+6,913,830** |
| Tier 1 ratio | 11.39% | **14.72%** | +333bp |
| **Capital adequacy ratio** | **17.15%** | **20.03%** | **+288bp** |
| CET1 ratio | 10.88% | **10.26%** | **−62bp** |

**ALBRK's CAR rose 288bp in a quarter when nearly every peer's fell:** ZIRAAT
18.64→16.68, VAKBN 16.11→14.16, AKBNK 21.14→19.96, QNBFB 17.35→15.30, YKBNK
18.55→16.81, TSKB 26.86→22.59, TEB 19.15→17.14.

---

## 5. How the two events connect

The sukuk reclassification took **₺7.74bn out of book equity and out of CET1**. The
free-provision reversal — a liability carrying **zero capital value** — was converted
into **₺7.0bn of CET1-eligible retained profit** in the same quarter. Book equity ends
**flat (+0.8%)**; CET1 ends down only 62bp.

CET1 was ₺16.60bn. Absorbing a ₺7.74bn charge unaided would have taken the CET1 ratio
to roughly **6%** — beneath the regulatory minimum plus buffers.

**The bank never states the two were coordinated**; the notes present them as unrelated.
The sizing, the timing (both inside the quarter of the BRSA letter), and the fact that
CET1 lands essentially flat make coincidence hard to defend. Flagged as **inference**.

### The bank's press release inverts the causality

[Anadolu Ajansı, 8 May 2025](https://www.aa.com.tr/tr/isdunyasi/finans/albaraka-turkten-ilk-ceyrekte-7-milyar-846-milyon-lira-konsolide-olmayan-net-kar/694981)
quotes ALBRK saying it *"carried out the cancellation of the ₺7bn free provision set
aside in previous periods, **raising its capital adequacy ratio to 20%**."*

That is not what happened. **Every basis point of the CAR increase came from the sukuk
remeasurement.** The provision release did not raise the ratio — it stopped the sukuk
move from cratering CET1. The plug was presented as the achievement.

---

## 6. What this is NOT (hypotheses tested and refuted)

- **NOT a repossessed-real-estate disposal.** Assets held for sale fell 4,245,475 →
  453,285, but **Note I.8 (p.57) shows Disposals = 0**. The 3,894,500 is a *Transfer*
  into "Other assets" (which rose 3,053,724 → 9,167,585). A line-item reclassification;
  no sale, no gain, no P&L effect.
- **NOT an NPL portfolio sale.** NPL stock *rose* (2,019,669 → 2,236,491); write-offs
  totalled 111,834; no sales recorded in `bank_audit_npl_movement`.
- **NOT a TAS 8 restatement.** The equity statement's rows "II. Correction made as per
  TAS 8" / "2.1 Effect of Corrections" / "2.2 Effect of Changes in Accounting Policies"
  are **nil** in 2025Q1 and FY2025.
- **NOT a sector or regulatory event.** No other participation bank (KUVEYT, TFKB,
  VAKIFK, ZIRAATK, EMLAK) shows either pattern — most *increased* other provisions in
  the quarter. ALBRK was the only Turkish bank carrying an AT1 sukuk inside equity at
  historical cost, which is why it drew a bank-specific supervisory letter. No published
  BDDK rule change exists; a *yazı* is not published in the Resmî Gazete.
- **The ₺0.83bn employee-benefit reserve fall is mundane** — the performance-bonus
  provision went 1,200,000 → 238,091.

---

## 7. What the dashboard should do about it — NOT BUILT

Neither screen exists today. Both would have caught this in one line.

### 7.1 Profit-vs-equity divergence screen
Flag any bank-quarter where **net profit and the change in shareholders' equity diverge
sharply**. ₺7.85bn of profit against +₺154m of equity is a signature nothing legitimate
produces. Cheap to compute — both legs are already in `bank_audit_profit_loss` (XXV.)
and `bank_audit_balance_sheet` (XIV.). Suggested rule: flag when
`|net_profit − Δequity| > 0.25 × opening_equity`, with OCI and dividends netted out
so ordinary quarters don't trip it.

### 7.2 Audit-opinion field — we do not capture it at all
**We have no column anywhere for whether the auditor's opinion was clean.** PwC has
qualified ALBRK for FY2024, Q1 2025, and FY2025 and our data is blind to it. The
opinion type sits on p.1–3 of every PDF we already store in R2 and is trivially
greppable (`Qualified Opinion` / `Basis for Qualified` / `Şartlı Görüş`). This is the
single highest-value field we are missing: an auditor telling you the numbers are wrong
is strictly better than any ratio we compute from them.

Proposed: `bank_audit_extractions.audit_opinion` (`clean` | `qualified` | `adverse` |
`disclaimer`) + `audit_opinion_basis` (the paragraph text), backfilled across the R2
corpus, surfaced as a badge on `/banks/[ticker]` and a flag in the /admin matrix.

---

## 8. Reproduction

```python
import sqlite3; c = sqlite3.connect('data/bank_audit.db')
# the profit — note the `kind` filter; consolidated + unconsolidated both live here
c.execute("""select period, amount from bank_audit_profit_loss
  where bank_ticker='ALBRK' and kind='unconsolidated' and hierarchy='VII.'
    and item_name like 'OTHER OPERATING INCOME%' and amount is not null""").fetchall()
# the equity charge
c.execute("""select period, other_capital_reserves, prior_period_profit_loss, total_equity
  from bank_audit_equity_change where bank_ticker='ALBRK'
    and item_name like '%Others Changes%' and period_type='current'""").fetchall()
# the capital payoff
c.execute("""select period, additional_tier1_capital, cet1_ratio, capital_adequacy_ratio
  from bank_audit_capital where bank_ticker='ALBRK' and kind='unconsolidated'
    and period_type='current'""").fetchall()
```

PDF: `r2_storage.download_to('albrk/ALBRK_2025Q1_unconsolidated.pdf', dest)` — notes on
pages 57 (held-for-sale), 66 (provisions), 68–69 (sukuk), 75 (other operating income);
qualified conclusion on page 2.

## 9. Sources

- **Primary:** ALBRK 2025Q1 + 2024Q4 unconsolidated BRSA reports (PwC), in R2 under `albrk/`
- Albaraka IR — https://www.albaraka.com.tr/en/investor-relations/financial-information/independent-audit-reports
- Anadolu Ajansı, 8 May 2025 — https://www.aa.com.tr/tr/isdunyasi/finans/albaraka-turkten-ilk-ceyrekte-7-milyar-846-milyon-lira-konsolide-olmayan-net-kar/694981
