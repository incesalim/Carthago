/**
 * Analyst V2 — typed, read-only research tools.
 *
 * The agent never writes SQL. Each tool validates its arguments against the
 * statement registry's allowlists, runs parameter-bound reads through the
 * same Queryable seam as V1, attaches the partitions' validation status and
 * missing-data warnings, and logs an EvidenceRecord with a stable id. The
 * tool result IS the evidence — findings cite ids, the verifier resolves
 * them, and nothing outside the log exists.
 */
import type { Queryable } from "../data";
import { buildPeerContext } from "../peers";
import { canonical, evidenceId, EvidenceLog, type EvidenceRecord, type SnapshotId } from "./evidence";
import { PEER_METRICS, RECONCILIATIONS, STATEMENTS, type ReconciliationName } from "./registry";

/* ------------------------------------------------------------------ types */

export interface FilingTextStore {
  bank: string;
  period: string;
  kind: string;
  pages: { page: number; text: string }[];
}

export interface ToolContext {
  db: Queryable;
  snapshot: SnapshotId;
  log: EvidenceLog;
  defaults: { bank: string; period: string; kind: string };
  filingText?: FilingTextStore | null;
}

interface ParamSpec {
  name: string;
  type: "string" | "number";
  required?: boolean;
  enum?: readonly string[];
  pattern?: RegExp;
  /** Materialized into args when absent, so an omitted-vs-explicit default yields ONE evidence id. */
  default?: string;
  description: string;
}

export interface ToolSpec {
  name: string;
  description: string;
  params: ParamSpec[];
  run: (ctx: ToolContext, args: Record<string, unknown>) => Promise<{
    data: unknown;
    warnings: string[];
    tables: string[];
    rows: number;
    sourcePages?: number[];
  }>;
}

const PERIOD_RE = /^\d{4}Q[1-4]$/;
const TICKER_RE = /^[A-Z]{2,8}$/;
const KINDS = ["consolidated", "unconsolidated"] as const;

const MAX_ROWS = 220;
// Safety bound for unexpected long strings in evidence. Every tool bounds its
// own text tighter (search contexts ~320, failed_detail 400, quotes 600) —
// EXCEPT get_source_page, whose 8000-char page IS the payload; 1400 here was
// measured clipping the sukuk instrument table out of the model's sight.
const TEXT_TRUNC = 8200;

/* ------------------------------------------------------------------ utils */

function bad(msg: string): never {
  throw new ToolError(msg);
}

export class ToolError extends Error {}

function validateArgs(spec: ToolSpec, raw: Record<string, unknown>, defaults: ToolContext["defaults"]): Record<string, unknown> {
  const args: Record<string, unknown> = {};
  for (const p of spec.params) {
    let v = raw[p.name];
    if (v == null && ["bank", "period", "kind"].includes(p.name)) {
      v = defaults[p.name as "bank" | "period" | "kind"];
    }
    if (v == null && p.default != null) v = p.default;
    if (v == null) {
      if (p.required) bad(`missing required param '${p.name}'`);
      continue;
    }
    if (p.type === "number") {
      const n = typeof v === "number" ? v : Number(v);
      if (!Number.isFinite(n)) bad(`param '${p.name}' must be a number`);
      args[p.name] = n;
      continue;
    }
    if (typeof v !== "string") bad(`param '${p.name}' must be a string`);
    if (p.enum && !p.enum.includes(v)) bad(`param '${p.name}' must be one of: ${p.enum.join(", ")}`);
    if (p.pattern && !p.pattern.test(v)) bad(`param '${p.name}' fails pattern ${p.pattern}`);
    args[p.name] = v;
  }
  for (const k of Object.keys(raw)) {
    if (!spec.params.some((p) => p.name === k)) bad(`unknown param '${k}' for ${spec.name}`);
  }
  return args;
}

/** Map statement key → the `statement` value bank_audit_validation uses. */
const VALIDATION_KEY: Record<string, string> = {
  balance_sheet_assets: "assets",
  balance_sheet_liabilities: "liabilities",
  off_balance: "off_balance",
  profit_loss: "profit_loss",
  oci: "oci",
  cash_flow: "cash_flow",
  equity_change: "equity_change",
  npl_movement: "npl_movement",
  credit_quality: "credit_quality",
  capital: "capital",
  liquidity: "liquidity",
  fx_position: "fx_position",
  repricing: "repricing",
  loans_by_sector: "loans_by_sector",
};

async function validationWarnings(
  ctx: ToolContext, bank: string, period: string, kind: string, statementKey?: string,
): Promise<string[]> {
  try {
    const stmt = statementKey ? VALIDATION_KEY[statementKey] : undefined;
    const rows = await ctx.db.all<{ statement: string; checks_failed: number; failed_detail: string | null }>(
      "SELECT statement, checks_failed, failed_detail FROM bank_audit_validation " +
        "WHERE bank_ticker = ? AND period = ? AND kind = ? AND checks_failed > 0" +
        (stmt ? " AND statement = ?" : ""),
      stmt ? [bank, period, kind, stmt] : [bank, period, kind],
    );
    return rows.map(
      (r) =>
        `VALIDATION FAILING — ${r.statement}: ${r.checks_failed} check(s) failed` +
        (r.failed_detail ? ` (${String(r.failed_detail).slice(0, 200)})` : ""),
    );
  } catch {
    return ["validation table unavailable — treat all figures as unvalidated"];
  }
}

