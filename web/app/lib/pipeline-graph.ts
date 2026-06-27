/**
 * Pipeline topology — the hand-authored data model behind the /pipeline tab.
 *
 * A pure, dependency-free description of how data flows through the system:
 * external SOURCES → INGESTION (GitHub workflows / scripts) → STORAGE
 * (Cloudflare D1 / R2 / KV) → CONSUMPTION (dashboard pages). Two isolated
 * ingestion lanes are tagged so the visualization can band them apart:
 *   - `bulletin`  — the `bddk-pipeline` concurrency group (BDDK/EVDS/macro/market)
 *   - `audit`     — the `bddk-audit` concurrency group (BRSA quarterly reports)
 *   - `shared`    — cross-cutting infra (snapshots, cache, deploy, CI, monitoring)
 *
 * This file is consumed both by the layout helper (`pipeline-layout.ts`, which
 * assigns x/y from `layer`/`lane`) and the live-status merge (`pipeline-status.ts`
 * → `statusKey`; `workflowFile` → GitHub Actions runs). Keep it in sync with
 * docs/ARCHITECTURE.md when the pipeline changes.
 */

export type Layer = "source" | "ingestion" | "storage" | "page";
export type Lane = "bulletin" | "audit" | "shared";
export type NodeKind = "source" | "workflow" | "store" | "page";

export interface PipelineNode {
  id: string;
  label: string;
  layer: Layer;
  lane: Lane;
  kind: NodeKind;
  /** Secondary line: source URL, schedule, table list, script names. */
  sublabel?: string;
  /** Resolves a live D1 freshness/row-count entry (see pipeline-status.ts). */
  statusKey?: string;
  /** Workflow filename → matched to a GitHub Actions run client-side. */
  workflowFile?: string;
  /** Dashboard route — makes `page` nodes clickable. */
  href?: string;
}

export type EdgeKind = "data" | "snapshot" | "guard";

export interface PipelineEdge {
  source: string;
  target: string;
  kind?: EdgeKind;
}

// ---------------------------------------------------------------------------
// Nodes
// ---------------------------------------------------------------------------

