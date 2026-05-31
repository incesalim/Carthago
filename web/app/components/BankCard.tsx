/**
 * BankCard — compact per-bank summary surfaced at the top of /banks/[ticker].
 *
 * Three sections:
 *   1. Profile  — branch counts (domestic / foreign / total) + personnel
 *   2. Credit   — TFRS 9 Stage 1 / 2 / 3 amounts with coverage ratios and
 *                 derived NPL ratio (Stage 3 / total loans)
 *   3. Period   — what the figures refer to (latest available year-end)
 *
 * Each section degrades gracefully when the underlying disclosure is
 * missing (rendered as "—"). The card is intentionally dense — one row
 * per metric so it fits on a single screen alongside the financial tables.
 */
import type { BankProfile, BankStages } from "@/app/lib/audit";

const NF0 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const PCT2 = new Intl.NumberFormat("en-US", {
  style: "percent",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Format a TL-thousands value as "X.XX B" (billion TL) / "X.X M" (million TL). */
function fmtTL(v: number | null | undefined): string {
  if (v == null) return "—";
  // Values come from BRSA in TL thousands; multiply by 1e3 to get TL.
  const tl = v * 1_000;
  if (Math.abs(tl) >= 1e9) return `${(tl / 1e9).toFixed(2)} B₺`;
  if (Math.abs(tl) >= 1e6) return `${(tl / 1e6).toFixed(1)} M₺`;
  return NF0.format(tl) + "₺";
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return "—";
  return PCT2.format(v);
}

function fmtInt(v: number | null | undefined): string {
  return v == null ? "—" : NF0.format(v);
}

/** "2025Q4" → "Q4 2025" for compact display. */
function fmtPeriod(p: string | null | undefined): string {
  if (!p) return "—";
  const m = /^(\d{4})Q([1-4])$/.exec(p);
  if (!m) return p;
  return `Q${m[2]} ${m[1]}`;
}

interface Props {
  profile: BankProfile | null;
  stages: BankStages | null;
  /** Latest period covered by financial tables (used as fallback if stages is null). */
  latestPeriod?: string | null;
}

export default function BankCard({ profile, stages, latestPeriod }: Props) {
  const nplRatio =
    stages?.stage3_amount != null && stages?.total_amount
      ? stages.stage3_amount / stages.total_amount
      : null;

  // Show whichever period the credit data is from; fall back to the
  // financial-table period so the card is never label-less.
  const period = stages?.period ?? profile?.period ?? latestPeriod ?? null;

  return (
    <section className="mb-6 rounded-lg border bg-card shadow-sm overflow-hidden">
      <div className="px-5 py-3 border-b bg-muted flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-foreground">Bank profile</h2>
        <span className="text-[11px] text-muted-foreground tabular-nums">
          {fmtPeriod(period)}
          {stages?.kind ? ` · ${stages.kind === "consolidated" ? "Consolidated" : "Bank-only"}` : ""}
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-border">
        {/* --- Operational scale ----------------------------------------- */}
        <div className="px-5 py-4">
          <h3 className="text-[10px] uppercase tracking-wide text-muted-foreground mb-2">Scale</h3>
          <div className="space-y-1.5">
            <CardRow label="Branches" value={fmtInt(profile?.branches_total)} />
            <CardRow
              label="Domestic"
              value={fmtInt(profile?.branches_domestic)}
              muted
            />
            <CardRow
              label="Foreign"
              value={fmtInt(profile?.branches_foreign)}
              muted
            />
            <CardRow label="Personnel" value={fmtInt(profile?.personnel)} />
          </div>
        </div>

        {/* --- TFRS 9 stage breakdown ----------------------------------- */}
        <div className="px-5 py-4">
          <h3 className="text-[10px] uppercase tracking-wide text-muted-foreground mb-2">
            Loan portfolio
          </h3>
          <div className="space-y-1.5">
            <CardRow label="Stage 1" value={fmtTL(stages?.stage1_amount)} />
            <CardRow label="Stage 2" value={fmtTL(stages?.stage2_amount)} />
            <CardRow label="Stage 3 (NPL)" value={fmtTL(stages?.stage3_amount)} />
            <CardRow
              label="Total loans"
              value={fmtTL(stages?.total_amount)}
              bold
            />
          </div>
        </div>

        {/* --- Coverage ratios ------------------------------------------- */}
        <div className="px-5 py-4">
          <h3 className="text-[10px] uppercase tracking-wide text-muted-foreground mb-2">
            Coverage
          </h3>
          <div className="space-y-1.5">
            <CardRow label="Stage 1 cov." value={fmtPct(stages?.stage1_coverage)} />
            <CardRow label="Stage 2 cov." value={fmtPct(stages?.stage2_coverage)} />
            <CardRow label="Stage 3 cov." value={fmtPct(stages?.stage3_coverage)} />
            <CardRow label="NPL ratio" value={fmtPct(nplRatio)} bold />
          </div>
        </div>
      </div>
    </section>
  );
}

function CardRow({
  label,
  value,
  bold,
  muted,
}: {
  label: string;
  value: string;
  bold?: boolean;
  muted?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between text-xs">
      <span
        className={
          muted
            ? "text-muted-foreground pl-2"
            : bold
            ? "text-foreground font-medium"
            : "text-muted-foreground"
        }
      >
        {label}
      </span>
      <span
        className={
          "tabular-nums " +
          (muted
            ? "text-muted-foreground"
            : bold
            ? "text-foreground font-semibold"
            : "text-foreground")
        }
      >
        {value}
      </span>
    </div>
  );
}
