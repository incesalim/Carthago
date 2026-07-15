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
  WEEKLY_BANK_TYPES,
  LIQ_OWNERSHIP_LABELS,
  LIQ_DOLLARIZATION_LABELS,
  type TimeSeriesRow,
  type WeeklyRow,
  type EvdsRow,
} from "@/app/lib/metrics";
import { sectorLiquidityRatios, AUDIT_LIQUIDITY_LABELS } from "@/app/lib/audit-ratios";
import {
  Ahead,
  ChartFoot,
  ChartRow,
  Colophon,
  Compare,
  Depth,
  DeskHeader,
  Flags,
  Levels,
  Movers,
  SecHead,
  Transmission,
  Vital,
  Vitals,
  type CompareRow,
  type Flag,
  type MoverRow,
  type TransmissionItem,
} from "@/app/components/desk";
import { lastVal, latestByGroup, monthLabel, signedPp, windowExtremes } from "@/app/lib/desk";
import { VERBS, bandsFor, direction, firstClaim } from "@/app/lib/prose";
import { aheadSlots } from "@/app/lib/ahead-data";
import { GlobalRangeSelector } from "@/app/components/range-context";
import TrendChart from "@/app/components/TrendChart";
import TimeSeriesChart from "@/app/components/TimeSeriesChart";
import ReserveBuffer, { type BufferPoint } from "@/app/liquidity/ReserveBuffer";
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

/** '2026-03…' or '2026Q1' (the audit lane's own format) → 'Q1 2026'. */
function quarterLabel(p: string | null | undefined): string {
  if (!p) return "latest quarter";
  const q = /^(\d{4})Q([1-4])$/.exec(p);
  if (q) return `Q${q[2]} ${q[1]}`;
  const m = /^(\d{4})-(\d{2})/.exec(p);
  return m ? `Q${Math.ceil(Number(m[2]) / 3)} ${m[1]}` : "latest quarter";
}

