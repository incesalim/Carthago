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
  action,
  className,
}: {
  title: React.ReactNode;
  /** Mono-caps annotation on the right (method, basis, count). */
  meta?: React.ReactNode;
  href?: string;
  hrefLabel?: React.ReactNode;
  /** A control that belongs to this section (bank-type switch, range pills). */
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-baseline gap-x-3 gap-y-1", className)}>
      <h2 className="text-[13.5px] font-bold text-foreground">{title}</h2>
      {href && (
        <Link href={href} className="text-[11px] font-semibold text-primary">
          {hrefLabel ?? "→"}
        </Link>
      )}
      {action}
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

const VITALS_COLS: Record<number, string> = {
  3: "sm:grid-cols-3 xl:grid-cols-3",
  4: "sm:grid-cols-2 xl:grid-cols-4",
  5: "sm:grid-cols-3 xl:grid-cols-5",
  6: "sm:grid-cols-3 xl:grid-cols-6",
};

export function Vitals({
  children,
  cols = 6,
  /** Top rule: the ink two-pixel rule opens the brief's band; the evidence
   *  layer's band repeats the same grid one step quieter. */
  rule = "ink",
  className,
}: {
  children: React.ReactNode;
  /** Cell count at xl (default 6) — pass the number of <Vital> children. */
  cols?: 3 | 4 | 5 | 6;
  rule?: "ink" | "hair";
  className?: string;
}) {
  return (
    <div
      className={cn(
        "grid grid-cols-2 border-b border-border",
        rule === "ink" ? "border-t-2 border-t-foreground" : "border-t border-t-hair",
        VITALS_COLS[cols] ?? VITALS_COLS[6],
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
  peer,
  series,
  format = "pct",
  decimals = 2,
}: {
  label: string;
  value: string;
  unit?: string;
  /** One computed line under the sparkline; may embed a route link. */
  note?: React.ReactNode;
  /** Optional peer bar (see <PeerBar/>) — where this cell sits vs the sector. */
  peer?: React.ReactNode;
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
      {peer}
      {note && <div className="mt-1.5 text-[9.5px] leading-snug text-faint">{note}</div>}
    </div>
  );
}

/**
 * Where a group's value sits in the league of bank-type groups, with the sector
 * marked. Navy fill = this group, grey tick = the sector — no new colour, and
 * the scale is the observed spread across groups, not an invented axis.
 */
export function PeerBar({
  value,
  sector,
  lo,
  hi,
  decimals = 1,
}: {
  value: number;
  sector: number;
  lo: number;
  hi: number;
  decimals?: number;
}) {
  const span = hi - lo || 1;
  const pos = (v: number) => Math.max(0, Math.min(100, ((v - lo) / span) * 100));
  return (
    <div className="mt-1.5 flex items-center gap-1.5 font-mono text-[9px] text-faint">
      <span className="relative h-[3px] flex-1 bg-muted">
        <span
          className="absolute inset-y-0 left-0 bg-data"
          style={{ width: `${pos(value).toFixed(1)}%` }}
        />
        <span
          className="absolute -top-[2px] -bottom-[2px] w-[1.5px] bg-context"
          style={{ left: `${pos(sector).toFixed(1)}%` }}
        />
      </span>
      <span className="whitespace-nowrap">sector {sector.toFixed(decimals)}</span>
    </div>
  );
}

/**
 * Level figures above a band — the sizes the ratios are ratios *of* (assets and
 * the three growth rates). One hairline row, no cells.
 */
export function Levels({
  items,
}: {
  items: { k: string; v: string; unit?: string }[];
}) {
  return (
    <div className="grid grid-cols-2 border-b border-hair sm:grid-cols-4">
      {items.map((it) => (
        <div
          key={it.k}
          className="border-r border-hair px-4 py-2.5 last:border-r-0 max-sm:odd:pl-0 sm:first:pl-0"
        >
          <div className="font-mono text-[8.5px] uppercase tracking-[0.07em] text-faint">
            {it.k}
          </div>
          <div className="mt-0.5 font-mono text-[15px] font-semibold text-foreground">
            {it.v}
            {it.unit && <small className="ml-0.5 text-[9.5px] font-normal text-faint">{it.unit}</small>}
          </div>
        </div>
      ))}
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
// Chart row — a chart constrained to 2/3 width with a computed reading rail
// ---------------------------------------------------------------------------

interface SeriesRow {
  period: string;
  bank_type_code: string;
  value: number | null;
}

/**
 * Lay a lone chart out at two-thirds width with a computed side column —
 * full-bleed width is reserved for hero charts (DESIGN.md). The rail is
 * derived from the SAME rows the chart renders: one line per series (latest +
 * change over `deltaPeriods`), or, for a single-series chart, its latest /
 * change / window high / low.
 */
export function ChartRow({
  data,
  labels = {},
  fmt,
  deltaPeriods = 12,
  deltaLabel = "12m",
  children,
}: {
  data: SeriesRow[];
  labels?: Record<string, string>;
  /** Value formatter (defaults to 2-dp percent). */
  fmt?: (v: number) => string;
  /** How many trailing periods the Δ column spans (12 monthly ≈ 52 weekly ≈ 1y). */
  deltaPeriods?: number;
  deltaLabel?: string;
  children: React.ReactNode;
}) {
  const f = fmt ?? ((v: number) => `${v.toFixed(2)}%`);
  const byKey = new Map<string, { period: string; value: number }[]>();
  for (const r of data) {
    if (r.value == null) continue;
    const arr = byKey.get(r.bank_type_code) ?? [];
    arr.push({ period: r.period, value: r.value });
    byKey.set(r.bank_type_code, arr);
  }
  for (const arr of byKey.values()) arr.sort((a, b) => (a.period < b.period ? -1 : 1));

  const keys = [...byKey.keys()];
  const latestPeriod = [...byKey.values()]
    .map((arr) => arr.at(-1)?.period ?? "")
    .sort()
    .at(-1);

  const rows: { name: string; value: string; delta: string }[] = [];
  if (keys.length > 1) {
    for (const k of keys) {
      const arr = byKey.get(k)!;
      const cur = arr.at(-1)!.value;
      const ago = arr.at(-1 - deltaPeriods)?.value ?? null;
      rows.push({
        name: labels[k] ?? k,
        value: f(cur),
        delta: ago != null ? `${cur - ago >= 0 ? "+" : "−"}${f(Math.abs(cur - ago))}` : "—",
      });
    }
    rows.sort((a, b) => parseFloat(b.value.replace(/[^\d.-]/g, "")) - parseFloat(a.value.replace(/[^\d.-]/g, "")));
  } else if (keys.length === 1) {
    const arr = byKey.get(keys[0])!;
    const cur = arr.at(-1)!.value;
    const ago = arr.at(-1 - deltaPeriods)?.value ?? null;
    let hi = arr[0], lo = arr[0];
    for (const p of arr) {
      if (p.value > hi.value) hi = p;
      if (p.value < lo.value) lo = p;
    }
    rows.push({ name: "Latest", value: f(cur), delta: "" });
    if (ago != null)
      rows.push({
        name: `Δ ${deltaLabel}`,
        value: `${cur - ago >= 0 ? "+" : "−"}${f(Math.abs(cur - ago)).replace(/^[+−-]/, "")}`,
        delta: "",
      });
    rows.push({ name: "High", value: f(hi.value), delta: hi.period.slice(0, 7) });
    rows.push({ name: "Low", value: f(lo.value), delta: lo.period.slice(0, 7) });
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <div className="lg:col-span-2">{children}</div>
      <div className="lg:pt-1">
        <h5 className="mb-1 font-mono text-[8px] uppercase tracking-[0.1em] text-faint">
          {keys.length > 1 ? `Latest · ${latestPeriod ?? ""} · Δ ${deltaLabel}` : `The read · ${latestPeriod ?? ""}`}
        </h5>
        <table className="w-full border-collapse">
          <tbody>
            {rows.map((r) => (
              <tr key={r.name}>
                <td className="border-b border-hair py-1.5 text-[12px] text-foreground">{r.name}</td>
                <td className="border-b border-hair py-1.5 text-right font-mono text-[12px] font-semibold text-foreground">
                  {r.value}
                </td>
                <td className="w-16 border-b border-hair py-1.5 text-right font-mono text-[10.5px] text-faint">
                  {r.delta}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/**
 * A chart's read, on one mono line under the mark: the hero series' latest and
 * its change over `deltaPeriods`, plus the leading and trailing group. Computed
 * from the SAME rows the chart renders, so a reader gets the finding without
 * hovering — and a screenshot still carries it.
 */
export function ChartFoot({
  data,
  labels = {},
  heroCode = "10001",
  decimals = 1,
  deltaPeriods = 12,
  deltaLabel = "12m",
}: {
  data: SeriesRow[];
  labels?: Record<string, string>;
  heroCode?: string;
  decimals?: number;
  deltaPeriods?: number;
  deltaLabel?: string;
}) {
  const byKey = new Map<string, { period: string; value: number }[]>();
  for (const r of data) {
    if (r.value == null) continue;
    const arr = byKey.get(r.bank_type_code) ?? [];
    arr.push({ period: r.period, value: r.value });
    byKey.set(r.bank_type_code, arr);
  }
  for (const arr of byKey.values()) arr.sort((a, b) => (a.period < b.period ? -1 : 1));
  if (!byKey.size) return null;

  const f = (v: number) => v.toFixed(decimals);
  const hero = byKey.get(heroCode);
  const heroNow = hero?.at(-1)?.value ?? null;
  const heroAgo = hero?.at(-1 - deltaPeriods)?.value ?? null;
  const delta = heroNow != null && heroAgo != null ? heroNow - heroAgo : null;

  const peers = [...byKey.entries()]
    .filter(([code, arr]) => code !== heroCode && arr.length > 0)
    .map(([code, arr]) => ({ code, value: arr.at(-1)!.value }))
    .sort((a, b) => b.value - a.value);
  const top = peers[0];
  const bottom = peers.at(-1);

  const items: { k: string; v: string }[] = [];
  if (heroNow != null) items.push({ k: labels[heroCode] ?? "Sector", v: f(heroNow) });
  if (delta != null)
    items.push({ k: `Δ ${deltaLabel}`, v: `${delta >= 0 ? "+" : "−"}${f(Math.abs(delta))}` });
  if (top) items.push({ k: "High", v: `${labels[top.code] ?? top.code} ${f(top.value)}` });
  if (bottom && bottom !== top)
    items.push({ k: "Low", v: `${labels[bottom.code] ?? bottom.code} ${f(bottom.value)}` });

  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[9px] text-faint">
      {items.map((it) => (
        <span key={it.k} className="flex items-baseline gap-1.5">
          <span className="uppercase tracking-[0.07em]">{it.k}</span>
          <b className="font-semibold text-foreground">{it.v}</b>
        </span>
      ))}
    </div>
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
