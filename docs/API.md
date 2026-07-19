# Carthago Data API (`/api/v1`)

Public, read-only, unauthenticated HTTP API serving the **BDDK monthly (tables
1–17) and weekly bulletin** statistics as time series.

Base URL: `https://carthago.app/api/v1`

It is deliberately shaped like **TCMB's EVDS**: series are addressed by short
dotted codes, joined with `-`, over a date range, in `json` or `csv`. Anyone who
has used EVDS can read this without documentation.

```
GET /api/v1/series?series=BDDK.T01.I001.10001.TOT&startDate=01-01-2024&type=csv
```

---

## Coverage

| | |
|---|---|
| Series | ~19,800 |
| Datasets | 24 (17 monthly + 7 weekly) |
| Monthly range | 2020-01 → current |
| Weekly range | 2019-11 → current |
| Source | BDDK (Banking Regulation and Supervision Agency of Türkiye) |

Live numbers: `GET /api/v1`.

---

## Series codes

```
BDDK.<DATASET>.<ITEM>.<BANKTYPE>.<COLUMN>

BDDK.T01.I001.10001.TOT       Balance sheet, item 1, whole sector, total
BDDK.T15.I003.10004.VAL       Ratios, item 3, participation banks
BDDK.WLOAN.I1_0_11.10001.TL   Weekly loans, item 1.0.11, sector, TL leg
```

Always exactly five dot-separated segments.

**`DATASET`** — `T01`–`T17` are **BDDK's own monthly table numbers**, so they
mean what BDDK says they mean:

| | | | |
|---|---|---|---|
| `T01` Balance Sheet | `T02` Income Statement | `T03` Loans | `T04` Consumer Loans |
| `T05` Sectoral Loans | `T06` SME Loans | `T07` Syndication | `T08` Securities |
| `T09` Deposits by Type | `T10` Deposits by Maturity | `T11` Liquidity | `T12` Capital Adequacy |
| `T13` FX Position | `T14` Off-Balance Sheet | `T15` Ratios | `T16` Other Information |
| `T17` Foreign Branch Ratios | | | |

Weekly bulletin sections: `WLOAN` (krediler), `WSEC` (menkul değerler), `WDEP`
(mevduat), `WNPL` (takipteki alacaklar), `WOBS` (bilanço dışı), `WBAL` (diğer
bilanço), `WFX` (YP pozisyon/saklama).

**`ITEM`** — a catalog token. **Look it up via `/serieList`; do not construct
it.** For most datasets it renders the source table's own line number, but for
`T08`/`T11`–`T14`/`T16` it is a catalog-assigned slot, because those lines are
keyed by name rather than number upstream.

**`BANKTYPE`** — BDDK's own bank-type code. `10001` is the whole sector. Full
list with names: `GET /api/v1/categories`.

**`COLUMN`** — the value leg. `TL`, `FX`, `TOT` mean the same thing everywhere.
Dataset-specific tokens:

| Dataset | Tokens |
|---|---|
| `T03` | `STTL` `STFX` `STTOT` (short-term), `MLTL` `MLFX` `MLTOT` (medium/long), `TL` `FX` `TOT` |
| `T05` | `TOT`, `NPL`, `NONCASH` |
| `T06` | `TL` `FX` `TOT`, `NPL`, `NONCASH`, `CUST` (customer count) |
| `T09` | `B10K` `B50K` `B250K` `B1M` `B1MP` (deposit brackets), `TOT` |
| `T10` | `DEM` (demand), `M1` `M13` `M36` `M612` `M12P` (maturity), `TOT` |
| `T11` | `D7` `M1` `M3` `M12` (buckets), `ALL` |
| `T15`, `T17` | `VAL` |
| `T16` | `CNT` (count) |

### Codes are stable

Once published, a code keeps its meaning. Three of five segments are keys BDDK
itself assigns, and the catalog builder carries existing item slots forward
rather than renumbering. If a series is ever retired the code stops resolving —
it is never silently repointed at different data.

---

## Endpoints

### `GET /api/v1/series` — observations

| Param | | |
|---|---|---|
| `series` | **required** | Dash-joined codes, max 20. Our codes contain no dashes. |
| `startDate` | optional | `DD-MM-YYYY` (EVDS style) or `YYYY-MM-DD`. |
| `endDate` | optional | Same. Omit both for full history. |
| `type` | optional | `json` (default) or `csv`. |

