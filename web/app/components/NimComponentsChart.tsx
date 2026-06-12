"use client";

/**
 * Signed stacked bar chart for the NIM decomposition: income buckets stack
 * above zero, expense buckets below (values arrive already signed), with a
 * "Net NIM" line overlay. Mirrors the Garanti BBVA Research chart style —
 * in annual mode each sizeable segment carries its value label.
 */
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  LabelList,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useChartTheme, tooltipStyles } from "@/app/lib/chart-theme";
import { NIM_SERIES, type NimBarPoint, type NimKey } from "@/app/lib/nim-components";

// Topmost positive segment — the net-total label rides on it so its `y` is
// the top of the income stack.
const TOP_INCOME_KEY = NIM_SERIES.filter((s) => s.sign === 1).at(-1)!.key;

export interface NimSeriesDef {
  key: NimKey;
  label: string;
}

interface Props {
  data: NimBarPoint[];
  series: NimSeriesDef[];
  /** annual: wide bars + in-segment labels; monthly: dense TTM bars. */
  mode: "annual" | "monthly";
  height?: number;
}

// Component palette — 8 buckets exceed the 6-slot theme palette, and the BBVA
// reading (warm income hues vs cool/muted expense hues) is specific to this
// chart, so the colours live here. Keyed by NimKey, light/dark variants.
const FILLS: Record<"light" | "dark", Record<NimKey, string>> = {
  light: {
    cust_loans: "#1e3a8a",
    banks_cb: "#60a5fa",
    securities: "#43a047",
    other_inc: "#f59e0b",
    dep_exp: "#facc15",
    interbank_exp: "#06b6d4",
    debt_exp: "#8b5cf6",
    other_exp: "#9ca3af",
  },
  dark: {
    cust_loans: "#5b8def",
    banks_cb: "#93c5fd",
    securities: "#4ade80",
    other_inc: "#fbbf24",
    dep_exp: "#fde047",
    interbank_exp: "#22d3ee",
    debt_exp: "#a78bfa",
    other_exp: "#9ca3af",
  },
};

const nf = (v: number, d: number) =>
  new Intl.NumberFormat("en-US", {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  }).format(v);

/** Black or white label text depending on the segment fill's luminance. */
function labelColor(hexFill: string): string {
  const r = parseInt(hexFill.slice(1, 3), 16);
  const g = parseInt(hexFill.slice(3, 5), 16);
  const b = parseInt(hexFill.slice(5, 7), 16);
  return 0.299 * r + 0.587 * g + 0.114 * b > 150 ? "#1f2937" : "#ffffff";
}

// LabelList custom-content props (Recharts passes more; these are what we use).
interface SegmentLabelProps {
  x?: number | string;
  y?: number | string;
  width?: number | string;
  height?: number | string;
  value?: unknown;
}

/** In-segment value label — skipped when the segment is too short to fit. */
function segmentLabel(fill: string) {
  const Label = (props: SegmentLabelProps) => {
    const x = Number(props.x);
    const y = Number(props.y);
    const width = Number(props.width);
    const height = Number(props.height);
    const value = Number(props.value);
    if (!Number.isFinite(value) || Math.abs(height) < 13 || width < 30) {
      return null;
    }
    return (
      <text
        x={x + width / 2}
        y={y + height / 2}
        textAnchor="middle"
        dominantBaseline="central"
        fontSize={10}
        fill={labelColor(fill)}
      >
        {nf(value, 1)}%
      </text>
    );
  };
  Label.displayName = "NimSegmentLabel";
  return Label;
}

/** Net-NIM total floated above each bar. Attached to the TOPMOST income
 * segment with dataKey="net", so `y` is the top of the positive stack while
 * `value` is the bar's net total. */
function netTotalLabel(color: string) {
  const Label = (props: SegmentLabelProps) => {
    const x = Number(props.x);
    const y = Number(props.y);
    const width = Number(props.width);
    const value = Number(props.value);
    if (!Number.isFinite(value) || !Number.isFinite(x)) return null;
    return (
      <text
        x={x + width / 2}
        y={y - 7}
        textAnchor="middle"
        fontSize={11}
        fontWeight={600}
        fill={color}
      >
        {nf(value, 1)}%
      </text>
    );
  };
  Label.displayName = "NimNetTotalLabel";
  return Label;
}

