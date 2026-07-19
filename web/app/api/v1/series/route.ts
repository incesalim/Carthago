/**
 * GET /api/v1/series — observations for one or more series.
 *
 * The API's primary endpoint, shaped after EVDS so anyone who has used TCMB's
 * service can read it without documentation:
 *
 *   /api/v1/series?series=BDDK.T01.I005.10001.TOT-BDDK.T02.I001.10001.TL
 *                 &startDate=01-01-2024&endDate=31-12-2025&type=json
 *
 * `series`     dash-joined codes (max 20). Our codes contain no dashes.
 * `startDate`  DD-MM-YYYY (EVDS style) or YYYY-MM-DD. Optional.
 * `endDate`    same. Optional — omit both for the full history.
 * `type`       json (default) | csv
 *
 * Unknown codes are reported in `meta.unknown` rather than failing the request:
 * a caller pulling 20 series shouldn't lose 19 of them because one was retired.
 */
import {
  MAX_SERIES_PER_REQUEST,
  fetchObservations,
  fetchSeriesMeta,
  isValidCodeShape,
  parseDate,
  parseSeriesParam,
  toCsv,
} from "@/app/lib/api-series";
import {
  apiDisabled,
  csvResponse,
  disabledResponse,
  errorResponse,
  jsonResponse,
} from "../_shared";

export { OPTIONS } from "../_shared";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  if (await apiDisabled()) return disabledResponse();

  const url = new URL(request.url);
  const raw = url.searchParams.get("series");
  if (!raw) {
    return errorResponse(
      "Missing `series`. Example: " +
        "/api/v1/series?series=BDDK.T01.I005.10001.TOT&startDate=01-01-2024",
    );
  }

  const codes = parseSeriesParam(raw);
  if (!codes.length) return errorResponse("No series codes found in `series`.");
  if (codes.length > MAX_SERIES_PER_REQUEST) {
    return errorResponse(
      `Too many series: ${codes.length}. The limit is ${MAX_SERIES_PER_REQUEST} per request.`,
    );
  }

  // Reject malformed codes up front so a typo gets a clear error rather than
  // silently landing in `unknown` alongside genuinely retired series.
  const malformed = codes.filter((c) => !isValidCodeShape(c));
  if (malformed.length) {
    return errorResponse(
      `Malformed series code(s): ${malformed.slice(0, 5).join(", ")}. ` +
        "Expected BDDK.<DATASET>.<ITEM>.<BANKTYPE>.<COLUMN>, " +
        "e.g. BDDK.T01.I005.10001.TOT. Browse /api/v1/serieList to find codes.",
    );
  }

  const startRaw = url.searchParams.get("startDate");
  const endRaw = url.searchParams.get("endDate");
  const from = parseDate(startRaw);
  const to = parseDate(endRaw);
  if (startRaw && !from) {
    return errorResponse(`Unparseable startDate "${startRaw}". Use DD-MM-YYYY or YYYY-MM-DD.`);
  }
  if (endRaw && !to) {
    return errorResponse(`Unparseable endDate "${endRaw}". Use DD-MM-YYYY or YYYY-MM-DD.`);
  }
  if (from && to && from > to) {
    return errorResponse("startDate is after endDate.");
  }

  const metas = await fetchSeriesMeta(codes);
  const found = new Set(metas.map((m) => m.series_code));
  const unknown = codes.filter((c) => !found.has(c));
  if (!metas.length) {
    return errorResponse(
      `None of the requested series exist: ${unknown.slice(0, 5).join(", ")}. ` +
        "Browse /api/v1/serieList to find valid codes.",
      404,
    );
  }

  const observations = await Promise.all(
    metas.map((m) => fetchObservations(m, from, to)),
  );

  if ((url.searchParams.get("type") ?? "json").toLowerCase() === "csv") {
    return csvResponse(toCsv(metas, observations), "carthago-series.csv");
  }

  return jsonResponse({
    meta: {
      source: "BDDK (Banking Regulation and Supervision Agency of Türkiye)",
      publisher: "Carthago — https://carthago.app",
      start_date: from,
      end_date: to,
      series_count: metas.length,
      unknown,
    },
    series: metas.map((m, i) => ({
      series_code: m.series_code,
      name: m.item_name,
      dataset: m.dataset,
      frequency: m.frequency,
      bank_type_code: m.bank_type_code,
      unit: m.unit,
      observations: observations[i],
    })),
  });
}
