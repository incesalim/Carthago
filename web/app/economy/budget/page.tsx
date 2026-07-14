/**
 * Central-Government Budget — reproduces the Albaraka "Bütçe Görünümü"
 * monthly report from TÜİK/Treasury budget series in EVDS: the annualised
 * balance & primary balance, the revenue and expenditure category mix
 * (this month vs a year ago), the revenue-growth trend, and the detail table.
 *
 * Data + derivations: app/lib/budget.ts (balance = revenues − expenditure,
 * primary = revenues − primary expenditure, non-tax = revenues − tax).
 *
 * "The Desk" (web/DESIGN.md): a computed brief (record line + vitals band)
 * above the full report, which is carried over intact under <Depth>.
 */
import type { Metadata } from "next";
import Link from "next/link";
import { getBudgetData, type TableRow as BudgetRow } from "@/app/lib/budget";
import {
  Section,
  Stat,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  TableCellNum,
  toneFor,
} from "@/app/components/ui";
import { direction } from "@/app/lib/prose";
import { GlobalRangeSelector } from "@/app/components/range-context";
import {
  Colophon,
  Depth,
  DeskHeader,
  SecHead,
  Vital,
  Vitals,
} from "@/app/components/desk";
import { monthLabel, signedPp } from "@/app/lib/desk";
import { nf } from "@/app/lib/chart-format";
import { ChartCard } from "@/app/components/ui/chart-card";
import TimeSeriesChart from "@/app/components/TimeSeriesChart";
import BopFlowChart, { type BarSeries } from "@/app/components/BopFlowChart";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkey Central Government Budget",
  description: "Türkiye's central-government budget — revenues, expenditures, balance and primary balance.",
  alternates: { canonical: "/economy/budget" },
};

const ORANGE = { light: "#e8833a", dark: "#f0a35e" };
const MAROON = { light: "#9c1f2f", dark: "#d65a5a" };

/** "−₺1,672 bn" / "₺791 bn". */
const bnTL = (v: number | null) => (v == null ? "—" : `${v < 0 ? "−" : ""}₺${nf(Math.abs(v), 0)} bn`);

/** "−1,672" / "791" — a bare mono figure for the vitals band (unit lives in `unit`). */
const nSigned = (v: number | null, d = 0) =>
  v == null ? "—" : `${v < 0 ? "−" : ""}${nf(Math.abs(v), d)}`;

/** "+₺214bn" / "−₺214bn" — a signed delta inside a computed note. */
const sTL = (v: number | null, d = 0) =>
  v == null ? "—" : `${v >= 0 ? "+" : "−"}₺${nf(Math.abs(v), d)}bn`;

/** {period_date,value} (chart shape) → {period,value} (sparkline shape). */
const sp = (pts: { period_date: string; value: number }[] | undefined) =>
  (pts ?? []).map((p) => ({ period: p.period_date, value: p.value }));

