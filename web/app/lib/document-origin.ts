/** Independent official-source observations; byte agreement never approves contents. */
import { CORPUS_PREFIX, type CorpusBucket, type FilingIdentity } from "./document-corpus";
import { readRecoveryArtifact } from "./document-recovery";
import regulatorNames from "../../../data/banks/bddk_audit_registry_names.json";

export type OriginReference = { key: string; sha256: string; bytes: number; checked_at: string; status: string; acquisition_sha256: string | null };
type Artifact = { key: string; sha256: string; bytes: number };
export type OriginObservation = { reference: OriginReference; current: boolean; review: OriginReview };
export type OriginReview = {
  schema_version: "document-origin-review-1"; filing: FilingIdentity; checked_at: string;
  status: "matches_acquired_bytes" | "same_pdf_after_acquisition_wrapper" | "different_pdf_revision"
    | "acquisition_missing" | "origin_unavailable" | "origin_needs_review";
  source_url: string; semantically_verified: false; error?: string;
  acquisition: { sha256: string; bytes: number } | null;
  transport: Artifact | null; origin_pdf: Artifact | null;
  source_listing?: Artifact & { registry_name: string; download_url: string; row_number: number;
    row_cells: string[]; response: { source_url: string } };
  origin_identity?: { status: string }; related_pdf_content_capture?: string;
  selection?: { archive_member?: string; unselected_pdf_members?: { name: string; bytes: number; sha256: string }[] };
};
const record = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const hash = (v: unknown): v is string => typeof v === "string" && /^[a-f0-9]{64}$/.test(v);
const count = (v: unknown): v is number => typeof v === "number" && Number.isSafeInteger(v) && v > 0;
const sameFiling = (v: unknown, f: FilingIdentity) => record(v) && Object.entries(f).every(([k, value]) => v[k] === value);
const time = (v: unknown): v is string => typeof v === "string" && /(?:Z|\+00:00)$/.test(v) && Number.isFinite(Date.parse(v));
const statuses = new Set(["matches_acquired_bytes", "same_pdf_after_acquisition_wrapper", "different_pdf_revision",
  "acquisition_missing", "origin_unavailable", "origin_needs_review"]);

async function getOriginIndex(bucket: CorpusBucket, filing: FilingIdentity) {
  const base = `${CORPUS_PREFIX}origins/${filing.bank_ticker}/${filing.period}/${filing.kind}/`;
  const object = await bucket.get(base + "index.json");
  if (!object) return null;
  if (object.size > 4_000_000) throw new Error("Oversized origin index");
  const index: unknown = await object.json();
  if (!record(index) || index.schema_version !== "document-origin-index-1" || !sameFiling(index.filing, filing)
      || index.semantically_verified !== false || !Array.isArray(index.revisions) || !record(index.current)) {
    throw new Error("Invalid origin index binding");
  }
  const fields = ["key", "sha256", "bytes", "checked_at", "status", "acquisition_sha256"];
  if (!index.revisions.length || index.revisions.length > 1000
      || new Set(index.revisions.map(r => record(r) ? r.sha256 : null)).size !== index.revisions.length
      || !index.revisions.every(r => record(r) && hash(r.sha256) && r.key === `${base}${r.sha256}.json`
        && count(r.bytes) && r.bytes <= 8_000_000 && time(r.checked_at) && statuses.has(String(r.status))
        && (r.acquisition_sha256 === null || hash(r.acquisition_sha256)))
      || !index.revisions.some(r => record(r) && fields.every(k => r[k] === (index.current as Record<string, unknown>)[k]))) {
    throw new Error("Invalid origin revision history");
  }
  return { current: index.current as OriginReference, revisions: index.revisions as OriginReference[] };
}

export async function getOriginReview(bucket: CorpusBucket, filing: FilingIdentity, observation?: string): Promise<OriginReview | null> {
  if (observation !== undefined && !hash(observation)) throw new Error("Invalid origin observation digest");
  const index = await getOriginIndex(bucket, filing);
  if (!index) return null;
  const reference = observation ? index.revisions.find(r => r.sha256 === observation) : index.current;
  if (!reference) throw new Error("Observation is absent from retained origin history");
  return readOriginReview(bucket, filing, reference);
}

export async function getOriginObservations(bucket: CorpusBucket, filing: FilingIdentity): Promise<OriginObservation[]> {
  const index = await getOriginIndex(bucket, filing);
  if (!index) return [];
  const results: OriginObservation[] = [];
  for (const reference of [...index.revisions].sort((a, b) => b.checked_at.localeCompare(a.checked_at) || b.sha256.localeCompare(a.sha256))) {
    results.push({ reference, current: reference.sha256 === index.current.sha256, review: await readOriginReview(bucket, filing, reference) });
  }
  return results;
}

