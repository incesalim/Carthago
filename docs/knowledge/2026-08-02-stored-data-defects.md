# Incorrect data found in the stored corpus (2026-08-02)

**Date:** 2026-08-02 · **Status:** FOUND, NOT FIXED — no D1 writes this session.
**How:** surfaced incidentally while benching an LLM extractor against
`data/audit_overrides.json`; each was then confirmed directly against the
snapshot or the filing. None of these came from the LLM — it was the harness
failures that pointed at them.

Four independent defects. Counts are against the local snapshot
(`data/bank_audit.db`, pulled 2026-07-27); D1 should be assumed to match until
checked.

---

## 1. 202 rows carry figures fused into `item_name`

The row LABEL has digits from neighbouring cells welded onto it:

```
'Teminat Mektupları III-a-2,ii 105,,025544,,157'
'Dış Ticaret İşlemleri Dolayısıyla Verilenler 54,9 21'
'Cayılamaz Taahhütler 1,732 , 30'
'Menkul Kıymetler 100,1 06,'
'GARANTİ ve KEFALETLER III-a-3,i 266,,712059,,786629 5140,,409504,,'
```

| | |
|---|---|
| rows | **202** |
| banks | ALNTF 118, YKBNK 74, TEB 8, ATBANK 2 |
| statements | `off_balance` 128, `assets` 74 |
| amounts | look **sound** — 145 of 188 checked are non-zero and plausible |

`'Cayılamaz Taahhütler 1,732 , 30'` sits next to a TL amount of 1,610,374 while
the row above holds 1,732,301 — the label has absorbed digits from an adjacent
row.

**Why it matters even though the amounts are right:** these names print on the
site, and **any consumer joining on `item_name` silently skips these rows**. It
also blocks label-based lookup entirely — it is what made 6 of the bench's
"failures" unresolvable.

Reproduce — the count is against a regex, because SQL `GLOB` cannot express
"a digit run with separators". The plain-SQL approximation below returns **100**
of the 202 (it only catches three consecutive digits, missing `'54,9 21'`-style
splits), so use the Python form for the real number:

```python
import re, sqlite3
db = sqlite3.connect("data/bank_audit.db"); db.row_factory = sqlite3.Row
rows = db.execute("SELECT bank_ticker, statement, item_name "
                  "FROM bank_audit_balance_sheet")
bad = [r for r in rows
       if re.search(r"\d{3,}|\d[\d ,.]{2,}$", r["item_name"] or "")]   # 202
```
```sql
-- narrower: 100 rows
SELECT * FROM bank_audit_balance_sheet WHERE item_name GLOB '*[0-9][0-9][0-9]*';
```

---

## 2. 347 junk P&L rows — a date header parsed as a line item

```
h='1'   'OCAK - 31 MART'   amount=202
h='31'  'MART'             amount=202
h='31'  'ARALIK'           amount=202
```

The filing's period header — "1 OCAK – 31 MART 2022" — was captured as a P&L
row, and `202` is a fragment of the year (2022/2023).

| | |
|---|---|
| rows with a bare-integer hierarchy | **347** |
| banks | VAKBN 38, ALNTF 32, then AKTIF / ATBANK / DENIZ / EMLAK / ICBCT / KUVEYT / ZIRAAT / ZIRAATK at 18 each |

Two different problems share this signature — worth separating before any fix:

| `item_name` | rows | what it is |
|---|---:|---|
| `MART` / `ARALIK` / `OCAK` / `OCAK - 31 MART` | ~243 | **junk** — the period header split into rows |
| `Adet Hisse Başına…` (earnings per share) | 24 | a **real line item** with a broken hierarchy |
| other | ~80 | mixed, unreviewed |

So do not simply delete on this predicate: roughly a quarter of the matches are
legitimate rows whose hierarchy is wrong, not rows that should not exist.

These also made the first version of the sub-item sum probe report a spurious
2.27% failure rate, because `1` looked like the parent of `1.1` (it is not — the
parent of `1.1` is roman `I.`).

Reproduce:
```python
import re, sqlite3
db = sqlite3.connect("data/bank_audit.db"); db.row_factory = sqlite3.Row
rows = db.execute("SELECT bank_ticker, hierarchy, item_name, amount "
                  "FROM bank_audit_profit_loss")
junk = [r for r in rows
        if re.fullmatch(r"\d+", (r["hierarchy"] or "").strip().rstrip("."))]  # 347
```