```bash
curl "https://carthago.app/api/v1/series?series=BDDK.T01.I001.10001.TOT&startDate=01-01-2025"
```

```json
{
  "meta": {
    "source": "BDDK (Banking Regulation and Supervision Agency of Türkiye)",
    "series_count": 1,
    "unknown": []
  },
  "series": [
    {
      "series_code": "BDDK.T01.I001.10001.TOT",
      "name": "Nakit Değerler",
      "dataset": "T01",
      "frequency": "monthly",
      "bank_type_code": "10001",
      "unit": "million TL",
      "observations": [
        { "date": "2025-01-31", "value": 512345.0 },
        { "date": "2025-02-28", "value": 519876.0 }
      ]
    }
  ]
}
```

Codes that don't exist are returned in `meta.unknown` rather than failing the
request — pulling 20 series shouldn't lose 19 because one was retired. If *none*
resolve you get `404`.

CSV output outer-joins dates across all requested series, one column each, so it
drops straight into a spreadsheet.

### `GET /api/v1/serieList` — find codes

| Param | |
|---|---|
| `dataset` | `T01`…`T17`, `WLOAN`… |
| `bankType` | BDDK bank-type code |
| `frequency` | `monthly` or `weekly` |
| `q` | substring match on the label (case-sensitive for Turkish characters) |
| `limit` / `offset` | default 500, max 5000 |
| `type` | `json` (default) or `csv` |

```bash
curl "https://carthago.app/api/v1/serieList?dataset=T01&bankType=10001&limit=5"
```

Each row carries `series_code`, `item_name`, `unit`, `start_date`, `end_date`
and `obs_count`, so you can see a series' coverage before requesting it.

### `GET /api/v1/categories` — the vocabulary

Dataset tokens with BDDK's own table names and coverage counts, plus every
bank-type code with its Turkish and English name. Computed from the catalog, so
it cannot drift from what `/series` will serve.

### `GET /api/v1` — self-describing index

The whole contract in one response: endpoints, code grammar, conventions, live
coverage, worked examples.

---

## Authentication

**There is none.** No API key, no signup, no header. The data is public, so the
endpoint is open — unlike TCMB's EVDS, which requires a `key` header.

```python
import urllib.request, json

BASE = "https://carthago.app/api/v1"

d = json.load(urllib.request.urlopen(
    f"{BASE}/series?series=BDDK.T01.I001.10001.TOT&startDate=01-01-2026"))
for o in d["series"][0]["observations"]:
    print(o["date"], o["value"])
```

Straight into pandas — `type=csv` returns a wide table (date + one column per
series), the same shape EVDS gives you:

```python
import pandas as pd
df = pd.read_csv(
    f"{BASE}/series?series=BDDK.T01.I001.10001.TOT-BDDK.T02.I001.10001.TOT"
    "&startDate=01-01-2024&type=csv",
    parse_dates=["date"],
).set_index("date")
```

No `User-Agent` gymnastics are needed: a Cloudflare Configuration Rule
(`starts_with(http.request.uri.path, "/api/v1")` → Browser Integrity Check
**Off**) exempts this path, so stdlib `urllib` — and therefore
`pandas.read_csv`, which uses it — works unmodified. The rest of the site keeps
its bot protection. If you ever see `403` with **Cloudflare error 1010** on
`/api/v1`, that rule has been removed or its expression broken; see
[OPERATIONS.md](OPERATIONS.md).

## Using it with ChatGPT / Claude / any LLM

Paste this as context. It needs web access (ChatGPT: browsing on).

The code table matters: series codes are **opaque and cannot be guessed**, and
`/serieList?q=` matches the **as-filed Turkish** labels, so an LLM searching
"total assets" gets zero hits. Giving it the common codes up front skips
discovery for most questions.

````text
You can query the Carthago API for Turkish banking-sector data (source: BDDK).
No API key. Base URL: https://carthago.app/api/v1

FETCH DATA
  GET /series?series=<CODE>&startDate=DD-MM-YYYY&endDate=DD-MM-YYYY
  Join up to 20 codes with "-". Add &type=csv for CSV.
  e.g. /series?series=BDDK.T01.I026.10001.TOT&startDate=01-01-2024

