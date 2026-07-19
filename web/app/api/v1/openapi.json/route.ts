/**
 * GET /api/v1/openapi.json — OpenAPI 3.1 description of the public API.
 *
 * Exists because an LLM agent generally CANNOT call this API from prose docs
 * alone. ChatGPT's browser, in particular, will fetch a URL a user pasted but
 * refuses to construct new parameterised sub-paths itself — so it can read
 * /api/v1, correctly learn that T01 is the balance sheet, and then be unable to
 * act on it. An OpenAPI schema is the mechanism that removes the guesswork:
 * registered as a ChatGPT Action / Custom GPT (or fed to Postman, Swagger UI, or
 * a client generator) it turns each endpoint into a typed call the model may
 * invoke with parameters of its choosing.
 *
 * The `description` strings are therefore load-bearing, not decoration — they
 * are the only place a model learns that codes must not be invented, that units
 * vary per series, and that bank-type groups overlap. Keep them in sync with
 * docs/API_MANUAL.md §10.
 */
import { apiDisabled, disabledResponse, jsonResponse } from "../_shared";

export { OPTIONS } from "../_shared";
export const dynamic = "force-dynamic";

const DESCRIPTION = `Turkish banking-sector statistics published by BDDK
(Türkiye's banking regulator), served as ~19,800 time series. Free, public, no
authentication.

CRITICAL RULES FOR CALLERS:
- NEVER invent a series code. Discover codes with /api/v1/serieList, or reuse a
  code you have already seen. A guessed code will not resolve.
- Units differ per series. Always read the "unit" field; never assume. In
  "million TL", 51760765 means 51.76 trillion TL.
- Monthly observations are dated to the period END (e.g. 2026-05-31) and are
  STOCKS — a balance on that date, not a flow. The exception is dataset T02
  (income statement), which is cumulative within a calendar year.
- A null value means BDDK filed no figure for that period. It does NOT mean zero.
- Bank-type groups OVERLAP; they are different cuts of the same sector, not
  disjoint buckets. 10002+10003+10004 covers the whole sector by licence, and
  10005+10006+10007 covers it again by ownership. NEVER sum across cuts.
- Data is sector and bank-group level only. Individual banks are not available.`;

