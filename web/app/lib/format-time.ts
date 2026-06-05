/** Compact relative-time formatting shared by admin server + client components. */

export function relativeFromHours(h: number | null | undefined): string {
  if (h == null || Number.isNaN(h)) return "—";
  if (h < 0) return "just now";
  if (h < 1) return `${Math.max(1, Math.round(h * 60))}m ago`;
  if (h < 48) return `${Math.round(h)}h ago`;
  return `${Math.round(h / 24)}d ago`;
}

export function hoursSinceIso(ts: string | null | undefined): number | null {
  if (!ts) return null;
  const norm = ts.includes("T") ? ts : ts.replace(" ", "T");
  const hasTz = /[zZ]$|[+-]\d\d:?\d\d$/.test(norm);
  const ms = Date.parse(hasTz ? norm : `${norm}Z`);
  if (Number.isNaN(ms)) return null;
  return (Date.now() - ms) / 3_600_000;
}

export function relativeFromIso(ts: string | null | undefined): string {
  return relativeFromHours(hoursSinceIso(ts));
}
