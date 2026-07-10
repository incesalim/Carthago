/**
 * Home / Overview tab.
 *
 * A single `?type=`-switchable Snapshot scorecard (size + growth + the Table-15
 * ratio vitals, formerly split across "Snapshot" and the standalone
 * /sector/ratios page) + by-group trend charts. The "Sector Pulse" lead stays
 * sector-aggregate regardless of the selected type.
 */
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
  latestPeriod,
  PRIMARY_BANK_TYPES,
  BANK_TYPES,
  BANK_TYPE_LABELS,
} from "@/app/lib/metrics";
import TrendChart from "@/app/components/TrendChart";
import Sparkline from "@/app/components/Sparkline";
import BankTypeFilter from "@/app/components/BankTypeFilter";
import { PageHeader, Section, Stat, DeltaBadge } from "@/app/components/ui";
import Takeaway from "@/app/components/Takeaway";
import { overviewInsights } from "@/app/lib/insights";
import { seriesFinding } from "@/app/lib/chart-findings";
import { withLlmHeadline } from "@/app/lib/read-headlines";
import type { TimeSeriesRow } from "@/app/lib/metrics";
import type { Metadata } from "next";

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
  keywords: [
    "Turkish banking sector",
    "BDDK",
    "BRSA",
    "bank financials",
    "Türkiye",
  ],
  isAccessibleForFree: true,
  spatialCoverage: "Türkiye",
  creator: {
    "@type": "Organization",
    name: "Carthago",
    url: "https://carthago.app",
  },
};

interface KpiCardProps {
  label: string;
  value: string;
  period: string;
  hint?: string;
  series?: TimeSeriesRow[];
  format?: "pct" | "trn" | "raw";
  decimals?: number;
  tone?: "neutral" | "positive" | "warn";
  /** Direction that colours the period-over-period delta chip green. */
  goodDirection?: "up" | "down" | "neutral";
}

function KpiCard({ label, value, period, hint, series, format, decimals, tone = "neutral", goodDirection = "up" }: KpiCardProps) {
  const curr = series?.at(-1)?.value ?? null;
  const prev = series?.at(-2)?.value ?? null;
  const deltaFormat = format === "trn" ? "trn" : format === "raw" ? "raw" : "pp";
  return (
    <Stat
      label={label}
      value={value}
      hint={`${period}${hint ? ` · ${hint}` : ""}`}
      tone={tone === "warn" ? "warning" : tone}
      badge={
        <DeltaBadge
          curr={curr}
          prev={prev}
          format={deltaFormat}
          decimals={decimals ?? 2}
          goodDirection={goodDirection}
        />
      }
    >
      {series && series.length > 0 && (
        <Sparkline
          data={series.map((r) => ({ period: r.period, value: r.value ?? 0 }))}
          format={format}
          decimals={decimals}
        />
      )}
    </Stat>
  );
}

const fmtPct = (v: number | null | undefined, d = 2) =>
  v == null ? "—" : `${v.toFixed(d)}%`;
const fmtTrn = (v: number | null | undefined) =>
  v == null ? "—" : `₺${(v / 1_000_000).toFixed(2)} trn`;

