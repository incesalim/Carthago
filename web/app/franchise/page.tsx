/**
 * Franchise tab — bank franchise & operational footprint (branches, employees,
 * ATMs, customers, cards) extracted deterministically from annual reports
 * (Faaliyet Raporları). Source: scripts/update_faaliyet.py → faaliyet_franchise.
 *
 * Counts are headline figures disclosed in the reports' "Bir Bakışta / At a
 * Glance" sections; each carries an extraction confidence and branch/employee
 * counts are cross-checked against the audited bank profile. Cells flagged
 * low-confidence are marked. The table is empty until the annual-report URLs are
 * curated and the backfill (backfill-faaliyet.yml) has run.
 */
import type { Metadata } from "next";
import Link from "next/link";
import {
  latestFranchiseByBank,
  franchiseCoverage,
  type FranchiseRow,
} from "@/app/lib/faaliyet";
import { BANK_NAMES } from "@/app/lib/bank_names";
import {
  Section,
  Stat,
  Badge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/app/components/ui";
import {
  Colophon,
  Depth,
  DeskHeader,
  SecHead,
  Vital,
  Vitals,
} from "@/app/components/desk";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkish Banks — Franchise & Operational Footprint",
  description: "Branch, ATM, POS, merchant, customer and card counts across Türkiye's banks, extracted from their annual reports (Faaliyet Raporları).",
  alternates: { canonical: "/franchise" },
};

const nfInt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

function intCell(v: number | null) {
  return v == null ? "—" : nfInt.format(Math.round(v));
}

/** Vitals-band value: full count, thousands-separated (no millions abbreviation). */
function bigCount(v: number): { value: string; unit?: string } {
  return { value: nfInt.format(Math.round(v)) };
}