export const PIPELINE_NODES: PipelineNode[] = [
  // ── Bulletin lane · sources ────────────────────────────────────────────
  { id: "src-bddk-monthly", kind: "source", layer: "source", lane: "bulletin", label: "BDDK monthly bulletin", sublabel: "bddk.org.tr API", statusKey: "monthly" },
  { id: "src-bddk-weekly", kind: "source", layer: "source", lane: "bulletin", label: "BDDK weekly bulletin", sublabel: "bddk.org.tr API", statusKey: "weekly" },
  { id: "src-bddk-nonbank", kind: "source", layer: "source", lane: "bulletin", label: "BDDK non-bank bulletin", sublabel: "BultenAylikBdmk · leasing/factoring/financing" },
  { id: "src-evds", kind: "source", layer: "source", lane: "bulletin", label: "TCMB EVDS", sublabel: "evds3.tcmb.gov.tr · rates / FX / macro", statusKey: "evds" },
  { id: "src-tuik", kind: "source", layer: "source", lane: "bulletin", label: "TÜİK veriportali", sublabel: "Excel theme-tree → TUIK.* series" },
  { id: "src-tbb-digital", kind: "source", layer: "source", lane: "bulletin", label: "TBB digital report", sublabel: "quarterly .xls/.xlsx", statusKey: "tbb_digital" },
  { id: "src-tbb-acq", kind: "source", layer: "source", lane: "bulletin", label: "TBB acquisition stats", sublabel: "monthly remote vs branch", statusKey: "tbb_acq" },
  { id: "src-kap", kind: "source", layer: "source", lane: "bulletin", label: "KAP Genel Bilgi Formu", sublabel: "kap.org.tr · ownership §5/§7", statusKey: "kap" },
  { id: "src-tefas", kind: "source", layer: "source", lane: "bulletin", label: "TEFAS fund market", sublabel: "tefas.gov.tr JSON API", statusKey: "tefas" },
  { id: "src-faaliyet", kind: "source", layer: "source", lane: "bulletin", label: "Bank annual reports", sublabel: "Faaliyet Raporları PDFs · franchise stats", statusKey: "faaliyet" },
  { id: "src-yahoo", kind: "source", layer: "source", lane: "bulletin", label: "Yahoo Finance", sublabel: "chart API · BIST prices/indices", statusKey: "bist" },
  { id: "src-rss-reg", kind: "source", layer: "source", lane: "bulletin", label: "TCMB / BDDK feeds", sublabel: "press releases + board decisions", statusKey: "regulation" },
  { id: "src-rss-press", kind: "source", layer: "source", lane: "bulletin", label: "Financial-media RSS", sublabel: "Bloomberg HT, Dünya, Ekonomim, AA, NTV", statusKey: "news" },
  { id: "src-rss-google", kind: "source", layer: "source", lane: "bulletin", label: "Google News", sublabel: "topic-scoped search RSS · long-tail outlets", statusKey: "news" },
  { id: "src-ir-presentations", kind: "source", layer: "source", lane: "bulletin", label: "Bank IR presentation decks", sublabel: "Garanti BBVA / Akbank / Yapı Kredi · quarterly PDF" },

  // ── Bulletin lane · ingestion (workflows) ──────────────────────────────
  { id: "wf-evds-daily", kind: "workflow", layer: "ingestion", lane: "bulletin", label: "refresh-evds-daily", sublabel: "Sun–Fri 05:00 · EVDS + BIST/TBB/KAP/TEFAS", workflowFile: "refresh-evds-daily.yml" },
  { id: "wf-bddk-bulletins", kind: "workflow", layer: "ingestion", lane: "bulletin", label: "refresh-bddk-bulletins", sublabel: "Sat 02:00 · update_monthly / update_weekly", workflowFile: "refresh-bddk-bulletins.yml" },
  { id: "wf-refresh-data", kind: "workflow", layer: "ingestion", lane: "bulletin", label: "refresh-data", sublabel: "Sat 03:00 · refresh.py (full) → push_to_d1", workflowFile: "refresh-data.yml" },
  { id: "wf-backfill-tefas", kind: "workflow", layer: "ingestion", lane: "bulletin", label: "backfill-tefas", sublabel: "manual · ~5y TEFAS history", workflowFile: "backfill-tefas.yml" },
  { id: "wf-backfill-faaliyet", kind: "workflow", layer: "ingestion", lane: "bulletin", label: "backfill-faaliyet", sublabel: "manual · annual-report franchise backfill", workflowFile: "backfill-faaliyet.yml" },
  { id: "wf-backfill-nonbank", kind: "workflow", layer: "ingestion", lane: "bulletin", label: "backfill-nonbank", sublabel: "manual · non-bank sector history (2020→)", workflowFile: "backfill-nonbank.yml" },
  { id: "wf-news-daily", kind: "workflow", layer: "ingestion", lane: "bulletin", label: "refresh-news-daily", sublabel: "daily 02:00 · sync_news.py", workflowFile: "refresh-news-daily.yml" },
  { id: "wf-summarize", kind: "workflow", layer: "ingestion", lane: "bulletin", label: "summarize-regulations", sublabel: "weekly Thu · LLM briefing", workflowFile: "summarize-regulations.yml" },
  { id: "wf-presentations", kind: "workflow", layer: "ingestion", lane: "bulletin", label: "refresh-presentations-weekly", sublabel: "Sat 06:00 · update_presentations.py", workflowFile: "refresh-presentations-weekly.yml" },

  // ── Bulletin lane · storage (D1) ───────────────────────────────────────
  { id: "store-d1-bulletin", kind: "store", layer: "storage", lane: "bulletin", label: "D1 · bulletin tables", sublabel: "balance_sheet · income_statement · loans · deposits · ratios · weekly", statusKey: "monthly" },
  { id: "store-d1-nonbank", kind: "store", layer: "storage", lane: "bulletin", label: "D1 · nonbank_balance_sheet", sublabel: "leasing · factoring · financing sector balance sheets" },
  { id: "store-d1-evds", kind: "store", layer: "storage", lane: "bulletin", label: "D1 · evds_series", sublabel: "macro / rates / FX · incl. TUIK.*", statusKey: "evds" },
  { id: "store-d1-tbb", kind: "store", layer: "storage", lane: "bulletin", label: "D1 · tbb_*", sublabel: "tbb_digital_stats · tbb_acquisition_stats", statusKey: "tbb_digital" },
  { id: "store-d1-kap", kind: "store", layer: "storage", lane: "bulletin", label: "D1 · kap_ownership", sublabel: "shareholders + §7 subsidiaries", statusKey: "kap" },
  { id: "store-d1-tefas", kind: "store", layer: "storage", lane: "bulletin", label: "D1 · tefas_*", sublabel: "manager / category / allocation / top_funds", statusKey: "tefas" },
  { id: "store-d1-faaliyet", kind: "store", layer: "storage", lane: "bulletin", label: "D1 · faaliyet_franchise", sublabel: "ATM / POS / merchant / customer / card counts", statusKey: "faaliyet" },
  { id: "store-d1-bist", kind: "store", layer: "storage", lane: "bulletin", label: "D1 · bist_*", sublabel: "bist_prices · bist_dividends · bist_shares", statusKey: "bist" },
  { id: "store-d1-news", kind: "store", layer: "storage", lane: "bulletin", label: "D1 · news_items", sublabel: "regulation + press + Google News", statusKey: "news" },
  { id: "store-d1-earnings", kind: "store", layer: "storage", lane: "bulletin", label: "D1 · bank_earnings", sublabel: "KAP results filings + IR presentation decks" },

  // ── Audit lane · sources ───────────────────────────────────────────────
  { id: "src-ir-pdf", kind: "source", layer: "source", lane: "audit", label: "Bank IR / BRSA PDFs", sublabel: "31 banks · +13 auto-discover quarters", statusKey: "audit" },

  // ── Audit lane · ingestion (workflows) ─────────────────────────────────
  { id: "wf-acquire-audit", kind: "workflow", layer: "ingestion", lane: "audit", label: "acquire-audit", sublabel: "Sun 04:00 · discover + download (no extract)", workflowFile: "acquire-audit.yml" },
  { id: "wf-refresh-audit", kind: "workflow", layer: "ingestion", lane: "audit", label: "refresh-audit", sublabel: "manual · extract → validate → push", workflowFile: "refresh-audit.yml" },
  { id: "wf-reextract", kind: "workflow", layer: "ingestion", lane: "audit", label: "reextract-statement", sublabel: "manual · one lane (oci/cf/equity/…)", workflowFile: "reextract-statement.yml" },
  { id: "wf-backfill-audit", kind: "workflow", layer: "ingestion", lane: "audit", label: "backfill-audit", sublabel: "manual · full re-extract (5-bank chunks)", workflowFile: "backfill-audit.yml" },

  // ── Audit lane · storage ───────────────────────────────────────────────
  { id: "store-r2-pdf", kind: "store", layer: "storage", lane: "audit", label: "R2 · PDF bucket", sublabel: "bddk-audit-reports/<ticker>/*.pdf" },
  { id: "store-d1-audit-fin", kind: "store", layer: "storage", lane: "audit", label: "D1 · bank_audit financials", sublabel: "balance_sheet · profit_loss · oci · cash_flow · equity_change", statusKey: "audit:balance_sheet" },
  { id: "store-d1-audit-credit", kind: "store", layer: "storage", lane: "audit", label: "D1 · bank_audit credit", sublabel: "credit_quality · stages · npl_movement · loans_by_sector", statusKey: "audit:stages" },
  { id: "store-d1-audit-reg", kind: "store", layer: "storage", lane: "audit", label: "D1 · bank_audit §4", sublabel: "capital · liquidity", statusKey: "audit:capital" },
  { id: "store-d1-audit-spine", kind: "store", layer: "storage", lane: "audit", label: "D1 · coverage spine", sublabel: "coverage · expected · validation · empty-copy guarded", statusKey: "audit:coverage" },

  // ── Shared · infra & ops ───────────────────────────────────────────────
  { id: "wf-ci", kind: "workflow", layer: "ingestion", lane: "shared", label: "ci", sublabel: "on PR · ruff + pytest + eslint + tsc + vitest", workflowFile: "ci.yml" },
  { id: "wf-deploy", kind: "workflow", layer: "ingestion", lane: "shared", label: "deploy-cloudflare", sublabel: "push web/** · D1 migrate + build + deploy", workflowFile: "deploy-cloudflare.yml" },
  { id: "store-r2-snap", kind: "store", layer: "storage", lane: "shared", label: "R2 · DB snapshots", sublabel: "state/*.db.gz + dated history (7 kept)" },
  { id: "store-kv", kind: "store", layer: "storage", lane: "shared", label: "KV · page cache", sublabel: "NEXT_INC_CACHE_KV · 12h TTL on D1 reads" },
  { id: "wf-healthcheck", kind: "workflow", layer: "page", lane: "shared", label: "healthcheck", sublabel: "daily 06:00 · freshness + chart-spec alert", workflowFile: "healthcheck.yml" },

  // ── Bulletin lane · pages ──────────────────────────────────────────────
  { id: "page-overview", kind: "page", layer: "page", lane: "bulletin", label: "Overview", sublabel: "/", href: "/" },
  { id: "page-credit", kind: "page", layer: "page", lane: "bulletin", label: "Credit", sublabel: "/credit", href: "/credit" },
  { id: "page-deposits", kind: "page", layer: "page", lane: "bulletin", label: "Deposits", sublabel: "/deposits", href: "/deposits" },
  { id: "page-asset-quality", kind: "page", layer: "page", lane: "bulletin", label: "Asset Quality", sublabel: "/asset-quality", href: "/asset-quality" },
  { id: "page-capital", kind: "page", layer: "page", lane: "bulletin", label: "Capital", sublabel: "/capital", href: "/capital" },
  { id: "page-profitability", kind: "page", layer: "page", lane: "bulletin", label: "Profitability", sublabel: "/profitability · NIM components", href: "/profitability" },
  { id: "page-ratios", kind: "page", layer: "page", lane: "bulletin", label: "Ratios", sublabel: "/sector/ratios", href: "/sector/ratios" },
  { id: "page-weekly", kind: "page", layer: "page", lane: "bulletin", label: "Weekly", sublabel: "/weekly", href: "/weekly" },
  { id: "page-rates", kind: "page", layer: "page", lane: "bulletin", label: "Rates", sublabel: "/rates", href: "/rates" },
  { id: "page-liquidity", kind: "page", layer: "page", lane: "bulletin", label: "Liquidity", sublabel: "/liquidity", href: "/liquidity" },
  { id: "page-economy", kind: "page", layer: "page", lane: "bulletin", label: "Economy", sublabel: "/economy", href: "/economy" },
  { id: "page-economy-bop", kind: "page", layer: "page", lane: "bulletin", label: "Balance of Payments", sublabel: "/economy/balance-of-payments", href: "/economy/balance-of-payments" },
  { id: "page-economy-growth", kind: "page", layer: "page", lane: "bulletin", label: "Economic Growth", sublabel: "/economy/economic-growth", href: "/economy/economic-growth" },
  { id: "page-economy-budget", kind: "page", layer: "page", lane: "bulletin", label: "Budget", sublabel: "/economy/budget", href: "/economy/budget" },
  { id: "page-economy-inflation", kind: "page", layer: "page", lane: "bulletin", label: "Inflation", sublabel: "/economy/inflation", href: "/economy/inflation" },
  { id: "page-economy-trade", kind: "page", layer: "page", lane: "bulletin", label: "Foreign Trade", sublabel: "/economy/foreign-trade", href: "/economy/foreign-trade" },
  { id: "page-digital", kind: "page", layer: "page", lane: "bulletin", label: "Digital", sublabel: "/digital", href: "/digital" },
  { id: "page-funds", kind: "page", layer: "page", lane: "bulletin", label: "Funds", sublabel: "/funds", href: "/funds" },
  { id: "page-franchise", kind: "page", layer: "page", lane: "bulletin", label: "Franchise", sublabel: "/franchise · branch/ATM/customer footprint", href: "/franchise" },
  { id: "page-nonbank", kind: "page", layer: "page", lane: "bulletin", label: "Non-Bank", sublabel: "/non-bank", href: "/non-bank" },
  { id: "page-nonbank-share", kind: "page", layer: "page", lane: "bulletin", label: "Share of Banking", sublabel: "/non-bank/share-of-banking", href: "/non-bank/share-of-banking" },
  { id: "page-ownership", kind: "page", layer: "page", lane: "bulletin", label: "Ownership", sublabel: "/ownership", href: "/ownership" },
  { id: "page-regulation", kind: "page", layer: "page", lane: "bulletin", label: "Regulation", sublabel: "/regulation", href: "/regulation" },
  { id: "page-news", kind: "page", layer: "page", lane: "bulletin", label: "News", sublabel: "/news", href: "/news" },
  { id: "page-earnings", kind: "page", layer: "page", lane: "bulletin", label: "Earnings", sublabel: "/earnings · results calendar + presentation decks", href: "/earnings" },

  // ── Audit lane · pages ─────────────────────────────────────────────────
  { id: "page-banks", kind: "page", layer: "page", lane: "audit", label: "Banks", sublabel: "/banks", href: "/banks" },
  { id: "page-bank-detail", kind: "page", layer: "page", lane: "audit", label: "Bank detail", sublabel: "/banks/[ticker] · Sankey, ownership, valuation", href: "/banks" },
  { id: "page-cross-bank", kind: "page", layer: "page", lane: "audit", label: "Compare", sublabel: "/cross-bank · performance heatmap", href: "/cross-bank" },

  // ── Shared · pages ─────────────────────────────────────────────────────
  { id: "page-admin", kind: "page", layer: "page", lane: "shared", label: "Admin", sublabel: "/admin · health · triggers · coverage matrix", href: "/admin" },
];

