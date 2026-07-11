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
import type { Metadata } from "next";
import Link from "next/link";
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
import {
  Section,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/app/components/ui";
import {
  ChartRow,
  Colophon,
  Depth,
  DeskHeader,
  SecHead,
  Vital,
  Vitals,
} from "@/app/components/desk";
import { lastVal, monthLabel, signedPp, valAgo, type Pt } from "@/app/lib/desk";
import { GlobalRangeSelector } from "@/app/components/range-context";
import TrendChart from "@/app/components/TrendChart";
import StackedArea from "@/app/components/StackedArea";
import type { StackPoint } from "@/app/components/StackedArea";
import CopyTableButton from "@/app/components/CopyTableButton";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkish Investment Funds (TEFAS)",
  description: "Turkish mutual and investment funds from TEFAS — assets under management, flows and allocation by fund type.",
  alternates: { canonical: "/funds" },
};

const nf0 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

/** Sum one field of the monthly per-type rows across fund types → Pt series. */
function sumField(
  rows: Array<{ period: string; aum_try: number | null; investors: number | null; funds: number | null }>,
  field: "aum_try" | "investors" | "funds",
  scale = 1,
): Pt[] {
  const totals = new Map<string, number>();
  for (const r of rows) {
    const v = r[field];
    if (v == null) continue;
    totals.set(r.period, (totals.get(r.period) ?? 0) + v * scale);
  }
  return [...totals.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([period, value]) => ({ period, value }));
}

