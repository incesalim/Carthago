import type { ReactNode } from "react";
import { useText } from "@/i18n/use-text";
import styles from "./sector-page.module.css";

/** Layout only: routes retain ownership of every query, calculation and chart. */
export function SectorPage({ children }: { children: ReactNode }) {
  return <main data-sector-page className={styles.page}>{children}</main>;
}

export function SectorNav({ sections }: { sections: { id: string; label: string }[] }) {
  const tx = useText();
  return <nav className={styles.navigation} aria-label={tx("On this page")}>
    {sections.map(({ id, label }) => <a key={id} href={`#${id}`}>{tx(label)}</a>)}
  </nav>;
}

/** The existing measure and chart move here intact, including notes and exports. */
export function SectorLead({ question, observation, metric, chart, controls }: {
  question: string;
  observation?: ReactNode;
  metric: ReactNode;
  chart: ReactNode;
  controls?: ReactNode;
}) {
  const tx = useText();
  return <section id="overview" className={styles.lead} aria-label={tx(question)}>
    <div className={styles.summary}>
      <p className={styles.kicker}>{tx("Sector outlook")}</p>
      <h2>{tx(question)}</h2>
      {observation && <div className={styles.observation}>{tx(observation)}</div>}
      {metric}
    </div>
    <div className={styles.primaryChart}>
      {controls && <div className={styles.controls}><span>{tx("Chart history")}</span>{controls}</div>}
      {chart}
    </div>
  </section>;
}

/** Keeps the original section's context connected to its relocated main chart. */
export function LeadChartLink() {
  const tx = useText();
  return <a data-lead-chart-link className={styles.chartLink} href="#overview">{tx("See the main chart above")} <span aria-hidden="true">↑</span></a>;
}
