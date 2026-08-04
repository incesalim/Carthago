/**
 * Analyst V2 — the evidence model.
 *
 * Every fact the research agent sees arrives as an EvidenceRecord with a
 * stable id, full provenance (snapshot, tool, args, tables, row identity,
 * source pages where known) and the validation state of the partitions it
 * came from. Findings cite evidence ids; the verifier resolves them; nothing
 * outside the log exists, analytically speaking.
 *
 * IDs are deterministic — fnv1a over (tool, canonical args, snapshot id) — so
 * the same question against the same snapshot yields the same id, retries
 * dedupe, and a finding's citations survive a rerun.
 */

export interface SnapshotId {
  /** `audit:<MAX(extracted_at)>:<extraction row count>` — moves iff the data did. */
  id: string;
  max_extracted_at: string | null;
  extraction_rows: number;
}

export interface EvidenceProvenance {
  snapshot: string;
  tables: string[];
  bank: string | null;
  period: string | null;
  kind: string | null;
  /** Source pages, when the underlying rows carry them. */
  source_pages: number[];
}

export interface EvidenceRecord {
  evidence_id: string;
  tool: string;
  args: Record<string, unknown>;
  provenance: EvidenceProvenance;
  /** Validation state of the touched partitions: e.g. "equity_change: 2 checks failed". */
  validation_warnings: string[];
  /** Data-completeness warnings: missing periods, absent tables, nulls that
   *  matter. NULL is never silently zero — it is a warning instead. */
  warnings: string[];
  rows_returned: number;
  /** Structured payload — shape depends on the tool; always JSON-serializable. */
  data: unknown;
}

export function fnv1a(s: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return (h >>> 0).toString(16).padStart(8, "0");
}

/** Canonical JSON: sorted keys, so arg order never changes an evidence id. */
export function canonical(v: unknown): string {
  if (v === null || typeof v !== "object") return JSON.stringify(v) ?? "null";
  if (Array.isArray(v)) return `[${v.map(canonical).join(",")}]`;
  const o = v as Record<string, unknown>;
  return `{${Object.keys(o).sort().map((k) => `${JSON.stringify(k)}:${canonical(o[k])}`).join(",")}}`;
}

export function evidenceId(tool: string, args: Record<string, unknown>, snapshot: string): string {
  return `E${fnv1a(`${tool}|${canonical(args)}|${snapshot}`)}`;
}

/** Append-only in-memory log, deduped by id; serialized to evidence.jsonl. */
export class EvidenceLog {
  private byId = new Map<string, EvidenceRecord>();

  add(rec: EvidenceRecord): EvidenceRecord {
    const existing = this.byId.get(rec.evidence_id);
    if (existing) return existing;
    this.byId.set(rec.evidence_id, rec);
    return rec;
  }

  get(id: string): EvidenceRecord | undefined {
    return this.byId.get(id);
  }

  has(id: string): boolean {
    return this.byId.has(id);
  }

  all(): EvidenceRecord[] {
    return [...this.byId.values()];
  }

  toJsonl(): string {
    return this.all().map((r) => JSON.stringify(r)).join("\n") + "\n";
  }
}
