"use client";

/**
 * The income statement's SHAPE — two readings of the same filed quarter.
 *
 *   Waterfall — HOW THE PROFIT IS BUILT. Interest income, then every deduction and
 *               addition as a running total, down to net profit. Red for outflows,
 *               navy for subtotals, and each bar sits where the money actually
 *               stands, so the reader sees what survives each stage.
 *
 *   Flow      — WHERE THE MONEY COMES FROM AND GOES. The branching a waterfall
 *               cannot draw: interest income fanned out by SOURCE on the left
 *               (loans / securities / required reserves / money market / banks)
 *               and by DESTINATION on the right (deposits / money market / funds
 *               borrowed / issued securities / lease) plus the net interest income
 *               the bank KEEPS — the hero, in navy.
 *
 * Both are derived in `app/lib/pl-shape.ts` and both reconcile EXACTLY to the
 * filed statement (Σ sources == filed I., Σ destinations + NII == filed I.); a
 * residual gets an explicit "Other" node rather than being dropped, and an
 * identity that doesn't close suppresses the picture instead of drawing numbers
 * that don't add up. Only the tab / period selection is client state — the
 * derivations are pure and run in a memo.
 */
import { useMemo, useState } from "react";
import { SecHead } from "@/app/components/desk";
import { cn } from "@/app/lib/cn";
import type { PlRow } from "@/app/lib/audit";
import {
  buildInterestFlow,
  buildWaterfall,
  layoutInterestFlow,
  type Waterfall,
  type InterestFlow,
} from "@/app/lib/pl-shape";

/** TL thousands → "₺124bn" / "₺4.2bn" / "₺380mn". */
function fmtTl(v: number): string {
  const bn = Math.abs(v) / 1e6;
  const sign = v < 0 ? "−" : "";
  if (bn >= 10) return `${sign}₺${bn.toFixed(0)}bn`;
  if (bn >= 1) return `${sign}₺${bn.toFixed(1)}bn`;
  return `${sign}₺${(Math.abs(v) / 1e3).toFixed(0)}mn`;
}

const periodLabel = (p: string) => p.replace(/^(\d{4})Q([1-4])$/, "$1 Q$2");

// ---------------------------------------------------------------------------
// Waterfall
// ---------------------------------------------------------------------------

