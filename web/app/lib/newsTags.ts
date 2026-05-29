/**
 * Lightweight topical tagging for TCMB/BDDK raw-feed items.
 *
 * The stored `category` column is a useless constant ("press_release" /
 * "duyuru"), so a topical tag is derived from the title via keyword
 * matching. Pure + synchronous — safe to call during server render.
 *
 * Two tags surface per card: the source (TCMB/BDDK) and the topic below.
 */
import type { NewsSource } from "./news";

export interface Tag {
  label: string;
  /** Tailwind classes for the pill (bg + text). */
  className: string;
}

const NEUTRAL = "bg-neutral-100 text-neutral-600";

// Source pills reuse the per-source accent colors from the feed cards.
const SOURCE_TAGS: Record<NewsSource, Tag> = {
  tcmb: { label: "TCMB", className: "bg-[#1f4068]/10 text-[#1f4068]" },
  bddk: { label: "BDDK", className: "bg-[#0f7b6c]/10 text-[#0f7b6c]" },
  kap: { label: "KAP", className: "bg-[#7a0d2e]/10 text-[#7a0d2e]" },
};

export function sourceTag(source: string): Tag {
  return SOURCE_TAGS[source as NewsSource] ?? { label: source.toUpperCase(), className: NEUTRAL };
}

// Ordered keyword rules — first match wins. Titles are English (TCMB) or
// Turkish (BDDK), so both languages' keywords live in one list. Patterns use
// word boundaries (\b) to avoid substring false-positives: bare `repo` once
// matched "Report", `ratio` matched "cooperation", `payment` matched
// "Repayments". Keep boundaries when editing.
const RULES: { test: RegExp; tag: Tag }[] = [
  // TCMB — monetary policy
  { test: /interest rate|policy committee|monetary policy|\bmpc\b|quantitative tightening|tightening measures|faiz/i,
    tag: { label: "Monetary Policy", className: "bg-amber-100 text-amber-700" } },
  // Capital / macroprudential rules (before Liquidity so "Macroprudential
  // Framework and Liquidity Steps" lands here, not in Liquidity)
  { test: /macroprudential|capital adequacy|reserve requirement|securities maintenance|\bratios?\b|makro/i,
    tag: { label: "Macroprudential", className: "bg-violet-100 text-violet-700" } },
  // TCMB — liquidity / FX operations
  { test: /liquidity|likidite|\bswap\b|lira-settled|\bfx\b|foreign exchange|foreign currency|rediscount|forward|\brepo\b|protected (?:deposit|account)|yuvam/i,
    tag: { label: "Liquidity & FX", className: "bg-sky-100 text-sky-700" } },
  // Payments / open banking / systems (specific terms — not the bare words
  // "payment"/"system", which leak into "Repayments"/"Systemic"/"Balance of
  // Payments"). `ödeme` retained for BDDK payment-institution items.
  { test: /open banking|\bfast\b|payment system|electronic money|elektronik para|ödeme|digital turkish lira|interbank card|request-to-pay|center of payments|overlay service/i,
    tag: { label: "Payments & Systems", className: "bg-teal-100 text-teal-700" } },
  // Reports / briefings / assembly notices (incl. Inflation Report briefings)
  { test: /inflation report|faaliyet raporu|\breport\b|briefing|general assembly|\brapor/i,
    tag: { label: "Report", className: "bg-neutral-200 text-neutral-700" } },
  // BDDK — licensing
  { test: /faaliyet izni|kuruluş izni|kurulmasına izin/i,
    tag: { label: "Licensing", className: "bg-emerald-100 text-emerald-700" } },
  // BDDK — revocation / cancellation
  { test: /iptal/i,
    tag: { label: "Revocation", className: "bg-rose-100 text-rose-700" } },
  // BDDK — generic board decision (after the more specific BDDK rules)
  { test: /kurul kararı/i,
    tag: { label: "Board Decision", className: "bg-indigo-100 text-indigo-700" } },
];

export function topicTag(title: string): Tag {
  for (const r of RULES) {
    if (r.test.test(title)) return r.tag;
  }
  return { label: "Announcement", className: NEUTRAL };
}
