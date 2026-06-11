import * as React from "react";
import { DeltaBadge } from "web";

const row: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  flexWrap: "wrap",
};

const label: React.CSSProperties = { minWidth: 130 };

/** Higher is better and it rose — green up chip (sector CAR). */
export const UpGood = () => (
  <div style={row}>
    <span className="text-sm text-muted-foreground" style={label}>
      Sermaye yeterliliği
    </span>
    <span className="text-sm font-semibold tabular-nums">CAR 17.94%</span>
    <DeltaBadge curr={17.94} prev={17.21} />
  </div>
);

/** Higher is better but it fell — red down chip (ROE cooling off). */
export const DownBad = () => (
  <div style={row}>
    <span className="text-sm text-muted-foreground" style={label}>
      Özkaynak kârlılığı
    </span>
    <span className="text-sm font-semibold tabular-nums">ROE 36.10%</span>
    <DeltaBadge curr={36.1} prev={38.6} />
  </div>
);

/** Lower is better and it fell — goodDirection="down" turns the drop green (NPL). */
export const DownGood = () => (
  <div style={row}>
    <span className="text-sm text-muted-foreground" style={label}>
      Takipteki alacaklar
    </span>
    <span className="text-sm font-semibold tabular-nums">NPL 2.41%</span>
    <DeltaBadge curr={2.41} prev={2.63} goodDirection="down" />
  </div>
);

/** Sub-precision move reads as flat — grey arrow, no colour from rounding noise. */
export const Flat = () => (
  <div style={row}>
    <span className="text-sm text-muted-foreground" style={label}>
      Kredi / mevduat
    </span>
    <span className="text-sm font-semibold tabular-nums">84.30%</span>
    <DeltaBadge curr={84.301} prev={84.298} />
  </div>
);

/** "trn" format — balance-sheet level deltas in ₺ trillions (inputs in ₺ millions). */
export const TrillionTL = () => (
  <div style={row}>
    <span className="text-sm text-muted-foreground" style={label}>
      Toplam aktifler
    </span>
    <span className="text-sm font-semibold tabular-nums">₺38.2 trn</span>
    <DeltaBadge curr={38_200_000} prev={36_950_000} format="trn" decimals={1} />
  </div>
);

/** goodDirection="neutral" — directional fact, no value judgement (branch count). */
export const NeutralDirection = () => (
  <div style={row}>
    <span className="text-sm text-muted-foreground" style={label}>
      Şube sayısı
    </span>
    <span className="text-sm font-semibold tabular-nums">10 942</span>
    <DeltaBadge curr={10942} prev={11014} format="raw" decimals={0} goodDirection="neutral" />
  </div>
);