export default async function BudgetPage() {
  const d = await getBudgetData();

  // ---- the brief's computed vitals ------------------------------------------
  // The summary table carries [now monthly, now 12m, year-ago monthly,
  // year-ago 12m] in ₺ million for every line the page already fetches.
  const cells = (label: string) =>
    d.table.find((r) => r.label === label)?.cells ?? [null, null, null, null];
  const bn = (v: number | null) => (v == null ? null : v / 1e3); // ₺ mn → ₺ bn
  const yoy = (now: number | null, ago: number | null) =>
    now != null && ago != null && ago !== 0 ? (now / ago - 1) * 100 : null;

  const balMonthly = sp(d.s5["Budget balance"]);
  const balRoll = sp(d.s1["Budget balance"]);
  const primRoll = sp(d.s1["Primary balance"]);

  const recP = balMonthly.at(-1)?.period ?? null;
  const prevP = balMonthly.at(-2)?.period ?? null;

  const balNow = balMonthly.at(-1)?.value ?? null;
  const balMonthAgo = bn(cells("Budget balance")[2]); // same month, a year earlier
  const bal12mAgo = bn(cells("Budget balance")[3]);
  const balYoY = d.balance12m != null && bal12mAgo != null ? d.balance12m - bal12mAgo : null;

  const prim12mAgo = bn(cells("Primary balance")[3]);
  const primYoY = d.primary12m != null && prim12mAgo != null ? d.primary12m - prim12mAgo : null;

  const rev12 = bn(cells("Budget revenues")[1]);
  const rev12Ago = bn(cells("Budget revenues")[3]);
  const exp12 = bn(cells("Budget expenditures")[1]);
  const exp12Ago = bn(cells("Budget expenditures")[3]);
  const revYoY = yoy(rev12, rev12Ago);
  const expYoY = yoy(exp12, exp12Ago);
  const gap = revYoY != null && expYoY != null ? revYoY - expYoY : null;

  // The section read. "The headline deficit widened on softer tax intake while the
  // primary balance stays in surplus" — the two directions are `balYoY` and
  // `d.primary12m`, both computed right here. The causal attribution to tax intake
  // was never computed at all, so it is gone rather than dressed up.
  //
  // Note the vocabulary: for a DEFICIT, a falling balance is a WIDENING one.
  const balMove = direction(
    balYoY,
    d.balance12m != null && d.balance12m < 0
      ? { flat: "flat", up: "narrowing", down: "widening" }
      : { flat: "flat", up: "growing", down: "shrinking" },
    { flat: 50, sharp: Number.POSITIVE_INFINITY },
  );

  const int12 = bn(cells("Interest expenditure")[1]);
  const int12Ago = bn(cells("Interest expenditure")[3]);
  const intShare = int12 != null && rev12 != null && rev12 !== 0 ? (int12 / rev12) * 100 : null;
  const intShareAgo =
    int12Ago != null && rev12Ago != null && rev12Ago !== 0 ? (int12Ago / rev12Ago) * 100 : null;
  const intShareD = intShare != null && intShareAgo != null ? intShare - intShareAgo : null;

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title="Central Government Budget"
        record={
          <>
            Record <b className="font-normal text-foreground">{monthLabel(recP ?? d.latestPeriod)}</b>{" "}
            · vs {monthLabel(prevP, false)} · 12m rolling sums
          </>
        }
        right="every figure computed from source series"
      />

      {/* ── The vitals ─────────────────────────────────────────────────── */}
      <SecHead
        title="The vitals"
        meta="treasury central-govt · trailing-12-month sums, ₺bn"
        className="mb-2.5 mt-6"
      />
      <Vitals cols={5}>
        <Vital
          label="Budget balance · monthly"
          value={nSigned(balNow)}
          unit="₺bn"
          series={balMonthly.slice(-13)}
          format="raw"
          decimals={0}
          note={
            <>
              {monthLabel(recP, false)} alone · {nSigned(balMonthAgo)}₺bn in the same month a year
              earlier
            </>
          }
        />
        <Vital
          label="Budget balance · 12m"
          value={nSigned(d.balance12m)}
          unit="₺bn"
          series={balRoll.slice(-13)}
          format="raw"
          decimals={0}
          note={
            balYoY != null ? (
              <>
                <b className={balYoY >= 0 ? "font-semibold text-positive" : "font-semibold text-negative"}>
                  {sTL(balYoY)}
                </b>{" "}
                vs a year earlier ({bnTL(bal12mAgo)})
              </>
            ) : (
              "revenues − expenditure, trailing 12m"
            )
          }
        />
        <Vital
          label="Primary balance · 12m"
          value={nSigned(d.primary12m)}
          unit="₺bn"
          series={primRoll.slice(-13)}
          format="raw"
          decimals={0}
          note={
            <>
              ex-interest
              {int12 != null && <> · the {bnTL(int12)} interest bill sits between the two</>}
              {primYoY != null && (
                <>
                  {" · "}
                  <b className={primYoY >= 0 ? "font-semibold text-positive" : "font-semibold text-negative"}>
                    {sTL(primYoY)}
                  </b>{" "}
                  y/y
                </>
              )}
            </>
          }
        />
        <Vital
          label="Revenues, y/y · 12m"
          value={revYoY != null ? `${revYoY >= 0 ? "+" : "−"}${Math.abs(revYoY).toFixed(0)}` : "—"}
          unit="%"
          note={
            expYoY != null && gap != null ? (
              <>
                expenditure {expYoY >= 0 ? "+" : "−"}
                {Math.abs(expYoY).toFixed(0)}% ·{" "}
                <b className={gap >= 0 ? "font-semibold text-positive" : "font-semibold text-negative"}>
                  {signedPp(gap, 1)}
                </b>{" "}
                {gap >= 0 ? "revenue outruns spending" : "spending outruns revenue"}
              </>
            ) : (
              "12m sum vs the 12m sum a year earlier"
            )
          }
        />
        <Vital
          label="Interest burden"
          value={intShare != null ? intShare.toFixed(1) : "—"}
          unit="%"
          note={
            <>
              {bnTL(int12)} of interest on {bnTL(rev12)} of revenue
              {intShareD != null && (
                <>
                  {" · "}
                  <b className={intShareD <= 0 ? "font-semibold text-positive" : "font-semibold text-negative"}>
                    {signedPp(intShareD, 1)}
                  </b>{" "}
                  y/y
                </>
              )}{" "}
              <Link href="/economy" className="font-semibold text-primary">
                /economy
              </Link>
            </>
          }
        />
      </Vitals>

      <Depth action={<GlobalRangeSelector />}>
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

        {/* "The headline deficit widened on softer tax intake while the primary
            balance stays in surplus" — the two directions are in d.s1 below; the
            causal attribution to tax intake is not, so it is gone. */}
        <Section
          title="Budget Balance"
          description={
            d.balance12m != null && d.primary12m != null
              ? `Annualised (trailing-12-month) central-government balance. The headline balance is ${
                  d.balance12m < 0 ? "in deficit" : "in surplus"
                }${balMove ? ` and ${balMove}` : ""}; the primary balance is ${
                  d.primary12m >= 0 ? "in surplus" : "in deficit"
                }.`
              : "Annualised (trailing-12-month) central-government balance."
          }
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
      </Depth>

      <Colophon>
        Compiled, not written — every figure computed from the Treasury (Hazine ve Maliye
        Bakanlığı) central-government budget series via TCMB EVDS. Balance = revenues −
        expenditure; primary balance = revenues − primary expenditure; 12-month figures are
        trailing rolling sums. No forecasts. Analytical information, not investment advice.
      </Colophon>
    </main>
  );
}