/** One stack key as a % of the sum of `keys`, per period → Pt series. */
function stackShare(rows: StackPoint[], key: string, keys: readonly string[]): Pt[] {
  const out: Pt[] = [];
  for (const r of rows) {
    const total = keys.reduce((s, k) => s + (Number(r[k]) || 0), 0);
    if (total > 0) out.push({ period: String(r.period), value: (100 * (Number(r[key]) || 0)) / total });
  }
  return out;
}

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

  // ---- the brief's computed vitals -----------------------------------------
  // Total AUM (₺ trn) per month across YAT+EMK+BYF, investor accounts (m) and
  // priced-fund counts — all summed from the same rows the charts render.
  const aumTotals = sumField(monthly, "aum_try", 1 / 1e12);
  const investorTotals = sumField(monthly, "investors", 1 / 1e6);
  const fundTotals = sumField(monthly, "funds");

  const aumNow = lastVal(aumTotals);
  const aumAgo = valAgo(aumTotals, 12);
  const aumYoY = aumNow != null && aumAgo != null && aumAgo > 0 ? (aumNow / aumAgo - 1) * 100 : null;

  const realIdx = aumIndex.filter((r) => r.bank_type_code === "real");
  const realNow = lastVal(realIdx);
  const realAgo = valAgo(realIdx, 12);
  const realYoY = realNow != null && realAgo != null && realAgo > 0 ? (realNow / realAgo - 1) * 100 : null;

  const CAT_KEYS = CATEGORY_SERIES.map((s) => s.key);
  const mmShare = stackShare(categories, "money_market", CAT_KEYS);
  const mmNow = lastVal(mmShare);
  const mmAgo = valAgo(mmShare, 12);
  const mmDelta = mmNow != null && mmAgo != null ? mmNow - mmAgo : null;

  const ALLOC_KEYS = ALLOCATION_SERIES.map((s) => s.key);
  const depositLike = stackShare(allocation, "money_market", ALLOC_KEYS);
  const depNow = lastVal(depositLike);
  const depAgo = valAgo(depositLike, 12);
  const depDelta = depNow != null && depAgo != null ? depNow - depAgo : null;

  const invNow = lastVal(investorTotals);
  const invAgo = valAgo(investorTotals, 12);
  const invYoY = invNow != null && invAgo != null && invAgo > 0 ? (invNow / invAgo - 1) * 100 : null;

  const fundNow = lastVal(fundTotals);
  const fundAgo = valAgo(fundTotals, 12);
  const fundDelta = fundNow != null && fundAgo != null ? fundNow - fundAgo : null;

  // Long-form allocation rows for the ChartRow rail — normalised to the same
  // %-of-covered-AUM basis the percent-stacked chart shows.
  const allocationLong = allocation.flatMap((r) => {
    const total = ALLOC_KEYS.reduce((s, k) => s + (Number(r[k]) || 0), 0);
    if (total <= 0) return [];
    return ALLOCATION_SERIES.map((s) => ({
      period: String(r.period),
      bank_type_code: s.key,
      value: (100 * (Number(r[s.key]) || 0)) / total,
    }));
  });
  const ALLOC_LABELS = Object.fromEntries(ALLOCATION_SERIES.map((s) => [s.key, s.label]));

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title="Funds"
        record={
          <>
            Record <b className="font-normal text-foreground">{monthLabel(aumTotals.at(-1)?.period)}</b> · vs{" "}
            {monthLabel(aumTotals.at(-2)?.period, false)} · TEFAS daily, month-end sampled
          </>
        }
        right="every figure computed from source series"
      />

      <SecHead
        title="The vitals"
        meta="month-end sample · YAT + EMK + BYF · GYF/GSYF excluded"
        className="mb-2.5 mt-6"
      />
      <Vitals cols={6}>
        <Vital
          label="Total AUM"
          value={aumNow != null ? aumNow.toFixed(2) : "—"}
          unit="₺trn"
          series={aumTotals.slice(-13)}
          format="raw"
          decimals={2}
          note={
            aumYoY != null ? (
              <>
                +{aumYoY.toFixed(0)}% y/y nominal — the deposit-substitution channel{" "}
                <Link href="/deposits" className="font-semibold text-primary">/deposits</Link>
              </>
            ) : (
              "mutual + pension + ETF"
            )
          }
        />
        <Vital
          label="Real AUM, y/y"
          value={realYoY != null ? `${realYoY >= 0 ? "+" : ""}${realYoY.toFixed(1)}` : "—"}
          unit="%"
          series={realIdx.slice(-13)}
          format="raw"
          decimals={0}
          note={
            realYoY != null
              ? `CPI-deflated — ${realYoY >= 0 ? "growing" : "shrinking"} in real terms`
              : "CPI-deflated 12-month change"
          }
        />
        <Vital
          label="Money-market share"
          value={mmNow != null ? mmNow.toFixed(1) : "—"}
          unit="%"
          series={mmShare.slice(-13)}
          decimals={1}
          note={
            mmDelta != null
              ? `${signedPp(mmDelta, 1)} over 12m — of mutual-fund AUM`
              : "of mutual-fund (YAT) AUM"
          }
        />
        <Vital
          label="Deposit-like holdings"
          value={depNow != null ? depNow.toFixed(1) : "—"}
          unit="%"
          series={depositLike.slice(-13)}
          decimals={1}
          note={
            depDelta != null
              ? `${signedPp(depDelta, 1)} over 12m — deposits, repo & money market in YAT portfolios`
              : "deposits, repo & money market in YAT portfolios"
          }
        />
        <Vital
          label="Investor accounts"
          value={invNow != null ? invNow.toFixed(1) : "—"}
          unit="m"
          series={investorTotals.slice(-13)}
          format="raw"
          decimals={1}
          note={
            invYoY != null
              ? `${invYoY >= 0 ? "+" : ""}${invYoY.toFixed(1)}% y/y — counted once per fund held`
              : "counted once per fund held"
          }
        />
        <Vital
          label="Funds priced"
          value={fundNow != null ? nf0.format(fundNow) : "—"}
          series={fundTotals.slice(-13)}
          format="raw"
          decimals={0}
          note={
            fundDelta != null
              ? `${fundDelta >= 0 ? "+" : "−"}${nf0.format(Math.abs(fundDelta))} funds over 12m`
              : "priced at month-end"
          }
        />
      </Vitals>

      <Depth action={<GlobalRangeSelector />}>
        <Section
          index="01"
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
          index="02"
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
          index="03"
          title="What mutual funds hold"
          description="AUM-weighted portfolio allocation of mutual funds (YAT), rolled up from TEFAS's ~55 instrument fields. Deposits, repo and money-market instruments dominate."
        >
          <ChartRow
            data={allocationLong}
            labels={ALLOC_LABELS}
            deltaPeriods={12}
            deltaLabel="12m"
            fmt={(v) => `${v.toFixed(1)}%`}
          >
            <StackedArea
              data={allocation}
              series={[...ALLOCATION_SERIES]}
              title="Mutual-fund portfolio allocation (% of covered AUM)"
              percentStack
              decimals={1}
              height={360}
            />
          </ChartRow>
        </Section>

        <Section
          index="04"
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
          index="05"
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
      </Depth>

      <Colophon>
        Compiled, not written — every figure computed from TEFAS daily fund data,
        month-end sampled · CPI deflator: TÜİK via EVDS · GYF/GSYF excluded from
        trends. No forecasts. Analytical information, not investment advice.
      </Colophon>
    </main>
  );
}
