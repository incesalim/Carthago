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
  | "capital_ceiling";

export interface KapOwnershipRow {
  item: KapItem;
  seq: number;
  /** Shareholder name, or the share-class ISIN ticker for free_float rows. */
  holder: string | null;
  /** Nominal TL. Caveat: in the non-listed form variant some banks repeat
   *  the percentage here (e.g. Ziraat files 100) — ratio_pct is authoritative. */
  share_tl: number | null;
  ratio_pct: number | null;
  voting_pct: number | null;
  as_of: string | null;
}

/** All ownership rows for one bank, grid order preserved. */
export async function bankOwnership(ticker: string): Promise<KapOwnershipRow[]> {
  return cachedAll<KapOwnershipRow>(
    `SELECT item, seq, holder, share_tl, ratio_pct, voting_pct, as_of
     FROM kap_ownership
     WHERE bank_ticker = ?
     ORDER BY item, seq`,
    [ticker],
  );
}
