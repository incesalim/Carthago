# Who the dashboard is for — actor research — 2026-08-02

Every group with a plausible reason to use carthago, researched individually:
what they need, why, what worries them, how fresh the data has to be, and a real
example of the document each one produces or consumes today.

> **Scope: research only. No code changed, nothing built, nothing decided.**
> This is the audience layer of the "rationale before narrative" rule — it has
> to exist before a new page gets designed. Companion to the CEO framing in the
> same conversation, which produced the seven-question spine referenced below.
> Status: **draft for review**, not an agreed roadmap.

## The seven questions (the CEO spine)

Derived by role-playing a Turkish bank CEO. Every actor below is scored against
these, because they turn out to be near-universal:

1. What are peers paying for deposits?
2. Real bad-loan formation, before write-offs and portfolio sales
3. Why is our return below theirs — decomposed into margin / cost / risk / leverage
4. Where did share move this quarter, by product
5. Who is capital- or growth-constrained and therefore cannot respond
6. Whose ratios are propped up by regulatory relief
7. Does this new rule hurt them more than us

Three answerable today from data already in D1 (1, 2, 3), two nearly (4, 5), two
genuinely missing (6, 7 — both narrative-side).

---

## Cluster A — Judging whether a bank is safe

The deepest need, the least served, and the cluster where the audit-report
extraction is the differentiator rather than a nice-to-have.

### A1. Credit investors — Eurobond, AT1, Tier 2 holders

