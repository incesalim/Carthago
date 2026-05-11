/**
 * Credit tab — loan growth, currency split, consumer mix, SME, public vs
 * private differentiator. Mirrors the panels from the old Python dashboard.
 */
import {
  totalLoans,
  tlLoans,
  fxLoans,
  totalLoansYoY,
  totalLoansMoM,
  consumerMix,
  smeLoans,
  smeLoansYoY,
  latestPerBank,
  PRIMARY_BANK_TYPES,
  BANK_TYPES,
  BANK_TYPE_LABELS,
  type TimeSeriesRow,
} from "@/app/lib/metrics";
import BarByBank from "@/app/components/BarByBank";
import TrendChart from "@/app/components/TrendChart";
import StackedArea from "@/app/components/StackedArea";

export const dynamic = "force-dynamic";

/** Compute FX share of loans = fx / (tl + fx) per period, sector only. */
function computeFxShare(tl: TimeSeriesRow[], fx: TimeSeriesRow[]): TimeSeriesRow[] {
  const tlMap = new Map(tl.map((r) => [r.period + "|" + r.bank_type_code, r.value]));
  const out: TimeSeriesRow[] = [];
  for (const r of fx) {
    const key = r.period + "|" + r.bank_type_code;
    const t = tlMap.get(key);
    if (t == null || r.value == null || (t + r.value) === 0) continue;
    out.push({
      period: r.period,
      bank_type_code: r.bank_type_code,
      value: (r.value * 100) / (t + r.value),
    });
  }
  return out;
}

