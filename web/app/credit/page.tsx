import { SectorReport, SectorHeader, SectorContents, SectorMetrics, SectorOpening, SectorGrid, SectorPanel, SectorSection, SectorDirectory, SectorFooter } from "@/app/components/sector-report";
/**
 * Credit analysis: currency-adjusted momentum, allocation and product detail.
 * Weekly activity and monthly structural snapshots retain their own dates.
 * Real purchasing power and the exchange-rate/inflation bridge remain a
 * separate analysis; research conditions stay in the admin workspace.
 */
import { localizeMetadata } from "@/i18n/metadata";
import { getText } from "@/i18n/server";
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
} from "@/app/lib/metrics";
import {
  ChartRow,
  Movers,
  SecHead,
  Vital,
  type MoverRow,
} from "@/app/components/desk";
import { lastVal, monthLabel, signedPp, valAgo } from "@/app/lib/desk";
import { claim, runPhrase } from "@/app/lib/prose";
import {
  annualizeGrowth,
  contributions,
  creditBridge,
  deflate,
  fxAdjustedGrowth,
  sumSeries,
  trailingRun,
  trailingRunVs,
  type Pt,
} from "@/app/lib/credit";
import { GlobalRangeSelector } from "@/app/components/range-context";
import SectorBreakdown from "@/app/components/SectorBreakdown";
import { loadCreditStructure } from "@/app/lib/sector-credit";
import SectorTrend from "@/app/components/SectorTrend";
import StackedArea from "@/app/components/StackedArea";
import Takeaway from "@/app/components/Takeaway";
import { creditInsights } from "@/app/lib/insights";
import { seriesFinding } from "@/app/lib/chart-findings";
import { withLlmHeadline } from "@/app/lib/read-headlines";
import { cpiYoYByMonth, nominalVsReal, REAL_TERMS_LABELS } from "@/app/lib/real-terms";
import Attribution from "@/app/components/Attribution";
import Bridge from "./Bridge";

export const dynamic = "force-dynamic";

const pageMetadata: Metadata = {
  title: "Turkish Banking Sector — Loans & Credit",
  description:
    "Loan growth and credit dynamics in Türkiye — nominal vs real and FX-adjusted, by segment, currency and bank type, from BDDK weekly and monthly data.",
  alternates: { canonical: "/credit" },
};

export async function generateMetadata(): Promise<Metadata> {
  return localizeMetadata(pageMetadata);
}

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

const fmtPct = (v: number | null | undefined, d = 1) => (v == null ? "—" : `${v.toFixed(d)}%`);

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
): Record<string, string | number | null>[] {
  const keys = parts.map((p) => p.key);
  const byPeriod = new Map<string, Record<string, string | number | null>>();
  for (const { key, rows } of parts) {
    for (const r of rows) {
      let row = byPeriod.get(r.period);
      if (!row) {
        row = { period: r.period };
        for (const k of keys) row[k] = null;
        byPeriod.set(r.period, row);
      }
      row[key] = r.value ?? null;
    }
  }
  return Array.from(byPeriod.values()).sort((a, b) =>
    String(a.period).localeCompare(String(b.period)),
  );
}

/** Combine several weekly series into long-form rows under synthetic codes. */
function combineWeekly(parts: { code: string; rows: Pt[] }[]): TimeSeriesRow[] {
  return parts.flatMap(({ code, rows }) =>
    rows.flatMap((r) =>
      r.value == null ? [] : [{ period: r.period, bank_type_code: code, value: r.value }],
    ),
  );
}

