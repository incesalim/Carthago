/**
 * /regulation — what the rules are, and what changed.
 *
 * Three layers, and the page never blurs them:
 *
 *   COMPILED     the state band and the loan growth caps are parsed from the
 *                instruments' own text; the policy rate is reconciled against
 *                EVDS. No figure here comes from a language model.
 *   SYNTHESIZED  the changelog is written from those same instruments by the
 *                weekly briefing model. Every claim carries the instrument it
 *                cites — an uncited claim is not published — and where the
 *                parser has read the same figure the two are compared: a match
 *                prints ✓, a conflict prints ✗ with what the instrument says.
 *   ABSENT       capital-adequacy and credit-card rules are published in BDDK
 *                Tebliğ / Resmî Gazete, which this site does not ingest. Their
 *                sections are shown empty rather than estimated.
 *
 * Balance-sheet consequences (what reserves cost, how the corridor transmits)
 * belong on /liquidity, /rates and /deposits — not here.
 *
 * Design + rationale: docs/knowledge/regulation-tab-redesign-v4-2026-07-13.md
 */
import type { Metadata } from "next";
import Link from "next/link";
import { latestRegulationBriefing, newsLookupBySourceIds, newsSourceSummary, type NewsItem } from "@/app/lib/news";
import { Colophon, Depth, DeskHeader, SecHead, Vital, Vitals } from "@/app/components/desk";
import { signed } from "@/app/lib/prose";
import {
  bankNames,
  buildChangelog,
  classifyInstrument,
  decisionLags,
  deriveCorridor,
  derivePolicyPath,
  deriveGrowthCaps,
  deriveReserves,
  licences,
  meetingsHeld,
  parseBoardDecision,
  policyRateFromEvds,
  rateChanges,
  regulationFeed,
  reserveCellLabel,
  reserveRatioSeries,
  type ChangeRow,
  type InstrumentKind,
  type LicenceKind,
} from "@/app/lib/regulation";
import Archive, { type ArchiveRow } from "./Archive";
import PolicyPath from "./PolicyPath";
import ReserveRatio from "./ReserveRatio";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkish Banking Regulation — the rules, and what changed",
  description:
    "The policy corridor, reserve requirements and loan growth caps Turkish banks comply with today, and every rule change dated and linked to the instrument that made it.",
  alternates: { canonical: "/regulation" },
};

const MONTHS = ["", "January", "February", "March", "April", "May", "June", "July",
  "August", "September", "October", "November", "December"];
const SHORT = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function shortDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? `${Number(m[3])} ${SHORT[Number(m[2])]}` : iso.slice(0, 10);
}
function longDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? `${Number(m[3])} ${SHORT[Number(m[2])]} ${m[1]}` : iso;
}
const pct = (v: number) => v.toFixed(v % 1 === 0 ? 0 : 2);
const cap = (v: number) => (v % 1 === 0 ? String(v) : v.toFixed(1));

const LICENCE_LABEL: Record<LicenceKind, string> = {
  operating: "operating licence",
  establishment: "permission to establish",
  revocation: "licence revoked",
};

/** Shortened section names for the changelog's category chips. */
const CHIP: Record<string, { label: string; cls: string }> = {
  "Monetary Policy Stance": { label: "Corridor", cls: "border-data text-data" },
  "Loan Growth Caps": { label: "Loan caps", cls: "border-chart-5 text-chart-5" },
  "Regulations on RRs": { label: "Reserves", cls: "border-chart-4 text-chart-4" },
  "Regulations for TL Deposit Share": { label: "TL share", cls: "border-border text-muted-foreground" },
  "Other Regulatory Actions": { label: "Other", cls: "border-border text-muted-foreground" },
};

