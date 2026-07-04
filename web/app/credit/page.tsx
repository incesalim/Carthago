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
  evdsSeries,
  WEEKLY_BANK_TYPES,
  WEEKLY_BANK_TYPE_LABELS,
  type WeeklyRow,
  type TimeSeriesRow,
  type EvdsRow,
} from "@/app/lib/metrics";
import { PageHeader, Section } from "@/app/components/ui";
import BarByBank from "@/app/components/BarByBank";
import TrendChart from "@/app/components/TrendChart";
import StackedArea from "@/app/components/StackedArea";
import Takeaway from "@/app/components/Takeaway";
import { creditInsights } from "@/app/lib/insights";
import { withLlmHeadline } from "@/app/lib/read-headlines";
import { cpiYoYByMonth, nominalVsReal, REAL_TERMS_LABELS } from "@/app/lib/real-terms";

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

/**
 * FX-adjusted loan growth (BBVA convention, 52w): value BOTH periods' FX book
 * at the BASE period's USD/TRY, so lira depreciation stops printing as credit
 * growth. FX book proxied as all-USD (BDDK publishes TL-equivalent only).
 */
function fxAdjustedYoY(tl: WeeklyRow[], fx: WeeklyRow[], usd: EvdsRow[]): TimeSeriesRow[] {
  const rateByDate = new Map(usd.map((r) => [r.period_date, r.value]));
  const rateOnOrBefore = (d: string): number | null => {
    const dt = new Date(d + "T00:00:00Z");
    for (let i = 0; i < 10; i++) {
      const v = rateByDate.get(dt.toISOString().slice(0, 10));
      if (v != null && v > 0) return v;
      dt.setUTCDate(dt.getUTCDate() - 1);
    }
    return null;
  };
  const tlByPeriod = new Map(tl.map((r) => [r.period, r.value]));
  const fxSorted = fx.slice().sort((a, b) => a.period.localeCompare(b.period));
  const out: TimeSeriesRow[] = [];
  for (let i = 52; i < fxSorted.length; i++) {
    const cur = fxSorted[i];
    const base = fxSorted[i - 52];
    const tlCur = tlByPeriod.get(cur.period);
    const tlBase = tlByPeriod.get(base.period);
    const rCur = rateOnOrBefore(cur.period);
    const rBase = rateOnOrBefore(base.period);
    if (tlCur == null || tlBase == null || rCur == null || rBase == null) continue;
    const num = tlCur + (cur.value / rCur) * rBase;
    const den = tlBase + base.value; // base FX book already at base rate
    if (den <= 0) continue;
    out.push({ period: cur.period, bank_type_code: "FXADJ", value: (num / den - 1) * 100 });
  }
  return out;
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
  const [cpiYoY, usdTry] = await Promise.all([cpiYoYByMonth(), evdsSeries("TP.DK.USD.A", 4)]);

  const fxShare = computeFxShare(tlSec, fxSec);
  const yoySector = yoyAll.filter((r) => r.bank_type_code === WEEKLY_BANK_TYPES.SECTOR);
  // Real-terms twin (Phase 2 convention): the y/y print deflated by CPI y/y.
  const realVsNominal = nominalVsReal(yoySector, cpiYoY);
  // FX-adjusted growth vs the nominal print — the BBVA headline credit metric.
  const fxAdjVsNominal: TimeSeriesRow[] = [
    ...yoySector.map((r) => ({ ...r, bank_type_code: "NOMINAL" })),
    ...fxAdjustedYoY(tlSec, fxSec, usdTry),
  ];

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

  // "The Read" — deterministic, computed from the same series the charts show.
  const read = creditInsights({
    yoy: yoySector,
    mom4: mom4Sector,
    yoyState: yoyPubPriv.filter((r) => r.bank_type_code === WEEKLY_BANK_TYPES.STATE),
    yoyPrivate: yoyPubPriv.filter((r) => r.bank_type_code === WEEKLY_BANK_TYPES.PRIVATE),
    fxShare,
    cardsYoY: consCards,
    smeYoY: smeYoY.filter((r) => r.bank_type_code === WEEKLY_BANK_TYPES.SECTOR),
  });

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
        rangeSelector
        dataThrough={latestPeriod(loansSector, yoyAll)}
      />

      <Takeaway data={await withLlmHeadline("credit", read)} />

      <Section
        index="01"
        title="Total Credit Growth"
        description="Growth by ownership group + short-window momentum. Levels: see the Overview snapshot."
      >
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2">
            <TrendChart
              data={yoyAll}
              seriesLabels={WEEKLY_BANK_TYPE_LABELS}
              title="Loan Growth YoY (%) by group"
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
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <TrendChart
            data={realVsNominal}
            seriesLabels={REAL_TERMS_LABELS}
            title="Loan Growth YoY — nominal vs real (sector, %)"
            yFormat="pct"
            decimals={1}
            zeroLine
          />
          <TrendChart
            data={fxAdjVsNominal}
            seriesLabels={{ NOMINAL: "Nominal", FXADJ: "FX-adjusted (constant USD/TRY)" }}
            title="Loan Growth YoY — FX-adjusted (sector, %)"
            yFormat="pct"
            decimals={1}
            zeroLine
          />
          <TrendChart
            data={mom4Sector}
            seriesLabels={{ [WEEKLY_BANK_TYPES.SECTOR]: "Sector" }}
            title="Loan Growth 4w (annualized %) — sector"
            yFormat="pct"
            decimals={1}
            zeroLine
          />
        </div>
      </Section>

      <Section
        index="02"
        title="Public vs Private & Currency"
        description="The clearest sector signal — who is driving the lending cycle, and in which currency."
      >
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
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
          <TrendChart
            data={fxShare}
            seriesLabels={{ [WEEKLY_BANK_TYPES.SECTOR]: "FX share" }}
            title="FX Share of Total Loans (%)"
            yFormat="pct"
            decimals={1}
          />
        </div>
      </Section>

      <Section index="03" title="Consumer Credit" description="Composition of household lending — cards & GPL drive the bulk.">
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

      <Section index="04" title="Consumer Segments" description="Per-product growth — cards & GPL drive the headline number.">
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

      <Section index="05" title="SME Lending" description="The SME cycle vs the commercial book — level detail for the digger.">
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
