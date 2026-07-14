/**
 * Economy tab — adapts the Türkiye macro section of the BBVA (Garanti BBVA
 * Research) "Türkiye Economic Outlook" into our data.
 *
 * Structure mirrors the report: growth & activity, labor market, inflation
 * & monetary policy, lira & external balance, fiscal stance — closed by
 * BBVA's published baseline scenario table for context.
 *
 * Out of scope (no data source here): CDS spreads, OIS pricing and
 * sovereign yield curves (Bloomberg), the GDP nowcast and the FCI composite
 * (BBVA-proprietary), and foreigners' positioning flows.
 */
import type { Metadata } from "next";
import Link from "next/link";
import { getEconomyData, BBVA_BASELINE, type Point } from "@/app/lib/economy";
import { bistIndexHistory, type PricePoint } from "@/app/lib/bist";
import { liveQuotes, type LiveQuote } from "@/app/lib/bist-live";
import { getMarketTicker } from "@/app/lib/market-ticker";
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
  SecHead,
  Vital,
  Vitals,
} from "@/app/components/desk";
import { lastVal, monthLabel, signedPp, streak, valAgo, windowExtremes, type Pt } from "@/app/lib/desk";
import { VERBS, direction, signed } from "@/app/lib/prose";
import { seriesFinding } from "@/app/lib/chart-findings";
import { GlobalRangeSelector } from "@/app/components/range-context";
import { fmtQuarter } from "@/app/lib/chart-format";
import MarketTicker from "@/app/components/MarketTicker";
import TimeSeriesChart from "@/app/components/TimeSeriesChart";

/** Rebase a level series to 100 at the first point, for cross-index comparison. */
function rebase100(pts: PricePoint[]): PricePoint[] {
  const base = pts.find((p) => p.value)?.value;
  if (!base) return pts;
  return pts.map((p) => ({ period_date: p.period_date, value: (p.value / base) * 100 }));
}

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
  description: "Türkiye's macro backdrop for the banking sector — growth, inflation, budget, balance of payments and foreign trade from official data.",
  alternates: { canonical: "/economy" },
};

