/**
 * Analyst V2 — the deterministic verifier. Checks MORE than numeric presence:
 * entity/period/kind association, comparison direction, arithmetic, evidence
 * resolution, failed-partition usage, contradictions, causal language and
 * unlabelled forecasts. Verdicts are per finding: pass / flag / fail — and a
 * fail is a reason with the numbers attached, never a vibe.
 *
 * The verifier can fully check the STRUCTURED claims; the thesis gets the
 * lexical + policy checks. That boundary is stated, not hidden: "automated
 * checks passed" is the strongest thing the UI may ever say.
 */
import type { EvidenceLog, EvidenceRecord } from "./evidence";
import type { ClaimSubject, Finding } from "./findings";

export interface CheckResult {
  check: string;
  ok: boolean;
  severity: "fail" | "flag";
  detail: string;
}

export interface FindingVerdict {
  finding_id: string;
  verdict: "pass" | "flag" | "fail";
  checks: CheckResult[];
}

export interface VerificationReport {
  findings: FindingVerdict[];
  summary: {
    total: number;
    pass: number;
    flag: number;
    fail: number;
    unsupported_numeric_claims: number;
    association_mismatches: number;
    contradictions: number;
  };
}

const NUM_TOL_REL = 0.005;
const NUM_TOL_ABS = 0.011;

/** Tools whose evidence is inherently single-period — for these, the evidence
 *  period must MATCH the claim subject's period (the 2026Q1-value-on-a-2025Q1-row
 *  regression class). History/peer/recon tools legitimately span periods. */
const SINGLE_PERIOD_TOOLS = new Set([
  "get_statement_rows",
  "rank_statement_movements",
  "get_validation_status",
  "list_available_data",
  "get_existing_signals",
]);

function collectNumbers(v: unknown, out: number[] = []): number[] {
  if (typeof v === "number" && Number.isFinite(v)) out.push(v);
  else if (Array.isArray(v)) for (const x of v) collectNumbers(x, out);
  else if (v && typeof v === "object") for (const x of Object.values(v)) collectNumbers(x, out);
  else if (typeof v === "string") {
    // Numbers embedded in strings (descriptions, payloads) count as present.
    for (const m of v.replace(/,/g, "").matchAll(/-?\d+(?:\.\d+)?/g)) out.push(parseFloat(m[0]));
  }
  return out;
}

function near(a: number, b: number): boolean {
  return Math.abs(a - b) <= Math.max(Math.abs(b) * NUM_TOL_REL, NUM_TOL_ABS);
}

const foldTr = (s: string) => s.replace(/İ/g, "I").replace(/ı/g, "i").toUpperCase();

/** Row-objects inside evidence data whose identity matches the claim's row
 *  (label contains-either-way after folding, or exact hierarchy). */
function subjectRows(v: unknown, row: string, out: unknown[] = []): unknown[] {
  if (Array.isArray(v)) for (const x of v) subjectRows(x, row, out);
  else if (v && typeof v === "object") {
    const r = v as Record<string, unknown>;
    const label = typeof r.item_name === "string" ? foldTr(r.item_name) : null;
    const target = foldTr(row);
    if ((label && (label.includes(target) || target.includes(label))) || r.hierarchy === row) out.push(v);
    else for (const x of Object.values(r)) subjectRows(x, row, out);
  }
  return out;
}

type MatchTier = "signed_scoped" | "signed" | "abs_only" | "none";

/** The ×100 bridge exists ONLY for stored fractions claimed as percents
 *  (stage coverages: 0.6349 → "63.49%"). Gating it to fraction-sized numbers
 *  matters: unrestricted, an evidence value of 100 would validate any claim
 *  near ±10,000 through the relative tolerance. */
function signedIn(value: number, nums: number[]): boolean {
  return nums.some((n) => near(value, n) || (Math.abs(n) <= 2 && near(value, n * 100)));
}

/**
 * How the claimed value relates to the cited evidence. Signed match within
 * the claim's own row beats signed-anywhere beats opposite-sign-only — the
 * old boolean accepted a number found anywhere at either sign, which lets a
 * direction-inverted claim through on magnitude alone. abs_only is kept as
 * a distinct tier (not a pass) because P&L deduction lines legitimately
 * print positive under "(-)" labels: the verdict downgrades, never silently
 * passes.
 */
