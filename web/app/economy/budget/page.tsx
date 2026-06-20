/**
 * Central-Government Budget — reproduces the Albaraka "Bütçe Görünümü"
 * monthly report from TÜİK/Treasury budget series in EVDS: the annualised
 * balance & primary balance, the revenue and expenditure category mix
 * (this month vs a year ago), the revenue-growth trend, and the detail table.
 *
 * Data + derivations: app/lib/budget.ts (balance = revenues − expenditure,
 * primary = revenues − primary expenditure, non-tax = revenues − tax).
 */
import Link from "next/link";
import { getBudgetData, type TableRow } from "@/app/lib/budget";
import { PageHeader, Section, Stat } from "@/app/components/ui";
import { ChartCard } from "@/app/components/ui/chart-card";
import TimeSeriesChart from "@/app/components/TimeSeriesChart";
import BopFlowChart, { type BarSeries } from "@/app/components/BopFlowChart";

export const dynamic = "force-dynamic";

const ORANGE = { light: "#e8833a", dark: "#f0a35e" };
const MAROON = { light: "#9c1f2f", dark: "#d65a5a" };

const nf0 = (v: number) => new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(v);

/** "−₺1,672 bn" / "₺791 bn". */
const bnTL = (v: number | null) => (v == null ? "—" : `${v < 0 ? "−" : ""}₺${nf0(Math.abs(v))} bn`);

export default async function BudgetPage() {
  const d = await getBudgetData();

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      <PageHeader
        title="Central Government Budget"
        description="Treasury (Hazine ve Maliye Bakanlığı) central-government budget: the annualised balance, revenue & expenditure mix, and the monthly detail. Values in ₺ bn unless noted."
        rangeSelector
        dataThrough={d.latestPeriod}
      >
        <Link
          href="/economy"
          className="rounded-md border border-border px-2.5 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-accent"
        >
          ← Economy
        </Link>
      </PageHeader>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Stat
          label="Budget balance · 12-month"
          value={bnTL(d.balance12m)}
          hint={`annualised · ${d.asOfLabel}`}
          tone={d.balance12m != null && d.balance12m < 0 ? "negative" : "positive"}
        />
        <Stat
          label="Primary balance · 12-month"
          value={bnTL(d.primary12m)}
          hint={`annualised · ${d.asOfLabel}`}
          tone={d.primary12m != null && d.primary12m < 0 ? "negative" : "positive"}
        />
        <Stat
          label="Tax revenue · 12-month"
          value={bnTL(d.tax12m)}
          hint={`annualised · ${d.asOfLabel}`}
        />
      </div>

      <Section
        title="Budget Balance"
        description="Annualised (trailing-12-month) central-government balance. The headline deficit widened on softer tax intake while the primary balance stays in surplus."
      >
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TimeSeriesChart
            series={d.s1}
            title="Şekil 1 · Budget & Primary Balance (12m rolling, ₺ bn)"
            yFormat="raw"
            decimals={0}
          />
          <TimeSeriesChart
            series={d.s5}
            title="Şekil 5 · Monthly Budget Balance (₺ bn)"
            yFormat="raw"
            decimals={0}
          />
        </div>
      </Section>

      <Section
        title="Revenues"
        description={`Tax-revenue growth has slipped below headline inflation. Tax lines compared ${d.barLabels.now} vs ${d.barLabels.prev}.`}
      >
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TimeSeriesChart
            series={d.s4}
            title="Şekil 4 · Revenue Growth (y/y %, 3-month moving average)"
            yFormat="pct"
            decimals={0}
          />
          <ChartCard title={`Şekil 3 · Tax Revenues by Type (₺ bn, ${d.barLabels.now} vs ${d.barLabels.prev})`}>
            <BopFlowChart
              data={d.s3}
              grouped
              bars={[
                { key: "prev", label: d.barLabels.prev, fill: ORANGE },
                { key: "now", label: d.barLabels.now, fill: MAROON },
              ] satisfies BarSeries[]}
              unit=" bn"
            />
          </ChartCard>
        </div>
      </Section>

      <Section
        title="Expenditures"
        description={`Current transfers and personnel dominate spending. Expenditure lines compared ${d.barLabels.now} vs ${d.barLabels.prev}.`}
      >
        <ChartCard title={`Şekil 2 · Expenditures by Type (₺ bn, ${d.barLabels.now} vs ${d.barLabels.prev})`}>
          <BopFlowChart
            data={d.s2}
            grouped
            bars={[
              { key: "prev", label: d.barLabels.prev, fill: ORANGE },
              { key: "now", label: d.barLabels.now, fill: MAROON },
            ] satisfies BarSeries[]}
            unit=" bn"
            height={340}
          />
        </ChartCard>
      </Section>

      <Section
        title="Summary"
        description={`Monthly and trailing-12-month figures, ₺ million — ${d.asOfLabel} vs. one year earlier.`}
      >
        <BudgetTable rows={d.table} now={d.barLabels.now} prev={d.barLabels.prev} />
        <p className="text-xs text-muted-foreground">
          Source: TÜİK / Treasury (Hazine ve Maliye Bakanlığı) central-government
          budget via EVDS.{" "}
          <Link href="/economy/balance-of-payments" className="text-primary hover:underline">
            Balance of Payments →
          </Link>
        </p>
      </Section>
    </main>
  );
}

function BudgetTable({ rows, now, prev }: { rows: TableRow[]; now: string; prev: string }) {
  const nf = (v: number | null) =>
    v == null ? "—" : new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(v);
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-accent/40 text-left">
            <th className="px-3 py-2 font-medium text-muted-foreground" />
            <th className="px-3 py-2 text-right font-medium text-muted-foreground" colSpan={2}>
              {now}
            </th>
            <th className="px-3 py-2 text-right font-medium text-muted-foreground" colSpan={2}>
              {prev}
            </th>
          </tr>
          <tr className="border-b border-border text-left text-xs text-muted-foreground">
            <th className="px-3 py-1.5 font-medium">₺ million</th>
            <th className="px-3 py-1.5 text-right font-medium">Monthly</th>
            <th className="px-3 py-1.5 text-right font-medium">12-month</th>
            <th className="px-3 py-1.5 text-right font-medium">Monthly</th>
            <th className="px-3 py-1.5 text-right font-medium">12-month</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const strong = r.label === "Budget balance" || r.label === "Primary balance";
            return (
              <tr
                key={r.label}
                className={`border-b border-border/60 last:border-0 ${strong ? "bg-accent/30 font-semibold" : ""}`}
              >
                <td className={`px-3 py-1.5 text-foreground ${r.indent ? "pl-6 text-muted-foreground" : ""}`}>
                  {r.label}
                </td>
                {r.cells.map((v, i) => (
                  <td
                    key={i}
                    className={`px-3 py-1.5 text-right tabular-nums ${
                      v == null ? "text-muted-foreground" : v < 0 ? "text-negative" : "text-foreground"
                    }`}
                  >
                    {nf(v)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
