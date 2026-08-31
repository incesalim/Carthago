/**
 * /disclosures — retired 2026-07-15. The KAP feed is now classified by act on
 * /actions (27% of it was coupon-payment plumbing shown reverse-chronologically).
 * This stub redirects, preserving a ?ticker= filter → /actions?ticker=. The
 * route stays served so the /pipeline graph check passes. See docs/PROJECT_STATE.md.
 */
import { redirect } from "next/navigation";
import { firstQueryValue, type QueryValue } from "@/app/lib/query-params";

export const dynamic = "force-dynamic";

interface Props {
  searchParams: Promise<{ ticker?: QueryValue }>;
}

export default async function DisclosuresRedirect({ searchParams }: Props) {
  const ticker = firstQueryValue((await searchParams).ticker)?.trim();
  redirect(ticker ? `/actions?ticker=${encodeURIComponent(ticker.toUpperCase())}` : "/actions");
}
