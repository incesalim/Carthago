# Faaliyet franchise extraction — quality audit

**Date:** 2026-07-12
**Status:** 🔴 **/franchise UNPUBLISHED** (route parked at `web/app/_franchise/`, removed from nav + sitemap). Extractor rebuild **NOT yet done**.
**Verdict:** The franchise extractor is **not fit to publish**. ~75% of non-ATM values are wrong.

## How this surfaced

After the FY2024+FY2025 backfill populated `/franchise`, the numbers didn't pass a smell test.
Cross-checking the extracted stats against **`bank_audit_profile.branches_total`** (audited,
reliable) and against **year-over-year consistency** confirmed the lane is sampling stray
numbers out of prose rather than reading headline figures.

## Evidence

**ATMs contradict themselves year-over-year** (a bank does not shed 97% of its fleet):

| Bank | FY2024 | FY2025 |
|---|---|---|
| Akbank | 6,210 | **202** |
| Albaraka | 10 | 278 |
| Odea | 10 | 74 |
| TSKB | 8 | 18 |

**ATMs vs. audited branch counts** (peers sit at 3–10× branches):

| Bank | Branches | ATMs extracted | Reality |
|---|---|---|---|
| İşbank | ~1,100 | **40 – 58** | ~6,500 (off ~100×) |
| Anadolubank | 96 | **3,000** (31×) | ~100 |
| Burgan | — | **2** | — |
| TSKB | — | **8 / 18** | **0** — investment bank, no ATMs |

**Customers contradict themselves year-over-year** (10–25× swings):

| Bank | FY2024 | FY2025 |
|---|---|---|
| Yapı Kredi | 57.9 mn | **3.0 mn** |
| Garanti | 28 mn | **1.1 mn** |
| QNB | 33 mn | **7.7 mn** |
| İşbank | 15.2 mn | **4.0 mn** |
| Halkbank | 6.5 mn | **264 k** |
| Deniz | 3.4 mn | **425 k** |

Ziraat shows **200k customers** (real: ~28 mn). Merchants: Kuveyt **6**, Yapı Kredi **34**,
Vakıf Katılım **60**, Emlak **65**.

**The confidence flags do not correlate with correctness** — several of the worst values
(`ZIRAAT pos 13`, `HALKB pos 598/653`, `DENIZ atm 190`) were emitted as `high`.

## Root cause

`src/faaliyet/extractor.py :: extract_from_pdf` concatenates the **first 60 pages** and takes the
**first regex match per metric**, with no page targeting and no validation. Loose anchors like
`(?P<num>\d+)\s+ATMs?` or `(\d+)\s+müşteri` match *any* sentence in 60 pages of prose. Secondary
bugs found along the way:

- **No year guard** — a bare `2025` next to an "ATM" label was captured as the count (fixed
  2026-07-12, `_looks_like_year()`; 13 such rows deleted).
- **Scale suffix not captured** on the label-before anchors — this is why Halkbank POS came out
  `653` instead of `653 bin` (i.e. 653,000). The `{_SUF}` group is missing from the POS anchors.
- Sanity `ABS_BANDS` are far too loose to catch any of this.

## What actually survives scrutiny

Only big-bank ATMs and two merchant series are YoY-consistent *and* pass the branch cross-check:

- ATMs: Ziraat 7,757→7,900 · Garanti 5,820→6,558 · Yapı Kredi 5,768→6,011 · Halkbank 4,089→4,148 ·
  VakıfBank 4,100→4,165 · Deniz 4,601 · Kuveyt 1,314→1,326 · TEB 1,543→1,488 · Ziraat Katılım 125→138
- Merchants: Akbank 647k→657k · Halkbank 397k→427k
- Customers: Ziraat Katılım 1.33→1.54 mn · ING 2 mn (stable)

## Rebuild plan (not started)

Cell-by-cell patching is the wrong move. The lane needs a **validation gate** — this repo's own
principle: *reconciliation > bands* (see `feedback_verify_validators_against_data`).

1. **Reconcile ATMs against `bank_audit_profile.branches_total`** — require a sane ATM/branch
   ratio; reject outside it. Branch counts are audited and trustworthy.
2. **Enforce year-over-year consistency** — franchise metrics are sticky; reject any value moving
   more than ~40% against the same bank's prior year (unless the prior year is itself unvalidated).
3. **Target the infographic page**, not 60 pages of prose — locate the "Bir Bakışta / Rakamlarla /
   Öne Çıkan Göstergeler / At a Glance" spread and extract only from it; require tight
   label↔number proximity.
4. **Capture the scale suffix on every anchor** (`{_SUF}`), so `653 bin` → 653,000.
5. **Publish only what passes**; report the honest coverage. Anything failing → not published.

Re-publish `/franchise` (move `web/app/_franchise/` back to `web/app/franchise/`, restore the nav
entry in `web/app/components/Nav.tsx` and the sitemap row) **only** once the gate is in place and a
corpus run shows the surviving values reconcile.

## Related

- Extractor: `src/faaliyet/extractor.py` · lane: `src/faaliyet/` · data: `faaliyet_franchise` (D1)
- Config: `data/banks/faaliyet_report_urls.json` (FY2024 25/25, FY2025 26/28 banks fetched)
- Memory: `[[reference_r2_token_scope_and_ci_ip]]` (how the reports get fetched)
