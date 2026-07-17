# IFRS-9 stages lane → 0 errors; 11 N/A → 3

**Date:** 2026-07-17 · **Status:** COMPLETE — shipped, live in D1 · **Lane:** `stages` (§5, derived)

Closes the headline finding of [validator-robustness-audit-2026-07-17](validator-robustness-audit-2026-07-17.md):
the `stages_bs_loans` reconciliation flagged 9 cells, **6 of which passed every other check**.
All 12 failures are now fixed at source and every remaining N/A rests on a positive citation.

| | before | after |
|---|---|---|
| `stages` errors | 12 | **0** |
| `stages` ok | 1027 | **1047** |
| `stages` N/A | 11 | **3** (all TOMK) |
| rows claiming NPL = 100% | 161 | **0** |
| fleet errors | 426 (session start) | 288 |

`credit_quality` — the lane `stages` is derived from — holds at **0 errors**.

## What was wrong

### FIBA ×9 — three distinct causes, one symptom

* **2022Q4 cons+unco** — the extractor read the **collateral-type** breakdown (note 5(8), p52)
  instead of §5.2 (p88). That table's Toplam row is `Standart Cari | Standart Önceki | Yakın Cari |
  Yakın Önceki`; the extractor took col0 as Stage 1 and summed cols 1–3 as Stage 2:
  `18,574,043 + 3,248,468 + 3,540,679 = 25,363,190` — exact. It **mixed current and prior periods
  across two portfolios**, and the stored `25,363,190 / 61,168,525` appear **nowhere in either
  PDF**. It won on first-wins dedup because p52 < p88.
* **2025Q2 cons** — the real §5.2 (p61) is **vector-outlined** (868 drawings, zero numbers), so the
  extractor fell through to p62: a `(devamı)` continuation headed *"Yakın izlemedeki kredilerin
  gecikme süreleri"* — a **day-count ageing table**, read as an IFRS-9 stage split.
  `allow_total_drop` discarded its 1,638,284 (= 1,008,524 + 629,760) and stored the rest as S1/S2.
  The extractor's **own docstring cites this exact row** as its motivating example.
* **2022Q1 ×2, 2023Q3, 2024Q1, 2025Q3 ×2** — real, printed data **curated as "not disclosed"** on
  an empty `get_text()`. p58 (2023Q3) is a pasted **bitmap** (169 images); the rest are **vector
  outlines** (511–870 drawings). §5.10 was a red herring — it is the prose interest-accrual note
  (*"Banka donuk alacakları için faiz tahakkuku ve reeskontu yapmamaktadır"*). **The stage table is
  §5.2.** These are whole-**report** failures, not §5 failures: the balance sheet is drawn too,
  which is why ~180k chars of prose have a text layer while every statement does not.

### SKBNK ×5 + EMLAK 2022Q3
The extractor grabbed the **§4 c.4.3 NPL-by-sector** table. SKBNK 2025Q4's `1,003,122` was
**synthesised** (Stage-3 Provisions + Write-Offs) and appears nowhere in the PDF; the cell published
an NPL of **39.51%** against a truth of **1.29%**. Ratios now 1.000–1.048.

### The three zero-pass cells were all faithful
DUNYAK 2023Q4 (nil loan book, S1/S2 genuinely 0), HAYATK 2023Q3 (S1 = 76,342 = BS exactly, prose-zero
S3), ZIRAATD 2026Q1 (700,100 + 2,549 = 702,649 = BS exactly). Nothing to fix but the verdict.

## How the FIBA figures were proven — a closed identity, not a band

The §5.2 Toplam includes factoring per its own `(*)` footnote; BS 2.1 excludes it (carried at 2.3):

> **S1 + S2 + S3 − faktoring alacakları = BS assets 2.1, exact to the lira**

It holds on all nine, and **predicted S3 to the exact lira before the page was rendered** on four.
FIBA's own stated ratios corroborate independently: 2022Q4 prints **%1,68** → we compute **1.68%**;
2023Q3 prints **%1,09** → we compute **1.09%**. `cons == unco` is genuine for FIBA (byte-identical
§5.2/ECL/NPL/BS in both books), not a cross-kind copy.

## The N/A verdicts

**11 → 3.** Both surviving "short filing" notes were **false claims about the bank**, and both rested
on absence-of-text reasoning:

* **ICBCT 2023Q4 cons — TRUNCATED, now re-fetched.** Its own balance sheet carries a footnote column
  headed **`Dipnot / (Beşinci Bölüm)`** with **39 cross-references** (`(5.I.1)`, `(5.IV.11)`, …) into
  a Fifth Section our 9-page copy did not contain, and every page closes *"İlişikteki notlar bu
  finansal tabloların tamamlayıcı bir parçasıdır."* Siblings are **108** (2022Q4) and **112**
  (2024Q4) pages.
  **Root cause:** ICBC's IR page publishes **two links per period** — `Mali Tablo` (tables-only) and
  `Dipnotlar` (the full report). We configured the first. Census of all 34 ICBCT URLs: this is the
  **only** affected entry (unconsolidated 17/17 correct; consolidated 16/17).
* **TSKB 2026Q1 unco — WRONG DOCUMENT, now re-fetched.** Our copy was a **KAP XBRL rendering** (p1 a
  KAP cover, pp4–14 KAP's generated table view), not the filed report. **PwC's own report inside our
  copy** refers to *"beşinci bölüm II. kısım 7.c.1 ve IV. kısım 5'te belirtildiği üzere"* and
  *"ilişikte yedinci bölümde yer verilen"* — asserting sections the copy lacks. The URL **already in
  the config** serves the real **100-page** report.

Both re-fetched, re-extracted and verified — stages reconcile to BS 2.1 at ratio **1.0000**
(ICBCT 34,900,671 = BS exactly, NPL 0.37%; TSKB 254,854,495 vs 254,854,895, NPL 2.23%).

* **TOMK ×3 — N/A CONFIRMED, on a positive citation.** TOMK is a **BDDK-approved TFRS-9 non-applier**;
  it does not run the ECL model, so a stage table cannot exist. Stated verbatim in all four reports
  (2023Q3 p18, 2023Q4 p23, 2024Q1 p18, 2024Q2 p19): *"…'Kredilerin Sınıflandırılması…Yönetmelik'in
  **dokuzuncu maddesinin altıncı fıkrası** kapsamında TFRS 9'un değer düşüklüğüne ilişkin hükümlerini
  **uygulamama** konusunda BDDK'ya başvuruda bulunmuş ve Banka'nın talebi **kabul edilmiştir**…
  **31 Aralık 2025 tarihine kadar**…"*
  Corroborated per period: 2023Q3 BS 2.1 = 0 and Bölüm 4 has no credit-risk section at all; 2023Q4's
  annual report positively prints a nil loan book (`Verilen Krediler: Kurumsal -, Bireysel -,
  İhtisas -`); 2024Q1's ₺5.314k is disclosed **only by maturity** (liquidity ladder p36:
  4.130 + 1.184 = 5.314 = BS 2.1) with the credit-risk section omitted **under a cited exemption**
  (p29, Tebliğ art. 25) and the bank stating its own materiality at p64: *"Krediler 5.314 TL ile
  **%0,19**"*.

## The `total = S3` fabrication — found on the way, fixed

`build_bank_audit_stages.py`'s comment said *"when all three present"*; the code said **`any`**. With
S1 and S2 both absent the sum collapsed to S3 alone, so the row asserted **every lira the bank lent
was non-performing**. **161 of 836 prior rows** were in that state — exactly the corpus's 161
NPL==100% rows.

**Latent, not live:** no `current` row was affected (which is why no chart showed it) and validation
reads current only (which is why no check caught it). Every consumer filters `period_type='current'`
(`audit.ts:634`, `credit-risk.ts:49`, every `bot-schema.ts` example) — but `bot-sql.ts` lets an LLM
write its own SQL over this table, so a fabricated 100% was one forgotten `WHERE` from being quoted
as fact. Now NULL when both S1 and S2 are unknown; **0 corpus-wide**. Deliberately **not** `all(...)`:
40 current rows have exactly one of S1/S2 null and a real total.

## Also fixed

**`bank_audit_statement_types` schema drift.** `section`/`section_rank` were added 2026-07-17 and
declared only in the `CREATE TABLE`. Every working DB is restored from the R2 snapshot, where the
table already exists — so `CREATE TABLE IF NOT EXISTS` is a no-op and `sync_audit_expected.write()`
dies on `no such column: section`. D1 had migration `0030`; the Python side had no mirror. Added to
`_COLUMN_MIGRATIONS`, which is what that list is for.

## Method notes worth keeping

* **A numbering gap is not a usable tell for TOMK.** The prior note claimed the asset notes *"jump
  straight from '2. Bankalar' to '4. Maddi duran varlıklara'"* — **false**. Item 3 is FVTPL
  (₺1.454.623 at 2024Q1). TOMK **renumbers contiguously** when a note is absent; it never leaves a
  hole. The real tell is the opposite: 2024Q2 **expands** to the full BRSA template while
  2023Q3/Q4/2024Q1 use a compressed 1–6/1–7 list.
* **Why the art. 9/6 citation was missed:** the report spells the article in words (*"dokuzuncu
  maddesinin altıncı fıkrası"*, not *"9 uncu madde"*), uses the regulation's full title (not
  *"Karşılıklar Yönetmeliği"*), and says *"uygulamama konusunda … başvuruda bulunmuş"* (not
  *"uygulamamaktadır"*). All three probe terms returned 0. The one *"9 uncu madde"* hit (2024Q1 p26)
  is a **false positive** — the *Özkaynaklar* Yönetmeliği art. 9, unrelated.
* **File size is a poor truncation proxy; page count is good.** ICBCT 2025Q3 unco is 0.55 MB but a
  complete **81 pages**. Conversely ICBCT 2025Q3 cons is 667 KB and complete at 80. Use page count +
  a `BEŞİNCİ BÖLÜM` probe.
* **A clean ending is not evidence of completeness.** Both truncated copies end at a *section
  boundary*, not mid-sentence — they are clean excerpts, not interrupted downloads. Neither has
  `Sayfa X / Y` footers. The documents' own **cross-references** decided both.
* **icbc.com.tr soft-404s return HTTP 200 with `text/html`**, and fitz opens the error page as a
  1-page "PDF". Check `%PDF` magic bytes, not the status code.
* **The ICBCT URL must stay percent-encoded.** The filename spells "Ş" as `S` + U+0327 COMBINING
  CEDILLA (NFD); the precomposed U+015E spelling is a **different object and 404s**. Any tool that
  NFC-normalizes the stored literal silently restores the dead link — almost certainly how the
  wrong link was configured in the first place.

## Open / follow-ups

* **`loans_by_sector` ICBCT 2023Q4 cons — 2 new errors**, surfaced because the lane finally has data.
  `mfg_total` (1,190,180) is a **parent** of the `mfg_*` rows, so children double-count — and don't
  foot (22,637 + 772,645 + 0 = 795,282 ≠ 1,190,180). Pre-existing parent/child weakness in that lane.
* **`audit_opinion` ICBCT 2023Q4 cons = missing** — the report *has* an opinion at p2; extractor gap.
* **`fx_position` TSKB 2026Q1 unco = missing**, **`equity_change` TSKB 2026Q1 unco = missing** — both
  disclosed in the 100-page report; extractor gaps, now honestly flagged instead of hidden under N/A.
* **TSKB 2026Q1 unco still carries `manual` §2 cells** hand-transcribed from the *KAP rendering*.
  The real report is now in R2 and machine-readable; those overlays could be retired.
* **FIBA `npl_brsa_gross`/`net`/`provision` are FC-only corpus-wide** — a larger correction, out of
  scope here. FIBA 2025Q2/Q3 also carry a stale prior column.
* **TOMK 2024Q2+ `stages` values are BRSA Group I/II, not IFRS stages** (the bank does not apply the
  ECL model until 31.12.2025). Consistent with the known section-dependent column rule, but the
  labelling should be confirmed honest for this bank.
* **ICBCT is not in `DISCOVERY_BANKS`.** Its `_skeleton()` would map the twins to different skeletons
  and `preferred[kind]` is learned from the latest entry (`FT ve Dipnotlar`) — so discovery would
  have picked the right file and **self-corrected this bug**. Worth adding (after
  `validate_discovery.py`), with care for the NFD/NFC hazard.
