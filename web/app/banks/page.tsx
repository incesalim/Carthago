/**
 * /banks — index of all banks with audit-data coverage.
 *
 * Banks are grouped by their BDDK type and, within each group, ordered by
 * latest total assets (largest first). Click a bank to drill into its
 * quarterly BS + P&L. Each per-bank page also surfaces its recent KAP
 * disclosures, and /disclosures (cross-bank) is reachable from the links row.
 */
import type { Metadata } from "next";
import Link from "next/link";
import { bankSummaries, type BankSummary } from "@/app/lib/audit";
import { BANK_NAMES, BANK_TYPE_BY_TICKER, BANK_TYPE_BADGE_LABELS } from "@/app/lib/bank_names";
import {
  Colophon,
  Depth,
  DeskHeader,
  SecHead,
  Vital,
  Vitals,
} from "@/app/components/desk";
import BankTypeBadge from "@/app/components/BankTypeBadge";
import BankLogo from "@/app/components/BankLogo";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkish Banks — Financials & Profiles",
  description: "Per-bank financials for every bank in Türkiye: balance sheet, income statement, capital, asset quality and profitability from audited BRSA reports.",
  alternates: { canonical: "/banks" },
};

// Section order, top to bottom. Codes: 10006 State · 10005 Private·Domestic ·
// 10007 Private·Foreign · 10003 Participation · 10004 Dev & Inv. Within each
// section, banks sort by latest total assets (desc).
const GROUP_ORDER = ["10006", "10005", "10007", "10003", "10004"];

/** '2026Q1' → 'Q1 2026' for the record line and vitals. */
function quarterLabel(p: string | null | undefined): string {
  const m = p ? /^(\d{4})Q([1-4])$/.exec(p) : null;
  return m ? `Q${m[2]} ${m[1]}` : p || "—";
}

export default async function BanksPage() {
  const banks = await bankSummaries();
  const through = banks.reduce(
    (m, b) => (b.latest_period > m ? b.latest_period : m),
    "",
  );

  // Bucket by BDDK type, then sort each bucket by total assets (desc, nulls last).
  const byType = new Map<string, BankSummary[]>();
  for (const b of banks) {
    const code = BANK_TYPE_BY_TICKER[b.bank_ticker] ?? "other";
    const bucket = byType.get(code) ?? [];
    bucket.push(b);
    byType.set(code, bucket);
  }
  for (const bucket of byType.values()) {
    bucket.sort((a, b) => (b.total_assets ?? -1) - (a.total_assets ?? -1));
  }
  // Known groups in GROUP_ORDER first; any unmapped ("other") fall to the end.
  const codes = [
    ...GROUP_ORDER.filter((c) => byType.has(c)),
    ...[...byType.keys()].filter((c) => !GROUP_ORDER.includes(c)),
  ];

  // ---- the brief's computed vitals — aggregates of the directory itself ----
  const atLatest = through
    ? banks.filter((b) => b.latest_period === through).length
    : 0;
  const withAssets = banks
    .filter((b): b is BankSummary & { total_assets: number } => b.total_assets != null)
    .sort((a, b) => b.total_assets - a.total_assets);
  // bank_audit_*.amount_total is thousand-TL → trillions = value / 1e9.
  const combined = withAssets.reduce((s, b) => s + b.total_assets, 0);
  const top5 = withAssets.slice(0, 5).reduce((s, b) => s + b.total_assets, 0);
  const top5Share = combined > 0 ? (top5 / combined) * 100 : null;
  const largest = withAssets[0] ?? null;
  const totalQuarters = banks.reduce((s, b) => s + b.periods, 0);
  const deepest = banks.reduce<BankSummary | null>(
    (m, b) => (m == null || b.periods > m.periods ? b : m),
    null,
  );

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title="Banks"
        record={
          <>
            Record <b className="font-normal text-foreground">{quarterLabel(through)}</b> ·{" "}
            {banks.length} banks · audited BRSA quarterly filings
          </>
        }
        right="every figure computed from source series"
      />

      <SecHead
        title="The vitals"
        meta="coverage · recency · size · depth"
        className="mb-2.5 mt-6"
      />
      <Vitals cols={5}>
        <Vital
          label="Banks covered"
          value={String(banks.length)}
          note={
            <>
              {codes.length} ownership groups — side by side at{" "}
              <Link href="/cross-bank" className="font-semibold text-primary">
                /cross-bank
              </Link>
            </>
          }
        />
        <Vital
          label="Latest audited quarter"
          value={quarterLabel(through)}
          note={`${atLatest} of ${banks.length} banks have filed it`}
        />
        <Vital
          label="Combined assets"
          value={combined > 0 ? `₺${(combined / 1e9).toFixed(1)}` : "—"}
          unit="trn"
          note={
            largest
              ? `largest: ${BANK_NAMES[largest.bank_ticker] ?? largest.bank_ticker} (₺${(largest.total_assets / 1e9).toFixed(1)} trn)`
              : "sum of latest balance sheets"
          }
        />
        <Vital
          label="Top-5 asset share"
          value={top5Share != null ? top5Share.toFixed(1) : "—"}
          unit="%"
          note="share of combined assets held by the five largest"
        />
        <Vital
          label="Bank-quarters archived"
          value={totalQuarters.toLocaleString("en-US")}
          note={
            deepest
              ? `deepest run: ${BANK_NAMES[deepest.bank_ticker] ?? deepest.bank_ticker} (${deepest.periods} quarters)`
              : "audited BS + P&L per bank-quarter"
          }
        />
      </Vitals>

      <Depth>
        <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
          <Link
            href="/disclosures"
            className="text-muted-foreground underline hover:text-foreground"
          >
            Recent KAP disclosures (all banks) →
          </Link>
          <Link
            href="/regulation"
            className="text-muted-foreground underline hover:text-foreground"
          >
            TCMB &amp; BDDK regulation →
          </Link>
        </div>

        <div className="space-y-8">
          {codes.map((code) => {
            const group = byType.get(code)!;
            const label = BANK_TYPE_BADGE_LABELS[code] ?? "Other";
            return (
              <section key={code}>
                <div className="mb-3 flex items-baseline gap-2">
                  <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {label}
                  </h2>
                  <span className="text-xs tabular-nums text-muted-foreground/60">
                    {group.length}
                  </span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {group.map((b) => {
                    const typeCode = BANK_TYPE_BY_TICKER[b.bank_ticker];
                    return (
                      <Link
                        key={b.bank_ticker}
                        href={`/banks/${b.bank_ticker}`}
                        className="block rounded-[10px] border border-border bg-card p-4 transition-colors hover:border-primary/40"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <BankLogo
                            ticker={b.bank_ticker}
                            name={BANK_NAMES[b.bank_ticker]}
                            height={20}
                          />
                          <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-semibold tabular-nums text-primary shrink-0">
                            {b.bank_ticker}
                          </span>
                        </div>
                        <div className="mt-2.5 flex items-center gap-2 min-w-0">
                          <span className="font-semibold truncate">{BANK_NAMES[b.bank_ticker] ?? b.bank_ticker}</span>
                          {typeCode && (
                            <BankTypeBadge code={typeCode} label={BANK_TYPE_BADGE_LABELS[typeCode]} />
                          )}
                        </div>
                        <div className="text-xs text-muted-foreground mt-1">
                          {b.periods} quarters · latest {b.latest_period}
                        </div>
                      </Link>
                    );
                  })}
                </div>
              </section>
            );
          })}
        </div>
      </Depth>

      <Colophon />
    </main>
  );
}
