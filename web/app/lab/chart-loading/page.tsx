/**
 * /lab/chart-loading — the four chart-loading strategies, side by side.
 *
 * A decision aid, not a product page. `/banks/[ticker]` ships 338 KB of
 * compressed JS across 19 chunks, of which one 101 KB chunk is Recharts, and
 * that is what blocks ~2.6s of main thread (2026-07-12 evaluation). Every fix
 * changes how a chart APPEARS, so the choice is a design call rather than a
 * bundling one — and it is much easier to make by looking than by reading.
 *
 * UNLISTED, like `/products`: `noindex`, absent from the nav, the sitemap and
 * the Colophon. Reachable by URL for whoever is deciding. Delete the folder once
 * the decision is made; nothing links to it.
 */
import type { Metadata } from "next";
import Link from "next/link";
import Strategies from "./Strategies";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Lab — chart loading",
  robots: { index: false, follow: false },
};

export default function ChartLoadingLab() {
  return (
    <div className="mx-auto max-w-4xl px-5 py-8 lg:px-8 lg:py-10">
      <header className="mb-5">
        <p className="font-mono text-[9.5px] uppercase tracking-[0.06em] text-faint">
          Lab · unlisted · decision aid
        </p>
        <h1 className="mt-1 text-[26px] font-semibold tracking-tight text-foreground">
          How the charts would arrive
        </h1>
      </header>

      <div className="mb-7 space-y-3 text-[13.5px] leading-relaxed text-foreground">
        <p>
          A bank page ships <b className="font-semibold">338 KB</b> of compressed
          JavaScript across 19 chunks. One chunk — <b className="font-semibold">101 KB</b>{" "}
          — is Recharts, and that is what costs roughly 2.6 seconds of main-thread work
          on a phone. Caching D1 fixed the server side; this is the rest of it.
        </p>
        <p>
          The four panels below are the real thing: the same sample series, the same
          chart component, the same network. What differs is only <i>when</i> the chart
          exists. Scroll slowly, and watch panel 3 in particular.
        </p>
        <p className="text-[12.5px] text-muted-foreground">
          The numbers are sample data — deterministic, identical in every panel. This
          page is about arrival, not about what the line says.
        </p>
      </div>

      <Strategies />

      <section className="mt-9 border-t-2 border-foreground pt-4">
        <h2 className="mb-2 text-[15px] font-semibold tracking-tight text-foreground">
          What I would pick, if it helps
        </h2>
        <div className="space-y-3 text-[13.5px] leading-relaxed text-foreground">
          <p className="rounded-md border border-warning/40 bg-warning/5 px-3 py-2 text-[12.5px]">
            <b className="font-semibold">Corrected 2026-07-25.</b> This page originally
            said option 1 draws the chart before JavaScript runs, and that option 2 was
            the weakest because it gives that up. Measurement says otherwise: the served
            HTML contains an <i>empty</i> Recharts container and no chart at all. Nothing
            is given up by deferring, because nothing is server-drawn today.
          </p>
          <p>
            <b className="font-semibold">4 for the small fixed marks, 3 for the big
            interactive ones.</b> Most charts here are a trend line a reader glances at —
            those lose almost nothing as hand-rolled SVG, and gain being genuinely
            server-rendered, which no option above delivers today. The Compare board, the
            ownership network and the per-bank drill-downs need hover, crosshair and
            export; those keep Recharts and simply stop loading it until someone scrolls
            to them.
          </p>
          <p>
            <b className="font-semibold">2 is now the cheap floor, not the weak option.</b>{" "}
            It changes what a reader sees only by putting a labelled placeholder where a
            blank area already is, and it takes 101 KB off the critical path. If nothing
            else is done, do that.
          </p>
          <p className="text-[12.5px] text-muted-foreground">
            Whatever you pick, it is a visible change to how the site feels on first
            load — which is exactly why it is your call and not mine.
          </p>
        </div>
      </section>

      <footer className="mt-9 border-t border-border pt-3 font-mono text-[8.5px] uppercase leading-relaxed tracking-[0.04em] text-faint">
        Unlisted · delete <code>app/lab/</code> once decided ·{" "}
        <Link href="/" className="text-primary">Back to the dashboard</Link>
      </footer>
    </div>
  );
}
