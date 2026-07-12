/**
 * Growth attribution — where the headline actually came from.
 *
 * The page's evidence layer is eleven growth-rate lines; not one of them says
 * WHICH book grew. These bars decompose the sector's print into per-segment
 * contributions (pp = Δsegment ÷ total_base), and they reconcile to it exactly.
 * The sum is printed for that reason: it is the reader's proof the cut is real,
 * not a decorative stack.
 *
 * SME is drawn INSIDE commercial (solid navy within the lighter bar) because it
 * IS commercial — a ~36% cut of that book, not a peer. The current page charts
 * "SME vs Commercial" as two lines, which invites the reader to add them.
 */
import type { Contribution } from "@/app/lib/credit";

const fmtPp = (v: number, d = 1) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(d)}pp`;
const fmtPct = (v: number, d = 1) => `${v < 0 ? "−" : ""}${Math.abs(v).toFixed(d)}%`;
const fmtTrn = (v: number) => `₺${(v / 1_000_000).toFixed(2)}trn`;

export default function Attribution({
  items,
  sumPp,
  nested,
  totalLevel,
}: {
  /** Disjoint, exhaustive segments — they must sum to the sector print. */
  items: Contribution[];
  sumPp: number;
  /** A cut of one of the items, drawn inside it (SME ⊂ commercial). */
  nested?: { of: string; label: string; pp: number; level: number };
  totalLevel: number | null;
}) {
  if (items.length === 0) {
    return <p className="py-6 text-[12px] text-faint">Contributions await a full 52-week base.</p>;
  }

  const rows = [...items].sort((a, b) => b.pp - a.pp);
  const max = Math.max(...rows.map((r) => Math.abs(r.pp)), 0.1);

  return (
    <div className="border-t border-foreground">
      {rows.map((r) => {
        const width = (Math.abs(r.pp) / max) * 100;
        const negative = r.pp < 0;
        const nest = nested && nested.of === r.key && r.pp > 0 ? nested : null;
        // The nested cut is expressed as a share of its parent's bar.
        const nestWidth = nest ? Math.min(100, (nest.pp / r.pp) * 100) : 0;

        return (
          <div
            key={r.key}
            className="grid grid-cols-[76px_minmax(0,1fr)_54px] items-center gap-3 border-b border-hair py-2 sm:grid-cols-[92px_minmax(0,1fr)_56px_128px]"
          >
            <span className="text-[12px] font-semibold text-foreground">{r.label}</span>

            <span className="relative block h-[17px]">
              <span
                className={`relative block h-full ${negative ? "bg-negative" : nest ? "bg-data/35" : "bg-data"}`}
                style={{ width: `${width}%` }}
              >
                {nest && (
                  <span
                    className="absolute inset-y-0 left-0 block border-r-2 border-card bg-data"
                    style={{ width: `${nestWidth}%` }}
                  >
                    <span className="absolute left-2 top-1/2 -translate-y-1/2 whitespace-nowrap font-mono text-[9px] font-semibold text-white dark:text-[#0f1319]">
                      {nest.label} {fmtPp(nest.pp)}
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
              {fmtPp(r.pp)}
            </span>

            <span className="hidden text-right font-mono text-[9.5px] text-faint sm:block">
              {fmtTrn(r.level)} · {fmtPct(r.growth)}
            </span>
          </div>
        );
      })}

      {/* The reconciliation. Printed, because it is the argument. */}
      <div className="grid grid-cols-[76px_minmax(0,1fr)_54px] gap-3 pt-2.5 sm:grid-cols-[92px_minmax(0,1fr)_56px_128px]">
        <span className="font-mono text-[10px] uppercase tracking-[0.06em] text-muted-foreground">
          Sector
        </span>
        <span className="text-[10px] leading-snug text-faint">
          contributions reconcile to the headline — {nested?.label ?? "SME"} is a cut of{" "}
          {items.find((i) => i.key === nested?.of)?.label.toLowerCase() ?? "commercial"}, not an
          addition
        </span>
        <span className="text-right font-mono text-[12.5px] font-semibold text-foreground">
          {fmtPp(sumPp)}
        </span>
        <span className="hidden text-right font-mono text-[9.5px] text-faint sm:block">
          {totalLevel != null ? `${fmtTrn(totalLevel)} book` : ""}
        </span>
      </div>
    </div>
  );
}
