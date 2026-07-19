# Carthago Data API — User Manual

**Turkish banking-sector statistics as time series. Free, public, no API key.**

Base URL — `https://carthago.app/api/v1`

---

## 1. What this is

BDDK (Bankacılık Düzenleme ve Denetleme Kurumu — Türkiye's banking regulator)
publishes the sector's statistics as monthly and weekly bulletin tables. This
API republishes them as **~19,800 addressable time series** you can pull by URL.

| | |
|---|---|
| **Source** | BDDK monthly bulletin (tables 1–17) + weekly bulletin |
| **Monthly coverage** | 2020-01 → current, ~17,600 series |
| **Weekly coverage** | 2019-11 → current, ~2,200 series |
| **Authentication** | none |
| **Formats** | JSON, CSV |
| **Licence** | BDDK's data is public. Please credit BDDK as source, Carthago as distributor |

**Not included:** individual banks. BDDK publishes these tables at sector and
bank-group level only, so every series is an aggregate. There is no series for
"Garanti's loan book" here.

If you have used **TCMB's EVDS**, this will feel familiar — it is modelled on
it deliberately. Series codes joined with `-`, `DD-MM-YYYY` dates, `type=csv`.
The differences: **no API key**, and codes carry both a Turkish and an English
label.

---

## 2. Quick start

Paste any of these into a browser.

```
https://carthago.app/api/v1
https://carthago.app/api/v1/series?series=BDDK.T01.I026.10001.TOT
https://carthago.app/api/v1/serieList?q=loans&limit=10
```

Python:

```python
import pandas as pd

df = pd.read_csv(
    "https://carthago.app/api/v1/series"
    "?series=BDDK.T01.I026.10001.TOT-BDDK.T01.I010.10001.TOT"
    "&startDate=01-01-2024&type=csv",
    parse_dates=["date"],
).set_index("date")
```

`type=csv` returns a **wide** table — one column per series, dates outer-joined
— which is what you want for analysis. JSON is better when you need the units
and labels alongside the numbers.

---

## 3. Series codes

Every series has a five-part code:

```
BDDK . <DATASET> . <ITEM> . <BANKTYPE> . <COLUMN>
BDDK .    T01    . I026  .   10001    .    TOT
```

| Part | Meaning |
|---|---|
| `DATASET` | which BDDK table — `T01`–`T17` monthly, `W…` weekly |
| `ITEM` | which line of that table |
| `BANKTYPE` | which slice of the sector |
| `COLUMN` | which value — currency leg, maturity bucket, etc. |

**Don't build codes by hand.** `ITEM` is a catalog identifier, not a line number
you can infer. Find codes with `/serieList` (§5) and reuse them — they are
stable and safe to hardcode.

The one part you *can* usefully edit is `BANKTYPE`: swapping `10001` for `10003`
gives you the same line for participation banks instead of the whole sector.

---

## 4. Getting data — `/series`

```
GET /api/v1/series?series=<CODES>&startDate=<D>&endDate=<D>&type=<FMT>
```

| Parameter | Required | Notes |
|---|---|---|
| `series` | yes | one or more codes joined by `-`, **max 20** |
| `startDate` | no | `DD-MM-YYYY` or `YYYY-MM-DD` |
| `endDate` | no | same; omit both for the full history |
| `type` | no | `json` (default) or `csv` |

```json
{
  "meta": { "series_count": 1, "unknown": [] },
  "series": [{
    "series_code": "BDDK.T01.I026.10001.TOT",
    "name": "TOPLAM AKTİFLER",
    "name_en": "TOTAL ASSETS",
    "unit": "million TL",
    "frequency": "monthly",
    "observations": [
      { "date": "2026-04-30", "value": 50984012 },
      { "date": "2026-05-31", "value": 51760765 }
    ]
  }]
}
```

Codes that don't exist come back in `meta.unknown` instead of failing the whole
request — asking for 20 series shouldn't lose 19 because one was retired. If
*none* resolve you get `404`.

---

## 5. Finding series — `/serieList`

```
GET /api/v1/serieList?q=<TERM>&dataset=<DS>&bankType=<CODE>&limit=<N>
```

| Parameter | Notes |
|---|---|
| `q` | substring of the label, **Turkish or English** |
| `dataset` | `T01`…`T17`, `WLOAN`… |
| `bankType` | see §8 |
| `frequency` | `monthly` or `weekly` |
| `limit` / `offset` | default 500, max 25000 (the whole catalog) |
| `type` | `json` or `csv` |

Three ways to work:

```
# 1. Search by term
/api/v1/serieList?q=deposits&limit=20

# 2. Browse one table for one bank group
/api/v1/serieList?dataset=T01&bankType=10001&limit=200

# 3. Export the ENTIRE catalog (all ~19,800 series, ~3 MB) and grep it locally
/api/v1/serieList?limit=25000&type=csv
```

The full export is often the fastest way to work: pull it once, then search it
in a spreadsheet or with `grep` instead of guessing search terms.

```bash
curl -s "https://carthago.app/api/v1/serieList?limit=25000&type=csv" \
  > carthago-series.csv
grep -i "capital adequacy" carthago-series.csv
```

```python
import pandas as pd
cat = pd.read_csv("https://carthago.app/api/v1/serieList?limit=25000&type=csv")
cat[cat.item_name_en.str.contains("Deposit", na=False)][["series_code", "item_name_en"]]
```

Columns: `series_code`, `dataset`, `frequency`, `item_name` (Turkish),
`item_name_en` (English), `bank_type_code`, `value_column`, `unit`,
`start_date`, `end_date`, `obs_count`.

Each row tells you the code, both labels, the unit, and **the period range it
actually covers** — so you can see whether a series is worth requesting before
you request it.

> **Search caveat.** Matching is plain substring, and case-insensitivity is
> ASCII-only: `İ` and `i` are different characters to the matcher. Prefer a
> lowercase ASCII stem — `kredi`, `mevduat`, `loans`, `deposit`. Broad terms hit
> hard: `q=kredi` matches over 4,000 series, so pair it with `dataset` or
> `bankType`.

---

## 6. How the catalog is shaped

~19,800 series sounds like a lot to browse. It isn't — the catalog is only
**554 distinct lines**, each repeated across bank groups and value columns:

```
series  =  line  ×  bank group  ×  value column
```

So finding what you want is three small choices, not one search through 19,800
things. Pick the line, then vary the last two segments of the code.

| Dataset | Lines | Bank groups | Value columns | Series |
|---|---|---|---|---|
| `T01` Balance Sheet | 62 | 10 | 3 | 1,860 |
| `T02` Income Statement | 53 | 10 | 3 | 1,590 |
| `T03` Loans | 20 | 10 | 9 | 1,712 |
| `T04` Consumer Loans | 40 | 10 | 3 | 957 |
| `T05` Sectoral Loans | 70 | 10 | 3 | 2,057 |
| `T06` SME Loans | 8 | 10 | 6 | 480 |
| `T07` Syndication | 3 | 10 | 3 | 74 |
| `T08` Securities | 31 | 10 | 3 | 930 |
| `T09` Deposits by Type | 26 | 10 | 6 | 1,560 |
| `T10` Deposits by Maturity | 24 | 10 | 7 | 1,680 |
| `T11` Liquidity | 44 | 10 | 5 | 2,200 |
| `T12` Capital Adequacy | 38 | 10 | 1 | 380 |
| `T13` FX Position | 11 | 10 | 1 | 110 |
| `T14` Off-Balance Sheet | 52 | 10 | 3 | 1,560 |
| `T15` Ratios | 32 | 10 | 1 | 320 |
| `T16` Other Information | 7 | 10 | 1 | 70 |
| `T17` Foreign Branch Ratios | 3 | 10 | 1 | 30 |
| `WLOAN` Loans (weekly) | 22 | 6 | 3 | 396 |
| `WSEC` Securities (weekly) | 13 | 6 | 3 | 234 |
| `WDEP` Deposits (weekly) | 12 | 6 | 3 | 201 |
| `WNPL` NPLs (weekly) | 12 | 6 | 3 | 216 |
| `WOBS` Off-balance (weekly) | 4 | 6 | 3 | 72 |
| `WBAL` Other balance (weekly) | 16 | 6 | 3 | 288 |
| `WFX` FX position & custody (weekly) | 45 | 6 | 3 | 810 |

To see every line in a table — 62 rows, not 1,860 — filter to one bank group and
one column:

```
/api/v1/serieList?dataset=T01&bankType=10001&limit=200
```

The weekly datasets cover 6 bank groups rather than 10; BDDK doesn't publish the
deposit-bank ownership splits weekly.

## 7. Datasets

`T01`–`T17` are **BDDK's own monthly table numbers**, so they mean exactly what
BDDK's bulletin says they mean.

| Code | Table | Unit | Series |
|---|---|---|---|
| `T01` | Balance Sheet | million TL | 1,860 |
| `T02` | Income Statement | million TL | 1,590 |
| `T03` | Loans | million TL | 1,712 |
| `T04` | Consumer Loans | million TL | 957 |
| `T05` | Sectoral Loan Distribution | **thousand TL** | 2,057 |
| `T06` | SME Loans | million TL | 480 |
| `T07` | Syndication & Securitization | million TL | 74 |
| `T08` | Securities | million TL | 930 |
| `T09` | Deposits by Type | million TL | 1,560 |
| `T10` | Deposits by Maturity | million TL | 1,680 |
| `T11` | Liquidity Position | million TL | 2,200 |
| `T12` | Capital Adequacy | million TL | 380 |
| `T13` | FX Position | million TL | 110 |
| `T14` | Off-Balance Sheet | million TL | 1,560 |
| `T15` | Ratios | **percentage** | 320 |
| `T16` | Other Information | **count** | 70 |
| `T17` | Foreign Branch Ratios | **percentage** | 30 |

Weekly (all **thousand TL**, 2019-11 → current):

| Code | Section | Series |
|---|---|---|
| `WLOAN` | Loans (krediler) | 396 |
| `WSEC` | Securities (menkul değerler) | 234 |
| `WDEP` | Deposits (mevduat) | 201 |
| `WNPL` | Non-performing loans (takipteki alacaklar) | 216 |
| `WOBS` | Off-balance sheet (bilanço dışı) | 72 |
| `WBAL` | Other balance sheet (diğer bilanço) | 288 |
| `WFX` | FX position & custody (YP pozisyon/saklama) | 810 |

---

## 8. Bank types

The fourth code segment. These are BDDK's own codes.

| Code | Group | Turkish |
|---|---|---|
| `10001` | Entire Sector | Sektör |
| `10002` | Deposit Banks | Mevduat |
| `10003` | Participation Banks | Katılım |
| `10004` | Development & Investment Banks | Kalkınma ve Yatırım |
| `10005` | Local Private Banks | Yerli Özel |
| `10006` | State Banks | Kamu |
| `10007` | Foreign Banks | Yabancı |
| `10008` | Deposit Banks — Local Private | Mevduat-Yerli Özel |
| `10009` | Deposit Banks — State | Mevduat-Kamu |
| `10010` | Deposit Banks — Foreign | Mevduat-Yabancı |

> These **overlap** — they are different cuts of the same sector, not disjoint
> buckets. `10001` is everything; `10002`+`10003`+`10004` partition it by
> licence; `10005`+`10006`+`10007` partition it by ownership; `10008`–`10010`
> are deposit banks split by ownership. **Never sum across cuts.**

---

## 9. Value columns

`TL`, `FX` and `TOT` mean the same everywhere: the lira leg, the
foreign-currency leg, and the total. Some datasets add their own:

| Dataset | Extra columns |
|---|---|
| `T03` | `STTL` `STFX` `STTOT` short-term · `MLTL` `MLFX` `MLTOT` medium/long |
| `T05` | `NPL` non-performing · `NONCASH` non-cash |
| `T06` | `NPL` · `NONCASH` · `CUST` customer count |
| `T09` | `B10K` `B50K` `B250K` `B1M` `B1MP` deposit size brackets |
| `T10` | `DEM` demand · `M1` `M13` `M36` `M612` `M12P` maturity buckets |
| `T11` | `D7` `M1` `M3` `M12` buckets · `ALL` all assets/liabilities |
| `T15` `T17` | `VAL` the ratio value |
| `T16` | `CNT` count |

---

## 10. Reading the numbers correctly

**Units differ per series — read `unit`, never assume.** Most monthly tables are
million TL, but table 5 is *thousand* TL, ratios are percent, table 16 is a
count, and all weekly data is thousand TL. In million TL, `51,760,765` is
**51.76 trillion TL**.

**Monthly dates are period ENDS.** `2026-04-30` is the April figure. These are
**stocks** (a balance at that date), not flows — except table 2, the income
statement, which is cumulative within the year.

**`null` means BDDK filed no figure. It does not mean zero.** Don't fill nulls
with 0 before aggregating.

**English labels come from BDDK, not from us.** BDDK publishes the monthly
bulletin in both languages and `name_en` is their wording — which matters for
regulatory terms. About 2% of monthly lines have no English (BDDK's own gap) and
the **weekly bulletin has none at all**; those come back `null` and you should
fall back to `name`. Nothing here is machine-translated.

**Trailing asterisks in a label are BDDK's footnote markers, not corruption.**
`Loans*`, `Deposit (Participation Funds)***`, `Provisions****` — each points at a
footnote in BDDK's bulletin qualifying that line's scope. Labels are passed
through exactly as filed, so the markers come with them. **We do not capture the
footnote text**, so you get the marker without what it refers to — worth knowing
when a line looks like it should reconcile and doesn't. Strip them with
`re.sub(r"\*+$", "", name)` if they're noise for your purpose.

A couple of labels also begin with `- ` (e.g. `- Devlet Tahvilleri (Bilgi için)`).
That's BDDK's own indentation marking a memo line, not a stray character.

**Nothing is derived.** Every value is as-filed by BDDK. No seasonal adjustment,
no rebasing, no FX conversion, no gap-filling. Ratios are BDDK's own (table 15),
not recomputed by us.

---

## 11. Limits

| | |
|---|---|
| Series per request | 20 |
| Observations per series | 2,000 |
| `/serieList` rows per page | 25,000 — the entire catalog in one call |
| Rate limit | none currently |
| Caching | responses cached 1 hour |

Data updates weekly (BDDK's Friday weekly bulletin) and monthly (mid-month, no
fixed day). There's no webhook — poll `/api/v1` and watch `coverage.latest`.

---

## 12. Errors

| Status | Meaning |
|---|---|
| `400` | bad parameter — the message says which |
| `404` | none of the requested codes exist |
| `503` | API temporarily disabled |

Errors are JSON: `{"error": "…"}`. Messages are meant to be actionable — a
malformed code tells you the expected shape and points at `/serieList`.

---

## 13. Worked examples

**Sector loan growth, last two years, into pandas**

```python
import pandas as pd
df = pd.read_csv("https://carthago.app/api/v1/series"
    "?series=BDDK.T01.I010.10001.TOT&startDate=01-01-2024&type=csv",
    parse_dates=["date"]).set_index("date")
df["yoy_%"] = df.iloc[:, 0].pct_change(12) * 100
```

**Participation vs deposit banks, same line**

```
/api/v1/series?series=BDDK.T01.I010.10003.TOT-BDDK.T01.I010.10002.TOT&type=csv
```

**Every ratio BDDK publishes for the sector**

```
/api/v1/serieList?dataset=T15&bankType=10001&type=csv
```

**Loan/deposit ratio**

```
/api/v1/series?series=BDDK.T01.I010.10001.TOT-BDDK.T01.I027.10001.TOT&type=csv
```
Then divide the columns. Both are million TL, so the ratio is unit-free.

---

## 14. Common series

Whole sector (`10001`); swap the fourth segment for any group in §8.

| Code | Series | Unit |
|---|---|---|
| `BDDK.T01.I026.10001.TOT` | Total assets | million TL |
| `BDDK.T01.I010.10001.TOT` | Loans | million TL |
| `BDDK.T01.I011.10001.TOT` | Non-performing loans (gross) | million TL |
| `BDDK.T01.I027.10001.TOT` | Deposits | million TL |
| `BDDK.T01.I001.10001.TOT` | Cash | million TL |
| `BDDK.T15.I001.10001.VAL` | NPL ratio | percent |
| `BDDK.T15.I002.10001.VAL` | NPL coverage ratio | percent |
| `BDDK.T16.I001.10001.CNT` | Number of banks | count |

---

## 15. Using it with an LLM

Codes can't be guessed, so hand the model the table in §14 plus these rules:

```text
Carthago API — Turkish banking data from BDDK. No key.
Base: https://carthago.app/api/v1
  Data:   GET /series?series=<CODE>&startDate=DD-MM-YYYY[&type=csv]
          (join up to 20 codes with "-")
  Search: GET /serieList?q=<term>&limit=20        (Turkish or English)
  Vocab:  GET /categories
Rules:
- NEVER invent a series code. Use /serieList or the supplied list.
- Read "unit" per series. Don't assume. million TL: 51,760,765 = 51.76tn TL.
- Monthly values are month-END stocks. null ≠ zero.
- Bank-type groups OVERLAP. Never sum across them.
```

---

## 16. Reference

| | |
|---|---|
| Index | `GET /api/v1` |
| Datasets + bank types | `GET /api/v1/categories` |
| Technical notes | [API.md](API.md) |
| Operations | [OPERATIONS.md](OPERATIONS.md) |
