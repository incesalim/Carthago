/**
 * Foreign Trade — reproduces the Albaraka "Dış Ticaret Dengesi" report from
 * TÜİK customs-trade series in EVDS: the trade balance, exports & imports
 * (level + growth), the coverage ratio, terms of trade, trade by BEC product
 * group, and the energy deficit vs Brent.
 *
 * Data + derivations: app/lib/foreign-trade.ts. The report's "core balance"
 * line (Albaraka-internal) and the HS-chapter ("Fasıl") tables (TÜİK dynamic
 * DB only) are flagged below rather than approximated.
 *
 * "The Desk" (web/DESIGN.md): a computed brief (record line + vitals band)
 * above the full report, which is carried over intact under <Depth>.
 */
import type { Metadata } from "next";
import Link from "next/link";
import { getForeignTradeData } from "@/app/lib/foreign-trade";
import { Section, Stat } from "@/app/components/ui";
import { GlobalRangeSelector } from "@/app/components/range-context";
import {
  Colophon,
  Depth,
  DeskHeader,
  SecHead,
  Vital,
  Vitals,
} from "@/app/components/desk";
import { lastVal, monthLabel, signedPp, valAgo } from "@/app/lib/desk";
import { ChartCard } from "@/app/components/ui/chart-card";
import TimeSeriesChart from "@/app/components/TimeSeriesChart";
import BopFlowChart, { type BarSeries, type OverlayLine } from "@/app/components/BopFlowChart";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkey Foreign Trade",
  description: "Türkiye's foreign trade — exports, imports and the trade balance by broad economic category.",
  alternates: { canonical: "/economy/foreign-trade" },
};

const MAROON = { light: "#9c1f2f", dark: "#d65a5a" };
const INK = { light: "#171717", dark: "#ededed" };

