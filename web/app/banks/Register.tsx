"use client";

/**
 * /banks — the register.
 *
 * The directory used to be 38 near-identical cards: 31 of them printed the same
 * line ("17 quarters · latest 2026Q1"), so the only thing that differed between
 * them was the name. Worse, the page already fetched every bank's total assets
 * and spent it only on sort() — a banking directory that showed no banking data.
 *
 * So: one hairline row per bank, carrying what actually distinguishes them —
 * size, share, returns, asset quality, capital, and how much history is on file.
 * Type to filter, click a column to rank, and the group rules carry each type's
 * asset subtotal and its MEDIAN ratios, so every bank reads against its own
 * peers rather than against the sector.
 *
 * Flags are rules, not decoration: an amber period = has not filed the latest
 * quarter; a short history bar = a young bank; "clearing" = carried but excluded
 * from every share and concentration figure (Takasbank is a CCP, not a lender).
 */
import { Fragment, useMemo, useState } from "react";
import Link from "next/link";
import BankLogo from "@/app/components/BankLogo";
import { median } from "@/app/lib/heatmap-normalize";

export interface RegisterRow {
  ticker: string;
  name: string;
  groupCode: string;
  groupLabel: string;
  /** Latest-period total assets, THOUSAND-TL (null if no balance sheet). */
  assets: number | null;
  /** Quarters of audited history on file. */
  periods: number;
  /** Latest quarter this bank has filed, e.g. "2026Q1". */
  latest: string;
  /** Record-quarter ratios. roe/npl/nim are FRACTIONS; car is in points. */
  roe: number | null;
  npl: number | null;
  nim: number | null;
  car: number | null;
  /** Carried, but out of every peer/share statistic (see PEER_EXCLUDED_TICKERS). */
  excluded: boolean;
}

interface Props {
  rows: RegisterRow[];
  /** Type groups in display order: [code, label]. */
  groups: [string, string][];
  /** The latest quarter anyone has filed — the recency benchmark. */
  latest: string;
  /** Longest run on file, for the history meter. */
  maxPeriods: number;
}

type SortKey = "assets" | "roe" | "npl" | "nim" | "car" | "periods";

/** ONE entry per body cell after the bank name — the header and the row are two
 *  halves of the same column list, so they cannot drift apart. (They did: the
 *  share cell had no header, which shifted every label one column left and made
 *  the table print each bank's share under "ROE".)
 *
 *  `share` sorts by assets: share is assets ÷ a constant, so the orders are
 *  identical, and giving it its own key would just let the two disagree. */
const COLUMNS: { key: SortKey; label: string }[] = [
  { key: "assets", label: "Assets" },
  { key: "assets", label: "Share" },
  { key: "roe", label: "ROE" },
  { key: "npl", label: "NPL" },
  { key: "nim", label: "NIM" },
  { key: "car", label: "CAR" },
  { key: "periods", label: "History" },
];

