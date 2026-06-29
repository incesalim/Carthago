/**
 * OwnershipSummary — simplified KAP ownership for /banks/[ticker], matching the
 * "Fresh / Flat" design mock: a shareholders (≥5%) bar card next to a
 * subsidiaries chip card. The fuller view (radial map, capital breakdown,
 * indirect holders, subsidiaries table) was retired in the redesign.
 */
import type { KapOwnershipRow } from "@/app/lib/kap";
import { Card } from "@/app/components/ui/card";

const PCT = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});
const fmtPct = (v: number | null | undefined): string =>
  v == null ? "—" : `${PCT.format(v)}%`;

/** A "free float / other" catch-all holder (Turkish "DİĞER" / "HALKA AÇIK"). */
function isOther(name: string | null): boolean {
  const t = (name ?? "").trim().toLocaleUpperCase("tr-TR");
  return t === "DİĞER" || t.includes("HALKA AÇIK") || t.includes("FREE FLOAT");
}
const holderLabel = (name: string | null): string =>
  isOther(name) ? "Other / free float" : name ?? "—";

/** Title-case, Turkish-aware (so İ/ı fold correctly). */
function titleCase(s: string): string {
  return s
    .toLocaleLowerCase("tr-TR")
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toLocaleUpperCase("tr-TR") + w.slice(1))
    .join(" ");
}

/** "AK PORTFÖY YÖNETİMİ A.Ş." → "Ak Portföy Yönetimi" — strip the legal suffix,
 *  title-case, and cap to the first few words so it reads as a chip. */
function shortName(name: string | null): string {
  let s = (name ?? "").trim();
  s = s.replace(/\s*ANON[İI]M\s+Ş[İI]RKET[İI]\s*$/giu, "");
  s = s.replace(/\s*A\.?\s*Ş\.?\s*$/iu, "");
  s = titleCase(s);
  const words = s.split(/\s+/).filter(Boolean);
  return words.length > 4 ? `${words.slice(0, 4).join(" ")}…` : s;
}

/** Associates (İştirak) are excluded from the subsidiary chips — the mock shows
 *  core holdings, not minority sector-consortium stakes. */
const isAssociate = (rel: string | null): boolean =>
  (rel ?? "").toLocaleUpperCase("tr-TR").includes("İŞTİRAK");

export default function OwnershipSummary({ rows }: { rows: KapOwnershipRow[] }) {
  if (rows.length === 0) return null;

  const shareholders = rows.filter(
    (r) => r.item === "shareholder" && !/^toplam$/i.test((r.holder ?? "").trim()),
  );
  const subsAll = rows.filter((r) => r.item === "subsidiary");
  const subsCore = subsAll.filter((r) => !isAssociate(r.relation));
  const subRows = subsCore.length > 0 ? subsCore : subsAll;
  const subNames = Array.from(
    new Set(subRows.map((r) => shortName(r.holder)).filter(Boolean)),
  );

  if (shareholders.length === 0 && subNames.length === 0) return null;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      {shareholders.length > 0 && (
        <Card className="p-5">
          <div className="mb-4">
            <div className="text-sm font-bold text-foreground">Shareholders ≥ 5%</div>
            <div className="text-xs text-muted-foreground">KAP Genel Bilgi Formu</div>
          </div>
          <div className="space-y-3">
            {shareholders.map((r) => {
              const other = isOther(r.holder);
              const w = Math.min(Math.max(r.ratio_pct ?? 0, 0), 100);
              return (
                <div key={r.seq} className="text-xs">
                  <div className="flex items-baseline justify-between gap-3">
                    <span
                      className="min-w-0 truncate font-medium text-foreground"
                      title={r.holder ?? undefined}
                    >
                      {holderLabel(r.holder)}
                    </span>
                    <span className="shrink-0 font-semibold tabular-nums text-foreground">
                      {fmtPct(r.ratio_pct)}
                    </span>
                  </div>
                  <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${w}%`,
                        backgroundColor: other ? "var(--chart-2)" : "var(--primary)",
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {subNames.length > 0 && (
        <Card className="p-5">
          <div className="mb-4">
            <div className="text-sm font-bold text-foreground">Subsidiaries &amp; investments</div>
            <div className="text-xs text-muted-foreground">KAP Genel Bilgi Formu · §7</div>
          </div>
          <div className="flex flex-wrap gap-2">
            {subNames.map((n) => (
              <span
                key={n}
                className="rounded-full border border-border bg-muted px-3 py-1 text-xs font-medium text-foreground"
              >
                {n}
              </span>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