function evidenceMatch(
  value: number, evidence: EvidenceRecord[], row?: string | null,
): { tier: MatchTier; scopedAvailable: boolean } {
  const scoped: number[] = [];
  const all: number[] = [];
  for (const e of evidence) {
    collectNumbers(e.data, all);
    if (row) for (const r of subjectRows(e.data, row)) collectNumbers(r, scoped);
  }
  if (row && scoped.length && signedIn(value, scoped)) return { tier: "signed_scoped", scopedAvailable: true };
  if (signedIn(value, all)) return { tier: "signed", scopedAvailable: !!row && scoped.length > 0 };
  if (all.some((n) => near(value, -n) || (Math.abs(n) <= 2 && near(value, -n * 100)))) return { tier: "abs_only", scopedAvailable: !!row && scoped.length > 0 };
  return { tier: "none", scopedAvailable: !!row && scoped.length > 0 };
}

/** Permissive presence (any sign) — for thesis tracing and derivation inputs,
 *  where prose conventions ("decreased by 6,719,898") legitimately drop signs. */
function numberInEvidence(value: number, evidence: EvidenceRecord[]): boolean {
  return evidenceMatch(value, evidence).tier !== "none";
}

const CAUSAL_RE = /\b(because|due to|driven by|caused by|led to|as a result of|thanks to|stems? from)\b/i;
const FORECAST_RE = /\b(will|is expected to|by next|within (one|two|three|\d) quarters?|forecast|is likely to|should (fall|rise|reach))\b/i;

