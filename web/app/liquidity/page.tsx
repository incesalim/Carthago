/**
 * Liquidity tab — adapts the liquidity section of the BBVA (Garanti BBVA
 * Research) "Türkiye Banking Sector Outlook" into our data.
 *
 * Structure mirrors the report: TL funding, FC & dollarization, CBRT
 * reserves/funding, and the real-appreciation backdrop. Public-vs-private
 * cuts follow BBVA's framing (Public = state banks; Private = private +
 * foreign banks) — see LIQ_OWNERSHIP in lib/metrics.ts.
 *
 * TCMB publishes NO net-reserves headline (only gross AB.TOPLAM + the IMF
 * reserve-template components), so NIR is DERIVED from the analytical balance
 * sheet (FX assets TP.BL054 − FX liabilities TP.BL122, converted to USD). The
 * swap SPOT leg sits in BL054 (verified: net moves with it), so it is split
 * into with-/excluding-swaps via the forward/swap short position from the IMF
 * template (TP.DOVVARNC.K15, monthly): net-excluding-swaps = NIR − |K15|.
 *
 * Out of scope (no data source here): investment-fund volumes/flows & fund
 * dollarization (TEFAS lacks an FC-fund category), under-the-mattress gold stock
 * and weekly reserve-flow attribution (BBVA-proprietary estimates), and the FCI
 * composite (Bloomberg inputs).
 */
import type { Metadata } from "next";
import Link from "next/link";
import {
  weeklyOwnershipRatio,
  weeklyGrowth,
  weeklyGrowthByOwnership,
  weeklyDollarization,
  evdsMulti,
  evdsSeries,
  latestPeriod,
  WEEKLY_BANK_TYPES,
  LIQ_OWNERSHIP_LABELS,
  LIQ_DOLLARIZATION_LABELS,
  type TimeSeriesRow,
  type WeeklyRow,
  type EvdsRow,
} from "@/app/lib/metrics";
import { sectorLiquidityRatios, AUDIT_LIQUIDITY_LABELS } from "@/app/lib/audit-ratios";
import { Section } from "@/app/components/ui";
import {
  Colophon,
  Depth,
  DeskHeader,
  SecHead,
  Vital,
  Vitals,
} from "@/app/components/desk";
import { lastVal, monthLabel, signedPp, windowExtremes } from "@/app/lib/desk";
import { GlobalRangeSelector } from "@/app/components/range-context";
import TrendChart from "@/app/components/TrendChart";
import TimeSeriesChart from "@/app/components/TimeSeriesChart";
import Takeaway from "@/app/components/Takeaway";
import { liquidityInsights } from "@/app/lib/insights";
import { seriesFinding } from "@/app/lib/chart-findings";
import { withLlmHeadline } from "@/app/lib/read-headlines";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkish Banks — Liquidity & Funding",
  description: "Liquidity and funding of Türkiye's banks: loan-to-deposit, LCR, FX liquidity and the deposit base from BDDK and BRSA data.",
  alternates: { canonical: "/liquidity" },
};

// Long-form rows → TrendChart points (structurally identical; keeps types tidy).
function toTrend(rows: (TimeSeriesRow | WeeklyRow)[]): { period: string; bank_type_code: string; value: number }[] {
  return rows.map((r) => ({ period: r.period, bank_type_code: r.bank_type_code, value: r.value }));
}

// EVDS rows → TimeSeriesChart points, scaling the value (e.g. /1000 → bn).
function toPoints(rows: EvdsRow[], scale = 1): { period_date: string; value: number }[] {
  return rows.map((r) => ({ period_date: r.period_date, value: r.value * scale }));
}

// Sum several EVDS series by date (used for FX cash = USD + EUR-eq deposits).
function sumByDate(sets: EvdsRow[][], scale = 1): { period_date: string; value: number }[] {
  const acc = new Map<string, number>();
  for (const set of sets) {
    for (const r of set) acc.set(r.period_date, (acc.get(r.period_date) ?? 0) + r.value);
  }
  return Array.from(acc.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([period_date, v]) => ({ period_date, value: v * scale }));
}

