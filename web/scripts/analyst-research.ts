/**
 * Analyst V2 — the research entry point (CI and local).
 *
 * Same staging seam as V1's analyst-run.ts: node:sqlite over the R2-pulled
 * snapshots, bulletin + analyst DBs attached, main shadowing stale copies.
 *
 * Modes:
 *   --scout      deterministic anomaly scout only → scout.json + evidence.jsonl
 *   --research   scout + bounded hypothesis loop + verifier → full artifact set
 *                (LLM keys are CI secrets; locally this degrades to --scout
 *                 unless keys are present)
 *
 * Usage:
 *   npx tsx scripts/analyst-research.ts --bank ALBRK --period 2025Q1 --kind unconsolidated --scout
 *   npx tsx scripts/analyst-research.ts --bank ALBRK --period 2025Q1 --kind unconsolidated --research --out-dir ../data/research
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { DatabaseSync } from "node:sqlite";

import type { Queryable } from "../app/lib/analyst/data";
import { EvidenceLog } from "../app/lib/analyst/v2/evidence";
import { runScout } from "../app/lib/analyst/v2/scout";
import { snapshotIdOf, type FilingTextStore, type ToolContext } from "../app/lib/analyst/v2/tools";

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
      console.warn(`analyst-research: ${file} not attached — its tables read as gaps`);
    }
  };
  attach("data/bddk_data.db", "bulletin");
  attach("data/analyst.db", "analyst");
  return {
    all: async <T>(sql: string, binds: unknown[] = []) =>
      db.prepare(sql).all(...(binds as (string | number | null)[])) as T[],
  };
}

function loadFilingText(root: string, bank: string, period: string, kind: string): FilingTextStore | null {
  const p = resolve(root, `data/filing_text_${bank}_${period}_${kind}.json`);
  if (!existsSync(p)) return null;
  try {
    return JSON.parse(readFileSync(p, "utf-8")) as FilingTextStore;
  } catch {
    console.warn(`analyst-research: ${p} unreadable — source-page tools disabled`);
    return null;
  }
}

async function main(): Promise<number> {
  const bank = arg("bank");
  const period = arg("period");
  const kind = arg("kind") ?? "unconsolidated";
  const root = arg("root") ?? resolve(process.cwd(), "..");
  const outDir = resolve(arg("out-dir") ?? resolve(root, "data/research"));
  if (!bank || !period) {
    console.error("required: --bank TICKER --period YYYYQN [--kind ...] [--scout|--research]");
    return 2;
  }
  mkdirSync(outDir, { recursive: true });

  const db = openStaging(root);
  const ctx: ToolContext = {
    db,
    snapshot: await snapshotIdOf(db),
    log: new EvidenceLog(),
    defaults: { bank, period, kind },
    filingText: loadFilingText(root, bank, period, kind),
  };

  const scout = await runScout(ctx);
  const tag = `${bank}_${period}_${kind}`;
  writeFileSync(resolve(outDir, `scout_${tag}.json`), JSON.stringify(scout, null, 2), "utf-8");
  console.log(
    `scout: ${scout.total_candidates} candidates (top ${scout.candidates.length} kept) → scout_${tag}.json`,
  );
  for (const c of scout.candidates.slice(0, 10)) {
    console.log(`  [${c.score.toFixed(1)}] ${c.source} ${c.statement ?? ""} ${c.row ?? c.metric ?? ""} — ${c.description.slice(0, 110)}`);
  }

  if (has("research")) {
    const { runResearch } = await import("../app/lib/analyst/v2/loop");
    const { verifyFindings } = await import("../app/lib/analyst/v2/verifier");
    const research = await runResearch(ctx, scout, process.env as Record<string, string | undefined>);
    const verification = verifyFindings(research.findings, ctx.log, { bank, period, kind });
    writeFileSync(resolve(outDir, `research_trace_${tag}.jsonl`), research.traceJsonl, "utf-8");
    writeFileSync(resolve(outDir, `hypotheses_${tag}.json`), JSON.stringify(research.hypotheses, null, 2), "utf-8");
    writeFileSync(resolve(outDir, `findings_${tag}.json`), JSON.stringify(research.findings, null, 2), "utf-8");
    writeFileSync(resolve(outDir, `verification_${tag}.json`), JSON.stringify(verification, null, 2), "utf-8");
    writeFileSync(resolve(outDir, `run_metrics_${tag}.json`), JSON.stringify(research.metrics, null, 2), "utf-8");
    const { renderSummary } = await import("../app/lib/analyst/v2/render");
    writeFileSync(resolve(outDir, `analyst_summary_${tag}.md`), renderSummary(research, verification, ctx.log), "utf-8");
    console.log(
      `research: ${research.findings.length} finding(s), ${research.metrics.turns} turns, ` +
        `${research.metrics.tool_calls} tool calls, abstained=${research.abstained} → ${outDir}`,
    );
    const failed = verification.findings.filter((f) => f.verdict === "fail").length;
    console.log(`verification: ${verification.findings.length - failed}/${verification.findings.length} findings pass`);
  }

  writeFileSync(resolve(outDir, `evidence_${tag}.jsonl`), ctx.log.toJsonl(), "utf-8");
  return 0;
}

main().then(
  (code) => process.exit(code),
  (err) => {
    console.error(err);
    process.exit(1);
  },
);
