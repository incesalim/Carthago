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
import { localizeMetadata } from "@/i18n/metadata";
import { useText } from "@/i18n/use-text";
import { getText } from "@/i18n/server";
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
  Flags,
  Movers,
  SecHead,
  Transmission,
  Vital,
  Vitals,
  type Flag,
  type MoverRow,
  type TransmissionItem,
} from "@/app/components/desk";
import { lastVal, monthLabel, signedPp, valAgo, type Pt } from "@/app/lib/desk";
import { seriesFinding } from "@/app/lib/chart-findings";
import { budgetInsights } from "@/app/lib/insights";
import Takeaway from "@/app/components/Takeaway";
import { nf } from "@/app/lib/chart-format";
import { ChartCard } from "@/app/components/ui/chart-card";
import TimeSeriesChart from "@/app/components/TimeSeriesChart";
import BopFlowChart, { type BarSeries } from "@/app/components/BopFlowChart";

export const dynamic = "force-dynamic";

const pageMetadata: Metadata = {
  title: "Turkey Central Government Budget",
  description: "Türkiye's central-government budget — revenues, expenditures, balance and primary balance.",
  alternates: { canonical: "/economy/budget" },
};

export async function generateMetadata(): Promise<Metadata> {
  return localizeMetadata(pageMetadata);
}

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
  const tx = await getText();
  const d = await getBudgetData();

  // ---- the brief's computed vitals ------------------------------------------
  // The summary table carries [now monthly, now 12m, year-ago monthly,
  // year-ago 12m] in ₺ million for every line the page already fetches.
  const cells = (label: string) =>
    d.table.find((r) => r.label === label)?.cells ?? [null, null, null, null];
  const bn = (v: number | null) => (v == null ? null : v / 1e3); // ₺ mn → ₺ bn

  /** EVDS rows ({period_date}) → the desk helpers' Pt shape ({period}). */
  const toPts = (s: { period_date: string; value: number }[] | undefined): Pt[] =>
    (s ?? []).map((r) => ({ period: r.period_date, value: r.value }));
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

  // ---- "The Read" — computed from the same series the charts show ----------
  const taxReal = toPts(d.real["Tax revenues (real y/y)"]);
  const expReal = toPts(d.real["Primary expenditure (real y/y)"]);
  const intReal = toPts(d.real["Interest expenditure (real y/y)"]);
  const balGdp = toPts(d.pctGdp["Budget balance"]);
  const primGdp = toPts(d.pctGdp["Primary balance"]);
  const intShareS = toPts(d.interestShare);

  const read = budgetInsights({
    balancePctGdp: balGdp,
    primaryPctGdp: primGdp,
    taxRealYoY: taxReal,
    expRealYoY: expReal,
    interestShare: intShareS,
  }, tx.locale);

  // ---- movers: REAL growth, not nominal ------------------------------------
  // A nominal Movers table here would say every line grew every month at a ~30%
  // price level — true, uninformative, and the opposite of the real direction
  // about as often as not. All four rows are CPI-deflated y/y on the same
  // monthly release.
  const realMover = (label: string, s: Pt[], good: MoverRow["good"] = "up"): MoverRow => ({
    label,
    prev: valAgo(s, 1),
    curr: lastVal(s),
    good,
    fmt: (v: number) => `${v.toFixed(1)}%`,
    deltaDecimals: 1,
  });
  const movers: MoverRow[] = [
    realMover("Tax revenues, real", taxReal),
    realMover("Primary expenditure, real", expReal, "down"),
    realMover("Interest expenditure, real", intReal, "down"),
    realMover("Budget balance, % GDP", balGdp),
    realMover("Primary balance, % GDP", primGdp),
    realMover("Interest / tax revenue", intShareS, "down"),
  ];

  // ---- transmission: the fiscal stance → the banks --------------------------
  const transmission: TransmissionItem[] = [
    {
      k: "Budget balance, 12m",
      v: d.balancePctGdpNow != null ? `${d.balancePctGdpNow.toFixed(1)}%` : "—",
      effect: (
        <>{tx("Of GDP. The deficit is funded by issuance the banks buy, so the fiscal stance sets how much government paper the sector carries — and how much of its balance sheet is not lending.")}</>
      ),
    },
    {
      k: "Interest / tax revenue",
      v: d.interestShareNow != null ? `${d.interestShareNow.toFixed(1)}%` : "—",
      effect: (
        <>{tx("Debt service as a claim on the tax take. It is also the sector’s interest income on government paper — the same flow, seen from the other side of the balance sheet.")}</>
      ),
    },
    {
      k: "Tax revenue, real y/y",
      v: d.taxRealYoYNow != null ? `${d.taxRealYoYNow.toFixed(1)}%` : "—",
      effect: (
        <>{tx("CPI-deflated. Consumption taxes (VAT, ÖTV) move with the same household demand that drives")}{" "}
          <Link href="/credit" className="font-semibold text-primary">{tx("retail credit")}</Link>{tx(", so real tax intake is a demand signal as well as a fiscal one.")}</>
      ),
    },
    {
      k: "Primary balance, 12m",
      v: d.primaryPctGdpNow != null ? `${d.primaryPctGdpNow.toFixed(1)}%` : "—",
      effect: (
        <>{tx("Of GDP, before interest. This is the number that says whether the debt path is stabilising on policy or on the rate cycle — the part of the budget the government still controls.")}</>
      ),
    },
  ];

  // ---- flags ----------------------------------------------------------------
  const taxRealNow = d.taxRealYoYNow;
  const expRealNow = lastVal(expReal);
  const flagList: Flag[] = [
    {
      code: "DEFICIT_3PCT",
      active: d.balancePctGdpNow != null && d.balancePctGdpNow < -3,
      rule: "budget_balance_12m / gdp < −3%",
      body: (
        <>
          <b className="font-semibold">{tx("The deficit is past the 3% reference value.")}</b>{" "}{tx("The 12-month central-government balance is")}{" "}
          {tx(d.balancePctGdpNow?.toFixed(1))}{tx("% of GDP, with the primary balance at")}{" "}
          {tx(d.primaryPctGdpNow?.toFixed(1))}%.
        </>
      ),
      clear: (
        <>{tx("The 12-month balance is")}{" "}
          {tx(d.balancePctGdpNow != null ? `${d.balancePctGdpNow.toFixed(1)}%` : "—")}{tx(" of GDP — inside the 3% reference value.")}</>
      ),
    },
    {
      code: "TAX_REAL_NEG",
      active: taxRealNow != null && taxRealNow < 0,
      rule: "tax_revenue_yoy_real < 0",
      body: (
        <>
          <b className="font-semibold">{tx("Tax revenue is shrinking in real terms.")}</b>{" "}
          {tx(taxRealNow?.toFixed(1))}{tx("% y/y once CPI is taken out — the nominal line grows and the purchasing power behind it does not.")}</>
      ),
      clear: (
        <>{tx("Real tax revenue is ")}{tx(taxRealNow != null ? `${taxRealNow.toFixed(1)}%` : "—")}{tx(" y/y — at or above zero in CPI-deflated terms.")}</>
      ),
    },
    {
      code: "SPEND_OUTPACES",
      active: taxRealNow != null && expRealNow != null && expRealNow > taxRealNow,
      rule: "primary_expenditure_yoy_real > tax_revenue_yoy_real",
      body: (
        <>
          <b className="font-semibold">{tx("Real spending outpaces real revenue.")}</b>{tx(" Primary expenditure at ")}{tx(expRealNow?.toFixed(1))}{tx("% against tax revenue at")}{" "}
          {tx(taxRealNow?.toFixed(1))}{tx("%, both CPI-deflated — the gap the primary balance absorbs.")}</>
      ),
      clear: (
        <>{tx("Real primary spending (")}{tx(expRealNow != null ? `${expRealNow.toFixed(1)}%` : "—")}{tx(") is at or below real tax growth (")}{tx(taxRealNow != null ? `${taxRealNow.toFixed(1)}%` : "—")}).
        </>
      ),
    },
    {
      code: "INTEREST_HEAVY",
      active: d.interestShareNow != null && d.interestShareNow > 25,
      rule: "interest_expenditure_12m / tax_revenue_12m > 25%",
      body: (
        <>
          <b className="font-semibold">{tx("Debt service takes more than a quarter of taxes.")}</b>{" "}{tx("Interest absorbs ")}{tx(d.interestShareNow?.toFixed(1))}{tx("% of the 12-month tax take before any spending decision is made.")}</>
      ),
      clear: (
        <>{tx("Interest takes")}{" "}
          {tx(d.interestShareNow != null ? `${d.interestShareNow.toFixed(1)}%` : "—")}{tx(" of tax revenue — inside the 25% line.")}</>
      ),
    },
  ];

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title={tx("Central Government Budget")}
        record={
          <>{tx("Record ")}<b className="font-normal text-foreground">{tx(monthLabel(recP ?? d.latestPeriod))}</b>{" "}{tx("· vs ")}{tx(monthLabel(prevP, false))}{tx(" · 12m rolling sums")}</>
        }
        right="every figure computed from source series"
      />

      {/* ── The vitals ─────────────────────────────────────────────────── */}
      <SecHead
        title={tx("The vitals")}
        meta={tx("treasury central-govt · trailing-12-month sums, ₺bn")}
        className="mb-2.5 mt-6"
      />
      <Vitals cols={5}>
        <Vital
          label={tx("Budget balance · monthly")}
          value={nSigned(balNow)}
          unit="₺bn"
          series={balMonthly.slice(-13)}
          format="raw"
          decimals={0}
          note={
            <>
              {tx(monthLabel(recP, false))}{tx(" alone · ")}{tx(nSigned(balMonthAgo))}{tx("₺bn in the same month a year earlier")}</>
          }
        />
        <Vital
          label={tx("Budget balance · 12m")}
          value={nSigned(d.balance12m)}
          unit="₺bn"
          series={balRoll.slice(-13)}
          format="raw"
          decimals={0}
          note={
            balYoY != null ? (
              <>
                <b className={balYoY >= 0 ? "font-semibold text-positive" : "font-semibold text-negative"}>
                  {tx(sTL(balYoY))}
                </b>{" "}{tx("vs a year earlier (")}{tx(bnTL(bal12mAgo))})
              </>
            ) : (
              "revenues − expenditure, trailing 12m"
            )
          }
        />
        <Vital
          label={tx("Primary balance · 12m")}
          value={nSigned(d.primary12m)}
          unit="₺bn"
          series={primRoll.slice(-13)}
          format="raw"
          decimals={0}
          note={
            <>{tx("ex-interest")}{int12 != null && <>{tx(" · the ")}{tx(bnTL(int12))}{tx(" interest bill sits between the two")}</>}
              {primYoY != null && (
                <>
                  {" · "}
                  <b className={primYoY >= 0 ? "font-semibold text-positive" : "font-semibold text-negative"}>
                    {tx(sTL(primYoY))}
                  </b>{" "}
                  y/y
                </>
              )}
            </>
          }
        />
        <Vital
          label={tx("Revenues, y/y · 12m")}
          value={revYoY != null ? `${revYoY >= 0 ? "+" : "−"}${Math.abs(revYoY).toFixed(0)}` : "—"}
          unit="%"
          note={
            expYoY != null && gap != null ? (
              <>{tx("expenditure ")}{tx(expYoY >= 0 ? "+" : "−")}
                {tx(Math.abs(expYoY).toFixed(0))}% ·{" "}
                <b className={gap >= 0 ? "font-semibold text-positive" : "font-semibold text-negative"}>
                  {tx(signedPp(gap, 1))}
                </b>{" "}
                {tx(gap >= 0 ? "revenue outruns spending" : "spending outruns revenue")}
              </>
            ) : (
              "12m sum vs the 12m sum a year earlier"
            )
          }
        />
        <Vital
          label={tx("Interest burden")}
          value={intShare != null ? intShare.toFixed(1) : "—"}
          unit="%"
          note={
            <>
              {tx(bnTL(int12))}{tx(" of interest on ")}{tx(bnTL(rev12))}{tx(" of revenue")}{intShareD != null && (
                <>
                  {" · "}
                  <b className={intShareD <= 0 ? "font-semibold text-positive" : "font-semibold text-negative"}>
                    {tx(signedPp(intShareD, 1))}
                  </b>{" "}
                  y/y
                </>
              )}{" "}
              <Link href="/economy" className="font-semibold text-primary">{tx("/economy")}</Link>
            </>
          }
        />
      </Vitals>

      {/* ── The Read ──────────────────────────────────────────────────── */}
      <div className="mt-7">
        <Takeaway data={read} variant="desk" />
      </div>

      {/* ── Movers | Transmission ─────────────────────────────────────── */}
      <div className="mt-8 grid grid-cols-1 gap-x-9 gap-y-7 lg:grid-cols-[5fr_7fr]">
        <div>
          <SecHead
            title={tx("Real growth by line")}
            meta={tx("cpi-deflated y/y · nominal growth is mostly the deflator")}
            className="mb-2.5"
          />
          <Movers from="Prior month" to={d.asOfLabel} rows={movers} />
        </div>
        <div>
          <SecHead title={tx("Transmission")} meta={tx("the fiscal stance → the banks · computed")} className="mb-2.5" />
          <Transmission items={transmission} />
        </div>
      </div>

      {/* ── Flags ─────────────────────────────────────────────────────── */}
      <div className="mt-8">
        <div>
          <SecHead title={tx("Flags")} meta={tx("rules printed whether or not they fire")} className="mb-2.5" />
          <Flags
            flags={flagList}
            showCleared
            quietNote="Every fiscal rule below was tested against the current release and none tripped."
          />
        </div>
      </div>

      <Depth action={<GlobalRangeSelector />}>
        {/* ── NEW: the real twin ───────────────────────────────────────── */}
        <Section
          title={tx("Nominal vs Real")}
          description={
            tx(d.taxRealYoYNow != null
              ? tx("Tax revenue grows {0}% in real terms once CPI is taken out. Every figure elsewhere on this page is nominal lira, and at the current price level a nominal line is largely a chart of the deflator — so the same series is shown both ways here.", {0: d.taxRealYoYNow.toFixed(1)})
              : "Budget lines in nominal lira and deflated by CPI.")
          }
        >
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <TimeSeriesChart
              series={d.taxNominalVsReal}
              title={
                tx(seriesFinding(toPts(d.taxNominalVsReal["Real (CPI-deflated)"]), {
                  noun: "Real tax revenue growth",
                  decimals: 1,
                }, tx.locale) ?? "Tax Revenue Growth — Nominal vs Real (y/y %)")
              }
              description={tx("The same series twice: nominal y/y, and deflated by the CPI index at both ends of the comparison. The gap between the lines is the price level.")}
              yFormat="pct"
              decimals={1}
              hero="Real (CPI-deflated)"
            />
            <TimeSeriesChart
              series={d.real}
              title={tx("Revenue & Spending, CPI-deflated (y/y %)")}
              description={tx("Tax revenue, primary expenditure and interest, all in real terms — what the money actually bought, year on year.")}
              yFormat="pct"
              decimals={1}
            />
            <TimeSeriesChart
              series={d.pctGdp}
              title={tx("Central-Government Balances (12m, % of GDP)")}
              description={tx("The 12-month balance over trailing-4Q nominal GDP. Both sides are lira, so the price level cancels — this is the ratio that is comparable across years.")}
              yFormat="pct"
              decimals={1}
              hero="Budget balance"
            />
            <TimeSeriesChart
              series={{ "Interest / tax revenue": d.interestShare }}
              title={tx("Interest Expenditure as % of Tax Revenue (12m)")}
              description={tx("What debt service claims out of the tax take before any policy choice is made.")}
              yFormat="pct"
              decimals={1}
            />
          </div>
        </Section>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Stat
            label={tx("Budget balance · 12-month")}
            value={bnTL(d.balance12m)}
            hint={tx("annualised · {0}", {0: d.asOfLabel})}
            tone={d.balance12m != null && d.balance12m < 0 ? "negative" : "positive"}
          />
          <Stat
            label={tx("Primary balance · 12-month")}
            value={bnTL(d.primary12m)}
            hint={tx("annualised · {0}", {0: d.asOfLabel})}
            tone={d.primary12m != null && d.primary12m < 0 ? "negative" : "positive"}
          />
          <Stat
            label={tx("Tax revenue · 12-month")}
            value={bnTL(d.tax12m)}
            hint={tx("annualised · {0}", {0: d.asOfLabel})}
          />
        </div>

        {/* "The headline deficit widened on softer tax intake while the primary
            balance stays in surplus" — the two directions are in d.s1 below; the
            causal attribution to tax intake is not, so it is gone. */}
        <Section
          title={tx("Budget Balance")}
          description={
            tx(d.balance12m != null && d.primary12m != null
              ? tx("Annualised (trailing-12-month) central-government balance. The headline balance is {0}{1}; the primary balance is {2}.", {0: d.balance12m < 0 ? "in deficit" : "in surplus", 1: balMove ? tx(" and {0}", {0: balMove}) : "", 2: d.primary12m >= 0 ? "in surplus" : "in deficit"})
              : "Annualised (trailing-12-month) central-government balance.")
          }
        >
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <TimeSeriesChart
              series={d.s1}
              title={tx("Şekil 1 · Budget & Primary Balance (12m rolling, ₺ bn)")}
              yFormat="raw"
              decimals={0}
            />
            <TimeSeriesChart
              series={d.s5}
              title={tx("Şekil 5 · Monthly Budget Balance (₺ bn)")}
              yFormat="raw"
              decimals={0}
            />
          </div>
        </Section>

        <Section
          title={tx("Revenues")}
          description={tx("Tax-revenue growth has slipped below headline inflation. Tax lines compared {0} vs {1}.", {0: d.barLabels.now, 1: d.barLabels.prev})}
        >
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <TimeSeriesChart
              series={d.s4}
              title={tx("Şekil 4 · Revenue Growth (y/y %, 3-month moving average)")}
              yFormat="pct"
              decimals={0}
            />
            <ChartCard title={tx("Şekil 3 · Tax Revenues by Type (₺ bn, {0} vs {1})", {0: d.barLabels.now, 1: d.barLabels.prev})}>
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
          title={tx("Expenditures")}
          description={tx("Current transfers and personnel dominate spending. Expenditure lines compared {0} vs {1}.", {0: d.barLabels.now, 1: d.barLabels.prev})}
        >
          <ChartCard title={tx("Şekil 2 · Expenditures by Type (₺ bn, {0} vs {1})", {0: d.barLabels.now, 1: d.barLabels.prev})}>
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
          title={tx("Summary")}
          description={tx("Monthly and trailing-12-month figures, ₺ million — {0} vs. one year earlier.", {0: d.asOfLabel})}
        >
          <BudgetTable rows={d.table} now={d.barLabels.now} prev={d.barLabels.prev} />
          <p className="text-xs text-muted-foreground">{tx("Source: TÜİK / Treasury (Hazine ve Maliye Bakanlığı) central-government budget via EVDS.")}{" "}
            <Link href="/economy/balance-of-payments" className="text-primary hover:underline">{tx("Balance of Payments →")}</Link>
          </p>
        </Section>
      </Depth>

      <Colophon>{tx("Compiled, not written — every figure computed from the Treasury (Hazine ve Maliye Bakanlığı) central-government budget series via TCMB EVDS. Balance = revenues − expenditure; primary balance = revenues − primary expenditure; 12-month figures are trailing rolling sums. No forecasts. Analytical information, not investment advice.")}</Colophon>
    </main>
  );
}

