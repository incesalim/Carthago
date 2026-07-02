/**
 * /sector root — retired orphan (audit verdict: MERGE).
 *
 * The page duplicated the Overview total-assets snapshot and was reachable
 * only by direct URL (never in Nav). Overview owns the sector headline;
 * /sector/ratios (the by-bank-type scorecard) remains a real child route.
 */
import { redirect } from "next/navigation";

export default function SectorPage() {
  redirect("/");
}
