/**
 * SubsidiariesCard — KAP §7 "Bağlı Ortaklıklar, Finansal Duran Varlıklar ile
 * Finansal Yatırımlar" on /banks/[ticker].
 *
 * One table row per holding: company, scope of activities (as filed,
 * Turkish), relation type, ownership ratio, and the bank's capital share in
 * the filing currency (TRY/EUR/USD — amounts are NOT normalised to TL).
 * Renders nothing when the bank doesn't file the grid (non-listed form
 * variant — Ziraat, Kuveyt Türk, …).
 */
import type { KapOwnershipRow } from "@/app/lib/kap";

const PCT = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Compact amount in the filing currency: "320.0 M EUR", "1.37 B TRY". */
function fmtAmount(v: number | null | undefined, ccy: string | null): string {
  if (v == null) return "—";
  const unit = ccy ?? "TRY";
  if (Math.abs(v) >= 1e9) return `${(v / 1e9).toFixed(2)} B ${unit}`;
  if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(1)} M ${unit}`;
  return `${new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(v)} ${unit}`;
}

/** Map the common Turkish relation labels to English; pass others through. */
function relationLabel(rel: string | null): string {
  if (!rel) return "—";
  const t = rel.trim().toLocaleUpperCase("tr-TR");
  if (t.includes("BAĞLI ORTAKLIK")) return "Subsidiary";
  if (t.includes("İŞTİRAK")) return "Associate";
  if (t.includes("BİRLİKTE KONTROL") || t.includes("İŞ ORTAKLIĞI")) return "Joint venture";
  if (t.includes("FİNANSAL YATIRIM")) return "Financial investment";
  return rel;
}

/** "2026-05-21" → "May 2026". */
function fmtAsOf(d: string | null | undefined): string | null {
  if (!d) return null;
  const m = /^(\d{4})-(\d{2})/.exec(d);
  if (!m) return d;
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${months[Number(m[2]) - 1]} ${m[1]}`;
}

interface Props {
  rows: KapOwnershipRow[];
}

export default function SubsidiariesCard({ rows }: Props) {
  const subs = rows.filter((r) => r.item === "subsidiary");
  if (subs.length === 0) return null;

  const asOf = fmtAsOf(subs[0]?.as_of);

  return (
    <section className="mb-6 rounded-lg border bg-card shadow-sm overflow-hidden">
      <div className="px-5 py-3 border-b bg-muted flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-foreground">
          Subsidiaries &amp; financial investments
        </h2>
        <span className="text-[11px] text-muted-foreground">
          KAP Genel Bilgi Formu{asOf ? ` · filed ${asOf}` : ""}
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-muted-foreground">
            <tr className="border-b">
              <th className="text-left py-2 pl-5 pr-3 font-medium">Company</th>
              <th className="text-left py-2 px-3 font-medium">Activity</th>
              <th className="text-left py-2 px-3 font-medium">Relation</th>
              <th className="text-right py-2 px-3 font-medium">Share %</th>
              <th className="text-right py-2 pl-3 pr-5 font-medium">Capital share</th>
            </tr>
          </thead>
          <tbody>
            {subs.map((r) => (
              <tr key={r.seq} className="border-b border-border last:border-b-0">
                <td className="py-1.5 pl-5 pr-3 text-foreground">
                  {r.holder ?? "—"}
                </td>
                <td
                  className="py-1.5 px-3 text-muted-foreground max-w-[16rem] truncate"
                  title={r.activity ?? undefined}
                >
                  {r.activity ?? "—"}
                </td>
                <td className="py-1.5 px-3 text-muted-foreground whitespace-nowrap">
                  {relationLabel(r.relation)}
                </td>
                <td className="py-1.5 px-3 text-right tabular-nums text-foreground">
                  {r.ratio_pct == null ? "—" : `${PCT.format(r.ratio_pct)}%`}
                </td>
                <td className="py-1.5 pl-3 pr-5 text-right tabular-nums text-foreground whitespace-nowrap">
                  {fmtAmount(r.share_tl, r.currency)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="px-5 py-2 text-[10px] text-muted-foreground border-t border-border">
        Capital share is the bank&apos;s nominal holding in each company&apos;s
        paid-in capital, in the currency the bank filed (not converted to TL).
      </p>
    </section>
  );
}
