import { SectorReport, SectorHeader, SectorContents, SectorMetrics, SectorSection, SectorDirectory, SectorFooter, SectorOpening, SectorGrid, SectorPanel } from "@/app/components/sector-report";
/** Returns, margin components, monthly income and the cost of deposit funding. */
import { localizeMetadata } from "@/i18n/metadata";
import { getText } from "@/i18n/server";
import type { Metadata } from "next";
import type { ReactNode } from "react";
import Link from "next/link";
import {
  ratioRoe,
  ratioRoa,
  ratioNim,
  ratioOpex,
  ratioFeesToRevenue,
  leverage,
  evdsSeries,
  nimComponentsRaw,
  PRIMARY_BANK_TYPES,
  BANK_TYPES,
  BANK_TYPE_LABELS,
  type TimeSeriesRow,
} from "@/app/lib/metrics";
import { sectorPnl, sectorDepositMix } from "@/app/lib/metrics";
import { buildNimDatasets } from "@/app/lib/nim-components";
import SectorTrend from "@/app/components/SectorTrend";
import SectorBreakdown from "@/app/components/SectorBreakdown";
import { feeOperatingCostCoverage, monthlyNetProfit } from "@/app/lib/sector-bddk-detail";
import NimComponentsSection from "./NimComponentsSection";
import EngineBars from "./EngineBars";
import ProfitBridge from "./ProfitBridge";
import Takeaway from "@/app/components/Takeaway";
import { profitabilityInsights } from "@/app/lib/insights";
import { seriesFinding } from "@/app/lib/chart-findings";
import { withLlmHeadline } from "@/app/lib/read-headlines";
import {
  ChartFoot,
  Levels,
  Movers,
  SecHead,
  Standings,
  Transmission,
  Vital,
  type MoverRow,
  type StandingsGroup,
  type TransmissionItem,
} from "@/app/components/desk";
import { monthLabel, signedPct, signedPp, streak, valAgo, windowExtremes } from "@/app/lib/desk";
import { firstClaim } from "@/app/lib/prose";
import { realRate } from "@/app/lib/real-terms";
import { bridge, costIncome, engine } from "@/app/lib/profitability";
import { GlobalRangeSelector } from "@/app/components/range-context";

export const dynamic = "force-dynamic";

const pageMetadata: Metadata = {
  title: "Turkish Banks — Profitability (ROE, ROA, NIM)",
  description: "Profitability of Turkish banks — return on equity, return on assets, net interest margin and pre-provision profit by bank and group.",
  alternates: { canonical: "/profitability" },
};

export async function generateMetadata(): Promise<Metadata> {
  return localizeMetadata(pageMetadata);
}

/** Route link styled for use inside a computed note. */
const Go = ({ href, children }: { href: string; children: ReactNode }) => (
  <Link href={href} className="font-semibold text-primary">
    {children}
  </Link>
);

