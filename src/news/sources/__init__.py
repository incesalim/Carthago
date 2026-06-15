"""Per-feed scrapers for the news lane.

One module per source (`bddk`, `kap`, `press`, `tcmb`); each exposes a small
fetcher that returns plain dicts, which `src.news.loader` upserts into the
`news_items` table. Mirrors the fetcher pattern documented in `src/news/__init__.py`.
"""
