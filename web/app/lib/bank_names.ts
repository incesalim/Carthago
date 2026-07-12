/**
 * BIST ticker → friendly bank name. Shared by /banks (index) and
 * /banks/[ticker] (drill-down). Sourced from
 * data/banks/bddk_bank_list.json (committed config) — when adding a
 * new bank to the audit pipeline, mirror the name here.
 *
 * The in-D1 mirror of this map is the `banks` dimension table
 * (migration 0021_banks_dimension.sql) — the single source of truth for
 * cross-lane joins (ticker/bank_ticker/symbol) and for the text-to-SQL bot.
 * Keep the two in sync: adding a bank here means adding a seed row there.
 */

export const BANK_NAMES: Record<string, string> = {
  AKBNK: "Akbank",
  AKTIF: "Aktif Yatırım Bankası",
  ALBRK: "Albaraka Türk",
  ALNTF: "Alternatifbank",
  ANADOLU: "Anadolubank",
  ATBANK: "Arap Türk Bankası",
  BURGAN: "Burgan Bank",
  COLENDI: "Colendi Bank",
  DENIZ: "Denizbank",
  DUNYAK: "Dünya Katılım",
  EMLAK: "Emlak Katılım",
  ENPARA: "Enpara Bank",
  EXIM: "Türk Eximbank",
  FIBA: "Fibabanka",
  GARAN: "Garanti BBVA",
  HALKB: "Halkbank",
  HAYATK: "Hayat Finans",
  HSBC: "HSBC Türkiye",
  ICBCT: "ICBC Turkey",
  ING: "ING Türkiye",
  ISCTR: "İş Bankası",
  KLNMA: "Kalkınma ve Yatırım Bk.",
  KUVEYT: "Kuveyt Türk",
  ODEA: "Odea Bank",
  PASHA: "Pasha Yatırım",
  QNBFB: "QNB",
  SKBNK: "Şekerbank",
  TAKAS: "Takasbank",
  TEB: "TEB",
  TFKB: "Türkiye Finans",
  TOMK: "T.O.M. Katılım",
  TSKB: "TSKB",
  VAKBN: "VakıfBank",
  VAKIFK: "Vakıf Katılım",
  YKBNK: "Yapı Kredi",
  ZIRAAT: "Ziraat Bankası",
  ZIRAATD: "Ziraat Dinamik",
  ZIRAATK: "Ziraat Katılım",
};

export function bankDisplayName(ticker: string): string {
  return BANK_NAMES[ticker.toUpperCase()] ?? ticker;
}

/**
 * BDDK aggregate group per bank, as a `bank_type_code` (see metrics.ts
 * BANK_TYPE_LABELS): 10005 Private · 10006 State · 10007 Foreign ·
 * 10003 Participation · 10004 Dev & Inv.
 *
 * This follows BDDK's OWNERSHIP split — the one the sector aggregates / charts
 * use — NOT the colloquial "private = not-state" labelling in
 * data/banks/bddk_bank_list.json. Deliberate consequences so the per-bank tag
 * always agrees with the State/Private/Foreign lines on the sector charts
 * (both read these same five codes):
 *   • Foreign-OWNED deposit banks get the Foreign/Yabancı code (10007). They
 *     are still PRIVATE banks — just foreign capital — so the badge labels them
 *     "Private · Foreign" (BANK_TYPE_BADGE_LABELS): GARAN (BBVA),
 *     DENIZ (Emirates NBD), QNBFB (Qatar), TEB (BNP Paribas), BURGAN (Kuwait),
 *     ALNTF (Qatar CB), ODEA (Bank Audi), ATBANK (Libyan Foreign Bank).
 *   • İş Bankası (ISCTR) is domestic-private — the only State deposit banks
 *     are Ziraat, Halkbank, VakıfBank.
 *   • Participation / Dev&Inv are their own groups regardless of owner, so
 *     state-owned Ziraat Katılım / Vakıf Katılım / Emlak Katılım / Eximbank /
 *     Kalkınma sit there, not under State.
 */
export const BANK_TYPE_BY_TICKER: Record<string, string> = {
  // State deposit (Kamu)
  ZIRAAT: "10006", HALKB: "10006", VAKBN: "10006",
  ZIRAATD: "10006", // Ziraat Dinamik — state-owned digital deposit bank
  // Private domestic deposit (Özel)
  AKBNK: "10005", ISCTR: "10005", YKBNK: "10005",
  SKBNK: "10005", ANADOLU: "10005", FIBA: "10005",
  COLENDI: "10005", // Colendi — domestic-private digital deposit bank
  // Foreign-owned deposit (Yabancı)
  GARAN: "10007", DENIZ: "10007", QNBFB: "10007", TEB: "10007",
  BURGAN: "10007", ALNTF: "10007", ODEA: "10007", ATBANK: "10007",
  HSBC: "10007", ING: "10007", ICBCT: "10007",
  ENPARA: "10007", // Enpara — QNB (Qatar) owned digital deposit bank
  // Participation (Katılım)
  ALBRK: "10003", KUVEYT: "10003", TFKB: "10003",
  EMLAK: "10003", VAKIFK: "10003", ZIRAATK: "10003",
  DUNYAK: "10003", HAYATK: "10003", TOMK: "10003",
  // Development & investment (Kalkınma ve Yatırım)
  TSKB: "10004", EXIM: "10004", KLNMA: "10004",
  AKTIF: "10004", PASHA: "10004",
  TAKAS: "10004", // Takasbank — BDDK licenses the CCP/clearing bank here (peer-excluded)
};

/**
 * Display labels for the per-bank pill on /banks. BDDK's "Özel" means
 * DOMESTIC-private, so its separate "Yabancı/Foreign" group is still private —
 * just foreign capital. The labels make that explicit (both deposit-private
 * codes read "Private · …") while the codes stay distinct so each pill keeps
 * its own sector-chart colour.
 */
export const BANK_TYPE_BADGE_LABELS: Record<string, string> = {
  "10006": "State",
  "10005": "Private · Domestic",
  "10007": "Private · Foreign",
  "10003": "Participation",
  "10004": "Dev & Inv",
};

export function bankTypeCode(ticker: string): string | undefined {
  return BANK_TYPE_BY_TICKER[ticker.toUpperCase()];
}

/**
 * Banks carried in the data but EXCLUDED from peer comparison, ranking and
 * concentration stats (`/cross-bank` heatmap, market-share league, HHI).
 *
 * TAKAS (Takasbank) is Turkey's central securities-settlement / clearing / CCP
 * and custody institution — BDDK licenses it as a development-and-investment
 * bank, but it is not a lender. At 2026Q1 it reports **zero deposits**, customer
 * loans of ~2.5% of assets, and ~94% of the balance sheet in cash + placements
 * (member cash and collateral it merely holds), plus ~178bn TL of off-balance CCP
 * guarantees. Ranking it against commercial and participation banks would make
 * NIM / LDR / NPL / cost-of-risk meaningless (several divide by ~0) and would
 * plant it near the top of the asset-size league on custody balances it doesn't
 * own — distorting every peer rank and the sector HHI.
 *
 * It still gets its own `/banks/TAKAS` page, where balance sheet, capital and
 * liquidity ARE meaningful. Present the bank; don't pretend it's comparable.
 */
export const PEER_EXCLUDED_TICKERS: ReadonlySet<string> = new Set(["TAKAS"]);

export function isPeerExcluded(ticker: string): boolean {
  return PEER_EXCLUDED_TICKERS.has(ticker.toUpperCase());
}
