/**
 * /sector/ratios — retired.
 *
 * The by-bank-type Table-15 scorecard now lives as a `?type=`-driven section on
 * the Overview page (its only distinct value — the bank-type filter — was folded
 * in). This stub redirects old deep links to Overview, preserving the selected
 * bank type so a bookmark like `/sector/ratios?type=10006` lands on State.
 */
import { redirect } from "next/navigation";

export default async function RatiosPage({
  searchParams,
}: {
  searchParams: Promise<{ type?: string }>;
}) {
  const { type } = await searchParams;
  redirect(type ? `/?type=${type}#by-type` : "/#by-type");
}
