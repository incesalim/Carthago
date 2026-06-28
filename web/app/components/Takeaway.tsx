/**
 * Takeaway — the "perspective" callout that leads a tab. Renders a deterministic
 * TabTakeaway (from lib/insights.ts): a one-line headline + bullet insights,
 * each tone-coloured and linking to the tab that proves it. Server component
 * (no interactivity); computed live from D1, so it always matches the charts.
 */
import Link from "next/link";
import type { TabTakeaway } from "@/app/lib/insights";

const TONE: Record<string, string> = {
  positive: "text-emerald-600 dark:text-emerald-400",
  warn: "text-amber-600 dark:text-amber-400",
  neutral: "text-foreground",
};

export default function Takeaway({
  title = "Sector Pulse",
  data,
}: {
  title?: string;
  data: TabTakeaway;
}) {
  if (!data.items.length) return null;
  return (
    <section className="rounded-lg border border-border bg-card p-4 shadow-sm">
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold text-foreground">{title}</h2>
        {data.asOf && (
          <span className="text-[11px] tabular-nums text-muted-foreground">
            {data.asOf} · computed from latest data
          </span>
        )}
      </div>
      <p className="mb-3 text-sm leading-snug text-foreground">{data.headline}</p>
      <ul className="space-y-1.5">
        {data.items.map((it, i) => (
          <li key={i} className="text-xs leading-snug">
            <span className="mr-1 text-muted-foreground">•</span>
            <span className={TONE[it.tone] ?? TONE.neutral}>{it.text}</span>
            {it.href && (
              <Link
                href={it.href}
                className="ml-1 text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                aria-label="open the related tab"
              >
                →
              </Link>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