export default async function CreditPage() {
  const tx = await getText();
  const all = Object.values(WEEKLY_BANK_TYPES);
  const sector = [WEEKLY_BANK_TYPES.SECTOR];
  const groups = all.filter((c) => c !== WEEKLY_BANK_TYPES.SECTOR);
  const pubPriv = [WEEKLY_BANK_TYPES.PRIVATE, WEEKLY_BANK_TYPES.STATE];
  const smeGroups = [WEEKLY_BANK_TYPES.SECTOR, ...pubPriv];

  const [
    loansSector, tlSec, fxSec,
    yoyAll, mom4Sector, yoyByBank,
    housingLvl, autoLvl, gplLvl, cardsLvl, smeLvlSec, commLvlSec,
    consHousing, consAuto, consGpl, consCards,
    smeYoY, commercialYoY,
    yoyPubPriv, tlYoyPubPriv,
    smeLevel,
    cards, smeBreak,
    tlByGroup, fxByGroup, cardInstalments, cardNonInstalments, consumerOverdraft, commercialOverdraft, structure,
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
    weeklySeries(KREDI, SME, "TOTAL", sector, 156),
    weeklySeries(KREDI, COMMERCIAL, "TOTAL", sector, 156),
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
    weeklySeries(KREDI, TOTAL, "TL", pubPriv, 156),
    weeklySeries(KREDI, TOTAL, "FX", pubPriv, 156),
    weeklySeries(KREDI, "1.0.9", "TOTAL", sector, 156),
    weeklySeries(KREDI, "1.0.10", "TOTAL", sector, 156),
    weeklySeries(KREDI, "1.0.23", "TOTAL", sector, 156),
    weeklySeries(KREDI, "1.0.24", "TOTAL", sector, 156),
    loadCreditStructure(),
  ]);
  const [cpiYoY, usdTry] = await Promise.all([cpiYoYByMonth(), evdsSeries("TP.DK.USD.A", 4)]);

  const fxShare = computeFxShare(tlSec, fxSec);
  const yoySector = yoyAll.filter((r) => r.bank_type_code === WEEKLY_BANK_TYPES.SECTOR);

  // ---- the bridge: nominal → −currency → −inflation → real ------------------
  const fxAdjSeries = fxAdjustedGrowth(tlSec, fxSec, usdTry);
  const fxAdj13w = annualizeGrowth(fxAdjustedGrowth(tlSec, fxSec, usdTry, 13 * 7), 13 * 7);
  const momentumByGroup = combineWeekly([
    { code: WEEKLY_BANK_TYPES.SECTOR, rows: fxAdj13w },
    ...pubPriv.map(code => ({ code, rows: annualizeGrowth(fxAdjustedGrowth(
      tlByGroup.filter(row => row.bank_type_code === code),
      fxByGroup.filter(row => row.bank_type_code === code), usdTry, 13 * 7,
    ), 13 * 7) })),
  ]);
  const instalmentMix = joinWeekly([
    { key: "INSTALMENTS", rows: cardInstalments },
    { key: "NON_INSTALMENTS", rows: cardNonInstalments },
  ]);
  const overdrafts = combineWeekly([
    { code: "CONSUMER", rows: consumerOverdraft },
    { code: "COMMERCIAL", rows: commercialOverdraft },
  ]);
  const realFxAdjSeries = deflate(fxAdjSeries, cpiYoY);
  const bridge = creditBridge(yoySector, fxAdjSeries, cpiYoY);

  // The hero chart: the three prints of the same book, on one axis. This
  // subsumes the old standalone "FX-adjusted vs nominal" chart (both its series
  // appear here) and adds the composed line neither twin showed.
  const threePrints: TimeSeriesRow[] = [
    ...yoySector.map((r) => ({ ...r, bank_type_code: "NOMINAL" })),
    ...combineWeekly([
      { code: "FXADJ", rows: fxAdjSeries },
      { code: "REALFX", rows: realFxAdjSeries },
    ]),
  ];
  // Real-terms twin (Phase 2 convention) — kept as its own chart.
  const realVsNominal = nominalVsReal(yoySector, cpiYoY);

  // ---- attribution: where the headline came from ----------------------------
  // Disjoint + exhaustive: housing + auto + GPL + cards + commercial reconciles
  // to the BDDK sector total. SME is a CUT of commercial — never an addend.
  const attrib = contributions(loansSector, [
    { key: "commercial", label: "Commercial", rows: commLvlSec },
    { key: "cards", label: "Retail cards", rows: cardsLvl },
    { key: "gpl", label: "Gen. purpose", rows: gplLvl },
    { key: "housing", label: "Housing", rows: housingLvl },
    { key: "auto", label: "Auto", rows: autoLvl },
  ]);
  const smeCut = contributions(loansSector, [{ key: "sme", label: "SME", rows: smeLvlSec }]);
  const smeContrib = smeCut.items[0] ?? null;

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

  const smeSector = smeYoY.filter((r) => r.bank_type_code === WEEKLY_BANK_TYPES.SECTOR);
  const smeVsCommercial = combineWeekly([
    { code: "SME", rows: smeSector },
    { code: "COMMERCIAL", rows: commercialYoY },
  ]);

  const pubPrivSet = new Set<string>(pubPriv);
  const yoyState = yoyPubPriv.filter((r) => r.bank_type_code === WEEKLY_BANK_TYPES.STATE);
  const yoyPrivate = yoyPubPriv.filter((r) => r.bank_type_code === WEEKLY_BANK_TYPES.PRIVATE);

  // Unsecured retail = the COMBINED cards + GPL book. Growth of the summed
  // level — never the mean of two growth rates, which would weight a ₺2.5trn
  // book like a ₺3.3trn one.
  const unsecuredLvl = sumSeries(cardsLvl, gplLvl);
  const unsecuredYoY = (() => {
    const out: Pt[] = [];
    const m = new Map(unsecuredLvl.map((r) => [r.period, r.value]));
    for (const r of unsecuredLvl) {
      if (r.value == null) continue;
      for (const days of [364, 371, 357]) {
        const base = m.get(
          new Date(Date.parse(r.period + "T00:00:00Z") - days * 86_400_000)
            .toISOString()
            .slice(0, 10),
        );
        if (base != null && base > 0) {
          out.push({ period: r.period, value: (Math.pow(r.value / base, 364 / days) - 1) * 100 });
          break;
        }
      }
    }
    return out;
  })();

  // "The Read" — deterministic, computed from the same series the charts show.
  const read = creditInsights({
    yoy: yoySector,
    mom4: mom4Sector,
    fxAdjusted13w: fxAdj13w,
    yoyState,
    yoyPrivate,
    fxShare,
    cardsYoY: consCards,
    smeYoY: smeSector,
    bridge,
  }, tx.locale);
  const readData = await withLlmHeadline("credit", read, tx.locale);

  // ---- the vitals — every figure computed from the series above -------------
  const recWeek = weekLabel(loansSector.at(-1)?.period);
  const vsWeek = weekLabel(loansSector.at(-2)?.period, false);

  const yoyNow = lastVal(yoySector);
  const mom4Now = lastVal(mom4Sector);
  const realFxNow = bridge.realFxAdj;
  const fxAdj13Now = lastVal(fxAdj13w);

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
  const unsecNow = lastVal(unsecuredYoY);
  const unsecLevel = lastVal(unsecuredLvl);

  const realNegRun = trailingRun(realFxAdjSeries, (v) => v < 0);
  const cardsHotRun = trailingRunVs(consCards, yoySector, (v, o) => v > o);
  const gplHotRun = trailingRunVs(consGpl, yoySector, (v, o) => v > o);
  const unsecuredHotRun = Math.min(cardsHotRun, gplHotRun);

  // ---- movers — which book accelerated, vs 13 weeks ago ---------------------
  const moverRows: MoverRow[] = (
    [
      ["Commercial", commercialYoY],
      ["SME", smeSector],
      ["Retail cards", consCards],
      ["Gen. purpose", consGpl],
      ["Housing", consHousing],
      ["Auto", consAuto],
    ] as [string, Pt[]][]
  )
    .map(([label, s]) => ({
      label,
      prev: valAgo(s as TimeSeriesRow[], 13),
      curr: lastVal(s as TimeSeriesRow[]),
      fmt: (v: number) => `${v.toFixed(1)}%`,
      deltaDecimals: 1,
      good: "neutral" as const,
    }))
    .filter((r) => r.curr != null)
    .sort((a, b) => {
      const da = a.curr != null && a.prev != null ? a.curr - a.prev : -Infinity;
      const db = b.curr != null && b.prev != null ? b.curr - b.prev : -Infinity;
      return db - da;
    });

  const consMixSeries = [
    { key: "Housing", label: "Housing" },
    { key: "Auto", label: "Auto" },
    { key: "Gen. Purpose", label: "Gen. Purpose" },
    { key: "Retail Cards", label: "Retail Cards" },
  ];

  // "cards & GPL drive the consumer book" was a ranking with nothing behind it,
  // and housing is a live contender. The mix is right here.
  const consLast = consMix.at(-1) as Record<string, number | string> | undefined;
  const consLead = consLast
    ? consMixSeries
        .map((s) => ({ label: s.label, v: Number(consLast[s.key]) || 0 }))
        .sort((a, b) => b.v - a.v)
        .slice(0, 2)
        .map((x) => x.label)
    : [];

  const realWeek = weekLabel(bridge.asOfReal, false);
  const headlinePct = bridge.nominal != null ? `${bridge.nominal.toFixed(1)}%` : "the headline";

  return (
    <SectorReport>
<SectorHeader sector="credit" record={<>{tx("Record ")}<b className="font-normal text-foreground">{tx("week ending {0}", { 0: recWeek })}</b>{tx(" · vs ")}{tx(vsWeek)}
          </>} observations={[
          {
            cadence: "weekly",
            role: "current",
            asOf: loansSector.at(-1)?.period,
            window: "13w annualized and 52w",
            basis: "BDDK sector lending, constant FX where stated",
          },
          {
            cadence: "monthly",
            role: "structure",
            asOf: structure.sectorDistribution.asOf,
            basis: "Monthly sector allocation, maturity, SME and non-cash lending",
          },
        ]} />
<SectorContents sections={[{id: "overview", label: "Key indicators"}, {id: "growth", label: "Credit momentum"}, {id: "contributions", label: "Growth contributions"}, {id: "bank-groups", label: "Bank groups"}, {id: "economic-sectors", label: "Economic sectors and maturities"}, {id: "retail", label: "Retail lending"}, {id: "sme", label: "SME loans"}, {id: "guarantees", label: "Non-cash lending"}, {id: "real-growth", label: "Real growth"}]} controls={<GlobalRangeSelector compact />} />
<SectorOpening><SectorMetrics><Vital
          label={tx("FX-adjusted momentum, 13w ann.")}
          observation={{ cadence: "weekly", asOf: fxAdj13w.at(-1)?.period }}
          value={
            fxAdj13Now != null
              ? `${fxAdj13Now < 0 ? "−" : ""}${Math.abs(fxAdj13Now).toFixed(1)}`
              : "—"
          }
          unit="%"
          series={fxAdj13w.slice(-26)}
          decimals={1}
          note={tx(fxAdj13Now != null ? "Exchange-rate valuation effects excluded." : "awaits a 13-week comparison base")}
        />
<Vital
          label={tx("Nominal growth, 52w")}
          value={yoyNow != null ? yoyNow.toFixed(1) : "—"}
          unit="%"
          series={yoySector.slice(-26)}
          decimals={1}
          note={
            mom4Now != null && yoyNow != null ? (
              <>{tx("4w momentum ")}{tx(fmtPct(mom4Now))}{tx(" ann. — ")}{tx(signedPp(mom4Now - yoyNow, 1))}{tx(" vs the 52w pace,")}{" "}
                {tx(mom4Now > yoyNow ? "accelerating" : "cooling")}
              </>
            ) : undefined
          }
        />
<Vital label={tx("Real, constant-FX growth, 52w")} observation={{ cadence: "weekly", asOf: bridge.asOfReal, basis: "Currency and price effects removed; published CPI only." }} value={realFxNow != null ? realFxNow.toFixed(1) : "—"} unit="%" series={realFxAdjSeries.slice(-26)} decimals={1} />
<Vital
          label={tx("FX share of loans")}
          value={fxShareNow != null ? fxShareNow.toFixed(1) : "—"}
          unit="%"
          series={fxShare.slice(-26)}
          decimals={1}
          note={
            <>
              {tx(fxShareDelta != null
                ? tx("{0} over 52w", { 0: signedPp(fxShareDelta, 1) })
                : "share of the total book")}{" "}
              <Link href="/deposits" className="font-semibold text-primary">{tx("Deposits")}</Link>
            </>
          }
        /></SectorMetrics>
</SectorOpening>
<SectorSection id="growth" title={tx("Credit momentum")} description={tx("Currency-adjusted lending momentum and the short-term nominal pace.")}>
<SectorGrid>
<SectorTrend data={momentumByGroup} seriesLabels={{
  [WEEKLY_BANK_TYPES.SECTOR]: "Sector", [WEEKLY_BANK_TYPES.STATE]: "State", [WEEKLY_BANK_TYPES.PRIVATE]: "Private",
}} hero={WEEKLY_BANK_TYPES.SECTOR} title={tx("FX-adjusted credit growth, 13-week annualised")}
  description={tx("Sector, public and private banks · exchange-rate valuation effects excluded")}
  source={tx("Source: BDDK weekly bulletin · TCMB USD/TRY. Foreign-currency loans are valued at the base week's exchange rate; the FX book is assumed to be in US dollars.")}
  yFormat="pct" decimals={1} height={300} zeroLine plain />
<SectorTrend height={280}
              data={mom4Sector}
              seriesLabels={{ [WEEKLY_BANK_TYPES.SECTOR]: "Sector" }}
              title={tx("Loan Growth 4w (annualized %) — sector")}
              yFormat="pct"
              decimals={1}
              zeroLine
              plain
            />
</SectorGrid>
<Takeaway data={readData} variant="report" />
</SectorSection>
<SectorSection id="contributions" title={tx("Growth contributions")} description={tx("Contribution by loan type to annual sector growth, in percentage points.")}>
<SectorGrid>
        <SectorPanel>
          <SecHead
            title={tx("Where the {0} came from", { 0: headlinePct })}
            meta={tx("contribution to sector growth · 52w · pp of the headline")}
            className="mb-2.5"
          />
          <Attribution
            rows={attrib.items.map((c) => ({
              key: c.key,
              label: c.label,
              value: c.pp,
              meta: tx("₺{0}trn · {1}%", { 0: (c.level / 1_000_000).toFixed(2), 1: c.growth.toFixed(1) }),
            }))}
            sum={attrib.sumPp}
            nested={
              smeContrib ? { of: "commercial", label: "SME", value: smeContrib.pp } : undefined
            }
            fmtValue={(v) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(1)}pp`}
            reconciliation="contributions reconcile to the headline — SME is a cut of commercial, not an addition"
            totalMeta={
              lastVal(loansSector) != null
                ? tx("₺{0}trn book", { 0: ((lastVal(loansSector) as number) / 1_000_000).toFixed(2) })
                : undefined
            }
          />
        </SectorPanel>
        <SectorPanel>
          <SecHead title={tx("Period changes")} meta={tx("52w growth · vs 13 weeks ago")} className="mb-2.5" />
          <Movers from="13w ago" to="Now" rows={moverRows} />
        </SectorPanel>
      </SectorGrid>
</SectorSection>
<SectorSection id="bank-groups" title={tx("Bank groups")} description={tx("Loan growth by bank ownership and currency.")}>
<Vital
          label={tx("State − private gap")}
          value={gapNow != null ? `${gapNow >= 0 ? "+" : "−"}${Math.abs(gapNow).toFixed(1)}` : "—"}
          unit="pp"
          series={gapSeries.slice(-26)}
          format="raw"
          decimals={1}
          note={
            stateNow != null && privNow != null && gapNow != null ? (
              <>{tx(gapNow >= 0
                ? "State-bank growth is {0}, versus {1} for private banks; state banks lead the cycle."
                : "State-bank growth is {0}, versus {1} for private banks; private banks lead the cycle.",
                { 0: fmtPct(stateNow), 1: fmtPct(privNow) })}</>
            ) : undefined
          }
        />
<SectorTrend mode="groups"
                data={yoyAll}
                seriesLabels={WEEKLY_BANK_TYPE_LABELS}
                title={
                  tx(seriesFinding(yoySector, { noun: "Loan growth", decimals: 1 }, tx.locale) ??
                    "Loan Growth YoY (%) by group")
                }
                description={tx("Loan growth YoY, %, weekly · by ownership group")}
                source={tx("Source: BDDK weekly bulletin")}
                yFormat="pct"
                decimals={1}
                deltaPeriods={13}
                deltaLabel="13w"
                height={160}
                zeroLine
                plain
              />
<SectorGrid columns={3}>
<SectorBreakdown
  data={yoyByBank.map(row => ({id: row.bank_type_code, label: WEEKLY_BANK_TYPE_LABELS[row.bank_type_code], values: {growth: row.value}}))}
  series={[{key: "growth", label: "Annual growth"}]} mode="ranking" format="pct" decimals={1}
  title={tx("Loan YoY by group · {0}", { 0: yoyByBank[0]?.period ?? "" })}
  asOf={yoyByBank[0]?.period} />
<SectorTrend height={280}
              data={yoyPubPriv}
              seriesLabels={{
                [WEEKLY_BANK_TYPES.PRIVATE]: "Private",
                [WEEKLY_BANK_TYPES.STATE]: "State",
              }}
              title={tx("Total Credit YoY — Public vs Private")}
              yFormat="pct"
              decimals={1}
              zeroLine
              plain
            />
<SectorTrend height={280}
              data={tlYoyPubPriv}
              seriesLabels={{
                [WEEKLY_BANK_TYPES.PRIVATE]: "Private",
                [WEEKLY_BANK_TYPES.STATE]: "State",
              }}
              title={tx("TL Loans YoY — Public vs Private")}
              yFormat="pct"
              decimals={1}
              zeroLine
              plain
            />
</SectorGrid>
</SectorSection>
<SectorSection id="economic-sectors" title={tx("Economic sectors and maturities")} description={tx("Monthly credit allocation by economic activity and the maturity profile of loan products.")}>
<SectorGrid columns={1}>
<SectorBreakdown data={structure.sectorDistribution.data} series={[{key: "credit", label: "Gross cash credit"}]}
  mode="ranking" format="bn" decimals={0} asOf={structure.sectorDistribution.asOf ?? undefined}
  title={tx("Credit by economic activity")}
  description={tx("Main economic sectors · gross cash credit, including non-performing loans")}
  source={tx("Source: BDDK monthly Table 5. Main sectors are mutually exclusive; manufacturing sub-sectors are not added again. Retail and other unallocated lending are outside this comparison. Source thousands of TL converted to millions of TL.")} />
<SectorBreakdown data={structure.maturities.data} series={[{key: "short", label: "Short term"}, {key: "long", label: "Medium and long term"}]}
  mode="composition" percent format="bn" decimals={0} asOf={structure.maturities.asOf ?? undefined}
  title={tx("Maturity profile by loan type")}
  description={tx("Each row represents 100% of that loan type; the exact amounts remain available.")}
  source={tx("Source: BDDK monthly Table 3. Published short-term and medium/long-term classifications; these are not remaining maturities or interest repricing dates. Missing or unreconciled components are not estimated.")} />
</SectorGrid>
<p className="text-[13px] text-muted-foreground"><Link href="/asset-quality#sector-risk" className="font-medium text-primary">{tx("Asset Quality")}</Link>{" · "}{tx("Manufacturing sub-sectors and SME credit quality")}</p>
</SectorSection>
<SectorSection id="retail" title={tx("Retail lending")} description={<>{tx("Housing, auto, general-purpose loans and credit cards: volumes, shares and growth.")}{" "}{claim(consLead.length === 2, tx("The composition behind the attribution bars — {0} & {1} lead the consumer book.", { 0: consLead[0], 1: consLead[1] }))}</>}>
<Vital
          label={tx("Unsecured retail loan growth")}
          value={unsecNow != null ? unsecNow.toFixed(1) : "—"}
          unit="%"
          series={unsecuredYoY.slice(-26)}
          decimals={1}
          note={
            unsecLevel != null ? (
              <>{tx("Cards and general-purpose loans total ₺{0}trn and have jointly outgrown the sector for {1} weeks.",
                { 0: (unsecLevel / 1_000_000).toFixed(2), 1: unsecuredHotRun })}</>
            ) : undefined
          }
        />
<SectorGrid>
            <SectorTrend mode="groups"
              data={consYoYLong}
              deltaPeriods={13}
              deltaLabel="13w"
              seriesLabels={{
                HOUSING: "Housing",
                AUTO: "Auto",
                GPL: "Gen. Purpose",
                CARDS: "Retail Cards",
              }}
              title={tx("Consumer Segment YoY Growth (%)")}
              yFormat="pct"
              decimals={1}
              zeroLine
              plain height={142} />
            <SectorTrend height={390}
              data={cards.flatMap(
                (r: { period: string; retail: number | null; corporate: number | null }) => {
                  const out: TimeSeriesRow[] = [];
                  if (r.retail != null) out.push({ period: r.period, bank_type_code: "RETAIL", value: r.retail });
                  if (r.corporate != null) out.push({ period: r.period, bank_type_code: "CORPORATE", value: r.corporate });
                  return out;
                },
              )}
              seriesLabels={{ RETAIL: "Retail Cards", CORPORATE: "Corporate Cards" }}
              title={tx("Credit Cards — Retail vs Corporate (Level · monthly)")}
              yFormat="bn"
              decimals={0}
              plain
            />
          </SectorGrid>
<SectorGrid>
<StackedArea
              data={consMix}
              series={consMixSeries}
              title={tx("Consumer Credit Mix — Share (%)")}
              percentStack
              plain
            />
<StackedArea
              data={consMix}
              series={consMixSeries}
              title={tx("Consumer Credit Mix — Level (sector)")}
              yFormat="trn"
              decimals={2}
              plain
            />
</SectorGrid>
<SectorGrid>
<StackedArea data={instalmentMix} series={[{key: "INSTALMENTS", label: "Instalment balances"}, {key: "NON_INSTALMENTS", label: "Non-instalment balances"}]}
  title={tx("Retail card balances by instalment structure")} percentStack height={280} plain
  description={tx("Weekly balances · each observation represents total retail card credit")}
  source={tx("Source: BDDK weekly bulletin, retail cards. Non-instalment balances are not a measure of arrears or interest-bearing debt; balances are not spending flows.")} />
<SectorTrend data={overdrafts} seriesLabels={{CONSUMER: "Consumer overdrafts", COMMERCIAL: "Commercial instalment overdrafts"}}
  title={tx("Overdraft balances")} yFormat="bn" decimals={0} height={280} plain
  description={tx("Consumer overdrafts and overdrafts within commercial instalment loans")}
  source={tx("Source: BDDK weekly bulletin. Overdrafts are already included in loan aggregates and must not be added again. Nominal balance growth does not measure borrower numbers, real growth or credit quality.")} />
</SectorGrid>
</SectorSection>
<SectorSection id="sme" title={tx("SME loans")} description={tx(smeContrib
              ? tx("{0} of the headline. SME is a SUBSET of the commercial book, not a peer — the two lines below are not additive.", { 0: signedPp(smeContrib.pp, 1) })
              : "SME is a subset of the commercial book, not a peer — the two lines below are not additive.")}>
<Vital
          label={tx("SME growth, 52w")}
          value={smeNow != null ? smeNow.toFixed(1) : "—"}
          unit="%"
          series={smeSector.slice(-26)}
          decimals={1}
          note={
            smeNow != null && commNow != null && smeContrib ? (
              <>{tx("SME contributes {0} to the sector's {1} growth; the commercial book including SME grows {2}.",
                { 0: signedPp(smeContrib.pp, 1), 1: headlinePct, 2: fmtPct(commNow) })}</>
            ) : undefined
          }
        />
<SectorGrid>
            <SectorTrend height={280}
              data={smeYoY}
              seriesLabels={{
                [WEEKLY_BANK_TYPES.SECTOR]: "Sector",
                [WEEKLY_BANK_TYPES.PRIVATE]: "Private",
                [WEEKLY_BANK_TYPES.STATE]: "State",
              }}
              title={tx("SME Loan Growth YoY (%)")}
              yFormat="pct"
              decimals={1}
              zeroLine
              plain
            />
            <SectorTrend height={280}
              data={smeVsCommercial}
              seriesLabels={{ SME: "SME", COMMERCIAL: "Commercial (incl. corp.)" }}
              title={tx("SME vs Commercial — YoY Growth (%)")}
              description={tx("SME is a cut of commercial — not additive.")}
              yFormat="pct"
              decimals={1}
              zeroLine
              plain
            />
          </SectorGrid>
<SectorGrid>
            <SectorTrend height={280}
              data={smeLevel.filter((r) => r.bank_type_code === WEEKLY_BANK_TYPES.SECTOR)}
              seriesLabels={{ [WEEKLY_BANK_TYPES.SECTOR]: "SME" }}
              title={tx("SME Loans — Level (sector)")}
              yFormat="trn"
              decimals={2}
              plain
            />
            <SectorTrend height={280}
              data={smeLevel.filter((r) => pubPrivSet.has(r.bank_type_code))}
              seriesLabels={{
                [WEEKLY_BANK_TYPES.PRIVATE]: "Private",
                [WEEKLY_BANK_TYPES.STATE]: "State",
              }}
              title={tx("SME Loans — Public vs Private (Level)")}
              yFormat="trn"
              decimals={2}
              plain
            />
          </SectorGrid>
<ChartRow
            data={smeBreak.flatMap(
              (r: { period: string; micro: number | null; small: number | null; medium: number | null }) => [
                { period: r.period, bank_type_code: "Micro", value: r.micro },
                { period: r.period, bank_type_code: "Small", value: r.small },
                { period: r.period, bank_type_code: "Medium", value: r.medium },
              ],
            )}
            deltaPeriods={12}
            deltaLabel="12m"
            fmt={(v) => `₺${(v / 1_000).toFixed(0)}bn`}
          >
            <StackedArea
              data={smeBreak.map(
                (r: { period: string; micro: number | null; small: number | null; medium: number | null }) => ({
                  period: r.period,
                  Micro: r.micro,
                  Small: r.small,
                  Medium: r.medium,
                }),
              )}
              series={[
                { key: "Micro", label: "Micro" },
                { key: "Small", label: "Small" },
                { key: "Medium", label: "Medium" },
              ]}
              title={tx("SME Mix — Micro / Small / Medium (sector, TL bn · monthly)")}
              yFormat="bn"
              decimals={0}
              plain
            />
          </ChartRow>
<SectorGrid>
<SectorBreakdown data={structure.smeCurrency.data} series={[{key: "tl", label: "Turkish lira"}, {key: "fx", label: "Foreign currency"}]}
  mode="composition" percent format="bn" decimals={0} asOf={structure.smeCurrency.asOf ?? undefined}
  title={tx("SME lending by size and currency")}
  description={tx("Currency composition within each enterprise-size class")}
  source={tx("Source: BDDK monthly Table 6. Credit-amount rows only; customer-count rows are not monetary balances.")} />
<SectorBreakdown data={structure.smeRecords.data} series={[{key: "records", label: "Customer record share"}, {key: "credit", label: "Cash-credit share"}]}
  mode="paired" format="pct" decimals={1} asOf={structure.smeRecords.asOf ?? undefined}
  title={tx("SME customer records and credit volumes")}
  description={tx("Share of cash-credit customer records compared with share of cash-credit balances")}
  source={tx("Source: BDDK monthly Table 6. Customer records are not unique enterprises across banks. Each measure has its own total; these shares do not measure average credit per unique borrower.")} />
</SectorGrid>
</SectorSection>
<SectorSection id="guarantees" title={tx("Non-cash lending")} description={tx("Guarantees and credit commitments beyond the cash-loan book.")}>
<SectorGrid>
<SectorBreakdown data={structure.nonCash.data} series={[{key: "tl", label: "Turkish lira"}, {key: "fx", label: "Foreign currency"}]}
  mode="composition" percent={false} format="bn" decimals={0} asOf={structure.nonCash.asOf ?? undefined}
  title={tx("Non-cash credit by instrument and currency")}
  description={tx("Nominal balances in TL equivalents; derivatives are a separate population")}
  source={tx("Source: BDDK monthly Table 14. These are nominal commitments, not expected losses or cash outflows. Zero disclosures remain zero; missing amounts are not estimated.")} />
<SectorBreakdown data={structure.guaranteePurpose.data} series={[{key: "amount", label: "Letters of guarantee"}]}
  mode="ranking" format="bn" decimals={0} asOf={structure.guaranteePurpose.asOf ?? undefined}
  title={tx("Letters of guarantee by purpose")}
  description={tx("Seven purposes within the published letters-of-guarantee total")}
  source={tx("Source: BDDK monthly Table 14, purpose classification. Collateral types are a separate classification of the same book and are not added to these purposes.")} />
</SectorGrid>
</SectorSection>
<SectorSection id="real-growth" title={tx("Real growth and valuation effects")} description={tx("Nominal growth and the effects of exchange rates and inflation.")}>
<SectorGrid ratio="wide-left">
<SectorTrend height={320} hero="REALFX"
          data={threePrints}
          seriesLabels={{
            NOMINAL: "Nominal",
            FXADJ: "FX-adjusted",
            REALFX: "Real, constant FX",
          }}
          title={tx("Loan growth and purchasing power")}
          description={<>{tx(seriesFinding(realFxAdjSeries as TimeSeriesRow[], {
            noun: "Real, constant-FX loan growth", decimals: 1, windowLabel: "12w",
          }, tx.locale))}{" · "}{tx("Loan growth 52w, %, weekly · sector · the gap between the lines is the lira and the price level")}</>}
          source={tx("Source: BDDK weekly bulletin · TÜİK CPI · TCMB USD/TRY")}
          yFormat="pct"
          decimals={1}
          zeroLine
          plain
        />
<SectorPanel>
<SecHead
        title={tx("Exchange-rate and inflation effects")}
        meta={tx("nominal → constant currency → constant prices · 52w")}
        action={
          bridge.lagged ? (
            <span className="text-[12px] leading-relaxed text-muted-foreground">{tx("real legs at W/E ")}{tx(realWeek)}{tx(" — CPI lags the weekly print")}</span>
          ) : undefined
        }
        className="mb-4"
      />
<Bridge bridge={bridge} />
<div className="mt-4">
          <p className="text-[16px] leading-snug tracking-tight text-foreground">
            {/* nominalAtReal, NOT nominal: this sentence then subtracts the legs, which
                are read at the real week. Pairing the latest nominal with June legs made
                the sentence stop adding up (36.2% − 7.1 − 31.4 ≠ −2.1%). */}
            {tx(realFxNow != null && realFxNow < 0
              ? "Nominal loan growth is {0}. After removing currency and price effects, the book contracts {1} in real terms."
              : "Nominal loan growth is {0}. After removing currency and price effects, the book expands {1} in real terms.",
              { 0: fmtPct(bridge.nominalAtReal), 1: fmtPct(Math.abs(realFxNow ?? 0)) })}
          </p>
          <p className="mt-3 text-[12.5px] leading-relaxed text-muted-foreground">
            {bridge.currencyPp != null && bridge.inflationPp != null ? (
              <>{tx("Of that print, ")}{tx(signedPp(bridge.currencyPp, 1))}{tx(" is lira depreciation revaluing the FX book and ")}{tx(signedPp(bridge.inflationPp, 1))}{tx(" is inflation (CPI ")}{tx(fmtPct(bridge.cpi))}{tx("). What remains is real volume —")}{" "}
                {/* The run count was computed and the word "negative" was typed, so the
                    week real growth turned positive this read "negative for 0 weeks". */}
                {tx(runPhrase(realNegRun, "negative", "w", tx.locale) ??
                  (realFxNow != null ? tx("positive at {0}", { 0: fmtPct(realFxNow) }) : "not yet negative"))}
                .
              </>
            ) : (
              <>{tx("The bridge awaits a CPI print.")}</>
            )}
          </p>
          <p className="mt-3 border-t border-hair pt-3 text-[12px] leading-relaxed text-muted-foreground">{tx("Real growth = (1 + FX-adjusted growth) ÷ (1 + annual CPI) − 1. Foreign-currency loans are valued at the base week’s USD/TRY rate and assumed to be denominated in US dollars.")}</p>
        </div>
</SectorPanel>
</SectorGrid>


<SectorGrid>

<SectorTrend height={280}
              data={realVsNominal}
              seriesLabels={REAL_TERMS_LABELS}
              title={tx("Loan Growth YoY — nominal vs real (sector, %)")}
              description={tx("The CPI-deflated twin alone — it does not remove the currency effect.")}
              yFormat="pct"
              decimals={1}
              zeroLine
              plain
            />
<SectorTrend height={280}
              data={fxShare}
              seriesLabels={{ [WEEKLY_BANK_TYPES.SECTOR]: "FX share" }}
              title={tx("FX Share of Total Loans (%)")}
              description={tx("How much of the book the currency adjustment is acting on.")}
              yFormat="pct"
              decimals={1}
              plain
            />
</SectorGrid>
</SectorSection>
<SectorDirectory sector="credit" />
<SectorFooter />
</SectorReport>
  );
}
