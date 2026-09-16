"use client";

import { useState, type ReactNode } from "react";
import { Colophon } from "@/app/components/desk";
import { createFormatters } from "@/app/lib/chart-format";
import { useChartTheme } from "@/app/lib/chart-theme";
import { useText } from "@/i18n/use-text";
import type { DesignData, PlotRow } from "./data";
import styles from "./design.module.css";

const fmt = createFormatters("tr");
const number = (v: number | null | undefined, d = 1) => v == null ? "—" : fmt.raw(v, d);
const pct = (v: number | null | undefined) => v == null ? "—" : fmt.pct(v, 1);
const signed = (v: number | null | undefined) => v == null ? "—" : `${v > 0 ? "+" : ""}${number(v)}`;
function date(p: string | null | undefined) {
  if (!p) return "Veri yok";
  if (/^\d{4}Q\d$/.test(p)) return `${p.slice(0, 4)} · ${p.at(-1)}. çeyrek`;
  return new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(`${p.slice(0, 10)}T00:00:00Z`));
}

type Series = { key: string; label: string; dash?: boolean };

function Plot({ rows, series, unit = "%", title, baseline = 0 }: { rows: PlotRow[]; series: Series[]; unit?: string; title: string; baseline?: number }) {
  const theme = useChartTheme();
  const [range, setRange] = useState(104);
  const [selected, setSelected] = useState<string | null>(null);
  const latest = rows.at(-1)?.period;
  const cutoff = latest ? new Date(new Date(`${latest}T00:00:00Z`).valueOf() - range * 7 * 86400000).toISOString().slice(0, 10) : "";
  const data = rows.filter((r) => r.period >= cutoff);
  const index = selected == null ? data.length - 1 : Math.max(0, data.findIndex((r) => r.period === selected));
  const active = data[index];
  const colors = [theme.hero, theme.contextActive, theme.palette[1]];
  const values = data.flatMap((r) => series.flatMap((s) => typeof r[s.key] === "number" ? [r[s.key] as number] : []));
  const low = Math.min(baseline, ...values), high = Math.max(baseline, ...values);
  const step = Math.pow(10, Math.floor(Math.log10((high - low || 1) / 4)));
  const increment = Math.ceil((high - low || 1) / 4 / step) * step;
  const min = Math.floor(low / increment) * increment, max = Math.ceil(high / increment) * increment || increment;
  const time = (p: string) => new Date(`${p}T00:00:00Z`).valueOf();
  const startTime = data[0] ? time(data[0].period) : 0;
  const duration = latest ? time(latest) - startTime : 1;
  const x = (i: number) => 48 + (data[i] ? time(data[i].period) - startTime : 0) / (duration || 1) * 646;
  const y = (v: number) => 22 + (max - v) / (max - min) * 246;
  const ticks = Array.from({ length: Math.round((max - min) / increment) + 1 }, (_, i) => min + i * increment);
  const show = (v: unknown) => typeof v === "number" ? `${number(v)}${unit === "%" ? "%" : ""}` : "—";
  return <div className={styles.plot}>
    <div className={styles.chartToolbar}>
      <span className={styles.meta}>{unit === "%" ? "Yüzde" : unit} · {date(data[0]?.period)} — {date(latest)}</span>
      <div className={styles.switches} aria-label={`${title}: tarih aralığı`}>
        {[52, 104, 156].map((r) => <button key={r} aria-pressed={range === r} onClick={() => { setRange(r); setSelected(null); }}>{r / 52}Y</button>)}
      </div>
    </div>
    {values.length === 0 ? <p className={styles.empty}>Bu tarih aralığında yayımlanmış gözlem bulunamadı.</p> : <>
      <div className={styles.chartAndRail}>
        <svg viewBox="0 0 720 308" role="img" aria-label={`${title}. Değerleri incelemek için aşağıdaki tarih kaydırıcısını kullanın.`}
          onPointerMove={(e) => { const rect = e.currentTarget.getBoundingClientRect(); const pos = (e.clientX - rect.left) / rect.width * 720; const nearest = data.reduce((best, _, i) => Math.abs(x(i) - pos) < Math.abs(x(best) - pos) ? i : best, 0); setSelected(data[nearest]?.period ?? null); }}
          onPointerLeave={() => setSelected(null)}>
          {ticks.map((v) => <g key={v}><line x1="48" x2="694" y1={y(v)} y2={y(v)} stroke={v === baseline ? theme.reference : theme.grid} strokeDasharray={v === baseline ? "4 4" : undefined} /><text x="39" y={y(v) + 4} textAnchor="end" fill={theme.axis}>{number(v, 0)}</text></g>)}
          {series.map((s, i) => {
            let pen = false;
            const path = data.map((r, j) => { const v = r[s.key]; if (typeof v !== "number") { pen = false; return ""; } const command = pen ? "L" : "M"; pen = true; return `${command}${x(j)},${y(v)}`; }).join(" ");
            return <path key={s.key} d={path} fill="none" stroke={colors[i]} strokeWidth={i === 0 ? 2.6 : 1.8} strokeDasharray={s.dash ? "5 4" : undefined} />;
          })}
          {selected && active && <line x1={x(index)} x2={x(index)} y1="16" y2="270" stroke={theme.crosshair} />}
          {selected && active && series.map((s, i) => typeof active[s.key] === "number" && <circle key={s.key} cx={x(index)} cy={y(active[s.key] as number)} r="3.5" fill={colors[i]} stroke={theme.tooltipBg} strokeWidth="2" />)}
          {[0, Math.floor((data.length - 1) / 2), data.length - 1].map((i, j) => <text key={j} x={x(i)} y="298" textAnchor={j === 0 ? "start" : j === 2 ? "end" : "middle"} fill={theme.axis}>{date(data[i]?.period)}</text>)}
        </svg>
        <div className={styles.readout}>
          <p className={styles.meta}>{selected ? date(active?.period) : "Son gözlemler"}</p>
          {series.map((s, i) => { const point = selected ? active : data.findLast((r) => typeof r[s.key] === "number"); return <div key={s.key} className={styles.readoutItem}>
            <span><i style={{ borderColor: colors[i], borderTopStyle: s.dash ? "dashed" : "solid" }} />{s.label}</span>
            <strong>{show(point?.[s.key])}</strong>
            <small>{point && typeof point[s.key] === "number" ? date(point.period) : "Bu tarihte veri yok"}</small>
          </div>; })}
        </div>
      </div>
      <label className={styles.scrubber}><span>Tarihi incele</span><input type="range" aria-label={`${title}: gözlem tarihi`} min={0} max={Math.max(0, data.length - 1)} value={Math.max(0, index)} aria-valuetext={date(active?.period)} onChange={(e) => setSelected(data[Number(e.target.value)]?.period ?? null)} /><span>{date(active?.period)}</span></label>
    </>}
  </div>;
}

