import * as React from "react";
import { Section, Stat, Badge, DeltaBadge } from "web";

const twoCol: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "1fr 1fr",
  gap: 12,
};

/** Full heading row — title, description, actions slot — over a KPI grid. */
export const HeadingWithActions = () => (
  <Section
    title="Sermaye Yeterliliği"
    description="Sektör geneli, solo bazda — BDDK Mart 2026"
    actions={
      <>
        <Badge variant="secondary">Çeyreklik</Badge>
        <Badge variant="outline">31 banka</Badge>
      </>
    }
  >
    <div style={twoCol}>
      <Stat
        label="CAR"
        value="17.94%"
        hint="2026-03 · yasal eşik %12"
        badge={<DeltaBadge curr={17.94} prev={17.21} />}
      />
      <Stat
        label="Çekirdek sermaye"
        value="14.21%"
        hint="2026-03 · Tier 1"
        badge={<DeltaBadge curr={14.21} prev={14.05} />}
      />
    </div>
  </Section>
);

/** Title + description only — no actions. */
export const TitledProse = () => (
  <Section
    title="Metodoloji"
    description="Oranların türetilmesi ve kapsam"
  >
    <p className="text-sm text-muted-foreground" style={{ maxWidth: 560 }}>
      ROE, son dört çeyreğin net kârının beş çeyreklik ortalama özkaynağa
      bölünmesiyle hesaplanır; NPL oranı 3. aşama kredilerin toplam nakdi
      kredilere oranıdır. Katılım bankaları özkaynağı bilançoda XIV. kalemde
      raporlar.
    </p>
  </Section>
);

/** Untitled bare section — just spaces its content, no heading row. */
export const Bare = () => (
  <Section>
    <div style={twoCol}>
      <Stat label="NPL oranı" value="2.41%" hint="2026-03 · sektör" tone="positive" />
      <Stat label="YP kredi payı" value="41.3%" hint="2026-03 · kur etkisi dahil" tone="warning" />
    </div>
  </Section>
);
