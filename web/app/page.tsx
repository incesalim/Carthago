import { SectorReport, SectorHeader, SectorContents, SectorMetrics, SectorOpening, SectorGrid, SectorPanel, SectorSection, SectorDirectory, SectorFooter } from "@/app/components/sector-report";
import { localizeMetadata } from "@/i18n/metadata";
import { getText } from "@/i18n/server";
import Link from "next/link";
import {
  ratioCar,
  ratioLdr,
  ratioNim,
  ratioNpl,
  ratioRoa,
  ratioRoe,
  totalAssets,
  totalAssetsYoY,
  totalLoansYoY,
  totalDepositsYoY,
  weeklySeries,
  weeklyGrowth,
  evdsSeries,
  BANK_TYPES,
  PRIMARY_BANK_TYPES,
  WEEKLY_BANK_TYPES,
  BANK_TYPE_LABELS,
} from "@/app/lib/metrics";
import { perBankCapital } from "@/app/lib/audit-ratios";
import { bankSummaries } from "@/app/lib/audit";
import { BANK_COUNT, BANK_NAMES } from "@/app/lib/bank_names";
import {
  cpiFromIndex,
  groupSpread,
  lastVal,
  monthLabel,
  signedPct,
  signedPp,
  streak,
  valAgo,
  windowExtremes,
} from "@/app/lib/desk";
import { LDR_PUBLISHED } from "@/app/lib/ldr";
import { realRate, cpiYoYByMonth } from "@/app/lib/real-terms";
import { creditBridge, fxAdjustedGrowth } from "@/app/lib/credit";
import { stageLadder } from "@/app/lib/credit-risk";
import {
  ChartFoot,
  Levels,
  Movers,
  PeerBar,
  SecHead,
  Standings,
  Transmission,
  Vital,
  Vitals,
  type MoverRow,
  type StandingsGroup,
  type TransmissionItem,
} from "@/app/components/desk";
import SectorTrend from "@/app/components/SectorTrend";
import SectorBreakdown from "@/app/components/SectorBreakdown";
import { sectorBalanceSheetStructure, sectorOperatingNetwork, operatingNetworkViews } from "@/app/lib/sector-overview";
import BankTypeFilter from "@/app/components/BankTypeFilter";
import { GlobalRangeSelector } from "@/app/components/range-context";
import Takeaway from "@/app/components/Takeaway";
import { overviewInsights } from "@/app/lib/insights";
import { seriesFinding } from "@/app/lib/chart-findings";
import { withLlmHeadline } from "@/app/lib/read-headlines";
import type { TimeSeriesRow } from "@/app/lib/metrics";
import type { Metadata } from "next";
import type { ReactNode } from "react";

export const dynamic = "force-dynamic";

/**
 * The one number in our metadata that is a CLAIM about the data: how many banks
 * we hold audited filings for. It was typed as "32" and was still saying so at
 * 38 — the text Google indexes, wrong for months, because nothing computed it.
 *
 * `bankSummaries()` is the same source /banks counts its rows from, so the two
 * can't disagree. It's KV-cached (`cachedAll`), and if D1 is unreachable we fall
 * back to the compile-time universe rather than shipping a stale integer.
 */
async function auditedBankCount(): Promise<number> {
  try {
    return (await bankSummaries()).length || BANK_COUNT;
  } catch {
    return BANK_COUNT;
  }
}

export async function generateMetadata(): Promise<Metadata> {
  const tx = await getText();
  const n = await auditedBankCount();
  return localizeMetadata({
    // Absolute title bypasses the "· Carthago" template so the home page leads
    // with the target phrase. This is the page that competes for "Turkish
    // banking sector data".
    title: {
      absolute: "Turkish Banking Sector Data, Financials & Analytics — Carthago",
    },
    description: tx("Live data on Türkiye's banking sector: {0} banks' audited BRSA financials, BDDK aggregates, capital adequacy, NPLs, liquidity, profitability and macro context — updated every quarter, free.", {0: n}),
    keywords: [
      "Turkish banking sector",
      "Turkish banks data",
      "BDDK data",
      "BRSA bank financials",
      "Türkiye banking",
      "Turkish bank ratios",
      "capital adequacy",
      "non-performing loans",
    ],
    alternates: { canonical: "/" },
    openGraph: {
      title: "Turkish Banking Sector Data, Financials & Analytics",
      description: tx("{0} banks' audited BRSA financials, BDDK aggregates and macro context for Türkiye's banking sector — updated quarterly, free.", {0: n}),
      url: "https://carthago.app",
    },
  });
}

