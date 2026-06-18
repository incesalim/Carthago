/**
 * Credit tab — loan growth, currency split, consumer mix, SME, public vs
 * private differentiator.
 *
 * Sourced from the BDDK *weekly* bulletin (`weekly_series`) for every series the
 * weekly feed carries — fresher and denser than the monthly tables, at the cost
 * of a ~3-year rolling history. The two metrics weekly does NOT carry stay on the
 * monthly tables: the card retail-vs-corporate split (`cardsSplit`) and the SME
 * micro/small/medium mix (`smeBreakdown`). Growth windows: monthly YoY → weekly
 * 52w; the old monthly MoM chart → weekly 4w annualized momentum.
 */
import {
  weeklySeries,
  weeklyGrowth,
  weeklyTotalLoansYoY,
  cardsSplit,
  smeBreakdown,
  latestPerBank,
  latestPeriod,
  WEEKLY_BANK_TYPES,
  WEEKLY_BANK_TYPE_LABELS,
  type WeeklyRow,
  type TimeSeriesRow,
} from "@/app/lib/metrics";
import { PageHeader, Section } from "@/app/components/ui";
import BarByBank from "@/app/components/BarByBank";
import TrendChart from "@/app/components/TrendChart";
import StackedArea from "@/app/components/StackedArea";

export const dynamic = "force-dynamic";

const KREDI = "krediler";
const TOTAL = "1.0.1";
const HOUSING = "1.0.4";
const AUTO = "1.0.5";
const GPL = "1.0.6";
const CARDS = "1.0.8";
const SME = "1.0.11";
const COMMERCIAL = "1.0.12";

/** FX share = fx / (tl + fx) per period (×100). */
function computeFxShare(tl: WeeklyRow[], fx: WeeklyRow[]): TimeSeriesRow[] {
  const tlMap = new Map(tl.map((r) => [r.period + "|" + r.bank_type_code, r.value]));
  const out: TimeSeriesRow[] = [];
  for (const r of fx) {
    const t = tlMap.get(r.period + "|" + r.bank_type_code);
    if (t == null || r.value == null || t + r.value === 0) continue;
    out.push({
      period: r.period,
      bank_type_code: r.bank_type_code,
      value: (r.value * 100) / (t + r.value),
    });
  }
  return out;
}

/** Pivot several weekly series into wide rows ({period, [key]: value}) for StackedArea. */
function joinWeekly(
  parts: { key: string; rows: WeeklyRow[] }[],
): Record<string, string | number>[] {
  const keys = parts.map((p) => p.key);
  const byPeriod = new Map<string, Record<string, string | number>>();
  for (const { key, rows } of parts) {
    for (const r of rows) {
      let row = byPeriod.get(r.period);
      if (!row) {
        row = { period: r.period };
        for (const k of keys) row[k] = 0;
        byPeriod.set(r.period, row);
      }
      row[key] = r.value ?? 0;
    }
  }
  return Array.from(byPeriod.values()).sort((a, b) =>
    String(a.period).localeCompare(String(b.period)),
  );
}

/** Combine several weekly series into long-form rows under synthetic codes. */
function combineWeekly(parts: { code: string; rows: WeeklyRow[] }[]): TimeSeriesRow[] {
  return parts.flatMap(({ code, rows }) =>
    rows.map((r) => ({ period: r.period, bank_type_code: code, value: r.value })),
  );
}