export default async function FranchisePage() {
  const [coverage, rows] = await Promise.all([
    franchiseCoverage(),
    latestFranchiseByBank(),
  ]);

  const hasData = rows.length > 0;
  const yearSpan =
    coverage.min_year && coverage.max_year
      ? coverage.min_year === coverage.max_year
        ? `${coverage.max_year}`
        : `${coverage.min_year}–${coverage.max_year}`
      : "—";

  // ---- the brief's computed vitals -----------------------------------------
  // Sums run over each bank's LATEST annual report (mixed fiscal years where a
  // bank's newest curated report is older).
  const agg = (f: (r: FranchiseRow) => number | null) => {
    let s = 0;
    let n = 0;
    for (const r of rows) {
      const v = f(r);
      if (v != null) {
        s += v;
        n += 1;
      }
    }
    return { s, n };
  };
  // Same sub-50k mis-capture guard as mnCell for the millions-scale figures.
  const headline = (v: number | null) => (v != null && v >= 5e4 ? v : null);
  const atm = agg((r) => r.atm_count);
  const pos = agg((r) => r.pos_count);
  const merchant = agg((r) => r.merchant_count);
  const customer = agg((r) => headline(r.customer_active ?? r.customer_total));
  const cards = agg((r) => headline(r.cards_total));
  const nActive = rows.filter((r) => headline(r.customer_active) != null).length;
  const nTotalOnly = customer.n - nActive;

  // Rows arrive ordered atm_count DESC NULLS LAST — the first discloser leads.
  const atmLeader = rows.find((r) => r.atm_count != null) ?? null;
  const atmLeaderShare =
    atmLeader?.atm_count != null && atm.s > 0
      ? Math.round((atmLeader.atm_count / atm.s) * 100)
      : null;

  const vitalOf = (t: { s: number; n: number }): { value: string; unit?: string } =>
    t.n > 0 ? bigCount(t.s) : { value: "—" };
  const atmV = vitalOf(atm);
  const posV = vitalOf(pos);
  const merchantV = vitalOf(merchant);
  const customerV = vitalOf(customer);
  const cardsV = vitalOf(cards);

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title="Franchise"
        record={
          <>
            Record{" "}
            <b className="font-normal text-foreground">
              FY {coverage.max_year ?? "—"}
            </b>{" "}
            · latest annual report per bank · archive {yearSpan}
          </>
        }
        right="every figure computed from source series"
      />

      <SecHead
        title="The vitals"
        meta="sums over each bank's latest report"
        className="mb-2.5 mt-6"
      />
      <Vitals cols={6}>
        <Vital
          label="Banks covered"
          value={String(coverage.banks ?? 0)}
          note={`${coverage.reports ?? 0} reports extracted · ${coverage.ocr_skipped ?? 0} image-only skipped`}
        />
        <Vital
          label="ATMs"
          value={atmV.value}
          unit={atmV.unit}
          note={
            atmLeader && atmLeaderShare != null
              ? `${BANK_NAMES[atmLeader.bank_ticker] ?? atmLeader.bank_ticker} runs ${atmLeaderShare}% of the mapped fleet`
              : "no ATM counts extracted yet"
          }
        />
        <Vital
          label="POS terminals"
          value={posV.value}
          unit={posV.unit}
          note={`disclosed by ${pos.n} of ${rows.length} covered banks`}
        />
        <Vital
          label="Merchants"
          value={merchantV.value}
          unit={merchantV.unit}
          note={`disclosed by ${merchant.n} of ${rows.length} covered banks`}
        />
        <Vital
          label="Customers"
          value={customerV.value}
          unit={customerV.unit}
          note={
            customer.n > 0
              ? `${nActive} banks report active customers · ${nTotalOnly} headline totals`
              : "no customer counts extracted yet"
          }
        />
        <Vital
          label="Cards"
          value={cardsV.value}
          unit={cardsV.unit}
          note={
            <>
              issued across {cards.n} banks — channel mix on{" "}
              <Link href="/digital" className="font-semibold text-primary">/digital</Link>
            </>
          }
        />
      </Vitals>

      <Depth>
        <Section
          index="01"
          title="Coverage"
          description="Annual reports are curated per bank-year; banks with no text-extractable report (image-only PDFs) are flagged and skipped, not failed."
        >
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Stat label="Banks covered" value={coverage.banks ?? 0} />
            <Stat label="Reports extracted" value={coverage.reports ?? 0} />
            <Stat label="Fiscal years" value={yearSpan} />
            <Stat
              label="Image-only (skipped)"
              value={coverage.ocr_skipped ?? 0}
              tone={(coverage.ocr_skipped ?? 0) > 0 ? "warning" : "neutral"}
            />
          </div>
        </Section>

        <Section
          index="02"
          title="Latest franchise snapshot"
          description="Most recent annual report per bank. Customer and card figures are headline totals in millions. Cells marked with a dot are low-confidence extractions pending review."
        >
          {hasData ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Bank</TableHead>
                  <TableHead className="w-16 text-right">Year</TableHead>
                  <TableHead className="text-right">ATMs</TableHead>
                  <TableHead className="text-right">POS</TableHead>
                  <TableHead className="text-right">Merchants</TableHead>
                  <TableHead className="text-right">Active customers</TableHead>
                  <TableHead className="text-right">Cards</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r: FranchiseRow) => (
                  <TableRow key={r.bank_ticker}>
                    <TableCell className="font-medium">
                      {BANK_NAMES[r.bank_ticker] ?? r.bank_ticker}
                      {r.min_confidence === "low" && (
                        <Badge variant="secondary" className="ml-2" title="low-confidence extraction">
                          ·
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-muted-foreground">
                      {r.fiscal_year}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{intCell(r.atm_count)}</TableCell>
                    <TableCell className="text-right tabular-nums">{intCell(r.pos_count)}</TableCell>
                    <TableCell className="text-right tabular-nums">{intCell(r.merchant_count)}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {mnCell(r.customer_active ?? r.customer_total)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{mnCell(r.cards_total)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="rounded-[10px] border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">
              No annual-report franchise data has been extracted yet. Curate the
              report URLs in <code>data/banks/faaliyet_report_urls.json</code> and run
              the <code>backfill-faaliyet</code> workflow to populate this view.
            </p>
          )}
        </Section>
      </Depth>

      <Colophon />
    </main>
  );
}