const datasetJsonLd = {
  "@context": "https://schema.org",
  "@type": "Dataset",
  name: "Turkish Banking Sector Data",
  description:
    "Quarterly audited financials for Türkiye's banks (balance sheet, income statement, capital, asset quality, liquidity, profitability) from BRSA reports, plus BDDK sector aggregates and macro context.",
  url: "https://carthago.app",
  keywords: ["Turkish banking sector", "BDDK", "BRSA", "bank financials", "Türkiye"],
  isAccessibleForFree: true,
  spatialCoverage: "Türkiye",
  creator: { "@type": "Organization", name: "Carthago", url: "https://carthago.app" },
};

const fmtPct = (v: number | null | undefined, d = 2) =>
  v == null ? "—" : `${v.toFixed(d)}%`;
const fmtTrn = (v: number | null | undefined) =>
  v == null ? "—" : `₺${(v / 1_000_000).toFixed(2)} trn`;

// Weekly bulletin codes — the constant-FX credit bridge is built on them, the
// same series /credit uses, so the landing page cannot print a different real
// loan-growth figure from the Credit tab.
const KREDI = "krediler";
const TOTAL_LOANS = "1.0.1";
const CARDS = "1.0.8";
const GPL = "1.0.6";
const SME = "1.0.11";

/** Route link styled for use inside a computed note. */
const Go = ({ href, children }: { href: string; children: ReactNode }) => (
  <Link href={href} className="font-semibold text-primary">
    {children}
  </Link>
);

/** '2026Q1' (audit-lane format) or '2026-03…' → 'Q1 2026'. */
function quarterLabel(p: string | null): string {
  if (!p) return "latest quarter";
  const q = /^(\d{4})Q([1-4])$/.exec(p);
  if (q) return `Q${q[2]} ${q[1]}`;
  const m = /^(\d{4})-(\d{2})/.exec(p);
  return m ? `Q${Math.ceil(Number(m[2]) / 3)} ${m[1]}` : p;
}

