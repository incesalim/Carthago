# SEO & Search Discoverability — 2026-07-07

Status: **on-page shipped & live**; off-page (Search Console verification, backlinks)
is a manual / ongoing to-do. Goal driving this work: rank for **"Turkish banking
sector data"** and related queries. Context: the [strategic review](strategic-review-2026-07.md)
named distribution/discoverability the single biggest gap.

## What shipped (on-page, live on carthago.app)

- **`web/app/robots.ts`** → `/robots.txt`: allow all, disallow `/admin` + `/api/`,
  point at the sitemap. (Cloudflare's zone-level "content signals" feature prepends
  an AI-policy comment header; our directives are appended below it.)
- **`web/app/sitemap.ts`** → `/sitemap.xml`: 30 public content routes + one URL per
  bank (from `bankSummaries()`, KV-cached), `force-dynamic`. `<lastmod>` is the real
  data-freshness date (latest reported quarter → quarter-end), not deploy time.
  `/sector` and `/sector/ratios` are intentionally excluded (they 307/soft-redirect
  to `/` — a sitemap must not list redirecting URLs).
- **Per-page metadata** on every content route: unique keyword-targeted `title` +
  `description` + canonical. Home leads with an absolute title "Turkish Banking
  Sector Data, Financials & Analytics"; per-bank pages use `generateMetadata` with
  the bank's display name. `/admin` is `noindex,nofollow`. (Before this, all 34
  routes inherited one identical title/description — the biggest on-page gap.)
- **Structured data (JSON-LD)**: `Organization` + `WebSite` site-wide in the root
  layout; `Dataset` on the home page (eligible for Google Dataset Search).
- OG/Twitter images already existed (`app/opengraph-image.png`, `twitter-image.png`).

## Manual next steps (need the owner's Google/Bing login — cannot be automated)

### 1. Google Search Console (do this first)
1. https://search.google.com/search-console → **Add property → Domain** → `carthago.app`.
2. Google shows a `google-site-verification=…` TXT value.
3. Cloudflare dashboard → `carthago.app` → **DNS → Add record**: type `TXT`, name `@`,
   content = the value. Save, then click **Verify** in GSC. (Domain property via DNS
   is best — covers http/https + all subdomains.)
4. GSC → **Sitemaps** → submit `sitemap.xml`.
5. Use **URL Inspection → Request indexing** on the home page and 3–4 top routes to
   prime the crawl.

### 2. Bing Webmaster Tools
1. https://www.bing.com/webmasters → Add site → **Import from Google Search Console**
   (one click once GSC is set up), or verify via DNS TXT.
2. Submit `https://carthago.app/sitemap.xml`.
(Bing also feeds DuckDuckGo/ChatGPT search, so it's worth the 2 minutes.)

## Ranking strategy — on-page is necessary but not sufficient

On-page (done) makes the site *eligible* and *well-represented*. Actually ranking
**#1** for a competitive head term also needs:

- **Indexation + freshness signal** — GSC submission above; the daily data updates +
  honest `<lastmod>` help.
- **Content depth on the target phrase** — the home H1/body should say "Turkish
  banking sector" in prose, not just chart labels. A short evergreen intro paragraph
  ("What this is / data sources / update cadence") would add crawlable keyword text.
- **Backlinks / authority** — the hardest and highest-leverage off-page factor. Levers:
  get listed in data-catalog / open-data directories, fintech & Türkiye-econ link
  lists, relevant subreddits/forums, and — per the strategic review — **own a
  distribution channel** (a weekly "State of Turkish Banking" brief on X/LinkedIn/a
  newsletter that links back). Inbound links from finance/econ sites move rankings
  more than any on-page tweak.
- **Realistic framing** — competitors for the head term include BDDK, TBB, CBRT,
  Trading Economics, CEIC, Statista (high-authority domains). Expect to win
  **specific long-tail** first ("Turkish bank NPL ratio by bank", "Akbank BRSA
  financials", "Türkiye capital adequacy ratio data") — which is exactly what the
  per-page titles now target — and climb the head term as authority accrues.

## Verify-live commands
```
curl -s https://carthago.app/robots.txt
curl -s https://carthago.app/sitemap.xml | grep -c '<loc>'      # expect ~61
curl -s https://carthago.app/ | grep -oiE '<title>[^<]*</title>'
curl -s https://carthago.app/capital | grep -oiE '<title>[^<]*</title>'
```
