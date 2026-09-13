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
    return <p className="py-6 text-[14px] text-muted-foreground">{tx(emptyNote)}</p>;
  }

  const sorted = [...rows].sort((a, b) => b.value - a.value);
  const low = Math.min(0, ...sorted.map((r) => r.value));
  const high = Math.max(0, ...sorted.map((r) => r.value));
  const span = high - low || 1;
  const zero = -low / span * 100;

  return (
    <div data-attribution className={styles.attribution}>
      {sorted.map((r) => {
        const width = Math.abs(r.value) / span * 100;
        const negative = r.value < 0;
        const nest = nested && nested.of === r.key ? nested : null;
        // A subset can contribute more than its parent if the remaining book
        // contracts. Only a contribution genuinely inside the parent is nested
        // visually; the exact subgroup figure always remains printed below it.
        const nestFits = nest != null && r.value !== 0 && Math.sign(nest.value) === Math.sign(r.value) && Math.abs(nest.value) <= Math.abs(r.value);
        const nestWidth = nestFits && nest ? Math.abs(nest.value / r.value) * 100 : 0;

        return (
          <div key={r.key} className={styles.row}>
            <span className={styles.label}>{tx(r.label)}</span>

            <span className={styles.bar} aria-hidden="true">
              <i className={styles.zero} style={{ left: `${zero}%` }} />
              <span
                className={styles.mark}
                data-negative={negative || undefined}
                data-nested={nestFits || undefined}
                style={{ left: `${negative ? zero - width : zero}%`, width: `${width}%` }}
              >
                {nestFits && (
                  <span
                    className={styles.nestedMark}
                    style={{ width: `${nestWidth}%`, ...(negative ? { right: 0 } : { left: 0 }) }}
                  />
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
              {nest && <span className={styles.nestedNote}><i />{tx(nest.label)} <strong>{tx(fmtValue(nest.value))}</strong></span>}
              {r.meta != null && <span>{tx(r.meta)}</span>}
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
