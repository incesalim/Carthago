/**
 * /regulation — the regime in force, compiled from the instruments that set it.
 *
 * The feed table (news_items) holds the regulators' own text. This module turns
 * that text into *state*: the policy corridor, the reserve ratios, the date each
 * one binds, and the board decisions keyed on the date they were TAKEN rather
 * than the date we happened to scrape them.
 *
 * Three rules the design depends on (see docs/knowledge/regulation-tab-redesign-2026-07-12.md):
 *
 *  1. FIGURES ARE COMPILED, NOT WRITTEN. Nothing here comes from the LLM
 *     briefing. The policy rate is read from EVDS and *reconciled* against the
 *     press release; a disagreement raises a flag rather than picking a winner.
 *  2. WHAT CANNOT BE READ IS PRINTED. TCMB ships most macroprudential releases
 *     without a parseable parameter table (10 of the last 12). A rule we can
 *     classify but cannot parse becomes an `unreadRules` entry, so the band
 *     declares its own incompleteness instead of implying the regime is six
 *     numbers wide.
 *  3. UNKNOWN IS A STATE. Classification has three outcomes, not two — an
 *     unrecognised release is `unclassified` and counted, never silently
 *     dropped into "not regulation".
 */
import { cachedAll } from "./db";
import type { NewsItem } from "./news";

// ─────────────────────────────────────────────────────────── types

/** What kind of thing a feed item is. `unclassified` is deliberate — see rule 3. */
export type InstrumentKind = "rate" | "rule" | "board" | "other" | "unclassified";

/** An instrument actually changes the rules; comms and housekeeping do not. */
export function isInstrument(kind: InstrumentKind): boolean {
  return kind === "rate" || kind === "rule" || kind === "board";
}

export interface BoardDecision {
  /** ISO date the BOARD took the decision — parsed from the title, not published_at. */
  decidedAt: string;
  /** BDDK's sequential Kurul Kararı number. */
  decisionNo: number;
  /** The title with the "(date - no)" prefix stripped. */
  subject: string;
}

export interface Corridor {
  policy: number;
  lending: number | null;
  borrowing: number | null;
  /** Publication date of the release that set it. */
  decidedAt: string;
  url: string;
}

export interface ReserveChange {
  label: string;
  prev: number;
  next: number;
}

export interface ReserveState {
  changes: ReserveChange[];
  /** Ratios abolished outright, e.g. the 2.5% additional TL reserve. */
  terminated: { label: string; was: number }[];
  /** The date the release says the new ratios start being maintained. */
  bindsOn: string | null;
  decidedAt: string;
  url: string;
}

/** A release we classified as a rule but could extract no parameters from. */
export interface UnreadRule {
  title: string;
  publishedAt: string;
  url: string;
  /** Body length — the tell: a rule release under ~600 chars lost its table. */
  bodyLength: number;
}

export interface PolicyPoint {
  date: string;
  rate: number;
}

export interface DecisionLagRow extends BoardDecision {
  publishedAt: string;
  /** Days between the decision and its arrival in the feed. */
  lagDays: number;
}

// ─────────────────────────────────────────────────────────── title parsing

/**
 * BDDK prints the decision date AND the board-decision number in the title:
 *
 *   "(12.03.2026 - 11428) Siemens Finansman A.Ş.'ye faaliyet izni ... Kurul Kararı"
 *     └ decided        └ no.
 *
 * We store `published_at` = the day we scraped it, which lags the decision by a
 * mean of 309 days (worst: 629). Sorting the archive by publication therefore
 * presents a 2024 decision as 2026 news. Parse the real date out of the title.
 *
 * Only ~33 of 603 BDDK titles carry the prefix; the rest return null and fall
 * back to the publication date, marked as such in the UI.
 */
const BOARD_TITLE_RE = /^\((\d{2})\.(\d{2})\.(\d{4})\s*[-–]\s*(\d+)\)\s*(.*)$/;

