/**
 * Ownership-graph model + radial layout for the KAP ownership visualizations
 * (per-bank map on /banks/[ticker], sector network on /ownership).
 *
 * Pure isomorphic TS — no "use client", no db imports — so the graph can be
 * built in a server component and the layout re-computed client-side.
 *
 * Holder names come from KAP filings verbatim and are NOT normalized across
 * banks ("T.C. HAZİNESİ" vs "Hazine ve Maliye Bakanlığı"), so cross-bank
 * identity goes through `normalizeHolderKey` + the alias maps below. Alias and
 * entity matching is EXACT-match on the normalized key, never substring — the
 * İş Bankası pension fund ("T.İŞ BANKASI A.Ş.MENS.MUNZ.SOS.GÜV.VE YAR.SAN.
 * VAKFI") would otherwise be mistaken for the bank itself.
 */
import type { KapOwnershipRow, KapOwnershipRowWithBank } from "./kap";
import { BANK_NAMES, BANK_TYPE_BY_TICKER } from "./bank_names";

// ---------------------------------------------------------------------------
// Graph model
// ---------------------------------------------------------------------------

export interface GraphLeaf {
  /** Unique within one bank: `${item}:${seq}` (PK order from the filing). */
  id: string;
  kind: "holder" | "sub";
  /** Short display label (canonical name for aliased entities). */
  label: string;
  fullName: string;
  ratioPct: number | null;
  votingPct: number | null;
  /** Nominal capital share — TL for holders, `currency` for subsidiaries. */
  shareAmt: number | null;
  currency: string | null;
  activity: string | null;
  relation: string | null;
  asOf: string | null;
  /** Canonical key when the entity appears under ≥2 banks (sector view). */
  sharedKey?: string;
  /** Ticker when the entity is itself one of our banks. */
  bankRef?: string;
  /** The per-bank "Diğer" grid row — never merged across banks. */
  isOther?: boolean;
  /** Leaves folded into a "+N more" aggregate node (dense fans only). */
  collapsed?: GraphLeaf[];
}

export interface GraphBank {
  ticker: string;
  name: string;
  typeCode: string | undefined;
  freeFloatPct: number | null;
  holders: GraphLeaf[];
  subs: GraphLeaf[];
  /** Indirect (ultimate) holders — listed in the details panel, not fanned. */
  indirect: { fullName: string; ratioPct: number | null }[];
}

export interface SharedHolderLink {
  ticker: string;
  kind: "holder" | "sub";
  ratioPct: number | null;
}

export interface SharedHolder {
  key: string;
  label: string;
  links: SharedHolderLink[];
}

/** Bank-to-bank ownership: `from` owns a stake in `to`. */
export interface BankEdge {
  from: string;
  to: string;
  /** Which side filed it: a holder row of `to`, or a subsidiary row of `from`. */
  kind: "holder" | "sub";
  ratioPct: number | null;
}

export interface OwnershipGraph {
  banks: GraphBank[];
  sharedHolders: SharedHolder[];
  bankEdges: BankEdge[];
}

// ---------------------------------------------------------------------------
// Holder-name normalization
// ---------------------------------------------------------------------------

/** Whitespace-collapse + Turkish-aware uppercase + trailing-punct strip. */
export function normalizeHolderKey(name: string): string {
  return name
    .trim()
    .replace(/\s+/g, " ")
    .toLocaleUpperCase("tr-TR")
    .replace(/[.,;]+$/, "");
}

/**
 * Spelling variants → canonical normalized key. Only entities verified to
 * appear under ≥2 banks with different spellings in `kap_ownership`.
 */
const HOLDER_ALIASES: Record<string, string> = {
  // Treasury (canonical: KLNMA/VAKBN spelling)
  "HAZİNE VE MALİYE BAKANLIĞI": "T.C. HAZİNE VE MALİYE BAKANLIĞI",
  "T.C. HAZİNESİ": "T.C. HAZİNE VE MALİYE BAKANLIĞI",
  // Interbank Card Center (BKM)
  "BANKALAR ARASI KART MERKEZİ A.Ş": "BANKALARARASI KART MERKEZİ A.Ş",
  "BANKALARARASI KART.MERK.A.Ş": "BANKALARARASI KART MERKEZİ A.Ş",
  // Takasbank
  "TAKASBANK İSTANBUL TAKAS VE SAKLAMA BANKASI A.Ş":
    "İSTANBUL TAKAS VE SAKLAMA BANKASI A.Ş",
  // Central bank
  "T.C.MERKEZ BANKASI A.Ş": "TÜRKİYE CUMHURİYET MERKEZ BANKASI A.Ş",
};