function Section({ id, index, title, meta, children }: { id: string; index: string; title: string; meta: string; children: ReactNode }) {
  return <section id={id} className={styles.section}><div className={styles.sectionHead}><span className={styles.sectionNumber}>{index}</span><div><h2>{title}</h2><p className={styles.meta}>{meta}</p></div></div>{children}</section>;
}

function Waterfall({ data }: { data: DesignData["credit"] }) {
  const b = data.bridge;
  if (b.nominalAtReal == null || b.fxAdj == null || b.realFxAdj == null || b.currencyPp == null || b.inflationPp == null) return <p>Ortak tarihte nominal, kur ve TÜFE verisi gerekli.</p>;
  const steps = [
    { label: "Nominal", from: 0, to: b.nominalAtReal, value: b.nominalAtReal, delta: false },
    { label: "Kur etkisi", from: b.nominalAtReal, to: b.fxAdj, value: -b.currencyPp, delta: true },
    { label: "Sabit kur", from: 0, to: b.fxAdj, value: b.fxAdj, delta: false },
    { label: "Fiyat etkisi", from: b.fxAdj, to: b.realFxAdj, value: -b.inflationPp, delta: true },
    { label: "Reel, sabit kur", from: 0, to: b.realFxAdj, value: b.realFxAdj, delta: false },
  ];
  const max = Math.max(0, ...steps.flatMap((s) => [s.from, s.to]));
  const min = Math.min(0, ...steps.flatMap((s) => [s.from, s.to]));
  const y = (v: number) => 36 + (max - v) / (max - min || 1) * 110;
  return <><svg className={styles.waterfall} viewBox="0 0 670 208" role="img" aria-label={`Nominal ${pct(b.nominalAtReal)}, sabit kur ${pct(b.fxAdj)}, reel ve sabit kur ${pct(b.realFxAdj)}.`}>
    <line x1="10" x2="660" y1={y(0)} y2={y(0)} className="stroke-faint" strokeDasharray="3 3" />
    {steps.map((s, i) => <g key={s.label}><rect x={i * 134 + 28} y={Math.min(y(s.from), y(s.to))} width="78" height={Math.abs(y(s.from) - y(s.to))} className={s.delta ? s.value < 0 ? "fill-negative" : "fill-positive" : i === 4 ? "fill-data" : "fill-context"} />
      <text x={i * 134 + 67} y={Math.min(y(s.from), y(s.to)) - 12} textAnchor="middle" className="fill-foreground">{s.delta ? `${signed(s.value)} yp` : pct(s.value)}</text>
      <text x={i * 134 + 67} y="190" textAnchor="middle" className="fill-muted-foreground">{s.label}</text></g>)}
  </svg><p className={styles.note}>Aynı hafta, aynı portföy. YP krediler baz haftanın USD/TRY kuruyla değerlenir; YP portföyünün tamamı USD kabul edilir. Reel büyüme: (1 + sabit kur büyümesi) / (1 + TÜFE) − 1.</p></>;
}

