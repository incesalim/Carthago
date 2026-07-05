/**
 * Deck HTML builder — the web twin of scripts/generate_presentation.py's
 * build_html(). A pure string builder (no DOM), so it runs in the Worker.
 * Served by app/api/presentation/route.ts; the browser's print → "Save as PDF"
 * turns it into the PDF (Workers can't run headless Chrome, unlike the CLI).
 *
 * Kept visually in sync with the Python version: same 16:9 slide structure,
 * same figure-emphasis rule, same editorial palette (chart-theme.ts LIGHT).
 * Both consume the same deterministic reads shape ({tab, headline, items[]}).
 */

export interface DeckSection {
  tab: string;
  headline: string;
  items: string[];
}

export interface DeckOptions {
  title?: string;
  subtitle?: string;
  /** ISO date shown on the title slide (caller passes it — no Date in the lib). */
  generatedAt?: string;
  /** Fire the print dialog on load (the admin "Generate PDF" flow). */
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
const MUTED = "#5A6472";
const FIG = "#1C3A60";

// Numeric figures to emphasise: currency amounts (₺…) and any number glued to a
// unit (%, pp, ×, bp). Not bare integers/years, so "2026-05"/"4-week" stay plain.
// Applied AFTER escaping — the escaped entities never form a number+unit token.
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

/** Drop a leading "As of YYYY-MM:" clause and re-capitalise the remainder. */
function stripAsOf(headline: string): string {
  const out = headline.replace(/^\s*[Aa]s of \d{4}-\d{2}:\s*/, "").trim();
  return out ? out.charAt(0).toUpperCase() + out.slice(1) : out;
}

/** Pull "As of YYYY-MM" out of the overview headline for the deck period. */
function asOf(sections: DeckSection[]): string {
  for (const s of sections) {
    const m = s.headline.match(/[Aa]s of (\d{4}-\d{2})/);
    if (m) return m[1];
  }
  return "";
}

function pad2(n: number): string {
  return n < 10 ? `0${n}` : `${n}`;
}

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
      display: flex; flex-direction: column; padding: 84px 96px 72px;
    }
    .slide:last-child { page-break-after: auto; }

    .kicker {
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
      font-size: 15px; letter-spacing: .22em; text-transform: uppercase;
      color: ${NAVY}; font-weight: 600;
    }
    .kicker::before {
      content: ""; display: inline-block; width: 30px; height: 3px;
      background: ${NAVY}; vertical-align: middle; margin-right: 14px;
      margin-bottom: 4px;
    }
    .fig { color: ${FIG}; font-weight: 600; }
    .slide-num {
      position: absolute; right: 96px; bottom: 40px;
      font-family: "SFMono-Regular", Consolas, monospace;
      font-size: 13px; color: ${MUTED}; letter-spacing: .1em;
    }
    .slide-foot {
      position: absolute; left: 96px; bottom: 40px; font-size: 13px; color: ${MUTED};
    }
    .ghost {
      position: absolute; right: 60px; top: 20px; font-family: Georgia, serif;
      font-size: 340px; line-height: 1; color: ${NAVY}; opacity: .04;
      font-weight: 700; user-select: none;
    }

    .headline {
      font-family: Georgia, "Times New Roman", serif; font-weight: 600;
      font-size: 42px; line-height: 1.28; color: ${INK};
      margin: 30px 0 34px; max-width: 1000px;
    }
    .bullets { list-style: none; max-width: 1010px; }
    .bullets li {
      position: relative; font-size: 22px; line-height: 1.5; color: #3A4759;
      padding-left: 30px; margin-bottom: 18px;
    }
    .bullets li::before {
      content: ""; position: absolute; left: 4px; top: 12px;
      width: 8px; height: 8px; background: ${NAVY}; border-radius: 50%;
    }

    .title { justify-content: center; padding-left: 110px; }
    .title::before {
      content: ""; position: absolute; left: 0; top: 0; bottom: 0;
      width: 14px; background: ${NAVY};
    }
    .brand {
      font-family: "SFMono-Regular", Consolas, monospace; font-size: 16px;
      letter-spacing: .22em; text-transform: uppercase; color: ${NAVY};
      font-weight: 600; margin-bottom: 26px;
    }
    h1.deck-title {
      font-family: Georgia, serif; font-weight: 700; font-size: 76px;
      line-height: 1.08; color: ${INK}; letter-spacing: -.5px; max-width: 940px;
    }
    .deck-sub { font-size: 27px; color: ${MUTED}; margin-top: 18px; font-weight: 400; }
    .deck-period {
      display: inline-block; margin-top: 40px; font-size: 20px; font-weight: 600;
      color: ${NAVY}; border: 1.5px solid ${NAVY}; border-radius: 999px;
      padding: 8px 22px;
    }
    .deck-meta {
      position: absolute; left: 110px; bottom: 56px; font-size: 15px; color: ${MUTED};
    }

    .closing { justify-content: center; padding-left: 110px; }
    .closing::before {
      content: ""; position: absolute; left: 0; top: 0; bottom: 0;
      width: 14px; background: ${NAVY};
    }
    .closing h2 { font-family: Georgia, serif; font-size: 40px; color: ${INK}; margin-bottom: 26px; }
    .closing p { font-size: 20px; line-height: 1.65; color: #3A4759; max-width: 880px; margin-bottom: 16px; }
    .closing .fine { font-size: 15px; color: ${MUTED}; margin-top: 20px; }

    /* on-screen preview chrome — hidden when printing */
    .toolbar {
      position: fixed; top: 0; left: 0; right: 0; z-index: 10;
      display: flex; align-items: center; gap: 14px; justify-content: center;
      padding: 10px 16px; background: ${NAVY}; color: #fff; font-size: 13px;
    }
    .toolbar button {
      font: inherit; font-weight: 600; cursor: pointer; color: ${NAVY};
      background: #fff; border: 0; border-radius: 6px; padding: 6px 14px;
    }
    @media screen {
      body { display: flex; flex-direction: column; align-items: center; gap: 18px; padding: 64px 16px 32px; }
      .slide { box-shadow: 0 6px 30px rgba(0,0,0,.16); }
    }
    @media print { .toolbar { display: none !important; } }
  `;
}

function titleSlide(o: Required<Pick<DeckOptions, "title" | "subtitle" | "generatedAt">>, period: string): string {
  const pill = period ? `<div class="deck-period">As of ${esc(period)}</div>` : "";
  return `
    <section class="slide title">
      <div class="brand">BDDK · Sector Analytics</div>
      <h1 class="deck-title">${esc(o.title)}</h1>
      <div class="deck-sub">${esc(o.subtitle)}</div>
      ${pill}
      <div class="deck-meta">Generated ${esc(o.generatedAt)} · Source: BDDK monthly &amp; weekly
      bulletins + BRSA quarterly audit reports</div>
    </section>`;
}

function sectionSlide(idx: number, total: number, s: DeckSection, period: string): string {
  const title = sectionTitle(s.tab);
  const headline = emphasise(stripAsOf(s.headline));
  const items = s.items.map((i) => `<li>${emphasise(i)}</li>`).join("");
  const foot = `Turkish Banking Sector · The Read${period ? ` · ${period}` : ""}`;
  return `
    <section class="slide section">
      <div class="ghost">${pad2(idx)}</div>
      <div class="kicker">${pad2(idx)} · ${esc(title.toUpperCase())}</div>
      <h2 class="headline">${headline}</h2>
      <ul class="bullets">${items}</ul>
      <div class="slide-foot">${esc(foot)}</div>
      <div class="slide-num">${idx} / ${total}</div>
    </section>`;
}

function closingSlide(): string {
  return `
    <section class="slide closing">
      <div class="kicker">Methodology</div>
      <h2>How this deck is built</h2>
      <p>Every figure is drawn from the dashboard's deterministic insight
      engine — no model rewriting, no estimates. The same headline and drivers
      shown on each tab, generated on demand.</p>
      <p>Underlying data: BDDK monthly &amp; weekly banking bulletins and BRSA
      quarterly audit reports, refreshed on the pipeline's regular cadence.</p>
      <p class="fine">Indicative analytics for internal use — not investment
      advice. Ratios follow BDDK / BRSA definitions; audited metrics (CET1, LCR,
      NSFR) are quarterly.</p>
    </section>`;
}

export function buildDeckHtml(sections: DeckSection[], opts: DeckOptions = {}): string {
  const o = {
    title: opts.title || "Turkish Banking Sector",
    subtitle: opts.subtitle || "The Read — Sector Snapshot",
    generatedAt: opts.generatedAt || "",
  };
  const period = asOf(sections);
  const total = sections.length;
  const slides = [
    titleSlide(o, period),
    ...sections.map((s, i) => sectionSlide(i + 1, total, s, period)),
    closingSlide(),
  ].join("\n");

  const toolbar = `
    <div class="toolbar">
      <span>Sector deck — press <b>Ctrl / Cmd + P</b> and choose “Save as PDF”.</span>
      <button onclick="window.print()">Save as PDF</button>
    </div>`;
  const autoPrint = opts.autoPrint
    ? `<script>window.addEventListener("load",function(){setTimeout(function(){window.print();},350);});</script>`
    : "";

  return (
    `<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n` +
    `<meta name="viewport" content="width=device-width, initial-scale=1">\n` +
    `<title>${esc(o.title)}</title>\n<style>${css()}</style>\n</head>\n` +
    `<body>\n${toolbar}\n${slides}\n${autoPrint}\n</body>\n</html>\n`
  );
}
