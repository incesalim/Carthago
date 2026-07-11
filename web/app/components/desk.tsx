import * as React from "react";
import Link from "next/link";
import Sparkline from "@/app/components/Sparkline";
import { cn } from "@/app/lib/cn";

/**
 * "The Desk" briefing layer — the shared skeleton every tab's brief is built
 * from: a page header with a record line, a market tape, the vitals band,
 * movers, transmission ("the backdrop → the banks"), rule-based flags,
 * standings, the schedule, and the "In depth" evidence divider.
 *
 * Design contract (web/DESIGN.md): no boxes inside the sheet — hierarchy comes
 * from hairlines (`border-hair`), two ink rules (`border-foreground`), mono
 * figures and type weight. Blue is reserved for route links; green/red state
 * data direction only; amber marks thresholds.
 */

// ---------------------------------------------------------------------------
// Header + tape
// ---------------------------------------------------------------------------

export function DeskHeader({
  title,
  record,
  right,
}: {
  title: React.ReactNode;
  /** Mono record line, e.g. "Record May 2026 · vs Apr". */
  record?: React.ReactNode;
  /** Right-aligned mono note, e.g. the automation-honesty line. */
  right?: React.ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
      <h1 className="text-[24px] font-bold tracking-tight text-foreground">{title}</h1>
      {record && (
        <span className="font-mono text-[9.5px] uppercase tracking-[0.07em] text-muted-foreground">
          {record}
        </span>
      )}
      {right && (
        <span className="ml-auto hidden font-mono text-[9px] uppercase tracking-[0.05em] text-faint sm:inline">
          {right}
        </span>
      )}
    </header>
  );
}

export interface TapeEntry {
  k: string;
  v: string;
  /** Signed % change — colours the chip green/red. */
  chg?: number | null;
}

