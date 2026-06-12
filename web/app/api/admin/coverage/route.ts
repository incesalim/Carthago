/**
 * GET /api/admin/coverage — read the audit coverage matrix. Admin-gated.
 *   (no params)                  → { types }
 *   ?type=<key>&kind=<kind>      → { types, grid }
 *   ?cell=BANK|PERIOD|KIND       → { detail }
 * Backed by the bank_audit_expected / _statement_types / _coverage tables
 * (scripts/sync_audit_expected.py). Read-only — re-extraction goes via /dispatch.
 */
import { requireAdminOr403 } from "@/app/lib/admin-auth";
import { coverageCellDetail, coverageGrid, statementTypes } from "@/app/lib/coverage";

export const dynamic = "force-dynamic";

const KINDS = new Set(["consolidated", "unconsolidated"]);

export async function GET(req: Request) {
  const gate = await requireAdminOr403();
  if ("response" in gate) return gate.response;

  const url = new URL(req.url);
  const cell = url.searchParams.get("cell");
  if (cell) {
    const parts = cell.split("|");
    if (parts.length !== 3 || !KINDS.has(parts[2])) {
      return Response.json({ error: "cell must be BANK|PERIOD|KIND" }, { status: 400 });
    }
    const [bank, period, kind] = parts;
    return Response.json({ detail: await coverageCellDetail(bank, period, kind) });
  }

  const types = await statementTypes();
  const type = url.searchParams.get("type");
  const kind = url.searchParams.get("kind");
  if (type && kind) {
    if (!KINDS.has(kind)) {
      return Response.json({ error: "unknown kind" }, { status: 400 });
    }
    return Response.json({ types, grid: await coverageGrid(type, kind) });
  }
  return Response.json({ types });
}
