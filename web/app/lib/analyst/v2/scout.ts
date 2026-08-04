/**
 * Analyst V2 — the generic anomaly scout.
 *
 * Story-agnostic and fully deterministic: it walks every numeric statement
 * row and surfaces WHAT MOVED, scored, without deciding what any of it
 * means. Its output is the research agent's starting terrain — ranked
 * candidates, each carrying the numbers that earned the rank — plus every
 * reconciliation break, validation failure and V1 detector signal as leads.
 *
 * The scout may rank. It must never conclude.
 */
import type { Queryable } from "../data";
import { ordOf, periodFromOrd } from "../../period-math";
import { RECONCILIATIONS, STATEMENTS } from "./registry";
import { runTool, type ToolContext } from "./tools";

export interface ScoutCandidate {
  candidate_id: string;
  source: "movement" | "history_break" | "reconciliation" | "validation" | "detector_signal" | "peer_rank";
  statement: string | null;
  row: string | null;
  metric: string | null;
  description: string;
  values: Record<string, number | string | null>;
  score: number;
}

export interface ScoutResult {
  bank: string;
  period: string;
  kind: string;
  snapshot: string;
  candidates: ScoutCandidate[];
  total_candidates: number;
  suppressed_below_rank: number;
}

const LINE_STATEMENTS = ["balance_sheet_assets", "balance_sheet_liabilities", "off_balance", "profit_loss", "oci", "cash_flow"] as const;
const SINGLETON_STATEMENTS = ["capital", "liquidity", "stages"] as const;
const TOP_N = 40;
const HISTORY_MIN = 6;

const fold = (s: string) => s.replace(/İ/g, "I").replace(/ı/g, "i").toUpperCase();

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function mean(xs: number[]): number {
  return xs.reduce((a, b) => a + b, 0) / xs.length;
}

function stdev(xs: number[]): number {
  const m = mean(xs);
  return Math.sqrt(mean(xs.map((x) => (x - m) ** 2)));
}

/** |z| capped at 8 so one wild history point cannot dominate every score. */
function zScore(value: number, history: number[]): number | null {
  if (history.length < HISTORY_MIN) return null;
  const sd = stdev(history);
  if (sd === 0) return value === mean(history) ? 0 : 8;
  return Math.min(Math.abs((value - mean(history)) / sd), 8);
}

