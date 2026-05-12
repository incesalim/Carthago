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
