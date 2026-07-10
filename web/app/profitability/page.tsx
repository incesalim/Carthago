/**
 * Profitability tab — ROE, ROA, NIM (all annualized).
 */
import type { Metadata } from "next";
import {
  ratioRoe,
  ratioRoa,
  ratioNim,
  ratioOpex,
  ratioFeesToRevenue,
  leverage,
  evdsSeries,
  nimComponentsRaw,
  latestPeriod,
  PRIMARY_BANK_TYPES,
  BANK_TYPES,
  BANK_TYPE_LABELS,
  type TimeSeriesRow,
} from "@/app/lib/metrics";
import { buildNimDatasets } from "@/app/lib/nim-components";
import { PageHeader, Section, Stat, DeltaBadge } from "@/app/components/ui";
import TrendChart from "@/app/components/TrendChart";
import NimComponentsSection from "./NimComponentsSection";
import Takeaway from "@/app/components/Takeaway";
import { profitabilityInsights } from "@/app/lib/insights";
import { seriesFinding } from "@/app/lib/chart-findings";
import { withLlmHeadline } from "@/app/lib/read-headlines";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkish Banks — Profitability (ROE, ROA, NIM)",
  description: "Profitability of Turkish banks — return on equity, return on assets, net interest margin and pre-provision profit by bank and group.",
  alternates: { canonical: "/profitability" },
};

export default async function ProfitabilityPage() {
  const [
    roe, roa, nim,
    opex, fees, lev,
    cpiRaw, nimRows,
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

  // "The Read" — deterministic, computed from the same series the charts show.
  const sectorOnly = (rows: TimeSeriesRow[]) =>
    rows.filter((r) => r.bank_type_code === BANK_TYPES.SECTOR);
  const read = profitabilityInsights({
    roe: sectorOnly(roe),
    roa: sectorOnly(roa),
    nim: sectorOnly(nim),
    opex: sectorOnly(opex),
    cpi: cpiAvg.map((c) => ({ period: c.period, bank_type_code: "CPI", value: c.value })),
  });

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
  const fmtPct = (v: number | null, d = 1) => (v == null ? "—" : `${v.toFixed(d)}%`);
  // leverage series = liabilities/equity (%); assets/equity = 1 + L/E.
  const levX = latest(lev) != null ? 1 + (latest(lev) as number) / 100 : null;

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      <PageHeader
        title="Profitability"
        description="ROE / ROA / NIM · annualized (YTD × 12 / month) · BDDK Table 15"
        rangeSelector
        dataThrough={latestPeriod(roe, roa, nim)}
      />

      <Takeaway data={await withLlmHeadline("profitability", read)} />

      <Section
        index="01"
        title="The return equation"
        description="ROE ≈ ROA × leverage; ROA is made of margin, fees and cost. Sector, latest month · deltas are y/y in pp."
      >
        <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
          <Stat
            label="ROA · annualized"
            value={fmtPct(latest(sectorRows.roa), 2)}
            badge={<DeltaBadge curr={latest(sectorRows.roa)} prev={yearAgo(sectorRows.roa)} format="pp" decimals={2} />}
          />
          <Stat
            label="× Leverage"
            value={levX != null ? `${levX.toFixed(1)}×` : "—"}
            hint="assets / equity"
          />
          <Stat
            label="= ROE · annualized"
            value={fmtPct(latest(sectorRows.roe))}
            badge={<DeltaBadge curr={latest(sectorRows.roe)} prev={yearAgo(sectorRows.roe)} format="pp" decimals={1} />}
          />
          <Stat
            label="NIM"
            value={fmtPct(latest(sectorRows.nim), 2)}
            badge={<DeltaBadge curr={latest(sectorRows.nim)} prev={yearAgo(sectorRows.nim)} format="pp" decimals={2} />}
          />
          <Stat
            label="Fees / revenue"
            value={fmtPct(latest(sectorRows.fees))}
            badge={<DeltaBadge curr={latest(sectorRows.fees)} prev={yearAgo(sectorRows.fees)} format="pp" decimals={1} />}
          />
          <Stat
            label="OPEX / avg assets"
            value={fmtPct(latest(sectorRows.opex), 2)}
            badge={
              <DeltaBadge
                curr={latest(sectorRows.opex)}
                prev={yearAgo(sectorRows.opex)}
                format="pp"
                decimals={2}
                goodDirection="down"
              />
            }
          />
        </div>
      </Section>

      <Section
        index="02"
        title="Returns"
        description="Return on equity & assets by bank group."
      >
        <TrendChart
          data={roe}
          seriesLabels={BANK_TYPE_LABELS}
          title={
            seriesFinding(roe.filter((r) => r.bank_type_code === BANK_TYPES.SECTOR), { noun: "ROE", decimals: 1 }) ??
            "ROE — Annualized (%)"
          }
          description="Return on equity, %, annualized (YTD × 12/month) · by ownership group"
          source="Source: BDDK monthly bulletin"
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
      </Section>

      {cpiAvg.length > 0 && (
        <Section
          index="03"
          title="Real Returns"
          description="Sector / Private / State ROE alongside the 12-month rolling average of CPI YoY — distance from inflation = real return. In a 28%+ CPI regime this is the number that decides whether the sector earns its cost of capital."
        >
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
        </Section>
      )}

      <Section index="04" title="Margins">
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
      </Section>

      <Section
        index="05"
        title="Cost Efficiency & Non-Interest Income"
        description="Operating cost intensity and fee-driven income contribution."
      >
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
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
        </div>
      </Section>
    </main>
  );
}
