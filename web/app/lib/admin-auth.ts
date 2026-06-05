/**
 * Admin auth — two modes, safe-by-default.
 *
 *  - **password** (default for workers.dev): a single shared password
 *    (ADMIN_PASSWORD secret) gates /admin via an HMAC-signed session cookie.
 *    Works with no custom domain and leaves the public dashboard untouched.
 *  - **access** (when on a custom domain): verify the Cloudflare Access JWT
 *    (Cf-Access-Jwt-Assertion) against the team JWKS with native WebCrypto.
 *
 * Precedence: ADMIN_DEV_BYPASS → Access (if configured) → password (if set) →
 * otherwise locked. If nothing is configured, requireAdmin() throws and /admin
 * shows a Forbidden card, so it's never publicly readable.
 */
import { cookies, headers } from "next/headers";
import { envFlag, getEnv, type StringEnv } from "./cf-env";

const ACCESS_HEADER = "cf-access-jwt-assertion";
export const SESSION_COOKIE = "admin_session";
export const SESSION_TTL_HOURS = 12;

export type AuthMode = "access" | "password" | "none";

export class AdminAuthError extends Error {
  /** 'login' → show the password form; 'forbidden' → show the denied card. */
  mode: "login" | "forbidden";
  constructor(message: string, mode: "login" | "forbidden" = "forbidden") {
    super(message);
    this.name = "AdminAuthError";
    this.mode = mode;
  }
}

export interface AdminIdentity {
  email: string;
  bypass?: boolean;
}

export function authMode(env: StringEnv): AuthMode {
  if (env.CF_ACCESS_TEAM_DOMAIN && env.CF_ACCESS_AUD) return "access";
  if (env.ADMIN_PASSWORD) return "password";
  return "none";
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
function bytesToB64url(b: ArrayBuffer | Uint8Array): string {
  const arr = b instanceof Uint8Array ? b : new Uint8Array(b);
  let s = "";
  for (const x of arr) s += String.fromCharCode(x);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
function strToB64url(s: string): string {
  return bytesToB64url(new TextEncoder().encode(s));
}

/** Constant-time string compare (equal length → no early exit). */
export function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let r = 0;
  for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return r === 0;
}

// ---------------------------------------------------------------------------
// Password mode — HMAC-signed session cookie keyed on the password itself.
// ---------------------------------------------------------------------------
async function hmac(key: string, data: string): Promise<string> {
  const k = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(key) as unknown as BufferSource,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign(
    "HMAC",
    k,
    new TextEncoder().encode(data) as unknown as BufferSource,
  );
  return bytesToB64url(sig);
}

export async function createSessionToken(password: string, ttlHours = SESSION_TTL_HOURS): Promise<string> {
  const exp = Math.floor(Date.now() / 1000) + ttlHours * 3600;
  const payload = strToB64url(JSON.stringify({ exp }));
  return `${payload}.${await hmac(password, payload)}`;
}

async function verifySession(token: string, password: string): Promise<boolean> {
  const [payload, sig] = token.split(".");
  if (!payload || !sig) return false;
  if (!timingSafeEqual(sig, await hmac(password, payload))) return false;
  try {
    const { exp } = JSON.parse(b64urlToString(payload)) as { exp?: number };
    return typeof exp === "number" && exp > Math.floor(Date.now() / 1000);
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// Access mode — Cloudflare Access JWT verification (custom-domain setups).
// ---------------------------------------------------------------------------
interface Jwk {
  kid: string;
  kty: string;
  n: string;
  e: string;
  alg?: string;
}
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

async function verifyAccessJwt(token: string, teamDomain: string, aud: string): Promise<AdminIdentity> {
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

/** Verify the current request is an authenticated admin (throws otherwise). */
export async function requireAdmin(): Promise<AdminIdentity> {
  const env = await getEnv();
  if (envFlag(env.ADMIN_DEV_BYPASS)) {
    return { email: "dev-bypass@local", bypass: true };
  }
  const mode = authMode(env);

  if (mode === "access") {
    const token = (await headers()).get(ACCESS_HEADER);
    if (!token) throw new AdminAuthError("missing Cf-Access-Jwt-Assertion header");
    return verifyAccessJwt(token, env.CF_ACCESS_TEAM_DOMAIN!, env.CF_ACCESS_AUD!);
  }

  if (mode === "password") {
    const cookie = (await cookies()).get(SESSION_COOKIE)?.value;
    if (cookie && (await verifySession(cookie, env.ADMIN_PASSWORD!))) {
      return { email: "admin" };
    }
    throw new AdminAuthError("login required", "login");
  }

  throw new AdminAuthError("admin auth not configured (set ADMIN_PASSWORD)");
}

/**
 * Route-handler convenience: returns either the identity or a ready 403
 * Response.
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
