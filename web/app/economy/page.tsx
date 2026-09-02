/**
 * Economy tab — the macro backdrop the banks operate in, as a Desk brief over
 * its evidence (web/DESIGN.md).
 *
 * The page used to be a header, a vitals band and a grid of one-series line
 * charts: no computed read, no flags, and no statement anywhere of what any of
 * it does to a bank. Everything the sector tabs had — <Takeaway>, <Movers>,
 * <Transmission>, <Flags> — was missing here, on the one tab
 * whose entire job is to explain the conditions the rest of the site measures.
 *
 * Three things it now carries that the data always supported and nobody wired:
 *   the reserve buffer   published gross + a derived net (lib/reserves.ts).
 *                        NOTHING swap-adjusted prints here — see the reserves
 *                        section for the measurement that removed it
 *   the transmission     policy → deposit → loan pricing, weekly bank rates that
 *                        sat in D1 unread by this page
 *   the scorecard        the third-party baseline, scored against what actually
 *                        happened, instead of a static forecast table nobody
 *                        came back to check
 *
 * Out of scope (no data source here): CDS spreads, OIS pricing and sovereign
 * yield curves (Bloomberg), and the GDP nowcast / FCI composite (proprietary).
 */
import { localizeMetadata } from "@/i18n/metadata";
import { getText } from "@/i18n/server";
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
import { GlobalRangeSelector } from "@/app/components/range-context";
import { fmtQuarter } from "@/app/lib/chart-format";
import Takeaway from "@/app/components/Takeaway";
import TimeSeriesChart from "@/app/components/TimeSeriesChart";
import BopFlowChart, { type BarSeries } from "@/app/components/BopFlowChart";
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

const pageMetadata: Metadata = {
  title: "Turkish Economy — Macro Dashboard",
  description: "Türkiye's macro backdrop for the banking sector — growth, inflation, policy transmission, reserves, the balance of payments and the budget, from official data.",
  alternates: { canonical: "/economy" },
};

export async function generateMetadata(): Promise<Metadata> {
  return localizeMetadata(pageMetadata);
}