export default async function CreditPage() {
  const all = Object.values(WEEKLY_BANK_TYPES);
  const sector = [WEEKLY_BANK_TYPES.SECTOR];
  const groups = all.filter((c) => c !== WEEKLY_BANK_TYPES.SECTOR);
  const pubPriv = [WEEKLY_BANK_TYPES.PRIVATE, WEEKLY_BANK_TYPES.STATE];
  const smeGroups = [WEEKLY_BANK_TYPES.SECTOR, ...pubPriv];

  const [
    loansSector, tlSec, fxSec,
    yoyAll, mom4Sector, yoyByBank,
    housingLvl, autoLvl, gplLvl, cardsLvl,
    consHousing, consAuto, consGpl, consCards,
    smeYoY, commercialYoY,
    yoyPubPriv, tlYoyPubPriv,
    smeLevel,
    cards, smeBreak,
  ] = await Promise.all([
    weeklySeries(KREDI, TOTAL, "TOTAL", sector, 156),
    weeklySeries(KREDI, TOTAL, "TL", sector, 156),
    weeklySeries(KREDI, TOTAL, "FX", sector, 156),
    weeklyGrowth(KREDI, TOTAL, "TOTAL", 52, all, 104),
    weeklyGrowth(KREDI, TOTAL, "TOTAL", 4, sector, 104),
    latestPerBank(weeklyTotalLoansYoY, groups),
    weeklySeries(KREDI, HOUSING, "TOTAL", sector, 156),
    weeklySeries(KREDI, AUTO, "TOTAL", sector, 156),
    weeklySeries(KREDI, GPL, "TOTAL", sector, 156),
    weeklySeries(KREDI, CARDS, "TOTAL", sector, 156),
    weeklyGrowth(KREDI, HOUSING, "TOTAL", 52, sector, 104),
    weeklyGrowth(KREDI, AUTO, "TOTAL", 52, sector, 104),
    weeklyGrowth(KREDI, GPL, "TOTAL", 52, sector, 104),
    weeklyGrowth(KREDI, CARDS, "TOTAL", 52, sector, 104),
    weeklyGrowth(KREDI, SME, "TOTAL", 52, smeGroups, 104),
    weeklyGrowth(KREDI, COMMERCIAL, "TOTAL", 52, sector, 104),
    weeklyGrowth(KREDI, TOTAL, "TOTAL", 52, pubPriv, 104),
    weeklyGrowth(KREDI, TOTAL, "TL", 52, pubPriv, 104),
    weeklySeries(KREDI, SME, "TOTAL", smeGroups, 156),
    cardsSplit(),
    smeBreakdown(),
  ]);

  const fxShare = computeFxShare(tlSec, fxSec);

  const consMix = joinWeekly([
    { key: "Housing", rows: housingLvl },
    { key: "Auto", rows: autoLvl },
    { key: "Gen. Purpose", rows: gplLvl },
    { key: "Retail Cards", rows: cardsLvl },
  ]);

  const consYoYLong = combineWeekly([
    { code: "HOUSING", rows: consHousing },
    { code: "AUTO", rows: consAuto },
    { code: "GPL", rows: consGpl },
    { code: "CARDS", rows: consCards },
  ]);

  const smeVsCommercial = combineWeekly([
    { code: "SME", rows: smeYoY.filter((r) => r.bank_type_code === WEEKLY_BANK_TYPES.SECTOR) },
    { code: "COMMERCIAL", rows: commercialYoY },
  ]);

  const pubPrivSet = new Set<string>(pubPriv);
  const consMixSeries = [
    { key: "Housing", label: "Housing" },
    { key: "Auto", label: "Auto" },
    { key: "Gen. Purpose", label: "Gen. Purpose" },
    { key: "Retail Cards", label: "Retail Cards" },
  ];

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      <PageHeader
        title="Credit"
        description="Loan growth · currency split · consumer mix · SME · public vs. private — BDDK weekly bulletin (card split & SME size-mix: monthly)"
        dataThrough={latestPeriod(loansSector, yoyAll)}
      />

      <Section title="Total Credit Growth" description="Sector level + cross-sectional and short-window momentum.">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TrendChart
            data={loansSector}
            seriesLabels={{ [WEEKLY_BANK_TYPES.SECTOR]: "Sector" }}
            title="Total Loans — Level (sector)"
            yFormat="trn"
            decimals={2}
          />
          <TrendChart
            data={yoyAll}
            seriesLabels={WEEKLY_BANK_TYPE_LABELS}
            title="Loan Growth YoY (%) by group"
            yFormat="pct"
            decimals={1}
            zeroLine
          />
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2">
            <TrendChart
              data={mom4Sector}
              seriesLabels={{ [WEEKLY_BANK_TYPES.SECTOR]: "Sector" }}
              title="Loan Growth 4w (annualized %) — sector"
              yFormat="pct"
              decimals={1}
              zeroLine
            />
          </div>
          <BarByBank
            data={yoyByBank}
            labels={WEEKLY_BANK_TYPE_LABELS}
            title={`Loan YoY by group · ${yoyByBank[0]?.period ?? ""}`}
            format="pct"
            decimals={1}
          />
        </div>
      </Section>

      <Section title="Currency Breakdown" description="FX exposure stays moderate; TL drives sector growth.">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <TrendChart
            data={tlSec}
            seriesLabels={{ [WEEKLY_BANK_TYPES.SECTOR]: "TL Loans" }}
            title="TL Loans — Level"
            yFormat="trn"
            decimals={2}
          />
          <TrendChart
            data={fxSec}
            seriesLabels={{ [WEEKLY_BANK_TYPES.SECTOR]: "FX Loans" }}
            title="FX Loans — Level (TL equivalent)"
            yFormat="trn"
            decimals={2}
          />
          <TrendChart
            data={fxShare}
            seriesLabels={{ [WEEKLY_BANK_TYPES.SECTOR]: "FX share" }}
            title="FX Share of Total Loans (%)"
            yFormat="pct"
            decimals={1}
          />
        </div>
      </Section>

      <Section title="Consumer Credit" description="Composition of household lending — cards & GPL drive the bulk.">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <StackedArea
            data={consMix}
            series={consMixSeries}
            title="Consumer Credit Mix — Level (sector)"
            yFormat="trn"
            decimals={2}
          />
          <StackedArea
            data={consMix}
            series={consMixSeries}
            title="Consumer Credit Mix — Share (%)"
            percentStack
          />
        </div>
      </Section>

      <Section title="Consumer Segments" description="Per-product growth — cards & GPL drive the headline number.">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TrendChart
            data={consYoYLong}
            seriesLabels={{
              HOUSING: "Housing",
              AUTO: "Auto",
              GPL: "Gen. Purpose",
              CARDS: "Retail Cards",
            }}
            title="Consumer Segment YoY Growth (%)"
            yFormat="pct"
            decimals={1}
            zeroLine
          />
          <TrendChart
            data={cards.flatMap((r: { period: string; retail: number | null; corporate: number | null }) => {
              const out: TimeSeriesRow[] = [];
              if (r.retail    != null) out.push({ period: r.period, bank_type_code: "RETAIL",    value: r.retail });
              if (r.corporate != null) out.push({ period: r.period, bank_type_code: "CORPORATE", value: r.corporate });
              return out;
            })}
            seriesLabels={{ RETAIL: "Retail Cards", CORPORATE: "Corporate Cards" }}
            title="Credit Cards — Retail vs Corporate (Level · monthly)"
            yFormat="bn"
            decimals={0}
          />
        </div>
      </Section>

      <Section title="SME & Public vs. Private" description="Public bank lending vs. private bank lending — the clearest sector signal.">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TrendChart
            data={smeYoY}
            seriesLabels={{
              [WEEKLY_BANK_TYPES.SECTOR]: "Sector",
              [WEEKLY_BANK_TYPES.PRIVATE]: "Private",
              [WEEKLY_BANK_TYPES.STATE]: "State",
            }}
            title="SME Loan Growth YoY (%)"
            yFormat="pct"
            decimals={1}
            zeroLine
          />
          <TrendChart
            data={smeVsCommercial}
            seriesLabels={{ SME: "SME", COMMERCIAL: "Commercial (incl. corp.)" }}
            title="SME vs Commercial — YoY Growth (%)"
            yFormat="pct"
            decimals={1}
            zeroLine
          />
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TrendChart
            data={yoyPubPriv}
            seriesLabels={{
              [WEEKLY_BANK_TYPES.PRIVATE]: "Private",
              [WEEKLY_BANK_TYPES.STATE]: "State",
            }}
            title="Total Credit YoY — Public vs Private"
            yFormat="pct"
            decimals={1}
            zeroLine
          />
          <TrendChart
            data={tlYoyPubPriv}
            seriesLabels={{
              [WEEKLY_BANK_TYPES.PRIVATE]: "Private",
              [WEEKLY_BANK_TYPES.STATE]: "State",
            }}
            title="TL Loans YoY — Public vs Private"
            yFormat="pct"
            decimals={1}
            zeroLine
          />
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TrendChart
            data={smeLevel.filter((r) => r.bank_type_code === WEEKLY_BANK_TYPES.SECTOR)}
            seriesLabels={{ [WEEKLY_BANK_TYPES.SECTOR]: "SME" }}
            title="SME Loans — Level (sector)"
            yFormat="trn"
            decimals={2}
          />
          <TrendChart
            data={smeLevel.filter((r) => pubPrivSet.has(r.bank_type_code))}
            seriesLabels={{
              [WEEKLY_BANK_TYPES.PRIVATE]: "Private",
              [WEEKLY_BANK_TYPES.STATE]: "State",
            }}
            title="SME Loans — Public vs Private (Level)"
            yFormat="trn"
            decimals={2}
          />
        </div>
        <StackedArea
          data={smeBreak.map((r: { period: string; micro: number | null; small: number | null; medium: number | null }) => ({
            period: r.period,
            Micro: r.micro ?? 0,
            Small: r.small ?? 0,
            Medium: r.medium ?? 0,
          }))}
          series={[
            { key: "Micro", label: "Micro" },
            { key: "Small", label: "Small" },
            { key: "Medium", label: "Medium" },
          ]}
          title="SME Mix — Micro / Small / Medium (sector, TL bn · monthly)"
          yFormat="bn"
          decimals={0}
        />
      </Section>
    </main>
  );
}
