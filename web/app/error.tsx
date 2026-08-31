"use client";

import { useText } from "@/i18n/use-text";

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const tx = useText();
  return (
    <main className="mx-auto max-w-3xl px-5 py-10 lg:px-8">
      <h1 className="text-2xl font-semibold">{tx("This page couldn’t load")}</h1>
      <p className="mt-3 text-sm text-muted-foreground">{tx("A server error occurred. Reload to try again.")}</p>
      <button type="button" onClick={reset} className="mt-5 rounded border border-border px-4 py-2 text-sm font-medium text-primary focus-visible:outline-2 focus-visible:outline-ring">
        {tx("Reload")}
      </button>
    </main>
  );
}
