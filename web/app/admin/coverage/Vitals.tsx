/**
 * The vitals strip under the Coverage section head — pure, no hooks, so the
 * parity/staleness/trend rendering is testable without D1 or a router.
 *
 * The parity piece is the one that keeps a registered-but-never-synced lane
 * VISIBLE: "D1 holds 19/20 lanes" says a lane is coming; an absent row in the
 * matrix says nothing at all.
 */
import { hoursSinceIso, relativeFromIso } from "@/app/lib/format-time";
import { trendDeltas, type CoverageVitals, type TrendDelta } from "@/app/lib/coverage";

const SPINE_STALE_HOURS = 8 * 24;

function Meta({ tone = "text-faint", children }: { tone?: string; children: React.ReactNode }) {
  return <span className={tone}>{children}</span>;
}

function DeltaChip({ d }: { d: TrendDelta }) {
  const tone = d.to < d.from ? "text-positive" : d.to > d.from ? "text-negative" : "text-faint";
  return (
    <Meta tone={tone}>
      {d.metric === "error" ? "errors" : "missing"} {d.from}→{d.to} ({d.days}d)
    </Meta>
  );
}

export default function Vitals({
  error,
  missing,
  vitals,
}: {
  error: number;
  missing: number;
  vitals: CoverageVitals | null;
}) {
  const spine = vitals?.spine;
  const ageH = spine?.syncedAt ? hoursSinceIso(spine.syncedAt) : null;
  const behind = spine != null && spine.lanesDeclared != null && spine.lanesInD1 < spine.lanesDeclared;
  const warn = !spine?.syncedAt || behind || (ageH != null && ageH > SPINE_STALE_HOURS);
  const deltas = trendDeltas(vitals?.trend ?? []);

  return (
    <p className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[10px] uppercase tracking-[0.04em]">
      <span className="text-negative">
        <span className="font-semibold">{error}</span> errors
      </span>
      <span className="text-warning">
        <span className="font-semibold">{missing}</span> missing
      </span>
      <span className="text-faint">·</span>
      <Meta tone={warn ? "text-warning" : "text-faint"}>
        {spine?.syncedAt
          ? `spine synced ${relativeFromIso(spine.syncedAt)} · ${spine.lanesInD1}/${spine.lanesDeclared ?? "?"} lanes in D1`
          : `spine never synced · ${spine?.lanesInD1 ?? 0} lanes in D1`}
      </Meta>
      {vitals?.lastValidated && <Meta>validated {relativeFromIso(vitals.lastValidated)}</Meta>}
      {deltas.map((d) => (
        <DeltaChip key={d.metric} d={d} />
      ))}
      <Meta>✓ = has validator</Meta>
    </p>
  );
}
