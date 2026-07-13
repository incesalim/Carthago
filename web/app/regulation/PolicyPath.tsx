/**
 * The policy rate, reconstructed from the press releases themselves.
 *
 * A step function, not a line: a policy rate holds until the next Committee
 * moves it, so interpolating between meetings would draw a rate that never
 * existed. Server-rendered SVG — there is no interaction to justify shipping
 * Recharts and a client bundle for 48 static points.
 */
import type { PolicyPoint } from "@/app/lib/regulation";

const W = 620;
const H = 190;
const PAD = { l: 4, r: 46, t: 12, b: 20 };

export default function PolicyPath({ path, through }: { path: PolicyPoint[]; through: string }) {
  if (path.length < 2) return null;

  const t0 = Date.parse(path[0].date);
  const t1 = Date.parse(through);
  const lo = 5;
  const hi = Math.ceil(Math.max(...path.map((p) => p.rate)) / 10) * 10 + 2;

  const x = (iso: string) =>
    PAD.l + ((Date.parse(iso) - t0) / (t1 - t0)) * (W - PAD.l - PAD.r);
  const y = (v: number) => PAD.t + ((hi - v) / (hi - lo)) * (H - PAD.t - PAD.b);

  // step-after: carry each rate forward to the meeting that changed it
  const pts: [number, number][] = [];
  path.forEach((p, i) => {
    pts.push([x(p.date), y(p.rate)]);
    pts.push([x(path[i + 1]?.date ?? through), y(p.rate)]);
  });
  const line = "M" + pts.map(([px, py]) => `${px.toFixed(1)},${py.toFixed(1)}`).join(" L");
  const area = `${line} L${pts[pts.length - 1][0].toFixed(1)},${y(lo).toFixed(1)} L${pts[0][0].toFixed(1)},${y(lo).toFixed(1)} Z`;

  const last = path[path.length - 1];
  const peak = path.reduce((a, b) => (b.rate > a.rate ? b : a));
  const trough = path.reduce((a, b) => (b.rate < a.rate ? b : a));

  const gridValues: number[] = [];
  for (let v = 10; v < hi; v += 10) gridValues.push(v);

  const years: number[] = [];
  for (let yr = new Date(t0).getUTCFullYear(); yr <= new Date(t1).getUTCFullYear(); yr++) years.push(yr);

  const axis = "font-mono text-[8px] fill-faint";

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="mt-2.5 block h-[190px] w-full overflow-visible"
      role="img"
      aria-label={`CBRT policy rate across ${path.length} Committee decisions, from ${path[0].rate}% in ${path[0].date.slice(0, 4)} to ${last.rate}% today; peak ${peak.rate}%, trough ${trough.rate}%.`}
    >
      {gridValues.map((v) => (
        <g key={v}>
          <line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} stroke="var(--hair)" strokeWidth="1" />
          <text x={W - PAD.r + 5} y={y(v) + 3} className={axis}>
            {v}%
          </text>
        </g>
      ))}

      <path d={area} fill="var(--data)" opacity="0.06" />
      <path d={line} fill="none" stroke="var(--data)" strokeWidth="1.6" strokeLinejoin="round" />

      {[
        { p: peak, dy: -9, label: `${peak.rate}% peak` },
        { p: trough, dy: 14, label: `${trough.rate}% trough` },
      ].map(({ p, dy, label }) => (
        <g key={label}>
          <circle cx={x(p.date)} cy={y(p.rate)} r="2.6" fill="var(--data)" />
          <text x={x(p.date)} y={y(p.rate) + dy} className="font-mono text-[8.5px] fill-muted-foreground" textAnchor="middle">
            {label}
          </text>
        </g>
      ))}

      <circle cx={x(last.date)} cy={y(last.rate)} r="3" fill="var(--data)" />
      <text x={W - PAD.r + 5} y={y(last.rate) - 3} className="font-mono text-[10px] font-semibold fill-data">
        {last.rate}%
      </text>

      {years.map((yr) => (
        <text key={yr} x={x(`${yr}-01-01`)} y={H - 5} className={axis} textAnchor="middle">
          {yr}
        </text>
      ))}
    </svg>
  );
}
