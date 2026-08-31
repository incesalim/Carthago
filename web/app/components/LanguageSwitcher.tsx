"use client";

import { useState, useTransition } from "react";
import { useLocale } from "next-intl";
import { setLocale } from "@/i18n/actions";
import { LOCALES } from "@/i18n/config";
import { useText } from "@/i18n/use-text";

export default function LanguageSwitcher() {
  const locale = useLocale();
  const text = useText();
  const [pending, startTransition] = useTransition();
  const [failed, setFailed] = useState(false);

  return (
    <div className="relative">
      <div role="group" aria-label={text("Language")} aria-busy={pending}
        className="inline-flex items-center gap-0.5 font-mono text-[11px]">
        {LOCALES.map((choice) => (
          <button key={choice} type="button" lang={choice}
            aria-label={choice === "tr" ? "Türkçe" : "English"}
            aria-pressed={locale === choice} disabled={pending}
            onClick={() => {
              if (choice === locale) return;
              setFailed(false);
              startTransition(async () => {
                try { await setLocale(choice); }
                catch { setFailed(true); }
              });
            }}
            className={`min-h-9 min-w-9 border-b-2 px-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50 ${locale === choice ? "border-foreground font-semibold text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}
          >{choice.toUpperCase()}</button>
        ))}
      </div>
      {failed && <p role="alert" className="absolute right-0 top-full z-50 w-48 border border-border bg-card p-2 text-xs text-foreground">
        {text("Could not change language. Please try again.")}
      </p>}
    </div>
  );
}
