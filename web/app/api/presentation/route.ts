/**
 * GET /api/presentation — the sector "Read" as a print-ready HTML slide deck.
 * Computes the same deterministic per-tab takeaways as /api/reads (via
 * computeReads), lays them out with buildDeckHtml, and returns a standalone
 * HTML document. The browser's print → "Save as PDF" produces the PDF (the
 * Worker runtime can't run headless Chrome — that path is the CLI script,
 * scripts/generate_presentation.py).
 *
 * Query params:
 *   ?print=1        fire the print dialog on load (the admin "Generate PDF" flow)
 *   ?tabs=a,b,c     include/reorder only these section slugs
 *   ?title=…        override the deck title
 *
 * Returns already-public dashboard copy (same as /api/reads), so not admin-gated.
 */
import { computeReads } from "@/app/lib/reads";
import { buildDeckHtml, type DeckSection } from "@/app/lib/presentation-deck";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const url = new URL(req.url);
  const autoPrint = url.searchParams.get("print") === "1";
  const title = url.searchParams.get("title") ?? undefined;
  const tabsParam = url.searchParams.get("tabs");

  const reads = await computeReads();
  let sections: DeckSection[] = reads.map((r) => ({
    tab: r.tab,
    headline: r.takeaway.headline,
    items: r.takeaway.items.map((i) => i.text),
  }));

  if (tabsParam) {
    const byTab = new Map(sections.map((s) => [s.tab, s]));
    sections = tabsParam
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean)
      .map((t) => byTab.get(t))
      .filter((s): s is DeckSection => s !== undefined);
  }

  const generatedAt = new Date().toISOString().slice(0, 10);
  const html = buildDeckHtml(sections, { title, autoPrint, generatedAt });

  return new Response(html, {
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}
