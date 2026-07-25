"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import TrendChart from "@/app/components/TrendChart";
import { SAMPLE, SAMPLE_LABELS } from "./sample";
import SvgLine from "./SvgLine";

/**
 * The four ways the same chart can arrive. Each panel is the real thing — real
 * Recharts, real network, real hydration — so what you see here is what the site
 * would do.
 *
 * A "slow" toggle throttles the deferred options by a fixed delay, because on a
 * fast connection option 2 and 3 land so quickly that the difference the
 * decision turns on (does a blank area appear? for how long?) is invisible. The
 * delay is a magnifying glass, not a claim about real latency.
 */

const COMMON = {
  data: SAMPLE,
  seriesLabels: SAMPLE_LABELS,
  yFormat: "pct" as const,
  decimals: 1,
  height: 260,
  plain: true,
};

/** Option 2: no server render — the chart only exists after hydration. */
const NoSsrChart = dynamic(() => import("@/app/components/TrendChart"), {
  ssr: false,
  loading: () => <Placeholder note="loading chart module…" />,
});

function Placeholder({ note }: { note: string }) {
  return (
    <div
      style={{ height: 260 }}
      className="flex items-center justify-center rounded-md border border-dashed border-border bg-muted/30"
    >
      <span className="font-mono text-[9.5px] uppercase tracking-[0.06em] text-faint">{note}</span>
    </div>
  );
}

/**
 * True after `ms`, counted from the moment `armed` becomes true.
 *
 * setState happens only inside the timeout callback, never synchronously in the
 * effect body — `react-hooks/set-state-in-effect` forbids the latter, and it is
 * right to: a synchronous reset here would render once with the stale answer and
 * again with the real one. Toggling slow motion remounts these panels via `key`
 * instead, which is what actually resets the timer.
 */
function useSlowdown(ms: number, armed: boolean) {
  const [ready, setReady] = useState(ms === 0);
  useEffect(() => {
    if (!armed || ms === 0) return;
    const t = setTimeout(() => setReady(true), ms);
    return () => clearTimeout(t);
  }, [ms, armed]);
  return ms === 0 ? true : ready;
}

/** Option 3: nothing loads until the panel is actually scrolled into view. */
function InView({ delayMs }: { delayMs: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || seen) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) setSeen(true);
      },
      { rootMargin: "0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [seen]);
  const ready = useSlowdown(delayMs, seen);
  return (
    <div ref={ref}>
      {seen && ready ? (
        <NoSsrChart {...COMMON} />
      ) : (
        <Placeholder note={seen ? "in view — loading…" : "not scrolled to yet"} />
      )}
    </div>
  );
}

function DelayedNoSsr({ delayMs }: { delayMs: number }) {
  const ready = useSlowdown(delayMs, true);
  return ready ? <NoSsrChart {...COMMON} /> : <Placeholder note="waiting for hydration…" />;
}

function Panel({
  n,
  title,
  cost,
  verdict,
  children,
}: {
  n: number;
  title: string;
  cost: string;
  verdict: string;
  children: React.ReactNode;
}) {
  return (
    <section className="border-t border-hair pt-4">
      <div className="mb-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="text-[15px] font-semibold tracking-tight text-foreground">
          <span className="font-mono text-[11px] text-faint">{n}</span> {title}
        </h2>
        <span className="font-mono text-[9.5px] uppercase tracking-[0.05em] text-faint">{cost}</span>
      </div>
      <p className="mb-3 text-[12.5px] leading-snug text-muted-foreground">{verdict}</p>
      {children}
    </section>
  );
}

export default function Strategies() {
  const [slow, setSlow] = useState(true);
  const delay = slow ? 1400 : 0;

  return (
    <div className="space-y-7">
      <div className="flex flex-wrap items-center gap-3 rounded-md border border-border bg-muted/40 px-4 py-3">
        <button
          type="button"
          onClick={() => setSlow((v) => !v)}
          aria-pressed={slow}
          className="min-h-11 rounded-md border border-primary bg-primary px-4 text-[12.5px] font-medium text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          {slow ? "Slow motion: ON" : "Slow motion: OFF"}
        </button>
        <p className="text-[12.5px] leading-snug text-muted-foreground">
          Adds a fixed delay to options 2 and 3 so the blank state is visible. On a fast
          connection they land in a blink — which is the honest answer, but not the one
          you can look at. Reload with it off to see real timing.
        </p>
      </div>

      <Panel
        n={1}
        title="Today — client-rendered after hydration"
        cost="ships 101 KB of Recharts in the initial chunk graph; ~2.6s of main thread on a bank page"
        verdict="CORRECTED 2026-07-25: the server sends an EMPTY container. Recharts needs a measured width, so nothing is drawn until the JavaScript runs — which means this panel and panel 2 look the same to a reader. The only difference is that today the library sits on the critical path."
      >
        <TrendChart {...COMMON} />
      </Panel>

      <Panel
        key={`p2-${slow}`}
        n={2}
        title="No server render (ssr: false)"
        cost="same 101 KB, but off the critical path; smaller HTML"
        verdict="Every chart starts as an empty box and fills in — which, per panel 1, is ALREADY what happens today. So the visible cost of this option is a labelled placeholder instead of a blank area, and the gain is that Recharts leaves the critical path. Cheaper than it looks."
      >
        <DelayedNoSsr delayMs={delay} />
      </Panel>

      <Panel
        key={`p3-${slow}`}
        n={3}
        title="Deferred until scrolled into view"
        cost="101 KB, paid only if the reader scrolls that far"
        verdict="Identical to option 2 for anything above the fold, and free for anything below it that nobody looks at. Scroll down slowly and watch this one arrive as it enters the viewport."
      >
        <InView delayMs={delay} />
      </Panel>

      <Panel
        n={4}
        title="Hand-rolled SVG — no chart library"
        cost="~2 KB, no library, server-rendered"
        verdict="Drawn with the same tokens and hairlines as the rest of the sheet. No hover tooltip, no crosshair, no legend machinery — everything Recharts gives you has to be built. Fine for a small trend, wrong for the interactive Compare board."
      >
        <SvgLine />
      </Panel>
    </div>
  );
}