COMMON CODES (whole sector = bank type 10001; monthly)
  BDDK.T01.I026.10001.TOT   Total assets                      million TL
  BDDK.T01.I010.10001.TOT   Loans                             million TL
  BDDK.T01.I011.10001.TOT   Non-performing loans (gross)      million TL
  BDDK.T01.I027.10001.TOT   Deposits                          million TL
  BDDK.T01.I001.10001.TOT   Cash                              million TL
  BDDK.T15.I001.10001.VAL   NPL ratio                         percent
  BDDK.T15.I002.10001.VAL   NPL coverage ratio                percent

SWAP THE BANK TYPE (4th segment) TO SLICE THE SECTOR
  10001 entire sector    10002 deposit banks     10003 participation banks
  10004 development & investment banks           10005 local private banks
  Full list: GET /categories

FIND OTHER SERIES
  GET /serieList?q=<TURKISH TERM>&limit=20
  Labels are Turkish as filed by BDDK — search "kredi", "mevduat",
  "aktif", "karşılık", NOT English. Also filter by dataset/bankType:
  GET /serieList?dataset=T01&bankType=10001&limit=200
  Datasets: T01 balance sheet, T02 income statement, T03-T07 loans,
  T09/T10 deposits, T15 ratios. GET /categories lists all 24.

RULES
- NEVER invent a series code. Get it from /serieList or the list above.
- Units differ per series — read "unit" in the response. Don't assume.
- Monthly values are dated to month-END and are STOCKS, not flows.
- A null value means BDDK filed no figure. It does not mean zero.
- Amounts in "million TL": 51,760,765 = 51.76 trillion TL.
````

## Conventions

- **Dates in** — `DD-MM-YYYY` or `YYYY-MM-DD`. **Dates out** — always `YYYY-MM-DD`.
- **Monthly observations are dated to the period END** (`2026-04-30`), because a
  BDDK monthly figure is a month-end stock, not something that happened on the 1st.
- **Units vary by series.** Read `unit` from `/serieList`. Monthly tables are
  mostly `million TL`, table 5 is `thousand TL`, ratios are `percentage`, table
  16 is `count`, weekly is `thousand TL`. Never assume.
- **`null` means BDDK filed no figure** for that period. It does not mean zero.
- **CORS** is open (`*`). The data is public and there are no credentials.
- **Caching** — responses carry `Cache-Control: max-age=3600`. Data moves monthly
  or weekly; an hour of staleness is invisible.
- **Limits** — 20 series per request, 2,000 observations per series, 5,000 catalog
  rows per `/serieList` page. No rate limit or API key at present.

## Not served

- **Per-bank data.** The `bank_audit_*` family (individual banks' BRSA filings)
  is not exposed here. This API is BDDK's published sector aggregates only.
- **The USD reporting basis.** BDDK's monthly tables carry a USD-converted
  variant, but it exists for a single month (2025-12) against 76 months of TL, so
  publishing it would add ~14,000 single-observation series. Convert with a rate
  of your choosing instead. See `INCLUDE_USD_BASIS` in
  `scripts/build_api_catalog.py`.

## Attribution

Data is published by **BDDK** and is public. Attribution to BDDK as the source,
and to Carthago as the distributor, is appreciated.

---

## How it works (internal)

BDDK tables are stored **long** (period × dimension × item) — nothing in them
names a series. `scripts/build_api_catalog.py` enumerates every
`(dataset, item, bank type, value column)` tuple that carries data and writes it
to the `api_series` catalog (migration `0031`), which is what `/serieList`
lists and what turns a code into a query.

A code is **never parsed into SQL**. It is looked up in `api_series`, which holds
the real filter values. That indirection is what lets published codes survive
storage quirks — `other_data` keys items by name because its `item_order`
collides inside table 12, and no caller should have to know that.

Rebuild + publish:

```bash
python scripts/build_api_catalog.py --dry-run   # report, change nothing
python scripts/build_api_catalog.py             # write data/bddk_data.db
python scripts/push_to_d1.py --only-tables api_series
```

`api_series` is a full-rebuild table, so it is pushed only when named
explicitly. `refresh-data.yml` does both steps after every BDDK refresh.

Kill switch: set `PUBLIC_API_DISABLED=1` on the Worker and every `/api/v1` route
returns `503` without a deploy.
