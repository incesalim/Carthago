/**
 * Loans by sector — the Desk brief above the carried-over evidence.
 *
 * The first dashboard use of the BDDK monthly bulletin's sector cut (`loans`
 * table 5): the ~22-sector NACE breakdown of the loan book, with an NPL stock
 * per sector. The page leads with WHERE the credit is allocated (the share
 * stack), then says WHERE the risk is (the calm ~2.7% headline NPL hides a
 * spread from ~0.2% housing to ~5% consumer), then how the mix has shifted in
 * real terms. All arithmetic lives in app/lib/loans-by-sector.ts.
 *
 * Sourced from the monthly bulletin (sector aggregate, all banks) — table 5 has
 * no per-bank or FX/maturity split, so this is the whole-sector book only. Units:
 * table 5 is thousand-TL, divided to million-TL in the lib module.
 */
import type { Metadata } from "next";
import Link from "next/link";
import {
  loansBySector,
  GROUP_ORDER,
  GROUP_LABELS,
  MATERIAL_SHARE,
} from "@/app/lib/loans-by-sector";
import { Section } from "@/app/components/ui";
import {
  Colophon,
  Depth,
  DeskHeader,
  Flags,
  Movers,
  SecHead,
  Vital,
  Vitals,
  type Flag,
  type MoverRow,
} from "@/app/components/desk";
import { lastVal, monthLabel, signedPp, valAgo } from "@/app/lib/desk";
import { VERBS, claim, direction, toneClass } from "@/app/lib/prose";
import { GlobalRangeSelector } from "@/app/components/range-context";
import BarByBank from "@/app/components/BarByBank";
import TrendChart from "@/app/components/TrendChart";
import StackedArea from "@/app/components/StackedArea";
import Attribution from "@/app/components/Attribution";
import Takeaway from "@/app/components/Takeaway";
import { loansBySectorInsights } from "@/app/lib/insights";
import { seriesFinding } from "@/app/lib/chart-findings";
import { REAL_TERMS_LABELS } from "@/app/lib/real-terms";
import type { TimeSeriesRow } from "@/app/lib/metrics";
import SectorHeatmap from "./SectorHeatmap";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkish Banking Sector — Loans by Sector",
  description:
    "The Turkish loan book by economic sector — where credit is allocated and where non-performing loans concentrate, from the BDDK monthly bulletin (table 5). Manufacturing, credit cards, trade and consumer credit, with an NPL ratio per sector.",
  alternates: { canonical: "/loans-by-sector" },
};

const pct = (v: number | null | undefined, d = 1) => (v == null ? "—" : `${v.toFixed(d)}%`);
const trn = (mn: number) => `₺${(mn / 1_000_000).toFixed(1)} trn`;

