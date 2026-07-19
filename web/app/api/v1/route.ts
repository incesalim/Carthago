/**
 * GET /api/v1 — self-describing index.
 *
 * Someone who finds this API will land here first, with no documentation and no
 * idea what a series code looks like. So this returns the whole contract: the
 * endpoints, the code grammar, worked examples they can paste into a browser,
 * and live coverage numbers read from the catalog.
 */
import { allDirect } from "@/app/lib/db";
import { MAX_SERIES_PER_REQUEST } from "@/app/lib/api-series";
import { apiDisabled, disabledResponse, jsonResponse } from "./_shared";

export { OPTIONS } from "./_shared";
export const dynamic = "force-dynamic";

export async function GET() {
  if (await apiDisabled()) return disabledResponse();

  const [summary] = await allDirect<{
    series_count: number;
    dataset_count: number;
    start_date: string | null;
    end_date: string | null;
  }>(
    `SELECT COUNT(*) AS series_count,
            COUNT(DISTINCT dataset) AS dataset_count,
            MIN(start_date) AS start_date,
            MAX(end_date) AS end_date
       FROM api_series`,
  );

  return jsonResponse({
    name: "Carthago Data API",
    version: "v1",
    description:
      "Turkish banking-sector statistics published by BDDK — monthly tables 1–17 " +
      "and the weekly bulletin — served as time series.",
    source: "BDDK (Banking Regulation and Supervision Agency of Türkiye)",
    publisher: "Carthago — https://carthago.app",
    licence:
      "BDDK publishes this data publicly. Attribution to BDDK as the source, " +
      "and to Carthago as the distributor, is appreciated.",
    coverage: {
      series: summary?.series_count ?? 0,
      datasets: summary?.dataset_count ?? 0,
      earliest: summary?.start_date ?? null,
      latest: summary?.end_date ?? null,
    },
    endpoints: {
      "GET /api/v1/series":
        "Observations for up to " + MAX_SERIES_PER_REQUEST +
        " series. Params: series (dash-joined codes), startDate, endDate, type=json|csv",
      "GET /api/v1/serieList":
        "Browse/search the catalog. Params: dataset, bankType, frequency, q, limit, offset, type=json|csv",
      "GET /api/v1/categories":
        "Dataset tokens and bank-type codes, with coverage counts",
      "GET /api/v1/openapi.json":
        "OpenAPI 3.1 schema — register as a ChatGPT Action / Custom GPT, or feed to Postman, Swagger UI or a client generator",
    },
    series_code_format: {
      pattern: "BDDK.<DATASET>.<ITEM>.<BANKTYPE>.<COLUMN>",
      dataset:
        "T01–T17 = BDDK's own monthly table numbers; " +
        "WLOAN/WSEC/WDEP/WNPL/WOBS/WBAL/WFX = weekly bulletin sections",
      item: "Catalog item token — find it via /api/v1/serieList, don't construct it",
      banktype: "BDDK bank-type code, e.g. 10001 = whole sector. See /api/v1/categories",
      column:
        "Value leg: TL, FX, TOT everywhere; plus per-dataset tokens " +
        "(maturity buckets, deposit brackets, VAL for ratios)",
    },
    authentication:
      "None — no API key or signup required. The data is public.",
    conventions: {
      dates:
        "Request dates as DD-MM-YYYY (EVDS style) or YYYY-MM-DD. Responses are always YYYY-MM-DD.",
      monthly_dating:
        "Monthly observations are dated to the period END (2026-04-30), because a BDDK monthly figure is a month-end stock.",
      units: "Per series — read `unit` from /api/v1/serieList. Never assume.",
      missing:
        "A null observation means BDDK filed no figure for that period. It does not mean zero.",
    },
    examples: {
      "One balance-sheet line, whole sector, full history":
        "https://carthago.app/api/v1/series?series=BDDK.T01.I001.10001.TOT",
      "Two series over a window, as CSV":
        "https://carthago.app/api/v1/series?series=BDDK.T01.I001.10001.TOT-BDDK.T02.I001.10001.TOT&startDate=01-01-2024&endDate=31-12-2025&type=csv",
      "Find loan series for participation banks":
        "https://carthago.app/api/v1/serieList?dataset=T03&bankType=10004",
      "Search labels": "https://carthago.app/api/v1/serieList?q=kredi&limit=20",
    },
    openapi: "https://carthago.app/api/v1/openapi.json",
    documentation: "https://github.com/incesalim/Carthago/blob/master/docs/API_MANUAL.md",
  });
}