/** '2026-03…' → 'Q1 2026' for the audited-quarter basis note. */
function quarterLabel(p: string | null | undefined): string {
  const m = p ? /^(\d{4})-(\d{2})/.exec(p) : null;
  return m ? `Q${Math.ceil(Number(m[2]) / 3)} ${m[1]}` : "latest quarter";
}

/** Value ~a year (364 d) before the latest point, paired by DATE not row offset. */
function valYearAgoByDate(s: { period: string; value: number | null }[]): number | null {
  const last = s.at(-1)?.period;
  if (!last) return null;
  const d = new Date(last);
  d.setUTCDate(d.getUTCDate() - 364);
  const cut = d.toISOString().slice(0, 10);
  for (let i = s.length - 1; i >= 0; i--) {
    if (s[i].period <= cut) return s[i].value;
  }
  return null;
}

/** Trailing ~year of points (sparkline window for weekly/daily cadences). */
function lastYearWindow<T extends { period: string }>(s: T[]): T[] {
  const last = s.at(-1)?.period;
  if (!last) return s;
  const d = new Date(last);
  d.setUTCDate(d.getUTCDate() - 364);
  const cut = d.toISOString().slice(0, 10);
  return s.filter((r) => r.period >= cut);
}

export default async function LiquidityPage() {
  const LOANS = { category: "krediler", item_id: "1.0.1" };
  const DEPOSITS = { category: "mevduat", item_id: "4.0.1" };

  const [
    tlLtd, fcLtd,
    tlGrowthYoY, tlGrowth13w, tlGrowthOwn,
    dollarization,
    evds, reer, liqRatios,
  ] = await Promise.all([
    // Loan-to-deposit ratios, public vs private
    weeklyOwnershipRatio(LOANS.category, LOANS.item_id, DEPOSITS.category, DEPOSITS.item_id, "TL"),
    weeklyOwnershipRatio(LOANS.category, LOANS.item_id, DEPOSITS.category, DEPOSITS.item_id, "FX"),
    // TL deposit growth — sector YoY (52w) + 13-week annualized momentum, plus
    // a public-vs-private 13w cut. Mirrors BBVA's two TL-deposit-growth panels.
    weeklyGrowth(DEPOSITS.category, DEPOSITS.item_id, "TL", 52, [WEEKLY_BANK_TYPES.SECTOR]),
    weeklyGrowth(DEPOSITS.category, DEPOSITS.item_id, "TL", 13, [WEEKLY_BANK_TYPES.SECTOR]),
    weeklyGrowthByOwnership(DEPOSITS.category, DEPOSITS.item_id, "TL", 13),
    // Deposit dollarization (sector / public / private)
    weeklyDollarization(),
    // CBRT funding + reserves + residents' FC (EVDS, already in D1). BL054/BL122
    // are the analytical-balance-sheet FX assets/liabilities for derived NIR;
    // DK.USD.A converts them from TL to USD; DOVVARNC.K15 is the forward/swap
    // short position used to split NIR into with-/excluding-swaps.
    evdsMulti(
      ["TP.APIFON3", "TP.AB.TOPLAM", "TP.BL054", "TP.BL122", "TP.DK.USD.A",
       "TP.DOVVARNC.K15",
       "TP.HPBITABLO4.4", "TP.HPBITABLO4.5", "TP.HPBITABLO4.7"],
      3,
    ),
    // REER over a longer horizon to show the real-appreciation trend
    evdsSeries("TP.RK.T1.Y", 8),
    // Audited §4 regulatory-liquidity ratios (LCR/NSFR/leverage), sector view
    sectorLiquidityRatios(),
  ]);

  // EVDS-derived series. APIFON3 is million TL → TrendChart "bn" divides by 1000.
  const netFunding = (evds["TP.APIFON3"] ?? []).map((r) => ({
    period: r.period_date,
    bank_type_code: "NETFUND",
    value: r.value,
  }));

  // TL deposit growth — merge sector YoY + 13w annualized into one chart.
  const tlDepGrowth = [
    ...tlGrowthYoY.map((r) => ({ period: r.period, bank_type_code: "YOY", value: r.value })),
    ...tlGrowth13w.map((r) => ({ period: r.period, bank_type_code: "W13", value: r.value })),
  ];

  // Reserves & residents' FC are in USD millions → /1000 for USD bn.
  // Derived net international reserves: (FX assets − FX liabilities) from the
  // CBRT analytical balance sheet (both TL thousand, weekly), converted to USD
  // bn at the same-date USD/TRY. (BL054−BL122) / USDTRY / 1e6 = USD bn. The
  // swap SPOT leg sits in BL054 (verified: net FX position moves with it), so
  // this net position INCLUDES swap FX.
  const usdMap = new Map((evds["TP.DK.USD.A"] ?? []).map((r) => [r.period_date, r.value]));
  const bl122Map = new Map((evds["TP.BL122"] ?? []).map((r) => [r.period_date, r.value]));
  const nir = (evds["TP.BL054"] ?? [])
    .filter((r) => bl122Map.has(r.period_date) && usdMap.get(r.period_date))
    .map((r) => ({
      period_date: r.period_date,
      value: (r.value - bl122Map.get(r.period_date)!) / usdMap.get(r.period_date)! / 1e6,
    }));
  // Forward/swap short position (IMF reserve template §2.2.1, monthly, USD m,
  // negative) = the off-BS FX owed forward, dominated by swaps. Net-excl-swaps
  // = NIR − |K15|. Stepped onto the weekly NIR dates (nearest-earlier month).
  const fwdRows = evds["TP.DOVVARNC.K15"] ?? [];
  const fwdBnAt = (date: string): number => {
    for (let i = fwdRows.length - 1; i >= 0; i--) {
      if (fwdRows[i].period_date <= date) return Math.abs(fwdRows[i].value) / 1000;
    }
    return 0;
  };
  const nirExSwaps = nir.map((p) => ({
    period_date: p.period_date,
    value: p.value - fwdBnAt(p.period_date),
  }));
  const reserves = {
    "Gross reserves": toPoints(evds["TP.AB.TOPLAM"] ?? [], 1 / 1000),
    "Net int'l reserves": nir,
    "Net excl. swaps": nirExSwaps,
  };
  const residentsFc = {
    "FX cash (USD + EUR)": sumByDate(
      [evds["TP.HPBITABLO4.4"] ?? [], evds["TP.HPBITABLO4.5"] ?? []],
      1 / 1000,
    ),
    "Precious metals": toPoints(evds["TP.HPBITABLO4.7"] ?? [], 1 / 1000),
  };
  const reerSeries = { "REER (CPI based, 2003=100)": toPoints(reer) };

  // ---- vitals — every figure computed from the series fetched above --------
  const lcrS = liqRatios.filter((r) => r.bank_type_code === "LCR");
  const nsfrS = liqRatios.filter((r) => r.bank_type_code === "NSFR");
  const tlLdrPub = tlLtd.filter((r) => r.bank_type_code === "PUBLIC");
  const tlLdrPriv = tlLtd.filter((r) => r.bank_type_code === "PRIVATE");
  const dollSector = dollarization.filter((r) => r.bank_type_code === "SECTOR");
  const netFundingBn = netFunding.map((r) => ({ period: r.period, value: r.value / 1000 }));

  const lcrNow = lastVal(lcrS);
  const nsfrNow = lastVal(nsfrS);
  const pubNow = lastVal(tlLdrPub);
  const privNow = lastVal(tlLdrPriv);
  const dollNow = lastVal(dollSector);
  const fundNow = lastVal(netFundingBn);

  const lcrFloor = lcrNow != null ? lcrNow - 100 : null; // regulatory floor 100%
  const nsfrFloor = nsfrNow != null ? nsfrNow - 100 : null; // regulatory floor 100%
  const pubPrivGap = pubNow != null && privNow != null ? pubNow - privNow : null;
  const privRange = windowExtremes(tlLdrPriv, 52);
  const dollYearAgo = valYearAgoByDate(dollSector);
  const dollYoY = dollNow != null && dollYearAgo != null ? dollNow - dollYearAgo : null;

  const auditQ = quarterLabel(lcrS.at(-1)?.period ?? liqRatios.at(-1)?.period);
  const recMonth = monthLabel(latestPeriod(tlLtd, fcLtd, dollarization, netFunding));

  // "The Read" — deterministic, computed from the same series the charts show.
  const read = liquidityInsights({
    tlLdrPublic: toTrend(tlLtd).filter((r) => r.bank_type_code === "PUBLIC"),
    tlLdrPrivate: toTrend(tlLtd).filter((r) => r.bank_type_code === "PRIVATE"),
    dollarization: toTrend(dollarization).filter((r) => r.bank_type_code === "SECTOR"),
    netCbrtFunding: netFunding,
    lcr: liqRatios.filter((r) => r.bank_type_code === "LCR"),
  });

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title="Liquidity"
        record={
          <>
            Record <b className="font-normal text-foreground">{recMonth}</b> · {auditQ} filings + weekly
          </>
        }
        right="every figure computed from source series"
      />

      {/* ── The vitals ─────────────────────────────────────────────────── */}
      <SecHead
        title="The vitals"
        meta="weekly bulletin + evds + audited §4"
        className="mb-2.5 mt-6"
      />
      <Vitals>
        <Vital
          label="LCR"
          value={lcrNow != null ? lcrNow.toFixed(0) : "—"}
          unit="%"
          series={lcrS.slice(-13)}
          decimals={0}
          note={
            lcrFloor != null ? (
              <>
                <b
                  className={
                    lcrFloor >= 0 ? "font-semibold text-positive" : "font-semibold text-negative"
                  }
                >
                  {signedPp(lcrFloor, 0)}
                </b>{" "}
                vs the 100% floor · audited {auditQ}
              </>
            ) : undefined
          }
        />
        <Vital
          label="NSFR"
          value={nsfrNow != null ? nsfrNow.toFixed(0) : "—"}
          unit="%"
          series={nsfrS.slice(-13)}
          decimals={0}
          note={
            nsfrFloor != null ? (
              <>
                <b
                  className={
                    nsfrFloor >= 0 ? "font-semibold text-positive" : "font-semibold text-negative"
                  }
                >
                  {signedPp(nsfrFloor, 0)}
                </b>{" "}
                vs the 100% floor · audited {auditQ}
              </>
            ) : undefined
          }
        />
        <Vital
          label="TL loan / deposit — public"
          value={pubNow != null ? pubNow.toFixed(1) : "—"}
          unit="%"
          series={lastYearWindow(tlLdrPub)}
          decimals={1}
          note={
            pubPrivGap != null ? (
              <>
                {pubPrivGap >= 0
                  ? `${pubPrivGap.toFixed(1)}pp above`
                  : `${Math.abs(pubPrivGap).toFixed(1)}pp below`}{" "}
                private
              </>
            ) : undefined
          }
        />
        <Vital
          label="TL loan / deposit — private"
          value={privNow != null ? privNow.toFixed(1) : "—"}
          unit="%"
          series={lastYearWindow(tlLdrPriv)}
          decimals={1}
          note={
            privRange ? (
              <>
                52w range {privRange.min.toFixed(0)}–{privRange.max.toFixed(0)}%
              </>
            ) : undefined
          }
        />
        <Vital
          label="FC share of deposits"
          value={dollNow != null ? dollNow.toFixed(1) : "—"}
          unit="%"
          series={lastYearWindow(dollSector)}
          decimals={1}
          note={
            dollYoY != null ? (
              <>
                <b
                  className={
                    dollYoY <= 0 ? "font-semibold text-positive" : "font-semibold text-negative"
                  }
                >
                  {signedPp(dollYoY, 1)}
                </b>{" "}
                y/y{" "}
                <Link href="/deposits" className="font-semibold text-primary">
                  /deposits
                </Link>
              </>
            ) : undefined
          }
        />
        <Vital
          label="Net CBRT funding"
          value={fundNow != null ? fundNow.toFixed(0) : "—"}
          unit="₺bn"
          series={lastYearWindow(netFundingBn)}
          format="raw"
          decimals={0}
          note={
            fundNow != null ? (
              <>{fundNow >= 0 ? "+ excess" : "− lack"} of TL liquidity in the system</>
            ) : undefined
          }
        />
      </Vitals>

      {/* ── In depth — the evidence layer ──────────────────────────────── */}
      <Depth action={<GlobalRangeSelector />}>
        <Takeaway data={await withLlmHeadline("liquidity", read)} />

        <Section
          title="TL Funding"
          description="Loan-to-deposit pressure and TL deposit inflows — public vs private. Full maturity/demand breakdown lives on the Deposits tab."
        >
          <TrendChart
            data={toTrend(tlLtd)}
            seriesLabels={LIQ_OWNERSHIP_LABELS}
            title="TL Loan / Deposit Ratio (%) — public vs private"
            yFormat="pct"
            decimals={0}
            height={320}
          />
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <TrendChart
              data={tlDepGrowth}
              seriesLabels={{ YOY: "YoY", W13: "13-week annualized" }}
              title="TL Deposit Growth — sector (YoY & 13w annualized, %)"
              yFormat="pct"
              decimals={0}
              zeroLine
            />
            <TrendChart
              data={toTrend(tlGrowthOwn)}
              seriesLabels={LIQ_OWNERSHIP_LABELS}
              title="TL Deposit Growth — public vs private (13w annualized, %)"
              yFormat="pct"
              decimals={0}
              zeroLine
            />
          </div>
        </Section>

        <Section
          title="FC & Dollarization"
          description="Foreign-currency funding pressure and households' appetite for FC savings vs TL."
        >
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <TrendChart
              data={toTrend(fcLtd)}
              seriesLabels={LIQ_OWNERSHIP_LABELS}
              title="FC Loan / Deposit Ratio (%) — public vs private"
              yFormat="pct"
              decimals={0}
            />
            <TrendChart
              data={toTrend(dollarization)}
              seriesLabels={LIQ_DOLLARIZATION_LABELS}
              title={
                seriesFinding(toTrend(dollarization).filter((r) => r.bank_type_code === "SECTOR"), { noun: "Deposit dollarization", decimals: 1 }) ??
                "Deposit Dollarization — FC share of deposits (%)"
              }
              description="FC share of total deposits, %, weekly · sector / public / private"
              source="Source: BDDK weekly bulletin"
              yFormat="pct"
              decimals={1}
            />
          </div>
          <TimeSeriesChart
            series={residentsFc}
            title="Residents' FC Savings — households (USD bn)"
            yFormat="raw"
            decimals={0}
          />
        </Section>

        <Section
          title="CBRT Liquidity & Reserves"
          description="System TL liquidity stance and the central bank's FX reserve buffer. Net reserves are derived from the analytical balance sheet (FX assets − liabilities); gross − net is required-reserve FX, and net − net-excl-swaps is the CBRT swap stock."
        >
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <TrendChart
              data={netFunding}
              seriesLabels={{ NETFUND: "Net CBRT funding" }}
              title="Net CBRT Funding (TL bn) — + excess / − lack of TL liquidity"
              yFormat="bn"
              decimals={0}
              zeroLine
            />
            <TimeSeriesChart
              series={reserves}
              title="CBRT International Reserves (USD bn) — gross, net, net excl. swaps"
              yFormat="raw"
              decimals={0}
            />
          </div>
        </Section>

        <Section
          title="Regulatory Liquidity (audited §4)"
          description="LCR, NSFR and leverage from the quarterly BRSA reports — asset-weighted average across reporting banks. These Basel ratios aren't in the monthly bulletin; this is the per-bank §4 lane aggregated to the sector."
        >
          <TrendChart
            data={liqRatios}
            seriesLabels={AUDIT_LIQUIDITY_LABELS}
            title="LCR / NSFR / Leverage (%) — sector, audited quarterly"
            yFormat="pct"
            decimals={0}
            height={320}
          />
        </Section>

        <Section
          title="Macro Backdrop"
          description="Real appreciation eases financial conditions and supports the appetite for TL savings."
        >
          <TimeSeriesChart
            series={reerSeries}
            title="Real Effective Exchange Rate (CPI based, 2003 = 100)"
            yFormat="rate"
            decimals={1}
          />
        </Section>
      </Depth>

      <Colophon />
    </main>
  );
}