function Grid({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">{children}</div>;
}

const pct1 = (v: number | null, d = 1) => (v == null ? "—" : `${v.toFixed(d)}%`);
const bn = (v: number | null, d = 1) => (v == null ? "—" : `$${v.toFixed(d)}bn`);

export default async function EconomyPage() {
  const tx = await getText();
  const [d, flows] = await Promise.all([
    getEconomyData(),
    getPortfolioFlowsData(),
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

  // Reserves. Only the PUBLISHED gross drives a headline figure here; the
  // derived net is plotted and labelled as ours, and nothing swap-adjusted is
  // shown at all (see the reserves section).
  const grossNow = d.reserves.latest?.gross ?? null;
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
  }, tx.locale);

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
        <>{tx("The marginal price of TL for the system. It sets the floor under deposit pricing and, with a lag, under loan pricing — the two legs of")}{" "}
          <Link href="/profitability" className="font-semibold text-primary">{tx("the margin")}</Link>
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
          <>{tx("Funding costs more than expected inflation, so lira carries a positive expected real return — the condition under which deposits compete with FX and gold on their own merits.")}</>
        ) : (
          <>{tx("Funding costs less than expected inflation, so a lira deposit is expected to lose purchasing power — the standing incentive behind")}{" "}
            <Link href="/deposits" className="font-semibold text-primary">{tx("dollarization")}</Link>
            .
          </>
        ),
    },
    {
      k: "Loan − deposit spread",
      v: spreadNow != null ? `${spreadNow.toFixed(1)}pp` : "—",
      effect: (
        <>{tx("Commercial loan pricing at ")}{tx(pct1(loanRateNow))}{tx(" over TL deposits at")}{" "}
          {tx(pct1(depRateNow))}{tx(". This gap is the sector’s gross margin before funding mix, fees and the cost of risk —")}{" "}
          <Link href="/rates" className="font-semibold text-primary">{tx("/rates")}</Link>{" "}{tx("carries the full pricing curve.")}</>
      ),
    },
    {
      k: "Real deposit rate",
      v: realDepNow != null ? signedPct(realDepNow) : "—",
      effect:
        realDepNow == null ? (
          "The TL deposit rate deflated by the 12-month-ahead expectation."
        ) : (
          <>{tx("What a saver expects to earn after inflation. It is")}{" "}
            {tx(realDepNow >= 0 ? "above" : "below")}{tx(" zero, so the expected real return on a lira deposit is ")}{tx(realDepNow >= 0 ? "a gain" : "a loss")}{tx(" of")}{" "}
            {tx(Math.abs(realDepNow).toFixed(1))}{tx("% — the number that competes with FX cash and gold in a household’s decision.")}</>
        ),
    },
    {
      k: "CPI, y/y",
      v: pct1(cpiNow),
      effect: (
        <>{tx("Prices the nominal book: at this rate a balance sheet can grow in lira and shrink in real terms, which is why every nominal level on this site ships with a deflated twin. It also sets operating costs and CPI-linker income.")}</>
      ),
    },
    {
      k: "GDP growth, y/y",
      v: pct1(gdpNow),
      effect: (
        <>{tx("The demand side of the loan book — ")}{tx(gdpQuarter ? fmtQuarter(gdpQuarter) : "—")}{tx(", quarterly, so it moves later than everything above it. Output is what eventually settles")}{" "}
          <Link href="/asset-quality" className="font-semibold text-primary">{tx("NPL formation")}</Link>
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
          <b className="font-semibold">{tx("Policy is accommodative in real terms.")}</b>{tx(" Funding at ")}{tx(pct1(fundNow))}{tx(" sits under the ")}{tx(pct1(exp12Now))}{tx(" expected for the next twelve months, a real rate of ")}{tx(realNow != null ? signedPct(realNow) : "—")}.
        </>
      ),
      clear: (
        <>{tx("Ex-ante real funding rate ")}{tx(realNow != null ? signedPct(realNow) : "—")}{tx(" — at or above zero against the ")}{tx(pct1(exp12Now))}{tx(" expectation.")}</>
      ),
    },
    {
      code: "IMPORT_COVER",
      active: d.importCover != null && d.importCover < 3,
      rule: "gross_reserves / (imports_12m / 12) < 3 months",
      body: (
        <>
          <b className="font-semibold">{tx("Reserve cover is below the conventional floor.")}</b>{" "}{tx("Gross reserves of ")}{tx(bn(grossNow))}{tx(" cover ")}{tx(d.importCover?.toFixed(1))}{tx(" months of the goods import bill, under the three-month rule of thumb.")}</>
      ),
      clear: (
        <>{tx("Gross reserves cover ")}{tx(d.importCover != null ? d.importCover.toFixed(1) : "—")}{" "}{tx("months of imports — at or above the three-month rule of thumb.")}</>
      ),
    },
    // A swap-adjusted flag used to sit here ("the CBRT's own net FX is
    // negative"). It tested a quantity this page cannot compute — see the
    // reserves section — so the rule is gone rather than left firing off a
    // number that was $5bn out.
    {
      code: "CA_WIDE",
      active: caGdpNow != null && caGdpNow < -4,
      rule: "current_account_12m / gdp < −4%",
      body: (
        <>
          <b className="font-semibold">{tx("The external deficit is wide.")}</b>{tx(" The twelve-month current account is ")}{tx(caGdpNow != null ? `${caGdpNow.toFixed(1)}%` : "—")}{tx(" of GDP, which has to be financed every month it persists.")}</>
      ),
      clear: (
        <>{tx("The 12-month current account is")}{" "}
          {tx(caGdpNow != null ? `${caGdpNow.toFixed(1)}%` : "—")}{tx(" of GDP — inside the −4% line this rule tests.")}</>
      ),
    },
    {
      code: "CPI_MM_RUN",
      active: cpiAcc >= 3,
      rule: "consecutive_rise(cpi_m/m) ≥ 3",
      body: (
        <>
          <b className="font-semibold">{tx("The monthly print has risen ")}{tx(cpiAcc)}{tx(" months running.")}</b>{" "}{tx("The annual rate is built from these; a run of three sets the direction of the next few readings before any base effect.")}</>
      ),
      clear: <>{tx("The monthly CPI print has not risen three months running.")}</>,
    },
    {
      code: "BUDGET_WIDE",
      active: budget.length > 0 && lastVal(budget) != null && (lastVal(budget) as number) < -3,
      rule: "general_budget_12m / gdp < −3%",
      body: (
        <>
          <b className="font-semibold">{tx("The budget deficit is past the 3% reference.")}</b>{" "}{tx("The twelve-month general budget balance is ")}{tx(pct1(lastVal(budget)))}{tx(" of GDP, with the primary balance at ")}{tx(pct1(primNow))}.
        </>
      ),
      clear: (
        <>{tx("The 12-month general budget balance is ")}{tx(pct1(lastVal(budget)))}{tx(" of GDP — inside the 3% reference value.")}</>
      ),
    },
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
        title={tx("Economy")}
        record={
          <>{tx("Record ")}<b className="font-normal text-foreground">{tx(monthLabel(d.cpiYoY.at(-1)?.period_date))}</b>{" "}{tx("· monthly EVDS · GDP quarterly (")}{tx(gdpQuarter ? fmtQuarter(gdpQuarter) : "—")}{tx(") · reserves weekly")}</>
        }
        right="every figure computed from source series"
      />

      {/* ── The vitals ─────────────────────────────────────────────────── */}
      <SecHead
        title={tx("The vitals")}
        meta={tx("policy · prices · activity · lira · reserves · external")}
        className="mb-2.5 mt-6"
      />
      <Levels
        items={[
          { k: "Nominal GDP, 4Q", v: lastVal(toPts(d.nominalGdp4q))?.toFixed(1) ?? "—", unit: "₺trn" },
          { k: "Reserve cover", v: d.importCover?.toFixed(1) ?? "—", unit: "months" },
          { k: "Imports, 12m", v: lastVal(toPts(d.imports12m))?.toFixed(0) ?? "—", unit: "$bn" },
          { k: "Employed", v: lastVal(toPts(d.employedMn))?.toFixed(1) ?? "—", unit: "mn" },
        ]}
      />
      <Vitals>
        <Vital
          label={tx("CBRT cost of funding")}
          value={fundNow != null ? fundNow.toFixed(1) : "—"}
          unit="%"
          series={fund.slice(-13)}
          decimals={1}
          note={
            realNow != null && exp12Now != null ? (
              <>
                ≈{" "}
                <em className={`not-italic font-semibold ${realNow >= 0 ? "text-positive" : "text-negative"}`}>
                  {tx(signed(realNow))}{tx("% ex-ante real")}</em>{" "}{tx("vs the ")}{tx(exp12Now.toFixed(1))}{tx("% 12m-ahead expectation")}</>
            ) : (
              "monthly average of the daily effective rate"
            )
          }
        />
        <Vital
          label={tx("CPI, y/y")}
          value={cpiNow != null ? cpiNow.toFixed(1) : "—"}
          unit="%"
          series={cpi.slice(-13)}
          decimals={1}
          note={
            <>
              {tx(cpiD12 != null ? tx("{0} over 12m", {0: signedPp(cpiD12, 1)}) : "TÜİK headline")}
              {cpiFall >= 3 && <> · {tx(cpiFall)}{tx(" straight monthly falls")}</>} ·{" "}
              <Link href="/economy/inflation" className="font-semibold text-primary">{tx("/inflation")}</Link>
            </>
          }
        />
        <Vital
          label={tx("GDP growth, y/y")}
          value={gdpNow != null ? gdpNow.toFixed(1) : "—"}
          unit="%"
          series={gdp.slice(-13)}
          decimals={1}
          note={
            <>
              {tx(gdpQuarter ? fmtQuarter(gdpQuarter) : "—")}
              {gdpD != null && <> · {tx(signedPp(gdpD, 1))}{tx(" vs the prior quarter")}</>} ·{" "}
              <Link href="/economy/economic-growth" className="font-semibold text-primary">{tx("/growth")}</Link>
            </>
          }
        />
        <Vital
          label={tx("USD/TRY")}
          value={usdNow != null ? usdNow.toFixed(2) : "—"}
          series={usd.slice(-90)}
          format="raw"
          decimals={2}
          note={
            usdYoY != null ? (
              <>
                <em className={`not-italic font-semibold ${toneClass(usdYoY, "down")}`}>
                  {tx(usdYoY >= 0 ? "higher" : "lower")}{tx(" by ")}{tx(Math.abs(usdYoY).toFixed(1))}%
                </em>{" "}{tx("over 12 months — lira per dollar")}</>
            ) : (
              "daily CBRT selling rate"
            )
          }
        />
        {/* The PUBLISHED figure, not a derived one. This cell used to carry
            "net reserves, ex-swaps", which was wrong by ~$5bn on every week
            checked — see the reserves section below for what happened and why
            nothing swap-adjusted prints here now. */}
        <Vital
          label={tx("Gross reserves")}
          value={grossNow != null ? grossNow.toFixed(1) : "—"}
          unit="$bn"
          series={d.reserves.points.slice(-26).map((p) => ({ period: p.period, value: p.gross }))}
          format="raw"
          decimals={1}
          note={
            d.importCover != null ? (
              <>
                {tx(d.importCover.toFixed(1))}{tx(" months of the goods import bill · TCMB weekly, as published")}</>
            ) : (
              "TCMB weekly total reserves, as published"
            )
          }
        />
        <Vital
          label={tx("Current account, 12m")}
          value={caGdpNow != null ? caGdpNow.toFixed(1) : "—"}
          unit="% GDP"
          series={caGdp.slice(-13)}
          decimals={1}
          note={
            caNow != null ? (
              <>
                {tx(bn(caNow))}{tx(" in level terms")}{caXgeNow != null && <> · {tx(bn(caXgeNow))}{tx(" ex gold & energy")}</>} ·{" "}
                <Link href="/economy/balance-of-payments" className="font-semibold text-primary">{tx("/bop")}</Link>
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
            title={tx("The record")}
            meta={tx("monthly series only · each row states its own vintage")}
            className="mb-2.5"
          />
          <Movers from="Prior" to="Latest" rows={movers} />
        </div>
        <div>
          <SecHead
            title={tx("Transmission")}
            meta={tx("the backdrop → the banks · computed")}
            className="mb-2.5"
          />
          <Transmission items={transmission} />
        </div>
      </div>

      {/* ── Flags ─────────────────────────────────────────────────────── */}
      <div className="mt-8">
        <div>
          <SecHead title={tx("Flags")} meta={tx("rules printed whether or not they fire")} className="mb-2.5" />
          <Flags
            flags={flagList}
            showCleared
            quietNote="Every macro rule below was tested against the current record and none tripped."
          />
        </div>
      </div>

      {/* ── In depth — the evidence layer ──────────────────────────────── */}
      <Depth action={<GlobalRangeSelector />}>
        <Section
          title={tx("Growth & Activity")}
          description={
            tx([
              seriesFinding(gdp, {
                noun: "GDP growth",
                decimals: 1,
                window: 4,
                windowLabel: "4 quarters",
              }, tx.locale),
              seriesFinding(ip, { noun: "industrial production", decimals: 1 }, tx.locale),
            ]
              .filter(Boolean)
              .join(" · ") || "GDP and industrial production, y/y.")
          }
        >
          <Grid>
            <TimeSeriesChart
              series={{ "GDP growth (y/y)": d.gdpGrowth }}
              title={tx("GDP Growth (y/y %, chain-linked volume, quarterly)")}
              yFormat="pct"
              xFormat="quarter"
              decimals={1}
            />
            <TimeSeriesChart
              series={{ "Industrial production (y/y)": d.ipGrowth }}
              title={tx("Industrial Production (y/y %, SA, 2021=100)")}
              yFormat="pct"
              decimals={1}
            />
          </Grid>
        </Section>

        <Section
          title={tx("Labor Market")}
          description={
            tx([
              unempNow != null
                ? tx("Unemployment {0}%{1}{2}", {0: unempNow.toFixed(1), 1: unAtLow ? " — the lowest in the window we hold" : "", 2: unempD12 != null ? tx(" ({0} over 12m)", {0: signedPp(unempD12, 1)}) : ""})
                : null,
              partMove ? tx("participation {0}", {0: partMove}) : null,
            ]
              .filter(Boolean)
              .join("; ")
              .concat(".") || "Unemployment, participation and the employment level, SA.")
          }
        >
          <Grid>
            <TimeSeriesChart
              series={{
                "Unemployment rate": d.unemployment,
                "Participation rate": d.participation,
              }}
              title={tx("Unemployment & Labor Force Participation (SA %)")}
              yFormat="pct"
              decimals={1}
            />
            <TimeSeriesChart
              series={{ Employed: d.employedMn }}
              title={tx("Employment Level (mn persons, SA)")}
              yFormat="raw"
              decimals={1}
            />
          </Grid>
        </Section>

        <Section
          title={tx("Inflation & Monetary Policy")}
          description={
            tx(seriesFinding(cpi, { noun: "CPI", decimals: 1 }, tx.locale) ??
            "CPI y/y against the CBRT's effective cost of funding.")
          }
        >
          <Grid>
            <TimeSeriesChart
              series={{
                "CPI (y/y)": d.cpiYoY,
                "CBRT cost of funding": d.fundingMonthly,
              }}
              title={tx("CPI Inflation vs CBRT Effective Funding Cost (%)")}
              yFormat="pct"
              decimals={1}
              hero="CPI (y/y)"
            />
            <TimeSeriesChart
              series={{ "CPI (m/m)": d.cpiMoM }}
              title={tx("Monthly CPI (m/m %)")}
              yFormat="pct"
              decimals={2}
            />
            <TimeSeriesChart
              series={{
                "Current year-end": d.expCurrentYearEnd,
                "Next year-end": d.expNextYearEnd,
                "12 months ahead": d.exp12m,
              }}
              title={tx("Market Participants' CPI Expectations (CBRT survey, %)")}
              yFormat="pct"
              decimals={1}
            />
            <TimeSeriesChart
              series={{ "Ex-ante real funding rate": d.realRate }}
              title={tx("Ex-ante Real Policy Rate (funding cost vs 12m-ahead expectation, %)")}
              yFormat="pct"
              decimals={1}
            />
          </Grid>
          {/* The households' survey is thin in D1 (a handful of prints), so it is a
              stated figure rather than a chart — plotting seven points as a trend
              would draw a line the series cannot support. */}
          {hhExpNow != null && exp12Now != null && (
            <p className="text-xs text-muted-foreground">{tx("Households expect")}{" "}
              <b className="font-semibold text-foreground">{tx(hhExpNow.toFixed(1))}%</b>{tx(" twelve months out against the market’s")}{" "}
              <b className="font-semibold text-foreground">{tx(exp12Now.toFixed(1))}%</b>{tx(" — a gap of ")}{tx(Math.abs(hhExpNow - exp12Now).toFixed(1))}{tx("pp. Households have run above market participants for as long as both surveys have been published; the household series (TP.HANEBEK.HAN14A) carries too few points in our store to chart as a trend, so it is quoted, not drawn.")}</p>
          )}
        </Section>

        {/* ── NEW: the pricing chain the page never showed ──────────────── */}
        <Section
          title={tx("Policy Transmission")}
          description={
            tx(seriesFinding(spread, { noun: "The loan–deposit spread", decimals: 1, format: "raw" }, tx.locale) ??
            "Policy rate, deposit pricing and loan pricing on one axis, with the spread the sector earns between the last two.")
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
              title={tx("Policy → Deposit → Loan Pricing (monthly average, %)")}
              description={tx("Weekly CBRT bank-rate statistics and the daily funding cost, collapsed to monthly averages so the four sit on one cadence.")}
              yFormat="pct"
              decimals={1}
              hero="CBRT funding cost"
            />
            <TimeSeriesChart
              series={{ "Commercial loan − TL deposit": d.loanDepositSpread }}
              title={tx("Loan − Deposit Spread (pp)")}
              description={tx("The sector's gross pricing gap, before funding mix, fees and the cost of risk.")}
              yFormat="raw"
              decimals={1}
            />
            <TimeSeriesChart
              series={{
                "Commercial": d.loanCommercial,
                "Consumer": d.loanConsumer,
                "Housing": d.loanHousing,
              }}
              title={tx("Loan Pricing by Segment (monthly average, %)")}
              yFormat="pct"
              decimals={1}
            />
            <TimeSeriesChart
              series={{
                "Real funding rate": d.realRate,
                "Real TL deposit rate": d.realDepositRate,
              }}
              title={tx("Real Rates — Policy vs the Saver (ex-ante, %)")}
              description={tx("Both deflated by the same 12-month-ahead market expectation, compounded (Fisher), so the two are comparable.")}
              yFormat="pct"
              decimals={1}
            />
          </Grid>
        </Section>

        <Section
          title={tx("Lira & External Balance")}
          description={
            tx(caNow != null
              ? tx("The 12-month current account is {0}{1} — against USD/TRY and the real effective exchange rate.", {0: signed(caNow, (v) => `$${v.toFixed(1)}bn`), 1: caMove ? tx(" and {0} over the year", {0: caMove}) : ""})
              : "USD/TRY, the real effective exchange rate and the 12-month current account.")
          }
        >
          <Grid>
            <TimeSeriesChart
              series={{ "USD/TRY": d.usdtry, "EUR/TRY": d.eurtry }}
              title={tx("Lira per USD and EUR")}
              yFormat="fx"
              decimals={2}
              hero="USD/TRY"
            />
            <TimeSeriesChart
              series={{ "REER (CPI based)": d.reer }}
              title={tx("Real Effective Exchange Rate (2003 = 100)")}
              description={tx("Above 100 the lira is stronger than its 2003 basket-weighted real average — a nominal move and a real move are different facts.")}
              yFormat="rate"
              decimals={1}
            />
            <TimeSeriesChart
              series={{
                "Current account": d.ca12m,
                "ex gold": d.caExGold12m,
                "ex gold & energy": d.caExGoldEnergy12m,
              }}
              title={tx("Current Account Balance (12m rolling, USD bn)")}
              yFormat="raw"
              decimals={1}
              hero="Current account"
            />
            <TimeSeriesChart
              series={{ "Current account (% of GDP)": d.caPctGdp }}
              title={tx("Current Account as % of GDP (12m, USD-converted)")}
              description={tx("The 12-month balance over trailing-4Q nominal GDP, converted at the average USD/TRY across the same window — not the spot rate.")}
              yFormat="pct"
              decimals={1}
            />
          </Grid>
        </Section>

        {/* ── NEW: the buffer that finances the deficit ─────────────────── */}
        {/* This section used to draw a third line, "net excluding swaps", and a
            vitals cell and a flag on top of it. All three are gone. Measured
            2026-08-07 against the figures the press reports, over five
            consecutive weeks, the swap-adjusted line was ~$5bn low EVERY week
            (31 Jul: ours $35.7bn against $40.8bn reported) and missed an
            independent 2025 anchor by $9.8bn (TCMB's own MPC summary put
            ex-swaps at $66.0bn on 12 Dec 2025; the formula gave $56.2bn).
            The cause is not a bug that can be fixed by picking a better series:
              · TCMB publishes NO net-reserves series at all — every reserve
                datagroup in EVDS carries gold / FX / total and nothing else, so
                both "net rezerv" and "swap hariç net rezerv" in the press are
                ANALYST constructs, each house with its own method.
              · The deduction those figures imply (~$13.4bn) matches no official
                series: the CBRT's own swap book now reads ZERO across all six
                `bie_swaptektarf` outstanding series, the IMF template's
                forward/futures short leg (TP.DOVVARNC.K15) is $17.7bn and only
                monthly, and non-resident liabilities are $14.6bn and move the
                wrong way.
            So the swap-adjusted level is not something this page can compute
            from source series, and a number that LOOKS like the headline figure
            while sitting $5bn under it is the worst thing this dashboard can
            print. Gross is published and matches to the decimal; net is our own
            derivation and is labelled as one. Do not re-add a swap-adjusted
            line here without a source that reproduces the published figure. */}
        <Section
          title={tx("Reserves & the External Buffer")}
          description={tx("Gross reserves {0} as published by TCMB{1}. The net line is our own derivation from the CBRT balance sheet — TCMB publishes no net-reserves series, so there is no official figure to carry.", {0: bn(grossNow), 1: d.importCover != null ? tx(", {0} months of the goods import bill", {0: d.importCover.toFixed(1)}) : ""})}
        >
          <TimeSeriesChart
            series={{
              "Gross reserves (published)": d.reserves.points.map((p) => ({
                period_date: p.period,
                value: p.gross,
              })),
              "Net FX position (derived)": d.reserves.points.map((p) => ({
                period_date: p.period,
                value: p.net,
              })),
            }}
            title={tx("Reserves — Published Gross and a Derived Net (USD bn, weekly)")}
            description={tx("Gross is TP.AB.TOPLAM exactly as TCMB publishes it. The net line is total FX assets less total FX liabilities from the CBRT balance sheet, converted at the same-date USD/TRY.")}
            source={tx("Source: TCMB, via EVDS")}
            yFormat="raw"
            decimals={1}
            hero="Gross reserves (published)"
            height={340}
          />
          <p className="text-xs text-muted-foreground">
            <b className="font-semibold text-foreground">{tx("No swap-adjusted figure is shown, deliberately.")}</b>{" "}{tx("The “swap hariç net rezerv” quoted in the press is an analyst calculation, not a TCMB release — there is no net-reserves series in EVDS to carry, and the deduction those figures imply does not correspond to any published series we could find. Our derived net tracks the reported net within about a billion dollars, which is close enough to plot and not close enough to call the same number, so it is labelled as ours. Where a figure cannot be computed from a source, this site prints nothing rather than an approximation dressed as the headline.")}</p>
        </Section>

        {/* ── NEW: who finances it, and how fast that money can leave ───── */}
        <Section
          title={tx("Non-resident Flows")}
          description={tx("Weekly net purchases of Turkish equities and government debt by non-residents, {0}. Portfolio money reprices daily — distinct from, and more timely than, the monthly balance-of-payments portfolio line.", {0: flows.asOfLabel})}
        >
          <Grid>
            <ChartCard title={tx("Weekly Net Non-resident Flows (USD m)")}>
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
              title={tx("Non-resident Holdings (stock, USD bn)")}
              description={tx("The stock behind the weekly flow — what would have to be sold, not what was.")}
              yFormat="raw"
              decimals={1}
            />
          </Grid>
        </Section>

        {/* ── NEW: the other side of the same question ──────────────────── */}
        <Section
          title={tx("Residents' Currency Preference")}
          description={tx("Households hold {0} in FX deposits and {1} in precious metals. Set against the central bank's own net FX, this is the domestic side of the same balance the reserves finance.", {0: bn(hhFxNow), 1: bn(hhGoldNow)})}
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
              title={tx("Households' FX and Gold Holdings (USD bn)")}
              description={tx("Residents' foreign-currency deposits and precious metals, from the CBRT's household financial-assets table.")}
              yFormat="raw"
              decimals={1}
              height={340}
            />
          </ChartRow>
        </Section>

        <Section
          title={tx("Fiscal Stance")}
          description={
            tx(primNow != null
              ? tx("The primary balance is {0} of GDP — {1}. Treasury general budget, 12m rolling.", {0: signed(primNow, (v) => `${v.toFixed(1)}%`), 1: primNow >= 0 ? "in surplus" : "in deficit"})
              : "Treasury general budget, 12m rolling.")
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
              title={tx("General Budget Balances (12m rolling, % of GDP)")}
              yFormat="pct"
              decimals={1}
              height={340}
            />
          </ChartRow>
        </Section>

        {/* ── The baseline, scored ──────────────────────────────────────── */}
        <Section
          title={tx("A Published Baseline, Scored")}
          description={tx("{0} ({1}), against what the series have actually printed since. {2} of {3} rows are scorable from data we hold on the same basis; the rest state why not.", {0: BBVA_BASELINE.source, 1: BBVA_BASELINE.asOf, 2: scoredCount, 3: scored.length})}
        >
          <Table wrapperClassName="rounded-[10px] border border-border bg-card">
            <TableHeader>
              <TableRow className="bg-muted/50">
                <TableHead />
                {BBVA_BASELINE.years.map((y) => (
                  <TableHead key={y} className="text-right">
                    {tx(y)}
                  </TableHead>
                ))}
                <TableHead className="text-right">
                  {tx(BBVA_BASELINE.forecastYear)}{tx(" actual")}</TableHead>
                <TableHead className="text-right">{tx("vs forecast")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {scored.map((r) => (
                <TableRow key={r.label}>
                  <TableCell className="py-1.5">{tx(r.label)}</TableCell>
                  {r.values.map((v, i) => (
                    <TableCellNum
                      key={i}
                      tone={i === r.values.length - 1 ? "neutral" : "muted"}
                      className={`py-1.5 ${i === r.values.length - 1 ? "font-semibold" : ""}`}
                    >
                      {tx(v)}
                    </TableCellNum>
                  ))}
                  <TableCellNum tone="neutral" className="py-1.5 font-semibold">
                    {tx(r.realized ?? "—")}
                    {r.n != null && (
                      <span className="ml-1 font-normal text-faint">({tx(r.n)})</span>
                    )}
                  </TableCellNum>
                  <TableCellNum tone="muted" className="py-1.5">
                    {r.gap != null ? signed(r.gap) : (
                      <span className="text-faint">{tx(r.note)}</span>
                    )}
                  </TableCellNum>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <p className="text-xs text-muted-foreground">{tx("The “actual” column is the mean of the ")}{tx(BBVA_BASELINE.forecastYear)}{" "}{tx("observations we hold, and the figure in brackets is how many that is — an average over four months is not a year, and a scorecard that hid the count would read as though it were. End-of-period rows are not scored before December, and the two %-of-GDP budget rows are not scored at all: the forecast is central government and our 12-month ratio is the general budget, so the difference between them would be a basis gap dressed up as a forecast error. This is a third party’s published scenario, carried for context — not our forecast.")}</p>
        </Section>
      </Depth>

      <Colophon>{tx("Compiled, not written — growth, labour, prices, policy and bank pricing, lira, reserves, external and fiscal series computed from TCMB EVDS (TÜİK · CBRT · Treasury). Net reserves are derived from the CBRT analytical balance sheet, not published. The baseline scenario is a third party’s, scored here against our own series. No forecasts of our own. Analytical information, not investment advice.")}</Colophon>
    </main>
  );
}