export default async function OverviewPage({
  searchParams,
}: {
  searchParams: Promise<{ type?: string }>;
}) {
  const tx = await getText();
  const sector = [BANK_TYPES.SECTOR];

  // Bank-type filter for the in-depth scorecard (BANK_TYPE_LABELS keys are
  // exactly the six tabs BankTypeFilter offers). Defaults to Sector.
  const params = await searchParams;
  const bankType =
    params.type && params.type in BANK_TYPE_LABELS ? params.type : BANK_TYPES.SECTOR;
  const bt = [bankType];

  const [
    balanceStructure, operatingNetwork,
    // Sector vitals for the brief.
    sCar, sNpl, sNim, sLdr, sRoe, sRoa, sAssetsYoY, sLoansYoY, sDepositsYoY,
    // By-group series: the four in-depth charts, and the league spread each
    // scorecard cell's peer bar is scaled against.
    loansYoYGroups, nplAllGroups, carGroups, roeGroups, nimGroups, ldrGroups, roaGroups,
    // Standings + backdrop.
    league, usdRaw, cpiRaw, fundingRaw,
    // In-depth scorecard for the selected bank type.
    assets, assetsYoY, loansYoY, depositsYoY, npl, car, nim, ldr, roa, roe,
    // Weekly credit bridge (constant FX) + the Stage-2 watchlist for the brief.
    weeklyLoansYoY, tlWeekly, fxWeekly, cardsYoY, gplYoY, smeYoY, usdTryRaw, cpiYoYMap, ladder,
  ] = await Promise.all([
    sectorBalanceSheetStructure(), sectorOperatingNetwork(),
    ratioCar(sector),
    ratioNpl(sector),
    ratioNim(sector),
    ratioLdr(sector),
    ratioRoe(sector),
    ratioRoa(sector),
    totalAssetsYoY(sector),
    totalLoansYoY(sector),
    totalDepositsYoY(sector),

    totalLoansYoY(PRIMARY_BANK_TYPES),
    ratioNpl(PRIMARY_BANK_TYPES),
    ratioCar(PRIMARY_BANK_TYPES),
    ratioRoe(PRIMARY_BANK_TYPES),
    ratioNim(PRIMARY_BANK_TYPES),
    ratioLdr(PRIMARY_BANK_TYPES),
    ratioRoa(PRIMARY_BANK_TYPES),

    perBankCapital(),
    // USD/TRY from TCMB, not the market tape: the Yahoo feed this page used to
    // read was removed 2026-08-01 (its terms forbid redistribution outright).
    // EVDS carries the same quantity and permits republication with attribution.
    evdsSeries("TP.DK.USD.A", 1),
    evdsSeries("TP.TUKFIY2025.GENEL", 10),
    evdsSeries("TP.APIFON4", 1),

    totalAssets(bt),
    totalAssetsYoY(bt),
    totalLoansYoY(bt),
    totalDepositsYoY(bt),
    ratioNpl(bt),
    ratioCar(bt),
    ratioNim(bt),
    ratioLdr(bt),
    ratioRoa(bt),
    ratioRoe(bt),

    weeklyGrowth(KREDI, TOTAL_LOANS, "TOTAL", 52, [WEEKLY_BANK_TYPES.SECTOR], 104),
    weeklySeries(KREDI, TOTAL_LOANS, "TL", [WEEKLY_BANK_TYPES.SECTOR], 156),
    weeklySeries(KREDI, TOTAL_LOANS, "FX", [WEEKLY_BANK_TYPES.SECTOR], 156),
    weeklyGrowth(KREDI, CARDS, "TOTAL", 52, [WEEKLY_BANK_TYPES.SECTOR], 104),
    weeklyGrowth(KREDI, GPL, "TOTAL", 52, [WEEKLY_BANK_TYPES.SECTOR], 104),
    weeklyGrowth(KREDI, SME, "TOTAL", 52, [WEEKLY_BANK_TYPES.SECTOR], 104),
    evdsSeries("TP.DK.USD.A", 4),
    cpiYoYByMonth(),
    stageLadder(),
  ]);

  // ---- the computed backdrop -----------------------------------------------
  const cpi = cpiFromIndex(
    (cpiRaw as { period_date: string; value: number | null }[]).filter(
      (r): r is { period_date: string; value: number } => r.value != null,
    ),
  );
  const cpiAvgNow = lastVal(cpi.avg12);
  const cpiYoYNow = lastVal(cpi.yoy);
  const funding = (fundingRaw as { period_date: string; value: number | null }[])
    .filter((r) => r.value != null)
    .at(-1)?.value as number | null;

  // ---- vitals ---------------------------------------------------------------
  const carNow = lastVal(sCar);
  const nplNow = lastVal(sNpl);
  const nimNow = lastVal(sNim);
  const ldrNow = lastVal(sLdr);
  const roeNow = lastVal(sRoe);
  const roaNow = lastVal(sRoa);
  const assetsYoYNow = lastVal(sAssetsYoY);

  const assetsRealNow = realRate(assetsYoYNow, cpiYoYNow);
  const buffer = carNow != null ? carNow - 12 : null;
  const nplStreak = streak(sNpl, "up");
  const nimRange = windowExtremes(sNim, 24);
  const nimLow = nimRange?.min ?? null;
  const nimLowPeriod = nimRange?.minPeriod ?? null;
  // Fisher, not roe − cpi: at a ~32% CPI the shortcut is ~1.8pp adrift. The base
  // is the 12m AVERAGE because ROE is earned across the year, not at a point —
  // and the surfaces below print which base they used. (series.ts / real-terms.ts)
  const roeReal = realRate(roeNow, cpiAvgNow);

  const recMonth = monthLabel(sNpl.at(-1)?.period);
  const vsMonth = monthLabel(sNpl.at(-2)?.period, false);

  const spark = (s: TimeSeriesRow[]) => s.slice(-13);

  // ---- movers ---------------------------------------------------------------
  const roePeak = windowExtremes(sRoe, 13);
  const carSlip = streak(sCar, "down");
  const moverRows: MoverRow[] = [
    {
      label: "ROE, ann.",
      note:
        roePeak && roeNow != null && roePeak.max - roeNow > 1
          ? tx("cooling from {0}% {1} peak", {0: roePeak.max.toFixed(1), 1: monthLabel(roePeak.maxPeriod, false)})
          : undefined,
      prev: sRoe.at(-2)?.value ?? null,
      curr: roeNow,
      fmt: (v) => `${v.toFixed(1)}%`,
      deltaDecimals: 1,
      good: "up",
    },
    {
      label: "Capital adequacy",
      note: carSlip >= 3 ? tx("{0} straight monthly slips", {0: carSlip}) : undefined,
      prev: sCar.at(-2)?.value ?? null,
      curr: carNow,
      fmt: (v) => `${v.toFixed(1)}%`,
      deltaDecimals: 1,
      good: "up",
    },
    {
      label: "NPL ratio",
      note: nplStreak >= 2 ? tx("{0} consecutive rises", {0: nplStreak}) : undefined,
      prev: sNpl.at(-2)?.value ?? null,
      curr: nplNow,
      good: "down",
    },
    {
      label: "Net interest margin",
      prev: sNim.at(-2)?.value ?? null,
      curr: nimNow,
      good: "up",
    },
    {
      label: LDR_PUBLISHED.label,
      prev: sLdr.at(-2)?.value ?? null,
      curr: ldrNow,
      fmt: (v) => `${v.toFixed(1)}%`,
      deltaDecimals: 1,
      good: "neutral",
    },
    {
      label: "Assets, y/y",
      note:
        assetsRealNow != null && Math.abs(assetsRealNow) < 5
          ? "≈ flat in real terms"
          : undefined,
      prev: sAssetsYoY.at(-2)?.value ?? null,
      curr: assetsYoYNow,
      fmt: (v) => `${v.toFixed(1)}%`,
      deltaDecimals: 1,
      good: "neutral",
    },
  ];

  // ---- transmission ---------------------------------------------------------
  const usdtryNow = (usdRaw ?? []).at(-1)?.value ?? null;

  // THE real credit number: strip the FX revaluation and CPI, exactly as
  // /credit does. A CPI-only deflation is a different quantity and is never
  // called bare "real" — where it appears it carries the CPI-only chip.
  const usdTryRows = (usdTryRaw as { period_date: string; value: number | null }[])
    .filter((r): r is { period_date: string; value: number } => r.value != null);
  const fxAdjSeries = fxAdjustedGrowth(
    tlWeekly.map((r) => ({ period: r.period, value: r.value })),
    fxWeekly.map((r) => ({ period: r.period, value: r.value })),
    usdTryRows,
  );
  const bridge = creditBridge(weeklyLoansYoY, fxAdjSeries, cpiYoYMap);
  const creditRealFx = bridge.realFxAdj;
  const creditNominalAtReal = bridge.nominalAtReal ?? bridge.nominal;

  const transmission: TransmissionItem[] = [];
  if (cpiAvgNow != null) {
    transmission.push({
      k: "CPI, 12m-avg",
      v: `≈${cpiAvgNow.toFixed(1)}`,
      unit: "%",
      effect: (
        <>{tx("ROE ")}{tx(fmtPct(roeNow, 1))} ≈{" "}
          <b>{tx(roeReal != null ? signedPct(roeReal, 1) : "—")}{tx(" in real terms")}</b>{tx(" (deflated by 12m-avg CPI) —")}{" "}
          {tx(roeReal != null && roeReal < 0
            ? "the sector still compounds a real loss."
            : "the sector clears its inflation hurdle.")}{" "}
          <Go href="/profitability">{tx("Profitability")}</Go>
        </>
      ),
    });
  }
  if (funding != null) {
    transmission.push({
      k: "TCMB funding cost",
      v: funding.toFixed(1),
      unit: "%",
      effect: (
        <>{tx("Deposits reprice first; each policy move feeds the margin with a lag.")}{" "}
          <Go href="/profitability">{tx("Profitability")}</Go>
        </>
      ),
    });
  }
  if (creditRealFx != null) {
    transmission.push({
      k: "Credit — real, constant FX",
      v: signedPct(creditRealFx, 1).replace("%", ""),
      unit: "%",
      effect: (
        <>{tx("Loan growth {0} y/y nominal, FX included; after removing currency and price effects the book {1} {2} in real, constant-FX terms.", {
          0: fmtPct(creditNominalAtReal, 1),
          1: creditRealFx < 0 ? "shrank" : "grew",
          2: fmtPct(Math.abs(creditRealFx), 1),
        })}{" "}
          <Go href="/credit">{tx("Credit")}</Go>
        </>
      ),
    });
  }
  if (usdtryNow != null) {
    transmission.push({
      k: "USD/TRY",
      v: `₺${usdtryNow.toFixed(2)}`,
      effect: (
        <>{tx("The lira’s path sets the ")}<b>{tx("dollarization incentive")}</b>{tx(" — the FX share of deposits is the tell. ")}<Go href="/deposits">{tx("Deposits")}</Go>
        </>
      ),
    });
  }

  // ---- standings ------------------------------------------------------------
  const ranked = league.rows.filter((r) => r.car != null);
  const standings: StandingsGroup[] = [
    {
      heading: tx("Best capitalised — {0}", {0: quarterLabel(league.period)}),
      rows: ranked.slice(0, 3).map((r, i) => ({
        rank: i + 1,
        name: BANK_NAMES[r.bank_ticker] ?? r.bank_ticker,
        value: fmtPct(r.car, 1),
        tone: "up" as const,
      })),
    },
    {
      heading: "Thinnest buffer",
      rows: ranked
        .slice(-3)
        .reverse()
        .map((r, i) => ({
          rank: i + 1,
          name: BANK_NAMES[r.bank_ticker] ?? r.bank_ticker,
          value: fmtPct(r.car, 1),
          tone: "dn" as const,
        })),
    },
  ];

  // ---- the deterministic pulse + gated LLM lead (unchanged feature) ---------
  const pulse = overviewInsights({
    assetsYoY: sAssetsYoY, loansYoY: sLoansYoY, depositsYoY: sDepositsYoY,
    npl: sNpl, car: sCar, ldr: sLdr, roe: sRoe,
    cardsYoY, gplYoY, smeYoY,
  }, tx.locale);
  const read = await withLlmHeadline("overview", pulse, tx.locale);
  const network = operatingNetworkViews(operatingNetwork);

  // ---- the scorecard = the brief's band, for the selected group ------------
  // Same six vitals, same cell, same sparkline — only the group changes. Each
  // cell's peer bar is scaled to the observed spread across ownership groups,
  // with the sector marked, so a group reads against its league.
  const isSector = bankType === BANK_TYPES.SECTOR;
  const groupLabel = BANK_TYPE_LABELS[bankType] ?? "Sector";
  const change12 = (s: TimeSeriesRow[]): string | null => {
    const now = lastVal(s);
    const ago = valAgo(s, 12);
    return now != null && ago != null ? signedPp(now - ago, 1) : null;
  };
  const scorecard: {
    label: string;
    series: TimeSeriesRow[];
    groups: TimeSeriesRow[];
    sector: number | null;
    decimals: number;
  }[] = [
    { label: "Capital adequacy", series: car, groups: carGroups, sector: carNow, decimals: 1 },
    { label: "NPL ratio", series: npl, groups: nplAllGroups, sector: nplNow, decimals: 2 },
    { label: "Net int. margin", series: nim, groups: nimGroups, sector: nimNow, decimals: 2 },
    { label: LDR_PUBLISHED.label, series: ldr, groups: ldrGroups, sector: ldrNow, decimals: 1 },
    { label: "ROE, ann.", series: roe, groups: roeGroups, sector: roeNow, decimals: 1 },
    { label: "ROA, ann.", series: roa, groups: roaGroups, sector: roaNow, decimals: 2 },
  ];

  return (
    <SectorReport>
<SectorHeader sector="overview" record={<>{tx("Record ")}<b className="font-normal text-foreground">{tx(recMonth)}</b>{tx(" · vs ")}{tx(vsMonth)}
          </>} observations={[
          {
            cadence: "monthly",
            role: "current",
            asOf: sNpl.at(-1)?.period,
            window: "13m context",
            basis: "BDDK published sector aggregate",
          },
          {
            cadence: "quarterly",
            role: "audited",
            asOf: league.period,
            basis: "bank-level standings only",
          },
        ]} />
<SectorContents sections={[{id: "overview", label: "Key indicators"}, {id: "balance-sheet", label: "Balance sheet structure"}, {id: "developments", label: "Sector developments"}, {id: "by-type", label: "Bank groups"}, {id: "operating-network", label: "Operating network"}]} controls={<GlobalRangeSelector compact />} />
<script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify({ ...datasetJsonLd, name: tx(datasetJsonLd.name), description: tx(datasetJsonLd.description), inLanguage: tx.locale }) }}
      />
