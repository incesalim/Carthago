/**
 * Reserves held against deposits — required reserves ÷ deposits, weekly.
 *
 * The rule states a ratio; this is the ratio that actually lands, after
 * exemptions and maturity mix. Two lines, no stack: the lira and FX legs are
 * different rules on different bases and summing them would mean nothing.
 */
import type { RatioPoint } from "@/app/lib/regulation";

const W = 560;
const H = 150;
const PAD = { l: 4, r: 48, t: 12, b: 18 };

export default function ReserveRatio({ series }: { series: RatioPoint[] }) {
  const pts = series.filter((p) => p.tl != null || p.fx != null);
  if (pts.length < 2) return null;

  const t0 = Date.parse(pts[0].date);
  const t1 = Date.parse(pts[pts.length - 1].date);
  const hi = Math.ceil(Math.max(...pts.map((p) => Math.max(p.fx ?? 0, p.tl ?? 0))) / 5) * 5 + 2;

  const x = (iso: string) => PAD.l + ((Date.parse(iso) - t0) / (t1 - t0)) * (W - PAD.l - PAD.r);
  const y = (v: number) => PAD.t + ((hi - v) / hi) * (H - PAD.t - PAD.b);

  const path = (pick: (p: RatioPoint) => number | null) => {
    const d = pts
      .filter((p) => pick(p) != null)
      .map((p) => `${x(p.date).toFixed(1)},${y(pick(p) as number).toFixed(1)}`);
    return d.length ? `M${d.join(" L")}` : "";
  };

  const last = (pick: (p: RatioPoint) => number | null) => {
    for (let i = pts.length - 1; i >= 0; i--) {
      const v = pick(pts[i]);
      if (v != null) return { date: pts[i].date, value: v };
    }
    return null;
  };

  const fxLast = last((p) => p.fx);
  const tlLast = last((p) => p.tl);
  const first = pts.find((p) => p.tl != null);

  const ticks: number[] = [];
  for (let v = 10; v < hi; v += 10) ticks.push(v);

  const years: number[] = [];
  for (let yr = new Date(t0).getUTCFullYear(); yr <= new Date(t1).getUTCFullYear(); yr++) years.push(yr);

  const axis = "font-mono text-[8px] fill-faint";

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="mt-2.5 block h-[150px] w-full overflow-visible"
      role="img"
      aria-label={`Required reserves as a share of deposits, weekly. Foreign currency is ${fxLast?.value.toFixed(1)} percent; lira is ${tlLast?.value.toFixed(1)} percent, up from ${first?.tl?.toFixed(2)} percent in ${first?.date.slice(0, 4)}.`}
    >
      {ticks.map((v) => (
        <g key={v}>
          <line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} stroke="var(--hair)" strokeWidth="1" />
          <text x={W - PAD.r + 5} y={y(v) + 3} className={axis}>
            {v}%
          </text>
        </g>
      ))}

      <path d={path((p) => p.fx)} fill="none" stroke="var(--data)" strokeWidth="1.5" />
      <path d={path((p) => p.tl)} fill="none" stroke="var(--chart-4)" strokeWidth="1.5" />

      {fxLast && (
        <>
          <circle cx={x(fxLast.date)} cy={y(fxLast.value)} r="2.6" fill="var(--data)" />
          <text x={W - PAD.r + 5} y={y(fxLast.value) + 3} className="font-mono text-[10px] font-semibold fill-data">
            FX {fxLast.value.toFixed(1)}%
          </text>
        </>
      )}
      {tlLast && (
        <>
          <circle cx={x(tlLast.date)} cy={y(tlLast.value)} r="2.6" fill="var(--chart-4)" />
          <text
            x={W - PAD.r + 5}
            y={y(tlLast.value) + 3}
            className="font-mono text-[10px] font-semibold"
            style={{ fill: "var(--chart-4)" }}
          >
            TL {tlLast.value.toFixed(1)}%
          </text>
        </>
      )}

      {years.map((yr) => (
        <text key={yr} x={x(`${yr}-01-01`)} y={H - 4} className={axis} textAnchor="middle">
          {yr}
        </text>
      ))}
    </svg>
  );
}
