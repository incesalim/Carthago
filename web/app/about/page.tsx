/**
 * /about — what this is, who makes it, and what it is for.
 *
 * The other half of the trust layer the 2026-07-12 evaluation flagged (with
 * /privacy and /methodology). Kept short on purpose: a reader who wants the
 * detail wants /methodology, and an About page that pads is worse than none.
 *
 * Counts are READ from the data, never typed — see the note in /methodology.
 */
import type { Metadata } from "next";
import Link from "next/link";
import { bankSummaries } from "@/app/lib/audit";
import { BANK_COUNT } from "@/app/lib/bank_names";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "About",
  description:
    "What Carthago is: an independent, open-source dashboard of Turkish banking-sector data compiled from BDDK, BRSA, TCMB and TÜİK sources.",
  alternates: { canonical: "/about" },
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-t border-hair pt-5">
      <h2 className="mb-2 text-[15px] font-semibold tracking-tight text-foreground">{title}</h2>
      <div className="space-y-3 text-[13.5px] leading-relaxed text-foreground">{children}</div>
    </section>
  );
}

export default async function AboutPage() {
  const summaries = await bankSummaries().catch(() => []);
  const latest = summaries.map((s) => s.latest_period).sort().at(-1) ?? null;

  return (
    <div className="mx-auto max-w-3xl px-5 py-8 lg:px-8 lg:py-10">
      <header className="mb-6">
        <h1 className="text-[26px] font-semibold tracking-tight text-foreground">About</h1>
        <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.06em] text-faint">
          Carthago · Turkish banking sector
        </p>
      </header>

      <p className="mb-7 text-[13.5px] leading-relaxed text-foreground">
        Carthago is an independent dashboard of the Turkish banking sector: the
        regulator&rsquo;s own aggregates, every listed and unlisted bank&rsquo;s audited
        quarterly filings, and the macro series that move them — compiled into one
        place and kept current automatically.
      </p>

      <div className="space-y-6">
        <Section title="What it covers">
          <p>
            Sector aggregates from the BDDK monthly and weekly bulletins; per-bank
            audited financial statements for <b className="font-semibold">{BANK_COUNT} banks</b>{" "}
            extracted from their BRSA quarterly reports
            {latest && <> and current through <b className="font-semibold">{latest}</b></>};
            capital, liquidity, asset quality, market risk and profitability views over
            both; ownership from KAP; prices and valuation for the listed banks; and the
            macro backdrop from TCMB and TÜİK — policy rate, inflation, reserves, the
            balance of payments and the budget.
          </p>
          <p>
            A public, read-only API serves the bulletin series under{" "}
            <code className="font-mono text-[12px]">/api/v1</code>, no key required.
          </p>
        </Section>

        <Section title="Why it exists">
          <p>
            The underlying data is public but scattered: monthly aggregates in one
            bulletin, weekly in another, per-bank detail locked inside quarterly PDFs
            that nobody reads at scale, and the macro context somewhere else entirely.
            Answering an ordinary question — is this bank&rsquo;s loan book growing in
            real terms, is its capital buffer made of common equity or instruments,
            is the sector&rsquo;s problem loan book bigger than the headline ratio
            suggests — means assembling all four by hand, every time.
          </p>
          <p>
            This site does that assembly once, in code, and shows its work.
          </p>
        </Section>

        <Section title="How it is built">
          <p>
            A scheduled pipeline scrapes the published sources, extracts the filings
            with deterministic code, validates the results against the filings&rsquo; own
            internal identities, and loads what passes. The dashboard reads that store
            and computes each view at request time. There is no manual data entry step,
            and no language model sets a figure.
          </p>
          <p>
            The whole thing —  pipeline, extraction, checks and site — is{" "}
            <a
              href="https://github.com/incesalim/Carthago"
              className="font-semibold text-primary underline-offset-2 hover:underline"
              rel="noopener"
            >
              open source
            </a>
            . Any figure can be traced to the code that produced it and the source it
            came from. The rules behind the numbers are written up in{" "}
            <Link href="/methodology" className="font-semibold text-primary underline-offset-2 hover:underline">
              methodology
            </Link>
            .
          </p>
        </Section>

        <Section title="Who makes it">
          <p>
            A solo, non-commercial project by Salim İnce. It is not affiliated with,
            endorsed by, or speaking for the BDDK, the TCMB, any bank, or any other
            institution named on the site. There is no advertising and nothing is sold.
          </p>
          <p>
            Questions, corrections and data disputes:{" "}
            <a
              href="mailto:incesalim10@gmail.com"
              className="font-semibold text-primary underline-offset-2 hover:underline"
            >
              incesalim10@gmail.com
            </a>
            .
          </p>
        </Section>

        <Section title="Terms of use">
          <p>
            Everything here is analytical information about public data — not
            investment advice, not a recommendation to buy or sell anything, and no
            forecast of what any bank or the sector will do. Figures are provided as
            they are, with no warranty; where a number matters, the filing is the
            authority.
          </p>
          <p>
            The underlying source data belongs to the institutions that publish it and
            their terms govern its reuse. The code is open source under its own licence;
            reuse of the compiled figures is fine with attribution and a link.
          </p>
        </Section>
      </div>

      <footer className="mt-9 border-t border-border pt-3 font-mono text-[8.5px] uppercase leading-relaxed tracking-[0.04em] text-faint">
        <Link href="/methodology" className="text-primary">Methodology</Link> ·{" "}
        <Link href="/privacy" className="text-primary">Privacy</Link> ·{" "}
        <Link href="/" className="text-primary">Back to the dashboard</Link>
      </footer>
    </div>
  );
}
