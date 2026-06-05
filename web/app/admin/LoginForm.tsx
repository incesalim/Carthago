/** Password-mode sign-in form (server-rendered; posts to /api/admin/login). */
import { Button, Card } from "@/app/components/ui";

export default function LoginForm({ error }: { error?: "wrong" | "config" }) {
  return (
    <main className="mx-auto max-w-sm px-4 py-24">
      <Card className="p-8">
        <h1 className="text-lg font-semibold text-foreground">Admin sign-in</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Enter the admin password to open the control center.
        </p>
        {error === "wrong" && (
          <p className="mt-3 text-sm text-negative">Wrong password — try again.</p>
        )}
        {error === "config" && (
          <p className="mt-3 text-sm text-warning">
            Password auth isn&rsquo;t set up yet (add the <code className="rounded bg-muted px-1">ADMIN_PASSWORD</code> secret).
          </p>
        )}
        <form method="post" action="/api/admin/login" className="mt-4 space-y-3">
          <input
            type="password"
            name="password"
            required
            autoFocus
            placeholder="Password"
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
          />
          <Button type="submit" className="w-full">
            Sign in
          </Button>
        </form>
      </Card>
    </main>
  );
}
