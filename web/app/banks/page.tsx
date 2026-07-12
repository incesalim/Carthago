/**
 * /banks — the directory of every bank with audit coverage, as a REGISTER.
 *
 * It used to be a wall of 38 near-identical cards. The figures below aren't new
 * extraction: `bankSummaries()` was already fetching total assets (and spending
 * it only on the sort), and the ratio columns come from `heatmapPanel()` — the
 * same cached panel /cross-bank runs on. So the page finally prints what it
 * already knew.
 *
 * Ratios are AT THE RECORD QUARTER, not at each bank's own latest: mixing
 * periods down a column would make the medians meaningless. A bank that has not
 * filed the record quarter shows "—" and an amber period instead.
 */
import type { Metadata } from "next";
import Link from "next/link";
import { bankSummaries } from "@/app/lib/audit";
import { heatmapPanel, latestCommonPeriod } from "@/app/lib/heatmap";
import {
  BANK_NAMES,
  BANK_TYPE_BY_TICKER,
  BANK_TYPE_BADGE_LABELS,
  isPeerExcluded,
} from "@/app/lib/bank_names";
import { Colophon, Depth, DeskHeader, SecHead, Vital, Vitals } from "@/app/components/desk";
import Register, { type RegisterRow } from "./Register";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkish Banks — Financials & Profiles",
  description:
    "Per-bank financials for every bank in Türkiye: balance sheet, income statement, capital, asset quality and profitability from audited BRSA reports.",
  alternates: { canonical: "/banks" },
};

// 10006 State · 10005 Private·Domestic · 10007 Private·Foreign ·
// 10003 Participation · 10004 Dev & Inv.
const GROUP_ORDER = ["10006", "10005", "10007", "10003", "10004"];

/** A bank with fewer than three years on file is a recent entrant, not a gap. */
const YOUNG_QUARTERS = 12;

function quarterLabel(p: string | null | undefined): string {
  const m = p ? /^(\d{4})Q([1-4])$/.exec(p) : null;
  return m ? `Q${m[2]} ${m[1]}` : p || "—";
}

const trn = (v: number) => `₺${(v / 1e9).toFixed(1)}`;

