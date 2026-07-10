/**
 * Rates & Macro tab — TCMB EVDS series cached in D1.
 *
 * Cron-fed via scripts/refresh.py → src/scrapers/evds_scraper.py.
 */
import type { Metadata } from "next";
import { evdsMulti, latestPeriod } from "@/app/lib/metrics";
import { PageHeader, Stat } from "@/app/components/ui";
import TimeSeriesChart from "@/app/components/TimeSeriesChart";
import TrendChart from "@/app/components/TrendChart";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkish Banking — Interest Rates",
  description: "Lending and deposit interest rates in Türkiye's banking sector from CBRT and BDDK data.",
  alternates: { canonical: "/rates" },
};

const RATE_CORRIDOR = {
  "TP.PY.P02.1H": "Policy (1-week repo)",
  "TP.PY.P02.ON": "ON Lending",
  "TP.PY.P01.ON": "ON Borrowing",
  "TP.APIFON4":   "CBRT Effective Funding Cost",
};

const FX = {
  "TP.DK.USD.A": "USD / TRY",
  "TP.DK.EUR.A": "EUR / TRY",
};

const STERIL = {
  "TP.APIFON2.IHA": "Auction (TL deposit)",
  "TP.APIFON2.KOT": "Quotation",
  "TP.APIFON2.LIK": "Liquidity Bills",
};

const LENDING = {
  "TP.KTFTUK":   "Consumer",
  "TP.KTF17":    "Commercial",
  "TP.KTF12":    "Housing",
  "TP.TRY.MT06": "Deposit (TL)",
};

// TL deposit rates by maturity bucket (TCMB weekly flow survey) — mirrors the
// BBVA liquidity section's deposit-cost ladder. MT06 above is the blended total.
const DEP_MATURITY = {
  "TP.TRY.MT01": "≤1m",
  "TP.TRY.MT02": "1-3m",
  "TP.TRY.MT03": "3-6m",
  "TP.TRY.MT04": "6-12m",
  "TP.TRY.MT05": ">12m",
};

// TL loan–deposit spread = commercial loan (excl. overdraft, KTF18) − blended
// TL deposit (MT06). BBVA's "TL interest-rate spread"; goes negative when
// deposit competition outruns loan pricing.
const SPREAD_LOAN = "TP.KTF18";
const SPREAD_DEPOSIT = "TP.TRY.MT06";

// FC interest-rate spread = FC commercial-loan rate − FC deposit rate, per
// currency (BBVA's "FC interest-rate spread"). USD and EUR shown separately.
const FC_SPREADS = [
  { key: "USD", loan: "TP.KTF17.USD", deposit: "TP.USD.MT06", label: "USD (loan − deposit)" },
  { key: "EUR", loan: "TP.KTF17.EUR", deposit: "TP.EUR.MT06", label: "EUR (loan − deposit)" },
] as const;

const fmtPct = (v: number | undefined) => (v == null ? "—" : `${v.toFixed(2)}%`);
const fmtFx  = (v: number | undefined) => (v == null ? "—" : `₺${v.toFixed(2)}`);

interface KpiCardProps {
  label: string;
  value: string;
  asOf: string;
}

function KpiCard({ label, value, asOf }: KpiCardProps) {
  return <Stat label={label} value={value} hint={`as of ${asOf}`} />;
}

