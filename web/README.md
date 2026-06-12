# Turkish Banking Dashboard (web)

Next.js 16 + OpenNext + Recharts dashboard deployed to Cloudflare Workers.
Reads directly from Cloudflare D1.

Production: <https://turkish-banking-dashboard.incesalim10.workers.dev>

## Local development

```bash
npm install
npm run dev          # http://localhost:3000 — hot reload
npm run test         # vitest — unit tests for pure lib code (app/lib/*.test.ts)
```

`npm run dev` runs against the **local miniflare** D1 (`.wrangler/state/`),
which starts empty — pages that query unseeded tables 500 with
`no such table`. Seed the tables you need before testing:

```bash
# schema (run each migration file)
npx wrangler d1 execute DB --local --file=migrations/0001_baseline_schema.sql
# data — export rows from remote, convert to INSERTs, load:
npx wrangler d1 execute DB --remote --json --command "SELECT … LIMIT …" > rows.json
npx wrangler d1 execute DB --local --file=seed.sql
```

Seeding gotchas / shortcuts:

- The local SQLite mirror `../data/bddk_data.db` is usually a faster seed
  source than remote export: dump `CREATE TABLE` + `INSERT`s for just the
  tables the page under test reads.
- **Include FK-referenced tables in the seed** (e.g. `income_statement` /
  `balance_sheet` reference `bank_types`) — otherwise the DDL fails with
  `no such table` mid-file and the whole seed silently no-ops.
- Server-rendered numbers can be asserted **without a browser**: client
  components' props are embedded verbatim in the RSC payload of the HTML,
  so `curl localhost:3000/<page>` and grep for a known value (works against
  the live workers.dev URL too — handy for post-deploy checks).

`npm run preview` (full Workers runtime) is broken on Windows — and when it
does build, it can 500 every route with zero error output. Don't fight it;
verify with `npm run dev` locally and live after pushing.

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
├── page.tsx                  # Overview — KPIs + summary charts
├── credit/ deposits/ asset-quality/ capital/ profitability/ liquidity/
│                             # Monthly-bulletin sector views
├── weekly/                   # BDDK weekly bulletin growth charts
├── rates/ economy/           # TCMB EVDS — rates corridor, FX, macro outlook
├── banks/                    # Index + per-bank drill-down (BS + P&L tables,
│                             #   P&L flow Sankey, ownership radial, stages)
├── cross-bank/               # Cross-bank heatmap (ROE/ROA/NIM/cost-income…)
├── sector/                   # Top-level sector views (Total Assets, ratios)
├── ownership/                # Sector-wide KAP ownership network
├── digital/ funds/           # TBB digital-banking stats, TEFAS fund market
├── news/ disclosures/ regulation/ admin/
├── components/               # Charts + cards (design system in ui/)
└── lib/                      # One module per data domain — every D1 query
    ├── db.ts                 #   lives here, never in a page file
    ├── metrics.ts            #   monthly/weekly bulletin queries
    ├── audit.ts              #   per-bank audit-report queries (bank_audit_*)
    ├── pl-sankey.ts          #   pure P&L Sankey derivation (+ .test.ts)
    └── …                     #   kap/ownership-*, heatmap, funds, digital, …
```

Every page is a Server Component. Routes call helpers from `app/lib/*`
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
before generating Next.js code — this codebase pins Next 16 + Tailwind
v4 + OpenNext, which differ from older training data).
