/**
 * Capital tab — "The Desk" two-layer page.
 *
 * Layer 1 (the brief): the vitals band — CAR + buffer over the 12% regulatory
 * minimum, audited Tier-1 / CET1, equity growth vs asset growth (the capital
 * generation gap), RWA density and leverage — every note computed from the
 * same series the charts read.
 *
 * Layer 2 ("In depth"): the pre-Desk evidence — CAR by group, the headroom
 * sizing device, audited capital composition, the per-bank capital-adequacy
 * ranking, equity & leverage and risk density — carried over, restyled, not
 * removed.
 */
import type { Metadata } from "next";
import type { ReactNode } from "react";
import Link from "next/link";
import {
  ratioCar,
  ratioRwaDensity,
  ratioOffBsDerivatives,
  totalEquity,
  equityYoY,
  totalAssetsYoY,
  leverage,
  latestPerBank,
  PRIMARY_BANK_TYPES,
  BANK_TYPES,
  BANK_TYPE_LABELS,
} from "@/app/lib/metrics";
import { sectorCapitalRatios, perBankCapital, AUDIT_CAPITAL_LABELS } from "@/app/lib/audit-ratios";
import { Section, Stat } from "@/app/components/ui";
import BarByBank from "@/app/components/BarByBank";
import CapitalByBank from "./CapitalByBank";
import TrendChart from "@/app/components/TrendChart";
import Takeaway from "@/app/components/Takeaway";
import { capitalInsights } from "@/app/lib/insights";
import { seriesFinding } from "@/app/lib/chart-findings";
import { withLlmHeadline } from "@/app/lib/read-headlines";
import {
  ChartRow,
  Colophon,
  Depth,
  DeskHeader,
  SecHead,
  Vital,
  Vitals,
} from "@/app/components/desk";
import { lastVal, monthLabel, signedPp, valAgo } from "@/app/lib/desk";
import { GlobalRangeSelector } from "@/app/components/range-context";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkish Banks — Capital Adequacy (CAR)",
  description: "Capital adequacy of Türkiye's banking sector: CAR/SYR, Tier 1 and leverage by bank and ownership group, from BRSA data.",
  alternates: { canonical: "/capital" },
};

/** Route link styled for use inside a computed note. */
const Go = ({ href, children }: { href: string; children: ReactNode }) => (
  <Link href={href} className="font-semibold text-primary">
    {children}
  </Link>
);

