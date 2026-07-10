"use client";

/**
 * Peer relative-value chart: each listed bank as a point of (ROE, P/B), with an
 * OLS fit line. Banks above the line trade rich for their returns, below cheap —
 * the analyst's first-pass "where's the value" read. Click a point to load that
 * bank into the per-bank model. ROE is shown in percent on the x-axis.
 */
import {
  CartesianGrid,
  Cell,
  LabelList,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartCard } from "@/app/components/ui";
import { useChartTheme, tooltipStyles } from "@/app/lib/chart-theme";
import { nf } from "@/app/lib/chart-format";
import type { PbRoeRegression } from "@/app/lib/valuation";

export interface ScatterPoint {
  ticker: string;
  /** ROE, fraction. */
  roe: number;
  /** Observed P/B, multiple. */
  pb: number;
}

interface Props {
  points: ScatterPoint[];
  regression: PbRoeRegression | null;
  selected?: string;
  onSelect?: (ticker: string) => void;
}

export function PbRoeScatter({ points, regression, selected, onSelect }: Props) {
  const t = useChartTheme();
  const tt = tooltipStyles(t);

  const data = points.map((p) => ({
    x: p.roe * 100,
    y: p.pb,
    ticker: p.ticker,
    fitted: regression ? regression.predict(p.roe) : null,
  }));

  const xs = points.map((p) => p.roe);
  const minR = Math.min(...xs);
  const maxR = Math.max(...xs);
  const segment: [{ x: number; y: number }, { x: number; y: number }] | undefined =
    regression && points.length >= 2
      ? [
          { x: minR * 100, y: regression.predict(minR) },
          { x: maxR * 100, y: regression.predict(maxR) },
        ]
      : undefined;

  const action = regression ? (
    <span className="text-xs text-muted-foreground">
      P/B ≈ {nf(regression.intercept, 2)} + {nf(regression.slope, 2)}·ROE · R² {nf(regression.r2, 2)}
    </span>
  ) : null;

  return (
    <ChartCard
      title="Valuation vs peers — P/B against ROE"
      description="Listed banks; points above the fit trade rich for their returns, below cheap. Click to load a bank."
      action={action}
    >
      <div style={{ height: 360 }} className="cursor-pointer">
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 16, right: 24, left: 8, bottom: 28 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={t.grid} />
            <XAxis
              type="number"
              dataKey="x"
              name="ROE"
              tick={{ fontSize: 11, fill: t.axis }}
              tickFormatter={(v) => `${nf(Number(v), 0)}%`}
              axisLine={{ stroke: t.grid }}
              tickLine={{ stroke: t.grid }}
              label={{ value: "ROE (TTM)", position: "insideBottom", offset: -16, fontSize: 11, fill: t.axis }}
            />
            <YAxis
              type="number"
              dataKey="y"
              name="P/B"
              tick={{ fontSize: 11, fill: t.axis }}
              tickFormatter={(v) => `${nf(Number(v), 1)}×`}
              axisLine={{ stroke: t.grid }}
              tickLine={{ stroke: t.grid }}
              label={{ value: "Price / Book", angle: -90, position: "insideLeft", fontSize: 11, fill: t.axis }}
            />
            <Tooltip
              {...tt}
              cursor={{ stroke: t.grid }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const p = payload[0].payload as (typeof data)[number];
                const resid = p.fitted != null ? p.y - p.fitted : null;
                return (
                  <div style={tt.contentStyle}>
                    <div style={tt.labelStyle}>{p.ticker}</div>
                    <div>ROE {nf(p.x, 1)}%</div>
                    <div>P/B {nf(p.y, 2)}×</div>
                    {p.fitted != null && <div>Fitted {nf(p.fitted, 2)}×</div>}
                    {resid != null && (
                      <div>
                        {resid >= 0 ? "Rich" : "Cheap"} {nf(Math.abs(resid), 2)}×
                      </div>
                    )}
                  </div>
                );
              }}
            />
            {segment && (
              <ReferenceLine
                ifOverflow="extendDomain"
                stroke={t.reference}
                strokeDasharray="5 4"
                segment={segment}
              />
            )}
            <Scatter
              data={data}
              isAnimationActive={false}
              onClick={(d) => {
                const item = d as unknown as { ticker?: string; payload?: { ticker?: string } };
                const tk = item.ticker ?? item.payload?.ticker;
                if (tk) onSelect?.(tk);
              }}
            >
              {data.map((d) => (
                <Cell
                  key={d.ticker}
                  fill={d.ticker === selected ? t.palette[0] : t.palette[1]}
                  fillOpacity={d.ticker === selected ? 1 : 0.55}
                  stroke={d.ticker === selected ? t.palette[0] : "transparent"}
                  strokeWidth={2}
                />
              ))}
              <LabelList dataKey="ticker" position="top" style={{ fontSize: 10, fill: t.axis }} />
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}
