"use client";

import type { ReactNode } from "react";
import { useText } from "@/i18n/use-text";
import { ChartCard } from "./ui/chart-card";
import { ChartData } from "./ui/chart-csv";
import { createFormatters } from "@/app/lib/chart-format";
import type { BulletinBridgeRow } from "@/app/lib/sector-bddk-detail";
import styles from "./sector-breakdown.module.css";

/** A horizontal cumulative bridge keeps financial labels readable on phones.
 * Each component starts where the previous one ended; the published total
 * starts at zero. Inputs have already passed the source identity check. */
export default function SectorBalanceBridge({ rows, title, description, source, asOf }: {
  rows: BulletinBridgeRow[];
  title: ReactNode;
  description?: ReactNode;
  source?: ReactNode;
  asOf?: string;
}) {
  const tx = useText();
  const fmt = createFormatters(tx.locale);
  const steps = rows.map((row, index) => {
    const running = rows.slice(0, index).reduce((sum, prior) => sum + (prior.total ? 0 : prior.value), 0);
    const from = row.total ? 0 : running;
    const to = row.total ? row.value : running + row.value;
    return { ...row, from, to };
  });
  const low = Math.min(0, ...steps.flatMap(r => [r.from, r.to]));
  const high = Math.max(0, ...steps.flatMap(r => [r.from, r.to]));
  const span = high - low || 1;
  const place = (v: number) => ((v - low) / span) * 100;
  return <ChartCard plain title={title} description={description} source={<>{source}{asOf && <> · {tx(asOf)}</>}</>}>
    <ChartData table={{ columns: [`${tx("Component")}${asOf ? ` (${asOf})` : ""}`, `${tx("Value")} (${tx("TL million")})`],
      rows: rows.map(r => [tx(r.label), r.value]) }} />
    {rows.length === 0 ? <p className="py-10 text-sm text-muted-foreground">{tx("The published components are incomplete or do not reconcile to the total.")}</p> :
      <div className="space-y-1 py-2">
        {steps.map(row => <div key={row.id} className={`${styles.bridgeRow} ${row.total ? styles.bridgeTotal : ""}`}>
          <div className="min-w-0 text-sm leading-snug">{tx(row.label)}</div>
          <div className={styles.bridgePlot}>
            <span className="absolute inset-y-[-6px] border-l border-dashed border-muted-foreground/50" style={{ left: `${place(0)}%` }} />
            <span className={`absolute top-1 h-5 rounded-sm ${row.value < 0 ? "bg-negative" : "bg-data"}`}
              style={{ left: `${place(Math.min(row.from, row.to))}%`, width: `${Math.abs(row.to - row.from) / span * 100}%`, minWidth: row.value === 0 ? 0 : 1 }} />
          </div>
          <div className={styles.bridgeValue}>{fmt.bn(row.value, 1)}</div>
        </div>)}
        <div className="pt-3 text-xs text-muted-foreground">{tx("Cumulative bridge · TL billion")}</div>
      </div>}
  </ChartCard>;
}
