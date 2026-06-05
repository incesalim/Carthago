/**
 * BIST ticker → friendly bank name. Shared by /banks (index) and
 * /banks/[ticker] (drill-down). Sourced from
 * data/banks/bddk_bank_list.json (committed config) — when adding a
 * new bank to the audit pipeline, mirror the name here.
 */

export const BANK_NAMES: Record<string, string> = {
  AKBNK: "Akbank",
  AKTIF: "Aktif Yatırım Bankası",
  ALBRK: "Albaraka Türk",
  ALNTF: "Alternatifbank",
  ANADOLU: "Anadolubank",
  ATBANK: "Arap Türk Bankası",
  BURGAN: "Burgan Bank",
  DENIZ: "Denizbank",
  EMLAK: "Emlak Katılım",
  EXIM: "Türk Eximbank",
  FIBA: "Fibabanka",
  GARAN: "Garanti BBVA",
  HALKB: "Halkbank",
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
  TEB: "TEB",
  TFKB: "Türkiye Finans",
  TSKB: "TSKB",
  VAKBN: "VakıfBank",
  VAKIFK: "Vakıf Katılım",
  YKBNK: "Yapı Kredi",
  ZIRAAT: "Ziraat Bankası",
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
 *   • Foreign-OWNED deposit banks are Foreign, even though they're everyday
 *     "private" names: GARAN (BBVA), DENIZ (Emirates NBD), QNBFB (Qatar),
 *     TEB (BNP Paribas), BURGAN (Kuwait), ALNTF (Qatar CB), ODEA (Bank Audi),
 *     ATBANK (Libyan Foreign Bank).
 *   • İş Bankası (ISCTR) is Private — the only State deposit banks are Ziraat,
 *     Halkbank, VakıfBank.
 *   • Participation / Dev&Inv are their own groups regardless of owner, so
 *     state-owned Ziraat Katılım / Vakıf Katılım / Emlak Katılım / Eximbank /
 *     Kalkınma sit there, not under State.
 */
export const BANK_TYPE_BY_TICKER: Record<string, string> = {
  // State deposit (Kamu)
  ZIRAAT: "10006", HALKB: "10006", VAKBN: "10006",
  // Private domestic deposit (Özel)
  AKBNK: "10005", ISCTR: "10005", YKBNK: "10005",
  SKBNK: "10005", ANADOLU: "10005", FIBA: "10005",
  // Foreign-owned deposit (Yabancı)
  GARAN: "10007", DENIZ: "10007", QNBFB: "10007", TEB: "10007",
  BURGAN: "10007", ALNTF: "10007", ODEA: "10007", ATBANK: "10007",
  HSBC: "10007", ING: "10007", ICBCT: "10007",
  // Participation (Katılım)
  ALBRK: "10003", KUVEYT: "10003", TFKB: "10003",
  EMLAK: "10003", VAKIFK: "10003", ZIRAATK: "10003",
  // Development & investment (Kalkınma ve Yatırım)
  TSKB: "10004", EXIM: "10004", KLNMA: "10004",
  AKTIF: "10004", PASHA: "10004",
};

export function bankTypeCode(ticker: string): string | undefined {
  return BANK_TYPE_BY_TICKER[ticker.toUpperCase()];
}
