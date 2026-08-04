/**
 * Analyst V2 — renderer. Prose is the LAST step and only for findings that
 * survived verification; everything it prints is a restatement of structured,
 * checked content. Rejected findings and the investigation trace stay in the
 * artifacts, never on a public page.
 */
import type { EvidenceLog } from "./evidence";
import type { ResearchResult } from "./loop";
import type { VerificationReport } from "./verifier";

export function renderSummary(
  research: ResearchResult,
  verification: VerificationReport,
  log: EvidenceLog,
): string {
  const out: string[] = [];
  const verdictOf = (id: string) => verification.findings.find((v) => v.finding_id === id)?.verdict ?? "fail";
  const passing = research.findings.filter((f) => verdictOf(f.finding_id) !== "fail");
  const failed = research.findings.filter((f) => verdictOf(f.finding_id) === "fail");

  out.push(`# Analyst research summary`);
  out.push("");
  if (research.abstained || passing.length === 0) {
    out.push(`**Abstention.** ${research.abstain_reason ?? "No finding survived verification."}`);
    out.push("");
    out.push(`The investigation ran ${research.metrics.turns} turns and ${research.metrics.tool_calls} tool calls; ` +
      `${research.hypotheses.length} hypothesis(es) were worked, none produced a verified material story. ` +
      `An ordinary quarter is a valid result.`);
  } else {
    out.push(`**${passing.length} verified finding(s)** (of ${research.findings.length} emitted; automated checks, not a human review).`);
    out.push("");
    for (const f of passing) {
      const v = verdictOf(f.finding_id);
      out.push(`## ${f.finding_id} — ${f.classification}${v === "flag" ? " · ⚠ flagged" : ""} · confidence ${f.confidence}`);
      out.push("");
      out.push(f.thesis);
      out.push("");
      out.push(`*Why it matters:* ${f.materiality_rationale}`);
      out.push("");
      for (const c of f.claims) {
        const bits = [
          c.subject.statement ?? "", c.subject.row ?? c.subject.metric ?? "",
          c.value != null ? `= ${c.value}${c.unit ? ` ${c.unit}` : ""}` : "",
          c.comparison ? `${c.comparison.op} ${c.comparison.rhs_value}` : "",
          c.change ? `${c.change.from_value} → ${c.change.to_value} (Δ ${c.change.delta})` : "",
        ].filter(Boolean).join(" · ");
        out.push(`- ${c.claim_id} [${c.claim_kind}] ${bits} — evidence: ${c.evidence_ids.join(", ")}`);
      }
      if (f.counterevidence?.length) {
        out.push("");
        out.push(`*Counterevidence considered:* ${f.counterevidence.map((c) => c.note).join(" · ")}`);
      }
      if (f.caveats?.length) out.push(`*Caveats:* ${f.caveats.join(" · ")}`);
      if (f.missing?.length) out.push(`*Not held:* ${f.missing.join(" · ")}`);
      if (f.source_pages?.length) out.push(`*Filing pages:* ${f.source_pages.join(", ")}`);
      out.push("");
    }
  }

  if (failed.length) {
    out.push(`---`);
    out.push(`${failed.length} finding(s) FAILED verification and are excluded above (details in verification.json):`);
    for (const f of failed) {
      const v = verification.findings.find((x) => x.finding_id === f.finding_id);
      const why = v?.checks.filter((c) => !c.ok && c.severity === "fail").map((c) => c.check).join(", ");
      out.push(`- ${f.finding_id}: ${why}`);
    }
    out.push("");
  }

  out.push("---");
  out.push(
    `run: ${research.metrics.turns} turns · ${research.metrics.tool_calls} tool calls · ` +
      `${research.metrics.protocol_errors} protocol errors · ${(research.metrics.duration_ms / 1000).toFixed(0)}s · ` +
      `model ${research.metrics.model ?? "n/a"} · evidence records ${log.all().length}` +
      (research.metrics.aborted ? ` · aborted: ${research.metrics.aborted}` : ""),
  );
  return out.join("\n");
}
