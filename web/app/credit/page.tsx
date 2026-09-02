/**
 * Credit tab — the Desk brief above the carried-over evidence.
 *
 * The page's claim used to be its nominal loan print (36%+). In a 32% CPI
 * regime with a depreciating lira that number is mostly not credit, and the
 * page owned both corrections already — it just never composed them. It now
 * leads with the bridge (nominal → −currency → −inflation → real), then says
 * WHERE the growth came from (segment contributions, which reconcile to the
 * headline exactly), then raises the computed flags. See app/lib/credit.ts.
 *
 * Sourced from the BDDK *weekly* bulletin (`weekly_series`) for every series the
 * weekly feed carries — fresher and denser than the monthly tables, at the cost
 * of a ~3-year rolling history. The two metrics weekly does NOT carry stay on the
 * monthly tables: the card retail-vs-corporate split (`cardsSplit`) and the SME
 * micro/small/medium mix (`smeBreakdown`). Growth windows: monthly YoY → weekly
 * 52w; the old monthly MoM chart → weekly 4w annualized momentum.
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
import { Section } from "@/app/components/ui";
import {
  ChartRow,
  Colophon,
  Depth,
  DeskHeader,
  Flags,
  Movers,
  SecHead,
  Vital,
  Vitals,
  type Flag,
  type MoverRow,
} from "@/app/components/desk";
import { lastVal, monthLabel, signedPp, valAgo } from "@/app/lib/desk";
import { claim, runPhrase, toneClass } from "@/app/lib/prose";
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
import BarByBank from "@/app/components/BarByBank";
import TrendChart from "@/app/components/TrendChart";
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
  ]);
  const [cpiYoY, usdTry] = await Promise.all([cpiYoYByMonth(), evdsSeries("TP.DK.USD.A", 4)]);

  const fxShare = computeFxShare(tlSec, fxSec);
  const yoySector = yoyAll.filter((r) => r.bank_type_code === WEEKLY_BANK_TYPES.SECTOR);

  // ---- the bridge: nominal → −currency → −inflation → real ------------------
  const fxAdjSeries = fxAdjustedGrowth(tlSec, fxSec, usdTry);
  const fxAdj13w = annualizeGrowth(fxAdjustedGrowth(tlSec, fxSec, usdTry, 13 * 7), 13 * 7);
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

  // ---- flags — each prints the rule that raised it --------------------------
  const realNegRun = trailingRun(realFxAdjSeries, (v) => v < 0);
  const autoNegRun = trailingRun(consAuto, (v) => v < 0);
  const cardsHotRun = trailingRunVs(consCards, yoySector, (v, o) => v > o);
  const gplHotRun = trailingRunVs(consGpl, yoySector, (v, o) => v > o);
  const unsecuredHotRun = Math.min(cardsHotRun, gplHotRun);
  const autoNow = lastVal(consAuto);
  const cardsNow = lastVal(consCards);
  const gplNow = lastVal(consGpl);

  const flags: Flag[] = [
    {
      code: "real_credit_contraction",
      active: realNegRun > 0 && realFxNow != null && realFxNow < 0,
      rule: `real_fxadj(52w) < 0 for ${realNegRun}w`,
      body: (
        <>{tx("Real, constant-FX credit has contracted {0} for {1} consecutive weeks. The published {2} nominal rate includes lira and inflation effects.",
          {0: fmtPct(Math.abs(realFxNow ?? 0)), 1: realNegRun, 2: fmtPct(yoyNow)})}</>
      ),
      clear: <>{tx("Real, constant-FX growth is positive at ")}{tx(fmtPct(realFxNow))}.</>,
    },
    {
      code: "auto_contraction",
      active: autoNegRun >= 8 && autoNow != null && autoNow < 0,
      rule: `auto_yoy < 0 for ${autoNegRun}w`,
      body: (
        <>{tx("Auto loans have contracted {0} and remained negative for {1} consecutive weeks. The book is small ({2}), so its effect on total growth is limited.",
          {0: fmtPct(Math.abs(autoNow ?? 0)), 1: autoNegRun, 2: autoLvl.at(-1)?.value != null ? `₺${((autoLvl.at(-1)!.value as number) / 1_000).toFixed(0)}bn` : "—"})}</>
      ),
      clear: <>{tx("Auto loans are growing at ")}{tx(fmtPct(autoNow))}.</>,
    },
    {
      code: "unsecured_retail_hot",
      active: unsecuredHotRun >= 8,
      rule: `cards_yoy > sector AND gpl_yoy > sector for ${unsecuredHotRun}w`,
      body: (
        <>{tx("Cards ({0}) and general-purpose loans ({1}) have both outgrown the sector ({2}) for {3} consecutive weeks. Follow the asset-quality implications in",
          {0: fmtPct(cardsNow), 1: fmtPct(gplNow), 2: fmtPct(yoyNow), 3: unsecuredHotRun})}{" "}
          <Link href="/asset-quality" className="font-semibold text-primary">{tx("/asset-quality")}</Link>
          .
        </>
      ),
      clear: <>{tx("Neither cards nor general-purpose has outrun the sector for 8 straight weeks.")}</>,
    },
  ];

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
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title={tx("Credit")}
        record={
          <>{tx("Record ")}<b className="font-normal text-foreground">{tx("week ending {0}", {0: recWeek})}</b>{tx(" · vs ")}{tx(vsWeek)}
          </>
        }
        right="every figure computed from source series"
        observations={[
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
            asOf: bridge.asOfReal,
            basis: "CPI deflator only; never nowcast",
          },
        ]}
      />

      {/* ── The bridge — what the headline is worth ─────────────────────── */}
      <SecHead
        title={tx("What the headline is worth")}
        meta={tx("nominal → constant currency → constant prices · 52w")}
        action={
          bridge.lagged ? (
            <span className="font-mono text-[8.5px] uppercase tracking-[0.07em] text-faint">{tx("real legs at W/E ")}{tx(realWeek)}{tx(" — CPI lags the weekly print")}</span>
          ) : undefined
        }
        className="mb-2.5 mt-6"
      />
      <div className="grid grid-cols-1 gap-8 border-t-2 border-foreground pt-4 lg:grid-cols-[minmax(0,7fr)_minmax(260px,4fr)]">
        <Bridge bridge={bridge} />
        <div className="self-center">
          <p className="text-[19px] leading-snug tracking-tight text-foreground">
            {/* nominalAtReal, NOT nominal: this sentence then subtracts the legs, which
                are read at the real week. Pairing the latest nominal with June legs made
                the sentence stop adding up (36.2% − 7.1 − 31.4 ≠ −2.1%). */}
            {tx(realFxNow != null && realFxNow < 0
              ? "Nominal loan growth is {0}. After removing currency and price effects, the book contracts {1} in real terms."
              : "Nominal loan growth is {0}. After removing currency and price effects, the book expands {1} in real terms.",
            {0: fmtPct(bridge.nominalAtReal), 1: fmtPct(Math.abs(realFxNow ?? 0))})}
          </p>
          <p className="mt-3 text-[12.5px] leading-relaxed text-muted-foreground">
            {bridge.currencyPp != null && bridge.inflationPp != null ? (
              <>{tx("Of that print, ")}{tx(signedPp(bridge.currencyPp, 1))}{tx(" is lira depreciation revaluing the FX book and ")}{tx(signedPp(bridge.inflationPp, 1))}{tx(" is inflation (CPI ")}{tx(fmtPct(bridge.cpi))}{tx("). What remains is real volume —")}{" "}
                {/* The run count was computed and the word "negative" was typed, so the
                    week real growth turned positive this read "negative for 0 weeks". */}
                {tx(runPhrase(realNegRun, "negative", "w", tx.locale) ??
                  (realFxNow != null ? tx("positive at {0}", {0: fmtPct(realFxNow)}) : "not yet negative"))}
                .
              </>
            ) : (
              <>{tx("The bridge awaits a CPI print.")}</>
            )}
          </p>
          <p className="mt-3 border-t border-hair pt-2.5 font-mono text-[9px] uppercase leading-relaxed tracking-[0.06em] text-faint">{tx("real_fxadj = (1 + fx_adjusted) ÷ (1 + cpi_yoy) − 1 · FX book held at the base week's USD/TRY and proxied as all-USD")}</p>
        </div>
      </div>

      {/* ── The vitals ─────────────────────────────────────────────────── */}
      <SecHead title={tx("The vitals")} meta={tx("equal weight · trailing 26 weeks")} className="mb-2.5 mt-8" />
      <Vitals>
        <Vital
          label={tx("FX-adjusted momentum, 13w ann.")}
          value={
            fxAdj13Now != null
              ? `${fxAdj13Now < 0 ? "−" : ""}${Math.abs(fxAdj13Now).toFixed(1)}`
              : "—"
          }
          unit="%"
          series={fxAdj13w.slice(-26)}
          decimals={1}
          note={
            fxAdj13Now != null ? (
              <>{tx("lira valuation stripped; the 52w real, constant-FX rate is ")}
                <em className={`font-semibold not-italic ${toneClass(realFxNow, "up")}`}>
                  {tx(fmtPct(realFxNow))}
                </em>
                {bridge.lagged ? tx(" · real rate at W/E {0}", {0: realWeek}) : ""}
              </>
            ) : (
              "awaits a 13-week comparison base"
            )
          }
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
        <Vital
          label={tx("FX share of loans")}
          value={fxShareNow != null ? fxShareNow.toFixed(1) : "—"}
          unit="%"
          series={fxShare.slice(-26)}
          decimals={1}
          note={
            <>
              {tx(fxShareDelta != null
                ? tx("{0} over 52w", {0: signedPp(fxShareDelta, 1)})
                : "share of the total book")}{" "}
              <Link href="/deposits" className="font-semibold text-primary">{tx("/deposits")}</Link>
            </>
          }
        />
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
              {0: fmtPct(stateNow), 1: fmtPct(privNow)})}</>
            ) : undefined
          }
        />
        <Vital
          label={tx("SME growth, 52w")}
          value={smeNow != null ? smeNow.toFixed(1) : "—"}
          unit="%"
          series={smeSector.slice(-26)}
          decimals={1}
          note={
            smeNow != null && commNow != null && smeContrib ? (
              <>{tx("SME contributes {0} to the sector's {1} growth; the commercial book including SME grows {2}.",
                {0: signedPp(smeContrib.pp, 1), 1: headlinePct, 2: fmtPct(commNow)})}</>
            ) : undefined
          }
        />
        <Vital
          label={tx("Unsecured retail")}
          value={unsecNow != null ? unsecNow.toFixed(1) : "—"}
          unit="%"
          series={unsecuredYoY.slice(-26)}
          decimals={1}
          note={
            unsecLevel != null ? (
              <>{tx("Cards and general-purpose loans total ₺{0}trn and have jointly outgrown the sector for {1} weeks.",
                {0: (unsecLevel / 1_000_000).toFixed(2), 1: unsecuredHotRun})}</>
            ) : undefined
          }
        />
      </Vitals>

      {/* ── Attribution — where the headline came from ──────────────────── */}
      <div className="mt-8 grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,7fr)_minmax(260px,4fr)]">
        <div>
          <SecHead
            title={tx("Where the {0} came from", {0: headlinePct})}
            meta={tx("contribution to sector growth · 52w · pp of the headline")}
            className="mb-2.5"
          />
          <Attribution
            rows={attrib.items.map((c) => ({
              key: c.key,
              label: c.label,
              value: c.pp,
              meta: tx("₺{0}trn · {1}%", {0: (c.level / 1_000_000).toFixed(2), 1: c.growth.toFixed(1)}),
            }))}
            sum={attrib.sumPp}
            nested={
              smeContrib ? { of: "commercial", label: "SME", value: smeContrib.pp } : undefined
            }
            fmtValue={(v) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(1)}pp`}
            reconciliation="contributions reconcile to the headline — SME is a cut of commercial, not an addition"
            totalMeta={
              lastVal(loansSector) != null
                ? tx("₺{0}trn book", {0: ((lastVal(loansSector) as number) / 1_000_000).toFixed(2)})
                : undefined
            }
          />
        </div>
        <div>
          <SecHead title={tx("Movers")} meta={tx("52w growth · vs 13 weeks ago")} className="mb-2.5" />
          <Movers from="13w ago" to="Now" rows={moverRows} />
        </div>
      </div>

      {/* ── Flags ──────────────────────────────────────────────────────── */}
      <SecHead
        title={tx("Flags")}
        meta={tx("each prints the rule that raised it")}
        className="mb-2.5 mt-8"
      />
      <Flags
        flags={flags}
        showCleared
        quietNote="No credit rule fired this week."
      />

      {/* ── In depth — the evidence layer ──────────────────────────────── */}
      <Depth
        meta={tx("carried over, reordered by question — nothing removed")}
        action={<GlobalRangeSelector />}
      >
        <Takeaway data={readData} variant="desk" />

        <Section
          index="01"
          title={tx("Is the growth real?")}
          description={tx("The three prints of the same book on one axis. Nominal is where the reader starts; the composed line is what the book actually did.")}
        >
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <TrendChart
                data={threePrints}
                seriesLabels={{
                  NOMINAL: "Nominal",
                  FXADJ: "FX-adjusted",
                  REALFX: "Real, constant FX",
                }}
                title={
                  tx(seriesFinding(realFxAdjSeries as TimeSeriesRow[], {
                    noun: "Real, constant-FX loan growth",
                    decimals: 1,
                  }, tx.locale) ?? "Loan growth 52w — nominal vs FX-adjusted vs real, constant FX")
                }
                description={tx("Loan growth 52w, %, weekly · sector · the gap between the lines is the lira and the price level")}
                source={tx("Source: BDDK weekly bulletin · TÜİK CPI · TCMB USD/TRY")}
                yFormat="pct"
                decimals={1}
                zeroLine
              plain
            />
            </div>
            <TrendChart
              data={mom4Sector}
              seriesLabels={{ [WEEKLY_BANK_TYPES.SECTOR]: "Sector" }}
              title={tx("Loan Growth 4w (annualized %) — sector")}
              yFormat="pct"
              decimals={1}
              zeroLine
              plain
            />
          </div>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <TrendChart
              data={realVsNominal}
              seriesLabels={REAL_TERMS_LABELS}
              title={tx("Loan Growth YoY — nominal vs real (sector, %)")}
              description={tx("The CPI-deflated twin alone — it does not remove the currency effect.")}
              yFormat="pct"
              decimals={1}
              zeroLine
              plain
            />
            <TrendChart
              data={fxShare}
              seriesLabels={{ [WEEKLY_BANK_TYPES.SECTOR]: "FX share" }}
              title={tx("FX Share of Total Loans (%)")}
              description={tx("How much of the book the currency adjustment is acting on.")}
              yFormat="pct"
              decimals={1}
              plain
            />
          </div>
        </Section>

        <Section
          index="02"
          title={tx("Who is lending?")}
          description={tx("The clearest sector signal — who is driving the lending cycle, and in which currency.")}
        >
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <TrendChart
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
                zeroLine
              plain
            />
            </div>
            <BarByBank
              data={yoyByBank}
              labels={WEEKLY_BANK_TYPE_LABELS}
              title={tx("Loan YoY by group · {0}", {0: yoyByBank[0]?.period ?? ""})}
              format="pct"
              decimals={1}
              plain
            />
          </div>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <TrendChart
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
            <TrendChart
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
          </div>
        </Section>

        <Section
          index="03"
          title={tx("Where is it going?")}
          description={
            tx(claim(
              consLead.length === 2,
              tx("The composition behind the attribution bars — {0} & {1} lead the consumer book.", {0: consLead[0], 1: consLead[1]}),
            ) ?? "The composition behind the attribution bars.")
          }
        >
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <StackedArea
              data={consMix}
              series={consMixSeries}
              title={tx("Consumer Credit Mix — Level (sector)")}
              yFormat="trn"
              decimals={2}
              plain
            />
            <StackedArea
              data={consMix}
              series={consMixSeries}
              title={tx("Consumer Credit Mix — Share (%)")}
              percentStack
              plain
            />
          </div>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <TrendChart
              data={consYoYLong}
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
              plain
            />
            <TrendChart
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
          </div>
        </Section>

        <Section
          index="04"
          title={tx("SME — the engine inside commercial")}
          description={
            tx(smeContrib
              ? tx("{0} of the headline. SME is a SUBSET of the commercial book, not a peer — the two lines below are not additive.", {0: signedPp(smeContrib.pp, 1)})
              : "SME is a subset of the commercial book, not a peer — the two lines below are not additive.")
          }
        >
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <TrendChart
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
            <TrendChart
              data={smeVsCommercial}
              seriesLabels={{ SME: "SME", COMMERCIAL: "Commercial (incl. corp.)" }}
              title={tx("SME vs Commercial — YoY Growth (%)")}
              description={tx("SME is a cut of commercial — not additive.")}
              yFormat="pct"
              decimals={1}
              zeroLine
              plain
            />
          </div>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <TrendChart
              data={smeLevel.filter((r) => r.bank_type_code === WEEKLY_BANK_TYPES.SECTOR)}
              seriesLabels={{ [WEEKLY_BANK_TYPES.SECTOR]: "SME" }}
              title={tx("SME Loans — Level (sector)")}
              yFormat="trn"
              decimals={2}
              plain
            />
            <TrendChart
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
          </div>
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
                  Micro: r.micro ?? 0,
                  Small: r.small ?? 0,
                  Medium: r.medium ?? 0,
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
        </Section>
      </Depth>

      <Colophon />
    </main>
  );
}