<SectorOpening><SectorMetrics><Vital
          label={tx("Capital adequacy")}
          value={carNow != null ? carNow.toFixed(1) : "—"}
          unit="%"
          series={spark(sCar)}
          decimals={1}
          note={
            <>{tx("buffer ")}<b className="font-semibold text-positive">{tx(buffer != null ? `+${buffer.toFixed(1)}pp` : "—")}</b>{" "}
              <Go href="/capital">{tx("Capital")}</Go>
            </>
          }
        />
<Vital
          label={tx("NPL ratio")}
          value={nplNow != null ? nplNow.toFixed(2) : "—"}
          unit="%"
          series={spark(sNpl)}
          note={
            <>
              <em className="not-italic font-semibold text-negative">
                {nplStreak >= 1
                  ? tx("{0} straight monthly rises", { 0: nplStreak })
                  : tx("rising")}
              </em>
              {ladder ? (
                <>
                  {" · "}
                  {tx("Stage 2 watchlist {0} — not in the NPL ratio", { 0: fmtPct(ladder.stage2Share) })}
                </>
              ) : null}{" "}
              <Go href="/asset-quality">{tx("Asset Quality")}</Go>
            </>
          }
        />
<Vital
          label={tx("Net int. margin")}
          value={nimNow != null ? nimNow.toFixed(2) : "—"}
          unit="%"
          series={spark(sNim)}
          note={
            <>
              {tx(nimLow != null && nimLowPeriod != null && nimNow != null && nimNow - nimLow > 0.5
                ? tx("recovered from the {0}% trough in {1}", { 0: nimLow.toFixed(1), 1: monthLabel(nimLowPeriod, false) })
                : tx("within its 24-month range"))}{" "}
              <Go href="/profitability">{tx("Profitability")}</Go>
            </>
          }
        />
