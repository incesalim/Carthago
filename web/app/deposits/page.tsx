/**
 * Deposits tab — total, growth, demand share, maturity composition.
 *
 * Levels / growth / demand-share / currency split are sourced from the BDDK
 * *weekly* bulletin (`weekly_series`); the full maturity ladder (`depositMaturityMix`,
 * weekly carries only demand/time/KKM, not the ≤1m…>12m buckets) and the LDR ratio
 * (`ratioLdr`, a published BDDK ratio) stay on the monthly tables. Total demand has no
 * single weekly line — it is summed from the three depositor-type demand components
 * (real-persons 4.0.3 + commercial 4.0.6 + official 4.0.9). Growth: monthly YoY → weekly
 * 52w; the old monthly MoM chart → weekly 4w annualized.
 */
import {
  weeklySeries,
  weeklyGrowth,
  weeklyTotalDepositsYoY,
  depositMaturityMix,
  ratioLdr,
  latestPerBank,
  latestPeriod,
  PRIMARY_BANK_TYPES,
  BANK_TYPES,
  BANK_TYPE_LABELS,
  WEEKLY_BANK_TYPES,
  WEEKLY_BANK_TYPE_LABELS,
  type WeeklyRow,
  type TimeSeriesRow,
} from "@/app/lib/metrics";
import { PageHeader, Section } from "@/app/components/ui";
import BarByBank from "@/app/components/BarByBank";
import TrendChart from "@/app/components/TrendChart";
import StackedArea from "@/app/components/StackedArea";
import Takeaway from "@/app/components/Takeaway";
import { depositsInsights } from "@/app/lib/insights";
import { withLlmHeadline } from "@/app/lib/read-headlines";
import { cpiYoYByMonth, nominalVsReal, REAL_TERMS_LABELS } from "@/app/lib/real-terms";

export const dynamic = "force-dynamic";

const MEVDUAT = "mevduat";
const TOTAL = "4.0.1";
// Demand ("Vadesiz") is split by depositor type in the weekly feed; sum the three.
const DEMAND_PARTS = ["4.0.3", "4.0.6", "4.0.9"];

/** Demand share = demand / total per period (×100). */
function demandShare(total: WeeklyRow[], demand: WeeklyRow[]): TimeSeriesRow[] {
  const totalMap = new Map(total.map((r) => [r.period + "|" + r.bank_type_code, r.value]));
  const out: TimeSeriesRow[] = [];
  for (const r of demand) {
    const t = totalMap.get(r.period + "|" + r.bank_type_code);
    if (t == null || r.value == null || t === 0) continue;
    out.push({ period: r.period, bank_type_code: r.bank_type_code, value: (r.value * 100) / t });
  }
  return out;
}

/** Sum several weekly series element-wise by (period, bank_type_code). */
function sumWeekly(parts: WeeklyRow[][]): WeeklyRow[] {
  const byKey = new Map<string, WeeklyRow>();
  for (const rows of parts) {
    for (const r of rows) {
      if (r.value == null) continue;
      const k = r.period + "|" + r.bank_type_code;
      const cur = byKey.get(k);
      if (cur) cur.value += r.value;
      else byKey.set(k, { period: r.period, bank_type_code: r.bank_type_code, value: r.value });
    }
  }
  return Array.from(byKey.values()).sort((a, b) =>
    a.period === b.period
      ? a.bank_type_code.localeCompare(b.bank_type_code)
      : a.period.localeCompare(b.period),
  );
}

/** Pivot long-form weekly rows into wide {period, [code]: value} rows for StackedArea. */
function pivotByCode(rows: WeeklyRow[], codes: string[]): Record<string, string | number>[] {
  const byPeriod = new Map<string, Record<string, string | number>>();
  for (const r of rows) {
    let row = byPeriod.get(r.period);
    if (!row) {
      row = { period: r.period };
      for (const c of codes) row[c] = 0;
      byPeriod.set(r.period, row);
    }
    row[r.bank_type_code] = r.value ?? 0;
  }
  return Array.from(byPeriod.values()).sort((a, b) =>
    String(a.period).localeCompare(String(b.period)),
  );
}

