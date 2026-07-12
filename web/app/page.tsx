/**
 * Home / Overview — "The Desk" two-layer page.
 *
 * Layer 1 (the brief): vitals band → movers vs last month → the macro
 * backdrop's computed transmission into bank P&L → rule-based flags (rules
 * printed) → capital standings → the release schedule. Every figure and every
 * note is computed from the same D1/EVDS series the charts read — compiled,
 * not written.
 *
 * Layer 2 ("In depth"): the same evidence, on the same grid. The read leads
 * (deterministic pulse, no card); the Table-15 scorecard is the brief's OWN
 * vitals band re-rendered for whichever ownership group `?type=` selects, with
 * a peer bar marking where the sector sits; the by-group trend charts sit
 * directly on the sheet, two per row — each spanning three cells of the band
 * above it — under a computed foot line. No boxes, no second grid.
 */
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
  evdsSeries,
  BANK_TYPES,
  PRIMARY_BANK_TYPES,
  BANK_TYPE_LABELS,
} from "@/app/lib/metrics";
import { perBankCapital } from "@/app/lib/audit-ratios";
import { getMarketTicker } from "@/app/lib/market-ticker";
import { BANK_NAMES } from "@/app/lib/bank_names";
import {
  cpiFromIndex,
  groupSpread,
  lastVal,
  monthLabel,
  signedPp,
  streak,
  valAgo,
  windowExtremes,
} from "@/app/lib/desk";
import {
  Ahead,
  ChartFoot,
  Colophon,
  Depth,
  DeskHeader,
  Flags,
  Levels,
  Movers,
  PeerBar,
  SecHead,
  Standings,
  Tape,
  Transmission,
  Vital,
  Vitals,
  type Flag,
  type MoverRow,
  type StandingsGroup,
  type TransmissionItem,
} from "@/app/components/desk";
import TrendChart from "@/app/components/TrendChart";
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