function WaterfallView({ w }: { w: Waterfall }) {
  if (!w.renderable) {
    return (
      <div className="border-t-2 border-foreground py-6">
        <p className="text-[12.5px] leading-relaxed text-muted-foreground">{w.notes[0]}</p>
      </div>
    );
  }
  // The common-size column: every step as a share of the interest income it
  // started from — the same denominator the "of every ₺100" lead uses.
  const income = w.steps.find((s) => s.id === "interest_income")?.reported ?? 0;
  const [lo, hi] = w.domain;
  const span = hi - lo || 1;
  const x = (v: number) => ((v - lo) / span) * 100;

  return (
    <div className="border-t-2 border-foreground">
      {w.steps.map((s) => {
        const isTotal = s.kind === "subtotal" || s.kind === "result" || s.kind === "open";
        const prev = s.running - s.delta;
        const from = isTotal ? Math.min(0, s.running) : Math.min(prev, s.running);
        const to = isTotal ? Math.max(0, s.running) : Math.max(prev, s.running);
        const figure = isTotal ? s.reported : s.delta;
        return (
          <div
            key={s.id}
            className={cn(
              "grid items-center gap-x-3 py-[7px] grid-cols-[minmax(130px,1.5fr)_minmax(110px,3fr)_auto_auto]",
              s.kind === "result"
                ? "border-b-2 border-foreground"
                : s.kind === "subtotal" || s.kind === "open"
                  ? "border-b border-foreground"
                  : "border-b border-hair",
            )}
          >
            <div
              className={cn(
                "truncate text-[12px]",
                isTotal ? "font-semibold text-foreground" : "pl-3 text-muted-foreground",
              )}
              title={s.label}
            >
              {s.label}
            </div>
            <div className="relative h-2.5 rounded-[1px] bg-muted">
              <span
                className={cn(
                  "absolute inset-y-0 rounded-[1px]",
                  s.kind === "out"
                    ? "bg-negative"
                    : s.kind === "in"
                      ? "bg-positive"
                      : "bg-data",
                )}
                style={{ left: `${x(from)}%`, width: `${Math.max(x(to) - x(from), 0.4)}%` }}
              />
            </div>
            <span
              className={cn(
                "w-[74px] text-right font-mono text-[12px] tabular-nums",
                isTotal
                  ? "font-semibold text-foreground"
                  : figure < 0
                    ? "text-negative"
                    : "text-positive",
              )}
            >
              {fmtTl(figure)}
            </span>
            <span className="w-12 text-right font-mono text-[10.5px] tabular-nums text-faint">
              {income > 0 ? `${((figure / income) * 100).toFixed(0)}%` : "--"}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Flow — the interest fan
// ---------------------------------------------------------------------------

function FlowView({ f }: { f: InterestFlow }) {
  const layout = useMemo(() => layoutInterestFlow(f), [f]);
  if (!f.renderable) {
    return (
      <div className="border-t-2 border-foreground py-6">
        <p className="text-[12.5px] leading-relaxed text-muted-foreground">{f.notes[0]}</p>
      </div>
    );
  }
  const { W, H } = layout;
  const fillOf = (side: string, hero?: boolean) => {
    if (hero) return "fill-data";
    if (side === "hub") return "fill-[--color-chart-2]";
    if (side === "source") return "fill-[--color-chart-3]";
    return "fill-negative";
  };

  return (
    <div className="border-t-2 border-foreground pt-2">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="h-auto w-full select-none"
        role="img"
        aria-label={`Interest income of ${fmtTl(f.income)} fanned out by source and by destination; net interest income kept: ${fmtTl(f.nii)}`}
      >
        {layout.ribbons.map((r) => (
          <path
            key={r.id}
            d={r.path}
            className={
              r.kind === "keep"
                ? "fill-data"
                : r.kind === "out"
                  ? "fill-negative"
                  : "fill-[--color-chart-3]"
            }
            fillOpacity={r.kind === "keep" ? 0.42 : 0.26}
          />
        ))}
        {layout.nodes.map((n) => (
          <g key={n.id}>
            <rect
              x={n.x}
              y={n.y}
              width={n.w}
              height={n.h}
              rx={2}
              className={fillOf(n.side, n.hero)}
            />
            {n.leader && (
              <polyline
                points={`${n.leader.x1},${n.leader.y1} ${n.leader.x2},${n.leader.y2}`}
                fill="none"
                className="stroke-faint"
                strokeWidth={0.9}
                strokeOpacity={0.55}
              />
            )}
            {n.side === "hub" ? (
              <text
                x={n.labelX}
                y={n.labelY}
                textAnchor="middle"
                className="fill-muted-foreground font-mono"
                fontSize={9}
                style={{ letterSpacing: "0.06em" }}
              >
                {n.label.toUpperCase()} {fmtTl(n.value)}
              </text>
            ) : (
              <>
                <text
                  x={n.labelX}
                  y={n.labelY - 2}
                  textAnchor={n.labelAnchor}
                  className={n.hero ? "fill-data font-semibold" : "fill-foreground"}
                  fontSize={11}
                >
                  {n.label}
                </text>
                <text
                  x={n.labelX}
                  y={n.labelY + 10}
                  textAnchor={n.labelAnchor}
                  className="fill-muted-foreground font-mono tabular-nums"
                  fontSize={9.5}
                >
                  {fmtTl(n.value)} · {n.share.toFixed(1)}%
                </text>
              </>
            )}
          </g>
        ))}
      </svg>
      <div className="mt-1 flex flex-wrap gap-x-5 gap-y-1 font-mono text-[9px] uppercase tracking-[0.05em] text-faint">
        <span className="inline-flex items-center gap-1.5">
          <i className="inline-block size-2 rounded-[2px] bg-[--color-chart-3]" aria-hidden /> earned on
        </span>
        <span className="inline-flex items-center gap-1.5">
          <i className="inline-block size-2 rounded-[2px] bg-negative" aria-hidden /> paid out on
        </span>
        <span className="inline-flex items-center gap-1.5">
          <i className="inline-block size-2 rounded-[2px] bg-data" aria-hidden /> kept — net interest income
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// The section
// ---------------------------------------------------------------------------

type Tab = "waterfall" | "flow";

const TABS: Array<{ id: Tab; title: string; sub: string }> = [
  { id: "waterfall", title: "Waterfall", sub: "how the profit is built" },
  { id: "flow", title: "Flow", sub: "where the money comes from & goes" },
];

export default function IncomeShape({
  rowsByPeriod,
  periods,
}: {
  rowsByPeriod: Record<string, PlRow[]>;
  /** Display order, latest first — matches the table columns. */
  periods: string[];
}) {
  const [tab, setTab] = useState<Tab>("waterfall");
  const [period, setPeriod] = useState(periods[0]);
  const active = periods.includes(period) ? period : periods[0];
  const rows = useMemo(() => rowsByPeriod[active] ?? [], [rowsByPeriod, active]);

  const waterfall = useMemo(() => buildWaterfall(rows), [rows]);
  const flow = useMemo(() => buildInterestFlow(rows), [rows]);

  if (periods.length === 0) return null;

  const lead = tab === "waterfall" ? waterfall.lead : flow.lead;
  const notes = tab === "waterfall" ? waterfall.notes : flow.notes;
  const shown = tab === "waterfall" ? waterfall.renderable : flow.renderable;

  return (
    <section className="mb-7">
      <SecHead
        title="The shape"
        meta={`${periodLabel(active)} as filed · year-to-date cumulative · TL`}
        className="mb-2"
      />

      <div className="mb-3 flex flex-wrap items-end justify-between gap-3 border-b border-hair">
        <div className="flex items-baseline gap-5">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              aria-pressed={tab === t.id}
              className={cn(
                "-mb-px border-b-2 pb-1.5 text-[12.5px] transition-colors",
                tab === t.id
                  ? "border-foreground text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              <b className={tab === t.id ? "font-semibold" : "font-normal"}>{t.title}</b>
              <span className="ml-1.5 text-[11px] text-faint">— {t.sub}</span>
            </button>
          ))}
        </div>
        <div className="mb-1 flex items-center gap-1">
          {periods.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setPeriod(p)}
              aria-pressed={p === active}
              className={cn(
                "rounded-md px-2 py-0.5 font-mono text-[10.5px] tabular-nums transition-colors",
                p === active
                  ? "bg-primary/10 font-semibold text-primary"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {periodLabel(p)}
            </button>
          ))}
        </div>
      </div>

      {shown && lead && (
        <p className="mb-3.5 max-w-[92ch] text-[12.5px] leading-relaxed text-foreground">{lead}</p>
      )}

      {tab === "waterfall" ? <WaterfallView w={waterfall} /> : <FlowView f={flow} />}

      {shown && notes.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-[11px] leading-relaxed text-muted-foreground">
          {notes.map((n, i) => (
            <li key={i}>{n}</li>
          ))}
        </ul>
      )}
      <p className="mt-2 font-mono text-[9px] uppercase leading-relaxed tracking-[0.04em] text-faint">
        {tab === "waterfall"
          ? "every step reconciled against the filed BRSA subtotal (III / VIII / XIII / XVII / XXV) — a bridge that does not close is suppressed, not drawn"
          : "Σ sources = filed I. · Σ destinations + net interest income = filed I. — any residual is drawn as an explicit “Other” node, never dropped"}
      </p>
    </section>
  );
}
