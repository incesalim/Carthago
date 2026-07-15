"use client";

/**
 * /cross-bank — "the matchup sheet": the brief layer of the Compare tab.
 *
 * The tab is named Compare, so it has to let you compare BANKS, not just rank
 * everything at once. Three controls drive the whole page:
 *
 *   • the bench    — pick up to four banks (four is what a person can hold);
 *   • the frame    — who they are measured against (all / their types / majors);
 *   • the metric   — every metric is a ROW on a real value axis.
 *
 * The scorecard is the point. A rank-coloured cell says "3rd of 34" but hides
 * DISTANCE: a bank 0.1pp behind the leader is painted exactly as far from it as
 * one 10pp behind. Here each metric gets its own axis — every peer a faint tick,
 * the interquartile band shaded, the median marked, the picks as labelled dots —
 * so the gaps are to scale and the sector's bunching is visible.
 *
 * Everything (axes, medians, ranks, the read, the grid below) recomputes off the
 * frame, because a rank is only meaningful against a stated peer set. Ranks come
 * from normalizeColumn() — the SAME percentile rule the heatmap cells use — so
 * "rank" is defined in exactly one place.
 */
import { useMemo, useState, type ReactNode } from "react";
import {
  METRIC_FAMILIES,
  type MetricDef,
  type MetricFamily,
} from "@/app/lib/heatmap";
import {
  formatMetricValue,
  median,
  normalizeColumn,
  quantile,
} from "@/app/lib/heatmap-normalize";
import { Depth, SecHead, Vital, Vitals } from "@/app/components/desk";
import HeatmapView from "./HeatmapView";
import type { PanelCell } from "./HeatmapOverTime";
import { MAX_PICKS, PICK_COLORS, type BoardBank } from "./picks";

interface Props {
  metrics: MetricDef[];
  /** Every bank in the panel, ordered by group then assets desc. */
  banks: BoardBank[];
  /** Quarters ascending. */
  periods: string[];
  /** One cell per (bank, quarter), raw values aligned to `metrics`. */
  panel: PanelCell[];
  /** The latest quarter a quorum of banks has filed — the snapshot. */
  period: string;
  /** Market-share + concentration block, server-rendered and slotted under the grid. */
  marketShare?: ReactNode;
}

/** Deposit-bank majors. Panel assets are THOUSAND-TL, so ₺500bn = 500e6. */
const MAJORS_MIN = 500e6;

const DEFAULT_PICKS = ["AKBNK", "GARAN", "ISCTR", "YKBNK"];

type FrameKey = "all" | "types" | "majors";
const FRAME_LABELS: Record<FrameKey, string> = {
  all: "All banks",
  types: "Their types",
  majors: "Majors ₺500bn+",
};

/** Column statistics over one metric across the framed banks. */
interface Col {
  /** 0..1 percentile score per ticker (1 = best), null when not filed. */
  scores: Map<string, number | null>;
  /** Competition rank per ticker (1 = best); ties share a rank. */
  ranks: Map<string, number>;
  /** How many banks in the frame filed this metric. */
  n: number;
  min: number;
  max: number;
  med: number;
  q1: number;
  q3: number;
}

/** Position (0..100) of `v` on an axis running lo→hi, log-scaled for size. */
function axisPos(v: number, lo: number, hi: number, log?: boolean): number {
  if (hi === lo) return 50;
  const p = log
    ? ((Math.log10(v) - Math.log10(lo)) / (Math.log10(hi) - Math.log10(lo))) * 100
    : ((v - lo) / (hi - lo)) * 100;
  return Math.max(0, Math.min(100, p));
}

/** The strip is inset 6px each side, so a % of the CONTAINER overshoots the
 *  axis. Convert an axis-% into a CSS left offset that lands on the axis. */
function leftOf(p: number): string {
  return `calc(6px + ${p}% - ${(p / 100) * 12}px)`;
}

