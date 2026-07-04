/**
 * Home / Overview tab.
 *
 * Sector-level KPI cards + bar chart of loan growth by bank type +
 * trend chart of NPL across groups + total-assets time series, plus the
 * by-bank-type Table-15 scorecard (formerly the standalone /sector/ratios page)
 * folded in as a `?type=`-driven section.
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
import type { TimeSeriesRow } from "@/app/lib/metrics";

export const dynamic = "force-dynamic";

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
    assets, assetsYoY, loansYoY, depositsYoY, npl, car, ldr, roe,
    loansYoYGroups, nplAllGroups, carGroups, roeGroups,
    btAssets, btNpl, btNim, btLdr, btRoa, btRoe,
  ] = await Promise.all([
    totalAssets(sector),
    totalAssetsYoY(sector),
    totalLoansYoY(sector),
    totalDepositsYoY(sector),
    ratioNpl(sector),
    ratioCar(sector),
    ratioLdr(sector),
    ratioRoe(sector),
    // By-group trends for the chart grid — one per CAMELS vital.
    totalLoansYoY(PRIMARY_BANK_TYPES),
    ratioNpl(PRIMARY_BANK_TYPES),
    ratioCar(PRIMARY_BANK_TYPES),
    ratioRoe(PRIMARY_BANK_TYPES),
    // Table-15 scorecard for the selected bank type (defaults to sector).
    totalAssets(bt),
    ratioNpl(bt),
    ratioNim(bt),
    ratioLdr(bt),
    ratioRoa(bt),
    ratioRoe(bt),
  ]);

  const a = assets.at(-1);
  const ay = assetsYoY.at(-1);
  const ly = loansYoY.at(-1);
  const dy = depositsYoY.at(-1);
  const n = npl.at(-1);
  const c = car.at(-1);
  const l = ldr.at(-1);
  const r = roe.at(-1);

  // Latest point of each Table-15 scorecard series (selected bank type).
  const bta = btAssets.at(-1);
  const btn = btNpl.at(-1);
  const btm = btNim.at(-1);
  const btl = btLdr.at(-1);
  const btra = btRoa.at(-1);
  const btre = btRoe.at(-1);

  // Deterministic "Sector Pulse" — computed live from the same series the cards
  // show, so the lead can never drift from the numbers below it.
  const pulse = overviewInsights({
    assetsYoY, loansYoY, depositsYoY, npl, car, ldr, roe,
  });

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      <PageHeader
        eyebrow="Banking Sector"
        title="Overview"
        description="BDDK monthly bulletin · sector aggregate · live D1 query"
        rangeSelector
        dataThrough={latestPeriod(assets, npl, car, roe)}
      />

      <Takeaway data={pulse} />

      <Section
        index="01"
        title="Snapshot"
        description="the aggregate that 32 banks roll up to · 18-month trend"
      >
      {/* Top row — size + growth */}
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

      {/* Quality + capital + returns */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KpiCard label="NPL Ratio" value={fmtPct(n?.value)} period={n?.period ?? "—"}
                 series={npl} format="pct" decimals={2} goodDirection="down" />
        <KpiCard label="Capital Adequacy" value={fmtPct(c?.value, 1)} period={c?.period ?? "—"}
                 hint="SYR · regulatory min 12%" series={car} format="pct" decimals={1} />
        <KpiCard label="Loan / Deposit" value={fmtPct(l?.value, 1)} period={l?.period ?? "—"}
                 series={ldr} format="pct" decimals={1} goodDirection="neutral" />
        <KpiCard label="ROE (annualized)" value={fmtPct(r?.value, 1)} period={r?.period ?? "—"}
                 series={roe} format="pct" decimals={1} />
      </div>

      </Section>

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
          title="Loan Growth YoY (%) — by group"
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

      {/* The by-bank-type Table-15 scorecard — folded in from the retired
          /sector/ratios page. The filter drives ONLY this section (Snapshot +
          Pulse above stay sector-aggregate); it's the one surface where the
          deposit / participation / development-investment groups are compared
          on the regulator's own ratios. */}
      <div id="by-type" className="scroll-mt-24">
      <Section
        index="03"
        title="Ratios by bank type"
        description="the official BDDK Table-15 scorecard · deposit, participation and development-investment groups on the regulator's own ratios · queried live from D1"
        actions={<BankTypeFilter active={bankType} />}
      >
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
        <KpiCard label="Total Assets" value={fmtTrn(bta?.value)} period={bta?.period ?? "—"}
                 series={btAssets} format="trn" decimals={2} />
        <KpiCard label="NPL Ratio" value={fmtPct(btn?.value)} period={btn?.period ?? "—"}
                 hint="Takipteki / Toplam Krediler" series={btNpl} format="pct" decimals={2} goodDirection="down" />
        <KpiCard label="Net Interest Margin" value={fmtPct(btm?.value)} period={btm?.period ?? "—"}
                 hint="annualized · NII / avg assets" series={btNim} format="pct" decimals={2} />
        <KpiCard label="Loan / Deposit" value={fmtPct(btl?.value, 1)} period={btl?.period ?? "—"}
                 series={btLdr} format="pct" decimals={1} goodDirection="neutral" />
        <KpiCard label="ROA" value={fmtPct(btra?.value)} period={btra?.period ?? "—"}
                 hint="annualized" series={btRoa} format="pct" decimals={2} />
        <KpiCard label="ROE" value={fmtPct(btre?.value, 1)} period={btre?.period ?? "—"}
                 hint="annualized" series={btRoe} format="pct" decimals={1} />
      </div>
      </Section>
      </div>
    </main>
  );
}