**Who.** EM credit desks at global asset managers, dedicated EM debt funds,
private banks placing Turkish bank paper with clients, and the syndicate banks
themselves. The market is real and active: Akbank sold **$600m of AT1 at 7.95%**
in February 2026, callable at 5.5 years, via Citi, Emirates NBD, First Abu Dhabi
Bank, HSBC, JPMorgan and BofA — extending Vakıfbank's record for the cheapest
Turkish AT1 ever
([bne IntelliNews](https://www.intellinews.com/istanbul-listed-akbank-extends-vakifbank-s-record-for-cheapest-ever-subordinated-at1-eurobond-426241/)).
Fitch expects total outstanding paper from Turkish issuers to exceed **$540bn in
2026**.

**What they need.** Capital stack detail, not equity metrics. Common Equity
Tier 1 versus total capital, the buffer over the requirement, AT1 trigger
distance, leverage ratio, LCR and NSFR, FX position, and the maturity profile of
external funding. Then asset quality: stage 2 and stage 3 balances, coverage
ratios, and gross NPL formation before write-offs.

**Why.** An AT1 holder is short a call on the bank's capital ratio. The single
number that matters is *how far CET1 sits above the trigger*, and the second is
whether the earnings that rebuild capital are real or accounting.

**Concerns.** Coupon non-payment (AT1 coupons are discretionary), conversion or
write-down, and the sovereign ceiling — a Turkish bank cannot outrun its
sovereign for long. Also: whether the reported capital ratio uses BDDK's
forbearance FX rate.

**Freshness.** Quarterly is adequate for the balance sheet; *same-week* for
anything that changes the capital story (a new issue, a regulatory change, a
rating action).

**Real example.** [S&P: *Türkiye Banking Outlook 2026 — A Rocky Road To Recovery*](https://www.spglobal.com/ratings/en/regulatory/article/turkiye-banking-outlook-2026-a-rocky-road-to-recovery-s101665211)
and the companion [*Sector Review: Turkish Participation Banks Grappling With Growth Constraints*](https://www.spglobal.com/ratings/en/regulatory/article/sector-review-turkish-participation-banks-grapple-with-growth-constraints-s101682885).

**Carthago fit.** Strong. The `capital`, `liquidity`, `fx_position`,
`credit_quality`, `stages` and `npl_movement` lanes are exactly this reader's
worksheet. The gap is question 6 — forbearance usage — which is narrative.

### A2. Rating agencies

**Who.** Fitch, Moody's, S&P internationally; JCR Eurasia and SAHA
domestically. All three internationals maintain active Turkish bank coverage and
move in blocks — Fitch has repeatedly taken sector-wide actions on Turkish banks
tied to the sovereign and the operating environment
([example rating action coverage](https://www.seenews.com/news/fitch-downgrades-turkish-banks-isbank-garanti-akbank-yapi-kredi-427383),
[outlook revisions in line with the sovereign](https://gulfnews.com/business/banking/fitch-revises-turkish-banks-outlooks-to-negative-on-sovereign-outlook-change-1.73579042)).

**What they need.** Consistent peer comparables across the whole system — not
just the listed banks — plus multi-year history to place a bank in its cohort.

**Why.** Their methodologies are explicitly relative: a viability rating is
assigned against peers in the same operating environment. Building that peer set
by hand across 37 institutions is the laborious part of the job.

**Concerns.** Comparability. Two banks' cost of risk are not comparable if their
ECL scenario weights differ, and that difference is disclosed in prose.

**Freshness.** Quarterly, with the annual audited report as the anchor.

**Carthago fit.** They will not buy a data product to replace their own work,
but they are a credibility audience — being cited in a rating report is worth
more than the subscription would be. And the ECL-assumption extraction is
something even they do inconsistently.

### A3. Correspondent banks setting counterparty limits

**Who.** Any foreign bank clearing USD or EUR for a Turkish bank, or taking
trade-finance risk on one.

**What they need.** A defensible annual credit file on the respondent bank:
ownership, financials, capital, liquidity, plus governance and any adverse news.

**Why.** This is a regulatory obligation, not an investment choice. The
[FATF *Guidance on Correspondent Banking Services*](https://www.fatf-gafi.org/content/dam/fatf-gafi/guidance/Guidance-Correspondent-Banking-Services.pdf)
and the [FFIEC BSA/AML manual on foreign correspondent due diligence](https://bsaaml.ffiec.gov/manual/AssessingComplianceWithBSARegulatoryRequirements/10)
require ongoing monitoring for "changes in the respondent institution's risk
profile". The World Bank publishes a
[Correspondent Account KYC Toolkit](https://documents1.worldbank.org/curated/en/792381468142174651/pdf/941830WP0Box3800ACCOUNT0KYC0TOOLKIT.pdf)
for exactly this file.

**Concerns.** De-risking exposure — the cost of getting it wrong is a
regulatory action, so the file must be *documented*, not merely correct. That
makes a citable, traceable source unusually valuable to them.

**Freshness.** Annual review cycle, with event-driven interrupts.

**Real example.** Moody's sells [BankFocus](https://www.bvdinfo.com/en-us/our-products/data/international/bankfocus)
into precisely this use case — its brochure is subtitled *"research and analyse
banks, for counterparty"* — bundling roughly ten years of standardised bank
financials with ownership and compliance data.

**Carthago fit.** Genuine, and the "documented and traceable" requirement plays
to the pipeline's strength. But this buyer wants global coverage in one place;
Turkey-only is a supplement, not a replacement.

### A4. Development finance institutions

**Who.** EBRD, IFC, EIB, plus bilateral agencies (KfW, Proparco, FMO). Volume is
substantial: **EBRD invested a record €2.7bn across 54 projects in Türkiye in
2025**, 91% of it private-sector
([EBRD](https://www.ebrd.com/home/news-and-events/news/2026/ebrd-invested-a-record--2-7-billion-in-tuerkiye-in-2025.html)).
Recent bank facilities include **$130m to Akbank** in December 2025 ($70m
women-led SMEs, $50m youth-led, $10m digital transformation) and **€50m to TEB**
in March 2026 under the €600m Women in Business II programme.

**What they need.** Credit assessment of the intermediary bank, plus the ability
to verify that on-lending reached the intended segment.

**Why.** They lend *through* banks. The bank's solvency is their credit risk and
the bank's SME book is their impact metric.

**Concerns.** Both credit and reputational — a partner bank in difficulty is a
headline as well as a loss.

**Freshness.** Annual for the credit file, quarterly for monitoring.

**Real example.** The [EBRD Project Summary Document for the Akbank SME credit line](https://www.ebrd.com/home/work-with-us/projects/psd/43783.html)
is instructive for what it *lacks*: a "The Client" section giving market
position, business segments and agency ratings, and **no financial statements,
balance-sheet data or profitability metrics at all**. The public record of these
deals contains almost no bank fundamentals.

**Carthago fit.** Strong and underserved, especially the SME and sector-lending
breakdown, which is exactly the `loans_by_sector` lane. These institutions
publish in English and work in English.

### A5. Corporate treasurers

**Who.** Treasury functions at large Turkish corporates and at multinationals
with Turkish operations, holding deposits and credit lines across several banks.

**What they need.** A bank-by-bank health view they can put in a policy
document, and early warning of deterioration.

**Why.** Standard treasury practice sets exposure limits by institution and by
rating tier ([Association of Corporate Treasurers](https://www.treasurers.org/hub/treasurer-magazine/treasury-essentials-counterparty-risk),
[Treasury Today](https://treasurytoday.com/risk-management/counterparty-risk/counterparty-credit-risk/)).
The known weakness of that approach is that **ratings lag** — market indicators
moved faster than downgrades through the last crisis — so treasurers supplement
with CDS spreads and news flow. For most Turkish banks there is no liquid CDS,
which leaves a hole that *fundamentals published quarterly* could fill.

**Concerns.** Losing corporate cash in a bank failure, and being unable to show
the board a documented monitoring process. Note the deposit-insurance ceiling is
irrelevant at their scale: **TMSF cover rises to ₺1.2m per person per institution
for 2026**, from ₺950,000 — meaningless for a corporate balance
([TMSF](https://www.tmsf.org.tr/en/Tmsf/Finansman/mevduat.sss.guncel.en)).

**Freshness.** Quarterly baseline; immediate on an adverse event.

**Carthago fit.** Real, underserved, and nobody is selling to them. The obstacle
is distribution, not data — treasurers do not browse dashboards.

---

## Cluster B — Valuing a bank

### B1. Sell-side analysts

**Who.** Research desks at the Turkish brokerages — Ak Yatırım (covering ~70
BIST names, ~85% of market cap), İş Yatırım, Garanti BBVA Yatırım, Yapı Kredi
Yatırım, Ünlü, Oyak — plus the global banks' EM teams. Goldman Sachs was
publicly positive on Turkish bank stocks for 2027 as of February 2026.

**What they need.** Fast quarterly comparables in a consistent format, and the
components to build a NIM bridge: loan yield, deposit cost, swap cost, CPI-linker
contribution.

**Why.** Their product is a quarterly preview and review across the coverage
universe within days of results. Turkish banks were noted trading at a ~73%
discount to global EM peers — the whole debate is about whether that gap is
justified, which is a comparables argument.

**Concerns.** Being wrong on the margin call. Swap-adjusted NIM is the perennial
fight, and it is **not cleanly derivable** from disclosed data — a known trap.

**Freshness.** Results day. Within hours, not days. This is the most
freshness-sensitive audience.

**Real example.** [Ak Yatırım research](https://www.akyatirim.com.tr/research.aspx),
[Garanti BBVA Yatırım research](https://www.garantibbvayatirim.com.tr/medium/ResearchReports-Constant-83300.vsf).

**Carthago fit.** Good on content, weak on timing — the audit-report pipeline
lands well after the results-day window that matters most to this reader.

### B2. Buy-side — EM funds and local institutions

**Who.** Foreign EM equity and debt funds, Turkish pension and mutual funds, and
the local asset managers already visible in the TEFAS lane.

**What they need.** Positioning-level questions: who is over-earning, who is
under-provisioned, which balance sheet is most rate-sensitive.

**Concerns.** Currency and policy risk swamping bank-specific analysis; and
being unable to verify what a bank's IR deck asserts.

**Freshness.** Quarterly, but they want history and export more than speed.

**Carthago fit.** Strong, and the public API is the right delivery mechanism for
them.

### B3. Bank investor relations teams

**Who.** IR at each of the listed banks. Garanti BBVA, for instance, publishes a
full BRSA consolidated results presentation in Turkish and English each quarter
— 1H26 showed net income of **TL 64.4bn (+20% y/y), CAR 15.9%, ROAE 28.1%, ROAA
2.7%**, with Q2 EPS missing consensus by roughly 16%
([TipRanks](https://www.tipranks.com/news/company-announcements/garanti-bbva-publishes-1h26-brsa-consolidated-financial-results-presentation),
[Investing.com](https://www.investing.com/news/company-news/garanti-bbva-1h26-slides-strong-fees-offset-margin-pressure-93CH-4825639)).

**What they need.** To know how they will be compared *before* the call — what
peers reported, on what basis, and where their own numbers look weak.

**Why.** IR is asked "why is your margin below theirs" live on an earnings call.
Standard IR practice is a concise peer summary before earnings and a briefing on
how competitor disclosures will shape questions.

**Concerns.** Being surprised. Also being *mis*-compared, when a peer's
favourable ratio rests on a different definition.

**Freshness.** Peak demand in the 48 hours before their own results.

**Carthago fit.** Good, and this is a buyer with a budget who is easy to reach.
Slightly awkward — selling comparison to the compared.

---

## Cluster C — Competing with a bank

### C1. The four desks inside a bank

Not one buyer. **Treasury/ALM** wants peer deposit cost and repricing gaps.
**Risk** wants peer provisioning, coverage and stage migration to benchmark its
own. **Pricing** wants competitor product rates — the highest-value item on the
whole list and the one carthago's product-shelf lane was designed for but never
automated. **Strategy** wants share movement by segment.

**Why quarterly-published data still helps a pricing team:** it does not replace
shopping competitor rates, but it tells them *whether a competitor can afford*
the price it is quoting.

**Concerns.** Regulatory constraint is now first-order. The BDDK and CBRT
tightened consumer lending in 2026 — overdraft limits capped at **twice
documented three-month average income**, and from **1 April 2026 a 10% credit
conversion factor** applies to unused overdraft limits in capital adequacy
([P.A. Turkey](https://www.paturkey.com/news/2026/turkey-unveils-overnight-credit-tightening-as-central-bank-and-regulator-clamp-down-on-lending-27303/),
[Daily Sabah on the review of credit curbs](https://www.dailysabah.com/business/economy/turkiye-reviews-credit-curbs-as-financing-relief-seen-as-of-mid-2026)).
Under growth caps, banks push margin into uncapped categories — so knowing who
is at their cap is directly tradeable knowledge.

**Freshness.** Pricing wants daily. Everything else, quarterly.

### C2. Foreign parent banks

**Who.** BBVA holds **~86% of Garanti** after the takeover bid
([BBVA](https://www.bbva.com/en/bbva-reaches-86-percent-stake-in-its-turkish-franchise-following-the-closing-of-the-takeover-bid/)).
Others in the same position include BNP Paribas (TEB), ING, HSBC, QNB, Emirates
NBD (Denizbank), ICBC and Burgan.

**What they need.** "How is our subsidiary doing against local peers" — in
English, on a consistent basis, without reading Turkish filings.

**Why.** Head office allocates capital between country franchises and must
justify Türkiye against Mexico or Colombia. BBVA's own research arm publishes a
**monthly Türkiye Banking Sector Outlook** — credit growth, dollarisation, RoE
for deposit banks, capital adequacy, regulation — released within days of month
end ([BBVA Research, March 2026](https://www.bbvaresearch.com/en/publicaciones/turkiye-monthly-banking-sector-outlook-march-2026/)).
That a foreign parent staffs a team to produce this monthly is direct evidence
of demand — and it is the closest existing analogue to carthago's output.

**Concerns.** Currency translation, capital repatriation, and being the last to
know about a local regulatory shift.

**Freshness.** Monthly, aligned to BDDK's bulletin cycle.

**Carthago fit.** Very strong, and **English is mandatory**. This is the single
clearest business case for the parked bilingual work.

### C3. Fintechs and new entrants

**Who.** Turkish payment and e-money institutions, digital banks, and foreign
players assessing entry. The regime is defined: digital-bank minimum capital is
**₺2.5bn**, digital banks may serve only consumers and SMEs, and may not operate
branches ([Paksoy, *Fintech in Türkiye 2026*](https://paksoy.av.tr/en/2026/04/fintech-in-turkiye-2026-law-and-practice/),
[Chambers Fintech 2026 — Turkey](https://practiceguides.chambers.com/practice-guides/fintech-2026/turkey)).
Wallet providers unlicensed before October 2023 had to be authorised by the CBRT
by end-2025.

**What they need.** Market sizing by segment, digital adoption benchmarks, and
incumbent product pricing.

**Concerns.** Whether a segment is large enough to enter and whether incumbents
can undercut them.

**Freshness.** Not time-critical — this is a planning purchase, consumed once.

**Carthago fit.** The TBB/TKBB digital lane and the product shelf are aimed
straight at this reader.

---

## Cluster D — Understanding the sector

### D1. Consultancies

**Who.** McKinsey, BCG, Bain, and the Big Four's Turkish banking practices.
Their published work is global — [McKinsey's Global Banking Annual Review](https://www.mckinsey.com/industries/financial-services/our-insights/global-banking-annual-review)
(global banking net income $1.3tn in 2025, +7%) and
[Deloitte's 2026 Banking and Capital Markets Outlook](https://www.deloitte.com/us/en/insights/industry/financial-services/financial-services-industry-outlooks/banking-industry-outlook.html) —
with **no Turkey-specific equivalent found**. The country analysis is built
privately, per engagement, repeatedly.

**What they need.** A ready peer set, so a pitch deck takes a day rather than a
week.

**Freshness.** Quarterly is fine; history matters more.

**Carthago fit.** Consultancies buy data and have budget. Probably the most
realistic near-term paying segment.

### D2. Audit firms

Benchmarking peer provisioning practice and disclosure completeness, both for
audit quality and for advisory. The ECL-assumption comparison is directly useful
to them, and they are the source of the key audit matters that would populate it.

### D3. Regulators — BDDK, TCMB, TMSF

BDDK already holds the raw data — banks report to it — and publishes a
[monthly bulletin](https://www.bddk.org.tr/bultenaylik/en),
[weekly sector data](https://www.bddk.org.tr/BultenHaftalik/en), the
[FinTurk system](https://www.bddk.org.tr/BultenFinturk) and quarterly
[Banking Sector Main Indicators](https://www.bddk.org.tr/Veri/Detay/171). It even
runs its own academic journal.

They will not buy anything. What they lack is the **cross-join** — regulation in
force ⋈ balance sheets ⋈ macro ⋈ market — in one place. Being cited by a
regulator is worth more than a subscription, and it is achievable.

Note the structural change in train: **Ziraat Katılım, Vakıf Katılım and Halk
Katılım are merging**, announced June 2026 ([Bloomberg](https://www.bloomberg.com/news/articles/2026-06-05/three-turkish-state-run-lenders-to-merge-in-islamic-economy-push)).
That alters the bank universe carthago tracks and will need handling in the
registry regardless of any audience decision.

### D4. International financial institutions

**Who.** IMF country teams, World Bank, BIS.

**Real example.** The **2025 Article IV consultation** concluded 13 February
2026 (Country Report No. 2026/043). It found inflation down from 49.4% in
September 2024 to **30.9% at end-2025**, with end-2026 expected at 23% and growth
at 4.2% — and specifically flagged that high inflation is impairing financial
deepening, visible as **falling maturities on bank lending and a widening gap
between corporate and SME profitability**
([IMF press release](https://www.imf.org/en/news/articles/2026/02/13/pr-26047-turkiye-imf-executive-board-concludes-2025-article-iv-consultation),
[full staff report](https://www.imf.org/en/publications/cr/issues/2026/02/13/republic-of-trkiye-2025-article-iv-consultation-press-release-staff-report-and-statement-573962)).
Turkey's last full [Financial System Stability Assessment](https://www.imf.org/en/publications/cr/issues/2017/02/03/turkey-financial-sector-assessment-program-financial-system-stability-assessment-44617)
was 2017.

**What they need.** System-level aggregates with the distribution behind them —
not just the sector average but the dispersion across banks.

**Carthago fit.** Note that "maturity of bank lending" and "SME versus corporate
profitability" are both bank-level series carthago could produce and the IMF had
to assert qualitatively.

### D5. Journalists

**Who.** Bloomberg and Reuters Türkiye desks, [Bloomberg HT](https://www.bloomberght.com/haberler/turkiye-ekonomisi),
Ekonomim, Dünya, Daily Sabah.

**What they need.** One citable number and a chart, in minutes, on deadline.

**Freshness.** Immediate or worthless.

**Carthago fit.** They will never pay. They are the distribution channel — a
chart credited in the press is the cheapest marketing available, and the backlink
serves the SEO lane directly.

### D6. Academics

Turkish banking is a well-populated research field — DEA efficiency studies,
CAMELS frameworks, panel analyses. A representative recent paper builds its
dataset for **18 banks over 2010–2023 from BRSA financial statements by hand**
([CAMELS-DEA, *Applied Economics*](https://www.tandfonline.com/doi/full/10.1080/00036846.2024.2339186)).
There are even community R packages — [`bddkR`](https://cran.r-project.org/package=bddkR)
and `rbrsa` — built to scrape BDDK, which is evidence of unmet demand for
programmatic access.

**Carthago fit.** The public API answers a need people are currently coding
around. No revenue; high citation and credibility value.

---

## Cluster E — Choosing a bank

### E1. Savers

**What they need.** Which bank pays most, and is my money safe. Cover is
**₺1.2m per person per institution for 2026**, and it applies to participation
funds as well as interest-bearing deposits.

**Freshness.** Rates: daily. Safety: never changes until it does.

**Who serves them today.** [HangiKredi](https://www.hangikredi.com/yatirim-araclari/mevduat-faiz-oranlari)
and [Enuygun Finans](https://www.enuygunfinans.com/mevduat/) compare deposit
rates — but purely as rate tables, with **no bank-health dimension at all**.

**Carthago fit.** Pays nothing directly, but this is the traffic engine, and the
combination of *rate plus health* is not currently offered by anyone.

### E2. SMEs and mid-corporates

Choosing a lender, and increasingly constrained: the IMF explicitly noted the
widening corporate/SME profitability gap, and consumer and SME credit are under
active macroprudential restriction. Which bank still has room to lend to their
sector is a genuine question with a data answer.

---

## Freshness matrix

| Actor | Required freshness | Carthago's natural cadence fits? |
|---|---|---|
| Sell-side analysts | Hours after results | ✗ — the audit pipeline is too slow |
| Journalists | Minutes | ✗ for filings, ✓ for the news/KAP lane |
| Bank pricing desks | Daily | ✗ — needs the product-shelf automation |
| Bank IR | 48h pre-results | ~ |
| Foreign parents / BBVA-style | Monthly | ✓ |
| Credit investors, DFIs, treasurers | Quarterly + event alerts | ✓ |
| Consultancies, academics, IFIs | Quarterly, history-heavy | ✓ |
| Savers | Daily rates, static safety | Partly |

**The pattern:** carthago's cadence is a natural fit for the *credit and
institutional* audiences and a natural mismatch for the *equity and media*
audiences. That is an argument for aiming at the former.

## What they use today

- **Free and official:** BDDK monthly/weekly bulletins and FinTurk; TBB and TKBB
  statistical reports; KAP for filings; bank IR presentations.
- **Paid:** Moody's BankFocus and Orbis, Fitch Connect, S&P Capital IQ,
  Bloomberg, Refinitiv — all with thin Türkiye-specific depth, standardised to a
  global template that discards local detail.
- **Home-made:** every consultancy, every research desk, every academic, and
  BBVA's own research team, all rebuilding the same comparables privately.

**The gap:** official sources publish *sector aggregates*; commercial databases
publish *standardised summaries*. Nobody publishes per-bank Turkish detail at
audit-report depth. That is carthago's actual position.

## Implications

1. **The credit cluster is the best-fit paying audience** — deepest need, worst
   served, and its quarterly cadence matches the pipeline. Equity users are more
   numerous but want speed carthago cannot offer.
2. **English is not a nice-to-have.** Every high-value actor identified — credit
   investors, DFIs, foreign parents, rating agencies, IFIs, correspondent banks —
   works in English. The parked bilingual plan has a business case now that it
   did not have as a general improvement.
3. **BBVA Research's monthly Türkiye outlook is the proof of demand** and the
   nearest competitor. A foreign parent funds a standing team to produce it.
4. **The two missing spine questions are both narrative** — forbearance usage and
   per-bank regulation impact — and both appear in multiple actor profiles above.
   That is the strongest argument yet for starting the narrative extraction.
5. **Before any of it: the upstream terms.** BDDK/TCMB/TBB attribution is fine;
   **monetising requires written permission**. Every paying path above runs into
   that before it runs into an engineering problem.

## Open questions

- Does the product-shelf automation get revived? It is the highest-value item for
  the single most reachable buyer (bank pricing desks).
- Does the results-day gap get closed for the sell-side, or is that audience
  conceded?
- Is the three-way state participation-bank merger handled as a registry change
  before or after any audience work?
