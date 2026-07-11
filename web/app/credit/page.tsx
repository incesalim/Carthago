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
import type { Metadata } from "next";
import Link from "next/link";
import {
  weeklySeries,
  weeklyGrowth,
  weeklyTotalLoansYoY,
  cardsSplit,
  smeBreakdown,
  latestPerBank,
  evdsSeries,
  WEEKLY_BANK_TYPES,
  WEEKLY_BANK_TYPE_LABELS,
  type WeeklyRow,
  type TimeSeriesRow,
  type EvdsRow,
} from "@/app/lib/metrics";
import { Section } from "@/app/components/ui";
import {
  ChartRow,
  Colophon,
  Depth,
  DeskHeader,
  SecHead,
  Vital,
  Vitals,
} from "@/app/components/desk";
import { lastVal, monthLabel, signedPp, valAgo } from "@/app/lib/desk";
import { GlobalRangeSelector } from "@/app/components/range-context";
import BarByBank from "@/app/components/BarByBank";
import TrendChart from "@/app/components/TrendChart";
import StackedArea from "@/app/components/StackedArea";
import Takeaway from "@/app/components/Takeaway";
import { creditInsights } from "@/app/lib/insights";
import { seriesFinding } from "@/app/lib/chart-findings";
import { withLlmHeadline } from "@/app/lib/read-headlines";
import { cpiYoYByMonth, nominalVsReal, REAL_TERMS_LABELS } from "@/app/lib/real-terms";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkish Banking Sector — Loans & Credit",
  description: "Loan growth and credit dynamics in Türkiye — TL vs FX, by sector and by bank type, from BDDK weekly and monthly data.",
  alternates: { canonical: "/credit" },
};

const KREDI = "krediler";
const TOTAL = "1.0.1";
const HOUSING = "1.0.4";
const AUTO = "1.0.5";
const GPL = "1.0.6";
const CARDS = "1.0.8";
const SME = "1.0.11";
const COMMERCIAL = "1.0.12";

/** 'YYYY-MM-DD' → '04 Jul 2026' / '04 Jul' — the weekly record line. */
function weekLabel(p: string | null | undefined, withYear = true): string {
  const m = p ? /^\d{4}-\d{2}-(\d{2})/.exec(p) : null;
  return m ? `${m[1]} ${monthLabel(p, withYear)}` : monthLabel(p, withYear);
}

