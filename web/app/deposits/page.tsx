import {
  SectorReport,
  SectorHeader,
  SectorContents,
  SectorMetrics,
  SectorOpening,
  SectorGrid,
  SectorPanel,
  SectorSection,
  SectorDirectory,
  SectorFooter,
} from "@/app/components/sector-report";
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
  CadenceBand,
  ChartFoot,
  ChartRow,
  Levels,
  Movers,
  SecHead,
  Standings,
  Transmission,
  Vital,
  Vitals,
  type MoverRow,
  type StandingsGroup,
  type TransmissionItem,
} from "@/app/components/desk";
import {
  lastVal,
  latestByGroup,
  monthLabel,
  signedPp,
  valAgo,
} from "@/app/lib/desk";
import { LDR_PUBLISHED } from "@/app/lib/ldr";
import { everyOf, firstClaim } from "@/app/lib/prose";
import { GlobalRangeSelector } from "@/app/components/range-context";
import SectorTrend from "@/app/components/SectorTrend";
import StackedArea from "@/app/components/StackedArea";
import Takeaway from "@/app/components/Takeaway";
import { depositsInsights } from "@/app/lib/insights";
import { seriesFinding } from "@/app/lib/chart-findings";
import { withLlmHeadline } from "@/app/lib/read-headlines";
import {
  cpiYoYByMonth,
  nominalVsReal,
  REAL_TERMS_LABELS,
} from "@/app/lib/real-terms";

export const dynamic = "force-dynamic";

