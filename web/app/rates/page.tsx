/**
 * Rates & Macro tab — TCMB EVDS series cached in D1.
 *
 * Cron-fed via scripts/refresh.py → src/scrapers/evds_scraper.py.
 */
import { evdsMulti, latestPeriod } from "@/app/lib/metrics";
import { PageHeader, Stat } from "@/app/components/ui";
import TimeSeriesChart from "@/app/components/TimeSeriesChart";

export const dynamic = "force-dynamic";

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
  ];
  const data = await evdsMulti(allCodes, 5);

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
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-6">
      <PageHeader
        eyebrow="TCMB EVDS"
        title="Rates & Macro"
        description="Daily snapshots · cached in D1, refreshed weekly with the BDDK pipeline"
        dataThrough={latestPeriod(...Object.values(data))}
      />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
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

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        <TimeSeriesChart
          series={byLabel(RATE_CORRIDOR)}
          title="Rate Corridor — Policy + ON + Effective Funding (%)"
          yFormat="pct"
          decimals={2}
          range={{ default: "1Y" }}
        />
        <TimeSeriesChart
          series={byLabel(FX)}
          title="Exchange Rates — USD &amp; EUR"
          yFormat="fx"
          decimals={2}
          range={{ default: "1Y" }}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <TimeSeriesChart
          series={byLabel(LENDING)}
          title="Lending &amp; Deposit Rates (weekly survey, %)"
          yFormat="pct"
          decimals={2}
          range={{ default: "1Y" }}
        />
        <TimeSeriesChart
          series={byLabel(STERIL)}
          title="CBRT Sterilization Channels (TL bn)"
          yFormat="raw"
          decimals={0}
          range={{ default: "1Y" }}
        />
      </div>
    </main>
  );
}
