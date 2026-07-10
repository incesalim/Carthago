/**
 * CapitalByBank — the per-bank capital-adequacy ranking on /capital.
 *
 * Editorial league table: each bank's total CAR is drawn as a horizontal bar
 * (coloured by ownership group, the same hue the sector charts use for that
 * group), followed by its Tier-1 and CET1 ratios and the buffer over the 12%
 * regulatory minimum. Ranked by CAR, best-capitalised first.
 *
 * Server component — pure presentation off perBankCapital(). Bar fill is scaled
 * against a fixed 25% ceiling (CAR_DOMAIN_MAX) rather than the max in the data,
 * so a handful of tiny specialist banks that run very high CAR don't compress
 * every deposit bank into a stub; their exact figure still shows in the label.
 */
import Link from "next/link";
import { BANK_NAMES, BANK_TYPE_BY_TICKER } from "@/app/lib/bank_names";
import type { BankCapitalRow } from "@/app/lib/audit-ratios";

const CAR_MIN = 12; // regulatory minimum CAR (%)
const CAR_DOMAIN_MAX = 25; // bar-track ceiling; CAR ≥ this fills the track

/** Ownership group → its fixed chart hue (theme-aware CSS var). Mirrors the
 *  BANK_TYPE_COLOR_INDEX slots in chart-theme.ts so a group keeps one colour. */
const TYPE_COLOR: Record<string, string> = {
  "10006": "var(--chart-2)", // State
  "10005": "var(--chart-3)", // Private · Domestic
  "10007": "var(--chart-4)", // Private · Foreign
  "10003": "var(--chart-5)", // Participation
  "10004": "var(--chart-6)", // Dev & Inv
};

const pctStr = (v: number | null, d = 1) => (v == null ? "—" : `${v.toFixed(d)}%`);

function quarterLabel(period: string | null): string {
  if (!period) return "";
  const m = /^(\d{4})Q([1-4])$/.exec(period);
  return m ? `Q${m[2]} ${m[1]}` : period;
}

/** Buffer colour — same thresholds as the page's "Buffer over 12%" Stat tile. */
function bufferTone(pp: number): string {
  if (pp < 0) return "text-negative";
  if (pp < 2) return "text-warning";
  if (pp >= 4) return "text-positive";
  return "text-foreground";
}

export default function CapitalByBank({
  period,
  rows,
}: {
  period: string | null;
  rows: BankCapitalRow[];
}) {
  if (rows.length === 0) return null;

  return (
    <section className="space-y-3">
      {/* Header — serif title + inline descriptor, "All banks" on the right. */}
      <div className="flex items-baseline justify-between gap-3">
        <div className="flex items-baseline gap-2.5">
          <h2 className="font-serif text-xl font-semibold tracking-tight text-foreground">
            By bank
          </h2>
          <span className="text-xs text-muted-foreground">
            ranked by capital adequacy
          </span>
        </div>
        <Link
          href="/banks"
          className="shrink-0 text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
        >
          All banks →
        </Link>
      </div>

      <div className="overflow-x-auto rounded-[10px] border border-border bg-card">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-border text-[11px] uppercase tracking-wide text-muted-foreground">
              <th className="py-2.5 pl-4 pr-3 text-left font-medium">Bank</th>
              <th className="py-2.5 pr-3 text-left font-medium">CAR</th>
              <th className="py-2.5 pr-3 text-right font-medium">Tier 1</th>
              <th className="py-2.5 pr-3 text-right font-medium">CET1</th>
              <th className="py-2.5 pr-4 text-right font-medium">Buffer</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((b) => {
              const code = BANK_TYPE_BY_TICKER[b.bank_ticker];
              const color = TYPE_COLOR[code] ?? "var(--chart-6)";
              const name = BANK_NAMES[b.bank_ticker] ?? b.bank_ticker;
              const fill =
                b.car == null ? 0 : Math.min(b.car / CAR_DOMAIN_MAX, 1) * 100;
              const buffer = b.car == null ? null : b.car - CAR_MIN;

              return (
                <tr
                  key={b.bank_ticker}
                  className="group border-b border-border/70 last:border-0 hover:bg-muted/40"
                >
                  <td className="py-2.5 pl-4 pr-3">
                    <Link
                      href={`/banks/${b.bank_ticker}`}
                      className="flex items-center gap-2.5"
                    >
                      <span
                        className="size-2.5 shrink-0 rounded-[3px]"
                        style={{ background: color }}
                        aria-hidden
                      />
                      <span className="font-medium text-foreground group-hover:text-primary">
                        {name}
                      </span>
                      <span className="text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100">
                        ›
                      </span>
                    </Link>
                  </td>
                  <td className="py-2.5 pr-3">
                    <div className="flex items-center gap-3">
                      <div className="h-2 min-w-[80px] flex-1 rounded-full bg-muted">
                        <div
                          className="h-full rounded-full"
                          style={{ width: `${fill}%`, background: color }}
                        />
                      </div>
                      <span className="w-14 shrink-0 text-right font-mono tabular-nums text-foreground">
                        {pctStr(b.car)}
                      </span>
                    </div>
                  </td>
                  <td className="py-2.5 pr-3 text-right font-mono tabular-nums text-muted-foreground">
                    {pctStr(b.tier1)}
                  </td>
                  <td className="py-2.5 pr-3 text-right font-mono tabular-nums text-muted-foreground">
                    {pctStr(b.cet1)}
                  </td>
                  <td className="py-2.5 pr-4 text-right">
                    {buffer == null ? (
                      <span className="text-muted-foreground">—</span>
                    ) : (
                      <span className={`font-mono tabular-nums ${bufferTone(buffer)}`}>
                        {buffer >= 0 ? "+" : "−"}
                        {Math.abs(buffer).toFixed(1)}pp
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border px-4 py-2.5 text-[11px] text-muted-foreground">
          <span>Source: BRSA quarterly filings · {quarterLabel(period)}</span>
          <span>Buffer = CAR − 12% minimum</span>
        </div>
      </div>
    </section>
  );
}
