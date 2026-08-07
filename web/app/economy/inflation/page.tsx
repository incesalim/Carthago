/**
 * Inflation — reproduces the Albaraka "Enflasyon" monthly report from TÜİK
 * CPI/PPI series in EVDS: headline & core inflation, the CPI special-scope
 * core indices (A/B/C/D), the CPI-group and PPI-sector mix, and the monthly
 * history table.
 *
 * Data + derivations: app/lib/inflation.ts. Şekil 2/3 show m/m % per group
 * (the report's weighted contributions need TÜİK weights not in EVDS); the
 * PPI Main-Industrial-Groupings table is TÜİK-Excel-only and not wired.
 */
import type { Metadata } from "next";
import Link from "next/link";
import { getInflationData, type Table1Row, type CoreRow } from "@/app/lib/inflation";
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
import { monthLabel, signedPp, streak, valAgo, type Pt } from "@/app/lib/desk";
import { seriesFinding } from "@/app/lib/chart-findings";
import { inflationInsights } from "@/app/lib/insights";
import { aheadSlots } from "@/app/lib/ahead-data";
import { GlobalRangeSelector } from "@/app/components/range-context";
import { nf } from "@/app/lib/chart-format";
import { ChartCard } from "@/app/components/ui/chart-card";
import Takeaway from "@/app/components/Takeaway";
import TimeSeriesChart from "@/app/components/TimeSeriesChart";
import BopFlowChart, { type BarSeries } from "@/app/components/BopFlowChart";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkey Inflation — CPI & PPI",
  description: "Türkiye inflation — CPI, core inflation and producer prices (Yİ-ÜFE) from TÜİK.",
  alternates: { canonical: "/economy/inflation" },
};

const MAROON = { light: "#9c1f2f", dark: "#d65a5a" };
const GREEN = { light: "#3f7d3f", dark: "#6bbf6b" };

