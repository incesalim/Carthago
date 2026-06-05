/**
 * Cloudflare Web Analytics (RUM) summary for the traffic panel, via the GraphQL
 * Analytics API. Needs three values (all optional — the panel degrades to a
 * "not configured" state when any is missing):
 *   CF_ANALYTICS_TOKEN     account API token with Analytics: Read   (secret)
 *   CF_ANALYTICS_SITE_TAG  the Web Analytics site tag               (var)
 *   CF_ACCOUNT_TAG         Cloudflare account id                    (var)
 */
import { getEnv } from "./cf-env";

const GRAPHQL = "https://api.cloudflare.com/client/v4/graphql";

export interface TrafficSummary {
  configured: boolean;
  error?: string;
  rangeDays: number;
  pageViews: number;
  visits: number;
  topPaths: { path: string; views: number }[];
  daily: { date: string; views: number; visits: number }[];
}

const NOT_CONFIGURED: TrafficSummary = {
  configured: false,
  rangeDays: 7,
  pageViews: 0,
  visits: 0,
  topPaths: [],
  daily: [],
};

const QUERY = `
query Traffic($accountTag: String!, $siteTag: String!, $start: Time!, $end: Time!, $startDate: Date!, $endDate: Date!) {
  viewer {
    accounts(filter: { accountTag: $accountTag }) {
      totals: rumPageloadEventsAdaptiveGroups(
        limit: 1
        filter: { datetime_geq: $start, datetime_leq: $end, siteTag: $siteTag }
      ) {
        count
        sum { visits }
      }
      byPath: rumPageloadEventsAdaptiveGroups(
        limit: 10
        orderBy: [count_DESC]
        filter: { datetime_geq: $start, datetime_leq: $end, siteTag: $siteTag }
      ) {
        count
        dimensions { metric: requestPath }
      }
      byDay: rumPageloadEventsAdaptiveGroups(
        limit: 90
        orderBy: [date_ASC]
        filter: { date_geq: $startDate, date_leq: $endDate, siteTag: $siteTag }
      ) {
        count
        sum { visits }
        dimensions { date }
      }
    }
  }
}`;

interface GqlGroup {
  count: number;
  sum?: { visits?: number };
  dimensions?: { metric?: string; date?: string };
}

export async function getTrafficSummary(rangeDays = 7): Promise<TrafficSummary> {
  const env = await getEnv();
  const token = env.CF_ANALYTICS_TOKEN;
  const siteTag = env.CF_ANALYTICS_SITE_TAG;
  const accountTag = env.CF_ACCOUNT_TAG;
  if (!token || !siteTag || !accountTag) return { ...NOT_CONFIGURED, rangeDays };

  const end = new Date();
  const start = new Date(end.getTime() - rangeDays * 86_400_000);
  const variables = {
    accountTag,
    siteTag,
    start: start.toISOString(),
    end: end.toISOString(),
    startDate: start.toISOString().slice(0, 10),
    endDate: end.toISOString().slice(0, 10),
  };

  try {
    const res = await fetch(GRAPHQL, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query: QUERY, variables }),
    });
    if (!res.ok) {
      return { ...NOT_CONFIGURED, configured: true, rangeDays, error: `HTTP ${res.status}` };
    }
    const json = (await res.json()) as {
      errors?: { message: string }[];
      data?: {
        viewer?: {
          accounts?: { totals?: GqlGroup[]; byPath?: GqlGroup[]; byDay?: GqlGroup[] }[];
        };
      };
    };
    if (json.errors?.length) {
      return { ...NOT_CONFIGURED, configured: true, rangeDays, error: json.errors[0].message };
    }
    const acct = json.data?.viewer?.accounts?.[0];
    const totals = acct?.totals?.[0];
    return {
      configured: true,
      rangeDays,
      pageViews: totals?.count ?? 0,
      visits: totals?.sum?.visits ?? 0,
      topPaths: (acct?.byPath ?? []).map((g) => ({
        path: g.dimensions?.metric ?? "/",
        views: g.count,
      })),
      daily: (acct?.byDay ?? []).map((g) => ({
        date: g.dimensions?.date ?? "",
        views: g.count,
        visits: g.sum?.visits ?? 0,
      })),
    };
  } catch (e) {
    return {
      ...NOT_CONFIGURED,
      configured: true,
      rangeDays,
      error: e instanceof Error ? e.message : "request failed",
    };
  }
}
