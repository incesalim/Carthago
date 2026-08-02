# Who the dashboard is for — actor research — 2026-08-02

Every group with a plausible reason to use carthago, researched individually:
who they are, **the questions they actually ask**, how they get an answer today,
how fresh it has to be, and a real example of the document each one produces or
consumes.

> **Scope: research only. No code changed, nothing built, nothing decided.**
> This is the audience layer the "rationale before narrative" rule requires — it
> has to exist before a new page gets designed. Status: **draft for review**, not
> an agreed roadmap.

The "how they answer it today" line is the load-bearing one throughout. It shows
what carthago would be replacing, and how bad the current path is.

---

## The spine — a bank CEO's questions

Derived by role-play, and the origin of everything below. Seven headline
questions, which turn out to be near-universal across the actors:

1. What are peers paying for deposits?
2. Real bad-loan formation, before write-offs and portfolio sales
3. Why is our return below theirs — decomposed into margin / cost / risk / leverage
4. Where did share move this quarter, by product
5. Who is capital- or growth-constrained and therefore cannot respond
6. Whose ratios are propped up by regulatory relief
7. Does this new rule hurt them more than us

Three are answerable today from data already in D1 (1, 2, 3), two nearly (4, 5),
and **two are genuinely missing and both are narrative-side** (6, 7).

Peer data matters to a CEO in exactly two moments: **setting a price**, and
**explaining performance to the board.** Everything else is internal reporting.
Decomposed into what is actually asked in a Monday meeting:

**Margin**
- What is Garanti paying for a 32-day TL deposit *this week* — not last quarter?
- Is anyone paying visibly above market? Is that a land grab or a liquidity
  problem?
- Are we longer or shorter duration than peers going into the next cut?
- What share of peer funding is demand deposits — the free money — versus ours?
- How much of peer NIM is CPI linkers, and what happens at 23% inflation?
- How much swap funding are peers running, and at what cost?

*Today:* interbank chatter and brokers; customers who shop around and mention it
to the relationship manager; posted rate sheets that don't match negotiated
rates; CBRT weekly averages that describe the pool, not the competitor.

**Risk**
- Is our cost of risk high because our book is worse, or because we provision
  harder than they do?
- What ECL scenario weights do peers use? If they weight the bad case at 10% and
  we weight it at 30%, our cost of risk is not comparable to theirs.
- What is peer stage 2 as a share of loans, and is it rising faster than ours?
- Gross NPL formation before write-offs and portfolio sales — theirs versus ours.
- Who is selling NPL portfolios, and at what price? That is the clearing level
  for our own book.
- Are we an outlier on any sector concentration?

*Today:* reading peer filings by hand; informal signals from the audit firm,
which audits competitors too; BDDK aggregates for context; risk-manager networks
and TBB working groups.

**Capital and constraint**
- Who is close enough to their requirement that they cannot chase the next large
  deal?
- Who is at the credit growth cap and therefore physically cannot compete this
  month?
- Whose capital ratio uses the forbearance FX rate, and what is it without?
- If the lira drops 20%, whose ratio falls furthest?

*Today:* inference from behaviour — you learn a competitor was constrained by
winning a deal you expected to lose.

**Competition**
- Where did we lose share this quarter, by product, not in total?
- What is our revenue per branch and per employee against peers?
- Is anyone growing in a segment we exited?
- If we are at the cap, where should the marginal lira of lending go?

**The board conversation**
- Why is our return on equity four points below theirs — how much is margin, how
  much cost, how much risk, how much leverage?
- Which of those four can we actually move next year?
- Is their return real, or a one-off — a free-provision release, a subsidiary
  sale, a property revaluation?

---

## Cluster A — Judging whether a bank is safe

The deepest need, the least served, and the cluster where audit-report extraction
is the differentiator rather than a nice-to-have.

### A1. Credit investors — Eurobond, AT1, Tier 2 holders