function Grid({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">{children}</div>;
}

const pct = (v: number | null, d = 2) => (v == null ? "—" : `${nf(v, d)}%`);

/** EVDS rows ({period_date}) → the desk helpers' Pt shape ({period}). */
const toPts = (s: { period_date: string; value: number }[] | undefined): Pt[] =>
  (s ?? []).map((r) => ({ period: r.period_date, value: r.value }));

/** Mean of the trailing 12 y/y prints (the 12-month average inflation read). */
const mean12 = (s: Pt[], skip = 0): number | null => {
  const end = s.length - skip;
  const w = s.slice(Math.max(0, end - 12), end).filter((p) => p.value != null);
  if (w.length < 12) return null;
  return w.reduce((a, p) => a + (p.value as number), 0) / 12;
};

export default async function InflationPage() {
  const [d, ahead] = await Promise.all([getInflationData(), aheadSlots()]);

  // ---- the brief's computed vitals ------------------------------------------
  // Every cell below is derived from the series this page already fetches.
  const cpi = toPts(d.s1["CPI (y/y)"]);
  const core = toPts(d.s1["Core C (y/y)"]);
  const ppi = toPts(d.s1["PPI / Yİ-ÜFE (y/y)"]);
  const mom = toPts(d.cpiMoM);
  const diff = toPts(d.diffusion);
  const exp = toPts(d.exp12m);

  const cpiAgo = valAgo(cpi, 12);
  const cpiD12 = d.cpiYoY != null && cpiAgo != null ? d.cpiYoY - cpiAgo : null;
  const cpiFall = streak(cpi, "down");

  const avg12 = mean12(cpi);
  const avg12Prev = mean12(cpi, 1);
  const avg12D = avg12 != null && avg12Prev != null ? avg12 - avg12Prev : null;

  const coreGap =
    d.coreYoY != null && d.cpiYoY != null ? d.coreYoY - d.cpiYoY : null;
  const coreRowC = d.core.find((r) => r.label.startsWith("C "));

  const ppiGap = d.ppiYoY != null && d.cpiYoY != null ? d.ppiYoY - d.cpiYoY : null;

  // Monthly CPI — table1 is newest-first, so reverse it for the sparkline.
  const cpiMoM: Pt[] = d.table1
    .slice()
    .reverse()
    .map((r) => ({ period: r.month, value: r.cpiMM }));
  const mmNow = d.table1[0]?.cpiMM ?? null;
  const mmPrev = d.table1[1]?.cpiMM ?? null;
  const mmD = mmNow != null && mmPrev != null ? mmNow - mmPrev : null;

  // ---- "The Read" — computed from the same series the charts show ----------
  const read = inflationInsights({
    cpi,
    core,
    ppi,
    cpiMoM: mom,
    exp12m: exp,
    diffusion: d.diffusionNow,
    diffusionOf: d.diffusionOf,
  });

  // ---- movers: the groups that moved, not the groups that are high ---------
  // Ranked by |Δ| on the monthly print, so a group sitting still at a high level
  // does not crowd out the one that turned. Eight rows: enough to carry the
  // month, short enough to read.
  const groupMovers: MoverRow[] = d.groupMoves.slice(0, 8).map((r) => ({
    label: r.label,
    prev: r.prev,
    curr: r.curr,
    good: "down",
    fmt: (v: number) => `${v.toFixed(2)}%`,
    deltaDecimals: 2,
  }));

  // ---- transmission: prices → the banks ------------------------------------
  const realDrift = d.cpiYoY;
  const transmission: TransmissionItem[] = [
    {
      k: "Headline CPI, y/y",
      v: pct(d.cpiYoY, 1),
      effect: (
        <>
          The deflator on every nominal balance-sheet line. A book growing slower than
          this is shrinking in real terms, which is why{" "}
          <Link href="/credit" className="font-semibold text-primary">
            the loan book
          </Link>{" "}
          is read against the price level rather than in lira alone.
        </>
      ),
    },
    {
      k: "Core-C, y/y",
      v: pct(d.coreYoY, 1),
      effect:
        d.coreYoY != null && d.cpiYoY != null ? (
          <>
            Underlying prices sit {Math.abs(d.coreYoY - d.cpiYoY).toFixed(1)}pp{" "}
            {d.coreYoY >= d.cpiYoY ? "above" : "below"} the headline. Core is what the
            CBRT&rsquo;s reaction function tracks, so it — not the headline — is the
            better read on where{" "}
            <Link href="/rates" className="font-semibold text-primary">
              policy
            </Link>{" "}
            goes next.
          </>
        ) : (
          "Underlying prices, with energy, food, alcohol-tobacco and gold stripped out."
        ),
    },
    {
      k: "Yİ-ÜFE, y/y",
      v: pct(d.ppiYoY, 1),
      effect:
        d.ppiYoY != null && d.cpiYoY != null ? (
          <>
            Producer prices run {Math.abs(d.ppiYoY - d.cpiYoY).toFixed(1)}pp{" "}
            {d.ppiYoY >= d.cpiYoY ? "above" : "below"} consumer prices — the cost-push
            pipeline. Where producers cannot pass costs through, the squeeze lands on
            corporate margins and then on{" "}
            <Link href="/asset-quality" className="font-semibold text-primary">
              credit quality
            </Link>
            .
          </>
        ) : (
          "Domestic producer prices — the cost-push pipeline into consumer prices."
        ),
    },
    {
      k: "Breadth",
      v: d.diffusionNow != null ? `${Math.round(d.diffusionNow)}%` : "—",
      effect: (
        <>
          The share of the {d.diffusionOf} COICOP groups printing above the headline.
          Breadth is what separates a relative-price shock from a general one — the
          first fades on its own, the second has to be paid for in rates.
        </>
      ),
    },
    {
      k: "12m expectation",
      v: pct(d.exp12mNow, 1),
      effect:
        d.exp12mNow != null && realDrift != null ? (
          <>
            The market prices {d.exp12mNow.toFixed(1)}% a year out, {Math.abs(d.exp12mNow - realDrift).toFixed(1)}pp{" "}
            {d.exp12mNow >= realDrift ? "above" : "below"} today&rsquo;s print. This is
            the number every real rate on the site is deflated by, so it sets what a
            deposit is expected to be worth.
          </>
        ) : (
          "The CBRT survey's 12-month-ahead market expectation — the deflator behind every ex-ante real rate here."
        ),
    },
  ];

  // ---- flags ----------------------------------------------------------------
  const mmRun = streak(mom, "up");
  const coreGapNow = d.coreYoY != null && d.cpiYoY != null ? d.coreYoY - d.cpiYoY : null;
  const ppiGapNow = d.ppiYoY != null && d.cpiYoY != null ? d.ppiYoY - d.cpiYoY : null;
  const flagList: Flag[] = [
    {
      code: "CORE_ABOVE",
      active: coreGapNow != null && coreGapNow > 0,
      rule: "core_c_yoy > headline_yoy",
      body: (
        <>
          <b className="font-semibold">Underlying inflation is above the headline.</b>{" "}
          Core-C at {pct(d.coreYoY, 1)} against {pct(d.cpiYoY, 1)} means the headline is
          being held down by the volatile items core excludes, not by the trend.
        </>
      ),
      clear: (
        <>
          Core-C {pct(d.coreYoY, 1)} against a {pct(d.cpiYoY, 1)} headline — underlying
          is at or below the headline.
        </>
      ),
    },
    {
      code: "PPI_PIPELINE",
      active: ppiGapNow != null && ppiGapNow > 5,
      rule: "ppi_yoy − cpi_yoy > 5pp",
      body: (
        <>
          <b className="font-semibold">Producer prices lead consumer prices by more than 5pp.</b>{" "}
          Yİ-ÜFE at {pct(d.ppiYoY, 1)} against {pct(d.cpiYoY, 1)} — unpassed cost sitting
          in the pipeline.
        </>
      ),
      clear: (
        <>
          Producer prices run {ppiGapNow != null ? `${signedPp(ppiGapNow, 1)}` : "—"} against
          consumer prices — inside the 5pp line.
        </>
      ),
    },
    {
      code: "BROAD",
      active: d.diffusionNow != null && d.diffusionNow > 60,
      rule: "share_of_groups_above_headline > 60%",
      body: (
        <>
          <b className="font-semibold">The monthly move is broad.</b>{" "}
          {d.diffusionNow != null ? Math.round((d.diffusionNow / 100) * d.diffusionOf) : "—"} of{" "}
          {d.diffusionOf} groups printed above the headline — a general price move rather
          than a few heavy items.
        </>
      ),
      clear: (
        <>
          {d.diffusionNow != null ? Math.round((d.diffusionNow / 100) * d.diffusionOf) : "—"} of{" "}
          {d.diffusionOf} groups printed above the headline — inside the 60% breadth line.
        </>
      ),
    },
    {
      code: "MM_RUN",
      active: mmRun >= 3,
      rule: "consecutive_rise(cpi_m/m) ≥ 3",
      body: (
        <>
          <b className="font-semibold">The monthly print has risen {mmRun} months running.</b>{" "}
          The annual rate is assembled from these, so a run sets the floor under the next
          few readings before any base effect.
        </>
      ),
      clear: <>The monthly print has not risen three months running.</>,
    },
    {
      code: "EXP_ABOVE",
      active: d.exp12mNow != null && d.cpiYoY != null && d.exp12mNow > d.cpiYoY,
      rule: "expectation_12m_ahead > headline_yoy",
      body: (
        <>
          <b className="font-semibold">The market expects more inflation than it is seeing.</b>{" "}
          {pct(d.exp12mNow, 1)} expected twelve months out against a {pct(d.cpiYoY, 1)}{" "}
          print — disinflation the survey does not yet believe.
        </>
      ),
      clear: (
        <>
          The 12m-ahead expectation is {pct(d.exp12mNow, 1)} against a {pct(d.cpiYoY, 1)}{" "}
          print — at or below the current rate.
        </>
      ),
    },
  ];

  const aheadItems = [
    { when: "3rd", what: <>TÜİK CPI &amp; Yİ-ÜFE — next month&rsquo;s print</> },
    ...(ahead.mpc
      ? [{ when: ahead.mpc.when, what: <>CBRT rate decision</>, href: "/rates" }]
      : []),
    ...(ahead["inflation-report"]
      ? [{ when: ahead["inflation-report"].when, what: <>CBRT Inflation Report — the forecast path</> }]
      : []),
    { when: "monthly", what: <>CBRT Survey of Market Participants — the expectation above</> },
  ];

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title="Inflation"
        record={
          <>
            Record <b className="font-normal text-foreground">{monthLabel(d.latestPeriod)}</b> ·
            monthly TÜİK CPI &amp; Yİ-ÜFE via EVDS · y/y, m/m and cores derived from the index
          </>
        }
        right="every figure computed from source series"
      />

      {/* ── The vitals ─────────────────────────────────────────────────── */}
      <SecHead
        title="The vitals"
        meta="headline · trend · underlying · cost push"
        className="mb-2.5 mt-6"
      />
      <Vitals cols={5}>
        <Vital
          label="CPI, y/y"
          value={d.cpiYoY != null ? d.cpiYoY.toFixed(1) : "—"}
          unit="%"
          series={cpi.slice(-13)}
          decimals={1}
          note={
            <>
              {cpiD12 != null ? `${signedPp(cpiD12, 1)} over 12m` : `TÜFE · ${d.asOfLabel}`}
              {cpiFall >= 3 && (
                <>
                  {" "}
                  ·{" "}
                  <em className="not-italic font-semibold text-positive">
                    {cpiFall} straight monthly falls
                  </em>
                </>
              )}
            </>
          }
        />
        <Vital
          label="CPI, 12m average"
          value={avg12 != null ? avg12.toFixed(1) : "—"}
          unit="%"
          decimals={1}
          note={
            avg12 != null && d.cpiYoY != null ? (
              <>
                mean of the trailing 12 y/y prints
                {avg12D != null && <> · {signedPp(avg12D, 1)} on the month</>} — headline is{" "}
                {d.cpiYoY < avg12 ? "below" : "above"} it
              </>
            ) : (
              "mean of the trailing 12 y/y prints"
            )
          }
        />
        <Vital
          label="Core CPI (C), y/y"
          value={d.coreYoY != null ? d.coreYoY.toFixed(1) : "—"}
          unit="%"
          series={core.slice(-13)}
          decimals={1}
          note={
            coreGap != null ? (
              <>
                <em
                  className={
                    coreGap <= 0
                      ? "not-italic font-semibold text-positive"
                      : "not-italic font-semibold text-negative"
                  }
                >
                  {signedPp(coreGap, 1)} vs headline
                </em>{" "}
                — excl. energy, food, alcohol-tobacco, gold
                {coreRowC?.mm != null && <> · {pct(coreRowC.mm, 1)} m/m</>}
              </>
            ) : (
              "C index — the cleanest underlying read"
            )
          }
        />
        <Vital
          label="Yİ-ÜFE (PPI), y/y"
          value={d.ppiYoY != null ? d.ppiYoY.toFixed(1) : "—"}
          unit="%"
          series={ppi.slice(-13)}
          decimals={1}
          note={
            ppiGap != null ? (
              <>
                producer prices run{" "}
                <em
                  className={
                    ppiGap > 0
                      ? "not-italic font-semibold text-negative"
                      : "not-italic font-semibold text-positive"
                  }
                >
                  {signedPp(ppiGap, 1)}
                </em>{" "}
                vs consumer prices — the cost-push pipeline
              </>
            ) : (
              "domestic producer prices, TÜİK"
            )
          }
        />
        <Vital
          label="CPI, m/m"
          value={mmNow != null ? mmNow.toFixed(2) : "—"}
          unit="%"
          series={cpiMoM.slice(-13)}
          decimals={2}
          note={
            <>
              {mmD != null && d.table1[1]
                ? `${signedPp(mmD, 2)} vs ${d.table1[1].month}`
                : `latest print · ${d.asOfLabel}`}{" "}
              ·{" "}
              <Link href="/economy" className="font-semibold text-primary">
                /economy
              </Link>
            </>
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
            title="What moved"
            meta={`coicop groups · ${d.asOfLabel} m/m vs prior month`}
            className="mb-2.5"
          />
          <Movers from="Prior m/m" to={`${d.asOfLabel} m/m`} rows={groupMovers} />
        </div>
        <div>
          <SecHead title="Transmission" meta="prices → the banks · computed" className="mb-2.5" />
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
            quietNote="Every price rule below was tested against the current print and none tripped."
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
          <Stat label="CPI · y/y" value={pct(d.cpiYoY)} hint={`TÜFE · ${d.asOfLabel}`} tone="warning" />
          <Stat label="PPI · y/y" value={pct(d.ppiYoY)} hint={`Yİ-ÜFE · ${d.asOfLabel}`} tone="warning" />
          <Stat label="Core CPI · y/y" value={pct(d.coreYoY)} hint={`C index · ${d.asOfLabel}`} tone="warning" />
        </div>

        {/* ── NEW: how broad is it? ────────────────────────────────────── */}
        <Section
          title="Breadth"
          description={
            d.diffusionNow != null
              ? `${Math.round((d.diffusionNow / 100) * d.diffusionOf)} of ${d.diffusionOf} COICOP groups printed a monthly change above the headline's. A headline can move on two heavy groups while the rest of the basket does nothing — this counts groups, so it says how broad the move is, never how large.`
              : "Share of COICOP groups printing above the headline monthly change."
          }
        >
          <Grid>
            <TimeSeriesChart
              series={{ "Groups above the headline m/m": d.diffusion }}
              title={
                seriesFinding(diff, { noun: "Breadth", decimals: 0 }) ??
                "CPI Diffusion — Share of Groups Above the Headline (%)"
              }
              description={`Share of the ${d.diffusionOf} COICOP main groups whose monthly change exceeds the headline's. A month is plotted only when every group reports, so the denominator never moves.`}
              yFormat="pct"
              decimals={0}
            />
            <TimeSeriesChart
              series={{ "CPI (y/y)": d.s1["CPI (y/y)"], "12m-ahead expectation": d.exp12m }}
              title="The Print Against What Was Expected (%)"
              description="Headline y/y and the CBRT survey's 12-month-ahead market expectation on one axis — the expectation is a forecast of the next twelve months, not of this print."
              yFormat="pct"
              decimals={1}
              hero="CPI (y/y)"
            />
          </Grid>
        </Section>

        <Section
          title="Headline & Core Inflation"
          description="Annual CPI, core-C and producer-price inflation. Core C strips out energy, food, alcohol-tobacco and gold — the cleanest read on underlying trend."
        >
          <Grid>
            <TimeSeriesChart
              series={d.s1}
              title="Şekil 1 · Inflation Indicators (y/y %)"
              yFormat="pct"
              decimals={1}
            />
            <TimeSeriesChart
              series={d.s6}
              title="Şekil 6 · Core Inflation — C Index (% change)"
              yFormat="pct"
              decimals={1}
            />
          </Grid>
          <Table wrapperClassName="rounded-[10px] border border-border bg-card">
            <TableHeader>
              <TableRow className="bg-muted/50">
                <TableHead>Core index</TableHead>
                <TableHead className="text-right">Monthly</TableHead>
                <TableHead className="text-right">Since Dec</TableHead>
                <TableHead className="text-right">Annual</TableHead>
                <TableHead className="text-right">12m avg</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {d.core.map((r: CoreRow) => (
                <TableRow
                  key={r.label}
                  className={r.label.startsWith("C ") ? "bg-accent/30 font-semibold" : undefined}
                >
                  <TableCell className="py-1.5">{r.label}</TableCell>
                  <TableCellNum tone={toneFor(r.mm)} className="py-1.5">{pct(r.mm)}</TableCellNum>
                  <TableCellNum tone={toneFor(r.cum)} className="py-1.5">{pct(r.cum)}</TableCellNum>
                  <TableCellNum tone={toneFor(r.yy)} className="py-1.5">{pct(r.yy)}</TableCellNum>
                  <TableCellNum tone={toneFor(r.avg12)} className="py-1.5">{pct(r.avg12)}</TableCellNum>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Section>

        <Section
          title="Consumer Prices by Group"
          description={`Monthly % change by COICOP main group, ${d.asOfLabel}. The report plots weighted contributions to monthly inflation; shown here as each group's m/m change (TÜİK group weights aren't published in EVDS) — leaders & signs match, magnitudes scale by weight.`}
        >
          <Grid>
            <ChartCard title="Şekil 2 · CPI Groups (monthly % change)">
              <BopFlowChart
                data={d.s2}
                grouped
                bars={[{ key: "mm", label: "Monthly % change", fill: MAROON }] satisfies BarSeries[]}
                unit="%"
                height={340}
              />
            </ChartCard>
            <TimeSeriesChart
              series={d.s4}
              title="Şekil 4 · Clothing & Footwear (monthly %)"
              yFormat="pct"
              decimals={1}
            />
          </Grid>
        </Section>

        <Section
          title="Producer Prices (Yİ-ÜFE)"
          description={`Domestic PPI by NACE sub-sector, monthly % change, ${d.asOfLabel}. Energy and refining swings dominate producer-cost pressure.`}
        >
          <Grid>
            <ChartCard title="Şekil 3 · PPI Sub-sectors (monthly % change)">
              <BopFlowChart
                data={d.s3}
                grouped
                bars={[{ key: "mm", label: "Monthly % change", fill: GREEN }] satisfies BarSeries[]}
                unit="%"
                height={340}
              />
            </ChartCard>
            <TimeSeriesChart
              series={d.s5}
              title="Şekil 5 · Electricity & Gas Production (monthly %)"
              yFormat="pct"
              decimals={1}
            />
          </Grid>
          {d.hasMig && (
            <div className="space-y-2">
              <Table wrapperClassName="rounded-[10px] border border-border bg-card">
                <TableHeader>
                  <TableRow className="bg-muted/50">
                    <TableHead>Main Industrial Grouping</TableHead>
                    <TableHead className="text-right">Monthly</TableHead>
                    <TableHead className="text-right">Annual</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {d.mig.map((r) => (
                    <TableRow key={r.label}>
                      <TableCell className="py-1.5">{r.label}</TableCell>
                      <TableCellNum tone={toneFor(r.mm)} className="py-1.5">{pct(r.mm)}</TableCellNum>
                      <TableCellNum tone={toneFor(r.yy)} className="py-1.5">{pct(r.yy)}</TableCellNum>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <p className="text-xs text-muted-foreground">
                Producer prices by Main Industrial Grouping — ingested from TÜİK&apos;s
                bulletin (Domestic PPI MIG, 2003=100; m/m and y/y derived). Not in EVDS.
              </p>
            </div>
          )}
        </Section>

        <Section
          title="Monthly History"
          description="CPI (TÜFE) and PPI (Yİ-ÜFE), monthly and annual % change."
        >
          <Table wrapperClassName="rounded-[10px] border border-border bg-card">
            <TableHeader>
              <TableRow className="bg-muted/50">
                <TableHead />
                <TableHead className="text-right" colSpan={2}>
                  CPI (TÜFE)
                </TableHead>
                <TableHead className="text-right" colSpan={2}>
                  PPI (Yİ-ÜFE)
                </TableHead>
              </TableRow>
              <TableRow>
                <TableHead>Month</TableHead>
                <TableHead className="text-right">m/m</TableHead>
                <TableHead className="text-right">y/y</TableHead>
                <TableHead className="text-right">m/m</TableHead>
                <TableHead className="text-right">y/y</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {d.table1.map((r: Table1Row, i) => (
                <TableRow key={r.month} className={i === 0 ? "bg-accent/30 font-semibold" : undefined}>
                  <TableCell className="py-1.5">{r.month}</TableCell>
                  <TableCellNum tone={toneFor(r.cpiMM)} className="py-1.5">{pct(r.cpiMM)}</TableCellNum>
                  <TableCellNum tone={toneFor(r.cpiYY)} className="py-1.5">{pct(r.cpiYY)}</TableCellNum>
                  <TableCellNum tone={toneFor(r.ppiMM)} className="py-1.5">{pct(r.ppiMM)}</TableCellNum>
                  <TableCellNum tone={toneFor(r.ppiYY)} className="py-1.5">{pct(r.ppiYY)}</TableCellNum>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <p className="text-xs text-muted-foreground">
            <Link href="/economy" className="text-primary hover:underline">
              ← Economy
            </Link>{" "}
            · Source: TÜİK (TurkStat) CPI &amp; domestic PPI via EVDS. The
            producer-price Main Industrial Groupings breakdown (intermediate /
            durable / energy / capital goods) is published only in TÜİK&apos;s
            bulletin, not EVDS — not shown here.{" "}
            <Link href="/economy/budget" className="text-primary hover:underline">
              Budget →
            </Link>
          </p>
        </Section>
      </Depth>

      <Colophon>
        Compiled, not written — headline, core (A/B/C/D), group and producer-price figures
        computed from TÜİK CPI (2025=100) and domestic Yİ-ÜFE index levels via TCMB EVDS,
        plus the TÜİK bulletin&rsquo;s PPI Main-Industrial-Groupings detail. m/m, y/y,
        since-December and 12-month averages are derived from the index. No forecasts.
        Analytical information, not investment advice.
      </Colophon>
    </main>
  );
}