/** Friendly display names for the best-known shared entities. */
const CANONICAL_LABELS: Record<string, string> = {
  "T.C. HAZİNE VE MALİYE BAKANLIĞI": "T.C. Hazine ve Maliye Bakanlığı",
  "TÜRKİYE VARLIK FONU": "Türkiye Varlık Fonu",
  "BANKALARARASI KART MERKEZİ A.Ş": "Bankalararası Kart Merkezi (BKM)",
  "İSTANBUL TAKAS VE SAKLAMA BANKASI A.Ş": "Takasbank",
  "TÜRKİYE CUMHURİYET MERKEZ BANKASI A.Ş": "TCMB",
  "KREDİ GARANTİ FONU A.Ş": "Kredi Garanti Fonu",
  "KREDİ KAYIT BÜROSU A.Ş": "Kredi Kayıt Bürosu",
  "BORSA İSTANBUL A.Ş": "Borsa İstanbul",
  "JCR AVRASYA DERECELENDİRME A.Ş": "JCR Avrasya",
  "İHRACATI GELİŞTİRME A.Ş": "İhracatı Geliştirme A.Ş.",
  "BİRLEŞİK İPOTEK FİNANSMANI A.Ş": "Birleşik İpotek Finansmanı",
  "İŞ FİNANSAL KİRALAMA A.Ş": "İş Finansal Kiralama",
};

/**
 * Entities that ARE one of our banks (normalized key → ticker). Exact match
 * only — see the pension-fund caveat in the module docstring.
 */
const ENTITY_TO_TICKER: Record<string, string> = {
  "T.C. ZİRAAT BANKASI A.Ş": "ZIRAAT",
  "TÜRKİYE İŞ BANKASI A.Ş": "ISCTR",
  "TÜRKİYE VAKIFLAR BANKASI T.A.O": "VAKBN",
  "TÜRKİYE SINAİ KALKINMA BANKASI A.Ş": "TSKB",
  "ARAP-TÜRK BANKASI A.Ş": "ATBANK",
};

const isToplam = (h: string | null) => /^toplam$/i.test((h ?? "").trim());
const isDiger = (h: string | null) =>
  (h ?? "").trim().toLocaleUpperCase("tr-TR") === "DİĞER";

// ---------------------------------------------------------------------------
// Per-bank node building (shared by OwnershipRadial and the sector graph)
// ---------------------------------------------------------------------------

function rowToLeaf(r: KapOwnershipRow, kind: "holder" | "sub"): GraphLeaf {
  const other = kind === "holder" && isDiger(r.holder);
  return {
    id: `${r.item}:${r.seq}`,
    kind,
    label: other ? "Other / free float" : (r.holder ?? "—"),
    fullName: other ? "Other / free float" : (r.holder ?? "—"),
    ratioPct: r.ratio_pct,
    votingPct: r.voting_pct,
    shareAmt: r.share_tl,
    currency: r.currency,
    activity: r.activity,
    relation: r.relation,
    asOf: r.as_of,
    ...(other ? { isOther: true } : {}),
  };
}

/** Leaf groups for one bank's rows (TOPLAM dropped, ratio-desc sorted). */
export function buildBankNodes(rows: KapOwnershipRow[]): {
  holders: GraphLeaf[];
  subs: GraphLeaf[];
  indirect: { fullName: string; ratioPct: number | null }[];
  freeFloatPct: number | null;
} {
  const byRatioDesc = (a: GraphLeaf, b: GraphLeaf) =>
    (b.ratioPct ?? -1) - (a.ratioPct ?? -1);

  const holders = rows
    .filter((r) => r.item === "shareholder" && !isToplam(r.holder))
    .map((r) => rowToLeaf(r, "holder"))
    .sort(byRatioDesc);
  const subs = rows
    .filter((r) => r.item === "subsidiary" && !isToplam(r.holder))
    .map((r) => rowToLeaf(r, "sub"))
    .sort(byRatioDesc);
  const indirect = rows
    .filter((r) => r.item === "indirect_shareholder" && !isToplam(r.holder))
    .map((r) => ({ fullName: r.holder ?? "—", ratioPct: r.ratio_pct }));
  const freeFloat = rows.filter((r) => r.item === "free_float");
  return {
    holders,
    subs,
    indirect,
    freeFloatPct: freeFloat[0]?.ratio_pct ?? null,
  };
}

