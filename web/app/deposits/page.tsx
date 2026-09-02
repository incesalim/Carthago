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
import { localizeMetadata } from "@/i18n/metadata";
import { getText } from "@/i18n/server";
import type { Metadata } from "next";
import Link from "next/link";
import {
  weeklySeries,
  weeklyGrowth,
  weeklyTotalDepositsYoY,
  depositMaturityMix,
  ratioLdr,
  latestPerBank,
  PRIMARY_BANK_TYPES,
  BANK_TYPES,
  BANK_TYPE_LABELS,
  WEEKLY_BANK_TYPES,
  WEEKLY_BANK_TYPE_LABELS,
  type WeeklyRow,
  type TimeSeriesRow,
} from "@/app/lib/metrics";
import {
  Ahead,
  CadenceBand,
  ChartFoot,
  ChartRow,
  Colophon,
  Depth,
  DeskHeader,
  Flags,
  Levels,
  Movers,
  SecHead,
  Standings,
  Transmission,
  Vital,
  Vitals,
  type Flag,
  type MoverRow,
  type StandingsGroup,
  type TransmissionItem,
} from "@/app/components/desk";
import { lastVal, latestByGroup, monthLabel, signedPp, valAgo } from "@/app/lib/desk";
import { LDR_PUBLISHED } from "@/app/lib/ldr";
import { everyOf, firstClaim } from "@/app/lib/prose";
import { aheadSlots } from "@/app/lib/ahead-data";
import { GlobalRangeSelector } from "@/app/components/range-context";
import TrendChart from "@/app/components/TrendChart";
import StackedArea from "@/app/components/StackedArea";
import Takeaway from "@/app/components/Takeaway";
import { depositsInsights } from "@/app/lib/insights";
import { seriesFinding } from "@/app/lib/chart-findings";
import { withLlmHeadline } from "@/app/lib/read-headlines";
import { cpiYoYByMonth, nominalVsReal, REAL_TERMS_LABELS } from "@/app/lib/real-terms";

export const dynamic = "force-dynamic";

const pageMetadata: Metadata = {
  title: "Turkish Banking Sector — Deposits",
  description: "Deposit trends for Türkiye's banks — TL vs FX, by bank type, and deposit growth from BDDK weekly and monthly bulletins.",
  alternates: { canonical: "/deposits" },
};

export async function generateMetadata(): Promise<Metadata> {
  return localizeMetadata(pageMetadata);
}

const MEVDUAT = "mevduat";
const TOTAL = "4.0.1";
// Demand ("Vadesiz") is split by depositor type in the weekly feed; sum the three.
const DEMAND_PARTS = ["4.0.3", "4.0.6", "4.0.9"];

/** The maturity ladder, shortest first — the shape of the funding. */
const MATURITY_SERIES = [
  { key: "demand", label: "Demand" },
  { key: "maturity_1m", label: "≤1m" },
  { key: "maturity_1_3m", label: "1–3m" },
  { key: "maturity_3_6m", label: "3–6m" },
  { key: "maturity_6_12m", label: "6–12m" },
  { key: "maturity_over_12m", label: ">12m" },
];

/** 'YYYY-MM-DD' → '04 Jul 2026' / '04 Jul' — the weekly record line. */
function weekLabel(p: string | null | undefined, withYear = true): string {
  const m = p ? /^\d{4}-\d{2}-(\d{2})/.exec(p) : null;
  return m ? `${m[1]} ${monthLabel(p, withYear)}` : monthLabel(p, withYear);
}

const fmtPct = (v: number | null | undefined, d = 1) =>
  v == null ? "—" : `${v.toFixed(d)}%`;

