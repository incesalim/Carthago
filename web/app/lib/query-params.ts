/** App Router query values are arrays when a key occurs more than once. */
export type QueryValue = string | string[] | undefined;

/** Use the first occurrence, matching URLSearchParams.get. */
export function firstQueryValue(value: QueryValue): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

/** A URL cannot introduce unsupported control states. */
export function queryChoice<T extends string>(value: QueryValue, choices: readonly T[], fallback: T): T {
  const first = firstQueryValue(value);
  return choices.find((choice) => choice === first) ?? fallback;
}
