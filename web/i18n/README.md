# Website languages

The public dashboard supports English and Turkish. The operator-only admin tools,
source documents, news headlines, transcripts and stored research prose retain
their original language. No data is translated or written back to D1.

`next-intl` supplies a request-scoped locale to server and client components.
`request.ts` chooses the supported `carthago-locale` cookie first, and otherwise
Turkish, regardless of the browser's `Accept-Language` header. The TR/EN switcher
sets a one-year, HTTP-only, same-site cookie through a server action. Next.js
rerenders the current page without changing its URL, query parameters or filters.
The preference is separate from analytics consent. Existing canonical URLs stay
unchanged; there are no language-prefixed routes or separate language sitemaps.

English text at the call site is the source key. `tr.json` is the authored Turkish
catalog; source whitespace is normalized for lookup, with outer whitespace kept.
Unknown text is preserved. Add both languages when changing public display copy:

```tsx
// Async server components:
const tx = await getText(); // @/i18n/server
// Synchronous server or client components:
const tx = useText(); // @/i18n/use-text, always before early returns

<h1>{tx("Overview")}</h1>
<p>{tx("{0} — public", { 0: amount })}</p>
```

Use explicit numbered slots for computed sentences, rather than translating an
already-interpolated English sentence. Translate only displayed labels: never
query keys, tickers, financial values, CSS classes, predicates, API payloads or
CSV data. Turkish may omit an English plural suffix slot, but must retain every
figure, sign, unit, qualification and condition. Keep original quotations verbatim
and mark their language with `lang` and `translate="no"` when known.

Pure analytical builders take an optional locale, defaulting to English so the
API, existing callers and English prose gates retain their behavior. Pass
`tx.locale` from public pages. Stored English LLM headlines are used only in
English; Turkish uses the deterministic read with the same inputs and thresholds.
The hash and known-number gates remain unchanged.

Chart formatting uses `useChartFormat` / `createFormatters`; date labels use
`formatDateLabel`. These never change source units or period identifiers. Visible
metadata is translated with `localizeMetadata`; canonicals and robots rules stay
intact. Use `latin-ext` fonts for Turkish glyphs.

Run `npm run lint`, `npx tsc --noEmit`, `npm run test`, and `npm run build`.
Tests cover locale selection, cookie validation, per-locale isolation, interpolation,
null versus zero, chart descriptions/exports, and unchanged analytical decisions.
The desktop switcher sits below the brand, and the mobile switcher in the top
bar, so neither is covered by the analytics consent banner. For browser QA, test
EN/TR switching before dismissing that banner, reload, query/filter preservation,
mobile navigation and long Turkish labels. Data routes require an up-to-date **local** D1
fixture; schema/data gaps in that fixture must not become fabricated UI values.
