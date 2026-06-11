# design-sync notes — BDDK dashboard UI kit

Target: claude.ai/design project **BDDK Dashboard UI Kit** (`45ee1550-6151-41fb-b5f8-da2e1eff1568`).
Source: `web/app/components/ui` (no standalone package, no Storybook — package shape via a generated dist).

## How this repo builds

- The kit has **no dist of its own**; `cfg.buildCmd` generates one: `tsc -p web/tsconfig.ds.json`
  emits JS + `.d.ts` to `web/.ds-dist/` (gitignored), and `web/package.json` carries a
  `"types": ".ds-dist/app/components/ui/index.d.ts"` field solely so the converter's type
  extractor finds it. The Tailwind 4 CLI then compiles `.design-sync/ds-css-entry.css`
  (imports `web/app/globals.css`, adds `--font-geist-*` static stand-ins) → `web/.ds-dist/ds.css`
  (= `cfg.cssEntry`). **Run both buildCmd steps before any converter run.**
- Tailwind class sources: `web/app/**` + `.design-sync/previews/**` (via `@source` in
  ds-css-entry.css). Preview wrappers should use inline styles or utilities the app already
  uses — new utility classes only appear after re-running the Tailwind step.
- Geist + Geist Mono ship as committed woff2 (latin + latin-ext — Turkish chars and ₺ need
  latin-ext) under `.design-sync/fonts/`, wired via `cfg.extraFonts`. The app itself gets them
  from `next/font`; the `--font-geist-sans/-mono` variables are defined statically in
  ds-css-entry.css.
- Playwright: local cache pins **chromium-1194 → playwright 1.56.0** (install that exact
  version into `.ds-sync/`; latest pins 1223 and fails to launch). `typescript` must also be
  installed in `.ds-sync/` or validate skips the `.d.ts` parse check.
- `cfg.provider` wraps every preview in the app's `ThemeProvider` (next-themes), defaultTheme
  light, enableSystem false — keeps screenshots deterministic and lets ThemeToggle/Toaster render.

## Known render warns (triaged legitimate)

- `[RENDER_THIN] ThemeProvider` — invisible wrapper, height 0 by construction; deliberate
  floor card (unauthored).
- Toaster — floor card by design: renders no static DOM (sonner portal, needs a toast() call).

## Preview authoring conventions

- Import components from `"web"` (shimmed to `window.BDDKUI`); content is realistic Turkish
  banking data (bank names, CAR/NPL/ROE, ₺ figures).
- Card/Table subcomponents (CardHeader…, TableRow…) are exported top-level and keep floor
  cards; they're exercised inside the Card/Table authored previews instead.
- Previews CAN use Tailwind classes (ds-css-entry.css `@source "./previews"`), but the CSS
  only refreshes on a full buildCmd run — inline styles for wrapper layout stay the safe default.
- `var(--chart-1)`/`var(--border)` etc. work directly as SVG stroke/fill in placeholder charts.
- lucide-react bundles normally in previews; icons inherit the components' `[&_svg]:size-4`.
- Bare `<Card>` has no padding (padding lives in CardHeader/CardContent) — pad when using it
  as a raw wrapper. Vertical `Separator` needs an explicit container height (`h-full w-px`).
- DeltaBadge `format="trn"` divides by 1e6 (inputs are ₺ millions); flat threshold is
  `0.5 × 10^-decimals`. PageHeader previews: ≤1 action child or the badge cluster wraps at
  review-cell width.

## Re-sync risks

- `web/.ds-dist/` is generated and gitignored — a re-sync on a fresh clone MUST re-run
  `cfg.buildCmd` first or the converter sees no dist/`.d.ts`.
- The `"types"` field in `web/package.json` points at the gitignored dist — harmless to the
  app, but don't "clean it up"; the converter needs it.
- Geist woff2s are pinned copies of Google Fonts v5/v6 — if the app's `next/font` families
  change, refresh `.design-sync/fonts/`.
- The Tailwind compile snapshots the app's utility usage; if components gain classes via app
  refactors, the next sync's buildCmd run picks them up automatically (deterministic), but a
  hand-rebuilt ds.css from a stale checkout would silently drop styles.
- Token values live in `web/app/globals.css`; the bundle copies them at build time — palette
  changes need a re-sync to reach claude.ai/design.
