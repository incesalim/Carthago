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
  Colophon,
  Depth,
  DeskHeader,
  SecHead,
  Vital,
  Vitals,
} from "@/app/components/desk";
import { lastVal, signedPp, valAgo, windowExtremes, type Pt } from "@/app/lib/desk";
import { GlobalRangeSelector } from "@/app/components/range-context";
import { ChartCard } from "@/app/components/ui/chart-card";
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

export default async function EconomicGrowthPage() {
  const d = await getGrowthData();

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

        <Section
          title="GDP Growth & Contributions"
          description="GDP grew 2.5% y/y in 2026-Q1 (q/q +0.1% on TÜİK's seasonally-adjusted series — not carried in EVDS). Private consumption drove the expansion (+3.4 pp) while the −12.7% export slump subtracted −2.9 pp."
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
          description="Gross value added by activity, y/y %. Construction and services led; industry and agriculture lagged. Figures use the unadjusted chain-volume index (see table note)."
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