/** 'YYYY-MM-DD' → '03 Jul' — a weekly record needs its day, not just its month. */
function weekLabel(p: string | null | undefined, withYear = false): string {
  const m = p ? /^\d{4}-\d{2}-(\d{2})/.exec(p) : null;
  return m ? `${m[1]} ${monthLabel(p, withYear)}` : monthLabel(p, withYear);
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
  // What lands next — derived from the record periods + TCMB's published calendar.
  const ahead = await aheadSlots();

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
  // Gross / net / net-excl-swaps are no longer three lines on a shared axis —
  // they are the buffer DECOMPOSITION (see <ReserveBuffer/>), where the gaps
  // between them are named: the banks' required reserves and the swap stock.
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

  // "Both systems are pulling lira in at much the same pace" asserted a
  // CONVERGENCE with no threshold — the two could diverge 20pp and it would still
  // say so. The chart 40 lines up (pubPrivGap) already knew how to branch.
  const ownGrowth = [...latestByGroup(toTrend(tlGrowthOwn)).values()].map((v) => v.value);
  const ownSpread =
    ownGrowth.length >= 2 ? Math.max(...ownGrowth) - Math.min(...ownGrowth) : null;
  const privRange = windowExtremes(tlLdrPriv, 52);
  const dollYearAgo = valYearAgoByDate(dollSector);
  const dollYoY = dollNow != null && dollYearAgo != null ? dollNow - dollYearAgo : null;

  const auditQ = quarterLabel(lcrS.at(-1)?.period ?? liqRatios.at(-1)?.period);
  // The page's cadence is WEEKLY (the bulletin + the CBRT balance sheet); the §4
  // ratios are the one quarterly input, so the record line names both.
  const recWeek = weekLabel(tlLtd.at(-1)?.period, true);

  // "The Read" — deterministic, computed from the same series the charts show.
  const read = liquidityInsights({
    tlLdrPublic: toTrend(tlLtd).filter((r) => r.bank_type_code === "PUBLIC"),
    tlLdrPrivate: toTrend(tlLtd).filter((r) => r.bank_type_code === "PRIVATE"),
    dollarization: toTrend(dollarization).filter((r) => r.bank_type_code === "SECTOR"),
    netCbrtFunding: netFunding,
    lcr: liqRatios.filter((r) => r.bank_type_code === "LCR"),
  });

  // ---- the buffer, decomposed ---------------------------------------------
  // The page already DERIVES net reserves and the swap-excluded net; it has
  // never read them out. Gross − net is the banks' own FX, held at the CBRT as
  // required reserves; net − net-excl-swaps is the CBRT's swap stock.
  const grossAt = new Map((evds["TP.AB.TOPLAM"] ?? []).map((r) => [r.period_date, r.value / 1000]));
  const exAt = new Map(nirExSwaps.map((r) => [r.period_date, r.value]));
  const buffer: BufferPoint[] = nir
    .filter((r) => grossAt.has(r.period_date) && exAt.has(r.period_date))
    .map((r) => ({
      period: r.period_date,
      gross: grossAt.get(r.period_date) as number,
      net: r.value,
      own: exAt.get(r.period_date) as number,
    }));

  const bNow = buffer.at(-1) ?? null;
  const grossNow = bNow?.gross ?? null;
  const netNow = bNow?.net ?? null;
  const ownNow = bNow?.own ?? null;
  const swapStock = netNow != null && ownNow != null ? netNow - ownNow : null;
  const banksFx = grossNow != null && netNow != null ? grossNow - netNow : null;
  const ownPctGross = ownNow != null && grossNow ? (ownNow / grossNow) * 100 : null;
  const swapPctNet = swapStock != null && netNow ? (swapStock / netNow) * 100 : null;
  // How long the CBRT's own net FX has been below zero in this window — the
  // reason this is three lines and not a stacked area.
  const weeksOwnNegative = buffer.filter((b) => b.own < 0).length;

  // ---- households vs the central bank -------------------------------------
  // Residents' FC is MONTHLY, the reserves WEEKLY: pair them on the same date
  // (the last month both publish), never a fresh weekly print against a
  // month-old household number.
  const goldAt = new Map(residentsFc["Precious metals"].map((r) => [r.period_date, r.value]));
  const nirAtDate = (d: string): number | null => {
    for (let i = nir.length - 1; i >= 0; i--) if (nir[i].period_date <= d) return nir[i].value;
    return null;
  };
  const hh = residentsFc["FX cash (USD + EUR)"]
    .map((r) => ({
      period: r.period_date,
      cash: r.value,
      gold: goldAt.get(r.period_date) ?? 0,
      nir: nirAtDate(r.period_date),
    }))
    .filter((r): r is { period: string; cash: number; gold: number; nir: number } => r.nir != null);
  const hhNow = hh.at(-1) ?? null;
  const hhTotal = hhNow ? hhNow.cash + hhNow.gold : null;
  const hhVsNir = hhNow && hhTotal != null && hhNow.nir ? hhTotal / hhNow.nir : null;
  const goldVsNir = hhNow && hhNow.nir ? hhNow.gold / hhNow.nir : null;

  const reerNow = lastVal(reer.map((r) => ({ period: r.period_date, value: r.value })));
  const reer12 = reer.at(-13)?.value ?? null;
  const tl13w = lastVal(tlGrowth13w);
  const tlYoY = lastVal(tlGrowthYoY);

  const fmtBn = (v: number | null) => (v == null ? "—" : `$${v.toFixed(1)}bn`);
  const fmtPct = (v: number | null, d = 1) => (v == null ? "—" : `${v.toFixed(d)}%`);

  // ---- movers: the WEEKLY record only -------------------------------------
  // Net CBRT funding is DAILY; putting it in this Δ column would mix cadences,
  // so it goes to the transmission below, where its basis is stated.
  const gross = (evds["TP.AB.TOPLAM"] ?? []).map((r) => ({
    period: r.period_date,
    value: r.value / 1000,
  }));
  const wk = (s: { value: number | null }[]) => ({
    prev: s.at(-2)?.value ?? null,
    curr: s.at(-1)?.value ?? null,
  });
  const moverRows: MoverRow[] = [
    { label: "TL loan / deposit — public", ...wk(tlLdrPub), fmt: (v) => `${v.toFixed(1)}%`, deltaDecimals: 1, good: "down" },
    {
      label: "TL loan / deposit — private",
      note: privNow != null ? `${(100 - privNow).toFixed(1)}pp from the 100% line` : undefined,
      ...wk(tlLdrPriv), fmt: (v) => `${v.toFixed(1)}%`, deltaDecimals: 1, good: "down",
    },
    { label: "FC share of deposits", note: "the dollarization tell", ...wk(dollSector), good: "down" },
    {
      label: "Gross reserves", note: "USD bn",
      ...wk(gross), fmt: (v) => `$${v.toFixed(1)}`, deltaDecimals: 1, deltaUnit: "", good: "up",
    },
    {
      label: "Net reserves", note: "derived · USD bn",
      prev: buffer.at(-2)?.net ?? null, curr: netNow,
      fmt: (v) => `$${v.toFixed(1)}`, deltaDecimals: 1, deltaUnit: "", good: "up",
    },
    {
      label: "Net excl. swaps", note: "the CBRT's own FX · USD bn",
      prev: buffer.at(-2)?.own ?? null, curr: ownNow,
      fmt: (v) => `$${v.toFixed(1)}`, deltaDecimals: 1, deltaUnit: "", good: "up",
    },
  ];

  // ---- the buffer → the system --------------------------------------------
  const transmission: TransmissionItem[] = [];
  if (grossNow != null && netNow != null && banksFx != null) {
    transmission.push({
      k: "Net ÷ gross",
      v: ((netNow / grossNow) * 100).toFixed(0),
      unit: "%",
      effect: (
        <>
          Gross reserves are <b>{fmtBn(grossNow)}</b>, net <b>{fmtBn(netNow)}</b>. The difference —{" "}
          <b>{fmtBn(banksFx)}</b> —{" "}
          {banksFx > 0 ? (
            <>
              is the banks&rsquo; own FX, held at the CBRT as required reserves.{" "}
              <b>It is not the central bank&rsquo;s money.</b>
            </>
          ) : (
            // gross − net ≡ the banks' FX at the CBRT, so this is normally positive.
            // If it inverts, the sentence above becomes nonsense — say what it is.
            <>is negative: net reserves exceed gross, which the identity does not allow.</>
          )}
        </>
      ),
    });
  }
  if (swapStock != null && ownNow != null) {
    transmission.push({
      k: "Borrowed FX",
      v: `$${swapStock.toFixed(1)}`,
      unit: "bn",
      effect: (
        <>
          {fmtPct(swapPctNet, 0)} of the net buffer is swapped in. Strip the swaps and the
          CBRT&rsquo;s own net reserves are <b>{fmtBn(ownNow)}</b> —{" "}
          <b>{fmtPct(ownPctGross, 0)} of the headline</b>.
        </>
      ),
    });
  }
  if (hhNow && hhTotal != null) {
    transmission.push({
      k: "Households",
      v: `$${hhTotal.toFixed(0)}`,
      unit: "bn",
      effect: (
        <>
          Residents hold <b>{fmtBn(hhNow.cash)}</b> in FX cash and <b>{fmtBn(hhNow.gold)}</b> in
          gold — <b>{hhVsNir?.toFixed(1)}× the CBRT&rsquo;s net reserves</b> on the same date; the
          gold alone is {goldVsNir?.toFixed(1)}×. Dollarization is not just a deposit line.{" "}
          <Link href="/deposits" className="font-semibold text-primary">/deposits</Link>
        </>
      ),
    });
  }
  if (fundNow != null) {
    transmission.push({
      k: "TL deficit",
      v: `₺${fundNow.toFixed(0)}`,
      unit: "bn · daily",
      effect: (
        <>
          {fundNow < 0 ? (
            <>
              The system is <b>short of lira</b> and funds the gap at the CBRT — the channel a rate
              decision travels down. How fast it arrives is the maturity ladder&rsquo;s question,
              not this one.{" "}
            </>
          ) : (
            <>The system holds <b>excess lira</b> and places it back with the CBRT. </>
          )}
          <Link href="/deposits" className="font-semibold text-primary">/deposits</Link>
        </>
      ),
    });
  }
  if (reerNow != null && reer12 != null) {
    // The noun used to be typed while the sign was computed, so a real
    // DEPRECIATION printed "Real appreciation of −4.3 … is what makes holding
    // lira pay". Both the noun and the carry read now come off the same delta.
    const reerD = reerNow - reer12;
    const reerMove = direction(reerD, VERBS.noun, bandsFor(reer12));
    transmission.push({
      k: "REER",
      v: reerNow.toFixed(1),
      effect: (
        <>
          {reerMove === VERBS.noun.flat ? (
            <>The real exchange rate is flat over 12 months — the lira carry is unchanged.</>
          ) : (
            <>
              Real {reerMove} of <b>{Math.abs(reerD).toFixed(1)}</b> over 12 months{" "}
              {reerD > 0 ? "is what makes holding lira pay" : "works against the lira carry"} — TL
              deposits run at <b>{fmtPct(tl13w, 0)} annualized</b>.
            </>
          )}{" "}
          <Link href="/economy" className="font-semibold text-primary">/economy</Link>
        </>
      ),
    });
  }

  // ---- flags: seven rules, each printed whether or not it fires ------------
  const flags: Flag[] = [
    {
      code: "thin-own-buffer",
      active: ownPctGross != null && ownPctGross < 40,
      body: (
        <>
          <b className="font-semibold">Thin own-buffer</b> — the CBRT&rsquo;s own net reserves are{" "}
          {fmtBn(ownNow)}, {fmtPct(ownPctGross, 0)} of the {fmtBn(grossNow)} headline. The rest is
          the banks&rsquo; required reserves and swapped-in FX.
        </>
      ),
      rule: "net_excl_swaps / gross < 40%",
      clear: <>Own buffer — {fmtPct(ownPctGross, 0)} of gross is the CBRT&rsquo;s own FX</>,
    },
    {
      code: "swap-dependence",
      active: swapPctNet != null && swapPctNet > 25,
      body: (
        <>
          <b className="font-semibold">Swap dependence</b> — {fmtBn(swapStock)} of the{" "}
          {fmtBn(netNow)} net buffer is borrowed ({fmtPct(swapPctNet, 0)}). A swap is a liability
          with a date on it.
        </>
      ),
      rule: "swaps / nir > 25%",
      clear: <>Swaps — {fmtPct(swapPctNet, 0)} of the net buffer</>,
    },
    {
      code: "tl-deficit",
      active: fundNow != null && fundNow < 0,
      body: (
        <>
          <b className="font-semibold">TL deficit</b> — net CBRT funding is{" "}
          <b>₺{fundNow?.toFixed(0)}bn</b>: the system is short of lira and funds the gap at the
          policy rate.
        </>
      ),
      rule: "net_cbrt_funding < 0",
      clear: <>TL liquidity — net CBRT funding ₺{fundNow?.toFixed(0)}bn, in surplus</>,
    },
    {
      code: "private-ldr",
      active: privNow != null && privNow > 95,
      body: (
        <>
          <b className="font-semibold">Private LDR at the line</b> — private TL loan/deposit{" "}
          {fmtPct(privNow)}, within {privNow != null ? (100 - privNow).toFixed(1) : "—"}pp of 100%.
          New lending has to be funded, not recycled.
        </>
      ),
      rule: "tl_ldr_private > 95%",
      clear: <>Private TL loan/deposit — {fmtPct(privNow)}, clear of the line</>,
    },
    {
      code: "lcr-floor",
      active: lcrNow != null && lcrNow < 100,
      body: (
        <>
          <b className="font-semibold">LCR below the floor</b> — {fmtPct(lcrNow, 0)} against the
          100% regulatory minimum (audited {auditQ}).
        </>
      ),
      rule: "lcr < 100%",
      clear: <>LCR — {fmtPct(lcrNow, 0)}, clear of the floor</>,
    },
    {
      code: "nsfr-floor",
      active: nsfrNow != null && nsfrNow < 100,
      body: (
        <>
          <b className="font-semibold">NSFR below the floor</b> — {fmtPct(nsfrNow, 0)} against the
          100% regulatory minimum (audited {auditQ}).
        </>
      ),
      rule: "nsfr < 100%",
      clear: <>NSFR — {fmtPct(nsfrNow, 0)}, clear of the floor</>,
    },
    {
      code: "re-dollarization",
      active: dollYoY != null && dollYoY > 1,
      body: (
        <>
          <b className="font-semibold">Re-dollarization</b> — FC share {fmtPct(dollNow)},{" "}
          {dollYoY != null ? signedPp(dollYoY, 2) : "—"} y/y: savers are moving back into hard
          currency.
        </>
      ),
      rule: "Δ52w(fc_share) > +1pp",
      clear: (
        <>Dollarization — FC share {dollYoY != null ? signedPp(dollYoY, 2) : "—"} over 52w</>
      ),
    },
  ];
  const activeFlags = flags.filter((f) => f.active).length;

  // ---- the two systems ----------------------------------------------------
  const fcPub = lastVal(fcLtd.filter((r) => r.bank_type_code === "PUBLIC"));
  const fcPriv = lastVal(fcLtd.filter((r) => r.bank_type_code === "PRIVATE"));
  const dollPub = lastVal(dollarization.filter((r) => r.bank_type_code === "PUBLIC"));
  const dollPriv = lastVal(dollarization.filter((r) => r.bank_type_code === "PRIVATE"));
  const compareRows: CompareRow[] = [
    { label: "TL loan / deposit", a: pubNow, b: privNow },
    { label: "FC loan / deposit", a: fcPub, b: fcPriv },
    { label: "FC share of deposits", a: dollPub, b: dollPriv },
  ];

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title="Liquidity"
        record={
          <>
            Record <b className="font-normal text-foreground">W/E {recWeek}</b> · {auditQ} filings +
            weekly
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

      {/* ── Movers | The buffer → the system ───────────────────────────── */}
      <div className="mt-8 grid gap-x-10 gap-y-8 lg:grid-cols-[5fr_7fr]">
        <div>
          {/* Pair the week labels off a SINGLE-series array: tlLtd is long-form
              (one row per ownership group per week), so its .at(-2) is the same
              week's other group, not last week. */}
          <SecHead
            title="Movers"
            meta={`the weekly record · ${weekLabel(tlLdrPriv.at(-2)?.period)} → ${weekLabel(tlLdrPriv.at(-1)?.period)}`}
            className="mb-2.5"
          />
          <Movers
            from={weekLabel(tlLdrPriv.at(-2)?.period).toUpperCase()}
            to={weekLabel(tlLdrPriv.at(-1)?.period).toUpperCase()}
            rows={moverRows}
          />
        </div>
        <div>
          <SecHead
            title="The buffer → the system"
            meta="whose money is it · computed"
            className="mb-2.5"
          />
          <Transmission items={transmission} />
        </div>
      </div>

      {/* ── Flags | The two systems | Ahead ────────────────────────────── */}
      <div className="mt-8 grid gap-x-10 gap-y-8 lg:grid-cols-3">
        <div>
          <SecHead
            title="Flags"
            meta={`rule-based — ${activeFlags} of ${flags.length}`}
            className="mb-2.5"
          />
          <Flags
            flags={flags}
            showCleared
            quietNote="The buffer, the swap stock, the TL deficit, the private LDR, both regulatory floors and dollarization are all below threshold."
          />
        </div>
        <div>
          <SecHead
            title="The two systems"
            meta={`public vs private · w/e ${recWeek}`}
            className="mb-2.5"
          />
          <Compare a="Public" b="Private" rows={compareRows} />
          <p className="mt-2 text-[10.5px] leading-snug text-faint">
            BBVA&rsquo;s cut, which this page follows: public = state banks; private = private +
            foreign.
          </p>
        </div>
        <div>
          <SecHead title="Ahead" meta="schedule — derived from the record periods + the tcmb calendar" className="mb-2.5" />
          <Ahead
            items={[
              { when: "THU", what: <>TCMB analytical balance sheet — the reserve buffer</> },
              ahead.mpc && {
                when: ahead.mpc.when,
                what: (
                  <>
                    TCMB MPC — the rate the{" "}
                    {fundNow != null ? `₺${Math.abs(fundNow).toFixed(0)}bn` : ""} deficit is funded at
                  </>
                ),
              },
              ahead["brsa-filings"] && {
                when: ahead["brsa-filings"].when,
                what: <>BRSA {ahead["brsa-filings"].record} filings — LCR, NSFR, leverage</>,
                href: "/actions",
              },
              ahead.fsr && {
                when: ahead.fsr.when,
                what: <>TCMB Financial Stability Report — funding &amp; liquidity risks</>,
              },
            ].filter((i) => !!i)}
          />
        </div>
      </div>

      {/* ── In depth — the evidence, on the brief's own grid ───────────── */}
      <Depth action={<GlobalRangeSelector />}>
        <Takeaway data={await withLlmHeadline("liquidity", read)} variant="desk" />

        {/* The buffer — the page's own arithmetic, finally read out. */}
        <div>
          <SecHead
            title="The buffer"
            meta="whose fx is it · derived from the tcmb analytical balance sheet"
            className="mb-2.5"
          />
          <Levels
            items={[
              { k: "Gross reserves", v: fmtBn(grossNow) },
              { k: "Net (derived)", v: fmtBn(netNow) },
              { k: "Net excl. swaps", v: fmtBn(ownNow) },
              { k: "Residents' FX + gold", v: fmtBn(hhTotal) },
            ]}
          />
          <div className="mt-6 grid grid-cols-1 gap-x-10 gap-y-9 lg:grid-cols-2">
            <ReserveBuffer
              data={buffer}
              title={
                weeksOwnNegative > 0 && ownNow != null
                  ? `The central bank's own net FX was below zero for ${weeksOwnNegative} of the last ${buffer.length} weeks — and is ${fmtBn(ownNow)} today`
                  : "Gross → net → net excluding swaps"
              }
              description="gross → net → net excl. swaps, USD bn, weekly · the gaps are the banks' required reserves and the swap stock"
              source={
                <div className="flex flex-wrap gap-x-4 gap-y-1">
                  <span>
                    GROSS <b className="font-semibold text-foreground">{fmtBn(grossNow)}</b>
                  </span>
                  <span>
                    CBRT&rsquo;S OWN{" "}
                    <b className="font-semibold text-foreground">
                      {fmtBn(ownNow)} ({fmtPct(ownPctGross, 0)} of gross)
                    </b>
                  </span>
                  <span>
                    SWAPPED <b className="font-semibold text-foreground">{fmtBn(swapStock)}</b>
                  </span>
                  <span>
                    BANKS&rsquo; REQ. RES.{" "}
                    <b className="font-semibold text-foreground">{fmtBn(banksFx)}</b>
                  </span>
                </div>
              }
              height={300}
            />
            <TimeSeriesChart
              plain
              series={{
                "Residents FX + gold": hh.map((r) => ({
                  period_date: r.period,
                  value: r.cash + r.gold,
                })),
                "— of which gold": hh.map((r) => ({ period_date: r.period, value: r.gold })),
                "CBRT net reserves": hh.map((r) => ({ period_date: r.period, value: r.nir })),
              }}
              title={
                hhVsNir != null && hhVsNir > 1
                  ? "Households hold more FX and gold than the central bank holds net reserves"
                  : "Residents' FC savings vs the CBRT's net reserves"
              }
              description="residents' fc savings vs cbrt net reserves, USD bn, monthly · paired on the same date"
              source={
                <div className="flex flex-wrap gap-x-4 gap-y-1">
                  <span>
                    RESIDENTS <b className="font-semibold text-foreground">{fmtBn(hhTotal)}</b>
                  </span>
                  <span>
                    GOLD <b className="font-semibold text-foreground">{fmtBn(hhNow?.gold ?? null)}</b>
                  </span>
                  <span>
                    CBRT NET, SAME DATE{" "}
                    <b className="font-semibold text-foreground">{fmtBn(hhNow?.nir ?? null)}</b>
                  </span>
                  <span>
                    RATIO{" "}
                    <b className="font-semibold text-foreground">
                      {hhVsNir != null ? `${hhVsNir.toFixed(1)}×` : "—"}
                    </b>
                  </span>
                </div>
              }
              yFormat="raw"
              decimals={0}
              height={300}
            />
          </div>
        </div>

        {/* TL funding */}
        <div>
          <SecHead
            title="TL funding"
            meta="loan-to-deposit pressure · the maturity ladder lives on /deposits"
            className="mb-2.5"
          />
          <ChartRow data={toTrend(tlLtd)} labels={LIQ_OWNERSHIP_LABELS} deltaPeriods={52} deltaLabel="52w" fmt={(v) => `${v.toFixed(0)}%`}>
            <TrendChart
              plain
              data={toTrend(tlLtd)}
              seriesLabels={LIQ_OWNERSHIP_LABELS}
              title={
                pubPrivGap != null && pubPrivGap < 0
                  ? "The private banks lend out nearly every lira they take in; the state banks do not"
                  : "TL loan / deposit — public vs private"
              }
              description="tl loans ÷ tl deposits, %, weekly · public vs private"
              yFormat="pct"
              decimals={0}
              height={300}
              hero="PRIVATE"
            />
          </ChartRow>
          <div className="mt-6 grid grid-cols-1 gap-x-10 gap-y-9 lg:grid-cols-2">
            <TrendChart
              plain
              data={tlDepGrowth}
              seriesLabels={{ YOY: "52w", W13: "13w ann." }}
              title={
                tl13w != null && tlYoY != null && tl13w - tlYoY > 5
                  ? `TL deposits are running at a ${tl13w.toFixed(0)}% annualized pace — well above the ${tlYoY.toFixed(0)}% yearly rate`
                  : "TL deposit growth — sector"
              }
              description="tl deposit growth, %, weekly · 52w vs 13w annualized · sector"
              source={
                <ChartFoot
                  data={tlDepGrowth}
                  labels={{ YOY: "52w", W13: "13w ann." }}
                  heroCode="W13"
                  decimals={1}
                  deltaPeriods={52}
                  deltaLabel="52w"
                />
              }
              yFormat="pct"
              decimals={0}
              height={280}
              hero="W13"
              zeroLine
            />
            <TrendChart
              plain
              data={toTrend(tlGrowthOwn)}
              seriesLabels={LIQ_OWNERSHIP_LABELS}
              title={
                firstClaim(
                  [
                    ownSpread != null && ownSpread < 5,
                    "Both systems are pulling lira in at much the same pace",
                  ],
                  [
                    ownSpread != null,
                    `The two systems are pulling lira in at different speeds — ${(ownSpread ?? 0).toFixed(0)}pp apart`,
                  ],
                ) ?? "TL deposit growth — public vs private"
              }
              description="tl deposit growth, 13w annualized, %, weekly · public vs private"
              source={
                <ChartFoot
                  data={toTrend(tlGrowthOwn)}
                  labels={LIQ_OWNERSHIP_LABELS}
                  heroCode="PRIVATE"
                  decimals={1}
                  deltaPeriods={52}
                  deltaLabel="52w"
                />
              }
              yFormat="pct"
              decimals={0}
              height={280}
              hero="PRIVATE"
              zeroLine
            />
          </div>
        </div>

        {/* FC & dollarization */}
        <div>
          <SecHead
            title="FC &amp; dollarization"
            meta="fc funding pressure · households' appetite for hard currency"
            className="mb-2.5"
          />
          <div className="grid grid-cols-1 gap-x-10 gap-y-9 lg:grid-cols-2">
            <TrendChart
              plain
              data={toTrend(fcLtd)}
              seriesLabels={LIQ_OWNERSHIP_LABELS}
              title={
                fcPub != null && fcPriv != null && fcPub > fcPriv
                  ? "In foreign currency the roles reverse — the state banks are the stretched ones"
                  : "FC loan / deposit — public vs private"
              }
              description="fc loans ÷ fc deposits, %, weekly · public vs private"
              source={
                <ChartFoot
                  data={toTrend(fcLtd)}
                  labels={LIQ_OWNERSHIP_LABELS}
                  heroCode="PUBLIC"
                  decimals={1}
                  deltaPeriods={52}
                  deltaLabel="52w"
                />
              }
              yFormat="pct"
              decimals={0}
              height={280}
              hero="PUBLIC"
            />
            <TrendChart
              plain
              data={toTrend(dollarization)}
              seriesLabels={LIQ_DOLLARIZATION_LABELS}
              title={
                seriesFinding(
                  toTrend(dollarization).filter((r) => r.bank_type_code === "SECTOR"),
                  { noun: "Deposit dollarization", decimals: 1 },
                ) ?? "Deposit dollarization — FC share of deposits"
              }
              description="fc share of total deposits, %, weekly · sector / public / private"
              source={
                <ChartFoot
                  data={toTrend(dollarization)}
                  labels={LIQ_DOLLARIZATION_LABELS}
                  heroCode="SECTOR"
                  decimals={1}
                  deltaPeriods={52}
                  deltaLabel="52w"
                />
              }
              yFormat="pct"
              decimals={1}
              height={280}
              hero="SECTOR"
            />
          </div>
        </div>

        {/* CBRT TL liquidity */}
        <div>
          <SecHead
            title="CBRT liquidity"
            meta="the system's tl stance · + excess / − lack · daily"
            className="mb-2.5"
          />
          <ChartRow data={netFunding} deltaPeriods={252} deltaLabel="52w" fmt={(v) => `₺${(v / 1000).toFixed(0)}bn`}>
            <TrendChart
              plain
              data={netFunding}
              seriesLabels={{ NETFUND: "Net funding" }}
              title={
                fundNow != null && fundNow < 0
                  ? "The system is short of lira — it funds the gap at the CBRT"
                  : "Net CBRT funding"
              }
              description="net cbrt funding, ₺ bn, daily · zero = neutral"
              yFormat="bn"
              decimals={0}
              height={300}
              zeroLine
            />
          </ChartRow>
        </div>

        {/* Regulatory + the macro backdrop */}
        <div>
          <SecHead
            title="Regulatory liquidity"
            meta={`audited §4 · ${auditQ} · asset-weighted across reporting banks`}
            className="mb-2.5"
          />
          <div className="grid grid-cols-1 gap-x-10 gap-y-9 lg:grid-cols-2">
            <TrendChart
              plain
              data={liqRatios}
              seriesLabels={AUDIT_LIQUIDITY_LABELS}
              title={
                lcrNow != null && nsfrNow != null && lcrNow > 100 && nsfrNow > 100
                  ? "LCR and NSFR clear their floors with room to spare"
                  : "LCR / NSFR / leverage — sector"
              }
              description="lcr / nsfr / leverage, %, quarterly · 100% regulatory floor"
              source={
                <ChartFoot
                  data={liqRatios}
                  labels={AUDIT_LIQUIDITY_LABELS}
                  heroCode="LCR"
                  decimals={0}
                  deltaPeriods={4}
                  deltaLabel="4q"
                />
              }
              yFormat="pct"
              decimals={0}
              height={280}
              hero="LCR"
            />
            <TimeSeriesChart
              plain
              series={reerSeries}
              title={
                reerNow != null && reer12 != null && reerNow > reer12
                  ? "Real appreciation is what makes holding lira pay"
                  : "Real effective exchange rate"
              }
              description="real effective exchange rate, cpi based, 2003 = 100, monthly"
              source={
                <div className="flex flex-wrap gap-x-4 gap-y-1">
                  <span>
                    LATEST{" "}
                    <b className="font-semibold text-foreground">
                      {reerNow != null ? reerNow.toFixed(1) : "—"}
                    </b>
                  </span>
                  <span>
                    Δ 12M{" "}
                    <b className="font-semibold text-foreground">
                      {reerNow != null && reer12 != null
                        ? signedPp(reerNow - reer12, 1).replace("pp", "")
                        : "—"}
                    </b>
                  </span>
                  <span>
                    BASIS <b className="font-semibold text-foreground">2003 = 100</b>
                  </span>
                </div>
              }
              yFormat="rate"
              decimals={1}
              height={280}
            />
          </div>
        </div>
      </Depth>

      <Colophon />
    </main>
  );
}
