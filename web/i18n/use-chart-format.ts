import { useLocale } from "next-intl";
import { createFormatters } from "@/app/lib/chart-format";

export function useChartFormat() {
  return createFormatters(useLocale());
}
