/**
 * Economic Growth — reproduces the Albaraka "Ekonomik Büyüme" quarterly GDP
 * report from TÜİK national-accounts series in EVDS: headline growth, the
 * expenditure-side growth contributions, sectoral (production-side) growth,
 * and the two y/y detail tables.
 *
 * Data + derivations: app/lib/growth.ts. What EVDS can't supply (the q/q
 * seasonally-adjusted line, the consumption/investment detail of Şekil 4–5,
 * and the calendar-adjusted production variant) is flagged in the page notes
 * — it would need a separate TÜİK Excel scraper.
 */
import type { Metadata } from "next";
import Link from "next/link";
import { getGrowthData, type GrowthTable } from "@/app/lib/growth";
import { type BarRow } from "@/app/lib/bop";
import {
  Section,
  Stat,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  TableCellNum,
  toneFor,
} from "@/app/components/ui";
import {
  Ahead,
  Colophon,
  Depth,
  DeskHeader,
  Flags,
  Movers,
  SecHead,
  Transmission,
  Vital,
  Vitals,
  type Flag,
  type MoverRow,
  type TransmissionItem,
} from "@/app/components/desk";
import { lastVal, signedPp, streak, valAgo, windowExtremes, type Pt } from "@/app/lib/desk";
import { VERBS, direction, signed } from "@/app/lib/prose";
import { GlobalRangeSelector } from "@/app/components/range-context";
import { ChartCard } from "@/app/components/ui/chart-card";
import Takeaway from "@/app/components/Takeaway";
import { growthInsights } from "@/app/lib/insights";
import { aheadSlots } from "@/app/lib/ahead-data";
import TimeSeriesChart from "@/app/components/TimeSeriesChart";
import BopFlowChart, { type BarSeries, type OverlayLine } from "@/app/components/BopFlowChart";
import { nf } from "@/app/lib/chart-format";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkey Economic Growth — GDP",
  description: "Türkiye GDP and economic growth — chain-volume series and year-on-year growth from TÜİK.",
  alternates: { canonical: "/economy/economic-growth" },
};

const MAROON = { light: "#9c1f2f", dark: "#d65a5a" };
const AMBER = { light: "#f5c518", dark: "#fbd34d" };
const ORANGE = { light: "#e8833a", dark: "#f0a35e" };
const GREY = { light: "#9ca3af", dark: "#9ca3af" };
const LBLUE = { light: "#6f9fe0", dark: "#93c5fd" };
const DBLUE = { light: "#1f4068", dark: "#3b6ea5" };
const GREEN = { light: "#0f7b6c", dark: "#34c9b0" };
const NAVY = { light: "#1f4068", dark: "#6f9fe0" };
const INK = { light: "#171717", dark: "#ededed" };

const pct1 = (v: number | null) =>
  v == null ? "—" : `${v > 0 ? "+" : ""}${nf(v, 1)}%`;

/** EVDS rows ({period_date}) → the desk helpers' Pt shape ({period}). */
const toPts = (s: { period_date: string; value: number }[]): Pt[] =>
  s.map((r) => ({ period: r.period_date, value: r.value }));

/** A BarRow cell as a number (BarRow values are number | string). */
const cell = (r: BarRow | undefined, k: string): number | null => {
  const v = r?.[k];
  return typeof v === "number" ? v : null;
};

/** The per-quarter history of one BarRow key, as a sparkline series. */
const barSeries = (rows: BarRow[], k: string): Pt[] =>
  rows.map((r) => ({ period: String(r.x), value: cell(r, k) }));

/** Pick the largest / smallest component of the latest BarRow. */
function extremeComponent(
  rows: BarRow[],
  labels: Record<string, string>,
  dir: "max" | "min",
): { key: string; label: string; value: number } | null {
  const last = rows.at(-1);
  if (!last) return null;
  let best: { key: string; label: string; value: number } | null = null;
  for (const [key, label] of Object.entries(labels)) {
    const v = cell(last, key);
    if (v == null) continue;
    if (best == null || (dir === "max" ? v > best.value : v < best.value)) {
      best = { key, label, value: v };
    }
  }
  return best;
}

