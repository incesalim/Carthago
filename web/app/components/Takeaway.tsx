/**
 * Takeaway — "The Read": the editorial perspective callout that leads a tab.
 * Renders a deterministic TabTakeaway (from lib/insights.ts) in the editorial
 * frame: a terracotta left rail, a mono kicker, a serif lead paragraph, and a
 * joined-cell grid of tone-coloured drivers that link to the tab proving each.
 * Server component — computed live from D1, so it always matches the charts.
 */
import Link from "next/link";
import type { TabTakeaway } from "@/app/lib/insights";

const TONE_TEXT: Record<string, string> = {
  positive: "text-positive",
  warn: "text-warning",
  neutral: "text-foreground",
};
const TONE_GLYPH: Record<string, string> = {
  positive: "▲",
  warn: "◆",
  neutral: "●",
};
// Literal class strings (Tailwind must see them verbatim) for spanning the last
// cell to fill its row. Indexed by the number of columns to span.
const SM_SPAN = ["", "sm:col-span-1", "sm:col-span-2"];
const LG_SPAN = ["", "lg:col-span-1", "lg:col-span-2", "lg:col-span-3"];

export default function Takeaway({
  title = "The Read",
  data,
}: {
  title?: string;
  data: TabTakeaway;
}) {
  if (!data.items.length) return null;
  // Fill the last row so no empty grid slot shows the grey gap background: span
  // the final driver across whatever columns are left over at each breakpoint.
  const n = data.items.length;
  const lastSpan = `${SM_SPAN[2 - ((n - 1) % 2)]} ${LG_SPAN[3 - ((n - 1) % 3)]}`;
  return (
    <section className="flex overflow-hidden rounded-[10px] border border-border bg-card">
      <div className="w-1 shrink-0 bg-primary" aria-hidden />
      <div className="min-w-0 flex-1 p-6">
        <div className="mb-4 flex items-center justify-between gap-3">
          <span className="inline-flex items-center gap-2.5">
            <span className="font-mono text-[10.5px] font-medium uppercase tracking-[0.18em] text-primary">
              {title}
            </span>
            <span className="size-1 rounded-full bg-border" aria-hidden />
            <span className="font-mono text-[10px] tracking-[0.04em] text-faint">
              Carthago analysis
            </span>
          </span>
          {data.asOf && (
            <span className="font-mono text-[11px] text-faint">{data.asOf} · computed</span>
          )}
        </div>
        <p className="mb-5 max-w-3xl font-serif text-[21px] font-medium leading-[1.42] tracking-tight text-foreground">
          {data.headline}
        </p>
        <div className="grid grid-cols-1 gap-px overflow-hidden rounded-[9px] border border-border bg-border sm:grid-cols-2 lg:grid-cols-3">
          {data.items.map((it, i) => (
            <div
              key={i}
              className={`bg-card p-4 text-[12.5px] leading-[1.5] text-foreground ${
                i === n - 1 ? lastSpan : ""
              }`}
            >
              <span
                className={`mr-2 text-[10px] leading-none ${TONE_TEXT[it.tone] ?? TONE_TEXT.neutral}`}
                aria-hidden
              >
                {TONE_GLYPH[it.tone] ?? TONE_GLYPH.neutral}
              </span>
              {it.text}
              {it.href && (
                <Link href={it.href} className="whitespace-nowrap font-semibold text-primary">
                  {" "}
                  →
                </Link>
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