export default async function BanksPage() {
  const [summaries, period] = await Promise.all([bankSummaries(), latestCommonPeriod()]);
  const panel = await heatmapPanel();

  // The recency benchmark: the newest quarter ANY bank has filed.
  const through = summaries.reduce(
    (m, b) => (b.latest_period > m ? b.latest_period : m),
    "",
  );
  // Ratios at the record quarter (the quarter a quorum has filed).
  const record = period ?? through;
  const ratios = new Map(
    panel.filter((r) => r.period === record).map((r) => [r.bank_ticker, r]),
  );

  const rows: RegisterRow[] = summaries.map((b) => {
    const code = BANK_TYPE_BY_TICKER[b.bank_ticker] ?? "other";
    const m = ratios.get(b.bank_ticker);
    return {
      ticker: b.bank_ticker,
      name: BANK_NAMES[b.bank_ticker] ?? b.bank_ticker,
      groupCode: code,
      groupLabel: BANK_TYPE_BADGE_LABELS[code] ?? "Other",
      assets: b.total_assets,
      periods: b.periods,
      latest: b.latest_period,
      roe: m?.roe ?? null,
      npl: m?.npl_ratio ?? null,
      nim: m?.nim ?? null,
      car: m?.car ?? null,
      excluded: isPeerExcluded(b.bank_ticker),
    };
  });

  const groups: [string, string][] = [
    ...GROUP_ORDER.filter((c) => rows.some((r) => r.groupCode === c)),
    ...[...new Set(rows.map((r) => r.groupCode))].filter((c) => !GROUP_ORDER.includes(c)),
  ].map((c) => [c, BANK_TYPE_BADGE_LABELS[c] ?? "Other"]);

  const maxPeriods = Math.max(...rows.map((r) => r.periods), 1);

  // ---- the vitals — aggregates of the directory itself ----------------------
  // Every size figure is over the LENDING banks: Takasbank is a CCP holding
  // member collateral, so folding its balance sheet into "combined assets" or a
  // market share would be a category error (see PEER_EXCLUDED_TICKERS).
  const lenders = rows
    .filter((r) => !r.excluded && r.assets != null)
    .sort((a, b) => (b.assets as number) - (a.assets as number)) as (RegisterRow & {
    assets: number;
  })[];
  const combined = lenders.reduce((s, r) => s + r.assets, 0);
  const top5 = lenders.slice(0, 5).reduce((s, r) => s + r.assets, 0);
  const top5Share = combined > 0 ? (top5 / combined) * 100 : null;
  const largest = lenders[0] ?? null;

  const filed = rows.filter((r) => r.latest === through);
  const late = rows.filter((r) => r.latest !== through);
  const fullRun = rows.filter((r) => r.periods === maxPeriods).length;
  const quarters = rows.reduce((s, r) => s + r.periods, 0);
  const young = rows
    .filter((r) => r.periods < YOUNG_QUARTERS)
    .sort((a, b) => a.periods - b.periods);

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title="Banks"
        record={
          <>
            Record <b className="font-normal text-foreground">{quarterLabel(through)}</b> ·{" "}
            {rows.length} banks · audited BRSA quarterly filings
          </>
        }
        right="every figure computed from source series"
      />

      <SecHead
        title="The vitals"
        meta="coverage · recency · size · depth"
        className="mb-2.5 mt-6"
      />
      <Vitals cols={6}>
        <Vital
          label="Banks covered"
          value={String(rows.length)}
          note={
            <>
              {groups.length} ownership groups — head to head at{" "}
              <Link href="/cross-bank" className="font-semibold text-primary">
                /cross-bank
              </Link>
            </>
          }
        />
        <Vital
          label="Latest audited quarter"
          value={quarterLabel(through)}
          note={
            late.length > 0 ? (
              <>
                {filed.length} of {rows.length} have filed it ·{" "}
                <b className="font-semibold text-warning">
                  {late.map((r) => r.name).join(", ")}
                </b>{" "}
                still on {late[0].latest}
              </>
            ) : (
              `all ${rows.length} banks have filed it`
            )
          }
        />
        <Vital
          label="Combined assets"
          value={combined > 0 ? trn(combined) : "—"}
          unit="trn"
          note={
            largest ? (
              <>
                largest: <b className="font-semibold text-foreground">{largest.name}</b>{" "}
                {trn(largest.assets)} trn
              </>
            ) : (
              "sum of the latest balance sheets"
            )
          }
        />
        <Vital
          label="Top-5 asset share"
          value={top5Share != null ? top5Share.toFixed(1) : "—"}
          unit="%"
          note={`held by ${lenders.slice(0, 5).map((r) => r.ticker).join(" · ")}`}
        />
        <Vital
          label="Bank-quarters archived"
          value={quarters.toLocaleString("en-US")}
          note={`${fullRun} banks carry the full ${maxPeriods}-quarter run`}
        />
        <Vital
          label="Under three years"
          value={String(young.length)}
          note={
            young.length > 0 ? (
              <>
                youngest: <b className="font-semibold text-foreground">{young[0].name}</b> —{" "}
                {young[0].periods} quarters filed
              </>
            ) : (
              "every bank carries three years or more"
            )
          }
        />
      </Vitals>

      {/* ---- the read ---- */}
      {largest && (
        <p className="mt-4 max-w-[82ch] border-l-2 border-foreground pl-3 text-[13.5px] leading-relaxed text-foreground">
          The five largest banks hold{" "}
          <span className="font-mono tabular-nums">{top5Share?.toFixed(1)}%</span> of the{" "}
          <span className="font-mono tabular-nums">{trn(combined)} trn</span> on file, and{" "}
          <b className="font-semibold">{largest.name}</b> alone holds{" "}
          <span className="font-mono tabular-nums">
            {((largest.assets / combined) * 100).toFixed(1)}%
          </span>
          .{" "}
          {late.length === 1 ? (
            <>
              <b className="font-semibold">{late[0].name}</b> is the only bank yet to file{" "}
              {quarterLabel(through)} — it is still on {late[0].latest}.{" "}
            </>
          ) : late.length > 1 ? (
            <>
              <span className="font-mono tabular-nums">{late.length}</span> banks have not filed{" "}
              {quarterLabel(through)} yet.{" "}
            </>
          ) : null}
          {young.length > 0 && (
            <>
              <span className="font-mono tabular-nums">{young.length}</span> banks carry under three
              years of audited history, the youngest being{" "}
              <b className="font-semibold">{young[0].name}</b> at{" "}
              <span className="font-mono tabular-nums">{young[0].periods}</span> quarters.
            </>
          )}
        </p>
      )}

      <Depth meta="the directory, as a register">
        <Register rows={rows} groups={groups} latest={through} maxPeriods={maxPeriods} />

        <div className="flex flex-wrap gap-x-6 gap-y-2 border-t border-hair pt-3">
          <Link href="/disclosures" className="text-[12.5px] font-semibold text-primary">
            Recent KAP disclosures (all banks) →
          </Link>
          <Link href="/regulation" className="text-[12.5px] font-semibold text-primary">
            TCMB &amp; BDDK regulation →
          </Link>
        </div>
      </Depth>

      <Colophon />
    </main>
  );
}
