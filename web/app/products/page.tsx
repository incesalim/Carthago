/**
 * Products — the product-shelf benchmark: which bank offers which products, with
 * every "has it" backed by the bank's own published page. 32 banks × 100
 * attributes, from a frozen research snapshot in D1 (src/products/build.py).
 *
 * Two-layer Desk page: a computed brief (what the shelf says) above the evidence
 * grid. Product presence is a STRATEGY signal, not a quality score — a thin
 * digital bank is thin by design. Two numbers stay separate on purpose: evidence
 * coverage (about us) and verified shelf breadth (about the bank).
 */
import type { Metadata } from "next";
import { getProductBenchmark, type ProductBenchmark } from "@/app/lib/products";
import { Colophon, DeskHeader, SecHead } from "@/app/components/desk";
import { Section } from "@/app/components/ui";
import ProductMatrix from "./ProductMatrix";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Products — Turkish bank product-shelf benchmark",
  description:
    "Which Turkish bank offers which products, every 'has it' backed by the bank's own published page — deposits, lending, cards, investment, insurance, SME, trade finance and treasury.",
  alternates: { canonical: "/products" },
};

const pct = (x: number) => `${Math.round(x * 100)}%`;

export default async function ProductsPage() {
  const data = await getProductBenchmark();

  if (!data.snapshot || !data.banks.length) {
    return (
      <div className="mx-auto max-w-5xl px-1">
        <DeskHeader title="Products" record="Product-shelf benchmark" />
        <p className="mt-6 text-[14px] text-muted-foreground">
          The product-shelf snapshot has not been loaded into the database yet.
          Once <code className="font-mono">src/products/build.py</code> has run and
          synced, this page shows the full 32-bank matrix.
        </p>
      </div>
    );
  }

  const findings = computeFindings(data);
  const tiers = computeTiers(data);

  return (
    <div className="mx-auto max-w-6xl px-1">
      <DeskHeader
        title="Products"
        record={`${data.nBanks} banks · ${data.nAttrs} attributes · snapshot ${data.snapshot}`}
        right="every ‘has it’ cites the bank’s own page"
      />
      <p className="mt-3 max-w-2xl text-[14px] leading-relaxed text-muted-foreground">
        Everything else here measures what banks <em>earn</em>. This measures what
        they <em>sell</em>: the product shelf that feeds those financials. Shelf
        breadth is a <strong className="font-semibold text-foreground">strategy</strong>{" "}
        signal, not a quality score.
      </p>

      {/* ledger */}
      <div className="mt-5 flex flex-wrap overflow-hidden rounded-md border border-border bg-card">
        {[
          ["banks", String(data.nBanks)],
          ["attributes", String(data.nAttrs)],
          ["cells", data.nCells.toLocaleString("en-US")],
          ["evidence URLs", String(data.nUrls)],
          ["uncited claims", "0"],
        ].map(([k, v]) => (
          <div key={k} className="min-w-[110px] flex-1 border-r border-border px-4 py-3 last:border-r-0">
            <div className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">{k}</div>
            <div className={`mt-0.5 font-mono text-[22px] font-semibold ${k === "uncited claims" ? "text-positive" : "text-foreground"}`}>{v}</div>
          </div>
        ))}
      </div>

      {/* computed brief */}
      <Section className="mt-8">
        <SecHead title="What the shelf says" meta="computed, not raw" />
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {findings.map((f) => (
            <div key={f.stat + f.cap} className={`rounded-md border bg-card p-4 ${f.tone === "pos" ? "border-positive/40" : f.tone === "warn" ? "border-[#b07a18]/45" : "border-border"}`}>
              <div className={`font-mono text-[28px] font-semibold leading-none tracking-tight ${f.tone === "pos" ? "text-positive" : f.tone === "warn" ? "text-[#b07a18] dark:text-[#d6a23e]" : "text-foreground"}`}>
                {f.stat}
                {f.unit && <span className="text-[15px] font-medium text-muted-foreground"> {f.unit}</span>}
              </div>
              <p className="mt-2.5 text-[13px] leading-relaxed text-muted-foreground [&>strong]:font-semibold [&>strong]:text-foreground" dangerouslySetInnerHTML={{ __html: f.cap }} />
            </div>
          ))}
        </div>
      </Section>

      {/* the matrix */}
      <Section className="mt-9">
        <SecHead title="The evidence matrix" meta={`${data.nBanks} banks × ${data.nAttrs} attributes`} />
        <p className="mb-3 mt-1 max-w-2xl text-[13px] text-muted-foreground">
          Pick a block, filter by cluster, find a bank. Click a cell for the value,
          its rationale and the bank’s own evidence link; click a bank for its shelf profile.
        </p>
        <ProductMatrix data={data} />
      </Section>

      {/* penetration tiers */}
      <Section className="mt-9">
        <SecHead title="What’s common, what discriminates" meta={`penetration for ${tiers.enoughCount}/${data.nAttrs} attributes`} />
        <p className="mb-4 mt-1 max-w-2xl text-[13px] text-muted-foreground">
          Penetration is computed only for attributes verified at ≥{data.minVer}/{data.nBanks} banks — for the rest, a
          researcher who didn’t find a product often wrote “unverified”, not “no”, which would inflate a small denominator.
        </p>
        <div className="space-y-4">
          {tiers.groups.map((g) => (
            <div key={g.title}>
              <h3 className="mb-2 flex items-baseline gap-2 text-[13px] font-semibold tracking-tight text-foreground">
                {g.title} <span className="font-mono text-[11px] font-normal text-muted-foreground">{g.band} · {g.rows.length}</span>
              </h3>
              <div className="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
                {g.rows.map((a) => (
                  <div key={a.code} className={`flex items-center gap-2.5 rounded border bg-card px-2.5 py-1.5 ${a.distinctive ? "border-positive/30" : "border-border"}`}>
                    <span className="min-w-[34px] text-right font-mono text-[13px] font-semibold text-foreground">{a.enough ? pct(a.pen ?? 0) : String(a.yes)}</span>
                    <span className="text-[12px] leading-tight text-muted-foreground">
                      {a.label}{a.distinctive && <span className="text-[#b07a18] dark:text-[#d6a23e]"> ◆</span>} <code className="font-mono text-[10px] text-faint">{a.code}</code>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Section>

      {/* methodology */}
      <Section className="mt-9">
        <SecHead title="Method & the honesty budget" meta="what to trust, what not" />
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <Method title="The evidence rule — four values, each says a different thing">
            <ul className="space-y-1 text-[12.5px]">
              <li><b className="text-foreground">Has it</b> — the bank’s own page shows the product (URL required) — about the bank</li>
              <li><b className="text-foreground">No</b> — category page checked, product absent — about the bank</li>
              <li><b className="text-foreground">Partial</b> — via a subsidiary / agency / branch-only / one segment</li>
              <li><b className="text-[#b07a18] dark:text-[#d6a23e]">Unverified</b> — we couldn’t confirm — about us, not a gap in the bank</li>
            </ul>
            <p className="mt-2.5">Across {data.nCells.toLocaleString("en-US")} cells, not a single “has it” is uncited.</p>
          </Method>
          <Method title="A limit: a URL existing ≠ the URL bearing the claim" warn>
            <p>An automated check can ask “is there a URL”, not “does the URL <b>carry</b> this claim”. One bank’s group-insurance claim rested on a fee-schedule page — proof the product is sold, not that the company is owned. Ownership claims are only provable from a subsidiary list or the KAP filing.</p>
          </Method>
          <Method title="Two measurement biases — corrected" warn>
            <p><b>1.</b> The “unverified” rate varies by bank, so ranking on raw “has it” would make an under-researched bank look thin → coverage (about us) and shelf (about the bank) are reported separately.</p>
            <p className="mt-2"><b>2.</b> When a product was simply absent from a page, researchers often wrote “unverified”, not “no” → penetration is computed only for the {tiers.enoughCount}/{data.nAttrs} attributes with a big-enough denominator.</p>
          </Method>
          <Method title="Known gaps">
            <p>Treasury (block I) and subsidiaries (block J) carry the most “unverified”: banks don’t enumerate derivatives or subsidiary detail on the web. The next step is to fill block J from the KAP ownership data already in the pipeline — deterministic and free.</p>
          </Method>
        </div>
        <Colophon>
          Source of truth: <code className="font-mono">data/product_benchmark/</code> (one JSON per bank, every cell URL-backed). Snapshot {data.snapshot}; snapshots accrete, never overwrite.
        </Colophon>
      </Section>
    </div>
  );
}

function Method({ title, warn, children }: { title: string; warn?: boolean; children: React.ReactNode }) {
  return (
    <div className={`rounded-md border bg-card p-4 ${warn ? "border-[#b07a18]/40" : "border-border"}`}>
      <h3 className="mb-2 text-[14px] font-semibold tracking-tight text-foreground">{title}</h3>
      <div className="space-y-2 text-[13px] leading-relaxed text-muted-foreground [&_code]:rounded [&_code]:bg-background [&_code]:px-1">{children}</div>
    </div>
  );
}

// ---- computed brief + tiers ------------------------------------------------

interface Finding { stat: string; unit?: string; cap: string; tone: "pos" | "warn" | "ink" }

function computeFindings(data: ProductBenchmark): Finding[] {
  const attr = (c: string) => data.attrs.find((a) => a.code === c);
  const cellVal = (t: string, c: string) => data.banks.find((b) => b.ticker === t)?.cells[c]?.v;
  const insurers = attr("J03")?.yes ?? 0;
  const sellers = data.banks.filter((b) => {
    const v = b.cells["E07"]?.v;
    return v === "yes" || v === "partial";
  }).length;
  const forex = attr("D08")?.yes ?? 0;
  const crypto = attr("D12")?.yes ?? 0;
  const enough = data.attrs.filter((a) => a.enough).length;
  const entry = data.attrs.filter((a) => a.enough && (a.pen ?? 0) >= 0.9).length;
  const bottom5 = [...data.banks].sort((a, b) => a.shelf - b.shelf).slice(0, 5).map((b) => b.ticker);
  const stateNoInsurer = ["ZIRAAT", "HALKB", "VAKBN"].every((t) => cellVal(t, "J03") === "no");

  return [
    { stat: `${insurers}`, unit: `/${sellers}`, tone: "pos",
      cap: `<strong>Bancassurance is distribution, not manufacture.</strong> Of ${sellers} banks selling insurance, only ${insurers} own the insurer; the rest act as agents.` },
    { stat: stateNoInsurer ? "0" : "—", unit: "/3", tone: "warn",
      cap: `<strong>None of the three state banks</strong> holds a group insurer — Ziraat/Halk Sigorta + Vakıf pension were merged into Türkiye Sigorta / Türkiye Hayat in 2020. State bancassurance is pure distribution income.` },
    { stat: `${entry}`, unit: `/${enough}`, tone: "ink",
      cap: `<strong>The retail shelf has converged.</strong> ${entry} of the ${enough} well-covered attributes sit at 90%+ — table stakes, not differentiators.` },
    { stat: `${forex}`, unit: "bank", tone: "ink",
      cap: `<strong>Leveraged forex</strong> is offered by ${forex} bank (Burgan); crypto by ${crypto}. Investment depth is where the shelf discriminates most.` },
    { stat: "19–49%", tone: "ink",
      cap: `<strong>Digital banks compete on a thin shelf by design.</strong> The bottom five are all digital (${bottom5.join(", ")}); no branch bank drops into that band.` },
    { stat: "3", tone: "warn",
      cap: `<strong>Shelf withdrawals show too:</strong> HSBC pulled mortgage+vehicle from new sales, QNB’s wallet closed in Jan 2026, and FX-protected deposits are winding down.` },
  ];
}

interface TierGroup { title: string; band: string; rows: ProductBenchmark["attrs"] }
function computeTiers(data: ProductBenchmark): { enoughCount: number; groups: TierGroup[] } {
  const scored = data.attrs.filter((a) => a.enough).sort((a, b) => (b.pen ?? 0) - (a.pen ?? 0));
  const thin = data.attrs
    .filter((a) => !a.enough)
    .sort((a, b) => b.yes + b.no + b.partial - (a.yes + a.no + a.partial));
  const band = (lo: number, hi: number) => scored.filter((a) => (a.pen ?? 0) >= lo && (a.pen ?? 0) < hi);
  return {
    enoughCount: scored.length,
    groups: [
      { title: "Table stakes", band: "≥ 90% — no differentiation", rows: band(0.9, 1.01) },
      { title: "Common but not universal", band: "75–90%", rows: band(0.75, 0.9) },
      { title: "Real discriminators", band: "25–75% — where the race is", rows: band(0.25, 0.75) },
      { title: "Rare / niche", band: "< 25%", rows: band(0, 0.25) },
      { title: "Evidence too thin", band: `denominator < ${data.minVer} — penetration not computed; count is a floor`, rows: thin },
    ].filter((g) => g.rows.length),
  };
}
