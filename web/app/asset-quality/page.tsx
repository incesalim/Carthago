/**
 * Asset Quality tab — the Desk brief above the carried-over evidence.
 *
 * The page used to lead with "NPL ratio 2.69%", which is calm, and is the TIP.
 * What the ratio prints is Stage 3. Loans the banks themselves classify as
 * deteriorated are ~4x that, and three-quarters of the problem book is the
 * Stage-2 watchlist the ratio never shows. The brief now leads with that
 * (<Waterline/>), then the pipeline behind it (formation is running at 2.2x, and
 * the exits are collections — NOT write-offs, so this is real deterioration and
 * not a managed ratio), then where the new bad loans came from.
 *
 * What this page deliberately does NOT claim: that inflation flatters the ratio.
 * An NPL ratio is deflator-invariant — see the note in app/lib/asset-quality.ts
 * and the test that pins it. Loan-growth dilution is real but worth ~0.1pp, so it
 * is a footnote at its honest size, not a headline.
 */
import { localizeMetadata } from "@/i18n/metadata";
import { getText } from "@/i18n/server";
import type { Metadata } from "next";
import Link from "next/link";
import {
  ratioNpl,
  ratioCoverage,
  consumerNplMix,
  consumerNplRatios,
  commercialNplRatios,
  weeklySeries,
  latestPerBank,
  PRIMARY_BANK_TYPES,
  WEEKLY_BANK_TYPES,
  BANK_TYPE_LABELS,
  type TimeSeriesRow,
} from "@/app/lib/metrics";
import { Section } from "@/app/components/ui";
import { GlobalRangeSelector } from "@/app/components/range-context";
import {
  ChartRow,
  Colophon,
  Depth,
  DeskHeader,
  Disclosure,
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
import Attribution from "@/app/components/Attribution";
import { lastVal, monthLabel, signedPp } from "@/app/lib/desk";
import { signed, toneClass } from "@/app/lib/prose";
import BarByBank from "@/app/components/BarByBank";
import TrendChart from "@/app/components/TrendChart";
import StackedArea from "@/app/components/StackedArea";
import Takeaway from "@/app/components/Takeaway";
import { assetQualityInsights } from "@/app/lib/insights";
import { seriesFinding } from "@/app/lib/chart-findings";
import { withLlmHeadline } from "@/app/lib/read-headlines";
import { cpiYoYByMonth } from "@/app/lib/real-terms";
import {
  sectorStageShares,
  STAGE_SHARE_LABELS,
  provisionMigrationScenarios,
  stageLadder,
  nplRollForwardAnnual,
  problemBookCoverage,
} from "@/app/lib/credit-risk";
import {
  impliedRatio,
  nplStockAttribution,
  segmentRatios,
  NPL_ITEMS,
  LOAN_ITEMS,
} from "@/app/lib/asset-quality";
import { deflate, growthSeries, risingRun } from "@/app/lib/series";
import Waterline from "./Waterline";
import FormationBars from "./FormationBars";

export const dynamic = "force-dynamic";

const pageMetadata: Metadata = {
  title: "Turkish Banks — Asset Quality & NPLs",
  description:
    "Non-performing loans, the Stage-2 watchlist the NPL ratio does not print, coverage and NPL formation across Türkiye's banking sector and by bank.",
  alternates: { canonical: "/asset-quality" },
};

export async function generateMetadata(): Promise<Metadata> {
  return localizeMetadata(pageMetadata);
}

const NPL = "takipteki_alacaklar";
const KREDI = "krediler";
const SECTOR = "10001";

function ratiosToTrendRows(
  rows: Array<{ period: string; housing: number | null; auto: number | null; gpl: number | null; cards: number | null }>,
): TimeSeriesRow[] {
  const out: TimeSeriesRow[] = [];
  for (const r of rows) {
    if (r.housing != null) out.push({ period: r.period, bank_type_code: "HOUSING", value: r.housing });
    if (r.auto != null) out.push({ period: r.period, bank_type_code: "AUTO", value: r.auto });
    if (r.gpl != null) out.push({ period: r.period, bank_type_code: "GPL", value: r.gpl });
    if (r.cards != null) out.push({ period: r.period, bank_type_code: "CARDS", value: r.cards });
  }
  return out;
}

function commercialToTrendRows(
  rows: Array<{ period: string; sme: number | null; commercial: number | null; non_sme: number | null }>,
): TimeSeriesRow[] {
  const out: TimeSeriesRow[] = [];
  for (const r of rows) {
    if (r.sme != null) out.push({ period: r.period, bank_type_code: "SME", value: r.sme });
    if (r.commercial != null) out.push({ period: r.period, bank_type_code: "COMMERCIAL", value: r.commercial });
    if (r.non_sme != null) out.push({ period: r.period, bank_type_code: "NONSME", value: r.non_sme });
  }
  return out;
}

const fmtPct = (v: number | null | undefined, d = 1) => (v == null ? "—" : `${v.toFixed(d)}%`);

/** 'YYYY-MM-DD' → '03 Jul 2026' — the weekly stock's record line. */
function weekLabel(p: string | null | undefined): string {
  const m = p ? /^\d{4}-\d{2}-(\d{2})/.exec(p) : null;
  return m ? `${m[1]} ${monthLabel(p)}` : monthLabel(p);
}
const fmtBn = (v: number) => `₺${Math.round(v).toLocaleString("en-US")}bn`;
const fmtTrnFromBn = (bn: number) => `₺${(bn / 1000).toFixed(2)}trn`;

export default async function AssetQualityPage() {
  const tx = await getText();
  const sector = [WEEKLY_BANK_TYPES.SECTOR];
  const groups = PRIMARY_BANK_TYPES.filter((c) => c !== SECTOR);
  const nplW = (item: string) => weeklySeries(NPL, item, "TOTAL", sector, 156);
  const loanW = (item: string) => weeklySeries(KREDI, item, "TOTAL", sector, 156);

  const [
    nplAll, nplByBank, coverageAll,
    gross, loansTotal,
    stockHousing, stockAuto, stockGpl, stockCards, stockCommercial, stockSme,
    loanHousing, loanAuto, loanGpl, loanCards, loanCommercial, loanSme,
    cMix, cRatios, commRatios,
    stageShares, migration, ladder, roll, problemCov,
  ] = await Promise.all([
    ratioNpl(PRIMARY_BANK_TYPES),
    latestPerBank(ratioNpl, groups),
    ratioCoverage(PRIMARY_BANK_TYPES),
    nplW(NPL_ITEMS.TOTAL),
    loanW(LOAN_ITEMS.TOTAL),
    nplW(NPL_ITEMS.HOUSING), nplW(NPL_ITEMS.AUTO), nplW(NPL_ITEMS.GPL),
    nplW(NPL_ITEMS.CARDS), nplW(NPL_ITEMS.COMMERCIAL), nplW(NPL_ITEMS.SME),
    loanW(LOAN_ITEMS.HOUSING), loanW(LOAN_ITEMS.AUTO), loanW(LOAN_ITEMS.GPL),
    loanW(LOAN_ITEMS.CARDS), loanW(LOAN_ITEMS.COMMERCIAL), loanW(LOAN_ITEMS.SME),
    consumerNplMix(),
    consumerNplRatios(),
    commercialNplRatios(),
    sectorStageShares(),
    provisionMigrationScenarios(),
    stageLadder(),
    nplRollForwardAnnual(),
    problemBookCoverage(),
  ]);
  const cpiYoY = await cpiYoYByMonth();

  const consumerTrend = ratiosToTrendRows(cRatios);
  const commercialTrend = commercialToTrendRows(commRatios);

  const nplSector = nplAll.filter((r) => r.bank_type_code === SECTOR);
  const covSector = coverageAll.filter((r) => r.bank_type_code === SECTOR);
  const stage2 = stageShares.filter((r) => r.bank_type_code === "STAGE2");
  const stage3 = stageShares.filter((r) => r.bank_type_code === "STAGE3");

  const asOf = gross.filter((r) => r.value != null).at(-1)?.period ?? null;

  // ---- the stock, and how fast it is compounding ----------------------------
  const stockYoY = growthSeries(gross);
  const loanYoY = growthSeries(loansTotal);
  const stockRealYoY = deflate(stockYoY, cpiYoY);
  const loanRealYoY = deflate(loanYoY, cpiYoY);
  const stockNominalNow = lastVal(stockYoY as TimeSeriesRow[]);
  const stockRealNow = lastVal(stockRealYoY as TimeSeriesRow[]);
  const loanRealNow = lastVal(loanRealYoY as TimeSeriesRow[]);

  // The monthly and weekly ratios can have different reporting dates as well
  // as different bases. Label each observation; do not call the latest gap a
  // fixed definition effect or mix either with the audited staging multiple.
  const impliedSeries = impliedRatio(gross, loansTotal);
  const impliedNow = lastVal(impliedSeries as TimeSeriesRow[]);
  const publishedNow = lastVal(nplSector);
  const publishedPeriod = nplSector.filter((r) => r.value != null).at(-1)?.period;
  const impliedPeriod = impliedSeries.at(-1)?.period;
  const publishedRun = risingRun(nplSector);

  // ---- segments -------------------------------------------------------------
  const segs = asOf
    ? segmentRatios(
        [
          { key: "cards", label: "Retail cards", stock: stockCards, loans: loanCards },
          { key: "gpl", label: "Gen. purpose", stock: stockGpl, loans: loanGpl },
          { key: "housing", label: "Housing", stock: stockHousing, loans: loanHousing },
          { key: "auto", label: "Auto", stock: stockAuto, loans: loanAuto },
          { key: "commercial", label: "Commercial", stock: stockCommercial, loans: loanCommercial },
          { key: "sme", label: "SME", stock: stockSme, loans: loanSme },
        ],
        asOf,
      )
    : [];
  const sme = segs.find((s) => s.key === "sme") ?? null;
  const commercial = segs.find((s) => s.key === "commercial") ?? null;

  // Where the increase in the NPL stock came from. The five parts are DISJOINT and
  // reconcile to the total at 100% — SME is a CUT of commercial, so it rides as a
  // memo and is never added.
  const attrib = nplStockAttribution(
    gross,
    [
      { key: "commercial", label: "Commercial", rows: stockCommercial },
      { key: "cards", label: "Retail cards", rows: stockCards },
      { key: "gpl", label: "Gen. purpose", rows: stockGpl },
      { key: "housing", label: "Housing", rows: stockHousing },
      { key: "auto", label: "Auto", rows: stockAuto },
    ],
    { key: "sme", label: "SME", rows: stockSme },
  );
  const smeShareOfCommNpl =
    sme && commercial && commercial.stockBn > 0 ? (sme.stockBn / commercial.stockBn) * 100 : null;
  const smeShareOfCommLoans =
    sme && commercial && commercial.loanBn > 0 ? (sme.loanBn / commercial.loanBn) * 100 : null;

  const rollNow = roll.at(-1) ?? null;
  const rollPrev = roll.at(-2) ?? null;
  const formationMultiple =
    rollNow && rollPrev && rollPrev.additions > 0 ? rollNow.additions / rollPrev.additions : null;

  // "The Read" — deterministic, from the same series the charts show.
  const read = assetQualityInsights({
    npl: nplSector,
    coverage: covSector,
    grossNpl: gross,
    cardsNpl: consumerTrend.filter((r) => r.bank_type_code === "CARDS"),
    smeNpl: commercialTrend.filter((r) => r.bank_type_code === "SME"),
    stage2,
    ladder,
    roll: rollNow,
    formationMultiple,
  }, tx.locale);

  // ---- flags — each prints the rule that raised it --------------------------
  const s2OverS3 = ladder && ladder.stage3Share > 0 ? ladder.stage2Share / ladder.stage3Share : null;
  const flags: Flag[] = [
    {
      code: "watchlist_thinly_covered",
      active: !!(ladder && s2OverS3 && s2OverS3 >= 2 && ladder.cov2 < ladder.cov3 / 5),
      rule: ladder
        ? `stage2 ÷ stage3 = ${s2OverS3?.toFixed(1)}× AND cov2 < cov3 ÷ 5`
        : "stage2 ÷ stage3 AND cov2 < cov3 ÷ 5",
      body: ladder ? (
        <>{tx("Stage 2 totals {0}, versus {1} in Stage 3. Coverage is {2} and {3}, respectively. Stage 2 is a watchlist rather than an impaired-loan classification, so lower coverage is expected; the migration scenario sizes a possible cost, not a current shortfall.",
          {0: fmtTrnFromBn(ladder.stage2Bn), 1: fmtTrnFromBn(ladder.stage3Bn), 2: fmtPct(ladder.cov2), 3: fmtPct(ladder.cov3)})}</>
      ) : null,
      clear: ladder ? (
        <>{tx("Stage-2 cover is ")}{tx(fmtPct(ladder.cov2))}{tx(" against Stage 3's ")}{tx(fmtPct(ladder.cov3))}.</>
      ) : undefined,
    },
    {
      code: "formation_doubling",
      active: !!(formationMultiple && formationMultiple >= 1.5 && rollNow && rollNow.net > 0),
      rule: rollNow && rollPrev ? `formation(${rollNow.year}) ÷ formation(${rollPrev.year}) = ${formationMultiple?.toFixed(1)}×` : "formation ÷ prior year ≥ 1.5×",
      body: rollNow ? (
        <>{tx("New NPL formation was {0}, versus {1} of exits, leaving net formation of {2}. Collections account for {3} of exits; write-offs or sales are not driving the ratio down, so the deterioration is in the book itself.",
          {0: fmtBn(rollNow.additions), 1: fmtBn(rollNow.exits), 2: signed(rollNow.net, fmtBn), 3: fmtPct(rollNow.collectionShare)})}</>
      ) : null,
      clear: rollNow ? <>{tx("Formation of ")}{tx(fmtBn(rollNow.additions))}{tx(" is not outrunning the prior year.")}</> : undefined,
    },
    {
      code: "stock_compounding",
      active: !!(stockRealNow != null && loanRealNow != null && stockRealNow > 3 * Math.max(loanRealNow, 0.1)),
      rule:
        stockRealNow != null && loanRealNow != null
          ? `npl_stock_real (${fmtPct(stockRealNow)}) > 3× loan_book_real (${fmtPct(loanRealNow)})`
          : "npl_stock_real > 3× loan_book_real",
      body: (
        <>{tx("On the same CPI-deflated basis, the NPL stock grew {0} in real terms, versus {1} real growth in the loan book.",
          {0: fmtPct(stockRealNow), 1: fmtPct(loanRealNow)})}</>
      ),
      clear: <>{tx("The NPL stock is growing ")}{tx(fmtPct(stockRealNow))}{tx(" in real terms.")}</>,
    },
    {
      code: "npl_ratio_streak",
      active: publishedRun >= 6,
      rule: tx("npl_ratio rising for {0} consecutive months", {0: publishedRun}),
      body: (
        <>
          {tx("The published NPL ratio rose from {0} to {1}. It is registering the deterioration, but slowly: the direction is informative even when the level looks low.",
          {0: fmtPct(nplSector.at(-1 - publishedRun)?.value, 2), 1: fmtPct(publishedNow, 2)})}</>
      ),
      clear: <>{tx("The NPL ratio has not risen for six months straight.")}</>,
    },
  ];

  // ---- movers — each segment's NPL ratio, 52w ago vs now --------------------
  const moverRows: MoverRow[] = segs
    .map((s) => ({
      label: s.label,
      note: s.key === "sme" ? "⊂ commercial" : undefined,
      prev: s.base,
      curr: s.now,
      fmt: (v: number) => `${v.toFixed(2)}%`,
      deltaDecimals: 2,
      good: "down" as const, // a rising NPL ratio is bad
    }))
    .sort((a, b) => (b.curr - b.prev) - (a.curr - a.prev));

  // A watchlist migration only ever ADDS provisions — Stage 2 → Stage 3 raises ECL
  // by construction, so these read "+" today. The sign still comes off the number.
  const migrationItems: TransmissionItem[] = migration.scenarios.map((s) => ({
    k: tx("{0}% of the watchlist migrates", {0: s.migratePct}),
    v: signed(s.provisionBn, (v) => `₺${v.toFixed(0)}bn`),
    unit: "provisions",
    effect:
      s.pctOfEclStock != null ? (
        <>{tx(signed(s.pctOfEclStock, (v) => `${v.toFixed(1)}%`))}{tx(" of ECL stock")}</>
      ) : null,
  }));

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title={tx("Asset Quality")}
        record={
          <>{tx("Record ")}<b className="font-normal text-foreground">{tx(monthLabel(nplSector.at(-1)?.period))}</b>{" "}{tx("· stock to W/E ")}{tx(asOf ? weekLabel(asOf) : "—")}{tx(" · stages quarterly")}</>
        }
        right="every figure computed from source series"
        observations={[
          {
            cadence: "quarterly",
            role: "audited",
            asOf: ladder?.period,
            basis: "same-bank TFRS-9 staging ladder",
          },
          {
            cadence: "monthly",
            role: "current",
            asOf: publishedPeriod,
            basis: "BDDK published NPL ratio",
          },
          {
            cadence: "weekly",
            role: "early-warning",
            asOf,
            window: "52w",
            basis: "stock and segment signals",
          },
          {
            cadence: "annual",
            role: "audited",
            asOf: rollNow?.year,
            basis: "NPL roll-forward",
          },
        ]}
      />

      {/* ── The waterline — what the ratio doesn't print ─────────────────── */}
      <SecHead
        title={tx("What the ratio doesn't print")}
        meta={tx("TFRS-9 staging · % of gross loans")}
        action={
          ladder ? (
            <span className="font-mono text-[8.5px] uppercase tracking-[0.07em] text-faint">{tx("audited ")}{tx(ladder.period)} · n={tx(ladder.n)}
            </span>
          ) : undefined
        }
        className="mb-2.5 mt-6"
      />
      <div className="grid grid-cols-1 gap-8 border-t-2 border-foreground pt-4 lg:grid-cols-[minmax(0,7fr)_minmax(260px,4fr)]">
        <Waterline ladder={ladder} />
        <div className="self-center">
          {ladder ? (
            <>
              <p className="text-[19px] leading-snug tracking-tight text-foreground">
                {tx("Audited Stage 3 is {0} of loans. Including the Stage-2 watchlist, the problem book reaches {1} — {2}× the visible tip.",
                {0: fmtPct(ladder.stage3Share), 1: fmtPct(ladder.problemShare), 2: ladder.multipleOfPrinted.toFixed(1)})}
              </p>
              <p className="mt-3 text-[12.5px] leading-relaxed text-muted-foreground">
                {tx("Stage 2 accounts for {0} of the problem book but never enters the published NPL ratio. Its coverage is {1}, versus {2} for Stage 3.",
                {0: fmtPct((ladder.stage2Bn / ladder.problemBn) * 100), 1: fmtPct(ladder.cov2), 2: fmtPct(ladder.cov3)})}
              </p>
              {rollNow && formationMultiple && (
                <p className="mt-3 text-[12.5px] leading-relaxed text-muted-foreground">
                  {tx("Stage 2 is a watchlist, not an impaired-loan classification; lower coverage is therefore expected, not automatically a shortfall. The stronger warning is the flow: new NPL formation ran at {0}× last year's level and net formation was {1}.",
                  {0: formationMultiple.toFixed(1), 1: signed(rollNow.net, fmtBn)})}
                </p>
              )}
              <p className="mt-3 border-t border-hair pt-2.5 font-mono text-[9px] uppercase leading-relaxed tracking-[0.06em] text-faint">
                {tx("Problem loans = Stage 2 + Stage 3, both from the same audited TFRS-9 filings. The {0}× multiple is {1} ÷ {2}; it never mixes in the monthly published ratio.",
                {0: ladder.multipleOfPrinted.toFixed(1), 1: fmtPct(ladder.problemShare), 2: fmtPct(ladder.stage3Share)})}
              </p>
            </>
          ) : (
            <p className="text-[12px] text-faint">{tx("The staging ladder awaits an audited quarter.")}</p>
          )}
        </div>
      </div>

      {/* ── The vitals ──────────────────────────────────────────────────── */}
      <SecHead title={tx("The risk ladder and its signals")} meta={tx("each figure carries its own observation clock")} className="mb-2.5 mt-8" />
      <Vitals>
        <Vital
          label={tx("Problem loans, S2+S3")}
          value={ladder ? ladder.problemShare.toFixed(1) : "—"}
          unit="%"
          series={stage2.map((r, i) => ({
            period: r.period,
            value: (r.value ?? 0) + (stage3[i]?.value ?? 0),
          }))}
          decimals={1}
          observation={{ cadence: "quarterly", role: "audited", asOf: ladder?.period, basis: "TFRS-9 Stage 2 + Stage 3" }}
          note={
            ladder ? (
              <>
                <em className="font-semibold not-italic text-negative">
                  {tx(ladder.multipleOfPrinted.toFixed(1))}×
                </em>{" "}{tx("the audited Stage-3 share — ")}{tx(fmtTrnFromBn(ladder.problemBn))}{tx(" of loans (")}{tx(ladder.period)})
              </>
            ) : undefined
          }
        />
        <Vital
          label={tx("Cover on the problem book")}
          value={ladder ? ladder.problemCov.toFixed(1) : "—"}
          unit="%"
          // The coverage series, NOT the Stage-2 share: the value is provisions
          // over the problem book (~70%), and this sparkline used to draw a share
          // of gross loans (~10%) — a different quantity on a different axis.
          series={problemCov.map((r) => ({ period: r.period, value: r.value }))}
          decimals={1}
          observation={{ cadence: "quarterly", role: "audited", asOf: ladder?.period, basis: "same-bank problem-loan book" }}
          note={
            ladder ? (
              <>{tx("Stage 2 at ")}<b className="font-semibold text-foreground">{tx(fmtPct(ladder.cov2))}</b>{tx(" vs Stage 3 at ")}<b className="font-semibold text-foreground">{tx(fmtPct(ladder.cov3))}</b> —{" "}
                {tx(fmtBn(ladder.provisionsBn))}{tx(" of provisions")}</>
            ) : undefined
          }
        />
        <Vital
          label={tx("NPL stock, real y/y")}
          value={stockRealNow != null ? stockRealNow.toFixed(1) : "—"}
          unit="%"
          series={(stockRealYoY as TimeSeriesRow[]).slice(-26)}
          decimals={1}
          observation={{ cadence: "weekly", role: "early-warning", asOf: stockRealYoY.at(-1)?.period, window: "52w real", basis: "weekly stock; published CPI only" }}
          note={
            stockRealNow != null && loanRealNow != null ? (
              <>{tx("bad loans compounding — the loan book grew just ")}{tx(fmtPct(loanRealNow))}{tx(" real ·")}{" "}
                <Link href="/credit" className="font-semibold text-primary">{tx("/credit")}</Link>
              </>
            ) : (
              "awaits the CPI print"
            )
          }
        />
        <Vital
          label={tx("Net NPL formation")}
          // Net formation turning negative is the GOOD case — the stock is
          // shrinking. It used to render "+-42".
          value={rollNow ? signed(rollNow.net, (v) => String(Math.round(v))) : "—"}
          unit="₺bn"
          series={roll.map((y) => ({ period: y.year, value: y.net }))}
          format="raw"
          decimals={0}
          observation={{ cadence: "annual", role: "audited", asOf: rollNow?.year, window: "year flow", basis: "NPL roll-forward" }}
          note={
            rollNow && formationMultiple ? (
              <>{tx("formation ")}<b className="font-semibold text-foreground">{tx(formationMultiple.toFixed(1))}×</b>{" "}{tx("last year · exits are")}{" "}
                <b className="font-semibold text-foreground">
                  {tx(rollNow.collectionShare.toFixed(0))}{tx("% collections")}</b>
              </>
            ) : undefined
          }
        />
        <Vital
          label={tx("NPL ratio, as printed")}
          value={publishedNow != null ? publishedNow.toFixed(2) : "—"}
          unit="%"
          series={nplSector.slice(-24)}
          decimals={2}
          observation={{ cadence: "monthly", role: "current", asOf: publishedPeriod, basis: "BDDK published ratio" }}
          note={
            publishedRun >= 3 ? (
              <>
                <em className="font-semibold not-italic text-negative">
                  {tx(publishedRun)}{tx(" straight monthly rises")}</em>{" "}{tx("— BDDK published basis")}</>
            ) : (
              "BDDK published basis"
            )
          }
        />
        <Vital
          label={tx("SME NPL")}
          value={sme ? sme.now.toFixed(2) : "—"}
          unit="%"
          series={(sme?.series ?? []).slice(-26) as TimeSeriesRow[]}
          decimals={2}
          observation={{ cadence: "weekly", role: "early-warning", asOf: sme?.series.at(-1)?.period, window: "52w", basis: "SME loan and NPL stock" }}
          note={
            sme && attrib.memo ? (
              <>
                {tx(signedPp(sme.delta, 2))}{tx(" in 52w — SME drove")}{" "}
                <b className="font-semibold text-foreground">{tx(attrib.memo.share.toFixed(1))}%</b>{tx(" of all new bad loans")}</>
            ) : undefined
          }
        />
      </Vitals>

      <Disclosure
        title={tx("Flows, scenarios and attribution")}
        meta={tx("annual audited flow · scenario sizing · 52w attribution")}
      >
        <div>
      {/* ── The pipeline behind the tip ─────────────────────────────────── */}
      <SecHead
        title={tx("The pipeline behind the tip")}
        meta={tx("audited NPL roll-forward · annual · ₺bn")}
        className="mb-2.5"
      />
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
        <div>
          <FormationBars data={roll} />
          {rollNow && formationMultiple && rollPrev && (
            <p className="mt-2 text-[11.5px] leading-relaxed text-muted-foreground">{tx("Formation is ")}<b className="font-semibold text-foreground">{tx(formationMultiple.toFixed(1))}×</b>{" "}{tx("last year (")}{tx(fmtBn(rollPrev.additions))} → {tx(fmtBn(rollNow.additions))}{tx("), net")}{" "}
              <b className={`font-semibold ${toneClass(rollNow.net, "down")}`}>
                {tx(signed(rollNow.net, fmtBn))}
              </b>{tx(". Exits are")}{" "}
              <b className="font-semibold text-foreground">
                {tx(rollNow.collectionShare.toFixed(0))}{tx("% collections")}</b>{" "}{tx("— not write-offs or sales.")}{" "}
              <em>{tx("The ratio is not being managed down; the book is genuinely deteriorating.")}</em>
            </p>
          )}
        </div>
        <div>
          <SecHead
            title={tx("If the watchlist migrates")}
            meta={tx("sizing device — not a forecast")}
            className="mb-2.5 mt-0"
          />
          {migrationItems.length > 0 ? (
            <>
              <Transmission items={migrationItems} />
              <p className="mt-2.5 text-[9.5px] leading-relaxed text-faint">{tx("Migration provisioned at Stage 3's rate (")}{tx(migration.cov3 != null ? `${(migration.cov3 * 100).toFixed(0)}%` : "—")}{tx(") against Stage 2 today (")}{tx(migration.cov2 != null ? `${(migration.cov2 * 100).toFixed(0)}%` : "—")}{tx("), on a ₺")}{tx(migration.stage2Bn?.toFixed(0))}{tx("bn book · ")}{tx(migration.period)}{tx(". Stage 2 is")}{" "}
                <b className="font-semibold text-muted-foreground">{tx("not")}</b>{tx(" impaired — this is what migration would cost, ")}<b className="font-semibold text-muted-foreground">{tx("not a gap the banks owe")}</b>.
              </p>
            </>
          ) : (
            <p className="text-[12px] text-faint">{tx("The migration sizing needs Stage-3 cover above Stage-2 cover in the latest filing.")}</p>
          )}
        </div>
      </div>

      {/* ── Where the new bad loans came from ───────────────────────────── */}
      <div className="mt-8 grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,7fr)_minmax(260px,4fr)]">
        <div>
          <SecHead
            title={tx("Where the new bad loans came from")}
            meta={tx("share of the ₺{0}trn increase · 52w", {0: (attrib.totalDelta / 1_000_000).toFixed(2)})}
            className="mb-2.5 mt-0"
          />
          <Attribution
            rows={attrib.items.map((i) => {
              const seg = segs.find((s) => s.key === i.key);
              return {
                key: i.key,
                label: i.label,
                value: i.share,
                meta: seg ? tx("{0}% NPL · {1}", {0: seg.now.toFixed(2), 1: signedPp(seg.delta, 2)}) : undefined,
              };
            })}
            sum={attrib.sumShare}
            nested={
              attrib.memo
                ? { of: "commercial", label: "SME", value: attrib.memo.share }
                : undefined
            }
            fmtValue={(v) => `${v.toFixed(1)}%`}
            reconciliation={
              smeShareOfCommNpl != null && smeShareOfCommLoans != null ? (
                <>{tx("segments reconcile to the NPL stock — SME is a cut of commercial (")}{tx(smeShareOfCommNpl.toFixed(0))}{tx("% of its bad loans on ")}{tx(smeShareOfCommLoans.toFixed(0))}{tx("% of its lending), not an addition")}</>
              ) : (
                <>{tx("segments reconcile to the NPL stock — SME is a cut of commercial, not an addition")}</>
              )
            }
            totalMeta={tx("₺{0}trn added", {0: (attrib.totalDelta / 1_000_000).toFixed(2)})}
          />
        </div>
        <div>
          <SecHead title={tx("Movers")} meta={tx("NPL ratio · 52w")} className="mb-2.5 mt-0" />
          <Movers from="52w ago" to="Now" rows={moverRows} />
        </div>
      </div>
        </div>
      </Disclosure>

      {/* ── Flags ───────────────────────────────────────────────────────── */}
      <SecHead title={tx("Flags")} meta={tx("each prints the rule that raised it")} className="mb-2.5 mt-8" />
      <Flags flags={flags} showCleared quietNote="No asset-quality rule fired this month." />

      {/* ── The two honesty footnotes ───────────────────────────────────── */}
      <Disclosure
        title={tx("Basis and method notes")}
        meta={tx("why the dates and ratio definitions differ")}
      >
      <div className="grid grid-cols-1 gap-7 sm:grid-cols-2">
        <div>
          <h4 className="mb-1 text-[10.5px] font-semibold text-foreground">{tx("Why we do not claim that inflation flatters the ratio")}</h4>
          <p className="text-[10px] leading-relaxed text-faint">{tx("An NPL ratio is ")}<b className="text-muted-foreground">{tx("NPL ÷ loans")}</b>{tx(". Deflate both legs by CPI and it is ")}<b className="text-muted-foreground">{tx("unchanged")}</b>{tx(" — a ratio is deflator-invariant. Only ")}<b className="text-muted-foreground">{tx("real")}</b>{tx(" book growth dilutes it, and that was ")}{tx(fmtPct(loanRealNow))}{tx(": worth about")}{" "}
            <b className="text-muted-foreground">{tx("0.1pp")}</b>{tx(", not the ~1pp a nominally-frozen-book counterfactual would suggest. A real bias does exist — the numerator is stale (a loan that defaulted two years ago sits at its origination principal) while the denominator reprices — but sizing it needs origination-vintage data we do not have, so we put no number on it.")}</p>
        </div>
        <div>
          <h4 className="mb-1 text-[10.5px] font-semibold text-foreground">{tx("NPL measures and reporting dates")}</h4>
          <p className="text-[10px] leading-relaxed text-faint">
            {tx("The published monthly NPL ratio is {0} ({1}); the weekly stock-to-loan ratio is {2} (week ending {3}).", {0: fmtPct(publishedNow, 2), 1: monthLabel(publishedPeriod), 2: fmtPct(impliedNow, 2), 3: weekLabel(impliedPeriod)})}{" "}
            {tx("Different reporting dates and bases mean the latest gap cannot be attributed to definitions alone.")}{" "}
            {ladder && tx("The audited staging comparison above uses only the same {0} reporting banks in {1}; its multiple is Stage 2 + 3 divided by Stage 3 on that same book.", {0: ladder.n, 1: ladder.period})}
          </p>
        </div>
      </div>
      </Disclosure>

      {/* ── In depth — the evidence layer ───────────────────────────────── */}
      <Depth
        collapsed
        meta={tx("carried over, reordered by question — nothing removed")}
        action={<GlobalRangeSelector />}
      >
        <Takeaway data={await withLlmHeadline("asset-quality", read, tx.locale)} variant="desk" />

        <Section
          index="01"
          title={tx("What is coming?")}
          description={tx("How the watchlist has built up. The roll-forward and the migration sizing sit in the brief above.")}
        >
          {stageShares.length > 0 && (
            <TrendChart
              data={stageShares}
              seriesLabels={STAGE_SHARE_LABELS}
              title={tx("TFRS-9 staging — % of gross loans (audited quarterly)")}
              description={tx("Stage 2 is the watchlist the NPL ratio never prints.")}
              yFormat="pct"
              decimals={1}
              plain
            />
          )}
        </Section>

        <Section
          index="02"
          title={tx("Is the stock or the ratio moving?")}
          description={tx("The stock is the fast-moving series; the ratio is a slow summary of it.")}
        >
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {/* NOT a seriesFinding title. That helper renders values as a PERCENT
                with pp deltas over a 12-POINT window (≈ a year of MONTHLY data).
                This is a weekly ₺ level, so it printed "776,287%" and "+87,655pp"
                in production. The finding belongs in the description, computed. */}
            <TrendChart
              data={gross}
              seriesLabels={{ [WEEKLY_BANK_TYPES.SECTOR]: "Gross NPL" }}
              title={tx("Gross NPL — Level (sector, TL bn · weekly)")}
              description={
                tx(stockNominalNow != null && stockRealNow != null
                  ? tx("The stock is growing {0} y/y — {1} in real terms. The ratio is a slow summary of it.", {0: fmtPct(stockNominalNow), 1: fmtPct(stockRealNow)})
                  : "Reported NPL stock, BDDK weekly bulletin")
              }
              source={tx("Source: BDDK weekly bulletin")}
              yFormat="bn"
              decimals={0}
              plain
            />
            <TrendChart
              data={coverageAll}
              seriesLabels={BANK_TYPE_LABELS}
              title={tx("Provisions / Gross NPL (%) — by group")}
              yFormat="pct"
              decimals={1}
              plain
            />
          </div>
        </Section>

        <Section
          index="03"
          title={tx("Where is it?")}
          description={tx("The composition behind the attribution bars — household credit and the commercial book.")}
        >
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <StackedArea
              data={cMix.map((r) => ({
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
              title={tx("Consumer NPL — Composition (sector, TL bn)")}
              yFormat="bn"
              decimals={0}
              plain
            />
            <TrendChart
              data={consumerTrend}
              seriesLabels={{
                HOUSING: "Housing",
                AUTO: "Auto",
                GPL: "Gen. Purpose",
                CARDS: "Retail Cards",
              }}
              title={tx("Consumer NPL Ratio by Product (%)")}
              yFormat="pct"
              decimals={2}
              plain
            />
          </div>
          <ChartRow
            data={commercialTrend}
            labels={{ SME: "SME", COMMERCIAL: "Commercial (all)", NONSME: "Non-SME (derived)" }}
            deltaPeriods={52}
            deltaLabel="52w"
          >
            <TrendChart
              data={commercialTrend}
              seriesLabels={{
                SME: "SME",
                COMMERCIAL: "Commercial (all)",
                NONSME: "Non-SME (derived)",
              }}
              title={tx("Commercial NPL Ratio (%) — sector")}
              description={
                tx(smeShareOfCommNpl != null && smeShareOfCommLoans != null
                  ? tx("SME is a SUBSET of commercial — {0}% of its bad loans on {1}% of its lending. The lines are not additive.", {0: smeShareOfCommNpl.toFixed(0), 1: smeShareOfCommLoans.toFixed(0)})
                  : "SME is a subset of commercial — the lines are not additive.")
              }
              yFormat="pct"
              decimals={2}
              height={320}
              plain
            />
          </ChartRow>
        </Section>

        <Section index="04" title={tx("Who holds it?")} description={tx("NPL by ownership group.")}>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <TrendChart
                data={nplAll}
                seriesLabels={BANK_TYPE_LABELS}
                title={
                  tx(seriesFinding(nplSector, { noun: "The NPL ratio", decimals: 2 }, tx.locale) ??
                  "NPL Ratio (%) — by group")
                }
                description={tx("Gross NPL / total loans, %, monthly · by ownership group")}
                source={tx("Source: BDDK monthly bulletin")}
                yFormat="pct"
                decimals={2}
                plain
              />
            </div>
            <BarByBank
              data={nplByBank}
              labels={BANK_TYPE_LABELS}
              title={tx("NPL by group · {0}", {0: nplByBank[0]?.period ?? ""})}
              format="pct"
              decimals={2}
              plain
            />
          </div>
        </Section>
      </Depth>

      <Colophon />
    </main>
  );
}