export async function runScout(ctx: ToolContext): Promise<ScoutResult> {
  const { bank, period, kind } = ctx.defaults;
  const db = ctx.db;
  const ord = ordOf(period);
  if (ord == null) throw new Error(`bad period ${period}`);
  const prevQ = periodFromOrd(ord - 1);
  const candidates: ScoutCandidate[] = [];
  let seq = 0;
  const push = (c: Omit<ScoutCandidate, "candidate_id">) => {
    candidates.push({ candidate_id: `C${String(++seq).padStart(3, "0")}`, ...c });
  };

  // Scale denominators for normalization — absence just disables that axis.
  const denomRows = await db.all<{ statement: string; total: number | null }>(
    "SELECT statement, MAX(amount_total) AS total FROM bank_audit_balance_sheet " +
      "WHERE bank_ticker = ? AND period = ? AND kind = ? AND hierarchy = '' " +
      "AND statement IN ('assets','liabilities') GROUP BY bank_ticker, statement",
    [bank, period, kind],
  );
  const assets = Math.max(...denomRows.map((r) => r.total ?? 0), 0) || null;

  /* ---- line statements: per-row QoQ/YoY, history z, sign flips ---- */
  for (const statement of LINE_STATEMENTS) {
    const spec = STATEMENTS[statement];
    const amountCol = spec.numericColumns.includes("amount") ? "amount" : "amount_total";
    const rows = await db.all<{ period: string; hierarchy: string; item_name: string | null; v: number | null }>(
      `SELECT period, hierarchy, item_name, ${amountCol} AS v FROM ${spec.table} ` +
        `WHERE bank_ticker = ? AND kind = ?` + (spec.where ? ` AND ${spec.where}` : "") + " ORDER BY period, item_order",
      [bank, kind],
    );
    if (!rows.length) continue;
    const byRow = new Map<string, Map<string, number>>();
    const labels = new Map<string, string>();
    for (const r of rows) {
      const k = `${r.hierarchy}|${fold(r.item_name ?? "")}`;
      labels.set(k, `${r.hierarchy} ${r.item_name ?? ""}`.trim());
      if (r.v == null) continue;
      let m = byRow.get(k);
      if (!m) byRow.set(k, (m = new Map()));
      m.set(r.period, r.v);
    }
    const totalAbsDelta = [...byRow.values()].reduce((s, m) => {
      const now = m.get(period);
      const pq = m.get(prevQ);
      return s + (now != null && pq != null ? Math.abs(now - pq) : 0);
    }, 0);

    for (const [k, m] of byRow) {
      const now = m.get(period);
      if (now == null) continue;
      const pq = m.get(prevQ) ?? null;
      const qoq = pq != null ? now - pq : null;
      // History of QoQ deltas for THIS row.
      const deltas: number[] = [];
      for (let back = 1; back <= 16; back++) {
        const a = m.get(periodFromOrd(ord - back));
        const b = m.get(periodFromOrd(ord - back - 1));
        if (a != null && b != null) deltas.push(a - b);
      }
      const z = qoq != null ? zScore(qoq, deltas) : null;
      const share = qoq != null && totalAbsDelta > 0 ? Math.abs(qoq) / totalAbsDelta : null;
      const normAssets = qoq != null && assets ? Math.abs(qoq) / assets : null;
      const signFlip = pq != null && pq !== 0 && now !== 0 && Math.sign(now) !== Math.sign(pq);
      const appeared = pq == null && [...m.keys()].filter((p) => p < period).length === 0 && Math.abs(now) > 0;

      // SURPRISE dominates; magnitude terms are capped so an always-huge row
      // cannot outrank an unusual one; rollup/total rows restate their
      // children and are damped, not hidden.
      const isRollup = /TOPLAM|TOTAL|GENEL|\([A-Z](\+[A-Z])+\)|\([IVX]+(\+[IVX]+)+\)/.test(fold(String(labels.get(k) ?? "")));
      let score =
        (z ?? 0) * 1.5 +
        Math.min(share ?? 0, 0.6) * 3.0 +
        Math.min(normAssets ?? 0, 0.05) * 40 +
        (signFlip ? 2 : 0) +
        (appeared ? 1.5 : 0);
      if (isRollup) score *= 0.4;
      if (score < 1.5) continue;
      push({
        source: "movement",
        statement,
        row: labels.get(k) ?? k,
        metric: amountCol,
        description: `row moved: now ${now}, QoQ ${qoq ?? "n/a"}${signFlip ? ", SIGN FLIP" : ""}${appeared ? ", first appearance" : ""}`,
        values: { now, prev_quarter: pq, qoq_delta: qoq, z_vs_own_history: z, share_of_statement_abs_change: share != null ? Number(share.toFixed(3)) : null, pct_of_assets: normAssets != null ? Number((normAssets * 100).toFixed(3)) : null },
        score: Number(score.toFixed(2)),
      });
    }
  }

  /* ---- equity movements: each movement row vs its own history ---- */
  {
    const rows = await db.all<{ period: string; item_order: number; item_name: string | null; total_equity: number | null }>(
      "SELECT period, item_order, item_name, total_equity FROM bank_audit_equity_change " +
        "WHERE bank_ticker = ? AND kind = ? AND period_type = 'current' ORDER BY period, item_order",
      [bank, kind],
    );
    const byPeriod = new Map<string, { item_order: number; item_name: string | null; total_equity: number | null }[]>();
    for (const r of rows) {
      const arr = byPeriod.get(r.period) ?? [];
      arr.push(r);
      byPeriod.set(r.period, arr);
    }
    const nowRows = byPeriod.get(period) ?? [];
    const equityBase = nowRows.length ? Math.abs(num(nowRows[nowRows.length - 1].total_equity) ?? 0) || null : null;
    for (let i = 1; i < nowRows.length - 1; i++) {
      const r = nowRows[i];
      const impact = num(r.total_equity);
      if (impact == null || impact === 0) continue;
      const label = fold(r.item_name ?? String(r.item_order));
      const history: number[] = [];
      for (const [p, list] of byPeriod) {
        if (p >= period) continue;
        const match = list.find((x) => fold(x.item_name ?? String(x.item_order)) === label);
        if (match && num(match.total_equity) != null) history.push(num(match.total_equity) as number);
      }
      const z = zScore(impact, history);
      const shareOfEquity = equityBase ? Math.abs(impact) / equityBase : null;
      const score = (z ?? (shareOfEquity != null && shareOfEquity > 0.02 ? 3 : 0)) + (shareOfEquity ?? 0) * 20;
      if (score < 1.2) continue;
      push({
        source: "movement",
        statement: "equity_change",
        row: `${r.item_order} ${r.item_name ?? ""}`.trim(),
        metric: "total_equity",
        description: `equity movement: impact ${impact}${shareOfEquity != null ? ` (=${(shareOfEquity * 100).toFixed(1)}% of closing equity)` : ""}`,
        values: { impact, z_vs_own_history: z, pct_of_closing_equity: shareOfEquity != null ? Number((shareOfEquity * 100).toFixed(2)) : null, history_points: history.length },
        score: Number(score.toFixed(2)),
      });
    }
  }

  /* ---- singleton statements: metric deltas vs own history ---- */
  for (const statement of SINGLETON_STATEMENTS) {
    const spec = STATEMENTS[statement];
    const rows = await db.all<Record<string, unknown> & { period: string }>(
      `SELECT period, ${spec.numericColumns.join(", ")} FROM ${spec.table} ` +
        "WHERE bank_ticker = ? AND kind = ? AND period_type = 'current' ORDER BY period",
      [bank, kind],
    );
    if (!rows.length) continue;
    for (const col of spec.numericColumns) {
      const series = new Map(rows.map((r) => [r.period, num(r[col])]));
      const now = series.get(period);
      const pq = series.get(prevQ);
      if (now == null || pq == null) continue;
      const qoq = now - pq;
      const deltas: number[] = [];
      for (let back = 1; back <= 16; back++) {
        const a = series.get(periodFromOrd(ord - back));
        const b = series.get(periodFromOrd(ord - back - 1));
        if (a != null && b != null) deltas.push(a - b);
      }
      const z = zScore(qoq, deltas);
      if (z == null || z < 2.2) continue;
      push({
        source: "history_break",
        statement,
        row: null,
        metric: col,
        description: `metric broke from its own history: now ${now}, QoQ ${Number(qoq.toFixed(3))}, |z| ${z.toFixed(1)}`,
        values: { now, prev_quarter: pq, qoq_delta: Number(qoq.toFixed(4)), z_vs_own_history: Number(z.toFixed(2)) },
        score: Number(z.toFixed(2)),
      });
    }
  }

  /* ---- reconciliations: any break is a lead ---- */
  for (const rec of RECONCILIATIONS) {
    try {
      const r = await runTool(ctx, "reconcile_statements", { reconciliation: rec });
      const flat = JSON.stringify(r.data);
      if (flat.includes('"BREAKS"')) {
        push({
          source: "reconciliation",
          statement: null,
          row: null,
          metric: rec,
          description: `reconciliation BREAKS: ${rec} (evidence ${r.evidence_id})`,
          values: { evidence_id: r.evidence_id },
          score: 5,
        });
      }
    } catch {
      /* not computable for this partition */
    }
  }

  /* ---- validation failures + V1 signals: always leads ---- */
  try {
    const v = await runTool(ctx, "get_validation_status", {});
    for (const row of (v.data as { statement: string; checks_failed: number }[]) ?? []) {
      if (row.checks_failed > 0) {
        push({
          source: "validation",
          statement: row.statement,
          row: null,
          metric: null,
          description: `validator failing on ${row.statement} (${row.checks_failed}) — anomalies here may be extraction defects, not economics`,
          values: { checks_failed: row.checks_failed, evidence_id: v.evidence_id },
          score: 3,
        });
      }
    }
  } catch { /* absent */ }
  try {
    const s = await runTool(ctx, "get_existing_signals", {});
    for (const sig of (s.data as { signal_id: string; signal_type: string; severity: string }[]) ?? []) {
      push({
        source: "detector_signal",
        statement: null,
        row: null,
        metric: sig.signal_type,
        description: `V1 detector: ${sig.signal_id} [${sig.severity}]`,
        values: { evidence_id: s.evidence_id },
        score: sig.severity === "critical" ? 6 : sig.severity === "alert" ? 4 : 2,
      });
    }
  } catch { /* absent */ }

  const ranked = candidates.sort((a, b) => b.score - a.score);
  return {
    bank, period, kind,
    snapshot: ctx.snapshot.id,
    candidates: ranked.slice(0, TOP_N),
    total_candidates: ranked.length,
    suppressed_below_rank: Math.max(ranked.length - TOP_N, 0),
  };
}
