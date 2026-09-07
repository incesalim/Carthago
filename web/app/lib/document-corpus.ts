/** Read-only access to the private, source-bound audit document corpus. */
import { getCloudflareContext } from "@opennextjs/cloudflare";

export const CORPUS_PREFIX = "document-corpus/v1/";
/** Only the read capabilities used here; no writes are exposed to admin code. */
export interface CorpusBucket {
  get(key: string): Promise<{ size: number; uploaded: Date; body: ReadableStream<Uint8Array>;
    json<T = unknown>(): Promise<T> } | null>;
}
export type FilingIdentity = { bank_ticker: string; period: string; kind: "consolidated" | "unconsolidated" };
export type CorpusCapture = {
  source: (FilingIdentity & { pdf_sha256: string; source_url?: string | null }) | null;
  page_count: number | null;
  table_candidates: number | null;
  text_blocks: number | null;
  pages_with_issues: number | null;
  source_versions: number;
  capture_revisions: number;
  last_attempt_status: string;
  last_error: string | null;
  structure_engine: Record<string, string> | null;
};
export type CorpusFiling = FilingIdentity & {
  registered: boolean;
  source_urls: string[];
  object_keys: string[];
  acquisition_status: string;
  in_current_inventory: boolean;
  capture: CorpusCapture | null;
  source_capture_stale: boolean;
  structure_stale: boolean;
  latest_attempt_failed: boolean;
};
export type CorpusCatalog = {
  schema_version: "document-corpus-catalog-1";
  summary: { filings: number; registered: number; acquired: number | null; source_preserved: number;
    structured_candidates: number; failed: number; stale: number; semantically_verified: 0 };
  filings: CorpusFiling[];
};
export type CorpusCatalogResult = { status: "ready"; catalog: CorpusCatalog; updated: string }
  | { status: "not_connected" | "not_started" | "unavailable" };

const HASH = /^[a-f0-9]{64}$/;
const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const isCount = (value: unknown): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0;

export function parseFiling(value: string): FilingIdentity | null {
  const match = /^([A-Z0-9]+)\|(\d{4}Q[1-4])\|(consolidated|unconsolidated)$/.exec(value);
  return match ? { bank_ticker: match[1], period: match[2], kind: match[3] as FilingIdentity["kind"] } : null;
}

export function filingId(filing: FilingIdentity): string {
  return `${filing.bank_ticker}|${filing.period}|${filing.kind}`;
}

