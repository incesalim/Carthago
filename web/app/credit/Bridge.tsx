/** A horizontal waterfall keeps labels legible inside a narrow analysis panel. */
import { useText } from "@/i18n/use-text";
import { createFormatters } from "@/app/lib/chart-format";
import type { CreditBridge } from "@/app/lib/credit";
import styles from "./bridge.module.css";

type Step = { kind: "level" | "cut"; label: string; sub?: string; value: number; hero?: boolean };

export default function Bridge({ bridge }: { bridge: CreditBridge }) {
  const tx = useText();
  const fmt = createFormatters(tx.locale);
  const { nominalAtReal, fxAdj, realFxAdj, currencyPp, inflationPp, cpi, asOfReal, lagged } = bridge;
  if (nominalAtReal == null || fxAdj == null || realFxAdj == null || currencyPp == null || inflationPp == null) {
    return <p className={styles.empty}>{tx("The bridge needs a nominal print, an FX-adjusted print and a CPI month. One is not yet published.")}</p>;
  }
  const pct = (value: number) => fmt.pct(value, 1);
  const pp = (value: number) => tx("{0} pp", { 0: `${value < 0 ? "−" : "+"}${fmt.raw(Math.abs(value), 1)}` });
  const steps: Step[] = [
    { kind: "level", label: "Nominal 52w", sub: lagged && asOfReal ? tx(asOfReal) : undefined, value: nominalAtReal },
    { kind: "cut", label: "Lira", sub: tx("depreciation"), value: -currencyPp },
    { kind: "level", label: "FX-adjusted", value: fxAdj, hero: true },
    { kind: "cut", label: "Inflation", sub: cpi != null ? tx("CPI {0}%", { 0: fmt.raw(cpi, 1) }) : undefined, value: -inflationPp },
    { kind: "level", label: "Real, const. FX", value: realFxAdj, hero: true },
  ];
  // Every step is from the same observation date. Differences already reconcile
  // in creditBridge; these coordinates display that identity without recomputing it.
  const levels = [0, nominalAtReal, fxAdj, realFxAdj];
  const low = Math.min(...levels);
  const high = Math.max(...levels);
  const span = high - low || 1;
  const position = (value: number) => (value - low) / span * 100;
  const zero = position(0);
  let running = 0;
  const bars = steps.map((step) => {
    const from = step.kind === "level" ? 0 : running;
    const to = step.kind === "level" ? step.value : running + step.value;
    running = to;
    return { step, from, to };
  });

  return <figure className={styles.bridge} aria-label={tx("Exchange-rate and inflation effects")}>
    <ol className={styles.steps}>
      {bars.map(({ step, from, to }) => <li className={styles.step} key={step.label} data-kind={step.kind}>
        <div className={styles.label}>{tx(step.label)}{step.sub && <span>{step.sub}</span>}</div>
        <div className={styles.plot} aria-hidden="true">
          <i className={styles.zero} style={{ left: `${zero}%` }} />
          <span className={styles.bar} data-negative={step.value < 0 || undefined} data-hero={step.hero || undefined}
            style={{ left: `${position(Math.min(from, to))}%`, width: `${Math.abs(to - from) / span * 100}%` }} />
          {step.kind === "cut" && <><i className={styles.endpoint} style={{ left: `${position(from)}%` }} /><i className={styles.endpoint} style={{ left: `${position(to)}%` }} /></>}
        </div>
        <strong className={styles.value} data-negative={step.value < 0 || undefined}>{step.kind === "cut" ? pp(step.value) : pct(step.value)}</strong>
      </li>)}
    </ol>
    <div className={styles.axis} aria-hidden="true"><span>{pct(low)}</span><span>{pct(high)}</span></div>
  </figure>;
}