/** Flat market strip between two hairlines — no card, no scroll animation. */
export function Tape({ items }: { items: TapeEntry[] }) {
  if (!items.length) return null;
  return (
    <div className="mt-3 flex gap-5 overflow-x-auto whitespace-nowrap border-y border-border py-2 font-mono text-[11px]">
      {items.map((it) => (
        <div key={it.k} className="flex items-baseline gap-1.5">
          <span className="text-[9px] tracking-[0.05em] text-faint">{it.k}</span>
          <span className="font-semibold text-foreground">{it.v}</span>
          {it.chg != null && (
            <span className={it.chg >= 0 ? "text-positive" : "text-negative"}>
              {it.chg >= 0 ? "+" : ""}
              {it.chg.toFixed(2)}%
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section head
// ---------------------------------------------------------------------------

export function SecHead({
  title,
  meta,
  href,
  hrefLabel,
  className,
}: {
  title: React.ReactNode;
  /** Mono-caps annotation on the right (method, basis, count). */
  meta?: React.ReactNode;
  href?: string;
  hrefLabel?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex items-baseline gap-2.5", className)}>
      <h2 className="text-[13.5px] font-bold text-foreground">{title}</h2>
      {href && (
        <Link href={href} className="text-[11px] font-semibold text-primary">
          {hrefLabel ?? "→"}
        </Link>
      )}
      {meta && (
        <span className="ml-auto font-mono text-[8.5px] uppercase tracking-[0.07em] text-faint">
          {meta}
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Vitals band — the signature element
// ---------------------------------------------------------------------------

export function Vitals({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "grid grid-cols-2 border-b border-border border-t-2 border-t-foreground sm:grid-cols-3 xl:grid-cols-6",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function Vital({
  label,
  value,
  unit,
  note,
  series,
  format = "pct",
  decimals = 2,
}: {
  label: string;
  value: string;
  unit?: string;
  /** One computed line under the sparkline; may embed a route link. */
  note?: React.ReactNode;
  series?: { period: string; value: number | null }[];
  format?: "pct" | "trn" | "raw";
  decimals?: number;
}) {
  return (
    <div className="border-r border-hair px-4 py-3 last:border-r-0 max-sm:odd:pl-0 sm:first:pl-0">
      <div className="text-[10.5px] text-muted-foreground">{label}</div>
      <div className="mt-0.5 font-mono text-[22px] font-semibold tracking-tight text-foreground">
        {value}
        {unit && <small className="ml-0.5 text-[11px] font-normal text-faint">{unit}</small>}
      </div>
      {series && series.length > 0 && (
        <div className="mt-1.5 h-10">
          <Sparkline
            data={series.filter((r) => r.value != null).map((r) => ({ period: r.period, value: r.value as number }))}
            format={format}
            decimals={decimals}
          />
        </div>
      )}
      {note && <div className="mt-1.5 text-[9.5px] leading-snug text-faint">{note}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Movers
// ---------------------------------------------------------------------------

export interface MoverRow {
  label: string;
  /** Computed sub-note under the metric name. */
  note?: string;
  prev: number | null;
  curr: number | null;
  /** Formats prev/curr (defaults to 2-dp percent). */
  fmt?: (v: number) => string;
  /** Delta decimals (pp). */
  deltaDecimals?: number;
  /** Which direction is good — colours the delta. */
  good?: "up" | "down" | "neutral";
}

export function Movers({ from, to, rows }: { from: string; to: string; rows: MoverRow[] }) {
  const fmtDefault = (v: number) => `${v.toFixed(2)}%`;
  return (
    <table className="w-full border-collapse">
      <thead>
        <tr>
          {["Metric", from, to, "Δ"].map((h, i) => (
            <th
              key={h}
              className={cn(
                "border-b border-foreground pb-1.5 font-mono text-[8.5px] font-normal uppercase tracking-[0.07em] text-faint",
                i === 0 ? "text-left" : "text-right",
              )}
            >
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const f = r.fmt ?? fmtDefault;
          const d = r.curr != null && r.prev != null ? r.curr - r.prev : null;
          const tone =
            d == null || r.good === "neutral" || Math.abs(d) < 1e-9
              ? "text-foreground"
              : (r.good === "down" ? -d : d) >= 0
                ? "text-positive"
                : "text-negative";
          return (
            <tr key={r.label}>
              <td className="border-b border-hair py-1.5 pr-2 text-[12.5px] font-medium text-foreground">
                {r.label}
                {r.note && (
                  <span className="block text-[10px] font-normal text-faint">{r.note}</span>
                )}
              </td>
              <td className="border-b border-hair py-1.5 text-right font-mono text-[11.5px] text-faint">
                {r.prev != null ? f(r.prev) : "—"}
              </td>
              <td className="border-b border-hair py-1.5 pl-2 text-right font-mono text-[12.5px] font-semibold text-foreground">
                {r.curr != null ? f(r.curr) : "—"}
              </td>
              <td className={cn("border-b border-hair py-1.5 pl-2 text-right font-mono text-[11.5px] font-semibold", tone)}>
                {d != null ? `${d >= 0 ? "+" : "−"}${Math.abs(d).toFixed(r.deltaDecimals ?? 2)}pp` : "—"}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

// ---------------------------------------------------------------------------
// Transmission — the backdrop → the banks
// ---------------------------------------------------------------------------

export interface TransmissionItem {
  k: string;
  v: string;
  unit?: string;
  effect: React.ReactNode;
}

export function Transmission({ items }: { items: TransmissionItem[] }) {
  return (
    <div>
      {items.map((it) => (
        <div
          key={it.k}
          className="grid grid-cols-[minmax(100px,3fr)_minmax(180px,8fr)] gap-3.5 border-b border-hair py-2"
        >
          <div>
            <div className="text-[10.5px] text-muted-foreground">{it.k}</div>
            <div className="mt-0.5 font-mono text-[15px] font-semibold text-foreground">
              {it.v}
              {it.unit && <small className="ml-0.5 text-[9.5px] font-normal text-faint">{it.unit}</small>}
            </div>
          </div>
          <p className="text-[12px] leading-relaxed text-foreground">{it.effect}</p>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Flags — rule-based, rules printed
// ---------------------------------------------------------------------------

export interface Flag {
  code: string;
  active: boolean;
  body: React.ReactNode;
  /** The literal rule, printed under the flag (automation honesty). */
  rule: string;
}

export function Flags({ flags, quietNote }: { flags: Flag[]; quietNote?: string }) {
  const active = flags.filter((f) => f.active);
  if (active.length === 0) {
    return (
      <div className="flex gap-3 border-b border-hair py-2">
        <span className="min-w-5 pt-0.5 font-mono text-[10px] font-semibold text-positive">—</span>
        <p className="text-[12px] leading-relaxed">
          <b className="font-semibold">No flags active.</b> {quietNote}
        </p>
      </div>
    );
  }
  return (
    <div>
      {active.map((f, i) => (
        <div key={f.code} className="flex gap-3 border-b border-hair py-2">
          <span className="min-w-5 pt-0.5 font-mono text-[10px] font-semibold text-negative">
            F{i + 1}
          </span>
          <p className="text-[12px] leading-relaxed">
            {f.body}
            <span className="mt-0.5 block font-mono text-[8px] text-faint">{f.rule}</span>
          </p>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Standings + Ahead
// ---------------------------------------------------------------------------

export interface StandingsGroup {
  heading: string;
  rows: { rank: number; name: string; value: string; tone?: "up" | "dn" }[];
}

export function Standings({ groups }: { groups: StandingsGroup[] }) {
  return (
    <div>
      {groups.map((g) => (
        <React.Fragment key={g.heading}>
          <h5 className="mb-1 mt-2.5 font-mono text-[8px] uppercase tracking-[0.1em] text-faint first:mt-0">
            {g.heading}
          </h5>
          <table className="w-full border-collapse">
            <tbody>
              {g.rows.map((r) => (
                <tr key={r.name}>
                  <td className="w-5 border-b border-hair py-1 font-mono text-[9.5px] text-faint">
                    {r.rank}
                  </td>
                  <td className="border-b border-hair py-1 text-[12px] text-foreground">{r.name}</td>
                  <td
                    className={cn(
                      "border-b border-hair py-1 text-right font-mono text-[12px] font-semibold",
                      r.tone === "up" ? "text-positive" : r.tone === "dn" ? "text-negative" : "text-foreground",
                    )}
                  >
                    {r.value}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </React.Fragment>
      ))}
    </div>
  );
}

export interface AheadItem {
  when: string;
  what: React.ReactNode;
  href?: string;
}

export function Ahead({ items }: { items: AheadItem[] }) {
  return (
    <table className="w-full border-collapse">
      <tbody>
        {items.map((it, i) => (
          <tr key={i}>
            <td className="border-b border-hair py-1.5 pr-3 font-mono text-[10.5px] font-semibold whitespace-nowrap text-foreground">
              {it.when}
            </td>
            <td className="border-b border-hair py-1.5 text-[12px] text-foreground">
              {it.href ? (
                <Link href={it.href} className="text-foreground hover:text-primary">
                  {it.what}
                </Link>
              ) : (
                it.what
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ---------------------------------------------------------------------------
// Depth divider + colophon
// ---------------------------------------------------------------------------

/** "In depth" — the evidence layer below the brief. */
export function Depth({
  meta = "carried over from the current page — restyled, not removed",
  action,
  children,
}: {
  meta?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-9 border-t-2 border-foreground pt-2">
      <div className="flex items-baseline gap-2.5">
        <h2 className="text-[14.5px] font-bold text-foreground">In depth</h2>
        {action && <span className="ml-2">{action}</span>}
        <span className="ml-auto font-mono text-[8.5px] uppercase tracking-[0.07em] text-faint">
          {meta}
        </span>
      </div>
      <div className="mt-4 space-y-8">{children}</div>
    </section>
  );
}

/** Page colophon — sources, rules, no-advice line. */
export function Colophon({ children }: { children?: React.ReactNode }) {
  return (
    <footer className="mt-8 border-t border-border pt-2.5 font-mono text-[8.5px] uppercase leading-relaxed tracking-[0.04em] text-faint">
      {children ??
        "Compiled, not written — every figure computed from BDDK · BRSA · TCMB · TÜİK · KAP · BIST source series. Flag rules are printed where they fire. No forecasts. Analytical information, not investment advice."}
    </footer>
  );
}
