"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowUpRight, Download, Search } from "lucide-react";
import { useText } from "@/i18n/use-text";
import { SECTOR_PAGES, type SectorKey } from "../../lib/sector-pages";
import type { SignalSnapshot } from "../../lib/sector-signals";
import type { SectorSignal, SignalState } from "../../lib/sector-signals/types";
import { filterSignals, formatSignalFact, localText, type SignalFilters } from "./model";
import styles from "./signals.module.css";

const copy = {
  tr: {
    title: "Sinyaller", description: "Bankacılık verilerinde araştırmaya değer koşullar ve ayrışmalar.",
    active: "Tetiklenen", clear: "Tetiklenmeyen", unavailable: "Veri eksik", all: "Tümü",
    topic: "Konu", topics: "Tüm konular", search: "Sinyallerde ara", export: "Görünümü indir",
    observation: "Gözlem", criteria: "Koşul ve kaynak", criterion: "Sinyal koşulu", source: "Veri kaynağı ve kapsam",
    chart: "İlgili analiz", noDate: "Dönem bilinmiyor", count: "sinyal", empty: "Bu seçimle eşleşen sinyal yok.",
    reset: "Filtreleri temizle", unavailableNote: "Gerekli veriler tamamlanmadan bu koşul değerlendirilemiyor.",
    partial: "Verileri yüklenemeyen konular", note: "Sinyaller araştırma başlangıcıdır. Yazılarda kullanılacak değerlendirmeler, kaynaklar ve karşı bulgular incelendikten sonra oluşturulur.",
    daily: "Günlük", weekly: "Haftalık", monthly: "Aylık", quarterly: "Çeyreklik", mixed: "Farklı dönemler",
    dataTime: "Veri kontrolü", facts: "Dayanak veriler", formula: "Hesaplama kuralı", date: "Dönem",
  },
  en: {
    title: "Signals", description: "Conditions and divergences in banking data worth investigating.",
    active: "Triggered", clear: "Not triggered", unavailable: "Data missing", all: "All",
    topic: "Topic", topics: "All topics", search: "Search signals", export: "Download view",
    observation: "Observation", criteria: "Condition and source", criterion: "Signal condition", source: "Data source and coverage",
    chart: "Related analysis", noDate: "Period unavailable", count: "signals", empty: "No signals match this selection.",
    reset: "Clear filters", unavailableNote: "This condition cannot be evaluated until the required data is available.",
    partial: "Topics whose data could not be loaded", note: "Signals are starting points for research. Assessments used in articles follow a review of sources and counterevidence.",
    daily: "Daily", weekly: "Weekly", monthly: "Monthly", quarterly: "Quarterly", mixed: "Mixed periods",
    dataTime: "Data checked", facts: "Supporting data", formula: "Calculation rule", date: "Period",
  },
};

function SignalCard({ signal, locale }: { signal: SectorSignal; locale: string }) {
  const tx = useText();
  const c = copy[locale === "tr" ? "tr" : "en"];
  const text = (value: SectorSignal["title"]) => localText(value, locale);
  return <article id={signal.id} className={styles.signal} data-state={signal.state}>
    <div className={styles.signalMeta}>
      <span className={styles.status} data-state={signal.state}>{c[signal.state]}</span>
      <span>{tx(SECTOR_PAGES[signal.sector].title)}</span>
      <span>{c[signal.cadence]}{signal.asOf ? ` · ${tx(signal.asOf)}` : ` · ${c.noDate}`}</span>
    </div>
    <div className={styles.signalBody}>
      <h2>{text(signal.title)}</h2>
      <p>{text(signal.summary)}</p>
      {signal.facts.length > 0 && <dl className={styles.facts} aria-label={c.facts}>
        {signal.facts.slice(0, 4).map(fact => <div key={fact.key}>
          <dt>{text(fact.label)}</dt><dd>{formatSignalFact(fact, locale)}</dd>
          {fact.asOf && fact.asOf !== signal.asOf && <dd className={styles.factDate}>{tx(fact.asOf)}</dd>}
        </div>)}
      </dl>}
      <div className={styles.signalFooter}>
        <details>
          <summary>{c.criteria}</summary>
          <div className={styles.detail}>
            <h3>{c.criterion}</h3><p>{text(signal.criterion)}</p>
            <h3>{c.source}</h3><p>{text(signal.source)}</p>
            {signal.facts.length > 4 && <dl className={styles.extraFacts}>{signal.facts.slice(4).map(fact => <div key={fact.key}>
              <dt>{text(fact.label)}{fact.asOf && <small>{tx(fact.asOf)}</small>}</dt><dd>{formatSignalFact(fact, locale)}</dd>
            </div>)}</dl>}
            <h3>{c.formula}</h3><code>{signal.rule}</code>
          </div>
        </details>
        <Link href={signal.href}>{c.chart}<ArrowUpRight size={15} aria-hidden="true" /></Link>
      </div>
    </div>
  </article>;
}

