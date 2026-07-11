# New-banks coverage gap — feasibility assessment (2026-07-11)

**Status:** investigation complete → **onboarding executed 2026-07-11** for the six
onboard-ready banks (see "Onboarding executed" at the bottom). Triggered by "there
are new banks in the system and we lack some of them in our data."

**One-line finding:** the BDDK master registry we store is current except for one
omission (Takasbank). The real gap is the **per-bank data lane**: of the recently
licensed banks, **6 publish clean, text-based BRSA quarterly reports and are
onboard-ready today**, 2 are licensed-but-not-yet-reporting, and 1 (Takasbank) is
technically extractable but is a clearing/CCP bank that should be kept out of the
commercial peer set.

---

## What "our data" covers today (the two universes)

- **Sector aggregates** (`balance_sheet`, `income_statement`, … from the BDDK
  monthly bulletin) are **group totals by type/ownership code**, not per bank. Every
  licensed bank — including all the new ones below — is **already inside** these
  aggregates (participation total, private-deposit total, etc.). So **onboarding
  these banks does not change any sector chart**; there is no gap there.
- **Per-bank data** (the `bank_audit_*` lanes → `/banks`, `/cross-bank`,
  margins/market-share) covers a fixed **31-bank universe** (`banks` dimension,
  migration 0021; `bank_names.ts`; `audit_report_urls.json` — all in lockstep). This
  is the only place a "missing bank" is actually missing. Adding a bank here expands
  the per-bank breadth (and the market-share denominator, currently ~98% of sector),
  it does not touch the aggregates.

So this whole exercise is about **per-bank breadth** — specifically whether we want
to represent the fast-growing **digital / new-entrant challenger** segment
individually.

## Registry delta (the master list)

Live BDDK list (`bddk.org.tr/Kurulus/Liste/77`, fetched 2026-07-11) vs our stored
`data/banks/bddk_bank_list.json` (fetched 2026-05-09): **all 36 deposit, 10
participation, 1 TMSF match exactly.** The **only** difference is one
development-investment bank:

- **İSTANBUL TAKAS VE SAKLAMA BANKASI A.Ş. (Takasbank)** — present on the live list
  (making dev/inv = 21), **absent from our `banks[]` array** (which has 20, even
  though the file's own `summary` already claims 21 and total 68). A pre-existing
  transcription omission, not a new license. See the Takasbank row below for why it
  is infrastructure, not a commercial bank.

All the recent digital / new-participation banks (Colendi, Fups, Enpara, Ziraat
Dinamik, Adil / Dünya / Hayat Finans / T.O.M. Katılım) are **already in our stored
list** — they are not new to the registry file, only absent from the per-bank data.

---

## Feasibility matrix (9 candidates)

Verified 2026-07-11 by fetching each bank's IR/registry pages and **text-extracting
real report PDFs** (PyMuPDF) to confirm they are not image-only.

| Bank | Group | Publishes quarterly BRSA? | Coverage | Format | Lang | Total assets (latest) | Verdict |
|---|---|---|---|---|---|---|---|
| **Enpara Bank** | Deposit (ex-QNB, foreign) | Yes | 2024Q4→2026Q1 | Text PDF | TR | **≈250 bn TRY** (2025-12) | **ONBOARD-READY** |
| **Dünya Katılım** | Participation (ex-Adabank) | Yes | 2024Q3→2026Q1 | Text PDF | TR+EN | **≈123 bn TRY** (2026Q1) | **ONBOARD-READY** |
| **Hayat Finans Katılım** | Participation (digital) | Yes | 2023Q1→2026Q1 | Text PDF | TR+EN | ≈34 bn TRY (2026Q1) | **ONBOARD-READY** |
| **T.O.M. Katılım** | Participation (digital) | Yes | 2023Q3→2026Q1 | Text PDF | TR+EN (from 2024) | ≈28 bn TRY (2026Q1) | **ONBOARD-READY** |
| **Ziraat Dinamik Banka** | Deposit (digital, state) | Yes | 2024Q4→2026Q1 | Text PDF | TR | ≈5.7 bn TRY (2025Q3) | **ONBOARD-READY** |
| **Colendi Bank** | Deposit (digital) | Yes | 2025Q2→2026Q1 | Text PDF | TR+EN | ≈4.8 bn TRY (2026Q1) | **ONBOARD-READY** |
| **Adil Katılım** | Participation (digital) | No | — | — | — | not reported | **NOT-YET** |
| **Fups Bank** | Deposit (digital) | No | — | — | — | not reported | **NOT-YET** |
| **Takasbank** | Dev & Inv (CCP/clearing) | Yes | 2005→2026Q1 | Text PDF | TR | ≈378 bn TRY (2026Q1) | **SKIP for peer set** |

### Per-bank notes

- **Enpara Bank** — by far the largest new bank. It was a ~10 bn TRY shell until the
  **demerger from QNB Bank completed 27 Aug 2025**, when the Enpara business (~10% of
  QNB's book) transferred in; it becomes a genuine mid-size bank **from 2025Q3**.
  Two consequences: (1) a **time-series discontinuity** — pre-2025Q3 quarters are the
  shell, and that business is inside QNB's own per-bank history, so a naïve stitch
  double-counts; treat 2025Q3 as the effective start. (2) Ownership is QNB (Qatar) →
  BDDK-classifies as **Foreign deposit (10007)**. TR-only reports; URLs are Sitefinity
  `?sfvrsn=` tokens (don't hardcode — source from KAP id 6034 / the IR page).
- **Dünya Katılım** — legally the former Adabank, converted to participation and
  growing fast (34.6 bn 2024YE → 123 bn 2026Q1, ~3.5×). Normal participation balance
  sheet (real loan book + participation funds ≈50 bn). Solo **and** consolidated,
  TR **and** EN, on both KAP (id 2412) and its own site. Participation (10003).
- **Hayat Finans / T.O.M.** — the two most-established digital participation banks;
  clean quarterly text PDFs with the longest histories (Hayat from 2023Q1, T.O.M.
  from 2023Q3), bilingual. Participation (10003).
- **Ziraat Dinamik / Colendi** — full BRSA filers but very small (<6 bn TRY). Real,
  growing, standard format — worth adding for completeness of the digital segment,
  but negligible sector weight. Ziraat Dinamik = state deposit (10006); Colendi =
  private-domestic deposit (10005).
- **Adil Katılım** — operating license only 11 Sept 2025; still pre-launch (app
  "çok yakında"). No financial statements exist anywhere. Re-check after its first
  filing.
- **Fups Bank** — licensed 31 Oct 2024, registered on the BDDK audit-report portal
  (EFT 159) but has filed **zero** reports (confirmed genuine by cross-checking that
  the same portal returns Colendi's 4 reports). Nothing to extract yet.
- **Takasbank** — technically fully extractable (clean text BRSA series back to
  2005), **but it is Turkey's central clearing/settlement/CCP + custody bank, not a
  commercial lender.** From its 2026Q1 balance sheet: **deposits = 0**, customer
  **loans ≈2.5%** of assets, **≈94% cash/placements**, plus 177.7 bn off-balance CCP
  guarantees. Its ratios (NIM/LDR/CAR/NPL) would distort any commercial or
  participation peer comparison. If ingested at all, it belongs in a separate
  "market-infrastructure / development-investment" bucket, not the `/cross-bank`
  peer heatmap.

---

## Recommendation

**Tier 1 — onboard now (materially interesting, low effort, clean inputs):**
1. **Enpara Bank** — largest new bank; the digital-challenger headline. Start the
   series at **2025Q3** (post-demerger) to avoid the QNB double-count.
2. **Dünya Katılım** — second-largest and a real, fast-growing participation bank.
3. **Hayat Finans Katılım** and **T.O.M. Katılım** — the two established digital
   participation banks; longest histories, bilingual, together they complete the
   "digital participation" cohort.

Together these four are the coherent, high-value add: the **digital / new-entrant
segment** the current 31-bank universe misses entirely, and they're all standard
text PDFs that fit the existing PyMuPDF extractor with no new machinery.

**Tier 2 — optional, add for completeness (tiny, but trivially cheap once Tier 1's
machinery is proven):** Ziraat Dinamik, Colendi.

**Defer (re-check quarterly):** Adil Katılım, Fups Bank — licensed but no reports
filed yet. First filings will likely appear on the BDDK BdrUyg portal.

**Do not add to the peer set:** Takasbank. Separately, **fix the registry-list
omission** regardless of the above — add its row to `bddk_bank_list.json` and
reconcile the 20-vs-21 count (see below); that's a one-line correctness fix
independent of any per-bank onboarding.

If we onboard only one thing, it should be **Enpara** (it's ~10× the size of the next
new bank and is the natural "challenger bank" story). If we onboard a *segment*, it's
the **four participation/digital banks** above.

---

## How to onboard (mechanics, for when a decision is made)

Per [`docs/AUDIT_PIPELINE.md`](../AUDIT_PIPELINE.md) — no new machinery needed:

1. **Assign an internal ticker** (== `bank_ticker` across all lanes). Proposed,
   avoiding collisions with existing tickers: `ENPARA`, `DUNYAK`, `HAYATK`, `TOMK`,
   `ZIRAATD`, `COLENDI`. (Existing participation tickers are ALBRK/KUVEYT/TFKB/EMLAK/
   VAKIFK/ZIRAATK; `ZIRAAT`+`ZIRAATK` are taken, hence `ZIRAATD` for Ziraat Dinamik.)
2. **Add the bank + its quarterly PDF URLs** to `data/banks/audit_report_urls.json`
   (per-kind, per-period). **Prefer sourcing URLs from the BDDK BdrUyg registry or
   KAP** over the banks' fragile CMS URLs (see process note below).
3. **Mirror the identity in three places** (they must stay in lockstep):
   - `banks` dimension — a new migration doing `INSERT OR REPLACE` one row
     (ticker, name, name_tr, bank_category, is_participation, is_listed, bist_symbol).
   - `web/app/lib/bank_names.ts` — `BANK_NAMES` + `BANK_TYPE_BY_TICKER` (ownership
     code: Enpara 10007, Ziraat Dinamik 10006, Colendi 10005, the three participation
     10003) + confirm the badge label resolves.
   - `data/banks/bddk_bank_list.json`.
4. **(Optional) enable auto-discovery** — add the ticker to `DISCOVERY_BANKS` in
   `src/audit_reports/discovery.py` only after `scripts/validate_discovery.py`
   confirms discovery reproduces the known period→URL map.
5. **Acquire → extract**: `acquire-audit.yml` (or `sync_audit_reports.py`) pulls PDFs
   to R2; `refresh-audit.yml` extracts → `bank_audit_*` → the bank appears in the
   `/admin` coverage matrix and on `/banks`. Watch the matrix for per-bank layout
   quirks (participation banks put equity at BS roman XIV., not XVI. —
   `reference_participation_equity_hierarchy`).

Effort: Tier-1 (4 banks) is a few hours of config + one migration + an extraction
run, plus per-bank validator cleanup for whatever layout quirks surface (the usual
tail — expect 1–2 partitions each to need attention).

---

## Two process findings worth keeping

1. **The BDDK BdrUyg registry is the authoritative discovery source.** Every bank's
   audit reports are queryable at
   `https://www.bddk.org.tr/BdrUyg/Home/SorguSonuc?KurulusTuru=1&EFTKodu=<code>&RaporTipi=TÜMÜ&DonemYil=0&DonemAy=0`
   with direct "İndir" download links. This is a single, mandatory, uniform source —
   more robust than scraping 31 heterogeneous IR sites, and it definitively answers
   "has bank X filed yet?" (it's how we confirmed Fups has filed nothing). Worth
   considering as a discovery backend for `acquire-audit.yml` generally, not just for
   these new banks.
2. **The Enpara/QNB demerger (27 Aug 2025) is a per-bank discontinuity** to encode
   wherever we join Enpara history — its book was inside QNB before 2025Q3.

## Open decisions for the user

- **Scope:** Tier-1 four banks (recommended) / just Enpara / all six ready / none.
- **Fix the `bddk_bank_list.json` Takasbank omission now?** (independent, 1-line).
- **Ticker names** — confirm or override the proposed codes above.

---

## Onboarding executed — 2026-07-11

User chose **all six onboard-ready banks**. Config + identity wired (no extraction
run locally — that's a CI step). Tickers: `ENPARA`, `COLENDI`, `ZIRAATD`, `TOMK`,
`DUNYAK`, `HAYATK`.

**Files changed:**
- `data/banks/audit_report_urls.json` — 6 bank blocks, **59 verified text-PDF
  report-periods** (each URL confirmed 200 + `%PDF` + balance-sheet/§4 anchors via a
  first-bytes/one-sample smoke test).
- `web/migrations/0022_banks_dimension_new_entrants.sql` — 6 dimension rows.
- `web/app/lib/bank_names.ts` — `BANK_NAMES` + `BANK_TYPE_BY_TICKER` (ENPARA 10007,
  ZIRAATD 10006, COLENDI 10005, DUNYAK/HAYATK/TOMK 10003).
- `data/banks/bddk_bank_list.json` — Ziraat Dinamik category corrected `Özel`→`Kamu`
  (state-owned).
- `scripts/sync_audit_reports.py` — `DUNYAK` added to `REFERERS` (its CDN drops bare
  requests).

**Per-bank coverage wired** (all standard BRSA text PDFs; no hand-transcription):

| Ticker | Kind(s) | Periods | Lang | Source quirks found |
|---|---|---|---|---|
| ENPARA | unconsolidated | 2024Q4→2026Q1 (6) | TR | Sitefinity `?sfvrsn=` URLs; **step-up at 2025Q3** (QNB demerger 27 Aug 2025) — pre-2025Q3 is a ~10bn shell |
| DUNYAK | solo + consol | solo 2023Q4→2026Q1 (10), consol (7) | TR | needs **Referer** header |
| HAYATK | solo + consol | solo 2023Q1→2026Q1 (13), consol 2025Q1→2026Q1 (5) | EN | JS-rendered `getmedia/{guid}` links; **guid-only URL form works** (verified) |
| TOMK | unconsolidated | 2023Q3→2026Q1 (11) | TR | clean `DDMMYYYY[-tr].pdf` |
| COLENDI | unconsolidated | 2025Q2→2026Q1 (4) | EN | WordPress; filenames use ASCII "Bagimsiz" (en-dash `%E2%80%93`) |
| ZIRAATD | unconsolidated | **2025Q3**→2026Q1 (3) | TR | full report = **`bagimsiz-denetim-raporu`** file (~75pp), NOT `mali-tablolar` (7pp summary); **2025Q2 source PDF is corrupt** (non-PDF blob) + 2024Q4/2025Q1 KAP-only → deferred |

**Deferred (re-check quarterly):** Adil Katılım, Fups Bank (no reports filed yet);
Takasbank (SKIP — CCP/clearing bank); Ziraat Dinamik 2024Q4/2025Q1/2025Q2 (KAP-only /
corrupt source).

**Remaining step = extraction on CI** (heavy → not run locally per project rule): the
6 banks are `missing + pdf_absent` until `acquire-audit.yml` scrapes their PDFs to R2
and `refresh-audit.yml` extracts them. They surface on `/banks` + the coverage matrix
only after `bank_audit_extractions` rows exist. Watch the matrix for the usual per-bank
layout tail (participation equity at BS roman XIV.).