function truncateRows<T>(rows: T[], warnings: string[]): T[] {
  if (rows.length > MAX_ROWS) {
    warnings.push(`result truncated to ${MAX_ROWS} of ${rows.length} rows`);
    return rows.slice(0, MAX_ROWS);
  }
  return rows;
}

function collectPages(rows: Record<string, unknown>[]): number[] {
  const pages = new Set<number>();
  for (const r of rows) {
    const p = r["source_page"];
    if (typeof p === "number" && Number.isFinite(p)) pages.add(p);
  }
  return [...pages].sort((a, b) => a - b);
}

const foldTr = (s: string) => s.replace(/İ/g, "I").replace(/ı/g, "i").toUpperCase();

/* ---------------------------------------------------------------- helpers */

const P_BANK: ParamSpec = { name: "bank", type: "string", pattern: TICKER_RE, description: "ticker (defaults to the run's bank)" };
const P_PERIOD: ParamSpec = { name: "period", type: "string", pattern: PERIOD_RE, description: "YYYYQN (defaults to the run's period)" };
const P_KIND: ParamSpec = { name: "kind", type: "string", enum: KINDS, description: "consolidation basis (defaults to the run's kind)" };

async function statementRows(
  ctx: ToolContext, statement: string, bank: string, period: string, kind: string, periodType?: string,
): Promise<{ rows: Record<string, unknown>[]; spec: (typeof STATEMENTS)[string] }> {
  const spec = STATEMENTS[statement];
  if (!spec) bad(`unknown statement '${statement}'`);
  let sql =
    `SELECT ${spec.columns.join(", ")} FROM ${spec.table} ` +
    `WHERE bank_ticker = ? AND period = ? AND kind = ?` +
    (spec.where ? ` AND ${spec.where}` : "");
  const binds: unknown[] = [bank, period, kind];
  if (spec.hasPeriodType) {
    sql += " AND period_type = ?";
    binds.push(periodType ?? "current");
  }
  if (spec.columns.includes("item_order")) sql += " ORDER BY item_order";
  const rows = await ctx.db.all<Record<string, unknown>>(sql, binds);
  return { rows, spec };
}

/* ------------------------------------------------------------------ tools */