<Vital
          label={tx(LDR_PUBLISHED.label)}
          value={ldrNow != null ? ldrNow.toFixed(1) : "—"}
          unit="%"
          series={spark(sLdr)}
          decimals={1}
          note={
            <>
              {tx(ldrNow != null && ldrNow < LDR_PUBLISHED.line
                ? tx("below the {0}% line", { 0: LDR_PUBLISHED.line })
                : tx("above the {0}% line", { 0: LDR_PUBLISHED.line }))}{" "}{tx("— published, monthly, BDDK Table 15, all banks ")}<Go href="/deposits">{tx("Deposits")}</Go>
            </>
          }
        />
<Vital
          label={tx("ROE, ann.")}
          value={roeNow != null ? roeNow.toFixed(1) : "—"}
          unit="%"
          series={spark(sRoe)}
          decimals={1}
          note={
            <>{tx("nominal")}{" · "}{tx("Fisher real")}{" "}
              <em
                className={
                  roeReal != null && roeReal < 0
                    ? "not-italic font-semibold text-negative"
                    : "not-italic font-semibold text-positive"
                }
              >
                {tx(roeReal != null ? signedPct(roeReal, 1) : "—")}</em>{" "}
              <Go href="/profitability">{tx("Profitability")}</Go>
            </>
          }
        />
