"use client";

/**
 * NIM-components shell: bank-group + view (annual / monthly TTM) toggles over
 * the signed stacked bar chart. All datasets are computed server-side and
 * passed in; this component only owns the two pill rows.
 */
import { useState } from "react";
import { ChartCard } from "@/app/components/ui/chart-card";
import NimComponentsChart, {
  type NimSeriesDef,
} from "@/app/components/NimComponentsChart";
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
      className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
        active
          ? "bg-accent text-foreground"
          : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
      }`}
    >
      {label}
    </button>
  );

  return (
    <ChartCard
      title={`NIM components — ${group.label} (% of avg total assets, annualized)`}
      description={
        view === "annual"
          ? `Full-year interest income/expense over 13-month average assets; the trailing bar annualizes ${dataThrough ?? "the current year"} YTD — actuals, not a forecast.`
          : "Trailing-12-month interest income/expense over 13-month average total assets."
      }
      action={
        <div className="flex flex-wrap items-center justify-end gap-2">
          <div className="inline-flex items-center gap-0.5 rounded-lg border border-border bg-card p-0.5">
            {NIM_GROUPS.map((g) =>
              pill(g.key === groupKey, g.label, () => setGroupKey(g.key)),
            )}
          </div>
          <div className="inline-flex items-center gap-0.5 rounded-lg border border-border bg-card p-0.5">
            {pill(view === "annual", "Annual", () => setView("annual"))}
            {pill(view === "monthly", "Monthly TTM", () => setView("monthly"))}
          </div>
        </div>
      }
    >
      {data && data.length > 0 ? (
        <NimComponentsChart data={data} series={series} mode={view} />
      ) : (
        <div className="flex h-[380px] items-center justify-center text-sm text-muted-foreground">
          No data for this group.
        </div>
      )}
    </ChartCard>
  );
}