function Grid({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">{children}</div>;
}

const nf1 = (v: number | null) =>
  v == null ? "—" : new Intl.NumberFormat("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(v);

/** "+4.2%" / "−4.2%" — a signed growth rate inside a computed note. */
const sPct = (v: number | null, d = 1) =>
  v == null ? "—" : `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(d)}%`;

/** {period_date,value} (chart shape) → {period,value} (sparkline / desk helpers). */
const sp = (pts: { period_date: string; value: number }[] | undefined) =>
  (pts ?? []).map((p) => ({ period: p.period_date, value: p.value }));

/** % change of a 12m-rolling series vs its own value 12 months ago. */
const yoy12 = (s: { period: string; value: number | null }[]) => {
  const now = lastVal(s);
  const ago = valAgo(s, 12);
  return now != null && ago != null && ago !== 0 ? (now / ago - 1) * 100 : null;
};

/** The labelled series with the highest latest value — "which group leads". */
function topSeries(rec: Record<string, { value: number }[]>): string | null {
  let best: { label: string; v: number } | null = null;
  for (const [label, pts] of Object.entries(rec)) {
    const v = pts.at(-1)?.value;
    if (v == null || !Number.isFinite(v)) continue;
    if (!best || v > best.v) best = { label, v };
  }
  return best ? best.label.toLowerCase() : null;
}

export default async function ForeignTradePage() {
  const d = await getForeignTradeData();

  // The section reads — the trade gap and the leading BEC groups, off the charts'
  // own data. "Imports run well above exports" and "intermediate goods dominate
  // imports" were both rankings nobody re-checked.
  const expNow = d.levels["Exports"]?.at(-1)?.value ?? null;
  const impNow = d.levels["Imports"]?.at(-1)?.value ?? null;
  const gap = expNow != null && impNow != null ? impNow - expNow : null;
  const becImpTop = topSeries(d.becImp);
  const becExpTop = topSeries(d.becExp);

  // ---- the brief's computed vitals ------------------------------------------
  const expS = sp(d.levels.Exports);
  const impS = sp(d.levels.Imports);
  const balS = sp(d.s1["Trade balance"]);
  const exEnS = sp(d.s1["ex energy"]);
  const covS = sp(d.coverage["Coverage ratio"]);

  const recP = expS.at(-1)?.period ?? null;
  const prevP = expS.at(-2)?.period ?? null;

  const exp12 = lastVal(expS);
  const imp12 = lastVal(impS);
  const expYoY = yoy12(expS);
  const impYoY = yoy12(impS);

  const bal12 = lastVal(balS);
  const exEn12 = lastVal(exEnS);
  // energy12 = balance − ex-energy balance (the energy bill inside the gap).
  const energy12 = bal12 != null && exEn12 != null ? bal12 - exEn12 : null;

  const cov = lastVal(covS);
  const covAgo = valAgo(covS, 12);
  const covD = cov != null && covAgo != null ? cov - covAgo : null;

  // Brent + the 12m energy deficit ride on the same monthly bar rows (Şekil 8).
  const num = (v: number | string | undefined) => (typeof v === "number" ? v : null);
  const brentNow = num(d.energy.at(-1)?.brent);
  const brentAgo = num(d.energy.at(-13)?.brent);
  const brentYoY =
    brentNow != null && brentAgo != null && brentAgo !== 0 ? (brentNow / brentAgo - 1) * 100 : null;
  const brentS = d.energy
    .map((r) => ({ period: String(r.x), value: num(r.brent) }))
    .filter((r) => r.value != null);

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title="Foreign Trade"
        record={
          <>
            Record <b className="font-normal text-foreground">{monthLabel(recP ?? d.latestPeriod)}</b>{" "}
            · vs {monthLabel(prevP, false)} · 12m rolling sums
          </>
        }
        right="every figure computed from source series"
      />

      {/* ── The vitals ─────────────────────────────────────────────────── */}
      <SecHead
        title="The vitals"
        meta="tüik customs · trailing-12-month sums, usd bn"
        className="mb-2.5 mt-6"
      />
      <Vitals cols={5}>
        <Vital
          label="Exports · 12m"
          value={nf1(exp12)}
          unit="$bn"
          series={expS.slice(-13)}
          format="raw"
          decimals={0}
          note={
            <>
              {expYoY != null && (
                <>
                  <b className={expYoY >= 0 ? "font-semibold text-positive" : "font-semibold text-negative"}>
                    {sPct(expYoY)}
                  </b>{" "}
                  y/y ·{" "}
                </>
              )}
              ${nf1(d.expQ)}bn in the last 3 months
            </>
          }
        />
        <Vital
          label="Imports · 12m"
          value={nf1(imp12)}
          unit="$bn"
          series={impS.slice(-13)}
          format="raw"
          decimals={0}
          note={
            <>
              {impYoY != null && (
                <>
                  <b className={impYoY <= 0 ? "font-semibold text-positive" : "font-semibold text-negative"}>
                    {sPct(impYoY)}
                  </b>{" "}
                  y/y ·{" "}
                </>
              )}
              ${nf1(d.impQ)}bn in the last 3 months
            </>
          }
        />
        <Vital
          label="Trade deficit · 12m"
          value={bal12 != null ? nf1(Math.abs(bal12)) : "—"}
          unit="$bn"
          series={balS.slice(-13)}
          format="raw"
          decimals={0}
          note={
            <>
              {energy12 != null && <>energy bill ${nf1(Math.abs(energy12))}bn · </>}
              {exEn12 != null && <>ex-energy gap ${nf1(Math.abs(exEn12))}bn</>}
            </>
          }
        />
        <Vital
          label="Coverage ratio · 12m"
          value={cov != null ? cov.toFixed(1) : "—"}
          unit="%"
          series={covS.slice(-13)}
          decimals={1}
          note={
            covD != null ? (
              <>
                <b className={covD >= 0 ? "font-semibold text-positive" : "font-semibold text-negative"}>
                  {signedPp(covD, 1)}
                </b>{" "}
                y/y — exports fund this much of the import bill
              </>
            ) : (
              "exports ÷ imports, 12m sums"
            )
          }
        />
        <Vital
          label="Brent"
          value={brentNow != null ? brentNow.toFixed(1) : "—"}
          unit="$/bbl"
          series={brentS.slice(-13)}
          format="raw"
          decimals={1}
          note={
            <>
              {brentYoY != null && (
                <>
                  <b className={brentYoY <= 0 ? "font-semibold text-positive" : "font-semibold text-negative"}>
                    {sPct(brentYoY, 0)}
                  </b>{" "}
                  y/y ·{" "}
                </>
              )}
              the energy bill&rsquo;s single driver —{" "}
              <Link href="/economy" className="font-semibold text-primary">
                /economy
              </Link>
            </>
          }
        />
      </Vitals>

      <Depth action={<GlobalRangeSelector />}>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Stat label="Exports · last 3 months" value={`$${nf1(d.expQ)} bn`} hint={`customs · to ${d.asOfLabel}`} tone="positive" />
          <Stat label="Imports · last 3 months" value={`$${nf1(d.impQ)} bn`} hint={`customs · to ${d.asOfLabel}`} tone="neutral" />
          <Stat label="Trade deficit · last 3 months" value={`$${nf1(d.deficitQ)} bn`} hint={`imports − exports · to ${d.asOfLabel}`} tone="negative" />
        </div>

        <Section
          title="Trade Balance"
          description="Annualised (trailing-12-month) customs trade balance, USD bn. The ex-energy line strips out the energy bill — the dominant swing factor."
        >
          <Grid>
            <TimeSeriesChart series={d.s1} title="Şekil 1 · Trade Balance (12m rolling, USD bn)" yFormat="raw" decimals={1} />
            <TimeSeriesChart series={d.coverage} title="Şekil 4 · Export/Import Coverage Ratio (12m, %)" yFormat="pct" decimals={1} />
          </Grid>
        </Section>

        <Section
          title="Exports & Imports"
          description={
            gap != null
              ? `Annualised level (USD bn) and annual growth. Imports run $${Math.abs(gap).toFixed(0)}bn ${
                  gap > 0 ? "above" : "below"
                } exports — the structural trade gap.`
              : "Annualised level (USD bn) and annual growth."
          }
        >
          <Grid>
            <TimeSeriesChart series={d.levels} title="Şekil 2–3 · Exports & Imports (12m rolling, USD bn)" yFormat="raw" decimals={0} />
            <TimeSeriesChart series={d.growth} title="Export & Import Growth (y/y %)" yFormat="pct" decimals={0} />
          </Grid>
        </Section>

        <Section
          title="By Product Group (BEC)"
          description={
            becImpTop && becExpTop
              ? `Broad Economic Categories, annualised USD bn. ${becImpTop} lead imports; ${becExpTop} lead exports.`
              : "Broad Economic Categories, annualised USD bn."
          }
        >
          <Grid>
            <TimeSeriesChart series={d.becExp} title="Şekil 6 · Exports by BEC Group (12m, USD bn)" yFormat="raw" decimals={0} />
            <TimeSeriesChart series={d.becImp} title="Şekil 7 · Imports by BEC Group (12m, USD bn)" yFormat="raw" decimals={0} />
          </Grid>
        </Section>

        {/* "The energy deficit tracks Brent — the report's clearest single driver of
            the trade gap" is a correlation claim we never computed. The charts show
            both series; the reader can see the co-movement without being told. */}
        <Section
          title="Terms of Trade & Energy"
          description="Terms of trade = export unit-value ÷ import unit-value (2015=100), against the energy balance and Brent."
        >
          <Grid>
            <TimeSeriesChart series={d.terms} title="Şekil 5 · Terms of Trade (%)" yFormat="rate" decimals={1} />
            <ChartCard title="Şekil 8 · Energy Deficit (12m, USD bn) & Brent ($/bbl)">
              <BopFlowChart
                data={d.energy}
                bars={[{ key: "deficit", label: "Energy deficit (12m)", fill: MAROON }] satisfies BarSeries[]}
                line={{ key: "brent", label: "Brent ($/bbl, right)", color: INK, rightAxis: true } satisfies OverlayLine}
                decimals={1}
              />
            </ChartCard>
          </Grid>
        </Section>

        <p className="text-xs text-muted-foreground">
          Source: TÜİK (TurkStat) foreign-trade statistics + Brent via TCMB EVDS.
          Two elements are not shown: the «Çekirdek Denge» (core balance) line,
          which doesn&apos;t reconcile from EVDS primitives; and the HS-chapter
          («Fasıl») trade tables, which live only in TÜİK&apos;s dynamic
          foreign-trade database, not EVDS.{" "}
          <Link href="/economy/balance-of-payments" className="text-primary hover:underline">
            Balance of Payments →
          </Link>
        </p>
      </Depth>

      <Colophon>
        Compiled, not written — every figure computed from TÜİK (TurkStat) customs foreign-trade
        series and Brent, via TCMB EVDS. 12-month figures are trailing rolling sums; the coverage
        ratio is exports ÷ imports on those sums. No forecasts. Analytical information, not
        investment advice.
      </Colophon>
    </main>
  );
}
