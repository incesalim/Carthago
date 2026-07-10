/**
 * Capital tab — CAR, equity level + growth, leverage.
 */
import type { Metadata } from "next";
import {
  ratioCar,
  ratioRwaDensity,
  ratioOffBsDerivatives,
  totalEquity,
  equityYoY,
  totalAssetsYoY,
  leverage,
  latestPerBank,
  latestPeriod,
  PRIMARY_BANK_TYPES,
  BANK_TYPES,
  BANK_TYPE_LABELS,
} from "@/app/lib/metrics";
import { sectorCapitalRatios, perBankCapital, AUDIT_CAPITAL_LABELS } from "@/app/lib/audit-ratios";
import { PageHeader, Stat } from "@/app/components/ui";
import BarByBank from "@/app/components/BarByBank";
import CapitalByBank from "./CapitalByBank";
import TrendChart from "@/app/components/TrendChart";
import Takeaway from "@/app/components/Takeaway";
import { capitalInsights } from "@/app/lib/insights";
import { withLlmHeadline } from "@/app/lib/read-headlines";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkish Banks — Capital Adequacy (CAR)",
  description: "Capital adequacy of Türkiye's banking sector: CAR/SYR, Tier 1 and leverage by bank and ownership group, from BRSA data.",
  alternates: { canonical: "/capital" },
};