export default async function RatesPage() {
  const allCodes = [
    ...Object.keys(RATE_CORRIDOR),
    ...Object.keys(FX),
    ...Object.keys(STERIL),
    ...Object.keys(LENDING),
    ...Object.keys(DEP_MATURITY),
    SPREAD_LOAN,
    ...FC_SPREADS.flatMap((s) => [s.loan, s.deposit]),
  ];
  const data = await evdsMulti(allCodes, 5);

  // Spread of a loan series minus a deposit series, aligned on the deposit
  // survey's dates. Returns TrendPoints keyed by `code`.
  const spreadOf = (loanCode: string, depCode: string, code: string) => {
    const depMap = new Map((data[depCode] ?? []).map((r) => [r.period_date, r.value]));
    return (data[loanCode] ?? [])
      .filter((r) => depMap.has(r.period_date))
      .map((r) => ({
        period: r.period_date,
        bank_type_code: code,
        value: r.value - depMap.get(r.period_date)!,
      }));
  };

  // TL loan–deposit spread.
  const spread = spreadOf(SPREAD_LOAN, SPREAD_DEPOSIT, "SPREAD");
  // FC loan–deposit spread (USD + EUR on one chart).
  const fcSpread = FC_SPREADS.flatMap((s) => spreadOf(s.loan, s.deposit, s.key));
  const fcSpreadLabels = Object.fromEntries(FC_SPREADS.map((s) => [s.key, s.label]));

  const byLabel = (group: Record<string, string>) => {
    const out: Record<string, { period_date: string; value: number }[]> = {};
    for (const [code, label] of Object.entries(group)) {
      out[label] = data[code] ?? [];
    }
    return out;
  };

  const policy = data["TP.PY.P02.1H"]?.at(-1);
  const usd = data["TP.DK.USD.A"]?.at(-1);
  const eur = data["TP.DK.EUR.A"]?.at(-1);
  const cbrtCost = data["TP.APIFON4"]?.at(-1);

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      <PageHeader
        eyebrow="TCMB EVDS"
        title="Rates & Macro"
        description="Daily snapshots · cached in D1, refreshed weekly with the BDDK pipeline"
        rangeSelector
        dataThrough={latestPeriod(...Object.values(data))}
      />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard label="Policy Rate"
                 value={fmtPct(policy?.value)}
                 asOf={policy?.period_date ?? "—"} />
        <KpiCard label="CBRT Funding Cost"
                 value={fmtPct(cbrtCost?.value)}
                 asOf={cbrtCost?.period_date ?? "—"} />
        <KpiCard label="USD / TRY"
                 value={fmtFx(usd?.value)}
                 asOf={usd?.period_date ?? "—"} />
        <KpiCard label="EUR / TRY"
                 value={fmtFx(eur?.value)}
                 asOf={eur?.period_date ?? "—"} />
      </div>

      {/* Transmission first (display-study Phase 5): the strategist question is
          not "where is the policy rate" but "how fast does it reach bank
          pricing" — deposit rates reprice in weeks, loan rates with a lag; the
          gap between the two lines IS the margin cycle. */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <TimeSeriesChart
          series={byLabel(RATE_CORRIDOR)}
          title="Rate Corridor — Policy + ON + Effective Funding (%)"
          yFormat="pct"
          decimals={2}        />
        <TimeSeriesChart
          series={byLabel(LENDING)}
          title="Transmission — policy cuts reach deposit pricing first (weekly survey, %)"
          yFormat="pct"
          decimals={2}        />
      </div>

      {/* Deposit-cost ladder + loan–deposit spreads — the BBVA liquidity
          section's margin read: where the TL deposit curve sits by maturity,
          and whether loans out-price deposits (positive spread) in TL and FC. */}
      <TimeSeriesChart
        series={byLabel(DEP_MATURITY)}
        title="TL Deposit Rates by Maturity (weekly survey, %)"
        yFormat="pct"
        decimals={2}
      />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <TrendChart
          data={spread}
          seriesLabels={{ SPREAD: "Commercial (ex-OD) − Deposit" }}
          title="TL Loan–Deposit Spread (pp) — commercial vs deposit cost"
          yFormat="pct"
          decimals={2}
          zeroLine
        />
        <TrendChart
          data={fcSpread}
          seriesLabels={fcSpreadLabels}
          title="FC Loan–Deposit Spread (pp) — USD &amp; EUR commercial vs deposit"
          yFormat="pct"
          decimals={2}
          zeroLine
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <TimeSeriesChart
          series={byLabel(FX)}
          title="Exchange Rates — USD &amp; EUR"
          yFormat="fx"
          decimals={2}        />
        <TimeSeriesChart
          series={byLabel(STERIL)}
          title="CBRT Sterilization Channels (TL bn)"
          yFormat="raw"
          decimals={0}        />
      </div>
    </main>
  );
}
