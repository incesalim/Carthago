/**
 * D1 helper for Server Components and Route Handlers.
 *
 * Use `getDB()` inside server components / route handlers / server actions.
 * Returns the bound D1Database instance from the Cloudflare env.
 */
import { getCloudflareContext } from "@opennextjs/cloudflare";

export async function getDB() {
  const { env } = await getCloudflareContext({ async: true });
  return env.DB;
}

export interface BalanceSheetRow {
  year: number;
  month: number;
  currency: string;
  bank_type_code: string;
  item_order: number;
  item_name: string;
  is_subtotal: number | null;
  amount_tl: number | null;
  amount_fx: number | null;
  amount_total: number | null;
}
