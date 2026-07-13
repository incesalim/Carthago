/**
 * Decided, then published — the archive's clock.
 *
 * One hairline per board decision, running from the date the BDDK board took it
 * (grey) to the date it reached the feed (navy). The regulator publishes in
 * batches, so the lines fan out on the left and converge on the right: the shape
 * IS the finding, and a bar chart of lag-in-days would hide it.
 *
 * Decisions older than the window (BDDK published same-day until 2020, then
 * stopped) are drawn off-scale and stated in the foot rather than squashing the
 * comb into a third of the width.
 */
import type { DecisionLagRow } from "@/app/lib/regulation";

const W = 620;
const H = 200;
const PAD = { l: 4, r: 54, t: 10, b: 20 };
const LATE_DAYS = 365;

export default function DecisionLag({ rows, from }: { rows: DecisionLagRow[]; from: string }) {
  const inScale = rows.filter((r) => r.decidedAt >= from);
  if (inScale.length === 0) return null;

  const t0 = Date.parse(from);
  const t1 = Math.max(...inScale.map((r) => Date.parse(r.publishedAt)));
  const x = (iso: string) => PAD.l + ((Date.parse(iso) - t0) / (t1 - t0)) * (W - PAD.l - PAD.r);

  const band = (H - PAD.t - PAD.b) / inScale.length;

  // The batch: where publication dates pile up.
  const pubs = inScale.map((r) => Date.parse(r.publishedAt)).sort((a, b) => a - b);
  const batchStart = pubs[Math.floor(pubs.length / 2)];
  const batchLabel = new Date(batchStart).toLocaleDateString("en-US", {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });

  // Quarter ticks, so a two-year window does not print one lonely year label.
  const ticks: { at: number; label: string }[] = [];
  const start = new Date(t0);
  for (let d = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), 1)); d.getTime() <= t1; d.setUTCMonth(d.getUTCMonth() + 6)) {
    ticks.push({
      at: d.getTime(),
      label: d.toLocaleDateString("en-US", { month: "short", year: "2-digit", timeZone: "UTC" }),
    });
  }

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="mt-2.5 block h-[200px] w-full overflow-visible"
      role="img"
      aria-label={`Each of ${inScale.length} BDDK board decisions drawn from the date it was taken to the date it was published; most converge on a single batch around ${batchLabel}.`}
    >
      {inScale.map((r, i) => {
        const y = PAD.t + band * i + band / 2;
        const late = r.lagDays > LATE_DAYS;
        return (
          <g key={`${r.decisionNo}-${r.decidedAt}`}>
            <line
              x1={x(r.decidedAt)}
              x2={x(r.publishedAt)}
              y1={y}
              y2={y}
              stroke={late ? "var(--negative)" : "var(--context)"}
              strokeWidth="1.1"
              opacity={late ? 0.85 : 1}
            />
            <circle cx={x(r.decidedAt)} cy={y} r="1.9" fill="var(--faint)" />
            <circle cx={x(r.publishedAt)} cy={y} r="1.9" fill="var(--data)" />
          </g>
        );
      })}

      <text x={W - PAD.r + 5} y={PAD.t + 8} className="font-mono text-[10px] font-semibold fill-warning">
        {batchLabel}
      </text>
      <text x={W - PAD.r + 5} y={PAD.t + 19} className="font-mono text-[8px] fill-faint">
        the batch
      </text>

      {ticks.map((t) => (
        <text key={t.at} x={x(new Date(t.at).toISOString())} y={H - 5} className="font-mono text-[8px] fill-faint" textAnchor="middle">
          {t.label}
        </text>
      ))}
    </svg>
  );
}