function CreditSections({ data, includeTrend = true }: { data: DesignData["credit"]; includeTrend?: boolean }) {
  const tx = useText();
  const a = data.attribution;
  const reconciled = a.totalPp != null && a.items.length === 5 && Math.abs(a.sumPp - a.totalPp) < 0.1;
  const magnitude = Math.max(1, ...a.items.map((r) => Math.abs(r.pp)));
  return <>
    {includeTrend && <Section id="trend" index="01" title="Büyümenin üç görünümü" meta="HAFTALIK · SEKTÖR · 52 HAFTALIK DEĞİŞİM">
      <Plot title="Kredi büyümesi" rows={data.trend} series={[{ key: "real", label: "Reel, sabit kur" }, { key: "nominal", label: "Nominal", dash: true }, { key: "adjusted", label: "Sabit kur" }]} />
      <p className={styles.note}>Kaynak: BDDK · TCMB USD/TRY · TÜİK TÜFE. Reel seri {date(data.bridge.asOfReal)} tarihinde biter; sonraki haftalar için TÜFE tahmini kullanılmaz.</p>
    </Section>}
    <Section id="drivers" index="02" title="Nominalden reel büyümeye" meta={`ORTAK VERİ KESİMİ · ${date(data.bridge.asOfReal)}`}><Waterfall data={data} /></Section>
    <Section id="structure" index="03" title="Kredi büyümesinin kaynağı" meta={`HAFTALIK · ${date(a.at)} · SEKTÖR BÜYÜMESİNE KATKI`}>
      {reconciled ? <><div className={styles.contributionHeader}><span>Segment</span><span>Katkı · yüzde puan</span><span>Yıllık büyüme</span></div>
        {a.items.map((r) => <div key={r.key} className={styles.contribution}><span>{r.label}</span><div className={styles.signedBar}><i className={styles.zero} /><i className={r.pp < 0 ? styles.negative : styles.positive} style={{ left: `${r.pp < 0 ? 50 - Math.abs(r.pp) / magnitude * 43 : 50}%`, width: `${Math.abs(r.pp) / magnitude * 43}%` }} /><strong>{signed(r.pp)}</strong></div><span className={styles.mono}>{pct(r.growth)}</span></div>)}
        <div className={styles.total}><span>Toplam katkı</span><strong>{signed(a.sumPp)} yp</strong></div></> : <p className={styles.empty}>Segment katkıları sektör toplamıyla uzlaşmıyor veya veri eksik; katkı grafiği gösterilmedi.</p>}
      <p className={styles.note}>KOBİ, ticari kredilerin içindedir; toplama ikinci kez eklenmez. Katkı = segmentteki değişim / bir yıl önceki toplam kredi stoku.</p>
      <h3 className={styles.subheading}>Sahiplik grupları</h3><div className={styles.tableWrap}><table><thead><tr><th>Grup</th><th>Gözlem</th><th>52 haftalık büyüme</th></tr></thead><tbody>{data.groups.map((g) => <tr key={g.code}><th scope="row">{tx(g.label)}</th><td>{date(g.rows.at(-1)?.period)}</td><td>{pct(g.rows.at(-1)?.value)}</td></tr>)}</tbody></table></div>
    </Section>
  </>;
}

