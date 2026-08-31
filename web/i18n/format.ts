import { intlLocale } from "./config";

/** Localize a standalone display unit, retaining every character of its number. */
export function formatUnitLabel(value: string, locale: string): string {
  if (locale !== "tr") return value;
  const match = /^([+−-]?[₺$]?[+−-]?[\d.,]+)\s*(trn|tn|bn|mn|pp)(\/yr\.?)?$/.exec(value);
  if (!match) return value;
  const units: Record<string, string> = { trn: "trilyon", tn: "trilyon", bn: "milyar", mn: "milyon", pp: "yüzde puan" };
  return `${match[1]} ${units[match[2]]}${match[3] ? "/yıl" : ""}`;
}

/** Format dates for display without changing the ISO keys used by queries/charts. */
export function formatDateLabel(value: string, locale: string): string {
  const iso = /^(\d{4})-(\d{2})(?:-(\d{2}))?$/.exec(value);
  if (iso) {
    const year = Number(iso[1]), month = Number(iso[2]), day = Number(iso[3] ?? 1);
    const date = new Date(Date.UTC(year, month - 1, day));
    if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return value;
    return new Intl.DateTimeFormat(intlLocale(locale), {
      year: "numeric", month: "short", ...(iso[3] ? {day: "numeric" as const} : {}), timeZone: "UTC",
    }).format(date);
  }
  if (locale !== "tr") return value;
  if (value.includes(" → ")) return value.split(" → ").map((part) => formatDateLabel(part, locale)).join(" → ");
  const quarter = /^(\d{4})-?Q([1-4])$/.exec(value);
  if (quarter) return `${quarter[1]} ${quarter[2]}.Ç`;
  const quarterFirst = /^Q([1-4]) (\d{4})$/.exec(value);
  if (quarterFirst) return `${quarterFirst[2]} ${quarterFirst[1]}.Ç`;
  const months: Record<string, string> = {
    Jan: "Oca", Feb: "Şub", Mar: "Mar", Apr: "Nis", May: "May", Jun: "Haz",
    Jul: "Tem", Aug: "Ağu", Sep: "Eyl", Oct: "Eki", Nov: "Kas", Dec: "Ara",
    January: "Ocak", February: "Şubat", March: "Mart", April: "Nisan", June: "Haziran",
    July: "Temmuz", August: "Ağustos", September: "Eylül", October: "Ekim", November: "Kasım", December: "Aralık",
  };
  const monthName = (s: string) => months[s[0].toUpperCase() + s.slice(1).toLowerCase()];
  const monthDay = /^([A-Za-z]+) (\d{1,2})(?:,? (\d{4}))?$/.exec(value);
  if (monthDay && monthName(monthDay[1])) return [monthDay[2], monthName(monthDay[1]), monthDay[3]].filter(Boolean).join(" ");
  const written = /^(?:(\d{1,2}) )?([A-Za-z]+)(?: (\d{4}))?$/.exec(value);
  if (!written || !monthName(written[2])) return value;
  return [written[1], monthName(written[2]), written[3]].filter(Boolean).join(" ");
}
