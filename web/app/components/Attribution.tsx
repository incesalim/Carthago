/**
 * Attribution bars — which book actually moved the headline.
 *
 * A page whose evidence layer is a wall of rate lines cannot say WHICH book did
 * the moving. These bars decompose the headline into per-segment contributions
 * and reconcile to it exactly. The sum is PRINTED, because it is the argument:
 * it is the reader's proof the cut is real rather than a decorative stack.
 *
 * A segment that is a CUT of another (SME ⊂ commercial) is drawn INSIDE its
 * parent — solid mark within a lighter bar — never beside it. Charting a subset
 * as a peer invites the reader to add them, which is exactly what /credit's old
 * "SME vs Commercial" pair did.
 *
 * Shared by /credit (contributions in pp of growth) and /asset-quality (shares of
 * the NPL-stock increase, in %), hence the caller supplies the value formatter.
 */

export interface AttributionRow {
  key: string;
  label: string;
  /** The contribution — pp of growth, or % of an increase. `fmtValue` names it. */
  value: number;
  /** Optional right-hand context (level, own growth …). */
  meta?: React.ReactNode;
}

export default function Attribution({
  rows,
  sum,
  nested,
  fmtValue,
  totalLabel = "Sector",
  reconciliation,
  totalMeta,
  emptyNote = "Contributions await a full 52-week base.",
}: {
  /** Disjoint, exhaustive segments — they must sum to the headline. */
  rows: AttributionRow[];
  sum: number;
  /** A cut of one of the rows, drawn inside it. Never summed. */
  nested?: { of: string; label: string; value: number };
  fmtValue: (v: number) => string;
  totalLabel?: string;
  /** The line that states what the sum proves. */
  reconciliation: React.ReactNode;
  totalMeta?: React.ReactNode;
  emptyNote?: string;
}) {
  if (rows.length === 0) {
    return <p className="py-6 text-[12px] text-faint">{emptyNote}</p>;
  }

  const sorted = [...rows].sort((a, b) => b.value - a.value);
  const max = Math.max(...sorted.map((r) => Math.abs(r.value)), 0.1);
  const GRID =
    "grid grid-cols-[76px_minmax(0,1fr)_56px] gap-3 sm:grid-cols-[96px_minmax(0,1fr)_58px_136px]";

  return (
    <div className="border-t border-foreground">
      {sorted.map((r) => {
        const width = (Math.abs(r.value) / max) * 100;
        const negative = r.value < 0;
        const nest = nested && nested.of === r.key && r.value > 0 ? nested : null;
        // The nested cut is expressed as a share of its PARENT's bar, so it can
        // never render wider than the bar that contains it.
        const nestWidth = nest ? Math.min(100, (nest.value / r.value) * 100) : 0;

        return (
          <div key={r.key} className={`${GRID} items-center border-b border-hair py-2`}>
            <span className="text-[12px] font-semibold text-foreground">{r.label}</span>

            <span className="relative block h-[17px]">
              <span
                className={`relative block h-full ${
                  negative ? "bg-negative" : nest ? "bg-data/35" : "bg-data"
                }`}
                style={{ width: `${width}%` }}
              >
                {nest && (
                  <span
                    className="absolute inset-y-0 left-0 block border-r-2 border-card bg-data"
                    style={{ width: `${nestWidth}%` }}
                  >
                    <span className="absolute left-2 top-1/2 -translate-y-1/2 whitespace-nowrap font-mono text-[9px] font-semibold text-white dark:text-[#0f1319]">
                      {nest.label} {fmtValue(nest.value)}
                    </span>
                  </span>
                )}
              </span>
            </span>

            <span
              className={`text-right font-mono text-[12.5px] font-semibold ${
                negative ? "text-negative" : "text-foreground"
              }`}
            >
              {fmtValue(r.value)}
            </span>

            <span className="hidden text-right font-mono text-[9.5px] text-faint sm:block">
              {r.meta}
            </span>
          </div>
        );
      })}

      {/* The reconciliation. Printed, because it is the argument. */}
      <div className={`${GRID} pt-2.5`}>
        <span className="font-mono text-[10px] uppercase tracking-[0.06em] text-muted-foreground">
          {totalLabel}
        </span>
        <span className="text-[10px] leading-snug text-faint">{reconciliation}</span>
        <span className="text-right font-mono text-[12.5px] font-semibold text-foreground">
          {fmtValue(sum)}
        </span>
        <span className="hidden text-right font-mono text-[9.5px] text-faint sm:block">
          {totalMeta}
        </span>
      </div>
    </div>
  );
}
