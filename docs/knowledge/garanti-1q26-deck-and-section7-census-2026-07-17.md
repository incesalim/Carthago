# Garanti 1Q26 deck + the §7 census that killed my own recommendation — 2026-07-17

**Status: ANALYSIS ONLY — nothing built, nothing changed.** Companion to
[akbank-1q26-deck-reproducibility-2026-07-17.md](akbank-1q26-deck-reproducibility-2026-07-17.md).
Sources: [1Q26 BRSA Consolidated Earnings Presentation](https://www.garantibbvainvestorrelations.com/en/images/pdf/1Q26_BRSA_Consolidated_Earnings_Presentation.pdf)
(29pp) + the 31 March 2026 Consolidated Financial Report (141pp), against
`data/bank_audit.db` (2026-07-17).

## Headline

**Garanti reproduces better than Akbank — and it publishes the swap cost we said was
unobtainable.** Garanti's deck is a real text layer (28.8k chars vs Akbank's 12k of
fragments; the annex pages carry **zero images**). Its appendix P&L prints
`(-) Swap Cost -11,432` outright.

And the fleet census I recommended in the Akbank doc **destroyed that doc's own
"best follow-up"**. See below. Census-before-build earned its keep.

## Garanti ties exactly, same as Akbank

| Deck | Our row | |
|---|---|---|
| Net income 33,615 | `profit_loss` XXV. = 33,615,247 | exact |
| CAR 16.2 | `capital` cons = 16.20 | exact |
| CET-1 12.0 | `capital` cons = 11.97 | exact |
| Net fees 42,860 | `profit_loss` IV. = 42,859,908 | exact |
| HR opex 19,384 | `profit_loss` XI. = 19,384,028 | exact |
| Non-HR opex 34,892 | `profit_loss` XII. = 34,892,066 | exact |
| Tax 14,100 | `profit_loss` XVIII. = 14,100,339 | exact |
| Stage 1 / 2 / 3 = 2,465 / 308 / 92bn | `stages` cons = 2,465,229,674 / 308,285,722 / 92,363,869 | exact |
| Stage 2 prior "278bn" | `stages` prior = 278,477,644 | exact |

Unlike AKBNK 2026Q1, **GARAN's rows carry `item_name`** (English template: "NET
PROFIT/LOSS (XIX+XXIV)", "Equity holders of the bank"). The empty-label defect is
AKBNK-specific, not fleet-wide.

## The swap cost: same gap, opposite disclosure

Garanti's appendix P&L (deck p26) hands over the plug Akbank makes you derive:

```
our  P&L III. (NII)         = 71,431,416      deck: 65,437 + 5,995 = 71,432  ✓
        − deck swap cost      11,432          deck "NII incl. swap costs" = 59,999  ✓
```

Our NII minus Garanti's published swap cost lands on the deck's figure **exactly**.
That is the cleanest possible proof of the Akbank finding: **swap cost is the one and
only missing input** — everything else in the margin build is already ours.

Both banks confirm the structural rule: **swap cost is never in the BRSA filing, always
in the IR deck.** Garanti's filing has no swap-cost line either (its own guidance calls
for "NIM incl. swap cost ~75bps expansion" while disclosing no swap cost). What differs
is only the *deck's* machine-readability.

### This corrects the Akbank doc

That doc concluded the only route to swap cost is "per-bank IR decks, i.e. image-only
PowerPoint … not worth it." **Half wrong.** Deck extractability is per-bank:

| Bank | Deck text layer | Swap cost |
|---|---|---|
| GARAN | **yes** — annex pages have 0 images, 28.8k chars | printed, `-11,432`, parseable today |
| AKBNK | **no** — 83–137 images/page, 0 numbers in text | printed on p26, but only as pixels |

So swap-adj NIM is reachable for Garanti-like filers and not for Akbank-like ones. Still
not a lane — per-bank layouts with no stable anchors is the `faaliyet_franchise` trap
([[project_franchise_extractor_broken]]) — but "impossible" was too strong.

## The §7 census — and how it killed the guidance lane

The Akbank doc called a per-bank guidance + self-reported-ratio lane the "best follow-up
available", flagged as AKBNK-only-verified. I ran the census over **all 35 banks with a
2026Q1 URL**; 26 fetched cleanly (9 failed: control chars in stored URLs — ICBCT/ISCTR/
TFKB/ZIRAATK — plus timeouts/resets).

