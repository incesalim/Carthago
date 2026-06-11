import * as React from "react";
import { Badge } from "web";

const row: React.CSSProperties = { display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" };

/** Every variant of the pill, labeled with its variant name. */
export const Variants = () => (
  <div style={row}>
    <Badge>default</Badge>
    <Badge variant="secondary">secondary</Badge>
    <Badge variant="outline">outline</Badge>
    <Badge variant="positive">positive</Badge>
    <Badge variant="negative">negative</Badge>
    <Badge variant="warning">warning</Badge>
    <Badge variant="info">info</Badge>
  </div>
);

/** Data-semantic chips the dashboard actually renders. */
export const DataSemantics = () => (
  <div style={row}>
    <Badge variant="positive">CAR 17.9%</Badge>
    <Badge variant="negative">NPL 2.4%</Badge>
    <Badge variant="warning">FX share 41%</Badge>
    <Badge variant="info">Participation</Badge>
    <Badge variant="secondary">
      <span style={{ width: 6, height: 6, borderRadius: 9999 }} className="bg-positive" aria-hidden="true" />
      Data through Mar 2026
    </Badge>
  </div>
);

/** Brand-accent badges used as section eyebrows and counts. */
export const BrandAccent = () => (
  <div style={row}>
    <Badge>31 banks</Badge>
    <Badge>Kamu bankaları</Badge>
    <Badge variant="outline">₺38.2 trn</Badge>
  </div>
);
