"use client";

/**
 * Small pill marking a bank's BDDK aggregate group (Private / State / Foreign /
 * Participation / Dev & Inv). The colour is pulled from the SAME per-type
 * palette the sector charts use (chart-theme `seriesColor`), so a bank's badge
 * matches its line / legend colour across the dashboard. `label` is resolved
 * server-side (from metrics.ts BANK_TYPE_LABELS) and passed in, keeping the
 * server-only metrics module out of the client bundle.
 */
import { useChartTheme, seriesColor } from "@/app/lib/chart-theme";

export default function BankTypeBadge({
  code,
  label,
}: {
  code: string;
  label: string;
}) {
  const theme = useChartTheme();
  const hue = seriesColor(theme, code, 0);
  return (
    <span
      className="inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-[11px] font-medium leading-none whitespace-nowrap"
      style={{ color: hue, backgroundColor: `${hue}1f`, borderColor: `${hue}3d` }}
      title={`BDDK group: ${label}`}
    >
      {label}
    </span>
  );
}
