"use client";

/**
 * BankSectionNav — sticky in-page jump-nav for /banks/[ticker].
 *
 * Renders a row of pill links (styled like the statement-control toggles) that
 * scroll to the page's anchored groups (#overview, #financials, #ownership,
 * #disclosures). An IntersectionObserver highlights the section currently in
 * view. The page passes only the sections that actually render (the ownership
 * group is conditional), so every `#id` always resolves.
 *
 * Links are plain `<a href="#id">` on purpose: a bare hash anchor mutates only
 * the URL fragment and preserves the `?statement/view/kind` query params that
 * the financials toggles set — `next/link` would route and drop them.
 */
import { useEffect, useState } from "react";

export interface NavSection {
  id: string;
  label: string;
}

// -72px clears the sticky bar; -65% narrows the active band so exactly one
// pill lights up at a time.
const OBSERVER_MARGIN = "-72px 0px -65% 0px";

export default function BankSectionNav({ sections }: { sections: NavSection[] }) {
  const [active, setActive] = useState<string>(sections[0]?.id ?? "");

  useEffect(() => {
    const els = sections
      .map((s) => document.getElementById(s.id))
      .filter((el): el is HTMLElement => el !== null);
    if (els.length === 0) return;

    const visible = new Map<string, number>();
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) visible.set(e.target.id, e.boundingClientRect.top);
          else visible.delete(e.target.id);
        }
        if (visible.size > 0) {
          let best: string | null = null;
          let bestTop = Infinity;
          for (const [id, top] of visible) {
            if (top < bestTop) {
              bestTop = top;
              best = id;
            }
          }
          if (best) setActive(best);
        }
      },
      { rootMargin: OBSERVER_MARGIN, threshold: [0, 1] },
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, [sections]);

  if (sections.length <= 1) return null;

  return (
    <nav
      aria-label="Sections"
      // Mobile/tablet: self-stick just below the mobile nav bar (top-14).
      // lg+: not self-sticky — the page wraps this and the PageHeader in one
      // sticky group so they pin stacked (header on top, this nav directly
      // below) instead of both grabbing top-0 and overlapping.
      className="sticky top-14 z-30 -mx-4 mb-6 border-b border-border bg-background/95 px-4 py-2 backdrop-blur supports-[backdrop-filter]:bg-background/80 sm:-mx-6 sm:px-6 lg:static lg:-mx-8 lg:px-8"
    >
      <div className="flex w-fit gap-1 rounded-[9px] border border-border bg-card p-[3px]">
        {sections.map((s) => (
          <a
            key={s.id}
            href={`#${s.id}`}
            aria-current={active === s.id ? "true" : undefined}
            className={`px-3 py-1 text-xs rounded-lg transition ${
              active === s.id
                ? "bg-primary/10 font-semibold text-primary"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {s.label}
          </a>
        ))}
      </div>
    </nav>
  );
}
