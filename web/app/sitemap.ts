import type { MetadataRoute } from "next";
import { bankSummaries } from "@/app/lib/audit";

// Read D1 at request time (never at build — no Cloudflare context then), same
// as the pages. The per-bank query is itself KV-cached via `cachedAll`, so this
// doesn't hammer D1 on every crawl.
export const dynamic = "force-dynamic";

const BASE = "https://carthago.app";

type ChangeFrequency = NonNullable<
  MetadataRoute.Sitemap[number]["changeFrequency"]
>;

// "YYYYQN" → the quarter-end date, so <lastmod> reflects real data freshness
// (the latest reported period) rather than the deploy time. A stable, honest
// lastmod is what crawlers reward; a value that changes every request looks
// like noise. Returns undefined for anything that isn't a quarter period.
function quarterEndDate(period: string): Date | undefined {
  const m = /^(\d{4})Q([1-4])$/.exec(period);
  if (!m) return undefined;
  const year = Number(m[1]);
  const endMonth = Number(m[2]) * 3; // Q1→3, Q2→6, Q3→9, Q4→12
  const day = endMonth === 3 || endMonth === 12 ? 31 : 30;
  return new Date(Date.UTC(year, endMonth - 1, day));
}

// Public content routes, one per app/ folder, in rough nav order. `/admin` is
// password-gated and `/api/*` isn't content, so both are omitted. Per-bank
// drill-downs (`/banks/[ticker]`) are appended dynamically below.
const STATIC_ROUTES: {
  path: string;
  priority: number;
  changeFrequency: ChangeFrequency;
}[] = [
  { path: "/", priority: 1.0, changeFrequency: "daily" },
  // NB: /sector and /sector/ratios are intentionally omitted — both 307-redirect
  // to "/", and a sitemap must not list redirecting URLs.
  { path: "/banks", priority: 0.9, changeFrequency: "weekly" },
  { path: "/cross-bank", priority: 0.8, changeFrequency: "weekly" },
  { path: "/products", priority: 0.7, changeFrequency: "monthly" },
  { path: "/capital", priority: 0.8, changeFrequency: "weekly" },
  { path: "/liquidity", priority: 0.8, changeFrequency: "weekly" },
  { path: "/asset-quality", priority: 0.8, changeFrequency: "weekly" },
  { path: "/profitability", priority: 0.8, changeFrequency: "weekly" },
  { path: "/credit", priority: 0.8, changeFrequency: "weekly" },
  { path: "/deposits", priority: 0.8, changeFrequency: "weekly" },
  { path: "/rates", priority: 0.7, changeFrequency: "weekly" },
  { path: "/market-risk", priority: 0.7, changeFrequency: "weekly" },
  { path: "/ownership", priority: 0.6, changeFrequency: "monthly" },
  // /earnings and /disclosures 307-redirect to /actions since 2026-07-15 — a
  // sitemap must not list redirecting URLs, so only /actions appears.
  { path: "/actions", priority: 0.7, changeFrequency: "daily" },
  { path: "/regulation", priority: 0.7, changeFrequency: "weekly" },
  { path: "/news", priority: 0.7, changeFrequency: "daily" },
  { path: "/news/google", priority: 0.6, changeFrequency: "daily" },
  { path: "/digital", priority: 0.6, changeFrequency: "monthly" },
  { path: "/funds", priority: 0.6, changeFrequency: "daily" },
  { path: "/non-bank", priority: 0.6, changeFrequency: "monthly" },
  { path: "/non-bank/share-of-banking", priority: 0.5, changeFrequency: "monthly" },
  { path: "/economy", priority: 0.8, changeFrequency: "weekly" },
  { path: "/economy/inflation", priority: 0.6, changeFrequency: "monthly" },
  { path: "/economy/budget", priority: 0.6, changeFrequency: "monthly" },
  { path: "/economy/foreign-trade", priority: 0.6, changeFrequency: "monthly" },
  { path: "/economy/economic-growth", priority: 0.6, changeFrequency: "monthly" },
  { path: "/economy/balance-of-payments", priority: 0.6, changeFrequency: "monthly" },
  { path: "/pipeline", priority: 0.3, changeFrequency: "monthly" },
];

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  let banks: Awaited<ReturnType<typeof bankSummaries>> = [];
  try {
    banks = await bankSummaries();
  } catch {
    // If D1 is momentarily unavailable, still serve the static sitemap rather
    // than 500 the whole thing — per-bank URLs get picked up next crawl.
  }

  // The most recent reported quarter across all banks — the site's "data
  // updated" date, used as lastmod for the sector/aggregate pages. Falls back
  // to today only if D1 gave us nothing.
  const latestPeriod = banks.reduce(
    (mx, b) => (b.latest_period > mx ? b.latest_period : mx),
    "",
  );
  const dataDate = quarterEndDate(latestPeriod) ?? new Date();

  const staticEntries: MetadataRoute.Sitemap = STATIC_ROUTES.map((r) => ({
    url: `${BASE}${r.path}`,
    lastModified: dataDate,
    changeFrequency: r.changeFrequency,
    priority: r.priority,
  }));

  const bankEntries: MetadataRoute.Sitemap = banks.map((b) => ({
    url: `${BASE}/banks/${b.bank_ticker}`,
    lastModified: quarterEndDate(b.latest_period) ?? dataDate,
    changeFrequency: "weekly",
    priority: 0.7,
  }));

  return [...staticEntries, ...bankEntries];
}