function Grid({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">{children}</div>;
}

/** EVDS points ({period_date}) → the shape the finding engine reads. */
const asPts = (p: Point[]): Pt[] => p.map((r) => ({ period: r.period_date, value: r.value }));

export default async function EconomyPage() {
  const d = await getEconomyData();

  const ticker = await getMarketTicker();
  const bistIdx = await bistIndexHistory(8);
  const bistRebased = Object.fromEntries(
    Object.entries(bistIdx).map(([label, pts]) => [label, rebase100(pts)]),
  );
  const hasBist = Object.values(bistRebased).some((s) => s.length > 0);

  // Append a live (delayed) final point to each rebased index series, in the
  // same rebased scale (live level ÷ the series' base × 100). No-op on failure.
  const idxLabel: Record<string, string> = { XU100: "BIST 100", XBANK: "BIST Banks" };
  const liveIdx: Map<string, LiveQuote> = hasBist
    ? await liveQuotes(["XU100", "XBANK"])
    : new Map();
  let bistLivePoint = false;
  for (const [sym, q] of liveIdx) {
    const label = idxLabel[sym];
    const base = label ? bistIdx[label]?.find((p) => p.value)?.value : undefined;
    const series = label ? bistRebased[label] : undefined;
    if (!base || !series || series.length === 0) continue;
    series.push({ period_date: new Date(q.asOf * 1000).toISOString().slice(0, 10), value: (q.price / base) * 100 });
    bistLivePoint = true;
  }
  const bistSubtitle =
    "Borsa İstanbul benchmark vs the banking sector, rebased to 100 — does the banks index lead or lag the broad market? (Yahoo Finance, daily close" +
    (bistLivePoint ? " · last point live, ~15-min delayed)" : ".)");

  // ---- the brief's computed vitals ------------------------------------------
  // Every cell below is derived from a series this page already fetches.
  const cpi = toPts(d.cpiYoY);
  const gdp = toPts(d.gdpGrowth);
  const fund = toPts(d.fundingMonthly);
  const usd = toPts(d.usdtry);
  const unemp = toPts(d.unemployment);
  const part = toPts(d.participation);
  const ca = toPts(d.ca12m);

  const cpiNow = lastVal(cpi);
  const cpiAgo = valAgo(cpi, 12);
  const cpiD12 = cpiNow != null && cpiAgo != null ? cpiNow - cpiAgo : null;
  const cpiFall = streak(cpi, "down");

  const gdpNow = lastVal(gdp);
  const gdpPrev = valAgo(gdp, 1);
  const gdpD = gdpNow != null && gdpPrev != null ? gdpNow - gdpPrev : null;
  const gdpQuarter = d.gdpGrowth.at(-1)?.period_date;

  const fundNow = lastVal(fund);
  const realNow = lastVal(toPts(d.realRate));
  const exp12Now = lastVal(toPts(d.exp12m));

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
  const caXgeNow = lastVal(toPts(d.caExGoldEnergy12m));

  // The section reads. These descriptions used to carry third-party claims from a
  // March-2026 outlook — "industrial momentum stays weak", "disinflation
  // decelerated even before the conflict", "every 10% rise in energy prices costs
  // ~0.3–0.4% of GDP" — typed into a prop that a reader parses as methodology.
  // Where we hold the series the sentence is ours and recomputes; where the claim
  // was causal, an elasticity, or a judgment, it is gone rather than fabricated.
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
  const primNow = lastVal(toPts(d.primaryPctGdp));

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title="Economy"
        record={
          <>
            Record <b className="font-normal text-foreground">{monthLabel(d.cpiYoY.at(-1)?.period_date)}</b>{" "}
            · monthly EVDS · GDP quarterly ({gdpQuarter ? fmtQuarter(gdpQuarter) : "—"})
          </>
        }
        right="every figure computed from source series"
      />

      {ticker.length > 0 && (
        <div className="mt-3">
          <MarketTicker items={ticker} />
        </div>
      )}

      {/* ── The vitals ─────────────────────────────────────────────────── */}
      <SecHead
        title="The vitals"
        meta="policy · prices · activity · lira · external"
        className="mb-2.5 mt-6"
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
                <em
                  className={
                    realNow >= 0
                      ? "not-italic font-semibold text-positive"
                      : "not-italic font-semibold text-negative"
                  }
                >
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
                lira{" "}
                <em
                  className={
                    usdYoY >= 0
                      ? "not-italic font-semibold text-negative"
                      : "not-italic font-semibold text-positive"
                  }
                >
                  {usdYoY >= 0 ? "weaker" : "stronger"} by {Math.abs(usdYoY).toFixed(1)}%
                </em>{" "}
                over 12 months
              </>
            ) : (
              "daily CBRT selling rate"
            )
          }
        />
        <Vital
          label="Unemployment, SA"
          value={unempNow != null ? unempNow.toFixed(1) : "—"}
          unit="%"
          series={unemp.slice(-13)}
          decimals={1}
          note={
            <>
              {unempD12 != null ? `${signedPp(unempD12, 1)} over 12m` : "TÜİK labour force survey"}
              {partNow != null && <> · participation {partNow.toFixed(1)}%</>}
            </>
          }
        />
        <Vital
          label="Current account, 12m"
          value={caNow != null ? signed(caNow) : "—"}
          unit="USD bn"
          series={ca.slice(-13)}
          format="raw"
          decimals={1}
          note={
            caXgeNow != null ? (
              <>
                {signed(caXgeNow)} bn excluding gold &amp; energy — the structural read
              </>
            ) : (
              "rolling 12-month sum, balance of payments"
            )
          }
        />
      </Vitals>

      {/* ── In depth — the evidence layer ──────────────────────────────── */}
      <Depth action={<GlobalRangeSelector />}>
        {/* These section descriptions used to be third-party claims lifted from a
            March-2026 outlook — "industrial momentum stays weak", "disinflation
            decelerated even before the conflict" — typed into a prop that reads as
            methodology. Where we hold the series, the sentence is now ours and
            recomputes. Where the claim was causal, an elasticity, or a report's
            judgment, it is gone rather than dressed up: we will not fabricate it. */}
        <Section
          title="Growth & Activity"
          description={
            [
              seriesFinding(asPts(d.gdpGrowth), {
                noun: "GDP growth",
                decimals: 1,
                window: 4,
                windowLabel: "4 quarters",
              }),
              seriesFinding(asPts(d.ipGrowth), { noun: "industrial production", decimals: 1 }),
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
                ? `Unemployment ${unempNow.toFixed(1)}%${unAtLow ? " — the lowest in the window we hold" : ""}`
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
            seriesFinding(asPts(d.cpiYoY), { noun: "CPI", decimals: 1 }) ??
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
              series={{ "USD/TRY": d.usdtry }}
              title="USD/TRY"
              yFormat="fx"
              decimals={2}
            />
            <TimeSeriesChart
              series={{ "REER (CPI based)": d.reer }}
              title="Real Effective Exchange Rate (2003 = 100)"
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
            />
            <TimeSeriesChart
              series={{ "Net errors & omissions": d.neo12m }}
              title="Net Errors & Omissions (12m rolling, USD bn)"
              yFormat="raw"
              decimals={1}
            />
          </Grid>
        </Section>

        {hasBist && (
          <Section
            title="Equity Markets (BIST)"
            description={bistSubtitle}
          >
            <ChartRow
              data={tsRows(bistRebased)}
              deltaPeriods={252}
              deltaLabel="1y"
              fmt={(v) => v.toFixed(0)}
            >
              <TimeSeriesChart
                series={bistRebased}
                title="BIST 100 vs Banks (rebased to 100)"
                yFormat="raw"
                decimals={0}
                height={340}
              />
            </ChartRow>
          </Section>
        )}

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

        <Section
          title="BBVA Baseline Scenario"
          description={`${BBVA_BASELINE.source} (${BBVA_BASELINE.asOf}). Forecasts assume a short-lived conflict; biases are to higher inflation and weaker growth if it lasts.`}
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
              </TableRow>
            </TableHeader>
            <TableBody>
              {BBVA_BASELINE.rows.map((r) => (
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
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Section>
      </Depth>

      <Colophon>
        Compiled, not written — growth, labour, prices, lira, external and fiscal series
        computed from TCMB EVDS (TÜİK · CBRT · Treasury); BIST index levels from Yahoo
        Finance. The BBVA baseline is a third party&rsquo;s published scenario, carried for
        context — not our forecast. Analytical information, not investment advice.
      </Colophon>
    </main>
  );
}
