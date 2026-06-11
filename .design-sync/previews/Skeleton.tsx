import * as React from "react";
import { Card, Skeleton } from "web";

/** Loading KPI tile — bars sized like the real <Stat> label / value / hint. */
export const KpiTileLoading = () => (
  <Card style={{ padding: 20, maxWidth: 280 }}>
    <Skeleton style={{ height: 10, width: 110 }} />
    <Skeleton style={{ height: 28, width: 140, marginTop: 10 }} />
    <Skeleton style={{ height: 12, width: 175, marginTop: 8 }} />
  </Card>
);

/** Bank-ranking table streaming in: full-width row bars, varied widths. */
export const TableRowsLoading = () => (
  <div style={{ display: "flex", flexDirection: "column", gap: 10, maxWidth: 360 }}>
    <Skeleton style={{ height: 16, width: "100%" }} />
    <Skeleton style={{ height: 16, width: "94%" }} />
    <Skeleton style={{ height: 16, width: "98%" }} />
    <Skeleton style={{ height: 16, width: "86%" }} />
  </div>
);
