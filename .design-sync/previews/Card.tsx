import * as React from "react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
  Button,
} from "web";

const metricRow: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "baseline",
  padding: "6px 0",
};

/** Full composition: header, title, description, content, footer. */
export const FullComposition = () => (
  <Card style={{ maxWidth: 360 }}>
    <CardHeader>
      <CardTitle>Ziraat Bankası — 2026-Q1</CardTitle>
      <CardDescription>
        Konsolide olmayan bağımsız denetim raporu, BDDK formatı
      </CardDescription>
    </CardHeader>
    <CardContent>
      <div style={metricRow}>
        <span className="text-muted-foreground" style={{ fontSize: 12 }}>
          Aktif toplamı
        </span>
        <span style={{ fontSize: 14, fontWeight: 600 }}>₺7.94 trn</span>
      </div>
      <div style={metricRow}>
        <span className="text-muted-foreground" style={{ fontSize: 12 }}>
          SYR (CAR)
        </span>
        <span style={{ fontSize: 14, fontWeight: 600 }}>17.9%</span>
      </div>
      <div style={metricRow}>
        <span className="text-muted-foreground" style={{ fontSize: 12 }}>
          Takipteki krediler (NPL)
        </span>
        <span style={{ fontSize: 14, fontWeight: 600 }}>2.41%</span>
      </div>
    </CardContent>
    <CardFooter style={{ gap: 8 }}>
      <Button size="sm">Detaya git</Button>
      <Button size="sm" variant="outline">
        PDF kaynağı
      </Button>
    </CardFooter>
  </Card>
);

/** Header + content only — the most common dashboard panel shape. */
export const HeaderAndContent = () => (
  <Card style={{ maxWidth: 360 }}>
    <CardHeader>
      <CardTitle>Sektör mevduatı</CardTitle>
      <CardDescription>Mart 2026, tüm bankacılık sektörü</CardDescription>
    </CardHeader>
    <CardContent>
      <div style={{ fontSize: 24, fontWeight: 700 }}>₺38.2 trn</div>
      <p className="text-muted-foreground" style={{ fontSize: 12, marginTop: 4 }}>
        Yıllık artış <span className="text-positive">+%48.3</span> · TP payı %59
      </p>
    </CardContent>
  </Card>
);

/** Bare card surface used as a custom container. */
export const Minimal = () => (
  <Card style={{ maxWidth: 360, padding: 20 }}>
    <p style={{ fontSize: 13, margin: 0 }}>
      İş Bankası 2026-Q1 finansalları 12 Mayıs&apos;ta KAP&apos;a iletildi.
    </p>
  </Card>
);
