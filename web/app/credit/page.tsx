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
import { VERBS, direction, runPhrase, toneClass } from "@/app/lib/prose";
import {
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

export const metadata: Metadata = {
  title: "Turkish Banking Sector — Loans & Credit",
  description:
    "Loan growth and credit dynamics in Türkiye — nominal vs real and FX-adjusted, by segment, currency and bank type, from BDDK weekly and monthly data.",
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
  });
  const readData = await withLlmHeadline("credit", read);

  // ---- the vitals — every figure computed from the series above -------------
  const recWeek = weekLabel(loansSector.at(-1)?.period);
  const vsWeek = weekLabel(loansSector.at(-2)?.period, false);

  const yoyNow = lastVal(yoySector);
  const mom4Now = lastVal(mom4Sector);
  const realFxNow = bridge.realFxAdj;

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
        <>
          Real, constant-FX credit is <b className="font-semibold text-negative">contracting</b> —{" "}
          {fmtPct(realFxNow)} for {realNegRun} consecutive weeks. The {fmtPct(yoyNow)} nominal print
          is lira and CPI.
        </>
      ),
      clear: <>Real, constant-FX growth is positive at {fmtPct(realFxNow)}.</>,
    },
    {
      code: "auto_contraction",
      active: autoNegRun >= 8 && autoNow != null && autoNow < 0,
      rule: `auto_yoy < 0 for ${autoNegRun}w`,
      body: (
        <>
          Auto loans in sustained contraction — {fmtPct(autoNow)}, negative for {autoNegRun}{" "}
          consecutive weeks. The book is small (
          {autoLvl.at(-1)?.value != null ? `₺${((autoLvl.at(-1)!.value as number) / 1_000).toFixed(0)}bn` : "—"}
          ), so it drags the headline by little.
        </>
      ),
      clear: <>Auto loans are growing at {fmtPct(autoNow)}.</>,
    },
    {
      code: "unsecured_retail_hot",
      active: unsecuredHotRun >= 8,
      rule: `cards_yoy > sector AND gpl_yoy > sector for ${unsecuredHotRun}w`,
      body: (
        <>
          Unsecured retail is running above the sector — cards {fmtPct(cardsNow)} and general-purpose{" "}
          {fmtPct(gplNow)} vs {fmtPct(yoyNow)}, for {unsecuredHotRun} consecutive weeks. Watch it in{" "}
          <Link href="/asset-quality" className="font-semibold text-primary">
            /asset-quality
          </Link>
          .
        </>
      ),
      clear: <>Neither cards nor general-purpose has outrun the sector for 8 straight weeks.</>,
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

  const realWeek = weekLabel(bridge.asOfReal, false);
  const headlinePct = bridge.nominal != null ? `${bridge.nominal.toFixed(1)}%` : "the headline";

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

      {/* ── The bridge — what the headline is worth ─────────────────────── */}
      <SecHead
        title="What the headline is worth"
        meta="nominal → constant currency → constant prices · 52w"
        action={
          bridge.lagged ? (
            <span className="font-mono text-[8.5px] uppercase tracking-[0.07em] text-faint">
              real legs at W/E {realWeek} — CPI lags the weekly print
            </span>
          ) : undefined
        }
        className="mb-2.5 mt-6"
      />
      <div className="grid grid-cols-1 gap-8 border-t-2 border-foreground pt-4 lg:grid-cols-[minmax(0,7fr)_minmax(260px,4fr)]">
        <Bridge bridge={bridge} />
        <div className="self-center">
          <p className="text-[19px] leading-snug tracking-tight text-foreground">
            Nominal credit grew{" "}
            <b className="font-mono font-semibold">{fmtPct(bridge.nominal)}</b>. Strip the lira and
            the price level and the loan book{" "}
            {realFxNow != null && realFxNow < 0 ? (
              <b className="font-semibold text-negative">shrank {fmtPct(Math.abs(realFxNow))}</b>
            ) : (
              <b className="font-semibold text-positive">grew {fmtPct(realFxNow)}</b>
            )}
            .
          </p>
          <p className="mt-3 text-[12.5px] leading-relaxed text-muted-foreground">
            {bridge.currencyPp != null && bridge.inflationPp != null ? (
              <>
                Of that print, {signedPp(bridge.currencyPp, 1)} is lira depreciation revaluing the FX
                book and {signedPp(bridge.inflationPp, 1)} is inflation (CPI {fmtPct(bridge.cpi)}).
                What remains is real volume —{" "}
                {/* The run count was computed and the word "negative" was typed, so the
                    week real growth turned positive this read "negative for 0 weeks". */}
                {runPhrase(realNegRun, "negative") ??
                  (realFxNow != null ? `positive at ${fmtPct(realFxNow)}` : "not yet negative")}
                .
              </>
            ) : (
              <>The bridge awaits a CPI print.</>
            )}
          </p>
          <p className="mt-3 border-t border-hair pt-2.5 font-mono text-[9px] uppercase leading-relaxed tracking-[0.06em] text-faint">
            real_fxadj = (1 + fx_adjusted) ÷ (1 + cpi_yoy) − 1 · FX book held at the base week&apos;s
            USD/TRY and proxied as all-USD
          </p>
        </div>
      </div>

      {/* ── The vitals ─────────────────────────────────────────────────── */}
      <SecHead title="The vitals" meta="equal weight · trailing 26 weeks" className="mb-2.5 mt-8" />
      <Vitals>
        <Vital
          label="Real growth, constant FX"
          value={
            realFxNow != null
              ? `${realFxNow < 0 ? "−" : ""}${Math.abs(realFxNow).toFixed(1)}` // typographic minus, as the gap vital
              : "—"
          }
          unit="%"
          series={realFxAdjSeries.slice(-26)}
          decimals={1}
          note={
            realFxNow != null ? (
              <>
                the book{" "}
                {/* The verb branched on the sign; the colour did not — a book
                    GROWING in real terms rendered "grew" in red. */}
                <em className={`font-semibold not-italic ${toneClass(realFxNow, "up")}`}>
                  {direction(realFxNow, VERBS.size)}
                </em>{" "}
                once lira and CPI are stripped
                {realNegRun > 0 ? ` — ${realNegRun}w negative` : ""}
                {bridge.lagged ? ` · at W/E ${realWeek}` : ""}
              </>
            ) : (
              "awaits the CPI print"
            )
          }
        />
        <Vital
          label="Nominal growth, 52w"
          value={yoyNow != null ? yoyNow.toFixed(1) : "—"}
          unit="%"
          series={yoySector.slice(-26)}
          decimals={1}
          note={
            mom4Now != null && yoyNow != null ? (
              <>
                4w momentum {fmtPct(mom4Now)} ann. — {signedPp(mom4Now - yoyNow, 1)} vs the 52w pace,{" "}
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
              {fxShareDelta != null
                ? `${signedPp(fxShareDelta, 1)} over 52w`
                : "share of the total book"}{" "}
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
            smeNow != null && commNow != null && smeContrib ? (
              <>
                {signedPp(smeContrib.pp, 1)} of the {headlinePct} headline —{" "}
                {smeNow >= commNow ? "outpaces" : "trails"} commercial {fmtPct(commNow)}
              </>
            ) : undefined
          }
        />
        <Vital
          label="Unsecured retail"
          value={unsecNow != null ? unsecNow.toFixed(1) : "—"}
          unit="%"
          series={unsecuredYoY.slice(-26)}
          decimals={1}
          note={
            unsecLevel != null ? (
              <>
                cards + GPL as one book (₺{(unsecLevel / 1_000_000).toFixed(2)}trn) —{" "}
                {unsecuredHotRun}w above the sector
              </>
            ) : undefined
          }
        />
      </Vitals>

      {/* ── Attribution — where the headline came from ──────────────────── */}
      <div className="mt-8 grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,7fr)_minmax(260px,4fr)]">
        <div>
          <SecHead
            title={`Where the ${headlinePct} came from`}
            meta="contribution to sector growth · 52w · pp of the headline"
            className="mb-2.5"
          />
          <Attribution
            rows={attrib.items.map((c) => ({
              key: c.key,
              label: c.label,
              value: c.pp,
              meta: `₺${(c.level / 1_000_000).toFixed(2)}trn · ${c.growth.toFixed(1)}%`,
            }))}
            sum={attrib.sumPp}
            nested={
              smeContrib ? { of: "commercial", label: "SME", value: smeContrib.pp } : undefined
            }
            fmtValue={(v) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(1)}pp`}
            reconciliation="contributions reconcile to the headline — SME is a cut of commercial, not an addition"
            totalMeta={
              lastVal(loansSector) != null
                ? `₺${((lastVal(loansSector) as number) / 1_000_000).toFixed(2)}trn book`
                : undefined
            }
          />
        </div>
        <div>
          <SecHead title="Movers" meta="52w growth · vs 13 weeks ago" className="mb-2.5" />
          <Movers from="13w ago" to="Now" rows={moverRows} />
        </div>
      </div>

      {/* ── Flags ──────────────────────────────────────────────────────── */}
      <SecHead
        title="Flags"
        meta="each prints the rule that raised it"
        className="mb-2.5 mt-8"
      />
      <Flags
        flags={flags}
        showCleared
        quietNote="No credit rule fired this week."
      />

      {/* ── In depth — the evidence layer ──────────────────────────────── */}
      <Depth
        meta="carried over, reordered by question — nothing removed"
        action={<GlobalRangeSelector />}
      >
        <Takeaway data={readData} variant="desk" />

        <Section
          index="01"
          title="Is the growth real?"
          description="The three prints of the same book on one axis. Nominal is where the reader starts; the composed line is what the book actually did."
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
                  seriesFinding(realFxAdjSeries as TimeSeriesRow[], {
                    noun: "Real, constant-FX loan growth",
                    decimals: 1,
                  }) ?? "Loan growth 52w — nominal vs FX-adjusted vs real, constant FX"
                }
                description="Loan growth 52w, %, weekly · sector · the gap between the lines is the lira and the price level"
                source="Source: BDDK weekly bulletin · TÜİK CPI · TCMB USD/TRY"
                yFormat="pct"
                decimals={1}
                zeroLine
              plain
            />
            </div>
            <TrendChart
              data={mom4Sector}
              seriesLabels={{ [WEEKLY_BANK_TYPES.SECTOR]: "Sector" }}
              title="Loan Growth 4w (annualized %) — sector"
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
              title="Loan Growth YoY — nominal vs real (sector, %)"
              description="The CPI-deflated twin alone — it does not remove the currency effect."
              yFormat="pct"
              decimals={1}
              zeroLine
              plain
            />
            <TrendChart
              data={fxShare}
              seriesLabels={{ [WEEKLY_BANK_TYPES.SECTOR]: "FX share" }}
              title="FX Share of Total Loans (%)"
              description="How much of the book the currency adjustment is acting on."
              yFormat="pct"
              decimals={1}
              plain
            />
          </div>
        </Section>

        <Section
          index="02"
          title="Who is lending?"
          description="The clearest sector signal — who is driving the lending cycle, and in which currency."
        >
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
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
              plain
            />
            </div>
            <BarByBank
              data={yoyByBank}
              labels={WEEKLY_BANK_TYPE_LABELS}
              title={`Loan YoY by group · ${yoyByBank[0]?.period ?? ""}`}
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
              title="Total Credit YoY — Public vs Private"
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
              title="TL Loans YoY — Public vs Private"
              yFormat="pct"
              decimals={1}
              zeroLine
              plain
            />
          </div>
        </Section>

        <Section
          index="03"
          title="Where is it going?"
          description="The composition behind the attribution bars — cards & GPL drive the consumer book."
        >
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <StackedArea
              data={consMix}
              series={consMixSeries}
              title="Consumer Credit Mix — Level (sector)"
              yFormat="trn"
              decimals={2}
              plain
            />
            <StackedArea
              data={consMix}
              series={consMixSeries}
              title="Consumer Credit Mix — Share (%)"
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
              title="Consumer Segment YoY Growth (%)"
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
              title="Credit Cards — Retail vs Corporate (Level · monthly)"
              yFormat="bn"
              decimals={0}
              plain
            />
          </div>
        </Section>

        <Section
          index="04"
          title="SME — the engine inside commercial"
          description={
            smeContrib
              ? `${signedPp(smeContrib.pp, 1)} of the headline. SME is a SUBSET of the commercial book, not a peer — the two lines below are not additive.`
              : "SME is a subset of the commercial book, not a peer — the two lines below are not additive."
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
              title="SME Loan Growth YoY (%)"
              yFormat="pct"
              decimals={1}
              zeroLine
              plain
            />
            <TrendChart
              data={smeVsCommercial}
              seriesLabels={{ SME: "SME", COMMERCIAL: "Commercial (incl. corp.)" }}
              title="SME vs Commercial — YoY Growth (%)"
              description="SME is a cut of commercial — not additive."
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
              title="SME Loans — Level (sector)"
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
              title="SME Loans — Public vs Private (Level)"
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
              title="SME Mix — Micro / Small / Medium (sector, TL bn · monthly)"
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
