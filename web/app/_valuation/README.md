# `_valuation` — archived (hidden from the site)

This was the **`/valuation`** tab: forward scenario projection + intrinsic
valuation (residual income / DDM / justified P/B) for the BIST-listed banks.

It was hidden on **2026-07-10** at the user's request. The code is preserved
here intact — the leading underscore makes this a Next.js
[private folder](https://nextjs.org/docs/app/getting-started/project-structure#private-folders),
so it is **opted out of routing** (no `/valuation` route is served) but still
lives in the tree and is typechecked, so it won't bit-rot.

## Supporting code (left in place, still compiles + tested)
- `web/app/lib/valuation.ts` — the pure valuation maths (vitest cases).
- `web/app/lib/valuation-data.ts` — per-bank server-side "seed" builder.
- `web/app/lib/valuation-presets.ts` — assumption presets.

These are only referenced by this folder now; they're kept so revival is a
no-op. (Unrelated: `bistValuation` in `web/app/lib/bist.ts` powers the
"Market & Valuation" panel on each bank's own page — that is a *different*
feature and was never part of this tab.)

## To bring it back
1. `git mv web/app/_valuation web/app/valuation`
2. Re-add the nav link in `web/app/components/Nav.tsx` (the `banks` section):
   `{ href: "/valuation", label: "Valuation" },` after Compare.
3. Re-add the sitemap entry in `web/app/sitemap.ts`:
   `{ path: "/valuation", priority: 0.7, changeFrequency: "daily" },`.
4. Rebuild/redeploy and verify `/valuation` returns 200.