const bn = (v: number | null) =>
  v == null ? "—" : `₺${(v / 1e6).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
const p1 = (v: number | null) => (v == null ? "—" : `${(v * 100).toFixed(1)}%`);
const p2 = (v: number | null) => (v == null ? "—" : `${(v * 100).toFixed(2)}%`);
/** CAR arrives in percentage POINTS already (audited §4). */
const pts = (v: number | null) => (v == null ? "—" : `${v.toFixed(1)}%`);

export default function Register({ rows, groups, latest, maxPeriods }: Props) {
  const [query, setQuery] = useState("");
  const [grouped, setGrouped] = useState(true);
  const [sortKey, setSortKey] = useState<SortKey>("assets");
  const [sortDir, setSortDir] = useState<-1 | 1>(-1);

  // Share and concentration are over the LENDING banks only — counting a CCP's
  // custody balances as market share would be a category error.
  const total = useMemo(
    () => rows.filter((r) => !r.excluded).reduce((s, r) => s + (r.assets ?? 0), 0),
    [rows],
  );
  const maxAssets = useMemo(
    () => Math.max(...rows.filter((r) => !r.excluded).map((r) => r.assets ?? 0), 1),
    [rows],
  );
  const shareOf = (r: RegisterRow) =>
    r.excluded || r.assets == null || !total ? null : r.assets / total;

  const hits = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (r) =>
        r.name.toLowerCase().includes(q) ||
        r.ticker.toLowerCase().includes(q) ||
        r.groupLabel.toLowerCase().includes(q),
    );
  }, [rows, query]);

  const sort = (list: RegisterRow[]) =>
    [...list].sort((x, y) => {
      const a = x[sortKey];
      const b = y[sortKey];
      if (a == null && b == null) return 0;
      if (a == null) return 1;
      if (b == null) return -1;
      return (a - b) * sortDir;
    });

  const clickSort = (k: SortKey) => {
    if (k === sortKey) setSortDir((d) => (d === -1 ? 1 : -1));
    else {
      setSortKey(k);
      setSortDir(-1);
    }
  };

  const head =
    "border-b border-foreground pb-1.5 font-mono text-[8.5px] font-semibold uppercase tracking-[0.07em] whitespace-nowrap";
  const num = "border-b border-hair py-1.5 px-2.5 text-right font-mono text-[12.5px] tabular-nums";

  /** A bank row. */
  const Row = ({ r, rank }: { r: RegisterRow; rank?: number }) => {
    const share = shareOf(r);
    const tone = (v: number | null) =>
      v == null ? "text-faint" : v < 0 ? "text-negative" : "text-foreground";
    return (
      <tr className="group">
        <td className="border-b border-hair py-1.5 pr-2.5">
          <Link href={`/banks/${r.ticker}`} className="flex items-center gap-2.5" title={`Open ${r.name}`}>
            {rank != null && (
              <span className="w-5 shrink-0 text-right font-mono text-[10px] text-faint">{rank}</span>
            )}
            <span className="flex w-8 shrink-0 justify-center">
              <BankLogo ticker={r.ticker} name={r.name} height={14} maxWidth={26} />
            </span>
            <span className="truncate text-[13px] font-medium text-foreground">{r.name}</span>
            <span className="font-mono text-[9px] text-faint">{r.ticker}</span>
            {!grouped && (
              <span className="hidden font-mono text-[9px] text-faint lg:inline">{r.groupLabel}</span>
            )}
            {r.excluded && (
              <span
                className="font-mono text-[9px] text-warning"
                title="Central clearing / CCP — carried, but excluded from share and concentration stats"
              >
                clearing
              </span>
            )}
            <span
              aria-hidden
              className="font-mono text-[11px] text-primary opacity-0 transition-opacity group-hover:opacity-100"
            >
              →
            </span>
          </Link>
        </td>
        <td className={`${num} text-foreground`}>
          {bn(r.assets)}
          <span className="text-faint"> bn</span>
        </td>
        <td className="border-b border-hair px-2.5 py-1.5">
          <div className="flex items-center justify-end gap-2">
            <span className="h-[5px] w-[78px] shrink-0 overflow-hidden rounded-[1px] bg-hair">
              <span
                className="block h-full bg-data"
                style={{ width: `${((r.excluded ? 0 : (r.assets ?? 0)) / maxAssets) * 100}%` }}
              />
            </span>
            <span className="w-11 text-right font-mono text-[11.5px] tabular-nums text-muted-foreground">
              {share == null ? "—" : `${(share * 100).toFixed(2)}%`}
            </span>
          </div>
        </td>
        <td className={`${num} ${tone(r.roe)}`}>{p1(r.roe)}</td>
        <td className={`${num} ${tone(r.npl)}`}>{p2(r.npl)}</td>
        <td className={`${num} ${tone(r.nim)}`}>{p2(r.nim)}</td>
        <td className={`${num} ${tone(r.car)}`}>{pts(r.car)}</td>
        <td className="border-b border-hair px-2.5 py-1.5">
          <div className="flex items-center justify-end gap-2">
            <span className="h-[5px] w-11 shrink-0 overflow-hidden rounded-[1px] bg-hair">
              <span
                className="block h-full bg-context"
                style={{ width: `${(r.periods / maxPeriods) * 100}%` }}
              />
            </span>
            <span className="w-7 text-right font-mono text-[11.5px] tabular-nums text-muted-foreground">
              {r.periods}q
            </span>
            <span
              title={
                r.latest === latest
                  ? "Has filed the latest audited quarter"
                  : `Has not filed ${latest} yet`
              }
              className={`w-14 text-right font-mono text-[11.5px] tabular-nums ${
                r.latest === latest ? "text-muted-foreground" : "font-semibold text-warning"
              }`}
            >
              {r.latest}
            </span>
          </div>
        </td>
      </tr>
    );
  };

  /** A type rule: the group's asset subtotal, its share, and its MEDIAN ratios. */
  const GroupRule = ({ label, list }: { label: string; list: RegisterRow[] }) => {
    const lend = list.filter((r) => !r.excluded);
    const a = lend.reduce((s, r) => s + (r.assets ?? 0), 0);
    const m = (k: "roe" | "npl" | "nim" | "car") => median(list.map((r) => r[k]));
    const med = "border-b border-hair px-2.5 pb-1 pt-4 text-right font-mono text-[10px] tabular-nums text-muted-foreground";
    return (
      <tr>
        <td className="border-b border-hair pb-1 pr-2.5 pt-4">
          <span className="font-mono text-[8.5px] font-semibold uppercase tracking-[0.09em] text-foreground">
            {label}
          </span>
          <span className="ml-2 font-mono text-[8.5px] text-faint">
            {list.length} bank{list.length > 1 ? "s" : ""}
          </span>
        </td>
        <td className={med}>
          {bn(a)}
          <span className="text-faint"> bn</span>
        </td>
        <td className={med}>{total ? `${((a / total) * 100).toFixed(1)}%` : "—"}</td>
        <td className={med}>{p1(m("roe"))}</td>
        <td className={med}>{p2(m("npl"))}</td>
        <td className={med}>{p2(m("nim"))}</td>
        <td className={med}>{pts(m("car"))}</td>
        <td className={`${med} text-faint`}>median →</td>
      </tr>
    );
  };

  const arrow = (k: SortKey) => (sortKey === k ? (sortDir < 0 ? " ↓" : " ↑") : "");

  return (
    <div>
      <div className="flex flex-wrap items-baseline gap-x-5 gap-y-2 border-b border-hair pb-1.5">
        <h2 className="text-[13.5px] font-bold text-foreground">The register</h2>
        <span className="font-mono text-[8.5px] uppercase tracking-[0.07em] text-faint">
          {query.trim() ? `${hits.length} of ${rows.length} banks` : `all ${rows.length} banks`} ·
          click a column to rank · click a row to open the bank
        </span>
        <span className="ml-auto flex items-center gap-x-5">
          {(
            [
              [true, "By type"],
              [false, "By size"],
            ] as const
          ).map(([g, label]) => (
            <button
              key={label}
              type="button"
              onClick={() => {
                setGrouped(g);
                if (!g) {
                  setSortKey("assets");
                  setSortDir(-1);
                }
              }}
              aria-pressed={grouped === g}
              className={`border-b-[1.5px] pb-0.5 font-mono text-[10.5px] transition-colors ${
                grouped === g
                  ? "border-foreground font-semibold text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              {label}
            </button>
          ))}
          <label className="flex items-center gap-1.5 border-b border-border pb-0.5">
            <span aria-hidden className="text-[11px] text-faint">
              ⌕
            </span>
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="find a bank"
              aria-label="Find a bank"
              className="w-32 bg-transparent font-mono text-[11px] text-foreground placeholder:text-faint focus:outline-none"
            />
          </label>
        </span>
      </div>

      <div className="mt-1 overflow-x-auto">
        <table className="w-full min-w-[940px] border-collapse text-foreground">
          <thead>
            <tr>
              <th className={`${head} pr-2.5 text-left text-faint`}>Bank</th>
              {COLUMNS.map((c) => (
                <th key={c.label} className={`${head} px-2.5 text-right`}>
                  <button
                    type="button"
                    onClick={() => clickSort(c.key)}
                    className={`transition-colors ${
                      sortKey === c.key ? "text-foreground" : "text-faint hover:text-foreground"
                    }`}
                  >
                    {c.label}
                    {arrow(c.key)}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {hits.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-6 text-[12.5px] text-faint">
                  No bank matches “{query}”.
                </td>
              </tr>
            ) : grouped ? (
              groups.map(([code, label]) => {
                const list = hits.filter((r) => r.groupCode === code);
                if (!list.length) return null;
                return (
                  <Fragment key={code}>
                    <GroupRule label={label} list={list} />
                    {sort(list).map((r) => (
                      <Row key={r.ticker} r={r} />
                    ))}
                  </Fragment>
                );
              })
            ) : (
              sort(hits).map((r, i) => <Row key={r.ticker} r={r} rank={i + 1} />)
            )}
          </tbody>
        </table>
      </div>

      <p className="mt-2.5 font-mono text-[8.5px] leading-relaxed tracking-[0.04em] text-faint">
        Group rules carry each type&rsquo;s asset subtotal, its share of the reporting total, and its{" "}
        <b className="font-medium text-muted-foreground">median</b> ROE / NPL / NIM / CAR — so every
        bank reads against its own peers, not the sector. History bar is quarters filed out of{" "}
        {maxPeriods}. An <span className="text-warning">amber period</span> marks a bank that has
        not filed {latest}. Ratios are at the record quarter; a bank that has not filed it shows
        “—”. Takasbank shows no share by rule, not by omission.
      </p>
    </div>
  );
}