<Vital
          label={tx("ROA, ann.")}
          value={roaNow != null ? roaNow.toFixed(2) : "—"}
          unit="%"
          series={spark(sRoa)}
          note="the leverage-free read"
        /></SectorMetrics>
</SectorOpening>
<SectorSection id="balance-sheet" title={tx("Balance sheet structure")} description={tx("How the sector's assets and funding are distributed.")}>
  <SectorGrid>
    <SectorBreakdown title={tx("Asset composition")} data={balanceStructure.assets} series={[{key:"amount",label:"Amount"}]}
      mode="ranking" format="trn" maxValue={balanceStructure.total ?? undefined} asOf={balanceStructure.period}
      source={tx("BDDK monthly balance sheet. Loans include non-performing balances and exclude expected loss allowances. Both charts use the same scale.")} />
    <SectorBreakdown title={tx("Funding composition")} data={balanceStructure.funding} series={[{key:"amount",label:"Amount"}]}
      mode="ranking" format="trn" maxValue={balanceStructure.total ?? undefined} asOf={balanceStructure.period}
      source={tx("BDDK monthly balance sheet. Each side reconciles to its published total; the charts do not assign funding sources to individual assets.")} />
  </SectorGrid>
  <SectorTrend data={[...sLoansYoY.map(row => ({...row,bank_type_code:"loans"})), ...sDepositsYoY.map(row => ({...row,bank_type_code:"deposits"}))]}
    seriesLabels={{loans:"Loans",deposits:"Deposits"}} title={tx("Loan and deposit growth")}
    description={tx("Annual growth, nominal and FX-included, on the same monthly reporting basis")}
    source={tx("BDDK monthly bulletin · nominal annual growth, including currency effects.")}
    yFormat="pct" height={260} zeroLine />