// ---------------------------------------------------------------------------
// Edges
// ---------------------------------------------------------------------------

export const PIPELINE_EDGES: PipelineEdge[] = [
  // sources → bulletin workflows
  { source: "src-bddk-monthly", target: "wf-bddk-bulletins" },
  { source: "src-bddk-monthly", target: "wf-refresh-data" },
  { source: "src-bddk-weekly", target: "wf-bddk-bulletins" },
  { source: "src-bddk-weekly", target: "wf-refresh-data" },
  { source: "src-bddk-nonbank", target: "wf-bddk-bulletins" },
  { source: "src-bddk-nonbank", target: "wf-refresh-data" },
  { source: "src-bddk-nonbank", target: "wf-backfill-nonbank" },
  { source: "src-evds", target: "wf-evds-daily" },
  { source: "src-evds", target: "wf-refresh-data" },
  { source: "src-tuik", target: "wf-evds-daily" },
  { source: "src-tbb-digital", target: "wf-evds-daily" },
  { source: "src-tbb-acq", target: "wf-refresh-data" },
  { source: "src-kap", target: "wf-evds-daily" },
  { source: "src-tefas", target: "wf-evds-daily" },
  { source: "src-tefas", target: "wf-backfill-tefas" },
  { source: "src-faaliyet", target: "wf-backfill-faaliyet" },
  { source: "src-faaliyet", target: "wf-refresh-data" },
  { source: "src-yahoo", target: "wf-evds-daily" },
  { source: "src-rss-reg", target: "wf-news-daily" },
  { source: "src-rss-reg", target: "wf-summarize" },
  { source: "src-rss-press", target: "wf-news-daily" },
  { source: "src-rss-google", target: "wf-news-daily" },
  { source: "src-kap", target: "wf-news-daily" },
  { source: "src-ir-presentations", target: "wf-presentations" },

  // bulletin workflows → D1 stores
  { source: "wf-evds-daily", target: "store-d1-evds" },
  { source: "wf-evds-daily", target: "store-d1-tbb" },
  { source: "wf-evds-daily", target: "store-d1-kap" },
  { source: "wf-evds-daily", target: "store-d1-tefas" },
  { source: "wf-evds-daily", target: "store-d1-bist" },
  { source: "wf-bddk-bulletins", target: "store-d1-bulletin" },
  { source: "wf-bddk-bulletins", target: "store-d1-nonbank" },
  { source: "wf-refresh-data", target: "store-d1-bulletin" },
  { source: "wf-refresh-data", target: "store-d1-nonbank" },
  { source: "wf-backfill-nonbank", target: "store-d1-nonbank" },
  { source: "wf-refresh-data", target: "store-d1-evds" },
  { source: "wf-refresh-data", target: "store-d1-tbb" },
  { source: "wf-refresh-data", target: "store-d1-tefas" },
  { source: "wf-backfill-tefas", target: "store-d1-tefas" },
  { source: "wf-backfill-faaliyet", target: "store-d1-faaliyet" },
  { source: "wf-refresh-data", target: "store-d1-faaliyet" },
  { source: "wf-news-daily", target: "store-d1-news" },
  { source: "wf-summarize", target: "store-d1-news" },
  { source: "wf-news-daily", target: "store-d1-earnings" },
  { source: "wf-presentations", target: "store-d1-earnings" },

  // audit lane
  { source: "src-ir-pdf", target: "wf-acquire-audit" },
  { source: "wf-acquire-audit", target: "store-r2-pdf" },
  { source: "wf-acquire-audit", target: "store-d1-audit-spine" },
  { source: "store-r2-pdf", target: "wf-refresh-audit" },
  { source: "store-r2-pdf", target: "wf-reextract" },
  { source: "store-r2-pdf", target: "wf-backfill-audit" },
  { source: "wf-refresh-audit", target: "store-d1-audit-fin" },
  { source: "wf-refresh-audit", target: "store-d1-audit-credit" },
  { source: "wf-refresh-audit", target: "store-d1-audit-reg" },
  { source: "wf-refresh-audit", target: "store-d1-audit-spine", kind: "guard" },
  { source: "wf-reextract", target: "store-d1-audit-fin" },
  { source: "wf-reextract", target: "store-d1-audit-credit" },
  { source: "wf-backfill-audit", target: "store-d1-audit-fin" },
  { source: "wf-backfill-audit", target: "store-d1-audit-credit" },
  { source: "wf-backfill-audit", target: "store-d1-audit-reg" },

  // R2 snapshots (push side)
  { source: "wf-refresh-data", target: "store-r2-snap", kind: "snapshot" },
  { source: "wf-refresh-audit", target: "store-r2-snap", kind: "snapshot" },
  { source: "wf-presentations", target: "store-r2-snap", kind: "snapshot" },

  // D1 (bulletin) → pages
  { source: "store-d1-bulletin", target: "page-overview" },
  { source: "store-d1-bulletin", target: "page-credit" },
  { source: "store-d1-bulletin", target: "page-deposits" },
  { source: "store-d1-bulletin", target: "page-asset-quality" },
  { source: "store-d1-bulletin", target: "page-capital" },
  { source: "store-d1-bulletin", target: "page-profitability" },
  { source: "store-d1-bulletin", target: "page-ratios" },
  { source: "store-d1-bulletin", target: "page-weekly" },
  { source: "store-d1-bulletin", target: "page-rates" },
  { source: "store-d1-bulletin", target: "page-liquidity" },
  { source: "store-d1-bulletin", target: "page-economy" },

  // D1 (evds) → pages
  { source: "store-d1-evds", target: "page-economy" },
  { source: "store-d1-evds", target: "page-economy-bop" },
  { source: "store-d1-evds", target: "page-economy-growth" },
  { source: "store-d1-evds", target: "page-economy-budget" },
  { source: "store-d1-evds", target: "page-economy-inflation" },
  { source: "store-d1-evds", target: "page-economy-trade" },
  { source: "store-d1-evds", target: "page-rates" },
  { source: "store-d1-evds", target: "page-liquidity" },

  // D1 (market / sector aggregates) → pages
  { source: "store-d1-bist", target: "page-economy" },
  { source: "store-d1-bist", target: "page-bank-detail" },
  { source: "store-d1-bist", target: "page-cross-bank" },
  { source: "store-d1-tbb", target: "page-digital" },
  { source: "store-d1-tefas", target: "page-funds" },
  { source: "store-d1-faaliyet", target: "page-franchise" },
  { source: "store-d1-nonbank", target: "page-nonbank" },
  { source: "store-d1-nonbank", target: "page-nonbank-share" },
  { source: "store-d1-bulletin", target: "page-nonbank-share" },
  { source: "store-d1-kap", target: "page-ownership" },
  { source: "store-d1-kap", target: "page-bank-detail" },
  { source: "store-d1-news", target: "page-regulation" },
  { source: "store-d1-news", target: "page-news" },
  { source: "store-d1-earnings", target: "page-earnings" },
  { source: "store-d1-earnings", target: "page-bank-detail" },

  // D1 (audit) → pages
  { source: "store-d1-audit-fin", target: "page-banks" },
  { source: "store-d1-audit-fin", target: "page-bank-detail" },
  { source: "store-d1-audit-fin", target: "page-cross-bank" },
  { source: "store-d1-audit-credit", target: "page-bank-detail" },
  { source: "store-d1-audit-credit", target: "page-cross-bank" },
  { source: "store-d1-audit-credit", target: "page-asset-quality" },
  { source: "store-d1-audit-reg", target: "page-bank-detail" },
  { source: "store-d1-audit-reg", target: "page-cross-bank" },
  { source: "store-d1-audit-reg", target: "page-capital" },
  { source: "store-d1-audit-reg", target: "page-liquidity" },
  { source: "store-d1-audit-spine", target: "page-admin" },

  // cache layer
  { source: "store-d1-bulletin", target: "store-kv", kind: "snapshot" },
  { source: "store-kv", target: "page-overview" },

  // ops & monitoring
  { source: "wf-ci", target: "wf-deploy", kind: "guard" },
  { source: "wf-deploy", target: "store-kv", kind: "snapshot" },
  { source: "store-d1-bulletin", target: "wf-healthcheck" },
  { source: "store-d1-audit-fin", target: "wf-healthcheck" },
];
