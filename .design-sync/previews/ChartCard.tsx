import * as React from "react";
import { ChartCard, Button } from "web";

/** Simple line chart placeholder drawn with chart tokens. */
const LineChartSvg = () => (
  <svg viewBox="0 0 280 120" style={{ width: "100%", height: 120, display: "block" }}>
    <line x1="0" y1="100" x2="280" y2="100" stroke="var(--border)" strokeWidth="1" />
    <line x1="0" y1="60" x2="280" y2="60" stroke="var(--border)" strokeWidth="1" strokeDasharray="3 3" />
    <line x1="0" y1="20" x2="280" y2="20" stroke="var(--border)" strokeWidth="1" strokeDasharray="3 3" />
    <polyline
      points="0,86 40,80 80,72 120,75 160,58 200,46 240,38 280,30"
      fill="none"
      stroke="var(--chart-1)"
      strokeWidth="2"
    />
    <polyline
      points="0,95 40,92 80,90 120,84 160,82 200,74 240,70 280,64"
      fill="none"
      stroke="var(--chart-2)"
      strokeWidth="2"
    />
  </svg>
);

/** Canonical chart card: title, description and an action slot. */
export const WithAction = () => (
  <ChartCard
    title="Toplam krediler"
    description="Aylık, ₺ trilyon — Kamu vs özel mevduat bankaları"
    action={
      <Button size="sm" variant="outline">
        2026-Q1
      </Button>
    }
  >
    <LineChartSvg />
  </ChartCard>
);

/** Grouped bars using the chart token ramp. */
export const BarChart = () => (
  <ChartCard
    title="SYR (CAR) — seçili bankalar"
    description="Mart 2026, konsolide olmayan"
  >
    <svg viewBox="0 0 280 130" style={{ width: "100%", height: 130, display: "block" }}>
      <line x1="0" y1="110" x2="280" y2="110" stroke="var(--border)" strokeWidth="1" />
      <rect x="20" y="38" width="28" height="72" fill="var(--chart-1)" rx="2" />
      <rect x="80" y="50" width="28" height="60" fill="var(--chart-2)" rx="2" />
      <rect x="140" y="30" width="28" height="80" fill="var(--chart-3)" rx="2" />
      <rect x="200" y="58" width="28" height="52" fill="var(--chart-1)" rx="2" />
      <text x="34" y="124" textAnchor="middle" fontSize="9" fill="var(--muted-foreground)">
        Ziraat
      </text>
      <text x="94" y="124" textAnchor="middle" fontSize="9" fill="var(--muted-foreground)">
        İş Bankası
      </text>
      <text x="154" y="124" textAnchor="middle" fontSize="9" fill="var(--muted-foreground)">
        Garanti BBVA
      </text>
      <text x="214" y="124" textAnchor="middle" fontSize="9" fill="var(--muted-foreground)">
        Akbank
      </text>
    </svg>
  </ChartCard>
);

/** Title-only header, no description or action. */
export const TitleOnly = () => (
  <ChartCard title="Takipteki krediler oranı (NPL)">
    <svg viewBox="0 0 280 100" style={{ width: "100%", height: 100, display: "block" }}>
      <line x1="0" y1="84" x2="280" y2="84" stroke="var(--border)" strokeWidth="1" />
      <polyline
        points="0,30 40,36 80,44 120,52 160,56 200,60 240,66 280,70"
        fill="none"
        stroke="var(--chart-3)"
        strokeWidth="2"
      />
      <circle cx="280" cy="70" r="3" fill="var(--chart-3)" />
    </svg>
  </ChartCard>
);
