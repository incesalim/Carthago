/** Resolve a captured edition through an exact retained source observation. */
import { CORPUS_PREFIX, parseCorpusRevision, type CorpusBucket, type FilingIdentity } from "./document-corpus";
import { getOriginObservations } from "./document-origin";

const record = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
export async function getEditionRevision(bucket: CorpusBucket, filing: FilingIdentity, observation: string) {
  if (!/^[a-f0-9]{64}$/.test(observation)) throw new Error("Invalid edition observation");
  const observations = await getOriginObservations(bucket, filing);
  const origin = observations.find(o => o.reference.sha256 === observation)?.review;
  if (origin?.status !== "different_pdf_revision" || !origin.origin_pdf) throw new Error("Observation does not identify a different PDF edition");
  const pdf = origin.origin_pdf.sha256;
  const object = await bucket.get(`${CORPUS_PREFIX}editions/${filing.bank_ticker}/${filing.period}/${filing.kind}/${pdf}.json`);
  if (!object) return null;
  if (object.size > 8_000_000) throw new Error("Oversized edition index");
  const index: unknown = await object.json();
  const binding = record(index) ? index.edition : null;
  if (!record(index) || !record(binding) || binding.schema_version !== "document-edition-binding-1"
      || binding.relationship !== "observed_different_official_pdf" || binding.semantic_verification !== "not_performed"
      || binding.pdf_sha256 !== pdf || !record(binding.filing)
      || Object.entries(filing).some(([k, v]) => (binding.filing as Record<string, unknown>)[k] !== v)
      || !Array.isArray(index.origin_observations) || !index.origin_observations.length
      || index.origin_observations.length > 1000) throw new Error("Invalid edition source binding");
  const prefix = `${CORPUS_PREFIX}origins/${filing.bank_ticker}/${filing.period}/${filing.kind}/`;
  const references = index.origin_observations;
  if (new Set(references.map(r => record(r) ? r.sha256 : null)).size !== references.length
      || !references.some(r => record(r) && r.sha256 === observation)) throw new Error("Edition lacks the requested origin observation");
  const sourceUrls: string[] = [];
  for (const ref of references) {
    if (!record(ref) || typeof ref.sha256 !== "string" || !/^[a-f0-9]{64}$/.test(ref.sha256)
        || ref.key !== `${prefix}${ref.sha256}.json`) throw new Error("Invalid edition observation reference");
    const observed = observations.find(o => o.reference.sha256 === ref.sha256);
    const review = observed?.review;
    if (!review || review.status !== "different_pdf_revision" || review.origin_pdf?.sha256 !== pdf
        || !observed || Object.entries(observed.reference).some(([k, v]) => ref[k] !== v)
        || review.status !== ref.status || review.checked_at !== ref.checked_at
        || review.acquisition?.sha256 !== ref.acquisition_sha256) throw new Error("Edition observation differs from its origin receipt");
    sourceUrls.push(review.source_url);
  }
  const revision = parseCorpusRevision(index, filing);
  if (revision && (revision.source.pdf_sha256 !== pdf || !sourceUrls.includes(revision.source.source_url ?? "")
      || !record(index.current) || index.current.semantic_verification !== "not_performed")) {
    throw new Error("Edition capture differs from its observed PDF source");
  }
  return revision;
}