const pageMetadata: Metadata = {
  title: "Turkish Banking Sector — Deposits",
  description:
    "Deposit trends for Türkiye's banks — TL vs FX, by bank type, and deposit growth from BDDK weekly and monthly bulletins.",
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
const Go = ({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) => (
  <Link href={href} className="font-semibold text-primary">
    {children}
  </Link>
);

/** Demand share = demand / total per period (×100). */
function demandShare(total: WeeklyRow[], demand: WeeklyRow[]): TimeSeriesRow[] {
  const totalMap = new Map(
    total.map((r) => [r.period + "|" + r.bank_type_code, r.value]),
  );
  const out: TimeSeriesRow[] = [];
  for (const r of demand) {
    const t = totalMap.get(r.period + "|" + r.bank_type_code);
    if (t == null || r.value == null || t === 0) continue;
    out.push({
      period: r.period,
      bank_type_code: r.bank_type_code,
      value: (r.value * 100) / t,
    });
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
      else
        byKey.set(k, {
          period: r.period,
          bank_type_code: r.bank_type_code,
          value: r.value,
        });
    }
  }
  return Array.from(byKey.values()).sort((a, b) =>
    a.period === b.period
      ? a.bank_type_code.localeCompare(b.bank_type_code)
      : a.period.localeCompare(b.period),
  );
}

/** Pivot long-form weekly rows into wide {period, [code]: value} rows for StackedArea. */
function pivotByCode(
  rows: WeeklyRow[],
  codes: string[],
): Record<string, string | number>[] {
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
  const all = Object.values(WEEKLY_BANK_TYPES);
  const sector = [WEEKLY_BANK_TYPES.SECTOR];
  const groups = all.filter((c) => c !== WEEKLY_BANK_TYPES.SECTOR);

  const [
    depSector,
    depByGroup,
    yoyAll,
    mom4Sector,
    yoyByBank,
    demandParts,
    tlSec,
    fxSec,
    mix,
    ldr,
    loansYoYSector,
    tlYoySector,
  ] = await Promise.all([
    weeklySeries(MEVDUAT, TOTAL, "TOTAL", sector, 156),
    weeklySeries(MEVDUAT, TOTAL, "TOTAL", groups, 156),
    weeklyGrowth(MEVDUAT, TOTAL, "TOTAL", 52, all, 104),
    weeklyGrowth(MEVDUAT, TOTAL, "TOTAL", 4, sector, 104),
    latestPerBank(weeklyTotalDepositsYoY, groups),
    Promise.all(
      DEMAND_PARTS.map((id) => weeklySeries(MEVDUAT, id, "TOTAL", sector, 156)),
    ),
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
  const yoySector = yoyAll.filter(
    (r) => r.bank_type_code === WEEKLY_BANK_TYPES.SECTOR,
  );
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
    fxShare.push({
      period: r.period,
      bank_type_code: WEEKLY_BANK_TYPES.SECTOR,
      value: (r.value * 100) / total,
    });
  }

  const ldrSector = ldr.filter((r) => r.bank_type_code === BANK_TYPES.SECTOR);

  // "The Read" — deterministic, computed from the same series the charts show.
  const read = depositsInsights(
    {
      yoy: yoySector,
      loansYoY: loansYoYSector,
      fxShare,
      demandShare: dShare,
      ldr: ldrSector,
    },
    tx.locale,
  );
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
  const fxShareDelta =
    fxShareNow != null && fxShare52 != null ? fxShareNow - fxShare52 : null;

  const dShareNow = lastVal(dShare);
  const dShare52 = valAgo(dShare, 52);
  const dShareDelta =
    dShareNow != null && dShare52 != null ? dShareNow - dShare52 : null;

  const ldrNow = lastVal(ldrSector);

  // "Every deposit-taking group funds its loan book below the 100% line" was
  // guarded on the SECTOR ratio — while the Standings table on this very page
  // already tones a group red when it breaches 100. Test the groups.
  //
  // Development & investment banks take no deposits: their LDR is not a funding
  // ratio, and folding them into a claim about deposit-taking groups is a
  // category error. The sector aggregate is not a group either.
  const depositTaking = new Set<string>(
    PRIMARY_BANK_TYPES.filter(
      (c) => c !== BANK_TYPES.SECTOR && c !== BANK_TYPES.DEV_INV,
    ),
  );
  const ldrGroups = [...latestByGroup(ldr)].filter(([code]) =>
    depositTaking.has(code),
  );
  const ldrDisplayed = ldr.filter(
    (row) =>
      row.bank_type_code === BANK_TYPES.SECTOR ||
      depositTaking.has(row.bank_type_code),
  );
  const ldrBreach = ldrGroups
    .filter(([, v]) => v.value >= 100)
    .map(([code]) => BANK_TYPE_LABELS[code] ?? code);

  // "Stopped falling" presumes the prior regime WAS a fall — flat-after-a-rise
  // would have printed the same sentence.
  const fxShare104 = valAgo(fxShare, 104);
  const fxSharePrior =
    fxShare52 != null && fxShare104 != null ? fxShare52 - fxShare104 : null;
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
  const trn = (v: number | null | undefined) =>
    v == null ? null : v / 1_000_000;
  const levelNow = trn(lastVal(depSector));
  const levelPrev = trn(depSector.at(-2)?.value ?? null);
  const levelWow =
    levelNow != null && levelPrev != null ? levelNow - levelPrev : null;

  const stateRows = depByGroup.filter(
    (r) => r.bank_type_code === WEEKLY_BANK_TYPES.STATE,
  );
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
    "demand",
    "maturity_1m",
    "maturity_1_3m",
    "maturity_3_6m",
    "maturity_6_12m",
    "maturity_over_12m",
  ] as const;
  const matTotal = mNow ? MAT_KEYS.reduce((s, k) => s + (mNow[k] ?? 0), 0) : 0;
  const pctOf = (k: (typeof MAT_KEYS)[number]) =>
    mNow && matTotal > 0 ? ((mNow[k] ?? 0) * 100) / matTotal : null;
  const demandPct = pctOf("demand");
  const m1Pct = pctOf("maturity_1m");
  const m13Pct = pctOf("maturity_1_3m");
  const repriceQuarter =
    demandPct != null && m1Pct != null && m13Pct != null
      ? demandPct + m1Pct + m13Pct
      : null;

  // Real growth: Fisher-deflated by the published CPI print — never g − π.
  const realNow = lastVal(
    realVsNominal.filter((r) => r.bank_type_code === "REAL"),
  );
  const cpiImplied =
    depYoYNow != null && realNow != null ? depYoYNow - realNow : null;

  // ---- movers: the six vitals, week on week, plus the level ----------------
  const wow = (s: { value: number | null }[]) => ({
    prev: s.at(-2)?.value ?? null,
    curr: s.at(-1)?.value ?? null,
  });
  const moverRows: MoverRow[] = [
    {
      label: "Deposit growth, 52w",
      ...wow(yoySector),
      fmt: (v) => `${v.toFixed(1)}%`,
      deltaDecimals: 1,
      good: "up",
    },
    {
      label: "Deposit growth, 4w annualized",
      note: "annualized from four weekly prints — volatile by construction",
      ...wow(mom4Sector),
      fmt: (v) => `${v.toFixed(1)}%`,
      deltaDecimals: 1,
      good: "up",
    },
    {
      label: "TL deposit growth, 52w",
      ...wow(tlYoySector),
      fmt: (v) => `${v.toFixed(1)}%`,
      deltaDecimals: 1,
      good: "up",
    },
    {
      label: "FX share",
      note: "the dollarization tell",
      ...wow(fxShare),
      good: "down",
    },
    {
      label: "Demand share",
      note: "cheap, but flighty",
      ...wow(dShare),
      good: "neutral",
    },
    {
      label: "Total deposits",
      note: "the level, ₺ trn",
      prev: levelPrev,
      curr: levelNow,
      fmt: (v) => `₺${v.toFixed(2)}`,
      deltaDecimals: 2,
      deltaUnit: " trn",
      good: "up",
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
        <>
          {tx(
            "Demand deposits are {0}, maturities up to one month {1}, and one-to-three months {2}. The sector lends long but funds itself within a quarter, so policy changes reach deposit costs quickly.",
            { 0: fmtPct(demandPct), 1: fmtPct(m1Pct), 2: fmtPct(m13Pct) },
          )}{" "}
          <Go href="/liquidity">{tx("Liquidity")}</Go>
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
        <>
          {tx("Loans grow ")}
          {tx(fmtPct(loansYoYNow))}
          {tx(" against deposits’ ")}
          {tx(fmtPct(depYoYNow))} —{" "}
          <b>
            {tx(
              fundingGap > 0
                ? "the loan book is outrunning the base"
                : "deposits are funding the loan book outright",
            )}
          </b>
          {tx(
            fundingGap > 0
              ? ", and the difference is bought in the market."
              : ".",
          )}{" "}
          <Go href="/credit">{tx("Credit")}</Go>
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
          {tx(
            realNow < 0
              ? "Deposits grow {0} nominally against {1} CPI, but contract {2} in real terms."
              : "Deposits grow {0} nominally against {1} CPI and expand {2} in real terms.",
            {
              0: fmtPct(depYoYNow),
              1: fmtPct(cpiImplied),
              2: fmtPct(Math.abs(realNow)),
            },
          )}{" "}
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
          {tx(fxShareDelta != null ? signedPp(fxShareDelta, 2) : "—")}
          {tx(" over 52 weeks —")}{" "}
          <b>
            {tx("dollarization is")}{" "}
            {tx(
              fxShareDelta != null && Math.abs(fxShareDelta) < 1
                ? "flat, not falling"
                : fxShareDelta != null && fxShareDelta < 0
                  ? "receding"
                  : "building",
            )}
          </b>
          {tx(". The TL leg (")}
          {tx(fmtPct(tlYoYNow))}
          {tx(") is carrying the growth.")}{" "}
          <Go href="/liquidity">{tx("Liquidity")}</Go>
        </>
      ),
    });
  }


  // ---- standings: growth by group, and who is closest to the 100% line -----
  const growthRanked = [...yoyByBank]
    .filter((r) => r.value != null)
    .sort((a, b) => (b.value as number) - (a.value as number));
  const ldrRanked = PRIMARY_BANK_TYPES.map((code) => {
    const rows = ldr.filter((r) => r.bank_type_code === code);
    return { code, value: lastVal(rows) };
  })
    .filter(
      (r) => r.value != null && r.value > 0 && r.code !== BANK_TYPES.SECTOR,
    )
    .sort((a, b) => (b.value as number) - (a.value as number));

  const standings: StandingsGroup[] = [
    {
      heading: tx("Deposit growth, 52w — {0}", {
        0: weekLabel(depSector.at(-1)?.period, false),
      }),
      rows: growthRanked.map((r, i) => ({
        rank: i + 1,
        name: WEEKLY_BANK_TYPE_LABELS[r.bank_type_code] ?? r.bank_type_code,
        value: fmtPct(r.value),
        tone:
          depYoYNow != null && (r.value as number) >= depYoYNow
            ? ("up" as const)
            : ("dn" as const),
      })),
    },
    {
      heading: tx("{0} — monthly", { 0: LDR_PUBLISHED.label }),
      rows: ldrRanked.map((r, i) => ({
        rank: i + 1,
        name: BANK_TYPE_LABELS[r.code] ?? r.code,
        value: fmtPct(r.value),
        tone: (r.value as number) > 100 ? ("dn" as const) : undefined,
      })),
    },
  ];

  return (
    <SectorReport>
      <SectorHeader
        sector="deposits"
        record={
          <>
            {tx("Record ")}
            <b className="font-normal text-foreground">
              {tx("week ending {0}", { 0: recWeek })}
            </b>
            {tx(" · vs ")}
            {tx(vsWeek)}
          </>
        }
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
      <SectorContents
        sections={[
          { id: "overview", label: "Key indicators" },
          { id: "growth", label: "Deposit growth" },
          { id: "bank-groups", label: "Bank groups" },
          { id: "currency", label: "Currency composition" },
          { id: "maturity", label: "Maturity structure" },
          { id: "loan-funding", label: "Loan-to-deposit" },
        ]}
        controls={<GlobalRangeSelector compact />}
      />
      <SectorOpening>
        <SectorMetrics>
          <Vital
            label={tx("Deposit growth, 52w")}
            value={depYoYNow != null ? depYoYNow.toFixed(1) : "—"}
            unit="%"
            series={yoySector.slice(-26)}
            decimals={1}
            note={
              fundingGap != null ? (
                <>
                  {tx("loans ")}
                  {tx(fmtPct(loansYoYNow))} —{" "}
                  <em
                    className={
                      fundingGap > 0
                        ? "not-italic font-semibold text-negative"
                        : "not-italic font-semibold text-positive"
                    }
                  >
                    {tx(
                      fundingGap > 0
                        ? "Loans are growing {0}pp faster than deposits."
                        : "Deposits are growing {0}pp faster than loans.",
                      { 0: Math.abs(fundingGap).toFixed(1) },
                    )}
                  </em>{" "}
                  <Link href="/credit" className="font-semibold text-primary">
                    {tx("Credit")}
                  </Link>
                </>
              ) : undefined
            }
          />
          <Vital
            label={tx("Deposit growth, 4w annualized")}
            value={mom4Now != null ? mom4Now.toFixed(1) : "—"}
            unit="%"
            series={mom4Sector.slice(-26)}
            decimals={1}
            note={
              mom4Now != null && depYoYNow != null ? (
                <>
                  {tx(signedPp(mom4Now - depYoYNow, 1))}
                  {tx(" vs the 52w pace —")}{" "}
                  {tx(mom4Now > depYoYNow ? "accelerating" : "cooling")}
                </>
              ) : undefined
            }
          />
          <Vital
            label={tx("TL deposit growth, 52w")}
            value={tlYoYNow != null ? tlYoYNow.toFixed(1) : "—"}
            unit="%"
            series={tlYoySector.slice(-26)}
            decimals={1}
            note={
              tlYoYNow != null && depYoYNow != null ? (
                <>
                  {tx(
                    tlYoYNow >= depYoYNow
                      ? "TL deposits are growing {0}pp faster than total deposits."
                      : "TL deposits are growing {0}pp slower than total deposits.",
                    { 0: Math.abs(tlYoYNow - depYoYNow).toFixed(1) },
                  )}
                </>
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
                {tx(
                  fxShareDelta != null
                    ? tx("{0} over 52w — {1}", {
                        0: signedPp(fxShareDelta, 1),
                        1:
                          fxShareDelta < 0
                            ? "de-dollarizing"
                            : "re-dollarizing",
                      })
                    : "the dollarization tell",
                )}{" "}
                <Link href="/liquidity" className="font-semibold text-primary">
                  {tx("Liquidity")}
                </Link>
              </>
            }
          />
        </SectorMetrics>
        <Takeaway data={readData} variant="report-summary" />
      </SectorOpening>
      <SectorSection
        id="growth"
        title={tx("Deposit growth")}
        description={tx(
          "Deposit volumes and growth by bank group, including the effect of inflation.",
        )}
      >
        <SectorGrid columns={2} ratio="balanced">
          <SectorTrend
            data={realVsNominal}
            seriesLabels={REAL_TERMS_LABELS}
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
            zeroLine
            title={tx("Deposit growth — nominal and real")}
            height={320}
            mode="trend"
            description={
              <>
                {tx("deposit growth 52w, %, weekly · nominal vs CPI-deflated")}
                <p className="mt-2 text-[14px] leading-relaxed">
                  {tx(
                    realNow != null && realNow < 0
                      ? "In real terms the base is shrinking, not growing"
                      : "The base is growing ahead of prices",
                  )}
                </p>
              </>
            }
          />
          <SectorTrend
            data={mom4Sector}
            seriesLabels={{ [WEEKLY_BANK_TYPES.SECTOR]: "4w ann." }}
            description={tx(
              "deposit growth, 4 weeks annualized, %, weekly · sector",
            )}
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
            zeroLine
            title={tx("Deposit growth over four weeks, annualized")}
            height={320}
            mode="trend"
          />
        </SectorGrid>
<Takeaway data={readData} variant="report-details" />

        <SectorGrid columns={2} ratio="balanced">
          <SectorPanel>
            <SecHead
              title={tx("Period changes")}
              meta={tx(
                `${vsWeek} → ${weekLabel(depSector.at(-1)?.period, false)}`,
              )}
              className="mb-2.5"
            />
            <Movers
              from={vsWeek.toUpperCase()}
              to={weekLabel(depSector.at(-1)?.period, false).toUpperCase()}
              rows={moverRows}
            />
          </SectorPanel>
          <SectorPanel title={tx("Deposit balances")}>
            <Levels
              items={[
                { k: "Total deposits", v: fmtTrn(levelNow), unit: "trn" },
                {
                  k: "TL leg",
                  v: fmtTrn(
                    share(fxShareNow != null ? 100 - fxShareNow : null),
                  ),
                  unit: "trn",
                },
                { k: "FX leg", v: fmtTrn(share(fxShareNow)), unit: "trn" },
                { k: "Demand", v: fmtTrn(share(dShareNow)), unit: "trn" },
              ]}
            />
          </SectorPanel>
        </SectorGrid>
      </SectorSection>
      <SectorSection
        id="bank-groups"
        title={tx("Bank groups")}
        description={tx(
          "Deposit volumes and growth by bank group, including the effect of inflation.",
        )}
      >
        <SectorTrend
          data={yoyAll}
          seriesLabels={WEEKLY_BANK_TYPE_LABELS}
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
          deltaPeriods={13}
          deltaLabel="13w"
          zeroLine
          title={tx("Deposit growth by bank group")}
          height={190}
          hero={WEEKLY_BANK_TYPES.SECTOR}
          mode="groups"
          description={
            <>
              {tx("deposit growth 52w, %, weekly · by ownership group")}
              <p className="mt-2 text-[14px] leading-relaxed">
                {tx(
                  seriesFinding(
                    yoySector,
                    { noun: "Deposit growth", decimals: 1 },
                    tx.locale,
                  ) ?? "Deposit growth 52w (%) — by group",
                )}
              </p>
            </>
          }
        />
        <SectorGrid columns={2} ratio="balanced">
          <StackedArea
            plain
            data={depByGroupWide}
            series={groupSeries}
            source={
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-[13px] text-faint">
                <span>
                  {tx("TOTAL ")}
                  <b className="font-semibold text-foreground">
                    {tx(fmtTrn(levelNow))}
                    {tx(" trn")}
                  </b>
                </span>
                <span>
                  {tx("Δ WEEK")}{" "}
                  <b className="font-semibold text-foreground">
                    {tx(
                      levelWow != null
                        ? tx("{0}{1} trn", {
                            0: levelWow >= 0 ? "+" : "−",
                            1: Math.abs(levelWow).toFixed(2),
                          })
                        : "—",
                    )}
                  </b>
                </span>
                <span>
                  {tx("STATE ")}
                  <b className="font-semibold text-foreground">
                    {tx(fmtTrn(stateNow))}
                    {tx(" trn")}
                  </b>
                </span>
              </div>
            }
            yFormat="trn"
            decimals={2}
            colorKeys
            title={tx("Deposit balances by bank group")}
            height={340}
            description={
              <>
                {tx(
                  "total deposits, ₺ trn, weekly · stacked by ownership group",
                )}
                <p className="mt-2 text-[14px] leading-relaxed">
                  {tx(
                    levelWow != null && stateWow != null
                      ? tx(
                          "The book {0} ₺{1} trn in the week — the state banks {2} ₺{3} trn",
                          {
                            0: levelWow < 0 ? "shrank" : "grew",
                            1: Math.abs(levelWow).toFixed(2),
                            2: stateWow < 0 ? "lost" : "added",
                            3: Math.abs(stateWow).toFixed(2),
                          },
                        )
                      : "Total deposits — level by group",
                  )}
                </p>
              </>
            }
          />
          <SectorPanel>
            <SecHead
              title={tx("Bank comparisons")}
              meta={tx("by ownership group · w/e {0}", {
                0: weekLabel(depSector.at(-1)?.period, false),
              })}
              href="/banks"
              hrefLabel={tx("by bank →")}
              className="mb-2.5"
            />
            <Standings groups={standings} />
          </SectorPanel>
        </SectorGrid>
      </SectorSection>
      <SectorSection
        id="currency"
        title={tx("Currency composition")}
        description={tx(
          "The share of foreign-currency deposits in total deposits.",
        )}
      >
        <SectorGrid columns={2} ratio="wide-left">
          <SectorTrend
            data={fxShare}
            seriesLabels={{ [WEEKLY_BANK_TYPES.SECTOR]: "FX share" }}
            yFormat="pct"
            decimals={1}
            title={tx("FX share of total deposits")}
            height={320}
            mode="trend"
            description={
              <>
                {tx("fx deposits ÷ total deposits, %, weekly · sector")}
                <p className="mt-2 text-[14px] leading-relaxed">
                  {tx(
                    firstClaim(
                      [
                        fxFlat && fxSharePrior != null && fxSharePrior < -1,
                        "The FX share has stopped falling — flat for a year",
                      ],
                      [
                        fxFlat && fxSharePrior != null && fxSharePrior > 1,
                        "The FX share has stopped climbing — flat for a year",
                      ],
                      [fxFlat, "The FX share is flat — a year without a trend"],
                    ) ?? "FX share of total deposits",
                  )}
                </p>
              </>
            }
            source={
              <>
                <details className="mt-3">
                  <summary className="cursor-pointer text-[13px] font-medium">
                    {tx("Historical comparison")}
                  </summary>
                  <ChartRow
                    data={fxShare}
                    deltaPeriods={52}
                    deltaLabel="52w"
                    fmt={(v) => `${v.toFixed(1)}%`}
                  >
                    {null}
                  </ChartRow>
                </details>
              </>
            }
          />
          <SectorPanel
            title={tx("Deposit structure and funding")}
            description={tx("Currency and maturity composition")}
          >
            <Transmission items={transmission} />
          </SectorPanel>
        </SectorGrid>
      </SectorSection>
      <SectorSection
        id="maturity"
        title={tx("Maturity structure")}
        description={tx("weekly demand share · monthly maturity ladder")}
      >
        <Vital
          label={tx("Demand share")}
          value={dShareNow != null ? dShareNow.toFixed(1) : "—"}
          unit="%"
          series={dShare.slice(-26)}
          decimals={1}
          note={
            dShareDelta != null ? (
              <>
                {tx(signedPp(dShareDelta, 1))}
                {tx(" over 52w — funding")}{" "}
                {tx(
                  dShareDelta >= 0
                    ? "cheaper, less sticky in rate terms"
                    : "termed out",
                )}
              </>
            ) : undefined
          }
        />
        <SectorGrid columns={2} ratio="balanced">
          <SectorTrend
            data={dShare}
            seriesLabels={{ [WEEKLY_BANK_TYPES.SECTOR]: "Demand" }}
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
            title={tx("Demand share of total deposits")}
            height={300}
            mode="trend"
            description={
              <>
                {tx("demand ÷ total deposits, %, weekly · sector")}
                <p className="mt-2 text-[14px] leading-relaxed">
                  {tx(
                    seriesFinding(
                      dShare,
                      { noun: "Demand share", decimals: 1 },
                      tx.locale,
                    ) ?? "Demand share of total deposits",
                  )}
                </p>
              </>
            }
          />
          <StackedArea
            plain
            data={mix}
            series={MATURITY_SERIES}
            title={tx("Deposit maturity — portfolio share")}
            description={
              <>
                {tx("maturity composition, % of deposits, monthly · sector")}
                <p className="mt-2 text-[14px] leading-relaxed">
                  {tx(
                    repriceQuarter != null
                      ? tx("{0}% of the book matures inside three months", {
                          0: repriceQuarter.toFixed(0),
                        })
                      : "Maturity composition — share",
                  )}
                </p>
              </>
            }
            source={
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-[13px] text-faint">
                <span>
                  {tx("REPRICES ≤3M")}{" "}
                  <b className="font-semibold text-foreground">
                    {tx(fmtPct(repriceQuarter))}
                  </b>
                </span>
                <span>
                  {tx("DEMAND ")}
                  <b className="font-semibold text-foreground">
                    {tx(fmtPct(demandPct))}
                  </b>
                </span>
                <span>
                  {tx("OVER 12M")}{" "}
                  <b className="font-semibold text-foreground">
                    {tx(fmtPct(pctOf("maturity_over_12m")))}
                  </b>
                </span>
                <span>
                  {tx("BOOK")}{" "}
                  <b className="font-semibold text-foreground">
                    {tx(fmtTrn(trn(matTotal)))}
                    {tx(" trn")}
                  </b>
                </span>
              </div>
            }
            percentStack
            height={300}
          />
        </SectorGrid>
        <SectorPanel>
          <StackedArea
            plain
            data={mix}
            series={MATURITY_SERIES}
            title={tx("Deposit maturity — balances")}
            description={
              <>
                {tx("maturity composition, ₺ trn, monthly · sector")}
                <p className="mt-2 text-[14px] leading-relaxed">
                  {tx(
                    firstClaim(
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
                        tx(
                          "The ladder in lira — the shape is shifting ({0}pp over 12m)",
                          { 0: (mixShift ?? 0).toFixed(1) },
                        ),
                      ],
                    ) ?? "The maturity ladder in lira",
                  )}
                </p>
              </>
            }
            source={tx("Source: BDDK monthly bulletin — deposits by maturity")}
            yFormat="trn"
            decimals={1}
            height={320}
          />
        </SectorPanel>
      </SectorSection>
      <SectorSection
        id="loan-funding"
        title={tx("Loan-to-deposit")}
        description={tx(
          "Published monthly ratio for TL and foreign-currency loans and deposits.",
        )}
      >
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
                  {tx(
                    ldrNow != null && ldrNow < LDR_PUBLISHED.line
                      ? "Below the {0}% line. This is the BDDK-published monthly sector ratio for all currencies. The weekly TL-only public/private comparison is on"
                      : "Above the {0}% line. This is the BDDK-published monthly sector ratio for all currencies. The weekly TL-only public/private comparison is on",
                    { 0: LDR_PUBLISHED.line },
                  )}{" "}
                  <Link
                    href={LDR_PUBLISHED.elsewhere.href}
                    className="font-semibold text-primary"
                  >
                    {tx(LDR_PUBLISHED.elsewhere.href)}
                  </Link>
                </>
              }
            />
          </Vitals>
        </CadenceBand>
        <SectorTrend
          data={ldrDisplayed}
          seriesLabels={BANK_TYPE_LABELS}
          yFormat="pct"
          decimals={0}
          title={tx("Loan-to-deposit ratio by bank group")}
          height={180}
          mode="groups"
          references={[{ value: 100, label: tx("100% reference") }]}
          description={
            <>
              {tx(
                "published all-currency loans ÷ deposits, %, monthly · by ownership group",
              )}
              <p className="mt-2 text-[14px] leading-relaxed">
                {tx(
                  firstClaim(
                    [
                      everyOf(ldrGroups, ([, v]) => v.value < 100),
                      "Every deposit-taking group funds its loan book below the 100% line",
                    ],
                    [
                      ldrBreach.length > 0,
                      tx(
                        "{0} lend more than they take in — above the 100% line",
                        { 0: ldrBreach.join(" and ") },
                      ),
                    ],
                  ) ?? tx("{0} by group", { 0: LDR_PUBLISHED.label }),
                )}
              </p>
            </>
          }
          source={
            <>
              <details className="mt-3">
                <summary className="cursor-pointer text-[13px] font-medium">
                  {tx("Historical comparison")}
                </summary>
                <ChartRow
                  data={ldrDisplayed}
                  labels={BANK_TYPE_LABELS}
                  deltaPeriods={12}
                  deltaLabel="12m"
                  fmt={(v) => `${v.toFixed(0)}%`}
                >
                  {null}
                </ChartRow>
              </details>
            </>
          }
        />
      </SectorSection>
      <SectorDirectory sector="deposits" />
      <SectorFooter />
    </SectorReport>
  );
}
