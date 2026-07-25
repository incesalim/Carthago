/**
 * Option 4, drawn honestly: the same series as a hand-rolled SVG line chart.
 *
 * No Recharts, no client component, no hydration — this renders on the server
 * and is inert. It is here so the comparison is fair: the question is not "can
 * we draw a line" (obviously) but "what do we lose", and the answer is visible
 * the moment you try to hover one of these.
 *
 * The repo already draws this way where the mark is fixed — Sparkline, the P&L
 * Sankey, the balance-sheet shapes — so this is an existing idiom, not a new one.
 */
import { SAMPLE, SAMPLE_LABELS } from "./sample";

const W = 760;
const H = 260;
const PAD = { t: 14, r: 54, b: 22, l: 38 };

const STROKE: Record<string, string> = {
  A: "var(--chart-1)",
  B: "var(--chart-2)",
  C: "var(--chart-4)",
};

export default function SvgLine() {
  const periods = [...new Set(SAMPLE.map((r) => r.period))].sort();
  const codes = [...new Set(SAMPLE.map((r) => r.bank_type_code))];
  const values = SAMPLE.map((r) => r.value).filter((v): v is number => v != null);
  const lo = Math.floor(Math.min(...values) - 0.5);
  const hi = Math.ceil(Math.max(...values) + 0.5);

  const x = (i: number) =>
    PAD.l + (i / (periods.length - 1)) * (W - PAD.l - PAD.r);
  const y = (v: number) =>
    PAD.t + (1 - (v - lo) / (hi - lo)) * (H - PAD.t - PAD.b);

  const ticks = [lo, (lo + hi) / 2, hi];

  return (
    <figure className="m-0">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        height={H}
        role="img"
        aria-label={`Sample trend of ${codes.length} series across ${periods.length} months`}
        className="overflow-visible"
      >
        {ticks.map((t) => (
          <g key={t}>
            <line
              x1={PAD.l}
              x2={W - PAD.r}
              y1={y(t)}
              y2={y(t)}
              stroke="var(--hair)"
              strokeWidth={1}
            />
            <text
              x={PAD.l - 6}
              y={y(t) + 3}
              textAnchor="end"
              className="font-mono"
              fontSize={9}
              fill="var(--faint)"
            >
              {t.toFixed(1)}
            </text>
          </g>
        ))}

        {codes.map((code) => {
          const pts = periods.map((p, i) => {
            const row = SAMPLE.find((r) => r.period === p && r.bank_type_code === code);
            return row?.value == null ? null : `${x(i)},${y(row.value)}`;
          });
          const d = pts.filter(Boolean).join(" ");
          const lastIdx = periods.length - 1;
          const lastRow = SAMPLE.find(
            (r) => r.period === periods[lastIdx] && r.bank_type_code === code,
          );
          return (
            <g key={code}>
              <polyline
                points={d}
                fill="none"
                stroke={STROKE[code]}
                strokeWidth={1.5}
                strokeLinejoin="round"
              />
              {lastRow?.value != null && (
                <text
                  x={x(lastIdx) + 6}
                  y={y(lastRow.value) + 3}
                  className="font-mono"
                  fontSize={9.5}
                  fill={STROKE[code]}
                >
                  {SAMPLE_LABELS[code]}
                </text>
              )}
            </g>
          );
        })}

        {[0, Math.floor(periods.length / 2), periods.length - 1].map((i) => (
          <text
            key={i}
            x={x(i)}
            y={H - 6}
            textAnchor={i === 0 ? "start" : i === periods.length - 1 ? "end" : "middle"}
            className="font-mono"
            fontSize={9}
            fill="var(--faint)"
          >
            {periods[i]}
          </text>
        ))}
      </svg>
      <figcaption className="mt-1 font-mono text-[8.5px] uppercase tracking-[0.05em] text-faint">
        Hand-rolled SVG · server-rendered · no hover, no crosshair, no export
      </figcaption>
    </figure>
  );
}
