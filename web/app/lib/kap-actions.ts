/**
 * kap-actions — what banks DID, read out of the KAP filing stream.
 *
 * /disclosures showed the KAP feed reverse-chronologically; 27% of it is
 * coupon-payment plumbing and company-information boilerplate. This module
 * classifies each filing by the ACT it records — a debt issue, a capital move,
 * a rating action, a portfolio sale — so /actions can lead with what happened
 * instead of what was filed most recently.
 *
 * The classifier is DETERMINISTIC: a fixed ruleset over the KAP form type
 * (`title`) refined by the disclosure subject (`summary`). No model sets a
 * category, matching DESIGN.md's automation-honesty rule and the prose.ts
 * "compiled, not written" contract. It fails SAFE: only provably-mechanical
 * filings are suppressed as `routine` (an allow-list); anything unrecognised
 * lands in the visible `material` bucket, never silently dropped. So a KAP form
 * type we have never seen shows up on the page rather than vanishing.
 *
 * Automation: news_items is refreshed daily by refresh-news-daily.yml
 * (sync_news.py) — this module re-derives every figure from those rows at
 * request time, so the page needs no new cron, table or column.
 *
 * The honest limit (printed on the page): KAP carries structured amount / ISIN /
 * maturity / coupon fields on the filing's detail form, but we hold only the
 * title + summary line (news_items.body_text is empty for KAP). So this counts
 * acts; it does not measure them.
 */
import { cachedAll } from "./db";

export type ActCategory =
  | "funding" // wholesale funding & capital instruments (bonds, sub-debt, syndication, DPR)
  | "capital" // shareholder & capital events (rights issue, dividend, buyback, ceilings)
  | "rating" // credit-rating actions on the bank itself
  | "results" // financial-report filings + financial calendar
  | "material" // other genuine events (NPL sales, litigation, business development) + residual
  | "governance" // board / executive / committee / articles / sustainability / corp-gov
  | "routine"; // coupons, redemptions, dematerialisation, company-info forms, ceiling admin, 3rd-party IPO intermediation

export interface KapRow {
  ticker: string;
  published_at: string;
  title: string;
  summary: string | null;
  url: string;
  external_id: string;
}

export interface ClassifiedRow extends KapRow {
  category: ActCategory;
  /** Deterministic English gloss of the act; falls back to the Turkish subject. */
  gloss: string;
  /** Funding only: to foreign markets vs domestic. */
  offshore?: boolean;
  /** Rating only: the agency named in the filing. */
  agency?: string | null;
}

// ─────────────────────────────────────────────────────────── matching ──

/** Turkish-aware fold for keyword matching (lower-case + strip diacritics). */
export function foldTr(s: string | null | undefined): string {
  let x = (s ?? "").toLowerCase().replace(/i̇/g, "i");
  for (const [a, b] of [
    ["ı", "i"],
    ["ş", "s"],
    ["ç", "c"],
    ["ğ", "g"],
    ["ü", "u"],
    ["ö", "o"],
  ] as const) {
    x = x.split(a).join(b);
  }
  return x;
}

