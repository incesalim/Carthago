/**
 * CapitalByBank — the per-bank capital register on /capital.
 *
 * The bar is the point: each bank's total capital drawn as CET1 (navy) plus the
 * AT1 + Tier-2 stack (plum), against a 12% tick on the track. Read down the navy
 * and you can see how much of the sector's "capital adequacy" is common equity
 * and how much is instruments. Sorted THINNEST COMMON EQUITY FIRST, because that
 * is the finding; the meta line says so.
 *
 * TWO DIFFERENT THRESHOLDS live here, and conflating them was a real defect:
 * the 12% tick is BDDK's TOTAL-capital target, which AT1 and Tier-2 legitimately
 * count toward — sitting below it on common equity alone is composition, NOT a
 * breach, and the prose has always said so. The red CET1 figure is a different
 * test: 7% (4.5 minimum + 2.5pp conservation), which is what common equity
 * actually answers to. It used to redden every bank under 12%, painting most of
 * the register as deficient when none of it was.
 *
 * Server component, on the sheet — no card (DESIGN.md ground rule 1).
 */
import Link from "next/link";
import { BANK_NAMES } from "@/app/lib/bank_names";
import { SecHead } from "@/app/components/desk";
import { CAR_TARGET, CET1_TARGET } from "@/app/lib/capital-thresholds";
import type { BankCapitalRow } from "@/app/lib/audit-ratios";

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
  const hybridFunded = ranked.filter((b) => b.cet1 != null && b.cet1 < CAR_TARGET).length;
  const belowCet1Req = ranked.filter((b) => b.cet1 != null && b.cet1 < CET1_TARGET).length;

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
          {hybridFunded} of {ranked.length} banks
        </b>{" "}
        hold common equity below the {CAR_TARGET}% target they must meet in total. AT1 and Tier-2
        count toward that target, so this is not a breach — it is what the cushion is made of.
        Common equity answers to its own {CET1_TARGET}% requirement, and{" "}
        {belowCet1Req === 0 ? (
          <b className="font-semibold text-foreground">every bank clears it</b>
        ) : (
          <b className="font-semibold text-foreground">{belowCet1Req} sit below it</b>
        )}
        .
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
            const buffer = b.car == null ? null : b.car - CAR_TARGET;
            const thinCet1 = b.cet1 != null && b.cet1 < CET1_TARGET;

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
                    {/* BDDK's total-capital target, on the track */}
                    <span
                      className="absolute -top-0.5 -bottom-0.5 w-px bg-warning"
                      style={{ left: w(CAR_TARGET) }}
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
        <span>
          Track = 0–25% of RWA · tick = BDDK&rsquo;s {CAR_TARGET}% target · red CET1 = below the{" "}
          {CET1_TARGET}% common-equity requirement
        </span>
        <span>Source: BRSA quarterly filings · {quarterLabel(period)}</span>
      </div>
    </div>
  );
}
