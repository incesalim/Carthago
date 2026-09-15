"use client";

import { useText } from "@/i18n/use-text";
import Link from "next/link";
import Script from "next/script";
import { writeConsent } from "@/app/lib/consent";
import { useConsent, useHydrated } from "@/app/lib/use-consent";

/**
 * The consent gate for Google Analytics, and the bar that asks for it.
 *
 * GA4 is opt-IN: `gtag.js` is not requested at all until the visitor accepts, so
 * a "no" (or no answer) means Google never sees the request — nothing to
 * suppress afterwards, no cookie written and then deleted.
 *
 * Server/client boundary: the measurement id is read on the server (it is a
 * public value) and passed in; the DECISION is client-only, because it lives in
 * localStorage. Both the banner and the scripts render only after mount, so the
 * server HTML and the first client render agree — a consent UI that flashes
 * during hydration is a consent UI that gets clicked by accident.
 */
export default function AnalyticsConsent({ measurementId }: { measurementId: string }) {
  const tx = useText();
  const consent = useConsent();
  const hydrated = useHydrated();

  // Pre-hydration: neither the scripts nor the banner. See useHydrated().
  if (!hydrated) return null;

  if (consent === "granted") {
    return (
      <>
        <Script
          src={`https://www.googletagmanager.com/gtag/js?id=${measurementId}`}
          strategy="afterInteractive"
        />
        <Script id="ga-gtag" strategy="afterInteractive">
          {tx(`window.dataLayer = window.dataLayer || [];
function gtag(){dataLayer.push(arguments);}
gtag('js', new Date());
gtag('config', '${measurementId}');`)}
        </Script>
      </>
    );
  }

  if (consent === "denied") return null;

  return (
    <div
      role="dialog"
      aria-modal="false"
      aria-labelledby="consent-title"
      className="fixed inset-x-0 bottom-0 z-50 border-t border-border bg-card/95 pb-[env(safe-area-inset-bottom)] backdrop-blur"
    >
      <div className="mx-auto flex max-w-5xl flex-col gap-2 px-4 py-2.5 sm:flex-row sm:items-center sm:justify-between sm:gap-5">
        <p id="consent-title" className="max-w-[85ch] text-xs leading-snug text-foreground">{tx("May we use Google Analytics to see which pages get read? It sets cookies and sends your visit to Google. Everything works the same if you decline — page counts still come from Cloudflare’s analytics, which sets no cookie and keeps no identifier.")}{" "}
          <Link href="/privacy" className="font-semibold text-primary underline-offset-2 hover:underline">{tx("What we collect")}</Link>
        </p>
        {/* Both choices are one click, same size, same weight — a "decline" that
            is harder to find than "accept" is not a free choice. The bar stays
            one compact row on desktop so it cannot bury the page footer. */}
        <div className="flex shrink-0 gap-2">
          <button
            type="button"
            onClick={() => writeConsent("denied")}
            className="min-h-9 rounded-md border border-border px-3 text-xs font-medium text-foreground hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          >{tx("Decline")}</button>
          <button
            type="button"
            onClick={() => writeConsent("granted")}
            className="min-h-9 rounded-md border border-primary bg-primary px-3 text-xs font-medium text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          >{tx("Accept")}</button>
        </div>
      </div>
    </div>
  );
}
