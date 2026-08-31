/**
 * /ownership — sector-wide ownership network from KAP Genel Bilgi Formu data.
 *
 * Who owns the banks (≥5% shareholders) and what the banks own (§7
 * subsidiaries), as one explorable graph: banks on a circle grouped by BDDK
 * type, entities shared across ≥2 banks inside (Treasury, TVF, BKM,
 * Takasbank, KGF, …), bank-to-bank stakes as arrows. Click a bank for its
 * radial fan; ?focus=TICKER deep-links a focused view.
 *
 * Holder names are matched across banks via Turkish-aware normalization plus
 * an exact-match alias map — see web/app/lib/ownership-graph.ts.
 */
import { localizeMetadata } from "@/i18n/metadata";
import { getText } from "@/i18n/server";
import type { Metadata } from "next";
import Link from "next/link";
import { Section } from "@/app/components/ui";
import OwnershipNetwork from "@/app/components/OwnershipNetwork";
import { sectorOwnership } from "@/app/lib/kap";
import { buildOwnershipGraph, trimLabel } from "@/app/lib/ownership-graph";
import { bankSummaries } from "@/app/lib/audit";
import {
  Colophon,
  Depth,
  DeskHeader,
  SecHead,
  Vital,
  Vitals,
} from "@/app/components/desk";
import { monthLabel } from "@/app/lib/desk";

export const dynamic = "force-dynamic";

const pageMetadata: Metadata = {
  title: "Turkish Banks — Ownership & Subsidiaries",
  description: "Ownership structure and subsidiaries of Türkiye's banks from KAP public disclosures — shareholders and group networks.",
  alternates: { canonical: "/ownership" },
};

export async function generateMetadata(): Promise<Metadata> {
  return localizeMetadata(pageMetadata);
}

interface Props {
  searchParams: Promise<{ focus?: string; view?: string }>;
}

export default async function OwnershipPage({ searchParams }: Props) {
  const tx = await getText();
  const sp = await searchParams;
  const rows = await sectorOwnership();
  const graph = buildOwnershipGraph(rows);

  // Latest total assets per bank sizes the network's bank nodes. Fail-soft:
  // the graph is still fully usable with uniform node sizes (e.g. in a local
  // dev DB without the audit tables).
  let assets: Record<string, number | null> = {};
  try {
    const summaries = await bankSummaries();
    assets = Object.fromEntries(summaries.map((s) => [s.bank_ticker, s.total_assets]));
  } catch {
    // keep {}
  }

  // ---- the brief's computed vitals -----------------------------------------
  const filed = graph.banks.filter((b) => b.holders.length + b.subs.length > 0);
  const hollow = graph.banks.length - filed.length;
  const totalSubs = graph.banks.reduce((n, b) => n + b.subs.length, 0);
  const banksWithSubs = graph.banks.filter((b) => b.subs.length > 0).length;
  const foreignOwned = graph.banks.filter((b) => b.typeCode === "10007").length;

  // Most-linked shared entity (sharedHolders is sorted by link count desc).
  const topShared = graph.sharedHolders[0];
  const topSharedBanks = topShared
    ? new Set(topShared.links.map((l) => l.ticker)).size
    : 0;

  // Largest bank-to-bank stake on the graph.
  let maxEdge: { from: string; to: string; pct: number } | null = null;
  for (const e of graph.bankEdges) {
    if (e.ratioPct != null && (!maxEdge || e.ratioPct > maxEdge.pct)) {
      maxEdge = { from: e.from, to: e.to, pct: e.ratioPct };
    }
  }
  const nameOf = (t: string) => graph.banks.find((b) => b.ticker === t)?.name ?? t;

  // Largest single ≥5% holder stake + how many banks sit at 100% with one holder.
  let maxStake: { pct: number; holder: string; bank: string } | null = null;
  let wholly = 0;
  for (const b of graph.banks) {
    let bankMax = 0;
    for (const h of b.holders) {
      if (h.isOther || h.ratioPct == null) continue;
      if (h.ratioPct > bankMax) bankMax = h.ratioPct;
      if (!maxStake || h.ratioPct > maxStake.pct) {
        maxStake = { pct: h.ratioPct, holder: h.label, bank: b.name };
      }
    }
    if (bankMax >= 99.995) wholly++;
  }

  // Latest filing date across every row — free-float lines are refreshed
  // near-daily by KAP, so this tracks the weekly scrape's recency.
  let latestAsOf: string | null = null;
  for (const r of rows) {
    if (r.as_of && (latestAsOf == null || r.as_of > latestAsOf)) latestAsOf = r.as_of;
  }

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title={tx("Ownership network")}
        record={
          <>{tx("Record ")}<b className="font-normal text-foreground">{tx(monthLabel(latestAsOf))}</b>{tx(" · latest KAP filing · re-scraped weekly")}</>
        }
        right="every figure computed from source series"
      />

      <SecHead
        title={tx("The vitals")}
        meta={tx("network · control · cross-holdings")}
        className="mb-2.5 mt-6"
      />
      <Vitals cols={6}>
        <Vital
          label={tx("Banks filing KAP forms")}
          value={String(filed.length)}
          note={
            <>
              {tx(hollow > 0 ? tx("+{0} linked by stakes only — ", {0: hollow}) : "")}{tx("per-bank fans on")}{" "}
              <Link href="/banks" className="font-semibold text-primary">{tx("/banks")}</Link>
            </>
          }
        />
        <Vital
          label={tx("Subsidiaries mapped")}
          value={String(totalSubs)}
          note={tx("§7 grids filed by {0} of {1} banks", {0: banksWithSubs, 1: filed.length})}
        />
        <Vital
          label={tx("Shared entities")}
          value={String(graph.sharedHolders.length)}
          note={
            topShared
              ? tx("{0} alone links {1} banks", {0: trimLabel(topShared.label, 26), 1: topSharedBanks})
              : "entities held by ≥2 banks"
          }
        />
        <Vital
          label={tx("Cross-bank stakes")}
          value={String(graph.bankEdges.length)}
          note={
            maxEdge
              ? tx("largest: {0} → {1}, {2}%", {0: nameOf(maxEdge.from), 1: nameOf(maxEdge.to), 2: maxEdge.pct.toFixed(1)})
              : "bank-to-bank arrows on the graph"
          }
        />
        <Vital
          label={tx("Foreign-owned banks")}
          value={String(foreignOwned)}
          note={<>{tx("BDDK’s Yabancı group — foreign-capital deposit banks")}</>}
        />
        <Vital
          label={tx("Largest single stake")}
          value={maxStake ? maxStake.pct.toFixed(1) : "—"}
          unit="%"
          note={
            wholly > 0
              ? tx("{0} banks are wholly owned by a single holder", {0: wholly})
              : maxStake
                ? `${trimLabel(maxStake.holder, 20)} in ${maxStake.bank}`
                : "no shareholder rows extracted"
          }
        />
      </Vitals>

      <Depth>
        <Section
          index="01"
          title={tx("The network")}
          description={tx("Banks on a circle grouped by BDDK type; entities shared across ≥2 banks sit inside (Treasury, TVF, BKM, Takasbank, KGF, …); bank-to-bank stakes draw as arrows. Click a bank for its radial fan. Stakes filed years ago persist until the structure changes.")}
        >
          <OwnershipNetwork
            graph={graph}
            assets={assets}
            initialFocus={sp.focus?.toUpperCase()}
            initialView={sp.view}
          />
        </Section>
      </Depth>

      <Colophon />
    </main>
  );
}
