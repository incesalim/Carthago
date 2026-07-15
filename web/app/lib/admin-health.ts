/**
 * Admin health — read-only D1 queries that answer "is the data fresh and did
 * the scrapers work?". Each source reports its latest data period, when it was
 * last ingested, a row count, and a freshness status derived from the expected
 * refresh cadence. (Audit extraction / structural-validation detail lives in the
 * coverage matrix — see app/lib/coverage.ts — not here.)
 *
 * Every query is wrapped so a missing table/column (e.g. evds_series isn't in
 * web/migrations) degrades to "unknown" instead of breaking the page.
 */
import { getDB } from "./db";
import { nextMonthlyBulletinDue } from "./ahead";

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

export interface HealthReport {
  sources: SourceHealth[];
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
const MONTH = 24 * 31;
/** Days past the expected release before a missing month reads "stale". */
const MONTHLY_OVERDUE_GRACE_DAYS = 14;

/**
 * The BDDK monthly bulletin publishes ~once a month with a 4–11 week lag, and the
 * non-destructive upsert never rewrites an unchanged month — so `downloaded_at`
 * freezes the day a month lands, and an age-vs-cadence check reads "stale" for
 * the weeks BETWEEN releases even though we hold the latest data that exists.
 *
 * So freshness here is schedule-aware, not age-based: while we hold the latest
 * month due by now (per nextMonthlyBulletinDue), we're fresh; only once the NEXT
 * month is genuinely overdue does it go late → stale.
 */
function monthlyStatus(latestPeriod: string | null): FreshnessStatus {
  if (!latestPeriod) return "unknown";
  const due = nextMonthlyBulletinDue(latestPeriod);
  if (!due) return "unknown";
  const overdueDays = (Date.now() - Date.parse(`${due.date}T00:00:00Z`)) / 86_400_000;
  if (overdueDays < 0) return "fresh"; // the next month isn't due yet
  if (overdueDays <= MONTHLY_OVERDUE_GRACE_DAYS) return "late";
  return "stale";
}

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
  const latestPeriod = period
    ? `${period.year}-${String(period.month).padStart(2, "0")}`
    : null;
  const due = latestPeriod ? nextMonthlyBulletinDue(latestPeriod) : null;
  const status = monthlyStatus(latestPeriod);
  const noteParts: string[] = [];
  if (due && status === "fresh") noteParts.push(`next (${due.record}) due ~${due.date}`);
  if (fails && fails.n > 0) noteParts.push(`${fails.n} non-success rows in download_log`);
  return {
    key: "monthly",
    label: "Monthly bulletin",
    latestPeriod,
    lastRefresh: agg?.last_refresh ?? null,
    rowCount: agg?.n ?? null,
    ageHours: hoursSince(agg?.last_refresh),
    cadenceHours: MONTH,
    status,
    note: noteParts.length ? noteParts.join(" · ") : undefined,
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
  const agg = await safeFirst<{
    latest: string | null;
    last_refresh: string | null;
    n: number;
    failed: number;
  }>(
    db,
    "SELECT MAX(period) AS latest, MAX(extracted_at) AS last_refresh, COUNT(*) AS n, " +
      "SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) AS failed FROM bank_audit_extractions",
  );
  // Extraction is admin-triggered (no schedule), so audit freshness isn't
  // time-based — health = whether every extracted partition succeeded.
  // Acquisition (acquire-audit.yml, weekly) keeps new PDFs flowing; the coverage
  // matrix is where "what's missing" is surfaced and acted on.
  const n = agg?.n ?? 0;
  const status: FreshnessStatus =
    n === 0 ? "unknown" : (agg?.failed ?? 0) > 0 ? "late" : "fresh";
  return {
    key: "audit",
    label: "Audit reports",
    latestPeriod: agg?.latest ?? null,
    lastRefresh: agg?.last_refresh ?? null,
    rowCount: n,
    ageHours: hoursSince(agg?.last_refresh),
    cadenceHours: WEEK,
    status,
  };
}

export async function getHealthReport(): Promise<HealthReport> {
  const db = await getDB();
  const [monthly, weekly, evds, audit, news, regulation] = await Promise.all([
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
  ]);

  return { sources: [monthly, weekly, evds, audit, news, regulation] };
}
