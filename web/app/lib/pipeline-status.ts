/**
 * Live status for the pipeline graph's storage/source nodes.
 *
 * Reuses the admin "data health" report (admin-health.ts) for the sources it
 * already covers, and adds row-count / freshness for the rest (BIST, TBB, KAP,
 * TEFAS, the per-table audit groups) via plain COUNT/MAX queries. Every query is
 * wrapped so a missing table (these live Python-side, not in web/migrations)
 * degrades to "no data" instead of breaking the page. All reads go through
 * `cachedAll`'s 12h window — freshness changes at most daily, and the long
 * window keeps KV writes well under the free-tier cap.
 *
 * Returned map is keyed by `PipelineNode.statusKey`.
 */
import { cachedAll } from "./db";
import { getHealthReport, type FreshnessStatus } from "./admin-health";
import { hoursSinceIso } from "./format-time";

export type StatusTone = "positive" | "warning" | "negative" | "info" | "muted";

export interface NodeStatus {
  rowCount: number | null;
  /** Period of the freshest data point (informational). */
  latest: string | null;
  lastRefresh: string | null;
  ageHours: number | null;
  tone: StatusTone;
}

export type PipelineStatusMap = Record<string, NodeStatus>;

const DAY = 24;
const WEEK = 24 * 7;
const MONTH = 24 * 31;
const QUARTER = 24 * 100;
const YEAR = 24 * 400;

function toneFor(status: FreshnessStatus): StatusTone {
  switch (status) {
    case "fresh":
      return "positive";
    case "late":
      return "warning";
    case "stale":
      return "negative";
    default:
      return "muted";
  }
}

/** Same thresholds as admin-health's (private) statusFor. */
function freshnessFor(ageHours: number | null, cadenceHours: number): FreshnessStatus {
  if (ageHours == null) return "unknown";
  if (ageHours <= cadenceHours * 1.5) return "fresh";
  if (ageHours <= cadenceHours * 3) return "late";
  return "stale";
}

interface AggRow {
  n: number | null;
  last_refresh: string | null;
  latest: string | null;
}

async function aggQuery(sql: string): Promise<AggRow | null> {
  try {
    const rows = await cachedAll<AggRow>(sql);
    return rows[0] ?? null;
  } catch {
    return null;
  }
}

async function countQuery(table: string): Promise<number | null> {
  const row = await aggQuery(`SELECT COUNT(*) AS n, NULL AS last_refresh, NULL AS latest FROM ${table}`);
  return row ? Number(row.n ?? 0) : null;
}

/** Sources not covered by admin-health: each has a refresh column + cadence. */
const EXT_SOURCES: { key: string; sql: string; cadenceHours: number }[] = [
  {
    key: "bist",
    sql: "SELECT COUNT(*) AS n, MAX(downloaded_at) AS last_refresh, MAX(period_date) AS latest FROM bist_prices",
    cadenceHours: DAY,
  },
  {
    key: "tbb_digital",
    sql: "SELECT COUNT(*) AS n, MAX(downloaded_at) AS last_refresh, MAX(period) AS latest FROM tbb_digital_stats",
    cadenceHours: QUARTER,
  },
  {
    key: "tbb_acq",
    sql: "SELECT COUNT(*) AS n, MAX(downloaded_at) AS last_refresh, MAX(period) AS latest FROM tbb_acquisition_stats",
    cadenceHours: MONTH,
  },
  {
    key: "tkbb_digital",
    sql: "SELECT COUNT(*) AS n, MAX(downloaded_at) AS last_refresh, MAX(period) AS latest FROM tkbb_digital_stats",
    cadenceHours: QUARTER,
  },
  {
    key: "tkbb_acq",
    sql: "SELECT COUNT(*) AS n, MAX(downloaded_at) AS last_refresh, MAX(period) AS latest FROM tkbb_acquisition_stats",
    cadenceHours: MONTH,
  },
  {
    key: "kap",
    sql: "SELECT COUNT(*) AS n, MAX(downloaded_at) AS last_refresh, MAX(as_of) AS latest FROM kap_ownership",
    cadenceHours: WEEK,
  },
  {
    key: "tefas",
    sql: "SELECT COUNT(*) AS n, MAX(downloaded_at) AS last_refresh, MAX(date) AS latest FROM tefas_manager_daily",
    cadenceHours: DAY,
  },
  {
    key: "faaliyet",
    sql: "SELECT COUNT(*) AS n, MAX(extracted_at) AS last_refresh, MAX(fiscal_year) AS latest FROM faaliyet_franchise",
    cadenceHours: YEAR,
  },
  {
    key: "advertised_rates",
    sql: "SELECT COUNT(*) AS n, MAX(downloaded_at) AS last_refresh, MAX(snapshot_date) AS latest FROM bank_advertised_rates",
    cadenceHours: WEEK,
  },
];

/** Audit D1 groups — extraction is admin-triggered, so health = "has rows". */
const AUDIT_TABLES: { key: string; table: string }[] = [
  { key: "audit:balance_sheet", table: "bank_audit_balance_sheet" },
  { key: "audit:stages", table: "bank_audit_stages" },
  { key: "audit:capital", table: "bank_audit_capital" },
  { key: "audit:coverage", table: "bank_audit_coverage" },
];

export async function getPipelineStatus(): Promise<PipelineStatusMap> {
  const map: PipelineStatusMap = {};

  try {
    const { sources } = await getHealthReport();
    for (const s of sources) {
      map[s.key] = {
        rowCount: s.rowCount,
        latest: s.latestPeriod,
        lastRefresh: s.lastRefresh,
        ageHours: s.ageHours,
        tone: toneFor(s.status),
      };
    }
  } catch {
    // health report unavailable — extension queries below still populate.
  }

  await Promise.all([
    ...EXT_SOURCES.map(async (e) => {
      const row = await aggQuery(e.sql);
      if (!row) return;
      const ageHours = hoursSinceIso(row.last_refresh);
      map[e.key] = {
        rowCount: row.n == null ? null : Number(row.n),
        latest: row.latest,
        lastRefresh: row.last_refresh,
        ageHours,
        tone: toneFor(freshnessFor(ageHours, e.cadenceHours)),
      };
    }),
    ...AUDIT_TABLES.map(async (a) => {
      const n = await countQuery(a.table);
      if (n == null) return;
      map[a.key] = {
        rowCount: n,
        latest: null,
        lastRefresh: null,
        ageHours: null,
        tone: n > 0 ? "positive" : "muted",
      };
    }),
  ]);

  return map;
}