export const TOOLS: ToolSpec[] = [
  {
    name: "list_available_data",
    description: "What exists for this bank/period/kind: statements with status and row counts, extraction record, and every period held for the bank.",
    params: [P_BANK, P_PERIOD, P_KIND],
    run: async (ctx, a) => {
      const warnings: string[] = [];
      const [coverage, extraction, periods] = await Promise.all([
        ctx.db.all<Record<string, unknown>>(
          "SELECT statement_type, status, row_count, checks_failed, pdf_present " +
            "FROM bank_audit_coverage WHERE bank_ticker = ? AND period = ? AND kind = ? ORDER BY statement_type",
          [a.bank, a.period, a.kind],
        ).catch(() => []),
        ctx.db.all<Record<string, unknown>>(
          "SELECT extracted_at, success, note FROM bank_audit_extractions WHERE bank_ticker = ? AND period = ? AND kind = ?",
          [a.bank, a.period, a.kind],
        ),
        ctx.db.all<{ period: string }>(
          "SELECT DISTINCT period FROM bank_audit_balance_sheet WHERE bank_ticker = ? AND kind = ? ORDER BY period",
          [a.bank, a.kind],
        ),
      ]);
      if (!extraction.length) warnings.push("no extraction record — this partition may not exist");
      return {
        data: { coverage, extraction, periods_held: periods.map((p) => p.period), statements_available: Object.keys(STATEMENTS) },
        warnings,
        tables: ["bank_audit_coverage", "bank_audit_extractions", "bank_audit_balance_sheet"],
        rows: coverage.length,
      };
    },
  },
  {
    name: "get_validation_status",
    description: "Validation results for the partition: which checks passed/failed per statement, with failure detail.",
    params: [P_BANK, P_PERIOD, P_KIND, { name: "statement", type: "string", enum: Object.keys(VALIDATION_KEY), description: "optional single statement" }],
    run: async (ctx, a) => {
      const stmt = a.statement ? VALIDATION_KEY[a.statement as string] : undefined;
      const rows = await ctx.db.all<Record<string, unknown>>(
        "SELECT statement, checks_passed, checks_failed, checks_skipped, failed_detail " +
          "FROM bank_audit_validation WHERE bank_ticker = ? AND period = ? AND kind = ?" +
          (stmt ? " AND statement = ?" : "") + " ORDER BY statement",
        stmt ? [a.bank, a.period, a.kind, stmt] : [a.bank, a.period, a.kind],
      );
      for (const r of rows) {
        if (typeof r.failed_detail === "string") r.failed_detail = r.failed_detail.slice(0, 400);
      }
      return { data: rows, warnings: rows.length ? [] : ["no validation rows for this partition"], tables: ["bank_audit_validation"], rows: rows.length };
    },
  },
  {
    name: "get_statement_rows",
    description: "The COMPLETE rows of one statement for the partition — every column the registry allows, nothing curated away. Read the caveats in the result.",
    params: [
      P_BANK, P_PERIOD, P_KIND,
      { name: "statement", type: "string", required: true, enum: Object.keys(STATEMENTS), description: "which statement" },
      { name: "period_type", type: "string", enum: ["current", "prior"], default: "current", description: "for statements that carry a prior block" },
    ],
    run: async (ctx, a) => {
      const warnings: string[] = [];
      const { rows, spec } = await statementRows(ctx, a.statement as string, a.bank as string, a.period as string, a.kind as string, a.period_type as string | undefined);
      if (!rows.length) warnings.push("0 rows — statement absent for this partition (see list_available_data; absence is N/A, not zero)");
      const out = truncateRows(rows, warnings);
      return {
        data: { caveats: spec.caveats, rows: out },
        warnings,
        tables: [spec.table],
        rows: rows.length,
        sourcePages: collectPages(rows),
      };
    },
  },
  {
    name: "get_row_history",
    description: "One row or metric across every stored period for the bank/kind. Identify line rows by hierarchy or a label fragment; singleton statements by column name.",
    params: [
      P_BANK, P_KIND,
      { name: "statement", type: "string", required: true, enum: Object.keys(STATEMENTS), description: "which statement" },
      { name: "hierarchy", type: "string", description: "exact hierarchy of a line row (e.g. 'XI.')" },
      { name: "item_name_like", type: "string", description: "label fragment (case/diacritic-folded contains-match)" },
      { name: "group_code", type: "string", enum: ["III", "IV", "V"], description: "npl_movement group" },
      { name: "section", type: "string", description: "credit_quality section" },
      { name: "currency", type: "string", enum: ["USD", "EUR", "OTHER", "TOTAL"], description: "fx_position row" },
      { name: "column", type: "string", description: "numeric column to return (defaults to all numeric columns)" },
    ],
    run: async (ctx, a) => {
      const spec = STATEMENTS[a.statement as string];
      if (!spec) bad("unknown statement");
      const warnings: string[] = [];
      const cols = a.column
        ? (spec.numericColumns.includes(a.column as string) ? [a.column as string] : bad(`column must be one of: ${spec.numericColumns.join(", ")}`))
        : spec.numericColumns;
      let where = "bank_ticker = ? AND kind = ?" + (spec.where ? ` AND ${spec.where}` : "");
      const binds: unknown[] = [a.bank, a.kind];
      if (spec.hasPeriodType) where += " AND period_type = 'current'";
      if (a.hierarchy != null) { where += " AND hierarchy = ?"; binds.push(a.hierarchy); }
      if (a.group_code != null) { where += " AND group_code = ?"; binds.push(a.group_code); }
      if (a.section != null) { where += " AND section = ?"; binds.push(a.section); }
      if (a.currency != null) { where += " AND currency = ?"; binds.push(a.currency); }
      const idCols = spec.rowIdentity.length ? spec.rowIdentity.join(", ") + ", " : "";
      const rows = await ctx.db.all<Record<string, unknown>>(
        `SELECT period, ${idCols}${cols.join(", ")} FROM ${spec.table} WHERE ${where} ORDER BY period`,
        binds,
      );
      let filtered = rows;
      if (a.item_name_like != null) {
        const needle = foldTr(String(a.item_name_like));
        filtered = rows.filter((r) => typeof r.item_name === "string" && foldTr(r.item_name as string).includes(needle));
        if (!filtered.length) warnings.push(`no rows matched label fragment '${a.item_name_like}' — labels vary by language and template; try a shorter fragment or hierarchy`);
      }
      if (spec.rowIdentity.length && !a.hierarchy && !a.item_name_like && !a.group_code && !a.section && !a.currency) {
        bad("this statement has row identity — pass hierarchy/item_name_like/group_code/section/currency to pick a row");
      }
      const out = truncateRows(filtered, warnings);
      if (!out.length && !warnings.length) warnings.push("no history rows found");
      return { data: out, warnings, tables: [spec.table], rows: filtered.length };
    },
  },
  {
    name: "rank_statement_movements",
    description: "Deterministic movement ranking for one statement at the period: per-row QoQ/YoY deltas and share of total absolute change (line statements), or per-movement-row equity impact with per-component column sums (equity_change). Singleton statements (capital, liquidity, …) have no rows to rank — use get_row_history there.",
    params: [
      P_BANK, P_PERIOD, P_KIND,
      // Advertising unrankable statements cost measured turns (3 in one run
      // on npl_movement alone) — the enum IS the contract.
      { name: "statement", type: "string", required: true, enum: Object.keys(STATEMENTS).filter((k) => k === "equity_change" || STATEMENTS[k].columns.includes("item_name")), description: "which statement (line statements + equity_change)" },
    ],
    run: async (ctx, a) => {
      const statement = a.statement as string;
      const spec = STATEMENTS[statement];
      if (!spec) bad("unknown statement");
      const warnings: string[] = [];
      const bank = a.bank as string;
      const period = a.period as string;
      const kind = a.kind as string;
      const [y, q] = [Number(period.slice(0, 4)), Number(period.slice(5))];
      const prevQ = q === 1 ? `${y - 1}Q4` : `${y}Q${q - 1}`;
      const prevY = `${y - 1}Q${q}`;

      if (statement === "equity_change") {
        const { rows } = await statementRows(ctx, statement, bank, period, kind, "current");
        if (!rows.length) return { data: [], warnings: ["no equity rows"], tables: [spec.table], rows: 0 };
        const movements = rows.map((r, i) => ({
          item_order: r.item_order,
          item_name: r.item_name,
          total_equity_impact: r.total_equity,
          looks_like_boundary:
            i === 0 || i === rows.length - 1 ||
            (typeof r.item_name === "string" && /BEGIN|OPENING|BA[SŞ]I|END|SONU|BALANCES AT/i.test(foldTr(r.item_name as string))),
          components: Object.fromEntries(
            spec.numericColumns.filter((c) => c !== "total_equity").map((c) => [c, r[c]]),
          ),
        }));
        const ranked = [...movements].sort(
          (x, z) => Math.abs(Number(z.total_equity_impact) || 0) - Math.abs(Number(x.total_equity_impact) || 0),
        );
        const columnSums = Object.fromEntries(
          spec.numericColumns.map((c) => [
            c,
            rows.reduce((s, r, i) => (i === 0 || i === rows.length - 1 ? s : s + (Number(r[c]) || 0)), 0),
          ]),
        );
        warnings.push("boundary detection is heuristic (labels can be template-shifted) — confirm with reconcile_statements('equity_opening_to_closing')");
        return {
          data: { ranked_by_total_equity_impact: ranked, movement_column_sums_excl_boundaries: columnSums },
          warnings, tables: [spec.table], rows: rows.length, sourcePages: collectPages(rows as Record<string, unknown>[]),
        };
      }

      if (!spec.columns.includes("item_name")) bad("movement ranking supports line statements and equity_change — use get_row_history for singleton statements");
      const amountCol = spec.numericColumns.includes("amount") ? "amount" : "amount_total";
      const fetch = (p: string) => statementRows(ctx, statement, bank, p, kind, "current").then((r) => r.rows);
      const [nowR, qR, yR] = await Promise.all([fetch(period), fetch(prevQ), fetch(prevY)]);
      if (!nowR.length) return { data: [], warnings: ["no rows at the period"], tables: [spec.table], rows: 0 };
      const key = (r: Record<string, unknown>) => `${r.hierarchy}|${foldTr(String(r.item_name ?? ""))}`;
      const qMap = new Map(qR.map((r) => [key(r), r[amountCol] as number | null]));
      const yMap = new Map(yR.map((r) => [key(r), r[amountCol] as number | null]));
      const items = nowR
        .map((r) => {
          const now = r[amountCol] as number | null;
          const pq = qMap.get(key(r)) ?? null;
          const py = yMap.get(key(r)) ?? null;
          return {
            hierarchy: r.hierarchy, item_name: r.item_name, now,
            qoq_delta: now != null && pq != null ? now - pq : null,
            yoy_delta: now != null && py != null ? now - py : null,
          };
        })
        .filter((r) => r.now != null || r.qoq_delta != null);
      const totalAbs = items.reduce((s, r) => s + Math.abs(r.qoq_delta ?? 0), 0);
      const ranked = items
        .map((r) => ({ ...r, qoq_share_of_total_abs_change: totalAbs > 0 && r.qoq_delta != null ? Number((Math.abs(r.qoq_delta) / totalAbs).toFixed(3)) : null }))
        .sort((x, z) => Math.abs(z.qoq_delta ?? 0) - Math.abs(x.qoq_delta ?? 0));
      if (!qR.length) warnings.push(`no rows at ${prevQ} — QoQ deltas are null`);
      if (!yR.length) warnings.push(`no rows at ${prevY} — YoY deltas are null`);
      if (statement === "profit_loss" || statement === "oci" || statement === "cash_flow") {
        warnings.push("amounts are YTD-cumulative — a Q1 column compares whole-YTD to whole-YTD");
      }
      return { data: truncateRows(ranked, warnings), warnings, tables: [spec.table], rows: ranked.length };
    },
  },
  {
    name: "compare_with_peers",
    description: "The bank against its licence class on one metric: named per-bank values, class median, the bank's value and rank.",
    params: [
      P_BANK, P_PERIOD, P_KIND,
      { name: "metric", type: "string", required: true, enum: PEER_METRICS, description: "which metric" },
    ],
    run: async (ctx, a) => {
      const peers = await buildPeerContext(ctx.db, a.bank as string, a.period as string, a.kind as string);
      const metric = a.metric as (typeof PEER_METRICS)[number];
      const field: Record<string, keyof (typeof peers.rows)[number]> = {
        total_assets: "total_assets", car: "car", cet1: "cet1", npl_ratio_pct: "npl_ratio_pct",
        stage2_ratio_pct: "stage2_ratio_pct", stage3_coverage_pct: "stage3_coverage_pct", roe_ttm_pct: "roe_ttm_pct",
      };
      const rows = peers.rows
        .map((r) => ({ bank_ticker: r.bank_ticker, value: r[field[metric]] as number | null }))
        .filter((r) => r.value != null)
        .sort((x, z) => (z.value as number) - (x.value as number))
        .map((r, i) => ({ ...r, rank_desc: i + 1 }));
      const mine = rows.find((r) => r.bank_ticker === a.bank) ?? null;
      const warnings: string[] = [];
      if (!mine) warnings.push("the bank has no value for this metric at the period");
      if (metric === "stage2_ratio_pct" || metric === "stage3_coverage_pct") {
        warnings.push("stage definitions differ across banks (SICR/DPD thresholds) — comparisons carry that caveat unless both banks' disclosed thresholds match");
      }
      return {
        data: { licence_class: peers.licence_class, metric, bank_value: mine, peers: rows, medians: peers.medians },
        warnings, tables: ["bank_audit_capital", "bank_audit_stages", "bank_audit_balance_sheet", "bank_audit_profit_loss", "bank_audit_equity_change"],
        rows: rows.length,
      };
    },
  },
  {
    name: "reconcile_statements",
    description: "Deterministic cross-statement arithmetic with every component shown: " + RECONCILIATIONS.join(", "),
    params: [
      P_BANK, P_PERIOD, P_KIND,
      { name: "reconciliation", type: "string", required: true, enum: RECONCILIATIONS, description: "which reconciliation" },
    ],
    run: async (ctx, a) => runReconciliation(ctx, a.reconciliation as ReconciliationName, a.bank as string, a.period as string, a.kind as string),
  },
  {
    name: "search_filing_text",
    description: "Text search over the filing PDF's extracted text (prepared per run). SUBSTRING match per term; separate alternatives with ' OR '. Short fragments beat long phrases. Returns page numbers with context windows.",
    params: [
      { name: "query", type: "string", required: true, description: "substring (diacritic-folded, min 3 chars), or alternatives joined by ' OR ' — matched independently" },
      { name: "max_hits", type: "number", description: "default 8" },
    ],
    run: async (ctx, a) => {
      if (!ctx.filingText) {
        return { data: [], warnings: ["filing text not prepared in this run — the source-page tools need the PDF pre-extract step"], tables: [], rows: 0 };
      }
      // Models reach for boolean syntax under pressure — measured: 7 of 12
      // searches across two runs were 'X OR Y' forms that matched nothing as
      // literal substrings. Split on OR and match each alternative.
      const terms = String(a.query).split(/\s+OR\s+/i).map((t) => foldTr(t.trim())).filter((t) => t.length > 0);
      if (!terms.length || terms.some((t) => t.length < 3)) bad("each search term must be at least 3 chars");
      const maxHits = Math.min(Number(a.max_hits) || 8, 20);
      const warnings: string[] = [];
      const hits: { page: number; term: string; context: string }[] = [];
      outer: for (const p of ctx.filingText.pages) {
        const folded = foldTr(p.text);
        for (const q of terms) {
          let idx = folded.indexOf(q);
          while (idx >= 0) {
            hits.push({ page: p.page, term: q, context: p.text.slice(Math.max(0, idx - 160), idx + q.length + 160).replace(/\s+/g, " ") });
            if (hits.length >= maxHits) break outer;
            idx = folded.indexOf(q, idx + q.length);
          }
        }
      }
      if (!hits.length) {
        warnings.push("no matches");
        if (terms.some((t) => t.split(/\s+/).length >= 4)) {
          warnings.push("this is SUBSTRING search — long phrases rarely appear verbatim; retry with short distinctive fragments (a number, a defined term)");
        }
      }
      // Rarest term first: a distinctive hit (an exact amount on a notes
      // page) must not sit below a pile of boilerplate matches — measured: a
      // decisive page-92 hit was listed last twice and never followed.
      const freq = new Map<string, number>();
      for (const h of hits) freq.set(h.term, (freq.get(h.term) ?? 0) + 1);
      hits.sort((x, y) => (freq.get(x.term)! - freq.get(y.term)!) || (x.page - y.page));
      return { data: hits, warnings, tables: [], rows: hits.length, sourcePages: [...new Set(hits.map((h) => h.page))].sort((x, y) => x - y) };
    },
  },
  {
    name: "get_source_page",
    description: "The extracted text of one PDF page of the filing (prepared per run).",
    params: [{ name: "page", type: "number", required: true, description: "1-based page number" }],
    run: async (ctx, a) => {
      if (!ctx.filingText) {
        return { data: null, warnings: ["filing text not prepared in this run"], tables: [], rows: 0 };
      }
      const page = ctx.filingText.pages.find((p) => p.page === a.page);
      if (!page) return { data: null, warnings: [`page ${a.page} not in the prepared text (${ctx.filingText.pages.length} pages)`], tables: [], rows: 0 };
      return { data: { page: page.page, text: page.text.slice(0, 8000) }, warnings: [], tables: [], rows: 1, sourcePages: [page.page] };
    },
  },
  {
    name: "get_existing_signals",
    description: "V1 detector signals for the partition (unit switches, restatements, opinion/perimeter changes, divergences) — leads, not conclusions.",
    params: [P_BANK, P_PERIOD, P_KIND],
    run: async (ctx, a) => {
      const rows = await ctx.db.all<Record<string, unknown>>(
        "SELECT signal_id, signal_type, severity, payload FROM analyst_signals WHERE bank_ticker = ? AND period = ? AND kind = ?",
        [a.bank, a.period, a.kind],
      ).catch(() => [] as Record<string, unknown>[]);
      return { data: rows, warnings: rows.length ? [] : ["no signals staged for this partition"], tables: ["analyst_signals"], rows: rows.length };
    },
  },
  {
    name: "get_management_commentary",
    description: "Verbatim executive turns from the bank's earnings-call transcript for the period (management's claims, not verified data).",
    params: [
      P_BANK, P_PERIOD,
      { name: "query", type: "string", description: "optional keyword filter over turns" },
    ],
    run: async (ctx, a) => {
      const row = await ctx.db.all<{ period: string; call_date: string; title: string | null; transcript_json: string }>(
        "SELECT period, call_date, title, transcript_json FROM bank_call_transcripts " +
          "WHERE bank_ticker = ? AND period = ? ORDER BY call_date DESC LIMIT 1",
        [a.bank, a.period],
      ).catch(() => []);
      if (!row.length) {
        return { data: null, warnings: ["no transcribed call for this bank/period"], tables: ["bank_call_transcripts"], rows: 0 };
      }
      let turns: { role?: string; text?: string }[] = [];
      try { turns = JSON.parse(row[0].transcript_json); } catch { /* malformed */ }
      let exec = turns.filter((t) => t.role === "executive" && t.text && t.text.length > 60);
      if (a.query) {
        const q = foldTr(String(a.query));
        exec = exec.filter((t) => foldTr(t.text as string).includes(q));
      }
      const out = exec.slice(0, 6).map((t) => ({ role: "executive", quote: (t.text as string).slice(0, 600) }));
      return {
        data: { call_date: row[0].call_date, title: row[0].title, turns: out },
        warnings: ["management claims are NOT verified data — quote with attribution only"],
        tables: ["bank_call_transcripts"], rows: out.length,
      };
    },
  },
  {
    name: "get_regulatory_or_macro_context",
    description: "Macro backdrop at the period (CBRT funding rate, CPI y/y, USDTRY) and the latest regulation-briefing categories.",
    params: [P_PERIOD],
    run: async (ctx, a) => {
      const period = a.period as string;
      const month = { "1": "03", "2": "06", "3": "09", "4": "12" }[period.slice(5)];
      const bound = `${period.slice(0, 4)}-${month}-99`;
      const evds = await ctx.db.all<{ code: string; period_date: string; value: number | null }>(
        "SELECT code, period_date, value FROM evds_series WHERE code IN ('TP.APIFON4','TP.DK.USD.A','TP.TUKFIY2025.GENEL') AND period_date <= ? ORDER BY period_date",
        [bound],
      ).catch(() => []);
      const latest = (code: string) => {
        let v: { period_date: string; value: number | null } | null = null;
        for (const r of evds) if (r.code === code && r.value != null) v = r;
        return v;
      };
      const cpiAt = (ym: string) => {
        let v: number | null = null;
        for (const r of evds) if (r.code === "TP.TUKFIY2025.GENEL" && r.value != null && r.period_date.slice(0, 7) <= ym) v = r.value;
        return v;
      };
      const now = cpiAt(`${period.slice(0, 4)}-${month}`);
      const base = cpiAt(`${Number(period.slice(0, 4)) - 1}-${month}`);
      const briefing = await ctx.db.all<{ categories_json: string | null }>(
        "SELECT categories_json FROM regulation_briefings ORDER BY generated_at DESC LIMIT 1", [],
      ).catch(() => []);
      let categories: string[] = [];
      try {
        const parsed = briefing[0]?.categories_json ? JSON.parse(briefing[0].categories_json) : null;
        if (parsed && typeof parsed === "object") categories = Object.keys(parsed);
      } catch { /* absent */ }
      return {
        data: {
          funding_rate_pct: latest("TP.APIFON4"),
          usd_try: latest("TP.DK.USD.A"),
          cpi_yoy_pct: now != null && base != null && base > 0 ? Number(((now / base - 1) * 100).toFixed(2)) : null,
          regulation_categories: categories,
        },
        warnings: evds.length ? [] : ["macro series unavailable in this snapshot"],
        tables: ["evds_series", "regulation_briefings"], rows: evds.length,
      };
    },
  },
];

