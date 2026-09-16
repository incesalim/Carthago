"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  CadenceBand,
  Colophon,
  Compare,
  DeskHeader,
  LayerHead,
  SecHead,
  Vital,
  Vitals,
} from "@/app/components/desk";
import type { ObservationMeta } from "@/app/lib/cadence";
import { createFormatters } from "@/app/lib/chart-format";
import {
  crosshairCursor,
  PLOT_MARGIN_LEFT,
  tooltipStyles,
  useChartTheme,
  Y_AXIS_WIDTH,
} from "@/app/lib/chart-theme";

type SummaryFormat = "pct" | "bn";

interface SummaryMetric {
  label: string;
  value: number | null;
  format: SummaryFormat;
}

interface GroupSnapshot {
  code: string;
  label: string;
  value: number;
  previous: number | null;
  delta: number | null;
}

export interface CreditPrototypeData {
  kind: "credit";
  title: string;
  question: string;
  cadence: string;
  asOf: string;
  commonCutoff: string;
  headline: string;
  summary: SummaryMetric[];
  bridge: Array<{
    label: string;
    value: number | null;
    kind: "total" | "delta" | "subtotal";
  }>;
  trend: Array<Record<string, string | number | null>>;
  contributions: Array<{
    key: string;
    label: string;
    value: number;
    growth: number;
    level: number;
    nested: { label: string; value: number } | null;
  }>;
  groups: GroupSnapshot[];
  sourceNote: string;
}

export interface LiquidityPrototypeData {
  kind: "liquidity";
  title: string;
  question: string;
  cadence: string;
  asOf: string;
  weeklyAsOf: string;
  quarterlyAsOf: string;
  headline: string;
  summary: SummaryMetric[];
  funding: Array<{ period: string; value: number }>;
  ldr: Array<Record<string, string | number | null>>;
  ownershipGrowth: GroupSnapshot[];
  regulatory: Array<{ label: string; short: string; value: number | null; floor: number }>;
  publicLdr: number | null;
  privateLdr: number | null;
  sourceNote: string;
}

export type PrototypeData = CreditPrototypeData | LiquidityPrototypeData;

const fmt = createFormatters("tr");

const metricValue = (value: number | null, digits = 1) =>
  value == null ? "—" : fmt.raw(value, digits);

const signedPp = (value: number | null, digits = 1) => {
  if (value == null) return "—";
  return `${value >= 0 ? "+" : "−"}${fmt.raw(Math.abs(value), digits)} yp`;
};

const shortDate = (value: string | number) => {
  const raw = String(value);
  const months = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"];
  const match = /^(\d{4})-(\d{2})/.exec(raw);
  return match ? `${months[Number(match[2]) - 1]} ${match[1]}` : raw;
};

const tooltipDate = (value: ReactNode) =>
  shortDate(typeof value === "string" || typeof value === "number" ? value : "");

function PrototypeHeader({ data }: { data: PrototypeData }) {
  const observations: ObservationMeta[] = data.kind === "credit"
    ? [
        {
          cadence: "weekly",
          role: "current",
          asOf: data.asOf,
          window: "52 haftalık değişim",
          basis: "BDDK sektör kredileri",
        },
        {
          cadence: "monthly",
          role: "structure",
          asOf: data.commonCutoff,
          basis: "TÜFE ile ortak veri kesimi",
        },
      ]
    : [
        {
          cadence: "daily",
          role: "current",
          asOf: data.asOf,
          basis: "TCMB net fonlama",
        },
        {
          cadence: "weekly",
          role: "structure",
          asOf: data.weeklyAsOf,
          basis: "BDDK TL kredi ve mevduat",
        },
        {
          cadence: "quarterly",
          role: "audited",
          asOf: data.quarterlyAsOf,
          basis: "BRSA LCR ve NSFR",
        },
      ];

  return (
    <>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3 border-b border-hair pb-2">
        <span className="font-mono text-[8.5px] uppercase tracking-[0.08em] text-faint">
          Yerel tasarım denemesi · V3
        </span>
        <nav aria-label="Prototip sayfaları" className="flex gap-5 text-[11px] font-semibold">
          <Link
            href="/lab/sector-v2?page=credit"
            aria-current={data.kind === "credit" ? "page" : undefined}
            className={`pb-1 text-primary ${data.kind === "credit" ? "border-b-2 border-foreground text-foreground" : "hover:underline"}`}
          >
            Krediler
          </Link>
          <Link
            href="/lab/sector-v2?page=liquidity"
            aria-current={data.kind === "liquidity" ? "page" : undefined}
            className={`pb-1 text-primary ${data.kind === "liquidity" ? "border-b-2 border-foreground text-foreground" : "hover:underline"}`}
          >
            Likidite
          </Link>
        </nav>
      </div>
      <DeskHeader
        title={data.title}
        record={<>{data.cadence} · <b className="font-normal text-foreground">{data.asOf}</b></>}
        right="her rakam kaynak serilerinden hesaplanır"
        observations={observations}
      />
    </>
  );
}

