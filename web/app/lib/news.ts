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
              title, summary, url, language
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
