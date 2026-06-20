/**
 * Profitability tab — ROE, ROA, NIM (all annualized).
 */
import {
  ratioRoe,
  ratioRoa,
  ratioNim,
  ratioOpex,
  ratioFeesToRevenue,
  ratioNonInterestCoverage,
  ratioFeesToOpex,
  evdsSeries,
  nimComponentsRaw,
  latestPeriod,
  PRIMARY_BANK_TYPES,
  BANK_TYPES,
  BANK_TYPE_LABELS,
  type TimeSeriesRow,
} from "@/app/lib/metrics";
import { buildNimDatasets } from "@/app/lib/nim-components";
import { PageHeader } from "@/app/components/ui";
import TrendChart from "@/app/components/TrendChart";
import NimComponentsSection from "./NimComponentsSection";

export const dynamic = "force-dynamic";

export default async function ProfitabilityPage() {
  const [
    roe, roa, nim,
    opex, fees, coverage, feesOpex,
    cpiRaw, nimRows,
  ] = await Promise.all([
    ratioRoe(PRIMARY_BANK_TYPES),
    ratioRoa(PRIMARY_BANK_TYPES),
    ratioNim(PRIMARY_BANK_TYPES),
    ratioOpex(PRIMARY_BANK_TYPES),
    ratioFeesToRevenue(PRIMARY_BANK_TYPES),
    ratioNonInterestCoverage(PRIMARY_BANK_TYPES),
    ratioFeesToOpex(PRIMARY_BANK_TYPES),
    // CPI 2025=100 — TP.FG.J0 (2003=100) died at the Jan-2026 TUIK rebase
    evdsSeries("TP.TUKFIY2025.GENEL", 10),
    nimComponentsRaw(),
  ]);

  const nimDatasets = buildNimDatasets(nimRows);
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

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      <PageHeader
        title="Profitability"
        description="ROE / ROA / NIM · annualized (YTD × 12 / month) · BDDK Table 15"
        rangeSelector
        dataThrough={latestPeriod(roe, roa, nim)}
      />

      <section className="space-y-4">
        <div className="space-y-0.5">
          <h2 className="text-base font-semibold text-foreground">Returns</h2>
          <p className="text-xs text-muted-foreground">Return on equity & assets by bank group.</p>
        </div>
        <TrendChart
          data={roe}
          seriesLabels={BANK_TYPE_LABELS}
          title="ROE — Annualized (%)"
          yFormat="pct"
          decimals={1}
          zeroLine
          height={300}
        />
        <TrendChart
          data={roa}
          seriesLabels={BANK_TYPE_LABELS}
          title="ROA — Annualized (%)"
          yFormat="pct"
          decimals={2}
          zeroLine
          height={300}
        />
      </section>

      <section className="space-y-4">
        <div className="space-y-0.5">
          <h2 className="text-base font-semibold text-foreground">Margins</h2>
        </div>
        <TrendChart
          data={nim}
          seriesLabels={BANK_TYPE_LABELS}
          title="Net Interest Margin — Annualized (%)"
          yFormat="pct"
          decimals={2}
        />
        <div className="space-y-1">
          <NimComponentsSection datasets={nimDatasets} dataThrough={nimThrough} />
          <p className="text-xs text-muted-foreground">
            NIM components of private banks:
            BDDK monthly income-statement interest items (income 1–14, expense 16–22)
            over 13-month average total assets. Private = domestic-private + foreign
            deposit banks.
          </p>
        </div>
      </section>

      <section className="space-y-4">
        <div className="space-y-0.5">
          <h2 className="text-base font-semibold text-foreground">Cost Efficiency & Non-Interest Income</h2>
          <p className="text-xs text-muted-foreground">
            Operating cost intensity and fee-driven income contribution.
          </p>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <TrendChart
            data={opex}
            seriesLabels={BANK_TYPE_LABELS}
            title="OPEX / Avg Assets — Annualized (%)"
            yFormat="pct"
            decimals={2}
          />
          <TrendChart
            data={fees}
            seriesLabels={BANK_TYPE_LABELS}
            title="Fees & Commissions / Total Revenue (%)"
            yFormat="pct"
            decimals={1}
          />
          <TrendChart
            data={coverage}
            seriesLabels={BANK_TYPE_LABELS}
            title="Non-Interest Income / Non-Interest Expense (%)"
            yFormat="pct"
            decimals={0}
          />
        </div>
        <TrendChart
          data={feesOpex}
          seriesLabels={BANK_TYPE_LABELS}
          title="Fees & Commissions / OPEX (%) — fee-led cost coverage"
          yFormat="pct"
          decimals={0}
        />
      </section>

      {cpiAvg.length > 0 && (
        <section className="space-y-4">
          <div className="space-y-0.5">
            <h2 className="text-base font-semibold text-foreground">Real Returns</h2>
            <p className="text-xs text-muted-foreground">
              Sector / Private / State ROE alongside the 12-month rolling average of CPI YoY —
              distance from inflation = real return.
            </p>
          </div>
          <TrendChart
            data={roePlusCpi}
            seriesLabels={{
              [BANK_TYPES.SECTOR]: "Sector ROE",
              [BANK_TYPES.PRIVATE]: "Private ROE",
              [BANK_TYPES.STATE]: "State ROE",
              CPI: "CPI 12m avg",
            }}
            title="ROE (annualized) vs CPI 12m avg (%)"
            yFormat="pct"
            decimals={1}
            height={340}
          />
        </section>
      )}
    </main>
  );
}
