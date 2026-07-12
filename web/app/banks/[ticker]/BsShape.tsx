/**
 * The balance sheet's SHAPE — what this bank owns, and what funds it.
 *
 * The layer the statement table cannot be: two composition columns, each line a
 * proportional bar of total assets carrying its share AND its REAL year-over-year
 * (green/red). Under 30-40 % inflation the nominal column of a Turkish balance
 * sheet says almost nothing — a book that grew 35 % shrank. The lead sentence
 * makes that the first thing the page says, and it is computed, not authored.
 *
 * Server component (no interactivity) — Desk idiom: hairlines, no boxes, mono
 * figures, and every proportion drawn rather than described.
 */
import { SecHead } from "@/app/components/desk";
import { cn } from "@/app/lib/cn";
import type { CompRow } from "@/app/lib/bank-financials";

const PF = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1, signDisplay: "exceptZero" });

function RealCell({ real }: { real: number | null }) {
  if (real == null) {
    return <span className="font-mono text-[11px] text-faint">--</span>;
  }
  return (
    <span
      className={cn(
        "font-mono text-[11.5px] font-semibold tabular-nums",
        real > 3 ? "text-positive" : real < -3 ? "text-negative" : "text-warning",
      )}
    >
      {PF.format(real)}%
    </span>
  );
}

function Column({ title, rows }: { title: string; rows: CompRow[] }) {
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between">
        <h3 className="font-mono text-[9px] uppercase tracking-[0.07em] text-faint">{title}</h3>
        <span className="font-mono text-[9px] uppercase tracking-[0.07em] text-faint">
          share · real y/y
        </span>
      </div>
      <div className="border-t-2 border-foreground">
        {rows.map((r) => (
          <div
            key={r.key}
            className="grid items-center gap-x-3 border-b border-hair py-[7px] grid-cols-[minmax(96px,1.5fr)_minmax(48px,1.4fr)_auto_auto]"
          >
            <div
              className={cn(
                "truncate text-[12px]",
                r.sub ? "pl-3 text-muted-foreground" : "text-foreground",
              )}
              title={r.label}
            >
              {r.sub && <span className="mr-1 text-faint">of which</span>}
              {r.label}
            </div>
            <div className="relative h-2.5 rounded-[1px] bg-muted">
              <span
                className={cn(
                  "absolute inset-y-0 left-0 rounded-[1px]",
                  r.sub ? "bg-data/40" : "bg-data",
                )}
                style={{ width: `${Math.min(Math.abs(r.share), 100)}%` }}
              />
            </div>
            <span className="w-12 text-right font-mono text-[12px] font-semibold tabular-nums text-foreground">
              {r.share.toFixed(1)}%
            </span>
            <span className="w-14 text-right">
              <RealCell real={r.real} />
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function BsShape({
  assets,
  funding,
  lead,
  meta,
  footnote,
}: {
  assets: CompRow[];
  funding: CompRow[];
  /** The one computed sentence. Null when the deflator or the prior year is absent. */
  lead: string | null;
  /** Mono-caps method line on the section head. */
  meta: string;
  /** How the CPI was matched — printed under the columns (automation honesty). */
  footnote: string;
}) {
  if (assets.length === 0 && funding.length === 0) return null;
  return (
    <section className="mb-7">
      <SecHead title="The shape" meta={meta} className="mb-2" />
      {lead && (
        <p className="mb-3.5 max-w-[92ch] text-[12.5px] leading-relaxed text-foreground">{lead}</p>
      )}
      <div className="grid gap-x-10 gap-y-6 lg:grid-cols-2">
        <Column title="Assets — what it owns" rows={assets} />
        <Column title="Funding — what pays for it" rows={funding} />
      </div>
      <p className="mt-2 font-mono text-[9px] uppercase leading-relaxed tracking-[0.04em] text-faint">
        {footnote}
      </p>
    </section>
  );
}
