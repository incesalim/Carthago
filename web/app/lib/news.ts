/**
 * D1 queries for the qualitative-data layer (news_items table).
 *
 * Three sources, one table:
 *   - kap  → BIST disclosure platform (Turkish, per-ticker, regulator-mandated)
 *   - tcmb → CBRT press releases (English)
 *   - bddk → Banking regulator announcements (Turkish)
 *
 * Pipeline: scripts/sync_news.py → SQLite → push_to_d1.py → here.
 */
import { getDB } from "./db";

export type NewsSource = "kap" | "tcmb" | "bddk";

export interface NewsItem {
  source: NewsSource;
  external_id: string;
  published_at: string;
  ticker: string | null;
  category: string | null;
  title: string;
  summary: string | null;
  url: string;
  language: "tr" | "en";
  body_text?: string | null;     // full extracted body — only selected by newsBySource
}

const SOURCE_LABELS: Record<NewsSource, string> = {
  kap: "KAP",
  tcmb: "TCMB",
  bddk: "BDDK",
};

export function sourceLabel(s: string): string {
  return SOURCE_LABELS[s as NewsSource] ?? s.toUpperCase();
}

/** Latest items across all sources. */
export async function latestNews(limit = 100): Promise<NewsItem[]> {
  const db = await getDB();
  const { results } = await db
    .prepare(
      `SELECT source, external_id, published_at, ticker, category,
              title, summary, url, language
       FROM news_items
       ORDER BY published_at DESC
       LIMIT ?`,
    )
    .bind(limit)
    .all<NewsItem>();
  return results;
}

/** Latest items from a specific source. */
export async function newsBySource(
  source: NewsSource,
  limit = 100,
): Promise<NewsItem[]> {
  const db = await getDB();
  const { results } = await db
    .prepare(
      `SELECT source, external_id, published_at, ticker, category,
              title, summary, url, language, body_text
       FROM news_items
       WHERE source = ?
       ORDER BY published_at DESC
       LIMIT ?`,
    )
    .bind(source, limit)
    .all<NewsItem>();
  return results;
}

/** Latest KAP disclosures for one bank ticker. */
export async function newsByTicker(
  ticker: string,
  limit = 20,
): Promise<NewsItem[]> {
  const db = await getDB();
  const { results } = await db
    .prepare(
      `SELECT source, external_id, published_at, ticker, category,
              title, summary, url, language
       FROM news_items
       WHERE ticker = ?
       ORDER BY published_at DESC
       LIMIT ?`,
    )
    .bind(ticker.toUpperCase(), limit)
    .all<NewsItem>();
  return results;
}

/** Lookup table for {source}:{external_id} → {title, url} so the
 *  AI-generated briefing can render its cited source links inline. */
export async function newsLookupBySourceIds(
  pairs: { source: string; external_id: string }[],
): Promise<Map<string, { title: string; url: string; published_at: string }>> {
  const out = new Map<string, { title: string; url: string; published_at: string }>();
  if (pairs.length === 0) return out;
  const db = await getDB();
  // Build a (source,external_id) IN-list. D1 supports tuples via OR.
  const conditions = pairs.map(() => "(source = ? AND external_id = ?)").join(" OR ");
  const flat: string[] = [];
  for (const { source, external_id } of pairs) flat.push(source, external_id);
  const { results } = await db
    .prepare(
      `SELECT source, external_id, title, url, published_at FROM news_items
       WHERE ${conditions}`,
    )
    .bind(...flat)
    .all<{ source: string; external_id: string; title: string; url: string; published_at: string }>();
  for (const r of results) {
    out.set(`${r.source}:${r.external_id}`, { title: r.title, url: r.url, published_at: r.published_at });
  }
  return out;
}

/** Briefing types — mirrors the JSON structure stored in
 *  regulation_briefings.categories_json (validated server-side by
 *  scripts/summarize_regulations.py before insert). */
export interface BriefingBullet {
  text: string;
  source_ids: string[];          // "tcmb:ANO2026-19", "bddk:2286", ...
}
export interface BriefingCategory {
  name: string;
  bullets: BriefingBullet[];
}
export interface Briefing {
  generated_at: string;
  window_days: number;
  item_count: number;
  model: string;
  prompt_version: string;
  categories: BriefingCategory[];
}

/** Fetch the most recent regulatory briefing (null if none yet). */
export async function latestRegulationBriefing(): Promise<Briefing | null> {
  const db = await getDB();
  const { results } = await db
    .prepare(
      `SELECT generated_at, window_days, item_count, model, prompt_version, categories_json
       FROM regulation_briefings
       ORDER BY generated_at DESC
       LIMIT 1`,
    )
    .all<{
      generated_at: string;
      window_days: number;
      item_count: number;
      model: string;
      prompt_version: string;
      categories_json: string;
    }>();
  if (results.length === 0) return null;
  const row = results[0];
  let categories: BriefingCategory[] = [];
  try {
    const parsed = JSON.parse(row.categories_json);
    categories = parsed.categories ?? [];
  } catch {
    categories = [];
  }
  return {
    generated_at: row.generated_at,
    window_days: row.window_days,
    item_count: row.item_count,
    model: row.model,
    prompt_version: row.prompt_version,
    categories,
  };
}

/** Per-source counts and latest publish-time — used by the /news header. */
export async function newsSourceSummary(): Promise<
  { source: NewsSource; total: number; latest: string }[]
> {
  const db = await getDB();
  const { results } = await db
    .prepare(
      `SELECT source,
              COUNT(*) AS total,
              MAX(published_at) AS latest
       FROM news_items
       GROUP BY source
       ORDER BY source`,
    )
    .all<{ source: NewsSource; total: number; latest: string }>();
  return results;
}