export default async function RegulationPage() {
  const [feed, evds, banks, summary, briefing, ratios] = await Promise.all([
    regulationFeed(),
    policyRateFromEvds(),
    bankNames(),
    newsSourceSummary(),
    latestRegulationBriefing(),
    reserveRatioSeries(),
  ]);

  const corridor = deriveCorridor(feed);
  const reserves = deriveReserves(feed);
  const caps = deriveGrowthCaps(feed);
  const path = derivePolicyPath(feed);
  const changes = rateChanges(path);
  const held = meetingsHeld(path);
  const lastChange = changes[changes.length - 1] ?? null;
  const reconciled =
    corridor != null && evds != null ? Math.abs(corridor.policy - evds.value) < 0.01 : false;

  // The changelog: the briefing's claims, re-keyed on the date of the instrument
  // each one cites. An uncited claim is dropped — a model sentence a reader
  // cannot check is not something to publish.
  const lookup = briefing
    ? await newsLookupBySourceIds(
        briefing.categories.flatMap((c) =>
          c.bullets.flatMap((b) =>
            b.source_ids.map((id) => {
              const [source, external_id] = id.split(":", 2);
              return { source, external_id };
            }),
          ),
        ),
      )
    : new Map();
  const changelog = buildChangelog(briefing, lookup, corridor, reserves, caps);
  const nAgree = changelog.filter((r) => r.agrees).length;
  const nConflict = changelog.filter((r) => r.conflicts).length;

  const byMonth = new Map<string, ChangeRow[]>();
  for (const r of changelog) {
    const k = r.date.slice(0, 7);
    if (!byMonth.has(k)) byMonth.set(k, []);
    byMonth.get(k)!.push(r);
  }

  const sections = new Map<string, ChangeRow[]>();
  for (const r of changelog) {
    if (!sections.has(r.category)) sections.set(r.category, []);
    sections.get(r.category)!.push(r);
  }

  const lags = decisionLags(feed);
  const meanLag = lags.length ? Math.round(lags.reduce((s, r) => s + r.lagDays, 0) / lags.length) : 0;
  const lic = licences(lags, banks);

  const tcmbTotal = summary.find((s) => s.source === "tcmb")?.total ?? 0;
  const bddkTotal = summary.find((s) => s.source === "bddk")?.total ?? 0;
  const heldTotal = tcmbTotal + bddkTotal;

  const kindOf = new Map<NewsItem, InstrumentKind>(feed.map((it) => [it, classifyInstrument(it)]));
  const rows: ArchiveRow[] = feed
    .map((item) => {
      const d = parseBoardDecision(item.title);
      const pub = item.published_at.slice(0, 10);
      return {
        item,
        kind: kindOf.get(item)!,
        decidedAt: d?.decidedAt ?? pub,
        decidedIsFallback: d == null,
        lagDays: d ? Math.round((Date.parse(pub) - Date.parse(d.decidedAt)) / 86_400_000) : null,
        decisionNo: d?.decisionNo ?? null,
      };
    })
    .sort((a, b) => b.decidedAt.localeCompare(a.decidedAt))
    .slice(0, 220)
    .map((r, i) => (i < 120 ? r : { ...r, item: { ...r.item, body_text: null } }));

  const consumerCap = caps?.caps.find((c) => c.label === "General-purpose & vehicle") ?? caps?.caps[0];
  const anchor = feed[0]?.published_at.slice(0, 10) ?? null;
  const lastRule = feed.find((it) => {
    const k = kindOf.get(it);
    return k === "rule" || k === "rate";
  })?.published_at.slice(0, 10);

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title="Regulation"
        record={
          <>
            In force <b className="font-normal text-foreground">{anchor ? longDate(anchor) : "—"}</b>
            {lastRule && (
              <> · last rule change <b className="font-normal text-foreground">{shortDate(lastRule)}</b></>
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
        title="The state today"
        meta="parsed from the instruments · policy rate reconciled against EVDS"
        className="mt-6 mb-2.5"
      />

      <Vitals cols={6}>
        <Vital
          label="Policy rate"
          value={corridor ? pct(corridor.policy) : "—"}
          unit={corridor ? "%" : undefined}
          note={
            corridor ? (
              <>
                {held > 0 && <>Held <b className="font-semibold text-foreground">{held} meetings</b>. </>}
                {lastChange && <>Last change {longDate(lastChange.date)}.</>}
                {evds && !reconciled && (
                  <span className="font-semibold text-negative"> EVDS reports {pct(evds.value)}%.</span>
                )}
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
                {/* The lending leg sits above policy by construction, so this is "+" today
                    — but the sign comes off the number, not the template. */}
                <b className="font-semibold text-foreground">
                  {signed(
                    Math.round((corridor.lending - corridor.policy) * 100),
                    (v) => `${v}bp`,
                  )}
                </b>{" "}
                over the policy rate.
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
                Corridor{" "}
                <b className="font-semibold text-foreground">
                  {Math.round((corridor.lending - corridor.borrowing) * 100)}bp
                </b>{" "}
                wide.
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
                </span>
                {reserves.bindsOn && (
                  <>
                    {" "}
                    <span className="font-semibold text-warning">Binds {longDate(reserves.bindsOn)}.</span>
                  </>
                )}
              </>
            }
          />
        ))}

        {consumerCap && (
          <Vital
            label="Consumer loan cap"
            value={cap(consumerCap.next)}
            unit="%"
            note={
              <>
                <span className="font-mono">
                  <s className="text-faint">{cap(consumerCap.prev)}%</s> →{" "}
                  <b className="font-semibold text-foreground">{cap(consumerCap.next)}%</b>
                </span>{" "}
                over 8 weeks. <a href="#caps" className="font-semibold text-primary">All caps →</a>
              </>
            }
          />
        )}
      </Vitals>

      {/* ── loan growth caps ─────────────────────────────────────────────── */}
      {caps && caps.caps.length > 0 && (
        <>
          <div id="caps" className="scroll-mt-4">
            <SecHead
              title="Loan growth caps"
              meta="8-week limits · a bank exceeding one holds additional reserves"
              className="mt-7 mb-2.5"
            />
          </div>
          <div className="grid grid-cols-1 gap-x-10 gap-y-5 lg:grid-cols-2">
            <table className="w-full border-collapse self-start">
              <thead>
                <tr>
                  {["8-week growth limit", "Was", "Now", "Δ"].map((h, i) => (
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
                {caps.caps.map((c) => (
                  <tr key={c.label}>
                    <td className="border-b border-hair py-1.5 text-[12.5px] font-medium text-foreground">
                      {c.label}
                    </td>
                    <td className="border-b border-hair py-1.5 pl-2 text-right font-mono text-[11px] tabular-nums text-faint">
                      <s>{cap(c.prev)}%</s>
                    </td>
                    <td className="border-b border-hair py-1.5 pl-2 text-right font-mono text-[12.5px] font-semibold tabular-nums text-foreground">
                      {cap(c.next)}%
                    </td>
                    <td className="border-b border-hair py-1.5 pl-2 text-right font-mono text-[11px] tabular-nums text-muted-foreground">
                      {c.next > c.prev ? "+" : "−"}
                      {cap(Math.abs(c.next - c.prev))}pp
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div>
              <p className="mb-2 text-[12px] leading-relaxed text-muted-foreground">
                The caps apply to a <b className="font-semibold text-foreground">restricted base</b>:
                export, investment, agriculture, tradesmen, KOSGEB and CGF loans are exempt, and the
                limits are enforced <b className="font-semibold text-foreground">bank by bank</b>.
              </p>
              <p className="mb-2 text-[12px] leading-relaxed text-muted-foreground">
                <b className="font-semibold text-foreground">
                  Sector loan growth is therefore not comparable with these limits.
                </b>{" "}
                Compared directly, sector growth exceeds them in most weeks — a consequence of the
                exempt base, not a breach.
              </p>
              <p className="text-[12px] leading-relaxed">
                <a
                  href={caps.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-semibold text-primary"
                >
                  {caps.title}, {longDate(caps.decidedAt)} ↗
                </a>
              </p>
            </div>
          </div>
        </>
      )}

      {/* ── the changelog ────────────────────────────────────────────────── */}
      {changelog.length > 0 && (
        <>
          <SecHead
            title="What changed"
            meta={`${changelog.length} rule changes · newest first · each links to the instrument that made it`}
            className="mt-7 mb-2.5"
          />

          <div className="border-t-2 border-b border-foreground border-b-hair py-1.5 text-[11.5px] text-muted-foreground">
            Written from the instruments by{" "}
            <b className="font-semibold text-foreground">{briefing?.model}</b> · every claim carries
            its source ·{" "}
            <span className="mx-0.5 inline-block border border-positive px-1 font-mono text-[8.5px] font-semibold text-positive">
              ✓ {nAgree}
            </span>{" "}
            match the parameter parsed from the instrument ·{" "}
            <span className="mx-0.5 inline-block border border-negative px-1 font-mono text-[8.5px] font-semibold text-negative">
              ✗ {nConflict}
            </span>{" "}
            {nConflict === 1 ? "conflicts" : "conflict"} with it
          </div>

          {[...byMonth.entries()].map(([ym, items]) => (
            <div key={ym} className="border-b border-border py-3">
              <h4 className="mb-1.5 text-[12px] font-bold text-foreground">
                {MONTHS[Number(ym.slice(5, 7))]} {ym.slice(0, 4)}
                <span className="ml-1.5 font-mono text-[8.5px] font-normal tracking-[0.07em] uppercase text-faint">
                  {items.length} change{items.length === 1 ? "" : "s"}
                </span>
              </h4>
              <ul>
                {items.map((r, i) => {
                  const chip = CHIP[r.category] ?? {
                    label: "Other",
                    cls: "border-border text-muted-foreground",
                  };
                  const day = Number(r.date.slice(8, 10));
                  const mon = SHORT[Number(r.date.slice(5, 7))];
                  return (
                    <li
                      key={`${r.date}-${i}`}
                      className="grid grid-cols-[46px_1fr] items-baseline gap-x-2.5 border-t border-hair py-1.5 sm:grid-cols-[46px_72px_1fr]"
                    >
                      <span className="font-mono text-[10px] font-semibold whitespace-nowrap text-muted-foreground">
                        {day} {mon}
                      </span>
                      <span
                        className={`hidden border px-1 py-px text-center font-mono text-[8px] font-semibold tracking-[0.06em] whitespace-nowrap uppercase sm:inline-block ${chip.cls}`}
                      >
                        {chip.label}
                      </span>
                      <span className="col-span-2 text-[12.5px] leading-snug text-foreground sm:col-span-1">
                        {r.text}
                        {r.agrees && (
                          <span
                            className="ml-1.5 inline-block border border-positive px-1 font-mono text-[8.5px] font-semibold whitespace-nowrap text-positive"
                            title="Matches the parameter parsed from the instrument."
                          >
                            ✓ {r.agrees}
                          </span>
                        )}
                        {r.conflicts && (
                          <span
                            className="ml-1.5 inline-block border border-negative px-1 font-mono text-[8.5px] font-semibold whitespace-nowrap text-negative"
                            title="Conflicts with the parameter parsed from the instrument."
                          >
                            ✗ {r.conflicts}
                          </span>
                        )}
                        <a
                          href={r.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="mt-0.5 block font-mono text-[8.5px] font-semibold tracking-[0.04em] uppercase text-primary"
                        >
                          {r.title} ↗
                        </a>
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </>
      )}

      {/* ── two instruments, drawn ───────────────────────────────────────── */}
      <div className="mt-7 grid grid-cols-1 gap-x-10 gap-y-7 lg:grid-cols-2">
        <div>
          <h3 className="text-[12.5px] leading-snug font-semibold text-foreground">
            The policy rate has changed {changes.length} times since {path[0]?.date.slice(0, 4)}
          </h3>
          <span className="mt-0.5 block font-mono text-[8.5px] tracking-[0.07em] uppercase text-faint">
            one-week repo auction rate · EVDS TP.PY.P02.1H
          </span>
          <PolicyPath path={path} through={anchor ?? new Date().toISOString().slice(0, 10)} />
          <div className="mt-2 flex flex-wrap gap-4 border-t border-hair pt-1.5 font-mono text-[9px] text-faint">
            <span>Changes <b className="font-semibold text-foreground">{changes.length}</b></span>
            {corridor && <span>Now <b className="font-semibold text-foreground">{pct(corridor.policy)}%</b></span>}
            {held > 0 && <span>Held <b className="font-semibold text-foreground">{held} meetings</b></span>}
          </div>
        </div>

        <div>
          <h3 className="text-[12.5px] leading-snug font-semibold text-foreground">
            Reserves held against deposits — the lira ratio has risen from near zero since 2022
          </h3>
          <span className="mt-0.5 block font-mono text-[8.5px] tracking-[0.07em] uppercase text-faint">
            required reserves ÷ deposits, weekly · what banks hold, not what the rule states
          </span>
          <ReserveRatio series={ratios} />
          <div className="mt-2 flex flex-wrap gap-4 border-t border-hair pt-1.5 font-mono text-[9px] text-faint">
            {ratios.at(-1)?.fx != null && (
              <span>FX <b className="font-semibold text-foreground">{ratios.at(-1)!.fx!.toFixed(1)}%</b></span>
            )}
            {ratios.at(-1)?.tl != null && (
              <span>TL <b className="font-semibold text-foreground">{ratios.at(-1)!.tl!.toFixed(1)}%</b></span>
            )}
            {ratios[0]?.tl != null && (
              <span>
                TL in {ratios[0].date.slice(0, 4)}{" "}
                <b className="font-semibold text-foreground">{ratios[0].tl!.toFixed(2)}%</b>
              </span>
            )}
          </div>
        </div>
      </div>

      {/* ── in force, by section ─────────────────────────────────────────── */}
      {sections.size > 0 && (
        <>
          <SecHead
            title="In force, by section"
            meta={`the same ${changelog.length} rules, grouped for reference`}
            className="mt-7 mb-2.5"
          />
          <div className="grid grid-cols-1 gap-x-8 gap-y-5 sm:grid-cols-2 xl:grid-cols-3">
            {[...sections.entries()].map(([name, items]) => (
              <div key={name}>
                <h4 className="mb-1 text-[11.5px] font-bold text-foreground">
                  {name}
                  <span className="ml-1 font-mono text-[8.5px] font-normal text-faint">{items.length}</span>
                </h4>
                <ul>
                  {items.map((r, i) => (
                    <li
                      key={i}
                      className="border-t border-hair py-1.5 text-[11.5px] leading-snug text-muted-foreground"
                    >
                      {r.text.length > 150 ? `${r.text.slice(0, 148)}…` : r.text}
                      <span className="ml-1 font-mono text-[8.5px] whitespace-nowrap text-faint">
                        {shortDate(r.date)}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}

            {/* Named, not estimated. These rules live in BDDK Tebliğ / Resmî
                Gazete, which this site does not ingest. */}
            {[
              {
                t: "Capital adequacy",
                d: "Risk weights, FX-rate forbearance in credit-risk calculations, capital floors and buffers.",
              },
              {
                t: "Credit cards",
                d: "Maximum contractual and overdue interest by balance tier, minimum-payment ratios, installment and limit rules.",
              },
            ].map((s) => (
              <div key={s.t} className="border-l-2 border-border pl-3">
                <h4 className="mb-1 text-[11.5px] font-bold text-faint">
                  {s.t}
                  <span className="ml-1.5 border border-negative px-1 py-px font-mono text-[8px] font-semibold tracking-[0.06em] uppercase text-negative">
                    no source
                  </span>
                </h4>
                <p className="text-[11.5px] leading-snug text-faint">
                  {s.d} Published in{" "}
                  <b className="font-semibold text-muted-foreground">BDDK Tebliğ / Resmî Gazete</b>,
                  which this site does not ingest. Left empty rather than estimated.
                </p>
              </div>
            ))}
          </div>
        </>
      )}

      {/* ── ahead / licensing / related ──────────────────────────────────── */}
      <div className="mt-7 grid grid-cols-1 gap-x-10 gap-y-6 lg:grid-cols-3">
        <div>
          <SecHead title="What binds next" meta="dates the instruments state" className="mb-2" />
          <table className="w-full border-collapse">
            <tbody>
              {reserves?.bindsOn && (
                <tr>
                  <td className="border-b border-hair py-1.5 pr-3 font-mono text-[10.5px] font-semibold whitespace-nowrap text-foreground">
                    {shortDate(reserves.bindsOn)}
                  </td>
                  <td className="border-b border-hair py-1.5 text-[12px] text-muted-foreground">
                    <b className="font-semibold text-foreground">FX reserve ratios</b> rise to{" "}
                    {reserves.changes.map((c) => `${pct(c.next)}%`).join(" and ")}
                    {reserves.terminated[0] && (
                      <>; the {pct(reserves.terminated[0].was)}% additional lira reserve on FX deposits ends</>
                    )}
                    .
                  </td>
                </tr>
              )}
              <tr>
                <td className="border-b border-hair py-1.5 pr-3 font-mono text-[10.5px] font-semibold text-foreground">
                  —
                </td>
                <td className="border-b border-hair py-1.5 text-[12px] text-muted-foreground">
                  Next MPC meeting —{" "}
                  <b className="font-semibold text-foreground">the calendar is not held on this site.</b>
                </td>
              </tr>
              <tr>
                <td className="border-b border-hair py-1.5 pr-3 font-mono text-[10.5px] font-semibold text-foreground">
                  —
                </td>
                <td className="border-b border-hair py-1.5 text-[12px] text-muted-foreground">
                  BDDK board decisions — no announced publication cadence.
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div>
          <SecHead
            title="Newly licensed banks"
            meta="BDDK licensing · not yet in the sector figures"
            className="mb-2"
          />
          <table className="w-full border-collapse">
            <tbody>
              {lic.slice(0, 5).map((r) => (
                <tr key={r.decision.decisionNo}>
                  <td className="border-b border-hair py-1.5">
                    <span className="text-[12.5px] font-medium text-foreground">{r.institution}</span>
                    <span
                      className={`ml-1.5 inline-block border px-1 py-px align-[1px] font-mono text-[9px] font-semibold ${
                        r.ticker ? "border-border text-muted-foreground" : "border-warning text-warning"
                      }`}
                    >
                      {r.ticker ?? "not yet reporting"}
                    </span>
                    <span className="block font-mono text-[9px] text-faint">
                      #{r.decision.decisionNo} · {LICENCE_LABEL[r.kind]}
                    </span>
                  </td>
                  <td className="border-b border-hair py-1.5 pl-2 text-right font-mono text-[11.5px] font-semibold whitespace-nowrap tabular-nums text-muted-foreground">
                    {r.decision.lagDays}d
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-[12px] leading-snug text-muted-foreground">
            A licence appears here before the bank files its first statement. The lag is the time
            from the board&apos;s decision to its publication.
          </p>
        </div>

        <div>
          <SecHead title="Related" meta="what these rules do to the sector" className="mb-2" />
          <p className="text-[12px] leading-relaxed text-muted-foreground">
            Reserves held at the central bank, the pass-through from the policy rate into deposit
            and loan pricing, and the FX-protected deposit stock are covered on{" "}
            <Link href="/liquidity" className="font-semibold text-primary">Liquidity</Link>,{" "}
            <Link href="/rates" className="font-semibold text-primary">Rates</Link> and{" "}
            <Link href="/deposits" className="font-semibold text-primary">Deposits</Link>.
          </p>
        </div>
      </div>

      <Depth meta="the archive">
        <p className="mb-3 max-w-[80ch] text-[12px] leading-relaxed text-muted-foreground">
          {heldTotal.toLocaleString()} releases, dated by the day the decision was taken. BDDK
          publishes its board decisions a mean of{" "}
          <b className="font-semibold text-foreground">{meanLag} days</b> after taking them, in
          irregular batches — a decision surfacing this month may be over a year old. Open any row
          to read the regulator&apos;s own words.
        </p>
        <Archive rows={rows} held={heldTotal} />
      </Depth>

      <Colophon>
        The state band and the loan growth caps are parsed from the instruments&apos; own text; the
        policy rate is reconciled against EVDS TP.PY.P02.1H
        {briefing && (
          <>
            {" "}· the changelog is written from those instruments by {briefing.model} over{" "}
            {briefing.item_count} releases, every claim source-linked and cross-checked against the
            parsed parameter where one exists ({nAgree} match, {nConflict} conflicts)
          </>
        )}{" "}
        · capital-adequacy and credit-card rules are published in BDDK Tebliğ / Resmî Gazete, which
        this site does not ingest, and are left empty · reserves ÷ deposits from the weekly BDDK
        bulletin · decision dates parsed from BDDK titles
      </Colophon>
    </main>
  );
}
