# Carthago Website Evaluation

**Evaluation date:** 12 July 2026  
**Production site:** <https://carthago.app/>  
**Overall rating:** **7.8/10**

## Verdict

The site is strong and distinctive, rising above 8/10 for an expert banking audience. Its analytical structure and visual identity are excellent. The largest weaknesses are performance and accessibility, not the core design.

| Area | Rating |
| --- | ---: |
| Analytical content | 9/10 |
| Visual design | 8.5/10 |
| Desktop UX | 8.5/10 |
| Mobile UX | 7/10 |
| Engineering | 8/10 |
| SEO | 8.5/10 |
| Accessibility | 6.5/10 |
| Performance | 6/10 |

## Highest-priority findings

### 1. Core pages hydrate too heavily on mobile

Lighthouse performance scored 58 on [Overview](https://carthago.app/), 66 on [Compare](https://carthago.app/cross-bank), and 57 on the [Akbank page](https://carthago.app/banks/AKBNK). LCP was 4.1–4.5 seconds, while the Akbank page blocked the main thread for 2.62 seconds. The problem is primarily React/Recharts execution and layout work, not excessive network transfer.

### 2. Accessibility is visibly weaker than the design quality

The pale `text-faint` color produces contrast ratios around 1.7–2.4:1. There is extensive 8–10px text, 18px-high bank selector targets, skipped heading levels, and data tables without headers. These originate largely in `web/app/components/desk.tsx`. Lighthouse accessibility scored 92–95, but meaningful chart accessibility is not covered: most Recharts SVGs have no useful accessible description or visible data-table alternative.

### 3. Every inspected page throws a client-side error

The inline theme initializer calls an undefined `__name`. Theme switching ultimately works, including dark-mode detection, but the exception can cause flash or inconsistent initial rendering. Lighthouse also recorded Cloudflare Analytics CORS failures, so the manually injected beacon in `web/app/components/Beacon.tsx` needs operational verification.

### 4. The public trust layer is incomplete

For a financial-data product, there is no public About, methodology, data dictionary, privacy, terms, or contact page. The recurring colophon and transparent source labels are good, but they are not a substitute—especially while collecting analytics and publishing AI-synthesized regulation summaries.

### 5. Mobile works, but remains desktop analysis compressed onto a phone

There is no body-level overflow, the navigation drawer works, and dense surfaces use contained horizontal scrolling. However, Compare contains 720–825px-wide scorecards and tables, with little indication that users should swipe. Chart export controls in `web/app/components/ui/chart-export.tsx` are hover-revealed, making them difficult to discover on touch devices.

### 6. Some inexpensive performance gains remain

The 256×256 logo is 68KB but displayed at 28×28 and explicitly bypasses Next image optimization in `web/app/components/Nav.tsx`. Lighthouse estimates roughly 66–73KB of image savings. Pages also produce substantial server markup—up to roughly 899KB uncompressed on `/rates`—and all 32 data pages are forced dynamic with `no-store` HTML responses.

## What is already excellent

- The “brief first, evidence second” hierarchy is unusually effective.
- Freshness, reporting periods, computation rules, peer frames, and caveats are explicit.
- Compare correctly distinguishes rank from distance and names the comparison population.
- Navigation grouping and active states are clear; mobile menu, theme toggle, bank selection, and route navigation all worked.
- Visual design is coherent: disciplined hairlines, mono figures, restrained color, and strong information density.
- Technical SEO is solid: page-specific metadata, canonicals, structured data, robots, and sitemap. Lighthouse SEO scored 100 on all three audited pages.
- All 66 sitemap URLs returned HTTP 200.
- ESLint passes, all 127 frontend tests pass, and the production build ultimately succeeds.

## Engineering caveat

The first production build transiently failed after type-checking because `pages-manifest.json` was missing; an immediate retry passed. This should be monitored as a Windows/build-pipeline flake rather than treated as a current release blocker.

## Scope

This evaluation covers product structure, visual presentation, UX, responsive behavior, implementation, accessibility, SEO, and delivery. It does not independently reconcile the published financial figures against BDDK, TCMB, or other source publications.
