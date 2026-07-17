/**
 * The bridge — /credit's signature element.
 *
 * Nominal loan growth in Türkiye is mostly not credit: it is the lira and the
 * price level. This walks the headline down to what actually grew:
 *
 *   nominal → −lira depreciation → FX-adjusted → −inflation → real, constant FX
 *
 * The nominal bar is drawn in CONTEXT grey, not hero navy: it is where the
 * reader starts, not what the page claims. The terminal bar carries the claim.
 * Deduction bars are floating (they hang between the two levels they connect),
 * so the legs reconcile the endpoints visually as well as arithmetically.
 */
import type { CreditBridge } from "@/app/lib/credit";

const fmtPct = (v: number, d = 1) => `${v < 0 ? "−" : ""}${Math.abs(v).toFixed(d)}%`;
const fmtPp = (v: number, d = 1) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(d)}pp`;

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** 'YYYY-MM-DD' → 'at 26 Jun' */
function weekOf(period: string): string {
  const m = /^\d{4}-(\d{2})-(\d{2})/.exec(period);
  return m ? `at ${m[2]} ${MONTHS[Number(m[1]) - 1]}` : "";
}

type Step =
  | { kind: "level"; label: string; sub?: string; value: number; hero?: boolean }
  | { kind: "cut"; label: string; sub?: string; value: number };

export default function Bridge({ bridge }: { bridge: CreditBridge }) {
  const { nominalAtReal, fxAdj, realFxAdj, currencyPp, inflationPp, cpi, asOfReal, lagged } =
    bridge;
  if (
    nominalAtReal == null || fxAdj == null || realFxAdj == null ||
    currencyPp == null || inflationPp == null
  ) {
    return (
      <p className="py-6 text-[12px] text-faint">
        The bridge needs a nominal print, an FX-adjusted print and a CPI month. One is
        not yet published.
      </p>
    );
  }

  const steps: Step[] = [
    // Nominal is the only CONTEXT bar: it is where the reader starts, not the
    // claim. Every level after it is a real measure of the book, so it carries
    // the hero mark (or the negative mark, if the book actually shrank).
    // Read at the REAL week, so a CPI lag can't mix two dates inside one bridge.
    // That makes it differ from the vitals' nominal (the latest week) — say which
    // week this is, rather than let the two numbers silently disagree.
    {
      kind: "level",
      label: "Nominal 52w",
      sub: lagged && asOfReal ? weekOf(asOfReal) : undefined,
      value: nominalAtReal,
    },
    { kind: "cut", label: "Lira", sub: "depreciation", value: -currencyPp },
    { kind: "level", label: "FX-adjusted", value: fxAdj, hero: true },
    { kind: "cut", label: "Inflation", sub: cpi != null ? `CPI ${cpi.toFixed(1)}%` : undefined, value: -inflationPp },
    { kind: "level", label: "Real, const. FX", value: realFxAdj, hero: true },
  ];

  // Geometry — derived from the data so the bars can't overflow the frame.
  const W = 660, H = 208;
  const PLOT_TOP = 26, PLOT_BOTTOM = 156; // below PLOT_BOTTOM: the x labels
  const levels = steps.filter((s) => s.kind === "level").map((s) => s.value);
  const maxPos = Math.max(0, ...levels);
  const minNeg = Math.min(0, ...levels);
  const span = maxPos - minNeg || 1;
  const scale = (PLOT_BOTTOM - PLOT_TOP) / span;
  const zeroY = PLOT_TOP + maxPos * scale; // where 0 sits
  const y = (v: number) => zeroY - v * scale;

  const bw = 78, gap = 52;
  const step = bw + gap;
  const x0 = 6;

  let running = 0;
  const bars = steps.map((s, i) => {
    const x = x0 + i * step;
    let top: number, height: number, valueY: number;

    if (s.kind === "level") {
      const yv = y(s.value);
      top = Math.min(yv, zeroY);
      height = Math.max(Math.abs(yv - zeroY), 1.5);
      valueY = s.value < 0 ? top + height + 13 : top - 7;
      running = s.value;
    } else {
      const from = y(running);
      const to = y(running + s.value);
      top = Math.min(from, to);
      height = Math.max(Math.abs(to - from), 1.5);
      valueY = top - 7;
      running += s.value;
    }
    return { s, i, x, top, height, valueY, running };
  });

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full"
      role="img"
      aria-label={`Nominal loan growth of ${fmtPct(nominalAtReal)} bridges down to ${fmtPct(
        realFxAdj,
      )} once lira depreciation (${fmtPp(-currencyPp)}) and inflation (${fmtPp(
        -inflationPp,
      )}) are removed.`}
    >
      {/* the zero rule — the only baseline the reader needs */}
      <line
        x1={0}
        x2={W}
        y1={zeroY}
        y2={zeroY}
        className="stroke-faint"
        strokeWidth={1}
        strokeDasharray="2 2"
      />

      {bars.map(({ s, i, x, top, height, valueY }, idx) => {
        const prev = bars[idx - 1];
        return (
          <g key={s.label}>
            {/* connector from the previous bar's landing height */}
            {s.kind === "cut" && prev && (
              <line
                x1={x - gap}
                x2={x}
                y1={top}
                y2={top}
                className="stroke-faint"
                strokeWidth={1}
                strokeDasharray="2 2"
              />
            )}
            {s.kind === "level" && i > 0 && prev && (
              <line
                x1={x - gap}
                x2={x}
                y1={y(s.value)}
                y2={y(s.value)}
                className="stroke-faint"
                strokeWidth={1}
                strokeDasharray="2 2"
              />
            )}

            <rect
              x={x}
              y={top}
              width={bw}
              height={height}
              className={
                s.kind === "cut"
                  ? "fill-negative opacity-25"
                  : s.value < 0
                    ? "fill-negative"
                    : s.hero
                      ? "fill-data"
                      : "fill-context"
              }
            />

            <text
              x={x + bw / 2}
              y={valueY}
              textAnchor="middle"
              className={`font-mono text-[11px] font-semibold ${
                s.kind === "cut" || s.value < 0 ? "fill-negative" : "fill-foreground"
              }`}
            >
              {s.kind === "cut" ? fmtPp(s.value) : fmtPct(s.value)}
            </text>

            <text
              x={x + bw / 2}
              y={s.sub ? H - 17 : H - 7}
              textAnchor="middle"
              className="fill-muted-foreground text-[8.5px] uppercase tracking-[0.05em]"
            >
              {s.label}
            </text>
            {s.sub && (
              <text
                x={x + bw / 2}
                y={H - 6}
                textAnchor="middle"
                className="fill-faint font-mono text-[8px]"
              >
                {s.sub}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