export default async function CreditPage() {
  const sector = [BANK_TYPES.SECTOR];
  const groups = PRIMARY_BANK_TYPES.filter((c) => c !== BANK_TYPES.SECTOR);
  const publicVsPrivate = [BANK_TYPES.PRIVATE, BANK_TYPES.STATE];

  const [
    loansSector, tlSec, fxSec,
    yoyAll, momAll, yoyByBank,
    consMix, smeLevel, smeYoY,
  ] = await Promise.all([
    totalLoans(sector),
    tlLoans(sector),
    fxLoans(sector),
    totalLoansYoY(PRIMARY_BANK_TYPES),
    totalLoansMoM(sector),
    latestPerBank(totalLoansYoY, groups),
    consumerMix(BANK_TYPES.SECTOR),
    smeLoans([BANK_TYPES.SECTOR, ...publicVsPrivate]),
    smeLoansYoY([BANK_TYPES.SECTOR, ...publicVsPrivate]),
  ]);

  const fxShare = computeFxShare(tlSec, fxSec);
  const pubPriv = new Set<string>(publicVsPrivate);
  const yoyPubVsPriv = yoyAll.filter((r: TimeSeriesRow) => pubPriv.has(r.bank_type_code));

  return (
    <main className="px-6 py-8 max-w-7xl mx-auto space-y-8">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Credit</h1>
        <p className="text-sm text-neutral-500">
          Loan growth · currency split · consumer mix · SME · public vs. private — BDDK monthly bulletin
        </p>
      </header>

      <Section title="Total Credit Growth" subtitle="Sector level + cross-sectional and time-series growth.">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TrendChart
            data={loansSector}
            seriesLabels={{ [BANK_TYPES.SECTOR]: "Sector" }}
            title="Total Loans — Level (sector)"
            yFormat="trn"
            decimals={2}
          />
          <TrendChart
            data={yoyAll}
            seriesLabels={BANK_TYPE_LABELS}
            title="Loan Growth YoY (%) by group"
            yFormat="pct"
            decimals={1}
            zeroLine
          />
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2">
            <TrendChart
              data={momAll}
              seriesLabels={{ [BANK_TYPES.SECTOR]: "Sector" }}
              title="Loan Growth MoM (%) — sector"
              yFormat="pct"
              decimals={2}
              zeroLine
            />
          </div>
          <BarByBank
            data={yoyByBank}
            labels={BANK_TYPE_LABELS}
            title={`Loan YoY by group · ${yoyByBank[0]?.period ?? ""}`}
            format="pct"
            decimals={1}
          />
        </div>
      </Section>

      <Section title="Currency Breakdown" subtitle="FX exposure stays moderate; TL drives sector growth.">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <TrendChart
            data={tlSec}
            seriesLabels={{ [BANK_TYPES.SECTOR]: "TL Loans" }}
            title="TL Loans — Level"
            yFormat="trn"
            decimals={2}
          />
          <TrendChart
            data={fxSec}
            seriesLabels={{ [BANK_TYPES.SECTOR]: "FX Loans" }}
            title="FX Loans — Level (TL equivalent)"
            yFormat="trn"
            decimals={2}
          />
          <TrendChart
            data={fxShare}
            seriesLabels={{ [BANK_TYPES.SECTOR]: "FX share" }}
            title="FX Share of Total Loans (%)"
            yFormat="pct"
            decimals={1}
          />
        </div>
      </Section>

      <Section title="Consumer Credit" subtitle="Composition of household lending — cards & GPL drive the bulk.">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <StackedArea
            data={consMix.map((r: { period: string; housing: number | null; auto: number | null; gpl: number | null; cards: number | null }) => ({
              period: r.period,
              Housing: r.housing ?? 0,
              Auto: r.auto ?? 0,
              "Gen. Purpose": r.gpl ?? 0,
              "Retail Cards": r.cards ?? 0,
            }))}
            series={[
              { key: "Housing", label: "Housing" },
              { key: "Auto", label: "Auto" },
              { key: "Gen. Purpose", label: "Gen. Purpose" },
              { key: "Retail Cards", label: "Retail Cards" },
            ]}
            title="Consumer Credit Mix — Level (sector)"
            yFormat="trn"
            decimals={2}
          />
          <StackedArea
            data={consMix.map((r: { period: string; housing: number | null; auto: number | null; gpl: number | null; cards: number | null }) => ({
              period: r.period,
              Housing: r.housing ?? 0,
              Auto: r.auto ?? 0,
              "Gen. Purpose": r.gpl ?? 0,
              "Retail Cards": r.cards ?? 0,
            }))}
            series={[
              { key: "Housing", label: "Housing" },
              { key: "Auto", label: "Auto" },
              { key: "Gen. Purpose", label: "Gen. Purpose" },
              { key: "Retail Cards", label: "Retail Cards" },
            ]}
            title="Consumer Credit Mix — Share (%)"
            percentStack
          />
        </div>
      </Section>

      <Section title="SME & Public vs. Private" subtitle="Public bank lending vs. private bank lending — the clearest sector signal.">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TrendChart
            data={smeYoY}
            seriesLabels={{
              [BANK_TYPES.SECTOR]: "Sector",
              [BANK_TYPES.PRIVATE]: "Private",
              [BANK_TYPES.STATE]: "State",
            }}
            title="SME Loan Growth YoY (%)"
            yFormat="pct"
            decimals={1}
            zeroLine
          />
          <TrendChart
            data={yoyPubVsPriv}
            seriesLabels={{
              [BANK_TYPES.PRIVATE]: "Private",
              [BANK_TYPES.STATE]: "State",
            }}
            title="Total Credit YoY — Public vs Private"
            yFormat="pct"
            decimals={1}
            zeroLine
          />
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TrendChart
            data={smeLevel.filter((r: TimeSeriesRow) => r.bank_type_code === BANK_TYPES.SECTOR)}
            seriesLabels={{ [BANK_TYPES.SECTOR]: "SME" }}
            title="SME Loans — Level (sector)"
            yFormat="trn"
            decimals={2}
          />
          <TrendChart
            data={smeLevel.filter((r: TimeSeriesRow) => pubPriv.has(r.bank_type_code))}
            seriesLabels={{
              [BANK_TYPES.PRIVATE]: "Private",
              [BANK_TYPES.STATE]: "State",
            }}
            title="SME Loans — Public vs Private (Level)"
            yFormat="trn"
            decimals={2}
          />
        </div>
      </Section>
    </main>
  );
}

function Section({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section className="space-y-4">
      <div className="space-y-0.5">
        <h2 className="text-base font-semibold text-neutral-900">{title}</h2>
        {subtitle && <p className="text-xs text-neutral-500">{subtitle}</p>}
      </div>
      <div className="space-y-4">{children}</div>
    </section>
  );
}
