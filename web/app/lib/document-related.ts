/** Resolve an attachment only through its retained official archive relationship. */
import { CORPUS_PREFIX, parseCorpusRevision, type CorpusBucket, type CorpusRevision, type FilingIdentity } from "./document-corpus";
import { getOriginReview } from "./document-origin";
import { readRecoveryArtifact } from "./document-recovery";

const record = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
export type RelatedRevision = CorpusRevision & { archive_identity?: {
  status: string; claim_page: number | null; observed_periods: string[]; issues: string[];
} };

export async function getRelatedRevision(bucket: CorpusBucket, filing: FilingIdentity, memberHash: string, observation?: string): Promise<RelatedRevision | null> {
  if (!/^[a-f0-9]{64}$/.test(memberHash)) throw new Error("Invalid related document hash");
  const origin = await getOriginReview(bucket, filing, observation);
  const members = origin?.selection?.unselected_pdf_members?.filter(m => m.sha256 === memberHash) ?? [];
  if (!origin?.transport || !origin.origin_pdf || members.length !== 1) {
    throw new Error("Related document is absent or ambiguous in the verified source archive");
  }
  const member = members[0];
  const key = `${CORPUS_PREFIX}related/${filing.bank_ticker}/${filing.period}/${filing.kind}/${origin.transport.sha256}/${memberHash}.json`;
  const object = await bucket.get(key);
  if (!object) return null;
  if (object.size > 8_000_000) throw new Error("Oversized related document index");
  const index: unknown = await object.json();
  const relation = record(index) ? index.relationship : null;
  if (!record(relation) || relation.schema_version !== "related-source-binding-1"
      || relation.relationship !== "other_pdf_in_same_registered_source_archive" || relation.semantically_verified !== false
      || !record(relation.filing) || Object.entries(filing).some(([k, v]) => (relation.filing as Record<string, unknown>)[k] !== v)
      || relation.transport_sha256 !== origin.transport.sha256 || relation.transport_key !== origin.transport.key
      || relation.primary_pdf_sha256 !== origin.origin_pdf.sha256 || relation.primary_member_name !== origin.selection?.archive_member
      || !record(relation.member) || Object.entries(member).some(([k, v]) => (relation.member as Record<string, unknown>)[k] !== v)) {
    throw new Error("Related document index differs from its official source archive");
  }
  const revision = parseCorpusRevision(index, filing);
  // For ordinary PDF members, the origin's independently retained member hash
  // binds the current source directly. A wrapped member needs a separate
  // verified wrapper binding; never accept another valid filing revision here.
  if (revision && revision.source.pdf_sha256 !== memberHash) {
    throw new Error("Related PDF bytes cannot be matched directly to the retained archive member");
  }
  if (revision && (!record(index) || !record(index.current) || index.current.semantic_verification !== "not_performed")) {
    throw new Error("Related source claims unsupported semantic approval");
  }
  if (revision && record(index) && record(index.current) && index.current.related_identity_review !== undefined) {
    const ref = index.current.related_identity_review;
    if (!record(ref) || typeof ref.sha256 !== "string" || !/^[a-f0-9]{64}$/.test(ref.sha256)
        || ref.key !== `${CORPUS_PREFIX}sources/${memberHash}/related-identity/${ref.sha256}.json`
        || typeof ref.bytes !== "number" || !Number.isSafeInteger(ref.bytes) || ref.bytes < 1 || ref.bytes > 2_000_000) {
      throw new Error("Invalid related identity reference");
    }
    const bytes = await readRecoveryArtifact(bucket, ref as { key: string; sha256: string; bytes: number });
    const packet: unknown = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
    const sameFiling = (value: unknown) => record(value) && Object.entries(filing).every(([k, v]) => value[k] === v);
    if (!record(packet) || packet.schema_version !== "related-identity-review-1"
        || packet.source_filing_role !== "archive_container" || packet.semantic_verification !== "not_performed"
        || !sameFiling(packet.container_filing) || !sameFiling(packet.source) || !record(packet.source)
        || packet.source.pdf_sha256 !== memberHash || packet.evidence_artifact_sha256 !== index.current.artifact_sha256
        || revision.evidence_key !== `${CORPUS_PREFIX}sources/${memberHash}/${packet.evidence_artifact_sha256}.jsonl.gz`
        || !record(packet.identity_review) || !sameFiling(packet.identity_review.filing)) {
      throw new Error("Related identity differs from its native source or archive");
    }
    const review = packet.identity_review;
    if (!["supported_by_source_text", "unresolved", "ambiguous", "source_text_conflict"].includes(String(review.status))
        || review.semantic_verification !== "not_performed" || review.scope !== "leading_source_text_only"
        || review.claim_page !== null && (typeof review.claim_page !== "number" || !Number.isSafeInteger(review.claim_page)
          || review.claim_page < 1 || review.claim_page > Math.min(3, revision.page_count))
        || !Array.isArray(review.issues) || !review.issues.every(i => typeof i === "string")
        || !Array.isArray(review.observations)) throw new Error("Invalid related identity observation");
    const periods: string[] = [];
    for (const observation of review.observations) {
      if (!record(observation) || typeof observation.page !== "number" || !Array.isArray(observation.quarter_end_dates)) {
        throw new Error("Invalid related source date observation");
      }
      for (const date of observation.quarter_end_dates) {
        if (!record(date) || typeof date.period !== "string" || !/^\d{4}Q[1-4]$/.test(date.period)) {
          throw new Error("Invalid related source period");
        }
        if (observation.page === review.claim_page && !periods.includes(date.period)) periods.push(date.period);
      }
    }
    return { ...revision, archive_identity: { status: String(review.status), claim_page: review.claim_page as number | null,
      observed_periods: periods, issues: review.issues as string[] } };
  }
  return revision;
}
