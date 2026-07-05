/**
 * Deck HTML builder — renders the sector "Read" as a print-ready 16:9 slide
 * deck: a dark title slide, a KPI vitals slide (stat tiles), one slide per tab
 * (headline + driver bullets + an inline-SVG trend chart), and a methodology
 * slide. Served by app/api/presentation/route.ts; the browser's print → "Save
 * as PDF" is the render step (Workers can't run headless Chrome — that path is
 * the CLI, scripts/generate_presentation.py, which fetches this same HTML).
 *
 * Pure string builder (no DOM). All figures/series come from presentation-data.ts,
 * which reuses the dashboard's own metrics.ts functions — so the deck carries the
 * same numbers as the site, no re-derivation. Palette = chart-theme.ts LIGHT.
 */

export interface DeckChart {
  label: string;
  unit: string;
  points: { period: string; value: number }[];
}
export interface DeckVital {
  label: string;
  value: number | null;
  unit: string;
  decimals: number;
}
export interface DeckSection {
  tab: string;
  headline: string;
  items: string[];
  chart?: DeckChart;
}
export interface DeckData {
  asOf: string;
  sections: DeckSection[];
  vitals: DeckVital[];
}
export interface DeckOptions {
  title?: string;
  subtitle?: string;
  generatedAt?: string;
  autoPrint?: boolean;
}

const SECTION_TITLES: Record<string, string> = {
  overview: "Sector Overview",
  credit: "Credit",
  deposits: "Deposits",
  "asset-quality": "Asset Quality",
  capital: "Capital",
  profitability: "Profitability",
  liquidity: "Liquidity",
  "market-risk": "Market Risk",
};

// "Editorial" palette, mirrored from app/lib/chart-theme.ts (LIGHT).
const PAPER = "#FBFAF7";
const INK = "#16243B";
const NAVY = "#1C3A60";
const DEEP = "#12233B"; // title-slide background
const GOLD = "#B98A5E"; // warm accent
const MUTED = "#5A6472";
const HAIRLINE = "#E4DED2";
const FIG = "#1C3A60";

const FIG_RE =
  /(₺\s?\d[\d.,]*\s?(?:trn|bn|mn|m|k)?|[+\-−]?\d[\d.,]*\s?(?:%|pp|ppt|bps|bp|×))/g;

function esc(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#x27;");
}

function emphasise(text: string): string {
  return esc(text).replace(FIG_RE, '<span class="fig">$1</span>');
}

function sectionTitle(tab: string): string {
  return (
    SECTION_TITLES[tab] ??
    tab.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
  );
}

function stripAsOf(headline: string): string {
  const out = headline.replace(/^\s*[Aa]s of \d{4}-\d{2}:\s*/, "").trim();
  return out ? out.charAt(0).toUpperCase() + out.slice(1) : out;
}

function pad2(n: number): string {
  return n < 10 ? `0${n}` : `${n}`;
}

function fmtVal(v: number | null, decimals: number): string {
  return v == null ? "—" : v.toFixed(decimals);
}

/** Short period label for a chart axis ("2026-05", weekly date → "2026-05"). */
function periodLabel(s: string): string {
  return s.length >= 7 ? s.slice(0, 7) : s;
}

// ---------------------------------------------------------------- SVG chart ---