function OpeningRead({ data }: { data: PrototypeData }) {
  return (
    <div className="mt-5 grid gap-4 border-b border-hair pb-5 lg:grid-cols-[minmax(0,4fr)_minmax(0,7fr)] lg:items-start">
      <p className="text-[13px] font-medium leading-relaxed text-muted-foreground">{data.question}</p>
      <p className="max-w-[58rem] text-[18px] font-semibold leading-snug tracking-tight text-foreground">
        {data.headline}
      </p>
    </div>
  );
}

function MetricBand({ data }: { data: PrototypeData }) {
  return (
    <section className="mt-7">
      <SecHead title="Ana göstergeler" meta={`${data.cadence} · ${data.asOf}`} className="mb-2.5" />
      <Vitals cols={3}>
        {data.summary.map((metric) => (
          <Vital
            key={metric.label}
            label={metric.label}
            value={metricValue(metric.value, metric.format === "pct" ? 1 : 0)}
            unit={metric.format === "pct" ? "%" : "milyar ₺"}
            format="raw"
          />
        ))}
      </Vitals>
    </section>
  );
}

function BridgePanel({ data }: { data: CreditPrototypeData }) {
  return (
    <div className="max-w-[58rem]">
      <SecHead
        title="Nominal büyümeden reel hacme"
        meta={`ortak veri kesimi · ${data.commonCutoff}`}
        className="mb-2.5"
      />
      <div className="grid border-t-2 border-foreground sm:grid-cols-5">
        {data.bridge.map((step, index) => {
          const isDelta = step.kind === "delta";
          return (
            <div
              key={step.label}
              className="grid grid-cols-[2rem_1fr_auto] items-baseline gap-2 border-b border-hair py-3 sm:block sm:min-h-[118px] sm:border-r sm:px-3 sm:first:pl-0 sm:last:border-r-0"
            >
              <span className="font-mono text-[8px] text-faint">0{index + 1}</span>
              <div className="text-[11px] font-medium text-muted-foreground sm:mt-4">{step.label}</div>
              <div className={`font-mono text-[17px] font-semibold tabular-nums sm:mt-1 sm:text-[20px] ${isDelta ? "text-negative" : "text-foreground"}`}>
                {step.value == null
                  ? "—"
                  : isDelta
                    ? signedPp(step.value)
                    : `${metricValue(step.value)}%`}
              </div>
              <div className={`col-span-full mt-2 h-0.5 sm:mt-4 ${isDelta ? "bg-negative" : step.kind === "subtotal" ? "bg-context" : "bg-data"}`} />
            </div>
          );
        })}
      </div>
      <p className="mt-2.5 max-w-[72ch] font-mono text-[8.5px] uppercase leading-relaxed tracking-[0.04em] text-faint">
        TÜFE yalnızca yayımlanmış son aya kadar kullanılır; daha güncel haftalar için tahmin üretilmez.
      </p>
    </div>
  );
}

