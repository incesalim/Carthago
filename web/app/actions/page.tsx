/**
 * /actions — what Türkiye's banks DID, read out of the KAP filing stream.
 *
 * Replaces /earnings (a link directory) and /disclosures (a reverse-chron KAP
 * feed, 27% of it coupon plumbing). Every figure is computed at request time by
 * `bankActions()` (app/lib/kap-actions.ts) from the same news_items rows the
 * daily news cron already refreshes — no new source, table, column or workflow.
 * The classifier is deterministic (no LLM sets a category), and only
 * provably-mechanical filings are suppressed; see the lib header.
 *
 * `?ticker=AKBNK` renders one bank's acts (absorbs the old /disclosures?ticker=).
 */
import type { Metadata } from "next";
import type { ReactNode } from "react";
import Link from "next/link";
import {
  bankActions,
  type ActionsData,
  type ClassifiedRow,
} from "@/app/lib/kap-actions";
import { latestEarnings, type EarningsEvent } from "@/app/lib/earnings";
import {
  Colophon,
  Depth,
  DeskHeader,
  SecHead,
  Vital,
  Vitals,
} from "@/app/components/desk";
import { monthLabel } from "@/app/lib/desk";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkish Banks — Corporate Actions",
  description:
    "What Türkiye's banks are doing, classified from KAP filings: wholesale funding and capital instruments, rights issues and dividends, rating actions, and results season.",
  alternates: { canonical: "/actions" },
};

interface Props {
  searchParams: Promise<{ ticker?: string }>;
}

// ── formatting ──────────────────────────────────────────────────────────
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function shortDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso.slice(0, 10);
  return `${MONTHS[Number(m[2]) - 1] ?? m[2]} ${Number(m[3])}`;
}
function fmtPeriod(p: string | null): string {
  if (!p || p.length < 6) return p ?? "";
  return `${p.slice(4)} ${p.slice(0, 4)}`; // 2026Q1 → Q1 2026
}

// ── small view pieces ───────────────────────────────────────────────────

/** One classified KAP act as a table row: date · bank · English gloss (with the
 *  Turkish original beneath, so the gloss is checkable) · an optional right cell. */
