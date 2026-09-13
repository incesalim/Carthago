import type { ReactNode } from "react";
import Link from "next/link";
import { useText } from "@/i18n/use-text";
import { cadenceLabel, type ObservationMeta } from "@/app/lib/cadence";
import { RELATED_SECTORS, SECTOR_PAGES, type SectorKey } from "@/app/lib/sector-pages";
import styles from "./sector-report.module.css";

export { SectorContents } from "./sector-contents";

export function SectorReport({ children }: { children: ReactNode }) {
  return <main data-sector-page data-sector-report className={styles.report}>{children}</main>;
}

export function SectorHeader({ sector, record, observations }: {
  sector: SectorKey;
  record?: ReactNode;
  observations?: ObservationMeta[];
}) {
  const tx = useText();
  const page = SECTOR_PAGES[sector];
  const dates = observations?.filter((item, i, all) => all.findIndex(other =>
    other.cadence === item.cadence && other.asOf === item.asOf && other.source === item.source) === i);
  return <header className={styles.header}>
    <div className={styles.breadcrumb}>
      {sector === "overview" ? <span>{tx("Banking sector")}</span> : <Link href="/">{tx("Banking sector")}</Link>}
      {sector !== "overview" && <><span aria-hidden="true">/</span><span>{tx(page.title)}</span></>}
    </div>
    <h1>{tx(page.title)}</h1>
    <p className={styles.description}>{tx(page.description)}</p>
    {record && <div className={styles.record}>{tx(record)}</div>}
    {dates && <div className={styles.observations}>
      {dates.map((item, i) => <div key={i}>
        <strong>{tx(cadenceLabel(item.cadence))}</strong>
        {item.asOf && <span>{tx(item.asOf)}</span>}
        {item.source && <span>{tx(item.source)}</span>}
      </div>)}
    </div>}
    {observations?.some(item => item.basis || item.window) && <details className={styles.dataNotes}>
      <summary>{tx("Data coverage and definitions")}</summary>
      <ul>{observations.map((item, i) => <li key={i}>
        <strong>{tx(cadenceLabel(item.cadence))}</strong>{" · "}{tx(item.asOf)}
        {item.window && <>{" · "}{tx(item.window)}</>}
        {item.basis && <>{" · "}{tx(item.basis)}</>}
      </li>)}</ul>
    </details>}
  </header>;
}

export function SectorMetrics({ children }: { children: ReactNode }) {
  const tx = useText();
  return <section id="overview" className={styles.metrics} aria-label={tx("Key indicators")}>
    <h2>{tx("Key indicators")}</h2>
    <div className={styles.metricsGrid}>{children}</div>
  </section>;
}

/** Current figures lead into the first charts; the assessment follows them. */
export function SectorOpening({ children }: { children: ReactNode }) {
  return <div className={styles.opening}>{children}</div>;
}

export function SectorGrid({ children, columns = 2, ratio = "balanced" }: {
  children: ReactNode;
  columns?: 1 | 2 | 3;
  ratio?: "balanced" | "wide-left" | "wide-right";
}) {
  return <div className={styles.grid} data-columns={columns} data-ratio={ratio}>{children}</div>;
}

export function SectorPanel({ children, title, description }: {
  children: ReactNode;
  title?: ReactNode;
  description?: ReactNode;
}) {
  const tx = useText();
  return <div data-sector-panel className={styles.panel}>
    {(title || description) && <header className={styles.panelHeader}>
      {title && <h3>{tx(title)}</h3>}
      {description && <p>{tx(description)}</p>}
    </header>}
    {children}
  </div>;
}

export function SectorSection({ id, title, description, children }: {
  id: string;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
}) {
  const tx = useText();
  return <section id={id} data-sector-section className={styles.section} aria-labelledby={`${id}-title`}>
    <header className={styles.sectionHeader}>
      <h2 id={`${id}-title`}>{tx(title)}</h2>
      {description && <div className={styles.sectionDescription}>{tx(description)}</div>}
    </header>
    <div className={styles.sectionBody}>{children}</div>
  </section>;
}

export function SectorDirectory({ sector = "overview" }: { sector?: SectorKey }) {
  const tx = useText();
  const keys = sector === "overview"
    ? (Object.keys(SECTOR_PAGES) as SectorKey[]).filter(key => key !== "overview")
    : RELATED_SECTORS[sector];
  return <nav className={styles.directory} aria-label={tx(sector === "overview" ? "Explore the banking sector" : "Related sector analysis")}>
    <h2>{tx(sector === "overview" ? "Explore the banking sector" : "Related sector analysis")}</h2>
    <div>{keys.map(key => <Link key={key} href={SECTOR_PAGES[key].href}>
      <span className={styles.directoryTitle}>{tx(SECTOR_PAGES[key].title)}<span aria-hidden="true">↗</span></span>
      <span>{tx(SECTOR_PAGES[key].description)}</span>
    </Link>)}</div>
  </nav>;
}

export function SectorFooter() {
  const tx = useText();
  return <footer className={styles.footer}>
    <p>{tx("Sources: BDDK, BRSA financial statements, TCMB, TÜİK and KAP. Reporting dates and calculation bases are stated with the indicators. Scenarios are illustrative, not forecasts. Analytical information, not investment advice.")}</p>
    <div><Link href="/methodology">{tx("Methodology")}</Link><Link href="/about">{tx("About")}</Link><Link href="/privacy">{tx("Privacy")}</Link></div>
  </footer>;
}
