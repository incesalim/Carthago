/**
 * Economy tab — the macro backdrop the banks operate in, as a Desk brief over
 * its evidence (web/DESIGN.md).
 *
 * The page used to be a header, a vitals band and a grid of one-series line
 * charts: no computed read, no flags, no schedule, and no statement anywhere of
 * what any of it does to a bank. Everything the sector tabs had — <Takeaway>,
 * <Movers>, <Transmission>, <Flags>, <Ahead> — was missing here, on the one tab
 * whose entire job is to explain the conditions the rest of the site measures.
 *
 * Three things it now carries that the data always supported and nobody wired:
 *   the reserve buffer   gross → net → net-excl-swaps (lib/reserves.ts, shared
 *                        with /liquidity so the two cannot print rival numbers)
 *   the transmission     policy → deposit → loan pricing, weekly bank rates that
 *                        sat in D1 unread by this page
 *   the scorecard        the third-party baseline, scored against what actually
 *                        happened, instead of a static forecast table nobody
 *                        came back to check
 *
 * Out of scope (no data source here): CDS spreads, OIS pricing and sovereign
 * yield curves (Bloomberg), and the GDP nowcast / FCI composite (proprietary).
 */
import type { Metadata } from "next";
import Link from "next/link";
import {
  getEconomyData,
  monthlyAverage,
  scoreBaseline,
  BBVA_BASELINE,
  type Point,
} from "@/app/lib/economy";
import { getPortfolioFlowsData } from "@/app/lib/portfolio-flows";
import {
  Section,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  TableCellNum,
} from "@/app/components/ui";
import {
  Ahead,
  ChartRow,
  Colophon,
  Depth,
  DeskHeader,
  Flags,
  Levels,
  Movers,
  SecHead,
  Transmission,
  Vital,
  Vitals,
  type Flag,
  type MoverRow,
  type TransmissionItem,
} from "@/app/components/desk";
import { lastVal, monthLabel, signedPp, streak, valAgo, windowExtremes, type Pt } from "@/app/lib/desk";
import { VERBS, direction, signed, signedPct, toneClass } from "@/app/lib/prose";
import { seriesFinding } from "@/app/lib/chart-findings";
import { economyInsights } from "@/app/lib/insights";
import { aheadSlots } from "@/app/lib/ahead-data";
import { GlobalRangeSelector } from "@/app/components/range-context";
import { fmtQuarter } from "@/app/lib/chart-format";
import Takeaway from "@/app/components/Takeaway";
import TimeSeriesChart from "@/app/components/TimeSeriesChart";
import BopFlowChart, { type BarSeries } from "@/app/components/BopFlowChart";
import ReserveBuffer from "@/app/components/ReserveBuffer";
import { ChartCard } from "@/app/components/ui/chart-card";

const MAROON = { light: "#9c1f2f", dark: "#d65a5a" };
const NAVY = { light: "#1f4068", dark: "#6f9fe0" };

/** EVDS rows ({period_date}) → the desk helpers' Pt shape ({period}). */
const toPts = (s: { period_date: string; value: number }[]): Pt[] =>
  s.map((r) => ({ period: r.period_date, value: r.value }));

/** TimeSeriesChart's `series` map → ChartRow's long-form rows. */
const tsRows = (s: Record<string, { period_date: string; value: number | null }[]>) =>
  Object.entries(s).flatMap(([k, points]) =>
    points.map((p) => ({ period: p.period_date, bank_type_code: k, value: p.value })),
  );

/**
 * Value of a daily series one calendar year before its last point — the last
 * observation on or before the same date a year earlier (no `new Date()`:
 * decrement the year in the ISO string and scan).
 */
function valYearAgo(s: Point[]): number | null {
  const last = s.at(-1);
  if (!last) return null;
  const target = `${Number(last.period_date.slice(0, 4)) - 1}${last.period_date.slice(4)}`;
  let hit: number | null = null;
  for (const p of s) {
    if (p.period_date <= target) hit = p.value;
    else break;
  }
  return hit;
}

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkish Economy — Macro Dashboard",
  description: "Türkiye's macro backdrop for the banking sector — growth, inflation, policy transmission, reserves, the balance of payments and the budget, from official data.",
  alternates: { canonical: "/economy" },
};