const RE = {
  thirdPartyIpo: /fiyat tespit rapor|halka arz sonuc|halka arz islemlerinde|analist rapor/,
  results: /finansal rapor|sorumluluk beyani|finansal takvim/,
  ratingForm: /kredi derecelendirmesi/,
  ratingLike: /derecelendirme/,
  agency: /\b(fitch|moody|jcr|dbrs)\b/,
  ratingWord: /not|rating|derecelendir/,
  dividendForm: /kar pay/,
  capitalForm: /sermaye artirimi|sermaye azalt|bedelli|bedelsiz|kayitli sermaye tavani/,
  buyback: /geri al/,
  coupon: /kupon|itfa|anapara/,
  issuanceForm: /izahname|ihrac belgesi|tasarruf sahiplerine satis|yatirim kurulusu varant/,
  bondForm: /pay disinda sermaye piyasasi araci/,
  issuanceWord:
    /tahvil ihra|borclanma araci|finansman bonosu|gmtn|katki sermaye|sermaye benzeri|nitelikli yatirimci|yurtdisi tahvil|surdurulebilir borclanma|ihrac tavani/,
  wholesaleMoney:
    /sendikasyon|sekuritizasyon|future flow|gelecekteki nakit akis|havale akim|kredi anlasmasi imzalan|yabanci kaynak temini|imar ve kalkinma|dunya bankasi|world bank|ibrd|\b(afd|jbic|ifc|ebrd|eib|kfw|dfc)\b/,
  portfolioSale: /takipteki kredi|tahsili gecikmis alacak|alacak.*sati|portfoy.*satis/,
  legal: /dava|ofac|ceza|sorusturma|el konul|idari para cezas|tasfiye/,
  governanceForm:
    /kurumsal yonetim|yonetim kurulu|genel kurul|komite|surdurulebilirlik|esas sozlesme|faaliyet raporu|bagimsiz denetim kurulusu/,
  governanceSubject:
    /atama|ayrilma|istifa|degisikligi|genel mudur|yonetim kurulu uye|icra kurulu|gorev paylasim|yatirimci iliskileri/,
  companyForm: /sirket genel bilgi formu/,
  admin: /kaydilesti|kupon|itfa|anapara|bilgi guncelleme/,
};

/**
 * The act a KAP filing records. Priority order matters — the first rule that
 * matches wins, most-specific first. Validated against the full live feed
 * (kap-actions.test.ts locks the buckets).
 */
export function classifyKap(title: string, summary: string | null): ActCategory {
  const T = foldTr(title);
  const S = foldTr(summary);
  const B = `${T} || ${S}`;
  const coupon = RE.coupon.test(S);

  // Third-party IPO intermediation (the bank is underwriter, not issuer).
  if (RE.thirdPartyIpo.test(T)) return "routine";

  if (RE.results.test(T)) return "results";

  // Credit rating — form type is authoritative; corporate-governance compliance
  // ratings ("Kurumsal Yönetim İlkelerine Uyum Derecelendirmesi") are NOT this.
  if (RE.ratingForm.test(T)) return "rating";
  if (RE.ratingLike.test(T) && !T.includes("kurumsal yonetim")) return "rating";
  if (RE.agency.test(S) && RE.ratingWord.test(S)) return "rating";

  // Capital & shareholder events.
  if (RE.dividendForm.test(T)) return "capital";
  if (RE.capitalForm.test(T)) return "capital";
  if (RE.buyback.test(S) && S.includes("pay")) return "capital";

  // Wholesale funding / issuance / money raised.
  if (RE.issuanceForm.test(T)) return "funding";
  if (RE.bondForm.test(T)) return coupon ? "routine" : "funding";
  if (RE.issuanceWord.test(B) && !coupon) return "funding";
  if (RE.wholesaleMoney.test(S)) return "funding";

  // Other genuinely material events.
  if (RE.portfolioSale.test(S)) return "material";
  if (RE.legal.test(B)) return "material";

  // Governance / administration.
  if (RE.governanceForm.test(T)) return "governance";
  if (RE.governanceSubject.test(S)) return "governance";

  // Provably mechanical → suppressed.
  if (RE.companyForm.test(T)) return "routine";
  if (RE.admin.test(S)) return "routine";

  // Residual: keep it VISIBLE rather than guess. A new, unrecognised — and
  // possibly important — filing surfaces here instead of being suppressed.
  return "material";
}

// ─────────────────────────────────────────────────────── enrichment ──

const OFFSHORE = /yurtdisi|yurt disi|turkiye disinda|gmtn|surdurulebilir|eurobond|foreign/;

/** Funding filing: raised abroad vs at home. */
export function isOffshore(summary: string | null): boolean {
  return OFFSHORE.test(foldTr(summary));
}

const AGENCIES: [RegExp, string][] = [
  [/moody/, "Moody's"],
  [/fitch/, "Fitch"],
  [/jcr/, "JCR Eurasia"],
  [/dbrs/, "DBRS"],
  [/s&p|standard & poor/, "S&P"],
];

/** The rating agency named in a filing, if any. */
export function ratingAgency(summary: string | null, title: string): string | null {
  const s = foldTr(`${summary} ${title}`);
  for (const [re, name] of AGENCIES) if (re.test(s)) return name;
  return null;
}

