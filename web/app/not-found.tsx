import Link from "next/link";
import { useText } from "@/i18n/use-text";

export default function NotFound() {
  const tx = useText();
  return (
    <main className="mx-auto max-w-3xl px-5 py-10 lg:px-8">
      <p className="font-mono text-sm text-muted-foreground">404</p>
      <h1 className="mt-2 text-2xl font-semibold">{tx("Page not found")}</h1>
      <p className="mt-3 text-sm text-muted-foreground">{tx("This page does not exist or has moved.")}</p>
      <Link href="/" className="mt-5 inline-block text-sm font-medium text-primary hover:underline">{tx("Back to the dashboard")}</Link>
    </main>
  );
}
