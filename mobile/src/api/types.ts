/**
 * Wire types for /api/app/v1.
 *
 * Hand-written to mirror the route handlers in web/app/api/app/v1/. They are
 * not generated, so they are a CLAIM about the server rather than proof — the
 * contract test in src/api/__tests__ fetches the live endpoints and asserts the
 * fields these declare actually arrive, which is what turns the claim back into
 * something checkable.
 *
 * Every numeric field is `number | null`. A null is not zero: it means the
 * filer disclosed nothing for that cell, and a client that coalesces it to 0
 * prints a confident wrong number. Formatters render null as an em dash.
 */

export interface WirePoint {
  t: string;
  v: number | null;
}

export type Direction = "up" | "down" | "neutral";

export interface Handshake {
  name: string;
  version: number;
  minSupportedClient: number;
  web: string;
  screens: Record<string, string>;
}

export interface Vital {
  key: string;
  label: string;
  value: number | null;
  unit: string;
  decimals: number;
  series: WirePoint[];
  change12: number | null;
  good: Direction;
}

export interface Mover {
  key: string;
  label: string;
  prev: number | null;
  curr: number | null;
  decimals: number;
  good: Direction;
  note: string | null;
}

export interface TransmissionItem {
  key: string;
  label: string;
  value: number | null;
  unit: string | null;
  decimals: number;
  effect: {
    metric: string;
    nominal?: number | null;
    real?: number | null;
    deflator?: number | null;
    deflatorBasis?: string;
    low24m?: number | null;
    href: string;
  };
}

export interface Flag {
  code: string;
  active: boolean;
  /** The rule the flag fired by, printed under it. Never a client-side string. */
  rule: string;
  operands: Record<string, number | null>;
}

export interface StandingRow {
  rank: number;
  ticker: string;
  name: string;
  car: number | null;
}

export interface PulseInsight {
  text?: string;
  tone?: string;
  [k: string]: unknown;
}

export interface Overview {
  record: { period: string | null; label: string; vs: string };
  coverage: { banks: number };
  levels: {
    /** Thousand TL — normalised server-side. The BDDK bulletin this comes from
     *  is denominated in MILLION TL while the audit tables are in thousand;
     *  the route converts so the client has one scale. See `units`. */
    totalAssets: number | null;
    assetsYoY: number | null;
    loansYoY: number | null;
    depositsYoY: number | null;
  };
  units: { amounts: string; rates: string };
  tape: { label: string; value: string | number; changePct: number | null }[];
  vitals: Vital[];
  movers: Mover[];
  transmission: TransmissionItem[];
  flags: Flag[];
  standings: { period: string | null; best: StandingRow[]; thinnest: StandingRow[] };
  pulse: unknown;
  ahead: { kind: string; when: string; date: string; rule: string; record: string | null }[];
}

export interface BankRow {
  ticker: string;
  name: string;
  type: string | null;
  typeLabel: string | null;
  /** True for Takasbank — a CCP whose ratios answer a different question. Never
   *  rank it against deposit-funded lenders. */
  peerExcluded: boolean;
  totalAssets: number | null;
  roe: number | null;
  roeAdjusted: number | null;
  npl: number | null;
  car: number | null;
  cet1: number | null;
  nim: number | null;
  costIncome: number | null;
  periodsHeld: number;
  latestPeriodHeld: string | null;
}

export interface BankList {
  period: string | null;
  /** The whole universe we hold filings for. */
  count: number;
  /** The rankable subset. Rank and colour-scale off this, never off `count`. */
  peers: number;
  rows: BankRow[];
}

/** "pct" = stored as a FRACTION (0.155 → 15.5%); "pts" = already in percentage
 *  POINTS (15.5 → 15.5%). Getting this wrong is a silent 100× error. */
export type MetricUnit = "pct" | "pts" | "trn" | "bn" | "raw" | "mult";

export interface ScorecardMetric {
  key: string;
  label: string;
  short: string;
  unit: MetricUnit;
  decimals: number;
  direction: Direction;
  rule: string | null;
  value: number | null;
  series: WirePoint[];
}

export interface NewsEntry {
  id: string;
  publishedAt: string;
  title: string;
  summary: string | null;
  url: string;
  source: string;
  category: string | null;
  language: string;
  tickers?: string[];
}

export interface BankDetail {
  ticker: string;
  name: string;
  type: string | null;
  typeLabel: string | null;
  peerExcluded: boolean;
  period: string | null;
  coverage: { periodsHeld: number; latestPeriodHeld: string | null };
  /** False for a bank the ratio panel refuses to hold (a CCP). The filings are
   *  real; the peer ratios are simply not computed for it. */
  scorecardAvailable: boolean;
  scorecardNote: string | null;
  scorecard: ScorecardMetric[];
  earningsQuality: {
    roe: number | null;
    roeAdjusted: number | null;
    freeProvision: number | null;
  };
  profile: {
    period: string;
    branchesTotal: number | null;
    branchesDomestic: number | null;
    branchesForeign: number | null;
    personnel: number | null;
  } | null;
  stages: {
    period: string;
    stage1: number | null;
    stage2: number | null;
    stage3: number | null;
    total: number | null;
    coverage1: number | null;
    coverage2: number | null;
    coverage3: number | null;
  } | null;
  news: NewsEntry[];
  web: string;
}

export interface Economy {
  headline: Record<string, number | null>;
  series: Record<string, WirePoint[]>;
  units: Record<string, string>;
  source: string;
}

export interface BriefingCategory {
  name: string;
  bullets: { text: string; source_ids: string[] }[];
}

export interface NewsFeed {
  source: string;
  count: number;
  items: NewsEntry[];
  briefing: {
    generatedAt: string;
    windowDays: number;
    itemCount: number;
    model: string;
    categories: BriefingCategory[];
  } | null;
}
