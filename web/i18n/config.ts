export const LOCALE_COOKIE = "carthago-locale";
export const LOCALES = ["tr", "en"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "tr";

export function isLocale(value: unknown): value is Locale {
  return value === "en" || value === "tr";
}

/** Turkish for every new visitor; an explicit saved preference takes priority. */
export function resolveLocale(cookie: unknown): Locale {
  return isLocale(cookie) ? cookie : DEFAULT_LOCALE;
}

export const intlLocale = (locale: string) => locale === "tr" ? "tr-TR" : "en-US";