/** Route link styled for use inside a computed note. */
const Go = ({ href, children }: { href: string; children: React.ReactNode }) => (
  <Link href={href} className="font-semibold text-primary">
    {children}
  </Link>
);

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
  const tx = await getText();
  // What lands next — derived from the record periods + TCMB's published calendar.
  const ahead = await aheadSlots();
  const all = Object.values(WEEKLY_BANK_TYPES);
  const sector = [WEEKLY_BANK_TYPES.SECTOR];
  const groups = all.filter((c) => c !== WEEKLY_BANK_TYPES.SECTOR);

  const [
    depSector, depByGroup, yoyAll, mom4Sector, yoyByBank,
    demandParts,
    tlSec, fxSec,
    mix, ldr, loansYoYSector,
    tlYoySector,
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
    // TL-only deposit growth — the vitals' de-dollarized read of the base.
    weeklyGrowth(MEVDUAT, TOTAL, "TL", 52, sector, 104),
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

  const ldrSector = ldr.filter((r) => r.bank_type_code === BANK_TYPES.SECTOR);

  // "The Read" — deterministic, computed from the same series the charts show.
  const read = depositsInsights({
    yoy: yoySector,
    loansYoY: loansYoYSector,
    fxShare,
    demandShare: dShare,
    ldr: ldrSector,
  }, tx.locale);
  const readData = await withLlmHeadline("deposits", read, tx.locale);

  // ---- the vitals — every figure computed from the series above -------------
  const recWeek = weekLabel(depSector.at(-1)?.period);
  const vsWeek = weekLabel(depSector.at(-2)?.period, false);

  const depYoYNow = lastVal(yoySector);
  const loansYoYNow = lastVal(loansYoYSector);
  const fundingGap =
    loansYoYNow != null && depYoYNow != null ? loansYoYNow - depYoYNow : null;

  const tlYoYNow = lastVal(tlYoySector);
  const mom4Now = lastVal(mom4Sector);

  const fxShareNow = lastVal(fxShare);
  const fxShare52 = valAgo(fxShare, 52);
  const fxShareDelta = fxShareNow != null && fxShare52 != null ? fxShareNow - fxShare52 : null;

  const dShareNow = lastVal(dShare);
  const dShare52 = valAgo(dShare, 52);
  const dShareDelta = dShareNow != null && dShare52 != null ? dShareNow - dShare52 : null;

  const ldrNow = lastVal(ldrSector);

  // "Every deposit-taking group funds its loan book below the 100% line" was
  // guarded on the SECTOR ratio — while the Standings table on this very page
  // already tones a group red when it breaches 100. Test the groups.
  //
  // Development & investment banks take no deposits: their LDR is not a funding
  // ratio, and folding them into a claim about deposit-taking groups is a
  // category error. The sector aggregate is not a group either.
  const depositTaking = new Set<string>(
    PRIMARY_BANK_TYPES.filter((c) => c !== BANK_TYPES.SECTOR && c !== BANK_TYPES.DEV_INV),
  );
  const ldrGroups = [...latestByGroup(ldr)].filter(([code]) => depositTaking.has(code));
  const ldrDisplayed = ldr.filter(
    (row) => row.bank_type_code === BANK_TYPES.SECTOR || depositTaking.has(row.bank_type_code),
  );
  const ldrBreach = ldrGroups
    .filter(([, v]) => v.value >= 100)
    .map(([code]) => BANK_TYPE_LABELS[code] ?? code);

  // "Stopped falling" presumes the prior regime WAS a fall — flat-after-a-rise
  // would have printed the same sentence.
  const fxShare104 = valAgo(fxShare, 104);
  const fxSharePrior = fxShare52 != null && fxShare104 != null ? fxShare52 - fxShare104 : null;
  const fxFlat = fxShareDelta != null && Math.abs(fxShareDelta) < 1;

  // "The book grows, its shape does not" — both halves are in `mix`, the chart's
  // own data: the sum of the buckets, and how far the shares have travelled.
  const mixTotal = (r: Record<string, number>) =>
    MATURITY_SERIES.reduce((s, m) => s + (r[m.key] ?? 0), 0);
  const mixLast = mix.at(-1);
  const mixAgo = mix.at(-13);
  const mixGrew =
    mixLast && mixAgo ? mixTotal(mixLast) > mixTotal(mixAgo) : null;
  const mixShift =
    mixLast && mixAgo && mixTotal(mixLast) > 0 && mixTotal(mixAgo) > 0
      ? Math.max(
          ...MATURITY_SERIES.map((m) =>
            Math.abs(
              (100 * (mixLast[m.key] ?? 0)) / mixTotal(mixLast) -
                (100 * (mixAgo[m.key] ?? 0)) / mixTotal(mixAgo),
            ),
          ),
        )
      : null;
  const mixHeld = mixShift != null ? mixShift < 3 : null; // no bucket moved 3pp

  // ---- the base: the level, and what the book is actually made of -----------
  const trn = (v: number | null | undefined) => (v == null ? null : v / 1_000_000);
  const levelNow = trn(lastVal(depSector));
  const levelPrev = trn(depSector.at(-2)?.value ?? null);
  const levelWow = levelNow != null && levelPrev != null ? levelNow - levelPrev : null;

  const stateRows = depByGroup.filter((r) => r.bank_type_code === WEEKLY_BANK_TYPES.STATE);
  const stateNow = trn(lastVal(stateRows));
  const stateWow =
    stateNow != null && stateRows.at(-2)?.value != null
      ? stateNow - (trn(stateRows.at(-2)!.value) as number)
      : null;

  const fmtTrn = (v: number | null) => (v == null ? "—" : `₺${v.toFixed(2)}`);
  const share = (pct: number | null) =>
    levelNow != null && pct != null ? levelNow * (pct / 100) : null;

  // The maturity ladder, read out: how much of the book reprices inside a
  // quarter. This is the page's headline fact and nothing was saying it.
  const mNow = mix.at(-1);
  const MAT_KEYS = [
    "demand", "maturity_1m", "maturity_1_3m",
    "maturity_3_6m", "maturity_6_12m", "maturity_over_12m",
  ] as const;
  const matTotal = mNow ? MAT_KEYS.reduce((s, k) => s + (mNow[k] ?? 0), 0) : 0;
  const pctOf = (k: (typeof MAT_KEYS)[number]) =>
    mNow && matTotal > 0 ? ((mNow[k] ?? 0) * 100) / matTotal : null;
  const demandPct = pctOf("demand");
  const m1Pct = pctOf("maturity_1m");
  const m13Pct = pctOf("maturity_1_3m");
  const repriceQuarter =
    demandPct != null && m1Pct != null && m13Pct != null ? demandPct + m1Pct + m13Pct : null;

  // Real growth: Fisher-deflated by the published CPI print — never g − π.
  const realNow = lastVal(realVsNominal.filter((r) => r.bank_type_code === "REAL"));
  const cpiImplied = depYoYNow != null && realNow != null ? depYoYNow - realNow : null;

  // ---- movers: the six vitals, week on week, plus the level ----------------
  const wow = (s: { value: number | null }[]) => ({
    prev: s.at(-2)?.value ?? null,
    curr: s.at(-1)?.value ?? null,
  });
  const moverRows: MoverRow[] = [
    { label: "Deposit growth, 52w", ...wow(yoySector), fmt: (v) => `${v.toFixed(1)}%`, deltaDecimals: 1, good: "up" },
    {
      label: "4w momentum, ann.",
      note: "annualized from four weekly prints — volatile by construction",
      ...wow(mom4Sector), fmt: (v) => `${v.toFixed(1)}%`, deltaDecimals: 1, good: "up",
    },
    { label: "TL deposits, 52w", ...wow(tlYoySector), fmt: (v) => `${v.toFixed(1)}%`, deltaDecimals: 1, good: "up" },
    { label: "FX share", note: "the dollarization tell", ...wow(fxShare), good: "down" },
    { label: "Demand share", note: "cheap, but flighty", ...wow(dShare), good: "neutral" },
    {
      label: "Total deposits",
      note: "the level, ₺ trn",
      prev: levelPrev, curr: levelNow,
      fmt: (v) => `₺${v.toFixed(2)}`,
      deltaDecimals: 2, deltaUnit: " trn", good: "up",
    },
  ];

  // ---- the base → the balance sheet ---------------------------------------
  const transmission: TransmissionItem[] = [];
  if (repriceQuarter != null) {
    transmission.push({
      k: "Reprices ≤ 3 months",
      v: repriceQuarter.toFixed(1),
      unit: "%",
      effect: (
        <>{tx("Demand deposits are {0}, maturities up to one month {1}, and one-to-three months {2}. The sector lends long but funds itself within a quarter, so policy changes reach deposit costs quickly.",
          {0: fmtPct(demandPct), 1: fmtPct(m1Pct), 2: fmtPct(m13Pct)})}{" "}<Go href="/liquidity">{tx("/liquidity")}</Go>
        </>
      ),
    });
  }
  if (fundingGap != null) {
    transmission.push({
      k: "Funding gap",
      v: signedPp(fundingGap, 1).replace("pp", ""),
      unit: "pp",
      effect: (
        <>{tx("Loans grow ")}{tx(fmtPct(loansYoYNow))}{tx(" against deposits’ ")}{tx(fmtPct(depYoYNow))} —{" "}
          <b>
            {tx(fundingGap > 0
              ? "the loan book is outrunning the base"
              : "deposits are funding the loan book outright")}
          </b>
          {tx(fundingGap > 0 ? ", and the difference is bought in the market." : ".")}{" "}
          <Go href="/credit">{tx("/credit")}</Go>
        </>
      ),
    });
  }
  if (realNow != null) {
    transmission.push({
      k: "Real growth",
      v: realNow.toFixed(1),
      unit: "%",
      effect: (
        <>
          {tx(realNow < 0
            ? "Deposits grow {0} nominally against {1} CPI, but contract {2} in real terms."
            : "Deposits grow {0} nominally against {1} CPI and expand {2} in real terms.",
          {0: fmtPct(depYoYNow), 1: fmtPct(cpiImplied), 2: fmtPct(Math.abs(realNow))})}{" "}
          <Go href="/economy">{tx("/economy")}</Go>
        </>
      ),
    });
  }
  if (fxShareNow != null) {
    transmission.push({
      k: "FX share",
      v: fxShareNow.toFixed(1),
      unit: "%",
      effect: (
        <>
          {tx(fxShareDelta != null ? signedPp(fxShareDelta, 2) : "—")}{tx(" over 52 weeks —")}{" "}
          <b>{tx("dollarization is")}{" "}
            {tx(fxShareDelta != null && Math.abs(fxShareDelta) < 1
              ? "flat, not falling"
              : fxShareDelta != null && fxShareDelta < 0
                ? "receding"
                : "building")}
          </b>{tx(". The TL leg (")}{tx(fmtPct(tlYoYNow))}{tx(") is carrying the growth.")}{" "}
          <Go href="/liquidity">{tx("/liquidity")}</Go>
        </>
      ),
    });
  }

  // ---- flags: five rules, each printed whether or not it fires -------------
  const flags: Flag[] = [
    {
      code: "reprice-cliff",
      active: repriceQuarter != null && repriceQuarter > 85,
      body: (
        <>
          <b className="font-semibold">{tx("Repricing cliff")}</b>{tx(" — {0} of deposits reprice within three months: {1} demand deposits and {2} with maturity up to three months. Funding costs therefore follow the policy rate with very little delay.",
          {0: fmtPct(repriceQuarter), 1: fmtPct(demandPct), 2: fmtPct(m1Pct != null && m13Pct != null ? m1Pct + m13Pct : null)})}</>
      ),
      rule: "share(demand + ≤3m) > 85%",
      clear: <>{tx("Maturity ladder — ")}{tx(fmtPct(repriceQuarter))}{tx(" of the book reprices inside a quarter")}</>,
    },
    {
      code: "funding-gap",
      active: fundingGap != null && fundingGap > 3,
      body: (
        <>
          <b className="font-semibold">{tx("Funding gap")}</b>{tx(" — Loans grew {0} and deposits {1} over 52 weeks. The loan book is growing {2}pp faster than its deposit base.",
          {0: fmtPct(loansYoYNow), 1: fmtPct(depYoYNow), 2: Math.abs(fundingGap ?? 0).toFixed(1)})}</>
      ),
      rule: "loans_52w − deposits_52w > 3pp",
      clear: <>{tx("Funding gap — loans ")}{tx(fmtPct(loansYoYNow))}{tx(" vs deposits ")}{tx(fmtPct(depYoYNow))}</>,
    },
    {
      code: "real-base",
      active: realNow != null && realNow < 0,
      body: (
        <>
          <b className="font-semibold">{tx("Real base shrinking")}</b>{tx(" — deposits ")}{tx(fmtPct(depYoYNow))}{" "}{tx("against ")}{tx(fmtPct(cpiImplied))}{tx(" CPI: the base loses")}{" "}
          {tx(realNow != null ? Math.abs(realNow).toFixed(1) : "—")}{tx("% of its purchasing power a year while the loan book grows.")}</>
      ),
      rule: "deposits_52w − cpi_yoy < 0",
      clear: <>{tx("Real growth — deposits clear CPI by ")}{tx(realNow != null ? signedPp(realNow, 1) : "—")}</>,
    },
    {
      code: "dollarization",
      active: fxShareDelta != null && fxShareDelta > 1,
      body: (
        <>
          <b className="font-semibold">{tx("Re-dollarization")}</b>{tx(" — FX share ")}{tx(fmtPct(fxShareNow))},{" "}
          {tx(fxShareDelta != null ? signedPp(fxShareDelta, 2) : "—")}{tx(" over 52 weeks: savers are moving back into hard currency.")}</>
      ),
      rule: "Δ52w(fx_share) > +1pp",
      clear: (
        <>{tx("Dollarization — FX share ")}{tx(fxShareDelta != null ? signedPp(fxShareDelta, 2) : "—")}{tx(" over 52w")}</>
      ),
    },
    {
      code: "funding-stretch",
      active: ldrNow != null && ldrNow > LDR_PUBLISHED.line,
      body: (
        <>
          <b className="font-semibold">{tx("Funding stretch")}</b>{tx(" — TL+FC loan/deposit ")}{tx(fmtPct(ldrNow))}{tx(": lending leans on non-deposit funding. The TL-only book is tested separately, against a tighter line, on ")}<Go href="/liquidity">{tx("/liquidity")}</Go>.
        </>
      ),
      rule: LDR_PUBLISHED.rule,
      clear: <>{tx("Funding stretch — TL+FC loan/deposit ")}{tx(fmtPct(ldrNow))}{tx(", below the line")}</>,
    },
  ];
  const activeFlags = flags.filter((f) => f.active).length;

  // ---- standings: growth by group, and who is closest to the 100% line -----
  const growthRanked = [...yoyByBank]
    .filter((r) => r.value != null)
    .sort((a, b) => (b.value as number) - (a.value as number));
  const ldrRanked = PRIMARY_BANK_TYPES.map((code) => {
    const rows = ldr.filter((r) => r.bank_type_code === code);
    return { code, value: lastVal(rows) };
  })
    .filter((r) => r.value != null && r.value > 0 && r.code !== BANK_TYPES.SECTOR)
    .sort((a, b) => (b.value as number) - (a.value as number));

  const standings: StandingsGroup[] = [
    {
      heading: tx("Deposit growth, 52w — {0}", {0: weekLabel(depSector.at(-1)?.period, false)}),
      rows: growthRanked.map((r, i) => ({
        rank: i + 1,
        name: WEEKLY_BANK_TYPE_LABELS[r.bank_type_code] ?? r.bank_type_code,
        value: fmtPct(r.value),
        tone:
          depYoYNow != null && (r.value as number) >= depYoYNow ? ("up" as const) : ("dn" as const),
      })),
    },
    {
      heading: tx("{0} — monthly", {0: LDR_PUBLISHED.label}),
      rows: ldrRanked.map((r, i) => ({
        rank: i + 1,
        name: BANK_TYPE_LABELS[r.code] ?? r.code,
        value: fmtPct(r.value),
        tone: (r.value as number) > 100 ? ("dn" as const) : undefined,
      })),
    },
  ];

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title={tx("Deposits")}
        record={
          <>{tx("Record ")}<b className="font-normal text-foreground">{tx("week ending {0}", {0: recWeek})}</b>{tx(" · vs ")}{tx(vsWeek)}
          </>
        }
        right="every figure computed from source series"
        observations={[
          {
            cadence: "weekly",
            role: "current",
            asOf: depSector.at(-1)?.period,
            window: "4w and 52w",
            basis: "BDDK weekly sector bulletin",
          },
          {
            cadence: "monthly",
            role: "structure",
            asOf: ldrSector.at(-1)?.period,
            basis: "published TL+FC funding ratio",
          },
        ]}
      />

      {/* ── The vitals ─────────────────────────────────────────────────── */}
      <SecHead
        title={tx("The vitals")}
        meta={tx("weekly funding pulse · trailing 26 weeks")}
        className="mb-2.5 mt-6"
      />
      <Vitals cols={5}>
        <Vital
          label={tx("Deposit growth, 52w")}
          value={depYoYNow != null ? depYoYNow.toFixed(1) : "—"}
          unit="%"
          series={yoySector.slice(-26)}
          decimals={1}
          note={
            fundingGap != null ? (
              <>{tx("loans ")}{tx(fmtPct(loansYoYNow))} —{" "}
                <em
                  className={
                    fundingGap > 0
                      ? "not-italic font-semibold text-negative"
                      : "not-italic font-semibold text-positive"
                  }
                >
                  {tx(fundingGap > 0
                    ? "Loans are growing {0}pp faster than deposits."
                    : "Deposits are growing {0}pp faster than loans.",
                  {0: Math.abs(fundingGap).toFixed(1)})}</em>{" "}
                <Link href="/credit" className="font-semibold text-primary">{tx("/credit")}</Link>
              </>
            ) : undefined
          }
        />
        <Vital
          label={tx("4w momentum, ann.")}
          value={mom4Now != null ? mom4Now.toFixed(1) : "—"}
          unit="%"
          series={mom4Sector.slice(-26)}
          decimals={1}
          note={
            mom4Now != null && depYoYNow != null ? (
              <>
                {tx(signedPp(mom4Now - depYoYNow, 1))}{tx(" vs the 52w pace —")}{" "}
                {tx(mom4Now > depYoYNow ? "accelerating" : "cooling")}
              </>
            ) : undefined
          }
        />
        <Vital
          label={tx("TL deposits, 52w")}
          value={tlYoYNow != null ? tlYoYNow.toFixed(1) : "—"}
          unit="%"
          series={tlYoySector.slice(-26)}
          decimals={1}
          note={
            tlYoYNow != null && depYoYNow != null ? (
              <>
                {tx(tlYoYNow >= depYoYNow
                  ? "TL deposits are growing {0}pp faster than total deposits."
                  : "TL deposits are growing {0}pp slower than total deposits.",
                {0: Math.abs(tlYoYNow - depYoYNow).toFixed(1)})}</>
            ) : undefined
          }
        />
        <Vital
          label={tx("FX share of deposits")}
          value={fxShareNow != null ? fxShareNow.toFixed(1) : "—"}
          unit="%"
          series={fxShare.slice(-26)}
          decimals={1}
          note={
            <>
              {tx(fxShareDelta != null
                ? tx("{0} over 52w — {1}", {0: signedPp(fxShareDelta, 1), 1: fxShareDelta < 0 ? "de-dollarizing" : "re-dollarizing"})
                : "the dollarization tell")}{" "}
              <Link href="/liquidity" className="font-semibold text-primary">{tx("/liquidity")}</Link>
            </>
          }
        />
        <Vital
          label={tx("Demand share")}
          value={dShareNow != null ? dShareNow.toFixed(1) : "—"}
          unit="%"
          series={dShare.slice(-26)}
          decimals={1}
          note={
            dShareDelta != null ? (
              <>
                {tx(signedPp(dShareDelta, 1))}{tx(" over 52w — funding")}{" "}
                {tx(dShareDelta >= 0 ? "cheaper, less sticky in rate terms" : "termed out")}
              </>
            ) : undefined
          }
        />
      </Vitals>

      <CadenceBand
        title={tx("Monthly funding structure")}
        observation={{
          cadence: "monthly",
          role: "structure",
          asOf: ldrSector.at(-1)?.period,
          basis: LDR_PUBLISHED.basis,
        }}
      >
        <Vitals cols={3} rule="hair">
        <Vital
          label={tx(LDR_PUBLISHED.label)}
          value={ldrNow != null ? ldrNow.toFixed(1) : "—"}
          unit="%"
          series={ldrSector.slice(-13)}
          decimals={1}
          note={
            <>
              {tx(ldrNow != null && ldrNow < LDR_PUBLISHED.line
                ? "Below the {0}% line. This is the BDDK-published monthly sector ratio for all currencies. The weekly TL-only public/private comparison is on"
                : "Above the {0}% line. This is the BDDK-published monthly sector ratio for all currencies. The weekly TL-only public/private comparison is on",
              {0: LDR_PUBLISHED.line})}{" "}
              <Link href={LDR_PUBLISHED.elsewhere.href} className="font-semibold text-primary">
                {tx(LDR_PUBLISHED.elsewhere.href)}
              </Link>
            </>
          }
        />
        </Vitals>
      </CadenceBand>

      {/* ── Movers | The base → the balance sheet ──────────────────────── */}
      <div className="mt-8 grid gap-x-10 gap-y-8 lg:grid-cols-[5fr_7fr]">
        <div>
          <SecHead
            title={tx("Movers")}
            meta={tx(`${vsWeek} → ${weekLabel(depSector.at(-1)?.period, false)}`)}
            className="mb-2.5"
          />
          <Movers
            from={vsWeek.toUpperCase()}
            to={weekLabel(depSector.at(-1)?.period, false).toUpperCase()}
            rows={moverRows}
          />
        </div>
        <div>
          <SecHead
            title={tx("The base → the balance sheet")}
            meta={tx("what the funding actually is")}
            className="mb-2.5"
          />
          <Transmission items={transmission} />
        </div>
      </div>

      {/* ── Flags | Standings | Ahead ──────────────────────────────────── */}
      <div className="mt-8 grid gap-x-10 gap-y-8 lg:grid-cols-3">
        <div>
          <SecHead
            title={tx("Flags")}
            meta={tx("rule-based — {0} of {1}", {0: activeFlags, 1: flags.length})}
            className="mb-2.5"
          />
          <Flags
            flags={flags}
            showCleared
            quietNote="Repricing, the funding gap, real growth, dollarization and the 100% line are all below threshold."
          />
        </div>
        <div>
          <SecHead
            title={tx("Standings")}
            meta={tx("by ownership group · w/e {0}", {0: weekLabel(depSector.at(-1)?.period, false)})}
            href="/banks"
            hrefLabel={tx("by bank →")}
            className="mb-2.5"
          />
          <Standings groups={standings} />
        </div>
        <div>
          <SecHead title={tx("Ahead")} meta={tx("schedule — derived from the record periods + the tcmb calendar")} className="mb-2.5" />
          <Ahead
            items={[
              ahead.mpc && {
                when: ahead.mpc.when,
                what: (
                  <>{tx("TCMB MPC — the rate ")}{tx(fmtPct(repriceQuarter))}{tx(" of the book reprices to")}</>
                ),
              },
              ahead["brsa-filings"] && {
                when: ahead["brsa-filings"].when,
                what: <>{tx("BRSA ")}{tx(ahead["brsa-filings"].record)}{tx(" filings — deposit cost per bank")}</>,
                href: "/actions",
              },
              ahead["inflation-report"] && {
                when: ahead["inflation-report"].when,
                what: <>{tx("TCMB Inflation Report — the real-return backdrop")}</>,
              },
            ].filter((i) => !!i)}
          />
        </div>
      </div>

      {/* ── In depth — the evidence, on the brief's own grid ───────────── */}
      <Depth action={<GlobalRangeSelector />}>
        <Takeaway data={readData} variant="desk" />

        {/* The base — the sizes the ratios are ratios of. */}
        <div>
          <SecHead
            title={tx("The base")}
            meta={tx("levels · by ownership group · BDDK weekly bulletin")}
            className="mb-2.5"
          />
          <Levels
            items={[
              { k: "Total deposits", v: fmtTrn(levelNow), unit: "trn" },
              { k: "TL leg", v: fmtTrn(share(fxShareNow != null ? 100 - fxShareNow : null)), unit: "trn" },
              { k: "FX leg", v: fmtTrn(share(fxShareNow)), unit: "trn" },
              { k: "Demand", v: fmtTrn(share(dShareNow)), unit: "trn" },
            ]}
          />
          <div className="mt-6 grid grid-cols-1 gap-x-10 gap-y-9 lg:grid-cols-2">
            <StackedArea
              plain
              data={depByGroupWide}
              series={groupSeries}
              title={
                tx(levelWow != null && stateWow != null
                  ? tx("The book {0} ₺{1} trn in the week — the state banks {2} ₺{3} trn", {0: levelWow < 0 ? "shrank" : "grew", 1: Math.abs(levelWow).toFixed(2), 2: stateWow < 0 ? "lost" : "added", 3: Math.abs(stateWow).toFixed(2)})
                  : "Total deposits — level by group")
              }
              description={tx("total deposits, ₺ trn, weekly · stacked by ownership group")}
              source={
                <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[9px] text-faint">
                  <span>{tx("TOTAL ")}<b className="font-semibold text-foreground">{tx(fmtTrn(levelNow))}{tx(" trn")}</b>
                  </span>
                  <span>{tx("Δ WEEK")}{" "}
                    <b className="font-semibold text-foreground">
                      {tx(levelWow != null ? tx("{0}{1} trn", {0: levelWow >= 0 ? "+" : "−", 1: Math.abs(levelWow).toFixed(2)}) : "—")}
                    </b>
                  </span>
                  <span>{tx("STATE ")}<b className="font-semibold text-foreground">{tx(fmtTrn(stateNow))}{tx(" trn")}</b>
                  </span>
                </div>
              }
              yFormat="trn"
              decimals={2}
              height={280}
              colorKeys
            />
            <TrendChart
              plain
              data={yoyAll}
              seriesLabels={WEEKLY_BANK_TYPE_LABELS}
              title={
                tx(seriesFinding(yoySector, { noun: "Deposit growth", decimals: 1 }, tx.locale) ??
                "Deposit growth 52w (%) — by group")
              }
              description={tx("deposit growth 52w, %, weekly · by ownership group")}
              source={
                <ChartFoot
                  data={yoyAll}
                  labels={WEEKLY_BANK_TYPE_LABELS}
                  heroCode={WEEKLY_BANK_TYPES.SECTOR}
                  decimals={1}
                  deltaPeriods={52}
                  deltaLabel="52w"
                />
              }
              yFormat="pct"
              decimals={1}
              height={280}
              zeroLine
            />
            <TrendChart
              plain
              data={realVsNominal}
              seriesLabels={REAL_TERMS_LABELS}
              title={
                tx(realNow != null && realNow < 0
                  ? "In real terms the base is shrinking, not growing"
                  : "The base is growing ahead of prices")
              }
              description={tx("deposit growth 52w, %, weekly · nominal vs CPI-deflated")}
              source={
                <ChartFoot
                  data={realVsNominal}
                  labels={REAL_TERMS_LABELS}
                  heroCode="NOMINAL"
                  decimals={1}
                  deltaPeriods={52}
                  deltaLabel="52w"
                />
              }
              yFormat="pct"
              decimals={1}
              height={280}
              zeroLine
            />
            <TrendChart
              plain
              data={mom4Sector}
              seriesLabels={{ [WEEKLY_BANK_TYPES.SECTOR]: "4w ann." }}
              title={tx("The four-week pace is a weekly print, annualized — read it as noise, not as a turn")}
              description={tx("deposit growth, 4 weeks annualized, %, weekly · sector")}
              source={
                <ChartFoot
                  data={mom4Sector}
                  labels={{ [WEEKLY_BANK_TYPES.SECTOR]: "4w ann." }}
                  heroCode={WEEKLY_BANK_TYPES.SECTOR}
                  decimals={1}
                  deltaPeriods={52}
                  deltaLabel="52w"
                />
              }
              yFormat="pct"
              decimals={1}
              height={280}
              zeroLine
            />
          </div>
        </div>

        {/* Dollarization — a lone chart keeps the register: mark, then its read. */}
        <div>
          <SecHead
            title={tx("Dollarization")}
            meta={tx("fx share of the base · the public/private split lives on /liquidity")}
            className="mb-2.5"
          />
          <ChartRow data={fxShare} deltaPeriods={52} deltaLabel="52w" fmt={(v) => `${v.toFixed(1)}%`}>
            <TrendChart
              plain
              data={fxShare}
              seriesLabels={{ [WEEKLY_BANK_TYPES.SECTOR]: "FX share" }}
              title={
                tx(firstClaim(
                  [
                    fxFlat && fxSharePrior != null && fxSharePrior < -1,
                    "The FX share has stopped falling — flat for a year",
                  ],
                  [
                    fxFlat && fxSharePrior != null && fxSharePrior > 1,
                    "The FX share has stopped climbing — flat for a year",
                  ],
                  [fxFlat, "The FX share is flat — a year without a trend"],
                ) ?? "FX share of total deposits")
              }
              description={tx("fx deposits ÷ total deposits, %, weekly · sector")}
              yFormat="pct"
              decimals={1}
              height={300}
            />
          </ChartRow>
        </div>

        {/* Demand vs term — the ladder, finally read out. */}
        <div>
          <SecHead
            title={tx("Demand vs term")}
            meta={tx("weekly demand share · monthly maturity ladder")}
            className="mb-2.5"
          />
          <div className="grid grid-cols-1 gap-x-10 gap-y-9 lg:grid-cols-2">
            <TrendChart
              plain
              data={dShare}
              seriesLabels={{ [WEEKLY_BANK_TYPES.SECTOR]: "Demand" }}
              title={
                tx(seriesFinding(dShare, { noun: "Demand share", decimals: 1 }, tx.locale) ??
                "Demand share of total deposits")
              }
              description={tx("demand ÷ total deposits, %, weekly · sector")}
              source={
                <ChartFoot
                  data={dShare}
                  labels={{ [WEEKLY_BANK_TYPES.SECTOR]: "Demand" }}
                  heroCode={WEEKLY_BANK_TYPES.SECTOR}
                  decimals={1}
                  deltaPeriods={52}
                  deltaLabel="52w"
                />
              }
              yFormat="pct"
              decimals={1}
              height={280}
            />
            <StackedArea
              plain
              data={mix}
              series={MATURITY_SERIES}
              title={
                tx(repriceQuarter != null
                  ? tx("{0}% of the book matures inside three months", {0: repriceQuarter.toFixed(0)})
                  : "Maturity composition — share")
              }
              description={tx("maturity composition, % of deposits, monthly · sector")}
              source={
                <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[9px] text-faint">
                  <span>{tx("REPRICES ≤3M")}{" "}
                    <b className="font-semibold text-foreground">{tx(fmtPct(repriceQuarter))}</b>
                  </span>
                  <span>{tx("DEMAND ")}<b className="font-semibold text-foreground">{tx(fmtPct(demandPct))}</b>
                  </span>
                  <span>{tx("OVER 12M")}{" "}
                    <b className="font-semibold text-foreground">{tx(fmtPct(pctOf("maturity_over_12m")))}</b>
                  </span>
                  <span>{tx("BOOK")}{" "}
                    <b className="font-semibold text-foreground">{tx(fmtTrn(trn(matTotal)))}{tx(" trn")}</b>
                  </span>
                </div>
              }
              height={280}
              percentStack
            />
          </div>
          <div className="mt-6">
            <StackedArea
              plain
              data={mix}
              series={MATURITY_SERIES}
              title={
                tx(firstClaim(
                  [
                    mixGrew === true && mixHeld === true,
                    "The ladder in lira — the book grows, its shape does not",
                  ],
                  [
                    mixGrew === false && mixHeld === true,
                    "The ladder in lira — the book shrinks, its shape does not",
                  ],
                  [
                    mixHeld === false && mixShift != null,
                    tx("The ladder in lira — the shape is shifting ({0}pp over 12m)", {0: (mixShift ?? 0).toFixed(1)}),
                  ],
                ) ?? "The maturity ladder in lira")
              }
              description={tx("maturity composition, ₺ trn, monthly · sector")}
              source={tx("Source: BDDK monthly bulletin — deposits by maturity")}
              yFormat="trn"
              decimals={1}
              height={280}
            />
          </div>
        </div>

        {/* Loan-to-deposit. */}
        <div>
          <SecHead
            title={tx("Loan-to-deposit — TL+FC")}
            meta={tx("published ratio · monthly · by ownership group · TL-only weekly on /liquidity")}
            className="mb-2.5"
          />
          <ChartRow data={ldrDisplayed} labels={BANK_TYPE_LABELS} deltaPeriods={12} deltaLabel="12m" fmt={(v) => `${v.toFixed(0)}%`}>
            <TrendChart
              plain
              data={ldrDisplayed}
              seriesLabels={BANK_TYPE_LABELS}
              title={
                tx(firstClaim(
                  [
                    everyOf(ldrGroups, ([, v]) => v.value < 100),
                    "Every deposit-taking group funds its loan book below the 100% line",
                  ],
                  [
                    ldrBreach.length > 0,
                    tx("{0} lend more than they take in — above the 100% line", {0: ldrBreach.join(" and ")}),
                  ],
                ) ?? tx("{0} by group", {0: LDR_PUBLISHED.label}))
              }
              description={tx("published all-currency loans ÷ deposits, %, monthly · by ownership group")}
              yFormat="pct"
              decimals={0}
              height={300}
            />
          </ChartRow>
        </div>
      </Depth>

      <Colophon />
    </main>
  );
}
