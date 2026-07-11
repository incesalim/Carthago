# Per-bank advertised lending & deposit rates — source study + lane

**Date:** 2026-07-12
**Status:** ✅ SHIPPED (data spine: scraper + `bank_advertised_rates` + weekly cron). UI deferred.

## The question

"At what rate is each bank lending credit / paying deposits?"

## The three tiers (and which we had)

| Tier | Meaning | Granularity | Where it lives |
|---|---|---|---|
| **Realized (effective)** | What each bank *actually earned/paid* last quarter | **per-bank** | ✅ already built — `heatmap.ts` margin engine: `loan_yield` = TTM interest-on-loans (P&L `1.1`) ÷ avg gross loans (BS asset `2.1`); `deposit_cost` = TTM interest-on-deposits (P&L `2.1`) ÷ avg deposits (BS liab `I.`). Surfaced on `/cross-bank` + `/banks/[ticker]` |
| **Advertised (sector)** | Posted new-business rates, sector average | sector only | ✅ already built — `evds_series`: `TP.KTFTUK` (consumer), `TP.KTF17` (commercial), `TP.KTF12` (housing), `TP.TRY.MT06` (TL deposit) |
| **Advertised (per-bank)** | What each bank offers **new customers right now** | **per-bank** | ❌ was MISSING → **this lane** |

The gap mattered: **no official source publishes per-bank advertised rates.** TCMB/EVDS
and the BDDK bulletin are sector/bank-type only. So the third tier has to come from
public rate-comparison sites.

## Source evaluation (verified 2026-07-11/12)

| Source | Loans | Deposits | Render | robots.txt | Verdict |
|---|---|---|---|---|---|
| **doviz.com** | `/kredi/{ihtiyac,konut,tasit}-kredisi` → single server-rendered `<table>`: Banka · Kredi Adı · Faiz Oranı · min/max vade | editorial articles only (no tool table) | server HTML | **permissive** — blocks only `/api/`, `/user-api/`, widgets | ✅ **chosen for loans** |
| **hangikredi** | server-rendered, but `/kredi/` is **Disallow**ed | `/yatirim-araclari/mevduat-faiz-oranlari` | server HTML + `__NEXT_DATA__` | `/kredi/` disallowed; `/yatirim-araclari/` partial | ✅ **chosen for deposits only** — we never touch its `/kredi/` |
| hesapkurdu | — | client-rendered cards (JS) | dynamic | — | ✗ needs a browser |
| individual bank sites | first-party | first-party | varies | clean | ✗ ~37 bespoke, brittle scrapers |

### Key parsing finding
HangiKredi's deposit page **server-renders only the first ~8 banks** (alphabetical, A–G;
the rest lazy-load). Scraping the visible `<table>` would have silently captured a third
of the market. The **full** list is embedded in the page's `__NEXT_DATA__` JSON at
`props.pageProps.deposit.interestRateTable.interestRates` — 40 entries, each with
`bankName` / `minimumRate` / `maximumRate` / maturity + amount bands. We parse that
instead → 23 TL banks (the other ~17 entries are FX/gold currency variants, skipped).

## What the data looks like

- **Loans** (doviz): a **POINT** rate per bank per product, quoted **MONTHLY** (TR convention)
  — e.g. Halkbank "Hızlı Kredi" 5.06%/mo, 1–12 months. 35 rows across consumer/mortgage/vehicle.
- **Deposits** (hangikredi): a min–max **BAND** per bank, quoted **ANNUAL** — e.g. Akbank
  2–42%, 1–400 days, ₺1k–₺10m. The aggregator publishes the band, not a point rate.
- `rate_basis` (`monthly` | `annual`) records which, so the web layer never guesses.
- Each run stamps `snapshot_date`; **the sources only ever expose "today"**, so history
  builds forward and rows are never deleted.

## Gotcha that nearly shipped a bug

Migration **0022** (2026-07-11) expanded the `banks` dimension 31 → **37**, licensing
three former sub-brands as banks in their own right. The first pass mapped them to their
ex-parents, which would have silently mis-attributed three banks' rates:

| Aggregator name | Correct ticker | Wrong (ex-parent) |
|---|---|---|
| Enpara | `ENPARA` | ~~QNBFB~~ |
| Ziraat Dinamik | `ZIRAATD` | ~~ZIRAAT~~ |
| Hayat Finans | `HAYATK` | ~~"not in universe"~~ |

Genuine digital sub-brands (no separate licence) *do* map to the parent: `CEPTETEB`→TEB,
`ON Dijital`→ODEA, `N Kolay`→AKTIF. Locked down by
`tests/test_rates_scraper.py::test_new_entrant_banks_are_not_their_former_parent`.

Resolution reuses `src/news/bank_tagger` (the Turkish alias matcher) + a lane-local
`EXTRA_ALIASES` for names `bank_aliases.json` doesn't carry. **Note:** `bank_aliases.json`
still only lists the original 31 — the *news* lane therefore can't tag the 6 new entrants.
Out of scope here, but worth a follow-up.

Current resolution: **55/58 rows → ticker**; the 2 unresolved (`getirfinans`,
`Türk Ticaret Bankası`) are genuinely outside the audited universe and stay `bank_ticker = NULL`
with `raw_bank_name` preserved.

## ToS / politeness posture

These are affiliate comparison aggregators, not open data. We:
- respect each `robots.txt` (never touch hangikredi's disallowed `/kredi/`),
- fetch **4 pages once a week** with a real UA and a 1s pause between requests,
- store `source` + `source_url` on every row (attribution),
- keep the parsers behind a source adapter so a layout change or a takedown swaps cleanly.

**Risk to watch:** these hosts may block the GitHub Actions IP (as VAKBN/ZIRAATK/EXIM/ANADOLU
do for the faaliyet lane). Verify the first scheduled run; if blocked, seed from a local IP.

## Deferred

- **UI**: the natural payoff is a 3-tier per-bank panel — *advertised (new)* vs *EVDS sector
  benchmark (new)* vs *P&L-derived realized*. Advertised and EVDS share the same
  posted/new-business basis, so that comparison is apples-to-apples; the realized rate is a
  different basis and should be labelled as such. Wire once ≥2 weekly snapshots prove the
  source stable.
- FC (USD/EUR) advertised rates; participation profit-share split; historical backfill
  (impossible — the sources expose only today).
