/**
 * BankTabs — the per-bank page's five views.
 *
 * These replace the old in-page jump-nav. That nav anchored into ONE document
 * carrying every section at once: 6,710px of scroll, 17 headings, 28 charts, and
 * most numbers stated twice (the brief said them, then the old sections said them
 * again). Each tab now *is* the page — the server renders only the active view, so
 * the payload and the scroll both collapse.
 *
 * Each link preserves the ?statement/?mode/?view/?kind params the Financials
 * controls set, and carries the tab in the URL so a view
 * is shareable and back/forward work.
 */
import { useText } from "@/i18n/use-text";
import Link from "next/link";
import { cn } from "@/app/lib/cn";

export type BankTab = "desk" | "financials" | "risk" | "ownership" | "news";

export const BANK_TABS: Array<{ id: BankTab; label: string }> = [
  { id: "desk", label: "The Desk" },
  { id: "financials", label: "Financials" },
  { id: "risk", label: "Risk & Capital" },
  { id: "ownership", label: "Ownership" },
  { id: "news", label: "News & Filings" },
];

/** Shared by the tab strip and the Desk's links into each section. */
export function bankTabHref(ticker: string, tab: BankTab, query = ""): string {
  const params = new URLSearchParams(query);
  if (tab === "desk") params.delete("tab");
  else params.set("tab", tab);
  const qs = params.toString();
  return `/banks/${ticker}${qs ? `?${qs}` : ""}`;
}

export function BankTabs({
  ticker,
  active,
  hide = [],
  query = "",
}: {
  ticker: string;
  active: BankTab;
  /** Tabs with nothing to show for this bank — omitted rather than left empty. */
  hide?: BankTab[];
  /** The financials controls' params, preserved across tab switches. */
  query?: string;
}) {
  const tx = useText();
  const tabs = BANK_TABS.filter((t) => !hide.includes(t.id));
  return (
    <nav
      aria-label={tx("Bank sections")}
      className="sticky top-0 z-20 -mx-4 flex gap-1 overflow-x-auto border-b border-border bg-card/95 px-4 backdrop-blur sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8"
    >
      {tabs.map((t) => {
        const href = bankTabHref(ticker, t.id, query);
        const on = t.id === active;
        return (
          <Link
            key={t.id}
            href={href}
            aria-current={on ? "page" : undefined}
            className={cn(
              "whitespace-nowrap border-b-2 px-3 py-2.5 text-[13px] transition-colors",
              on
                ? "border-foreground font-semibold text-foreground"
                : "border-transparent font-normal text-muted-foreground hover:text-foreground",
            )}
          >
            {tx(t.label)}
          </Link>
        );
      })}
    </nav>
  );
}
