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
  Colophon,
  Depth,
  DeskHeader,
  SecHead,
  Vital,
  Vitals,
} from "@/app/components/desk";
import { monthLabel, signedPp, streak, valAgo, type Pt } from "@/app/lib/desk";
import { GlobalRangeSelector } from "@/app/components/range-context";
import { nf } from "@/app/lib/chart-format";
import { ChartCard } from "@/app/components/ui/chart-card";
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
  const d = await getInflationData();

  // ---- the brief's computed vitals ------------------------------------------
  // Every cell below is derived from the series this page already fetches.
  const cpi = toPts(d.s1["CPI (y/y)"]);
  const core = toPts(d.s1["Core C (y/y)"]);
  const ppi = toPts(d.s1["PPI / Yİ-ÜFE (y/y)"]);

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

      {/* ── In depth — the evidence layer ──────────────────────────────── */}
      <Depth action={<GlobalRangeSelector />}>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Stat label="CPI · y/y" value={pct(d.cpiYoY)} hint={`TÜFE · ${d.asOfLabel}`} tone="warning" />
          <Stat label="PPI · y/y" value={pct(d.ppiYoY)} hint={`Yİ-ÜFE · ${d.asOfLabel}`} tone="warning" />
          <Stat label="Core CPI · y/y" value={pct(d.coreYoY)} hint={`C index · ${d.asOfLabel}`} tone="warning" />
        </div>

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
