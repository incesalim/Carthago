"use client";

import { useState, type ReactNode } from "react";
import { ChartCard } from "./ui/chart-card";
import { ChartData } from "./ui/chart-csv";
import { seriesColor, useChartTheme } from "@/app/lib/chart-theme";
import type { FormatKind } from "@/app/lib/chart-format";
import { useChartFormat } from "@/i18n/use-chart-format";
import { useText } from "@/i18n/use-text";
import styles from "./sector-breakdown.module.css";

export interface BreakdownRow {
  id: string;
  label: string;
  values: Record<string, number | null>;
  total?: number | null;
}

export interface SectorBreakdownProps {
  data: BreakdownRow[];
  series: { key: string; label: string }[];
  mode?: "composition" | "ranking" | "paired";
  percent?: boolean;
  format?: FormatKind;
  decimals?: number;
  title: ReactNode;
  description?: ReactNode;
  source?: ReactNode;
  asOf?: string;
  maxValue?: number;
  totalLabel?: string;
  totalFormat?: FormatKind;
}

/** A dated cross-section: amounts remain inspectable beside the same marks and in CSV. */
export default function SectorBreakdown({
  data, series, mode = "ranking", percent = mode === "composition",
  format = "bn", decimals = 1, title, description, source, asOf, maxValue, totalLabel, totalFormat = "bn",
}: SectorBreakdownProps) {
  const tx = useText();
  const fmt = useChartFormat();
  const theme = useChartTheme();
  const [selected, setSelected] = useState<string | null>(null);
  const finite = (v: number | null | undefined): v is number => v != null && Number.isFinite(v);
  const values = (row: BreakdownRow) => series.map(s => row.values[s.key]);
  const complete = (row: BreakdownRow) => values(row).every(finite);
  const total = (row: BreakdownRow) => complete(row) ? values(row).reduce<number>((sum, v) => sum + v!, 0) : null;
  const show = (v: number | null | undefined) => {
    if (!finite(v)) return "—";
    const scale = format === "bn" ? 1000 : format === "trn" ? 1e6 : 1;
    const precision = scale > 1 && v !== 0 ? Math.min(3, Math.max(decimals, Math.ceil(-Math.log10(Math.abs(v) / scale)))) : decimals;
    return fmt[format](v, precision);
  };
  const stack = mode === "composition";
  const allValues = data.flatMap(row => stack ? [total(row)] : values(row)).filter(finite);
  const negative = !stack && allValues.some(v => v < 0);
  const min = negative ? Math.min(...allValues, 0) : 0;
  const max = Math.max(...allValues, maxValue ?? 0, 0);
  const extent = max - min || 1;
  const zero = -min / extent * 100;
  const color = (i: number) => seriesColor(theme, series[i].key, i, series[i].label);
  const selectedRow = data.find(row => row.id === selected);
  const available = allValues.length > 0;
  const unit = format === "bn" || format === "trn" ? tx("million TL") : format === "pct" ? "%" : "";
  const totalUnit = totalFormat === "bn" || totalFormat === "trn" ? tx("million TL") : totalFormat === "pct" ? "%" : "";
  const table = {
    columns: [`${tx("Category")}${asOf ? ` (${asOf})` : ""}`, ...series.map(s => `${tx(s.label)}${unit ? ` (${unit})` : ""}`),
      ...(totalLabel ? [`${tx(totalLabel)}${totalUnit ? ` (${totalUnit})` : ""}`] : [])],
    rows: data.map(row => [tx(row.label), ...values(row).map(v => finite(v) ? v : null),
      ...(totalLabel ? [finite(row.total) ? row.total : null] : [])]),
  };
  return <ChartCard plain title={title} description={description} bodyClassName={styles.body}
    source={<>{asOf && <p>{tx("Reporting period")}: {tx(asOf)}</p>}{source}</>}>
    <ChartData table={table} />
    {series.length > 1 && <div className={styles.legend}>{series.map((s, i) =>
      <span key={s.key}><i style={{ background: color(i) }} />{tx(s.label)}</span>)}</div>}
    {!available ? <p className={styles.empty}>{tx("No data available for this breakdown.")}</p> :
      <div className={styles.rows} data-sector-breakdown={mode}>
        {data.map(row => {
          const sum = total(row);
          const isComplete = complete(row);
          const denominator = row.total ?? sum;
          const shareReady = isComplete && sum != null && denominator != null && denominator > 0
            && Math.abs(sum - denominator) <= Math.max(5, Math.abs(denominator) * 1e-6)
            && values(row).every(v => v! >= 0);
          return <button key={row.id} type="button" className={styles.row} aria-pressed={selected === row.id}
            onClick={() => setSelected(selected === row.id ? null : row.id)}>
            <span className={styles.label}>{tx(row.label)}
              {stack && percent && format !== "pct" && <small>{show(denominator)}</small>}
            </span>
            <span className={styles.plot}>
              {stack ? <span className={styles.stack}>
                {(percent ? shareReady : isComplete) && series.map((s, i) => {
                  const v = row.values[s.key]!;
                  const width = percent ? v / denominator! * 100 : v / (max || 1) * 100;
                  return <span key={s.key} title={`${tx(s.label)}: ${show(v)}${shareReady ? ` · ${fmt.pct(v / denominator! * 100, 1)}` : ""}`}
                    style={{ width: `${Math.max(0, width)}%`, background: color(i) }} />;
                })}
              </span> : <span className={styles.pairs}>
                {series.map((s, i) => {
                  const v = row.values[s.key];
                  return <span className={styles.track} key={s.key}>
                    {negative && <i className={styles.zero} style={{ left: `${zero}%` }} />}
                    {finite(v) && <span className={styles.mark} style={{
                      left: `${v < 0 ? (v - min) / extent * 100 : zero}%`,
                      width: `${Math.abs(v) / extent * 100}%`, background: v < 0 ? theme.negative : color(i),
                    }} />}
                  </span>;
                })}
              </span>}
            </span>
            <span className={styles.readout}>
              {stack && percent ? <>{series.map((s, i) => <span key={s.key}>
                <i style={{ background: color(i) }} />{shareReady ? fmt.pct(row.values[s.key]! / denominator! * 100, 1) : "—"}
              </span>)}</> : stack ? show(row.total ?? sum) : series.map((s, i) =>
                <span key={s.key}>{series.length > 1 && <i style={{ background: color(i) }} />}{show(row.values[s.key])}</span>)}
            </span>
          </button>;
        })}
      </div>}
    {selectedRow && <div className={styles.detail} aria-live="polite">
      <strong>{tx(selectedRow.label)}</strong>
      <dl>{series.map((s, i) => <div key={s.key}><dt><i style={{ background: color(i) }} />{tx(s.label)}</dt><dd>{show(selectedRow.values[s.key])}</dd></div>)}</dl>
      {totalLabel && <dl><div><dt>{tx(totalLabel)}</dt><dd>{finite(selectedRow.total) ? fmt[totalFormat](selectedRow.total, decimals) : "—"}</dd></div></dl>}
    </div>}
  </ChartCard>;
}
