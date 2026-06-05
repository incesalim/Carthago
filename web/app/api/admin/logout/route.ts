/**
 * POST /api/admin/logout — clear the admin session cookie and return to /admin
 * (which then shows the login form).
 */
import { SESSION_COOKIE } from "@/app/lib/admin-auth";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  return new Response(null, {
    status: 303,
    headers: {
      "Set-Cookie": `${SESSION_COOKIE}=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0`,
      Location: new URL("/admin", req.url).toString(),
    },
  });
}