/** '2026Q1' → 'Q1 2026' for the audited-quarter notes. */
function quarterLabel(p: string | null | undefined): string {
  const m = p ? /^(\d{4})Q([1-4])$/.exec(p) : null;
  return m ? `Q${m[2]} ${m[1]}` : p ?? "—";
}

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

  // ---- vitals — computed from the series above ------------------------------
  const t1Series = capRatios.filter((r) => r.bank_type_code === "TIER1");
  const cet1Series = capRatios.filter((r) => r.bank_type_code === "CET1");
  const rwaSector = rwa.filter((r) => r.bank_type_code === BANK_TYPES.SECTOR);
  const levSector = lev.filter((r) => r.bank_type_code === BANK_TYPES.SECTOR);

  const t1Now = lastVal(t1Series);
  const cet1Now = lastVal(cet1Series);
  const rwaNow = lastVal(rwaSector);
  const levNow = lastVal(levSector);

  const t1Ago = valAgo(t1Series, 4); // 4 audited quarters ≈ a year
  const t1Delta4q = t1Now != null && t1Ago != null ? t1Now - t1Ago : null;
  const rwaAgo = valAgo(rwaSector, 12);
  const rwaDrift = rwaNow != null && rwaAgo != null ? rwaNow - rwaAgo : null;
  const levX = levNow != null ? 1 + levNow / 100 : null; // assets/equity = 1 + L/E

  const recMonth = monthLabel(carSector.at(-1)?.period);
  const vsMonth = monthLabel(carSector.at(-2)?.period, false);
  const auditQ = quarterLabel(cet1Series.at(-1)?.period);

  // "The Read" — deterministic, computed from the same series the charts show.
  const read = capitalInsights({
    car: carSector,
    cet1: cet1Series,
    equityYoY: equityYoYSec,
    leverage: levSector,
  });

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title="Capital"
        record={
          <>
            Record <b className="font-normal text-foreground">{recMonth}</b> · vs {vsMonth}
          </>
        }
        right="every figure computed from source series"
      />

      {/* ── The vitals ─────────────────────────────────────────────────── */}
      <SecHead
        title="The vitals"
        meta="sector aggregate · monthly + audited quarterly"
        className="mb-2.5 mt-6"
      />
      <Vitals>
        <Vital
          label="Capital adequacy"
          value={carNow != null ? carNow.toFixed(1) : "—"}
          unit="%"
          series={carSector.slice(-13)}
          decimals={1}
          note={
            <>
              buffer{" "}
              <b
                className={
                  buffer != null && buffer >= 2
                    ? "font-semibold text-positive"
                    : "font-semibold text-negative"
                }
              >
                {buffer != null ? signedPp(buffer, 1) : "—"}
              </b>{" "}
              over the 12% min
              {drift != null && <> · drifting {signedPp(drift, 1)}/yr</>}
            </>
          }
        />
        <Vital
          label="Tier-1 (audited)"
          value={t1Now != null ? t1Now.toFixed(1) : "—"}
          unit="%"
          series={t1Series.slice(-8)}
          decimals={1}
          note={
            <>
              {t1Delta4q != null ? `${signedPp(t1Delta4q, 1)} over 4 audited qtrs` : `audited ${auditQ}`}
            </>
          }
        />
        <Vital
          label="CET1 (audited)"
          value={cet1Now != null ? cet1Now.toFixed(1) : "—"}
          unit="%"
          series={cet1Series.slice(-8)}
          decimals={1}
          note={<>audited {auditQ} · Σ capital ÷ Σ RWA</>}
        />
        <Vital
          label="Equity growth, y/y"
          value={eqG != null ? eqG.toFixed(1) : "—"}
          unit="%"
          series={equityYoYSec.slice(-13)}
          decimals={1}
          note={
            <>
              vs assets{" "}
              <b
                className={
                  genGap != null && genGap >= 0
                    ? "font-semibold text-positive"
                    : "font-semibold text-negative"
                }
              >
                {genGap != null ? signedPp(genGap, 1) : "—"}
              </b>{" "}
              generation gap <Go href="/profitability">/profitability</Go>
            </>
          }
        />
        <Vital
          label="RWA density"
          value={rwaNow != null ? rwaNow.toFixed(1) : "—"}
          unit="%"
          series={rwaSector.slice(-13)}
          decimals={1}
          note={<>{rwaDrift != null ? `${signedPp(rwaDrift, 1)} over 12m` : "—"} · RWA net / gross</>}
        />
        <Vital
          label="Liabilities / equity"
          value={levNow != null ? levNow.toFixed(0) : "—"}
          unit="%"
          series={levSector.slice(-13)}
          decimals={0}
          note={<>≈ {levX != null ? `${levX.toFixed(1)}×` : "—"} assets / equity</>}
        />
      </Vitals>

      {/* ── In depth — the evidence layer ──────────────────────────────── */}
      <Depth action={<GlobalRangeSelector />}>
        <Takeaway data={await withLlmHeadline("capital", read)} />

        <Section index="01" title="Capital Adequacy">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="lg:col-span-2">
              <TrendChart
                data={carAll}
                seriesLabels={BANK_TYPE_LABELS}
                title={
                  seriesFinding(carSector, { noun: "Capital adequacy", decimals: 1 }) ??
                  "Capital Adequacy Ratio (%) — by group"
                }
                description="Capital adequacy ratio (SYR), %, monthly · by ownership group · regulatory minimum 12%"
                source="Source: BDDK monthly bulletin"
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
        </Section>

        {buffer != null && (
          <Section
            index="02"
            title="Headroom"
            description="Where the buffer goes if the last 12 months simply repeat — a sizing device (straight-line extrapolation), not a forecast. Capital generation gap = equity growth − asset growth; negative means the balance sheet is outgrowing its capital."
          >
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
          </Section>
        )}

        <Section
          index="03"
          title="Capital composition (audited §4)"
          description="CET1 and Tier-1 ratios from the quarterly BRSA reports — aggregated Σ capital ÷ Σ RWA across reporting banks. The monthly bulletin carries only total CAR; CET1 is the Basel III / BBVA capital headline."
        >
          <ChartRow data={capRatios} labels={AUDIT_CAPITAL_LABELS} deltaPeriods={4} deltaLabel="4q" fmt={(v) => `${v.toFixed(1)}%`}>
            <TrendChart
              data={capRatios}
              seriesLabels={AUDIT_CAPITAL_LABELS}
              title="CET1 / Tier-1 / Total CAR (%) — sector, audited quarterly"
              yFormat="pct"
              decimals={1}
              height={320}
            />
          </ChartRow>
        </Section>

        <CapitalByBank index="04" period={byBankCap.period} rows={byBankCap.rows} />

        <Section
          index="05"
          title="Equity & Leverage"
          description="Sector equity level, growth, and gearing."
        >
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
        </Section>

        <Section
          index="06"
          title="Risk Density"
          description="How concentrated each group's balance-sheet risk is — lower RWA-net/gross means more low-weight exposure (govt bonds, cash). Off-BS derivatives / total assets shows derivative book size relative to balance sheet."
        >
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
        </Section>
      </Depth>

      <Colophon />
    </main>
  );
}