export function parseBoardDecision(title: string): BoardDecision | null {
  const m = BOARD_TITLE_RE.exec(title.trim());
  if (!m) return null;
  const [, dd, mm, yyyy, no, subject] = m;
  const month = Number(mm);
  const day = Number(dd);
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;
  return {
    decidedAt: `${yyyy}-${mm}-${dd}`,
    decisionNo: Number(no),
    subject: subject.trim(),
  };
}

// ─────────────────────────────────────────────────────────── classification

// Ordered, first match wins. Every pattern below was written against the real
// feed, and the NOISE list is a regression set: an SSL certificate, a journal
// issue, a Hong Kong memorandum and the results of a cleaning-staff recruitment
// exam were all being counted as "regulatory instruments" by the page this
// replaces.
//
// NOISE is tested BEFORE the rule patterns, because Turkish announcement titles
// are promiscuous: "Makro İhtiyati Önlemlere İlişkin Basın Duyurusu" is a rule,
// but "BDDK Altıncı Stratejik Planı Hakkında Basın Açıklaması" is not, and both
// end in the same words.
const RATE_RE = /press release on interest rates/i;

const NOISE_RE =
  // TCMB housekeeping and comms
  /certificate|memorandum of understanding|general assembly|meeting of the (?:council|financial stability)|briefing|obituary|appoint|summary of the monetary policy committee|inflation report|banknote|survey|website|data delivery|external debt|balance of payments|working paper|conference|seminar|award/i;

const NOISE_TR_RE =
  // BDDK housekeeping: journals, annual reports, statistics, staff exams,
  // strategic plans, fraud warnings — none of which change a rule.
  /dergi|faaliyet raporu|bülten|istatistik|temel göstergeler|stratejik plan|sınav|personel alımı|işçi|dolandırıcılık|etkinlik|çalıştay|anma|atama/i;

// A rule CHANGES A BINDING PARAMETER. Turkish and English both, because BDDK
// writes in Turkish and TCMB in English, and the regime is one regime.
const RULE_RE =
  /macroprudential|reserve requirement|required reserves|securities maintenance|liquidity management|forward selling|rediscount|remuneration of required reserves/i;

const RULE_TR_RE =
  /makro ?ihtiyati|yeniden yapılandırıl|kredi kartı|ihtiyaç kredi|taksit|azami (?:faiz|oran|vade)|limit|sınır|yönetmelik|tebliğ|değişiklik yapılmasına/i;

const BOARD_RE = /kurul karar|faaliyet izni|kuruluş izni|kurulmasına izin|iptaline ilişkin/i;

/**
 * rate | rule | board = an instrument (it changes something a bank must obey).
 * other = comms and housekeeping (the SSL cert, the journal, the staff exam).
 * unclassified = we do not recognise it — COUNTED AND PRINTED, never quietly
 * folded into "not regulation". An unrecognised release might be a rule; the
 * page says how many it could not place rather than pretending to know.
 */
export function classifyInstrument(item: Pick<NewsItem, "source" | "title">): InstrumentKind {
  const t = item.title;
  if (RATE_RE.test(t)) return "rate";
  if (NOISE_RE.test(t) || NOISE_TR_RE.test(t)) return "other";
  if (RULE_RE.test(t) || RULE_TR_RE.test(t)) return "rule";
  if (BOARD_RE.test(t)) return "board";
  return "unclassified";
}

// ─────────────────────────────────────────────────────────── corridor

/**
 * The MPC release states the corridor in one regular sentence, in both the
 * "hold" and the "change" phrasings:
 *
 *   "...decided to keep the policy rate (the one-week repo auction rate) at 37 percent."
 *   "...to reduce the policy rate (the one-week repo auction rate) from 38 percent to 37 percent."
 *   "The Committee has also maintained the Central Bank overnight lending rate and the
 *    overnight borrowing rate at 40 percent and 35.5 percent, respectively."
 *
 * 48 of 48 releases since 2022 parse. A phrasing we do not match returns null,
 * and the caller prints "not stated in the last release" — never the previous
 * value dressed up as current.
 */
