import * as React from "react";
import { Card, Separator, ThemeToggle } from "web";

/** Bare toggle — a single 36px icon button (moon in light theme). */
export const Default = () => <ThemeToggle />;

/** Composed at the right edge of a dashboard header toolbar. */
export const InToolbar = () => (
  <Card
    style={{
      display: "flex",
      alignItems: "center",
      gap: 12,
      padding: "8px 14px",
      maxWidth: 420,
    }}
  >
    <span className="text-sm font-semibold">BDDK Bankacılık Görünümü</span>
    <span className="text-xs text-muted-foreground">Mart 2026 verisi</span>
    <div
      style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10, height: 20 }}
    >
      <Separator orientation="vertical" />
      <ThemeToggle />
    </div>
  </Card>
);
