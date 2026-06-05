/**
 * POST /api/admin/login — exchange the shared password for a signed session
 * cookie. Accepts a normal HTML form post (redirects back to /admin) or JSON
 * (returns JSON). Used by the password-mode login form.
 */
import { createSessionToken, SESSION_COOKIE, SESSION_TTL_HOURS, timingSafeEqual } from "@/app/lib/admin-auth";
import { getEnv } from "@/app/lib/cf-env";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const env = await getEnv();
  const password = env.ADMIN_PASSWORD;
  const isJson = (req.headers.get("content-type") ?? "").includes("application/json");

  if (!password) {
    return isJson
      ? Response.json({ error: "password auth not configured" }, { status: 409 })
      : Response.redirect(new URL("/admin?error=config", req.url), 303);
  }

  let supplied = "";
  try {
    if (isJson) {
      supplied = String(((await req.json()) as { password?: unknown })?.password ?? "");
    } else {
      supplied = String((await req.formData()).get("password") ?? "");
    }
  } catch {
    supplied = "";
  }

  const ok = supplied.length > 0 && timingSafeEqual(supplied, password);
  if (!ok) {
    return isJson
      ? Response.json({ error: "invalid password" }, { status: 401 })
      : Response.redirect(new URL("/admin?error=1", req.url), 303);
  }

  const token = await createSessionToken(password);
  const cookie =
    `${SESSION_COOKIE}=${token}; Path=/; HttpOnly; Secure; SameSite=Lax; ` +
    `Max-Age=${SESSION_TTL_HOURS * 3600}`;

  if (isJson) {
    return Response.json({ ok: true }, { headers: { "Set-Cookie": cookie } });
  }
  return new Response(null, {
    status: 303,
    headers: { "Set-Cookie": cookie, Location: new URL("/admin", req.url).toString() },
  });
}
