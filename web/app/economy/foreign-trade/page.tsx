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
import { lastVal, monthLabel, signedPp, valAgo } from "@/app/lib/desk";
import { tradeInsights } from "@/app/lib/insights";
import { aheadSlots } from "@/app/lib/ahead-data";
import Takeaway from "@/app/components/Takeaway";
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
  const [d, ahead] = await Promise.all([getForeignTradeData(), aheadSlots()]);

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

  // ---- "The Read" — computed from the same series the charts show ----------
  const termsS = sp(d.terms["Terms of trade"]);
  const read = tradeInsights({
    balance12m: balS,
    exEnergy12m: exEnS,
    exports12m: expS,
    imports12m: impS,
    coverage: covS,
    terms: termsS,
  });

  // ---- movers: the 12-month sums, this month against last ------------------
  // One customs release, one 12-month basis, so a single from→to header is
  // honest. The Δ is between consecutive rolling windows — what "the deficit
  // widened this month" actually measures.
  const rollMover = (
    label: string,
    s: { period: string; value: number | null }[],
    good: MoverRow["good"],
    fmt: (v: number) => string,
    deltaUnit = "bn",
  ): MoverRow => ({
    label,
    prev: valAgo(s, 1),
    curr: lastVal(s),
    good,
    fmt,
    deltaDecimals: 1,
    deltaUnit,
  });
  const usdBn = (v: number) => `$${v.toFixed(1)}bn`;
  const movers: MoverRow[] = [
    rollMover("Exports, 12m", expS, "up", usdBn),
    rollMover("Imports, 12m", impS, "neutral", usdBn),
    rollMover("Trade balance, 12m", balS, "up", usdBn),
    rollMover("Balance ex energy, 12m", exEnS, "up", usdBn),
    rollMover("Coverage ratio", covS, "up", (v) => `${v.toFixed(1)}%`, "pp"),
    rollMover("Terms of trade", termsS, "up", (v) => v.toFixed(1), "pts"),
  ];

  // ---- transmission: the goods gap → the banks -----------------------------
  const termsNow = lastVal(termsS);
  const transmission: TransmissionItem[] = [
    {
      k: "Trade balance, 12m",
      v: bal12 != null ? `$${Math.abs(bal12).toFixed(1)}bn` : "—",
      effect: (
        <>
          The goods gap is the largest single line in the{" "}
          <Link href="/economy/balance-of-payments" className="font-semibold text-primary">
            current account
          </Link>
          , so it is the main driver of the external financing need the banks help
          fund.
        </>
      ),
    },
    {
      k: "Energy bill, 12m",
      v: energy12 != null ? `$${Math.abs(energy12).toFixed(1)}bn` : "—",
      effect: (
        <>
          The part of the gap set abroad. Energy is priced in dollars and consumed
          regardless of the lira, which is why the ex-energy balance is the read on
          what domestic policy can actually move.
        </>
      ),
    },
    {
      k: "Coverage ratio",
      v: cov != null ? `${cov.toFixed(1)}%` : "—",
      effect: (
        <>
          How much of the import bill exports pay for. The shortfall has to be
          borrowed or drawn from reserves every year it persists —{" "}
          <Link href="/economy" className="font-semibold text-primary">
            the buffer
          </Link>{" "}
          is the other half of that sentence.
        </>
      ),
    },
    {
      k: "Terms of trade",
      v: termsNow != null ? termsNow.toFixed(1) : "—",
      effect: (
        <>
          Export prices against import prices. A higher index buys more imports per
          unit exported, so it moves the gap without any change in volume — a price
          effect that is easy to misread as a demand one.
        </>
      ),
    },
    {
      k: "Exporters' FX",
      v: expYoY != null ? `${expYoY >= 0 ? "" : "−"}${Math.abs(expYoY).toFixed(1)}%` : "—",
      effect: (
        <>
          Export growth y/y on 12-month sums. Exporters are the system&rsquo;s natural
          source of foreign currency and a core commercial-banking segment — their
          receipts are an FC{" "}
          <Link href="/liquidity" className="font-semibold text-primary">
            funding
          </Link>{" "}
          input, not just a trade statistic.
        </>
      ),
    },
  ];

  // ---- flags ----------------------------------------------------------------
  const flagList: Flag[] = [
    {
      code: "COVER_LOW",
      active: cov != null && cov < 70,
      rule: "exports_12m / imports_12m < 70%",
      body: (
        <>
          <b className="font-semibold">Exports cover under 70% of the import bill.</b>{" "}
          At {cov?.toFixed(1)}%, close to a third of imports is funded from something
          other than export earnings.
        </>
      ),
      clear: (
        <>
          Exports cover {cov != null ? `${cov.toFixed(1)}%` : "—"} of imports — at or
          above the 70% line.
        </>
      ),
    },
    {
      code: "ENERGY_HEAVY",
      active:
        energy12 != null && bal12 != null && bal12 !== 0 &&
        Math.abs(energy12) / Math.abs(bal12) > 0.5,
      rule: "|energy_balance_12m| / |trade_balance_12m| > 50%",
      body: (
        <>
          <b className="font-semibold">Energy is more than half the goods gap.</b> $
          {energy12 != null ? Math.abs(energy12).toFixed(1) : "—"}bn of a $
          {bal12 != null ? Math.abs(bal12).toFixed(1) : "—"}bn deficit — a gap set by
          world prices rather than domestic demand.
        </>
      ),
      clear: (
        <>
          Energy is $
          {energy12 != null ? Math.abs(energy12).toFixed(1) : "—"}bn of the $
          {bal12 != null ? Math.abs(bal12).toFixed(1) : "—"}bn gap — inside half.
        </>
      ),
    },
    {
      code: "IMPORTS_OUTPACE",
      active: expYoY != null && impYoY != null && impYoY > expYoY,
      rule: "imports_yoy > exports_yoy (12m sums)",
      body: (
        <>
          <b className="font-semibold">Imports grow faster than exports.</b> Imports at{" "}
          {impYoY?.toFixed(1)}% y/y against exports at {expYoY?.toFixed(1)}% — the gap
          widens on volume, before any price effect.
        </>
      ),
      clear: (
        <>
          Exports ({expYoY != null ? `${expYoY.toFixed(1)}%` : "—"}) grow at or above
          imports ({impYoY != null ? `${impYoY.toFixed(1)}%` : "—"}) on 12-month sums.
        </>
      ),
    },
    {
      code: "EXPORTS_SHRINK",
      active: expYoY != null && expYoY < 0,
      rule: "exports_12m_yoy < 0",
      body: (
        <>
          <b className="font-semibold">Export earnings are below their year-ago level.</b>{" "}
          {expYoY?.toFixed(1)}% y/y on trailing-12-month sums — the economy&rsquo;s
          primary source of foreign currency.
        </>
      ),
      clear: (
        <>
          12-month exports are {expYoY != null ? `${expYoY.toFixed(1)}%` : "—"} y/y — at
          or above their year-ago level.
        </>
      ),
    },
  ];

  const aheadItems = [
    { when: "~1st", what: <>TÜİK / Ministry of Trade provisional foreign-trade figures</> },
    { when: "~end", what: <>TÜİK final foreign-trade statistics for the month</> },
    { when: "~11th", what: <>TCMB balance of payments — where this gap lands</>, href: "/economy/balance-of-payments" },
    ...(ahead.mpc ? [{ when: ahead.mpc.when, what: <>CBRT rate decision</>, href: "/rates" }] : []),
  ];

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

      {/* ── The Read ──────────────────────────────────────────────────── */}
      <div className="mt-7">
        <Takeaway data={read} variant="desk" />
      </div>

      {/* ── Movers | Transmission ─────────────────────────────────────── */}
      <div className="mt-8 grid grid-cols-1 gap-x-9 gap-y-7 lg:grid-cols-[5fr_7fr]">
        <div>
          <SecHead
            title="The 12-month sums"
            meta="consecutive rolling windows · one customs release"
            className="mb-2.5"
          />
          <Movers
            from={monthLabel(prevP, false)}
            to={monthLabel(recP ?? d.latestPeriod, false)}
            rows={movers}
          />
        </div>
        <div>
          <SecHead title="Transmission" meta="the goods gap → the banks · computed" className="mb-2.5" />
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
            quietNote="Every trade rule below was tested against the current release and none tripped."
          />
        </div>
        <div>
          <SecHead title="Ahead" meta="scraped calendar + fixed cadence" className="mb-2.5" />
          <Ahead items={aheadItems} />
        </div>
      </div>

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
