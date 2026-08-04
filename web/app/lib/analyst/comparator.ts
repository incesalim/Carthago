/**
 * Task 2.3 — previous-period comparator. QoQ and YoY for the metrics the memo
 * narrates, computed from the SAME SeriesBundle sections.ts used (one fetch
 * per run). Pure given the bundle; missing priors yield null, never zero.
 */
import { ordOf, periodFromOrd, singleQuarter, ttmEndingAt } from "../period-math";
import type { SeriesBundle } from "./series";

export interface MetricChange {
  metric: string;
  unit: "pct" | "pp" | "thousand_tl";
  now: number | null;
  qoq: { prior: number | null; delta: number | null; growth_pct: number | null; direction: "up" | "down" | "flat" | null };
  yoy: { prior: number | null; delta: number | null; growth_pct: number | null; direction: "up" | "down" | "flat" | null };
}

function direction(delta: number | null, eps: number): "up" | "down" | "flat" | null {
  if (delta == null) return null;
  if (delta > eps) return "up";
  if (delta < -eps) return "down";
  return "flat";
}

function change(
  metric: string,
  unit: MetricChange["unit"],
  at: (period: string) => number | null,
  period: string,
  eps = 0.05,
): MetricChange {
  const ord = ordOf(period);
  const now = at(period);
  const qP = ord != null ? periodFromOrd(ord - 1) : null;
  const yP = ord != null ? periodFromOrd(ord - 4) : null;
  const q = qP ? at(qP) : null;
  const yv = yP ? at(yP) : null;
  const dq = now != null && q != null ? Number((now - q).toFixed(2)) : null;
  const dy = now != null && yv != null ? Number((now - yv).toFixed(2)) : null;
  // Growth PERCENT precomputed for amount metrics — the AKBNK run derived
  // "+28.3% YoY" by hand from the delta because only the delta was given.
  // Ratio metrics keep deltas only (a growth-% of a percentage misleads).
  const g = (a: number | null, b: number | null): number | null =>
    unit === "thousand_tl" && a != null && b != null && b !== 0
      ? Number((((a - b) / Math.abs(b)) * 100).toFixed(1))
      : null;
  return {
    metric,
    unit,
    now,
    qoq: { prior: q, delta: dq, growth_pct: g(now, q), direction: direction(dq, eps) },
    yoy: { prior: yv, delta: dy, growth_pct: g(now, yv), direction: direction(dy, eps) },
  };
}

export function buildComparatives(bundle: SeriesBundle, period: string): MetricChange[] {
  const ord = ordOf(period);
  if (ord == null) return [];

  const stagesAt = (f: (r: NonNullable<ReturnType<SeriesBundle["stages"]["get"]>>) => number | null) =>
    (p: string): number | null => {
      const r = bundle.stages.get(p);
      return r ? f(r) : null;
    };
  const capAt = (f: (r: NonNullable<ReturnType<SeriesBundle["capital"]["get"]>>) => number | null) =>
    (p: string): number | null => {
      const r = bundle.capital.get(p);
      return r ? f(r) : null;
    };

  const netYtd = bundle.plByRole.get("period_net") ?? new Map<number, number>();

  return [
    change("total_assets", "thousand_tl", (p) => bundle.bsTotal.get(p) ?? null, period, 1),
    change(
      "net_income_quarterly",
      "thousand_tl",
      (p) => {
        const o = ordOf(p);
        return o == null ? null : singleQuarter(netYtd, o);
      },
      period,
      1,
    ),
    change(
      "net_income_ttm",
      "thousand_tl",
      (p) => {
        const o = ordOf(p);
        return o == null ? null : ttmEndingAt(netYtd, o);
      },
      period,
      1,
    ),
    change(
      "npl_ratio_pct",
      "pp",
      stagesAt((r) =>
        r.stage3_amount != null && r.total_amount
          ? Number(((r.stage3_amount / r.total_amount) * 100).toFixed(2))
          : null,
      ),
      period,
    ),
    change(
      "stage2_ratio_pct",
      "pp",
      stagesAt((r) =>
        r.stage2_amount != null && r.total_amount
          ? Number(((r.stage2_amount / r.total_amount) * 100).toFixed(2))
          : null,
      ),
      period,
    ),
    change(
      "stage3_coverage_pct",
      "pp",
      stagesAt((r) => (r.stage3_coverage != null ? Number((r.stage3_coverage * 100).toFixed(1)) : null)),
      period,
    ),
    change("car_pct", "pp", capAt((r) => r.capital_adequacy_ratio), period),
    change("cet1_pct", "pp", capAt((r) => r.cet1_ratio), period),
    change(
      "car_minus_cet1_pp",
      "pp",
      capAt((r) =>
        r.capital_adequacy_ratio != null && r.cet1_ratio != null
          ? Number((r.capital_adequacy_ratio - r.cet1_ratio).toFixed(2))
          : null,
      ),
      period,
    ),
    change(
      "total_equity",
      "thousand_tl",
      (p) => bundle.equityClosing.get(p) ?? null,
      period,
      1,
    ),
  ];
}
