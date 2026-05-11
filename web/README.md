# Turkish Banking Dashboard (web)

Next.js 15 + OpenNext + Recharts dashboard deployed to Cloudflare Workers.
Reads directly from Cloudflare D1.

Production: <https://turkish-banking-dashboard.incesalim10.workers.dev>

## Local development

```bash
npm install
npm run dev          # http://localhost:3000 — hot reload
```

`npm run dev` runs against the **remote** D1 binding configured in
`wrangler.jsonc`, so local + production read identical data.

## Deploy

Pushing to `master` with changes under `web/**` triggers
`.github/workflows/deploy-cloudflare.yml`, which runs:

```bash
npm run build        # Next.js production build
npm run deploy       # OpenNext → wrangler deploy
```

Both can be run manually too.

## Layout

```
app/
├── page.tsx                  # Overview — 8 KPIs + summary charts
├── credit/                   # Loan growth, currency split, consumer mix, SME
├── deposits/                 # Total / TL / FX deposits, maturity, LDR
├── asset-quality/            # NPL by group, consumer + commercial NPL ratios
├── capital/                  # CAR, equity, leverage, RWA density
├── profitability/            # ROE, ROA, NIM, efficiency, fee mix
├── weekly/                   # BDDK weekly bulletin growth charts
├── rates/                    # TCMB EVDS — rates corridor, FX, sterilization
├── banks/                    # Index + per-bank drill-down (BS + P&L tables)
├── sector/                   # Top-level sector views (Total Assets, ratios)
├── components/
│   ├── Nav.tsx
│   ├── TrendChart.tsx        # Multi-line time series (Recharts)
│   ├── TimeSeriesChart.tsx   # Single-bank time series with multiple Y formats
│   ├── BarByBank.tsx         # Horizontal bar comparing groups at latest period
│   └── StackedArea.tsx       # Stacked composition (level + % share)
└── lib/
    ├── db.ts                 # D1 binding helper via @opennextjs/cloudflare
    ├── metrics.ts            # SQL helpers — every dashboard query lives here
    └── audit.ts              # Per-bank audit-report queries (bank_audit_*)
```

Every page is a Server Component. Routes call helpers from `app/lib/metrics.ts`
which run D1 queries server-side; results stream to client charts.

## Adding a new chart

1. If the data isn't already in D1, add the source to the ingestion
   pipeline (`src/scrapers/`) and let the cron backfill.
2. Add a typed helper to `app/lib/metrics.ts` (or `audit.ts` for
   per-bank tables).
3. Import + render in the appropriate `app/<section>/page.tsx`.

Never put SQL strings inside a page file — keep them centralized in
`metrics.ts` so the schema surface stays auditable.

## Conventions

- All numbers render with **en-US** formatting (`1,234,567.89` — comma
  thousands, dot decimal) via `Intl.NumberFormat("en-US", ...)`.
- Recharts colors come from a fixed 6-tone palette so the same group
  (e.g. "Private" banks) renders the same shade across every chart.
- Sections use `space-y-8` containers + the `Section` wrapper for visual
  rhythm; cards are `rounded-xl border-neutral-200 shadow-sm`.

## AGENTS / CLAUDE

`AGENTS.md` and `CLAUDE.md` carry per-folder guidance for AI assistants
(read the relevant Next.js docs in `node_modules/next/dist/docs/`
before generating Next.js code — this codebase pins Next 15.5 + Tailwind
v4 + OpenNext, which differ from older training data).
