# UI design system

Modular, token-driven primitives used app-wide. Import everything from the
barrel:

```tsx
import { PageHeader, Stat, Card, Badge, ChartCard, Table } from "@/app/components/ui";
```

## Design tokens

Defined as CSS variables in `app/globals.css` and exposed as Tailwind utilities
via `@theme inline`. Light values live under `:root`, dark under `.dark`
(toggled by `next-themes`). **Never hard-code colours** — use the semantic
utility so light/dark stay correct:

| Token | Utilities | Use |
|---|---|---|
| `background` / `foreground` | `bg-background` `text-foreground` | page surface + body text |
| `card` / `card-foreground` | `bg-card` | raised surfaces (cards, charts) |
| `muted` / `muted-foreground` | `bg-muted` `text-muted-foreground` | secondary text, subtle fills |
| `border` / `input` | `border-border` | hairlines, inputs (default border colour app-wide) |
| `accent` | `bg-accent` | hover states |
| `primary` | `bg-primary` `text-primary` | brand maroon accent |
| `positive` `negative` `warning` `info` | `text-positive`, `bg-warning/15`, … | data semantics (tint with `/10`–`/15`) |
| `chart-1…6` | `bg-chart-1` | categorical chart series (mirrors `useChartTheme`) |
| `--radius` | `rounded-md/lg/xl` | corner radii |

## Primitives

- **`PageHeader`** — page title block (`eyebrow`, `title`, `description`, action `children`).
- **`Section`** — labelled content block with optional heading row.
- **`Stat`** — KPI tile: `label`, `value`, `hint`, `tone`, optional sparkline child.
- **`Card`** (+ `CardHeader/Title/Description/Content/Footer`) — generic surface.
- **`ChartCard`** — card chrome shared by every chart (`title`, `description`, `action`).
- **`Badge`** — pill with `default/secondary/outline/positive/negative/warning/info`.
- **`Button`** (+ `buttonVariants`) — `default/secondary/outline/ghost/destructive/link` × `sm/default/lg/icon`.
- **`Table`** (+ `TableHeader/Body/Row/Head/Cell`) — token-styled, horizontally scrollable.
- **`Skeleton`**, **`Separator`** — loading + dividers.
- **`ThemeToggle`**, **`ThemeProvider`**, **`Toaster`** — theming + toasts.

## Charts

Recharts can't read CSS variables from SVG attributes, so chart colours come
from `useChartTheme()` (`app/lib/chart-theme.ts`), which returns the
theme-correct `palette`, grid/axis/cursor colours, and a `tooltipStyles()`
helper. All chart wrappers use `ChartCard`.

## Helper

`cn(...)` (`app/lib/cn.ts`) merges class names and resolves Tailwind conflicts —
every primitive routes its `className` through it, so callers can override.