export default async function ProfitabilityPage() {
  const tx = await getText();

  const [
    roe, roa, nim,
    opex, fees, lev,
    cpiRaw, nimRows,
    pnl, depMix, feeCoverage,
  ] = await Promise.all([
    ratioRoe(PRIMARY_BANK_TYPES),
    ratioRoa(PRIMARY_BANK_TYPES),
    ratioNim(PRIMARY_BANK_TYPES),
    ratioOpex(PRIMARY_BANK_TYPES),
    ratioFeesToRevenue(PRIMARY_BANK_TYPES),
    leverage([BANK_TYPES.SECTOR]),
    // CPI 2025=100 — TP.FG.J0 (2003=100) died at the Jan-2026 TUIK rebase
    evdsSeries("TP.TUKFIY2025.GENEL", 10),
    nimComponentsRaw(),
    // The engine: the sector's own P&L and deposit mix. The income statement is
    // CUMULATIVE year-to-date — lib/profitability.ts de-cumulates it.
    sectorPnl(),
    sectorDepositMix(),
    feeOperatingCostCoverage(),
  ]);

  const nimDatasets = buildNimDatasets(nimRows);
  const monthlyProfit = monthlyNetProfit(pnl);
  const feePeriod = feeCoverage.filter(row => row.bank_type_code === BANK_TYPES.SECTOR).at(-1)?.period;
  const feePriorPeriod = feePeriod ? `${Number(feePeriod.slice(0, 4)) - 1}${feePeriod.slice(4)}` : undefined;
  const feeComparisons = PRIMARY_BANK_TYPES.map(code => ({ id: code, label: BANK_TYPE_LABELS[code], values: {
    prior: feeCoverage.find(row => row.period === feePriorPeriod && row.bank_type_code === code)?.value ?? null,
    current: feeCoverage.find(row => row.period === feePeriod && row.bank_type_code === code)?.value ?? null,
  } }));
  const nimThrough = nimRows.length > 0
    ? `${nimRows[nimRows.length - 1].year}-${String(nimRows[nimRows.length - 1].month).padStart(2, "0")}`
    : undefined;

  // Build CPI 12m-rolling-average YoY from monthly CPI levels
  type Cpi = { period_date: string; value: number };
  const cpi: Cpi[] = (cpiRaw as Cpi[]).slice().sort((a, b) =>
    a.period_date.localeCompare(b.period_date),
  );
  // YoY = level / level[12 months back] - 1
  const cpiYoY: { period: string; value: number }[] = [];
  for (let i = 12; i < cpi.length; i++) {
    const cur = cpi[i].value;
    const prev = cpi[i - 12].value;
    if (prev > 0) cpiYoY.push({ period: cpi[i].period_date.slice(0, 7), value: (cur / prev - 1) * 100 });
  }
  // 12m rolling average
  const cpiAvg: { period: string; value: number }[] = [];
  for (let i = 11; i < cpiYoY.length; i++) {
    let sum = 0;
    for (let j = i - 11; j <= i; j++) sum += cpiYoY[j].value;
    cpiAvg.push({ period: cpiYoY[i].period, value: sum / 12 });
  }

  // Combine sector ROE + Private + State + CPI for ROE-with-CPI chart
  const roePlusCpi: TimeSeriesRow[] = [];
  for (const r of roe) {
    if (r.bank_type_code === BANK_TYPES.SECTOR ||
        r.bank_type_code === BANK_TYPES.PRIVATE ||
        r.bank_type_code === BANK_TYPES.STATE) {
      roePlusCpi.push(r);
    }
  }
  for (const c of cpiAvg) {
    roePlusCpi.push({ period: c.period, bank_type_code: "CPI", value: c.value });
  }

  // "The Read" — deterministic, computed from the same series the charts show.
  const sectorOnly = (rows: TimeSeriesRow[]) =>
    rows.filter((r) => r.bank_type_code === BANK_TYPES.SECTOR);
  const read = profitabilityInsights({
    roe: sectorOnly(roe),
    roa: sectorOnly(roa),
    nim: sectorOnly(nim),
    opex: sectorOnly(opex),
    cpi: cpiAvg.map((c) => ({ period: c.period, bank_type_code: "CPI", value: c.value })),
  }, tx.locale);

  // "The return equation" — DuPont-lite: ROE ≈ ROA × (assets/equity). All from
  // series already on the page + sector leverage; deltas are y/y (12 months).
  const sectorRows = {
    roe: sectorOnly(roe),
    roa: sectorOnly(roa),
    nim: sectorOnly(nim),
    opex: sectorOnly(opex),
    fees: sectorOnly(fees),
  };
  const latest = (s: TimeSeriesRow[]) => s.at(-1)?.value ?? null;
  const yearAgo = (s: TimeSeriesRow[]) => s.at(-13)?.value ?? null;
  const fmtPct = (v: number | null | undefined, d = 1) =>
    v == null ? "—" : `${v.toFixed(d)}%`;
  // leverage series = liabilities/equity (%); assets/equity = 1 + L/E.
  const levX = latest(lev) != null ? 1 + (latest(lev) as number) / 100 : null;

  // ---- vitals — computed from the series above ------------------------------
  const roeNow = latest(sectorRows.roe);
  const roaNow = latest(sectorRows.roa);
  const nimNow = latest(sectorRows.nim);
  const opexNow = latest(sectorRows.opex);
  const feesNow = latest(sectorRows.fees);
  const cpiAvgNow = cpiAvg.at(-1)?.value ?? null;

  const roeReal = realRate(roeNow, cpiAvgNow);
  const roeDupont = roaNow != null && levX != null ? roaNow * levX : null;
  const nimExt = windowExtremes(sectorRows.nim, 24);
  const opexAgo = yearAgo(sectorRows.opex);
  const opexDelta = opexNow != null && opexAgo != null ? opexNow - opexAgo : null;
  const feesAgo = yearAgo(sectorRows.fees);
  const feesDelta = feesNow != null && feesAgo != null ? feesNow - feesAgo : null;
  const cpiFallStreak = streak(cpiAvg, "down");
  const cpiAgo = valAgo(cpiAvg, 12);
  const cpiDelta12 = cpiAvgNow != null && cpiAgo != null ? cpiAvgNow - cpiAgo : null;

  const recMonth = monthLabel(sectorRows.roe.at(-1)?.period);
  const vsMonth = monthLabel(sectorRows.roe.at(-2)?.period, false);
  const spark = (s: TimeSeriesRow[]) => s.slice(-13);

  // ---- the engine: what the deposits the sector doesn't pay for are worth ---
  const eng = engine(pnl, depMix);
  const E = eng.at(-1) ?? null;
  const ci = costIncome(pnl);
  const ciNow = ci.at(-1)?.value ?? null;
  const ci12 = ci.at(-13)?.value ?? null;

  // Three chart titles asserted things the series beside them already settle.
  //
  // "…pays a third of its depositors nothing — so the blended cost sits far below
  // inflation": both the fraction and the comparison are live numbers (and it is
  // the deposit BOOK, not the depositors, that the share measures).
  const blendedGap = E && cpiAvgNow != null ? E.blended - cpiAvgNow : null;
  // "The margin rebuilt as deposits repriced down": a NIM direction and a deposit-
  // cost direction, neither tested. Compression reverses both.
  const nim12 = yearAgo(sectorRows.nim);
  const nimD = nimNow != null && nim12 != null ? nimNow - nim12 : null;
  const blended12 = eng.at(-13)?.blended ?? null;
  const costD = E && blended12 != null ? E.blended - blended12 : null;
  // ONE ROE on this page: BDDK's published ratio. The counterfactual is a COST
  // applied to it, never a rival ROE computed a different way.
  const roeIfPaid = roeNow != null && E ? roeNow - E.roeCost : null;
  const engRatios = eng.slice(-18).map((e) => e.ratio);

  // ---- the month's P&L, de-cumulated — and its reconciliation gate ----------
  const br = bridge(pnl);
  const priorPeriod = br
    ? `${Number(br.period.slice(0, 4)) - 1}-${br.period.slice(5)}`
    : null;
  const brPrior = priorPeriod ? bridge(pnl, priorPeriod) : null;

  const fmtTrn = (v: number | null | undefined, d = 2) =>
    v == null ? "—" : tx("₺{0}trn", {0: v.toFixed(d)});
  const signedTrn = (v: number | null | undefined, d = 3) =>
    v == null ? "—" : tx("{0}₺{1}trn", {0: v >= 0 ? "+" : "−", 1: Math.abs(v).toFixed(d)});

  // ---- movers: the monthly record (incl. the ratio the page never printed) --
  const mv = (s: { value: number | null }[]) => ({
    prev: s.at(-2)?.value ?? null,
    curr: s.at(-1)?.value ?? null,
  });
  const moverRows: MoverRow[] = [
    { label: "ROE, ann.", ...mv(sectorRows.roe), fmt: (v) => `${v.toFixed(1)}%`, deltaDecimals: 1, good: "up" },
    { label: "ROA, ann.", ...mv(sectorRows.roa), good: "up" },
    { label: "Net int. margin", ...mv(sectorRows.nim), good: "up" },
    { label: "OPEX / avg assets", note: "cost intensity", ...mv(sectorRows.opex), good: "down" },
    { label: "Fees / revenue", ...mv(sectorRows.fees), fmt: (v) => `${v.toFixed(1)}%`, deltaDecimals: 1, good: "up" },
    {
      label: "Cost / income",
      note: "the efficiency ratio the page never printed",
      ...mv(ci), fmt: (v) => `${v.toFixed(1)}%`, deltaDecimals: 1, good: "down",
    },
  ];

  // ---- the engine → the return ---------------------------------------------
  const transmission: TransmissionItem[] = [];
  if (E) {
    transmission.push({
      k: "Free funding",
      v: E.demandShare.toFixed(1),
      unit: "%",
      effect: (
        <>{tx("{0} of deposits pay no interest. The sector pays {1} on interest-bearing deposits; the blended cost is {2}.",
          {0: fmtPct(E.demandShare), 1: fmtPct(E.paidOnTime), 2: fmtPct(E.blended)})}{" "}
          <Go href="/deposits">{tx("Deposits")}</Go>
        </>
      ),
    });
    transmission.push({
      k: "What it's worth",
      v: `₺${E.worth.toFixed(2)}`,
      unit: "trn",
      effect: (
        <>{tx("At the sector's paid rate, pricing demand deposits would cost {0} a year, versus {1} of sector profit. That equals {2}× the profit.",
          {0: fmtTrn(E.worth), 1: fmtTrn(E.profit), 2: E.ratio.toFixed(1)})}</>
      ),
    });
    transmission.push({
      k: "Without it",
      v: roeIfPaid != null ? roeIfPaid.toFixed(0) : "—",
      unit: "%",
      effect: (
        <>{tx("Published ROE is {0}. Pricing demand deposits at the paid rate would reduce it by {1}pp to {2}. This is a sizing exercise, not a forecast.",
          {0: fmtPct(roeNow), 1: E.roeCost.toFixed(0), 2: fmtPct(roeIfPaid)})}</>
      ),
    });
  }
  if (roeNow != null && cpiAvgNow != null) {
    transmission.push({
      k: "The hurdle",
      v: cpiAvgNow.toFixed(1),
      unit: "%",
      effect: (
        <>{tx(roeReal != null && roeReal < 0
          ? "Published ROE is {0}; deflated by {1} 12m-average CPI, it is {2} in real terms. The sector remains below the inflation hurdle."
          : "Published ROE is {0}; deflated by {1} 12m-average CPI, it is {2} in real terms. The sector clears the inflation hurdle.",
        {0: fmtPct(roeNow), 1: fmtPct(cpiAvgNow), 2: roeReal != null ? signedPct(roeReal, 1) : "—"})}{" "}
          <Go href="/economy/inflation">{tx("Inflation")}</Go>
        </>
      ),
    });
  }
  if (E && cpiAvgNow != null) {
    transmission.push({
      k: "The saver",
      v: E.blended.toFixed(1),
      unit: "%",
      effect: (
        <>{tx("The blended deposit cost is {0}, versus {1} inflation: a {2}pp nominal gap. That gap supports the margin.",
          {0: fmtPct(E.blended), 1: fmtPct(cpiAvgNow), 2: Math.abs(E.blended - cpiAvgNow).toFixed(1)})}</>
      ),
    });
  }



  // ---- standings: ROE by group against the CPI hurdle -----------------------
  const groupRoe = (PRIMARY_BANK_TYPES as readonly string[])
    .filter((c) => c !== BANK_TYPES.SECTOR)
    .map((c) => ({
      code: c as string,
      value: (roe.filter((r) => r.bank_type_code === c).at(-1)?.value ?? null) as number | null,
    }))
    .filter((r): r is { code: string; value: number } => r.value != null)
    .sort((a, b) => b.value - a.value);
  // Five groups: a top-3 and a bottom-3 would print one of them twice.
  const topN = Math.min(3, Math.floor(groupRoe.length / 2));
  const standings: StandingsGroup[] = [
    {
      heading: tx("Highest return on equity — {0}", {0: recMonth}),
      rows: groupRoe.slice(0, topN).map((r, i) => ({
        rank: i + 1,
        name: BANK_TYPE_LABELS[r.code] ?? r.code,
        value: fmtPct(r.value),
        tone: cpiAvgNow != null && r.value > cpiAvgNow ? ("up" as const) : ("dn" as const),
      })),
    },
    {
      heading: tx("Against the {0} CPI hurdle — the rest", {0: fmtPct(cpiAvgNow)}),
      rows: groupRoe
        .slice(topN)
        .reverse()
        .map((r, i) => ({
          rank: i + 1,
          name: BANK_TYPE_LABELS[r.code] ?? r.code,
          value: cpiAvgNow != null ? signedPp(r.value - cpiAvgNow, 1) : "—",
          tone:
            cpiAvgNow != null && r.value >= cpiAvgNow ? ("up" as const) : ("dn" as const),
        })),
    },
  ];

  const sectorAssessment = await withLlmHeadline("profitability", read, tx.locale);

  return (
    <SectorReport>
<SectorHeader sector="profitability" record={<>{tx("Record ")}<b className="font-normal text-foreground">{tx(recMonth)}</b>{tx(" · vs ")}{tx(vsMonth)}
          </>} observations={[
          {
            cadence: "monthly",
            role: "current",
            asOf: sectorRows.roe.at(-1)?.period,
            window: "YTD ratios, annualized",
            basis: "BDDK published sector ratios",
          },
          {
            cadence: "monthly",
            role: "current",
            asOf: br?.period,
            window: "month alone, de-cumulated",
            basis: "reported P&L reconciled before display",
          },
        ]} />
<SectorContents sections={[{id: "overview", label: "Key indicators"}, {id: "returns", label: "Returns"}, {id: "income", label: "Income statement"}, {id: "margins", label: "Margins and costs"}, ...(E ? [{id: "funding-cost", label: "Funding cost"}] : [])]} controls={<GlobalRangeSelector compact />} />
<SectorOpening>
<SectorMetrics><Vital
          label={tx("ROE, ann.")}
          value={roeNow != null ? roeNow.toFixed(1) : "—"}
          unit="%"
          series={spark(sectorRows.roe)}
          decimals={1}
          note={
            <>{tx("Fisher-deflated ≈")}{" "}
              <em
                className={
                  roeReal != null && roeReal < 0
                    ? "not-italic font-semibold text-negative"
                    : "not-italic font-semibold text-positive"
                }
              >
                {tx(roeReal != null ? signedPct(roeReal, 1) : "—")}{tx(" real")}</em>
            </>
          }
        />
<Vital
          label={tx("ROA, ann.")}
          value={roaNow != null ? roaNow.toFixed(2) : "—"}
          unit="%"
          series={spark(sectorRows.roa)}
          note={
            roeDupont != null && levX != null ? (
              <>× {tx(`${levX.toFixed(1)}×`)}{tx(" leverage ≈ ROE")}{" "}{tx(`${roeDupont.toFixed(1)}%`)}</>
            ) : (
              <>{tx("Leverage is unavailable; the ROE decomposition cannot be computed.")}</>
            )
          }
        />
<Vital
          label={tx("Net int. margin")}
          value={nimNow != null ? nimNow.toFixed(2) : "—"}
          unit="%"
          series={spark(sectorRows.nim)}
          note={
            nimExt != null && nimNow != null && nimNow - nimExt.min > 0.5 ? (
              <>{tx("Recovered from the {0}% low recorded in {1}.",
                { 0: nimExt.min.toFixed(1), 1: monthLabel(nimExt.minPeriod, false) })}</>
            ) : (
              <>{tx("within its 24m range")}</>
            )
          }
        />
<Vital
          label={tx("OPEX / avg assets")}
          value={opexNow != null ? opexNow.toFixed(2) : "—"}
          unit="%"
          series={spark(sectorRows.opex)}
          note={
            <>
              <b
                className={
                  opexDelta != null && opexDelta <= 0
                    ? "font-semibold text-positive"
                    : "font-semibold text-negative"
                }
              >
                {tx(opexDelta != null ? signedPp(opexDelta, 2) : "—")}
              </b>{" "}{tx("y/y cost intensity")}</>
          }
        /></SectorMetrics>
</SectorOpening>
<SectorSection id="returns" title={tx("Returns")} description={tx("Return on equity, return on assets and comparison with inflation.")}>
{cpiAvg.length > 0 && (<SectorTrend mode="trend" deltaBasis="published" deltaFromFullHistory deltaPeriods={12} deltaLabel="12m"

                  data={roePlusCpi}
                  seriesLabels={{
                    [BANK_TYPES.SECTOR]: "Sector ROE",
                    [BANK_TYPES.PRIVATE]: "Private ROE",
                    [BANK_TYPES.STATE]: "State ROE",
                    CPI: "CPI 12m avg",
                  }}
                  title={tx("Return on equity and inflation")}
                  description={tx("roe annualized vs the 12-month rolling average of CPI y/y, %, monthly")}
                  yFormat="pct"
                  decimals={1}
                  height={320}
                  hero={BANK_TYPES.SECTOR}
                />)}
<Takeaway data={sectorAssessment} variant="report" />

<SectorGrid ratio="balanced">
<SectorPanel>
<Vital
          label={tx("CPI, 12m-avg")}
          value={cpiAvgNow != null ? cpiAvgNow.toFixed(1) : "—"}
          unit="%"
          series={cpiAvg.slice(-13)}
          decimals={1}
          note={
            cpiFallStreak >= 3 ? (
              <>
                <b className="font-semibold text-positive">{tx("CPI has declined for {0} consecutive months.", { 0: cpiFallStreak })}</b>{" "}<Go href="/economy/inflation">{tx("Inflation")}</Go>
              </>
            ) : (
              <>
                {tx(cpiDelta12 != null ? signedPp(cpiDelta12, 1) : "—")} {tx("y/y — the real-return hurdle ")}<Go href="/economy/inflation">{tx("Inflation")}</Go>
              </>
            )
          }
        />
</SectorPanel>
<SectorPanel>
<div>
          <SecHead
            title={tx("Period changes")}
            meta={tx("{0} → {1} · monthly", { 0: vsMonth, 1: monthLabel(sectorRows.roe.at(-1)?.period, false) })}
            className="mb-2.5"
          />
          <Movers
            from={vsMonth.toUpperCase()}
            to={monthLabel(sectorRows.roe.at(-1)?.period, false).toUpperCase()}
            rows={moverRows}
          />
        </div>
</SectorPanel>
</SectorGrid>
<SectorTrend mode="groups"

          data={roe}
          seriesLabels={BANK_TYPE_LABELS}
          title={tx("Return on equity by bank group")}
          description={<><span className="block">{tx(seriesFinding(roe.filter((r) => r.bank_type_code === BANK_TYPES.SECTOR), {
              noun: "ROE",
              decimals: 1,
            }, tx.locale) ?? "ROE — annualized, by group")}</span><span className="mt-1 block">{tx("return on equity, %, annualized (ytd × 12/month) · by ownership group")}</span></>}
          source={<ChartFoot data={roe} labels={BANK_TYPE_LABELS} decimals={1} deltaPeriods={12} />}
          yFormat="pct"
          decimals={1}
          deltaPeriods={12}
          deltaLabel="12m"
          height={320}

          zeroLine
        />
<SectorTrend deltaPeriods={12} deltaLabel="12m" mode="groups"

              data={roa}
              seriesLabels={BANK_TYPE_LABELS}
              title={tx("Return on assets by bank group")}
              description={tx("return on assets, %, annualized · by ownership group")}
              source={<ChartFoot data={roa} labels={BANK_TYPE_LABELS} decimals={2} deltaPeriods={12} />}
              yFormat="pct"
              decimals={2}
              height={320}
              zeroLine
               />
<SectorPanel>
<div>
          <SecHead
            title={tx("Bank comparisons")}
            meta={tx("roe, ann. · {0}", { 0: recMonth })}
            href="/banks"
            hrefLabel={tx("by bank →")}
            className="mb-2.5"
          />
          <Standings groups={standings} />
        </div>
</SectorPanel>
</SectorSection>
<SectorSection id="income" title={tx("Income statement")} description={tx("Monthly income and expenses, derived from year-to-date reported figures.")}>
<SectorTrend data={monthlyProfit} seriesLabels={{ [BANK_TYPES.SECTOR]: "Monthly net profit" }}
  title={tx("Monthly net profit")}
  description={tx("Each month alone: reported year-to-date profit less the preceding month. January starts a new year; missing months remain gaps.")}
  source={tx("Source: BDDK monthly income statement · nominal TL billion")}
  yFormat="bn" decimals={0} zeroLine height={260} />
{br?.reconciles ? (
            <SectorGrid ratio="wide-left">
              <ProfitBridge
                bridge={br}
                prior={brPrior}
                title={tx("Monthly income and expenses")}
                description={<>{tx(monthLabel(br.period))}{" · "}{tx("₺ trn, the month alone · not the year to date")}
                  {brPrior && br.nii > brPrior.nii && br.net < brPrior.net && <p className="mt-2">{tx("{0} — net interest income rose, and the profit still fell", { 0: monthLabel(br.period) })}</p>}
                </>}
                source={
                  <div className="flex flex-wrap gap-x-4 gap-y-1">
                    <span>{tx("NET PROFIT")}{" "}
                      <b className="font-semibold text-foreground">{tx(fmtTrn(br.net, 3))}</b>
                    </span>
                    {brPrior && (
                      <span>
                        {tx("Annual change")}{" "}
                        <b className="font-semibold text-foreground">
                          {tx(signedTrn(br.net - brPrior.net))}
                        </b>
                      </span>
                    )}
                    <span>{tx("Reconciliation difference")}{" "}
                      <b className="font-semibold text-foreground">
                        ₺{tx(Math.abs(br.gap).toFixed(4))}{tx("trn")}</b>
                    </span>
                  </div>
                }
                height={300}
              />
              {/* The read: each line of the month, against the same month a year
                  ago — the comparison a YTD average cannot make. */}
              <SectorPanel>
                <h5 className="mb-1 text-[14px] font-semibold text-faint">{tx("The month, vs a year ago · ₺ trn")}</h5>
                <table className="w-full border-collapse">
                  <tbody>
                    {(
                      [
                        ["Net interest income", "nii"],
                        ["− Provisions", "prov"],
                        ["+ Fees & other", "fees"],
                        ["− Operating costs", "opex"],
                        ["± Trading / FX", "other"],
                        ["− Tax", "tax"],
                        ["= Net profit", "net"],
                      ] as const
                    ).map(([label, k]) => {
                      const v = br[k] as number;
                      const d = brPrior ? v - (brPrior[k] as number) : null;
                      return (
                        <tr key={k} className={k === "net" ? "font-semibold" : undefined}>
                          <td className="border-b border-hair py-1.5 text-[13px] text-foreground">
                            {tx(label)}
                          </td>
                          <td className="border-b border-hair py-1.5 text-right font-mono text-[13px] tabular-nums text-foreground">
                            {tx(v.toFixed(3))}
                          </td>
                          <td
                            className={`w-16 border-b border-hair py-1.5 pl-2 text-right font-mono text-[13px] tabular-nums ${d == null ? "text-faint" : d >= 0 ? "text-positive" : "text-negative"
                              }`}
                          >
                            {tx(d == null ? "—" : `${d >= 0 ? "+" : "−"}${Math.abs(d).toFixed(3)}`)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                {brPrior && (
                  <p className="mt-2 text-[13px] leading-relaxed text-muted-foreground">{tx("The statement is ")}<b className="font-semibold text-foreground">{tx("cumulative year-to-date")}</b>{tx("; this is the month alone, de-cumulated. Net interest income")}{" "}
                    {tx(signedTrn(br.nii - brPrior.nii))}{tx(" year-on-year and the profit still")}{" "}
                    <b className="font-semibold text-foreground">
                      {tx(br.net < brPrior.net ? "fell" : "rose")}
                    </b>{" "}{tx("— costs ")}{tx(signedTrn(br.opex - brPrior.opex))}{tx(" and trading")}{" "}
                    {tx(signedTrn(br.other - brPrior.other))}{tx(". A YTD average cannot show that.")}</p>
                )}
              </SectorPanel>
            </SectorGrid>
          ) : (
            <p className="max-w-[90ch] border-l-2 border-warning bg-warning/[0.07] py-2 pl-3 text-[13px] leading-relaxed text-foreground">
              <b className="font-semibold">{tx("Income-statement reconciliation is unavailable.")}</b>{tx(" Its parts no longer sum to the statement’s own net-profit line (")}{tx(br ? signedTrn(br.gap) : "—")}{tx("), which means the BDDK item numbering has moved. The chart is not drawn on numbers that do not add up — see the flag above.")}</p>
          )}
<SectorPanel>
<div>
          <SecHead
            title={tx("Profitability components")}
            meta={tx("Deposit costs and net interest income")}
            className="mb-2.5"
          />
          <Transmission items={transmission} />
        </div>
</SectorPanel>
</SectorSection>
<SectorSection id="margins" title={tx("Margins and costs")} description={tx("Net interest margin, operating costs and fee income")}>
<SectorGrid ratio="balanced">
  <SectorTrend data={feeCoverage.filter(row => row.bank_type_code === BANK_TYPES.SECTOR)}
    seriesLabels={{ [BANK_TYPES.SECTOR]: "Fee income / operating costs" }}
    title={tx("Operating costs covered by fee income")}
    description={tx("Fees, commissions and banking-service income relative to operating expenses. The 100% line marks equal income and costs.")}
    source={tx("Source: BDDK monthly bulletin · published ratio, Table 15")}
    references={[{ value: 100, label: "Income equals operating costs" }]} yFormat="pct" decimals={1} height={280} />
  <SectorBreakdown data={feeComparisons} mode="paired" format="pct" decimals={1} maxValue={100}
    series={[{ key: "prior", label: feePriorPeriod ?? "Prior year" }, { key: "current", label: feePeriod ?? "Latest" }]}
    title={tx("Fee coverage by bank group")}
    description={tx("Same calendar month, one year apart. This published fee-to-cost ratio differs from fees as a share of revenue.")}
    source={tx("Source: BDDK monthly bulletin · published ratio, Table 15")} asOf={feePeriod} />
</SectorGrid>
<div className="space-y-1">
            <NimComponentsSection datasets={nimDatasets} dataThrough={nimThrough} />
            <p className="text-[13px] font-medium text-faint">{tx("NIM components of private banks: BDDK monthly income-statement interest items (income 1–14, expense 16–22) over 13-month average total assets. Private = domestic-private + foreign deposit banks.")}</p>
          </div>
<SectorGrid ratio="wide-left">
<SectorTrend mode="trend"

              data={ci.map((c) => ({ period: c.period, bank_type_code: "CI", value: c.value }))}
              seriesLabels={{ CI: "Cost / income" }}
              // The guard tested the DIRECTION; the sentence claims a LEVEL. Cost/
              // income falling below 50% while still improving printed "Costs still
              // eat more than half of income". Every rung now tests what it says.
              title={tx("Operating cost to income")}
              description={<><span className="block">{tx(firstClaim(
                  [
                    ciNow != null && ciNow > 50 && ci12 != null && ciNow < ci12,
                    "Costs still eat more than half of income — but less than they did",
                  ],
                  [
                    ciNow != null && ciNow > 50,
                    tx("Costs eat {0} of income — more than half", { 0: fmtPct(ciNow) }),
                  ],
                  [
                    ciNow != null && ci12 != null,
                    tx("Costs take {0} of income — {1} over 12 months", { 0: fmtPct(ciNow), 1: signedPp((ciNow ?? 0) - (ci12 ?? 0), 1) }),
                  ],
                ) ?? "Cost / income")}</span><span className="mt-1 block">{tx("operating costs ÷ (nii + fees & other), %, monthly · sector")}</span></>}
              source={
                <div className="flex flex-wrap gap-x-4 gap-y-1">
                  <span>{tx("LATEST ")}<b className="font-semibold text-foreground">{tx(fmtPct(ciNow))}</b>
                  </span>
                  <span>{tx("A YEAR AGO ")}<b className="font-semibold text-foreground">{tx(fmtPct(ci12))}</b>
                  </span>
                  <span>
                    Δ 12M{" "}
                    <b className="font-semibold text-foreground">
                      {tx(ciNow != null && ci12 != null ? signedPp(ciNow - ci12, 1) : "—")}
                    </b>
                  </span>
                </div>
              }
              yFormat="pct"
              decimals={1}
              height={320}
              hero="CI"
            />
<SectorPanel>
<Vital
          label={tx("Fees / revenue")}
          value={feesNow != null ? feesNow.toFixed(1) : "—"}
          unit="%"
          series={spark(sectorRows.fees)}
          decimals={1}
          note={<>{tx(feesDelta != null ? signedPp(feesDelta, 1) : "—")} {tx("y/y share of revenue")}</>}
        />
</SectorPanel>
</SectorGrid>
<SectorTrend deltaPeriods={12} deltaLabel="12m" mode="groups"

              data={nim}
              seriesLabels={BANK_TYPE_LABELS}
              title={tx("Net interest margin by bank group")}
              description={<><span className="block">{tx(firstClaim(
                  [
                    nimD != null && nimD > 0 && costD != null && costD < 0,
                    "The margin rebuilt as deposits repriced down",
                  ],
                  [
                    nimD != null && nimD < 0 && costD != null && costD > 0,
                    "The margin compressed as deposits repriced up",
                  ],
                  [
                    nimD != null,
                    tx("Net interest margin {0} over 12 months", { 0: signedPp(nimD ?? 0, 2) }),
                  ],
                ) ?? "Net interest margin — by group")}</span><span className="mt-1 block">{tx("net interest margin, annualized %, monthly · by ownership group")}</span></>}
              source={<ChartFoot data={nim} labels={BANK_TYPE_LABELS} decimals={2} deltaPeriods={12} />}
              yFormat="pct"
              decimals={2}
              height={320}
               />
<SectorTrend deltaPeriods={12} deltaLabel="12m" mode="groups"

              data={opex}
              seriesLabels={BANK_TYPE_LABELS}
              title={tx("Operating costs relative to average assets")}
              description={tx("opex ÷ avg assets, annualized %, monthly · by ownership group")}
              source={<ChartFoot data={opex} labels={BANK_TYPE_LABELS} decimals={2} deltaPeriods={12} />}
              yFormat="pct"
              decimals={2}
              height={320}
               />
<SectorTrend deltaPeriods={12} deltaLabel="12m" mode="groups"

              data={fees}
              seriesLabels={BANK_TYPE_LABELS}
              title={tx("Fee and commission share of revenue")}
              description={tx("fees & commissions ÷ total revenue, %, monthly · by ownership group")}
              source={<ChartFoot data={fees} labels={BANK_TYPE_LABELS} decimals={1} deltaPeriods={12} />}
              yFormat="pct"
              decimals={1}
              height={320}
               />
</SectorSection>

{E && (<SectorSection id="funding-cost" title={tx("Funding cost")} description={tx("Deposit costs and the contribution of demand deposits to profitability.")}>
<SectorPanel>
<Levels
              items={[
                { k: "Demand share", v: E.demandShare.toFixed(1), unit: "%" },
                { k: "Paid on the rest", v: E.paidOnTime.toFixed(1), unit: "%" },
                { k: "Blended cost", v: E.blended.toFixed(1), unit: "%" },
                { k: "The free book, priced", v: `₺${E.worth.toFixed(2)}`, unit: "trn" },
              ]}
            />
</SectorPanel>
<SectorGrid ratio="balanced">
<SectorTrend mode="trend"

                data={[
                  ...eng.map((e) => ({ period: e.period, bank_type_code: "PAID", value: e.paidOnTime })),
                  ...eng.map((e) => ({ period: e.period, bank_type_code: "BLENDED", value: e.blended })),
                  ...cpiAvg
                    .filter((c) => eng.some((e) => e.period === c.period))
                    .map((c) => ({ period: c.period, bank_type_code: "CPI", value: c.value })),
                ]}
                seriesLabels={{
                  PAID: "Paid on time deposits",
                  BLENDED: "Blended cost",
                  CPI: "CPI 12m-avg",
                }}
                title={tx("Deposit cost and inflation")}
                description={<><span className="block">{tx(firstClaim(
                    [
                      blendedGap != null && blendedGap < -5,
                      tx("The sector pays nothing on {0}% of its deposit book — so the blended cost sits far below inflation", { 0: E.demandShare.toFixed(0) }),
                    ],
                    [
                      blendedGap != null && blendedGap < 0,
                      tx("The sector pays nothing on {0}% of its deposit book — enough to hold the blended cost under inflation", { 0: E.demandShare.toFixed(0) }),
                    ],
                    [
                      blendedGap != null,
                      tx("The sector pays nothing on {0}% of its deposit book — yet the blended cost is {1} against inflation", { 0: E.demandShare.toFixed(0), 1: signedPp(blendedGap ?? 0, 1) }),
                    ],
                  ) ?? "Deposit cost against the CPI hurdle")}</span><span className="mt-1 block">{tx("deposit cost, %, monthly · paid on time deposits vs blended, against the CPI hurdle")}</span></>}
                source={
                  <div className="flex flex-wrap gap-x-4 gap-y-1">
                    <span>{tx("PAID ON TIME")}{" "}
                      <b className="font-semibold text-foreground">{tx(fmtPct(E.paidOnTime))}</b>
                    </span>
                    <span>{tx("BLENDED ")}<b className="font-semibold text-foreground">{tx(fmtPct(E.blended))}</b>
                    </span>
                    <span>{tx("FREE FUNDING")}{" "}
                      <b className="font-semibold text-foreground">{tx(E.free.toFixed(1))}{tx("pp")}</b>
                    </span>
                    <span>{tx("CPI ")}<b className="font-semibold text-foreground">{tx(fmtPct(cpiAvgNow))}</b>
                    </span>
                  </div>
                }
                yFormat="pct"
                decimals={1}
                height={320}
                hero="PAID"
              />
<EngineBars
                data={eng.map((e) => ({ period: e.period, worth: e.worth, profit: e.profit }))}
                title={
                  tx(E.ratio > 1
                    ? tx("The free money is worth {0}× the profit it produces", { 0: E.ratio.toFixed(1) })
                    : "The free deposits, priced — against the profit")
                }
                description={tx("₺ trn, annualized, monthly · the demand book priced at the paid rate, vs net profit")}
                source={
                  <div className="flex flex-wrap gap-x-4 gap-y-1">
                    <span>{tx("THE FREE BOOK")}{" "}
                      <b className="font-semibold text-foreground">{tx(fmtTrn(E.worth))}</b>
                    </span>
                    <span>{tx("SECTOR PROFIT")}{" "}
                      <b className="font-semibold text-foreground">{tx(fmtTrn(E.profit))}</b>
                    </span>
                    <span>{tx("RATIO ")}<b className="font-semibold text-foreground">{tx(E.ratio.toFixed(1))}×</b>
                    </span>
                    <span>{tx("18M RANGE")}{" "}
                      <b className="font-semibold text-foreground">
                        {tx(Math.min(...engRatios).toFixed(1))}×–{tx(Math.max(...engRatios).toFixed(1))}×
                      </b>
                    </span>
                  </div>
                }
                height={280}
              />
</SectorGrid>
<SectorPanel>
<p className="mt-4 max-w-[100ch] text-[13px] leading-relaxed text-muted-foreground">
              <b className="font-semibold text-foreground">{tx("A sizing device, not a forecast.")}</b>{" "}{tx("Demand deposits are not literally free — servicing them (branches, payments, cards) is part of the ")}{tx(fmtPct(ciNow))}{tx(" cost/income below — and if the sector paid market rates on them the balance sheet would not stay the same. The arithmetic only says what the free funding is ")}<i>{tx("worth")}</i>{tx(" at the sector’s own paid rate: ")}{tx(fmtTrn(E.worth))}{tx(" a year against ")}{tx(fmtTrn(E.profit))}{tx(" of profit. One ROE is used throughout — BDDK’s published ratio (")}{tx(fmtPct(roeNow))}{tx("); the counterfactual is a cost applied to it, not a second ROE computed a different way.")}</p>
</SectorPanel>
</SectorSection>)}

<SectorDirectory sector="profitability" />
<SectorFooter />
    </SectorReport>
  );
}
