import tr from "./tr.json";
import { formatDateLabel, formatUnitLabel } from "./format";

const dictionary: Readonly<Record<string, string>> = tr;
export interface Text {
  <T>(value: T, values?: Readonly<Record<string, unknown>>): T;
  readonly locale: string;
}

/** Translate display text only. IDs, query keys and underlying data stay intact.
 * English is the source catalogue; unknown/source-provided text is preserved.
 * Never infer or modify a numerical value while translating a label.
 */
export function createText(locale: string): Text {
  const translate = <T>(value: T, values?: Readonly<Record<string, unknown>>): T => {
    if (typeof value !== "string") return value;
    const key = value.replace(/\s+/g, " ").trim();
    const translated = locale === "tr" && Object.hasOwn(dictionary, key) ? dictionary[key] : undefined;
    const start = value.match(/^\s*/)?.[0] ?? "";
    const end = value.match(/\s*$/)?.[0] ?? "";
    const template = translated === undefined
      ? locale === "tr" ? formatDateLabel(formatUnitLabel(value, locale), locale) : value
      : start + translated + end;
    if (!values) return template as T;
    // Explicit slots preserve signs, units and missing data. Never parse or
    // round financial figures while translating prose; React still escapes it.
    return template.replace(/\{(\d+)\}/g, (slot, id: string) =>
      Object.hasOwn(values, id) ? String(translate(values[id])) : slot,
    ) as T;
  };
  return Object.assign(translate, { locale });
}