export default function CompareBoard({
  metrics,
  banks,
  periods,
  panel,
  period,
  marketShare,
}: Props) {
  const [picks, setPicks] = useState<string[]>(() => {
    const known = new Set(banks.map((b) => b.ticker));
    const seed = DEFAULT_PICKS.filter((t) => known.has(t));
    return seed.length ? seed : banks.slice(0, MAX_PICKS).map((b) => b.ticker);
  });
  const [frame, setFrame] = useState<FrameKey>("all");

  const byTicker = useMemo(
    () => new Map(banks.map((b) => [b.ticker, b])),
    [banks],
  );

  /** Snapshot raw values at the record quarter, per ticker. */
  const snapshot = useMemo(() => {
    const m = new Map<string, (number | null)[]>();
    for (const c of panel) if (c.period === period) m.set(c.ticker, c.raw);
    return m;
  }, [panel, period]);

  /** The peer frame: the set every axis, median and rank is computed over.
   *  The picks are ALWAYS in it — you cannot compare a bank against a set it
   *  has been filtered out of. */
  const frameBanks = useMemo(() => {
    const picked = new Set(picks);
    const keep = (b: BoardBank) => {
      if (picked.has(b.ticker)) return true;
      if (frame === "types") {
        const types = new Set(picks.map((t) => byTicker.get(t)?.groupCode));
        return types.has(b.groupCode);
      }
      if (frame === "majors") {
        const a = snapshot.get(b.ticker)?.[0];
        return a != null && a >= MAJORS_MIN;
      }
      return true;
    };
    return banks.filter((b) => snapshot.has(b.ticker) && keep(b));
  }, [banks, picks, frame, byTicker, snapshot]);

  /** Count each frame would hold, for the switch's own labels. */
  const frameCounts = useMemo(() => {
    const picked = new Set(picks);
    const types = new Set(picks.map((t) => byTicker.get(t)?.groupCode));
    const filed = banks.filter((b) => snapshot.has(b.ticker));
    return {
      all: filed.length,
      types: filed.filter((b) => picked.has(b.ticker) || types.has(b.groupCode)).length,
      majors: filed.filter((b) => {
        const a = snapshot.get(b.ticker)?.[0];
        return picked.has(b.ticker) || (a != null && a >= MAJORS_MIN);
      }).length,
    } as Record<FrameKey, number>;
  }, [banks, picks, byTicker, snapshot]);

  /** Per-metric stats over the frame — scores from the shared percentile rule. */
  const cols = useMemo(() => {
    const out = new Map<string, Col>();
    metrics.forEach((m, ci) => {
      const raw = frameBanks.map((b) => snapshot.get(b.ticker)?.[ci] ?? null);
      const scores = normalizeColumn(raw, m.direction);
      const scoreByTicker = new Map<string, number | null>();
      frameBanks.forEach((b, i) => scoreByTicker.set(b.ticker, scores[i]));

      const ranks = new Map<string, number>();
      for (const b of frameBanks) {
        const s = scoreByTicker.get(b.ticker);
        if (s == null) continue;
        let better = 0;
        for (const o of frameBanks) {
          const so = scoreByTicker.get(o.ticker);
          if (so != null && so > s + 1e-12) better++;
        }
        ranks.set(b.ticker, better + 1);
      }

      const vals = raw.filter((v): v is number => v != null);
      out.set(m.key, {
        scores: scoreByTicker,
        ranks,
        n: vals.length,
        min: vals.length ? Math.min(...vals) : 0,
        max: vals.length ? Math.max(...vals) : 0,
        med: median(vals) ?? 0,
        q1: quantile(vals, 0.25) ?? 0,
        q3: quantile(vals, 0.75) ?? 0,
      });
    });
    return out;
  }, [metrics, frameBanks, snapshot]);

  /** Median of one metric across the frame, per quarter — the vitals sparklines. */
  const medianSeries = (key: string) => {
    const ci = metrics.findIndex((m) => m.key === key);
    if (ci < 0) return [];
    const inFrame = new Set(frameBanks.map((b) => b.ticker));
    return periods
      .map((p) => {
        const vals = panel
          .filter((c) => c.period === p && inFrame.has(c.ticker))
          .map((c) => c.raw[ci]);
        const v = median(vals);
        return { period: p, value: v == null ? null : v * 100 };
      })
      .filter((pt) => pt.value != null)
      .slice(-13);
  };

  const medOf = (key: string) => {
    const c = cols.get(key);
    return c && c.n ? c.med : null;
  };
  /** The frame's rank-1 bank on a metric (null when nobody filed it). */
  const bestOf = (key: string) =>
    frameBanks.find((b) => cols.get(key)?.ranks.get(b.ticker) === 1) ?? null;
  const rawOf = (ticker: string, key: string) =>
    snapshot.get(ticker)?.[metrics.findIndex((m) => m.key === key)] ?? null;

  // ---- concentration, over the frame's own assets --------------------------
  const conc = useMemo(() => {
    const rows = frameBanks
      .map((b) => ({ b, a: snapshot.get(b.ticker)?.[0] ?? null }))
      .filter((r): r is { b: BoardBank; a: number } => r.a != null);
    const total = rows.reduce((s, r) => s + r.a, 0);
    if (!total) return null;
    const shares = rows.map((r) => ({ b: r.b, s: r.a / total }));
    shares.sort((x, y) => y.s - x.s);
    const hhi = shares.reduce((s, r) => s + (r.s * 100) ** 2, 0);
    return { hhi, leader: shares[0] };
  }, [frameBanks, snapshot]);

  const togglePick = (ticker: string) => {
    setPicks((cur) => {
      const i = cur.indexOf(ticker);
      if (i >= 0) return cur.length > 1 ? cur.filter((t) => t !== ticker) : cur;
      if (cur.length < MAX_PICKS) return [...cur, ticker];
      return [...cur.slice(1), ticker]; // a fifth pick retires the first
    });
  };

  // ---- the read — deterministic, straight off the same columns --------------
  const read = useMemo(() => {
    const directional = metrics.filter((m) => m.direction !== "neutral");
    const wins = new Map<string, number>(picks.map((t) => [t, 0]));
    let judged = 0;
    for (const m of directional) {
      const c = cols.get(m.key);
      if (!c) continue;
      const have = picks.filter((t) => c.scores.get(t) != null);
      if (have.length < 2) continue;
      judged++;
      let top = have[0];
      for (const t of have) {
        if ((c.scores.get(t) as number) > (c.scores.get(top) as number)) top = t;
      }
      wins.set(top, (wins.get(top) ?? 0) + 1);
    }
    const ranked = [...picks].sort((a, b) => (wins.get(b) ?? 0) - (wins.get(a) ?? 0));

    // Where the picks disagree most, as a share of the frame's whole range.
    let widest: { m: MetricDef; rel: number; spread: number; hi: string; lo: string } | null = null;
    metrics.forEach((m, ci) => {
      const c = cols.get(m.key);
      if (!c || c.max === c.min) return;
      const vs = picks
        .map((t) => ({ t, v: snapshot.get(t)?.[ci] ?? null }))
        .filter((e): e is { t: string; v: number } => e.v != null);
      if (vs.length < 2) return;
      const hi = vs.reduce((a, b) => (b.v > a.v ? b : a));
      const lo = vs.reduce((a, b) => (b.v < a.v ? b : a));
      const spread = hi.v - lo.v;
      const rel = spread / (c.max - c.min);
      if (!widest || rel > widest.rel) widest = { m, rel, spread, hi: hi.t, lo: lo.t };
    });

    return { judged, wins, ranked, widest };
  }, [metrics, picks, cols, snapshot]);

  const nameOf = (t: string) => byTicker.get(t)?.name ?? t;

  // ---- render --------------------------------------------------------------
  const gridCols = `minmax(190px,1.3fr) minmax(230px,2.1fr) repeat(${picks.length}, minmax(74px,0.62fr)) minmax(78px,0.6fr)`;

  const benchGroups = useMemo(() => {
    const out: { code: string; label: string; rows: BoardBank[] }[] = [];
    for (const b of banks) {
      let g = out.find((x) => x.code === b.groupCode);
      if (!g) {
        g = { code: b.groupCode, label: b.groupLabel, rows: [] };
        out.push(g);
      }
      g.rows.push(b);
    }
    return out;
  }, [banks]);

  return (
    <>
      {/* ---- the bench ---- */}
      <SecHead
        title="The matchup"
        meta="pick up to four · the peer frame sets every axis, median and rank below"
        className="mb-3 mt-6"
      />
      <div className="grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-5">
        {benchGroups.map((g) => (
          <div key={g.code}>
            <div className="mb-1.5 font-mono text-[8.5px] uppercase tracking-[0.08em] text-faint">
              {g.label} <span className="text-context">{g.rows.length}</span>
            </div>
            <div className="flex flex-wrap gap-x-1 gap-y-0.5">
              {g.rows.map((b) => {
                const i = picks.indexOf(b.ticker);
                const on = i >= 0;
                return (
                  <button
                    key={b.ticker}
                    type="button"
                    onClick={() => togglePick(b.ticker)}
                    aria-pressed={on}
                    title={on ? `Drop ${b.name} from the matchup` : `Add ${b.name} to the matchup`}
                    className={`border-b-[1.5px] px-0.5 pb-0.5 font-mono text-[10px] transition-colors ${
                      on
                        ? "font-semibold text-foreground"
                        : "border-transparent text-muted-foreground hover:border-hair hover:text-foreground"
                    }`}
                    style={on ? { borderBottomColor: PICK_COLORS[i] } : undefined}
                  >
                    {on && (
                      <span
                        aria-hidden
                        className="mr-1.5 inline-block size-1.5 rounded-full align-baseline"
                        style={{ background: PICK_COLORS[i] }}
                      />
                    )}
                    {b.name}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* ---- the peer frame ---- */}
      <SecHead
        title="The peer frame"
        meta="who the picks are measured against"
        className="mb-3 mt-6 border-b border-hair pb-1.5"
      />
      <div className="-mt-1 mb-3 flex flex-wrap gap-x-5">
        {(Object.keys(FRAME_LABELS) as FrameKey[]).map((k) => (
          <button
            key={k}
            type="button"
            onClick={() => setFrame(k)}
            aria-pressed={frame === k}
            className={`border-b-[1.5px] pb-0.5 font-mono text-[10.5px] transition-colors ${
              frame === k
                ? "border-foreground font-semibold text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {FRAME_LABELS[k]} <span className="text-faint">{frameCounts[k]}</span>
          </button>
        ))}
      </div>

      {/* ---- the vitals, over the frame ---- */}
      <Vitals cols={6}>
        <Vital
          label="In the matchup"
          value={String(picks.length)}
          unit={` of ${frameBanks.length}`}
          note={
            <>
              {picks.map((t, i) => (
                <span key={t}>
                  {i > 0 && " · "}
                  <b className="font-semibold text-foreground">{nameOf(t)}</b>
                </span>
              ))}
            </>
          }
        />
        <Vital
          label="Median ROE (TTM)"
          value={medOf("roe") != null ? ((medOf("roe") as number) * 100).toFixed(1) : "—"}
          unit="%"
          series={medianSeries("roe")}
          decimals={1}
          note={
            bestOf("roe") ? (
              <>
                highest: <b className="font-semibold text-foreground">{bestOf("roe")!.name}</b>{" "}
                {(((rawOf(bestOf("roe")!.ticker, "roe") ?? 0) as number) * 100).toFixed(1)}%
              </>
            ) : (
              "TTM net income ÷ 5-quarter avg equity"
            )
          }
        />
        <Vital
          label="Median NPL"
          value={medOf("npl_ratio") != null ? ((medOf("npl_ratio") as number) * 100).toFixed(2) : "—"}
          unit="%"
          series={medianSeries("npl_ratio")}
          note={
            bestOf("npl_ratio") ? (
              <>
                cleanest:{" "}
                <b className="font-semibold text-foreground">{bestOf("npl_ratio")!.name}</b>{" "}
                {(((rawOf(bestOf("npl_ratio")!.ticker, "npl_ratio") ?? 0) as number) * 100).toFixed(2)}%
              </>
            ) : (
              "stage-3 ÷ total loans"
            )
          }
        />
        <Vital
          label="Median NIM"
          value={medOf("nim") != null ? ((medOf("nim") as number) * 100).toFixed(2) : "—"}
          unit="%"
          series={medianSeries("nim")}
          note="TTM net interest ÷ avg assets"
        />
        <Vital
          label="Median cost of risk"
          value={
            medOf("cost_of_risk") != null
              ? ((medOf("cost_of_risk") as number) * 100).toFixed(2)
              : "—"
          }
          unit="%"
          series={medianSeries("cost_of_risk")}
          note={
            bestOf("cost_of_risk") ? (
              <>
                lowest:{" "}
                <b className="font-semibold text-foreground">{bestOf("cost_of_risk")!.name}</b>{" "}
                {(((rawOf(bestOf("cost_of_risk")!.ticker, "cost_of_risk") ?? 0) as number) * 100).toFixed(2)}%
              </>
            ) : (
              "|TTM ECL flow| ÷ avg gross loans"
            )
          }
        />
        <Vital
          label="Concentration (HHI)"
          value={conc ? conc.hhi.toFixed(0) : "—"}
          format="raw"
          decimals={0}
          note={
            conc ? (
              <>
                <b className="font-semibold text-foreground">{conc.leader.b.name}</b> holds{" "}
                {(conc.leader.s * 100).toFixed(1)}% of the frame&rsquo;s assets
              </>
            ) : (
              "Σ share² × 10,000"
            )
          }
        />
      </Vitals>

      {/* ---- the read ---- */}
      {read.widest && (
        <p className="mt-4 max-w-[82ch] border-l-2 border-foreground pl-3 text-[13.5px] leading-relaxed text-foreground">
          Across <span className="font-mono tabular-nums">{read.judged}</span> directional metrics,{" "}
          <b className="font-semibold">{nameOf(read.ranked[0])}</b> takes{" "}
          <span className="font-mono tabular-nums">{read.wins.get(read.ranked[0]) ?? 0}</span>
          {read.ranked[1] && (
            <>
              {" "}
              and <b className="font-semibold">{nameOf(read.ranked[1])}</b>{" "}
              <span className="font-mono tabular-nums">{read.wins.get(read.ranked[1]) ?? 0}</span>
            </>
          )}
          . The set splits widest on{" "}
          <b className="font-semibold">{(read.widest as { m: MetricDef }).m.label}</b> —{" "}
          <span className="font-mono tabular-nums">
            {formatMetricValue(
              (read.widest as { spread: number }).spread,
              (read.widest as { m: MetricDef }).m.unit,
              (read.widest as { m: MetricDef }).m.decimals,
            ).replace("%", "pp")}
          </span>{" "}
          between {nameOf((read.widest as { hi: string }).hi)} and{" "}
          {nameOf((read.widest as { lo: string }).lo)}, which is{" "}
          <span className="font-mono tabular-nums">
            {Math.round((read.widest as { rel: number }).rel * 100)}%
          </span>{" "}
          of the entire range across the frame.
        </p>
      )}

      {/* ---- the scorecard ---- */}
      <SecHead
        title="The scorecard"
        meta="each metric on its own value axis — every peer a tick, the median marked, your picks as dots"
        className="mb-2 mt-7 border-b border-hair pb-1.5"
      />
      <div className="overflow-x-auto">
        <div className="min-w-[820px]">
          {/* header */}
          <div
            className="grid items-end border-b border-border pb-1.5"
            style={{ gridTemplateColumns: gridCols }}
          >
            <div className="font-mono text-[8.5px] uppercase tracking-[0.08em] text-faint">
              Metric
            </div>
            <div className="font-mono text-[8.5px] uppercase tracking-[0.08em] text-faint">
              Where they sit in the frame
            </div>
            {picks.map((t, i) => (
              <div key={t} className="pl-2.5 text-right">
                <div
                  className="font-mono text-[10px] font-semibold"
                  style={{ color: PICK_COLORS[i] }}
                >
                  {t}
                </div>
                <div className="truncate text-[10px] leading-tight text-muted-foreground">
                  {nameOf(t)}
                </div>
              </div>
            ))}
            <div className="pl-3 text-right font-mono text-[8.5px] uppercase tracking-[0.08em] text-faint">
              {picks.length === 2 ? `Δ ${picks[0]}−${picks[1]}` : "Set spread"}
            </div>
          </div>

          {METRIC_FAMILIES.map((fam: MetricFamily) => {
            const rows = metrics.filter((m) => m.family === fam);
            if (!rows.length) return null;
            return (
              <div key={fam}>
                <div className="pb-1 pt-4">
                  <span className="font-mono text-[8.5px] font-semibold uppercase tracking-[0.09em] text-foreground">
                    {fam}
                  </span>
                  <span className="ml-2 font-mono text-[8.5px] text-faint">
                    {rows.length} metric{rows.length > 1 ? "s" : ""}
                  </span>
                </div>

                {rows.map((m) => {
                  const ci = metrics.findIndex((x) => x.key === m.key);
                  const c = cols.get(m.key)!;
                  const arrow =
                    m.direction === "higher_better"
                      ? "↑"
                      : m.direction === "higher_worse"
                        ? "↓"
                        : "";
                  const dirNote =
                    m.direction === "neutral"
                      ? "no good side"
                      : m.direction === "higher_better"
                        ? "higher is better"
                        : "lower is better";

                  // Axis: clip to the Tukey whiskers so one freak value can't
                  // flatten the field — but never clip a PICK out of view.
                  const pickVals = picks
                    .map((t) => snapshot.get(t)?.[ci] ?? null)
                    .filter((v): v is number => v != null);
                  let lo = c.min;
                  let hi = c.max;
                  const iqr = c.q3 - c.q1;
                  if (!m.log && iqr > 0) {
                    lo = Math.min(Math.max(c.min, c.q1 - 1.5 * iqr), ...pickVals);
                    hi = Math.max(Math.min(c.max, c.q3 + 1.5 * iqr), ...pickVals);
                  }
                  const outLo = frameBanks.filter((b) => {
                    const v = snapshot.get(b.ticker)?.[ci];
                    return v != null && v < lo;
                  });
                  const outHi = frameBanks.filter((b) => {
                    const v = snapshot.get(b.ticker)?.[ci];
                    return v != null && v > hi;
                  });
                  const at = (v: number) => leftOf(axisPos(v, lo, hi, m.log));

                  const cut = (list: BoardBank[]) =>
                    list
                      .map((b) => `${b.name} ${formatMetricValue(snapshot.get(b.ticker)![ci], m.unit, m.decimals)}`)
                      .join(" · ");

                  // Δ (two picks) or the set's spread (three or four).
                  let tail: ReactNode = <span className="text-muted-foreground">—</span>;
                  if (picks.length === 2) {
                    const a = snapshot.get(picks[0])?.[ci] ?? null;
                    const b = snapshot.get(picks[1])?.[ci] ?? null;
                    if (a != null && b != null) {
                      const d = a - b;
                      const sa = c.scores.get(picks[0]);
                      const sb = c.scores.get(picks[1]);
                      const tone =
                        m.direction === "neutral" || Math.abs(d) < 1e-12 || sa == null || sb == null
                          ? "text-muted-foreground"
                          : sa > sb
                            ? "text-positive"
                            : "text-negative";
                      tail = (
                        <span className={tone}>
                          {d > 0 ? "+" : d < 0 ? "−" : ""}
                          {formatMetricValue(Math.abs(d), m.unit, m.decimals).replace("%", "pp")}
                        </span>
                      );
                    }
                  } else if (pickVals.length >= 2) {
                    tail = (
                      <span className="text-muted-foreground">
                        {formatMetricValue(
                          Math.max(...pickVals) - Math.min(...pickVals),
                          m.unit,
                          m.decimals,
                        ).replace("%", "pp")}
                      </span>
                    );
                  }

                  return (
                    <div
                      key={m.key}
                      className="grid items-center border-b border-hair py-2"
                      style={{ gridTemplateColumns: gridCols }}
                    >
                      <div className="pr-3.5">
                        <div className="text-[12.5px] font-medium leading-tight text-foreground">
                          {m.label}
                          <span className="ml-1 font-normal text-faint" title={dirNote}>
                            {arrow}
                          </span>
                        </div>
                        <div className="mt-0.5 font-mono text-[8.5px] leading-snug text-faint">
                          {m.rule}
                        </div>
                      </div>

                      {/* the strip */}
                      <div className="relative h-11 px-1.5">
                        {c.n >= 2 ? (
                          <>
                            <div className="absolute inset-x-1.5 top-6 h-px bg-hair" />
                            <div
                              className="absolute top-[19px] h-[11px] rounded-[1px] bg-hair"
                              style={{
                                left: at(c.q1),
                                width: `calc(${axisPos(c.q3, lo, hi, m.log) - axisPos(c.q1, lo, hi, m.log)}% - ${
                                  ((axisPos(c.q3, lo, hi, m.log) - axisPos(c.q1, lo, hi, m.log)) / 100) * 12
                                }px)`,
                              }}
                            />
                            {frameBanks.map((b) => {
                              const v = snapshot.get(b.ticker)?.[ci];
                              if (v == null || picks.includes(b.ticker)) return null;
                              const clipped = v < lo || v > hi;
                              return (
                                <div
                                  key={b.ticker}
                                  title={`${b.name} · ${formatMetricValue(v, m.unit, m.decimals)}${
                                    clipped ? " — beyond the axis" : ""
                                  }`}
                                  className={`absolute w-px bg-context ${
                                    clipped ? "top-[22px] h-[5px] opacity-55" : "top-5 h-[9px]"
                                  }`}
                                  style={{ left: at(v) }}
                                />
                              );
                            })}
                            <div
                              className="absolute top-4 h-[17px] w-px bg-faint"
                              style={{ left: at(c.med) }}
                            />
                            <div
                              className="absolute top-px whitespace-nowrap font-mono text-[8px] tracking-[0.05em] text-faint"
                              style={{
                                left: at(c.med),
                                transform:
                                  axisPos(c.med, lo, hi, m.log) < 12
                                    ? "translateX(0)"
                                    : axisPos(c.med, lo, hi, m.log) > 88
                                      ? "translateX(-100%)"
                                      : "translateX(-50%)",
                              }}
                            >
                              median {formatMetricValue(c.med, m.unit, m.decimals)}
                            </div>
                            {picks.map((t, i) => {
                              const v = snapshot.get(t)?.[ci];
                              if (v == null) return null;
                              const r = c.ranks.get(t);
                              return (
                                <div
                                  key={t}
                                  title={`${nameOf(t)} · ${formatMetricValue(v, m.unit, m.decimals)}${
                                    r ? ` · rank ${r}/${c.n}` : ""
                                  }`}
                                  className="absolute top-[18px] -ml-[5.5px] size-[11px] rounded-full border-[1.5px] border-card"
                                  style={{ left: at(v), background: PICK_COLORS[i] }}
                                />
                              );
                            })}
                            <div className="absolute left-1.5 top-8 font-mono text-[8.5px] text-faint">
                              {outLo.length > 0 && (
                                <>
                                  <span className="cursor-help text-context" title={`beyond the axis — ${cut(outLo)}`}>
                                    ‹{outLo.length}
                                  </span>
                                  <span className="mx-[3px] text-context">·</span>
                                </>
                              )}
                              {formatMetricValue(lo, m.unit, m.decimals)}
                            </div>
                            <div className="absolute right-1.5 top-8 font-mono text-[8.5px] text-faint">
                              {formatMetricValue(hi, m.unit, m.decimals)}
                              {outHi.length > 0 && (
                                <>
                                  <span className="mx-[3px] text-context">·</span>
                                  <span className="cursor-help text-context" title={`beyond the axis — ${cut(outHi)}`}>
                                    ›{outHi.length}
                                  </span>
                                </>
                              )}
                            </div>
                          </>
                        ) : (
                          <div className="absolute left-1.5 top-5 font-mono text-[8.5px] text-faint">
                            only {c.n} bank{c.n === 1 ? "" : "s"} filed this in the frame
                          </div>
                        )}
                      </div>

                      {/* the picks' values */}
                      {picks.map((t, i) => {
                        const v = snapshot.get(t)?.[ci] ?? null;
                        const r = c.ranks.get(t);
                        return (
                          <div key={t} className="pl-2.5 text-right">
                            <div
                              className="font-mono text-[12.5px] font-semibold tabular-nums leading-tight"
                              style={{ color: v == null ? "var(--faint)" : PICK_COLORS[i] }}
                            >
                              {formatMetricValue(v, m.unit, m.decimals)}
                            </div>
                            <div className="font-mono text-[8.5px] leading-snug text-faint">
                              {v == null ? "not filed" : `${r}/${c.n}`}
                            </div>
                          </div>
                        );
                      })}

                      <div className="pl-3 text-right font-mono text-[11.5px] tabular-nums">
                        {tail}
                      </div>
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>

      <p className="mt-2.5 font-mono text-[8.5px] leading-relaxed tracking-[0.04em] text-faint">
        Axis runs the peer frame&rsquo;s range, clipped to the Tukey whiskers (q₁/q₃ ± 1.5 × IQR)
        where a lone freak value would otherwise flatten the field — clipped peers are counted at
        the edge (<span className="text-context">‹3</span>), and a pick is never clipped out of
        view. Shaded band is the interquartile range. Assets use a log axis. Ranks are the same
        percentile rule the grid below colours by.
      </p>

      {/* ---- the evidence ---- */}
      <Depth>
        <HeatmapView
          metrics={metrics}
          banks={frameBanks}
          periods={periods}
          panel={panel}
          period={period}
          picks={picks}
          frameLabel={FRAME_LABELS[frame]}
        />
        {marketShare}
      </Depth>
    </>
  );
}
