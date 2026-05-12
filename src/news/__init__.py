"""News / qualitative-data ingestion.

Scrapes regulator and disclosure feeds (KAP, TCMB, BDDK) into the
`news_items` table. Mirrors the architecture of `src/audit_reports/`:
each source has a small fetcher that returns plain dicts; `loader.py`
upserts them into the local SQLite, push_to_d1.py syncs them to D1.
"""