export default async function DepositsPage() {
  const all = Object.values(WEEKLY_BANK_TYPES);
  const sector = [WEEKLY_BANK_TYPES.SECTOR];
  const groups = all.filter((c) => c !== WEEKLY_BANK_TYPES.SECTOR);

  const [
    depSector, depByGroup, yoyAll, mom4Sector, yoyByBank,
    demandParts,
    tlSec, fxSec,
    mix, ldr, loansYoYSector,
  ] = await Promise.all([
    weeklySeries(MEVDUAT, TOTAL, "TOTAL", sector, 156),
    weeklySeries(MEVDUAT, TOTAL, "TOTAL", groups, 156),
    weeklyGrowth(MEVDUAT, TOTAL, "TOTAL", 52, all, 104),
    weeklyGrowth(MEVDUAT, TOTAL, "TOTAL", 4, sector, 104),
    latestPerBank(weeklyTotalDepositsYoY, groups),
    Promise.all(DEMAND_PARTS.map((id) => weeklySeries(MEVDUAT, id, "TOTAL", sector, 156))),
    weeklySeries(MEVDUAT, TOTAL, "TL", sector, 156),
    weeklySeries(MEVDUAT, TOTAL, "FX", sector, 156),
    depositMaturityMix(BANK_TYPES.SECTOR),
    ratioLdr(PRIMARY_BANK_TYPES),
    // Loan growth (sector) — only for the deposits-vs-loans funding-gap read.
    weeklyGrowth("krediler", "1.0.1", "TOTAL", 52, sector, 104),
  ]);

  const cpiYoY = await cpiYoYByMonth();

  const demandSec = sumWeekly(demandParts);
  const dShare = demandShare(depSector, demandSec);
  const yoySector = yoyAll.filter((r) => r.bank_type_code === WEEKLY_BANK_TYPES.SECTOR);
  // Real-terms twin (Phase 2 convention): the y/y print deflated by CPI y/y.
  const realVsNominal = nominalVsReal(yoySector, cpiYoY);

  // Deposit level composition by ownership group — the 5 weekly groups partition
  // the sector total exactly. Stacked largest-first; colorKeys matches the colours
  // of the by-group YoY line chart below.
  const depByGroupWide = pivotByCode(depByGroup, groups);
  const groupSeries = [
    WEEKLY_BANK_TYPES.STATE,
    WEEKLY_BANK_TYPES.PRIVATE,
    WEEKLY_BANK_TYPES.FOREIGN,
    WEEKLY_BANK_TYPES.PARTICIPATION,
    WEEKLY_BANK_TYPES.DEV_INV,
  ].map((code) => ({ key: code, label: WEEKLY_BANK_TYPE_LABELS[code] }));

  // FX share = FX / (TL + FX) per period
  const tlMap = new Map(tlSec.map((r) => [r.period, r.value]));
  const fxShare: TimeSeriesRow[] = [];
  for (const r of fxSec) {
    const t = tlMap.get(r.period);
    if (t == null || r.value == null) continue;
    const total = t + r.value;
    if (total <= 0) continue;
    fxShare.push({ period: r.period, bank_type_code: WEEKLY_BANK_TYPES.SECTOR, value: (r.value * 100) / total });
  }

  // "The Read" — deterministic, computed from the same series the charts show.
  const read = depositsInsights({
    yoy: yoySector,
    loansYoY: loansYoYSector,
    fxShare,
    demandShare: dShare,
    ldr: ldr.filter((r) => r.bank_type_code === BANK_TYPES.SECTOR),
  });

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      <PageHeader
        title="Deposits"
        description="Sector aggregate + group breakdown · BDDK weekly bulletin (maturity ladder & LDR: monthly)"
        rangeSelector
        dataThrough={latestPeriod(depSector, yoyAll)}
      />

      <Takeaway data={await withLlmHeadline("deposits", read)} />

      <Section index="01" title="Total Deposits Growth">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <StackedArea
            data={depByGroupWide}
            series={groupSeries}
            title="Total Deposits — Level by group (sector, ₺ trn)"
            yFormat="trn"
            decimals={2}
            colorKeys
          />
          <TrendChart
            data={yoyAll}
            seriesLabels={WEEKLY_BANK_TYPE_LABELS}
            title="Deposit Growth YoY (%) by group"
            yFormat="pct"
            decimals={1}
            zeroLine
          />
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <TrendChart
            data={realVsNominal}
            seriesLabels={REAL_TERMS_LABELS}
            title="Deposit Growth YoY — nominal vs real (sector, %)"
            yFormat="pct"
            decimals={1}
            zeroLine
          />
          <TrendChart
            data={mom4Sector}
            seriesLabels={{ [WEEKLY_BANK_TYPES.SECTOR]: "Sector" }}
            title="Deposit Growth 4w (annualized %) — sector"
            yFormat="pct"
            decimals={1}
            zeroLine
          />
          <BarByBank
            data={yoyByBank}
            labels={WEEKLY_BANK_TYPE_LABELS}
            title={`Deposit YoY by group · ${yoyByBank[0]?.period ?? ""}`}
            format="pct"
            decimals={1}
          />
        </div>
      </Section>

      <Section
        index="02"
        title="Dollarization"
        description="The BBVA deposit headline — FX share of the base. The public/private split lives on Liquidity."
      >
        <TrendChart
          data={fxShare}
          seriesLabels={{ [WEEKLY_BANK_TYPES.SECTOR]: "FX share" }}
          title="FX Share of Total Deposits (%)"
          yFormat="pct"
          decimals={1}
          height={320}
        />
      </Section>

      <Section index="03" title="Demand vs. Term" description="Weekly demand share (funding stickiness) + the monthly maturity ladder.">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <TrendChart
            data={dShare}
            seriesLabels={{ [WEEKLY_BANK_TYPES.SECTOR]: "Demand share" }}
            title="Demand Share of Total Deposits (%)"
            yFormat="pct"
            decimals={1}
          />
          <StackedArea
            data={mix}
            series={[
              { key: "demand", label: "Demand" },
              { key: "maturity_1m", label: "≤1m" },
              { key: "maturity_1_3m", label: "1-3m" },
              { key: "maturity_3_6m", label: "3-6m" },
              { key: "maturity_6_12m", label: "6-12m" },
              { key: "maturity_over_12m", label: ">12m" },
            ]}
            title="Maturity Composition (sector · monthly)"
            yFormat="trn"
            decimals={1}
          />
          <StackedArea
            data={mix}
            series={[
              { key: "demand", label: "Demand" },
              { key: "maturity_1m", label: "≤1m" },
              { key: "maturity_1_3m", label: "1-3m" },
              { key: "maturity_3_6m", label: "3-6m" },
              { key: "maturity_6_12m", label: "6-12m" },
              { key: "maturity_over_12m", label: ">12m" },
            ]}
            title="Maturity Composition — Share (% · monthly)"
            percentStack
          />
        </div>
      </Section>

      <Section index="04" title="Loan-to-Deposit Ratio" description="Bank-group LDR — funding pressure indicator (monthly).">
        <TrendChart
          data={ldr}
          seriesLabels={BANK_TYPE_LABELS}
          title="LDR (%) — by group"
          yFormat="pct"
          decimals={0}
          height={320}
        />
      </Section>
    </main>
  );
}