export const metadata: Metadata = {
  // Absolute title bypasses the "· Carthago" template so the home page leads
  // with the target phrase. This is the page that competes for "Turkish
  // banking sector data".
  title: {
    absolute: "Turkish Banking Sector Data, Financials & Analytics — Carthago",
  },
  description:
    "Live data on Türkiye's banking sector: 32 banks' audited BRSA financials, BDDK aggregates, capital adequacy, NPLs, liquidity, profitability and macro context — updated every quarter, free.",
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
    description:
      "32 banks' audited BRSA financials, BDDK aggregates and macro context for Türkiye's banking sector — updated quarterly, free.",
    url: "https://carthago.app",
  },
};

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
  const sector = [BANK_TYPES.SECTOR];

  // Bank-type filter for the in-depth scorecard (BANK_TYPE_LABELS keys are
  // exactly the six tabs BankTypeFilter offers). Defaults to Sector.
  const params = await searchParams;
  const bankType =
    params.type && params.type in BANK_TYPE_LABELS ? params.type : BANK_TYPES.SECTOR;
  const bt = [bankType];

  const [
    // Sector vitals for the brief.
    sCar, sNpl, sNim, sLdr, sRoe, sRoa, sAssetsYoY, sLoansYoY, sDepositsYoY,
    // By-group series: the four in-depth charts, and the league spread each
    // scorecard cell's peer bar is scaled against.
    loansYoYGroups, nplAllGroups, carGroups, roeGroups, nimGroups, ldrGroups, roaGroups,
    // Standings + backdrop.
    league, ticker, cpiRaw, fundingRaw,
    // In-depth scorecard for the selected bank type.
    assets, assetsYoY, loansYoY, depositsYoY, npl, car, nim, ldr, roa, roe,
  ] = await Promise.all([
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
    getMarketTicker().catch(() => []),
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

  const buffer = carNow != null ? carNow - 12 : null;
  const nplStreak = streak(sNpl, "up");
  const nimLow = windowExtremes(sNim, 24)?.min ?? null;
  const roeReal = roeNow != null && cpiAvgNow != null ? roeNow - cpiAvgNow : null;
  const carDrift12 = carNow != null && valAgo(sCar, 12) != null ? carNow - (valAgo(sCar, 12) as number) : null;

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
          ? `cooling from ${roePeak.max.toFixed(1)}% ${monthLabel(roePeak.maxPeriod, false)} peak`
          : undefined,
      prev: sRoe.at(-2)?.value ?? null,
      curr: roeNow,
      fmt: (v) => `${v.toFixed(1)}%`,
      deltaDecimals: 1,
      good: "up",
    },
    {
      label: "Capital adequacy",
      note: carSlip >= 3 ? `${carSlip} straight monthly slips` : undefined,
      prev: sCar.at(-2)?.value ?? null,
      curr: carNow,
      fmt: (v) => `${v.toFixed(1)}%`,
      deltaDecimals: 1,
      good: "up",
    },
    {
      label: "NPL ratio",
      note: nplStreak >= 2 ? `${nplStreak} consecutive rises` : undefined,
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
      label: "Loan / deposit",
      prev: sLdr.at(-2)?.value ?? null,
      curr: ldrNow,
      fmt: (v) => `${v.toFixed(1)}%`,
      deltaDecimals: 1,
      good: "neutral",
    },
    {
      label: "Assets, y/y",
      note:
        assetsYoYNow != null && cpiYoYNow != null && Math.abs(assetsYoYNow - cpiYoYNow) < 5
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
  const loansYoYNow = lastVal(sLoansYoY);
  const creditReal =
    loansYoYNow != null && cpiYoYNow != null ? loansYoYNow - cpiYoYNow : null;
  const usdtry = (ticker ?? []).find((t) => t.label.toUpperCase().includes("USD"));

  const transmission: TransmissionItem[] = [];
  if (cpiAvgNow != null) {
    transmission.push({
      k: "CPI, 12m-avg",
      v: `≈${cpiAvgNow.toFixed(1)}`,
      unit: "%",
      effect: (
        <>
          ROE {fmtPct(roeNow, 1)} ≈ <b>{roeReal != null ? signedPp(roeReal, 1) : "—"} in real terms</b> —{" "}
          {roeReal != null && roeReal < 0
            ? "the sector still compounds a real loss."
            : "the sector clears its inflation hurdle."}{" "}
          <Go href="/profitability">/profitability</Go>
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
        <>
          Deposits reprice first —{" "}
          <b>
            NIM {nimLow != null ? `rebuilt ${nimLow.toFixed(1)}%` : ""} →{" "}
            {fmtPct(nimNow, 1)}
          </b>
          ; each policy move feeds the margin with a lag.{" "}
          <Go href="/profitability">/profitability</Go>
        </>
      ),
    });
  }
  if (creditReal != null) {
    transmission.push({
      k: "Credit, real",
      v: signedPp(creditReal, 1).replace("pp", ""),
      unit: "pp",
      effect: (
        <>
          Loan growth {fmtPct(loansYoYNow, 1)} nominal vs CPI {fmtPct(cpiYoYNow, 1)} —{" "}
          <b>
            {creditReal > 2
              ? "credit is growing ahead of prices."
              : creditReal < -2
                ? "the book is shrinking in real terms."
                : "growth with prices, not the economy."}
          </b>{" "}
          <Go href="/credit">/credit</Go>
        </>
      ),
    });
  }
  if (usdtry) {
    transmission.push({
      k: "USD/TRY",
      v: usdtry.value,
      effect: (
        <>
          The lira&rsquo;s path sets the <b>dollarization incentive</b> — the FX share
          of deposits is the tell. <Go href="/deposits">/deposits</Go>
        </>
      ),
    });
  }

  // ---- flags (rules printed) ------------------------------------------------
  const flags: Flag[] = [
    {
      code: "real-roe",
      active: roeReal != null && roeReal < 0,
      body: (
        <>
          <b className="font-semibold">Real returns</b> — ROE {fmtPct(roeNow, 1)} vs{" "}
          {fmtPct(cpiAvgNow, 1)} 12m-avg CPI: equity compounds a{" "}
          {roeReal != null ? Math.abs(roeReal).toFixed(1) : "—"}pp real loss.
        </>
      ),
      rule: "roe − cpi_12m_avg < 0",
    },
    {
      code: "npl-streak",
      active: nplStreak >= 6,
      body: (
        <>
          <b className="font-semibold">NPL streak</b> — {nplStreak} monthly rises (
          {fmtPct(valAgo(sNpl, nplStreak), 2)} → {fmtPct(nplNow, 2)}). Level{" "}
          {nplNow != null && nplNow < 3 ? "benign" : "elevated"}; persistence is the
          signal. Next read: Stage-2 at the quarterly filings.
        </>
      ),
      rule: "consecutive_rise(npl) ≥ 6m",
    },
    {
      code: "car-drift",
      active: carDrift12 != null && carDrift12 < -0.5,
      body: (
        <>
          <b className="font-semibold">Capital drift</b> — buffer{" "}
          {buffer != null ? buffer.toFixed(1) : "—"}pp over the 12% minimum, drifting{" "}
          {carDrift12 != null ? signedPp(carDrift12, 1) : "—"}/yr.
        </>
      ),
      rule: "Δcar_12m < −0.5pp",
    },
    {
      code: "funding-stretch",
      active: ldrNow != null && ldrNow > 100,
      body: (
        <>
          <b className="font-semibold">Funding stretch</b> — loan/deposit{" "}
          {fmtPct(ldrNow, 1)}: growth leans on non-deposit funding.
        </>
      ),
      rule: "ldr > 100%",
    },
  ];
  const activeFlags = flags.filter((f) => f.active).length;

  // ---- standings ------------------------------------------------------------
  const ranked = league.rows.filter((r) => r.car != null);
  const standings: StandingsGroup[] = [
    {
      heading: `Best capitalised — ${quarterLabel(league.period)}`,
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
  });
  const read = await withLlmHeadline("overview", pulse);

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
    { label: "Loan / deposit", series: ldr, groups: ldrGroups, sector: ldrNow, decimals: 1 },
    { label: "ROE, ann.", series: roe, groups: roeGroups, sector: roeNow, decimals: 1 },
    { label: "ROA, ann.", series: roa, groups: roaGroups, sector: roaNow, decimals: 2 },
  ];

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(datasetJsonLd) }}
      />

      <DeskHeader
        title="Overview"
        record={
          <>
            Record <b className="font-normal text-foreground">{recMonth}</b> · vs {vsMonth}
          </>
        }
        right="every figure computed from source series"
      />

      <Tape
        items={(ticker ?? []).map((t) => ({ k: t.label, v: t.value, chg: t.changePct }))}
      />

      {/* ── The vitals ─────────────────────────────────────────────────── */}
      <SecHead
        title="The vitals"
        meta="equal weight · trailing 13 months"
        className="mb-2.5 mt-6"
      />
      <Vitals>
        <Vital
          label="Capital adequacy"
          value={carNow != null ? carNow.toFixed(1) : "—"}
          unit="%"
          series={spark(sCar)}
          decimals={1}
          note={
            <>
              buffer <b className="font-semibold text-positive">{buffer != null ? `+${buffer.toFixed(1)}pp` : "—"}</b>{" "}
              <Go href="/capital">/capital</Go>
            </>
          }
        />
        <Vital
          label="NPL ratio"
          value={nplNow != null ? nplNow.toFixed(2) : "—"}
          unit="%"
          series={spark(sNpl)}
          note={
            nplStreak >= 3 ? (
              <>
                <em className="not-italic font-semibold text-negative">
                  {nplStreak} straight rises
                </em>{" "}
                <Go href="/asset-quality">/asset-quality</Go>
              </>
            ) : (
              <>
                broadly stable <Go href="/asset-quality">/asset-quality</Go>
              </>
            )
          }
        />
        <Vital
          label="Net int. margin"
          value={nimNow != null ? nimNow.toFixed(2) : "—"}
          unit="%"
          series={spark(sNim)}
          note={
            <>
              {nimLow != null && nimNow != null && nimNow - nimLow > 0.5
                ? `rebuilt from ${nimLow.toFixed(1)}%`
                : "cycle margin"}{" "}
              <Go href="/profitability">/profitability</Go>
            </>
          }
        />
        <Vital
          label="Loan / deposit"
          value={ldrNow != null ? ldrNow.toFixed(1) : "—"}
          unit="%"
          series={spark(sLdr)}
          decimals={1}
          note={
            <>
              {ldrNow != null && ldrNow < 100 ? "below the 100% line" : "above the 100% line"}{" "}
              <Go href="/deposits">/deposits</Go>
            </>
          }
        />
        <Vital
          label="ROE, ann."
          value={roeNow != null ? roeNow.toFixed(1) : "—"}
          unit="%"
          series={spark(sRoe)}
          decimals={1}
          note={
            <>
              − CPI ≈{" "}
              <em
                className={
                  roeReal != null && roeReal < 0
                    ? "not-italic font-semibold text-negative"
                    : "not-italic font-semibold text-positive"
                }
              >
                {roeReal != null ? signedPp(roeReal, 1) : "—"} real
              </em>{" "}
              <Go href="/profitability">/profitability</Go>
            </>
          }
        />
        <Vital
          label="ROA, ann."
          value={roaNow != null ? roaNow.toFixed(2) : "—"}
          unit="%"
          series={spark(sRoa)}
          note="the leverage-free read"
        />
      </Vitals>

      {/* ── Movers | Backdrop ──────────────────────────────────────────── */}
      <div className="mt-8 grid gap-x-10 gap-y-8 lg:grid-cols-[5fr_7fr]">
        <div>
          <SecHead title="Movers" meta={`${vsMonth} → ${monthLabel(sNpl.at(-1)?.period, false)}`} className="mb-2.5" />
          <Movers
            from={vsMonth.toUpperCase()}
            to={monthLabel(sNpl.at(-1)?.period, false).toUpperCase()}
            rows={moverRows}
          />
        </div>
        <div>
          <SecHead
            title="The backdrop → the banks"
            meta="transmission computed"
            className="mb-2.5"
          />
          <Transmission items={transmission} />
        </div>
      </div>

      {/* ── Flags | Standings | Ahead ──────────────────────────────────── */}
      <div className="mt-8 grid gap-x-10 gap-y-8 lg:grid-cols-3">
        <div>
          <SecHead title="Flags" meta={`rule-based — ${activeFlags}`} className="mb-2.5" />
          <Flags
            flags={flags}
            quietNote="NPL streak, capital drift, funding stretch and real returns are all below threshold."
          />
        </div>
        <div>
          <SecHead
            title="Standings"
            meta={`car · ${quarterLabel(league.period)}`}
            href="/capital"
            hrefLabel="full league →"
            className="mb-2.5"
          />
          <Standings groups={standings} />
        </div>
        <div>
          <SecHead title="Ahead" meta="schedule — not a forecast" className="mb-2.5" />
          <Ahead
            items={[
              { when: "JUL 23", what: <>TCMB MPC — rate decision</> },
              { when: "AUG ~12", what: <>BDDK monthly bulletin — June record</> },
              {
                when: "AUG–SEP",
                what: <>BRSA Q2 filings — audited statements + capital</>,
                href: "/earnings",
              },
              { when: "FRI", what: <>BDDK weekly series — credit, deposits, FX</> },
            ]}
          />
        </div>
      </div>

      {/* ── In depth — the evidence, on the brief's own grid ───────────── */}
      <Depth action={<GlobalRangeSelector />}>
        <Takeaway data={read} variant="desk" />

        {/* The scorecard IS the vitals band — one group at a time. */}
        <div id="by-type" className="scroll-mt-24">
          <SecHead
            title="Snapshot scorecard"
            action={<BankTypeFilter active={bankType} />}
            meta={`table-15 vitals · ${groupLabel.toLowerCase()} · live d1`}
            className="mb-2.5"
          />
          <Levels
            items={[
              { k: "Total assets", v: fmtTrn(assets.at(-1)?.value) },
              { k: "Assets y/y", v: fmtPct(assetsYoY.at(-1)?.value, 1) },
              { k: "Loan growth y/y", v: fmtPct(loansYoY.at(-1)?.value, 1) },
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
                  label={v.label}
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
            {isSector
              ? "the sector aggregate — switch the group to read it against the league"
              : "bar = this group across the league of ownership groups · grey tick = the sector"}
          </p>
        </div>

        {/* Two charts per row — each spans three cells of the band above. */}
        <div>
          <SecHead
            title="Sector dynamics"
            meta="by ownership group · sector = the navy hero line"
            className="mb-3"
          />
          <div className="grid grid-cols-1 gap-x-10 gap-y-9 lg:grid-cols-2">
            <TrendChart
              plain
              data={loansYoYGroups}
              seriesLabels={BANK_TYPE_LABELS}
              title={
                seriesFinding(sLoansYoY, { noun: "Loan growth", decimals: 1 }) ??
                "Loan growth YoY (%) — by group"
              }
              description="loan growth y/y, %, monthly · BDDK monthly bulletin"
              source={<ChartFoot data={loansYoYGroups} labels={BANK_TYPE_LABELS} decimals={1} />}
              yFormat="pct"
              decimals={1}
              height={280}
              zeroLine
            />
            <TrendChart
              plain
              data={nplAllGroups}
              seriesLabels={BANK_TYPE_LABELS}
              title={
                seriesFinding(sNpl, { noun: "NPL ratio", decimals: 2 }) ??
                "NPL ratio (%) — by group"
              }
              description="npl ratio, %, monthly · BDDK monthly bulletin"
              source={<ChartFoot data={nplAllGroups} labels={BANK_TYPE_LABELS} decimals={2} />}
              yFormat="pct"
              decimals={2}
              height={280}
            />
            <TrendChart
              plain
              data={carGroups}
              seriesLabels={BANK_TYPE_LABELS}
              title={
                seriesFinding(sCar, { noun: "Capital adequacy", decimals: 1 }) ??
                "Capital adequacy (%) — by group"
              }
              description="capital adequacy, %, monthly · regulatory minimum 12% · BDDK"
              source={<ChartFoot data={carGroups} labels={BANK_TYPE_LABELS} decimals={1} />}
              yFormat="pct"
              decimals={1}
              height={280}
            />
            <TrendChart
              plain
              data={roeGroups}
              seriesLabels={BANK_TYPE_LABELS}
              title={
                seriesFinding(sRoe, { noun: "ROE", decimals: 1 }) ??
                "ROE — annualized (%) — by group"
              }
              description="roe annualized, %, monthly · BDDK monthly bulletin"
              source={<ChartFoot data={roeGroups} labels={BANK_TYPE_LABELS} decimals={1} />}
              yFormat="pct"
              decimals={1}
              height={280}
              zeroLine
            />
          </div>
        </div>
      </Depth>

      <Colophon />
    </main>
  );
}
