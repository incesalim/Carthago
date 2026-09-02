/**
 * Balance of Payments — reproduces the Albaraka "Ödemeler Dengesi" monthly
 * report (10 figures + summary table) from TCMB EVDS series. Faithful to the
 * source layout: 3 headline balances, the annualised current-account block,
 * the financial-account (capital inflow) detail, and the financing identity.
 *
 * Data + derivations live in app/lib/bop.ts; all values are TCMB BoP, USD bn
 * unless the summary table (USD million). See METRICS.md § External balance.
 *
 * "The Desk" (web/DESIGN.md): a computed brief (record line + vitals band)
 * above the full report, which is carried over intact under <Depth>.
 */
import { localizeMetadata } from "@/i18n/metadata";
import { getText } from "@/i18n/server";
import type { Metadata } from "next";
import Link from "next/link";
import { getBopData } from "@/app/lib/bop";
import { getPortfolioFlowsData } from "@/app/lib/portfolio-flows";
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
import { GlobalRangeSelector } from "@/app/components/range-context";
import {
  ChartRow,
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
import { lastVal, monthLabel, valAgo } from "@/app/lib/desk";
import { bopInsights } from "@/app/lib/insights";
import Takeaway from "@/app/components/Takeaway";
import { ChartCard } from "@/app/components/ui/chart-card";
import TimeSeriesChart from "@/app/components/TimeSeriesChart";
import BopFlowChart, { type BarSeries, type OverlayLine } from "@/app/components/BopFlowChart";
import { nf } from "@/app/lib/chart-format";

export const dynamic = "force-dynamic";

const pageMetadata: Metadata = {
  title: "Turkey Balance of Payments",
  description: "Türkiye's balance of payments — current account and capital and financial flows from CBRT data.",
  alternates: { canonical: "/economy/balance-of-payments" },
};

export async function generateMetadata(): Promise<Metadata> {
  return localizeMetadata(pageMetadata);
}

// Source-report palette (orange / maroon / grey / amber), light & dark.
const ORANGE = { light: "#e8833a", dark: "#f0a35e" };
const MAROON = { light: "#9c1f2f", dark: "#d65a5a" };
const GREY = { light: "#9ca3af", dark: "#9ca3af" };
const AMBER = { light: "#f5c518", dark: "#fbd34d" };
const INK = { light: "#171717", dark: "#ededed" };

function Grid({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">{children}</div>;
}

const nf2 = (v: number | null) => (v == null ? "—" : nf(v, 2));

const nfInt = (v: number | null) => (v == null ? "—" : nf(v, 0));

/** "−12.4" / "12.4" — a bare mono figure for the vitals band (unit lives in `unit`). */
const nSigned = (v: number | null, d = 1) =>
  v == null ? "—" : `${v < 0 ? "−" : ""}${nf(Math.abs(v), d)}`;

/** "+$4.1bn" / "−$4.1bn" — a signed delta inside a computed note. */
const sBn = (v: number | null, d = 1) =>
  v == null ? "—" : `${v >= 0 ? "+" : "−"}$${nf(Math.abs(v), d)}bn`;

const tone = (v: number | null) =>
  v == null ? "neutral" : v < 0 ? "negative" : "positive";

/** {period_date,value} (chart shape) → {period,value} (sparkline / desk helpers). */
const sp = (pts: { period_date: string; value: number }[] | undefined) =>
  (pts ?? []).map((p) => ({ period: p.period_date, value: p.value }));

/** Record<label, {period_date,value}[]> → long rows for a ChartRow rail. */
const tsRows = (s: Record<string, { period_date: string; value: number | null }[]>) =>
  Object.entries(s).flatMap(([k, pts]) =>
    pts.map((p) => ({ period: p.period_date, bank_type_code: k, value: p.value })),
  );

export default async function BalanceOfPaymentsPage() {
  const tx = await getText();
  const [d, pf] = await Promise.all([getBopData(), getPortfolioFlowsData()]);

  // ---- the brief's computed vitals ------------------------------------------
  // The summary table already carries [now monthly, now 12m, year-ago monthly,
  // year-ago 12m] in USD million for every balance the page fetches.
  const cells = (label: string) =>
    d.table.find((r) => r.label === label)?.cells ?? [null, null, null, null];
  const bn = (v: number | null) => (v == null ? null : v / 1000); // USD mn → USD bn

  const caRoll = sp(d.s1["Current account"]);
  const goodsRoll = sp(d.s2["Trade balance (goods)"]);
  const neoRoll = sp(d.s9["Net errors & omissions"]);

  const recP = caRoll.at(-1)?.period ?? null;
  const prevP = caRoll.at(-2)?.period ?? null;

  const ca12mAgo = bn(cells("Current account")[3]);
  const caYoY = d.ca12m != null && ca12mAgo != null ? d.ca12m - ca12mAgo : null;

  const goods12 = bn(cells("Trade balance (goods)")[1]);
  const goods12Ago = bn(cells("Trade balance (goods)")[3]);
  const goodsYoY = goods12 != null && goods12Ago != null ? goods12 - goods12Ago : null;

  const services12 = bn(cells("Services balance")[1]);
  const travel12 = bn(cells("Travel income (net)")[1]);
  const servicesCover =
    services12 != null && goods12 != null && goods12 !== 0
      ? (services12 / Math.abs(goods12)) * 100
      : null;

  const neo12 = lastVal(neoRoll);
  const neoShare =
    neo12 != null && d.ca12m != null && d.ca12m !== 0
      ? (Math.abs(neo12) / Math.abs(d.ca12m)) * 100
      : null;

  const res12 = bn(cells("Reserve assets")[1]);
  const res12Ago = bn(cells("Reserve assets")[3]);
  const resYoY = res12 != null && res12Ago != null ? res12 - res12Ago : null;

  // ---- "The Read" — computed from the same series the charts show ----------
  const coreRoll = sp(d.s1["Core (ex gold & energy)"] ?? []);
  const fdiRoll = sp(d.fdi12m);
  const portRoll = sp(d.port12m);
  const nfiRoll = sp(d.nfi12m);
  const read = bopInsights({
    ca12m: caRoll,
    core12m: coreRoll,
    neo12m: neoRoll,
    fdi12m: fdiRoll,
    portfolio12m: portRoll,
  }, tx.locale);

  // ---- movers: the 12-month balances, this month against last -------------
  // Every row is the same monthly BoP release on the same 12-month basis, so one
  // from→to header is honest. The Δ is between consecutive 12-month windows,
  // which is what "the deficit widened this month" actually means.
  const rollMover = (label: string, s: { period: string; value: number | null }[]): MoverRow => ({
    label,
    prev: valAgo(s, 1),
    curr: lastVal(s),
    good: "up",
    fmt: (v: number) => `$${v.toFixed(1)}bn`,
    deltaDecimals: 1,
    deltaUnit: "bn",
  });
  const movers: MoverRow[] = [
    rollMover("Current account", caRoll),
    rollMover("Core (ex gold & energy)", coreRoll),
    rollMover("Trade balance (goods)", goodsRoll),
    rollMover("Direct investment (in)", fdiRoll),
    rollMover("Portfolio investment (in)", portRoll),
    rollMover("Net errors & omissions", neoRoll),
  ];

  // ---- transmission: the external account → the banks ----------------------
  const fdiNow = lastVal(fdiRoll);
  const portNow = lastVal(portRoll);
  const nfiNow = lastVal(nfiRoll);
  const transmission: TransmissionItem[] = [
    {
      k: "Current account, 12m",
      v: d.ca12m != null ? `$${Math.abs(d.ca12m).toFixed(1)}bn` : "—",
      effect: (
        <>{tx("The economy’s net external")}{" "}
          {tx(d.ca12m != null && d.ca12m < 0 ? "borrowing" : "lending")}{tx(" over a year. A deficit has to be funded every month it persists, and the banks are one of the channels it is funded through.")}</>
      ),
    },
    {
      k: "Direct investment (in)",
      v: fdiNow != null ? `$${fdiNow.toFixed(1)}bn` : "—",
      effect: (
        <>{tx("Committed capital: it does not leave on a headline. The higher the share of the financing need this covers, the less the external account depends on rollover.")}</>
      ),
    },
    {
      k: "Portfolio investment (in)",
      v: portNow != null ? `$${portNow.toFixed(1)}bn` : "—",
      effect: (
        <>{tx("Money that reprices daily. Its weekly counterpart sits on")}{" "}
          <Link href="/economy" className="font-semibold text-primary">{tx("/economy")}</Link>{" "}{tx("as non-resident flows — the same investors, a far shorter lag.")}</>
      ),
    },
    {
      k: "Net foreign investment",
      v: nfiNow != null ? `$${nfiNow.toFixed(1)}bn` : "—",
      effect: (
        <>{tx("FDI, portfolio and other investment together. What this does not cover is met from reserves or lands in errors and omissions — which is exactly the financing identity the last chart on this page draws.")}</>
      ),
    },
    {
      k: "Banks' external loans",
      v: "see Şekil 6",
      effect: (
        <>{tx("Loans by borrower sector splits out the banks’ own external borrowing. Rollover on that line is a direct")}{" "}
          <Link href="/liquidity" className="font-semibold text-primary">{tx("FC funding")}</Link>{" "}{tx("question, not just a balance-of-payments one.")}</>
      ),
    },
  ];

  // ---- flags ----------------------------------------------------------------
  const financingCover =
    nfiNow != null && d.ca12m != null && d.ca12m < 0 ? (nfiNow / Math.abs(d.ca12m)) * 100 : null;
  const flagList: Flag[] = [
    {
      code: "UNFUNDED",
      active: financingCover != null && financingCover < 100,
      rule: "net_foreign_investment_12m / |current_account_12m| < 100%",
      body: (
        <>
          <b className="font-semibold">{tx("Foreign investment does not cover the deficit.")}</b>{" "}{tx("Net foreign investment of $")}{tx(nfiNow?.toFixed(1))}{tx("bn against a $")}{tx(d.ca12m != null ? Math.abs(d.ca12m).toFixed(1) : "—")}{tx("bn financing need —")}{" "}
          {tx(financingCover?.toFixed(0))}{tx("% cover, with the remainder met from reserves or unidentified flows.")}</>
      ),
      clear: (
        <>{tx("Net foreign investment covers")}{" "}
          {tx(financingCover != null ? `${financingCover.toFixed(0)}%` : "—")}{tx(" of the 12-month financing need.")}</>
      ),
    },
    {
      code: "NEO_LARGE",
      active: neoShare != null && neoShare > 25,
      rule: "|net_errors_omissions_12m| / |current_account_12m| > 25%",
      body: (
        <>
          <b className="font-semibold">{tx("Unidentified flows are large.")}</b>{tx(" Net errors and omissions run $")}{tx(neo12 != null ? Math.abs(neo12).toFixed(1) : "—")}{tx("bn,")}{" "}
          {tx(neoShare?.toFixed(0))}{tx("% of the current-account balance — money the accounts cannot attribute.")}</>
      ),
      clear: (
        <>{tx("Net errors and omissions are")}{" "}
          {tx(neoShare != null ? `${neoShare.toFixed(0)}%` : "—")}{tx(" of the current-account balance — inside the 25% line.")}</>
      ),
    },
    {
      code: "PORTFOLIO_LED",
      active: fdiNow != null && portNow != null && portNow > fdiNow && portNow > 0,
      rule: "portfolio_inflow_12m > fdi_inflow_12m",
      body: (
        <>
          <b className="font-semibold">{tx("Financing leans on portfolio money rather than direct investment.")}</b>{" "}
          ${tx(portNow?.toFixed(1))}{tx("bn portfolio against $")}{tx(fdiNow?.toFixed(1))}{tx("bn direct — the first can reverse in a week, the second cannot.")}</>
      ),
      clear: (
        <>{tx("Direct investment ($")}{tx(fdiNow?.toFixed(1) ?? "—")}{tx("bn) is at or above portfolio inflow ($")}{tx(portNow?.toFixed(1) ?? "—")}{tx("bn).")}</>
      ),
    },
    {
      code: "CORE_DEFICIT",
      active: lastVal(coreRoll) != null && (lastVal(coreRoll) as number) < 0,
      rule: "current_account_ex_gold_energy_12m < 0",
      body: (
        <>
          <b className="font-semibold">{tx("The core balance is in deficit.")}</b>{tx(" Excluding gold and energy, the 12-month current account is $")}{tx(Math.abs(lastVal(coreRoll) as number).toFixed(1))}{tx("bn negative — a structural gap rather than a commodity-price one.")}</>
      ),
      clear: (
        <>{tx("The core balance (ex gold & energy) is $")}{tx(lastVal(coreRoll) != null ? (lastVal(coreRoll) as number).toFixed(1) : "—")}{tx("bn — at or above zero.")}</>
      ),
    },
  ];

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title={tx("Balance of Payments")}
        record={
          <>{tx("Record ")}<b className="font-normal text-foreground">{tx(monthLabel(recP))}</b>{tx(" · vs")}{" "}
            {tx(monthLabel(prevP, false))}{tx(" · 12m rolling sums")}</>
        }
        right="every figure computed from source series"
      />

      {/* ── The vitals ─────────────────────────────────────────────────── */}
      <SecHead
        title={tx("The vitals")}
        meta={tx("tcmb bpm6 · trailing-12-month sums, usd bn")}
        className="mb-2.5 mt-6"
      />
      <Vitals cols={5}>
        <Vital
          label={tx("Current account · 12m")}
          value={nSigned(d.ca12m)}
          unit="$bn"
          series={caRoll.slice(-13)}
          format="raw"
          decimals={1}
          note={
            <>
              {tx(nSigned(d.caMonthly, 1))}{tx("$bn in ")}{tx(monthLabel(recP, false))}
              {caYoY != null && (
                <>
                  {" · "}
                  <b className={caYoY >= 0 ? "font-semibold text-positive" : "font-semibold text-negative"}>
                    {tx(sBn(caYoY))}
                  </b>{" "}{tx("vs a year earlier")}</>
              )}
            </>
          }
        />
        <Vital
          label={tx("Goods balance · 12m")}
          value={nSigned(goods12)}
          unit="$bn"
          series={goodsRoll.slice(-13)}
          format="raw"
          decimals={1}
          note={
            <>
              {goodsYoY != null && (
                <>
                  <b className={goodsYoY >= 0 ? "font-semibold text-positive" : "font-semibold text-negative"}>
                    {tx(sBn(goodsYoY))}
                  </b>{" "}
                  y/y ·{" "}
                </>
              )}{tx("customs detail:")}{" "}
              <Link href="/economy/foreign-trade" className="font-semibold text-primary">{tx("/economy/foreign-trade")}</Link>
            </>
          }
        />
        <Vital
          label={tx("Services surplus · 12m")}
          value={nSigned(services12)}
          unit="$bn"
          note={
            <>{tx("net travel ")}{tx(nSigned(travel12))}{tx("$bn")}{servicesCover != null && (
                <>{tx(" · offsets ")}{tx(servicesCover.toFixed(0))}{tx("% of the goods gap")}</>
              )}
            </>
          }
        />
        <Vital
          label={tx("Net errors & omissions · 12m")}
          value={nSigned(neo12)}
          unit="$bn"
          series={neoRoll.slice(-13)}
          format="raw"
          decimals={1}
          note={
            neoShare != null ? (
              <>{tx("unrecorded flows — ")}{tx(neoShare.toFixed(0))}{tx("% of the |current account| 12m balance")}</>
            ) : (
              "unrecorded flows — the BoP residual"
            )
          }
        />
        <Vital
          label={tx("Reserve assets · 12m")}
          value={nSigned(res12)}
          unit="$bn"
          note={
            <>
              {resYoY != null && (
                <>
                  <b className={resYoY >= 0 ? "font-semibold text-positive" : "font-semibold text-negative"}>
                    {tx(sBn(resYoY))}
                  </b>{" "}{tx("vs a year earlier ·")}{" "}
                </>
              )}{tx("net acquisition, + = reserves built")}</>
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
            title={tx("The 12-month balances")}
            meta={tx("consecutive rolling windows · one bop release")}
            className="mb-2.5"
          />
          <Movers
            from={monthLabel(prevP, false)}
            to={monthLabel(recP ?? null, false)}
            rows={movers}
          />
        </div>
        <div>
          <SecHead title={tx("Transmission")} meta={tx("the external account → the banks · computed")} className="mb-2.5" />
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
            quietNote="Every financing rule below was tested against the current release and none tripped."
          />
        </div>
      </div>

      <Depth action={<GlobalRangeSelector />}>
        {/* Cover KPIs — mirror the report's three headline balances. */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Stat
            label={tx("Current account · monthly")}
            value={`${nf2(d.caMonthly)}`}
            hint={tx("USD bn · {0}", {0: d.asOfLabel})}
            tone={tone(d.caMonthly)}
          />
          <Stat
            label={tx("Current account · 12-month")}
            value={`${nf2(d.ca12m)}`}
            hint={tx("USD bn · trailing 12m to {0}", {0: d.asOfLabel})}
            tone={tone(d.ca12m)}
          />
          <Stat
            label={tx("Core balance · monthly")}
            value={`${nf2(d.coreMonthly)}`}
            hint={tx("USD bn · ex gold & energy · {0}", {0: d.asOfLabel})}
            tone={tone(d.coreMonthly)}
          />
        </div>

        {/* "net tourism is the main services offset to the goods deficit" was a
            ranking over a services breakdown this page does not load. The
            definitional half is timeless and stays. */}
        <Section
          title={tx("Current Account")}
          description={tx("Annualised (trailing-12-month) balances, USD bn. The core balance strips out the volatile gold and energy bills.")}
        >
          <Grid>
            <TimeSeriesChart
              series={d.s1}
              title={tx("Şekil 1 · Current Account (12m rolling, USD bn)")}
              yFormat="raw"
              decimals={1}          />
            <TimeSeriesChart
              series={d.s2}
              title={tx("Şekil 2 · Goods & Tourism (12m rolling, USD bn)")}
              yFormat="raw"
              decimals={1}          />
          </Grid>
        </Section>

        <Section
          title={tx("Capital Inflows & Financial Account")}
          description={tx("Monthly financing flows on a net-incurrence-of-liabilities basis (inflows into Türkiye), USD bn. Bars stack above/below zero; Şekil 4 & 5 add the 12-month cumulative on the right axis.")}
        >
          <Grid>
            <ChartCard title={tx("Şekil 3 · Capital Inflows (monthly, USD bn)")}>
              <BopFlowChart
                data={d.s3}
                bars={[
                  { key: "fdi", label: "Direct investment", fill: ORANGE },
                  { key: "portfolio", label: "Portfolio investment", fill: MAROON },
                  { key: "loans", label: "Loans", fill: GREY },
                  { key: "trade", label: "Trade credits", fill: AMBER },
                ] satisfies BarSeries[]}
                unit=" bn"
              />
            </ChartCard>
            <ChartCard title={tx("Şekil 4 · Direct Investment (monthly, USD bn)")}>
              <BopFlowChart
                data={d.s4}
                bars={[
                  { key: "realEstate", label: "Real estate", fill: ORANGE },
                  { key: "other", label: "Other", fill: MAROON },
                ] satisfies BarSeries[]}
                line={{ key: "twelveM", label: "12-month", color: INK, rightAxis: true } satisfies OverlayLine}
                unit=" bn"
              />
            </ChartCard>
            <ChartCard title={tx("Şekil 5 · Portfolio Investment (monthly, USD bn)")}>
              <BopFlowChart
                data={d.s5}
                bars={[
                  { key: "equity", label: "Equity & fund shares", fill: ORANGE },
                  { key: "debt", label: "Debt securities", fill: MAROON },
                ] satisfies BarSeries[]}
                line={{ key: "twelveM", label: "12-month", color: INK, rightAxis: true } satisfies OverlayLine}
                unit=" bn"
              />
            </ChartCard>
            <ChartCard title={tx("Şekil 6 · Loans by Borrower (net liab., monthly, USD bn)")}>
              <BopFlowChart
                data={d.s6}
                bars={[
                  { key: "banks", label: "Banks", fill: ORANGE },
                  { key: "gov", label: "General government", fill: MAROON },
                  { key: "other", label: "Other sectors", fill: GREY },
                ] satisfies BarSeries[]}
                unit=" bn"
              />
            </ChartCard>
          </Grid>
        </Section>

        <Section
          title={tx("Foreign Portfolio Flows — Weekly (TCMB securities statistics)")}
          description={tx("Non-residents' weekly net transactions in Borsa İstanbul equities and government domestic debt securities (GDDS / DİBS), net buy +, net sell −, and their total holdings. Week-ending Friday, USD. Source: TCMB «Yurt Dışı Yerleşikler Menkul Kıymet İstatistikleri» — the dataset behind the widely-cited weekly foreign-flows chart, and more timely than the monthly BoP portfolio line (Şekil 5) above.")}
        >
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Stat
              label={tx("Net equity flow · last week")}
              value={nfInt(pf.netEquityLatest)}
              hint={tx("USD mn · {0}", {0: pf.asOfLabel})}
              tone={tone(pf.netEquityLatest)}
            />
            <Stat
              label={tx("Net bond (GDDS) flow · last week")}
              value={nfInt(pf.netGddsLatest)}
              hint={tx("USD mn · {0}", {0: pf.asOfLabel})}
              tone={tone(pf.netGddsLatest)}
            />
            <Stat
              label={tx("Foreign equity holdings")}
              value={nf2(pf.equityHoldings)}
              hint={tx("USD bn · {0}", {0: pf.asOfLabel})}
              tone="neutral"
            />
          </div>
          <Grid>
            <ChartCard title={tx("Weekly Net Securities Flows (USD mn)")}>
              <BopFlowChart
                data={pf.flows}
                bars={[
                  { key: "equity", label: "Equity", fill: MAROON },
                  { key: "bonds", label: "Govt bonds (DİBS)", fill: ORANGE },
                ] satisfies BarSeries[]}
                unit=" mn"
                decimals={0}
                height={360}
              />
            </ChartCard>
            <TimeSeriesChart
              series={pf.holdings}
              title={tx("Non-resident Holdings (USD bn)")}
              yFormat="raw"
              decimals={1}
            />
          </Grid>
        </Section>

        <Section
          title={tx("Trade Credits, Deposits & Errors")}
          description={tx("Annualised (trailing-12-month) flows, USD bn. Currency & deposits split into residents' asset acquisition abroad vs. liabilities incurred to non-residents.")}
        >
          <Grid>
            <TimeSeriesChart
              series={d.s7}
              title={tx("Şekil 7 · Trade Credits (12m rolling, USD bn)")}
              yFormat="raw"
              decimals={1}          />
            <TimeSeriesChart
              series={d.s8}
              title={tx("Şekil 8 · Currency & Deposits (12m rolling, USD bn)")}
              yFormat="raw"
              decimals={1}          />
          </Grid>
          <ChartRow
            data={tsRows(d.s9)}
            deltaPeriods={12}
            deltaLabel="12m"
            fmt={(v) => `${v < 0 ? "−" : ""}$${Math.abs(v).toFixed(1)}bn`}
          >
            <TimeSeriesChart
              series={d.s9}
              title={tx("Şekil 9 · Net Errors & Omissions (12m rolling, USD bn)")}
              yFormat="raw"
              decimals={1}
            />
          </ChartRow>
        </Section>

        <Section
          title={tx("Financing of the Current-Account Deficit")}
          description={tx("Şekil 10 · Monthly, USD bn. Identity: current account ≡ net foreign investment + (reserves − net errors). Net foreign investment = FDI + portfolio + other investment (net); the residual is reserve change less net errors.")}
        >
          <ChartCard title={tx("Şekil 10 · Financing of the Current Account (monthly, USD bn)")}>
            <BopFlowChart
              data={d.s10}
              grouped
              bars={[
                { key: "nfi", label: "Net foreign investment", fill: ORANGE },
                { key: "need", label: "Financing requirement (current account)", fill: MAROON },
              ] satisfies BarSeries[]}
              line={{ key: "resNeo", label: "Reserves − net errors", color: INK, dotted: true } satisfies OverlayLine}
              unit=" bn"
              height={360}
            />
          </ChartCard>
        </Section>

        <Section
          title={tx("Summary")}
          description={tx("Monthly and trailing-12-month cumulative balances, USD million — {0} vs. one year earlier.", {0: d.asOfLabel})}
        >
          <Table wrapperClassName="rounded-[10px] border border-border bg-card">
            <TableHeader>
              <TableRow className="bg-muted/50">
                <TableHead />
                <TableHead className="text-right" colSpan={2}>
                  {tx(d.asOfLabel)}
                </TableHead>
                <TableHead className="text-right" colSpan={2}>{tx("year earlier")}</TableHead>
              </TableRow>
              <TableRow>
                <TableHead>{tx("USD million")}</TableHead>
                <TableHead className="text-right">{tx("Monthly")}</TableHead>
                <TableHead className="text-right">{tx("12-month")}</TableHead>
                <TableHead className="text-right">{tx("Monthly")}</TableHead>
                <TableHead className="text-right">{tx("12-month")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {d.table.map((r) => (
                <TableRow key={r.label}>
                  <TableCell className="py-1.5">{tx(r.label)}</TableCell>
                  {r.cells.map((v, i) => (
                    <TableCellNum key={i} tone={toneFor(v)} className="py-1.5">
                      {tx(nfInt(v))}
                    </TableCellNum>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <p className="text-xs text-muted-foreground">{tx("Source: TCMB (CBRT) balance-of-payments statistics via EVDS.")}{" "}
            <Link href="/economy" className="text-primary hover:underline">{tx("← Back to Economy")}</Link>
          </p>
        </Section>
      </Depth>

      <Colophon>{tx("Compiled, not written — every figure computed from TCMB (CBRT) balance-of-payments statistics (BPM6 analytic & detailed presentation) and the TCMB non-resident securities statistics, via EVDS. 12-month figures are trailing rolling sums of the monthly source series. No forecasts. Analytical information, not investment advice.")}</Colophon>
    </main>
  );
}
