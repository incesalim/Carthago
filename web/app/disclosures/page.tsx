/**
 * /disclosures — retired 2026-07-15. The KAP feed is now classified by act on
 * /actions (27% of it was coupon-payment plumbing shown reverse-chronologically).
 * This stub redirects, preserving a ?ticker= filter → /actions?ticker=. The
 * route stays served so the /pipeline graph check passes. See docs/PROJECT_STATE.md.
 */
import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

interface Props {
  searchParams: Promise<{ ticker?: string }>;
}

export default async function DisclosuresRedirect({ searchParams }: Props) {
  const { ticker } = await searchParams;
  redirect(ticker ? `/actions?ticker=${encodeURIComponent(ticker.toUpperCase())}` : "/actions");
}