// Two phrasings, and the order matters: "from 39.5 percent TO 38 percent" must
// yield the NEW rate, so the "to" form is tried first and the "at" form is the
// fallback for holds ("keep the policy rate … at 37 percent").
//
// Do NOT bound these with [^.] to keep them inside one sentence: a rate like
// "39.5" contains a full stop, so [^.] stops dead at the decimal and silently
// drops every decision whose OLD rate had a decimal — 8 of 48, including five
// of the cycle's largest moves. Bound by line and by length instead.
const POLICY_TO_RE = /policy rate\b[^\n]{0,200}?\bto\s+([\d.]+)\s*percent/i;
const POLICY_AT_RE = /policy rate\b[^\n]{0,200}?\b(?:constant\s+)?at\s+([\d.]+)\s*percent/i;
const OVERNIGHT_RE =
  /overnight lending rate and (?:the )?overnight borrowing rate\s+(?:at|to)\s+([\d.]+)\s*percent and\s+([\d.]+)\s*percent/i;

export function parsePolicyRate(body: string | null | undefined): number | null {
  if (!body) return null;
  const m = POLICY_TO_RE.exec(body) ?? POLICY_AT_RE.exec(body);
  return m ? Number(m[1]) : null;
}

export function parseOvernight(
  body: string | null | undefined,
): { lending: number; borrowing: number } | null {
  if (!body) return null;
  const m = OVERNIGHT_RE.exec(body);
  return m ? { lending: Number(m[1]), borrowing: Number(m[2]) } : null;
}

/** The corridor as set by the most recent rate decision we can parse. */
export function deriveCorridor(items: NewsItem[]): Corridor | null {
  const rates = items
    .filter((it) => classifyInstrument(it) === "rate")
    .sort((a, b) => b.published_at.localeCompare(a.published_at));
  for (const it of rates) {
    const policy = parsePolicyRate(it.body_text);
    if (policy == null) continue;
    const on = parseOvernight(it.body_text);
    return {
      policy,
      lending: on?.lending ?? null,
      borrowing: on?.borrowing ?? null,
      decidedAt: it.published_at.slice(0, 10),
      url: it.url,
    };
  }
  return null;
}

/**
 * The whole rate cycle, reconstructed from the releases: 14% → 8.5% (Feb 2023)
 * → 50% (Mar 2024) → 37%. 48 decisions, 24 of them changes. The page has stored
 * every one of these for four years and never drawn a line.
 */
export function derivePolicyPath(items: NewsItem[]): PolicyPoint[] {
  return items
    .filter((it) => classifyInstrument(it) === "rate")
    .map((it) => ({ date: it.published_at.slice(0, 10), rate: parsePolicyRate(it.body_text) }))
    .filter((p): p is PolicyPoint => p.rate != null)
    .sort((a, b) => a.date.localeCompare(b.date));
}

/** Points where the rate actually moved (the path is a step function). */
export function rateChanges(path: PolicyPoint[]): PolicyPoint[] {
  return path.filter((p, i) => i === 0 || p.rate !== path[i - 1].rate);
}

/** Consecutive meetings at the current rate, not counting the one that set it. */
export function meetingsHeld(path: PolicyPoint[]): number {
  if (path.length === 0) return 0;
  const now = path[path.length - 1].rate;
  let n = 0;
  for (let i = path.length - 1; i > 0; i--) {
    if (path[i].rate !== now) break;
    if (path[i - 1].rate !== now) break; // path[i] is the change itself
    n++;
  }
  return n;
}

// ─────────────────────────────────────────────────────────── reserve ratios

