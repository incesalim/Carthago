/**
 * /regulation — the regime in force.
 *
 * The page this replaced COUNTED the feed: how many items arrived, when the last
 * one landed, which keyword topic won. None of those is a fact about regulation.
 * Its headline "Latest decision" pointed at the replacement of an SSL certificate
 * on the CBRT website, and five of the seven "instruments" in its 30-day count
 * were not regulation at all (a magazine, a memorandum, a data release).
 *
 * This page STATES the regime instead — the corridor and the reserve ratios a
 * bank actually complies with — compiled from the instruments that set them.
 * Design + rationale: docs/knowledge/regulation-tab-redesign-2026-07-12.md
 *
 * Nothing here is written by hand or by an LLM:
 *   - the policy rate comes from EVDS and is RECONCILED against the press
 *     release; a disagreement raises a flag rather than picking a winner;
 *   - the read is a template with computed slots, so it says the same kind of
 *     thing next month, about next month;
 *   - a rule we can classify but cannot parse is PRINTED as a gap, so the band
 *     declares its own incompleteness (TCMB ships most macroprudential releases
 *     with no parseable table — the 23 May credit growth limits among them).
 */
import type { Metadata } from "next";
import Link from "next/link";
import { latestRegulationBriefing, newsSourceSummary, type NewsItem } from "@/app/lib/news";
import {
  Colophon,
  Depth,
  DeskHeader,
  Flags,
  SecHead,
  Vital,
  Vitals,
  type Flag,
} from "@/app/components/desk";
import {
  bankNames,
  classifyInstrument,
  decisionLags,
  deriveCorridor,
  derivePolicyPath,
  deriveReserves,
  isInstrument,
  licences,
  meetingsHeld,
  policyRateFromEvds,
  parseBoardDecision,
  rateChanges,
  regulationFeed,
  reserveCellLabel,
  unreadRules,
  type InstrumentKind,
  type LicenceKind,
} from "@/app/lib/regulation";
import Archive, { type ArchiveRow } from "./Archive";
import DecisionLag from "./DecisionLag";
import PolicyPath from "./PolicyPath";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkish Banking Regulation — the regime in force",
  description:
    "The policy corridor and reserve requirements Turkish banks comply with today — compiled from the CBRT and BDDK instruments that set them, with the date each one binds.",
  alternates: { canonical: "/regulation" },
};

const DAY = 86_400_000;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function shortDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso.slice(0, 10);
  return `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]}`;
}

function longDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  return `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}`;
}

function daysBetween(a: string, b: string): number {
  return Math.round((Date.parse(b) - Date.parse(a)) / DAY);
}

const pct = (v: number) => v.toFixed(v % 1 === 0 ? 0 : 2);

// A permission to ESTABLISH a bank is not a licence to OPERATE one, and a
// revocation is neither. Saying "operating licence granted" over all three, as
// the first cut did, is simply false for two of them.
const LICENCE_LABEL: Record<LicenceKind, string> = {
  operating: "operating licence",
  establishment: "permission to establish",
  revocation: "licence revoked",
};

