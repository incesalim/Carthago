/**
 * Admin auth — verify a Cloudflare Access JWT, safe-by-default.
 *
 * Cloudflare Access sits in front of the `/admin*` and `/api/admin/*` paths and
 * injects a signed `Cf-Access-Jwt-Assertion` header. We verify that JWT against
 * the team's public JWKS using native WebCrypto (no extra dependency — works in
 * both the Workers runtime and Node).
 *
 * Safe-by-default: if Access isn't configured yet (no team domain / AUD) or the
 * header is missing/invalid, `requireAdmin()` throws and the caller returns 403.
 * So `/admin` is never publicly readable, even before the Access policy is live.
 *
 * Local dev: set `ADMIN_DEV_BYPASS=1` to skip verification entirely.
 */
import { headers } from "next/headers";
import { envFlag, getEnv } from "./cf-env";

const ACCESS_HEADER = "cf-access-jwt-assertion";

export class AdminAuthError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AdminAuthError";
  }
}

export interface AdminIdentity {
  email: string;
  bypass?: boolean;
}

// --- base64url helpers ---
function b64urlToBytes(s: string): Uint8Array {
  const pad = s.length % 4 === 0 ? "" : "=".repeat(4 - (s.length % 4));
  const bin = atob(s.replace(/-/g, "+").replace(/_/g, "/") + pad);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}
function b64urlToString(s: string): string {
  return new TextDecoder().decode(b64urlToBytes(s));
}

interface Jwk {
  kid: string;
  kty: string;
  n: string;
  e: string;
  alg?: string;
}

// Module-scoped JWKS cache (keys rotate rarely; 1h TTL).
let jwksCache: { domain: string; keys: Jwk[]; at: number } | null = null;
const JWKS_TTL_MS = 60 * 60 * 1000;

async function getJwks(teamDomain: string): Promise<Jwk[]> {
  const now = Date.now();
  if (jwksCache && jwksCache.domain === teamDomain && now - jwksCache.at < JWKS_TTL_MS) {
    return jwksCache.keys;
  }
  const res = await fetch(`https://${teamDomain}/cdn-cgi/access/certs`);
  if (!res.ok) throw new AdminAuthError(`failed to fetch Access certs (${res.status})`);
  const jwks = (await res.json()) as { keys: Jwk[] };
  jwksCache = { domain: teamDomain, keys: jwks.keys, at: now };
  return jwks.keys;
}

async function verifyAccessJwt(
  token: string,
  teamDomain: string,
  aud: string,
): Promise<AdminIdentity> {
  const parts = token.split(".");
  if (parts.length !== 3) throw new AdminAuthError("malformed JWT");
  const [headerB64, payloadB64, sigB64] = parts;

  const header = JSON.parse(b64urlToString(headerB64)) as { kid?: string; alg?: string };
  if (header.alg !== "RS256") throw new AdminAuthError(`unexpected alg ${header.alg}`);

  const jwk = (await getJwks(teamDomain)).find((k) => k.kid === header.kid);
  if (!jwk) throw new AdminAuthError("signing key not found");

  const key = await crypto.subtle.importKey(
    "jwk",
    { kty: jwk.kty, n: jwk.n, e: jwk.e, alg: "RS256", ext: true } as JsonWebKey,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["verify"],
  );
  const ok = await crypto.subtle.verify(
    "RSASSA-PKCS1-v1_5",
    key,
    b64urlToBytes(sigB64) as unknown as BufferSource,
    new TextEncoder().encode(`${headerB64}.${payloadB64}`) as unknown as BufferSource,
  );
  if (!ok) throw new AdminAuthError("signature verification failed");

  const payload = JSON.parse(b64urlToString(payloadB64)) as {
    aud?: string | string[];
    exp?: number;
    iss?: string;
    email?: string;
  };
  const now = Math.floor(Date.now() / 1000);
  if (payload.exp && payload.exp < now) throw new AdminAuthError("token expired");
  const auds = Array.isArray(payload.aud) ? payload.aud : payload.aud ? [payload.aud] : [];
  if (!auds.includes(aud)) throw new AdminAuthError("aud mismatch");
  if (payload.iss && payload.iss !== `https://${teamDomain}`) {
    throw new AdminAuthError("iss mismatch");
  }
  return { email: payload.email ?? "unknown" };
}

/**
 * Verify the current request is an authenticated admin. Throws AdminAuthError
 * on any failure (missing config, missing/invalid token).
 */
export async function requireAdmin(): Promise<AdminIdentity> {
  const env = await getEnv();
  if (envFlag(env.ADMIN_DEV_BYPASS)) {
    return { email: "dev-bypass@local", bypass: true };
  }
  const teamDomain = env.CF_ACCESS_TEAM_DOMAIN;
  const aud = env.CF_ACCESS_AUD;
  if (!teamDomain || !aud) {
    throw new AdminAuthError(
      "Cloudflare Access not configured (set CF_ACCESS_TEAM_DOMAIN + CF_ACCESS_AUD)",
    );
  }
  const token = (await headers()).get(ACCESS_HEADER);
  if (!token) throw new AdminAuthError("missing Cf-Access-Jwt-Assertion header");
  return verifyAccessJwt(token, teamDomain, aud);
}

/**
 * Route-handler convenience: returns either the identity or a ready 403
 * Response. Usage:
 *   const gate = await requireAdminOr403();
 *   if ("response" in gate) return gate.response;
 */
export async function requireAdminOr403(): Promise<
  { identity: AdminIdentity } | { response: Response }
> {
  try {
    return { identity: await requireAdmin() };
  } catch (e) {
    const detail = e instanceof Error ? e.message : "forbidden";
    return { response: Response.json({ error: "forbidden", detail }, { status: 403 }) };
  }
}
