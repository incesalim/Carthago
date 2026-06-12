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
import { PageHeader } from "@/app/components/ui";
import OwnershipNetwork from "@/app/components/OwnershipNetwork";
import { sectorOwnership } from "@/app/lib/kap";
import { buildOwnershipGraph } from "@/app/lib/ownership-graph";

export const dynamic = "force-dynamic";

interface Props {
  searchParams: Promise<{ focus?: string; view?: string }>;
}

export default async function OwnershipPage({ searchParams }: Props) {
  const sp = await searchParams;
  const rows = await sectorOwnership();
  const graph = buildOwnershipGraph(rows);

  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6 lg:px-8">
      <PageHeader
        eyebrow="KAP"
        title="Ownership network"
        description="Shareholders, subsidiaries and cross-bank stakes from each bank's KAP Genel Bilgi Formu — shared entities link banks; stakes filed years ago persist until the structure changes"
        className="mb-6"
      />
      <OwnershipNetwork
        graph={graph}
        initialFocus={sp.focus?.toUpperCase()}
        initialView={sp.view}
      />
    </main>
  );
}
