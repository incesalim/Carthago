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
import type { Metadata } from "next";
import { PageHeader } from "@/app/components/ui";
import OwnershipNetwork from "@/app/components/OwnershipNetwork";
import { sectorOwnership } from "@/app/lib/kap";
import { buildOwnershipGraph } from "@/app/lib/ownership-graph";
import { bankSummaries } from "@/app/lib/audit";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkish Banks — Ownership & Subsidiaries",
  description: "Ownership structure and subsidiaries of Türkiye's banks from KAP public disclosures — shareholders and group networks.",
  alternates: { canonical: "/ownership" },
};

interface Props {
  searchParams: Promise<{ focus?: string; view?: string }>;
}

export default async function OwnershipPage({ searchParams }: Props) {
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

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8">
      <PageHeader
        eyebrow="KAP"
        title="Ownership network"
        description="Shareholders, subsidiaries and cross-bank stakes from each bank's KAP Genel Bilgi Formu — shared entities link banks; stakes filed years ago persist until the structure changes"
        className="mb-6"
      />
      <OwnershipNetwork
        graph={graph}
        assets={assets}
        initialFocus={sp.focus?.toUpperCase()}
        initialView={sp.view}
      />
    </main>
  );
}
