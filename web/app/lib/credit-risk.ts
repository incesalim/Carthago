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

// NOTE: nplFormationAnnual() + NPL_FORMATION_LABELS were REMOVED (2026-07-13).
// They returned values already in ₺bn while the only caller charted them with
// yFormat="bn", whose formatter divides by 1_000 again — so ₺673bn of NPL
// formation rendered as "₺1 bn" on the live page. nplRollForwardAnnual() below
// supersedes them: it returns the full split (collections / write-offs / sales),
// which is what the brief needs, and /asset-quality draws it with FormationBars.

// ---------------------------------------------------------------------------
// /asset-quality — the stage ladder and the full roll-forward
//
// stageAgg() already computes the stage AMOUNTS and their ECL; only the shares
// were ever exported. The asset-quality brief needs the amounts and the coverage
// per stage, because the whole finding is that what the NPL ratio prints (Stage
// 3) is the tip: Stage 2 is ~3x larger and carries a fraction of the cover.
// ---------------------------------------------------------------------------

export interface StageLadder {
  period: string;
  /** Reporting banks behind the aggregate. */
  n: number;
  /** Gross loans of the reporting banks (source units: TL thousands). */
  total: number;
  stage1Share: number;
  stage2Share: number;
  stage3Share: number;
  /** Books, ₺bn. */
  stage2Bn: number;
  stage3Bn: number;
  /** Provisions held (ECL), ₺bn. */
  ecl2Bn: number;
  ecl3Bn: number;
  /** ECL ÷ stage amount, %. */
  cov2: number;
  cov3: number;
  /** Stage 2 + Stage 3, % of gross loans — the whole problem book. */
  problemShare: number;
  /** Problem book ₺bn, and the provisions standing against it. */
  problemBn: number;
  provisionsBn: number;
  /** Provisions ÷ problem book, %. */
  problemCov: number;
  /**
   * problemShare ÷ stage3Share. BOTH legs come from the audited filings — never
   * divide by the *published* BDDK ratio, which is a different basis (see the
   * asset-quality rationale) and would inflate the multiple.
   */
  multipleOfPrinted: number;
}

export async function stageLadder(kind: string = DEFAULT_KIND): Promise<StageLadder | null> {
  const rows = await stageAgg(kind);
  const r = rows
    .filter(
      (x) =>
        x.n >= 5 &&
        x.total != null &&
        x.total > 0 &&
        x.s2 != null &&
        x.s3 != null &&
        x.ecl2 != null &&
        x.ecl3 != null,
    )
    .at(-1);
  if (!r) return null;

  const total = r.total!;
  const s2 = r.s2!;
  const s3 = r.s3!;
  const e2 = Math.abs(r.ecl2!);
  const e3 = Math.abs(r.ecl3!);
  const s1 = total - s2 - s3;

  const stage2Share = (s2 / total) * 100;
  const stage3Share = (s3 / total) * 100;
  const problem = s2 + s3;
  const provisions = e2 + e3;

  return {
    period: r.period,
    n: r.n,
    total,
    stage1Share: (s1 / total) * 100,
    stage2Share,
    stage3Share,
    stage2Bn: s2 / TH_TO_BN,
    stage3Bn: s3 / TH_TO_BN,
    ecl2Bn: e2 / TH_TO_BN,
    ecl3Bn: e3 / TH_TO_BN,
    cov2: s2 > 0 ? (e2 / s2) * 100 : 0,
    cov3: s3 > 0 ? (e3 / s3) * 100 : 0,
    problemShare: stage2Share + stage3Share,
    problemBn: problem / TH_TO_BN,
    provisionsBn: provisions / TH_TO_BN,
    problemCov: problem > 0 ? (provisions / problem) * 100 : 0,
    multipleOfPrinted: stage3Share > 0 ? (stage2Share + stage3Share) / stage3Share : 0,
  };
}

export interface RollForwardYear {
  year: string;
  n: number;
  /** All ₺bn. */
  additions: number;
  collections: number;
  writeOffs: number;
  sold: number;
  exits: number;
  /** additions − exits. */
  net: number;
  /** Collections as a share of exits, %. */
  collectionShare: number;
  /** Write-offs + sales as a share of exits, % — the "is the ratio being managed?" test. */
  disposalShare: number;
}

/**
 * The annual NPL roll-forward, split. `nplFormationAnnual` collapses the exits to
 * a single number; the brief needs the split, because the obvious suspicion —
 * that the ratio is held down by write-offs and NPL sales — is FALSE: exits run
 * ~77% collections. Stating that is what stops a reader assuming the wrong
 * mechanism.
 *
 * Q4 rows only: the audited movement tables are YTD flows, so Q4 = the full year.
 */
export async function nplRollForwardAnnual(
  kind: string = DEFAULT_KIND,
): Promise<RollForwardYear[]> {
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

  const out: RollForwardYear[] = [];
  for (const r of rows) {
    if (r.n < 5 || r.additions == null) continue;
    // Reducing flows may be stored signed either way per bank layout — take
    // magnitudes (they only ever reduce the NPL balance). Same rule as above.
    const collections = Math.abs(r.collections ?? 0) / TH_TO_BN;
    const writeOffs = Math.abs(r.write_offs ?? 0) / TH_TO_BN;
    const sold = Math.abs(r.sold ?? 0) / TH_TO_BN;
    const additions = r.additions / TH_TO_BN;
    const exits = collections + writeOffs + sold;
    out.push({
      year: r.period.slice(0, 4),
      n: r.n,
      additions,
      collections,
      writeOffs,
      sold,
      exits,
      net: additions - exits,
      collectionShare: exits > 0 ? (collections / exits) * 100 : 0,
      disposalShare: exits > 0 ? ((writeOffs + sold) / exits) * 100 : 0,
    });
  }
  return out;
}
