# mobile/ — the Expo app

Expo SDK 57 + expo-router + React Native 0.86, TypeScript. A read-only native
client over the same D1 the website reads, via `/api/app/v1`.

## The one rule

**No arithmetic in this app.** Every ratio, deflation, streak and aggregate is
computed in `web/app/lib/` and arrives over the wire already derived. If a screen
needs a number that doesn't exist yet, add it to `web/app/lib` and expose it in
`web/app/api/app/v1/` — never compute it here.

The reason is the whole reason a second client is risky: two surfaces that
derive the same metric independently will eventually print different values for
it, and the one people trust is whichever they saw last. The app is allowed to
FORMAT (`src/format.ts`) and to write COPY around figures; it is not allowed to
make them.

## Layout
- `src/app/` — expo-router routes. `(tabs)/` is the four-tab shell; `banks/[ticker].tsx`
  is the stack detail screen. Route files hold their own screen component.
- `src/api/` — `client.ts` (fetch + timeout + typed `ApiError`), `types.ts` (wire
  shapes, hand-mirrored from the route handlers), `use-resource.ts` (the one data
  hook: stale-while-revalidate over AsyncStorage).
- `src/components/` — `ui.tsx` (Desk primitives: Text/Label/Figure/Hairline/Row/
  Section), `screen.tsx` (scroll shell, header, loading/error/stale states),
  `charts.tsx` (react-native-svg).
- `src/theme/` — the palette, type scale and spacing. `tokens.ts` is a hand-copy
  of `web/app/globals.css`, gated by `npm run check:tokens`.
- `src/format.ts` — every number that reaches the screen goes through here.

## Conventions
- Colour only via `useTheme()`. A raw hex in a component is a bug — it will be
  wrong in one of the two themes.
- Every figure is `<Figure>` (mono, tabular). Every label is `<Label>` (mono,
  caps). Body copy is `<Text>`. That is the whole type system.
- `null` renders as an em dash, never `0`. A missing disclosure and a disclosed
  zero are different facts.
- Blue (`colors.primary`) is links and routes ONLY.
- Hairlines, not boxes or cards-with-shadows.

## Checks
```
npm run typecheck     # tsc --noEmit
npx eslint .
npm run check:tokens  # tokens.ts vs web/app/globals.css
npx expo export --platform ios --output-dir .expo-export   # proves Metro can bundle it
```
All four run in CI (`.github/workflows/ci.yml`, job `mobile`). The Metro bundle
is the one that matters most: `tsc` is happy with imports Metro cannot resolve.

## Running it
```
npm start                    # then scan the QR with Expo Go
EXPO_PUBLIC_API_BASE=http://<lan-ip>:3000 npm start   # against local web/
```
`localhost` is the DEVICE's localhost on a phone — a LAN IP is required, and
getting this wrong is the usual reason a dev build shows no data.

## Not built yet
No store submission, no push notifications, no offline write path, no Turkish
localisation. See docs/PROJECT_STATE.md § "Mobile app" for what that would take.
