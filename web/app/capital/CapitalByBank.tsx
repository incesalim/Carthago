/**
 * CapitalByBank — the per-bank capital register on /capital.
 *
 * The bar is the point: each bank's total capital drawn as CET1 (navy) plus the
 * AT1 + Tier-2 stack (plum), against a 12% tick on the track. Read down the navy
 * and you can see how much of the sector's "capital adequacy" is common equity
 * and how much is instruments — 17 of 34 banks hold CET1 below the 12% they must
 * meet in total. Sorted THINNEST COMMON EQUITY FIRST, because that is the
 * finding; the meta line says so.
 *
 * Server component, on the sheet — no card (DESIGN.md ground rule 1).
 */
import Link from "next/link";
import { BANK_NAMES } from "@/app/lib/bank_names";
import { SecHead } from "@/app/components/desk";
import type { BankCapitalRow } from "@/app/lib/audit-ratios";

const CAR_MIN = 12; // regulatory minimum total capital (%)
const DOMAIN_MAX = 25; // bar-track ceiling; a few specialists run far above it

const pctStr = (v: number | null, d = 1) => (v == null ? "—" : `${v.toFixed(d)}%`);

function quarterLabel(period: string | null): string {
  if (!period) return "";
  const m = /^(\d{4})Q([1-4])$/.exec(period);
  return m ? `Q${m[2]} ${m[1]}` : period;
}

export default function CapitalByBank({
  period,
  rows,
}: {
  period: string | null;
  rows: BankCapitalRow[];
}) {
  if (rows.length === 0) return null;

  // thinnest common equity first — the register's whole argument
  const ranked = [...rows].sort((a, b) => (a.cet1 ?? Infinity) - (b.cet1 ?? Infinity));
  const thin = ranked.filter((b) => b.cet1 != null && b.cet1 < CAR_MIN).length;

  return (
    <div>
      <SecHead
        title="By bank"
        href="/banks"
        hrefLabel="all banks →"
        meta={`common equity vs the hybrid stack · thinnest first · audited ${quarterLabel(period)}`}
        className="mb-2.5"
      />
      <p className="mb-3 text-[12px] leading-relaxed text-muted-foreground">
        <b className="font-semibold text-foreground">
          {thin} of {ranked.length} banks
        </b>{" "}
        hold common equity below the 12% minimum they must meet in total. AT1 and Tier-2 count
        toward that minimum, so this is not a breach — it is what the cushion is made of.
      </p>

      <table className="w-full border-collapse">
        <thead>
          <tr>
            {["Bank", "CET1 + AT1/Tier-2", "CET1", "Tier 1", "CAR", "Buffer"].map((h, i) => (
              <th
                key={h}
                className={`border-b border-foreground pb-1.5 font-mono text-[8.5px] font-normal uppercase tracking-[0.07em] text-faint ${
                  i <= 1 ? "text-left" : "text-right"
                }`}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ranked.map((b) => {
            const name = BANK_NAMES[b.bank_ticker] ?? b.bank_ticker;
            const cet1 = b.cet1 ?? 0;
            const hybrid = b.car != null ? Math.max(0, b.car - cet1) : 0;
            const w = (v: number) => `${Math.min(v / DOMAIN_MAX, 1) * 100}%`;
            const buffer = b.car == null ? null : b.car - CAR_MIN;
            const thinCet1 = b.cet1 != null && b.cet1 < CAR_MIN;

            return (
              <tr key={b.bank_ticker} className="hover:bg-muted">
                <td className="border-b border-hair py-1.5 pr-3 text-[12.5px]">
                  <Link href={`/banks/${b.bank_ticker}`} className="font-medium text-foreground hover:text-primary">
                    {name}
                  </Link>
                </td>
                <td className="border-b border-hair py-1.5 pr-3">
                  {/* the composition: common equity, then what was bought */}
                  <span className="relative flex h-2 w-full min-w-[120px] bg-muted">
                    <span className="h-full bg-data" style={{ width: w(cet1) }} />
                    <span className="h-full bg-chart-5 opacity-70" style={{ width: w(hybrid) }} />
                    {/* the 12% minimum, on the track */}
                    <span
                      className="absolute -top-0.5 -bottom-0.5 w-px bg-warning"
                      style={{ left: w(CAR_MIN) }}
                      aria-hidden
                    />
                  </span>
                </td>
                <td
                  className={`border-b border-hair py-1.5 pl-2 text-right font-mono text-[12px] font-semibold tabular-nums ${
                    thinCet1 ? "text-negative" : "text-foreground"
                  }`}
                >
                  {pctStr(b.cet1)}
                </td>
                <td className="border-b border-hair py-1.5 pl-2 text-right font-mono text-[11.5px] tabular-nums text-faint">
                  {pctStr(b.tier1)}
                </td>
                <td className="border-b border-hair py-1.5 pl-2 text-right font-mono text-[12px] tabular-nums text-foreground">
                  {pctStr(b.car)}
                </td>
                <td className="border-b border-hair py-1.5 pl-2 text-right font-mono text-[11.5px] tabular-nums text-faint">
                  {buffer == null
                    ? "—"
                    : `${buffer >= 0 ? "+" : "−"}${Math.abs(buffer).toFixed(1)}pp`}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[9px] uppercase tracking-[0.05em] text-faint">
        <span>
          <span className="mr-1 inline-block size-2 bg-data align-middle" aria-hidden /> CET1
        </span>
        <span>
          <span className="mr-1 inline-block size-2 bg-chart-5 align-middle opacity-70" aria-hidden />
          AT1 + Tier-2
        </span>
        <span>Track = 0–25% of RWA · tick = the 12% minimum</span>
        <span>Source: BRSA quarterly filings · {quarterLabel(period)}</span>
      </div>
    </div>
  );
}
