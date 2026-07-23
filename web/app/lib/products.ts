/**
 * Product-shelf benchmark: which bank offers which products, every "has it"
 * backed by the bank's own published page. Reads the frozen research snapshot in
 * D1 (tables from web/migrations/0034_bank_products.sql, loaded by
 * src/products/build.py). Powers /products.
 *
 * The shape returned here mirrors the standalone benchmark payload so the client
 * matrix can render one bank × 100-attribute grid with a cell→evidence and a
 * bank→profile detail. Two numbers are kept deliberately separate (see the
 * report's §2.2): evidence COVERAGE (how much we could verify — about us) and
 * verified SHELF breadth (about the bank). Penetration is computed only for
 * attributes with a large-enough denominator, for the same selection-bias reason.
 */
import { cachedAll } from "./db";
import { bankDisplayName } from "./bank_names";

export type CellValue = "yes" | "partial" | "no" | "unknown";

export interface ProductAttr {
  code: string;
  block: string;
  blockName: string;
  label: string;
  distinctive: boolean;
  order: number;
  yes: number;
  no: number;
  partial: number;
  unknown: number;
  /** verified penetration = (yes + 0.5*partial)/verified, or null if too thin. */
  pen: number | null;
  /** true when enough banks were verified to trust the penetration figure. */
  enough: boolean;
}

export interface ProductBank {
  ticker: string;
  name: string;
  cluster: string;
  shelf: number;
  coverage: number;
  yes: number;
  no: number;
  partial: number;
  unknown: number;
  shelfNotes: string | null;
  distinctive: string[];
  cells: Record<string, { v: CellValue; url: string | null }>;
}

export interface ProductBenchmark {
  snapshot: string | null;
  nBanks: number;
  nAttrs: number;
  nCells: number;
  nUrls: number;
  minVer: number;
  blocks: { id: string; name: string }[];
  clusters: string[];
  attrs: ProductAttr[];
  banks: ProductBank[];
}

// Benchmark peer-cluster display order (matches src/products/labels_en.py).
const CLUSTER_ORDER = [
  "State deposit",
  "Large private",
  "Foreign — large",
  "Foreign — mid",
  "Private — mid",
  "Participation — private",
  "Participation — state",
  "Digital deposit",
  "Digital participation",
  "Specialist / niche",
];

interface AttrRow {
  code: string;
  block: string;
  block_name_en: string;
  label_en: string;
  is_distinctive: number;
  sort_order: number;
}
interface ProfileRow {
  bank_ticker: string;
  snapshot_date: string;
  cluster_en: string;
  shelf: number;
  coverage: number;
  n_yes: number;
  n_no: number;
  n_partial: number;
  n_unknown: number;
  shelf_notes_en: string | null;
  distinctive_en: string | null;
}
interface CellRow {
  bank_ticker: string;
  attr_code: string;
  value: CellValue;
  evidence_url: string | null;
}

export async function getProductBenchmark(): Promise<ProductBenchmark> {
  const [attrRows, profileRows, cellRows] = await Promise.all([
    cachedAll<AttrRow>(
      `SELECT code, block, block_name_en, label_en, is_distinctive, sort_order
         FROM product_attributes
        ORDER BY sort_order`,
    ),
    cachedAll<ProfileRow>(
      `SELECT bank_ticker, snapshot_date, cluster_en, shelf, coverage,
              n_yes, n_no, n_partial, n_unknown, shelf_notes_en, distinctive_en
         FROM bank_product_profile
        WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM bank_product_profile)`,
    ),
    cachedAll<CellRow>(
      `SELECT bank_ticker, attr_code, value, evidence_url
         FROM bank_products
        WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM bank_products)`,
    ),
  ]);

  if (!profileRows.length || !attrRows.length) {
    return {
      snapshot: null, nBanks: 0, nAttrs: attrRows.length, nCells: 0, nUrls: 0,
      minVer: 0, blocks: [], clusters: [], attrs: [], banks: [],
    };
  }

  const nBanks = profileRows.length;
  const minVer = Math.floor(0.7 * nBanks);

  // cells → nested per bank, and per-attribute tallies for penetration.
  const cellsByBank: Record<string, Record<string, { v: CellValue; url: string | null }>> = {};
  const tally: Record<string, Record<CellValue, number>> = {};
  let nUrls = 0;
  const seenUrl = new Set<string>();
  for (const r of cellRows) {
    (cellsByBank[r.bank_ticker] ??= {})[r.attr_code] = { v: r.value, url: r.evidence_url };
    const t = (tally[r.attr_code] ??= { yes: 0, no: 0, partial: 0, unknown: 0 });
    t[r.value] += 1;
    if (r.evidence_url && !seenUrl.has(r.evidence_url)) {
      seenUrl.add(r.evidence_url);
      nUrls += 1;
    }
  }

  const attrs: ProductAttr[] = attrRows.map((a) => {
    const t = tally[a.code] ?? { yes: 0, no: 0, partial: 0, unknown: 0 };
    const ver = t.yes + t.no + t.partial;
    return {
      code: a.code,
      block: a.block,
      blockName: a.block_name_en,
      label: a.label_en,
      distinctive: a.is_distinctive === 1,
      order: a.sort_order,
      yes: t.yes, no: t.no, partial: t.partial, unknown: t.unknown,
      pen: ver ? (t.yes + 0.5 * t.partial) / ver : null,
      enough: ver >= minVer,
    };
  });

  const banks: ProductBank[] = profileRows
    .map((p) => ({
      ticker: p.bank_ticker,
      name: bankDisplayName(p.bank_ticker),
      cluster: p.cluster_en,
      shelf: p.shelf,
      coverage: p.coverage,
      yes: p.n_yes, no: p.n_no, partial: p.n_partial, unknown: p.n_unknown,
      shelfNotes: p.shelf_notes_en,
      distinctive: safeParse(p.distinctive_en),
      cells: cellsByBank[p.bank_ticker] ?? {},
    }))
    .sort((a, b) => b.shelf - a.shelf);

  const blocks = dedupeBlocks(attrs);
  const clusters = CLUSTER_ORDER.filter((c) => banks.some((b) => b.cluster === c));

  return {
    snapshot: profileRows[0]?.snapshot_date ?? null,
    nBanks,
    nAttrs: attrs.length,
    nCells: cellRows.length,
    nUrls,
    minVer,
    blocks,
    clusters,
    attrs,
    banks,
  };
}

function safeParse(s: string | null): string[] {
  if (!s) return [];
  try {
    const v = JSON.parse(s);
    return Array.isArray(v) ? v.map(String) : [];
  } catch {
    return [];
  }
}

function dedupeBlocks(attrs: ProductAttr[]): { id: string; name: string }[] {
  const seen = new Set<string>();
  const out: { id: string; name: string }[] = [];
  for (const a of attrs) {
    if (!seen.has(a.block)) {
      seen.add(a.block);
      out.push({ id: a.block, name: a.blockName });
    }
  }
  return out;
}