function chartSvg(chart: DeckChart, id: string): string {
  const p = chart.points;
  const W = 460;
  const H = 208;
  const padL = 6;
  const padR = 6;
  const padT = 18;
  const padB = 26;
  const x = (i: number) => padL + (i / (p.length - 1)) * (W - padL - padR);

  const vals = p.map((d) => d.value);
  let min = Math.min(...vals);
  let max = Math.max(...vals);
  if (min === max) {
    min -= 1;
    max += 1;
  }
  const gap = (max - min) * 0.14;
  min -= gap;
  max += gap;
  const y = (v: number) => padT + (1 - (v - min) / (max - min)) * (H - padT - padB);

  const line = p.map((d, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(d.value).toFixed(1)}`).join(" ");
  const area = `${line} L${x(p.length - 1).toFixed(1)},${(H - padB).toFixed(1)} L${x(0).toFixed(1)},${(H - padB).toFixed(1)} Z`;
  const lx = x(p.length - 1);
  const ly = y(p[p.length - 1].value);
  const lastTxt = `${(Math.round(p[p.length - 1].value * 10) / 10).toString()}${chart.unit}`;
  const tick = `font-family:'SFMono-Regular',Consolas,monospace;font-size:11px;fill:${MUTED};`;

  return `<svg viewBox="0 0 ${W} ${H}" width="100%" style="display:block" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${esc(chart.label)}">
    <defs><linearGradient id="grad-${id}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="${NAVY}" stop-opacity="0.17"/>
      <stop offset="1" stop-color="${NAVY}" stop-opacity="0"/></linearGradient></defs>
    <line x1="${padL}" y1="${(H - padB).toFixed(1)}" x2="${W - padR}" y2="${(H - padB).toFixed(1)}" stroke="${HAIRLINE}" stroke-width="1"/>
    <path d="${area}" fill="url(#grad-${id})"/>
    <path d="${line}" fill="none" stroke="${NAVY}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="4" fill="${NAVY}"/>
    <text x="${(lx - 6).toFixed(1)}" y="${(ly - 9).toFixed(1)}" text-anchor="end" style="font-family:Georgia,serif;font-size:15px;font-weight:700;fill:${NAVY};">${esc(lastTxt)}</text>
    <text x="${padL}" y="${H - 7}" style="${tick}">${esc(periodLabel(p[0].period))}</text>
    <text x="${W - padR}" y="${H - 7}" text-anchor="end" style="${tick}">${esc(periodLabel(p[p.length - 1].period))}</text>
  </svg>`;
}

// ------------------------------------------------------------------- slides ---

function css(): string {
  return `
    @page { size: 1280px 720px; margin: 0; }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    body {
      font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      color: ${INK}; background: #d9d6cf;
    }
    .slide {
      position: relative; width: 1280px; height: 720px; overflow: hidden;
      background: ${PAPER}; page-break-after: always;
      display: flex; flex-direction: column; padding: 76px 96px 64px;
    }
    .slide:last-child { page-break-after: auto; }

    .kicker {
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
      font-size: 15px; letter-spacing: .22em; text-transform: uppercase;
      color: ${NAVY}; font-weight: 600;
    }
    .kicker::before {
      content: ""; display: inline-block; width: 30px; height: 3px;
      background: ${GOLD}; vertical-align: middle; margin-right: 14px; margin-bottom: 4px;
    }
    .fig { color: ${FIG}; font-weight: 600; }
    .slide-num {
      position: absolute; right: 96px; bottom: 34px;
      font-family: "SFMono-Regular", Consolas, monospace;
      font-size: 13px; color: ${MUTED}; letter-spacing: .1em;
    }
    .slide-foot {
      position: absolute; left: 96px; bottom: 34px; font-size: 13px; color: ${MUTED};
    }
    .ghost {
      position: absolute; right: 54px; top: 8px; font-family: Georgia, serif;
      font-size: 300px; line-height: 1; color: ${NAVY}; opacity: .045;
      font-weight: 700; user-select: none;
    }

    .headline {
      font-family: Georgia, "Times New Roman", serif; font-weight: 600;
      font-size: 38px; line-height: 1.26; color: ${INK}; margin: 24px 0 26px; max-width: 1090px;
    }
    .section-body { display: flex; gap: 46px; align-items: flex-start; flex: 1; min-height: 0; }
    .bullets { list-style: none; flex: 1 1 55%; }
    .section-body.nochart .bullets { flex: 1 1 100%; }
    .bullets li {
      position: relative; font-size: 21px; line-height: 1.48; color: #3A4759;
      padding-left: 28px; margin-bottom: 16px;
    }
    .bullets li::before {
      content: ""; position: absolute; left: 3px; top: 11px;
      width: 8px; height: 8px; background: ${NAVY}; border-radius: 50%;
    }
    .chart-card {
      flex: 0 0 42%; align-self: stretch; max-height: 100%;
      border: 1px solid ${HAIRLINE}; border-radius: 14px; background: #fff;
      padding: 18px 20px 14px; display: flex; flex-direction: column;
    }
    .chart-title {
      font-family: "SFMono-Regular", Consolas, monospace; font-size: 12px;
      letter-spacing: .1em; text-transform: uppercase; color: ${NAVY}; font-weight: 600;
      margin-bottom: 10px;
    }
    .chart-svg { flex: 1; display: flex; align-items: center; }
    .chart-cap { font-size: 12.5px; color: ${MUTED}; margin-top: 8px; }

    /* title slide (dark) */
    .title { justify-content: center; padding-left: 110px; background: ${DEEP}; color: #fff; }
    .title::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 12px; background: ${GOLD}; }
    .brand {
      font-family: "SFMono-Regular", Consolas, monospace; font-size: 16px;
      letter-spacing: .24em; text-transform: uppercase; color: ${GOLD}; font-weight: 600; margin-bottom: 24px;
    }
    h1.deck-title { font-family: Georgia, serif; font-weight: 700; font-size: 78px; line-height: 1.06; color: #fff; letter-spacing: -.5px; max-width: 940px; }
    .deck-sub { font-size: 27px; color: #B9C2D0; margin-top: 18px; font-weight: 400; }
    .deck-period { display: inline-block; margin-top: 40px; font-size: 20px; font-weight: 600; color: #fff; border: 1.5px solid rgba(255,255,255,.55); border-radius: 999px; padding: 8px 22px; }
    .deck-meta { position: absolute; left: 110px; bottom: 52px; font-size: 15px; color: #8B95A6; }

    /* KPI vitals slide */
    .vitals-head { font-family: Georgia, serif; font-weight: 600; font-size: 34px; line-height: 1.28; color: ${INK}; margin: 22px 0 30px; max-width: 1090px; }
    .tiles { display: grid; grid-template-columns: repeat(4, 1fr); gap: 18px; }
    .tile { border: 1px solid ${HAIRLINE}; border-top: 3px solid ${NAVY}; border-radius: 14px; background: #fff; padding: 22px 22px 20px; }
    .tile-val { font-family: Georgia, serif; font-weight: 700; font-size: 42px; color: ${NAVY}; line-height: 1; }
    .tile-val .u { font-size: 22px; font-weight: 600; color: ${GOLD}; margin-left: 2px; }
    .tile-lbl { font-size: 14px; color: ${MUTED}; margin-top: 10px; letter-spacing: .01em; }

    /* closing */
    .closing { justify-content: center; padding-left: 110px; }
    .closing::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 12px; background: ${GOLD}; }
    .closing h2 { font-family: Georgia, serif; font-size: 40px; color: ${INK}; margin-bottom: 24px; }
    .closing p { font-size: 20px; line-height: 1.62; color: #3A4759; max-width: 900px; margin-bottom: 15px; }
    .closing .fine { font-size: 15px; color: ${MUTED}; margin-top: 18px; }

    /* on-screen preview chrome — hidden when printing */
    .toolbar {
      position: fixed; top: 0; left: 0; right: 0; z-index: 10;
      display: flex; align-items: center; gap: 14px; justify-content: center;
      padding: 10px 16px; background: ${NAVY}; color: #fff; font-size: 13px;
    }
    .toolbar button { font: inherit; font-weight: 600; cursor: pointer; color: ${NAVY}; background: #fff; border: 0; border-radius: 6px; padding: 6px 14px; }
    @media screen { body { display: flex; flex-direction: column; align-items: center; gap: 18px; padding: 64px 16px 32px; } .slide { box-shadow: 0 6px 30px rgba(0,0,0,.16); } }
    @media print { .toolbar { display: none !important; } }
  `;
}

function titleSlide(title: string, subtitle: string, generatedAt: string, period: string): string {
  const pill = period ? `<div class="deck-period">As of ${esc(period)}</div>` : "";
  const gen = generatedAt ? `Generated ${esc(generatedAt)} · ` : "";
  return `
    <section class="slide title">
      <div class="brand">BDDK · Sector Analytics</div>
      <h1 class="deck-title">${esc(title)}</h1>
      <div class="deck-sub">${esc(subtitle)}</div>
      ${pill}
      <div class="deck-meta">${gen}Source: BDDK monthly &amp; weekly bulletins + BRSA quarterly audit reports</div>
    </section>`;
}

function vitalsSlide(headline: string, period: string, vitals: DeckVital[]): string {
  const tiles = vitals
    .map(
      (v) => `
      <div class="tile">
        <div class="tile-val">${fmtVal(v.value, v.decimals)}<span class="u">${esc(v.unit)}</span></div>
        <div class="tile-lbl">${esc(v.label)}</div>
      </div>`,
    )
    .join("");
  return `
    <section class="slide vitals">
      <div class="kicker">Sector Vitals${period ? ` · ${esc(period)}` : ""}</div>
      <h2 class="vitals-head">${emphasise(stripAsOf(headline))}</h2>
      <div class="tiles">${tiles}</div>
    </section>`;
}

function sectionSlide(idx: number, total: number, s: DeckSection, period: string): string {
  const title = sectionTitle(s.tab);
  const headline = emphasise(stripAsOf(s.headline));
  const items = s.items.map((i) => `<li>${emphasise(i)}</li>`).join("");
  const foot = `Turkish Banking Sector · The Read${period ? ` · ${period}` : ""}`;
  const chart = s.chart
    ? `<div class="chart-card">
         <div class="chart-title">${esc(s.chart.label)}</div>
         <div class="chart-svg">${chartSvg(s.chart, s.tab)}</div>
         <div class="chart-cap">Sector aggregate · ${esc(periodLabel(s.chart.points[0].period))}–${esc(periodLabel(s.chart.points[s.chart.points.length - 1].period))}</div>
       </div>`
    : "";
  return `
    <section class="slide section">
      <div class="ghost">${pad2(idx)}</div>
      <div class="kicker">${pad2(idx)} · ${esc(title.toUpperCase())}</div>
      <h2 class="headline">${headline}</h2>
      <div class="section-body${s.chart ? "" : " nochart"}">
        <ul class="bullets">${items}</ul>
        ${chart}
      </div>
      <div class="slide-foot">${esc(foot)}</div>
      <div class="slide-num">${idx} / ${total}</div>
    </section>`;
}

function closingSlide(): string {
  return `
    <section class="slide closing">
      <div class="kicker">Methodology</div>
      <h2>How this deck is built</h2>
      <p>Every figure and chart is drawn from the dashboard's own metric
      functions — the same series the site plots, no re-derivation, no estimates.
      Generated on demand from live data.</p>
      <p>Underlying data: BDDK monthly &amp; weekly banking bulletins and BRSA
      quarterly audit reports, refreshed on the pipeline's regular cadence.</p>
      <p class="fine">Indicative analytics for internal use — not investment
      advice. Ratios follow BDDK / BRSA definitions; audited metrics (CET1, LCR,
      FX position) are quarterly.</p>
    </section>`;
}

export function buildDeckHtml(data: DeckData, opts: DeckOptions = {}): string {
  const title = opts.title || "Turkish Banking Sector";
  const subtitle = opts.subtitle || "The Read — Sector Snapshot";
  const period = data.asOf || "";

  const overview = data.sections.find((s) => s.tab === "overview");
  const rest = data.sections.filter((s) => s.tab !== "overview");
  const total = rest.length;

  const slides = [
    titleSlide(title, subtitle, opts.generatedAt || "", period),
    overview && data.vitals.length ? vitalsSlide(overview.headline, period, data.vitals) : "",
    ...rest.map((s, i) => sectionSlide(i + 1, total, s, period)),
    closingSlide(),
  ]
    .filter(Boolean)
    .join("\n");

  const toolbar = `
    <div class="toolbar">
      <span>Sector deck — press <b>Ctrl / Cmd + P</b> and choose “Save as PDF”.</span>
      <button onclick="window.print()">Save as PDF</button>
    </div>`;
  const autoPrint = opts.autoPrint
    ? `<script>window.addEventListener("load",function(){setTimeout(function(){window.print();},400);});</script>`
    : "";

  return (
    `<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n` +
    `<meta name="viewport" content="width=device-width, initial-scale=1">\n` +
    `<title>${esc(title)}</title>\n<style>${css()}</style>\n</head>\n` +
    `<body>\n${toolbar}\n${slides}\n${autoPrint}\n</body>\n</html>\n`
  );
}