function BudgetTable({ rows, now, prev }: { rows: BudgetRow[]; now: string; prev: string }) {
  return (
    <Table wrapperClassName="rounded-[10px] border border-border bg-card">
      <TableHeader>
        <TableRow className="bg-muted/50">
          <TableHead />
          <TableHead className="text-right" colSpan={2}>
            {now}
          </TableHead>
          <TableHead className="text-right" colSpan={2}>
            {prev}
          </TableHead>
        </TableRow>
        <TableRow>
          <TableHead>₺ million</TableHead>
          <TableHead className="text-right">Monthly</TableHead>
          <TableHead className="text-right">12-month</TableHead>
          <TableHead className="text-right">Monthly</TableHead>
          <TableHead className="text-right">12-month</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((r) => {
          const strong = r.label === "Budget balance" || r.label === "Primary balance";
          return (
            <TableRow key={r.label} className={strong ? "bg-accent/30 font-semibold" : undefined}>
              <TableCell className={`py-1.5 ${r.indent ? "pl-6 text-muted-foreground" : ""}`}>
                {r.label}
              </TableCell>
              {r.cells.map((v, i) => (
                <TableCellNum key={i} tone={toneFor(v)} className="py-1.5">
                  {v == null ? "—" : nf(v, 0)}
                </TableCellNum>
              ))}
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