export function verifyFindings(
  findings: Finding[],
  log: EvidenceLog,
  run: { bank: string; period: string; kind: string },
): VerificationReport {
  const verdicts: FindingVerdict[] = [];
  let unsupported = 0;
  let mismatches = 0;
  let contradictions = 0;

  // Cross-finding contradiction ledger: metric-key → asserted directions.
  const directionByKey = new Map<string, { finding_id: string; op: string; value: number; rhs: number }[]>();

  // Near-duplicate ledger: claim signatures + thesis tokens of processed findings.
  const seenSignatures: { finding_id: string; claims: Set<string>; tokens: Set<string> }[] = [];

  for (const f of findings) {
    const checks: CheckResult[] = [];
    const push = (check: string, ok: boolean, severity: "fail" | "flag", detail: string) =>
      checks.push({ check, ok, severity, detail });

    /* F1 — the finding is about the run's partition. */
    const fMatch = f.bank === run.bank && f.period === run.period && f.kind === run.kind;
    if (!fMatch) mismatches++;
    push("finding_partition", fMatch, "fail", fMatch ? "matches run" : `finding says ${f.bank}/${f.period}/${f.kind}, run is ${run.bank}/${run.period}/${run.kind}`);

    const allEvidenceNumbers: EvidenceRecord[] = [];
    const failedPartitionCited: string[] = [];

    for (const c of f.claims ?? []) {
      const tag = `claim ${c.claim_id}`;

      /* C1 — evidence resolves. */
      const evidence = (c.evidence_ids ?? []).map((id) => log.get(id)).filter((e): e is EvidenceRecord => !!e);
      const missing = (c.evidence_ids ?? []).filter((id) => !log.has(id));
      push(`${tag}: evidence_resolves`, missing.length === 0, "fail", missing.length ? `unknown evidence ids: ${missing.join(", ")}` : `${evidence.length} record(s)`);
      if (!evidence.length) continue;
      allEvidenceNumbers.push(...evidence);

      /* C2 — association: bank/kind always; period for single-period tools. */
      for (const e of evidence) {
        const s = c.subject as ClaimSubject;
        if (e.provenance.bank && s.bank && e.provenance.bank !== s.bank) {
          mismatches++;
          push(`${tag}: entity_association`, false, "fail", `evidence ${e.evidence_id} is about ${e.provenance.bank}, claim about ${s.bank}`);
        }
        if (e.provenance.kind && s.kind && e.provenance.kind !== s.kind) {
          mismatches++;
          push(`${tag}: kind_association`, false, "fail", `evidence ${e.evidence_id} is ${e.provenance.kind}, claim ${s.kind}`);
        }
        if (SINGLE_PERIOD_TOOLS.has(e.tool) && e.provenance.period && s.period && e.provenance.period !== s.period) {
          mismatches++;
          push(`${tag}: period_association`, false, "fail", `evidence ${e.evidence_id} (${e.tool}) is ${e.provenance.period}, claim asserts ${s.period}`);
        }
        if (e.validation_warnings.length) failedPartitionCited.push(`${e.evidence_id}: ${e.validation_warnings[0]}`);
      }

      /* C3 — the asserted number exists in the cited evidence: signed, and
         preferably inside the claim's own row. */
      if (typeof c.value === "number") {
        const m = evidenceMatch(c.value, evidence, (c.subject as ClaimSubject)?.row);
        if (m.tier === "none") {
          unsupported++;
          push(`${tag}: value_in_evidence`, false, "fail", `${c.value} appears in NONE of the cited evidence`);
        } else if (m.tier === "abs_only") {
          push(`${tag}: value_in_evidence`, false, "flag", `${c.value} matches only with the OPPOSITE sign — check the sign convention before publishing`);
        } else if (m.tier === "signed" && m.scopedAvailable) {
          push(`${tag}: value_in_evidence`, false, "flag", `${c.value} found in cited evidence but NOT within the named row '${(c.subject as ClaimSubject)?.row}'`);
        } else {
          push(`${tag}: value_in_evidence`, true, "fail", `${c.value} found${m.tier === "signed_scoped" ? " in the named row" : ""}`);
        }
      }

      /* C4 — comparison direction actually holds. */
      if (c.claim_kind === "comparison" && c.comparison && typeof c.value === "number") {
        const rhs = c.comparison.rhs_value;
        if (typeof rhs === "number") {
          const opOk =
            (c.comparison.op === "gt" && c.value > rhs) ||
            (c.comparison.op === "ge" && c.value >= rhs) ||
            (c.comparison.op === "lt" && c.value < rhs) ||
            (c.comparison.op === "le" && c.value <= rhs) ||
            (c.comparison.op === "eq" && near(c.value, rhs));
          push(`${tag}: comparison_direction`, opOk, "fail", `${c.value} ${c.comparison.op} ${rhs} is ${opOk}`);
          const rm = evidenceMatch(rhs, evidence);
          if (rm.tier === "none") push(`${tag}: comparison_rhs_in_evidence`, false, "fail", `rhs ${rhs} not in cited evidence`);
          else if (rm.tier === "abs_only") push(`${tag}: comparison_rhs_in_evidence`, false, "flag", `rhs ${rhs} matches only with the opposite sign`);
          else push(`${tag}: comparison_rhs_in_evidence`, true, "fail", "rhs found");
          const key = `${c.subject.bank}|${c.subject.period}|${c.subject.kind}|${c.subject.metric ?? c.subject.row ?? ""}`;
          const list = directionByKey.get(key) ?? [];
          list.push({ finding_id: f.finding_id, op: c.comparison.op, value: c.value, rhs });
          directionByKey.set(key, list);
        }
      }

      /* C5 — change arithmetic foots and endpoints are evidenced. */
      if (c.claim_kind === "change" && c.change) {
        const { from_value, to_value, delta } = c.change;
        const foots = near(from_value + delta, to_value);
        push(`${tag}: change_arithmetic`, foots, "fail", `${from_value} + ${delta} ${foots ? "=" : "≠"} ${to_value}`);
        const endpoints = numberInEvidence(from_value, evidence) && numberInEvidence(to_value, evidence);
        if (!endpoints) unsupported++;
        push(`${tag}: change_endpoints_in_evidence`, endpoints, "fail", endpoints ? "both endpoints found" : "an endpoint is not in cited evidence");
      }

      /* C6 — derivation inputs are evidenced. */
      if (c.derivation) {
        const allIn = c.derivation.inputs.every((n) => numberInEvidence(n, evidence));
        push(`${tag}: derivation_inputs`, allIn, allIn ? "flag" : "fail", allIn ? "inputs found" : "a derivation input is not in cited evidence");
      }
    }

    /* T1 — thesis/rationale numbers trace to claims or evidence. */
    {
      const text = `${f.thesis} ${f.materiality_rationale}`;
      const claimed = (f.claims ?? []).flatMap((c) => [
        ...(typeof c.value === "number" ? [c.value] : []),
        ...(c.comparison?.rhs_value != null ? [c.comparison.rhs_value] : []),
        ...(c.change ? [c.change.from_value, c.change.to_value, c.change.delta] : []),
        ...(c.derivation?.inputs ?? []),
      ]);
      const loose: number[] = [];
      for (const m of text.replace(/,/g, "").matchAll(/-?\d+(?:\.\d+)?/g)) {
        const n = parseFloat(m[0]);
        if (!Number.isFinite(n)) continue;
        if (Math.abs(n) < 3) continue; // ordinals and years-of-quarters noise
        if (/^\d{4}Q\d$/.test(m[0]) || (n >= 2020 && n <= 2030 && Number.isInteger(n))) continue;
        const ok = claimed.some((v) => near(n, v) || near(n, -v)) || numberInEvidence(n, allEvidenceNumbers);
        if (!ok) loose.push(n);
      }
      if (loose.length) unsupported += loose.length;
      push("thesis_numbers_traced", loose.length === 0, "fail", loose.length ? `numbers with no claim/evidence: ${loose.join(", ")}` : "all traced");
    }

    /* T2 — causal language needs connective machinery. */
    if (CAUSAL_RE.test(f.thesis) || CAUSAL_RE.test(f.materiality_rationale)) {
      const hasConnective = (f.claims ?? []).some((c) => c.claim_kind === "reconciliation" || c.derivation);
      const sev = f.classification === "observed_fact" ? "fail" : "flag";
      push("causal_language_supported", hasConnective, sev, hasConnective ? "reconciliation/derivation present" : `causal wording without a reconciliation or derivation claim (classification: ${f.classification})`);
    }

    /* T3 — forecasts must be labelled scenarios with assumptions. */
    if (FORECAST_RE.test(f.thesis) || FORECAST_RE.test(f.materiality_rationale)) {
      const ok = f.classification === "scenario";
      push("forecast_labelled", ok, "fail", ok ? "scenario" : "forward-looking language outside a scenario classification");
      if (ok) {
        push("scenario_assumptions", (f.caveats ?? []).length > 0, "flag", (f.caveats ?? []).length ? "assumptions present" : "scenario without disclosed assumptions");
      }
    }

    /* T4 — failed partitions must be caveated. */
    if (failedPartitionCited.length) {
      const caveated = (f.caveats ?? []).some((c) => /valid|extract|defect|failing/i.test(c));
      push("failed_partition_caveated", caveated, "fail", caveated ? "caveat present" : `cites evidence from failing partitions without a caveat (${failedPartitionCited[0]})`);
    }

    /* Interpretation presented as fact: fact-classified finding with hedged
       thesis language is fine; interpretation language inside observed_fact —
       heuristic flag only. */
    if (f.classification === "observed_fact" && /\b(suggests|likely|probably|appears to|may have)\b/i.test(f.thesis)) {
      push("fact_vs_interpretation", false, "flag", "hedged language inside observed_fact — consider interpretation");
    }

    /* T6 — near-duplicate of an earlier finding (same claims retold, or the
       same thesis reworded) adds noise, not information: the later one fails. */
    {
      const claimSig = new Set(
        (f.claims ?? []).map((c) => `${c.claim_kind}|${c.subject?.statement ?? ""}|${foldTr(String(c.subject?.row ?? ""))}|${c.value ?? ""}`),
      );
      const tokens = new Set(foldTr(f.thesis ?? "").split(/[^A-Z0-9]+/).filter((w) => w.length > 3));
      const dup = seenSignatures.find((s) => {
        const shared = [...claimSig].filter((k) => s.claims.has(k)).length;
        const jaccard = shared / (new Set([...claimSig, ...s.claims]).size || 1);
        const tokShared = [...tokens].filter((t) => s.tokens.has(t)).length;
        const overlap = tokShared / (Math.min(tokens.size, s.tokens.size) || 1);
        return jaccard >= 0.5 || overlap >= 0.75;
      });
      push("duplicate_finding", !dup, "fail", dup ? `near-duplicate of ${dup.finding_id} — merge or drop` : "distinct");
      seenSignatures.push({ finding_id: f.finding_id, claims: claimSig, tokens });
    }

    const anyFail = checks.some((c) => !c.ok && c.severity === "fail");
    const anyFlag = checks.some((c) => !c.ok && c.severity === "flag");
    verdicts.push({ finding_id: f.finding_id, verdict: anyFail ? "fail" : anyFlag ? "flag" : "pass", checks });
  }

  /* T5 — cross-finding contradictions on the same subject+metric. */
  for (const [key, list] of directionByKey) {
    for (let i = 0; i < list.length; i++) {
      for (let j = i + 1; j < list.length; j++) {
        const a = list[i];
        const b = list[j];
        const up = (op: string) => op === "gt" || op === "ge";
        if (near(a.value, b.value) && near(a.rhs, b.rhs) && up(a.op) !== up(b.op)) {
          contradictions++;
          for (const hit of [a, b]) {
            const v = verdicts.find((x) => x.finding_id === hit.finding_id);
            v?.checks.push({ check: "cross_finding_contradiction", ok: false, severity: "fail", detail: `conflicting directions on ${key}` });
            if (v) v.verdict = "fail";
          }
        }
      }
    }
  }

  return {
    findings: verdicts,
    summary: {
      total: verdicts.length,
      pass: verdicts.filter((v) => v.verdict === "pass").length,
      flag: verdicts.filter((v) => v.verdict === "flag").length,
      fail: verdicts.filter((v) => v.verdict === "fail").length,
      unsupported_numeric_claims: unsupported,
      association_mismatches: mismatches,
      contradictions,
    },
  };
}