// The scraper converts the release's <table> to a Markdown pipe table
// (src/news/_htmltext.py). When TCMB ships one, it looks like:
//
//   | Foreign currency deposits… | Previous Ratio | New Ratio |
//   | --- | --- | --- |
//   | Demand deposits … up to 1 month | 30% | 32% |
//
// When TCMB does NOT ship one — which is the common case — there is nothing to
// parse, and the release becomes an `unreadRule`.
const PCT_RE = /(-?[\d.,]+)\s*%/;

function pct(cell: string): number | null {
  const m = PCT_RE.exec(cell);
  if (!m) return null;
  const v = Number(m[1].replace(",", "."));
  return Number.isFinite(v) ? v : null;
}

export function parseReserveChanges(body: string | null | undefined): ReserveChange[] {
  if (!body) return [];
  const out: ReserveChange[] = [];
  for (const block of body.split(/\n{2,}/)) {
    const lines = block.trim().split("\n");
    if (lines.length < 3 || !lines.every((l) => l.trim().startsWith("|"))) continue;
    const header = lines[0].toLowerCase();
    if (!header.includes("previous") || !header.includes("new")) continue;
    for (const line of lines.slice(2)) {
      const cells = line
        .trim()
        .replace(/^\||\|$/g, "")
        .split("|")
        .map((c) => c.trim());
      if (cells.length < 3) continue;
      const prev = pct(cells[1]);
      const next = pct(cells[2]);
      if (prev == null || next == null) continue;
      out.push({ label: cells[0], prev, next });
    }
  }
  return out;
}

/**
 * "The additional Turkish lira reserve requirement ratio for FX deposits…,
 *  which was introduced in 2023 and is currently applied at 2.5%, has been
 *  terminated."
 *
 * A rule ending is a rule change. The label is the subject up to the first
 * subordinate clause — otherwise it swallows the whole sentence and prints a
 * paragraph where a cell label belongs.
 */
const TERMINATED_RE = /([^.\n]*?)\s*(?:,?\s*which (?:was|is)[^,]*)?,?\s*(?:is |are )?currently applied at\s+([\d.]+)\s*%[^.]*?has been terminated/gi;

export function parseTerminated(body: string | null | undefined): { label: string; was: number }[] {
  if (!body) return [];
  const out: { label: string; was: number }[] = [];
  for (const m of body.matchAll(TERMINATED_RE)) {
    const label = m[1]
      .replace(/^[-\s]+/, "")
      .replace(/,.*$/, "") // drop everything after the first comma — that is prose
      .trim();
    out.push({ label: label || "Reserve requirement", was: Number(m[2]) });
  }
  return out;
}

/**
 * "The reserve requirements according to new ratios will be maintained on July 17, 2026."
 * The binding date is stated in prose, not held in a column. Most releases state
 * none — those return null and the UI says so rather than inventing one.
 */
const MONTHS: Record<string, string> = {
  january: "01", february: "02", march: "03", april: "04", may: "05", june: "06",
  july: "07", august: "08", september: "09", october: "10", november: "11", december: "12",
};
const BINDS_RE =
  /(?:maintained on|enter into force on|effective (?:as of|from)|applied (?:as of|from))\s+([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})/i;

export function parseBindingDate(body: string | null | undefined): string | null {
  if (!body) return null;
  const m = BINDS_RE.exec(body);
  if (!m) return null;
  const mm = MONTHS[m[1].toLowerCase()];
  if (!mm) return null;
  return `${m[3]}-${mm}-${String(Number(m[2])).padStart(2, "0")}`;
}

/** The reserve regime as set by the most recent macropru release we can parse. */
export function deriveReserves(items: NewsItem[]): ReserveState | null {
  const rules = items
    .filter((it) => classifyInstrument(it) === "rule")
    .sort((a, b) => b.published_at.localeCompare(a.published_at));
  for (const it of rules) {
    const changes = parseReserveChanges(it.body_text);
    const terminated = parseTerminated(it.body_text);
    if (changes.length === 0 && terminated.length === 0) continue;
    return {
      changes,
      terminated,
      bindsOn: parseBindingDate(it.body_text),
      decidedAt: it.published_at.slice(0, 10),
      url: it.url,
    };
  }
  return null;
}

