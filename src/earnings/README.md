# `src/earnings/` — results calendar + IR presentation decks

Bank results filings and investor-presentation decks.

- `from_kap.py` — KAP results filings; `presentations.py` — IR deck discovery
  (static URLs + auto-discovery); `classify.py`; `loader.py` / `schema.py`.

**Entry point:** `scripts/update_presentations.py`
(`refresh-presentations-weekly.yml`).

**Writes:** `bank_earnings`.