function BudgetTable({ rows, now, prev }: { rows: BudgetRow[]; now: string; prev: string }) {
  const tx = useText();
  return (
    <Table wrapperClassName="rounded-[10px] border border-border bg-card">
      <TableHeader>
        <TableRow className="bg-muted/50">
          <TableHead />
          <TableHead className="text-right" colSpan={2}>
            {tx(now)}
          </TableHead>
          <TableHead className="text-right" colSpan={2}>
            {tx(prev)}
          </TableHead>
        </TableRow>
        <TableRow>
          <TableHead>{tx("₺ million")}</TableHead>
          <TableHead className="text-right">{tx("Monthly")}</TableHead>
          <TableHead className="text-right">{tx("12-month")}</TableHead>
          <TableHead className="text-right">{tx("Monthly")}</TableHead>
          <TableHead className="text-right">{tx("12-month")}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((r) => {
          const strong = r.label === "Budget balance" || r.label === "Primary balance";
          return (
            <TableRow key={r.label} className={strong ? "bg-accent/30 font-semibold" : undefined}>
              <TableCell className={`py-1.5 ${r.indent ? "pl-6 text-muted-foreground" : ""}`}>
                {tx(r.label)}
              </TableCell>
              {r.cells.map((v, i) => (
                <TableCellNum key={i} tone={toneFor(v)} className="py-1.5">
                  {tx(v == null ? "—" : nf(v, 0))}
                </TableCellNum>
              ))}
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