// ---------------------------------------------------------------------------
// Sector graph
// ---------------------------------------------------------------------------

/**
 * Build the cross-bank graph: per-bank leaf groups, shared entities
 * (normalized name under ≥2 banks), and bank-to-bank ownership edges.
 */
export function buildOwnershipGraph(
  rows: KapOwnershipRowWithBank[],
): OwnershipGraph {
  const byBank = new Map<string, KapOwnershipRow[]>();
  for (const r of rows) {
    const list = byBank.get(r.bank_ticker) ?? [];
    list.push(r);
    byBank.set(r.bank_ticker, list);
  }

  const banks: GraphBank[] = [];
  const bankEdges: BankEdge[] = [];
  // normalized key → { label, links } accumulated over every leaf
  const entityLinks = new Map<
    string,
    { label: string; links: SharedHolderLink[] }
  >();

  const dataTickers = new Set(byBank.keys());

  for (const [ticker, bankRows] of byBank) {
    const { holders, subs, indirect, freeFloatPct } = buildBankNodes(bankRows);

    for (const leaf of [...holders, ...subs]) {
      if (leaf.isOther) continue;
      const raw = normalizeHolderKey(leaf.fullName);
      const key = HOLDER_ALIASES[raw] ?? raw;

      const refTicker = ENTITY_TO_TICKER[key];
      if (refTicker) {
        leaf.bankRef = refTicker;
        leaf.label = BANK_NAMES[refTicker] ?? leaf.label;
        // holder row of `ticker` = refTicker owns ticker; subsidiary row the
        // other way around.
        bankEdges.push(
          leaf.kind === "holder"
            ? { from: refTicker, to: ticker, kind: "holder", ratioPct: leaf.ratioPct }
            : { from: ticker, to: refTicker, kind: "sub", ratioPct: leaf.ratioPct },
        );
        continue;
      }

      const entry = entityLinks.get(key) ?? {
        label: CANONICAL_LABELS[key] ?? leaf.fullName,
        links: [],
      };
      entry.links.push({ ticker, kind: leaf.kind, ratioPct: leaf.ratioPct });
      entityLinks.set(key, entry);
      leaf.sharedKey = key; // pruned below if single-bank
    }

    banks.push({
      ticker,
      name: BANK_NAMES[ticker] ?? ticker,
      typeCode: BANK_TYPE_BY_TICKER[ticker],
      freeFloatPct,
      holders,
      subs,
      indirect,
    });
  }

  // A stake filed by BOTH sides (TSKB lists İş Bankası as holder; İş Bankası
  // lists TSKB as subsidiary) produces two edges for one relationship — keep
  // the holder-side one (the owned bank's shareholder grid is the ≥5% view).
  const edgeByPair = new Map<string, BankEdge>();
  for (const e of bankEdges) {
    const k = `${e.from}→${e.to}`;
    const prev = edgeByPair.get(k);
    if (!prev || (prev.kind === "sub" && e.kind === "holder")) edgeByPair.set(k, e);
  }
  const dedupedEdges = [...edgeByPair.values()];

  // Keep only entities connected to ≥2 distinct banks.
  const sharedHolders: SharedHolder[] = [];
  const sharedKeys = new Set<string>();
  for (const [key, { label, links }] of entityLinks) {
    if (new Set(links.map((l) => l.ticker)).size >= 2) {
      sharedKeys.add(key);
      sharedHolders.push({ key, label, links });
    }
  }
  for (const b of banks) {
    for (const leaf of [...b.holders, ...b.subs]) {
      if (leaf.sharedKey && !sharedKeys.has(leaf.sharedKey)) {
        delete leaf.sharedKey;
      }
    }
  }
  sharedHolders.sort((a, b) => b.links.length - a.links.length);

  // Banks referenced only by an edge (ATBANK files no KAP form but İş Bankası
  // reports a 20.58% stake) still get a hollow node.
  for (const e of dedupedEdges) {
    for (const t of [e.from, e.to]) {
      if (!dataTickers.has(t) && !banks.some((b) => b.ticker === t)) {
        banks.push({
          ticker: t,
          name: BANK_NAMES[t] ?? t,
          typeCode: BANK_TYPE_BY_TICKER[t],
          freeFloatPct: null,
          holders: [],
          subs: [],
          indirect: [],
        });
      }
    }
  }

  banks.sort((a, b) => a.ticker.localeCompare(b.ticker));
  return { banks, sharedHolders, bankEdges: dedupedEdges };
}

