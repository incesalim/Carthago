/**
 * Funds tab — TEFAS fund-market sector statistics: total AUM by fund type,
 * the money-market/hedge fund boom, AUM-weighted portfolio allocation,
 * investor counts and the largest funds. Source: tefas.gov.tr daily fund
 * data, aggregated at ingest — see scripts/update_tefas.py.
 *
 * Time series sample the month-end trading day. GYF (real-estate) and GSYF
 * (venture-capital) funds are excluded from trends — they aren't daily-priced,
 * so daily sums would undercount — but appear in the largest-funds table.
 * Investor counts double-count people holding several funds.
 */
import {
  monthlyByType,
  aumStack,
  typeTrend,
  categoryStack,
  allocationStack,
  realAumIndex,
  topFunds,
  TREND_TYPES,
  TYPE_LABELS,
  CATEGORY_SERIES,
  ALLOCATION_SERIES,
  AUM_INDEX_LABELS,
  type TopFundRow,
} from "@/app/lib/funds";
import { latestPeriod } from "@/app/lib/metrics";
import {
  PageHeader,
  Section,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/app/components/ui";
import TrendChart from "@/app/components/TrendChart";
import StackedArea from "@/app/components/StackedArea";
import CopyTableButton from "@/app/components/CopyTableButton";

export const dynamic = "force-dynamic";

const nf0 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

function TopFundsTable({ rows, label }: { rows: TopFundRow[]; label: string }) {
  if (rows.length === 0) return null;
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-foreground">
          {label}{" "}
          <span className="font-normal text-muted-foreground">({rows[0].date})</span>
        </h3>
        <CopyTableButton />
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-10">#</TableHead>
            <TableHead className="w-16">Code</TableHead>
            <TableHead>Fund</TableHead>
            <TableHead>Manager</TableHead>
            <TableHead className="text-right">AUM (₺ bn)</TableHead>
            <TableHead className="text-right">Investors</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r.fon_kodu}>
              <TableCell className="text-muted-foreground">{r.rank}</TableCell>
              <TableCell className="font-medium">{r.fon_kodu}</TableCell>
              <TableCell
                className="max-w-[28rem] truncate text-muted-foreground"
                title={r.fon_unvan ?? ""}
              >
                {r.fon_unvan}
              </TableCell>
              <TableCell className="whitespace-nowrap">{r.manager}</TableCell>
              <TableCell className="text-right tabular-nums">
                {r.aum_bn == null ? "—" : nf1.format(r.aum_bn)}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {r.investor_count == null ? "—" : nf0.format(r.investor_count)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export default async function FundsPage() {
  const monthly = await monthlyByType();
  const [categories, allocation, aumIndex, top] = await Promise.all([
    categoryStack("YAT"),
    allocationStack("YAT"),
    realAumIndex(monthly),
    topFunds(),
  ]);

  const typeSeries = TREND_TYPES.map((t) => ({ key: t, label: TYPE_LABELS[t] }));
  const investorTrend = typeTrend(monthly, "investors", 1 / 1e6);
  const fundCountTrend = typeTrend(monthly, "funds");

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      <PageHeader
        eyebrow="TEFAS — Turkey Electronic Fund Trading Platform"
        title="Funds"
        description="Sector-wide fund-market statistics: assets under management, fund categories, portfolio allocation and investor counts across mutual, pension and exchange-traded funds."
        rangeSelector
        dataThrough={latestPeriod(monthly)}
      />

      <Section
        title="Fund market size"
        description="Month-end AUM. Real-estate (GYF) and venture-capital (GSYF) funds are excluded from trends — they aren't priced daily."
      >
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <StackedArea
            data={aumStack(monthly)}
            series={typeSeries}
            title="Assets under management by fund type (₺ trillion)"
            yFormat="raw"
            decimals={2}
          />
          <TrendChart
            data={aumIndex}
            seriesLabels={AUM_INDEX_LABELS}
            title="Total AUM, nominal vs CPI-deflated (index = 100 at start)"
            yFormat="raw"
            decimals={0}
          />
        </div>
      </Section>

      <Section
        title="Where mutual-fund money went"
        description="Mutual-fund (YAT) AUM by fund category, from fund names. Money-market and hedge (serbest) funds absorbed the deposit migration of recent years."
      >
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <StackedArea
            data={categories}
            series={[...CATEGORY_SERIES]}
            title="Mutual-fund AUM by category (₺ trillion)"
            yFormat="raw"
            decimals={2}
          />
          <StackedArea
            data={categories}
            series={[...CATEGORY_SERIES]}
            title="Mutual-fund AUM by category (% of total)"
            percentStack
            decimals={1}
          />
        </div>
      </Section>

      <Section
        title="What mutual funds hold"
        description="AUM-weighted portfolio allocation of mutual funds (YAT), rolled up from TEFAS's ~55 instrument fields. Deposits, repo and money-market instruments dominate."
      >
        <StackedArea
          data={allocation}
          series={[...ALLOCATION_SERIES]}
          title="Mutual-fund portfolio allocation (% of covered AUM)"
          percentStack
          decimals={1}
          height={360}
        />
      </Section>

      <Section
        title="Investors"
        description="Investor accounts per fund type (people holding several funds are counted once per fund) and the number of priced funds."
      >
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TrendChart
            data={investorTrend}
            seriesLabels={TYPE_LABELS}
            title="Investor accounts (millions)"
            yFormat="raw"
            decimals={1}
          />
          <TrendChart
            data={fundCountTrend}
            seriesLabels={TYPE_LABELS}
            title="Funds priced at month-end (count)"
            yFormat="raw"
            decimals={0}
          />
        </div>
      </Section>

      <Section
        title="Largest funds"
        description="Top funds by AUM on the latest trading day."
      >
        <div className="space-y-6">
          <TopFundsTable
            rows={top.filter((r) => r.fon_tipi === "YAT")}
            label="Mutual funds (YAT)"
          />
          <TopFundsTable
            rows={top.filter((r) => r.fon_tipi === "EMK")}
            label="Pension funds (EMK)"
          />
          <TopFundsTable
            rows={top.filter((r) => r.fon_tipi === "BYF")}
            label="ETFs (BYF)"
          />
        </div>
      </Section>
    </main>
  );
}
