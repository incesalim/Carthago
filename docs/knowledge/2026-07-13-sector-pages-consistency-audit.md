# Sector-page consistency audit — 2026-07-13

**Status: FINDINGS, NOT ACTED ON.** Every number below was verified against remote
D1 on 2026-07-13. Scope: the seven pages in the Nav "Sector" group — `/`, `/credit`,
`/deposits`, `/liquidity`, `/asset-quality`, `/capital`, `/profitability` (~7,700
lines) — plus the libs behind them. Yardstick: [`web/DESIGN.md`](../../web/DESIGN.md),
which already legislates most of what is broken here.

## Verdict

**The shell is consistent. The numbers are not.**

All seven pages carry the same skeleton — `DeskHeader → Vitals → Movers/Transmission
→ Flags → Depth → Colophon`, a deterministic `insights.ts` Read behind a `det_hash`
gate, computed flags that print their own rule. The Desk redesign held.

What has not held is **basis discipline**. The same quantity is computed from
different sources, over different windows, with different formulas, on pages a
reader crosses in one click — and in one case the *same page* answers its own
question twice, both ways, on one screen. DESIGN.md anticipated exactly this
("Compare like with like — the same BASIS, not just the same cadence"; "One metric,
one number"). The rules are right; the code drifted from them.

---

## Tier 1 — live contradictions a reader can see today

### 1. `/capital` contradicts itself on screen, right now

The hybrid stack is `AT1 + Tier-2 = 4.23pp` of RWA (audited 2026Q1). The page tests
"are the hybrids bigger than the buffer?" **twice, against two different buffers**:

| Surface | Buffer used | Value | Verdict rendered |
|---|---|---|---|
| `Flags` → `hybrid-buffer` (`capital/page.tsx:308`) | **audited** CAR − 12 | 4.06pp | 4.23 > 4.06 → **flag FIRES**: "Hybrid-funded buffer — strip them and the ratio is below the 12% it must meet" |
| `StackedArea` title (`capital/page.tsx:691`) | **bulletin** CAR − 12 | 4.34pp | 4.23 < 4.34 → benign title: "Capital composition — CET1, AT1 and Tier-2" |

Audited CAR = 16.06%, bulletin CAR = 16.34% (May 2026) — a 0.28pp basis gap, and
`hybrids` currently sits *inside* it. So the brief raises a red flag and the chart
below it, testing the same claim, quietly says everything is fine.

The page's own comment at `capital/page.tsx:182-185` explains why the audited buffer
must be used ("silently flatters or damns the answer"), and DESIGN.md quotes this
exact case. Line 691 is the one place that didn't get the memo.

**Fix:** `capital/page.tsx:691` — `buffer` → `auditBuffer`. One word.

### 2. "Loan-to-deposit" is three numbers under one name

| Page | Definition | Value (latest) | Flag threshold |
|---|---|---|---|
| `/deposits` | BDDK **published** ratio, monthly, **all-currency**, sector (`financial_ratios` t15) | **91.4%** | `> 100%` → clear |
| `/liquidity` | **computed**, weekly, **TL-only**, private banks (`weekly_series`) | **96.7%** | `> 95%` → **fires** |
| `/liquidity` | same, public banks | **80.6%** | — |

A reader on `/deposits` sees a comfortable 91% with no flag; one click later
`/liquidity` flags 97% as stretched. Both metrics are legitimate and the pages even
hand off to each other in prose — but neither *label* names its basis, so the two
read as one metric that disagrees with itself. (`/deposits`' LDR vital links to
`/credit`; its Takeaway bullet links to `/liquidity`.)

**Fix:** name the basis in the label ("Loan/deposit, all-currency, sector" vs "TL
loan/deposit, private"), and state the other figure once in each page's note.

### 3. "Real" is computed two different ways, and `/` uses the forbidden one

`series.ts:48` is explicit: *"Deflate a growth series by CPI (exact Fisher form, not
the g−π shortcut)."* `/credit`, `/deposits` and `/asset-quality` obey it. `/`
(Overview) does not — it subtracts, **and from two different CPI bases**:

| Overview line | Formula | CPI base | Prints | Fisher would print |
|---|---|---|---|---|
| Credit, real (`page.tsx:297`) | `loansYoY − cpiYoY` | spot y/y (32.6%) | **+4.9pp** | **+3.7%** |
| ROE, real (`page.tsx:227`) | `roe − cpiAvg12m` | 12m-avg (32.1%) | **−7.4pp** | **−5.6%** |

1.2–1.8pp of daylight on two of the site's most-quoted figures, on the landing page.
The shortcut also makes `/`'s "credit in real terms" disagree with `/credit`'s, which
is Fisher-deflated *and* FX-adjusted.

**Fix:** route both through `deflate()`; pick one CPI base per concept and say which.

---

## Tier 2 — silent, basis-level

### 4. The peer exclusion guards two aggregators out of three

`PEER_EXCLUDED_TICKERS = {TAKAS}` (`bank_names.ts:138`) keeps Takasbank — a CCP with
**zero deposits** and ~94% of its balance sheet in custodied cash — out of the
heatmap, the league and the HHI. It is enforced at the choke points in `heatmap.ts`
and `market-share.ts`.

**`audit-ratios.ts` and `credit-risk.ts` never import it.** Takasbank is therefore
inside every sector aggregate they feed:

| Aggregator | Feeds | TAKAS rows in D1 |
|---|---|---|
| `audit-ratios.sectorCapitalRatios` | `/capital` CET1 / Tier-1 / CAR vitals | 32 |
| `audit-ratios.sectorLiquidityRatios` | `/liquidity` LCR / NSFR / leverage vitals | 32 |
| `credit-risk.sectorStageShares` | `/asset-quality` Stage-2/3 shares | 29 |

Effect on capital today is small (sector CAR 16.06% → **16.03%** ex-TAKAS; CET1
11.83% → **11.79%**), but the *liquidity* aggregate is asset-weighted, and a clearing
house's LCR/NSFR/leverage is exactly the observation that does not belong in a
weighted average of banks. The rule exists; two of its three call sites don't apply it.

**Fix:** filter `isPeerExcluded()` inside `audit-ratios.ts` and `credit-risk.ts` — or
better, at the SQL, so a fourth aggregator can't repeat this.

### 5. `/asset-quality` — the vital's sparkline draws the wrong series

`asset-quality/page.tsx:420-424`, Vital **"Cover on the problem book"**:

```tsx
value={ladder.problemCov.toFixed(1)}                          // coverage %, ~70s
series={stage2.map((r) => ({ period: r.period, value: r.value }))}  // Stage-2 SHARE, ~10%
```

The headline figure is a coverage ratio; the sparkline under it is the Stage-2 share
of gross loans — a different quantity on a different axis. The number and its mark do
not measure the same thing.

### 6. Latent: Stage-2/Stage-3 paired by array index

`asset-quality/page.tsx:403-406` builds the "problem loans" spark with
`stage2.map((r, i) => r.value + stage3[i]?.value)` — index pairing. But
`credit-risk.ts:66-67` pushes STAGE2 and STAGE3 **conditionally per period**, so the
two arrays are not guaranteed parallel. Verified: **no period currently has one stage
without the other**, so this is not firing. It is a landmine, not a live error — and
every other series in this codebase pairs by date on principle (`series.ts`,
`weekly-growth.ts`, which exists *because* row offsets silently stretched a window).

---

## Tier 3 — coherence and hygiene

7. **The evidence layer is half-converted.** `/credit` and `/asset-quality` still wrap
   Depth content in the legacy `ui/Section` and use `Attribution`; the other five use
   `Levels` / `ChartFoot` / `Standings`. DESIGN.md: "the evidence layer speaks the
   brief's language."
8. **`Ahead` is hardcoded calendar strings** ("JUL 23", "AUG ~12") on five pages, sitting
   under a header that claims *"every figure computed from source series."* It will go
   stale silently — an automation-honesty violation by the site's own rule 6.
9. **Chart titles are computed on unfiltered arrays** while the charts they title are
   range-filtered client-side. Select "1Y" and a title still describes weeks that are
   no longer on the chart (worst on `/liquidity`'s ReserveBuffer, "N of the last M weeks").
10. **Formatters re-declared per page**, against `web/CLAUDE.md`'s explicit "don't
    re-declare a local `nf`": `fmtPct` exists on every page — **2dp on `/`, 1dp on
    `/credit`** — plus `fmtTrn`, `weekLabel` (different `withYear` defaults),
    `quarterLabel` (×2). `CAR_MIN = 12` is hardcoded in four files.
11. **The same 52w delta, two engines.** `/deposits` takes the FX-share delta with
    `valAgo(fxShare, 52)` (row offset); `/liquidity` takes it with `valYearAgoByDate`
    (date pairing). Both then print a flag whose stated rule is the same
    `Δ52w(fx_share) > +1pp`.
12. **Cadence hand-off is stated but not enforced.** `/` prints loan growth from the
    *monthly* bulletin (**37.5%**, May); `/credit` prints it from the *weekly* bulletin
    (**36.6%**, W/E 3 Jul). Both are right, the record lines do name the cadence, and
    the 0.9pp gap is explicable — but nothing on either page tells the reader that.

### `/profitability` is mid-flight (another session, uncommitted)

The working tree adds `lib/profitability.ts`, `EngineBars`, `ProfitBridge` and the P&L
bridge. Reviewed as-is, not touched. Worth passing on: **two OPEX definitions live on
that one page** (BDDK's published `İşletme Giderleri` in the vital vs `income_statement`
item 45 in the bridge and cost/income — both labelled "operating costs"); `engine()`
silently drops loss-making months (`profit > 0` guard), so the series can have
invisible holes; and `roeIfPaid` applies a cost computed on *our* 13-point average
equity against BDDK's `Ortalama Özkaynaklar`-based ROE. The bridge's reconcile-or-withhold
gate is exactly right and should be the template elsewhere.

### What is genuinely consistent (not damning with faint praise)

- The Desk skeleton, on all seven pages, with the two-layer contract intact.
- `withLlmHeadline` on all eight tabs, gated by `det_hash` + a no-invented-numbers
  check — the LLM cannot put a figure on any page. That design is holding.
- Flags print their rule whether or not they fire, on every page.
- `/capital` and `/asset-quality` *document* the bulletin-vs-audited seam. They each
  then break it in exactly one place (findings 1 and 5) — the intent is there.
- `/sector` and `/sector/ratios` are clean redirects to `/`, not orphans.

---

## Suggested order of work

1. `capital/page.tsx:691` — `buffer` → `auditBuffer`. One word, kills a live on-screen
   contradiction.
2. `asset-quality/page.tsx:424` — point the sparkline at the coverage series.
3. Peer exclusion into `audit-ratios.ts` + `credit-risk.ts`.
4. Overview onto `deflate()` (Fisher) and one CPI base per concept.
5. Name the basis on both loan-to-deposit surfaces.
6. Then the hygiene tier — one shared `fmtPct`/`fmtTrn`, `CAR_MIN` from one place,
   date-pairing everywhere, and either compute `Ahead` or stop claiming every figure
   is computed.
