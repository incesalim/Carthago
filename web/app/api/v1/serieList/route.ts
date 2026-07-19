/**
 * GET /api/v1/serieList — browse the catalog and find series codes.
 *
 * The discovery half of the API (EVDS names its equivalent the same thing).
 * Codes are opaque by design, so this is how a caller gets from "I want NPLs
 * for participation banks" to a code they can pass to /api/v1/series.
 *
 *   /api/v1/serieList?dataset=T01                 every balance-sheet series
 *   /api/v1/serieList?q=kredi&bankType=10004      search labels, one bank type
 *   /api/v1/serieList?dataset=WLOAN&type=csv      as CSV
 *
 * `dataset`   T01..T17 (monthly) or WLOAN/WSEC/WDEP/WNPL/WOBS/WBAL/WFX (weekly)
 * `bankType`  BDDK bank-type code (see /api/v1/categories)
 * `q`         substring match on the series label, case-insensitive
 * `limit`     default 500, max 5000
 * `offset`    for paging
 * `type`      json (default) | csv
 */
import { cachedAll } from "@/app/lib/db";
import {
  apiDisabled,
  csvResponse,
  disabledResponse,
  errorResponse,
  jsonResponse,
} from "../_shared";

export { OPTIONS } from "../_shared";
export const dynamic = "force-dynamic";

const DEFAULT_LIMIT = 500;
const MAX_LIMIT = 5000;

interface CatalogRow {
  series_code: string;
  dataset: string;
  frequency: string;
  item_name: string;
  bank_type_code: string;
  value_column: string;
  unit: string | null;
  start_date: string | null;
  end_date: string | null;
  obs_count: number | null;
}

export async function GET(request: Request) {
  if (await apiDisabled()) return disabledResponse();

  const p = new URL(request.url).searchParams;

  const where: string[] = [];
  const binds: unknown[] = [];
  const dataset = p.get("dataset");
  if (dataset) {
    where.push("dataset = ?");
    binds.push(dataset.toUpperCase());
  }
  const bankType = p.get("bankType");
  if (bankType) {
    where.push("bank_type_code = ?");
    binds.push(bankType);
  }
  const q = p.get("q");
  if (q) {
    // Turkish labels — SQLite's LIKE is ASCII-case-insensitive only, which is
    // why this is documented as a substring match rather than a real search.
    where.push("item_name LIKE ?");
    binds.push(`%${q}%`);
  }
  const freq = p.get("frequency");
  if (freq) {
    where.push("frequency = ?");
    binds.push(freq.toLowerCase());
  }

  const limitRaw = Number(p.get("limit") ?? DEFAULT_LIMIT);
  if (!Number.isFinite(limitRaw) || limitRaw < 1) {
    return errorResponse("`limit` must be a positive number.");
  }
  const limit = Math.min(Math.floor(limitRaw), MAX_LIMIT);
  const offsetRaw = Number(p.get("offset") ?? 0);
  if (!Number.isFinite(offsetRaw) || offsetRaw < 0) {
    return errorResponse("`offset` must be zero or a positive number.");
  }
  const offset = Math.floor(offsetRaw);

  const clause = where.length ? `WHERE ${where.join(" AND ")}` : "";
  const [rows, counted] = await Promise.all([
    cachedAll<CatalogRow>(
      `SELECT series_code, dataset, frequency, item_name, bank_type_code,
              value_column, unit, start_date, end_date, obs_count
         FROM api_series ${clause}
        ORDER BY series_code LIMIT ? OFFSET ?`,
      [...binds, limit, offset],
    ),
    cachedAll<{ n: number }>(
      `SELECT COUNT(*) AS n FROM api_series ${clause}`,
      binds,
    ),
  ]);
  const total = counted[0]?.n ?? 0;

  if ((p.get("type") ?? "json").toLowerCase() === "csv") {
    const esc = (s: string) =>
      /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    const cols: (keyof CatalogRow)[] = [
      "series_code", "dataset", "frequency", "item_name", "bank_type_code",
      "value_column", "unit", "start_date", "end_date", "obs_count",
    ];
    const csv = [
      cols.join(","),
      ...rows.map((r) => cols.map((c) => esc(String(r[c] ?? ""))).join(",")),
    ].join("\n");
    return csvResponse(csv, "carthago-serielist.csv");
  }

  return jsonResponse({
    meta: { total, count: rows.length, limit, offset },
    series: rows,
  });
}