export default async function CapitalPage() {
  const sector = [BANK_TYPES.SECTOR];
  const groups = PRIMARY_BANK_TYPES.filter((c) => c !== BANK_TYPES.SECTOR);

  const [
    carAll, carByBank, equity, equityYoYSec, lev,
    rwa, offBsDeriv, capRatios, assetsYoYSec, byBankCap,
  ] = await Promise.all([
    ratioCar(PRIMARY_BANK_TYPES),
    latestPerBank(ratioCar, groups),
    totalEquity(sector),
    equityYoY(sector),
    leverage(PRIMARY_BANK_TYPES),
    ratioRwaDensity(PRIMARY_BANK_TYPES),
    ratioOffBsDerivatives(PRIMARY_BANK_TYPES),
    sectorCapitalRatios(),
    totalAssetsYoY(sector),
    perBankCapital(),
  ]);

  // Headroom (display-study Phase 3): naive-extrapolation sizing of the CAR
  // buffer — where does the floor land if the last 12 months' drift persists?
  const CAR_MIN = 12;
  const carSector = carAll.filter((r) => r.bank_type_code === BANK_TYPES.SECTOR);
  const carNow = carSector.at(-1)?.value ?? null;
  const carYearAgo = carSector.at(-13)?.value ?? null;
  const buffer = carNow != null ? carNow - CAR_MIN : null;
  const drift = carNow != null && carYearAgo != null ? carNow - carYearAgo : null; // pp per year
  const quartersToFloor =
    buffer != null && drift != null && drift < 0 ? (buffer / -drift) * 4 : null;
  const eqG = equityYoYSec.at(-1)?.value ?? null;
  const asG = assetsYoYSec.at(-1)?.value ?? null;
  const genGap = eqG != null && asG != null ? eqG - asG : null;

  // "The Read" — deterministic, computed from the same series the charts show.
  const read = capitalInsights({
    car: carAll.filter((r) => r.bank_type_code === BANK_TYPES.SECTOR),
    cet1: capRatios.filter((r) => r.bank_type_code === "CET1"),
    equityYoY: equityYoYSec,
    leverage: lev.filter((r) => r.bank_type_code === BANK_TYPES.SECTOR),
  });

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      <PageHeader
        title="Capital"
        description="Capital adequacy + equity + leverage · BDDK · regulatory min CAR = 12%"
        rangeSelector
        dataThrough={latestPeriod(carAll, equity, lev)}
      />

      <Takeaway data={await withLlmHeadline("capital", read)} />

      <section className="space-y-4">
        <div className="space-y-0.5">
          <h2 className="text-base font-semibold text-foreground">Capital Adequacy</h2>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2">
            <TrendChart
              data={carAll}
              seriesLabels={BANK_TYPE_LABELS}
              title="Capital Adequacy Ratio (%) — by group"
              yFormat="pct"
              decimals={1}            />
          </div>
          <BarByBank
            data={carByBank}
            labels={BANK_TYPE_LABELS}
            title={`CAR by group · ${carByBank[0]?.period ?? ""}`}
            format="pct"
            decimals={1}
          />
        </div>
      </section>

      {buffer != null && (
        <section className="space-y-4">
          <div className="space-y-0.5">
            <h2 className="text-base font-semibold text-foreground">Headroom</h2>
            <p className="text-xs text-muted-foreground">
              Where the buffer goes if the last 12 months simply repeat — a sizing
              device (straight-line extrapolation), not a forecast. Capital generation
              gap = equity growth − asset growth; negative means the balance sheet is
              outgrowing its capital.
            </p>
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <Stat
              label="Buffer over 12% minimum"
              value={`${buffer.toFixed(1)}pp`}
              hint={`CAR ${carNow!.toFixed(1)}%`}
              tone={buffer < 2 ? "warning" : buffer >= 4 ? "positive" : "neutral"}
            />
            <Stat
              label="12-month drift"
              value={drift != null ? `${drift >= 0 ? "+" : ""}${drift.toFixed(1)}pp / yr` : "—"}
              tone={drift != null && drift < -0.5 ? "warning" : "neutral"}
            />
            <Stat
              label="At current drift"
              value={
                quartersToFloor != null
                  ? `floor in ~${Math.round(quartersToFloor)} qtrs`
                  : "buffer holding"
              }
              tone={quartersToFloor != null && quartersToFloor < 8 ? "warning" : "neutral"}
            />
            <Stat
              label="Capital generation gap"
              value={genGap != null ? `${genGap >= 0 ? "+" : ""}${genGap.toFixed(1)}pp` : "—"}
              hint={eqG != null && asG != null ? `equity ${eqG.toFixed(0)}% vs assets ${asG.toFixed(0)}% y/y` : undefined}
              tone={genGap != null && genGap < 0 ? "warning" : "positive"}
            />
          </div>
        </section>
      )}

      <section className="space-y-4">
        <div className="space-y-0.5">
          <h2 className="text-base font-semibold text-foreground">Capital composition (audited §4)</h2>
          <p className="text-xs text-muted-foreground">
            CET1 and Tier-1 ratios from the quarterly BRSA reports — aggregated Σ capital
            ÷ Σ RWA across reporting banks. The monthly bulletin carries only total CAR;
            CET1 is the Basel III / BBVA capital headline.
          </p>
        </div>
        <TrendChart
          data={capRatios}
          seriesLabels={AUDIT_CAPITAL_LABELS}
          title="CET1 / Tier-1 / Total CAR (%) — sector, audited quarterly"
          yFormat="pct"
          decimals={1}
          height={320}
        />
      </section>

      <CapitalByBank period={byBankCap.period} rows={byBankCap.rows} />

      <section className="space-y-4">
        <div className="space-y-0.5">
          <h2 className="text-base font-semibold text-foreground">Equity & Leverage</h2>
          <p className="text-xs text-muted-foreground">Sector equity level, growth, and gearing.</p>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <TrendChart
            data={equity}
            seriesLabels={{ [BANK_TYPES.SECTOR]: "Equity" }}
            title="Total Equity — Level (sector)"
            yFormat="trn"
            decimals={2}          />
          <TrendChart
            data={equityYoYSec}
            seriesLabels={{ [BANK_TYPES.SECTOR]: "Equity YoY" }}
            title="Equity Growth YoY (%)"
            yFormat="pct"
            decimals={1}
            zeroLine          />
          <TrendChart
            data={lev}
            seriesLabels={BANK_TYPE_LABELS}
            title="Liabilities / Equity (%)"
            yFormat="pct"
            decimals={0}          />
        </div>
      </section>

      <section className="space-y-4">
        <div className="space-y-0.5">
          <h2 className="text-base font-semibold text-foreground">Risk Density</h2>
          <p className="text-xs text-muted-foreground">
            How concentrated each group&apos;s balance-sheet risk is — lower RWA-net/gross
            means more low-weight exposure (govt bonds, cash). Off-BS derivatives /
            total assets shows derivative book size relative to balance sheet.
          </p>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TrendChart
            data={rwa}
            seriesLabels={BANK_TYPE_LABELS}
            title="RWA Net / Gross (%)"
            yFormat="pct"
            decimals={1}          />
          <TrendChart
            data={offBsDeriv}
            seriesLabels={BANK_TYPE_LABELS}
            title="Off-Balance-Sheet Derivatives / Total Assets (%)"
            yFormat="pct"
            decimals={1}          />
        </div>
      </section>

    </main>
  );
}