function FilingRow({ r, right }: { r: ClassifiedRow; right?: ReactNode }) {
  return (
    <tr>
      <td className="border-b border-hair py-2 pr-3 align-top font-mono text-[11px] whitespace-nowrap text-muted-foreground tabular-nums">
        {shortDate(r.published_at)}
      </td>
      <td className="border-b border-hair py-2 pr-3 align-top">
        <Link
          href={`/actions?ticker=${r.ticker}`}
          className="font-mono text-[11.5px] font-semibold text-foreground hover:text-primary"
        >
          {r.ticker}
        </Link>
      </td>
      <td className="border-b border-hair py-2 pr-3 align-top">
        <a
          href={r.url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[12.5px] leading-snug text-foreground hover:underline"
        >
          {r.gloss}
        </a>
        {r.summary && r.summary.trim() && (
          <span className="mt-0.5 block text-[10.5px] leading-snug text-faint line-clamp-1">
            {r.summary}
          </span>
        )}
      </td>
      {right !== undefined && (
        <td className="border-b border-hair py-2 align-top text-right whitespace-nowrap">{right}</td>
      )}
    </tr>
  );
}

function TableHead({ cols }: { cols: string[] }) {
  return (
    <thead>
      <tr>
        {cols.map((c, i) => (
          <th
            key={c}
            className={`border-b border-hair pb-1.5 font-mono text-[8.5px] font-normal uppercase tracking-[0.07em] text-faint ${
              i === cols.length - 1 && cols.length > 3 ? "text-right" : "text-left"
            }`}
          >
            {c}
          </th>
        ))}
      </tr>
    </thead>
  );
}

function Tag({ kind, children }: { kind: "offshore" | "domestic" | "tier2" | "muted"; children: ReactNode }) {
  const tone =
    kind === "offshore"
      ? "text-data border-data/30"
      : kind === "tier2"
        ? "text-warning border-warning/40"
        : kind === "domestic"
          ? "text-muted-foreground border-hair"
          : "text-faint border-hair";
  return (
    <span className={`rounded-[2px] border px-1.5 py-0.5 font-mono text-[8.5px] uppercase tracking-[0.06em] ${tone}`}>
      {children}
    </span>
  );
}

function fundingTag(r: ClassifiedRow): ReactNode {
  if (/tier-2/i.test(r.gloss)) return <Tag kind="tier2">tier 2</Tag>;
  if (r.offshore) return <Tag kind="offshore">offshore</Tag>;
  return <Tag kind="domestic">domestic</Tag>;
}

/** Per-bank funding bars — the mockup's strip, computed from `funding.byBank`. */
function FundingStrip({ data }: { data: ActionsData }) {
  const max = data.funding.byBank[0]?.n ?? 1;
  return (
    <div className="grid gap-1.5">
      {data.funding.byBank.map((b) => (
        <div key={b.ticker} className="grid grid-cols-[56px_1fr_92px] items-center gap-3">
          <Link
            href={`/actions?ticker=${b.ticker}`}
            className="font-mono text-[11px] font-semibold text-foreground hover:text-primary"
          >
            {b.ticker}
          </Link>
          <span className="h-3 rounded-[1px]" aria-hidden>
            <span
              className="block h-3 rounded-[1px] bg-data"
              style={{ width: `${Math.max(4, (b.n / max) * 100).toFixed(1)}%` }}
            />
          </span>
          <span className="text-right font-mono text-[11px] text-muted-foreground tabular-nums">
            {b.n}
            <span className="text-faint"> · {b.offshore} off</span>
          </span>
        </div>
      ))}
    </div>
  );
}

// ── results season (from bank_earnings, not news_items) ──────────────────
interface SeasonBank {
  ticker: string;
  filed: string | null;
  period: string | null;
  filingUrl: string | null;
  deckUrl: string | null;
  deckPeriod: string | null;
}
function buildSeason(events: EarningsEvent[]): { rows: SeasonBank[]; season: string | null; decks: number } {
  const byBank = new Map<string, SeasonBank>();
  for (const e of events) {
    const b =
      byBank.get(e.ticker) ??
      ({ ticker: e.ticker, filed: null, period: null, filingUrl: null, deckUrl: null, deckPeriod: null } as SeasonBank);
    if (e.kind === "results_filing" && (b.filed == null || e.event_date > b.filed)) {
      b.filed = e.event_date;
      b.period = e.period;
      b.filingUrl = e.url;
    }
    if (e.kind === "presentation_deck" && (b.deckPeriod == null || (e.period ?? "") > (b.deckPeriod ?? ""))) {
      b.deckUrl = e.url;
      b.deckPeriod = e.period;
    }
    byBank.set(e.ticker, b);
  }
  const rows = [...byBank.values()]
    .filter((b) => b.filed || b.deckUrl)
    .sort((a, b) => (b.filed ?? "").localeCompare(a.filed ?? ""));
  const season =
    rows
      .map((r) => r.period)
      .filter((p): p is string => !!p)
      .sort()
      .at(-1) ?? null;
  const decks = rows.filter((r) => r.deckUrl).length;
  return { rows, season, decks };
}

// ── page ─────────────────────────────────────────────────────────────────
export default async function ActionsPage({ searchParams }: Props) {
  const sp = await searchParams;
  const ticker = sp.ticker?.toUpperCase();

  const [data, earnings] = await Promise.all([
    bankActions({ ticker }),
    latestEarnings(400),
  ]);

  const season = buildSeason(
    ticker ? earnings.filter((e) => e.ticker === ticker) : earnings,
  );

  const weeks = Math.max(1, Math.round(data.window.days / 7));
  const universe = data.filerUniverse || 11;

  // ── per-ticker focused view ────────────────────────────────────────────
  if (ticker) {
    const sections: [string, ClassifiedRow[], boolean][] = [
      ["Funding & capital instruments", data.funding.rows, true],
      ["Capital & shareholder events", data.capital, false],
      ["Rating actions", data.rating, false],
      ["Other material events", data.material, false],
      ["Governance & management", data.governance, false],
    ];
    return (
      <main className="mx-auto w-full max-w-[1080px] px-4 py-7 sm:px-6 lg:px-9">
        <DeskHeader
          title={`${ticker} — corporate actions`}
          record={
            <>
              Record <b className="font-normal text-foreground">{monthLabel(data.window.last)}</b> · classified
              from {ticker}&apos;s KAP filings
            </>
          }
          right="compiled, not written"
        />
        <div className="mt-2 flex flex-wrap gap-4 font-mono text-[9.5px] uppercase tracking-[0.05em]">
          <Link href={`/banks/${ticker}`} className="font-semibold text-primary">
            ← back to {ticker}
          </Link>
          <Link href="/actions" className="font-semibold text-primary">
            ← all bank actions
          </Link>
        </div>

        <div className="mt-8 space-y-9">
          {sections
            .filter(([, rows]) => rows.length > 0)
            .map(([title, rows, isFunding]) => (
              <section key={title}>
                <SecHead title={title} meta={`${rows.length} filing${rows.length === 1 ? "" : "s"}`} className="mb-2" />
                <table className="w-full border-collapse">
                  <TableHead cols={isFunding ? ["Date", "Bank", "Act", "Type"] : ["Date", "Bank", "Act"]} />
                  <tbody>
                    {rows.map((r) => (
                      <FilingRow
                        key={`${r.external_id}`}
                        r={r}
                        right={isFunding ? fundingTag(r) : undefined}
                      />
                    ))}
                  </tbody>
                </table>
              </section>
            ))}

          {season.rows.length > 0 && (
            <section>
              <SecHead title="Results & presentations" meta="KAP filing · IR deck" className="mb-2" />
              <table className="w-full border-collapse">
                <TableHead cols={["Filed", "Report", "Deck"]} />
                <tbody>
                  {season.rows.map((b) => (
                    <tr key={b.ticker}>
                      <td className="border-b border-hair py-2 pr-3 font-mono text-[11px] whitespace-nowrap text-muted-foreground tabular-nums">
                        {shortDate(b.filed)}
                      </td>
                      <td className="border-b border-hair py-2 pr-3 text-[12.5px] text-foreground">
                        {b.filingUrl ? (
                          <a href={b.filingUrl} target="_blank" rel="noopener noreferrer" className="hover:underline">
                            {fmtPeriod(b.period) || "Financial report"} — KAP filing ↗
                          </a>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="border-b border-hair py-2 text-right text-[12px]">
                        {b.deckUrl ? (
                          <a href={b.deckUrl} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
                            {fmtPeriod(b.deckPeriod)} deck ↗
                          </a>
                        ) : (
                          <span className="text-faint">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          {data.routineCount > 0 && (
            <p className="text-[11px] text-muted-foreground">
              {data.routineCount} routine filing{data.routineCount === 1 ? "" : "s"} suppressed for {ticker} — coupon
              payments, redemptions, dematerialisation notices and information forms.{" "}
              <a href={`https://www.kap.org.tr/en/bldsm/${ticker}`} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
                All {ticker} filings on KAP ↗
              </a>
            </p>
          )}
        </div>

        <Colophon />
      </main>
    );
  }

  // ── cross-bank view ────────────────────────────────────────────────────

  // Computed headline facts — counts only. The KAP feed holds ~10 weeks with no
  // history, so no trend verb ("reopened", "surged") is asserted; the numbers
  // carry it. Second line names the standout events only when they exist.
  const rights = data.capital.find((r) => /Rights/i.test(r.gloss));
  const buyback = data.capital.find((r) => /buyback/i.test(r.gloss));
  const legal = data.material.find((r) => /Litigation/i.test(r.gloss));
  const nplSales = data.material.filter((r) => /NPL/i.test(r.gloss));

  const capBits: string[] = [];
  if (rights) capBits.push(`a rights issue at ${rights.ticker}`);
  if (buyback) capBits.push(`a buyback at ${buyback.ticker}`);
  if (nplSales.length)
    capBits.push(
      `${nplSales.length} loan-portfolio sale${nplSales.length === 1 ? "" : "s"} (${[...new Set(nplSales.map((r) => r.ticker))].join(", ")})`,
    );
  if (legal) capBits.push(`a live legal proceeding at ${legal.ticker}`);

  return (
    <main className="mx-auto w-full max-w-[1180px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title="Bank Actions"
        record={
          <>
            Record <b className="font-normal text-foreground">{monthLabel(data.window.last)}</b> · KAP filings,
            classified daily · routine notices suppressed
          </>
        }
        right="compiled, not written"
      />

      {/* The read — computed counts, no trend claim. */}
      <div className="mt-6 max-w-[74ch] space-y-2.5">
        <p className="text-[16.5px] leading-relaxed text-foreground">
          <b className="font-semibold">{data.funding.funders}</b> of the {universe} banks that file on KAP raised
          wholesale funding in the {weeks} weeks on record — <b className="font-semibold tabular-nums">{data.funding.total}</b>{" "}
          issuance approvals, <b className="font-semibold tabular-nums">{data.funding.offshore}</b> of them to foreign
          markets (bonds, GMTN programmes, Tier-2 sub-debt, syndication).
        </p>
        {capBits.length > 0 && (
          <p className="text-[13.5px] leading-relaxed text-muted-foreground">
            Beyond funding, the window holds {capBits.join("; ")}. Everything else in the KAP stream —{" "}
            {data.routineCount} coupon notices, redemptions and information forms — is counted below, not shown.
          </p>
        )}
      </div>

      {/* Vitals — the signature band. */}
      <SecHead title="The vitals" meta="funding · reach · ratings · capital · results" className="mb-2.5 mt-8" />
      <Vitals cols={5}>
        <Vital
          label="Wholesale funding filings"
          value={String(data.funding.total)}
          note={`${data.funding.offshore} to foreign markets · ${weeks} weeks on record`}
        />
        <Vital
          label="Banks tapping markets"
          value={String(data.funding.funders)}
          unit={`of ${universe}`}
          note="raised debt or capital instruments; the rest filed none"
        />
        <Vital
          label="Rating actions"
          value={String(data.counts.rating)}
          note={`across ${data.bankCounts.rating} bank${data.bankCounts.rating === 1 ? "" : "s"} · agency named per filing`}
        />
        <Vital
          label="Capital & shareholder events"
          value={String(data.counts.capital)}
          note={
            rights
              ? `incl. a rights issue at ${rights.ticker}`
              : "rights issues · dividends · buybacks · ceilings"
          }
        />
        <Vital
          label="Results season"
          value={season.season ? fmtPeriod(season.season) : "—"}
          note={`${season.rows.filter((r) => r.filed).length} filed · ${season.decks} IR decks collected`}
        />
      </Vitals>

      <Depth meta="classified from the KAP filing stream — deterministic, no model">
        {/* Wholesale funding */}
        <section>
          <SecHead
            title="Wholesale funding & capital instruments"
            meta={`${data.funding.total} filings · ${data.funding.offshore} offshore · ${weeks}w`}
            className="mb-3"
          />
          <div className="grid gap-6 lg:grid-cols-[minmax(260px,340px)_1fr]">
            <div>
              <FundingStrip data={data} />
              <p className="mt-3 text-[11px] leading-snug text-muted-foreground">
                Filings per bank — counts, not amounts (see <i>the gap</i>). &ldquo;off&rdquo; = to foreign markets.
                The four large private and state banks lead; participation and foreign-owned banks file least.
              </p>
            </div>
            <div>
              <table className="w-full border-collapse">
                <TableHead cols={["Date", "Bank", "Act", "Type"]} />
                <tbody>
                  {data.funding.rows.slice(0, 12).map((r) => (
                    <FilingRow key={r.external_id} r={r} right={fundingTag(r)} />
                  ))}
                </tbody>
              </table>
              {data.funding.rows.length > 12 && (
                <p className="mt-2 font-mono text-[9px] uppercase tracking-[0.06em] text-faint">
                  latest 12 of {data.funding.rows.length}
                </p>
              )}
            </div>
          </div>
        </section>

        {/* Capital events */}
        {data.capital.length > 0 && (
          <section>
            <SecHead title="Capital & shareholder events" meta="rights issues · dividends · buybacks · ceilings" className="mb-2" />
            <table className="w-full border-collapse">
              <TableHead cols={["Date", "Bank", "Act"]} />
              <tbody>
                {data.capital.map((r) => (
                  <FilingRow key={r.external_id} r={r} />
                ))}
              </tbody>
            </table>
          </section>
        )}

        {/* Rating actions */}
        {data.rating.length > 0 && (
          <section>
            <SecHead title="Rating actions" meta={`${data.rating.length} filings · ${data.bankCounts.rating} banks`} className="mb-2" />
            <table className="w-full border-collapse">
              <TableHead cols={["Date", "Bank", "Agency", "Filing"]} />
              <tbody>
                {data.rating.map((r) => (
                  <tr key={r.external_id}>
                    <td className="border-b border-hair py-2 pr-3 font-mono text-[11px] whitespace-nowrap text-muted-foreground tabular-nums">
                      {shortDate(r.published_at)}
                    </td>
                    <td className="border-b border-hair py-2 pr-3">
                      <Link href={`/actions?ticker=${r.ticker}`} className="font-mono text-[11.5px] font-semibold text-foreground hover:text-primary">
                        {r.ticker}
                      </Link>
                    </td>
                    <td className="border-b border-hair py-2 pr-3 text-[12.5px] font-medium text-foreground">
                      {r.agency ?? "—"}
                    </td>
                    <td className="border-b border-hair py-2 text-right text-[12px]">
                      <a href={r.url} target="_blank" rel="noopener noreferrer" className="text-foreground hover:underline">
                        {r.summary?.trim() || "rating filing"} ↗
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}

        {/* Other material events */}
        {data.material.length > 0 && (
          <section>
            <SecHead
              title="Other material events"
              meta="portfolio sales · litigation · business development"
              className="mb-2"
            />
            <table className="w-full border-collapse">
              <TableHead cols={["Date", "Bank", "Act"]} />
              <tbody>
                {data.material.slice(0, 12).map((r) => (
                  <FilingRow key={r.external_id} r={r} />
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-[10.5px] leading-snug text-faint">
              The residual bucket: genuine disclosed events the classifier does not slot into funding, capital, rating
              or results. Anything it cannot place lands here — visible, never suppressed.
            </p>
          </section>
        )}

        {/* Results season */}
        {season.rows.length > 0 && (
          <section>
            <SecHead
              title="Results season"
              meta={season.season ? `${fmtPeriod(season.season)} · KAP filing dates · IR decks` : "KAP filing dates · IR decks"}
              className="mb-2"
            />
            <table className="w-full border-collapse">
              <TableHead cols={["Filed", "Bank", "Report", "Deck"]} />
              <tbody>
                {season.rows.map((b) => (
                  <tr key={b.ticker}>
                    <td className="border-b border-hair py-2 pr-3 font-mono text-[11px] whitespace-nowrap text-muted-foreground tabular-nums">
                      {shortDate(b.filed)}
                    </td>
                    <td className="border-b border-hair py-2 pr-3">
                      <Link href={`/actions?ticker=${b.ticker}`} className="font-mono text-[11.5px] font-semibold text-foreground hover:text-primary">
                        {b.ticker}
                      </Link>
                    </td>
                    <td className="border-b border-hair py-2 pr-3 text-[12.5px] text-foreground">
                      {b.filingUrl ? (
                        <a href={b.filingUrl} target="_blank" rel="noopener noreferrer" className="hover:underline">
                          {fmtPeriod(b.period) || "Financial report"} — KAP filing ↗
                        </a>
                      ) : (
                        <span className="text-faint">deck only</span>
                      )}
                    </td>
                    <td className="border-b border-hair py-2 text-right text-[12px]">
                      {b.deckUrl ? (
                        <a href={b.deckUrl} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
                          {fmtPeriod(b.deckPeriod)} deck ↗
                        </a>
                      ) : (
                        <span className="text-faint">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-[10.5px] leading-snug text-faint">
              Turkish banks do not file earnings-call invitations on KAP and no free transcript feed exists, so there
              is no call calendar. Results filings and decks cover the {season.decks ? "listed" : ""} banks with public
              IR archives.
            </p>
          </section>
        )}

        {/* Governance */}
        {data.governance.length > 0 && (
          <section>
            <SecHead
              title="Governance & management"
              meta={`${data.governance.length} filings · latest ${Math.min(8, data.governance.length)}`}
              className="mb-2"
            />
            <table className="w-full border-collapse">
              <TableHead cols={["Date", "Bank", "Act"]} />
              <tbody>
                {data.governance.slice(0, 8).map((r) => (
                  <FilingRow key={r.external_id} r={r} />
                ))}
              </tbody>
            </table>
          </section>
        )}

        {/* Suppressed routine */}
        <section>
          <SecHead title="Suppressed as routine" meta="counted, not shown" className="mb-2" />
          <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
            <span className="font-mono text-[20px] font-semibold text-muted-foreground tabular-nums">
              {data.routineCount}
            </span>
            <span className="max-w-[62ch] text-[12.5px] leading-snug text-muted-foreground">
              coupon-payment notices, redemptions, dematerialisation notices, issuance-ceiling maintenance,
              company-information forms and third-party IPO intermediation — filings a bank makes because a rule
              requires it, not because anything happened. They were the top of /disclosures every day.
            </span>
          </div>
          {data.routineSample.length > 0 && (
            <details className="mt-3">
              <summary className="cursor-pointer font-mono text-[9px] uppercase tracking-[0.06em] text-primary">
                Show a sample
              </summary>
              <table className="mt-2 w-full border-collapse">
                <TableHead cols={["Date", "Bank", "Filing"]} />
                <tbody>
                  {data.routineSample.map((r) => (
                    <FilingRow key={r.external_id} r={r} />
                  ))}
                </tbody>
              </table>
            </details>
          )}
        </section>

        {/* The gap */}
        <section>
          <SecHead title="The gap" meta="what this page cannot yet say" className="mb-2" />
          <div className="max-w-[78ch] space-y-2 border-l-2 border-warning pl-4">
            <p className="text-[12.5px] leading-relaxed text-muted-foreground">
              A KAP filing carries structured amount, ISIN, maturity and coupon fields on its detail form. We hold only
              the title and summary line (the body is not fetched), so this page can say <i>that</i> a bank went to
              foreign markets but not for how much, for how long, or at what price. Until the detail form is scraped
              (<code className="font-mono text-[11.5px] text-foreground">src/news/kap.py</code>), this{" "}
              <b className="font-semibold text-foreground">counts acts; it does not measure them.</b>
            </p>
            <p className="text-[12.5px] leading-relaxed text-muted-foreground">
              The feed reaches back to <b className="font-semibold text-foreground">{shortDate(data.window.first)}</b> —
              KAP&apos;s own window — so a quarter-on-quarter issuance series needs a backfill before it can exist.
            </p>
          </div>
        </section>
      </Depth>

      <Colophon>
        Compiled, not written — classified deterministically from KAP filings (news_items), refreshed daily; IR decks
        from bank investor-relations sites. No model sets a category. Analytical information, not investment advice.
      </Colophon>
    </main>
  );
}