// ---------------------------------------------------------------------------
// Radial fan layout (per-bank map + sector focus mode)
// ---------------------------------------------------------------------------

export interface PlacedLeaf {
  leaf: GraphLeaf;
  x: number;
  y: number;
  /** Node circle radius (∝ √ratio). */
  r: number;
  labelX: number;
  labelY: number;
  anchor: "start" | "middle" | "end";
}

export interface RadialLayout {
  width: number;
  height: number;
  cx: number;
  cy: number;
  top: PlacedLeaf[];
  bottom: PlacedLeaf[];
}

export const RADIAL_WIDTH = 900;
const BASE_R = 180;
const ROW_GAP = 80;
const LABEL_PAD = 52;
const EMPTY_DEPTH = 110;
const MIN_SEP_DEG = 11;

export function nodeRadius(ratioPct: number | null): number {
  if (ratioPct == null) return 4;
  return 4 + 10 * Math.sqrt(Math.min(Math.max(ratioPct, 0), 100) / 100);
}

export function trimLabel(s: string, max = 22): string {
  return s.length > max ? s.slice(0, max - 1).trimEnd() + "…" : s;
}

/** Fan one side's leaves across [a0,a1] degrees (0°=east, y-down). */
function fanSide(
  leaves: GraphLeaf[],
  a0: number,
  a1: number,
  cx: number,
  cy: number,
): { placed: PlacedLeaf[]; depth: number } {
  if (leaves.length === 0) return { placed: [], depth: EMPTY_DEPTH };

  const span = a1 - a0;
  const maxPerRing = Math.floor(span / MIN_SEP_DEG);
  // Fold overflow beyond 3 rings into one "+N more" node (not reachable with
  // current data — max fan is 25 — but keeps the layout total).
  let fanned = leaves;
  const cap = 3 * maxPerRing;
  if (leaves.length > cap) {
    const kept = leaves.slice(0, cap - 1);
    const rest = leaves.slice(cap - 1);
    fanned = [
      ...kept,
      {
        id: `${rest[0].kind}:more`,
        kind: rest[0].kind,
        label: `+${rest.length} more`,
        fullName: `${rest.length} further holdings`,
        ratioPct: null,
        votingPct: null,
        shareAmt: null,
        currency: null,
        activity: null,
        relation: null,
        asOf: null,
        collapsed: rest,
      },
    ];
  }

  const n = fanned.length;
  const ringCount = Math.min(3, Math.ceil(n / maxPerRing));
  const placed: PlacedLeaf[] = fanned.map((leaf, i) => {
    const deg = a0 + ((i + 0.5) * span) / n;
    const rad = (deg * Math.PI) / 180;
    const ring = i % ringCount;
    const radius = BASE_R + ring * ROW_GAP;
    const x = cx + radius * Math.cos(rad);
    const y = cy + radius * Math.sin(rad);
    const r = nodeRadius(leaf.ratioPct);
    const labelDist = radius + r + 9;
    const cos = Math.cos(rad);
    return {
      leaf,
      x,
      y,
      r,
      labelX: cx + labelDist * Math.cos(rad),
      labelY: cy + labelDist * Math.sin(rad),
      anchor: cos < -0.15 ? "end" : cos > 0.15 ? "start" : "middle",
    };
  });
  return { placed, depth: BASE_R + (ringCount - 1) * ROW_GAP + LABEL_PAD };
}

/**
 * Holders fan the top arc, subsidiaries the bottom; a side with no leaves
 * collapses to a shallow band so the SVG isn't half blank (15 banks file no
 * §7 subsidiaries grid).
 */
export function layoutRadial(
  holders: GraphLeaf[],
  subs: GraphLeaf[],
): RadialLayout {
  const cx = RADIAL_WIDTH / 2;
  // Two passes: depths depend on ring counts only, so compute with cy=0 then
  // shift the real cy in.
  const topDry = fanSide(holders, -160, -20, cx, 0);
  const bottomDry = fanSide(subs, 20, 160, cx, 0);
  const cy = topDry.depth;
  const height = topDry.depth + bottomDry.depth;
  const shift = (p: PlacedLeaf): PlacedLeaf => ({
    ...p,
    y: p.y + cy,
    labelY: p.labelY + cy,
  });
  return {
    width: RADIAL_WIDTH,
    height,
    cx,
    cy,
    top: topDry.placed.map(shift),
    bottom: bottomDry.placed.map(shift),
  };
}

