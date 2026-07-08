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
import {
  latestFranchiseByBank,
  franchiseCoverage,
  type FranchiseRow,
} from "@/app/lib/faaliyet";
import { BANK_NAMES } from "@/app/lib/bank_names";
import {
  PageHeader,
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

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkish Banks — Franchise & Operational Footprint",
  description: "Branch, ATM, POS, merchant, customer and card counts across Türkiye's banks, extracted from their annual reports (Faaliyet Raporları).",
  alternates: { canonical: "/franchise" },
};

const nfInt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const nfMn = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

function intCell(v: number | null) {
  return v == null ? "—" : nfInt.format(Math.round(v));
}

/** Large customer/card counts shown in millions. */
function mnCell(v: number | null) {
  return v == null ? "—" : `${nfMn.format(v / 1e6)} mn`;
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

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      <PageHeader
        eyebrow="Faaliyet Raporları — bank annual reports"
        title="Franchise"
        description="Operational footprint — ATMs, POS terminals, merchants, customers and cards — disclosed in banks' annual reports and extracted deterministically. (Branch and employee counts come from the audited financials, not this lane.)"
        dataThrough={coverage.max_year ? String(coverage.max_year) : undefined}
      />

      <Section
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
          <p className="rounded-lg border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">
            No annual-report franchise data has been extracted yet. Curate the
            report URLs in <code>data/banks/faaliyet_report_urls.json</code> and run
            the <code>backfill-faaliyet</code> workflow to populate this view.
          </p>
        )}
      </Section>
    </main>
  );
}
