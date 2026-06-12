/**
 * Display formatting for KAP ownership values, shared by the interactive
 * ownership visualizations (OwnershipRadial, OwnershipNetwork). Mirrors the
 * conventions of OwnershipCard / SubsidiariesCard.
 */

const PCT = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function fmtPct(v: number | null | undefined): string {
  return v == null ? "—" : `${PCT.format(v)}%`;
}

/** Compact amount in the filing currency: "320.0 M EUR", "1.37 B TRY". */
export function fmtAmount(v: number | null | undefined, ccy: string | null): string {
  if (v == null) return "—";
  const unit = ccy ?? "TRY";
  if (Math.abs(v) >= 1e9) return `${(v / 1e9).toFixed(2)} B ${unit}`;
  if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(1)} M ${unit}`;
  return `${new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(v)} ${unit}`;
}

/** Map the common Turkish relation labels to English; pass others through. */
export function relationLabel(rel: string | null): string {
  if (!rel) return "—";
  const t = rel.trim().toLocaleUpperCase("tr-TR");
  if (t.includes("BAĞLI ORTAKLIK")) return "Subsidiary";
  if (t.includes("İŞTİRAK")) return "Associate";
  if (t.includes("BİRLİKTE KONTROL") || t.includes("İŞ ORTAKLIĞI")) return "Joint venture";
  if (t.includes("FİNANSAL YATIRIM")) return "Financial investment";
  return rel;
}

/** "2026-05-21" → "May 2026". */
export function fmtAsOf(d: string | null | undefined): string | null {
  if (!d) return null;
  const m = /^(\d{4})-(\d{2})/.exec(d);
  if (!m) return d;
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${months[Number(m[2]) - 1]} ${m[1]}`;
}