// ---------------------------------------------------------------------------
// Sector overview layout (banks on a circle, shared entities inside)
// ---------------------------------------------------------------------------

export interface NetworkBankNode {
  ticker: string;
  name: string;
  typeCode: string | undefined;
  hasData: boolean;
  nHolders: number;
  nSubs: number;
  x: number;
  y: number;
  labelX: number;
  labelY: number;
  anchor: "start" | "middle" | "end";
}

export interface NetworkSharedNode {
  key: string;
  label: string;
  links: SharedHolderLink[];
  x: number;
  y: number;
}

export interface NetworkLayout {
  size: number;
  banks: NetworkBankNode[];
  shared: NetworkSharedNode[];
}

export const NETWORK_SIZE = 1000;
const NETWORK_R = 340;
/** Type-group order around the circle: State, Private, Foreign, Part., D&I. */
export const GROUP_ORDER = ["10006", "10005", "10007", "10003", "10004"];

export function layoutNetwork(graph: OwnershipGraph): NetworkLayout {
  const size = NETWORK_SIZE;
  const R = NETWORK_R;
  const c = size / 2;
  const ordered = [...graph.banks].sort((a, b) => {
    const ga = GROUP_ORDER.indexOf(a.typeCode ?? "");
    const gb = GROUP_ORDER.indexOf(b.typeCode ?? "");
    return ga !== gb ? ga - gb : a.ticker.localeCompare(b.ticker);
  });

  const angleOf = new Map<string, number>();
  const banks: NetworkBankNode[] = ordered.map((b, i) => {
    const rad = -Math.PI / 2 + (2 * Math.PI * i) / ordered.length;
    angleOf.set(b.ticker, rad);
    const x = c + R * Math.cos(rad);
    const y = c + R * Math.sin(rad);
    const cos = Math.cos(rad);
    const labelDist = R + 22;
    return {
      ticker: b.ticker,
      name: b.name,
      typeCode: b.typeCode,
      hasData: b.holders.length + b.subs.length > 0,
      nHolders: b.holders.length,
      nSubs: b.subs.length,
      x,
      y,
      labelX: c + labelDist * Math.cos(rad),
      labelY: c + labelDist * Math.sin(rad),
      anchor: cos < -0.2 ? "end" : cos > 0.2 ? "start" : "middle",
    };
  });

  // Shared entities sit between the center and the angular centroid of their
  // banks; near-zero centroids (banks on opposite sides) fall back to a small
  // inner ring spread by index.
  const shared: NetworkSharedNode[] = graph.sharedHolders.map((s, i) => {
    const tickers = [...new Set(s.links.map((l) => l.ticker))];
    let vx = 0;
    let vy = 0;
    for (const t of tickers) {
      const a = angleOf.get(t);
      if (a == null) continue;
      vx += Math.cos(a);
      vy += Math.sin(a);
    }
    const len = Math.hypot(vx, vy);
    let x: number;
    let y: number;
    if (len < 0.35) {
      const a = -Math.PI / 2 + (2 * Math.PI * i) / graph.sharedHolders.length;
      x = c + 90 * Math.cos(a);
      y = c + 90 * Math.sin(a);
    } else {
      const reach = R * (0.35 + 0.18 * Math.min(len / tickers.length, 1));
      x = c + (vx / len) * reach;
      y = c + (vy / len) * reach;
    }
    return { key: s.key, label: s.label, links: s.links, x, y };
  });

  // A few relaxation passes to keep shared nodes from stacking.
  const MIN_D = 46;
  for (let pass = 0; pass < 6; pass++) {
    for (let i = 0; i < shared.length; i++) {
      for (let j = i + 1; j < shared.length; j++) {
        const a = shared[i];
        const b = shared[j];
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const d = Math.hypot(dx, dy) || 1;
        if (d < MIN_D) {
          const push = (MIN_D - d) / 2;
          const ux = dx / d;
          const uy = dy / d;
          a.x -= ux * push;
          a.y -= uy * push;
          b.x += ux * push;
          b.y += uy * push;
        }
      }
    }
  }

  return { size, banks, shared };
}