/* ------------------------------------------------------- reconciliations */

const TOL_REL = 0.005;

function verdictOf(lhs: number | null, rhs: number | null): { diff: number | null; pct_diff: number | null; verdict: string } {
  if (lhs == null || rhs == null) return { diff: null, pct_diff: null, verdict: "not_computable" };
  const diff = lhs - rhs;
  const base = Math.max(Math.abs(lhs), Math.abs(rhs), 1);
  const pct = Math.abs(diff) / base;
  return { diff, pct_diff: Number((pct * 100).toFixed(3)), verdict: pct <= TOL_REL ? "reconciles" : "BREAKS" };
}

async function runReconciliation(
  ctx: ToolContext, name: ReconciliationName, bank: string, period: string, kind: string,
): Promise<{ data: unknown; warnings: string[]; tables: string[]; rows: number; sourcePages?: number[] }> {
  const warnings: string[] = [];

  if (name === "bs_legs_balance") {
    const rows = await ctx.db.all<{ statement: string; total: number | null }>(
      "SELECT statement, MAX(amount_total) AS total FROM bank_audit_balance_sheet " +
        "WHERE bank_ticker = ? AND period = ? AND kind = ? AND hierarchy = '' " +
        "AND statement IN ('assets','liabilities') GROUP BY statement",
      [bank, period, kind],
    );
    const assets = rows.find((r) => r.statement === "assets")?.total ?? null;
    const liab = rows.find((r) => r.statement === "liabilities")?.total ?? null;
    return { data: { assets_total: assets, liabilities_total: liab, ...verdictOf(assets, liab) }, warnings, tables: ["bank_audit_balance_sheet"], rows: rows.length };
  }

  if (name.startsWith("equity_")) {
    const { rows } = await statementRows(ctx, "equity_change", bank, period, kind, "current");
    if (!rows.length) return { data: null, warnings: ["no equity rows"], tables: ["bank_audit_equity_change"], rows: 0 };
    const closing = rows[rows.length - 1];
    const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

    if (name === "equity_opening_to_closing") {
      // Opening = the earliest row with a nonzero total_equity that reads like
      // a balance (or simply the first nonzero row); everything between it and
      // the closing row is a movement. Method is REPORTED, not hidden.
      const openIdx = rows.findIndex((r) => (num(r.total_equity) ?? 0) !== 0);
      const opening = openIdx >= 0 && openIdx < rows.length - 1 ? rows[openIdx] : null;
      const movements = rows.slice((openIdx >= 0 ? openIdx : 0) + 1, rows.length - 1);
      const sumMoves = movements.reduce((s, r) => s + (num(r.total_equity) ?? 0), 0);
      const lhs = opening ? (num(opening.total_equity) ?? 0) + sumMoves : null;
      const rhs = num(closing.total_equity);
      warnings.push("opening-row selection is heuristic (first nonzero total_equity) — labels can be template-shifted; inspect the movement list");
      return {
        data: {
          method: "opening(first nonzero total_equity) + Σ movement rows = closing(last row)",
          opening: opening ? { item_order: opening.item_order, item_name: opening.item_name, total_equity: opening.total_equity } : null,
          movements: movements.map((r) => ({ item_order: r.item_order, item_name: r.item_name, total_equity: r.total_equity })),
          movements_sum: sumMoves,
          closing: { item_order: closing.item_order, item_name: closing.item_name, total_equity: closing.total_equity },
          ...verdictOf(lhs, rhs),
        },
        warnings, tables: ["bank_audit_equity_change"], rows: rows.length, sourcePages: collectPages(rows as Record<string, unknown>[]),
      };
    }

    if (name === "equity_net_profit_vs_pl") {
      const pl = await ctx.db.all<{ amount: number | null }>(
        "SELECT p.amount FROM bank_audit_profit_loss p JOIN bank_audit_pl_roles r " +
          "ON r.bank_ticker = p.bank_ticker AND r.period = p.period AND r.kind = p.kind AND r.hierarchy = p.hierarchy " +
          "WHERE r.role = 'period_net' AND p.bank_ticker = ? AND p.period = ? AND p.kind = ?",
        [bank, period, kind],
      );
      const lhs = num(closing.period_net_profit_loss);
      const rhs = pl[0]?.amount ?? null;
      return {
        data: { equity_closing_period_net_column: lhs, pl_period_net_ytd: rhs, ...verdictOf(lhs, rhs) },
        warnings, tables: ["bank_audit_equity_change", "bank_audit_profit_loss", "bank_audit_pl_roles"], rows: rows.length,
      };
    }

    if (name === "equity_closing_vs_balance_sheet") {
      const bsRows = await ctx.db.all<{ item_name: string | null; amount_total: number | null }>(
        "SELECT item_name, amount_total FROM bank_audit_balance_sheet " +
          "WHERE bank_ticker = ? AND period = ? AND kind = ? AND statement = 'liabilities' AND amount_total IS NOT NULL",
        [bank, period, kind],
      );
      const eqLines = bsRows.filter((r) => r.item_name && /OZKAYNAK|EQUITY/.test(foldTr(r.item_name)));
      const bsEquity = eqLines.length ? Math.max(...eqLines.map((r) => r.amount_total as number)) : null;
      warnings.push("balance-sheet equity is label-matched (ÖZKAYNAK/EQUITY, max of matches) — label matching is fragile; treat a small break as method noise before restatement");
      const lhs = num(closing.total_equity_incl_minority) ?? num(closing.total_equity);
      return {
        data: { equity_change_closing: lhs, balance_sheet_equity_line: bsEquity, matched_labels: eqLines.map((r) => r.item_name).slice(0, 5), ...verdictOf(lhs, bsEquity) },
        warnings, tables: ["bank_audit_equity_change", "bank_audit_balance_sheet"], rows: rows.length,
      };
    }
  }

  if (name === "npl_movement_footing") {
    const rows = await ctx.db.all<Record<string, number | string | null>>(
      "SELECT group_code, opening_balance, additions, transfers_in, transfers_out, collections, " +
        "write_offs, sold, fx_diff, accrual_movement, closing_balance FROM bank_audit_npl_movement " +
        "WHERE bank_ticker = ? AND period = ? AND kind = ? AND period_type = 'current' ORDER BY group_code",
      [bank, period, kind],
    );
    const per = rows.map((r) => {
      const n = (k: string) => (typeof r[k] === "number" ? (r[k] as number) : 0);
      const computed = n("opening_balance") + n("additions") + n("transfers_in") - n("transfers_out") - n("collections") - n("write_offs") - n("sold") + n("fx_diff") + n("accrual_movement");
      return {
        group: r.group_code,
        formula: "opening + additions + transfers_in − transfers_out − collections − write_offs − sold + fx_diff + accrual_movement",
        computed_closing: computed,
        reported_closing: r.closing_balance,
        components: r,
        ...verdictOf(computed, typeof r.closing_balance === "number" ? r.closing_balance : null),
      };
    });
    return {
      data: per,
      warnings: ["sign conventions vary by filer — a systematic per-group break may mean a component is printed with the opposite sign, not a bad extraction"],
      tables: ["bank_audit_npl_movement"], rows: rows.length,
    };
  }

  bad(`unknown reconciliation '${name}'`);
}

