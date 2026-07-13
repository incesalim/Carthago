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
import type { Briefing, NewsItem } from "./news";

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
  /** The table row: "Demand deposits and deposits with maturities up to 1 month". */
  label: string;
  /**
   * The table's HEADER cell — "Foreign currency deposits/participation funds".
   * Without it the row label is dangerously incomplete: "demand deposits …up to
   * 1 month" reads as a LIRA ratio, and it is not one.
   */
  group: string;
  prev: number;
  next: number;
}

/** "Foreign currency deposits…" + "…up to 1 month" → "FX deposits · ≤1 month". */
export function reserveCellLabel(c: ReserveChange): string {
  const prefix = /foreign currency|\bfx\b/i.test(c.group)
    ? "FX deposits"
    : /turkish lira|\btl\b/i.test(c.group)
      ? "TL deposits"
      : c.group.length > 0 && c.group.length <= 24
        ? c.group
        : "Reserve ratio";

  const m = /up to (\d+)\s*(month|year)/i.exec(c.label);
  const suffix = m
    ? `≤${m[1]} ${m[2]}`
    : /longer/i.test(c.label)
      ? "longer maturities"
      : c.label.length > 22
        ? `${c.label.slice(0, 20)}…`
        : c.label;

  return `${prefix} · ${suffix}`;
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
export function classifyInstrument(
  item: Pick<NewsItem, "source" | "title"> & { body_text?: string | null },
): InstrumentKind {
  const t = item.title;
  if (RATE_RE.test(t)) return "rate";

  // The MPC Summary reads like comms — "a summary of a decision already made" —
  // and was classified as such. But it is 8,000 characters, and it is the ONLY
  // document that states the 8-week loan growth limits in machine-readable prose:
  // the macroprudential release that sets them ships no table at all. A document
  // carrying binding parameters no other release exposes is not comms.
  if (/summary of the monetary policy committee/i.test(t) && parseGrowthCaps(item.body_text).length > 0) {
    return "rule";
  }

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
    const headerCells = lines[0]
      .trim()
      .replace(/^\||\|$/g, "")
      .split("|")
      .map((c) => c.trim());
    const header = lines[0].toLowerCase();
    if (!header.includes("previous") || !header.includes("new")) continue;
    const group = headerCells[0] ?? "";
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
      out.push({ label: cells[0], group, prev, next });
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

/** Not every licence is the same licence, and the page must not say it is. */
export type LicenceKind = "operating" | "establishment" | "revocation";

export interface LicenceRow {
  decision: DecisionLagRow;
  /** The institution named in the decision. */
  institution: string;
  kind: LicenceKind;
  /** Ticker if we cover it; null if we do not. */
  ticker: string | null;
}

const LICENCE_RE = /faaliyet izni|kurulmasına izin|kuruluş izni/i;
const REVOKE_RE = /iptal/i;
const ESTABLISH_RE = /kurulmasına izin|kuruluş izni/i;

/**
 * BDDK licenses banks, leasing companies, factoring houses, asset managers,
 * financing companies and e-money issuers from the SAME numbered decision
 * sequence. A "licensed institution missing from `banks`" flag that does not
 * filter to banks therefore fires on Real Varlık Yönetim (an asset manager) and
 * Pratik Finansman (a financing company) — institutions that will never be in
 * the bank universe, because they are not banks. The flag becomes noise, which
 * is worse than no flag.
 */
const BANK_RE = /\bbanka|\bbank\b|katılım|katilim/i;
const NON_BANK_RE =
  /varlık yönetim|finansman|faktoring|finansal kiralama|elektronik para|ödeme hizmet|ödeme kuruluş|sigorta|aracı kurum|portföy|leasing/i;

/** Is the institution named in this decision a BANK (not a leasing/e-money/AMC)? */
export function isBankInstitution(name: string): boolean {
  return BANK_RE.test(name) && !NON_BANK_RE.test(name);
}

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
    .filter((d) => isBankInstitution(institutionOf(d.subject)))
    .map((decision) => {
      const institution = institutionOf(decision.subject);
      const kind: LicenceKind = REVOKE_RE.test(decision.subject)
        ? "revocation"
        : ESTABLISH_RE.test(decision.subject)
          ? "establishment"
          : "operating";
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

      return { decision, institution, kind, ticker: hit?.ticker ?? null };
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

// ─────────────────────────────────────────────────────────── loan growth caps

export interface GrowthCap {
  label: string;
  prev: number;
  next: number;
}

export interface GrowthCaps {
  caps: GrowthCap[];
  decidedAt: string;
  url: string;
  title: string;
}

/**
 * The 8-week loan growth limits.
 *
 * These were long treated here as unreadable: the macroprudential release that
 * SETS them ships no table (we hold 342 characters of the 23 May one). But the
 * MPC SUMMARY recaps them, in a document we already store in full, in one
 * regular sentence:
 *
 *   "growth limits imposed for eight-week periods were reduced from 4% to 3% in
 *    general purpose and vehicle loans extended to consumers, from 2% to 1% in
 *    overdraft account limits extended to consumers, from 5% to 4.5% in Turkish
 *    lira loans extended to SMEs, and from 3% to 2% in Turkish lira loans
 *    extended to non-SME enterprises."
 *
 * One regex gets all four. That summary is 8,000 characters and was classified
 * as "comms about a decision already made" — which is exactly what hid the caps.
 */
const CAP_CLAUSE_RE = /from\s+([\d.]+)%\s+to\s+([\d.]+)%\s+in\s+([^,.;]+)/gi;

/** "general purpose and vehicle loans extended to consumers" → "General-purpose & vehicle" */
function capLabel(raw: string): string {
  const s = raw.toLowerCase();
  if (/non-sme/.test(s)) return "TL loans to non-SMEs";
  if (/\bsme/.test(s)) return "TL loans to SMEs";
  if (/overdraft/.test(s)) return "Consumer overdraft";
  if (/general purpose/.test(s) && /vehicle/.test(s)) return "General-purpose & vehicle";
  if (/foreign currency/.test(s)) return "FX loans";
  const t = raw.trim().replace(/\s+/g, " ");
  return t.charAt(0).toUpperCase() + t.slice(1, 40);
}

export function parseGrowthCaps(body: string | null | undefined): GrowthCap[] {
  if (!body) return [];

  // Bound the search to the PARAGRAPH that announces the limits. An 8,000-char
  // summary is full of other "from x% to y%" prose (inflation, reserves,
  // commissions) and any of it would otherwise be read as a cap.
  //
  // Do NOT bound with [^.] to "stay in the sentence" — a cap of 4.5% contains a
  // full stop, so the match dies at the decimal and silently returns two caps
  // instead of four. That is the same trap that ate a third of the policy-rate
  // path; it is pinned by a test below.
  const at = body.search(/growth limits/i);
  if (at < 0) return [];
  const end = body.indexOf("\n\n", at);
  const para = body.slice(at, end > 0 ? end : at + 700);
  if (!/(?:reduced|increased|set|revised|introduced)/i.test(para)) return [];

  const out: GrowthCap[] = [];
  for (const c of para.matchAll(CAP_CLAUSE_RE)) {
    const prev = Number(c[1]);
    const next = Number(c[2]);
    if (!Number.isFinite(prev) || !Number.isFinite(next)) continue;
    out.push({ label: capLabel(c[3]), prev, next });
  }
  return out;
}

/** The caps as stated by the most recent release that states them. */
export function deriveGrowthCaps(items: NewsItem[]): GrowthCaps | null {
  const sorted = [...items].sort((a, b) => b.published_at.localeCompare(a.published_at));
  for (const it of sorted) {
    const caps = parseGrowthCaps(it.body_text);
    if (caps.length >= 2) {
      return { caps, decidedAt: it.published_at.slice(0, 10), url: it.url, title: it.title };
    }
  }
  return null;
}

// ─────────────────────────────────────────────────────────── the changelog

export interface ChangeRow {
  category: string;
  text: string;
  /** Publication date of the instrument the claim cites. */
  date: string;
  url: string;
  title: string;
  /** The compiled parameter this claim agrees with, if any. */
  agrees: string | null;
  /** What the instrument actually says, where the claim conflicts with it. */
  conflicts: string | null;
}

/**
 * Cross-checks. Where the model states a figure the parser has ALSO read out of
 * the instrument, the two are compared: agreement earns a ✓, a conflict earns a
 * ✗ that prints what the instrument says.
 *
 * The conflict is real and current. The briefing reports the 4.5% cap as
 * applying to "commercial loans (excluding overdraft)"; the instrument says
 * "Turkish lira loans extended to SMEs" — a narrower set — and states a separate
 * 3%→2% cap for non-SMEs that the briefing omits altogether.
 */
function buildChecks(
  corridor: Corridor | null,
  reserves: ReserveState | null,
  caps: GrowthCaps | null,
): { re: RegExp; agrees?: string; conflicts?: string }[] {
  const out: { re: RegExp; agrees?: string; conflicts?: string }[] = [];
  if (corridor) {
    out.push({
      re: new RegExp(`policy rate[^.]*?\\b${corridor.policy}\\b`, "i"),
      agrees: `policy rate ${corridor.policy}%`,
    });
    if (corridor.lending != null) {
      out.push({
        re: new RegExp(`overnight lending[^.]*?\\b${corridor.lending}\\b`, "i"),
        agrees: `O/N lending ${corridor.lending}%`,
      });
    }
    if (corridor.borrowing != null) {
      out.push({
        re: new RegExp(`overnight borrowing[^.]*?${corridor.borrowing}`, "i"),
        agrees: `O/N borrowing ${corridor.borrowing}%`,
      });
    }
  }
  for (const c of reserves?.changes ?? []) {
    out.push({
      re: new RegExp(`${c.prev}%\\s*to\\s*${c.next}%`, "i"),
      agrees: `reserve ratio ${c.prev}→${c.next}%`,
    });
  }
  for (const t of reserves?.terminated ?? []) {
    out.push({
      re: /additional turkish lira reserve requirement[^.]*terminat/i,
      agrees: `${t.was}% add-on ended`,
    });
  }
  const sme = caps?.caps.find((c) => c.label === "TL loans to SMEs");
  if (sme) {
    out.push({
      re: /commercial loans \(excluding overdraft\)/i,
      conflicts: `instrument: TL loans to SMEs, ${sme.prev}% → ${sme.next}%`,
    });
  }
  return out;
}

/**
 * The briefing's claims, re-keyed on the date of the instrument each one cites.
 *
 * The briefing groups by BBVA-style section — a taxonomy. Useful for reference,
 * useless for the question a reader arrives with ("what changed since I last
 * looked?"). The bullets carry `source_ids`, the instruments carry dates, so the
 * same content sorts into a changelog.
 *
 * A claim that cites nothing is NOT published: an unsourced sentence from a model
 * is not something a reader can check.
 */
export function buildChangelog(
  briefing: Briefing | null,
  lookup: Map<string, { title: string; url: string; published_at: string }>,
  corridor: Corridor | null,
  reserves: ReserveState | null,
  caps: GrowthCaps | null,
): ChangeRow[] {
  if (!briefing) return [];
  const checks = buildChecks(corridor, reserves, caps);
  const rows: ChangeRow[] = [];

  for (const cat of briefing.categories) {
    for (const b of cat.bullets) {
      const hits = b.source_ids
        .map((id) => lookup.get(id))
        .filter((x): x is { title: string; url: string; published_at: string } => x != null);
      if (hits.length === 0) continue;
      const newest = hits.reduce((a, c) => (c.published_at > a.published_at ? c : a));

      let agrees: string | null = null;
      let conflicts: string | null = null;
      for (const c of checks) {
        if (!c.re.test(b.text)) continue;
        if (c.conflicts) {
          conflicts = c.conflicts;
          break;
        }
        if (c.agrees && !agrees) agrees = c.agrees;
      }

      rows.push({
        category: cat.name,
        text: b.text,
        date: newest.published_at.slice(0, 10),
        url: newest.url,
        title: newest.title,
        agrees: conflicts ? null : agrees,
        conflicts,
      });
    }
  }
  return rows.sort((a, b) => b.date.localeCompare(a.date));
}

// ─────────────────────────────────────────────────────────── reserves held

export interface RatioPoint {
  date: string;
  tl: number | null;
  fx: number | null;
}

/**
 * What banks actually hold against deposits — required reserves ÷ deposits, from
 * the weekly BDDK bulletin. The rule states a ratio; this is the ratio that
 * lands, after exemptions and maturity mix.
 *
 * Paired BY DATE, never by row offset: the weekly feed can omit a currency leg,
 * and a row-offset LAG would silently misalign the series.
 */
export async function reserveRatioSeries(): Promise<RatioPoint[]> {
  const rows = await cachedAll<{ period_date: string; currency: string; item_id: string; value: number }>(
    `SELECT period_date, currency, item_id, value
       FROM weekly_series
      WHERE bank_type_code = '10001'
        AND item_id IN ('5.0.4', '4.0.1')
        AND currency IN ('TL', 'FX')
        AND period_date >= '2022-01-01'
      ORDER BY period_date`,
  );
  const res = new Map<string, Map<string, number>>();
  const dep = new Map<string, Map<string, number>>();
  for (const r of rows) {
    const target = r.item_id === "5.0.4" ? res : dep;
    if (!target.has(r.period_date)) target.set(r.period_date, new Map());
    target.get(r.period_date)!.set(r.currency, r.value);
  }
  const out: RatioPoint[] = [];
  for (const [date, r] of [...res.entries()].sort()) {
    const d = dep.get(date);
    if (!d) continue;
    const ratio = (c: string) => {
      const rv = r.get(c);
      const dv = d.get(c);
      return rv != null && dv != null && dv > 0 ? (100 * rv) / dv : null;
    };
    out.push({ date: date.slice(0, 10), tl: ratio("TL"), fx: ratio("FX") });
  }
  return out;
}
