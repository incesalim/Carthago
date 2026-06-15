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
  tlLoansYoY,
  consumerMix,
  consumerSegmentYoYAll,
  cardsSplit,
  smeLoans,
  smeLoansYoY,
  smeBreakdown,
  latestPerBank,
  latestPeriod,
  PRIMARY_BANK_TYPES,
  BANK_TYPES,
  BANK_TYPE_LABELS,
  type TimeSeriesRow,
} from "@/app/lib/metrics";
import { PageHeader, Section } from "@/app/components/ui";
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
    consYoY, cards, smeBreak, tlYoYAll,
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
    consumerSegmentYoYAll(),
    cardsSplit(),
    smeBreakdown(),
    tlLoansYoY(publicVsPrivate),
  ]);

  const fxShare = computeFxShare(tlSec, fxSec);
  const pubPriv = new Set<string>(publicVsPrivate);
  const yoyPubVsPriv = yoyAll.filter((r: TimeSeriesRow) => pubPriv.has(r.bank_type_code));

  // Reshape consumer YoY into long-form for TrendChart
  const consYoYLong: TimeSeriesRow[] = [];
  for (const r of consYoY) {
    if (r.housing != null) consYoYLong.push({ period: r.period, bank_type_code: "HOUSING", value: r.housing });
    if (r.auto    != null) consYoYLong.push({ period: r.period, bank_type_code: "AUTO",    value: r.auto });
    if (r.gpl     != null) consYoYLong.push({ period: r.period, bank_type_code: "GPL",     value: r.gpl });
    if (r.cards   != null) consYoYLong.push({ period: r.period, bank_type_code: "CARDS",   value: r.cards });
  }

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      <PageHeader
        title="Credit"
        description="Loan growth · currency split · consumer mix · SME · public vs. private — BDDK monthly bulletin"
        dataThrough={latestPeriod(loansSector, yoyAll)}
      />

      <Section title="Total Credit Growth" description="Sector level + cross-sectional and time-series growth.">
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

      <Section title="Currency Breakdown" description="FX exposure stays moderate; TL drives sector growth.">
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

      <Section title="Consumer Credit" description="Composition of household lending — cards & GPL drive the bulk.">
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

      <Section title="Consumer Segments" description="Per-product growth — cards & GPL drive the headline number.">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TrendChart
            data={consYoYLong}
            seriesLabels={{
              HOUSING: "Housing",
              AUTO: "Auto",
              GPL: "Gen. Purpose",
              CARDS: "Retail Cards",
            }}
            title="Consumer Segment YoY Growth (%)"
            yFormat="pct"
            decimals={1}
            zeroLine
          />
          <TrendChart
            data={cards.flatMap((r: { period: string; retail: number | null; corporate: number | null }) => {
              const out: TimeSeriesRow[] = [];
              if (r.retail    != null) out.push({ period: r.period, bank_type_code: "RETAIL",    value: r.retail });
              if (r.corporate != null) out.push({ period: r.period, bank_type_code: "CORPORATE", value: r.corporate });
              return out;
            })}
            seriesLabels={{ RETAIL: "Retail Cards", CORPORATE: "Corporate Cards" }}
            title="Credit Cards — Retail vs Corporate (Level)"
            yFormat="bn"
            decimals={0}
          />
        </div>
      </Section>

      <Section title="SME & Public vs. Private" description="Public bank lending vs. private bank lending — the clearest sector signal.">
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
            data={tlYoYAll}
            seriesLabels={{
              [BANK_TYPES.PRIVATE]: "Private",
              [BANK_TYPES.STATE]: "State",
            }}
            title="TL Loans YoY — Public vs Private"
            yFormat="pct"
            decimals={1}
            zeroLine
          />
          <StackedArea
            data={smeBreak.map((r: { period: string; micro: number | null; small: number | null; medium: number | null }) => ({
              period: r.period,
              Micro: r.micro ?? 0,
              Small: r.small ?? 0,
              Medium: r.medium ?? 0,
            }))}
            series={[
              { key: "Micro", label: "Micro" },
              { key: "Small", label: "Small" },
              { key: "Medium", label: "Medium" },
            ]}
            title="SME Mix — Micro / Small / Medium (sector, TL bn)"
            yFormat="bn"
            decimals={0}
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
