/**
 * Lightweight topical tagging for TCMB/BDDK raw-feed items.
 *
 * The stored `category` column is a useless constant ("press_release" /
 * "duyuru"), so a topical tag is derived from the title via keyword
 * matching. Pure + synchronous — safe to call during server render.
 *
 * One tag surfaces per card: the topic derived below. (A companion
 * source-tag helper lived here until 2026-07-27 — the cards render the source
 * themselves, so nothing had called it for some time.)
 */

export interface Tag {
  label: string;
  /** Tailwind classes for the pill (bg + text). */
  className: string;
}

// All pill colours are semantic/chart TOKENS (never raw hex or Tailwind
// pastels) so they adapt to dark mode with the rest of the theme.
const NEUTRAL = "bg-muted text-muted-foreground";

// Ordered keyword rules — first match wins. Titles are English (TCMB) or
// Turkish (BDDK), so both languages' keywords live in one list. Patterns use
// word boundaries (\b) to avoid substring false-positives: bare `repo` once
// matched "Report", `ratio` matched "cooperation", `payment` matched
// "Repayments". Keep boundaries when editing.
const RULES: { test: RegExp; tag: Tag }[] = [
  // TCMB — monetary policy
  { test: /interest rate|policy committee|monetary policy|\bmpc\b|quantitative tightening|tightening measures|faiz/i,
    tag: { label: "Monetary Policy", className: "bg-warning/15 text-warning" } },
  // Capital / macroprudential rules (before Liquidity so "Macroprudential
  // Framework and Liquidity Steps" lands here, not in Liquidity)
  { test: /macroprudential|capital adequacy|reserve requirement|securities maintenance|\bratios?\b|makro/i,
    tag: { label: "Macroprudential", className: "bg-chart-5/15 text-foreground" } },
  // TCMB — liquidity / FX operations
  { test: /liquidity|likidite|\bswap\b|lira-settled|\bfx\b|foreign exchange|foreign currency|rediscount|forward|\brepo\b|protected (?:deposit|account)|yuvam/i,
    tag: { label: "Liquidity & FX", className: "bg-info/10 text-info" } },
  // Payments / open banking / systems (specific terms — not the bare words
  // "payment"/"system", which leak into "Repayments"/"Systemic"/"Balance of
  // Payments"). `ödeme` retained for BDDK payment-institution items.
  { test: /open banking|\bfast\b|payment system|electronic money|elektronik para|ödeme|digital turkish lira|interbank card|request-to-pay|center of payments|overlay service/i,
    tag: { label: "Payments & Systems", className: "bg-chart-2/15 text-foreground" } },
  // Reports / briefings / assembly notices (incl. Inflation Report briefings)
  { test: /inflation report|faaliyet raporu|\breport\b|briefing|general assembly|\brapor/i,
    tag: { label: "Report", className: NEUTRAL } },
  // BDDK — licensing
  { test: /faaliyet izni|kuruluş izni|kurulmasına izin/i,
    tag: { label: "Licensing", className: "bg-positive/10 text-positive" } },
  // BDDK — revocation / cancellation
  { test: /iptal/i,
    tag: { label: "Revocation", className: "bg-negative/10 text-negative" } },
  // BDDK — generic board decision (after the more specific BDDK rules)
  { test: /kurul kararı/i,
    tag: { label: "Board Decision", className: "bg-primary/10 text-primary" } },
];

export function topicTag(title: string): Tag {
  for (const r of RULES) {
    if (r.test.test(title)) return r.tag;
  }
  return { label: "Announcement", className: NEUTRAL };
}