export default function SignalsView({ snapshot, locale }: { snapshot: SignalSnapshot; locale: string }) {
  const tx = useText();
  const c = copy[locale === "tr" ? "tr" : "en"];
  const [filters, setFilters] = useState<SignalFilters>({ sector: "all", state: "active", query: "" });
  const filtered = filterSignals(snapshot.signals, filters, locale);
  const topics = (Object.keys(SECTOR_PAGES) as SectorKey[]).filter(sector => snapshot.signals.some(signal => signal.sector === sector) || snapshot.failedSectors.includes(sector));
  const withinTopic = filterSignals(snapshot.signals, { ...filters, state: "all" }, locale);
  const counts = (state: SignalState | "all") => state === "all" ? withinTopic.length : withinTopic.filter(signal => signal.state === state).length;
  function download() {
    const exportData = { ...snapshot, filters, signals: filtered };
    const url = URL.createObjectURL(new Blob([JSON.stringify(exportData, null, 2)], { type: "application/json;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `carthago-signals-${snapshot.evaluatedAt.slice(0, 10)}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <main className={styles.page} data-signals-page lang={locale}>
    <Link className={styles.back} href="/admin">{locale === "tr" ? "← Yönetim" : "← Control center"}</Link>
    <header className={styles.header}>
      <div><h1>{c.title}</h1><p>{c.description}</p></div>
      <button className={styles.download} onClick={download} disabled={!filtered.length}><Download size={16} aria-hidden="true" />{c.export}</button>
    </header>
    <div className={styles.filters}>
      <label>{c.topic}<select value={filters.sector} onChange={event => { const sector = event.target.value as SignalFilters["sector"]; setFilters(previous => ({ ...previous, sector })); }}>
        <option value="all">{c.topics}</option>{topics.map(key => <option key={key} value={key}>{tx(SECTOR_PAGES[key].title)}</option>)}
      </select></label>
      <label className={styles.search}><span className="sr-only">{c.search}</span><Search size={17} aria-hidden="true" /><input type="search" placeholder={c.search} value={filters.query} onChange={event => { const query = event.target.value; setFilters(previous => ({ ...previous, query })); }} /></label>
    </div>
    <div className={styles.tabs} aria-label={locale === "tr" ? "Sinyal durumu" : "Signal state"}>
      {(["active", "clear", "unavailable", "all"] as const).map(state => <button key={state} aria-pressed={filters.state === state} onClick={() => setFilters(previous => ({ ...previous, state }))}>{c[state]}<span>{counts(state)}</span></button>)}
    </div>
    {snapshot.failedSectors.length > 0 && <p className={styles.error} role="status">{c.partial}: {snapshot.failedSectors.map(key => tx(SECTOR_PAGES[key].title)).join(", ")}</p>}
    <div className={styles.resultBar}><span role="status">{filtered.length} {c.count}</span><span>{c.dataTime}: {new Intl.DateTimeFormat(locale === "tr" ? "tr-TR" : "en-GB", { dateStyle: "medium", timeStyle: "short", timeZone: "Europe/Istanbul" }).format(new Date(snapshot.evaluatedAt))}</span></div>
    <div className={styles.list}>
      {filtered.map(signal => <SignalCard key={signal.id} signal={signal} locale={locale} />)}
      {!filtered.length && <div className={styles.empty}><p>{c.empty}</p><button onClick={() => setFilters({ sector: "all", state: "all", query: "" })}>{c.reset}</button></div>}
    </div>
    <footer className={styles.note}>{c.note}</footer>
  </main>;
}
