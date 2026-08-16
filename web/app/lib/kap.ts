/**
 * KAP ownership-structure queries against D1 (`kap_ownership` table).
 *
 * Rows come from each bank's KAP Genel Bilgi Formu §5, refreshed weekly by
 * the bulletin-lane cron (see docs/OPERATIONS.md §KAP ownership). `as_of` is
 * the KAP filing date — ownership rows can be years old if the structure
 * hasn't changed; free-float rows are refreshed near-daily by KAP.
 */
import { cachedAll } from "./db";

export type KapItem =
  | "shareholder"
  | "indirect_shareholder"
  | "free_float"
  | "paid_in_capital"
  | "capital_ceiling"
  | "subsidiary";

export interface KapOwnershipRow {
  item: KapItem;
  seq: number;
  /** Shareholder / subsidiary name, or the share-class ISIN for free_float rows. */
  holder: string | null;
  /** Nominal amount. TL for ownership rows (caveat: in the non-listed form
   *  variant some banks repeat the percentage here — ratio_pct is
   *  authoritative); for subsidiary rows it is in `currency`. */
  share_tl: number | null;
  ratio_pct: number | null;
  voting_pct: number | null;
  as_of: string | null;
  /** subsidiary rows: ISO currency of share_tl (TRY/EUR/USD/…). */
  currency: string | null;
  /** subsidiary rows: scope of activities (Turkish, as filed). */
  activity: string | null;
  /** subsidiary rows: relation type (Bağlı Ortaklık / İştirak / …). */
  relation: string | null;
}

/**
 * A "free float / other" catch-all holder (Turkish "DİĞER" / "HALKA AÇIK").
 * It is the residual of the shareholder grid, not an owner — anything picking
 * "the owner" must skip it (the /banks Desk once crowned Akbank's owner as
 * "DİĞER 59.3%" while Sabancı Holding sat at 40.8%). The AUTHORITATIVE
 * free-float percentage is the separate `free_float` item, not this row.
 */
export function isFreeFloatHolder(name: string | null): boolean {
  const t = (name ?? "").trim().toLocaleUpperCase("tr-TR");
  return t === "DİĞER" || t.includes("HALKA AÇIK") || t.includes("FREE FLOAT");
}

/** Title-case, Turkish-aware (so İ/ı fold correctly). */
function titleCaseTr(s: string): string {
  return s
    .toLocaleLowerCase("tr-TR")
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toLocaleUpperCase("tr-TR") + w.slice(1))
    .join(" ");
}

/** "AK PORTFÖY YÖNETİMİ A.Ş." → "Ak Portföy Yönetimi" — strip the legal suffix,
 *  title-case, and cap to the first few words so it reads as a chip. */
export function holderShortName(name: string | null): string {
  let s = (name ?? "").trim();
  s = s.replace(/\s*ANON[İI]M\s+Ş[İI]RKET[İI]\s*$/giu, "");
  s = s.replace(/\s*A\.?\s*Ş\.?\s*$/iu, "");
  s = titleCaseTr(s);
  const words = s.split(/\s+/).filter(Boolean);
  return words.length > 4 ? `${words.slice(0, 4).join(" ")}…` : s;
}

/** All ownership rows for one bank, grid order preserved. */
export async function bankOwnership(ticker: string): Promise<KapOwnershipRow[]> {
  return cachedAll<KapOwnershipRow>(
    `SELECT item, seq, holder, share_tl, ratio_pct, voting_pct, as_of,
            currency, activity, relation
     FROM kap_ownership
     WHERE bank_ticker = ?
     ORDER BY item, seq`,
    [ticker],
  );
}

export type KapOwnershipRowWithBank = KapOwnershipRow & { bank_ticker: string };

/**
 * Ownership + subsidiary rows for EVERY bank in one query (~330 rows) —
 * feeds buildOwnershipGraph() for the /ownership sector network.
 */
export async function sectorOwnership(): Promise<KapOwnershipRowWithBank[]> {
  return cachedAll<KapOwnershipRowWithBank>(
    `SELECT bank_ticker, item, seq, holder, share_tl, ratio_pct, voting_pct,
            as_of, currency, activity, relation
     FROM kap_ownership
     WHERE item IN ('shareholder', 'indirect_shareholder', 'subsidiary', 'free_float')
     ORDER BY bank_ticker, item, seq`,
    [],
  );
}