**Who.** EM credit desks at global asset managers, dedicated EM debt funds,
private banks placing Turkish bank paper, and the syndicate banks. The market is
active: Akbank sold **$600m of AT1 at 7.95%** in February 2026, callable at 5.5
years, via Citi, Emirates NBD, First Abu Dhabi Bank, HSBC, JPMorgan and BofA —
extending Vakıfbank's record for the cheapest Turkish AT1 ever
([bne IntelliNews](https://www.intellinews.com/istanbul-listed-akbank-extends-vakifbank-s-record-for-cheapest-ever-subordinated-at1-eurobond-426241/)).
Fitch expects total outstanding paper from Turkish issuers to exceed **$540bn in
2026**.

**What they ask.**
- How far is CET1 above the AT1 trigger, and what single event moves it 100bp?
- Is the reported ratio calculated using BDDK's forbearance FX rate?
- How much of the last two quarters' capital build was CPI-linker income that
  reverses as inflation falls?
- Are there enough distributable reserves under Turkish law for the coupon, and
  is payment at management's discretion or the regulator's?
- What is the external maturity wall in the next 12 months, and is the rollover
  ratio holding?
- What share of deposits is FX, and what share sits above the ₺1.2m insurance
  ceiling — the flighty part?
- If the lira falls 20%, what happens? FX-denominated risk-weighted assets
  against largely lira capital.

An AT1 holder is effectively short a call on the bank's capital ratio. The number
that matters is how far CET1 sits above the trigger; the second is whether the
earnings rebuilding capital are real or accounting.

**How they answer it today.** The bank's English investor deck — fastest, but it
is marketing; the offering circular on the Irish or Luxembourg exchange for the
actual AT1 terms; Bloomberg for spread history; rating agency bank reports as the
nearest thing to a standardised peer view; a call to the syndicate desk that
placed the deal; and, if diligent, the BRSA filing itself — 300 pages in Turkish.

**Freshness.** Quarterly for the balance sheet; *same-week* for anything that
changes the capital story — a new issue, a regulatory change, a rating action.

**Example document.** [S&P: *Türkiye Banking Outlook 2026 — A Rocky Road To Recovery*](https://www.spglobal.com/ratings/en/regulatory/article/turkiye-banking-outlook-2026-a-rocky-road-to-recovery-s101665211)
and [*Sector Review: Turkish Participation Banks Grappling With Growth Constraints*](https://www.spglobal.com/ratings/en/regulatory/article/sector-review-turkish-participation-banks-grapple-with-growth-constraints-s101682885).

**Carthago fit.** Strong. The `capital`, `liquidity`, `fx_position`,
`credit_quality`, `stages` and `npl_movement` lanes are this reader's worksheet.
The gap is spine question 6 — forbearance usage — which is narrative.

### A2. Rating agency analysts

**Who.** Fitch, Moody's and S&P internationally; JCR Eurasia and SAHA
domestically. All three internationals move in blocks — Fitch has repeatedly
taken sector-wide actions tied to the sovereign and the operating environment
([example](https://www.seenews.com/news/fitch-downgrades-turkish-banks-isbank-garanti-akbank-yapi-kredi-427383),
[outlook revisions in line with the sovereign](https://gulfnews.com/business/banking/fitch-revises-turkish-banks-outlooks-to-negative-on-sovereign-outlook-change-1.73579042)).

**What they ask.**
- Where does this bank sit in its peer cohort on each factor, this year versus
  last?
- Is reported asset quality flattered by write-offs and portfolio sales?
- What is core profitability excluding one-offs — free provisions, trading,
  subsidiary gains?
- Is capital maintained by earnings, or by regulatory relief?
- Is related-party lending rising?
- Would the sovereign support this bank, and can it afford to?

Their methodologies are explicitly relative — a viability rating is assigned
against peers in the same operating environment — so building the cohort is the
laborious part.

**How they answer it today.** Their own internal bank database; **an annual
management meeting where they receive non-public data directly from the CFO and
CRO**; a data template the bank fills in for them; peer medians computed
in-house.

**Freshness.** Quarterly, anchored on the annual audited report.

**Carthago fit.** They will not buy a replacement for their own work, and they
have access carthago does not. Their real gap is *normalisation* — comparability
across banks whose ECL assumptions differ. And they are a credibility audience:
being cited in a rating report is worth more than a subscription.

### A3. Correspondent bank FI credit officers

**Who.** Any foreign bank clearing USD or EUR for a Turkish bank, or taking
trade-finance risk on one.

**What they ask.**
- Is this bank solvent enough that I can carry the exposure another year?
- Who ultimately owns it, and is any owner sanctioned or politically exposed?
- What has changed since the last review — a penalty, a management change, an
  adverse headline?
- Would my own regulator criticise this file if it read it?

This is a regulatory obligation, not an investment choice. The
[FATF *Guidance on Correspondent Banking Services*](https://www.fatf-gafi.org/content/dam/fatf-gafi/guidance/Guidance-Correspondent-Banking-Services.pdf)
and the [FFIEC BSA/AML manual](https://bsaaml.ffiec.gov/manual/AssessingComplianceWithBSARegulatoryRequirements/10)
require ongoing monitoring for "changes in the respondent institution's risk
profile". The cost of getting it wrong is regulatory action — so the file must be
*documented*, not merely correct, which makes a citable, traceable source
unusually valuable here.

**How they answer it today.** The respondent bank completes a **Wolfsberg
Correspondent Banking Due Diligence Questionnaire** — the standard industry
artefact; Bankers Almanac and Moody's BankFocus for financials and ownership;
World-Check or Dow Jones for sanctions and PEP screening; adverse-media
monitoring; annual refresh. The World Bank publishes a
[Correspondent Account KYC Toolkit](https://documents1.worldbank.org/curated/en/792381468142174651/pdf/941830WP0Box3800ACCOUNT0KYC0TOOLKIT.pdf)
for exactly this file.

**Freshness.** Annual review cycle, with event-driven interrupts.

**Example document.** Moody's sells [BankFocus](https://www.bvdinfo.com/en-us/our-products/data/international/bankfocus)
into precisely this use case — its brochure is subtitled *"research and analyse
banks, for counterparty"* — bundling roughly ten years of standardised bank
financials with ownership and compliance data.

**Carthago fit.** Genuine, and the traceability requirement plays to the
pipeline's strength. But this buyer wants global coverage in one place; Türkiye
alone is a supplement, not a replacement.

### A4. Development finance institution officers

**Who.** EBRD, IFC, EIB, plus bilaterals (KfW, Proparco, FMO). Volume is
substantial: **EBRD invested a record €2.7bn across 54 projects in Türkiye in
2025**, 91% private-sector
([EBRD](https://www.ebrd.com/home/news-and-events/news/2026/ebrd-invested-a-record--2-7-billion-in-tuerkiye-in-2025.html)).
Recent bank facilities include **$130m to Akbank** in December 2025 ($70m
women-led SMEs, $50m youth-led, $10m digital) and **€50m to TEB** in March 2026
under the €600m Women in Business II programme.

**What they ask.**
- Can this bank absorb $100m and on-lend it to the target segment inside the
  disbursement window?
- Is their SME book genuinely growing, or is it relabelled corporate lending?
- Do they have capital headroom to grow the book we are funding?
- Can their systems report sub-borrower attributes — women-led, youth-led, green?
- Are we already concentrated on this bank across our other facilities?

They lend *through* banks: the bank's solvency is their credit risk and the
bank's SME book is their impact metric. Exposure is both credit and reputational.

**How they answer it today.** An on-site due diligence mission; audited
financials and a bespoke data pack from the bank; internal credit scoring; a
board approval document that becomes the public Project Summary Document.

**Freshness.** Annual for the credit file, quarterly for monitoring.

**Example document.** The [EBRD Project Summary Document for the Akbank SME credit line](https://www.ebrd.com/home/work-with-us/projects/psd/43783.html)
is instructive for what it *lacks*: a "The Client" section giving market
position, business segments and agency ratings, and **no financial statements,
balance-sheet data or profitability metrics at all**. The public record of these
deals contains almost no bank fundamentals.

**Carthago fit.** Strong and underserved, especially the SME and sector-lending
breakdown — the `loans_by_sector` lane. These institutions publish and work in
English.

### A5. Corporate treasurers

**Who.** Treasury functions at large Turkish corporates and multinationals with
Turkish operations, holding deposits and credit lines across several banks.

**What they ask.**
- If I place ₺500m here for three months, do I get it back?
- Which of my eight banks is weakest right now — should I rebalance before the
  quarter closes?
- My policy caps exposure by rating tier. Has anyone moved tier?
- Am I being offered a competitive rate, or a sticky-customer rate?
- Can I show the board a documented monitoring process?

Standard practice sets exposure limits by institution and rating tier
([Association of Corporate Treasurers](https://www.treasurers.org/hub/treasurer-magazine/treasury-essentials-counterparty-risk),
[Treasury Today](https://treasurytoday.com/risk-management/counterparty-risk/counterparty-credit-risk/)).
The known weakness is that **ratings lag** — market indicators moved faster than
downgrades through the last crisis — so treasurers supplement with CDS and news
flow. For most Turkish banks there is no liquid CDS, which leaves a hole that
quarterly fundamentals could fill. The deposit-insurance ceiling is irrelevant at
their scale: **TMSF cover rises to ₺1.2m per person per institution for 2026**,
from ₺950,000 ([TMSF](https://www.tmsf.org.tr/en/Tmsf/Finansman/mevduat.sss.guncel.en)).

**How they answer it today.** Ratings as the policy anchor, which lag; CDS where
it exists, which mostly it does not; the relationship banker, who is conflicted;
news; a treasury management system that aggregates exposure but supplies no
credit view. In practice, **mostly nothing systematic**.

**Freshness.** Quarterly baseline; immediate on an adverse event.

**Carthago fit.** Real, underserved, nobody selling to them. The obstacle is
distribution, not data — treasurers do not browse dashboards.

---

## Cluster B — Valuing a bank

### B1. Sell-side analysts

**Who.** Research desks at the Turkish brokerages — Ak Yatırım (covering ~70 BIST
names, ~85% of market cap), İş Yatırım, Garanti BBVA Yatırım, Yapı Kredi Yatırım,
Ünlü, Oyak — plus the global banks' EM teams. Goldman Sachs was publicly positive
on Turkish bank stocks for 2027 as of February 2026.

**What they ask.**
- What was the quarter's NIM, and how much came from CPI linkers versus core
  spread?
- What is swap-adjusted NIM, and is management's full-year guidance still
  reachable?
- Cost of risk against guidance — and was there a free-provision release
  flattering it?
- Is fee growth real, or just inflation?
- Is the cost/income ratio flattered by inflation accounting?
- Was there a one-off — a subsidiary sale, a property revaluation, a tax item?
- Did loan growth hit the regulatory cap, and where did the margin go instead?
- How does all that compare with the three peers that reported the same morning?

Their product is a quarterly preview and review across the coverage universe
within days. Turkish banks were noted trading at a ~73% discount to global EM
peers — the whole debate is whether that gap is justified, which is a comparables
argument. Swap-adjusted NIM is the perennial fight, and it is **not cleanly
derivable** from disclosed data.

**How they answer it today.** The IR presentation and the Excel data pack banks
publish alongside it; the BRSA filing on KAP; the earnings call, where they can
simply ask; their own model updated within hours; consensus screens for the
surprise calculation. **Their pain is that six to eight banks report inside two
weeks, each on a slightly different basis.**

**Freshness.** Results day. Within hours, not days — the most freshness-sensitive
audience of all.

**Example document.** [Ak Yatırım research](https://www.akyatirim.com.tr/research.aspx),
[Garanti BBVA Yatırım research](https://www.garantibbvayatirim.com.tr/medium/ResearchReports-Constant-83300.vsf).

**Carthago fit.** Good on content, weak on timing — the audit-report pipeline
lands well after the results-day window that matters most.

### B2. Buy-side — EM funds and local institutions

**Who.** Foreign EM equity and debt funds, Turkish pension and mutual funds, and
the local asset managers already visible in the TEFAS lane.

**What they ask.**
- Is the sector's discount to EM peers justified, or is this the entry point?
- Which bank has the most operating leverage to falling rates?
- Who is over-earning on linkers and will disappoint when inflation normalises?
- Who is under-provisioned relative to their stage 2 book?
- Is the dividend real, or an accounting artefact?
- What regulatory change could remove a quarter of earnings overnight?

**How they answer it today.** Sell-side research paid through commissions;
company meetings and roadshows; terminal screens; their own models; broker
conferences.

**Freshness.** Quarterly, but they want history and export more than speed.

**Carthago fit.** Strong, and the public API is the right delivery mechanism.

### B3. Bank investor relations teams

**Who.** IR at each listed bank. Garanti BBVA, for instance, publishes a full
BRSA consolidated results presentation in Turkish and English each quarter — 1H26
showed net income of **TL 64.4bn (+20% y/y), CAR 15.9%, ROAE 28.1%, ROAA 2.7%**,
with Q2 EPS missing consensus by roughly 16%
([TipRanks](https://www.tipranks.com/news/company-announcements/garanti-bbva-publishes-1h26-brsa-consolidated-financial-results-presentation),
[Investing.com](https://www.investing.com/news/company-news/garanti-bbva-1h26-slides-strong-fees-offset-margin-pressure-93CH-4825639)).

**What they ask.**
- What will an analyst ask on Thursday that I cannot answer?
- Which peer has already reported, and what did they show on NIM and cost of
  risk?
- Will our cost/income look worse than everyone's, and what is the honest reason?
- Did a peer change a definition in a way that makes our comparison look bad?
- What did the sell-side write about us after last quarter?

IR is asked "why is your margin below theirs" live on a call. They are buying
defence against surprise, and against being *mis*-compared when a peer's
favourable ratio rests on a different definition.

**How they answer it today.** Reading peer presentations the day they land; a
peer table built by their own strategy team; sell-side notes on peers, received
free; pre-quiet-period calls with analysts; consensus screens.

**Freshness.** Peak demand in the 48 hours before their own results.

**Carthago fit.** Good, a buyer with budget and easy to reach. Slightly awkward —
selling comparison to the compared.

---

## Cluster C — Competing with a bank

### C1. The four desks inside a bank

Not one buyer but four, each with different questions.

**Treasury / ALM** — peer deposit cost and repricing gaps. Questions as under the
CEO's *Margin* heading above; this is the desk that does that work.

**Risk** — peer provisioning, coverage and stage migration, to benchmark its own.
Questions as under the CEO's *Risk* heading.

**Pricing** — the highest-value item on the whole list, and what the product-shelf
lane was designed for but never automated.
- What is the competitor's advertised rate on a 12-month general-purpose loan
  today?
- Did anyone cut mortgage pricing this week?
- Can that competitor *afford* the price they are quoting, or are they buying
  share below cost?
- Which competitor is capital constrained and therefore will not follow us down?

*Today:* mystery shopping — literally checking competitor websites and branches —
comparison sites, and lost-deal reports from the sales force that arrive weeks
late and anecdotally.

Quarterly filings do not replace shopping competitor rates, but they answer the
question shopping cannot: **whether a competitor can afford the price it is
quoting.**

**Strategy** — share movement by segment; questions as under the CEO's
*Competition* heading.

**Concerns across all four.** Regulatory constraint is now first-order. BDDK and
CBRT tightened consumer lending in 2026 — overdraft limits capped at **twice
documented three-month average income**, and from **1 April 2026 a 10% credit
conversion factor** applies to unused overdraft limits in capital adequacy
([P.A. Turkey](https://www.paturkey.com/news/2026/turkey-unveils-overnight-credit-tightening-as-central-bank-and-regulator-clamp-down-on-lending-27303/),
[Daily Sabah](https://www.dailysabah.com/business/economy/turkiye-reviews-credit-curbs-as-financing-relief-seen-as-of-mid-2026)).
Under growth caps banks push margin into uncapped categories — so knowing who is
at their cap is directly tradeable knowledge.

**Freshness.** Pricing wants daily. Everything else quarterly.

### C2. Foreign parent banks

**Who.** BBVA holds **~86% of Garanti** after the takeover bid
([BBVA](https://www.bbva.com/en/bbva-reaches-86-percent-stake-in-its-turkish-franchise-following-the-closing-of-the-takeover-bid/)).
Others in the same position include BNP Paribas (TEB), ING, HSBC, QNB, Emirates
NBD (Denizbank), ICBC and Burgan.

**What they ask.**
- Is our subsidiary out- or under-performing the local market, or just the local
  market?
- What return are we earning on capital allocated to Türkiye against Mexico or
  Colombia?
- When local management says "the market was difficult", is that true?
- What is the regulatory trajectory — will we be required to inject more capital?
- Can we get dividends out?

**How they answer it today.** The subsidiary reports upward and controls the
narrative; an in-house research team; local sell-side; board members on the local
board; the group auditor. **The unmet need is an independent check on what the
subsidiary tells head office** — a commercial need, not a curiosity.

**Freshness.** Monthly, aligned to BDDK's bulletin cycle.

**Example document.** BBVA's own research arm publishes a **monthly Türkiye
Banking Sector Outlook** — credit growth, dollarisation, RoE for deposit banks,
capital adequacy, regulation — released within days of month end
([BBVA Research, March 2026](https://www.bbvaresearch.com/en/publicaciones/turkiye-monthly-banking-sector-outlook-march-2026/)).
That a foreign parent staffs a standing team to produce this monthly is direct
evidence of demand — and it is the closest existing analogue to carthago's
output.

**Carthago fit.** Very strong, and **English is mandatory**. The clearest
business case for the parked bilingual work.

### C3. Fintechs and new entrants

**Who.** Turkish payment and e-money institutions, digital banks, and foreign
players assessing entry. The regime is defined: digital-bank minimum capital is
**₺2.5bn**, digital banks may serve only consumers and SMEs, and may not operate
branches ([Paksoy, *Fintech in Türkiye 2026*](https://paksoy.av.tr/en/2026/04/fintech-in-turkiye-2026-law-and-practice/),
[Chambers Fintech 2026 — Turkey](https://practiceguides.chambers.com/practice-guides/fintech-2026/turkey)).
Wallet providers unlicensed before October 2023 had to be authorised by the CBRT
by end-2025.

**What they ask.**
- How many people in Türkiye genuinely bank mobile-only, and how fast is that
  growing?
- What does an incumbent earn on a card or payments customer?
- Which segment are incumbents retreating from?
- What does it cost an incumbent to serve a branch customer — what is my cost
  advantage worth?
- What capital would I need, and who already holds a licence?

**How they answer it today.** TBB digital statistics; BDDK regulation; expensive
consultancy reports; incumbent investor decks; hiring an ex-banker for the tacit
knowledge.

**Freshness.** Not time-critical — a planning purchase, consumed once.

**Carthago fit.** The TBB/TKBB digital lane and the product shelf aim straight at
this reader.

---

## Cluster D — Understanding the sector

### D1. Consultancies

**Who.** McKinsey, BCG, Bain and the Big Four's Turkish banking practices. Their
published work is global — [McKinsey's Global Banking Annual Review](https://www.mckinsey.com/industries/financial-services/our-insights/global-banking-annual-review)
(global banking net income $1.3tn in 2025, +7%) and
[Deloitte's 2026 Banking and Capital Markets Outlook](https://www.deloitte.com/us/en/insights/industry/financial-services/financial-services-industry-outlooks/banking-industry-outlook.html) —
with **no Turkey-specific equivalent found**.

**What they ask.**
- What is the peer benchmark table for this pitch, by Tuesday?
- Where is this client's largest gap to best-in-class on cost/income?
- How big is the prize in this segment?

**How they answer it today.** A junior analyst rebuilds it from IR decks and BDDK
over two or three days, **per engagement, forever**; global proprietary
benchmarks that lack Turkish granularity; expert networks for the rest.

**Freshness.** Quarterly is fine; history matters more.

**Carthago fit.** Consultancies buy data and have budget. Probably the most
realistic near-term paying segment.

### D2. Audit firms

**What they ask.**
- Is our client's ECL assumption an outlier against peers?
- What key audit matters did other auditors report for comparable banks?
- Is a peer disclosing something our client is not?

**How they answer it today.** Reading peer filings; internal methodology and
national-office guidance; limited published benchmarking.

**Carthago fit.** The ECL-assumption comparison is directly useful to them — and
they are the source of the key audit matters that would populate it.

### D3. Regulators — BDDK, TCMB, TMSF

**What they ask.**
- Is the public picture consistent with the supervisory returns we receive?
- Which bank is an outlier, and is it gaming a definition?
- What will the rule we are drafting actually do?

**How they answer it today.** Supervisory returns, on-site examination and
in-house analytics — all better than anything public. BDDK also publishes a
[monthly bulletin](https://www.bddk.org.tr/bultenaylik/en),
[weekly sector data](https://www.bddk.org.tr/BultenHaftalik/en), the
[FinTurk system](https://www.bddk.org.tr/BultenFinturk) and quarterly
[Banking Sector Main Indicators](https://www.bddk.org.tr/Veri/Detay/171), and
runs its own academic journal.

**Carthago fit.** They will not buy anything. **What they lack is the
cross-join** — regulation in force ⋈ balance sheets ⋈ macro ⋈ market — in one
place, and a view of how their own rules land in public. Being cited by a
regulator is worth more than a subscription, and it is achievable.

Note the structural change in train: **Ziraat Katılım, Vakıf Katılım and Halk
Katılım are merging**, announced June 2026 ([Bloomberg](https://www.bloomberg.com/news/articles/2026-06-05/three-turkish-state-run-lenders-to-merge-in-islamic-economy-push)).
That alters the bank universe carthago tracks and needs handling in the registry
regardless of any audience decision.

### D4. IMF / World Bank / BIS

**What they ask.**
- Is the system resilient to a stress scenario?
- Are macroprudential caps suppressing credit, and where is it leaking around
  them?
- Is the maturity of bank lending shortening?
- Is there hidden impairment behind restructuring and forbearance?
- Is state-bank lending crowding out or subsidising?

**How they answer it today.** The Article IV mission — two weeks in country
meeting the authorities and banks; formal data requests; a full FSAP roughly every
five to ten years (Türkiye's last was [2017](https://www.imf.org/en/publications/cr/issues/2017/02/03/turkey-financial-sector-assessment-program-financial-system-stability-assessment-44617));
published aggregates.

**Example document.** The **2025 Article IV consultation**, concluded 13 February
2026 (Country Report No. 2026/043), found inflation down from 49.4% in September
2024 to **30.9% at end-2025**, with end-2026 expected at 23% and growth at 4.2% —
and specifically flagged that high inflation is impairing financial deepening,
visible as **falling maturities on bank lending and a widening gap between
corporate and SME profitability**
([press release](https://www.imf.org/en/news/articles/2026/02/13/pr-26047-turkiye-imf-executive-board-concludes-2025-article-iv-consultation),
[staff report](https://www.imf.org/en/publications/cr/issues/2026/02/13/republic-of-trkiye-2025-article-iv-consultation-press-release-staff-report-and-statement-573962)).

**Carthago fit.** Note that questions three and four above were asserted
**qualitatively** in that report, because the per-bank series to answer them
quantitatively were not to hand. Both are series carthago could produce.

### D5. Journalists

**Who.** Bloomberg and Reuters Türkiye desks,
[Bloomberg HT](https://www.bloomberght.com/haberler/turkiye-ekonomisi), Ekonomim,
Dünya, Daily Sabah.

**What they ask.**
- Which bank made the most money this quarter, and is that a story?
- Is anyone in trouble?
- What does this new rule mean for an ordinary person?
- Give me one number I can put in a headline that will not be wrong.

**How they answer it today.** KAP filings and press releases; a friendly analyst
on the phone; bank press offices; BDDK and TBB releases; a terminal if the outlet
has one.

**Freshness.** Immediate or worthless.

**Carthago fit.** They will never pay. They are the distribution channel — a
chart credited in the press is the cheapest marketing available, and the backlink
serves the SEO lane directly.

### D6. Academics

Turkish banking is a well-populated research field — DEA efficiency studies,
CAMELS frameworks, panel analyses.

**What they ask.**
- Does ownership type affect efficiency in Türkiye?
- Did macroprudential measure X change lending behaviour?
- I need a panel of N banks over T years with variables A, B and C.

**How they answer it today.** Manual assembly from BDDK and TBB downloads;
BankFocus or Orbis if the university subscribes; self-written scrapers; and,
genuinely, typing figures out of PDFs. A representative recent paper builds its
dataset for **18 banks over 2010–2023 from BRSA financial statements by hand**
([CAMELS-DEA, *Applied Economics*](https://www.tandfonline.com/doi/full/10.1080/00036846.2024.2339186)).
The community has written [`bddkR`](https://cran.r-project.org/package=bddkR) and
`rbrsa` purely to scrape BDDK — evidence of unmet demand for programmatic access.

**Carthago fit.** The public API answers a need people are currently coding
around. No revenue; high citation and credibility value.

---

## Cluster E — Choosing a bank

### E1. Savers

**What they ask.**
- Which bank pays most on ₺100,000 for three months?
- Is my money safe there, and is it covered?
- This small bank I have never heard of — is it real?
- Should I hold lira or foreign currency?

Cover is **₺1.2m per person per institution for 2026**, and applies to
participation funds as well as interest-bearing deposits.

**How they answer it today.** [HangiKredi](https://www.hangikredi.com/yatirim-araclari/mevduat-faiz-oranlari)
and [Enuygun Finans](https://www.enuygunfinans.com/mevduat/) for rates; bank
websites; asking at the branch; forums and word of mouth for the safety question,
**because no source answers it**. Both comparison sites are pure rate tables with
no bank-health dimension at all.

**Freshness.** Rates daily; safety never changes until it does.

**Carthago fit.** Pays nothing directly, but this is the traffic engine — and the
combination of *rate plus health* is not currently offered by anyone.

### E2. SMEs and mid-corporates

**What they ask.**
- Which bank will actually lend to my sector this month?
- Who is cheapest for ₺5m of working capital?
- Is my bank about to cut my limit?
- Is there a credit-guarantee window open?

**How they answer it today.** Their accountant; relationship managers at two or
three banks; the trade association; rumour.

Increasingly constrained: the IMF explicitly noted the widening corporate/SME
profitability gap, and consumer and SME credit are under active macroprudential
restriction. Which bank still has room to lend to their sector is a genuine
question with a data answer.

---

## Freshness matrix

| Actor | Required freshness | Carthago's natural cadence fits? |
|---|---|---|
| Sell-side analysts | Hours after results | ✗ — the audit pipeline is too slow |
| Journalists | Minutes | ✗ for filings, ✓ for the news/KAP lane |
| Bank pricing desks | Daily | ✗ — needs the product-shelf automation |
| Bank IR | 48h pre-results | ~ |
| Foreign parents | Monthly | ✓ |
| Credit investors, DFIs, treasurers | Quarterly + event alerts | ✓ |
| Consultancies, academics, IFIs | Quarterly, history-heavy | ✓ |
| Savers | Daily rates, static safety | Partly |

**The pattern:** carthago's cadence is a natural fit for the *credit and
institutional* audiences and a natural mismatch for the *equity and media*
audiences. That is an argument for aiming at the former.

## What they use today, in aggregate

- **Free and official:** BDDK monthly/weekly bulletins and FinTurk; TBB and TKBB
  statistical reports; KAP for filings; bank IR presentations and Excel data
  packs.
- **Paid:** Moody's BankFocus and Orbis, Fitch Connect, S&P Capital IQ,
  Bloomberg, Refinitiv — all with thin Türkiye-specific depth, standardised to a
  global template that discards local detail.
- **Home-made:** every consultancy, every research desk, every academic, every IR
  team, and BBVA's own research desk, all rebuilding the same comparables
  privately.

**The gap:** official sources publish *sector aggregates*; commercial databases
publish *standardised summaries*. Nobody publishes per-bank Turkish detail at
audit-report depth. That is carthago's actual position.

## Three patterns in the "today" column

1. **The most valuable questions are answered by gossip.** Peer deposit pricing,
   who is constrained, whether a competitor can afford its price — all sourced
   from brokers, lost deals and chatter. That is a market with no product in it.
2. **The comparability questions have no source at all.** Whose ECL weights,
   whose ratio uses forbearance, who changed a definition. Every actor from the
   CRO to the rating analyst to the auditor asks a version, and each answers it
   by reading filings by hand.
3. **Several actors are paying people to do this manually right now** —
   consultancy juniors, IR teams, BBVA's research desk, academics, rating
   analysts. Recurring manual effort on a fixed calendar is the clearest buy
   signal there is.

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
   per-bank regulation impact — and both recur across multiple actor profiles.
   That is the strongest argument yet for starting narrative extraction.
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