</SectorSection>
<SectorSection id="developments" title={tx("Sector developments")} description={tx("Credit growth, asset quality, capital adequacy and profitability by bank group.")}>
<SectorGrid>
  <SectorPanel title={tx("Period changes")} description={tx(`${vsMonth} → ${monthLabel(sNpl.at(-1)?.period, false)}`)}>
    <Movers from={vsMonth.toUpperCase()} to={monthLabel(sNpl.at(-1)?.period, false).toUpperCase()} rows={moverRows} />
  </SectorPanel>
  <SectorPanel title={tx("Macroeconomic context")} description={tx("Policy rates, inflation and funding")}>
    <Transmission items={transmission} />
  </SectorPanel>
</SectorGrid>
<SectorGrid>
  <SectorTrend data={carGroups} seriesLabels={BANK_TYPE_LABELS}
    title={tx("Capital adequacy")}
    description={tx(seriesFinding(sCar, { noun: "Capital adequacy", decimals: 1 }, tx.locale))}
    references={[{ value:12, label:"BDDK target ratio" }]}
    source={<><p>{tx("capital adequacy, %, monthly · target ratio 12% · BDDK")}</p><ChartFoot data={carGroups} labels={BANK_TYPE_LABELS} decimals={1} /></>}
    yFormat="pct" decimals={1} height={310} />
  <SectorTrend data={loansYoYGroups} seriesLabels={BANK_TYPE_LABELS}
    title={tx("Loan growth y/y — nominal, FX included")}
    description={tx(seriesFinding(sLoansYoY, { noun: "Loan growth", decimals: 1 }, tx.locale))}
    source={<><p>{tx("loan growth y/y, %, monthly, nominal and FX-included · BDDK monthly bulletin")}</p><ChartFoot data={loansYoYGroups} labels={BANK_TYPE_LABELS} decimals={1} /></>}
    yFormat="pct" decimals={1} deltaPeriods={12} deltaLabel="12m" zeroLine height={310} />
  <SectorTrend deltaPeriods={12} deltaLabel="12m" data={nplAllGroups} seriesLabels={BANK_TYPE_LABELS}
    title={tx("NPL ratio")}
    description={tx(seriesFinding(sNpl, { noun: "NPL ratio", decimals: 2 }, tx.locale))}
    source={<><p>{tx("npl ratio, %, monthly · BDDK monthly bulletin")}</p><ChartFoot data={nplAllGroups} labels={BANK_TYPE_LABELS} decimals={2} /></>}
    yFormat="pct" decimals={2} height={310} />
  <SectorTrend deltaPeriods={12} deltaLabel="12m" data={roeGroups} seriesLabels={BANK_TYPE_LABELS}
    title={tx("ROE, ann.")}
    description={tx(seriesFinding(sRoe, { noun: "ROE", decimals: 1 }, tx.locale))}
    source={<><p>{tx("roe annualized, %, monthly · BDDK monthly bulletin")}</p><ChartFoot data={roeGroups} labels={BANK_TYPE_LABELS} decimals={1} /></>}
    yFormat="pct" decimals={1} zeroLine height={310} />
