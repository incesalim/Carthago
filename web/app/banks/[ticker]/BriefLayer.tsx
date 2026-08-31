import { useText } from "@/i18n/use-text";
import * as React from "react";
import Link from "next/link";
import { SecHead, Flags, Movers, type Flag, type MoverRow } from "@/app/components/desk";
import { cn } from "@/app/lib/cn";
import {
  CAR_TARGET,
  ordinal,
  peerRead,
  type BriefFlag,
  type EngineGate,
  type PeerStat,
  type PeerFieldSpec,
} from "@/app/lib/bank-brief";

/**
 * The per-bank brief — the layer the old page never had.
 *
 * "Where it stands" is the signature: only a per-bank page can place this bank
 * on the field's distribution, which is what turns "19th of 34" into a reading.
 * Everything here is computed in `lib/bank-brief.ts`; this file only draws it.
 * Sections whose inputs don't resolve are omitted, and the engine states WHY.
 */

// ---------------------------------------------------------------------------
// Where it stands — the peer strip
// ---------------------------------------------------------------------------

function Strip({ s, spec }: { s: PeerStat; spec: PeerFieldSpec }) {
  const tx = useText();
  // H must clear the two label rows: the value sits above the rule, the median
  // and the axis ends below it. At H=40 the descenders of "MED 16.9" fell
  // outside the viewBox and were clipped.
  const W = 430, H = 50, x0 = 14, x1 = W - 14, base = 22;
  const clamp = (v: number) => Math.min(Math.max(v, spec.lo), spec.hi);
  const sc = (v: number) => x0 + ((clamp(v) - spec.lo) / (spec.hi - spec.lo)) * (x1 - x0);
  const me = sc(s.value);
  const med = sc(s.median);
  const overflow = s.max > spec.hi;

  return (
    <svg
      width={W}
      height={H}
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label={tx("{0}: {1}, median {2}, {3} of {4}", {0: spec.label, 1: s.value.toFixed(spec.decimals), 2: s.median.toFixed(spec.decimals), 3: ordinal(s.rank, tx.locale), 4: s.n})}
      className="max-w-full"
    >
      <line x1={x0} y1={base} x2={x1} y2={base} stroke="var(--chart-6)" strokeWidth={3} strokeLinecap="round" />
      <line x1={med} y1={base - 7} x2={med} y2={base + 7} stroke="var(--warning)" strokeWidth={1.6} />
      <text x={med} y={base + 17} textAnchor="middle" fill="var(--warning)" className="font-mono" fontSize={8}>{tx("MED ")}{tx(s.median.toFixed(spec.decimals))}
      </text>
      <circle cx={me} cy={base} r={5} fill="var(--data)" stroke="var(--card)" strokeWidth={1.5} />
      <text x={me} y={base - 9} textAnchor="middle" fill="var(--data)" className="font-mono font-semibold" fontSize={9.5}>
        {tx(s.value.toFixed(spec.decimals))}%
      </text>
      <text x={x0} y={base + 17} fill="var(--faint)" className="font-mono" fontSize={8}>
        {tx(spec.lo)}
      </text>
      <text x={x1} y={base + 17} textAnchor="end" fill="var(--faint)" className="font-mono" fontSize={8}>
        {tx(spec.hi)}
        {tx(overflow ? "+" : "")}
      </text>
    </svg>
  );
}