export default async function OverviewPage({
  searchParams,
}: {
  searchParams: Promise<{ type?: string }>;
}) {
  const sector = [BANK_TYPES.SECTOR];

  // Bank-type filter for the Table-15 scorecard section (BANK_TYPE_LABELS keys
  // are exactly the six tabs BankTypeFilter offers). Defaults to Sector.
  const params = await searchParams;
  const bankType =
    params.type && params.type in BANK_TYPE_LABELS
      ? params.type
      : BANK_TYPES.SECTOR;
  const bt = [bankType];

  const [
    // Sector series feeding the (always-sector) Pulse lead.
    sAssetsYoY, sLoansYoY, sDepositsYoY, sNpl, sCar, sLdr, sRoe,
    // By-group trends for the dynamics chart grid — one per CAMELS vital.
    loansYoYGroups, nplAllGroups, carGroups, roeGroups,
    // Snapshot scorecard for the selected bank type (defaults to sector):
    // size + growth, then the Table-15 ratio vitals.
    assets, assetsYoY, loansYoY, depositsYoY, npl, car, nim, ldr, roa, roe,
  ] = await Promise.all([
    totalAssetsYoY(sector),
    totalLoansYoY(sector),
    totalDepositsYoY(sector),
    ratioNpl(sector),
    ratioCar(sector),
    ratioLdr(sector),
    ratioRoe(sector),

    totalLoansYoY(PRIMARY_BANK_TYPES),
    ratioNpl(PRIMARY_BANK_TYPES),
    ratioCar(PRIMARY_BANK_TYPES),
    ratioRoe(PRIMARY_BANK_TYPES),

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

  // Latest point of each selected-type scorecard series.
  const a = assets.at(-1);
  const ay = assetsYoY.at(-1);
  const ly = loansYoY.at(-1);
  const dy = depositsYoY.at(-1);
  const n = npl.at(-1);
  const c = car.at(-1);
  const m = nim.at(-1);
  const l = ldr.at(-1);
  const ra = roa.at(-1);
  const re = roe.at(-1);

  // Deterministic "Sector Pulse" — always the sector aggregate (the copy reads
  // "the sector"), independent of the scorecard's bank-type selection.
  const pulse = overviewInsights({
    assetsYoY: sAssetsYoY, loansYoY: sLoansYoY, depositsYoY: sDepositsYoY,
    npl: sNpl, car: sCar, ldr: sLdr, roe: sRoe,
  });
  // Option 1: show the LLM-rewritten lead when it matches these live facts,
  // else the deterministic sentence (read-headlines.ts gates + falls back).
  const read = await withLlmHeadline("overview", pulse);

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(datasetJsonLd) }}
      />
      <PageHeader
        eyebrow="Banking Sector"
        title="Overview"
        description="BDDK monthly bulletin · sector aggregate · live D1 query"
        rangeSelector
        dataThrough={latestPeriod(assets, npl, car, roe)}
      />

      <Takeaway data={read} />

      {/* Snapshot scorecard — the sector aggregate by default, switchable to any
          bank-type group via the filter. Merges the old sector snapshot and the
          by-bank-type Table-15 scorecard into one surface. #by-type anchor is the
          redirect target for the retired /sector/ratios page. */}
      <div id="by-type" className="scroll-mt-24">
      <Section
        index="01"
        title="Snapshot"
        description="the sector aggregate — or any bank-type group — on the regulator's Table-15 vitals: size, growth, quality, capital, margin and returns · live D1"
        actions={<BankTypeFilter active={bankType} />}
      >
      {/* Size + growth */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KpiCard label="Total Assets" value={fmtTrn(a?.value)} period={a?.period ?? "—"}
                 series={assets} format="trn" decimals={2} />
        <KpiCard label="Assets YoY" value={fmtPct(ay?.value, 1)} period={ay?.period ?? "—"}
                 series={assetsYoY} format="pct" decimals={1} />
        <KpiCard label="Loan Growth YoY" value={fmtPct(ly?.value, 1)} period={ly?.period ?? "—"}
                 series={loansYoY} format="pct" decimals={1} />
        <KpiCard label="Deposit Growth YoY" value={fmtPct(dy?.value, 1)} period={dy?.period ?? "—"}
                 series={depositsYoY} format="pct" decimals={1} />
      </div>

      {/* Ratio vitals — the BDDK Table-15 scorecard */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
        <KpiCard label="NPL Ratio" value={fmtPct(n?.value)} period={n?.period ?? "—"}
                 hint="Takipteki / Toplam Krediler" series={npl} format="pct" decimals={2} goodDirection="down" />
        <KpiCard label="Capital Adequacy" value={fmtPct(c?.value, 1)} period={c?.period ?? "—"}
                 hint="SYR · regulatory min 12%" series={car} format="pct" decimals={1} />
        <KpiCard label="Net Interest Margin" value={fmtPct(m?.value)} period={m?.period ?? "—"}
                 hint="annualized · NII / avg assets" series={nim} format="pct" decimals={2} />
        <KpiCard label="Loan / Deposit" value={fmtPct(l?.value, 1)} period={l?.period ?? "—"}
                 series={ldr} format="pct" decimals={1} goodDirection="neutral" />
        <KpiCard label="ROA" value={fmtPct(ra?.value)} period={ra?.period ?? "—"}
                 hint="annualized" series={roa} format="pct" decimals={2} />
        <KpiCard label="ROE" value={fmtPct(re?.value, 1)} period={re?.period ?? "—"}
                 hint="annualized" series={roe} format="pct" decimals={1} />
      </div>

      </Section>
      </div>

      <Section
        index="02"
        title="Sector dynamics"
        description="growth, quality and returns by ownership group"
        contentClassName=""
      >
      {/* Vital-signs trends — one per CAMELS vital, by bank group, mirroring the
          KPI digest above (re-curated against the sector-story spine). */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <TrendChart
          data={loansYoYGroups}
          seriesLabels={BANK_TYPE_LABELS}
          title={
            seriesFinding(sLoansYoY, { noun: "Loan growth", decimals: 1 }) ??
            "Loan Growth YoY (%) — by group"
          }
          description="Loan growth YoY, %, monthly · by ownership group"
          source="Source: BDDK monthly bulletin"
          yFormat="pct"
          decimals={1}
          zeroLine
        />
        <TrendChart
          data={nplAllGroups}
          seriesLabels={BANK_TYPE_LABELS}
          title="NPL Ratio (%) — by group"
          yFormat="pct"
          decimals={2}
        />
        <TrendChart
          data={carGroups}
          seriesLabels={BANK_TYPE_LABELS}
          title="Capital Adequacy (%) — by group"
          yFormat="pct"
          decimals={1}
        />
        <TrendChart
          data={roeGroups}
          seriesLabels={BANK_TYPE_LABELS}
          title="ROE — Annualized (%) — by group"
          yFormat="pct"
          decimals={1}
          zeroLine
        />
      </div>
      </Section>
    </main>
  );
}
