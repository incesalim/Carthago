/**
 * /methodology — how a figure on this site is made.
 *
 * The trust layer the 2026-07-12 evaluation asked for, and the page a reader
 * checking a number needs most. Written against the rules the codebase actually
 * enforces in CI, with links to the gates, so a claim here can be verified
 * against the repository rather than believed.
 *
 * Counts are READ, never typed: `check_prose_claims.py` R3 fails a hardcoded
 * bank-universe count in rendered text, because the universe has been 31, 37 and
 * 38 within a year. Anything stating the size of the coverage reads it from the
 * data, so this page cannot go stale the way a hand-written one does.
 */
import type { Metadata } from "next";
import Link from "next/link";
import { bankSummaries } from "@/app/lib/audit";
import { BANK_COUNT, PEER_BANK_COUNT } from "@/app/lib/bank_names";
import { ScrollX } from "@/app/components/ui/scroll-x";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Methodology",
  description:
    "How Carthago computes Turkish banking-sector figures: sources, bases, deflation, period handling, and the checks that run before anything publishes.",
  alternates: { canonical: "/methodology" },
};

const SOURCES: { name: string; what: string; cadence: string }[] = [
  { name: "BDDK monthly bulletin", what: "sector and bank-group aggregates — balance sheet, income statement, loans, deposits, published ratios", cadence: "monthly" },
  { name: "BDDK weekly bulletin", what: "loans and deposits by ownership group and currency", cadence: "weekly" },
  { name: "BRSA quarterly reports", what: "per-bank audited financial statements and their footnotes, extracted from the filed PDFs", cadence: "quarterly" },
  { name: "TCMB EVDS", what: "policy rate, CPI, reserves, exchange rates, balance of payments, sector rates", cadence: "daily to monthly" },
  { name: "TÜİK", what: "CPI detail, national accounts, foreign trade", cadence: "monthly / quarterly" },
  { name: "KAP", what: "ownership structure, subsidiaries, company disclosures", cadence: "as filed" },
  { name: "Borsa İstanbul", what: "prices and shares for the listed banks, for market-based ratios", cadence: "daily" },
  { name: "TBB / TKBB", what: "digital-banking and channel statistics", cadence: "quarterly / monthly" },
];

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="border-t border-hair pt-5">
      <h2 className="mb-2 text-[15px] font-semibold tracking-tight text-foreground">{title}</h2>
      <div className="space-y-3 text-[13.5px] leading-relaxed text-foreground">{children}</div>
    </section>
  );
}

