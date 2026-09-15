import tr from "./tr.json";
import { formatDateLabel, formatUnitLabel } from "./format";

/**
 * Normalized lookup table. The runtime key is `value.replace(/\s+/g," ").trim()`,
 * so a catalogue entry whose SOURCE key carries leading/trailing whitespace
 * (`"As of {0}: … nominal, "`) could never be found: `Object.hasOwn` compares the
 * trimmed key against the raw spaced key and fell through to English. Normalize
 * the key here and, for those same entries, trim the translated value of its
 * mirrored surrounding whitespace — the space is put back from the source
 * string's own `start`/`end`, so "sektör … kârlı" style headlines actually
 * resolve in Turkish. Entries whose source has no surrounding whitespace keep
 * their value verbatim (some translations deliberately open with a space).
 */
const dictionary: ReadonlyMap<string, string> = new Map(
  Object.entries(tr).map(([source, translated]) => {
    const key = source.replace(/\s+/g, " ").trim();
    const value = source === source.trim()
      ? translated
      : translated.replace(/^\s+|\s+$/g, "");
    return [key, value];
  }),
);
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
    const translated = locale === "tr" ? dictionary.get(key) : undefined;
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
