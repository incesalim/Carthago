/**
 * Forward-looking credit risk — data layer (SERVER ONLY). Display-study
 * Phase 5: the early-warning lens the Asset Quality tab lacked. Aggregates the
 * per-bank audit lanes "of reporting banks" per quarter (same convention as
 * market-share.ts / audit-ratios.ts — the audited universe is ~98% of sector
 * assets, and same-source numerator/denominator avoids unit drift).
 *
 *   bank_audit_stages       — TFRS-9 staging (amounts + ECL per stage)
 *   bank_audit_npl_movement — NPL roll-forward (additions / collections /
 *                             write-offs / sold), groups III+IV+V, YTD flows
 *
 * Amounts are thousand TRY → ₺bn for display. Period `YYYYQN` sorts lexically.
 */
import { cachedAll } from "./db";

const DEFAULT_KIND = "unconsolidated";
const TH_TO_BN = 1_000_000;

export interface TrendPoint {
  period: string;
  bank_type_code: string;
  value: number;
}

interface StageAggRow {
  period: string;
  s2: number | null;
  s3: number | null;
  total: number | null;
  ecl2: number | null;
  ecl3: number | null;
  ecl_total: number | null;
  n: number;
}

async function stageAgg(kind: string): Promise<StageAggRow[]> {
  // Only banks with BOTH a stage amount and the total contribute to a share —
  // enforced per column via CASE so a partial filer can't skew the ratio.
  return cachedAll<StageAggRow>(
    `SELECT period,
            SUM(CASE WHEN stage2_amount IS NOT NULL AND total_amount IS NOT NULL THEN stage2_amount END) AS s2,
            SUM(CASE WHEN stage3_amount IS NOT NULL AND total_amount IS NOT NULL THEN stage3_amount END) AS s3,
            SUM(CASE WHEN stage2_amount IS NOT NULL AND total_amount IS NOT NULL THEN total_amount END)  AS total,
            SUM(CASE WHEN stage2_ecl IS NOT NULL AND stage2_amount IS NOT NULL THEN stage2_ecl END)      AS ecl2,
            SUM(CASE WHEN stage3_ecl IS NOT NULL AND stage3_amount IS NOT NULL THEN stage3_ecl END)      AS ecl3,
            SUM(total_ecl) AS ecl_total,
            COUNT(DISTINCT bank_ticker) AS n
       FROM bank_audit_stages
      WHERE kind = ? AND period_type = 'current'
      GROUP BY period
      ORDER BY period`,
    [kind],
  );
}

/**
 * Sector TFRS-9 staging shares (% of gross loans), per quarter — the
 * forward-looking stress lens: Stage 2 = significant credit deterioration
 * BEFORE default; Stage 3 = the audited NPL stock.
 */
export async function sectorStageShares(kind: string = DEFAULT_KIND): Promise<TrendPoint[]> {
  const rows = await stageAgg(kind);
  const out: TrendPoint[] = [];
  for (const r of rows) {
    if (r.total == null || r.total <= 0 || r.n < 5) continue;
    if (r.s2 != null) out.push({ period: r.period, bank_type_code: "STAGE2", value: (r.s2 / r.total) * 100 });
    if (r.s3 != null) out.push({ period: r.period, bank_type_code: "STAGE3", value: (r.s3 / r.total) * 100 });
  }
  return out;
}

export const STAGE_SHARE_LABELS: Record<string, string> = {
  STAGE2: "Stage 2 (watchlist)",
  STAGE3: "Stage 3 (NPL)",
};

/** One migration scenario: m% of Stage-2 moves to Stage-3 at Stage-3 coverage. */
export interface MigrationScenario {
  migratePct: number;
  /** Additional provisions required, ₺bn. */
  provisionBn: number;
  /** Same, as % of the existing total ECL stock. */
  pctOfEclStock: number | null;
}

/**
 * Sized scenario (moved here from Phase 3): if m% of the Stage-2 book migrates
 * to Stage-3 and gets provisioned at the CURRENT Stage-3 coverage rate, the
 * provision top-up ≈ m × S2 × (cov3 − cov2). First-order; assumes migration at
 * average coverage, no collateral/recovery changes.
 */
export async function provisionMigrationScenarios(
  kind: string = DEFAULT_KIND,
  migrations: number[] = [5, 10, 20],
): Promise<{ period: string | null; stage2Bn: number | null; cov2: number | null; cov3: number | null; scenarios: MigrationScenario[] }> {
  const rows = await stageAgg(kind);
  const last = rows.filter((r) => r.s2 != null && r.total != null && r.n >= 5).at(-1);
  if (!last || last.s2 == null) return { period: null, stage2Bn: null, cov2: null, cov3: null, scenarios: [] };
  const cov2 = last.ecl2 != null && last.s2 > 0 ? last.ecl2 / last.s2 : null;
  const cov3 = last.ecl3 != null && last.s3 != null && last.s3 > 0 ? last.ecl3 / last.s3 : null;
  if (cov2 == null || cov3 == null || cov3 <= cov2) {
    return { period: last.period, stage2Bn: last.s2 / TH_TO_BN, cov2, cov3, scenarios: [] };
  }
  const scenarios = migrations.map((m) => {
    const provTh = (m / 100) * last.s2! * (cov3 - cov2);
    return {
      migratePct: m,
      provisionBn: provTh / TH_TO_BN,
      pctOfEclStock: last.ecl_total != null && last.ecl_total > 0 ? (provTh / last.ecl_total) * 100 : null,
    };
  });
  return { period: last.period, stage2Bn: last.s2 / TH_TO_BN, cov2, cov3, scenarios };
}

/**
 * Annual NPL roll-forward "of reporting banks": new formation (additions) vs
 * exits (collections + write-offs + sales), ₺bn. Q4 rows only — the audited
 * movement tables are YTD flows, so Q4 = the full year without de-cumulation
 * assumptions. Groups III+IV+V summed (all NPL buckets).
 */
export async function nplFormationAnnual(kind: string = DEFAULT_KIND): Promise<TrendPoint[]> {
  const rows = await cachedAll<{
    period: string;
    additions: number | null;
    collections: number | null;
    write_offs: number | null;
    sold: number | null;
    n: number;
  }>(
    `SELECT period,
            SUM(additions)   AS additions,
            SUM(collections) AS collections,
            SUM(write_offs)  AS write_offs,
            SUM(sold)        AS sold,
            COUNT(DISTINCT bank_ticker) AS n
       FROM bank_audit_npl_movement
      WHERE kind = ? AND period_type = 'current' AND period LIKE '%Q4'
      GROUP BY period
      ORDER BY period`,
    [kind],
  );
  const out: TrendPoint[] = [];
  for (const r of rows) {
    if (r.n < 5) continue;
    if (r.additions != null)
      out.push({ period: r.period, bank_type_code: "FORMATION", value: r.additions / TH_TO_BN });
    // Reducing flows may be stored signed either way per bank layout — take
    // magnitudes (they only ever reduce the NPL balance).
    const exits = Math.abs(r.collections ?? 0) + Math.abs(r.write_offs ?? 0) + Math.abs(r.sold ?? 0);
    out.push({ period: r.period, bank_type_code: "EXITS", value: exits / TH_TO_BN });
  }
  return out;
}

export const NPL_FORMATION_LABELS: Record<string, string> = {
  FORMATION: "New NPL formation (additions)",
  EXITS: "Exits (collections + write-offs + sales)",
};