const fmtPct = (v: number | null | undefined, d = 1) =>
  v == null ? "—" : `${v.toFixed(d)}%`;

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

  const yoyState = yoyPubPriv.filter((r) => r.bank_type_code === WEEKLY_BANK_TYPES.STATE);
  const yoyPrivate = yoyPubPriv.filter((r) => r.bank_type_code === WEEKLY_BANK_TYPES.PRIVATE);
  const smeSector = smeYoY.filter((r) => r.bank_type_code === WEEKLY_BANK_TYPES.SECTOR);

  // "The Read" — deterministic, computed from the same series the charts show.
  const read = creditInsights({
    yoy: yoySector,
    mom4: mom4Sector,
    yoyState,
    yoyPrivate,
    fxShare,
    cardsYoY: consCards,
    smeYoY: smeSector,
  });
  const readData = await withLlmHeadline("credit", read);

  // ---- the vitals — every figure computed from the series above -------------
  const recWeek = weekLabel(loansSector.at(-1)?.period);
  const vsWeek = weekLabel(loansSector.at(-2)?.period, false);

  const yoyNow = lastVal(yoySector);
  const mom4Now = lastVal(mom4Sector);
  const realSeries = realVsNominal.filter((r) => r.bank_type_code === "REAL");
  const realNow = lastVal(realSeries);

  const fxShareNow = lastVal(fxShare);
  const fxShare52 = valAgo(fxShare, 52);
  const fxShareDelta = fxShareNow != null && fxShare52 != null ? fxShareNow - fxShare52 : null;

  const stateNow = lastVal(yoyState);
  const privNow = lastVal(yoyPrivate);
  const gapNow = stateNow != null && privNow != null ? stateNow - privNow : null;
  const privByPeriod = new Map(yoyPrivate.map((r) => [r.period, r.value]));
  // State − private gap, paired by date (row offsets are unsafe on weekly data).
  const gapSeries: TimeSeriesRow[] = yoyState.flatMap((r) => {
    const p = privByPeriod.get(r.period);
    return p == null || r.value == null
      ? []
      : [{ period: r.period, bank_type_code: "GAP", value: r.value - p }];
  });

  const smeNow = lastVal(smeSector);
  const commNow = lastVal(commercialYoY);

  const cardsNow = lastVal(consCards);
  const segReads: [string, number | null][] = [
    ["housing", lastVal(consHousing)],
    ["auto", lastVal(consAuto)],
    ["general-purpose", lastVal(consGpl)],
    ["retail cards", lastVal(consCards)],
  ];
  let fastestSeg: { name: string; v: number } | null = null;
  for (const [name, v] of segReads) {
    if (v != null && (fastestSeg == null || v > fastestSeg.v)) fastestSeg = { name, v };
  }

  const consMixSeries = [
    { key: "Housing", label: "Housing" },
    { key: "Auto", label: "Auto" },
    { key: "Gen. Purpose", label: "Gen. Purpose" },
    { key: "Retail Cards", label: "Retail Cards" },
  ];

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title="Credit"
        record={
          <>
            Record <b className="font-normal text-foreground">W/E {recWeek}</b> · vs {vsWeek}
          </>
        }
        right="every figure computed from source series"
      />

      {/* ── The vitals ─────────────────────────────────────────────────── */}
      <SecHead
        title="The vitals"
        meta="equal weight · trailing 26 weeks"
        className="mb-2.5 mt-6"
      />
      <Vitals>
        <Vital
          label="Loan growth, 52w"
          value={yoyNow != null ? yoyNow.toFixed(1) : "—"}
          unit="%"
          series={yoySector.slice(-26)}
          decimals={1}
          note={
            realNow != null ? (
              <>
                ≈{" "}
                <em
                  className={
                    realNow < 0
                      ? "not-italic font-semibold text-negative"
                      : "not-italic font-semibold text-positive"
                  }
                >
                  {realNow >= 0 ? "+" : "−"}
                  {Math.abs(realNow).toFixed(1)}% real
                </em>{" "}
                (CPI-deflated)
              </>
            ) : (
              "real twin awaits the CPI print"
            )
          }
        />
        <Vital
          label="4w momentum, ann."
          value={mom4Now != null ? mom4Now.toFixed(1) : "—"}
          unit="%"
          series={mom4Sector.slice(-26)}
          decimals={1}
          note={
            mom4Now != null && yoyNow != null ? (
              <>
                {signedPp(mom4Now - yoyNow, 1)} vs the 52w pace —{" "}
                {mom4Now > yoyNow ? "accelerating" : "cooling"}
              </>
            ) : undefined
          }
        />
        <Vital
          label="FX share of loans"
          value={fxShareNow != null ? fxShareNow.toFixed(1) : "—"}
          unit="%"
          series={fxShare.slice(-26)}
          decimals={1}
          note={
            <>
              {fxShareDelta != null ? `${signedPp(fxShareDelta, 1)} over 52w` : "share of the total book"}{" "}
              <Link href="/deposits" className="font-semibold text-primary">
                /deposits
              </Link>
            </>
          }
        />
        <Vital
          label="State − private gap"
          value={gapNow != null ? `${gapNow >= 0 ? "+" : "−"}${Math.abs(gapNow).toFixed(1)}` : "—"}
          unit="pp"
          series={gapSeries.slice(-26)}
          format="raw"
          decimals={1}
          note={
            stateNow != null && privNow != null && gapNow != null ? (
              <>
                state {fmtPct(stateNow)} vs private {fmtPct(privNow)} —{" "}
                {gapNow >= 0 ? "state banks lead the cycle" : "private banks lead the cycle"}
              </>
            ) : undefined
          }
        />
        <Vital
          label="SME growth, 52w"
          value={smeNow != null ? smeNow.toFixed(1) : "—"}
          unit="%"
          series={smeSector.slice(-26)}
          decimals={1}
          note={
            smeNow != null && commNow != null ? (
              <>
                {smeNow >= commNow ? "outpaces" : "trails"} commercial {fmtPct(commNow)} by{" "}
                {Math.abs(smeNow - commNow).toFixed(1)}pp
              </>
            ) : undefined
          }
        />
        <Vital
          label="Retail cards, 52w"
          value={cardsNow != null ? cardsNow.toFixed(1) : "—"}
          unit="%"
          series={consCards.slice(-26)}
          decimals={1}
          note={
            fastestSeg ? (
              fastestSeg.name === "retail cards" ? (
                <>the fastest consumer segment</>
              ) : (
                <>
                  fastest segment: {fastestSeg.name} at {fastestSeg.v.toFixed(1)}%
                </>
              )
            ) : undefined
          }
        />
      </Vitals>

      {/* ── In depth — the evidence layer ──────────────────────────────── */}
      <Depth action={<GlobalRangeSelector />}>
        <Takeaway data={readData} />

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
                title={
                  seriesFinding(yoySector, { noun: "Loan growth", decimals: 1 }) ??
                  "Loan Growth YoY (%) by group"
                }
                description="Loan growth YoY, %, weekly · by ownership group"
                source="Source: BDDK weekly bulletin"
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
          <ChartRow
            data={smeBreak.flatMap((r: { period: string; micro: number | null; small: number | null; medium: number | null }) => [
              { period: r.period, bank_type_code: "Micro", value: r.micro },
              { period: r.period, bank_type_code: "Small", value: r.small },
              { period: r.period, bank_type_code: "Medium", value: r.medium },
            ])}
            deltaPeriods={12}
            deltaLabel="12m"
            fmt={(v) => `₺${(v / 1_000).toFixed(0)}bn`}
          >
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
          </ChartRow>
        </Section>
      </Depth>

      <Colophon />
    </main>
  );
}
