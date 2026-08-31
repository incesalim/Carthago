"use client";

import { useText } from "@/i18n/use-text";
import { useCallback, useEffect, useRef, useState } from "react";
import { cn } from "@/app/lib/cn";

/**
 * A horizontally scrollable region that says so.
 *
 * `overflow-x-auto` alone is invisible on a phone: the scorecard on /cross-bank
 * is 820px wide inside a 390px viewport, and two thirds of it sits off-screen
 * with nothing to suggest it exists. Desktop gets a scrollbar; touch gets
 * nothing at all (2026-07-12 evaluation, finding 5).
 *
 * Two things this adds, both of which are information rather than decoration:
 *
 *  1. **An edge fade that only appears where there is more content.** It is
 *     rendered per side and removed on arrival, so "there is a fade" always
 *     means "there is more that way" — a permanent gradient would be a texture
 *     the reader learns to ignore.
 *  2. **Keyboard reach.** A scrollable region must be operable without a mouse
 *     (WCAG 2.1.1); focusable with a name makes the arrow keys work and gives a
 *     screen reader something to announce. `tabIndex={0}` on a scroller is the
 *     standard way, and it is why `label` is required rather than optional.
 *
 * Measured on scroll AND on resize: the same element is scrollable on a phone
 * and not on a desktop, so the answer changes with the viewport, not just with
 * the scroll position.
 */
export function ScrollX({
  label,
  children,
  className,
  innerClassName,
}: {
  /** Accessible name for the region, e.g. "Scorecard, scrolls horizontally". */
  label: string;
  children: React.ReactNode;
  className?: string;
  innerClassName?: string;
}) {
  const tx = useText();
  const ref = useRef<HTMLDivElement>(null);
  const [{ start, end }, setEdges] = useState({ start: true, end: true });

  const measure = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const max = el.scrollWidth - el.clientWidth;
    // 1px of slack: sub-pixel layout means scrollLeft rarely lands exactly on max.
    setEdges({ start: el.scrollLeft <= 1, end: el.scrollLeft >= max - 1 });
  }, []);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    measure();
    el.addEventListener("scroll", measure, { passive: true });
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    // Content can change width without the container resizing (a period toggle
    // adding a column), so watch the scrolled content too.
    if (el.firstElementChild) ro.observe(el.firstElementChild);
    return () => {
      el.removeEventListener("scroll", measure);
      ro.disconnect();
    };
  }, [measure]);

  const fade =
    "pointer-events-none absolute inset-y-0 w-8 transition-opacity duration-150";

  return (
    <div className={cn("relative", className)}>
      <div
        ref={ref}
        role="region"
        aria-label={tx(label)}
        tabIndex={0}
        className={cn(
          "overflow-x-auto focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
          innerClassName,
        )}
      >
        {children}
      </div>
      <div
        aria-hidden
        className={cn(fade, "left-0 bg-gradient-to-r from-card", start && "opacity-0")}
      />
      <div
        aria-hidden
        className={cn(fade, "right-0 bg-gradient-to-l from-card", end && "opacity-0")}
      />
    </div>
  );
}