async function readOriginReview(bucket: CorpusBucket, filing: FilingIdentity, current: OriginReference): Promise<OriginReview> {
  const bytes = await readRecoveryArtifact(bucket, current as Artifact);
  const value: unknown = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  if (!record(value) || value.schema_version !== "document-origin-review-1" || !sameFiling(value.filing, filing)
      || value.semantically_verified !== false || value.status !== current.status || value.checked_at !== current.checked_at
      || typeof value.source_url !== "string" || !/^https?:\/\//.test(value.source_url)
      || value.error !== undefined && typeof value.error !== "string") throw new Error("Origin receipt binding mismatch");
  if (value.acquisition !== null && (!record(value.acquisition) || !hash(value.acquisition.sha256)
      || !count(value.acquisition.bytes))) throw new Error("Invalid acquired-source observation");
  if ((record(value.acquisition) ? value.acquisition.sha256 : null) !== current.acquisition_sha256) {
    throw new Error("Origin acquisition differs from its index");
  }
  for (const name of ["transport", "origin_pdf"]) {
    const entry = value[name];
    if (entry === null) continue;
    if (!record(entry) || !hash(entry.sha256) || !count(entry.bytes)
        || entry.key !== (name === "transport" ? `${CORPUS_PREFIX}transports/${entry.sha256}/original.bin`
          : `${CORPUS_PREFIX}sources/${entry.sha256}/original.pdf`)) throw new Error("Invalid origin artifact key");
  }
  if (value.source_listing !== undefined) {
    const listing = value.source_listing;
    const expectedName = (regulatorNames.banks as Record<string, string>)[filing.bank_ticker];
    if (!record(listing) || listing.schema_version !== "document-origin-listing-1" || !sameFiling(listing.filing, filing)
        || listing.semantically_verified !== false || !hash(listing.sha256) || !count(listing.bytes)
        || listing.key !== `${CORPUS_PREFIX}origin-listings/${listing.sha256}.html` || listing.bytes > 20_000_000
        || !expectedName || listing.registry_name !== expectedName || listing.download_url !== value.source_url
        || !record(listing.engine) || !hash(listing.engine.implementation_sha256) || !hash(listing.engine.bank_names_sha256)
        || typeof listing.row_number !== "number" || !Number.isSafeInteger(listing.row_number) || listing.row_number < 0
        || !Array.isArray(listing.row_cells) || listing.row_cells.length !== 5
        || listing.row_cells[0] !== expectedName || listing.row_cells[1] !== filing.period.slice(0, 4)
        || listing.row_cells[2] !== String(Number(filing.period.slice(-1)) * 3)
        || listing.row_cells[3] !== (filing.kind === "consolidated" ? "KONSOLIDE" : "SOLO")
        || !record(listing.response) || listing.response.source_url !== "https://www.bddk.org.tr/BdrUyg/"
        || listing.response.resolved_url !== "https://www.bddk.org.tr/BdrUyg/Home/SorguSonuc?KurulusTuru=1&EFTKodu=0&RaporTipi=T%C3%9CM%C3%9C&DonemYil=0&DonemAy=0"
        || listing.response.method !== "POST"
        || !record(listing.response.form) || listing.response.form.KurulusTuru !== "1" || listing.response.form.EFTKodu !== "0"
        || listing.response.form.RaporTipi !== "TÜMÜ" || listing.response.form.DonemYil !== "0" || listing.response.form.DonemAy !== "0") {
      throw new Error("Invalid regulator listing witness");
    }
    const url = new URL(value.source_url as string);
    const target = url.searchParams.getAll("raporUrl");
    const basis = filing.kind === "consolidated" ? "KONSOLIDE" : "SOLO";
    const match = /^~\/Dosya\/BDREki-\d+-(SOLO|KONSOLIDE)-(\d{4})-(\d{2})\.zip$/.exec(target[0] ?? "");
    if (url.protocol !== "https:" || url.host !== "www.bddk.org.tr" || url.pathname !== "/BdrUyg/Home/DosyaIndir"
        || url.hash || [...url.searchParams.keys()].length !== 1 || target.length !== 1
        || !match || match[1] !== basis || match[2] !== filing.period.slice(0, 4)
        || match[3] !== String(Number(filing.period.slice(-1)) * 3).padStart(2, "0")) throw new Error("Regulator link differs from its filing");
  }
  if (value.origin_identity !== undefined && (!record(value.origin_identity) || typeof value.origin_identity.status !== "string")) {
    throw new Error("Invalid origin identity observation");
  }
  if (value.selection !== undefined) {
    if (!record(value.selection)) throw new Error("Invalid origin archive selection");
    const members = value.selection.unselected_pdf_members;
    if (members !== undefined && (!Array.isArray(members) || members.some(m => !record(m)
        || typeof m.name !== "string" || !count(m.bytes) || !hash(m.sha256)))) throw new Error("Invalid related PDF members");
  }
  const acquiredHash = record(value.acquisition) ? value.acquisition.sha256 : null;
  const originHash = record(value.origin_pdf) ? value.origin_pdf.sha256 : null;
  if (value.status === "matches_acquired_bytes" && (!acquiredHash || acquiredHash !== originHash)
      || value.status === "different_pdf_revision" && (!acquiredHash || !originHash || acquiredHash === originHash)
      || value.status === "acquisition_missing" && (acquiredHash !== null || !originHash)
      || value.status === "origin_unavailable" && (value.transport !== null || value.origin_pdf !== null)
      || value.status === "same_pdf_after_acquisition_wrapper" && (!acquiredHash || !originHash || !record(value.acquisition_wrapper))) {
    throw new Error("Origin comparison contradicts observed source hashes");
  }
  return value as unknown as OriginReview;
}
