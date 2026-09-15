# `src/news/` — news feeds, regulation briefing, "The Read"

Collects KAP / TCMB / BDDK / bank-press / Google News items, then runs two
LLM lanes on top of them.

- `sources/` — one module per feed (`kap.py`, `tcmb.py`, `bddk.py`, `press.py`,
  `google_news.py`); `loader.py` / `schema.py` — persistence; `bank_tagger.py` —
  entity tagging; `_htmltext.py` — text cleanup.
- `free_llm.py`, `kimi.py` — free-model clients.
- Briefing gates shared by generator and checker: `briefing_facts.py`,
  `briefing_citations.py`, `briefing_validate.py`.

**Entry points:** `scripts/sync_news.py`, `scripts/summarize_regulations.py`,
`scripts/generate_read_headlines.py`, `scripts/ingest_policy_baseline.py`.

**Writes:** `news_items`, `news_item_banks`, `regulation_briefings`,
`read_headlines`. The briefing lane is publication-gated by
`check_briefing_facts.py`.