</SectorGrid>
<Takeaway data={read} variant="report" />

</SectorSection>
<SectorSection id="by-type" title={tx("Bank groups")}>
<SectorPanel><SecHead
            title={tx("Group indicators")}
            action={<BankTypeFilter active={bankType} />}
            meta={tx("BDDK monthly bulletin · {0}", { 0: groupLabel.toLowerCase() })}
            className="mb-2.5"
          />
<Levels
            items={[
              { k: "Total assets", v: fmtTrn(assets.at(-1)?.value) },
              { k: "Assets y/y", v: fmtPct(assetsYoY.at(-1)?.value, 1) },
              { k: "Loan growth y/y — nominal, FX incl.", v: fmtPct(loansYoY.at(-1)?.value, 1) },
              { k: "Deposit growth y/y", v: fmtPct(depositsYoY.at(-1)?.value, 1) },
            ]}
          />
<Vitals rule="hair">
            {scorecard.map((v) => {
              const now = lastVal(v.series);
              const spread = groupSpread(v.groups);
              const chg = change12(v.series);
              return (
                <Vital
                  key={v.label}
                  label={tx(v.label)}
                  value={now != null ? now.toFixed(v.decimals) : "—"}
                  unit="%"
                  series={spark(v.series)}
                  decimals={v.decimals}
                  peer={
                    !isSector && now != null && v.sector != null && spread ? (
                      <PeerBar
                        value={now}
                        sector={v.sector}
                        lo={spread.lo}
                        hi={spread.hi}
                        decimals={v.decimals}
                      />
                    ) : undefined
                  }
                  note={chg ? `12m ${chg}` : undefined}
                />
              );
            })}
          </Vitals>
<p className="mt-2 font-mono text-[8.5px] uppercase tracking-[0.07em] text-faint">
            {tx(isSector
              ? "the sector aggregate — switch the group to read it against the league"
              : "bar = this group across the league of ownership groups · grey tick = the sector")}
          </p></SectorPanel><SectorPanel>
          <SecHead
            title={tx("Bank comparisons")}
            meta={tx("car · {0}", { 0: quarterLabel(league.period) })}
            href="/capital"
            hrefLabel={tx("full league →")}
            className="mb-2.5"
          />
          <Standings groups={standings} />
        </SectorPanel>
</SectorSection>

<SectorSection id="operating-network" title={tx("Operating network")} description={tx("Domestic distribution and the share of overseas branches within bank groups.")}>
  <SectorGrid>
    <SectorTrend data={network.history} seriesLabels={{"2":"Domestic branches","5":"ATMs","6":"Domestic employees"}}
      title={tx("Branches, ATMs and employees")}
      description={tx("Common starting period: {0} = 100",{0:network.basePeriod ?? "—"})}
      source={tx("BDDK monthly bulletin · counts indexed to a common starting month. Changes do not establish a causal link with digital banking.")}
      yFormat="raw" height={290} references={[{value:100,label:"Starting period"}]} />
    <SectorBreakdown title={tx("Overseas branches within bank groups")} data={network.overseas}
      series={[{key:"1",label:"Loan share"},{key:"2",label:"Asset share"},{key:"3",label:"Deposit share"}]}
      mode="paired" format="pct" asOf={network.overseasPeriod}
      source={tx("BDDK published ratios. Each share uses its own bank group's corresponding total. Overseas subsidiaries are outside this branch measure.")} />
  </SectorGrid>
</SectorSection>
<SectorDirectory />
<SectorFooter />
</SectorReport>
  );
}