/* ------------------------------------------------------------- execution */

export async function runTool(
  ctx: ToolContext, name: string, rawArgs: Record<string, unknown>,
): Promise<EvidenceRecord> {
  const spec = TOOLS.find((t) => t.name === name);
  if (!spec) bad(`unknown tool '${name}' — available: ${TOOLS.map((t) => t.name).join(", ")}`);
  const args = validateArgs(spec, rawArgs ?? {}, ctx.defaults);
  const id = evidenceId(name, args, ctx.snapshot.id);
  const cached = ctx.log.get(id);
  if (cached) return cached;

  const result = await spec.run(ctx, args);
  const bank = (args.bank as string) ?? null;
  const period = (args.period as string) ?? null;
  const kind = (args.kind as string) ?? null;
  const vWarnings =
    bank && period && kind
      ? await validationWarnings(ctx, bank, period, kind, typeof args.statement === "string" ? (args.statement as string) : undefined)
      : [];

  // Text fields are truncated in evidence to keep artifacts bounded.
  const data = JSON.parse(
    JSON.stringify(result.data, (_k, v) => (typeof v === "string" && v.length > TEXT_TRUNC ? v.slice(0, TEXT_TRUNC) + "…" : v)),
  );

  return ctx.log.add({
    evidence_id: id,
    tool: name,
    args,
    provenance: {
      snapshot: ctx.snapshot.id,
      tables: result.tables,
      bank, period, kind,
      source_pages: result.sourcePages ?? [],
    },
    validation_warnings: vWarnings,
    warnings: result.warnings,
    rows_returned: result.rows,
    data,
  });
}

/** The tool catalog as shown to the model — names, params, one-line purpose. */
export function toolCatalog(): string {
  return TOOLS.map((t) => {
    const params = t.params.map((p) => `${p.name}${p.required ? "" : "?"}: ${p.enum ? p.enum.join("|") : p.type}`).join(", ");
    return `- ${t.name}(${params}) — ${t.description}`;
  }).join("\n");
}

export async function snapshotIdOf(db: Queryable): Promise<SnapshotId> {
  try {
    const r = await db.all<{ m: string | null; n: number }>(
      "SELECT MAX(extracted_at) AS m, COUNT(1) AS n FROM bank_audit_extractions", [],
    );
    const m = r[0]?.m ?? null;
    const n = r[0]?.n ?? 0;
    return { id: `audit:${m ?? "unknown"}:${n}`, max_extracted_at: m, extraction_rows: n };
  } catch {
    return { id: "audit:unknown:0", max_extracted_at: null, extraction_rows: 0 };
  }
}

// canonical() is re-exported for the loop's dedupe of proposed actions.
export { canonical };