export default function NimComponentsChart({
  data,
  series,
  mode,
  height = 380,
}: Props) {
  const t = useChartTheme();
  const tt = tooltipStyles(t);
  const isLight = t.palette[0] === "#7a0d2e";
  const fills = FILLS[isLight ? "light" : "dark"];
  // Brighter than the brand maroon — the line crosses the navy loans band
  // for most of its length and needs the extra contrast (plus the halo below).
  const netColor = isLight ? "#e11d48" : "#fb7185";

  const sign: Record<string, 1 | -1> = Object.fromEntries(
    NIM_SERIES.map((s) => [s.key, s.sign]),
  );
  const incomeSeries = series.filter((s) => sign[s.key] === 1);
  const expenseSeries = series.filter((s) => sign[s.key] === -1);

  // Grouped tooltip: income block, expense block (each with a subtotal),
  // then Net NIM — the default flat name:value list is unreadable with
  // nine series.
  const renderTooltip = ({
    active,
    payload,
    label,
  }: {
    active?: boolean;
    payload?: ReadonlyArray<{ payload?: unknown }>;
    label?: unknown;
  }) => {
    if (!active || !payload?.length) return null;
    const row = payload[0].payload as NimBarPoint;
    const sum = (defs: NimSeriesDef[]) =>
      defs.reduce((acc, s) => acc + (row[s.key] ?? 0), 0);

    const line = (s: NimSeriesDef) => (
      <div
        key={s.key}
        style={{ display: "flex", alignItems: "center", gap: 6 }}
      >
        <span
          style={{
            display: "inline-block",
            width: 9,
            height: 9,
            borderRadius: 2,
            background: fills[s.key],
            flex: "none",
          }}
        />
        <span style={{ color: t.axis }}>{s.label}</span>
        <span style={{ marginLeft: "auto", paddingLeft: 16, fontVariantNumeric: "tabular-nums" }}>
          {nf(row[s.key], 2)}%
        </span>
      </div>
    );

    const subtotal = (text: string, value: number) => (
      <div
        style={{
          display: "flex",
          fontWeight: 600,
          marginTop: 2,
          paddingTop: 2,
          borderTop: `1px solid ${t.tooltipBorder}`,
        }}
      >
        <span>{text}</span>
        <span style={{ marginLeft: "auto", paddingLeft: 16, fontVariantNumeric: "tabular-nums" }}>
          {nf(value, 2)}%
        </span>
      </div>
    );

    return (
      <div style={{ ...tt.contentStyle, minWidth: 230, lineHeight: 1.7 }}>
        <div style={tt.labelStyle}>{String(label)}</div>
        {incomeSeries.map(line)}
        {subtotal("Interest income", sum(incomeSeries))}
        <div style={{ height: 6 }} />
        {expenseSeries.map(line)}
        {subtotal("Interest expense", sum(expenseSeries))}
        <div
          style={{
            display: "flex",
            fontWeight: 700,
            color: netColor,
            marginTop: 6,
            paddingTop: 4,
            borderTop: `2px solid ${t.tooltipBorder}`,
          }}
        >
          <span>Net NIM</span>
          <span style={{ marginLeft: "auto", paddingLeft: 16, fontVariantNumeric: "tabular-nums" }}>
            {nf(row.net, 2)}%
          </span>
        </div>
      </div>
    );
  };

  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart
          data={data}
          stackOffset="sign"
          margin={{ top: mode === "annual" ? 22 : 10, right: 20, left: 10, bottom: 30 }}
          barCategoryGap={mode === "annual" ? "28%" : "12%"}
        >
          <CartesianGrid strokeDasharray="3 3" stroke={t.grid} />
          <XAxis
            dataKey="x"
            tick={{ fontSize: 11, fill: t.axis }}
            tickMargin={6}
            minTickGap={30}
            axisLine={{ stroke: t.grid }}
            tickLine={{ stroke: t.grid }}
          />
          <YAxis
            tick={{ fontSize: 11, fill: t.axis }}
            tickFormatter={(v) => `${nf(Number(v), 0)}%`}
            axisLine={{ stroke: t.grid }}
            tickLine={{ stroke: t.grid }}
          />
          <ReferenceLine y={0} stroke={t.reference} />
          <Tooltip cursor={{ fill: t.cursor }} content={renderTooltip} />
          <Legend
            wrapperStyle={{ fontSize: 11, paddingTop: 4 }}
            content={() => (
              // Render straight from `series` so the legend order matches the
              // stack; Recharts 3 otherwise reorders it.
              <ul
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  justifyContent: "center",
                  gap: "2px 14px",
                  listStyle: "none",
                  margin: 0,
                  padding: 0,
                }}
              >
                {series.map((s) => (
                  <li
                    key={s.key}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 5,
                      color: t.axis,
                    }}
                  >
                    <span
                      style={{
                        display: "inline-block",
                        width: 11,
                        height: 11,
                        borderRadius: 2,
                        background: fills[s.key],
                      }}
                    />
                    {s.label}
                  </li>
                ))}
                <li
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 5,
                    color: t.axis,
                  }}
                >
                  <span
                    style={{
                      display: "inline-block",
                      width: 14,
                      borderTop: `2px solid ${netColor}`,
                    }}
                  />
                  Net NIM
                </li>
              </ul>
            )}
          />
          {series.map((s) => (
            <Bar
              key={s.key}
              dataKey={s.key}
              name={s.label}
              stackId="nim"
              fill={fills[s.key]}
              isAnimationActive={false}
            >
              {mode === "annual" && (
                <LabelList dataKey={s.key} content={segmentLabel(fills[s.key])} />
              )}
              {mode === "annual" && s.key === TOP_INCOME_KEY && (
                <LabelList dataKey="net" content={netTotalLabel(netColor)} />
              )}
            </Bar>
          ))}
          {/* Halo under the net line: card-background casing keeps the line
              legible over the dark loans band and the yellow deposits band. */}
          <Line
            dataKey="net"
            stroke={t.tooltipBg}
            strokeWidth={5}
            strokeOpacity={0.9}
            dot={false}
            activeDot={false}
            legendType="none"
            tooltipType="none"
            isAnimationActive={false}
          />
          <Line
            dataKey="net"
            name="Net NIM"
            stroke={netColor}
            strokeWidth={2.25}
            dot={
              mode === "annual"
                ? { r: 3.5, fill: netColor, stroke: t.tooltipBg, strokeWidth: 1.5 }
                : false
            }
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
