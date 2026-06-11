/**
 * OwnershipCard — KAP ownership structure on /banks/[ticker].
 *
 * Left: ≥5% direct shareholders (KAP Genel Bilgi Formu §5) with share bars;
 * indirect (ultimate) holders follow as a muted block when disclosed.
 * Right: paid-in capital / registered ceiling and actual free float per
 * share class (the free-float figure is refreshed near-daily by KAP).
 *
 * Renders nothing when the bank has no KAP form (e.g. ATBANK). The TOPLAM
 * row is dropped — it is always 100%. `ratio_pct` is the authoritative
 * field (some non-listed banks repeat the ratio in the TL column).
 */
import type { KapOwnershipRow } from "@/app/lib/kap";

const PCT = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Format a nominal-TL value as "X.XX B₺" / "X.X M₺" (KAP files plain TL). */
function fmtTl(v: number | null | undefined): string {
  if (v == null) return "—";
  if (Math.abs(v) >= 1e9) return `${(v / 1e9).toFixed(2)} B₺`;
  if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(1)} M₺`;
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(v) + "₺";
}

function fmtPct(v: number | null | undefined): string {
  return v == null ? "—" : `${PCT.format(v)}%`;
}

/** "2020-08-01" → "Aug 2020". */
function fmtAsOf(d: string | null | undefined): string | null {
  if (!d) return null;
  const m = /^(\d{4})-(\d{2})/.exec(d);
  if (!m) return d;
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${months[Number(m[2]) - 1]} ${m[1]}`;
}

function holderLabel(name: string | null): string {
  if (!name) return "—";
  // /i can't fold the Turkish dotted İ (U+0130), so compare via tr locale.
  const t = name.trim().toLocaleUpperCase("tr-TR");
  return t === "DİĞER" ? "Other / free float" : name;
}

interface Props {
  rows: KapOwnershipRow[];
}

export default function OwnershipCard({ rows }: Props) {
  if (rows.length === 0) return null;

  const byItem = (item: KapOwnershipRow["item"]) =>
    rows.filter((r) => r.item === item);

  const shareholders = byItem("shareholder").filter(
    (r) => !/^toplam$/i.test((r.holder ?? "").trim()),
  );
  const indirect = byItem("indirect_shareholder").filter(
    (r) => !/^toplam$/i.test((r.holder ?? "").trim()),
  );
  const freeFloat = byItem("free_float");
  const paidIn = byItem("paid_in_capital")[0] ?? null;
  const ceiling = byItem("capital_ceiling")[0] ?? null;

  const shareholdersAsOf = fmtAsOf(shareholders[0]?.as_of);
  const freeFloatAsOf = fmtAsOf(freeFloat[0]?.as_of);

  return (
    <section className="mb-6 rounded-lg border bg-card shadow-sm overflow-hidden">
      <div className="px-5 py-3 border-b bg-muted flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-foreground">Ownership</h2>
        <span className="text-[11px] text-muted-foreground">
          KAP Genel Bilgi Formu{shareholdersAsOf ? ` · filed ${shareholdersAsOf}` : ""}
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-border">
        {/* --- ≥5% shareholders (2/3 width on desktop) ------------------- */}
        <div className="px-5 py-4 md:col-span-2">
          <h3 className="text-[10px] uppercase tracking-wide text-muted-foreground mb-2">
            Shareholders ≥5% of capital
          </h3>
          {shareholders.length === 0 ? (
            <div className="text-xs text-muted-foreground italic">Not disclosed.</div>
          ) : (
            <div className="space-y-2">
              {shareholders.map((r) => (
                <div key={r.seq} className="text-xs">
                  <div className="flex items-baseline justify-between gap-3">
                    <span
                      className="min-w-0 truncate text-foreground"
                      title={r.holder ?? undefined}
                    >
                      {holderLabel(r.holder)}
                    </span>
                    <span className="shrink-0 tabular-nums font-medium text-foreground">
                      {fmtPct(r.ratio_pct)}
                    </span>
                  </div>
                  <div className="mt-1 h-1.5 rounded-full bg-muted overflow-hidden">
                    <div
                      className="h-full rounded-full bg-primary/70"
                      style={{ width: `${Math.min(Math.max(r.ratio_pct ?? 0, 0), 100)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
          {indirect.length > 0 && (
            <div className="mt-4">
              <h3 className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1.5">
                Indirect (ultimate) holders ≥5%
              </h3>
              <div className="space-y-1">
                {indirect.map((r) => (
                  <div
                    key={r.seq}
                    className="flex items-baseline justify-between gap-3 text-xs text-muted-foreground"
                  >
                    <span className="min-w-0 truncate" title={r.holder ?? undefined}>
                      {holderLabel(r.holder)}
                    </span>
                    <span className="shrink-0 tabular-nums">{fmtPct(r.ratio_pct)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* --- Capital + free float -------------------------------------- */}
        <div className="px-5 py-4">
          <h3 className="text-[10px] uppercase tracking-wide text-muted-foreground mb-2">
            Capital
          </h3>
          <div className="space-y-1.5">
            <div className="flex items-baseline justify-between text-xs">
              <span className="text-muted-foreground">Paid-in capital</span>
              <span className="tabular-nums text-foreground">{fmtTl(paidIn?.share_tl)}</span>
            </div>
            {ceiling?.share_tl != null && (
              <div className="flex items-baseline justify-between text-xs">
                <span className="text-muted-foreground">Registered ceiling</span>
                <span className="tabular-nums text-foreground">{fmtTl(ceiling.share_tl)}</span>
              </div>
            )}
          </div>
          {freeFloat.length > 0 && (
            <div className="mt-4">
              <h3 className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1.5">
                Actual free float{freeFloatAsOf ? ` · ${freeFloatAsOf}` : ""}
              </h3>
              <div className="space-y-1">
                {freeFloat.map((r) => (
                  <div
                    key={r.seq}
                    className="flex items-baseline justify-between gap-3 text-xs"
                  >
                    <span className="text-muted-foreground">{r.holder ?? "—"}</span>
                    <span className="tabular-nums font-medium text-foreground">
                      {fmtPct(r.ratio_pct)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
