/**
 * Analyst V2 — the findings schema. THE load-bearing design decision:
 * everything verifiable is a structured Claim, machine-checkable by
 * construction; free text is confined to the thesis and rationale, and even
 * there every number must trace back to a claim or cited evidence.
 */

export type Classification = "observed_fact" | "interpretation" | "scenario";
export type Confidence = "high" | "medium" | "low";
export type ClaimKind = "value" | "comparison" | "change" | "reconciliation";

export interface ClaimSubject {
  bank: string;
  period: string;
  kind: string;
  statement?: string;
  row?: string;
  metric?: string;
}

export interface Claim {
  claim_id: string;
  claim_kind: ClaimKind;
  subject: ClaimSubject;
  /** The asserted number (for value/comparison claims). */
  value?: number;
  unit?: string;
  /** comparison: `value <op> rhs` — rhs either literal or another subject
   *  whose number must ALSO be in the cited evidence. */
  comparison?: {
    op: "gt" | "lt" | "ge" | "le" | "eq";
    rhs_value?: number;
    rhs_subject?: ClaimSubject;
  };
  /** change: from → to across periods; delta must foot. */
  change?: { from_period: string; from_value: number; to_value: number; delta: number };
  /** derivation: a computed figure with its inputs (each input must appear in
   *  the cited evidence). */
  derivation?: { formula: string; inputs: number[] };
  evidence_ids: string[];
}

export interface Finding {
  finding_id: string;
  bank: string;
  period: string;
  kind: string;
  classification: Classification;
  /** One-to-three-sentence thesis. Numbers here must appear among the
   *  finding's claim values or cited evidence. */
  thesis: string;
  materiality_rationale: string;
  confidence: Confidence;
  claims: Claim[];
  counterevidence: { evidence_ids: string[]; note: string }[];
  caveats: string[];
  missing: string[];
  source_pages: number[];
}

/** Lenient structural validation for model-produced findings — returns the
 *  problems, never throws; the loop feeds problems back as protocol errors. */
export function findingProblems(f: unknown): string[] {
  const problems: string[] = [];
  const o = f as Partial<Finding> | null;
  if (!o || typeof o !== "object") return ["finding is not an object"];
  for (const k of ["finding_id", "bank", "period", "kind", "thesis", "materiality_rationale"] as const) {
    if (typeof o[k] !== "string" || !(o[k] as string).trim()) problems.push(`missing/empty '${k}'`);
  }
  if (!["observed_fact", "interpretation", "scenario"].includes(o.classification as string)) {
    problems.push("classification must be observed_fact | interpretation | scenario");
  }
  if (!["high", "medium", "low"].includes(o.confidence as string)) {
    problems.push("confidence must be high | medium | low");
  }
  if (!Array.isArray(o.claims) || o.claims.length === 0) {
    problems.push("at least one structured claim is required — a finding with no claims is unverifiable");
  } else {
    o.claims.forEach((c, i) => {
      if (!c || typeof c !== "object") return problems.push(`claim[${i}] not an object`);
      if (typeof c.claim_id !== "string") problems.push(`claim[${i}] missing claim_id`);
      if (!["value", "comparison", "change", "reconciliation"].includes(c.claim_kind as string)) {
        problems.push(`claim[${i}] bad claim_kind`);
      }
      if (!c.subject || typeof c.subject.bank !== "string" || typeof c.subject.period !== "string" || typeof c.subject.kind !== "string") {
        problems.push(`claim[${i}] subject needs bank/period/kind`);
      }
      if (!Array.isArray(c.evidence_ids) || c.evidence_ids.length === 0) {
        problems.push(`claim[${i}] cites no evidence`);
      }
      if (c.claim_kind === "comparison" && !c.comparison) problems.push(`claim[${i}] comparison missing`);
      if (c.claim_kind === "change" && !c.change) problems.push(`claim[${i}] change missing`);
      if ((c.claim_kind === "value" || c.claim_kind === "comparison") && typeof c.value !== "number") {
        problems.push(`claim[${i}] needs a numeric value`);
      }
    });
  }
  for (const k of ["counterevidence", "caveats", "missing", "source_pages"] as const) {
    if (o[k] != null && !Array.isArray(o[k])) problems.push(`'${k}' must be an array`);
  }
  return problems;
}

/** The schema as told to the model — compact, with one worked example. */
export const FINDING_SCHEMA_PROMPT = `A FINDING is a JSON object:
{
  "finding_id": "F1",
  "bank": "...", "period": "YYYYQN", "kind": "consolidated|unconsolidated",
  "classification": "observed_fact" | "interpretation" | "scenario",
  "thesis": "1-3 sentences. Every number here must also appear in a claim or cited evidence.",
  "materiality_rationale": "why it matters, quantified from claims",
  "confidence": "high|medium|low",
  "claims": [
    { "claim_id": "F1.c1", "claim_kind": "value",
      "subject": {"bank":"...","period":"...","kind":"...","statement":"equity_change","row":"X. Others Changes","metric":"total_equity"},
      "value": -7739022, "unit": "thousand_tl",
      "evidence_ids": ["E1a2b3c4"] },
    { "claim_id": "F1.c2", "claim_kind": "comparison",
      "subject": {"bank":"...","period":"...","kind":"...","metric":"npl_ratio_pct"},
      "value": 3.49, "comparison": {"op":"gt","rhs_value":2.47},
      "evidence_ids": ["E5d6e7f8"] }
  ],
  "counterevidence": [{"evidence_ids":["E..."],"note":"what argued against this and why it lost"}],
  "caveats": ["validation failing on equity_change for this partition", "..."],
  "missing": ["what would settle it but is not held"],
  "source_pages": [12, 13]
}
Rules: observed_fact = directly in evidence; interpretation = your reading (say so);
scenario = forward-looking, ONLY with assumptions in caveats. Causal language
("driven by", "because") requires a reconciliation or derivation claim connecting
the two sides. Never present an interpretation as a fact.`;
