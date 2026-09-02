"use client";

/**
 * One measure across several bank groups, faceted on a shared y-scale.
 *
 * The combined TrendChart remains the right form when the crossing of lines is
 * the question. This component is for the more common sector-page question:
 * how each ownership group moved, and how their latest levels compare. Keeping
 * one line per panel removes label collisions without surrendering a common
 * scale.
 */
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartCard } from "@/app/components/ui/chart-card";
import { ChartData } from "@/app/components/ui/chart-csv";
import { useChartFormat } from "@/i18n/use-chart-format";
import { useText } from "@/i18n/use-text";
import {
  crosshairCursor,
  tooltipStyles,
  useChartTheme,
} from "@/app/lib/chart-theme";
import { type FormatKind } from "@/app/lib/chart-format";
import { useRangeFilter } from "@/app/lib/use-date-range";
import { cn } from "@/app/lib/cn";

export interface SmallMultiplePoint {
  period: string;
  bank_type_code: string;
  value: number | null;
}

interface Props {
  data: SmallMultiplePoint[];
  seriesLabels: Record<string, string>;
  title?: React.ReactNode;
  description?: React.ReactNode;
  source?: React.ReactNode;
  yFormat?: FormatKind;
  decimals?: number;
  zeroLine?: boolean;
  deltaPeriods?: number;
  deltaLabel?: string;
  height?: number;
  columns?: 2 | 3;
  plain?: boolean;
  /** Shared event marker, for example a detected level shift. */
  referencePeriod?: string;
  referenceLabel?: string;
}

const GROUP_ORDER = ["Sector", "State", "Private", "Domestic", "Foreign", "Participation", "Dev & Inv"];

const COLS: Record<2 | 3, string> = {
  2: "sm:grid-cols-2",
  3: "sm:grid-cols-2 xl:grid-cols-3",
};

function signed(value: number, formatted: string): string {
  const sign = value >= 0 ? "+" : "−";
  const clean = formatted.replace(/^[+−-]/, "");
  const prefix = clean.match(/^[^\d.,]+/)?.[0] ?? "";
  return `${prefix}${sign}${clean.slice(prefix.length)}`;
}

export default function SmallMultiplesTrend({
  data,
  seriesLabels,
  title,
  description,
  source,
  yFormat = "raw",
  decimals = 1,
  zeroLine = false,
  deltaPeriods = 12,
  deltaLabel = "12m",
  height = 142,
  columns = 3,
  plain = true,
  referencePeriod,
  referenceLabel,
}: Props) {
  const tx = useText();
  const t = useChartTheme();
  const tt = tooltipStyles(t);
  const formatters = useChartFormat();
  const fmt = formatters[yFormat];
  const { filtered } = useRangeFilter(data, (row) => row.period);

  const rank = (code: string) => {
    const i = GROUP_ORDER.indexOf(seriesLabels[code]);
    return i === -1 ? Number.MAX_SAFE_INTEGER : i;
  };
  const codes = Object.keys(seriesLabels).sort((a, b) => rank(a) - rank(b));
  const grouped = codes.map((code) => ({
    code,
    rows: filtered
      .filter((row) => row.bank_type_code === code && row.value != null)
      .map((row) => ({ period: row.period, value: row.value as number }))
      .sort((a, b) => a.period.localeCompare(b.period)),
  })).filter((group) => group.rows.length > 0);

  const values = grouped.flatMap((group) => group.rows.map((row) => row.value));
  let min = values.length ? Math.min(...values) : 0;
  let max = values.length ? Math.max(...values) : 1;
  if (zeroLine) {
    min = Math.min(0, min);
    max = Math.max(0, max);
  }
  const span = max - min || Math.max(Math.abs(max), 1);
  const domain: [number, number] = [min - span * 0.08, max + span * 0.08];

  return (
    <ChartCard
      title={tx(title)}
      description={tx(description)}
      source={tx(source)}
      plain={plain}
      bodyClassName="max-w-[64rem]"
    >
      <ChartData
        table={{
          columns: ["Period", "Group", "Value"],
          rows: grouped.flatMap((group) =>
            group.rows.map((row) => [row.period, tx(seriesLabels[group.code]), row.value]),
          ),
        }}
      />
      <div
        data-small-multiples
        className={cn("grid grid-cols-1 border-l border-t border-hair", COLS[columns])}
      >
        {grouped.map((group) => {
          const current = group.rows.at(-1);
          const prior = group.rows.at(-1 - deltaPeriods);
          const delta = current && prior ? current.value - prior.value : null;
          const isSector = seriesLabels[group.code] === "Sector";
          const color = isSector ? t.hero : t.contextActive;
          return (
            <section
              key={group.code}
              className="min-w-0 border-b border-r border-hair px-3 pb-2.5 pt-2.5"
            >
              <div className="flex min-h-9 items-start justify-between gap-3">
                <div className="text-[11px] font-semibold leading-tight text-foreground">
                  {tx(seriesLabels[group.code])}
                </div>
                <div className="text-right font-mono tabular-nums">
                  <div className="text-[13px] font-semibold text-foreground">
                    {current ? tx(fmt(current.value, decimals)) : "—"}
                  </div>
                  <div className="text-[8px] uppercase tracking-[0.05em] text-faint">
                    {delta == null ? "—" : <>{tx(signed(delta, fmt(Math.abs(delta), decimals)))} · {tx(deltaLabel)}</>}
                  </div>
                </div>
              </div>
              <div style={{ height }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={group.rows} margin={{ top: 7, right: 5, bottom: 4, left: -12 }}>
                    <CartesianGrid vertical={false} stroke={t.grid} />
                    <XAxis
                      dataKey="period"
                      interval="preserveStartEnd"
                      minTickGap={55}
                      tickFormatter={(value) => tx(String(value).slice(0, 7))}
                      tick={{ fontSize: 8.5, fill: t.axis, fontFamily: "var(--font-geist-mono), monospace" }}
                      tickMargin={5}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      domain={domain}
                      width={43}
                      tickCount={3}
                      tickFormatter={(value) => fmt(Number(value), 0)}
                      tick={{ fontSize: 8.5, fill: t.axis, fontFamily: "var(--font-geist-mono), monospace" }}
                      axisLine={false}
                      tickLine={false}
                    />
                    {zeroLine && <ReferenceLine y={0} stroke={t.reference} strokeDasharray="3 3" />}
                    {referencePeriod && (
                      <ReferenceLine
                        x={referencePeriod}
                        stroke={t.reference}
                        strokeDasharray="3 3"
                        label={isSector && referenceLabel ? {
                          value: tx(referenceLabel),
                          position: "insideTopRight",
                          fill: t.axis,
                          fontSize: 8,
                        } : undefined}
                      />
                    )}
                    <Tooltip
                      {...tt}
                      cursor={crosshairCursor(t)}
                      labelFormatter={(label) => tx(String(label))}
                      formatter={(value) => [fmt(Number(value), decimals), tx(seriesLabels[group.code])]}
                    />
                    <Line
                      type="monotone"
                      dataKey="value"
                      name={tx(seriesLabels[group.code])}
                      stroke={color}
                      strokeWidth={isSector ? 2.5 : 2}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      dot={false}
                      activeDot={{ r: 3, fill: color, stroke: t.tooltipBg, strokeWidth: 1.5 }}
                      connectNulls
                      isAnimationActive={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </section>
          );
        })}
      </div>
    </ChartCard>
  );
}
