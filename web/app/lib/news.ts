/**
 * D1 queries for the qualitative-data layer (news_items table).
 *
 * Four sources, one table:
 *   - kap   → BIST disclosure platform (Turkish, per-ticker, regulator-mandated)
 *   - tcmb  → CBRT press releases (English)
 *   - bddk  → Banking regulator announcements (Turkish)
 *   - press → Banking-sector journalism from TR financial-media RSS feeds
 *             (headline + link + snippet only; the card links out, no body)
 *
 * Pipeline: scripts/sync_news.py → SQLite → push_to_d1.py → here.
 */
import { cachedAll } from "./db";

export type NewsSource = "kap" | "tcmb" | "bddk" | "press" | "google_news";

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
  tickers?: string | null;       // comma-joined bank tags (news_item_banks) —
                                 // only selected by latestPress/latestGoogleNews
}

const SOURCE_LABELS: Record<NewsSource, string> = {
  kap: "KAP",
  tcmb: "TCMB",
  bddk: "BDDK",
  press: "Press",
  google_news: "Google News",
};

export function sourceLabel(s: string): string {
  return SOURCE_LABELS[s as NewsSource] ?? s.toUpperCase();
}

/** Latest items across all sources. */
export async function latestNews(limit = 100): Promise<NewsItem[]> {
  return cachedAll<NewsItem>(
    `SELECT source, external_id, published_at, ticker, category,
              title, summary, url, language
       FROM news_items
       ORDER BY published_at DESC
       LIMIT ?`,
    [limit],
  );
}

/** Latest items from a specific source. */
export async function newsBySource(
  source: NewsSource,
  limit = 100,
): Promise<NewsItem[]> {
  return cachedAll<NewsItem>(
    `SELECT source, external_id, published_at, ticker, category,
              title, summary, url, language, body_text
       FROM news_items
       WHERE source = ?
       ORDER BY published_at DESC
       LIMIT ?`,
    [source, limit],
  );
}

/** Comma-joined bank tags for one item (news_item_banks junction, written by
 *  src/news/bank_tagger.py). Scalar subquery — no GROUP BY needed. */
const TICKERS_SUBQUERY = `(SELECT GROUP_CONCAT(b.ticker)
          FROM news_item_banks b
          WHERE b.source = n.source AND b.external_id = n.external_id) AS tickers`;

/** Latest banking-sector press items (source='press'). `category` holds the
 *  outlet name (e.g. "Bloomberg HT"). No body_text — these link out. */
export async function latestPress(limit = 120): Promise<NewsItem[]> {
  return cachedAll<NewsItem>(
    `SELECT n.source, n.external_id, n.published_at, n.ticker, n.category,
              n.title, n.summary, n.url, n.language,
              ${TICKERS_SUBQUERY}
       FROM news_items n
       WHERE n.source = 'press'
       ORDER BY n.published_at DESC
       LIMIT ?`,
    [limit],
  );
}

/** Latest Google News long-tail items (source='google_news'). `category` holds
 *  the publisher outlet (from the RSS <source url> tag). `url` is the resolved
 *  publisher link (falls back to the google redirect if a decode is pending).
 *  No body_text — these link out. */
export async function latestGoogleNews(limit = 160): Promise<NewsItem[]> {
  return cachedAll<NewsItem>(
    `SELECT n.source, n.external_id, n.published_at, n.ticker, n.category,
              n.title, n.summary, n.url, n.language,
              ${TICKERS_SUBQUERY}
       FROM news_items n
       WHERE n.source = 'google_news'
       ORDER BY n.published_at DESC
       LIMIT ?`,
    [limit],
  );
}

/** Press + Google News items tagged with one bank (news_item_banks junction)
 *  — the per-bank "In the News" feed on /banks/[ticker]. Cards link out. */
export async function pressNewsByBank(
  ticker: string,
  limit = 8,
): Promise<NewsItem[]> {
  return cachedAll<NewsItem>(
    `SELECT n.source, n.external_id, n.published_at, n.ticker, n.category,
              n.title, n.summary, n.url, n.language
       FROM news_item_banks b
       JOIN news_items n
         ON n.source = b.source AND n.external_id = b.external_id
       WHERE b.ticker = ?
       ORDER BY n.published_at DESC
       LIMIT ?`,
    [ticker.toUpperCase(), limit],
  );
}

/** Latest KAP disclosures for one bank ticker. */
export async function newsByTicker(
  ticker: string,
  limit = 20,
): Promise<NewsItem[]> {
  return cachedAll<NewsItem>(
    `SELECT source, external_id, published_at, ticker, category,
              title, summary, url, language
       FROM news_items
       WHERE ticker = ?
       ORDER BY published_at DESC
       LIMIT ?`,
    [ticker.toUpperCase(), limit],
  );
}

/** Lookup table for {source}:{external_id} → {title, url} so the
 *  AI-generated briefing can render its cited source links inline. */
export async function newsLookupBySourceIds(
  pairs: { source: string; external_id: string }[],
): Promise<Map<string, { title: string; url: string; published_at: string }>> {
  const out = new Map<string, { title: string; url: string; published_at: string }>();
  if (pairs.length === 0) return out;
  // Build a (source,external_id) IN-list. D1 supports tuples via OR.
  const conditions = pairs.map(() => "(source = ? AND external_id = ?)").join(" OR ");
  const flat: string[] = [];
  for (const { source, external_id } of pairs) flat.push(source, external_id);
  const results = await cachedAll<{ source: string; external_id: string; title: string; url: string; published_at: string }>(
    `SELECT source, external_id, title, url, published_at FROM news_items
       WHERE ${conditions}`,
    flat,
  );
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
  const results = await cachedAll<{
    generated_at: string;
    window_days: number;
    item_count: number;
    model: string;
    prompt_version: string;
    categories_json: string;
  }>(
    `SELECT generated_at, window_days, item_count, model, prompt_version, categories_json
       FROM regulation_briefings
       ORDER BY generated_at DESC
       LIMIT 1`,
    [],
  );
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
  return cachedAll<{ source: NewsSource; total: number; latest: string }>(
    `SELECT source,
              COUNT(*) AS total,
              MAX(published_at) AS latest
       FROM news_items
       GROUP BY source
       ORDER BY source`,
  );
}