export function parseCatalog(value: unknown): CorpusCatalog {
  if (!isRecord(value) || value.schema_version !== "document-corpus-catalog-1"
      || !Array.isArray(value.filings) || !isRecord(value.summary)) throw new Error("Invalid corpus catalog");
  const ids = new Set<string>();
  for (const row of value.filings) {
    if (!isRecord(row) || typeof row.bank_ticker !== "string" || typeof row.period !== "string"
        || typeof row.kind !== "string" || !parseFiling(`${row.bank_ticker}|${row.period}|${row.kind}`)) {
      throw new Error("Invalid corpus filing");
    }
    const id = `${row.bank_ticker}|${row.period}|${row.kind}`;
    if (ids.has(id)) throw new Error("Duplicate corpus filing");
    ids.add(id);
    for (const key of ["registered", "in_current_inventory", "source_capture_stale", "structure_stale", "latest_attempt_failed"]) {
      if (typeof row[key] !== "boolean") throw new Error("Invalid corpus status");
    }
    if (!Array.isArray(row.source_urls) || !row.source_urls.every((s) => typeof s === "string")
        || !Array.isArray(row.object_keys) || !row.object_keys.every((s) => typeof s === "string")
        || !["acquired", "missing", "not_checked"].includes(String(row.acquisition_status))) {
      throw new Error("Invalid corpus acquisition status");
    }
    if (row.capture !== null) {
      const capture = row.capture;
      if (!isRecord(capture) || capture.semantic_verification !== "not_performed") throw new Error("Invalid capture status");
      for (const key of ["page_count", "table_candidates", "text_blocks", "pages_with_issues"]) {
        if (capture[key] !== null && !isCount(capture[key])) throw new Error("Invalid capture count");
      }
      if (!isCount(capture.source_versions) || !isCount(capture.capture_revisions)
          || typeof capture.last_attempt_status !== "string"
          || (capture.last_error !== null && typeof capture.last_error !== "string")) throw new Error("Invalid capture metadata");
      if (capture.source !== null) {
        const source = capture.source;
        if (!isRecord(source) || source.bank_ticker !== row.bank_ticker || source.period !== row.period
            || source.kind !== row.kind || typeof source.pdf_sha256 !== "string" || !HASH.test(source.pdf_sha256)) {
          throw new Error("Capture source does not match filing");
        }
      }
    }
  }
  const catalog = value as unknown as CorpusCatalog;
  const active = catalog.filings.filter((row) => row.in_current_inventory);
  const computed = {
    filings: active.length, registered: active.filter((row) => row.registered).length,
    source_preserved: active.filter((row) => row.capture?.source).length,
    structured_candidates: active.filter((row) => row.capture?.structure_engine).length,
    failed: active.filter((row) => row.latest_attempt_failed).length,
    stale: active.filter((row) => row.source_capture_stale || row.structure_stale).length,
    semantically_verified: 0,
  };
  for (const [key, count] of Object.entries(computed)) {
    if (value.summary[key] !== count) throw new Error("Corpus summary disagrees with filings");
  }
  if (catalog.summary.acquired !== null
      && catalog.summary.acquired !== active.filter((row) => row.acquisition_status === "acquired").length) {
    throw new Error("Corpus acquisition count disagrees with filings");
  }
  return catalog;
}

export async function getCorpusBucket(): Promise<CorpusBucket | null> {
  try {
    const { env } = await getCloudflareContext({ async: true });
    return env.AUDIT_DOCUMENTS ?? null;
  } catch {
    return null;
  }
}

export async function getCorpusCatalog(): Promise<CorpusCatalogResult> {
  const bucket = await getCorpusBucket();
  if (!bucket) return { status: "not_connected" };
  try {
    const object = await bucket.get(`${CORPUS_PREFIX}catalog.json`);
    if (!object) return { status: "not_started" };
    if (object.size > 8_000_000) throw new Error("Oversized corpus catalog");
    return { status: "ready", catalog: parseCatalog(await object.json()), updated: object.uploaded.toISOString() };
  } catch {
    return { status: "unavailable" };
  }
}

export type CorpusRevision = {
  source: FilingIdentity & { pdf_sha256: string; source_url?: string | null };
  original_key: string; evidence_key: string; page_count: number;
  structure_current?: { key: string; artifact_sha256: string };
};

export async function getCorpusRevision(bucket: CorpusBucket, filing: FilingIdentity): Promise<CorpusRevision | null> {
  const object = await bucket.get(`${CORPUS_PREFIX}filings/${filing.bank_ticker}/${filing.period}/${filing.kind}.json`);
  if (!object) return null;
  if (object.size > 8_000_000) throw new Error("Oversized filing index");
  const index: unknown = await object.json();
  return parseCorpusRevision(index, filing);
}