function ChartHeading({ title, meta }: { title: string; meta: string }) {
  return (
    <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
      <h3 className="text-[13.5px] font-bold text-foreground">{title}</h3>
      <span className="font-mono text-[8.5px] uppercase tracking-[0.06em] text-faint">{meta}</span>
    </div>
  );
}

function CreditTrend({ data }: { data: CreditPrototypeData }) {
  const t = useChartTheme();
  return (
    <div className="w-full max-w-[52rem]">
      <ChartHeading title="Kredi büyümesinin üç görünümü" meta="52 hafta · yüzde · haftalık" />
      <div className="h-[290px] border-t border-hair pt-3">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data.trend} margin={{ top: 6, right: 10, bottom: 2, left: PLOT_MARGIN_LEFT }}>
            <CartesianGrid vertical={false} stroke={t.grid} />
            <XAxis dataKey="period" minTickGap={70} tickFormatter={shortDate} tick={{ fontSize: 10, fill: t.axis, fontFamily: "var(--font-mono)" }} axisLine={false} tickLine={false} />
            <YAxis width={Y_AXIS_WIDTH} tickFormatter={(value) => `${fmt.raw(Number(value), 0)}%`} tick={{ fontSize: 10, fill: t.axis, fontFamily: "var(--font-mono)" }} axisLine={false} tickLine={false} />
            <ReferenceLine y={0} stroke={t.reference} strokeDasharray="3 3" />
            <Tooltip {...tooltipStyles(t)} cursor={crosshairCursor(t)} labelFormatter={tooltipDate} formatter={(value, name) => [`${fmt.raw(Number(value), 1)}%`, name]} />
            <Line type="monotone" dataKey="nominal" name="Nominal" stroke={t.hero} strokeWidth={2.2} dot={false} activeDot={{ r: 3 }} />
            <Line type="monotone" dataKey="fxAdjusted" name="Sabit kur" stroke={t.palette[1]} strokeWidth={1.7} dot={false} activeDot={{ r: 3 }} />
            <Line type="monotone" dataKey="realFxAdjusted" name="Reel, sabit kur" stroke={t.contextActive} strokeWidth={1.6} strokeDasharray="5 4" dot={false} activeDot={{ r: 3 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 font-mono text-[8.5px] uppercase tracking-[0.04em] text-faint">
        <span><i className="mr-1.5 inline-block h-0.5 w-5 align-middle bg-data" />Nominal</span>
        <span><i className="mr-1.5 inline-block h-0.5 w-5 align-middle bg-[var(--chart-2)]" />Sabit kur</span>
        <span><i className="mr-1.5 inline-block w-5 border-t border-dashed border-muted-foreground align-middle" />Reel, sabit kur</span>
      </div>
    </div>
  );
}

function ContributionPanel({ data }: { data: CreditPrototypeData }) {
  const max = Math.max(1, ...data.contributions.map((item) => Math.abs(item.value)));
  return (
    <div>
      <ChartHeading title="Büyümeye katkı" meta="52 hafta · yüzde puan" />
      <div className="border-t border-foreground">
        {data.contributions.map((item) => (
          <div key={item.key} className="border-b border-hair py-2.5">
            <div className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-3">
              <span className="text-[12px] font-medium text-foreground">{item.label}</span>
              <span className="font-mono text-[12px] font-semibold tabular-nums text-foreground">{signedPp(item.value)}</span>
            </div>
            <div className="mt-1.5 h-1 bg-hair">
              <div className="h-full bg-data" style={{ width: `${Math.max(1.5, (Math.abs(item.value) / max) * 100)}%` }} />
            </div>
            {item.nested && (
              <div className="mt-1.5 flex justify-between gap-3 border-l border-context pl-2 text-[9.5px] text-faint">
                <span>{item.nested.label}</span>
                <span className="font-mono">{signedPp(item.nested.value)}</span>
              </div>
            )}
          </div>
        ))}
      </div>
      <p className="mt-2 font-mono text-[8px] uppercase leading-relaxed tracking-[0.04em] text-faint">
        KOBİ, ticari kredilerin içindedir; toplam katkıya ikinci kez eklenmez.
      </p>
    </div>
  );
}

function GroupComparison({ groups, title, meta }: { groups: GroupSnapshot[]; title: string; meta: string }) {
  const min = Math.min(0, ...groups.map((group) => group.value), ...groups.map((group) => group.previous ?? group.value));
  const max = Math.max(1, ...groups.map((group) => group.value), ...groups.map((group) => group.previous ?? group.value));
  const position = (value: number) => ((value - min) / (max - min || 1)) * 100;
  return (
    <div className="w-full max-w-[64rem]">
      <ChartHeading title={title} meta={meta} />
      <div className="border-t border-foreground">
        {groups.map((group) => (
          <div key={group.code} className="grid gap-2 border-b border-hair py-2.5 sm:grid-cols-[150px_minmax(0,1fr)_78px_74px] sm:items-center">
            <div className="text-[11.5px] font-medium text-foreground">{group.label}</div>
            <div className="relative h-5">
              <div className="absolute inset-x-0 top-1/2 h-px bg-hair" />
              {group.previous != null && (
                <span className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border border-muted-foreground bg-card" style={{ left: `${position(group.previous)}%` }} />
              )}
              <span className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-data ring-2 ring-card" style={{ left: `${position(group.value)}%` }} />
            </div>
            <div className="text-right font-mono text-[12px] font-semibold text-foreground">{metricValue(group.value)}%</div>
            <div className="text-right font-mono text-[9px] text-faint">{signedPp(group.delta)}</div>
          </div>
        ))}
      </div>
      <div className="mt-2 flex gap-5 font-mono text-[8px] uppercase tracking-[0.04em] text-faint">
        <span><i className="mr-1.5 inline-block h-2 w-2 rounded-full bg-data" />Güncel</span>
        <span><i className="mr-1.5 inline-block h-2 w-2 rounded-full border border-muted-foreground" />13 hafta önce</span>
      </div>
    </div>
  );
}

function FundingChart({ data }: { data: LiquidityPrototypeData }) {
  const t = useChartTheme();
  return (
    <div className="w-full max-w-[52rem]">
      <ChartHeading title="Net TCMB fonlaması" meta="milyar TL · günlük" />
      <div className="h-[300px] border-t border-hair pt-3">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data.funding} margin={{ top: 6, right: 10, bottom: 2, left: PLOT_MARGIN_LEFT }}>
            <CartesianGrid vertical={false} stroke={t.grid} />
            <XAxis dataKey="period" minTickGap={76} tickFormatter={shortDate} tick={{ fontSize: 10, fill: t.axis, fontFamily: "var(--font-mono)" }} axisLine={false} tickLine={false} />
            <YAxis width={Y_AXIS_WIDTH} tickFormatter={(value) => `₺${fmt.raw(Number(value), 0)}`} tick={{ fontSize: 10, fill: t.axis, fontFamily: "var(--font-mono)" }} axisLine={false} tickLine={false} />
            <ReferenceLine y={0} stroke={t.reference} />
            <Tooltip {...tooltipStyles(t)} cursor={crosshairCursor(t)} labelFormatter={tooltipDate} formatter={(value) => [`₺${fmt.raw(Number(value), 0)} milyar`, "Net fonlama"]} />
            <Line type="monotone" dataKey="value" name="Net fonlama" stroke={t.hero} strokeWidth={2.1} dot={false} activeDot={{ r: 3 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-2 font-mono text-[8px] uppercase tracking-[0.04em] text-faint">Sıfırın altı sistem açığını, üstü likidite fazlasını gösterir.</p>
    </div>
  );
}

function LdrChart({ data }: { data: LiquidityPrototypeData }) {
  const t = useChartTheme();
  return (
    <div className="w-full max-w-[52rem]">
      <ChartHeading title="TL kredi / mevduat oranı" meta="kamu ve özel · haftalık" />
      <div className="h-[275px] border-t border-hair pt-3">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data.ldr} margin={{ top: 6, right: 10, bottom: 2, left: PLOT_MARGIN_LEFT }}>
            <CartesianGrid vertical={false} stroke={t.grid} />
            <XAxis dataKey="period" minTickGap={72} tickFormatter={shortDate} tick={{ fontSize: 10, fill: t.axis, fontFamily: "var(--font-mono)" }} axisLine={false} tickLine={false} />
            <YAxis width={Y_AXIS_WIDTH} domain={["dataMin - 4", "dataMax + 4"]} tickFormatter={(value) => `${fmt.raw(Number(value), 0)}%`} tick={{ fontSize: 10, fill: t.axis, fontFamily: "var(--font-mono)" }} axisLine={false} tickLine={false} />
            <ReferenceLine y={100} stroke={t.reference} strokeDasharray="3 3" label={{ value: "%100", position: "insideTopRight", fill: t.axis, fontSize: 9 }} />
            <Tooltip {...tooltipStyles(t)} cursor={crosshairCursor(t)} labelFormatter={tooltipDate} formatter={(value, name) => [`${fmt.raw(Number(value), 1)}%`, name]} />
            <Line type="monotone" dataKey="private" name="Özel" stroke={t.hero} strokeWidth={2.1} dot={false} activeDot={{ r: 3 }} />
            <Line type="monotone" dataKey="public" name="Kamu" stroke={t.contextActive} strokeWidth={1.6} dot={false} activeDot={{ r: 3 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 flex gap-5 font-mono text-[8.5px] uppercase tracking-[0.04em] text-faint">
        <span><i className="mr-1.5 inline-block h-0.5 w-5 align-middle bg-data" />Özel</span>
        <span><i className="mr-1.5 inline-block h-0.5 w-5 align-middle bg-muted-foreground" />Kamu</span>
      </div>
    </div>
  );
}

function RegulatoryBuffers({ data }: { data: LiquidityPrototypeData }) {
  const max = Math.max(180, ...data.regulatory.map((row) => row.value ?? 0));
  return (
    <div className="w-full max-w-[52rem] border-t-2 border-foreground">
      {data.regulatory.map((row) => {
        const width = row.value == null ? 0 : Math.min(100, (row.value / max) * 100);
        const floor = (row.floor / max) * 100;
        return (
          <div key={row.short} className="grid gap-3 border-b border-hair py-4 sm:grid-cols-[56px_minmax(0,1fr)_72px] sm:items-center">
            <span className="font-mono text-[10px] font-semibold text-warning">{row.short}</span>
            <div>
              <div className="text-[11.5px] text-muted-foreground">{row.label}</div>
              <div className="relative mt-2 h-1.5 bg-hair">
                <div className="h-full bg-data" style={{ width: `${width}%` }} />
                <span className="absolute -top-1.5 h-4 w-px bg-warning" style={{ left: `${floor}%` }} />
              </div>
              <div className="mt-1 font-mono text-[7.5px] uppercase tracking-[0.04em] text-faint">Asgari eşik %100</div>
            </div>
            <span className="text-right font-mono text-[18px] font-semibold text-foreground">{row.value == null ? "—" : `${metricValue(row.value, 0)}%`}</span>
          </div>
        );
      })}
    </div>
  );
}

function CreditCanvas({ data }: { data: CreditPrototypeData }) {
  return (
    <>
      <LayerHead index="01" title="Mevcut durum" description="Önce aynı kredi stokunun nominal, sabit kur ve reel karşılığını ayırır." className="mt-8" />
      <OpeningRead data={data} />
      <MetricBand data={data} />
      <CadenceBand
        title="Reel hacim köprüsü"
        observation={{ cadence: "monthly", role: "structure", asOf: data.commonCutoff, basis: "haftalık kredi + yayımlanmış son TÜFE" }}
      >
        <BridgePanel data={data} />
      </CadenceBand>

      <LayerHead index="02" title="Büyümenin bileşenleri" description="Zaman içindeki seyir ile sektör büyümesine mutabık katkıları yan yana okur." className="mt-10" />
      <CadenceBand
        title="Haftalık kredi görünümü"
        observation={{ cadence: "weekly", role: "current", asOf: data.asOf, window: "52 hafta", basis: "BDDK sektör kredileri" }}
      >
        <div className="grid gap-8 lg:grid-cols-[minmax(0,7fr)_minmax(260px,4fr)]">
          <CreditTrend data={data} />
          <ContributionPanel data={data} />
        </div>
      </CadenceBand>

      <LayerHead index="03" title="Sahiplik grupları" description="Güncel büyümeyi aynı ölçek üzerinde 13 hafta önceki konumla karşılaştırır." className="mt-10" />
      <div className="mt-6">
        <GroupComparison groups={data.groups} title="Sahiplik gruplarına göre kredi büyümesi" meta="52 hafta · güncel ve 13 hafta önce" />
      </div>
    </>
  );
}

function LiquidityCanvas({ data }: { data: LiquidityPrototypeData }) {
  return (
    <>
      <LayerHead index="01" title="Günlük sistem pozisyonu" description="TCMB bilançosundaki net fonlama ile sistemin o günkü lira açığını veya fazlasını gösterir." className="mt-8" />
      <OpeningRead data={data} />
      <MetricBand data={data} />
      <CadenceBand
        title="Günlük sistem likiditesi"
        observation={{ cadence: "daily", role: "current", asOf: data.asOf, window: "son 400 gözlem", basis: "TCMB net fonlama" }}
      >
        <FundingChart data={data} />
      </CadenceBand>

      <LayerHead index="02" title="Haftalık fonlama yapısı" description="Kamu ve özel mevduat bankalarını aynı TL kredi/mevduat tanımıyla karşılaştırır." className="mt-10" />
      <CadenceBand
        title="Kamu ve özel mevduat bankaları"
        observation={{ cadence: "weekly", role: "structure", asOf: data.weeklyAsOf, window: "104 hafta", basis: "BDDK TL stokları" }}
      >
        <div className="grid gap-8 lg:grid-cols-[minmax(0,7fr)_minmax(250px,4fr)]">
          <LdrChart data={data} />
          <div>
            <SecHead title="Güncel karşılaştırma" meta="aynı hafta · aynı tanım" className="mb-2.5" />
            <Compare
              a="Kamu"
              b="Özel"
              rows={[
                {
                  label: "TL kredi / mevduat",
                  note: "BDDK haftalık stoklarından hesaplanır",
                  a: data.publicLdr,
                  b: data.privateLdr,
                  fmt: (value) => `${metricValue(value)}%`,
                },
              ]}
            />
            <div className="mt-7">
              <GroupComparison groups={data.ownershipGrowth} title="TL mevduat büyümesi" meta="13 haftalık yıllıklandırılmış" />
            </div>
          </div>
        </div>
      </CadenceBand>

      <LayerHead index="03" title="Düzenleyici tamponlar" description="Günlük sistem bakiyesinden ayrı olarak, denetimli çeyreklik oranları asgari eşikleriyle okur." className="mt-10" />
      <CadenceBand
        title="Likidite tamponları"
        observation={{ cadence: "quarterly", role: "audited", asOf: data.quarterlyAsOf, basis: "aktif ağırlıklı LCR ve NSFR" }}
      >
        <RegulatoryBuffers data={data} />
      </CadenceBand>
    </>
  );
}

export default function SectorPrototype({ data }: { data: PrototypeData }) {
  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <PrototypeHeader data={data} />
      {data.kind === "credit" ? <CreditCanvas data={data} /> : <LiquidityCanvas data={data} />}
      <Colophon>{data.sourceNote} · Yerel prototip; yayımlanmadı.</Colophon>
    </main>
  );
}
