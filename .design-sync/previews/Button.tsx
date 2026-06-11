import * as React from "react";
import { Button } from "web";
import { Download, RefreshCw, ChevronRight, Filter } from "lucide-react";

const row: React.CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: 8,
  alignItems: "center",
};

/** All six visual variants at default size. */
export const Variants = () => (
  <div style={row}>
    <Button>Raporu indir</Button>
    <Button variant="secondary">Sektör görünümü</Button>
    <Button variant="outline">Filtrele</Button>
    <Button variant="ghost">Temizle</Button>
    <Button variant="destructive">Veriyi sıfırla</Button>
    <Button variant="link">Tüm bankalar</Button>
  </div>
);

/** Size ramp: sm / default / lg / icon. */
export const Sizes = () => (
  <div style={row}>
    <Button size="sm">2026-Q1</Button>
    <Button size="default">Karşılaştır</Button>
    <Button size="lg">Bilanço analizi</Button>
    <Button size="icon" aria-label="Yenile">
      <RefreshCw />
    </Button>
  </div>
);

/** Icon + label compositions the dashboard toolbars use. */
export const WithIcons = () => (
  <div style={row}>
    <Button>
      <Download />
      CSV indir
    </Button>
    <Button variant="outline">
      <Filter />
      Banka grubu
    </Button>
    <Button variant="ghost" size="sm">
      Garanti BBVA detayı
      <ChevronRight />
    </Button>
  </div>
);

/** Disabled state across the main variants. */
export const Disabled = () => (
  <div style={row}>
    <Button disabled>Raporu indir</Button>
    <Button variant="secondary" disabled>
      Sektör görünümü
    </Button>
    <Button variant="outline" disabled>
      Filtrele
    </Button>
    <Button variant="destructive" disabled>
      Veriyi sıfırla
    </Button>
  </div>
);