export async function GET() {
  if (await apiDisabled()) return disabledResponse();

  return jsonResponse({
    openapi: "3.1.0",
    info: {
      title: "Carthago Data API",
      description: DESCRIPTION,
      version: "1.0.0",
      contact: { url: "https://carthago.app" },
      license: {
        name: "Source data published publicly by BDDK",
        url: "https://www.bddk.org.tr/",
      },
    },
    servers: [{ url: "https://carthago.app", description: "Production" }],
    paths: {
      "/api/v1/series": {
        get: {
          operationId: "getSeries",
          summary: "Fetch observations for one or more series",
          description:
            "Returns the time series for up to 20 series codes. Use " +
            "type=csv for a wide table (one column per series) suitable for " +
            "spreadsheets or pandas.",
          parameters: [
            {
              name: "series",
              in: "query",
              required: true,
              description:
                "One or more series codes joined by '-' (max 20). Codes look " +
                "like BDDK.T01.I026.10001.TOT and contain no dashes, so the " +
                "separator is unambiguous. Do not invent codes.",
              schema: { type: "string" },
              example:
                "BDDK.T01.I026.10001.TOT-BDDK.T01.I010.10001.TOT",
            },
            {
              name: "startDate",
              in: "query",
              required: false,
              description: "Inclusive start, DD-MM-YYYY or YYYY-MM-DD.",
              schema: { type: "string" },
              example: "01-01-2024",
            },
            {
              name: "endDate",
              in: "query",
              required: false,
              description:
                "Inclusive end, DD-MM-YYYY or YYYY-MM-DD. Omit both dates for " +
                "the full available history.",
              schema: { type: "string" },
              example: "31-12-2025",
            },
            {
              name: "type",
              in: "query",
              required: false,
              description: "Response format.",
              schema: { type: "string", enum: ["json", "csv"], default: "json" },
            },
          ],
          responses: {
            "200": {
              description:
                "Observations. Codes that do not exist are listed in " +
                "meta.unknown rather than failing the whole request.",
              content: {
                "application/json": {
                  schema: { $ref: "#/components/schemas/SeriesResponse" },
                },
                "text/csv": { schema: { type: "string" } },
              },
            },
            "400": { description: "Invalid parameter." },
            "404": { description: "None of the requested codes exist." },
          },
        },
      },
      "/api/v1/serieList": {
        get: {
          operationId: "searchSeries",
          summary: "Search or browse the catalog to find series codes",
          description:
            "The discovery endpoint. Call this FIRST whenever you do not " +
            "already have a series code. Labels are searchable in Turkish or " +
            "English. Use limit=25000&type=csv to export the entire catalog.",
          parameters: [
            {
              name: "q",
              in: "query",
              required: false,
              description:
                "Substring of the series label, Turkish or English " +
                "(e.g. 'loans', 'deposits', 'kredi', 'mevduat'). Matching is " +
                "plain substring and ASCII-case-insensitive only, so prefer a " +
                "short lowercase stem. Broad terms match thousands of series — " +
                "combine with dataset or bankType to narrow.",
              schema: { type: "string" },
              example: "capital adequacy",
            },
            {
              name: "dataset",
              in: "query",
              required: false,
              description:
                "Restrict to one dataset. T01 balance sheet, T02 income " +
                "statement, T03 loans, T04 consumer loans, T05 sectoral loans, " +
                "T06 SME loans, T07 syndication, T08 securities, T09 deposits " +
                "by type, T10 deposits by maturity, T11 liquidity, T12 capital " +
                "adequacy, T13 FX position, T14 off-balance sheet, T15 ratios, " +
                "T16 other information, T17 foreign branch ratios. Weekly: " +
                "WLOAN, WSEC, WDEP, WNPL, WOBS, WBAL, WFX.",
              schema: { type: "string" },
              example: "T01",
            },
            {
              name: "bankType",
              in: "query",
              required: false,
              description:
                "BDDK bank-group code. 10001 entire sector, 10002 deposit " +
                "banks, 10003 participation banks, 10004 development & " +
                "investment banks, 10005 local private, 10006 state, 10007 " +
                "foreign, 10008/10009/10010 deposit banks split by ownership. " +
                "These groups OVERLAP — never sum across them.",
              schema: { type: "string" },
              example: "10001",
            },
            {
              name: "frequency",
              in: "query",
              required: false,
              schema: { type: "string", enum: ["monthly", "weekly"] },
            },
            {
              name: "limit",
              in: "query",
              required: false,
              description: "Max rows (default 500, max 25000).",
              schema: { type: "integer", default: 500, maximum: 25000 },
            },
            {
              name: "offset",
              in: "query",
              required: false,
              schema: { type: "integer", default: 0 },
            },
            {
              name: "type",
              in: "query",
              required: false,
              schema: { type: "string", enum: ["json", "csv"], default: "json" },
            },
          ],
          responses: {
            "200": {
              description: "Matching catalog entries.",
              content: {
                "application/json": {
                  schema: { $ref: "#/components/schemas/SerieListResponse" },
                },
                "text/csv": { schema: { type: "string" } },
              },
            },
          },
        },
      },
      "/api/v1/categories": {
        get: {
          operationId: "getCategories",
          summary: "List datasets and bank-type codes with their meanings",
          description:
            "The vocabulary needed to read or vary a series code: every " +
            "dataset with BDDK's own table name and coverage, and every " +
            "bank-group code with its English and Turkish name.",
          responses: { "200": { description: "Datasets and bank types." } },
        },
      },
      "/api/v1": {
        get: {
          operationId: "getApiIndex",
          summary: "Self-describing index: coverage, conventions, examples",
          responses: { "200": { description: "API metadata." } },
        },
      },
    },
    components: {
      schemas: {
        SeriesResponse: {
          type: "object",
          properties: {
            meta: {
              type: "object",
              properties: {
                source: { type: "string" },
                series_count: { type: "integer" },
                unknown: {
                  type: "array",
                  items: { type: "string" },
                  description: "Requested codes that do not exist.",
                },
              },
            },
            series: {
              type: "array",
              items: {
                type: "object",
                properties: {
                  series_code: { type: "string" },
                  name: {
                    type: "string",
                    description: "Label as filed by BDDK, in Turkish.",
                  },
                  name_en: {
                    type: ["string", "null"],
                    description:
                      "BDDK's own English label. Null where BDDK publishes " +
                      "none (all weekly series); fall back to `name`.",
                  },
                  dataset: { type: "string" },
                  frequency: { type: "string", enum: ["monthly", "weekly"] },
                  bank_type_code: { type: "string" },
                  unit: {
                    type: ["string", "null"],
                    description:
                      "e.g. 'million TL', 'thousand TL', 'percentage', " +
                      "'count'. Varies per series — always read it.",
                  },
                  observations: {
                    type: "array",
                    items: {
                      type: "object",
                      properties: {
                        date: {
                          type: "string",
                          description:
                            "YYYY-MM-DD. Monthly values are dated to the " +
                            "period END.",
                        },
                        value: {
                          type: ["number", "null"],
                          description:
                            "Null means BDDK filed no figure. Not zero.",
                        },
                      },
                    },
                  },
                },
              },
            },
          },
        },
        SerieListResponse: {
          type: "object",
          properties: {
            meta: {
              type: "object",
              properties: {
                total: { type: "integer" },
                count: { type: "integer" },
                limit: { type: "integer" },
                offset: { type: "integer" },
              },
            },
            series: {
              type: "array",
              items: {
                type: "object",
                properties: {
                  series_code: { type: "string" },
                  dataset: { type: "string" },
                  frequency: { type: "string" },
                  item_name: { type: "string", description: "Turkish label." },
                  item_name_en: {
                    type: ["string", "null"],
                    description: "BDDK's English label, or null.",
                  },
                  bank_type_code: { type: "string" },
                  unit: { type: ["string", "null"] },
                  start_date: { type: ["string", "null"] },
                  end_date: { type: ["string", "null"] },
                  obs_count: { type: ["integer", "null"] },
                },
              },
            },
          },
        },
      },
    },
  });
}
