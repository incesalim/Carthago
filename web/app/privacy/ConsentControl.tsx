"use client";

import { useText } from "@/i18n/use-text";
import { clearConsent, writeConsent } from "@/app/lib/consent";
import { useConsent, useHydrated } from "@/app/lib/use-consent";

/**
 * The withdrawal path. A consent you cannot take back on the page that explains
 * it is not a consent — so /privacy states your current answer and lets you
 * change it in one click, without hunting through browser settings.
 *
 * Renders a placeholder line until mounted: the answer lives in localStorage, so
 * the server cannot know it, and guessing would show every visitor the wrong
 * state for a frame.
 */
export default function ConsentControl() {
  const tx = useText();
  const consent = useConsent();
  const hydrated = useHydrated();

  const state =
    !hydrated
      ? "Checking your current choice…"
      : consent === "granted"
        ? "Google Analytics is ON for this browser — you accepted."
        : consent === "denied"
          ? "Google Analytics is OFF for this browser — you declined."
          : "You have not answered yet, so Google Analytics is OFF.";

  return (
    <div className="mt-1 rounded-md border border-border bg-muted/40 px-4 py-3.5">
      <p className="text-[13px] font-medium text-foreground">{tx(state)}</p>
      <div className="mt-2.5 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => writeConsent("denied")}
          disabled={consent === "denied"}
          className="min-h-11 rounded-md border border-border px-4 text-[12.5px] font-medium text-foreground hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-45"
        >{tx("Turn off")}</button>
        <button
          type="button"
          onClick={() => writeConsent("granted")}
          disabled={consent === "granted"}
          className="min-h-11 rounded-md border border-primary bg-primary px-4 text-[12.5px] font-medium text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-45"
        >{tx("Turn on")}</button>
        {hydrated && consent != null && (
          <button
            type="button"
            onClick={() => clearConsent()}
            className="min-h-11 px-2 text-[12.5px] font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          >{tx("Ask me again")}</button>
        )}
      </div>
      <p className="mt-2 text-[12px] leading-snug text-muted-foreground">{tx("Turning it off does not delete what Google already received; it stops the tag from loading from now on. To remove data already collected, use the contact address below.")}</p>
    </div>
  );
}
