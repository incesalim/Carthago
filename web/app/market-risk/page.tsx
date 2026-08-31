/**
 * Market Risk tab — CAMELS "S" (Sensitivity to market risk). Homes spine S8
 * (the dashboard audit's P0). Per-bank §4 audit data aggregated "of reporting
 * banks": FX net open position and the interest-rate repricing gap.
 *
 * Securities mark-to-market (the third S-signal) is a documented fast-follow —
 * see web/app/lib/market-risk.ts.
 */
import { localizeMetadata } from "@/i18n/metadata";
import { getText } from "@/i18n/server";
import type { Metadata } from "next";
import Link from "next/link";
import { Section, Stat } from "@/app/components/ui";
import { ChartCard } from "@/app/components/ui/chart-card";
import {
  Colophon,
  Depth,
  DeskHeader,
  SecHead,
  Vital,
  Vitals,
} from "@/app/components/desk";
import { lastVal, monthLabel, signedPp, valAgo } from "@/app/lib/desk";
import TrendChart from "@/app/components/TrendChart";
import BopFlowChart from "@/app/components/BopFlowChart";
import {
  fxNopToCapital,
  fxByCurrency,
  FX_CURRENCY_BARS,
  repricingGap1y,
  repricingLadder,
  marketRiskLatestPeriod,
  niiSensitivity,
} from "@/app/lib/market-risk";
import Takeaway from "@/app/components/Takeaway";
import { marketRiskInsights } from "@/app/lib/insights";
import { seriesFinding } from "@/app/lib/chart-findings";
import { withLlmHeadline } from "@/app/lib/read-headlines";

export const dynamic = "force-dynamic";

const pageMetadata: Metadata = {
  title: "Turkish Banks — Market Risk (FX & Repricing)",
  description: "Market-risk profile of Türkiye's banks — FX net open position and interest-rate repricing gaps from BRSA disclosures.",
  alternates: { canonical: "/market-risk" },
};

export async function generateMetadata(): Promise<Metadata> {
  return localizeMetadata(pageMetadata);
}

const SECTOR = { SECTOR: "Sector (reporting banks)" };

// The ≤1y buckets of the repricing ladder, keyed by their display labels
// (market-risk.ts BUCKET_LABEL) — used to derive the ₺bn short-gap vital.
const LE_1Y_LABELS = new Set(["≤1 month", "1–3 months", "3–12 months"]);