export function parseCorpusRevision(index: unknown, filing: FilingIdentity): CorpusRevision | null {
  if (!isRecord(index) || !isRecord(index.filing) || index.schema_version !== "corpus-index-1"
      || Object.entries(filing).some(([key, value]) => index.filing && (index.filing as Record<string, unknown>)[key] !== value)) {
    throw new Error("Invalid filing index");
  }
  if (index.current === null) return null;
  const current = index.current;
  if (!isRecord(current) || !isRecord(current.source) || !isCount(current.page_count) || current.page_count < 1
      || Object.entries(filing).some(([key, value]) => (current.source as Record<string, unknown>)[key] !== value)
      || typeof current.source.pdf_sha256 !== "string" || !HASH.test(current.source.pdf_sha256)) {
    throw new Error("Invalid filing revision");
  }
  const base = `${CORPUS_PREFIX}sources/${current.source.pdf_sha256}/`;
  if (current.original_key !== `${base}original.pdf` || typeof current.evidence_key !== "string"
      || !current.evidence_key.startsWith(base) || !/^[a-f0-9]{64}\.jsonl\.gz$/.test(current.evidence_key.slice(base.length))) {
    throw new Error("Invalid source artifact key");
  }
  if (current.structure_current !== undefined) {
    const structure = current.structure_current;
    if (!isRecord(structure) || typeof structure.key !== "string" || !structure.key.startsWith(base)
        || !/^[a-f0-9]{64}\.structure\.jsonl?\.gz$/.test(structure.key.slice(base.length))
        || typeof structure.artifact_sha256 !== "string" || !HASH.test(structure.artifact_sha256)
        || !structure.key.endsWith(`/${structure.artifact_sha256}.structure.jsonl.gz`)
          && !structure.key.endsWith(`/${structure.artifact_sha256}.structure.json.gz`)) {
      throw new Error("Invalid structure artifact key");
    }
  }
  return current as unknown as CorpusRevision;
}

async function sha256(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

/** Verify the requested page's exact stored bytes; never load the whole filing. */
export async function readVerifiedPage(body: ReadableStream, pageNumber: number, sourceHash: string,
                                       pageCount: number, kind: "source" | "structure") {
  if (!Number.isSafeInteger(pageNumber) || pageNumber < 1 || pageNumber > pageCount || !HASH.test(sourceHash)) {
    throw new Error("Invalid source page request");
  }
  for await (const result of readVerifiedPages(body, sourceHash, pageCount, kind)) {
    if (result.page.page === pageNumber) return result;
  }
  throw new Error("Requested page is absent from the stored artifact");
}

/** Stream and checksum pages individually, keeping large reports out of memory. */
export async function* readVerifiedPages(body: ReadableStream, sourceHash: string,
                                        pageCount: number, kind: "source" | "structure") {
  if (!Number.isSafeInteger(pageCount) || pageCount < 1 || !HASH.test(sourceHash)) {
    throw new Error("Invalid source page request");
  }
  const reader = body.pipeThrough(new DecompressionStream("gzip")).pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "", position = -1;
  let manifest: Record<string, unknown> | null = null;
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += value ?? "";
      if (buffer.length > 24_000_000) throw new Error("Page exceeds the preview limit");
      let newline: number;
      while ((newline = buffer.indexOf("\n")) !== -1) {
        const line = buffer.slice(0, newline);
        buffer = buffer.slice(newline + 1);
        position++;
        if (position === 0) {
          const parsed: unknown = JSON.parse(line);
          if (!isRecord(parsed) || parsed.type !== `${kind}_manifest` || parsed.page_count !== pageCount
              || !isRecord(parsed.source) || parsed.source.pdf_sha256 !== sourceHash
              || !Array.isArray(parsed.page_sha256) || parsed.page_sha256.length !== pageCount
              || !parsed.page_sha256.every((h) => typeof h === "string" && HASH.test(h))) {
            throw new Error("Invalid page manifest; this capture may need updating");
          }
          manifest = parsed;
        } else {
          if (!manifest || position > pageCount
              || await sha256(line) !== (manifest.page_sha256 as string[])[position - 1]) {
            throw new Error("Page checksum mismatch");
          }
          const page: unknown = JSON.parse(line);
          if (!isRecord(page) || page.page !== position
              || page.type !== (kind === "source" ? "source_page" : "structured_page")) {
            throw new Error("Page identity mismatch");
          }
          yield { manifest, page };
        }
      }
      if (done) break;
    }
    if (position !== pageCount || buffer.trim()) throw new Error("Requested page is absent or has trailing content in the stored artifact");
  } finally {
    await reader.cancel().catch(() => undefined);
  }
}