/**
 * Rules we classified but could not read. This is the honesty counter: the
 * 23 May 2026 release sets credit "Growth Limits (For Eight Weeks)" and we hold
 * 342 characters of it — the heading, then the footer. A band that omits it
 * silently is worse than the feed-counting page it replaces.
 *
 * Scoped to the last `days` so it describes the regime now, not 2022.
 */
export function unreadRules(items: NewsItem[], anchor: string, days = 365): UnreadRule[] {
  const cutoff = Date.parse(anchor) - days * 86_400_000;
  return items
    .filter((it) => classifyInstrument(it) === "rule")
    .filter((it) => {
      const t = Date.parse(it.published_at);
      return Number.isFinite(t) && t >= cutoff;
    })
    .filter(
      (it) =>
        parseReserveChanges(it.body_text).length === 0 && parseTerminated(it.body_text).length === 0,
    )
    .map((it) => ({
      title: it.title,
      publishedAt: it.published_at.slice(0, 10),
      url: it.url,
      bodyLength: it.body_text?.length ?? 0,
    }))
    .sort((a, b) => b.publishedAt.localeCompare(a.publishedAt));
}

// ─────────────────────────────────────────────────────────── the clock

/** Board decisions keyed on the date they were taken, with the publication lag. */
export function decisionLags(items: NewsItem[]): DecisionLagRow[] {
  const out: DecisionLagRow[] = [];
  for (const it of items) {
    if (it.source !== "bddk") continue;
    const d = parseBoardDecision(it.title);
    if (!d) continue;
    const pub = it.published_at.slice(0, 10);
    const lag = Math.round((Date.parse(pub) - Date.parse(d.decidedAt)) / 86_400_000);
    if (!Number.isFinite(lag)) continue;
    out.push({ ...d, publishedAt: pub, lagDays: lag });
  }
  return out.sort((a, b) => a.decidedAt.localeCompare(b.decidedAt));
}

// ─────────────────────────────────────────────────────────── licensing

export interface LicenceRow {
  decision: DecisionLagRow;
  /** The institution named in the decision. */
  institution: string;
  /** Ticker if we cover it; null if we do not. */
  ticker: string | null;
}

const LICENCE_RE = /faaliyet izni ver|kurulmasına izin ver|kuruluş izni ver/i;

/** "Enpara Bank A.Ş.'ye faaliyet izni verilmesine ilişkin Kurul Kararı" → "Enpara Bank" */
export function institutionOf(subject: string): string {
  const m = /^(.*?)\s*A\.?Ş\.?/i.exec(subject);
  return (m ? m[1] : subject.split(/\s+/).slice(0, 4).join(" ")).trim();
}