export default async function MarketRiskPage() {
  const tx = await getText();
  const [nop, byCcy, gap1y, ladder, latest, nii] = await Promise.all([
    fxNopToCapital(),
    fxByCurrency(),
    repricingGap1y(),
    repricingLadder(),
    marketRiskLatestPeriod(),
    niiSensitivity(),
  ]);

  // "The Read" — deterministic, computed from the same series the charts show.
  const read = marketRiskInsights({ nop, gap1y }, tx.locale);

  // ---- the brief's computed vitals -----------------------------------------
  const nopNow = lastVal(nop);
  const nopHeadroom = nopNow != null ? 20 - Math.abs(nopNow) : null; // vs the ±20% limit
  const gapNow = lastVal(gap1y);
  const gap4qAgo = valAgo(gap1y, 4);
  const gapD4q = gapNow != null && gap4qAgo != null ? gapNow - gap4qAgo : null;

  // ≤1y net repricing gap in ₺bn, off the latest ladder — same rows the ladder
  // chart renders; deepest bucket = the largest |gap| among the ≤1y buckets.
  const le1yRows = ladder.data
    .filter((r) => LE_1Y_LABELS.has(String(r.x)) && typeof r.gap === "number")
    .map((r) => ({ x: String(r.x), gap: r.gap as number }));
  const le1yBn = le1yRows.length
    ? le1yRows.reduce((s, r) => s + r.gap, 0)
    : null;
  const deepest = le1yRows.length
    ? le1yRows.reduce((a, b) => (Math.abs(b.gap) > Math.abs(a.gap) ? b : a))
    : null;

  // First-order ΔNII for the +250bp scenario (same math as the panel below).
  const nii250 = nii.scenarios.find((s) => s.bps === 250) ?? null;

  // Largest single-currency net position, off the latest by-currency row.
  const ccyLast = byCcy.at(-1) ?? null;
  const ccyEntries = ccyLast
    ? (["USD", "EUR", "Other"] as const)
        .map((k) => ({ k: k === "Other" ? "other FC" : k, v: ccyLast[k] }))
        .filter((e): e is { k: string; v: number } => typeof e.v === "number")
    : [];
  const bigCcy = ccyEntries.length
    ? ccyEntries.reduce((a, b) => (Math.abs(b.v) > Math.abs(a.v) ? b : a))
    : null;

  const signedBn = (v: number, d = 0) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(d)}`;

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title={tx("Market Risk")}
        record={
          <>{tx("Record ")}<b className="font-normal text-foreground">{tx(monthLabel(latest))}</b>{tx(" · quarterly BRSA §4 · Σ of reporting banks")}</>
        }
        right="every figure computed from source series"
      />

      {/* ── The vitals ─────────────────────────────────────────────────── */}
      <SecHead
        title={tx("The vitals")}
        meta={tx("fx position · repricing gap · sized scenarios")}
        className="mb-2.5 mt-6"
      />
      <Vitals cols={5}>
        <Vital
          label={tx("FX net open / capital")}
          value={nopNow != null ? nopNow.toFixed(1) : "—"}
          unit="%"
          series={nop.slice(-8)}
          decimals={1}
          note={
            nopHeadroom != null ? (
              <>
                <b
                  className={
                    nopHeadroom >= 0 ? "font-semibold text-positive" : "font-semibold text-negative"
                  }
                >
                  {tx(nopHeadroom >= 0
                    ? tx("{0}pp inside", {0: nopHeadroom.toFixed(1)})
                    : tx("{0}pp outside", {0: Math.abs(nopHeadroom).toFixed(1)}))}
                </b>{" "}{tx("the ±20% regulatory limit")}</>
            ) : undefined
          }
        />
        <Vital
          label={tx("≤1y repricing gap / assets")}
          value={gapNow != null ? gapNow.toFixed(1) : "—"}
          unit="%"
          series={gap1y.slice(-8)}
          decimals={1}
          note={
            gapNow != null ? (
              <>
                {tx(gapNow < 0 ? "liabilities reprice first" : "assets reprice first")}
                {gapD4q != null && <> · {tx(signedPp(gapD4q, 1))}{tx(" over 4q")}</>}
              </>
            ) : undefined
          }
        />
        <Vital
          label={tx("≤1y net gap")}
          value={le1yBn != null ? signedBn(le1yBn) : "—"}
          unit="₺bn"
          note={
            deepest != null ? (
              <>{tx("deepest bucket ")}{tx(deepest.x)} ({tx(signedBn(deepest.gap))}{tx("₺bn) · per-bank ladders on")}{" "}
                <Link href="/banks" className="font-semibold text-primary">{tx("/banks")}</Link>
              </>
            ) : undefined
          }
        />
        <Vital
          label={tx("ΔNII if rates +250bp")}
          value={nii250 != null ? signedBn(nii250.niiBn) : "—"}
          unit="₺bn"
          note={
            nii250 != null ? (
              <>
                {nii250.pctRsa != null && (
                  <>
                    {tx(nii250.pctRsa >= 0 ? "+" : "−")}
                    {tx(Math.abs(nii250.pctRsa).toFixed(2))}{tx("% of rate-sensitive assets ·")}{" "}
                  </>
                )}{tx("first-order, one year — not a forecast")}</>
            ) : undefined
          }
        />
        <Vital
          label={tx("Largest FX book")}
          value={bigCcy != null ? signedBn(bigCcy.v) : "—"}
          unit="₺bn"
          note={
            bigCcy != null ? (
              <>{tx("net")}{" "}
                <b
                  className={
                    bigCcy.v >= 0 ? "font-semibold text-positive" : "font-semibold text-negative"
                  }
                >
                  {tx(bigCcy.v >= 0 ? "long" : "short")}
                </b>{" "}
                {tx(bigCcy.k)} · {tx(ccyLast?.x)}
              </>
            ) : undefined
          }
        />
      </Vitals>

      {/* ── In depth — the evidence layer ──────────────────────────────── */}
      <Depth>
        <Takeaway data={await withLlmHeadline("market-risk", read, tx.locale)} />

        <Section
          title={tx("FX exposure")}
          description={tx("The sector's net foreign-currency position. A small net-open-position / capital ratio means on- and off-balance FX is well-matched; the by-currency split shows where the system is net long (+) or short (−).")}
        >
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <TrendChart
              data={nop}
              seriesLabels={SECTOR}
              title={
                tx(seriesFinding(nop.filter((r) => r.bank_type_code === "SECTOR"), { noun: "The FX net open position", decimals: 1 }, tx.locale) ??
                "FX net open position / regulatory capital (%)")
              }
              description={tx("FX net open position / regulatory capital, %, quarterly · Σ of reporting banks")}
              source={tx("Source: BRSA quarterly filings (§4)")}
              yFormat="pct"
              decimals={1}
              zeroLine
            />
            <ChartCard title={tx("FX net position by currency (₺bn) — net long (+) / short (−)")}>
              <BopFlowChart data={byCcy} bars={FX_CURRENCY_BARS} unit=" ₺bn" decimals={0} />
            </ChartCard>
          </div>
        </Section>

        <Section
          title={tx("Interest-rate sensitivity")}
          description={tx("The repricing/maturity gap — rate-sensitive assets minus liabilities by bucket. A large net gap in the near buckets means net interest income is exposed to a rate move. Participation banks that don't disclose the schedule are excluded.")}
        >
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <ChartCard title={tx("Repricing gap by bucket (₺bn){0}", {0: ladder.period ? ` · ${ladder.period}` : ""})}>
              <BopFlowChart data={ladder.data} bars={[{ key: "gap", label: "Net repricing gap" }]} unit=" ₺bn" decimals={0} />
            </ChartCard>
            <TrendChart
              data={gap1y}
              seriesLabels={SECTOR}
              title={tx("Cumulative ≤1y repricing gap / total assets (%)")}
              yFormat="pct"
              decimals={1}
              zeroLine
            />
          </div>
        </Section>

        {nii.scenarios.length > 0 && (
          <Section
            title={tx("What a rate move does to NII")}
            description={tx("First-order one-year ΔNII from a parallel shift, off the {0} sector repricing ladder (≤1y buckets, bucket midpoints). Assumes no repricing beta or behavioral offsets — a sizing device, not a forecast.", {0: nii.period ?? "latest"})}
          >
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              {nii.scenarios.map((s) => (
                <Stat
                  key={s.bps}
                  label={tx("{0}{1} bps", {0: s.bps > 0 ? "+" : "", 1: s.bps})}
                  value={`${s.niiBn >= 0 ? "+" : "−"}₺${Math.abs(s.niiBn).toFixed(0)}bn`}
                  hint={tx(s.pctRsa != null ? tx("{0}{1}% of rate-sensitive assets", {0: s.pctRsa >= 0 ? "+" : "", 1: s.pctRsa.toFixed(2)}) : undefined)}
                  tone={s.niiBn >= 0 ? "positive" : "warning"}
                />
              ))}
            </div>
          </Section>
        )}
      </Depth>

      <Colophon />
    </main>
  );
}
