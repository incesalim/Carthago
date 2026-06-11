import * as React from "react";
import { PageHeader, Badge } from "web";

/** The canonical tab header: eyebrow, title, description, data-freshness badge and actions. */
export const Canonical = () => (
  <PageHeader
    eyebrow="Sektör Görünümü"
    title="Türk Bankacılık Sektörü"
    description="BDDK aylık verileriyle bilanço, kârlılık ve aktif kalitesi — mevduat ve katılım dahil."
    dataThrough="2026-03"
  >
    <Badge>31 banka</Badge>
  </PageHeader>
);

/** Minimal: a title and nothing else. */
export const TitleOnly = () => <PageHeader title="Krediler" />;

/** Daily-cadence tab: full-date dataThrough renders as '23 Mar 2026'. */
export const FullDateBadge = () => (
  <PageHeader
    eyebrow="Haftalık Bülten"
    title="Kredi Gelişmeleri"
    description="TCMB haftalık para ve banka istatistiklerinden kredi stoku ve büyüme."
    dataThrough="2026-03-23"
  />
);
