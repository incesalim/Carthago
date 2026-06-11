import * as React from "react";
import { Badge, DeltaBadge, Stat } from "web";

/** Canonical KPI tile: label, tabular value, period hint. */
export const Default = () => (
  <Stat label="Total assets" value="₺38.2 trn" hint="Mar 2026 · all banks" />
);

/** The four tones, as the sector-overview KPI row uses them. */
export const Tones = () => (
  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
    <Stat label="Net income" value="₺712 bn" hint="2026 YTD" tone="neutral" />
    <Stat label="CAR" value="17.9%" hint="Mar 2026 · sector" tone="positive" />
    <Stat label="FX loan share" value="41.3%" hint="Mar 2026" tone="warning" />
    <Stat label="NPL ratio" value="2.41%" hint="Mar 2026 · gross" tone="negative" />
  </div>
);

/** Badge slot: period-over-period delta chip next to the label. */
export const WithDeltaBadge = () => (
  <Stat
    label="ROE (TTM)"
    value="38.6%"
    hint="Trailing 4 quarters / 5-quarter avg. equity"
    badge={<DeltaBadge curr={38.6} prev={41.2} format="pp" decimals={1} />}
  />
);

/** Children slot: a sparkline rendered under the value. */
export const WithSparkline = () => (
  <Stat
    label="Loan growth"
    value="+34.2%"
    hint="y/y, FX-adjusted"
    tone="positive"
    badge={<Badge variant="positive">▲ 1.8pp</Badge>}
  >
    <svg viewBox="0 0 200 36" style={{ width: "100%", height: 36 }} aria-hidden="true">
      <polyline
        points="0,30 20,28 40,29 60,24 80,25 100,20 120,21 140,16 160,14 180,10 200,6"
        fill="none"
        stroke="var(--chart-1)"
        strokeWidth="2"
      />
    </svg>
  </Stat>
);