---

## 3. Two P&L partitions fail the new sub-item check

Surfaced by `check_pl_subitem_sums` (shipped this session, `989a8b0`). Over
1,050 partitions and 3,144 checks, exactly two fail — so these are findings, not
noise:

| partition | node | expected | actual | diff |
|---|---|---:|---:|---:|
| FIBA 2023Q3 consolidated | `4.1 Alınan Ücret ve Komisyonlar` | 2,889,781 | 2,889,181 | −600 |
| ODEA 2023Q3 unconsolidated | `1.5 Menkul Değerlerden Alınan Faizler` | 3,244,926 | 3,220,267 | −24,659 |

A parent that does not equal the sum of its own children means one of the
children was dropped or misread. Both want a look at the filing.

---

## 4. ⚠️ Filings print the same label twice with DIFFERENT figures

Not our defect — the source documents do this — but it silently decides which
number gets stored, and nothing records the choice.

**VAKBN 2025Q4 unconsolidated, page 46, both rows on the same page:**
```
'Toplam özkaynak (Ana Sermaye ve Katkı Sermaye Toplamı)'  479,407,722 / 326,527,975
'Toplam Özkaynak(Ana sermaye ve katkı sermaye toplamı)'   479,398,199 / 326,506,436
```
Difference: 9,523 current, 21,539 prior. The extractor takes the first by anchor
order. **Which one is correct is not established** — the stored value is simply
whichever the anchor hit first, and no note explains why.

Other instances:

| filing | label | values |
|---|---|---|
| QNBFB 2023Q1 P&L | `Non-cashloans` | 4.1.1 = 175,010 (fees received) / 4.2.1 = 449 (paid) |
| every `loans_by_sector` page | sector names | one block per period, repeated |

**Action worth taking:** for the VAKBN class, confirm which figure reconciles
with the printed capital ratios and record the reason next to the anchor. An
undocumented first-match on two legitimately-printed values is a coin flip that
looks like a decision.

---

---

## 5. Some hand-transcribed statements are now REDUNDANT

`data/manual_statements.json` holds 59 statements typed in by hand. Checking why
each partition needed it, against the PDF currently in R2:

| cause | partitions | statements |
|---|---|---:|
| **drawn pages** — printed but invisible to `get_text()` | 6 cached, all FIBA | ~41 |
| **PDF has since been replaced** — extracts fine now | TSKB 2026Q1 uncon | 6 |
| **page location still fails** | ISCTR 2025Q1 conso, 2025Q2 uncon | 7 |
| not cached, unchecked | TFKB 2022Q3, ALBRK 2025Q4, ATBANK 2025Q4, FIBA 2025Q2 | 5 |

**TSKB 2026Q1 unconsolidated no longer needs its transcription.** The current PDF
extracts 47 asset and 47 liability rows and agrees with the human:

| | hand | extracted |
|---|---:|---:|
| `VARLIKLAR TOPLAMI` / `TOTAL ASSETS` | 346,391,225 | 346,391,225 |
| `YÜKÜMLÜLÜKLER TOPLAMI` / `TOTAL LIABILITIES` | 346,391,225 | 346,391,225 |
| positional value match, liabilities | — | **47/47** |
| positional value match, assets | — | 44/47 |

The row NAMES differ completely because the human transcribed a **Turkish** copy
while the PDF now in R2 is the **English** one — the replaced-PDF mechanism, not
a data conflict. Retiring those 6 entries would let the lane extract normally;
the 3 asset rows that differ positionally should be looked at first.

**ISCTR is a different problem and still real.** `_locate_pages` returns only
`off_bs` for ISCTR 2025Q1 consolidated — it never finds the balance sheet, and
extraction yields 0 rows. That is a page-location failure, not a drawn page.

Probe: `scripts/scratch_probe_drawn_pages.py`.

## Not fixed, deliberately

No D1 writes were made this session (standing instruction). Fixing #1 and #2
means re-extracting the affected partitions, which the frozen-cron / no-write
posture rules out for now, and #2 in particular should be handled by the
extractor rejecting header rows rather than by a data patch. #3 and #4 need a
human to read two filings before anything is changed.