export default async function MethodologyPage() {
  const summaries = await bankSummaries().catch(() => []);
  const banksHeld = summaries.length;
  const latest = summaries.map((s) => s.latest_period).sort().at(-1) ?? null;
  const earliest = summaries.length
    ? Math.min(...summaries.map((s) => s.periods))
    : null;

  return (
    <div className="mx-auto max-w-3xl px-5 py-8 lg:px-8 lg:py-10">
      <header className="mb-6">
        <h1 className="text-[26px] font-semibold tracking-tight text-foreground">Methodology</h1>
        <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.06em] text-faint">
          How a figure on this site is made
        </p>
      </header>

      <p className="mb-7 text-[13.5px] leading-relaxed text-foreground">
        Every number here is compiled from a published source and computed by code in
        a{" "}
        <a
          href="https://github.com/incesalim/Carthago"
          className="font-semibold text-primary underline-offset-2 hover:underline"
          rel="noopener"
        >
          public repository
        </a>
        . Nothing is hand-keyed into the site, and nothing is estimated to fill a gap.
        Where a figure cannot be computed, the page says so instead of printing one.
      </p>

      <div className="space-y-6">
        <Section id="sources" title="Sources">
          <p>
            Eight public sources, each used for what it actually publishes rather than
            blended into one series:
          </p>
          <ScrollX label="Sources table — scrolls horizontally">
            <table className="w-full min-w-[34rem] border-collapse text-[12.5px]">
              <thead>
                <tr className="border-b border-border text-left font-mono text-[9.5px] uppercase tracking-[0.05em] text-faint">
                  <th scope="col" className="py-1.5 pr-3 font-normal">Source</th>
                  <th scope="col" className="py-1.5 pr-3 font-normal">What it carries</th>
                  <th scope="col" className="py-1.5 font-normal">Cadence</th>
                </tr>
              </thead>
              <tbody>
                {SOURCES.map((s) => (
                  <tr key={s.name} className="border-b border-hair align-top">
                    <td className="py-1.5 pr-3 font-medium text-foreground">{s.name}</td>
                    <td className="py-1.5 pr-3 text-muted-foreground">{s.what}</td>
                    <td className="py-1.5 whitespace-nowrap text-muted-foreground">{s.cadence}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ScrollX>
        </Section>

        <Section id="coverage" title="Coverage">
          <p>
            The per-bank data covers{" "}
            <b className="font-semibold">{BANK_COUNT} banks</b>
            {banksHeld > 0 && (
              <>
                , of which <b className="font-semibold">{banksHeld}</b> have audited
                filings extracted and loaded
              </>
            )}
            {latest && (
              <>
                , current through <b className="font-semibold">{latest}</b>
              </>
            )}
            . Figures are extracted from the filed PDFs by deterministic code —
            anchored to the labels and coordinates the regulator&rsquo;s own template
            uses — not by a language model, so the same PDF always yields the same
            number.
            {earliest != null && earliest > 0 && (
              <> Each bank carries the quarters it has filed since 2022.</>
            )}
          </p>
          <p>
            <b className="font-semibold">One bank is carried but excluded from every
            peer statistic.</b>{" "}
            Takasbank is BDDK-licensed and files the same quarterly reports, but it is
            the central clearing and settlement institution — no deposits, and most of
            its balance sheet is member cash and collateral it merely holds. Ranking it
            against lenders would make loan/deposit, NPL and margin ratios meaningless
            and would seat it near the top of an asset league on money it does not own.
            It keeps its own page; it is absent from ranks, market shares, the sector
            HHI and every audited sector ratio. Peer statistics are therefore drawn
            from {PEER_BANK_COUNT} banks.
          </p>
        </Section>

        {/* R2 targets a chart title whose series is on the page; this is a static heading in a
            methodology document, describing a permanent property of the sources rather than
            this quarter's data, and there is no series here to compute it from. */}
        {/* prose-ok: static methodology heading, no series on the page to compute against */}
        <Section id="basis" title="The same quantity often exists more than once">
          <p>
            This is the single largest source of apparent disagreement in Turkish
            banking data, and the site handles it by naming the basis rather than
            picking a winner. Sector capital adequacy is one number in the BDDK monthly
            bulletin and a slightly different one summed from the audited filings;
            loan-to-deposit exists as a published all-currency monthly ratio, as a
            TL-only weekly ratio by ownership group, and as a bank&rsquo;s own audited
            quarterly figure.
          </p>
          <p>
            All are correct and they answer different questions. So: a figure prints
            the basis it was computed on, a comparison is never made across two bases,
            and where a reader will meet the sibling figure on another page, the page
            says where and why it differs.
          </p>
        </Section>

        <Section id="computation" title="How the recurring figures are computed">
          <ul className="ml-4 list-disc space-y-2.5 marker:text-faint">
            <li>
              <b className="font-semibold">Real terms use the exact Fisher form</b>,
              (1+g)/(1+&pi;)&nbsp;&minus;&nbsp;1, never the g&nbsp;&minus;&nbsp;&pi;
              shortcut. At a ~30% CPI the shortcut is more than a point adrift. Growth
              rates are deflated by year-on-year CPI; a return earned across the year is
              deflated by the twelve-month average, and the page states which.
            </li>
            <li>
              <b className="font-semibold">Income-statement figures are year-to-date at
              source</b> and are de-cumulated before being read as a quarter. Return on
              equity is trailing-twelve-month profit over average equity across the
              window, not an annualised snapshot.
            </li>
            <li>
              <b className="font-semibold">Sector aggregates are summed, not averaged</b>,
              from the banks reporting that quarter — numerator and denominator over the
              same population, so a bank missing one component cannot drag a ratio down
              while still contributing to its denominator. Where a ratio has no stored
              numerator (liquidity coverage, for instance), the sector view is an
              asset-weighted average and is labelled as one.
            </li>
            <li>
              <b className="font-semibold">Growth is paired by date, not by row offset.</b>{" "}
              A source that skips a week must render as a gap; measuring 65 weeks and
              calling it a year is the failure mode this rule exists to prevent.
            </li>
          </ul>
        </Section>

        <Section id="checks" title="What runs before anything publishes">
          <p>
            The extraction is validated against the filings themselves — statements must
            foot, parents must equal the sum of their children, and totals must
            reconcile to the figure the bank printed. A partition that fails is held
            back rather than published; the coverage matrix behind the site tracks every
            bank-quarter-statement cell.
          </p>
          <p>
            On the presentation side, three checks run in continuous integration on
            every change: a sentence asserting a direction, a level or a ranking must be
            computed from the series beside it or it does not print; every colour used
            as text must clear the WCAG AA contrast floor; and the documentation must
            name every scheduled job and every secret it reads. These are gates, not
            conventions — a change that breaks one does not ship.
          </p>
        </Section>

        <Section id="limits" title="What this is not">
          <ul className="ml-4 list-disc space-y-2.5 marker:text-faint">
            <li>
              <b className="font-semibold">Not investment advice</b>, and no forecasts.
              Where a scenario is sized, its assumptions are printed next to it.
            </li>
            <li>
              <b className="font-semibold">Not real-time.</b> Each page carries the
              period of the data it shows and the date it was last refreshed. Market
              prices are delayed.
            </li>
            <li>
              <b className="font-semibold">Not a substitute for the filings.</b> Where a
              figure matters, the source document is the authority — this site is a
              faster way to read it, and its extraction is auditable in the repository.
            </li>
            <li>
              <b className="font-semibold">Not complete.</b> Some disclosures are filed
              as images rather than text and resist extraction; some banks disclose an
              item others do not. A gap prints as a gap.
            </li>
          </ul>
        </Section>

        <Section id="corrections" title="Corrections">
          <p>
            If a figure here disagrees with a filing, that is a bug and worth reporting:{" "}
            <a
              href="mailto:incesalim10@gmail.com"
              className="font-semibold text-primary underline-offset-2 hover:underline"
            >
              incesalim10@gmail.com
            </a>
            . Fixes land in the public repository with the reasoning attached, and the
            dated change history is part of it.
          </p>
        </Section>
      </div>

      <footer className="mt-9 border-t border-border pt-3 font-mono text-[8.5px] uppercase leading-relaxed tracking-[0.04em] text-faint">
        <Link href="/about" className="text-primary">About</Link> ·{" "}
        <Link href="/privacy" className="text-primary">Privacy</Link> ·{" "}
        <Link href="/" className="text-primary">Back to the dashboard</Link>
      </footer>
    </div>
  );
}