function LiquiditySections({ data, includeTrend = true }: { data: DesignData["liquidity"]; includeTrend?: boolean }) {
  return <>
    {includeTrend && <Section id="trend" index="01" title="Sistemin günlük lira pozisyonu" meta="GÜNLÜK · TCMB · NET FONLAMA BAKİYESİ">
      <Plot rows={data.funding} series={[{ key: "value", label: "Net TCMB fonlaması" }]} unit="Milyar TL" title="Sistem likiditesi" />
      <p className={styles.note}>Kaynak: TCMB EVDS · TP.APIFON3. Bu seride sıfırın altı sistem açığını, üstü fazlayı gösterir. Gözlemler arasında tahmin yapılmaz.</p>
    </Section>}
    <Section id="drivers" index="02" title="Kamu ve özel bankaların fonlama yapısı" meta={`HAFTALIK · ${date(data.ldr.at(-1)?.period)} · TL KREDİ / MEVDUAT`}>
      <Plot rows={data.ldr} series={[{ key: "PRIVATE", label: "Özel + yabancı" }, { key: "PUBLIC", label: "Kamu", dash: true }]} title="TL kredi / mevduat" baseline={100} />
      <p className={styles.note}>BDDK haftalık TL stoklarından hesaplanır. Özel grup yerli özel ve yabancı mevduat bankalarını kapsar. Aylık yayımlanan TL+YP kredi/mevduat oranından farklıdır.</p>
    </Section>
    <Section id="structure" index="03" title="Denetimli likidite tamponları" meta="ÇEYREKLİK · AKTİF AĞIRLIKLI · RAPORLAYAN MEVDUAT VE KATILIM BANKALARI">
      <div className={styles.regulatory}>{data.regulatory.map(({ code, row }) => <div key={code}><span className={styles.meta}>{code === "LCR" ? "Likidite karşılama oranı" : "Net istikrarlı fonlama oranı"}</span><strong>{pct(row?.value)}</strong><span className={styles.meta}>{date(row?.period)} · {code}</span></div>)}</div>
      <p className={styles.note}>Kaynak: BRSA denetimli solo finansallar. Her oran kendi raporlayan banka kümesinde aktif ağırlıklıdır; günlük sistem bakiyesiyle aynı gözlem veya kapsam değildir.</p>
    </Section>
  </>;
}