export default async function LoansBySectorPage() {
  const d = await loansBySector();

  const asOfLabel = monthLabel(d.asOf);
  const yearAgoLabel = monthLabel(`${Number(d.asOf.slice(0, 4)) - 1}${d.asOf.slice(4)}`, false);

  // ── headline scalars, all computed from the struct ────────────────────────
  const nplNow = d.headlineNplRatio;
  const nplPrev = valAgo(d.nplRatioSeries, 12);
  const nplDelta = nplPrev != null ? nplNow - nplPrev : null;

  const realNow = lastVal(d.bookYoYReal);
  const nomNow = lastVal(d.bookYoYNominal);

  const consumer = d.groups.find((g) => g.key === "consumer") ?? null;
  const industry = d.groups.find((g) => g.key === "industry") ?? null;
  const consMover = d.movers.find((m) => m.key === "consumer") ?? null;
  const consDelta =
    consMover?.shareNow != null && consMover?.shareThen != null
      ? consMover.shareNow - consMover.shareThen
      : null;

  // Material sectors (drop the tiny-book noise, e.g. households at 15% on ₺2bn).
  const material = d.sectors.filter((s) => s.share >= MATERIAL_SHARE);
  const byNpl = [...material].sort((a, b) => b.nplRatio - a.nplRatio);
  const worst = byNpl[0] ?? null;
  const best = byNpl.at(-1) ?? null;
  const topGroup = [...d.groups].sort((a, b) => b.book - a.book)[0] ?? null;

  // Consumer share at a record → a computed flag, not a typed claim.
  const consVals = d.consumerShareSeries.filter((r) => r.value != null).map((r) => r.value as number);
  const consMax = consVals.length ? Math.max(...consVals) : null;
  const consumerAtHigh = consumer != null && consMax != null && consumer.share >= consMax - 1e-9;

  // ── ranked-bar + attribution data ─────────────────────────────────────────
  const sizeBars = d.sectors.map((s) => ({ bank_type_code: s.key, value: s.book }));
  const sizeLabels = Object.fromEntries(d.sectors.map((s) => [s.key, s.label]));
  const nplBars = material.map((s) => ({ bank_type_code: s.key, value: s.nplRatio }));
  const nplLabels = Object.fromEntries(material.map((s) => [s.key, s.label]));

  // NPL-stock contribution to the headline ratio, by group: each group's
  // groupNpl / totalBook (pp), which sums to the headline exactly.
  const nplContrib = [...d.groups]
    .filter((g) => g.npl > 0)
    .sort((a, b) => b.npl - a.npl)
    .map((g) => ({
      key: g.key,
      label: g.label,
      value: (g.npl / d.totalBook) * 100,
      meta: `${pct(g.nplRatio)} of a ${trn(g.book)} book`,
    }));
  const nplContribSum = nplContrib.reduce((a, c) => a + c.value, 0);

  // ── time-series for the depth charts ──────────────────────────────────────
  const bookGrowthLong: TimeSeriesRow[] = [
    ...d.bookYoYNominal.map((r) => ({ period: r.period, code: "NOMINAL", value: r.value })),
    ...d.bookYoYReal.map((r) => ({ period: r.period, code: "REAL", value: r.value })),
  ].flatMap((r) =>
    r.value == null ? [] : [{ period: r.period, bank_type_code: r.code, value: r.value }],
  );

  const groupShareLong: TimeSeriesRow[] = d.groupStack.flatMap((row) => {
    const total = GROUP_ORDER.reduce((a, g) => a + Number(row[g] ?? 0), 0);
    if (total <= 0) return [];
    return GROUP_ORDER.map((g) => ({
      period: String(row.period),
      bank_type_code: g as string,
      value: (Number(row[g] ?? 0) / total) * 100,
    }));
  });
  const groupLabels = Object.fromEntries(GROUP_ORDER.map((g) => [g, GROUP_LABELS[g]]));
  const groupStackSeries = GROUP_ORDER.map((g) => ({ key: g, label: GROUP_LABELS[g] }));

  // ── movers — 12m group share change ───────────────────────────────────────
  const moverRows: MoverRow[] = d.movers
    .map((m) => ({
      label: m.label,
      prev: m.shareThen,
      curr: m.shareNow,
      fmt: (v: number) => `${v.toFixed(1)}%`,
      deltaDecimals: 1,
      good: "neutral" as const,
    }))
    .filter((r) => r.curr != null)
    .sort((a, b) => {
      const da = a.curr != null && a.prev != null ? a.curr - a.prev : -Infinity;
      const db = b.curr != null && b.prev != null ? b.curr - b.prev : -Infinity;
      return db - da;
    });

  // ── the Read — deterministic, from the same series the charts show ─────────
  const read = loansBySectorInsights({
    asOf: d.asOf,
    headlineNpl: nplNow,
    bookYoYReal: d.bookYoYReal,
    consumerShare: d.consumerShareSeries,
    topGroup: topGroup ? { label: topGroup.label, share: topGroup.share } : null,
    worstSector: worst ? { label: worst.label, nplRatio: worst.nplRatio } : null,
    bestSector: best ? { label: best.label, nplRatio: best.nplRatio } : null,
  });

  // ── flags — each prints the rule that raised it ───────────────────────────
  const flags: Flag[] = [
    {
      code: "consumer_share_high",
      active: consumerAtHigh,
      rule: "consumer_share == max(history)",
      body: (
        <>
          Consumer credit is at the top of its recorded range — {pct(consumer?.share)} of the book
          {consDelta != null ? <> ({signedPp(consDelta, 1)} over 12m)</> : null}. Unsecured retail is
          where NPLs run hottest; watch it in{" "}
          <Link href="/asset-quality" className="font-semibold text-primary">
            /asset-quality
          </Link>
          .
        </>
      ),
      clear: <>Consumer credit&apos;s share of the book is off its recorded top.</>,
    },
    {
      code: "sector_npl_dispersion",
      active: worst != null && worst.nplRatio > 2 * nplNow,
      rule: `max_material_sector_npl > 2 × headline (${pct(nplNow, 1)})`,
      body: (
        <>
          {worst?.label} carries an NPL ratio of {pct(worst?.nplRatio, 1)} — more than double the{" "}
          {pct(nplNow, 1)} sector headline. The average is calm; the book is not calm everywhere.
        </>
      ),
      clear: <>No material sector runs at more than twice the headline NPL ratio.</>,
    },
    {
      code: "real_book_contraction",
      active: realNow != null && realNow < 0,
      rule: "book_yoy_real(12m) < 0",
      body: (
        <>
          The loan book is contracting in real terms — {pct(realNow, 1)} once inflation is stripped,
          even as the nominal print reads {pct(nomNow, 0)}.
        </>
      ),
      clear: <>The loan book is growing in real terms at {pct(realNow, 1)}.</>,
    },
  ];

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title="Loans by Sector"
        record={
          <>
            Record <b className="font-normal text-foreground">{asOfLabel}</b> · vs {yearAgoLabel}
          </>
        }
        right="every figure computed from BDDK table 5"
      />

      {/* ── Hero: how the credit is allocated ────────────────────────────── */}
      <SecHead
        title="How the credit is allocated"
        meta="share of the sector loan book · by super-group · monthly"
        className="mb-2.5 mt-6"
      />
      <div className="grid grid-cols-1 gap-8 border-t-2 border-foreground pt-4 lg:grid-cols-[minmax(0,7fr)_minmax(260px,4fr)]">
        <StackedArea
          data={d.groupStack}
          series={groupStackSeries}
          title="Loan book by sector — share of total (%)"
          description="each band is a super-group's share of the whole sector loan book · monthly"
          source="Source: BDDK monthly bulletin, table 5 (sector aggregate)"
          percentStack
          height={340}
          plain
        />
        <div className="self-center">
          <p className="text-[19px] leading-snug tracking-tight text-foreground">
            The sector&apos;s {trn(d.totalBook)} loan book concentrates in a few blocks —{" "}
            <b className="font-mono font-semibold">{pct(consumer?.share)}</b> consumer credit,{" "}
            <b className="font-mono font-semibold">{pct(industry?.share)}</b> industry.
          </p>
          <p className="mt-3 text-[12.5px] leading-relaxed text-muted-foreground">
            The calm <b className="font-mono">{pct(nplNow, 1)}</b> headline NPL hides its spread:{" "}
            {worst && best ? (
              <>
                {worst.label.toLowerCase()} runs {pct(worst.nplRatio, 1)}, against {best.label.toLowerCase()}{" "}
                at {pct(best.nplRatio, 1)}.
              </>
            ) : (
              "sector ratios vary widely around it."
            )}
          </p>
          <p className="mt-3 border-t border-hair pt-2.5 font-mono text-[9px] uppercase leading-relaxed tracking-[0.06em] text-faint">
            share = sector book ÷ Σ sector books · npl ratio = takipteki ÷ book · table 5 is
            thousand-TL, shown in ₺
          </p>
        </div>
      </div>

      {/* ── The vitals ───────────────────────────────────────────────────── */}
      <SecHead title="The vitals" meta="sector aggregate · latest month" className="mb-2.5 mt-8" />
      <Vitals cols={4}>
        <Vital
          label="Total loan book"
          value={`₺${(d.totalBook / 1_000_000).toFixed(1)}`}
          unit="trn"
          series={d.totalBookSeries.slice(-36)}
          format="trn"
          decimals={1}
          note={
            nomNow != null ? (
              <>
                {pct(nomNow, 0)} nominal
                {realNow != null ? <> · {pct(realNow, 1)} real over 12m</> : null}
              </>
            ) : undefined
          }
        />
        <Vital
          label="Real book growth, 12m"
          value={realNow != null ? `${realNow < 0 ? "−" : ""}${Math.abs(realNow).toFixed(1)}` : "—"}
          unit="%"
          series={d.bookYoYReal.slice(-36)}
          decimals={1}
          note={
            realNow != null ? (
              <>
                the book{" "}
                <em className={`font-semibold not-italic ${toneClass(realNow, "up")}`}>
                  {direction(realNow, VERBS.size)}
                </em>{" "}
                once inflation is stripped
              </>
            ) : undefined
          }
        />
        <Vital
          label="Consumer share"
          value={consumer != null ? consumer.share.toFixed(1) : "—"}
          unit="%"
          series={d.consumerShareSeries.slice(-36)}
          decimals={1}
          note={
            consDelta != null ? (
              <>
                {signedPp(consDelta, 1)} over 12m — cards, general-purpose, housing &amp; auto as one
                book
              </>
            ) : (
              "cards, general-purpose, housing & auto"
            )
          }
        />
        <Vital
          label="Headline NPL ratio"
          value={nplNow.toFixed(2)}
          unit="%"
          series={d.nplRatioSeries.slice(-36)}
          decimals={2}
          note={
            nplDelta != null ? (
              <>
                {signedPp(nplDelta, 2)} over 12m —{" "}
                {worst ? `${worst.label.toLowerCase()} is the hot spot at ${pct(worst.nplRatio, 1)}` : "wide dispersion by sector"}
              </>
            ) : undefined
          }
        />
      </Vitals>

      {/* ── Movers ───────────────────────────────────────────────────────── */}
      <SecHead
        title="Movers"
        meta="share of the book · change over 12 months"
        className="mb-2.5 mt-8"
      />
      <Movers from={yearAgoLabel} to="Now" rows={moverRows} />

      {/* ── Flags ────────────────────────────────────────────────────────── */}
      <SecHead title="Flags" meta="each prints the rule that raised it" className="mb-2.5 mt-8" />
      <Flags flags={flags} showCleared quietNote="No sector rule fired this month." />

      {/* ── In depth — the evidence layer ────────────────────────────────── */}
      <Depth meta="carried over, ordered by question — nothing removed" action={<GlobalRangeSelector />}>
        <Takeaway data={read} variant="desk" />

        <Section
          index="01"
          title="Where the credit sits"
          description={
            claim(
              d.sectors.length >= 2,
              `The whole sector book, ranked. ${d.sectors[0]?.label} and ${d.sectors[1]?.label} are the two biggest single lines.`,
            ) ?? "The whole sector loan book, ranked by size."
          }
        >
          <BarByBank
            data={sizeBars}
            labels={sizeLabels}
            title="Loan book by sector (₺ bn)"
            format="bn"
            decimals={0}
            height={560}
            plain
          />
        </Section>

        <Section
          index="02"
          title="Where the risk sits"
          description="The headline NPL is a book-weighted average. Ranked by ratio, the dispersion is the story — and the stock contribution says which sectors actually move the headline."
        >
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <BarByBank
              data={nplBars}
              labels={nplLabels}
              title="NPL ratio by sector (%)"
              format="pct"
              decimals={1}
              height={420}
              plain
            />
            <div>
              <div className="mb-2 font-mono text-[9px] uppercase tracking-[0.07em] text-faint">
                NPL stock — contribution to the {pct(nplNow, 1)} headline
              </div>
              <Attribution
                rows={nplContrib}
                sum={nplContribSum}
                fmtValue={(v) => `${v >= 0 ? "" : "−"}${Math.abs(v).toFixed(2)}pp`}
                reconciliation="each group's NPL stock ÷ the total book — the parts sum to the headline ratio"
                totalMeta={`${trn(d.totalNpl)} of NPLs on a ${trn(d.totalBook)} book`}
              />
            </div>
          </div>
        </Section>

        <Section
          index="03"
          title="How the mix has shifted"
          description="The book grows nominally with inflation; the share view is the inflation-neutral read. Each super-group's share trajectory since 2020 shows where credit has rotated."
        >
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <StackedArea
              data={d.groupStack}
              series={groupStackSeries}
              title="Loan book by sector — level (₺ trn)"
              description="nominal ₺, so the shape is mostly the price level — the share view above is the real read"
              yFormat="trn"
              decimals={1}
              plain
            />
            <TrendChart
              data={groupShareLong}
              seriesLabels={groupLabels}
              title="Sector shares over time (%)"
              description="each super-group's share of the book · monthly"
              yFormat="pct"
              decimals={1}
              plain
            />
          </div>
          <div className="grid grid-cols-1 gap-4">
            <TrendChart
              data={bookGrowthLong}
              seriesLabels={REAL_TERMS_LABELS}
              title={
                seriesFinding(d.bookYoYReal as TimeSeriesRow[], {
                  noun: "Real loan-book growth",
                  decimals: 1,
                }) ?? "Loan-book growth — nominal vs real (%)"
              }
              description="whole-book growth YoY, %, monthly · CPI-deflated twin (Fisher form)"
              source="Source: BDDK monthly bulletin · TÜİK CPI"
              yFormat="pct"
              decimals={1}
              zeroLine
              plain
            />
          </div>
        </Section>

        <Section
          index="04"
          title="Which sectors are heating up"
          description="NPL ratio by sector across quarter-ends — a sector warming from green to red is where the next problem book is forming."
        >
          <SectorHeatmap rows={d.heatmap.rows} periods={d.heatmap.periods} cells={d.heatmap.cells} />
        </Section>
      </Depth>

      <Colophon />
    </main>
  );
}
