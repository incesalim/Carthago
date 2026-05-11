/**
 * Weekly Trends tab — BDDK weekly bulletin.
 *
 * Loans + Deposits + NPL with annualized 4-week and 13-week growth rates
 * across the 5 bank groups + sector, plus currency / consumer-segment /
 * SME-vs-commercial breakdowns.
 */
import {
  weeklySeries,
  weeklyGrowth,
  WEEKLY_BANK_TYPES,
  WEEKLY_BANK_TYPE_LABELS,
} from "@/app/lib/metrics";
import TrendChart from "@/app/components/TrendChart";
import type { WeeklyRow } from "@/app/lib/metrics";

export const dynamic = "force-dynamic";

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

// TrendChart expects `period: string`. weeklyGrowth/weeklySeries return rows
// with `period: string` (date) already — but the TrendChart format wants
// (period, bank_type_code, value) which matches WeeklyRow. The component
// types differ slightly so cast.
function adaptWeekly(rows: WeeklyRow[]): { period: string; bank_type_code: string; value: number }[] {
  return rows.map((r) => ({ period: r.period, bank_type_code: r.bank_type_code, value: r.value }));
}

export default async function WeeklyPage() {
  const TOPLAM_KREDILER = { category: "krediler", item_id: "1.0.1" };
  const HOUSING   = { category: "krediler", item_id: "1.0.4" };
  const AUTO      = { category: "krediler", item_id: "1.0.5" };
  const GPL       = { category: "krediler", item_id: "1.0.6" };
  const RETAIL_CARDS = { category: "krediler", item_id: "1.0.8" };
  const SME       = { category: "krediler", item_id: "1.0.11" };
  const COMMERCIAL = { category: "krediler", item_id: "1.0.12" };
  const TOPLAM_MEVDUAT = { category: "mevduat", item_id: "4.0.1" };
  const NPL = { category: "takipteki_alacaklar", item_id: "2.0.1" };

  const all = Object.values(WEEKLY_BANK_TYPES);
  const sectorOnly = [WEEKLY_BANK_TYPES.SECTOR];
  const pubPriv = [WEEKLY_BANK_TYPES.PRIVATE, WEEKLY_BANK_TYPES.STATE];

  const [
    loansLevel, loans4w, loans13w,
    depsLevel, deps4w, deps13w,
    nplLevel, nplYoY,
    // currency split: TL & FX 4w for sector
    loans4wTL, loans4wFX,
    // pub-vs-priv TL 4w
    loans4wTLpubpriv,
    // consumer segments 13w (sector)
    g13Housing, g13Auto, g13Gpl, g13Cards,
    // SME + Commercial 13w
    g13Sme, g13Commercial,
  ] = await Promise.all([
    weeklySeries(TOPLAM_KREDILER.category, TOPLAM_KREDILER.item_id, "TOTAL", all, 156),
    weeklyGrowth(TOPLAM_KREDILER.category, TOPLAM_KREDILER.item_id, "TOTAL", 4, all, 104),
    weeklyGrowth(TOPLAM_KREDILER.category, TOPLAM_KREDILER.item_id, "TOTAL", 13, all, 104),
    weeklySeries(TOPLAM_MEVDUAT.category, TOPLAM_MEVDUAT.item_id, "TOTAL", all, 156),
    weeklyGrowth(TOPLAM_MEVDUAT.category, TOPLAM_MEVDUAT.item_id, "TOTAL", 4, all, 104),
    weeklyGrowth(TOPLAM_MEVDUAT.category, TOPLAM_MEVDUAT.item_id, "TOTAL", 13, all, 104),
    weeklySeries(NPL.category, NPL.item_id, "TOTAL", all, 156),
    weeklyGrowth(NPL.category, NPL.item_id, "TOTAL", 52, all, 104),
    weeklyGrowth(TOPLAM_KREDILER.category, TOPLAM_KREDILER.item_id, "TL", 4, sectorOnly, 104),
    weeklyGrowth(TOPLAM_KREDILER.category, TOPLAM_KREDILER.item_id, "FX", 4, sectorOnly, 104),
    weeklyGrowth(TOPLAM_KREDILER.category, TOPLAM_KREDILER.item_id, "TL", 4, pubPriv, 104),
    weeklyGrowth(HOUSING.category, HOUSING.item_id, "TOTAL", 13, sectorOnly, 104),
    weeklyGrowth(AUTO.category, AUTO.item_id, "TOTAL", 13, sectorOnly, 104),
    weeklyGrowth(GPL.category, GPL.item_id, "TOTAL", 13, sectorOnly, 104),
    weeklyGrowth(RETAIL_CARDS.category, RETAIL_CARDS.item_id, "TOTAL", 13, sectorOnly, 104),
    weeklyGrowth(SME.category, SME.item_id, "TOTAL", 13, sectorOnly, 104),
    weeklyGrowth(COMMERCIAL.category, COMMERCIAL.item_id, "TOTAL", 13, sectorOnly, 104),
  ]);

  // Combine TL & FX into one long-form data array for the two-line chart
  const tlVsFx = [
    ...loans4wTL.map((r) => ({ period: r.period, bank_type_code: "TL", value: r.value })),
    ...loans4wFX.map((r) => ({ period: r.period, bank_type_code: "FX", value: r.value })),
  ];

  // Consumer segments combined
  const consumerSegments = [
    ...g13Housing.map((r) => ({ period: r.period, bank_type_code: "HOUSING", value: r.value })),
    ...g13Auto.map((r) => ({ period: r.period, bank_type_code: "AUTO", value: r.value })),
    ...g13Gpl.map((r) => ({ period: r.period, bank_type_code: "GPL", value: r.value })),
    ...g13Cards.map((r) => ({ period: r.period, bank_type_code: "CARDS", value: r.value })),
  ];

  // SME vs Commercial combined
  const smeVsCommercial = [
    ...g13Sme.map((r) => ({ period: r.period, bank_type_code: "SME", value: r.value })),
    ...g13Commercial.map((r) => ({ period: r.period, bank_type_code: "COMMERCIAL", value: r.value })),
  ];

  return (
    <main className="px-8 py-8 space-y-8">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Weekly Trends</h1>
        <p className="text-sm text-neutral-500">
          BDDK weekly bulletin · loans, deposits, NPL · annualized 4-week and 13-week growth · by bank group
        </p>
      </header>

      <Section title="Loans">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <TrendChart
            data={adaptWeekly(loansLevel)}
            seriesLabels={WEEKLY_BANK_TYPE_LABELS}
            title="Total Loans — Level (TL bn)"
            yFormat="bn"
            decimals={0}
          />
          <TrendChart
            data={adaptWeekly(loans4w)}
            seriesLabels={WEEKLY_BANK_TYPE_LABELS}
            title="Loan Growth 4w (annualized %)"
            yFormat="pct"
            decimals={1}
            zeroLine
          />
          <TrendChart
            data={adaptWeekly(loans13w)}
            seriesLabels={WEEKLY_BANK_TYPE_LABELS}
            title="Loan Growth 13w (annualized %)"
            yFormat="pct"
            decimals={1}
            zeroLine
          />
        </div>
      </Section>

      <Section title="Currency & Ownership Differentiators" subtitle="How 4-week momentum splits across currency and public-vs-private banks (sector only for currency).">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TrendChart
            data={tlVsFx}
            seriesLabels={{ TL: "TL Loans", FX: "FX Loans (TL eq.)" }}
            title="Loan Growth 4w — TL vs FX (sector, ann.)"
            yFormat="pct"
            decimals={1}
            zeroLine
          />
          <TrendChart
            data={adaptWeekly(loans4wTLpubpriv)}
            seriesLabels={{
              [WEEKLY_BANK_TYPES.PRIVATE]: "Private",
              [WEEKLY_BANK_TYPES.STATE]: "State",
            }}
            title="TL Loan Growth 4w — Public vs Private (ann.)"
            yFormat="pct"
            decimals={1}
            zeroLine
          />
        </div>
      </Section>

      <Section title="Consumer Segments" subtitle="13-week annualized growth per product, sector only — cards & GPL drive cycle.">
        <TrendChart
          data={consumerSegments}
          seriesLabels={{
            HOUSING: "Housing",
            AUTO: "Auto",
            GPL: "Gen. Purpose",
            CARDS: "Retail Cards",
          }}
          title="Consumer Segment Growth 13w (annualized %)"
          yFormat="pct"
          decimals={1}
          zeroLine
          height={320}
        />
      </Section>

      <Section title="SME vs Commercial" subtitle="Cycle-leading indicators for non-household credit growth.">
        <TrendChart
          data={smeVsCommercial}
          seriesLabels={{ SME: "SME", COMMERCIAL: "Commercial (incl. corp.)" }}
          title="SME vs Commercial Growth 13w (annualized %)"
          yFormat="pct"
          decimals={1}
          zeroLine
          height={320}
        />
      </Section>

      <Section title="Deposits">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <TrendChart
            data={adaptWeekly(depsLevel)}
            seriesLabels={WEEKLY_BANK_TYPE_LABELS}
            title="Total Deposits — Level (TL bn)"
            yFormat="bn"
            decimals={0}
          />
          <TrendChart
            data={adaptWeekly(deps4w)}
            seriesLabels={WEEKLY_BANK_TYPE_LABELS}
            title="Deposit Growth 4w (annualized %)"
            yFormat="pct"
            decimals={1}
            zeroLine
          />
          <TrendChart
            data={adaptWeekly(deps13w)}
            seriesLabels={WEEKLY_BANK_TYPE_LABELS}
            title="Deposit Growth 13w (annualized %)"
            yFormat="pct"
            decimals={1}
            zeroLine
          />
        </div>
      </Section>

      <Section title="Asset Quality">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TrendChart
            data={adaptWeekly(nplLevel)}
            seriesLabels={WEEKLY_BANK_TYPE_LABELS}
            title="NPL Stock — Level (TL bn)"
            yFormat="bn"
            decimals={0}
          />
          <TrendChart
            data={adaptWeekly(nplYoY)}
            seriesLabels={WEEKLY_BANK_TYPE_LABELS}
            title="NPL Growth YoY (%)"
            yFormat="pct"
            decimals={1}
            zeroLine
          />
        </div>
      </Section>
    </main>
  );
}
