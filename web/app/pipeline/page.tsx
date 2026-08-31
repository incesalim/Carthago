/**
 * /pipeline — interactive node graph of the whole data pipeline.
 *
 * External sources → ingestion workflows → Cloudflare D1/R2/KV → dashboard pages,
 * with the two isolated ingestion lanes (bulletin/`bddk-pipeline` vs
 * audit/`bddk-audit`) banded apart. Storage/source nodes carry live D1 freshness
 * + row counts (server-rendered here); workflow nodes get their last GitHub
 * Actions run client-side. See docs/ARCHITECTURE.md for the textual version.
 */
import { localizeMetadata } from "@/i18n/metadata";
import { getText } from "@/i18n/server";
import type { Metadata } from "next";
import { PageHeader } from "@/app/components/ui";
import PipelineFlow from "./PipelineFlow";
import { getPipelineStatus, type PipelineStatusMap } from "@/app/lib/pipeline-status";

export const dynamic = "force-dynamic";

const pageMetadata: Metadata = {
  title: "Data Pipeline",
  description: "Live data-lineage and pipeline status for the Carthago Turkish banking dashboard.",
  alternates: { canonical: "/pipeline" },
};

export async function generateMetadata(): Promise<Metadata> {
  return localizeMetadata(pageMetadata);
}

export default async function PipelinePage() {
  const tx = await getText();
  let status: PipelineStatusMap = {};
  try {
    status = await getPipelineStatus();
  } catch {
    // Graph still renders with neutral (no-data) nodes.
  }

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      <PageHeader
        eyebrow={tx("Data lineage")}
        title={tx("Pipeline")}
        description={tx("How data moves end-to-end: external sources → ingestion workflows → Cloudflare D1/R2/KV → dashboard pages. Storage nodes show live row counts & freshness; workflow nodes show their last GitHub Actions run. Drag to rearrange, scroll to zoom, hover a node to trace its connections.")}
      />
      <PipelineFlow status={status} />
    </main>
  );
}