/**
 * A deterministic English gloss for a KAP act, so the page isn't a wall of
 * Turkish. Keyword → phrase, most-specific first; falls back to the original
 * Turkish subject line (never invents meaning). The Turkish original is shown
 * alongside on the page so the gloss is checkable.
 */
export function glossKap(row: KapRow, category: ActCategory): string {
  const s = foldTr(row.summary);
  const cmb = /spk onay/.test(s) ? " — CMB approval" : /tamamlan/.test(s) ? " — completed" : "";

  if (category === "funding") {
    if (/gmtn/.test(s) && /surdurulebilir/.test(s)) return `Sustainable bond abroad, GMTN programme${cmb}`;
    if (/gmtn/.test(s)) return `Debt issue abroad, GMTN programme${cmb}`;
    if (/katki sermaye|sermaye benzeri/.test(s)) return `Tier-2 subordinated debt issue${cmb}`;
    if (/sendikasyon/.test(s)) return "Syndicated loan";
    if (/future flow|gelecekteki nakit|havale akim/.test(s)) return "Diversified payment-rights (future-flow) deal";
    if (/yabanci kaynak temini/.test(s)) return "Foreign funding secured";
    if (/imar ve kalkinma|dunya bankasi|world bank|ibrd|afd|jbic|ifc|ebrd|eib|kfw|dfc/.test(s))
      return "Development-finance credit line";
    if (/finansman bonosu/.test(s)) return `Commercial paper${/nitelikli yatirimci/.test(s) ? " to qualified investors" : ""}${cmb}`;
    if (/yurtdisi|yurt disi|turkiye disinda|foreign/.test(s)) return `Bond issue to foreign markets${cmb}`;
    if (/nitelikli yatirimci/.test(s)) return `Bond issue to qualified investors${cmb}`;
    if (/tahvil/.test(s)) return `Bond issue${cmb}`;
    if (/ihrac tavani/.test(s)) return "Issuance-ceiling registration";
    return "Debt / capital-markets instrument";
  }
  if (category === "capital") {
    if (/geri al/.test(s)) return "Share buyback";
    if (/bedelli/.test(s)) return `Rights (cash) capital increase${cmb}`;
    if (/bedelsiz/.test(s)) return "Bonus (scrip) capital increase";
    if (/kar pay|kar dagit/.test(s)) return "Dividend distribution";
    if (/kayitli sermaye tavani|esas sozlesme/.test(s)) return "Registered-capital ceiling change";
    return "Capital / shareholder event";
  }
  if (category === "rating") {
    const a = ratingAgency(row.summary, row.title);
    return a ? `${a} rating action` : "Credit-rating action";
  }
  if (category === "material") {
    if (/takipteki kredi|tahsili gecikmis/.test(s)) return "NPL / overdue-receivable portfolio sale";
    if (/ofac|ceza|dava|sorusturma/.test(s)) return "Litigation / legal proceeding";
    if (/kripto|saklama/.test(s)) return "Business development";
    if (/bagli ortaklik|istirak/.test(s)) return "Subsidiary / affiliate action";
  }
  if (category === "governance") {
    if (/atama/.test(s)) return "Senior appointment";
    if (/ayrilma|istifa/.test(s)) return "Senior departure";
    if (/uye|yonetim kurulu/.test(s)) return "Board change";
    if (/komite/.test(s)) return "Board committee update";
    if (/surdurulebilirlik/.test(s)) return "Sustainability report";
    if (/esas sozlesme/.test(s)) return "Articles of association";
  }
  // Fall back to the Turkish subject (trimmed), or the form type if no subject.
  const raw = (row.summary ?? row.title ?? "").trim();
  return raw.length > 90 ? `${raw.slice(0, 88)}…` : raw || "—";
}

// ─────────────────────────────────────────────────────────── query ──

const CATS: ActCategory[] = [
  "funding",
  "capital",
  "rating",
  "results",
  "material",
  "governance",
  "routine",
];

export interface FundingByBank {
  ticker: string;
  n: number;
  offshore: number;
}