export function WhereItStands({
  stats,
  ctx,
}: {
  stats: Array<{ spec: PeerFieldSpec; stat: PeerStat }>;
  // `filings` gates the "build-out" reading: past BUILD_OUT_QUARTERS, a cost base
  // above income is a franchise problem, not a young bank finding its feet.
  ctx: { buffer?: number | null; realRoe?: number | null; filings?: number | null };
}) {
  const tx = useText();
  if (stats.length === 0) return null;
  return (
    <section>
      <SecHead
        title={tx("Where it stands")}
        meta={tx("the {0} {1} reporting · dot = this bank · tick = median", {0: stats[0].stat.n, 1: stats[0].stat.universe})}
        className="mb-2.5 mt-8"
      />
      <div className="border-t-2 border-foreground">
        {stats.map(({ spec, stat }) => (
          <div
            key={spec.key}
            className="grid items-center gap-4 border-b border-hair py-2.5 lg:grid-cols-[minmax(110px,2fr)_minmax(230px,6fr)_minmax(150px,2.7fr)]"
          >
            <div>
              <div className="text-[12.5px] font-semibold text-foreground">{tx(spec.label)}</div>
              <div className="text-[9.5px] text-faint">{tx(spec.sub)}</div>
            </div>
            <div className="overflow-x-auto">
              <Strip s={stat} spec={spec} />
            </div>
            <p className="text-[11.5px] leading-snug text-muted-foreground">
              {tx(peerRead(spec.key, stat, ctx, tx.locale))}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// The engine — the margin ladder, or the reason it can't be built
// ---------------------------------------------------------------------------

export interface EngineRow {
  label: string;
  note?: string;
  value: number;
  unit: "%" | "pp";
  /** Bar direction: an inflow, an outflow, or a subtotal. */
  kind: "in" | "out" | "total" | "sub";
  /** Denominator for the bar width. */
  scale: number;
}

export function Engine({
  gate,
  rows,
  chart,
}: {
  gate: EngineGate;
  rows: EngineRow[];
  /** The margin-bridge chart the old Performance section already rendered. */
  chart?: React.ReactNode;
}) {
  const tx = useText();
  return (
    <section>
      <SecHead title={tx("The engine")} meta={tx("TTM · what the balance sheet earns")} className="mb-2.5 mt-8" />
      <div className="grid gap-7 lg:grid-cols-[5fr_7fr]">
        <div>
          {gate.ready ? (
            <div className="border-t-2 border-foreground">
              {rows.map((r) => (
                <div
                  key={r.label}
                  className={cn(
                    "grid items-center gap-3.5 py-2 lg:grid-cols-[minmax(130px,3fr)_minmax(110px,4fr)_auto]",
                    r.kind === "total" ? "border-b-2 border-foreground" : "border-b border-hair",
                  )}
                >
                  <div>
                    <div
                      className={cn(
                        "text-[12.5px]",
                        r.kind === "total" ? "font-bold text-foreground" : r.kind === "sub" ? "pl-3 text-muted-foreground" : "text-foreground",
                      )}
                    >
                      {tx(r.label)}
                    </div>
                    {r.note && <div className="text-[9.5px] text-faint">{tx(r.note)}</div>}
                  </div>
                  <div className="relative h-2.5 rounded-[1px] bg-muted">
                    <span
                      className={cn(
                        "absolute inset-y-0 left-0 rounded-[1px]",
                        r.kind === "out" ? "bg-negative" : r.value < 0 ? "bg-negative" : "bg-data",
                      )}
                      style={{ width: `${Math.min((Math.abs(r.value) / r.scale) * 100, 100)}%` }}
                    />
                  </div>
                  <div
                    className={cn(
                      "text-right font-mono font-semibold tabular-nums",
                      r.kind === "total" ? "text-[15px]" : "text-[13px]",
                      r.value < 0 ? "text-negative" : "text-foreground",
                    )}
                  >
                    {tx(r.value >= 0 ? "" : "−")}
                    {tx(Math.abs(r.value).toFixed(r.unit === "pp" ? 1 : 2))}
                    {tx(r.unit)}
                  </div>
                </div>
              ))}
              {gate.fundingNote && (
                <p className="mt-2.5 text-[9.5px] leading-relaxed text-faint">{tx(gate.fundingNote)}</p>
              )}
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-border bg-muted p-4">
              <h4 className="text-[12.5px] font-bold text-foreground">{tx("Not derivable yet — and the page says so")}</h4>
              <p className="mt-1 text-[11.5px] leading-relaxed text-muted-foreground">{tx(gate.reason)}</p>
              <p className="mt-2 font-mono text-[8px] uppercase tracking-[0.05em] text-faint">{tx("rule: the ladder needs a ttm roe — never a blank tile")}</p>
            </div>
          )}
        </div>
        <div>{tx(chart)}</div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// The franchise — what the balance sheet is made of
// ---------------------------------------------------------------------------

export interface FundingSlice {
  label: string;
  value: number;
  className: string;
}

export function Franchise({
  assets,
  funding,
  stats,
  stages,
  chart,
}: {
  assets: number;
  funding: FundingSlice[];
  stats: Array<{ k: string; v: string; note?: string }>;
  stages?: React.ReactNode;
  chart?: React.ReactNode;
}) {
  const tx = useText();
  const deposits = funding[0];
  const depShare = deposits ? (deposits.value / assets) * 100 : null;
  return (
    <section>
      <SecHead title={tx("The franchise")} meta={tx("what the balance sheet is made of")} className="mb-2.5 mt-8" />
      <div className="grid gap-7 lg:grid-cols-2">
        <div>
          {depShare != null && (
            <p className="mb-1 text-[12.5px] text-foreground">
              <b className="font-bold">
                {tx(depShare > 50 ? "Funded by depositors, not markets." : "Deposit-light — still funded by its own capital.")}
              </b>{" "}{tx("Deposits cover ")}{tx(depShare.toFixed(0))}{tx("% of the balance sheet.")}</p>
          )}
          <div className="mt-1 flex h-6 overflow-hidden rounded-[2px]">
            {funding.map((f) => (
              <span
                key={f.label}
                className={f.className}
                style={{ width: `${(f.value / assets) * 100}%` }}
                title={tx(`${f.label} — ${((f.value / assets) * 100).toFixed(1)}%`)}
              />
            ))}
          </div>
          <div className="mt-2 flex flex-wrap gap-x-3.5 gap-y-1 text-[10.5px] text-muted-foreground">
            {funding.map((f) => (
              <span key={f.label} className="inline-flex items-center gap-1.5">
                <i className={cn("inline-block size-2 rounded-[2px]", f.className)} aria-hidden />
                {tx(f.label)}{" "}
                <b className="font-mono font-semibold text-foreground">{tx(((f.value / assets) * 100).toFixed(1))}%</b>
              </span>
            ))}
          </div>
          <table className="mt-4 w-full border-collapse">
            <tbody>
              {stats.map((s) => (
                <tr key={s.k}>
                  <td className="border-b border-hair py-1.5 text-[12px] text-foreground">{tx(s.k)}</td>
                  <td className="border-b border-hair py-1.5 text-right font-mono text-[12px] font-semibold tabular-nums text-foreground">
                    {tx(s.v)}
                  </td>
                  <td className="border-b border-hair py-1.5 pl-3 text-right font-mono text-[10.5px] text-faint">
                    {tx(s.note ?? "")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="space-y-4">
          {tx(stages)}
          {tx(chart)}
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Movers + flags, side by side (the sector tabs' pairing, per bank)
// ---------------------------------------------------------------------------

export function MoversAndFlags({
  from,
  to,
  movers,
  flags,
}: {
  from: string;
  to: string;
  movers: MoverRow[];
  flags: BriefFlag[];
}) {
  const tx = useText();
  if (movers.length === 0 && flags.length === 0) return null;
  const active = flags.filter((f) => f.kind !== "ok").length;
  const asDeskFlags: Flag[] = flags.map((f) => ({
    code: f.id,
    active: true,
    body: (
      <>
        <b className="font-semibold">{tx(f.title)}.</b> {tx(f.detail)}
      </>
    ),
    rule: f.rule,
  }));
  return (
    <div className="mt-8 grid gap-x-10 gap-y-8 lg:grid-cols-[5fr_7fr]">
      <div>
        <SecHead title={tx("Movers")} meta={tx(`${from} → ${to}`)} className="mb-2.5" />
        <Movers from={from} to={to} rows={movers} />
      </div>
      <div>
        <SecHead title={tx("Flags")} meta={tx("rule-based — {0} firing", {0: active})} className="mb-2.5" />
        {/* The Desk Flags component prints the rule under each body; an "ok" flag
            renders as the quiet no-flags line. */}
        {active > 0 ? (
          <Flags flags={asDeskFlags.filter((_, i) => flags[i].kind !== "ok")} />
        ) : (
          <Flags flags={[]} quietNote={flags.find((f) => f.kind === "ok")?.detail ?? "No rule crossed its threshold this quarter."} />
        )}
        {active > 0 &&
          flags
            .filter((f) => f.kind === "ok")
            .map((f) => (
              <div key={f.id} className="flex gap-3 border-b border-hair py-2">
                <span className="min-w-5 pt-0.5 font-mono text-[10px] font-semibold text-positive">—</span>
                <p className="text-[12px] leading-relaxed">
                  <b className="font-semibold">{tx(f.title)}.</b> {tx(f.detail)}
                  <span className="mt-0.5 block font-mono text-[8px] text-faint">{tx(f.rule)}</span>
                </p>
              </div>
            ))}
      </div>
    </div>
  );
}

export { CAR_TARGET };

/** The identity strip — the facts this bank actually has, nothing invented. */
export function Identity({ items }: { items: Array<{ k: string; v: React.ReactNode }> }) {
  const tx = useText();
  return (
    <div className="mt-3 flex gap-5 overflow-x-auto whitespace-nowrap border-y border-border py-2">
      {items.map((it) => (
        <div key={it.k} className="flex items-baseline gap-1.5">
          <span className="font-mono text-[8.5px] uppercase tracking-[0.05em] text-faint">{tx(it.k)}</span>
          <span className="font-mono text-[11.5px] font-semibold tabular-nums text-foreground">{tx(it.v)}</span>
        </div>
      ))}
    </div>
  );
}

/** A route link inside a computed note. */
export const Go = ({ href, children }: { href: string; children: React.ReactNode }) => (
  <Link href={href} className="font-semibold text-primary">
    {children}
  </Link>
);