**First pass looked great: guidance 12/26. It was almost entirely false positives.**
`ileriye yönelik beklentiler` is **IFRS-9 ECL methodology boilerplate** ("forward-looking
expectations in the ECL calculation") — AKTIF, ZIRAAT, EMLAK, ODEA, FIBA, DUNYAK,
ZIRAATD all matched on it. Others (BURGAN p103, ING p89, VAKIFK p88) hit a *prose* macro
commentary section, not a table. Likewise `Sayılarla` matched KLNMA's "Sayılarla sınırlı
olmamak üzere" (= "including but not limited to"), and QNBFB's "number of customers" was
segment-note prose.

**Verified reality:**

| Disclosure | Banks | Note |
|---|---|---|
| **Guidance table** (9 numeric lines) | **AKBNK only** | 1 of 26, not 12 |
| **Ratio table** | **AKBNK, GARAN, DUNYAK** | 3 different headings/shapes — "Başlıca Finansal Oranlar" (TR) vs "Selected Financial Ratios" (EN); different ratio sets |
| **Franchise table** | **GARAN only** | KLNMA/QNBFB were boilerplate |

**Verdict: §7 "Diğer Açıklamalar" is a per-bank grab-bag, not a schema.** Each filer puts
something different there. A "guidance-vs-actual across 38 banks" lane **does not exist**
— it would be a one-bank lane. Recommendation withdrawn.

The lesson is the regex itself: my census counted ECL boilerplate as guidance and would
have justified building a lane on a 12/26 hit rate that was really 1/26. Same failure
mode as the validators in [[feedback_verify_validators_against_data]] — a marker that
matches is not a marker that means.

## Two real defects found (worth more than either lane)

Garanti's report p141 prints **"Garanti BBVA with Numbers"**: Branch Network **795**,
Employees **23,376**, ATM 6,537, POS 886,943, Customers 30,610,905, Digital Customers
18,234,320, Credit Card Customers 13,562,178.

1. **`PROJECT_STATE.md:32` is wrong.** It states ATM/POS/merchant/customer/card counts
   are what "**the stats audit reports don't carry**" — the stated reason the
   `faaliyet_franchise` lane reads annual reports instead. Garanti's *quarterly* report
   carries all of them, in a clean table, in text. For the one bank checked, the premise
   of a lane that is ~75% wrong is false. Not a rebuild trigger by itself (n=1), but the
   documented reason should not stand unqualified.
2. **`bank_audit_profile` disagrees with the filer, live.** We store GARAN 2026Q1
   `branches_total` = **794** (789 domestic + 5 foreign) and `personnel` = **NULL**. The
   same report prints **795** branches and **23,376** employees. So GARAN is counted in
   PROJECT_STATE's "~11 per-bank-phrasing long tail" that supposedly doesn't disclose
   personnel — **it does**, in an English §7 table our regex never reads. The branch
   count is off by one against the bank's own statement.

Neither is urgent (profile is a size indicator, not core financials), but both are
concrete, sourced, and currently mis-documented.

## Where Garanti's deck is not reproducible

Same shape as Akbank, with one addition:

- **Romania subsidiary sale** — 1Q26 reclassifies Romania into discontinued operations
  and **restates 1Q25**. Our stored statutory rows are as-filed per period, so a
  deck-vs-our-history comparison of 1Q25 will not match the deck's restated 1Q25. This
  is a genuine trap for any time series. (We hold the discontinued rows: XXII. 483,214 /
  XXIII. 83,339 / XXIV. 399,875.)
- Not ours: NIM/spread series (swap cost), TL loan product mix (p8), Stage-2 breakdown
  by SICR/restructured/watchlist/past-due (p9), external debt breakdown (p12), digital
  and NPS stats (p14), market shares on the bank-only weekly private-commercial basis.
- **Ours already**: summary BS (p25), summary P&L (p26) bar the swap split, key ratios
  (p27) — and `Net CoR` (p28) is checkable against `stages`/`credit_quality`.

## Recommendation

**Unchanged from the Akbank doc's item 1, now with the opposite conclusion: build
nothing.** The census removed the only candidate that looked fleet-wide. The two
defects above are the real output of this pass, and both are documentation/coverage
fixes, not new lanes.