function Grid({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">{children}</div>;
}

const pct1 = (v: number | null, d = 1) => (v == null ? "—" : `${v.toFixed(d)}%`);
const bn = (v: number | null, d = 1) => (v == null ? "—" : `$${v.toFixed(d)}bn`);

export default async function EconomyPage() {
  const [d, flows, ahead] = await Promise.all([
    getEconomyData(),
    getPortfolioFlowsData(),
    aheadSlots(),
  ]);

  // ---- the brief's computed vitals ------------------------------------------
  // Every cell below is derived from a series this page already fetches.
  const cpi = toPts(d.cpiYoY);
  const gdp = toPts(d.gdpGrowth);
  const fund = toPts(d.fundingMonthly);
  const usd = toPts(d.usdtry);
  const unemp = toPts(d.unemployment);
  const part = toPts(d.participation);
  const ca = toPts(d.ca12m);
  const caGdp = toPts(d.caPctGdp);
  const real = toPts(d.realRate);
  const realDep = toPts(d.realDepositRate);
  const spread = toPts(d.loanDepositSpread);
  const reer = toPts(d.reer);
  const ip = toPts(d.ipGrowth);
  const budget = toPts(d.budgetPctGdp);
  // USD/TRY is DAILY; a 12-month Δ off row offsets would be a 12-trading-day Δ,
  // so the monthly average is what the reads and the Movers column use.
  const usdMonthly = toPts(monthlyAverage(d.usdtry));

  const cpiNow = lastVal(cpi);
  const cpiAgo = valAgo(cpi, 12);
  const cpiD12 = cpiNow != null && cpiAgo != null ? cpiNow - cpiAgo : null;
  const cpiFall = streak(cpi, "down");

  const gdpNow = lastVal(gdp);
  const gdpPrev = valAgo(gdp, 1);
  const gdpD = gdpNow != null && gdpPrev != null ? gdpNow - gdpPrev : null;
  const gdpQuarter = d.gdpGrowth.at(-1)?.period_date;

  const fundNow = lastVal(fund);
  const realNow = lastVal(real);
  const realDepNow = lastVal(realDep);
  const exp12Now = lastVal(toPts(d.exp12m));
  const hhExpNow = lastVal(toPts(d.hhExp12m));
  const spreadNow = lastVal(spread);
  const depRateNow = lastVal(toPts(d.depositRate));
  const loanRateNow = lastVal(toPts(d.loanCommercial));

  const usdNow = lastVal(usd);
  const usdYearAgo = valYearAgo(d.usdtry);
  const usdYoY =
    usdNow != null && usdYearAgo != null && usdYearAgo > 0
      ? (usdNow / usdYearAgo - 1) * 100
      : null;

  const unempNow = lastVal(unemp);
  const unempAgo = valAgo(unemp, 12);
  const unempD12 = unempNow != null && unempAgo != null ? unempNow - unempAgo : null;
  const partNow = lastVal(part);

  const caNow = lastVal(ca);
  const caGdpNow = lastVal(caGdp);
  const caXgeNow = lastVal(toPts(d.caExGoldEnergy12m));
  const primNow = lastVal(toPts(d.primaryPctGdp));

  // The reserve buffer — one derivation, shared with /liquidity.
  const res = d.reserves.latest;
  const grossNow = res?.gross ?? null;
  const netNow = res?.net ?? null;
  const ownNow = res?.own ?? null;
  const hhFxNow = lastVal(toPts(d.householdFx));
  const hhGoldNow = lastVal(toPts(d.householdGold));

  // ---- "The Read" — computed from the same series the charts show -----------
  const read = economyInsights({
    cpi,
    exp12m: toPts(d.exp12m),
    funding: fund,
    realRate: real,
    gdp,
    unemployment: unemp,
    caPctGdp: caGdp,
    usdtry: usdMonthly,
    budgetPctGdp: budget,
    importCover: d.importCover,
    ownReserves: ownNow,
  });

  // ---- movers: MONTHLY series only -----------------------------------------
  // GDP is quarterly and USD/TRY is daily, so neither belongs in this Δ column
  // (DESIGN.md: never mix cadences in one Movers table). Every row states its
  // own record month in the note, because the monthly series publish on
  // different lags — CPI lands weeks before the balance of payments.
  const mover = (
    label: string,
    s: Pt[],
    good: MoverRow["good"],
    fmt?: (v: number) => string,
    deltaUnit = "pp",
  ): MoverRow => ({
    label,
    note: monthLabel(s.at(-1)?.period, true),
    prev: valAgo(s, 1),
    curr: lastVal(s),
    good,
    fmt,
    deltaDecimals: 1,
    deltaUnit,
  });

  const movers: MoverRow[] = [
    mover("CPI, y/y", cpi, "down", (v) => `${v.toFixed(1)}%`),
    mover("CBRT cost of funding", fund, "neutral", (v) => `${v.toFixed(1)}%`),
    mover("Ex-ante real funding rate", real, "neutral", (v) => `${v.toFixed(1)}%`),
    mover("TL deposit rate", toPts(d.depositRate), "neutral", (v) => `${v.toFixed(1)}%`),
    mover("Commercial loan rate", toPts(d.loanCommercial), "neutral", (v) => `${v.toFixed(1)}%`),
    mover("Industrial production, y/y", ip, "up", (v) => `${v.toFixed(1)}%`),
    mover("Unemployment, SA", unemp, "down", (v) => `${v.toFixed(1)}%`),
    mover("REER (2003=100)", reer, "neutral", (v) => v.toFixed(1), "pts"),
    mover("Current account, 12m", ca, "up", (v) => `$${v.toFixed(1)}bn`, "bn"),
    mover("General budget, 12m", budget, "up", (v) => `${v.toFixed(1)}%`),
  ];

  // ---- transmission: the backdrop → the banks -------------------------------
  // Every figure is computed; every EFFECT names a mechanism that holds in both
  // directions, and where the sentence turns on a sign it branches on the
  // computed sign rather than assuming one.
  const transmission: TransmissionItem[] = [
    {
      k: "CBRT cost of funding",
      v: pct1(fundNow),
      effect: (
        <>
          The marginal price of TL for the system. It sets the floor under deposit
          pricing and, with a lag, under loan pricing — the two legs of{" "}
          <Link href="/profitability" className="font-semibold text-primary">
            the margin
          </Link>
          .
        </>
      ),
    },
    {
      k: "Ex-ante real rate",
      v: realNow != null ? signedPct(realNow) : "—",
      effect:
        realNow == null ? (
          "The funding cost deflated by the 12-month-ahead expectation."
        ) : realNow >= 0 ? (
          <>
            Funding costs more than expected inflation, so lira carries a positive
            expected real return — the condition under which deposits compete with FX
            and gold on their own merits.
          </>
        ) : (
          <>
            Funding costs less than expected inflation, so a lira deposit is expected
            to lose purchasing power — the standing incentive behind{" "}
            <Link href="/deposits" className="font-semibold text-primary">
              dollarization
            </Link>
            .
          </>
        ),
    },
    {
      k: "Loan − deposit spread",
      v: spreadNow != null ? `${spreadNow.toFixed(1)}pp` : "—",
      effect: (
        <>
          Commercial loan pricing at {pct1(loanRateNow)} over TL deposits at{" "}
          {pct1(depRateNow)}. This gap is the sector&rsquo;s gross margin before
          funding mix, fees and the cost of risk —{" "}
          <Link href="/rates" className="font-semibold text-primary">
            /rates
          </Link>{" "}
          carries the full pricing curve.
        </>
      ),
    },
    {
      k: "Real deposit rate",
      v: realDepNow != null ? signedPct(realDepNow) : "—",
      effect:
        realDepNow == null ? (
          "The TL deposit rate deflated by the 12-month-ahead expectation."
        ) : (
          <>
            What a saver expects to earn after inflation. It is{" "}
            {realDepNow >= 0 ? "above" : "below"} zero, so the expected real return on a
            lira deposit is {realDepNow >= 0 ? "a gain" : "a loss"} of{" "}
            {Math.abs(realDepNow).toFixed(1)}% — the number that competes with FX cash
            and gold in a household&rsquo;s decision.
          </>
        ),
    },
    {
      k: "CPI, y/y",
      v: pct1(cpiNow),
      effect: (
        <>
          Prices the nominal book: at this rate a balance sheet can grow in lira and
          shrink in real terms, which is why every nominal level on this site ships
          with a deflated twin. It also sets operating costs and CPI-linker income.
        </>
      ),
    },
    {
      k: "GDP growth, y/y",
      v: pct1(gdpNow),
      effect: (
        <>
          The demand side of the loan book — {gdpQuarter ? fmtQuarter(gdpQuarter) : "—"},
          quarterly, so it moves later than everything above it. Output is what
          eventually settles{" "}
          <Link href="/asset-quality" className="font-semibold text-primary">
            NPL formation
          </Link>
          .
        </>
      ),
    },
  ];

  // ---- flags: rules printed, whether or not they fire ------------------------
  const cpiAcc = streak(toPts(d.cpiMoM), "up");
  const flagList: Flag[] = [
    {
      code: "REAL_NEG",
      active: realNow != null && realNow < 0,
      rule: "ex_ante_real_funding_rate < 0",
      body: (
        <>
          <b className="font-semibold">Policy is accommodative in real terms.</b> Funding
          at {pct1(fundNow)} sits under the {pct1(exp12Now)} expected for the next twelve
          months, a real rate of {realNow != null ? signedPct(realNow) : "—"}.
        </>
      ),
      clear: (
        <>
          Ex-ante real funding rate {realNow != null ? signedPct(realNow) : "—"} — at or
          above zero against the {pct1(exp12Now)} expectation.
        </>
      ),
    },
    {
      code: "IMPORT_COVER",
      active: d.importCover != null && d.importCover < 3,
      rule: "gross_reserves / (imports_12m / 12) < 3 months",
      body: (
        <>
          <b className="font-semibold">Reserve cover is below the conventional floor.</b>{" "}
          Gross reserves of {bn(grossNow)} cover {d.importCover?.toFixed(1)} months of the
          goods import bill, under the three-month rule of thumb.
        </>
      ),
      clear: (
        <>
          Gross reserves cover {d.importCover != null ? d.importCover.toFixed(1) : "—"}{" "}
          months of imports — at or above the three-month rule of thumb.
        </>
      ),
    },
    {
      code: "OWN_FX_NEG",
      active: ownNow != null && ownNow < 0,
      rule: "net_reserves_excluding_swaps < 0",
      body: (
        <>
          <b className="font-semibold">The CBRT&rsquo;s own net FX is negative.</b> Net
          reserves of {bn(netNow)} rest on a swap book; excluding it leaves{" "}
          {bn(ownNow)} —{" "}
          <Link href="/liquidity" className="font-semibold text-primary">
            the buffer, decomposed
          </Link>
          .
        </>
      ),
      clear: (
        <>
          Net reserves excluding the swap book are {bn(ownNow)} — the CBRT&rsquo;s own FX
          is at or above zero.
        </>
      ),
    },
    {
      code: "CA_WIDE",
      active: caGdpNow != null && caGdpNow < -4,
      rule: "current_account_12m / gdp < −4%",
      body: (
        <>
          <b className="font-semibold">The external deficit is wide.</b> The twelve-month
          current account is {caGdpNow != null ? `${caGdpNow.toFixed(1)}%` : "—"} of GDP,
          which has to be financed every month it persists.
        </>
      ),
      clear: (
        <>
          The 12-month current account is{" "}
          {caGdpNow != null ? `${caGdpNow.toFixed(1)}%` : "—"} of GDP — inside the −4%
          line this rule tests.
        </>
      ),
    },
    {
      code: "CPI_MM_RUN",
      active: cpiAcc >= 3,
      rule: "consecutive_rise(cpi_m/m) ≥ 3",
      body: (
        <>
          <b className="font-semibold">
            The monthly print has risen {cpiAcc} months running.
          </b>{" "}
          The annual rate is built from these; a run of three sets the direction of the
          next few readings before any base effect.
        </>
      ),
      clear: <>The monthly CPI print has not risen three months running.</>,
    },
    {
      code: "BUDGET_WIDE",
      active: budget.length > 0 && lastVal(budget) != null && (lastVal(budget) as number) < -3,
      rule: "general_budget_12m / gdp < −3%",
      body: (
        <>
          <b className="font-semibold">The budget deficit is past the 3% reference.</b>{" "}
          The twelve-month general budget balance is {pct1(lastVal(budget))} of GDP, with
          the primary balance at {pct1(primNow)}.
        </>
      ),
      clear: (
        <>
          The 12-month general budget balance is {pct1(lastVal(budget))} of GDP — inside
          the 3% reference value.
        </>
      ),
    },
  ];

  // ---- the schedule ---------------------------------------------------------
  // The cadence rows are literals on purpose: "TÜİK publishes CPI on the 3rd" is
  // true every month, so it is not a claim that can go stale (lib/ahead.ts).
  const aheadItems = [
    { when: "3rd", what: <>TÜİK CPI &amp; Yİ-ÜFE — the month&rsquo;s price print</>, href: "/economy/inflation" },
    ...(ahead.mpc
      ? [{ when: ahead.mpc.when, what: <>CBRT rate decision — the funding cost above</>, href: "/rates" }]
      : []),
    ...(ahead["mpc-minutes"]
      ? [{ when: ahead["mpc-minutes"].when, what: <>MPC minutes — the reasoning behind the decision</> }]
      : []),
    ...(ahead["inflation-report"]
      ? [{ when: ahead["inflation-report"].when, what: <>CBRT Inflation Report — the forecast path</> }]
      : []),
    { when: "FRI", what: <>CBRT weekly — reserves, the analytical balance sheet, non-resident flows</> },
  ];

  // ---- the scored baseline ---------------------------------------------------
  const scored = scoreBaseline(d);
  const scoredCount = scored.filter((r) => r.realized != null).length;

  // ---- section reads --------------------------------------------------------
  const unExt = windowExtremes(unemp, 60);
  const unAtLow = unempNow != null && unExt != null && unempNow <= unExt.min + 0.2;
  const partAgo = valAgo(part, 12);
  const partMove = direction(
    partNow != null && partAgo != null ? partNow - partAgo : null,
    VERBS.trend,
    { flat: 0.3, sharp: 1.5 },
  );
  const caAgo = valAgo(ca, 12);
  const caMove = direction(
    caNow != null && caAgo != null ? caNow - caAgo : null,
    VERBS.move,
    { flat: 2, sharp: 10 },
  );

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title="Economy"
        record={
          <>
            Record <b className="font-normal text-foreground">{monthLabel(d.cpiYoY.at(-1)?.period_date)}</b>{" "}
            · monthly EVDS · GDP quarterly ({gdpQuarter ? fmtQuarter(gdpQuarter) : "—"}) · reserves weekly
          </>
        }
        right="every figure computed from source series"
      />

      {/* ── The vitals ─────────────────────────────────────────────────── */}
      <SecHead
        title="The vitals"
        meta="policy · prices · activity · lira · reserves · external"
        className="mb-2.5 mt-6"
      />
      <Levels
        items={[
          { k: "Nominal GDP, 4Q", v: lastVal(toPts(d.nominalGdp4q))?.toFixed(1) ?? "—", unit: "₺trn" },
          { k: "Gross reserves", v: grossNow?.toFixed(0) ?? "—", unit: "$bn" },
          { k: "Imports, 12m", v: lastVal(toPts(d.imports12m))?.toFixed(0) ?? "—", unit: "$bn" },
          { k: "Employed", v: lastVal(toPts(d.employedMn))?.toFixed(1) ?? "—", unit: "mn" },
        ]}
      />
      <Vitals>
        <Vital
          label="CBRT cost of funding"
          value={fundNow != null ? fundNow.toFixed(1) : "—"}
          unit="%"
          series={fund.slice(-13)}
          decimals={1}
          note={
            realNow != null && exp12Now != null ? (
              <>
                ≈{" "}
                <em className={`not-italic font-semibold ${realNow >= 0 ? "text-positive" : "text-negative"}`}>
                  {signed(realNow)}% ex-ante real
                </em>{" "}
                vs the {exp12Now.toFixed(1)}% 12m-ahead expectation
              </>
            ) : (
              "monthly average of the daily effective rate"
            )
          }
        />
        <Vital
          label="CPI, y/y"
          value={cpiNow != null ? cpiNow.toFixed(1) : "—"}
          unit="%"
          series={cpi.slice(-13)}
          decimals={1}
          note={
            <>
              {cpiD12 != null ? `${signedPp(cpiD12, 1)} over 12m` : "TÜİK headline"}
              {cpiFall >= 3 && <> · {cpiFall} straight monthly falls</>} ·{" "}
              <Link href="/economy/inflation" className="font-semibold text-primary">
                /inflation
              </Link>
            </>
          }
        />
        <Vital
          label="GDP growth, y/y"
          value={gdpNow != null ? gdpNow.toFixed(1) : "—"}
          unit="%"
          series={gdp.slice(-13)}
          decimals={1}
          note={
            <>
              {gdpQuarter ? fmtQuarter(gdpQuarter) : "—"}
              {gdpD != null && <> · {signedPp(gdpD, 1)} vs the prior quarter</>} ·{" "}
              <Link href="/economy/economic-growth" className="font-semibold text-primary">
                /growth
              </Link>
            </>
          }
        />
        <Vital
          label="USD/TRY"
          value={usdNow != null ? usdNow.toFixed(2) : "—"}
          series={usd.slice(-90)}
          format="raw"
          decimals={2}
          note={
            usdYoY != null ? (
              <>
                <em className={`not-italic font-semibold ${toneClass(usdYoY, "down")}`}>
                  {usdYoY >= 0 ? "higher" : "lower"} by {Math.abs(usdYoY).toFixed(1)}%
                </em>{" "}
                over 12 months — lira per dollar
              </>
            ) : (
              "daily CBRT selling rate"
            )
          }
        />
        <Vital
          label="Net reserves, ex-swaps"
          value={ownNow != null ? ownNow.toFixed(1) : "—"}
          unit="$bn"
          series={d.reserves.points.slice(-26).map((p) => ({ period: p.period, value: p.own }))}
          format="raw"
          decimals={1}
          note={
            netNow != null && grossNow != null ? (
              <>
                {bn(netNow)} net of {bn(grossNow)} gross · derived, not published ·{" "}
                <Link href="/liquidity" className="font-semibold text-primary">
                  /liquidity
                </Link>
              </>
            ) : (
              "CBRT analytical balance sheet, weekly"
            )
          }
        />
        <Vital
          label="Current account, 12m"
          value={caGdpNow != null ? caGdpNow.toFixed(1) : "—"}
          unit="% GDP"
          series={caGdp.slice(-13)}
          decimals={1}
          note={
            caNow != null ? (
              <>
                {bn(caNow)} in level terms
                {caXgeNow != null && <> · {bn(caXgeNow)} ex gold &amp; energy</>} ·{" "}
                <Link href="/economy/balance-of-payments" className="font-semibold text-primary">
                  /bop
                </Link>
              </>
            ) : (
              "rolling 12-month sum, balance of payments"
            )
          }
        />
      </Vitals>

      {/* ── The Read ──────────────────────────────────────────────────── */}
      <div className="mt-7">
        <Takeaway data={read} variant="desk" />
      </div>

      {/* ── Movers | Transmission ─────────────────────────────────────── */}
      <div className="mt-8 grid grid-cols-1 gap-x-9 gap-y-7 lg:grid-cols-[5fr_7fr]">
        <div>
          <SecHead
            title="The record"
            meta="monthly series only · each row states its own vintage"
            className="mb-2.5"
          />
          <Movers from="Prior" to="Latest" rows={movers} />
        </div>
        <div>
          <SecHead
            title="Transmission"
            meta="the backdrop → the banks · computed"
            className="mb-2.5"
          />
          <Transmission items={transmission} />
        </div>
      </div>

      {/* ── Flags | Ahead ─────────────────────────────────────────────── */}
      <div className="mt-8 grid grid-cols-1 gap-x-9 gap-y-7 lg:grid-cols-[7fr_5fr]">
        <div>
          <SecHead title="Flags" meta="rules printed whether or not they fire" className="mb-2.5" />
          <Flags
            flags={flagList}
            showCleared
            quietNote="Every macro rule below was tested against the current record and none tripped."
          />
        </div>
        <div>
          <SecHead title="Ahead" meta="scraped calendar + fixed cadence" className="mb-2.5" />
          <Ahead items={aheadItems} />
        </div>
      </div>

      {/* ── In depth — the evidence layer ──────────────────────────────── */}
      <Depth action={<GlobalRangeSelector />}>
        <Section
          title="Growth & Activity"
          description={
            [
              seriesFinding(gdp, {
                noun: "GDP growth",
                decimals: 1,
                window: 4,
                windowLabel: "4 quarters",
              }),
              seriesFinding(ip, { noun: "industrial production", decimals: 1 }),
            ]
              .filter(Boolean)
              .join(" · ") || "GDP and industrial production, y/y."
          }
        >
          <Grid>
            <TimeSeriesChart
              series={{ "GDP growth (y/y)": d.gdpGrowth }}
              title="GDP Growth (y/y %, chain-linked volume, quarterly)"
              yFormat="pct"
              xFormat="quarter"
              decimals={1}
            />
            <TimeSeriesChart
              series={{ "Industrial production (y/y)": d.ipGrowth }}
              title="Industrial Production (y/y %, SA, 2021=100)"
              yFormat="pct"
              decimals={1}
            />
          </Grid>
        </Section>

        <Section
          title="Labor Market"
          description={
            [
              unempNow != null
                ? `Unemployment ${unempNow.toFixed(1)}%${unAtLow ? " — the lowest in the window we hold" : ""}${
                    unempD12 != null ? ` (${signedPp(unempD12, 1)} over 12m)` : ""
                  }`
                : null,
              partMove ? `participation ${partMove}` : null,
            ]
              .filter(Boolean)
              .join("; ")
              .concat(".") || "Unemployment, participation and the employment level, SA."
          }
        >
          <Grid>
            <TimeSeriesChart
              series={{
                "Unemployment rate": d.unemployment,
                "Participation rate": d.participation,
              }}
              title="Unemployment & Labor Force Participation (SA %)"
              yFormat="pct"
              decimals={1}
            />
            <TimeSeriesChart
              series={{ Employed: d.employedMn }}
              title="Employment Level (mn persons, SA)"
              yFormat="raw"
              decimals={1}
            />
          </Grid>
        </Section>

        <Section
          title="Inflation & Monetary Policy"
          description={
            seriesFinding(cpi, { noun: "CPI", decimals: 1 }) ??
            "CPI y/y against the CBRT's effective cost of funding."
          }
        >
          <Grid>
            <TimeSeriesChart
              series={{
                "CPI (y/y)": d.cpiYoY,
                "CBRT cost of funding": d.fundingMonthly,
              }}
              title="CPI Inflation vs CBRT Effective Funding Cost (%)"
              yFormat="pct"
              decimals={1}
              hero="CPI (y/y)"
            />
            <TimeSeriesChart
              series={{ "CPI (m/m)": d.cpiMoM }}
              title="Monthly CPI (m/m %)"
              yFormat="pct"
              decimals={2}
            />
            <TimeSeriesChart
              series={{
                "Current year-end": d.expCurrentYearEnd,
                "Next year-end": d.expNextYearEnd,
                "12 months ahead": d.exp12m,
              }}
              title="Market Participants' CPI Expectations (CBRT survey, %)"
              yFormat="pct"
              decimals={1}
            />
            <TimeSeriesChart
              series={{ "Ex-ante real funding rate": d.realRate }}
              title="Ex-ante Real Policy Rate (funding cost vs 12m-ahead expectation, %)"
              yFormat="pct"
              decimals={1}
            />
          </Grid>
          {/* The households' survey is thin in D1 (a handful of prints), so it is a
              stated figure rather than a chart — plotting seven points as a trend
              would draw a line the series cannot support. */}
          {hhExpNow != null && exp12Now != null && (
            <p className="text-xs text-muted-foreground">
              Households expect{" "}
              <b className="font-semibold text-foreground">{hhExpNow.toFixed(1)}%</b> twelve
              months out against the market&rsquo;s{" "}
              <b className="font-semibold text-foreground">{exp12Now.toFixed(1)}%</b> — a gap
              of {Math.abs(hhExpNow - exp12Now).toFixed(1)}pp. Households have run above
              market participants for as long as both surveys have been published; the
              household series (TP.HANEBEK.HAN14A) carries too few points in our store to
              chart as a trend, so it is quoted, not drawn.
            </p>
          )}
        </Section>

        {/* ── NEW: the pricing chain the page never showed ──────────────── */}
        <Section
          title="Policy Transmission"
          description={
            seriesFinding(spread, { noun: "The loan–deposit spread", decimals: 1, format: "raw" }) ??
            "Policy rate, deposit pricing and loan pricing on one axis, with the spread the sector earns between the last two."
          }
        >
          <Grid>
            <TimeSeriesChart
              series={{
                "Policy rate (1w repo)": d.policyRate,
                "CBRT funding cost": d.fundingMonthly,
                "TL deposit rate": d.depositRate,
                "Commercial loan rate": d.loanCommercial,
              }}
              title="Policy → Deposit → Loan Pricing (monthly average, %)"
              description="Weekly CBRT bank-rate statistics and the daily funding cost, collapsed to monthly averages so the four sit on one cadence."
              yFormat="pct"
              decimals={1}
              hero="CBRT funding cost"
            />
            <TimeSeriesChart
              series={{ "Commercial loan − TL deposit": d.loanDepositSpread }}
              title="Loan − Deposit Spread (pp)"
              description="The sector's gross pricing gap, before funding mix, fees and the cost of risk."
              yFormat="raw"
              decimals={1}
            />
            <TimeSeriesChart
              series={{
                "Commercial": d.loanCommercial,
                "Consumer": d.loanConsumer,
                "Housing": d.loanHousing,
              }}
              title="Loan Pricing by Segment (monthly average, %)"
              yFormat="pct"
              decimals={1}
            />
            <TimeSeriesChart
              series={{
                "Real funding rate": d.realRate,
                "Real TL deposit rate": d.realDepositRate,
              }}
              title="Real Rates — Policy vs the Saver (ex-ante, %)"
              description="Both deflated by the same 12-month-ahead market expectation, compounded (Fisher), so the two are comparable."
              yFormat="pct"
              decimals={1}
            />
          </Grid>
        </Section>

        <Section
          title="Lira & External Balance"
          description={
            caNow != null
              ? `The 12-month current account is ${signed(caNow, (v) => `$${v.toFixed(1)}bn`)}${
                  caMove ? ` and ${caMove} over the year` : ""
                } — against USD/TRY and the real effective exchange rate.`
              : "USD/TRY, the real effective exchange rate and the 12-month current account."
          }
        >
          <Grid>
            <TimeSeriesChart
              series={{ "USD/TRY": d.usdtry, "EUR/TRY": d.eurtry }}
              title="Lira per USD and EUR"
              yFormat="fx"
              decimals={2}
              hero="USD/TRY"
            />
            <TimeSeriesChart
              series={{ "REER (CPI based)": d.reer }}
              title="Real Effective Exchange Rate (2003 = 100)"
              description="Above 100 the lira is stronger than its 2003 basket-weighted real average — a nominal move and a real move are different facts."
              yFormat="rate"
              decimals={1}
            />
            <TimeSeriesChart
              series={{
                "Current account": d.ca12m,
                "ex gold": d.caExGold12m,
                "ex gold & energy": d.caExGoldEnergy12m,
              }}
              title="Current Account Balance (12m rolling, USD bn)"
              yFormat="raw"
              decimals={1}
              hero="Current account"
            />
            <TimeSeriesChart
              series={{ "Current account (% of GDP)": d.caPctGdp }}
              title="Current Account as % of GDP (12m, USD-converted)"
              description="The 12-month balance over trailing-4Q nominal GDP, converted at the average USD/TRY across the same window — not the spot rate."
              yFormat="pct"
              decimals={1}
            />
          </Grid>
        </Section>

        {/* ── NEW: the buffer that finances the deficit ─────────────────── */}
        <Section
          title="Reserves & the External Buffer"
          description={`Gross reserves ${bn(grossNow)}, net ${bn(netNow)}, and ${bn(ownNow)} once the swap book is excluded — ${
            d.importCover != null ? `${d.importCover.toFixed(1)} months of the goods import bill` : "the import-cover read"
          }. TCMB publishes no net-reserves headline; net is derived from the analytical balance sheet.`}
        >
          <ReserveBuffer
            data={d.reserves.points}
            title="The Reserve Buffer, Decomposed (USD bn, weekly)"
            description="Gross → net → net excluding swaps. The gross-to-net gap is the banks' own FX held at the CBRT as required reserves; the net-to-ex-swaps gap is the swap stock."
            source="Source: TCMB analytical balance sheet + IMF reserve template, via EVDS"
          />
          <p className="text-xs text-muted-foreground">
            Drawn as three lines rather than a stack because the CBRT&rsquo;s own net FX
            goes below zero — a stacked area cannot draw a negative band without
            misstating the total. The same derivation feeds{" "}
            <Link href="/liquidity" className="text-primary hover:underline">
              /liquidity
            </Link>
            , so the two pages cannot disagree.
          </p>
        </Section>

        {/* ── NEW: who finances it, and how fast that money can leave ───── */}
        <Section
          title="Non-resident Flows"
          description={`Weekly net purchases of Turkish equities and government debt by non-residents, ${flows.asOfLabel}. Portfolio money reprices daily — distinct from, and more timely than, the monthly balance-of-payments portfolio line.`}
        >
          <Grid>
            <ChartCard title="Weekly Net Non-resident Flows (USD m)">
              <BopFlowChart
                data={flows.flows}
                bars={[
                  { key: "equity", label: "Equities", fill: NAVY },
                  { key: "bonds", label: "Govt bonds (DİBS)", fill: MAROON },
                ] satisfies BarSeries[]}
                unit="m"
                height={320}
              />
            </ChartCard>
            <TimeSeriesChart
              series={flows.holdings}
              title="Non-resident Holdings (stock, USD bn)"
              description="The stock behind the weekly flow — what would have to be sold, not what was."
              yFormat="raw"
              decimals={1}
            />
          </Grid>
        </Section>

        {/* ── NEW: the other side of the same question ──────────────────── */}
        <Section
          title="Residents' Currency Preference"
          description={`Households hold ${bn(hhFxNow)} in FX deposits and ${bn(hhGoldNow)} in precious metals. Set against the central bank's own net FX, this is the domestic side of the same balance the reserves finance.`}
        >
          <ChartRow
            data={tsRows({
              "FX deposits (USD + EUR)": d.householdFx,
              "Precious metals": d.householdGold,
            })}
            deltaPeriods={12}
            deltaLabel="12m"
            fmt={(v) => `$${v.toFixed(1)}bn`}
          >
            <TimeSeriesChart
              series={{
                "FX deposits (USD + EUR)": d.householdFx,
                "Precious metals": d.householdGold,
              }}
              title="Households' FX and Gold Holdings (USD bn)"
              description="Residents' foreign-currency deposits and precious metals, from the CBRT's household financial-assets table."
              yFormat="raw"
              decimals={1}
              height={340}
            />
          </ChartRow>
        </Section>

        <Section
          title="Fiscal Stance"
          description={
            primNow != null
              ? `The primary balance is ${signed(primNow, (v) => `${v.toFixed(1)}%`)} of GDP — ${
                  primNow >= 0 ? "in surplus" : "in deficit"
                }. Treasury general budget, 12m rolling.`
              : "Treasury general budget, 12m rolling."
          }
        >
          <ChartRow
            data={tsRows({
              "Budget balance": d.budgetPctGdp,
              "Primary balance": d.primaryPctGdp,
              "Cash balance": d.cashPctGdp,
            })}
            deltaPeriods={12}
            deltaLabel="12m"
            fmt={(v) => `${v.toFixed(1)}%`}
          >
            <TimeSeriesChart
              series={{
                "Budget balance": d.budgetPctGdp,
                "Primary balance": d.primaryPctGdp,
                "Cash balance": d.cashPctGdp,
              }}
              title="General Budget Balances (12m rolling, % of GDP)"
              yFormat="pct"
              decimals={1}
              height={340}
            />
          </ChartRow>
        </Section>

        {/* ── The baseline, scored ──────────────────────────────────────── */}
        <Section
          title="A Published Baseline, Scored"
          description={`${BBVA_BASELINE.source} (${BBVA_BASELINE.asOf}), against what the series have actually printed since. ${scoredCount} of ${scored.length} rows are scorable from data we hold on the same basis; the rest state why not.`}
        >
          <Table wrapperClassName="rounded-[10px] border border-border bg-card">
            <TableHeader>
              <TableRow className="bg-muted/50">
                <TableHead />
                {BBVA_BASELINE.years.map((y) => (
                  <TableHead key={y} className="text-right">
                    {y}
                  </TableHead>
                ))}
                <TableHead className="text-right">
                  {BBVA_BASELINE.forecastYear} actual
                </TableHead>
                <TableHead className="text-right">vs forecast</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {scored.map((r) => (
                <TableRow key={r.label}>
                  <TableCell className="py-1.5">{r.label}</TableCell>
                  {r.values.map((v, i) => (
                    <TableCellNum
                      key={i}
                      tone={i === r.values.length - 1 ? "neutral" : "muted"}
                      className={`py-1.5 ${i === r.values.length - 1 ? "font-semibold" : ""}`}
                    >
                      {v}
                    </TableCellNum>
                  ))}
                  <TableCellNum tone="neutral" className="py-1.5 font-semibold">
                    {r.realized ?? "—"}
                    {r.n != null && (
                      <span className="ml-1 font-normal text-faint">({r.n})</span>
                    )}
                  </TableCellNum>
                  <TableCellNum tone="muted" className="py-1.5">
                    {r.gap != null ? signed(r.gap) : (
                      <span className="text-faint">{r.note}</span>
                    )}
                  </TableCellNum>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <p className="text-xs text-muted-foreground">
            The &ldquo;actual&rdquo; column is the mean of the {BBVA_BASELINE.forecastYear}{" "}
            observations we hold, and the figure in brackets is how many that is — an
            average over four months is not a year, and a scorecard that hid the count
            would read as though it were. End-of-period rows are not scored before
            December, and the two %-of-GDP budget rows are not scored at all: the
            forecast is central government and our 12-month ratio is the general
            budget, so the difference between them would be a basis gap dressed up as a
            forecast error. This is a third party&rsquo;s published scenario, carried
            for context — not our forecast.
          </p>
        </Section>
      </Depth>

      <Colophon>
        Compiled, not written — growth, labour, prices, policy and bank pricing, lira,
        reserves, external and fiscal series computed from TCMB EVDS (TÜİK · CBRT ·
        Treasury). Net reserves are derived from the CBRT analytical balance sheet, not
        published. The baseline scenario is a third party&rsquo;s, scored here against
        our own series. No forecasts of our own. Analytical information, not investment
        advice.
      </Colophon>
    </main>
  );
}
