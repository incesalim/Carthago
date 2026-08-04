/**
 * The analyst generation runner — CI's entry point, and the local harness.
 *
 * Runs the SAME web/app/lib/analyst modules the Worker will read from D1, but
 * over the local staging SQLite files via node:sqlite (Node ≥ 22.5; CI and the
 * dev machine are both on Node 24):
 *
 *   main      data/bank_audit.db          (audit lanes — R2-pulled in CI)
 *   ATTACH    data/bddk_data.db           (evds_series, kap_ownership, …)
 *   ATTACH    data/analyst.db             (signals + basis, detect.py --stage)
 *
 * Unqualified table names resolve main-first, so the STALE bank_audit_* copies
 * inside bddk_data.db are shadowed by the snapshot — do not reorder.
 *
 * Modes:
 *   --sections   assemble + print the 11-section JSON (no LLM, runs anywhere)
 *   --prompt     dry run: print the exact system+user messages, no LLM call
 *   --memo       full pipeline: sections → prompt → LLM → guard → memo JSON
 *                (needs OPEN_ROUTER_API / GROQ_API_KEY / CEREBRAS_KEY in env —
 *                 CI secrets; there are NO local keys by design)
 *
 * Usage:
 *   npx tsx scripts/analyst-run.ts --bank SKBNK --period 2026Q1 --kind unconsolidated --sections
 *   npx tsx scripts/analyst-run.ts --bank ALBRK --period 2026Q1 --kind unconsolidated --memo --out memo.json
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { DatabaseSync } from "node:sqlite";

import { buildComparatives } from "../app/lib/analyst/comparator";
import type { Queryable } from "../app/lib/analyst/data";
import { buildPeerContext } from "../app/lib/analyst/peers";
import { buildAnalystSections } from "../app/lib/analyst/sections";
import { fetchSeriesBundle } from "../app/lib/analyst/series";

function arg(name: string): string | undefined {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 ? process.argv[i + 1] : undefined;
}
const has = (name: string) => process.argv.includes(`--${name}`);

function openStaging(root: string): Queryable {
  const db = new DatabaseSync(resolve(root, "data/bank_audit.db"), { readOnly: true });
  const attach = (file: string, alias: string) => {
    try {
      db.exec(`ATTACH DATABASE 'file:${resolve(root, file).replace(/\\/g, "/")}?mode=ro' AS ${alias}`);
    } catch {
      console.warn(`analyst-run: ${file} not attached (absent) — its tables read as gaps`);
    }
  };
  attach("data/bddk_data.db", "bulletin");
  attach("data/analyst.db", "analyst");
  return {
    all: async <T>(sql: string, binds: unknown[] = []) =>
      db.prepare(sql).all(...(binds as (string | number | null)[])) as T[],
  };
}

async function main(): Promise<number> {
  const bank = arg("bank");
  const period = arg("period");
  const kind = arg("kind") ?? "unconsolidated";
  const root = arg("root") ?? resolve(process.cwd(), "..");
  if (!bank || !period) {
    console.error("required: --bank TICKER --period YYYYQN [--kind consolidated|unconsolidated]");
    return 2;
  }

  const db = openStaging(root);
  const bundle = await fetchSeriesBundle(db, bank, kind);
  const [sections, peersCtx] = await Promise.all([
    buildAnalystSections(db, bank, period, kind, bundle),
    buildPeerContext(db, bank, period, kind),
  ]);
  const comparatives = buildComparatives(bundle, period);

  if (has("prompt")) {
    const { buildMemoMessages } = await import("../app/lib/analyst/prompt");
    const msgs = buildMemoMessages({ sections, peers: peersCtx, comparatives });
    console.log("──── SYSTEM ────\n" + msgs.system + "\n──── USER ────\n" + msgs.user);
    return 0;
  }

  if (has("sections") || !has("memo")) {
    const out = JSON.stringify({ sections, peers: peersCtx, comparatives }, null, 2);
    const dest = arg("out");
    if (dest) {
      mkdirSync(dirname(resolve(dest)), { recursive: true });
      writeFileSync(dest, out, "utf-8");
      console.log(`sections written: ${dest}`);
    } else {
      console.log(out);
    }
    return 0;
  }

  // --memo: sections → prompt → LLM → guard. Imported lazily so --sections
  // never needs the LLM modules to resolve env keys.
  const { generateMemo } = await import("../app/lib/analyst/runner");
  const memo = await generateMemo(
    { sections, peers: peersCtx, comparatives },
    process.env as Record<string, string | undefined>,
  );
  const dest = arg("out") ?? `data/analyst_memo_${bank}_${period}_${kind}.json`;
  mkdirSync(dirname(resolve(dest)), { recursive: true });
  writeFileSync(dest, JSON.stringify(memo, null, 2), "utf-8");
  console.log(
    `memo ${memo.fact_check_passed ? "PASSED" : "FAILED"} fact-check ` +
      `(model ${memo.model ?? "none"}, ${memo.dropped_paragraphs} dropped ¶) → ${dest}`,
  );
  return memo.fact_check_passed ? 0 : 1;
}

main().then(
  (code) => process.exit(code),
  (err) => {
    console.error(err);
    process.exit(1);
  },
);