export default function SectorDesign({ data }: { data: DesignData }) {
  const [page, setPage] = useState<"credit" | "liquidity">("credit");
  const [direction, setDirection] = useState<"focus" | "briefing" | "atlas">("focus");
  const credit = page === "credit";
  const b = data.credit.bridge;
  const funding = data.liquidity.funding.at(-1);
  const previous = data.liquidity.funding.at(-2);
  const change = funding != null && previous != null ? funding.value - previous.value : null;
  const headline = credit
    ? b.realFxAdj == null ? "Kredi büyümesinin nominal ve reel görünümü" : b.realFxAdj < 0 ? "Kur ve fiyat etkileri sonrası kredi hacmi daralıyor." : b.realFxAdj > 0 ? "Kredi hacmi reel ve sabit kurla büyüyor." : "Kredi hacmi reel ve sabit kurla değişmedi."
    : funding == null ? "Sistemin günlük likidite pozisyonu" : funding.value < 0 ? "Bankacılık sistemi lirada açık veriyor." : funding.value > 0 ? "Bankacılık sistemi lirada fazla veriyor." : "Sistemin net lira bakiyesi sıfırda.";
  const sections = credit ? ["Büyümenin seyri", "Kur ve fiyat etkisi", "Segmentler ve gruplar"] : ["Sistem likiditesi", "Fonlama yapısı", "Likidite tamponları"];
  const stats = credit ? [
    { label: "Reel, sabit kur", value: number(b.realFxAdj), unit: "%", note: "52 haftalık kredi büyümesi" },
    { label: "Nominal", value: number(b.nominalAtReal), unit: "%", note: "Aynı haftanın açıklanan büyümesi" },
    { label: "Sabit kur", value: number(b.fxAdj), unit: "%", note: "Kur değerleme etkisi arındırılmış" },
  ] : [
    { label: "Net TCMB fonlaması", value: number(funding?.value, 0), unit: "mr TL", note: "Günlük sistem bakiyesi" },
    { label: "Önceki gözleme göre", value: signed(change), unit: "mr TL", note: previous ? `${date(previous.period)} tarihine göre` : "Önceki gözlem yok" },
    { label: "Önceki gözlem", value: number(previous?.value, 0), unit: "mr TL", note: date(previous?.period) },
  ];
  if (direction === "focus") return <main className={`${styles.study} ${styles.focus}`} lang="tr">
    <div className={styles.focusMasthead}><div><span className={styles.meta}>SEKTÖR ARAŞTIRMASI</span><h1>{credit ? "Krediler" : "Likidite"}</h1></div><div className={styles.switches} aria-label="Örnek sektör sayfası"><button aria-pressed={credit} onClick={() => setPage("credit")}>Krediler</button><button aria-pressed={!credit} onClick={() => setPage("liquidity")}>Likidite</button></div></div>
    <nav className={styles.focusNav} aria-label="Bu sayfada"><a href="#trend">Görünüm</a><a href="#drivers">{credit ? "Kur ve fiyat etkisi" : "Fonlama yapısı"}</a><a href="#structure">{credit ? "Segmentler ve gruplar" : "Likidite tamponları"}</a><a href="#sources">Kaynaklar</a></nav>
    <section id="trend" className={styles.focusHero}>
      <div className={styles.focusThesis}><p className={styles.meta}>01 / {credit ? "BÜYÜMENİN NİTELİĞİ" : "SİSTEM POZİSYONU"}</p><h2>{credit ? "Kredi büyümesinin ne kadarı gerçek?" : "Sistemin lira ihtiyacı ne durumda?"}</h2><div className={styles.focusNumber}>{credit ? number(b.realFxAdj) : number(funding?.value, 0)}<span>{credit ? "%" : "mr TL"}</span></div><p className={styles.focusMetric}>{credit ? "Reel, sabit kurla yıllık büyüme" : "Net TCMB fonlama bakiyesi"}</p><p className={styles.meta}>{date(credit ? b.asOfReal : funding?.period)}</p><p className={styles.focusFinding}>{headline}</p><div className={styles.focusComparisons}>{stats.slice(1).map((s) => <div key={s.label}><span>{s.label}</span><strong>{s.value}<small>{s.unit}</small></strong><p>{credit ? "Aynı veri kesimi" : s.note}</p></div>)}</div></div>
      <div className={styles.focusChart} key={page}><div className={styles.focusChartHeading}><h3>{credit ? "Aynı portföy. Üç farklı ölçüm." : "Günlük likidite dengesi"}</h3><p>{credit ? "Nominal, sabit kur ve reel kredi büyümesi · 52 hafta" : "Sıfırın altı sistem açığı · sıfırın üstü fazla"}</p></div>{credit ? <Plot rows={data.credit.trend} series={[{key:"real",label:"Reel, sabit kur"},{key:"nominal",label:"Nominal",dash:true},{key:"adjusted",label:"Sabit kur"}]} title="Kredi büyümesi" /> : <Plot rows={data.liquidity.funding} series={[{key:"value",label:"Net TCMB fonlaması"}]} unit="Milyar TL" title="Sistem likiditesi" />}<p className={styles.note}>{credit ? `BDDK · TCMB · TÜİK. Reel ve sabit kur serilerinin son ortak gözlemi ${date(b.asOfReal)}; son nominal gözlem ${date(b.asOfNominal)}. Her serinin tarihi değerin yanında.` : "TCMB EVDS · TP.APIFON3 · günlük gözlemler. Haftalık kredi/mevduat ve çeyreklik tamponlar ayrı bölümlerde."}</p></div>
    </section>
    <div className={styles.focusEvidence} key={`evidence-${page}`}>{credit ? <CreditSections data={data.credit} includeTrend={false} /> : <LiquiditySections data={data.liquidity} includeTrend={false} />}</div>
    <section id="sources" className={styles.focusSources}><h2>Kaynağa kadar izlenebilir.</h2><p>{credit ? "Kur etkisi için YP portföyü baz haftanın USD/TRY kuruyla değerlenir ve tamamı USD kabul edilir. Reel hesap yayımlanmış TÜFE ile sınırlıdır; son haftalara tahmin eklenmez." : "Sistem bakiyesi günlük, TL kredi/mevduat haftalık, denetimli likidite oranları çeyrekliktir. Her veri kümesi kendi tarihi ve raporlayan banka kapsamıyla okunmalıdır."}</p><a href={credit ? "/credit" : "/liquidity"}>Mevcut sayfanın tüm veri ve grafikleri <span aria-hidden="true">↗</span></a><span className={styles.meta}>YEREL GERÇEK VERİ KOPYASI · ÜRETİM VERİSİ GÜNCELLİĞİ İDDİASI TAŞIMAZ</span></section>
    <div className={styles.studioBar}><span className={styles.meta}>YENİ ÇALIŞMA · FOCUS</span><div className={styles.switches} aria-label="Önceki tasarım çalışmaları"><button onClick={() => setDirection("briefing")}>Önceki · Briefing</button><button onClick={() => setDirection("atlas")}>Önceki · Atlas</button></div></div><Colophon>Yerel tasarım çalışması · 13 Eylül 2026</Colophon>
  </main>;
  return <main className={`${styles.study} ${direction === "atlas" ? styles.atlas : ""}`} lang="tr">
    <div className={styles.studioBar}><span className={styles.meta}>TASARIM ÇALIŞMASI · YEREL VERİ KOPYASI</span><div className={styles.switches} aria-label="Tasarım yönü"><button onClick={() => setDirection("focus")}>Yeni · Focus</button><button aria-pressed={direction === "briefing"} onClick={() => setDirection("briefing")}>A · Briefing</button><button aria-pressed={direction === "atlas"} onClick={() => setDirection("atlas")}>B · Atlas</button></div></div>
    <header className={styles.header}><div><p className={styles.meta}>TÜRKİYE BANKACILIK SEKTÖRÜ / {credit ? "02" : "04"}</p><h1>{credit ? "Krediler" : "Likidite"}<span>.</span></h1><p>{credit ? "Büyüme, bileşim ve kredi döngüsü" : "Sistem pozisyonu, fonlama ve tamponlar"}</p></div><div className={styles.switches} aria-label="Örnek sektör sayfası"><button aria-pressed={credit} onClick={() => setPage("credit")}>Krediler</button><button aria-pressed={!credit} onClick={() => setPage("liquidity")}>Likidite</button></div></header>
    <div className={styles.read}><p className={styles.meta}>GÜNCEL OKUMA · {date(credit ? b.asOfReal : funding?.period)}</p><h2>{headline}</h2></div>
    <div className={styles.vitals}>{stats.map((s) => <div key={s.label}><span>{s.label}</span><strong>{s.value}<small>{s.unit}</small></strong><p>{s.note}</p></div>)}</div>
    <p className={styles.observation}>{credit ? `Karşılaştırma ${date(b.asOfReal)} ortak veri kesiminde. Son nominal gözlem: ${date(b.asOfNominal)} · ${pct(b.nominal)}.` : `Günlük gözlem: ${date(funding?.period)}. Haftalık fonlama ve çeyreklik oranlar kendi tarihleriyle aşağıda.`}</p>
    <div className={styles.body}><nav className={styles.contents} aria-label="Bu sayfada"><span className={styles.meta}>BU SAYFADA</span>{sections.map((s, i) => <a key={s} href={`#${["trend", "drivers", "structure"][i]}`}><span>0{i + 1}</span>{s}<span aria-hidden="true">↗</span></a>)}<a href="#sources"><span>04</span>Kaynak ve yöntem<span aria-hidden="true">↗</span></a></nav><div className={styles.sections} key={page}>{credit ? <CreditSections data={data.credit} /> : <LiquiditySections data={data.liquidity} />}
      <Section id="sources" index="04" title="Kaynak ve yöntem" meta="GÖZLEMLERDEN HESAPLANIR · TAHMİN İÇERMEZ"><div className={styles.sourceGrid}><p>{credit ? "BDDK haftalık bülteni kredi stoklarını ve sahiplik gruplarını sağlar. Yıllık büyüme 52 haftalık karşılaştırmadır; reel seri yalnızca yayımlanmış TÜFE aylarına kadar hesaplanır." : "TCMB sistem bakiyesi günlük; BDDK TL kredi ve mevduat stokları haftalık; denetimli LCR ve NSFR çeyrekliktir. Bu üç sıklık birbirinin yerine kullanılmaz."}</p><p>Bu tasarım çalışması yerel veritabanındaki gerçek gözlemleri kullanır; güncel üretim verisi iddiası taşımaz. Eksik gözlemler “—” olarak gösterilir.</p></div><a className={styles.fullEvidence} href={credit ? "/credit" : "/liquidity"}>Mevcut sayfadaki tüm kanıtları aç <span aria-hidden="true">↗</span></a></Section>
    </div></div><Colophon>Yerel tasarım çalışması · Briefing / Atlas · 13 Eylül 2026</Colophon>
  </main>;
}
