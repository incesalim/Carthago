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
import { useText } from "@/i18n/use-text";
import styles from "./attribution.module.css";


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
  const tx = useText();
  if (rows.length === 0) {
    return <p className="py-6 text-[12px] text-faint">{tx(emptyNote)}</p>;
  }

  const sorted = [...rows].sort((a, b) => b.value - a.value);
  const max = Math.max(...sorted.map((r) => Math.abs(r.value)), 0.1);

  return (
    <div data-attribution className={styles.attribution}>
      {sorted.map((r) => {
        const width = (Math.abs(r.value) / max) * 100;
        const negative = r.value < 0;
        const nest = nested && nested.of === r.key && r.value > 0 ? nested : null;
        // The nested cut is expressed as a share of its PARENT's bar, so it can
        // never render wider than the bar that contains it.
        const nestWidth = nest ? Math.min(100, (nest.value / r.value) * 100) : 0;

        return (
          <div key={r.key} className={styles.row}>
            <span className={styles.label}>{tx(r.label)}</span>

            <span className={styles.bar}>
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
                  </span>
                )}
              </span>
            </span>

            <span
              className={`${styles.value} ${
                negative ? "text-negative" : "text-foreground"
              }`}
            >
              {tx(fmtValue(r.value))}
            </span>

            <span className={styles.meta}>
              {nest && <span>{tx(nest.label)} {tx(fmtValue(nest.value))}{" · "}</span>}
              {tx(r.meta)}
            </span>
          </div>
        );
      })}

      {/* The reconciliation. Printed, because it is the argument. */}
      <div className={styles.total}>
        <span className={styles.label}>
          {tx(totalLabel)}
        </span>
        <span className={styles.reconciliation}>{tx(reconciliation)}</span>
        <span className={styles.value}>
          {tx(fmtValue(sum))}
        </span>
        <span className={styles.meta}>
          {tx(totalMeta)}
        </span>
      </div>
    </div>
  );
}
