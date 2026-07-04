/**
 * /sector root — retired orphan (audit verdict: MERGE).
 *
 * The page duplicated the Overview total-assets snapshot and was reachable
 * only by direct URL (never in Nav). Overview owns the sector headline; the
 * former /sector/ratios by-bank-type scorecard is now the "Ratios by bank type"
 * section on Overview (that child now redirects there too).
 */
import { redirect } from "next/navigation";

export default function SectorPage() {
  redirect("/");
}
