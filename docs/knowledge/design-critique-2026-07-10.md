# Design critique — carthago.app (2026-07-10)

**Status:** Proposal / not acted on. An honest visual read of the live site after the user
said they were dissatisfied with the design and asked for inspiration + a targeted critique.
Pages reviewed live: `/` (Overview), `/banks`, `/banks/AKBNK`, light + dark themes.

## Verdict

The design is **not bad** — it has a real, deliberate point of view (serif editorial
headlines + letter-spaced mono labels on a warm cream background with a muted "FT / old-money"
palette). That already puts it ahead of the generic Tailwind-dashboard look. What's holding it
back is a handful of specific, fixable things — mostly **flatness (no surface layering)**,
**unreadable multi-series charts**, and **an over-applied type signature** — plus one outright
bug on the flagship Banks page.

## What's genuinely working (keep)

- Clear IA: sidebar grouped Sector / By bank / Markets & macro is sensible and scannable.
- Distinctive editorial voice (serif headlines) vs. cookie-cutter SaaS dashboards.
- "The Read" narrative layer — a real differentiator most data sites don't have.
- Bank detail page structure: logo header, tab bar, rank chips ("6th of 30 by assets"),
  profile table, valuation KPI row. This page is the strongest in the product.
- Restrained chart chrome (subtle gridlines, no 3D/gradients).
- Competent dark mode.

## Top issues, ranked by impact

### 1. Everything sits on one warm value — no surface layering (biggest lever)
Page background, stat cards, and "The Read" box are all nearly the same cream. Cards are
separated only by a hairline, no elevation, same fill — so they don't read as objects and the
page looks flat/undifferentiated. **Fix:** introduce a second surface tone (pure-white cards on
the cream page, or a soft shadow / stronger border). One extra step of figure-ground contrast is
the single highest-ROI change. _Reference: Linear, Stripe, Koyfin surface hierarchy._

### 2. Multi-series line charts are spaghetti
The by-group charts (Loan Growth, NPL, Capital, ROE) draw 6 low-chroma lines — several
near-identical blues/greys — with only a bottom legend. At rest you cannot tell which line is
which (hover helps, but at-rest legibility is what sells a chart). **Fix:** direct end-of-line
labels; make the "Sector" line the hero and desaturate the rest; or switch to small multiples
(6 tiny charts) instead of one 6-line chart. _Reference: FT Visual Vocabulary, Economist,
Our World in Data._

### 3. The mono ALL-CAPS label is over-applied
Eyebrows, section titles, every card label (TOTAL ASSETS, ASSETS YOY), and nav headers are all
letter-spaced mono uppercase. When everything shouts, nothing does — and mono-caps at small sizes
hurt scannability and reads a bit "dated terminal." **Fix:** reserve mono-caps for ONE role
(eyebrow), put card labels in sentence case.

### 4. Density is stuck between editorial and terminal
The Overview is airy (big cards, lots of gap) but each card carries little signal (one number +
a decorative sparkline). A power-user audience expects more per screen (Koyfin/Bloomberg);
a curated-editorial audience expects fewer, more opinionated cards. Right now it's in between.
**Fix:** pick a lane — either densify the KPI grid or cut it to the 4–5 numbers that matter.

### 5. BUG — logo tiles render blank on `/banks`
On the Banks list every logo tile is an empty white box; the same logo renders fine on the
detail page (`/banks/AKBNK` shows the red AKBANK mark). Makes the flagship page look unfinished.
Investigate the list-card logo source vs. detail-page source.

### 6. Minor
- "The Read" is a good idea but a flat block of same-weight text; sub-bullets are cramped and the
  `→` arrows are ambiguous. Add scannable hierarchy.
- Brand accent (terracotta) and semantic red overlap — the ticker eyebrow and a negative price
  are both red. Separate brand accent from semantic up/down colors.
- Sparklines are purely decorative (no baseline/min-max). Either give them a reference line or drop them.

## Suggested first move
Prototype a redesign of **one** page (Overview or `/banks`) applying #1–#3, so there's a concrete
direction to react to rather than references. Tremor / shadcn-charts are drop-in-compatible with
the Next + Recharts stack.

## Status update — verified against current code (2026-07-10, later)

Re-checked every item against the live site + current code. See the companion
[design-system-audit-2026-07-10.md](design-system-audit-2026-07-10.md) (§5 scores the charts
against the FT benchmark and converges with #2 here).

- **#5 (blank logos on `/banks`) — RESOLVED.** Verified live: `/banks` now serves all 28 logo
  `<img src="/logos/*.png">` (assets 200), with ATBANK/PASHA/TSKB correctly on fallback ticker
  chips. `BankLogo` is the *same* component on list + detail and was untouched since logos
  shipped — so the "blank tiles" seen at review time was a **stale edge-cache artifact** (list
  HTML cached from before logos existed), this repo's known KV/edge-staleness pattern, not a bug.
- **#1 (flat surfaces) — STILL LIVE.** Card `#FBFAF7` vs page `#ECE8E0` is ~1 value apart; flat,
  hairline-only. Design choice, unaddressed. Highest-ROI lever.
- **#2 (spaghetti charts) — PARTIALLY ADDRESSED.** `TrendChart` now heavies the Sector line
  (2.5 vs 2), draws end-dots, and supports hover/pin isolation — but at rest still renders 6
  equal-weight lines + a bottom legend, no direct end-of-line labels. Core issue live.
- **#3 (mono-caps over-applied) — PARTLY OVERSTATED, mostly LIVE.** Section titles are serif
  (not mono-caps); but KPI labels, eyebrows, and nav-group labels are all mono-caps. Unaddressed.
- **#6 minor** — "The Read" now has tone glyphs + a driver grid (some hierarchy added ✓);
  terracotta (`#C2603A`) vs semantic negative (`#B23A3A`) overlap STILL LIVE; sparklines gained
  an end-dot + tooltip but still no baseline/min-max (mostly decorative).

**Prototype built (2026-07-10):** a redesigned Overview view applying #1–#3 (+#4 annotation, #6
sparklines) *within* the existing editorial identity, on real Apr-2026 data — surface-lifted
cards, a hero-line CAR-by-group chart with direct end-labels + a January-reset annotation, and
sentence-case KPI labels. Shared as a private Artifact for reaction (not committed to the app).

## Inspiration shortlist (full list in chat 2026-07-10)
Koyfin (density), Our World in Data (chart interaction), Tremor (implementation target),
FT Visual Vocabulary (chart choice), Linear/Stripe (surface + type), Trading Economics / FRED
(same-domain data pages).