export interface ActionsData {
  /** The record window the feed actually holds (min/max KAP publish date). */
  window: { first: string | null; last: string | null; days: number };
  total: number;
  /** Distinct banks that filed anything on KAP in the window. */
  filerUniverse: number;
  counts: Record<ActCategory, number>;
  bankCounts: Record<ActCategory, number>;
  funding: {
    total: number;
    offshore: number;
    funders: number;
    byBank: FundingByBank[];
    rows: ClassifiedRow[];
  };
  capital: ClassifiedRow[];
  rating: ClassifiedRow[];
  material: ClassifiedRow[];
  governance: ClassifiedRow[];
  routineCount: number;
  routineSample: ClassifiedRow[];
  /** Set when a ?ticker= filter is applied. */
  ticker: string | null;
}

async function fetchKap(limit = 1200, ticker?: string): Promise<KapRow[]> {
  if (ticker) {
    return cachedAll<KapRow>(
      `SELECT ticker, published_at, title, summary, url, external_id
         FROM news_items
        WHERE source = 'kap' AND ticker = ?
        ORDER BY published_at DESC
        LIMIT ?`,
      [ticker.toUpperCase(), limit],
    );
  }
  return cachedAll<KapRow>(
    `SELECT ticker, published_at, title, summary, url, external_id
       FROM news_items
      WHERE source = 'kap'
      ORDER BY published_at DESC
      LIMIT ?`,
    [limit],
  );
}

const DAY_MS = 86_400_000;

/** Classify + aggregate the KAP feed into the /actions view. */
export async function bankActions(opts?: { ticker?: string }): Promise<ActionsData> {
  const ticker = opts?.ticker?.toUpperCase() || null;
  const raw = await fetchKap(1200, ticker ?? undefined);

  const rows: ClassifiedRow[] = raw.map((r) => {
    const category = classifyKap(r.title, r.summary);
    const enriched: ClassifiedRow = { ...r, category, gloss: glossKap(r, category) };
    if (category === "funding") enriched.offshore = isOffshore(r.summary);
    if (category === "rating") enriched.agency = ratingAgency(r.summary, r.title);
    return enriched;
  });

  const counts = Object.fromEntries(CATS.map((c) => [c, 0])) as Record<ActCategory, number>;
  const bankSets = Object.fromEntries(CATS.map((c) => [c, new Set<string>()])) as Record<
    ActCategory,
    Set<string>
  >;
  for (const r of rows) {
    counts[r.category]++;
    bankSets[r.category].add(r.ticker);
  }
  const bankCounts = Object.fromEntries(
    CATS.map((c) => [c, bankSets[c].size]),
  ) as Record<ActCategory, number>;

  // Window from the data, not wall-clock: a stale feed reads as stale.
  const dates = rows.map((r) => r.published_at).filter(Boolean).sort();
  const first = dates[0] ?? null;
  const last = dates[dates.length - 1] ?? null;
  const days =
    first && last ? Math.max(1, Math.round((Date.parse(last) - Date.parse(first)) / DAY_MS)) : 0;

  const fundingRows = rows.filter((r) => r.category === "funding");
  const byBankMap = new Map<string, FundingByBank>();
  for (const r of fundingRows) {
    const e = byBankMap.get(r.ticker) ?? { ticker: r.ticker, n: 0, offshore: 0 };
    e.n++;
    if (r.offshore) e.offshore++;
    byBankMap.set(r.ticker, e);
  }
  const byBank = [...byBankMap.values()].sort((a, b) => b.n - a.n);

  const routineRows = rows.filter((r) => r.category === "routine");

  return {
    window: { first, last, days },
    total: rows.length,
    filerUniverse: new Set(rows.map((r) => r.ticker)).size,
    counts,
    bankCounts,
    funding: {
      total: fundingRows.length,
      offshore: fundingRows.filter((r) => r.offshore).length,
      funders: byBank.length,
      byBank,
      rows: fundingRows,
    },
    capital: rows.filter((r) => r.category === "capital"),
    rating: rows.filter((r) => r.category === "rating"),
    material: rows.filter((r) => r.category === "material"),
    governance: rows.filter((r) => r.category === "governance"),
    routineCount: routineRows.length,
    routineSample: routineRows.slice(0, 24),
    ticker,
  };
}
