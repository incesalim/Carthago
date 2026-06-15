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

## Local dev & deploy
- `npm run dev` — local dev (seed a local D1 first; see [the local-dev notes](../docs/OPERATIONS.md)).
- `npm run build` — production build; must stay green (CI gates deploy).
- `npm run lint` / `npm run test` (vitest).
- Deploy: `npm run deploy` (OpenNext → Cloudflare). `npm run preview` is known-broken on
  Windows — verify live after deploy. Stack detail: [../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).