/** Fold Turkish casing so "İKTİSAT" matches "iktisat". */
function fold(s: string): string {
  return s
    .replace(/İ/g, "i")
    .replace(/I/g, "ı")
    .toLocaleLowerCase("tr")
    .replace(/[^a-zçğıöşü ]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

// Words that appear in almost every Turkish bank's name and therefore identify
// nobody. Matching on substrings without stripping these is how "İş Bankası"
// (→ "bankası") comes to "match" Marin Yatırım Bankası, Adil Katılım Bankası
// and Aytemiz Yatırım Bankası — three banks it has nothing to do with.
const NAME_STOPWORDS = new Set([
  "bank", "bankasi", "bankası", "bankas", "banka", "katilim", "katılım",
  "yatirim", "yatırım", "finans", "finansman", "as", "aş", "a", "ş", "ve",
  "turkiye", "türkiye", "t", "anonim", "sirketi", "şirketi",
]);

/** The identifying tokens of a name — what is left once the boilerplate goes. */
function core(name: string): string[] {
  return fold(name)
    .split(" ")
    .filter((w) => w.length > 1 && !NAME_STOPWORDS.has(w));
}

/**
 * Licensing decisions, matched against the bank universe.
 *
 * The register is a LEAD INDICATOR: it named Enpara, Colendi and Ziraat Dinamik
 * 491–568 days before we onboarded them by hand. Crucially the match works on
 * an institution we have never seen — an *unmatched* name is the signal, so no
 * alias file needs updating first.
 *
 * Two states, not one. `licensed ∧ ticker ∉ banks` alone would false-alarm on
 * FUPS Bank, which is absent deliberately (licensed Oct-2024, zero reports
 * filed). The caller separates "covered" from "not covered" and says which.
 */
export function licences(lags: DecisionLagRow[], banks: { ticker: string; name: string }[]): LicenceRow[] {
  const index = banks
    .map((b) => ({ ...b, core: core(b.name) }))
    .filter((b) => b.core.length > 0);

  return lags
    .filter((d) => LICENCE_RE.test(d.subject))
    .map((decision) => {
      const institution = institutionOf(decision.subject);
      const key = core(institution);

      // Every identifying token of the bank must appear in the institution's
      // name. Where several banks qualify ("Ziraat" ⊂ "Ziraat Dinamik"), the
      // most specific wins — otherwise Ziraat Bankası would claim Ziraat
      // Dinamik's licence.
      const hit =
        key.length > 0
          ? index
              .filter((b) => b.core.every((w) => key.includes(w)))
              .sort((a, b) => b.core.length - a.core.length)[0]
          : undefined;

      return { decision, institution, ticker: hit?.ticker ?? null };
    })
    .sort((a, b) => b.decision.lagDays - a.decision.lagDays);
}

// ─────────────────────────────────────────────────────────── queries

/**
 * TCMB + BDDK with bodies — the instruments themselves.
 *
 * Fetched PER SOURCE, deliberately. A flat `ORDER BY published_at DESC LIMIT n`
 * looks equivalent and is not: BDDK dumped 29 board decisions into a two-week
 * window in March 2026, and that batch crowds TCMB out of the window — which
 * silently truncated the rate path from 48 decisions to 38 and lost five years
 * of the cycle. The composition of the window must not depend on how the
 * regulator happens to batch its publishing.
 */
export async function regulationFeed(tcmbLimit = 300, bddkLimit = 260): Promise<NewsItem[]> {
  const cols = `source, external_id, published_at, ticker, category, title, summary, url, language, body_text`;
  const rows = await cachedAll<NewsItem>(
    `SELECT * FROM (SELECT ${cols} FROM news_items WHERE source = 'tcmb' ORDER BY published_at DESC LIMIT ?)
     UNION ALL
     SELECT * FROM (SELECT ${cols} FROM news_items WHERE source = 'bddk' ORDER BY published_at DESC LIMIT ?)`,
    [tcmbLimit, bddkLimit],
  );
  return rows.sort((a, b) => b.published_at.localeCompare(a.published_at));
}

/**
 * The policy rate as an independent series. The boldest figure on the page does
 * not rest on one regex: EVDS is the value, the press release is the citation,
 * and the two are reconciled (they agree at 37%).
 */
export async function policyRateFromEvds(): Promise<{ date: string; value: number } | null> {
  const rows = await cachedAll<{ period_date: string; value: number }>(
    `SELECT period_date, value
       FROM evds_series
      WHERE code = 'TP.PY.P02.1H' AND value IS NOT NULL
      ORDER BY period_date DESC
      LIMIT 1`,
  );
  const r = rows[0];
  return r ? { date: r.period_date.slice(0, 10), value: r.value } : null;
}

export async function bankNames(): Promise<{ ticker: string; name: string }[]> {
  return cachedAll<{ ticker: string; name: string }>(`SELECT ticker, name FROM banks`);
}
