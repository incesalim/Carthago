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

export const metadata: Metadata = {
  title: "Turkish Banks — Asset Quality & NPLs",
  description:
    "Non-performing loans, the Stage-2 watchlist the NPL ratio does not print, coverage and NPL formation across Türkiye's banking sector and by bank.",
  alternates: { canonical: "/asset-quality" },
};

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
    stageShares, migration, ladder, roll,
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

  // The two NPL ratios. NEVER mixed inside one calculation — the published one is
  // the official figure, the implied one is fresher; they differ by a stable
  // ~0.10pp (definitional). Each is quoted with its basis named.
  const impliedSeries = impliedRatio(gross, loansTotal);
  const impliedNow = lastVal(impliedSeries as TimeSeriesRow[]);
  const publishedNow = lastVal(nplSector);
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
  });

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
        <>
          The watchlist is <b className="font-semibold text-foreground">{fmtTrnFromBn(ladder.stage2Bn)}</b>{" "}
          against Stage 3&apos;s {fmtTrnFromBn(ladder.stage3Bn)}, and carries {fmtPct(ladder.cov2)}{" "}
          cover versus {fmtPct(ladder.cov3)}. Stage 2 is <em>not</em> impaired, so lower cover is
          expected — the migration sizing is what it would cost, not a shortfall owed.
        </>
      ) : null,
      clear: ladder ? (
        <>Stage-2 cover is {fmtPct(ladder.cov2)} against Stage 3&apos;s {fmtPct(ladder.cov3)}.</>
      ) : undefined,
    },
    {
      code: "formation_doubling",
      active: !!(formationMultiple && formationMultiple >= 1.5 && rollNow && rollNow.net > 0),
      rule: rollNow && rollPrev ? `formation(${rollNow.year}) ÷ formation(${rollPrev.year}) = ${formationMultiple?.toFixed(1)}×` : "formation ÷ prior year ≥ 1.5×",
      body: rollNow ? (
        <>
          New NPLs of <b className="font-semibold text-foreground">{fmtBn(rollNow.additions)}</b> against{" "}
          {fmtBn(rollNow.exits)} of exits — net{" "}
          <b className={`font-semibold ${toneClass(rollNow.net, "down")}`}>
            {signed(rollNow.net, fmtBn)}
          </b>
          .
          And the exits are{" "}
          <b className="font-semibold text-foreground">{rollNow.collectionShare.toFixed(0)}% collections</b>,
          not write-offs or sales: the ratio is not being managed down, the book is genuinely
          deteriorating.
        </>
      ) : null,
      clear: rollNow ? <>Formation of {fmtBn(rollNow.additions)} is not outrunning the prior year.</> : undefined,
    },
    {
      code: "stock_compounding",
      active: !!(stockRealNow != null && loanRealNow != null && stockRealNow > 3 * Math.max(loanRealNow, 0.1)),
      rule:
        stockRealNow != null && loanRealNow != null
          ? `npl_stock_real (${fmtPct(stockRealNow)}) > 3× loan_book_real (${fmtPct(loanRealNow)})`
          : "npl_stock_real > 3× loan_book_real",
      body: (
        <>
          Like for like, both CPI-deflated: the bad-loan stock grew{" "}
          <b className="font-semibold text-negative">{fmtPct(stockRealNow)}</b> in real terms against a
          loan book growing <b className="font-semibold text-foreground">{fmtPct(loanRealNow)}</b>.
        </>
      ),
      clear: <>The NPL stock is growing {fmtPct(stockRealNow)} in real terms.</>,
    },
    {
      code: "npl_ratio_streak",
      active: publishedRun >= 6,
      rule: `npl_ratio rising for ${publishedRun} consecutive months`,
      body: (
        <>
          {fmtPct(nplSector.at(-1 - publishedRun)?.value, 2)} → {fmtPct(publishedNow, 2)}. The ratio is
          registering the deterioration — slowly. It is the <em>level</em> that misleads, not the
          direction.
        </>
      ),
      clear: <>The NPL ratio has not risen for six months straight.</>,
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
    k: `${s.migratePct}% of the watchlist migrates`,
    v: signed(s.provisionBn, (v) => `₺${v.toFixed(0)}bn`),
    unit: "provisions",
    effect:
      s.pctOfEclStock != null ? (
        <>{signed(s.pctOfEclStock, (v) => `${v.toFixed(1)}%`)} of ECL stock</>
      ) : null,
  }));

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title="Asset Quality"
        record={
          <>
            Record <b className="font-normal text-foreground">{monthLabel(nplSector.at(-1)?.period)}</b>{" "}
            · stock to W/E {asOf ? weekLabel(asOf) : "—"} · stages quarterly
          </>
        }
        right="every figure computed from source series"
      />

      {/* ── The waterline — what the ratio doesn't print ─────────────────── */}
      <SecHead
        title="What the ratio doesn't print"
        meta="TFRS-9 staging · % of gross loans"
        action={
          ladder ? (
            <span className="font-mono text-[8.5px] uppercase tracking-[0.07em] text-faint">
              audited {ladder.period} · n={ladder.n}
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
                The headline NPL ratio is the{" "}
                <b className="font-mono font-semibold text-negative">{fmtPct(ladder.stage3Share)}</b>{" "}
                tip. Loans the banks themselves classify as deteriorated are{" "}
                <b className="font-mono font-semibold text-negative">{fmtPct(ladder.problemShare)}</b> —{" "}
                <b className="font-semibold text-negative">{ladder.multipleOfPrinted.toFixed(1)}×</b> as
                much.
              </p>
              <p className="mt-3 text-[12.5px] leading-relaxed text-muted-foreground">
                <b className="font-semibold text-foreground">
                  {((ladder.stage2Bn / ladder.problemBn) * 100).toFixed(0)}%
                </b>{" "}
                of that problem book is Stage 2 — the watchlist that never reaches the ratio. It
                carries <b className="font-semibold text-foreground">{fmtPct(ladder.cov2)}</b> cover
                against Stage 3&apos;s {fmtPct(ladder.cov3)}.
              </p>
              {rollNow && formationMultiple && (
                <p className="mt-3 text-[12.5px] leading-relaxed text-muted-foreground">
                  Stage 2 is <em>not</em> impaired, so its lower cover is expected rather than a
                  shortfall. What matters is that the pipeline behind the tip is still filling:
                  formation ran{" "}
                  <b className="font-semibold text-foreground">{formationMultiple.toFixed(1)}×</b> last
                  year, net{" "}
                  <b className={`font-semibold ${toneClass(rollNow.net, "down")}`}>
                    {signed(rollNow.net, fmtBn)}
                  </b>
                  .
                </p>
              )}
              <p className="mt-3 border-t border-hair pt-2.5 font-mono text-[9px] uppercase leading-relaxed tracking-[0.06em] text-faint">
                problem loans = stage2 + stage3, both from the audited TFRS-9 filings · the{" "}
                {ladder.multipleOfPrinted.toFixed(1)}× is {fmtPct(ladder.problemShare)} ÷{" "}
                {fmtPct(ladder.stage3Share)}, same source — never divided by the published ratio
              </p>
            </>
          ) : (
            <p className="text-[12px] text-faint">The staging ladder awaits an audited quarter.</p>
          )}
        </div>
      </div>

      {/* ── The vitals ──────────────────────────────────────────────────── */}
      <SecHead title="The vitals" meta="stock · pipeline · cover" className="mb-2.5 mt-8" />
      <Vitals>
        <Vital
          label="Problem loans, S2+S3"
          value={ladder ? ladder.problemShare.toFixed(1) : "—"}
          unit="%"
          series={stage2.map((r, i) => ({
            period: r.period,
            value: (r.value ?? 0) + (stage3[i]?.value ?? 0),
          }))}
          decimals={1}
          note={
            ladder ? (
              <>
                <em className="font-semibold not-italic text-negative">
                  {ladder.multipleOfPrinted.toFixed(1)}×
                </em>{" "}
                the Stage-3 ratio the headline prints — {fmtTrnFromBn(ladder.problemBn)} of loans (
                {ladder.period})
              </>
            ) : undefined
          }
        />
        <Vital
          label="Cover on the problem book"
          value={ladder ? ladder.problemCov.toFixed(1) : "—"}
          unit="%"
          series={stage2.map((r) => ({ period: r.period, value: r.value }))}
          decimals={1}
          note={
            ladder ? (
              <>
                Stage 2 at <b className="font-semibold text-foreground">{fmtPct(ladder.cov2)}</b> vs
                Stage 3 at <b className="font-semibold text-foreground">{fmtPct(ladder.cov3)}</b> —{" "}
                {fmtBn(ladder.provisionsBn)} of provisions
              </>
            ) : undefined
          }
        />
        <Vital
          label="NPL stock, real y/y"
          value={stockRealNow != null ? stockRealNow.toFixed(1) : "—"}
          unit="%"
          series={(stockRealYoY as TimeSeriesRow[]).slice(-26)}
          decimals={1}
          note={
            stockRealNow != null && loanRealNow != null ? (
              <>
                bad loans compounding — the loan book grew just {fmtPct(loanRealNow)} real ·{" "}
                <Link href="/credit" className="font-semibold text-primary">
                  /credit
                </Link>
              </>
            ) : (
              "awaits the CPI print"
            )
          }
        />
        <Vital
          label="Net NPL formation"
          // Net formation turning negative is the GOOD case — the stock is
          // shrinking. It used to render "+-42".
          value={rollNow ? signed(rollNow.net, (v) => String(Math.round(v))) : "—"}
          unit="₺bn"
          series={roll.map((y) => ({ period: y.year, value: y.net }))}
          format="raw"
          decimals={0}
          note={
            rollNow && formationMultiple ? (
              <>
                formation <b className="font-semibold text-foreground">{formationMultiple.toFixed(1)}×</b>{" "}
                last year · exits are{" "}
                <b className="font-semibold text-foreground">
                  {rollNow.collectionShare.toFixed(0)}% collections
                </b>
              </>
            ) : undefined
          }
        />
        <Vital
          label="NPL ratio, as printed"
          value={publishedNow != null ? publishedNow.toFixed(2) : "—"}
          unit="%"
          series={nplSector.slice(-24)}
          decimals={2}
          note={
            publishedRun >= 3 ? (
              <>
                <em className="font-semibold not-italic text-negative">
                  {publishedRun} straight monthly rises
                </em>{" "}
                — BDDK published basis
              </>
            ) : (
              "BDDK published basis"
            )
          }
        />
        <Vital
          label="SME NPL"
          value={sme ? sme.now.toFixed(2) : "—"}
          unit="%"
          series={(sme?.series ?? []).slice(-26) as TimeSeriesRow[]}
          decimals={2}
          note={
            sme && attrib.memo ? (
              <>
                {signedPp(sme.delta, 2)} in 52w — SME drove{" "}
                <b className="font-semibold text-foreground">{attrib.memo.share.toFixed(1)}%</b> of all
                new bad loans
              </>
            ) : undefined
          }
        />
      </Vitals>

      {/* ── The pipeline behind the tip ─────────────────────────────────── */}
      <SecHead
        title="The pipeline behind the tip"
        meta="audited NPL roll-forward · annual · ₺bn"
        className="mb-2.5 mt-8"
      />
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
        <div>
          <FormationBars data={roll} />
          {rollNow && formationMultiple && rollPrev && (
            <p className="mt-2 text-[11.5px] leading-relaxed text-muted-foreground">
              Formation is <b className="font-semibold text-foreground">{formationMultiple.toFixed(1)}×</b>{" "}
              last year ({fmtBn(rollPrev.additions)} → {fmtBn(rollNow.additions)}), net{" "}
              <b className={`font-semibold ${toneClass(rollNow.net, "down")}`}>
                {signed(rollNow.net, fmtBn)}
              </b>
              . Exits are{" "}
              <b className="font-semibold text-foreground">
                {rollNow.collectionShare.toFixed(0)}% collections
              </b>{" "}
              — not write-offs or sales.{" "}
              <em>The ratio is not being managed down; the book is genuinely deteriorating.</em>
            </p>
          )}
        </div>
        <div>
          <SecHead
            title="If the watchlist migrates"
            meta="sizing device — not a forecast"
            className="mb-2.5 mt-0"
          />
          {migrationItems.length > 0 ? (
            <>
              <Transmission items={migrationItems} />
              <p className="mt-2.5 text-[9.5px] leading-relaxed text-faint">
                Migration provisioned at Stage 3&apos;s rate (
                {migration.cov3 != null ? `${(migration.cov3 * 100).toFixed(0)}%` : "—"}) against Stage
                2 today ({migration.cov2 != null ? `${(migration.cov2 * 100).toFixed(0)}%` : "—"}), on a
                ₺{migration.stage2Bn?.toFixed(0)}bn book · {migration.period}. Stage 2 is{" "}
                <b className="font-semibold text-muted-foreground">not</b> impaired — this is what
                migration would cost, <b className="font-semibold text-muted-foreground">not a gap the
                banks owe</b>.
              </p>
            </>
          ) : (
            <p className="text-[12px] text-faint">
              The migration sizing needs Stage-3 cover above Stage-2 cover in the latest filing.
            </p>
          )}
        </div>
      </div>

      {/* ── Where the new bad loans came from ───────────────────────────── */}
      <div className="mt-8 grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,7fr)_minmax(260px,4fr)]">
        <div>
          <SecHead
            title="Where the new bad loans came from"
            meta={`share of the ₺${(attrib.totalDelta / 1_000_000).toFixed(2)}trn increase · 52w`}
            className="mb-2.5 mt-0"
          />
          <Attribution
            rows={attrib.items.map((i) => {
              const seg = segs.find((s) => s.key === i.key);
              return {
                key: i.key,
                label: i.label,
                value: i.share,
                meta: seg ? `${seg.now.toFixed(2)}% NPL · ${signedPp(seg.delta, 2)}` : undefined,
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
                <>
                  segments reconcile to the NPL stock — SME is a cut of commercial (
                  {smeShareOfCommNpl.toFixed(0)}% of its bad loans on {smeShareOfCommLoans.toFixed(0)}%
                  of its lending), not an addition
                </>
              ) : (
                <>segments reconcile to the NPL stock — SME is a cut of commercial, not an addition</>
              )
            }
            totalMeta={`₺${(attrib.totalDelta / 1_000_000).toFixed(2)}trn added`}
          />
        </div>
        <div>
          <SecHead title="Movers" meta="NPL ratio · 52w" className="mb-2.5 mt-0" />
          <Movers from="52w ago" to="Now" rows={moverRows} />
        </div>
      </div>

      {/* ── Flags ───────────────────────────────────────────────────────── */}
      <SecHead title="Flags" meta="each prints the rule that raised it" className="mb-2.5 mt-8" />
      <Flags flags={flags} showCleared quietNote="No asset-quality rule fired this month." />

      {/* ── The two honesty footnotes ───────────────────────────────────── */}
      <div className="mt-7 grid grid-cols-1 gap-7 border-t border-hair pt-3.5 sm:grid-cols-2">
        <div>
          <h4 className="mb-1 text-[10.5px] font-semibold text-foreground">
            Why we do <em>not</em> claim inflation flatters the ratio
          </h4>
          <p className="text-[10px] leading-relaxed text-faint">
            An NPL ratio is <b className="text-muted-foreground">NPL ÷ loans</b>. Deflate both legs by
            CPI and it is <b className="text-muted-foreground">unchanged</b> — a ratio is
            deflator-invariant. Only <b className="text-muted-foreground">real</b> book growth dilutes
            it, and that was {fmtPct(loanRealNow)}: worth about{" "}
            <b className="text-muted-foreground">0.1pp</b>, not the ~1pp a nominally-frozen-book
            counterfactual would suggest. A real bias does exist — the numerator is stale (a loan that
            defaulted two years ago sits at its origination principal) while the denominator reprices —
            but sizing it needs origination-vintage data we do not have, so we put no number on it.
          </p>
        </div>
        <div>
          <h4 className="mb-1 text-[10.5px] font-semibold text-foreground">Two NPL ratios, one page</h4>
          <p className="text-[10px] leading-relaxed text-faint">
            The published ratio (BDDK monthly,{" "}
            <b className="text-muted-foreground">{fmtPct(publishedNow, 2)}</b>) and the ratio implied by
            the weekly bulletin (<b className="text-muted-foreground">{fmtPct(impliedNow, 2)}</b>) differ
            by a stable <b className="text-muted-foreground">~0.10pp</b> — definitional, not noise. They
            are never mixed inside one calculation; the vitals quote the published figure and say so,
            while the stock and its segments come from the weekly feed.
          </p>
        </div>
      </div>

      {/* ── In depth — the evidence layer ───────────────────────────────── */}
      <Depth
        meta="carried over, reordered by question — nothing removed"
        action={<GlobalRangeSelector />}
      >
        <Takeaway data={await withLlmHeadline("asset-quality", read)} variant="desk" />

        <Section
          index="01"
          title="What is coming?"
          description="How the watchlist has built up. The roll-forward and the migration sizing sit in the brief above."
        >
          {stageShares.length > 0 && (
            <TrendChart
              data={stageShares}
              seriesLabels={STAGE_SHARE_LABELS}
              title="TFRS-9 staging — % of gross loans (audited quarterly)"
              description="Stage 2 is the watchlist the NPL ratio never prints."
              yFormat="pct"
              decimals={1}
              plain
            />
          )}
        </Section>

        <Section
          index="02"
          title="Is the stock or the ratio moving?"
          description="The stock is the fast-moving series; the ratio is a slow summary of it."
        >
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {/* NOT a seriesFinding title. That helper renders values as a PERCENT
                with pp deltas over a 12-POINT window (≈ a year of MONTHLY data).
                This is a weekly ₺ level, so it printed "776,287%" and "+87,655pp"
                in production. The finding belongs in the description, computed. */}
            <TrendChart
              data={gross}
              seriesLabels={{ [WEEKLY_BANK_TYPES.SECTOR]: "Gross NPL" }}
              title="Gross NPL — Level (sector, TL bn · weekly)"
              description={
                stockNominalNow != null && stockRealNow != null
                  ? `The stock is growing ${fmtPct(stockNominalNow)} y/y — ${fmtPct(stockRealNow)} in real terms. The ratio is a slow summary of it.`
                  : "Reported NPL stock, BDDK weekly bulletin"
              }
              source="Source: BDDK weekly bulletin"
              yFormat="bn"
              decimals={0}
              plain
            />
            <TrendChart
              data={coverageAll}
              seriesLabels={BANK_TYPE_LABELS}
              title="Provisions / Gross NPL (%) — by group"
              yFormat="pct"
              decimals={1}
              plain
            />
          </div>
        </Section>

        <Section
          index="03"
          title="Where is it?"
          description="The composition behind the attribution bars — household credit and the commercial book."
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
              title="Consumer NPL — Composition (sector, TL bn)"
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
              title="Consumer NPL Ratio by Product (%)"
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
              title="Commercial NPL Ratio (%) — sector"
              description={
                smeShareOfCommNpl != null && smeShareOfCommLoans != null
                  ? `SME is a SUBSET of commercial — ${smeShareOfCommNpl.toFixed(0)}% of its bad loans on ${smeShareOfCommLoans.toFixed(0)}% of its lending. The lines are not additive.`
                  : "SME is a subset of commercial — the lines are not additive."
              }
              yFormat="pct"
              decimals={2}
              height={320}
              plain
            />
          </ChartRow>
        </Section>

        <Section index="04" title="Who holds it?" description="NPL by ownership group.">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <TrendChart
                data={nplAll}
                seriesLabels={BANK_TYPE_LABELS}
                title={
                  seriesFinding(nplSector, { noun: "The NPL ratio", decimals: 2 }) ??
                  "NPL Ratio (%) — by group"
                }
                description="Gross NPL / total loans, %, monthly · by ownership group"
                source="Source: BDDK monthly bulletin"
                yFormat="pct"
                decimals={2}
                plain
              />
            </div>
            <BarByBank
              data={nplByBank}
              labels={BANK_TYPE_LABELS}
              title={`NPL by group · ${nplByBank[0]?.period ?? ""}`}
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
