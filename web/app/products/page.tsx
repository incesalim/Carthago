import { createText } from "@/i18n/text";
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
import { localizeMetadata } from "@/i18n/metadata";
import { useText } from "@/i18n/use-text";
import { getText } from "@/i18n/server";
import type { Metadata } from "next";
import { getProductBenchmark, type ProductBenchmark } from "@/app/lib/products";
import { Colophon, DeskHeader, SecHead } from "@/app/components/desk";
import { Section } from "@/app/components/ui";
import ProductMatrix from "./ProductMatrix";

export const dynamic = "force-dynamic";

const pageMetadata: Metadata = {
  title: "Products — Turkish bank product-shelf benchmark",
  description:
    "Which Turkish bank offers which products, every 'has it' backed by the bank's own published page — deposits, lending, cards, investment, insurance, SME, trade finance and treasury.",
  // UNLISTED: reachable by direct URL, but kept out of search engines (and the
  // nav + sitemap). noindex here rather than a robots.txt Disallow, which would
  // publicly list the path.
  robots: { index: false, follow: false },
};

export async function generateMetadata(): Promise<Metadata> {
  return localizeMetadata(pageMetadata);
}

const pct = (x: number) => `${Math.round(x * 100)}%`;

export default async function ProductsPage() {
  const tx = await getText();
  const data = await getProductBenchmark();

  if (!data.snapshot || !data.banks.length) {
    return (
      <div className="mx-auto max-w-5xl px-1">
        <DeskHeader title={tx("Products")} record={tx("Product-shelf benchmark")} />
        <p className="mt-6 text-[14px] text-muted-foreground">{tx("The product-shelf snapshot has not been loaded into the database yet. Once ")}<code className="font-mono">src/products/build.py</code>{tx(" has run and synced, this page shows the full 32-bank matrix.")}</p>
      </div>
    );
  }

  const findings = computeFindings(data, tx.locale);
  const tiers = computeTiers(data, tx.locale);

  return (
    <div className="mx-auto max-w-6xl px-1">
      <DeskHeader
        title={tx("Products")}
        record={tx("{0} banks · {1} attributes · snapshot {2}", {0: data.nBanks, 1: data.nAttrs, 2: data.snapshot})}
        right="every ‘has it’ cites the bank’s own page"
      />
      <p className="mt-3 max-w-2xl text-[14px] leading-relaxed text-muted-foreground">{tx("Everything else here measures what banks ")}<em>{tx("earn")}</em>{tx(". This measures what they ")}<em>{tx("sell")}</em>{tx(": the product shelf that feeds those financials. Shelf breadth is a ")}<strong className="font-semibold text-foreground">{tx("strategy")}</strong>{" "}{tx("signal, not a quality score.")}</p>

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
            <div className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">{tx(k)}</div>
            <div className={`mt-0.5 font-mono text-[22px] font-semibold ${k === "uncited claims" ? "text-positive" : "text-foreground"}`}>{tx(v)}</div>
          </div>
        ))}
      </div>

      {/* computed brief */}
      <Section className="mt-8">
        <SecHead title={tx("What the shelf says")} meta={tx("computed, not raw")} />
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {findings.map((f) => (
            <div key={f.stat + f.cap} className={`rounded-md border bg-card p-4 ${f.tone === "pos" ? "border-positive/40" : f.tone === "warn" ? "border-warning/45" : "border-border"}`}>
              <div className={`font-mono text-[28px] font-semibold leading-none tracking-tight ${f.tone === "pos" ? "text-positive" : f.tone === "warn" ? "text-warning" : "text-foreground"}`}>
                {tx(f.stat)}
                {f.unit && <span className="text-[15px] font-medium text-muted-foreground"> {tx(f.unit)}</span>}
              </div>
              <p className="mt-2.5 text-[13px] leading-relaxed text-muted-foreground [&>strong]:font-semibold [&>strong]:text-foreground" dangerouslySetInnerHTML={{ __html: tx(f.cap) }} />
            </div>
          ))}
        </div>
      </Section>

      {/* the matrix */}
      <Section className="mt-9">
        <SecHead title={tx("The evidence matrix")} meta={tx("{0} banks × {1} attributes", {0: data.nBanks, 1: data.nAttrs})} />
        <p className="mb-3 mt-1 max-w-2xl text-[13px] text-muted-foreground">{tx("Pick a block, filter by cluster, find a bank. Click a cell for the value, its rationale and the bank’s own evidence link; click a bank for its shelf profile.")}</p>
        <ProductMatrix data={data} />
      </Section>

      {/* penetration tiers */}
      <Section className="mt-9">
        <SecHead title={tx("What’s common, what discriminates")} meta={tx("penetration for {0}/{1} attributes", {0: tiers.enoughCount, 1: data.nAttrs})} />
        <p className="mb-4 mt-1 max-w-2xl text-[13px] text-muted-foreground">{tx("Penetration is computed only for attributes verified at ≥")}{tx(data.minVer)}/{tx(data.nBanks)}{tx(" banks — for the rest, a researcher who didn’t find a product often wrote “unverified”, not “no”, which would inflate a small denominator.")}</p>
        <div className="space-y-4">
          {tiers.groups.map((g) => (
            <div key={g.title}>
              <h3 className="mb-2 flex items-baseline gap-2 text-[13px] font-semibold tracking-tight text-foreground">
                {tx(g.title)} <span className="font-mono text-[11px] font-normal text-muted-foreground">{tx(g.band)} · {tx(g.rows.length)}</span>
              </h3>
              <div className="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
                {g.rows.map((a) => (
                  <div key={a.code} className={`flex items-center gap-2.5 rounded border bg-card px-2.5 py-1.5 ${a.distinctive ? "border-positive/30" : "border-border"}`}>
                    <span className="min-w-[34px] text-right font-mono text-[13px] font-semibold text-foreground">{tx(a.enough ? pct(a.pen ?? 0) : String(a.yes))}</span>
                    <span className="text-[12px] leading-tight text-muted-foreground">
                      {tx(a.label)}{a.distinctive && <span className="text-warning"> ◆</span>} <code className="font-mono text-[10px] text-faint">{a.code}</code>
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
        <SecHead title={tx("Method & the honesty budget")} meta={tx("what to trust, what not")} />
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <Method title={tx("The evidence rule — four values, each says a different thing")}>
            <ul className="space-y-1 text-[12.5px]">
              <li><b className="text-foreground">{tx("Has it")}</b>{tx(" — the bank’s own page shows the product (URL required) — about the bank")}</li>
              <li><b className="text-foreground">{tx("No")}</b>{tx(" — category page checked, product absent — about the bank")}</li>
              <li><b className="text-foreground">{tx("Partial")}</b>{tx(" — via a subsidiary / agency / branch-only / one segment")}</li>
              <li><b className="text-warning">{tx("Unverified")}</b>{tx(" — we couldn’t confirm — about us, not a gap in the bank")}</li>
            </ul>
            <p className="mt-2.5">{tx("Across ")}{tx(data.nCells.toLocaleString("en-US"))}{tx(" cells, not a single “has it” is uncited.")}</p>
          </Method>
          <Method title={tx("A limit: a URL existing ≠ the URL bearing the claim")} warn>
            <p>{tx("An automated check can ask “is there a URL”, not “does the URL ")}<b>{tx("carry")}</b>{tx(" this claim”. One bank’s group-insurance claim rested on a fee-schedule page — proof the product is sold, not that the company is owned. Ownership claims are only provable from a subsidiary list or the KAP filing.")}</p>
          </Method>
          <Method title={tx("Two measurement biases — corrected")} warn>
            <p><b>1.</b>{tx(" The “unverified” rate varies by bank, so ranking on raw “has it” would make an under-researched bank look thin → coverage (about us) and shelf (about the bank) are reported separately.")}</p>
            <p className="mt-2"><b>2.</b>{tx(" When a product was simply absent from a page, researchers often wrote “unverified”, not “no” → penetration is computed only for the ")}{tx(tiers.enoughCount)}/{tx(data.nAttrs)}{tx(" attributes with a big-enough denominator.")}</p>
          </Method>
          <Method title={tx("Known gaps")}>
            <p>{tx("Treasury (block I) and subsidiaries (block J) carry the most “unverified”: banks don’t enumerate derivatives or subsidiary detail on the web. The next step is to fill block J from the KAP ownership data already in the pipeline — deterministic and free.")}</p>
          </Method>
        </div>
        <Colophon>{tx("Source of truth: ")}<code className="font-mono">data/product_benchmark/</code>{tx(" (one JSON per bank, every cell URL-backed). Snapshot ")}{tx(data.snapshot)}{tx("; snapshots accrete, never overwrite.")}</Colophon>
      </Section>
    </div>
  );
}

function Method({ title, warn, children }: { title: string; warn?: boolean; children: React.ReactNode }) {
  const tx = useText();
  return (
    <div className={`rounded-md border bg-card p-4 ${warn ? "border-warning/40" : "border-border"}`}>
      <h3 className="mb-2 text-[14px] font-semibold tracking-tight text-foreground">{tx(title)}</h3>
      <div className="space-y-2 text-[13px] leading-relaxed text-muted-foreground [&_code]:rounded [&_code]:bg-background [&_code]:px-1">{children}</div>
    </div>
  );
}

// ---- computed brief + tiers ------------------------------------------------

interface Finding { stat: string; unit?: string; cap: string; tone: "pos" | "warn" | "ink" }

function computeFindings(data: ProductBenchmark, locale = "en"): Finding[] {
  const tx = createText(locale);
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
      cap: tx("<strong>Bancassurance is distribution, not manufacture.</strong> Of {0} banks selling insurance, only {1} own the insurer; the rest act as agents.", {0: sellers, 1: insurers}) },
    { stat: stateNoInsurer ? "0" : "—", unit: "/3", tone: "warn",
      cap: tx("<strong>None of the three state banks</strong> holds a group insurer — Ziraat/Halk Sigorta + Vakıf pension were merged into Türkiye Sigorta / Türkiye Hayat in 2020. State bancassurance is pure distribution income.") },
    { stat: `${entry}`, unit: `/${enough}`, tone: "ink",
      cap: tx("<strong>The retail shelf has converged.</strong> {0} of the {1} well-covered attributes sit at 90%+ — table stakes, not differentiators.", {0: entry, 1: enough}) },
    { stat: `${forex}`, unit: "bank", tone: "ink",
      cap: tx("<strong>Leveraged forex</strong> is offered by {0} bank (Burgan); crypto by {1}. Investment depth is where the shelf discriminates most.", {0: forex, 1: crypto}) },
    { stat: "19–49%", tone: "ink",
      cap: tx("<strong>Digital banks compete on a thin shelf by design.</strong> The bottom five are all digital ({0}); no branch bank drops into that band.", {0: bottom5.join(", ")}) },
    { stat: "3", tone: "warn",
      cap: tx("<strong>Shelf withdrawals show too:</strong> HSBC pulled mortgage+vehicle from new sales, QNB’s wallet closed in Jan 2026, and FX-protected deposits are winding down.") },
  ];
}

interface TierGroup { title: string; band: string; rows: ProductBenchmark["attrs"] }
function computeTiers(data: ProductBenchmark, locale = "en"): { enoughCount: number; groups: TierGroup[] } {
  const tx = createText(locale);
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
      { title: "Evidence too thin", band: tx("denominator < {0} — penetration not computed; count is a floor", {0: data.minVer}), rows: thin },
    ].filter((g) => g.rows.length),
  };
}
