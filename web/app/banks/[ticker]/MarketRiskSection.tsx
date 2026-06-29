/**
 * MarketRiskSection — CAMELS "S" for one bank on /banks/[ticker]. The §4
 * footnotes turned into the market-risk view a strategist reads: three headline
 * tiles (FX net open position / capital, the cumulative ≤1y repricing gap, and
 * the liquidity-coverage ratio), the interest-rate repricing gap as a diverging
 * ladder, and the FX net open position by currency. Magnitude ratios are derived
 * in heatmap.ts (identical to Compare); the per-bucket / per-currency detail
 * comes from market-risk.ts. Renders nothing when the bank discloses no §4
 * market-risk data.
 */
import { Card } from "@/app/components/ui/card";
import { Section, Stat } from "@/app/components/ui";
import type { BankMetricRow } from "@/app/lib/heatmap";
import type { MarketRiskDetail } from "@/app/lib/market-risk";

/** "+2.3%" / "−8.4%" — signed, with an explicit plus on non-negatives. */
const signedPct = (v: number | null | undefined, d = 1): string =>
  v == null ? "—" : `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(d)}%`;
/** "168%" — an unsigned level. */
const levelPct = (v: number | null | undefined, d = 0): string =>
  v == null ? "—" : `${v.toFixed(d)}%`;

const toneClass = (good: boolean | null): string =>
  good == null ? "text-muted-foreground" : good ? "text-positive" : "text-negative";

/** Diverging horizontal bars centred on a zero line: positive → right (green),
 *  negative → left (red). Bar length scales to the largest |value| in the set. */
function DivergingBars({
  rows,
}: {
  rows: { label: string; pct: number | null }[];
}) {
  const maxAbs = Math.max(...rows.map((r) => Math.abs(r.pct ?? 0)), 0.001);
  return (
    <div className="space-y-2.5">
      {rows.map((r) => {
        const pct = r.pct ?? 0;
        const pos = pct >= 0;
        const w = (Math.abs(pct) / maxAbs) * 50; // % of the half-width
        return (
          <div key={r.label} className="flex items-center gap-3 text-xs">
            <div className="w-12 shrink-0 font-medium text-muted-foreground">{r.label}</div>
            <div className="relative h-2.5 flex-1">
              <div className="absolute inset-y-0 left-1/2 w-px bg-border" aria-hidden />
              <div
                className="absolute top-1/2 h-2.5 -translate-y-1/2 rounded-full"
                style={{
                  width: `${w}%`,
                  backgroundColor: pos ? "var(--positive)" : "var(--negative)",
                  ...(pos ? { left: "50%" } : { right: "50%" }),
                }}
              />
            </div>
            <div
              className={`w-14 shrink-0 text-right font-semibold tabular-nums ${
                pos ? "text-positive" : "text-negative"
              }`}
            >
              {r.pct == null ? "—" : signedPct(r.pct, 1)}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function MarketRiskSection({
  rows,
  detail,
}: {
  /** This bank's heatmap rows, ascending by period (carry fx_nop, lcr). */
  rows: BankMetricRow[];
  /** Per-bank §4 repricing ladder + FX net open position (latest quarter). */
  detail: MarketRiskDetail;
}) {
  const latest = rows[rows.length - 1] ?? null;
  const fxNop = latest?.fx_nop ?? null;
  const lcr = latest?.lcr ?? null;
  const gap1y = detail.repricing.gap1yPct;

  const hasTiles = fxNop != null || gap1y != null || lcr != null;
  if (!hasTiles && !detail.hasData) return null;

  return (
    <Section
      title="Market Risk"
      description="FX net open position and interest-rate repricing gap, from the bank's §4 footnotes."
      contentClassName=""
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Stat
          label="FX NOP / Capital"
          value={signedPct(fxNop)}
          hint={
            fxNop == null ? undefined : (
              <span className={toneClass(fxNop >= 0)}>
                {fxNop >= 0 ? "net long FX" : "net short FX"}
              </span>
            )
          }
        />
        <Stat
          label="1Y Repricing Gap"
          value={signedPct(gap1y)}
          hint={
            gap1y == null ? undefined : (
              <span className={toneClass(gap1y >= 0)}>of rate-sensitive assets</span>
            )
          }
        />
        <Stat
          label="Liquidity Coverage"
          value={levelPct(lcr)}
          hint={
            lcr == null ? undefined : (
              <span className={toneClass(lcr >= 100)}>LCR · min 100%</span>
            )
          }
        />
      </div>

      {(detail.repricing.buckets.length > 0 || detail.fx.items.length > 0) && (
        <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
          {detail.repricing.buckets.length > 0 && (
            <Card className="p-5">
              <div className="mb-4">
                <div className="text-sm font-bold text-foreground">Interest-rate repricing gap</div>
                <div className="text-xs text-muted-foreground">
                  % of rate-sensitive assets, by repricing bucket
                </div>
              </div>
              <DivergingBars rows={detail.repricing.buckets} />
            </Card>
          )}

          {detail.fx.items.length > 0 && (
            <Card className="p-5">
              <div className="mb-3">
                <div className="text-sm font-bold text-foreground">FX net open position</div>
                <div className="text-xs text-muted-foreground">
                  Net position as % of regulatory capital
                </div>
              </div>
              <div>
                {detail.fx.items.map((it) => {
                  const pos = (it.pct ?? 0) >= 0;
                  return (
                    <div
                      key={it.label}
                      className="flex items-center justify-between border-b border-border py-2.5 text-sm last:border-0"
                    >
                      <span className="font-medium text-foreground">{it.label}</span>
                      <span
                        className={`font-semibold tabular-nums ${
                          it.pct == null ? "text-muted-foreground" : pos ? "text-positive" : "text-negative"
                        }`}
                      >
                        {it.pct == null ? "—" : signedPct(it.pct, 1)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </Card>
          )}
        </div>
      )}
    </Section>
  );
}
