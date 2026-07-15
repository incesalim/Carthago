/**
 * /earnings — retired 2026-07-15. The earnings calendar + IR decks were folded
 * into /actions ("Results season"), which classifies the whole KAP filing
 * stream by act rather than showing a link directory. This stub keeps old links
 * and SEO alive by redirecting; the route stays served so the /pipeline graph
 * check (page-node hrefs must resolve) passes. See docs/PROJECT_STATE.md.
 */
import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

export default function EarningsRedirect() {
  redirect("/actions");
}
