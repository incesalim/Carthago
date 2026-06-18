"""Google News long-tail aggregator (source='google_news').

Pulls topic-scoped Google News SEARCH RSS feeds for banking-sector queries and
adds the long tail of outlets that the hand-picked press feeds
(src/news/sources/press.py) don't cover. Two things make this source different
from `press`:

1. Each Google News <item> carries a <source url="https://publisher/">Name</source>
   child — the real publisher, available *before* any decoding. We use it for
   the outlet label and to skip outlets already covered by the press feeds.

2. The <item> <link> is a news.google.com redirect token (the post-July-2024
   `AU_yqL…` format; the old base64 trick is dead). Resolving it to the real
   article URL needs Google's batchexecute RPC, which 429s on parallel/volume
   decoding. We therefore decode SERIALLY (~1.5s apart, via the maintained
   `googlenewsdecoder` library) and ONLY for items we haven't already resolved —
   news_items is the cache, so steady-state runs decode just the handful of new
   items and the rate-limit never bites. A decode failure keeps the still-clickable
   google redirect link as a fallback and is retried on a later run.

Everything else (banking-relevance keyword filter, RSS parsing helpers, date
normalization, summary cleaning) is reused from press.py.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import requests
from lxml import etree

from src.news.loader import NewsItem
from src.news.sources import press
from src.news.sources.press import (
    HEADERS,
    SUMMARY_MAX_CHARS,
    _child_text,
    _clean_text,
    _to_iso,
    is_banking_relevant,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
TOPICS_FILE = REPO_ROOT / "data" / "news" / "google_news_topics.json"

GOOGLE_REDIRECT_PREFIX = "https://news.google.com/"
MAX_ITEMS_PER_TOPIC = 50
# Seconds between decode requests — Google 429s parallel/volume decoding, so
# googlenewsdecoder spaces its requests by this interval. ~1.5s is the
# practitioner-reported safe rate.
DECODE_INTERVAL = 1.5
# Cap decodes per run so a cold cache (first run) can't blow the workflow
# timeout; the remainder is picked up on subsequent daily runs.
MAX_DECODE_PER_RUN = 60

# Hard-coded fallback so the lane still works if google_news_topics.json is
# missing/corrupt. Kept in sync with the JSON by hand.
DEFAULT_TOPICS: list[dict[str, str]] = [
    {"name": "bankacilik-sektoru", "query": "Türkiye bankacılık sektörü", "language": "tr"},
    {"name": "bddk", "query": "BDDK bankacılık", "language": "tr"},
    {"name": "mevduat-kredi-faiz", "query": "mevduat kredi faiz banka", "language": "tr"},
]


def _build_feed_url(query: str, language: str = "tr") -> str:
    """Google News SEARCH RSS feed for a query. Search feeds stay stable, unlike
    the topic/section feeds that began 302-redirecting to opaque hash URLs in
    May 2026."""
    gl = "TR"
    ceid = f"{gl}:{language}"
    return (
        f"https://news.google.com/rss/search?q={quote_plus(query)}"
        f"&hl={language}&gl={gl}&ceid={ceid}"
    )


def _host(url: str | None) -> str | None:
    """netloc, lowercased, sans leading 'www.'."""
    if not url:
        return None
    try:
        h = urlparse(url).netloc.lower()
    except ValueError:
        return None
    if not h:
        return None
    return h[4:] if h.startswith("www.") else h


def _source_url(el) -> str | None:
    """Publisher URL from the Google News <source url="…"> child (pre-decode)."""
    for child in el.xpath("./*[local-name()='source']"):
        href = child.get("url")
        if href and href.strip():
            return href.strip()
    return None


def _source_name(el) -> str | None:
    """Publisher display name from the <source> child text."""
    for child in el.xpath("./*[local-name()='source']"):
        if child.text and child.text.strip():
            return child.text.strip()
    return None


def _external_id(guid: str) -> str:
    """Stable id from the Google News <guid> (the article token). Same article
    → same id across runs, so news_items dedupes and acts as the decode cache."""
    return hashlib.sha1(guid.encode("utf-8")).hexdigest()[:16]


def parse_feed(content: bytes, language: str, skip_hosts: set[str]) -> list[NewsItem]:
    """Parse one Google News search feed into banking-relevant NewsItems.

    Pure (no network), so it is unit-testable. The `url` is left as the
    news.google.com redirect link — decoding happens later, only for new items.
    Items whose publisher host is already covered by the press feeds
    (`skip_hosts`) are dropped so the same outlet isn't shown twice.
    """
    parser = etree.XMLParser(recover=True, huge_tree=True, resolve_entities=False)
    try:
        root = etree.fromstring(content, parser=parser)
    except etree.XMLSyntaxError:
        return []
    if root is None:
        return []

    items: list[NewsItem] = []
    seen: set[str] = set()
    for el in root.xpath("//*[local-name()='item']"):
        title = _clean_text(_child_text(el, "title"))
        link = _child_text(el, "link", "guid", "id")
        guid = _child_text(el, "guid") or link
        if not title or not link or not guid:
            continue
        summary = _clean_text(_child_text(el, "description", "summary", "content"))
        if not is_banking_relevant(title + " " + (summary or "")):
            continue
        host = _host(_source_url(el))
        if host and host in skip_hosts:
            continue
        ext_id = _external_id(guid)
        if ext_id in seen:
            continue
        seen.add(ext_id)

        outlet = _source_name(el) or host or "Google News"
        # Google News titles are usually "Headline - Publisher"; drop the
        # trailing publisher since we already show the outlet separately.
        if outlet and title.endswith(f" - {outlet}"):
            title = title[: -(len(outlet) + 3)].rstrip()
        if summary and len(summary) > SUMMARY_MAX_CHARS:
            summary = summary[: SUMMARY_MAX_CHARS - 1].rstrip() + "…"

        items.append(NewsItem(
            source="google_news",
            external_id=ext_id,
            published_at=_to_iso(_child_text(el, "pubDate", "published", "updated")),
            ticker=None,
            category=outlet,
            title=title,
            summary=summary,
            url=link.strip(),                # news.google.com redirect (pre-decode)
            language=language,
            raw_json=json.dumps(
                {"outlet": outlet, "host": host, "google_url": link.strip()},
                ensure_ascii=False,
            ),
        ))
        if len(items) >= MAX_ITEMS_PER_TOPIC:
            break
    return items


def _decode_url(google_url: str, interval: float) -> str | None:
    """Resolve a news.google.com redirect link to the real publisher URL.

    Lazy-imports googlenewsdecoder so the minimal-deps CI test job (which
    imports this module via tests but never installs the decoder) doesn't fail
    at collection. Returns None on any failure — the caller keeps the google
    link as a working fallback and retries on a later run.
    """
    try:
        from googlenewsdecoder import gnewsdecoder
    except ImportError:
        print("  [google_news] googlenewsdecoder not installed — skipping decode", flush=True)
        return None
    try:
        res = gnewsdecoder(google_url, interval=interval)
    except Exception as e:  # noqa: BLE001 — never let one bad token break the run
        print(f"  [google_news] decode error: {type(e).__name__}: {e}", flush=True)
        return None
    if isinstance(res, dict) and res.get("status") and res.get("decoded_url"):
        return res["decoded_url"]
    return None


def _load_topics() -> list[dict[str, str]]:
    """Read the topic list from google_news_topics.json, falling back to
    DEFAULT_TOPICS. Disabled entries (enabled=false) are skipped."""
    if not TOPICS_FILE.exists():
        return DEFAULT_TOPICS
    try:
        data = json.loads(TOPICS_FILE.read_text(encoding="utf-8"))
        topics = [t for t in data.get("topics", []) if t.get("enabled", True) and t.get("query")]
        return topics or DEFAULT_TOPICS
    except (json.JSONDecodeError, OSError):
        return DEFAULT_TOPICS


def _fetch_feed(url: str, name: str, timeout: int, max_retries: int) -> bytes | None:
    for attempt in range(max_retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code == 200 and r.content:
                return r.content
            print(f"  [google_news:{name}] HTTP {r.status_code}", flush=True)
        except requests.RequestException as e:
            print(f"  [google_news:{name}] {type(e).__name__}: {e}", flush=True)
        time.sleep(2 ** attempt)
    return None


def fetch(
    decoded_ids: set[str] | None = None,
    *,
    decode_interval: float = DECODE_INTERVAL,
    max_decode: int | None = MAX_DECODE_PER_RUN,
    request_timeout: int = 25,
    max_retries: int = 2,
) -> list[NewsItem]:
    """Fetch banking-relevant items from all configured Google News topics.

    `decoded_ids` is the set of external_ids ALREADY stored with a resolved
    (non-google) URL — those are skipped entirely (no re-fetch, no re-decode, so
    their good URL is never clobbered). Every other candidate (brand-new, or
    stored earlier but still pointing at a google redirect) is decode-attempted,
    newest-first, capped at `max_decode` per run.

    Returns only the items processed this run, ready to upsert.
    """
    decoded_ids = decoded_ids or set()
    skip_hosts = {h for u in press.feed_urls() if (h := _host(u))}

    candidates: dict[str, NewsItem] = {}
    for topic in _load_topics():
        name = topic.get("name", topic.get("query", "?"))
        language = topic.get("language", "tr")
        url = _build_feed_url(topic["query"], language)
        content = _fetch_feed(url, name, request_timeout, max_retries)
        if content is None:
            print(f"  [google_news:{name}] skipped (no content)", flush=True)
            continue
        try:
            items = parse_feed(content, language, skip_hosts)
        except Exception as e:  # noqa: BLE001 — never let one feed break the run
            print(f"  [google_news:{name}] parse failed: {type(e).__name__}: {e}", flush=True)
            continue
        for it in items:
            candidates.setdefault(it.external_id, it)  # first writer wins across topics
        print(f"  [google_news:{name}] {len(items)} banking-relevant items", flush=True)

    pending = [it for it in candidates.values() if it.external_id not in decoded_ids]
    pending.sort(key=lambda x: x.published_at, reverse=True)
    if max_decode is not None:
        pending = pending[:max_decode]
    print(f"  [google_news] {len(candidates)} candidates, {len(pending)} to decode "
          f"(interval {decode_interval}s)", flush=True)

    out: list[NewsItem] = []
    decoded = failed = 0
    for it in pending:
        real = _decode_url(it.url, decode_interval)
        if real:
            it.url = real
            decoded += 1
        else:
            failed += 1  # keep the google redirect link; retried next run
        out.append(it)
    print(f"  [google_news] decoded ok={decoded} fallback={failed}", flush=True)
    out.sort(key=lambda x: x.published_at, reverse=True)
    return out
