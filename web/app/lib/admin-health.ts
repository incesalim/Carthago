/**
 * Admin health — read-only D1 queries that answer "is the data fresh and did
 * the scrapers work?". Each source reports its latest data period, when it was
 * last ingested, a row count, and a freshness status derived from the expected
 * refresh cadence. Plus audit-extraction success/failure detail.
 *
 * Every query is wrapped so a missing table/column (e.g. evds_series isn't in
 * web/migrations) degrades to "unknown" instead of breaking the page.
 */
import { getDB } from "./db";

export type FreshnessStatus = "fresh" | "late" | "stale" | "unknown";

export interface SourceHealth {
  key: string;
  label: string;
  /** Human period of the freshest data point (informational). */
  latestPeriod: string | null;
  /** ISO-ish timestamp of the most recent ingest. */
  lastRefresh: string | null;
  rowCount: number | null;
  /** Hours since lastRefresh. */
  ageHours: number | null;
  /** Expected refresh cadence in hours (drives the status colour). */
  cadenceHours: number;
  status: FreshnessStatus;
  note?: string;
}

export interface ExtractionFailure {
  bank_ticker: string;
  period: string;
  kind: string;
  note: string | null;
  extracted_at: string | null;
}

export interface ExtractionHealth {
  total: number;
  success: number;
  failed: number;
  failures: ExtractionFailure[];
}

export interface ValidationBankHealth {
  bank_ticker: string;
  partitions: number;
  failed_partitions: number;
  checks_failed: number;
}

export interface ValidationHealth {
  banks: ValidationBankHealth[];
  totalFailedPartitions: number;
}

export interface HealthReport {
  sources: SourceHealth[];
  extraction: ExtractionHealth;
  validation: ValidationHealth;
}

type DB = Awaited<ReturnType<typeof getDB>>;

/** Run a single-row query, returning null on any error (missing table/column). */
async function safeFirst<T>(db: DB, sql: string): Promise<T | null> {
  try {
    return await db.prepare(sql).first<T>();
  } catch {
    return null;
  }
}

/** Parse a D1 timestamp ("YYYY-MM-DD HH:MM:SS" / ISO) as UTC → hours since now. */
function hoursSince(ts: string | null | undefined): number | null {
  if (!ts) return null;
  const norm = ts.includes("T") ? ts : ts.replace(" ", "T");
  const ms = Date.parse(norm.endsWith("Z") || /[+-]\d\d:?\d\d$/.test(norm) ? norm : `${norm}Z`);
  if (Number.isNaN(ms)) return null;
  return (Date.now() - ms) / 3_600_000;
}

function statusFor(ageHours: number | null, cadenceHours: number): FreshnessStatus {
  if (ageHours == null) return "unknown";
  if (ageHours <= cadenceHours * 1.5) return "fresh";
  if (ageHours <= cadenceHours * 3) return "late";
  return "stale";
}

const DAY = 24;
const WEEK = 24 * 7;

async function monthlySource(db: DB): Promise<SourceHealth> {
  const agg = await safeFirst<{ last_refresh: string | null; n: number }>(
    db,
    "SELECT MAX(downloaded_at) AS last_refresh, COUNT(*) AS n FROM balance_sheet",
  );
  const period = await safeFirst<{ year: number; month: number }>(
    db,
    "SELECT year, month FROM balance_sheet ORDER BY year DESC, month DESC LIMIT 1",
  );
  const fails = await safeFirst<{ n: number }>(
    db,
    "SELECT COUNT(*) AS n FROM download_log WHERE status IS NOT NULL AND status <> 'success'",
  );
  const ageHours = hoursSince(agg?.last_refresh);
  return {
    key: "monthly",
    label: "Monthly bulletin",
    latestPeriod: period ? `${period.year}-${String(period.month).padStart(2, "0")}` : null,
    lastRefresh: agg?.last_refresh ?? null,
    rowCount: agg?.n ?? null,
    ageHours,
    cadenceHours: WEEK,
    status: statusFor(ageHours, WEEK),
    note: fails && fails.n > 0 ? `${fails.n} non-success rows in download_log` : undefined,
  };
}

async function simpleSource(
  db: DB,
  opts: {
    key: string;
    label: string;
    table: string;
    periodCol: string;
    refreshCol: string;
    cadenceHours: number;
  },
): Promise<SourceHealth> {
  const { key, label, table, periodCol, refreshCol, cadenceHours } = opts;
  const agg = await safeFirst<{ latest: string | null; last_refresh: string | null; n: number }>(
    db,
    `SELECT MAX(${periodCol}) AS latest, MAX(${refreshCol}) AS last_refresh, COUNT(*) AS n FROM ${table}`,
  );
  // EVDS-style tables may lack a refresh column; fall back to the period.
  const lastRefresh = agg?.last_refresh ?? agg?.latest ?? null;
  const ageHours = hoursSince(lastRefresh);
  return {
    key,
    label,
    latestPeriod: agg?.latest ?? null,
    lastRefresh,
    rowCount: agg?.n ?? null,
    ageHours,
    cadenceHours,
    status: statusFor(ageHours, cadenceHours),
  };
}

