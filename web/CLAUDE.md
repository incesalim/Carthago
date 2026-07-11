@AGENTS.md

# web/ — Next.js dashboard

Next 16 (App Router) + React 19 + Tailwind 4 + Recharts, deployed to Cloudflare
(Workers / D1 / R2 / KV) via OpenNext. A read-only analytics UI over the same D1
database the Python pipeline writes.

## Layout
- `app/` — App Router. One folder per route (kebab-case); `page.tsx` is the server
  component, and route-local client components live **alongside** it (e.g.
  `app/cross-bank/HeatmapView.tsx`, `app/banks/[ticker]/PlSankeySection.tsx`).
- `app/components/` — components shared across ≥2 routes only: charts (`TrendChart`,
  `TimeSeriesChart`, `StackedArea`, `BarByBank`, `BopFlowChart`), `Nav`, the ownership
  viz family, badges. Page-specific components belong in the route folder, not here.
- `app/components/ui/` — the design system (Card, Stat, Section, Table, PageHeader,
  ChartCard, …). Import via the barrel: `import { Card, Section } from "@/app/components/ui"`.
- `app/lib/` — data access + transforms. `db.ts` is the cached D1 wrapper (`cachedAll`);
  per-domain query modules (`metrics.ts`, `economy.ts`, `audit.ts`, `bist.ts`, …);
  `chart-theme.ts` / `chart-format.ts` for chart colours + number formatting;
  `pipeline-graph.ts` is the hand-authored `/pipeline` topology (kept in sync with the
  workflow files by `scripts/check_pipeline_graph_sync.py`).
- `app/api/` — small admin / monitoring routes (auth, GitHub run status, market ticker).

## Conventions
- Pages are async server components with `export const dynamic = "force-dynamic"`; fan
  out queries with `Promise.all`.
- Naming: components PascalCase, lib modules kebab-case, routes kebab-case.
- Charts take number formatting from `app/lib/chart-format.ts` (`nf`, `formatters`) —
  don't re-declare a local `nf`.

## Design
All UI work follows **[DESIGN.md](DESIGN.md)** ("The Desk" system): white sheet on
paper ground, hairlines not boxes, blue = links only, mono figures, two-layer
pages (computed brief above carried-over evidence). Chart colours live in
`app/lib/chart-theme.ts` in LOCKSTEP with `app/globals.css` tokens.

## Local dev & deploy
- `npm run dev` — local dev (seed a local D1 first; see [the local-dev notes](../docs/OPERATIONS.md)).
- `npm run build` — production build; must stay green (CI gates deploy). **Pinned to
  `next build --webpack`, NOT Turbopack** — see the warning below.
- `npm run lint` / `npm run test` (vitest).
- Deploy: `npm run deploy` (OpenNext → Cloudflare; OpenNext runs `npm run build` for the
  app build). `npm run preview` is known-broken on Windows — verify live after deploy
  (`curl` a few routes — a Turbopack regression returns 500 on **every** page while CI
  still reports the deploy "success"). Stack detail: [../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).

> ⚠️ **Keep the `--webpack` flag.** Next 16 defaults `next build` to Turbopack, which
> names server SSR chunks with square brackets (`server/chunks/ssr/[root-of-the-server]__….js`).
> The OpenNext Cloudflare Worker runtime can't resolve those bracketed filenames at load
> time → `ChunkLoadError` on a shared root chunk → HTTP 500 on every route. The build and
> deploy commands both exit 0, so CI shows green; only a live request reveals it. Building
> with webpack (numeric chunk names) is the fix. Don't drop `--webpack` from the `build`
> script (and don't let a deps PR re-introduce a Turbopack-only build) until OpenNext
> Cloudflare resolves bracketed Turbopack chunk names.
