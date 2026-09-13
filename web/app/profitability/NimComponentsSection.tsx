"use client";

/**
 * NIM-components shell: bank-group + view (annual / monthly TTM) toggles over
 * the signed stacked bar chart. All datasets are computed server-side and
 * passed in; this component only owns the two pill rows.
 */
import { useText } from "@/i18n/use-text";
import { useState } from "react";
import { ChartCard } from "@/app/components/ui/chart-card";
import NimComponentsChart, {
  type NimSeriesDef,
} from "./NimComponentsChart";
import {
  DEFAULT_NIM_GROUP,
  NIM_GROUPS,
  NIM_SERIES,
  type NimGroupDataset,
} from "@/app/lib/nim-components";

interface Props {
  datasets: Record<string, NimGroupDataset>;
  /** Latest monthly period ("YYYY-MM") — captions the annualized bar. */
  dataThrough?: string;
}

type ViewKind = "annual" | "monthly";

export default function NimComponentsSection({ datasets, dataThrough }: Props) {
  const tx = useText();
  const [groupKey, setGroupKey] = useState(DEFAULT_NIM_GROUP);
  const [view, setView] = useState<ViewKind>("annual");

  const group = NIM_GROUPS.find((g) => g.key === groupKey) ?? NIM_GROUPS[0];
  const dataset = datasets[group.key];
  const data = view === "annual" ? dataset?.annual : dataset?.ttm;

  // Participation banks pay profit shares on participation funds, not
  // deposit interest — relabel that bucket for the 10003 cut.
  const series: NimSeriesDef[] = NIM_SERIES.map((s) =>
    group.key === "participation" && s.key === "dep_exp"
      ? { key: s.key, label: "Participation funds" }
      : { key: s.key, label: s.label },
  );

  const pill = (
    active: boolean,
    label: string,
    onClick: () => void,
  ) => (
    <button
      key={label}
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`border-b-2 px-2 py-2 text-[11px] font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 ${
        active
          ? "border-foreground font-semibold text-foreground"
          : "border-transparent text-muted-foreground hover:text-foreground"
      }`}
    >
      {tx(label)}
    </button>
  );

  return (
    <ChartCard
      plain
      title={tx("NIM components — {0} (% of avg total assets, annualized)", {0: group.label})}
      description={
        tx(view === "annual"
          ? tx("Full-year interest income/expense over 13-month average assets; the trailing bar annualizes {0} YTD — actuals, not a forecast.", {0: dataThrough ?? "the current year"})
          : "Trailing-12-month interest income/expense over 13-month average total assets.")
      }
      action={
        <div className="flex min-w-0 max-w-full flex-wrap items-center gap-3">
          <div role="group" aria-label={tx("Bank group")} className="flex max-w-full flex-wrap items-center gap-0.5 border-b border-hair">
            {tx(NIM_GROUPS.map((g) =>
              pill(g.key === groupKey, g.label, () => setGroupKey(g.key)),
            ))}
          </div>
          <div role="group" aria-label={tx("Reporting period")} className="flex max-w-full flex-wrap items-center gap-0.5 border-b border-hair">
            {tx(pill(view === "annual", "Annual", () => setView("annual")))}
            {tx(pill(view === "monthly", "Monthly TTM", () => setView("monthly")))}
          </div>
        </div>
      }
    >
      {data && data.length > 0 ? (
        <NimComponentsChart data={data} series={series} mode={view} />
      ) : (
        <div className="flex h-[380px] items-center justify-center text-sm text-muted-foreground">{tx("No data for this group.")}</div>
      )}
    </ChartCard>
  );
}