async function evdsSource(db: DB): Promise<SourceHealth> {
  // evds_series isn't in web/migrations; query period_date only (no guaranteed
  // refresh column) and fall back gracefully.
  const withRefresh = await safeFirst<{ latest: string | null; last_refresh: string | null; n: number }>(
    db,
    "SELECT MAX(period_date) AS latest, MAX(downloaded_at) AS last_refresh, COUNT(*) AS n FROM evds_series",
  );
  const agg =
    withRefresh ??
    (await safeFirst<{ latest: string | null; n: number }>(
      db,
      "SELECT MAX(period_date) AS latest, COUNT(*) AS n FROM evds_series",
    ));
  const latest = agg?.latest ?? null;
  const lastRefresh = (agg as { last_refresh?: string | null })?.last_refresh ?? latest;
  const ageHours = hoursSince(lastRefresh);
  return {
    key: "evds",
    label: "EVDS (rates / FX)",
    latestPeriod: latest,
    lastRefresh,
    rowCount: agg?.n ?? null,
    ageHours,
    cadenceHours: DAY,
    status: statusFor(ageHours, DAY),
  };
}

async function auditSource(db: DB): Promise<SourceHealth> {
  const agg = await safeFirst<{ latest: string | null; last_refresh: string | null; n: number }>(
    db,
    "SELECT MAX(period) AS latest, MAX(extracted_at) AS last_refresh, COUNT(*) AS n FROM bank_audit_extractions",
  );
  const ageHours = hoursSince(agg?.last_refresh);
  return {
    key: "audit",
    label: "Audit reports",
    latestPeriod: agg?.latest ?? null,
    lastRefresh: agg?.last_refresh ?? null,
    rowCount: agg?.n ?? null,
    ageHours,
    cadenceHours: WEEK,
    status: statusFor(ageHours, WEEK),
  };
}

async function extractionHealth(db: DB): Promise<ExtractionHealth> {
  const counts = await safeFirst<{ total: number; success: number; failed: number }>(
    db,
    "SELECT COUNT(*) AS total, " +
      "SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) AS success, " +
      "SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) AS failed " +
      "FROM bank_audit_extractions",
  );
  let failures: ExtractionFailure[] = [];
  try {
    const { results } = await db
      .prepare(
        "SELECT bank_ticker, period, kind, note, extracted_at " +
          "FROM bank_audit_extractions WHERE success=0 " +
          "ORDER BY extracted_at DESC LIMIT 50",
      )
      .all<ExtractionFailure>();
    failures = results ?? [];
  } catch {
    failures = [];
  }
  return {
    total: counts?.total ?? 0,
    success: counts?.success ?? 0,
    failed: counts?.failed ?? 0,
    failures,
  };
}

async function validationHealth(db: DB): Promise<ValidationHealth> {
  // bank_audit_validation lands with the Phase-3 backfill (rework plan) —
  // degrade to an empty section until then.
  try {
    const { results } = await db
      .prepare(
        "SELECT bank_ticker, " +
          "COUNT(DISTINCT period || '|' || kind) AS partitions, " +
          "COUNT(DISTINCT CASE WHEN checks_failed > 0 THEN period || '|' || kind END) AS failed_partitions, " +
          "SUM(checks_failed) AS checks_failed " +
          "FROM bank_audit_validation GROUP BY bank_ticker " +
          "ORDER BY checks_failed DESC, bank_ticker",
      )
      .all<ValidationBankHealth>();
    const banks = results ?? [];
    return {
      banks,
      totalFailedPartitions: banks.reduce(
        (s: number, b: ValidationBankHealth) => s + (b.failed_partitions ?? 0), 0),
    };
  } catch {
    return { banks: [], totalFailedPartitions: 0 };
  }
}


export async function getHealthReport(): Promise<HealthReport> {
  const db = await getDB();
  const [monthly, weekly, evds, audit, news, regulation, extraction] = await Promise.all([
    monthlySource(db),
    simpleSource(db, {
      key: "weekly",
      label: "Weekly bulletin",
      table: "weekly_series",
      periodCol: "period_date",
      refreshCol: "downloaded_at",
      cadenceHours: WEEK,
    }),
    evdsSource(db),
    auditSource(db),
    simpleSource(db, {
      key: "news",
      label: "News",
      table: "news_items",
      periodCol: "published_at",
      refreshCol: "fetched_at",
      cadenceHours: DAY,
    }),
    simpleSource(db, {
      key: "regulation",
      label: "Regulation briefings",
      table: "regulation_briefings",
      periodCol: "generated_at",
      refreshCol: "fetched_at",
      cadenceHours: WEEK,
    }),
    extractionHealth(db),
  ]);
  const validation = await validationHealth(db);

  return { sources: [monthly, weekly, evds, audit, news, regulation], extraction, validation };
}