const EXPENDITURE: Record<string, string> = {
  consumption: "Consumption",
  government: "Government",
  investment: "Investment",
  inventories: "Inventories",
  exports: "Exports",
  imports: "Imports",
};

const SECTORS: Record<string, string> = {
  agri: "Agriculture",
  industry: "Industry",
  constr: "Construction",
  services: "Services",
};

function YoyTable({ table, note }: { table: GrowthTable; note?: string }) {
  return (
    <div className="space-y-2">
      <Table wrapperClassName="rounded-[10px] border border-border bg-card">
        <TableHeader>
          <TableRow className="bg-muted/50">
            <TableHead>y/y % change</TableHead>
            {table.quarters.map((q) => (
              <TableHead key={q} className="text-right">
                {q}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {table.rows.map((r) => {
            const isGdp = r.label === "GDP";
            return (
              <TableRow key={r.label} className={isGdp ? "bg-accent/30 font-semibold" : undefined}>
                <TableCell className={`py-1.5 ${r.indent ? "pl-6 text-muted-foreground" : ""}`}>
                  {r.label}
                </TableCell>
                {r.values.map((v, i) => (
                  <TableCellNum key={i} tone={toneFor(v)} className="py-1.5">
                    {v == null ? "—" : v.toFixed(1)}
                  </TableCellNum>
                ))}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
      {note && <p className="text-xs text-muted-foreground">{note}</p>}
    </div>
  );
}

const pp = (v: number) => signed(v, (x) => `${x.toFixed(1)}pp`);

export default async function EconomicGrowthPage() {
  const [d, ahead] = await Promise.all([getGrowthData(), aheadSlots()]);

  // ---- the brief's computed vitals ------------------------------------------
  // Every cell below is derived from the series this page already fetches.
  const gdp = toPts(d.s1["GDP (y/y)"] ?? []);
  const gdpNow = lastVal(gdp);
  const gdpPrev = valAgo(gdp, 1);
  const gdpD = gdpNow != null && gdpPrev != null ? gdpNow - gdpPrev : null;
  const gdpWin = windowExtremes(gdp, 8);
  const atWinHigh = gdpNow != null && gdpWin != null && gdpNow >= gdpWin.max;
  const atWinLow = gdpNow != null && gdpWin != null && gdpNow <= gdpWin.min;

  const topExp = extremeComponent(d.s2, EXPENDITURE, "max");
  const dragExp = extremeComponent(d.s2, EXPENDITURE, "min");
  const topSec = extremeComponent(d.s3, SECTORS, "max");
  const weakSec = extremeComponent(d.s3, SECTORS, "min");

  const signedPpStr = (v: number) => signedPp(v, 1);

  // The two section reads. Every number they used to hardcode — the quarter, the
  // GDP print, the leading and lagging contributors — is already computed above
  // and was simply never wired to the sentence.
  const gdpQuarter = d.s2.at(-1)?.x ?? null;
  const gdpVerb = direction(gdpNow, VERBS.size, { flat: 0.1, sharp: Number.POSITIVE_INFINITY });
  const growthRead =
    gdpNow != null && gdpVerb && gdpQuarter
      ? `GDP ${gdpVerb} ${Math.abs(gdpNow).toFixed(1)}% y/y in ${gdpQuarter}` +
        (topExp && topExp.value > 0
          ? `. ${topExp.label} drove it (${pp(topExp.value)})`
          : "") +
        (dragExp && dragExp.value < 0
          ? `, while ${dragExp.label.toLowerCase()} subtracted ${pp(dragExp.value)}`
          : "") +
        "."
      : null;

  const sectorRead =
    topSec || weakSec
      ? "Gross value added by activity, y/y %." +
        (topSec ? ` ${topSec.label} led (${pp(topSec.value)})` : "") +
        (weakSec ? `${topSec ? ";" : ""} ${weakSec.label.toLowerCase()} lagged (${pp(weakSec.value)})` : "") +
        ". Figures use the unadjusted chain-volume index (see table note)."
      : null;

  // ---- "The Read" — computed from the same series the charts show ----------
  const read = growthInsights({
    gdp,
    ip: toPts(d.s1["GDP (y/y)"] ?? []).length ? toPts(d.s1["GDP (y/y)"]) : [],
    consumption: toPts(d.expYoY["Household consumption"] ?? []),
    investment: toPts(d.expYoY["Fixed investment"] ?? []),
    exports: toPts(d.expYoY["Exports"] ?? []),
    imports: toPts(d.expYoY["Imports"] ?? []),
  });

  // ---- movers: the expenditure side, quarter on quarter --------------------
  // All five rows are the SAME quarterly cadence off the same national-accounts
  // release, so one from→to header is honest here (unlike the hub's mixed
  // monthly vintages).
  const expMover = (label: string): MoverRow => {
    const s = toPts(d.expYoY[label] ?? []);
    return {
      label,
      prev: valAgo(s, 1),
      curr: lastVal(s),
      good: label === "Imports" ? "neutral" : "up",
      fmt: (v: number) => `${v.toFixed(1)}%`,
      deltaDecimals: 1,
    };
  };
  const movers: MoverRow[] = [
    expMover("Household consumption"),
    expMover("Fixed investment"),
    expMover("Government consumption"),
    expMover("Exports"),
    expMover("Imports"),
  ];

  // BarRow cells are `number | string`, so the quarter key is stringified before
  // it becomes a column header.
  const prevQuarter = d.s2.at(-2)?.x != null ? String(d.s2.at(-2)!.x) : "Prior";
  const latestQuarter = gdpQuarter != null ? String(gdpQuarter) : "Latest";

  // ---- transmission: output → the banks ------------------------------------
  const consNow = lastVal(toPts(d.expYoY["Household consumption"] ?? []));
  const invNow = lastVal(toPts(d.expYoY["Fixed investment"] ?? []));
  const finNow = lastVal(toPts(d.prodYoY["Finance & insurance"] ?? []));
  const constrNow = lastVal(toPts(d.prodYoY["Construction"] ?? []));
  const transmission: TransmissionItem[] = [
    {
      k: "GDP, y/y",
      v: pct1(d.gdpYoY),
      effect: (
        <>
          The demand behind the loan book, and the denominator under every
          %-of-GDP ratio on the site. Output turns before{" "}
          <Link href="/asset-quality" className="font-semibold text-primary">
            NPL formation
          </Link>{" "}
          does, so this is the leading half of the credit-quality question.
        </>
      ),
    },
    {
      k: "Household consumption",
      v: pct1(consNow),
      effect: (
        <>
          The largest expenditure component, and the one that shows up first in
          card spending and{" "}
          <Link href="/credit" className="font-semibold text-primary">
            consumer credit
          </Link>
          . Retail demand is a volume signal for the unsecured book.
        </>
      ),
    },
    {
      k: "Fixed investment",
      v: pct1(invNow),
      effect: (
        <>
          Corporate capex is what long-tenor commercial lending funds. Investment
          is the component most sensitive to the real rate, so it carries the
          policy stance into the loan book.
        </>
      ),
    },
    {
      k: "Construction GVA",
      v: pct1(constrNow),
      effect: (
        <>
          Construction is a concentrated exposure for Turkish banks and a
          historically early source of problem loans — worth reading separately
          from the services aggregate it usually sits inside.
        </>
      ),
    },
    {
      k: "Finance & insurance GVA",
      v: pct1(finNow),
      effect: (
        <>
          The sector&rsquo;s own value added, on the production side of the
          accounts — the banks as an industry rather than as a lender to one.
        </>
      ),
    },
  ];

  // ---- flags ----------------------------------------------------------------
  const gdpFallRun = streak(gdp, "down");
  const importDrag = cell(d.s2.at(-1), "imports");
  const invContrib = cell(d.s2.at(-1), "investment");
  const flagList: Flag[] = [
    {
      code: "GDP_NEG",
      active: gdpNow != null && gdpNow < 0,
      rule: "gdp_yoy < 0",
      body: (
        <>
          <b className="font-semibold">Output is below its year-ago level.</b> GDP at{" "}
          {pct1(gdpNow)} y/y in {gdpQuarter ?? "the latest quarter"} — a contraction on
          the chain-volume index.
        </>
      ),
      clear: <>GDP is {pct1(gdpNow)} y/y — at or above its year-ago level.</>,
    },
    {
      code: "GDP_RUN",
      active: gdpFallRun >= 3,
      rule: "consecutive_fall(gdp_yoy) ≥ 3 quarters",
      body: (
        <>
          <b className="font-semibold">
            Growth has slowed for {gdpFallRun} quarters running.
          </b>{" "}
          Three consecutive lower y/y prints is a trend rather than a base effect.
        </>
      ),
      clear: <>The y/y growth rate has not fallen three quarters running.</>,
    },
    {
      code: "INV_NEG",
      active: invContrib != null && invContrib < 0,
      rule: "investment_contribution_pp < 0",
      body: (
        <>
          <b className="font-semibold">Investment is subtracting from growth.</b> Fixed
          capital formation contributed {pp(invContrib as number)} in{" "}
          {gdpQuarter ?? "the latest quarter"} — the component that funds long-tenor
          commercial lending.
        </>
      ),
      clear: (
        <>
          Investment contributed {invContrib != null ? pp(invContrib) : "—"} to growth —
          not a drag.
        </>
      ),
    },
    {
      code: "NET_TRADE_DRAG",
      active: importDrag != null && importDrag < -2,
      rule: "import_contribution_pp < −2pp",
      body: (
        <>
          <b className="font-semibold">Imports are a heavy drag on growth.</b> Import
          volumes subtracted {pp(importDrag as number)} in{" "}
          {gdpQuarter ?? "the latest quarter"} — domestic demand met from abroad, which
          lands in the current account.
        </>
      ),
      clear: (
        <>
          Imports contributed {importDrag != null ? pp(importDrag) : "—"} — inside the
          −2pp drag line.
        </>
      ),
    },
  ];

  const aheadItems = [
    ...(ahead.mpc ? [{ when: ahead.mpc.when, what: <>CBRT rate decision</>, href: "/rates" }] : []),
    { when: "quarterly", what: <>TÜİK national accounts — the next GDP release</> },
    { when: "monthly", what: <>TÜİK industrial production — the read between quarters</> },
  ];

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title="Economic Growth"
        record={
          <>
            Record <b className="font-normal text-foreground">{d.asOfLabel || "—"}</b> · quarterly
            TÜİK national accounts · chain-linked volume, y/y from the index
          </>
        }
        right="every figure computed from source series"
      />

      {/* ── The vitals ─────────────────────────────────────────────────── */}
      <SecHead
        title="The vitals"
        meta="headline · level · what added · what subtracted"
        className="mb-2.5 mt-6"
      />
      <Vitals cols={5}>
        <Vital
          label="GDP growth, y/y"
          value={gdpNow != null ? gdpNow.toFixed(1) : "—"}
          unit="%"
          series={gdp.slice(-13)}
          decimals={1}
          note={
            <>
              {gdpD != null ? `${signedPpStr(gdpD)} vs the prior quarter` : d.asOfLabel}
              {atWinHigh && <> · the fastest of the last 8 quarters</>}
              {atWinLow && <> · the slowest of the last 8 quarters</>}
            </>
          }
        />
        <Vital
          label="Nominal GDP, trailing 4Q"
          value={d.nominalAnnual == null ? "—" : `₺${d.nominalAnnual.toFixed(1)}`}
          unit="tn"
          format="raw"
          decimals={1}
          note={
            d.nominalQ != null ? (
              <>
                ₺{d.nominalQ.toFixed(1)} tn in {d.asOfLabel} alone · current prices
              </>
            ) : (
              "current prices, TÜİK"
            )
          }
        />
        <Vital
          label="Biggest contributor"
          value={topExp != null ? `${topExp.value >= 0 ? "+" : "−"}${Math.abs(topExp.value).toFixed(1)}` : "—"}
          unit="pp"
          series={topExp ? barSeries(d.s2, topExp.key).slice(-13) : undefined}
          format="raw"
          decimals={1}
          note={
            topExp != null && gdpNow != null ? (
              <>
                <em className="not-italic font-semibold text-foreground">{topExp.label}</em> — of the{" "}
                {gdpNow.toFixed(1)}% print, {d.asOfLabel}
              </>
            ) : (
              "expenditure-side contributions"
            )
          }
        />
        <Vital
          label="Biggest drag"
          value={dragExp != null ? `${dragExp.value >= 0 ? "+" : "−"}${Math.abs(dragExp.value).toFixed(1)}` : "—"}
          unit="pp"
          series={dragExp ? barSeries(d.s2, dragExp.key).slice(-13) : undefined}
          format="raw"
          decimals={1}
          note={
            dragExp != null ? (
              dragExp.value < 0 ? (
                <>
                  <em className="not-italic font-semibold text-negative">{dragExp.label}</em>{" "}
                  subtracted from growth, {d.asOfLabel}
                </>
              ) : (
                <>
                  no component subtracted — {dragExp.label} added the least
                </>
              )
            ) : (
              "expenditure-side contributions"
            )
          }
        />
        <Vital
          label="Fastest sector"
          value={topSec != null ? `${topSec.value >= 0 ? "+" : "−"}${Math.abs(topSec.value).toFixed(1)}` : "—"}
          unit="%"
          series={topSec ? barSeries(d.s3, topSec.key).slice(-13) : undefined}
          decimals={1}
          note={
            topSec != null && weakSec != null ? (
              <>
                <em className="not-italic font-semibold text-foreground">{topSec.label}</em> leads ·{" "}
                {weakSec.label} lags at {weakSec.value >= 0 ? "+" : "−"}
                {Math.abs(weakSec.value).toFixed(1)}%
              </>
            ) : (
              "gross value added by activity, y/y"
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
            title="The expenditure side"
            meta="y/y %, chain-volume · one national-accounts release"
            className="mb-2.5"
          />
          <Movers from={prevQuarter} to={latestQuarter} rows={movers} />
        </div>
        <div>
          <SecHead title="Transmission" meta="output → the banks · computed" className="mb-2.5" />
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
            quietNote="Every growth rule below was tested against the latest national accounts and none tripped."
          />
        </div>
        <div>
          <SecHead title="Ahead" meta="scraped calendar + fixed cadence" className="mb-2.5" />
          <Ahead items={aheadItems} />
        </div>
      </div>

      {/* ── In depth — the evidence layer ──────────────────────────────── */}
      <Depth action={<GlobalRangeSelector />}>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Stat
            label="GDP growth · y/y"
            value={pct1(d.gdpYoY)}
            hint={`${d.asOfLabel} · chain-linked volume`}
            tone={d.gdpYoY != null && d.gdpYoY < 0 ? "negative" : "positive"}
          />
          <Stat
            label="Nominal GDP · quarter"
            value={d.nominalQ == null ? "—" : `₺${d.nominalQ.toFixed(1)} tn`}
            hint={`current prices · ${d.asOfLabel}`}
          />
          <Stat
            label="Nominal GDP · annualized"
            value={d.nominalAnnual == null ? "—" : `₺${d.nominalAnnual.toFixed(1)} tn`}
            hint="current prices · trailing 4 quarters"
          />
        </div>

        {/* Five hardcoded numbers, a hardcoded quarter and three directional claims —
            all of them sitting in d.s2, which is the chart's own data prop one line
            below. The moment 2026-Q2 printed, the chart moved and the sentence did not. */}
        <Section
          title="GDP Growth & Contributions"
          description={growthRead ?? "GDP growth and the expenditure contributions behind it, y/y."}
        >
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <TimeSeriesChart
              series={d.s1}
              title="Şekil 1 · GDP Growth (y/y %, chain-linked volume)"
              yFormat="pct"
              xFormat="quarter"
              decimals={1}
            />
            <ChartCard title="Şekil 2 · Contributions to GDP Growth (y/y, pp)">
              <BopFlowChart
                data={d.s2}
                bars={[
                  { key: "consumption", label: "Consumption", fill: MAROON },
                  { key: "government", label: "Government", fill: AMBER },
                  { key: "investment", label: "Investment", fill: ORANGE },
                  { key: "inventories", label: "Inventories", fill: GREY },
                  { key: "exports", label: "Exports", fill: LBLUE },
                  { key: "imports", label: "Imports (−)", fill: DBLUE },
                ] satisfies BarSeries[]}
                line={{ key: "gdp", label: "GDP (y/y)", color: INK } satisfies OverlayLine}
                unit="%"
              />
            </ChartCard>
          </div>
        </Section>

        <Section
          title="Production Side"
          description={
            sectorRead ??
            "Gross value added by activity, y/y %. Figures use the unadjusted chain-volume index (see table note)."
          }
        >
          <ChartCard title="Şekil 3 · Sectoral Growth (y/y %)">
            <BopFlowChart
              data={d.s3}
              grouped
              bars={[
                { key: "agri", label: "Agriculture", fill: GREEN },
                { key: "industry", label: "Industry", fill: NAVY },
                { key: "constr", label: "Construction", fill: ORANGE },
                { key: "services", label: "Services", fill: AMBER },
              ] satisfies BarSeries[]}
              unit="%"
              height={340}
            />
          </ChartCard>
          <YoyTable
            table={d.prodTable}
            note="y/y from the unadjusted chain-volume index. TÜİK headlines a few sub-sectors (industry, manufacturing, services, public admin) on the calendar-adjusted series, which EVDS does not publish — those rows can differ by up to ~1.5 pp; the GDP total matches exactly."
          />
        </Section>

        <Section
          title="Expenditure Side"
          description="Demand components, y/y %. Consumption-by-durability and investment-by-type come from TÜİK's national-accounts detail (not in EVDS); government and the aggregates from EVDS."
        >
          {d.hasTuik && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <ChartCard title="Şekil 5 · Private Consumption by Durability (y/y %)">
                <BopFlowChart
                  data={d.s5cons}
                  grouped
                  bars={[
                    { key: "durable", label: "Durable", fill: MAROON },
                    { key: "semidur", label: "Semi-durable", fill: NAVY },
                    { key: "nondur", label: "Non-durable", fill: ORANGE },
                    { key: "services", label: "Services", fill: GREY },
                  ] satisfies BarSeries[]}
                  unit="%"
                  height={320}
                />
              </ChartCard>
              <ChartCard title="Şekil 4 · Investment by Type (y/y %)">
                <BopFlowChart
                  data={d.s4inv}
                  grouped
                  bars={[
                    { key: "construction", label: "Construction", fill: NAVY },
                    { key: "machinery", label: "Machinery & equipment", fill: ORANGE },
                    { key: "other", label: "Other assets", fill: GREY },
                  ] satisfies BarSeries[]}
                  unit="%"
                  height={320}
                />
              </ChartCard>
            </div>
          )}
          <ChartCard title="Şekil 6 · Government Consumption (y/y %)">
            <BopFlowChart
              data={d.s6}
              grouped
              bars={[{ key: "gov", label: "Government consumption", fill: ORANGE }] satisfies BarSeries[]}
              unit="%"
              height={300}
            />
          </ChartCard>
          <YoyTable
            table={d.expTable}
            note="Top-level expenditure aggregates from EVDS. The durable/semi/non-durable consumption (Şekil 5) and construction/machinery/other investment (Şekil 4) detail above is ingested from TÜİK's national-accounts Excel (chain-volume index, 2009=100; y/y derived)."
          />
        </Section>

        <p className="text-xs text-muted-foreground">
          <Link href="/economy" className="text-primary hover:underline">
            ← Economy
          </Link>{" "}
          · Source: TÜİK (TurkStat) quarterly national accounts via EVDS.{" "}
          <Link href="/economy/balance-of-payments" className="text-primary hover:underline">
            Balance of Payments →
          </Link>
        </p>
      </Depth>

      <Colophon>
        Compiled, not written — GDP growth, contributions and sectoral value added computed
        from TÜİK quarterly national accounts (chain-linked volume indices) via TCMB EVDS,
        plus the TÜİK national-accounts Excel detail for consumption and investment
        breakdowns. Contributions use the additive approximation; inventories are the
        residual. No forecasts. Analytical information, not investment advice.
      </Colophon>
    </main>
  );
}
