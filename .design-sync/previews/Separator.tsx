import * as React from "react";
import { Card, Separator } from "web";

/** Horizontal hairline dividing a KPI readout from its source footnote. */
export const Horizontal = () => (
  <Card style={{ padding: 20, maxWidth: 340 }}>
    <div className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
      Sektör toplam aktifleri
    </div>
    <div className="text-2xl font-semibold tabular-nums tracking-tight" style={{ marginTop: 6 }}>
      ₺38,2 trn
    </div>
    <Separator style={{ marginTop: 14, marginBottom: 12 }} />
    <p className="text-xs text-muted-foreground" style={{ margin: 0 }}>
      Kaynak: BDDK aylık bülten · Mart 2026 · 31 banka konsolide
    </p>
  </Card>
);

/** Vertical rules between inline meta items (fixed-height flex row). */
export const Vertical = () => (
  <div
    className="text-sm text-muted-foreground"
    style={{ display: "flex", alignItems: "center", gap: 12, height: 20 }}
  >
    <span className="font-medium text-foreground">Garanti BBVA</span>
    <Separator orientation="vertical" />
    <span>Mevduat bankası</span>
    <Separator orientation="vertical" />
    <span className="tabular-nums">Mar 2026</span>
  </div>
);