export default async function RegulationPage() {
  const [feed, evds, banks, summary, briefing] = await Promise.all([
    regulationFeed(),
    policyRateFromEvds(),
    bankNames(),
    newsSourceSummary(),
    latestRegulationBriefing(),
  ]);

  // THE BRIEFING IS THE EDITOR, NOT THE SOURCE OF THE FIGURES.
  //
  // Kimi's regime bullets ARE the band now — restating them below would be the
  // page arguing with itself. But the briefing also surfaces categories no cell
  // models (licensing, payments, structure), and dropping those would delete
  // analytical content the old page carried. So: keep the residue, drop the
  // duplication. If a category keeps reappearing here week after week, that is
  // the signal to give it a cell of its own.
  const MODELLED = /monetary policy|policy stance|interest rate|reserve requirement|deposit share/i;
  const residue = (briefing?.categories ?? []).filter((c) => !MODELLED.test(c.name));

  // The record is the newest thing we hold — but the newest INSTRUMENT is what
  // the page is about, and they are not the same date. Say both.
  const newest = feed[0]?.published_at.slice(0, 10) ?? null;
  const kindOf = new Map<NewsItem, InstrumentKind>(feed.map((it) => [it, classifyInstrument(it)]));
  const newestInstrument =
    feed.find((it) => isInstrument(kindOf.get(it)!))?.published_at.slice(0, 10) ?? null;
  const anchor = newest ?? new Date().toISOString().slice(0, 10);

  // ── the regime ────────────────────────────────────────────────────────────
  const corridor = deriveCorridor(feed);
  const reserves = deriveReserves(feed);
  const path = derivePolicyPath(feed);
  const changes = rateChanges(path);
  const held = meetingsHeld(path);
  const lastChange = changes[changes.length - 1] ?? null;
  const unread = unreadRules(feed, anchor);

  // Reconciliation: EVDS is the value, the release is the citation. If they
  // disagree, we do not pick a winner — we raise it.
  const reconciled =
    corridor != null && evds != null ? Math.abs(corridor.policy - evds.value) < 0.01 : false;

  // ── the clock ─────────────────────────────────────────────────────────────
  const lags = decisionLags(feed);
  const meanLag = lags.length ? Math.round(lags.reduce((s, r) => s + r.lagDays, 0) / lags.length) : 0;
  const worstLag = lags.length ? Math.max(...lags.map((r) => r.lagDays)) : 0;
  const numbers = lags.map((r) => r.decisionNo);
  const span = numbers.length ? Math.max(...numbers) - Math.min(...numbers) + 1 : 0;
  const lic = licences(lags, banks);
  // Only a bank that was actually LICENSED TO OPERATE and is absent from the
  // universe is worth a flag. A permission to establish is not an operating
  // licence, and a revocation is the opposite of one.
  const uncovered = lic.filter((r) => r.ticker == null && r.kind === "operating");
  const revoked = lic.filter((r) => r.kind === "revocation");

  // ── the 30-day window: what the old page's headline count actually contained
  const win = feed.filter((it) => daysBetween(it.published_at.slice(0, 10), anchor) <= 30);
  const winInstruments = win.filter((it) => isInstrument(kindOf.get(it)!));
  // "Not regulation" and "we could not place it" are different claims. Keep them
  // apart: an unclassified release might BE a rule, and saying otherwise would
  // be the same confident-but-wrong move the old page made with the SSL cert.
  const winNoise = win.filter((it) => kindOf.get(it) === "other");
  const winUnknown = win.filter((it) => kindOf.get(it) === "unclassified");

  const tcmbTotal = summary.find((s) => s.source === "tcmb")?.total ?? 0;
  const bddkTotal = summary.find((s) => s.source === "bddk")?.total ?? 0;

  // ── the read — a template with computed slots, not a sentence someone typed
  const sinceChange = lastChange ? daysBetween(lastChange.date, anchor) : null;
  const bindsIn = reserves?.bindsOn ? daysBetween(anchor, reserves.bindsOn) : null;
  const fxUp = reserves?.changes.filter((c) => c.next > c.prev) ?? [];
  const bump = fxUp.length ? fxUp[0].next - fxUp[0].prev : null;

  // ── the archive ───────────────────────────────────────────────────────────
  // Bodies are heavy (TCMB releases average 2.6kB) and every one of them would
  // otherwise be serialised into the client payload. Ship the text only for the
  // most recent slice — enough that the drawer opens instantly on anything a
  // reader is plausibly looking at — and let older rows fall back to the link.
  const BODY_BUDGET = 120;
  const rows: ArchiveRow[] = feed
    .map((item) => {
      const d = parseBoardDecision(item.title);
      const pub = item.published_at.slice(0, 10);
      return {
        item,
        kind: kindOf.get(item)!,
        decidedAt: d?.decidedAt ?? pub,
        decidedIsFallback: d == null,
        lagDays: d ? daysBetween(d.decidedAt, pub) : null,
        decisionNo: d?.decisionNo ?? null,
      };
    })
    .sort((a, b) => b.decidedAt.localeCompare(a.decidedAt))
    .slice(0, 220)
    .map((r, i) => (i < BODY_BUDGET ? r : { ...r, item: { ...r.item, body_text: null } }));

  // ── flags ─────────────────────────────────────────────────────────────────
  // Flags are for the READER, and every one of them says something about the
  // REGIME — not about our pipeline. Whether our two sources reconcile, how many
  // characters a release had, and what is in our `banks` table are our problems,
  // not a visitor's: they belong in the colophon and in CI, not shouting in red.
  // What a reader genuinely needs is: what binds, what we cannot show them, and
  // how the regulators behave.
  const flags: Flag[] = [
    {
      code: "NOT SHOWN",
      active: unread.length > 0,
      rule: "rule change ∧ no machine-readable parameters",
      body: (
        <>
          <b className="font-semibold">
            {unread.length} further rule change{unread.length === 1 ? " is" : "s are"} in force
            that this page cannot show you.
          </b>{" "}
          The regulators announced them without publishing the numbers in any machine-readable
          form — so the band above is <b className="font-semibold">not the whole regime</b>. Read
          them at the source:{" "}
          {unread.slice(0, 4).map((u, i) => (
            <span key={u.url}>
              {i > 0 && "; "}
              <a
                href={u.url}
                target="_blank"
                rel="noopener noreferrer"
                className="font-semibold text-primary"
              >
                {u.title.length > 58 ? `${u.title.slice(0, 56)}…` : u.title}
              </a>{" "}
              ({longDate(u.publishedAt)})
            </span>
          ))}
          {unread.length > 4 && <> … and {unread.length - 4} more</>}.
        </>
      ),
      clear: <>every rule change in the last 12 months is shown above with its parameters</>,
    },
    {
      code: "DISPUTED",
      // Only ever shown when it FIRES: a reader needs to know a headline figure is
      // contested. That the two sources AGREE is our QA, not their news.
      active: corridor != null && evds != null && !reconciled,
      rule: "policy rate: EVDS ≠ the release that set it",
      body: (
        <>
          <b className="font-semibold">The policy rate above is disputed between sources.</b> The
          CBRT&apos;s own statistics service reports{" "}
          <b className="font-semibold">{evds && pct(evds.value)}%</b>, while the rate decision that
          set it says <b className="font-semibold">{corridor && pct(corridor.policy)}%</b>. Treat
          the figure as provisional until they agree.
        </>
      ),
    },
    {
      code: "PIPELINE",
      active: uncovered.length > 0,
      rule: "bank licensed ∧ no financials filed yet",
      body: (
        <>
          <b className="font-semibold">
            {uncovered.length} bank{uncovered.length === 1 ? " holds" : "s hold"} a BDDK operating
            licence but {uncovered.length === 1 ? "has" : "have"} not started reporting
          </b>{" "}
          —{" "}
          {uncovered.slice(0, 5).map((r, i) => (
            <span key={r.decision.decisionNo}>
              {i > 0 && ", "}
              {r.institution}
            </span>
          ))}
          {uncovered.length > 5 && <> and {uncovered.length - 5} more</>}. They are licensed to
          operate and will appear in the sector figures once they file. This register is where
          Türkiye&apos;s newest banks show up first — Enpara, Colendi and Ziraat Dinamik were all
          named here before they filed a single statement.
        </>
      ),
      clear: <>every licensed bank is reporting</>,
    },
    {
      code: "LATE",
      active: lags.length > 0 && meanLag > 90,
      rule: "mean(published − decided) > 90d",
      body: (
        <>
          <b className="font-semibold">
            BDDK publishes its board decisions a mean of {meanLag} days after taking them
          </b>{" "}
          (worst: {worstLag} days), in irregular batches. So a decision that appears in the feed
          this month may be more than a year old — dates below are the dates the board{" "}
          <b className="font-semibold">decided</b>, which is the date that governs.
        </>
      ),
      clear: <>the regulator publishes its decisions promptly</>,
    },
    {
      code: "HELD",
      // A domain fact, not a self-check: the corridor is simply not moving.
      active: false,
      rule: "Δ policy rate over the last 3 meetings",
      body: <></>,
      clear:
        lastChange && held > 0 ? (
          <>
            the policy rate has not changed in {held} meeting{held === 1 ? "" : "s"} — last moved{" "}
            {longDate(lastChange.date)}
          </>
        ) : (
          <>the policy rate is unchanged</>
        ),
    },
    {
      code: "REVOKED",
      active: revoked.length > 0,
      rule: "licence revoked ∧ bank is in the sector figures",
      body: (
        <>
          <b className="font-semibold">
            {revoked.length} bank licence{revoked.length === 1 ? "" : "s"} revoked
          </b>{" "}
          —{" "}
          {revoked.slice(0, 4).map((r, i) => (
            <span key={r.decision.decisionNo}>
              {i > 0 && ", "}
              {r.institution}
            </span>
          ))}
          . A revocation removes a bank from the sector before its figures stop appearing.
        </>
      ),
      clear: <>no bank licence has been revoked</>,
    },
  ];

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title="Regulation"
        record={
          <>
            Rules in force <b className="font-normal text-foreground">{longDate(anchor)}</b>
            {corridor && (
              <> · corridor set <b className="font-normal text-foreground">{shortDate(corridor.decidedAt)}</b></>
            )}
            {reserves?.bindsOn && (
              <> · reserve ratios bind <b className="font-normal text-foreground">{shortDate(reserves.bindsOn)}</b></>
            )}
          </>
        }
        right="compiled, not written"
      />

      <div className="mt-2 flex flex-wrap gap-4 font-mono text-[9.5px] tracking-[0.05em] uppercase">
        <Link href="/banks" className="font-semibold text-primary">
          Per-bank disclosures (KAP) →
        </Link>
      </div>

      <SecHead
        title="The regime in force"
        meta="policy corridor · reserve requirements — read from the instruments that set them"
        className="mt-6 mb-2.5"
      />

      {/* The band's width follows the regime, not the markup: if a future release
          adds an instrument we can read, it gets a cell; if we can read none, the
          corridor still stands alone rather than leaving three empty columns. */}
      <Vitals
        cols={Math.min(
          6,
          Math.max(3, 3 + (reserves?.changes.slice(0, 2).length ?? 0) + (reserves?.terminated.length ? 1 : 0)),
        ) as 3 | 4 | 5 | 6}
      >
        <Vital
          label="Policy rate"
          value={corridor ? pct(corridor.policy) : "—"}
          unit={corridor ? "%" : undefined}
          note={
            corridor ? (
              <>
                {held > 0 && (
                  <>
                    Held for <b className="font-semibold text-foreground">{held}</b> consecutive
                    meeting{held === 1 ? "" : "s"}.{" "}
                  </>
                )}
                {lastChange && (
                  <>Last change {longDate(lastChange.date)}. </>
                )}
                {evds && reconciled ? (
                  <>EVDS and the release agree.</>
                ) : evds ? (
                  <span className="font-semibold text-negative">EVDS says {pct(evds.value)}%.</span>
                ) : null}
              </>
            ) : (
              "not stated in the last release"
            )
          }
        />
        <Vital
          label="O/N lending"
          value={corridor?.lending != null ? pct(corridor.lending) : "—"}
          unit={corridor?.lending != null ? "%" : undefined}
          note={
            corridor?.lending != null ? (
              <>
                The ceiling — what a bank pays the CBRT overnight.{" "}
                <b className="font-semibold text-foreground">
                  +{Math.round((corridor.lending - corridor.policy) * 100)}bp
                </b>{" "}
                over policy.
              </>
            ) : (
              "not stated in the last release"
            )
          }
        />
        <Vital
          label="O/N borrowing"
          value={corridor?.borrowing != null ? pct(corridor.borrowing) : "—"}
          unit={corridor?.borrowing != null ? "%" : undefined}
          note={
            corridor?.borrowing != null && corridor.lending != null ? (
              <>
                The floor — what it earns on cash left there. Corridor width{" "}
                <b className="font-semibold text-foreground">
                  {Math.round((corridor.lending - corridor.borrowing) * 100)}bp
                </b>
                .
              </>
            ) : (
              "not stated in the last release"
            )
          }
        />

        {reserves?.changes.slice(0, 2).map((c) => (
          <Vital
            key={c.label}
            label={reserveCellLabel(c)}
            value={pct(c.next)}
            unit="%"
            note={
              <>
                <span className="font-mono">
                  <s className="text-faint">{pct(c.prev)}%</s> →{" "}
                  <b className="font-semibold text-foreground">{pct(c.next)}%</b>
                  {c.next !== c.prev && ` · ${c.next > c.prev ? "+" : ""}${pct(c.next - c.prev)}pp`}
                </span>
                {reserves.bindsOn && (
                  <>
                    {" "}
                    <span className="font-semibold text-warning">
                      Binds {longDate(reserves.bindsOn)}.
                    </span>
                  </>
                )}
              </>
            }
          />
        ))}

        {reserves?.terminated.slice(0, 1).map((t) => (
          <Vital
            key={t.label}
            label="Additional TL reserve"
            value="—"
            note={
              <>
                <span className="font-mono">
                  <s className="text-faint">{pct(t.was)}%</s> →{" "}
                  <b className="font-semibold text-foreground">terminated</b>
                </span>
                <br />
                Abolished by the same release that raised the ratios. A rule ending is a rule
                change.
              </>
            }
          />
        ))}
      </Vitals>

      {/* The band prints what it could not read, immediately beneath it — never
          a silent omission, and never buried in a column further down. */}
      {/* Not an error state — a COVERAGE NOTE. The band is not the whole regime,
          and a reader relying on it has to be told so, with a route to the rest.
          Amber (a threshold), not red (a fault): nothing here is broken. */}
      {unread.length > 0 && (
        <div className="grid grid-cols-[20px_1fr] items-baseline gap-x-2.5 border-b border-border border-l-2 border-l-warning bg-warning/[0.07] py-2 pr-3 pl-2.5">
          <span className="font-mono text-[10px] font-semibold text-warning">△</span>
          <p className="text-[12px] leading-snug">
            <b className="font-semibold">
              This is not the whole regime: {unread.length} further rule change
              {unread.length === 1 ? "" : "s"} in the last 12 months
              {unread.length === 1 ? " is" : " are"} in force and not shown above.
            </b>{" "}
            The regulators announced {unread.length === 1 ? "it" : "them"} without publishing the
            numbers in machine-readable form — including{" "}
            <a
              href={unread[0].url}
              target="_blank"
              rel="noopener noreferrer"
              className="font-semibold text-primary"
            >
              {unread[0].title.length > 60 ? `${unread[0].title.slice(0, 58)}…` : unread[0].title}
            </a>{" "}
            ({longDate(unread[0].publishedAt)}). They are listed under{" "}
            <b className="font-semibold">Flags</b>, with links to the source.
          </p>
        </div>
      )}

      {/* The read — a template with computed slots. A hand-written thesis would
          be stale in a week; this one says the same kind of thing next month. */}
      <section className="mt-4 border-b border-border pb-4">
        <span className="font-mono text-[8.5px] tracking-[0.07em] uppercase text-faint">
          The read — computed, not written
        </span>
        <p className="mt-1 max-w-[74ch] text-[17px] leading-snug font-semibold tracking-[-0.01em] text-foreground">
          {corridor && sinceChange != null && lastChange ? (
            <>
              The corridor has not moved in{" "}
              <span className="font-mono tabular-nums">{sinceChange} days</span>
              {held > 0 && (
                <>
                  {" "}
                  — {held} meeting{held === 1 ? "" : "s"} held at{" "}
                  <span className="font-mono tabular-nums">{pct(corridor.policy)}%</span>
                </>
              )}
              .
            </>
          ) : (
            <>The corridor is not stated in the releases we hold.</>
          )}{" "}
          {reserves && bindsIn != null && bindsIn >= 0 && bump != null ? (
            <>
              The rules have. In{" "}
              <span className="font-mono tabular-nums">{bindsIn} day{bindsIn === 1 ? "" : "s"}</span>{" "}
              the reserve requirement on FX deposits rises{" "}
              <span className="font-mono tabular-nums">{pct(bump)}pp</span>
              {reserves.terminated[0] && (
                <>
                  , and the{" "}
                  <span className="font-mono tabular-nums">{pct(reserves.terminated[0].was)}%</span>{" "}
                  add-on it replaced ends the same day
                </>
              )}
              .
            </>
          ) : reserves ? (
            <>The last rule change took effect on {longDate(reserves.decidedAt)}.</>
          ) : null}
        </p>

        <ul className="mt-2.5 grid grid-cols-1 gap-x-6 sm:grid-cols-2 lg:grid-cols-4">
          {[
            corridor && {
              k: "Corridor",
              v: (
                <>
                  {pct(corridor.policy)}% policy
                  {corridor.lending != null && corridor.borrowing != null && (
                    <> · {pct(corridor.lending)}% / {pct(corridor.borrowing)}% overnight</>
                  )}
                  {lastChange && <> — unchanged since {longDate(lastChange.date)}.</>}
                </>
              ),
            },
            reserves?.changes.length && {
              k: "Binding next",
              v: (
                <>
                  {reserves.changes
                    .map((c) => `${pct(c.prev)}→${pct(c.next)}%`)
                    .join(" and ")}
                  {reserves.bindsOn && <>, maintained from {longDate(reserves.bindsOn)}.</>}
                </>
              ),
            },
            {
              k: "Announcements are not rules",
              v: (
                <>
                  The regulators published {win.length} things in 30 days.{" "}
                  {winInstruments.length} of them changed something a bank must obey; the rest are
                  reports, comms and housekeeping.
                </>
              ),
            },
            {
              k: "Not shown here",
              v:
                unread.length > 0 ? (
                  <>
                    {unread.length} further rule change{unread.length === 1 ? "" : "s"} in force —
                    announced without machine-readable numbers. Linked under Flags.
                  </>
                ) : (
                  <>Every rule change in the last 12 months is shown above, with its parameters.</>
                ),
            },
          ]
            .filter(Boolean)
            .map((d) => {
              const row = d as { k: string; v: React.ReactNode };
              return (
                <li key={row.k} className="border-t border-hair pt-1.5 text-[12px] leading-snug text-muted-foreground">
                  <b className="font-semibold text-foreground">{row.k}.</b> {row.v}
                </li>
              );
            })}
        </ul>

        <div className="mt-2.5 border-t border-hair pt-1.5 font-mono text-[8.5px] tracking-[0.05em] uppercase text-faint">
          takeaway = template + computed slots · days_since_rate_change · meetings_held ·
          next_binding_date · unread_rules · no sentence on this page is typed by a person
        </div>
      </section>

      {/* ── evidence ─────────────────────────────────────────────────────── */}

      <div className="mt-7 grid grid-cols-1 gap-x-10 gap-y-6 lg:grid-cols-[5fr_7fr]">
        <div>
          <SecHead
            title="The last 30 days at the regulators"
            meta="everything TCMB and BDDK published · and which of it actually changed a rule"
            className="mb-2"
          />
          <table className="w-full border-collapse">
            <tbody>
              {win.map((it) => {
                const kind = kindOf.get(it)!;
                const inst = isInstrument(kind);
                const unknown = kind === "unclassified";
                return (
                  <tr key={`${it.source}-${it.external_id}`}>
                    <td
                      className={`w-4 border-b border-hair py-1.5 font-mono text-[10px] font-semibold ${
                        inst ? "text-positive" : unknown ? "text-warning" : "text-negative"
                      }`}
                    >
                      {inst ? "✓" : unknown ? "?" : "✕"}
                    </td>
                    <td
                      className={`border-b border-hair py-1.5 text-[12px] ${
                        inst ? "font-semibold text-foreground" : "text-muted-foreground"
                      }`}
                    >
                      {it.title}
                    </td>
                    <td className="border-b border-hair py-1.5 pl-2 text-right font-mono text-[8.5px] whitespace-nowrap text-faint">
                      {it.source.toUpperCase()} · {shortDate(it.published_at)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="mt-2 flex flex-wrap gap-4 font-mono text-[9px] text-faint">
            <span>
              Changed a rule <b className="font-semibold text-foreground">{winInstruments.length}</b>
            </span>
            <span>
              Did not <b className="font-semibold text-foreground">{winNoise.length}</b>
            </span>
            {winUnknown.length > 0 && (
              <span>
                Uncategorised <b className="font-semibold text-warning">{winUnknown.length}</b>
              </span>
            )}
          </div>
          {newestInstrument && newest && newestInstrument !== newest && (
            <p className="mt-1.5 text-[11px] leading-snug text-faint">
              The most recent thing either regulator published ({shortDate(newest)}) did not change
              a rule. The last one that did was{" "}
              <b className="font-semibold text-foreground">{shortDate(newestInstrument)}</b>.
            </p>
          )}
        </div>

        <div>
          <h3 className="text-[12.5px] leading-snug font-semibold text-foreground">
            The policy rate, reconstructed from the press releases — {changes.length} changes in{" "}
            {path.length} decisions
          </h3>
          <span className="mt-0.5 block font-mono text-[8.5px] tracking-[0.07em] uppercase text-faint">
            parsed from news_items.body_text · the page stores every one of these
          </span>
          <PolicyPath path={path} through={anchor} />
          <div className="mt-2 flex flex-wrap gap-4 border-t border-hair pt-1.5 font-mono text-[9px] text-faint">
            <span>
              Decisions <b className="font-semibold text-foreground">{path.length}</b>
            </span>
            <span>
              Changes <b className="font-semibold text-foreground">{changes.length}</b>
            </span>
            {corridor && (
              <span>
                Now <b className="font-semibold text-foreground">{pct(corridor.policy)}%</b>
              </span>
            )}
            {evds && (
              <span>
                EVDS <b className="font-semibold text-foreground">{pct(evds.value)}%</b>{" "}
                {reconciled ? "✓" : "✕"}
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="mt-7 grid grid-cols-1 gap-x-10 gap-y-6 lg:grid-cols-[7fr_5fr]">
        <div>
          <h3 className="text-[12.5px] leading-snug font-semibold text-foreground">
            Decided, then published — the archive&apos;s clock is {meanLag} days slow
          </h3>
          <span className="mt-0.5 block font-mono text-[8.5px] tracking-[0.07em] uppercase text-faint">
            each line runs from the date the board decided (grey) to the date it reached the feed
            (navy) · red = over a year late
          </span>
          <DecisionLag rows={lags} from="2024-05-01" />
          <div className="mt-2 flex flex-wrap gap-4 border-t border-hair pt-1.5 font-mono text-[9px] text-faint">
            <span>
              Numbered decisions <b className="font-semibold text-foreground">{lags.length}</b>
            </span>
            <span>
              Mean lag <b className="font-semibold text-foreground">{meanLag}d</b>
            </span>
            <span>
              Worst <b className="font-semibold text-foreground">{worstLag}d</b>
            </span>
            <span>
              Numbering spans <b className="font-semibold text-foreground">{span.toLocaleString()}</b>
            </span>
          </div>
        </div>

        <div>
          <SecHead
            title="Where Türkiye's newest banks appear first"
            meta="BDDK bank licensing decisions · leasing, factoring, e-money and asset managers are licensed too, and excluded here"
            className="mb-2"
          />
          <table className="w-full border-collapse">
            <thead>
              <tr>
                {["Bank licensing decision", "Taken", "Late"].map((h, i) => (
                  <th
                    key={h}
                    className={`border-b border-foreground pb-1.5 font-mono text-[8.5px] font-normal tracking-[0.07em] uppercase text-faint ${
                      i === 0 ? "text-left" : "pl-2 text-right"
                    }`}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {lic.slice(0, 6).map((r) => (
                <tr key={r.decision.decisionNo}>
                  <td className="border-b border-hair py-1.5">
                    <span className="text-[12.5px] font-medium text-foreground">{r.institution}</span>
                    <span
                      className={`ml-1.5 inline-block border px-1 py-px align-[1px] font-mono text-[9px] font-semibold ${
                        r.ticker
                          ? "border-border text-muted-foreground"
                          : "border-warning text-warning"
                      }`}
                    >
                      {r.ticker ?? "not yet reporting"}
                    </span>
                    <span className="block font-mono text-[9px] text-faint">
                      #{r.decision.decisionNo} · {LICENCE_LABEL[r.kind]}
                    </span>
                  </td>
                  <td className="border-b border-hair py-1.5 pl-2 text-right font-mono text-[11px] tabular-nums text-muted-foreground">
                    {shortDate(r.decision.decidedAt)}
                  </td>
                  <td
                    className={`border-b border-hair py-1.5 pl-2 text-right font-mono text-[11.5px] font-semibold tabular-nums ${
                      r.decision.lagDays > 365 ? "text-negative" : "text-muted-foreground"
                    }`}
                  >
                    {r.decision.lagDays}d
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <SecHead
        title="Flags"
        meta="a rule prints whether or not it fires"
        className="mt-7 mb-2.5"
      />
      <Flags flags={flags} showCleared />

      <Depth meta="the archive — carried over, rekeyed, not removed">
        <Archive rows={rows} held={tcmbTotal + bddkTotal} />

        {residue.length > 0 && (
          <section className="mt-8">
            <SecHead
              title="What the briefing found that this page does not model"
              meta="the residue — kept so the dissolve loses nothing"
              className="mb-2.5"
            />
            <p className="mb-3 max-w-[78ch] text-[12.5px] leading-relaxed text-muted-foreground">
              The band above models the <b className="font-semibold text-foreground">corridor</b>{" "}
              and the <b className="font-semibold text-foreground">reserve requirements</b>, and
              its figures are compiled from the instruments — never from the model. The weekly
              briefing also surfaces licensing, structure and payments items that no cell
              represents, so they are listed here rather than dropped. This is the one place on
              the page where an LLM writes: a bad week costs a paragraph, never a figure.
            </p>
            <div className="grid grid-cols-1 gap-x-10 gap-y-5 lg:grid-cols-3">
              {residue.map((cat) => (
                <div key={cat.name}>
                  <h4 className="font-mono text-[8.5px] tracking-[0.07em] uppercase text-faint">
                    {cat.name}
                  </h4>
                  <table className="mt-1 w-full border-collapse">
                    <tbody>
                      {cat.bullets.slice(0, 5).map((b, i) => (
                        <tr key={i}>
                          <td className="border-b border-hair py-1.5 text-[12px] leading-snug text-muted-foreground">
                            {b.text}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))}
            </div>
          </section>
        )}
      </Depth>

      <Colophon>
        Compiled from news_items ({(tcmbTotal + bddkTotal).toLocaleString()} TCMB + BDDK
        instruments) in D1 · policy rate from EVDS TP.PY.P02.1H, reconciled against the release
        that set it · corridor and reserve ratios parsed from body_text, not from an LLM ·
        decision dates and board-decision numbers parsed from BDDK titles · binding dates quoted
        from the instruments that state them · rules we could not parse are counted, not hidden
        {briefing && (
          <>
            {" "}
            · editorial coverage only (never figures) from the weekly briefing —{" "}
            {briefing.model}, {briefing.item_count} items, {briefing.window_days}-day window,
            generated {longDate(briefing.generated_at.slice(0, 10))}
          </>
        )}
      </Colophon>
    </main>
  );
}
