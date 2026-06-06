"""Turkish financial-press RSS aggregator.

Unlike kap/tcmb/bddk (primary regulator + disclosure feeds), this source
pulls *journalism* about the banking sector from mainstream TR financial
outlets (Bloomberg HT, Dünya, Ekonomim, AA, Hürriyet, NTV …). The feed list
lives in data/news/press_feeds.json (hand-edited via PR).

Those feeds are GENERAL economy/finance feeds, so every item is passed
through a banking-relevance keyword filter (`is_banking_relevant`) — only
items whose headline or summary mention banks/regulators/rates survive.

Copyright/ToS: we store only headline + canonical link + a short snippet
(no full article body, unlike TCMB/BDDK where the regulator's own text is
fair to cache). The dashboard card links out to the original.

Parsing uses lxml in recover mode so it tolerates both RSS (<item>) and
Atom (<entry>), namespaced feeds, and the mildly-malformed XML some Turkish
outlets emit (AA's feed has unbalanced tags). A feed that fails to fetch or
parse is logged and skipped — it never fails the whole run.
"""
from __future__ import annotations

import hashlib
import html as html_lib
import json
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
from lxml import etree

from src.news.loader import NewsItem

REPO_ROOT = Path(__file__).resolve().parents[3]
FEEDS_FILE = REPO_ROOT / "data" / "news" / "press_feeds.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}

SUMMARY_MAX_CHARS = 400
# Cap kept items per feed so one outlet can't dominate a run; the relevance
# filter already trims most of a 20–100 item feed down to a handful.
MAX_ITEMS_PER_FEED = 60

# Hard-coded fallback so the pipeline still works if press_feeds.json is
# missing/corrupt. Kept in sync with the JSON by hand.
DEFAULT_FEEDS: list[dict[str, str]] = [
    {"name": "bloomberght", "outlet": "Bloomberg HT", "url": "https://www.bloomberght.com/rss", "language": "tr"},
    {"name": "dunya", "outlet": "Dünya", "url": "https://www.dunya.com/rss", "language": "tr"},
    {"name": "ekonomim", "outlet": "Ekonomim", "url": "https://www.ekonomim.com/rss", "language": "tr"},
    {"name": "aa_ekonomi", "outlet": "Anadolu Ajansı", "url": "https://www.aa.com.tr/tr/rss/default?cat=ekonomi", "language": "tr"},
    {"name": "ntv_ekonomi", "outlet": "NTV Ekonomi", "url": "https://www.ntv.com.tr/ekonomi.rss", "language": "tr"},
]
# Hürriyet was dropped 2026-06-06 — its feed froze a large Oct-2024 block that
# injected stale items. Kept out of DEFAULT_FEEDS too; see press_feeds.json
# "_removed".

# Banking-relevance keywords, pre-normalized to lowercase Turkish (see
# `_normalize_tr`). An item is kept if its title or summary matches ANY of
# these at a LEFT word boundary (see `_compile`). Left-boundary-only is
# deliberate: Turkish is agglutinative, so "banka" must still catch
# "bankalar", "bankacılık", "bankanın", etc. (suffixes), while the leading
# \b blocks mid-word collisions like "akreditasyonu" matching "kredi" or
# "garantili" (guaranteed) matching the bank "garanti".
RELEVANCE_KEYWORDS: tuple[str, ...] = (
    # institutions / regulators
    "banka", "bankac", "bddk", "tmsf", "tcmb", "merkez bankas", "katılım finans",
    # the major banks by name (so a bank story survives even without a generic
    # term). Bank short-names that collide with common Turkish words are
    # qualified — "garanti" alone also means "guarantee", so require the brand.
    "akbank", "garanti bbva", "garanti bankas", "yapı kredi", "yapıkredi",
    "iş bankas", "is bankas", "ziraat bankas", "vakıfbank", "vakıf bank",
    "halkbank", "halk bankas", "şekerbank", "denizbank", "qnb", "albaraka",
    "kuveyt türk", "fibabanka", "odeabank", "anadolubank", "tskb", "eximbank",
    # products / activity that is banking-sector by nature
    "mevduat", "kredi", "faiz", "takipteki", "sermaye yeterlilik",
    "munzam karşılık", "politika faizi", "swap",
)

# Items that match a relevance keyword only incidentally and are almost never
# Turkish-banking-sector news. Checked AFTER relevance: an item is dropped if
# it matches one of these and contains no STRONGER banking signal.
NEGATIVE_KEYWORDS: tuple[str, ...] = (
    "dünya bankas",          # World Bank
    "avrupa imar",           # EBRD (Avrupa İmar ve Kalkınma Bankası)
    "asya altyapı",          # AIIB
    "islam kalkınma bankas", # Islamic Development Bank
)
# A negative match is overridden (item kept) if any of these strong, clearly
# domestic-banking signals is also present.
STRONG_KEYWORDS: tuple[str, ...] = (
    "bddk", "tcmb", "merkez bankas", "mevduat", "kredi kartı",
    "akbank", "garanti bbva", "yapı kredi", "iş bankas", "is bankas",
    "ziraat bankas", "vakıfbank", "halkbank", "şekerbank", "denizbank",
    "qnb", "albaraka", "kuveyt türk", "bankacılık sektör",
)


def _normalize_tr(s: str | None) -> str:
    """Lowercase Turkish-aware: map the dotted/dotless I pair before lower()
    so 'İŞ BANKASI' → 'iş bankası' and 'BANKACILIK' → 'bankacılık'."""
    if not s:
        return ""
    return s.replace("İ", "i").replace("I", "ı").lower()


def _compile(keywords: tuple[str, ...]) -> re.Pattern[str]:
    """Compile keywords into one alternation anchored at a LEFT word boundary.
    Keywords are normalized first so they match against `_normalize_tr` text."""
    alt = "|".join(re.escape(_normalize_tr(k)) for k in keywords)
    return re.compile(r"\b(?:" + alt + r")", re.UNICODE)


_RELEVANCE_RE = _compile(RELEVANCE_KEYWORDS)
_NEGATIVE_RE = _compile(NEGATIVE_KEYWORDS)
_STRONG_RE = _compile(STRONG_KEYWORDS)


def is_banking_relevant(text: str) -> bool:
    """True if `text` (title + summary) looks like Turkish-banking news."""
    t = _normalize_tr(text)
    if not _RELEVANCE_RE.search(t):
        return False
    if _NEGATIVE_RE.search(t) and not _STRONG_RE.search(t):
        return False
    return True


def _clean_text(raw: str | None) -> str | None:
    """Strip HTML tags + CDATA, unescape entities, collapse whitespace."""
    if not raw:
        return None
    text = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", raw, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _canonical_link(url: str | None) -> str | None:
    """Drop tracking query params + fragment + trailing slash so the same
    article from the same feed yields a stable id across runs."""
    if not url:
        return None
    url = url.strip()
    url = url.split("#", 1)[0]
    url = re.sub(r"[?&](utm_[^=]+|fbclid|gclid)=[^&]*", "", url)
    url = re.sub(r"\?$", "", url)
    return url.rstrip("/") or url


def _external_id(canonical_link: str) -> str:
    """Short, stable id for the (source, external_id) primary key. Same link
    → same id, so re-scrapes upsert in place and a story syndicated to the
    same URL never duplicates."""
    return hashlib.sha1(canonical_link.encode("utf-8")).hexdigest()[:16]


def _to_iso(raw: str | None) -> str:
    """Parse an RSS pubDate (RFC 822) or Atom published/updated (ISO-8601)
    into ISO-8601 UTC. Falls back to now() on an unparseable date."""
    if not raw:
        return datetime.now(timezone.utc).isoformat()
    raw = raw.strip()
    # RFC 822: 'Sat, 06 Jun 2026 11:20:07 +0300' (and the odd '... Z' variant)
    try:
        dt = parsedate_to_datetime(raw)
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        pass
    # ISO-8601: '2026-05-25T10:38:59+03:00' (Atom)
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except ValueError:
        return datetime.now(timezone.utc).isoformat()


def _child_text(el, *local_names: str) -> str | None:
    """First non-empty child by local-name (namespace-agnostic). For <link>
    with no text (Atom), fall back to its href attribute."""
    for nm in local_names:
        for child in el.xpath(f"./*[local-name()='{nm}']"):
            if child.text and child.text.strip():
                return child.text.strip()
            href = child.get("href")
            if href and href.strip():
                return href.strip()
    return None


def parse_feed(content: bytes, outlet: str, language: str) -> list[NewsItem]:
    """Parse one feed's bytes into banking-relevant NewsItems.

    Pure (no network) so it is unit-testable. Handles RSS <item> and Atom
    <entry>, dedupes by canonical link within the feed, and applies the
    relevance filter. Items lacking a usable link are skipped.
    """
    parser = etree.XMLParser(recover=True, huge_tree=True, resolve_entities=False)
    try:
        root = etree.fromstring(content, parser=parser)
    except etree.XMLSyntaxError:
        return []
    if root is None:
        return []

    entries = root.xpath("//*[local-name()='item'] | //*[local-name()='entry']")
    items: list[NewsItem] = []
    seen: set[str] = set()
    for el in entries:
        title = _clean_text(_child_text(el, "title"))
        link = _canonical_link(_child_text(el, "link", "guid", "id"))
        if not title or not link:
            continue
        summary = _clean_text(_child_text(el, "description", "summary", "content"))
        blob = title + " " + (summary or "")
        if not is_banking_relevant(blob):
            continue
        ext_id = _external_id(link)
        if ext_id in seen:
            continue
        seen.add(ext_id)
        if summary and len(summary) > SUMMARY_MAX_CHARS:
            summary = summary[: SUMMARY_MAX_CHARS - 1].rstrip() + "…"
        published = _to_iso(_child_text(el, "pubDate", "published", "updated", "date"))
        items.append(NewsItem(
            source="press",
            external_id=ext_id,
            published_at=published,
            ticker=None,                 # sector-level feed; no per-bank tagging
            category=outlet,             # display outlet, e.g. "Bloomberg HT"
            title=title,
            summary=summary,
            url=link,
            language=language,
            # body_text intentionally None — we link out, not cache full text.
            raw_json=json.dumps({"outlet": outlet, "link": link}, ensure_ascii=False),
        ))
        if len(items) >= MAX_ITEMS_PER_FEED:
            break
    return items


def _load_feeds() -> list[dict[str, str]]:
    """Read the feed list from press_feeds.json, falling back to DEFAULT_FEEDS.
    Disabled entries (enabled=false) are skipped."""
    if not FEEDS_FILE.exists():
        return DEFAULT_FEEDS
    try:
        data = json.loads(FEEDS_FILE.read_text(encoding="utf-8"))
        feeds = [f for f in data.get("feeds", []) if f.get("enabled", True) and f.get("url")]
        return feeds or DEFAULT_FEEDS
    except (json.JSONDecodeError, OSError):
        return DEFAULT_FEEDS


def enabled_outlets() -> set[str]:
    """Outlet display names for the currently-enabled feeds. Used to purge
    stored press rows from outlets that have been removed/disabled in
    press_feeds.json (e.g. Hürriyet), so a removed feed's items don't linger."""
    return {f.get("outlet", f.get("name", "")) for f in _load_feeds()}


def fetch(request_timeout: int = 25, max_retries: int = 2) -> list[NewsItem]:
    """Fetch + filter all configured press feeds. Resilient: a feed that
    fails to fetch/parse is logged and skipped. Returns items newest-first,
    deduped by external_id across feeds."""
    all_items: dict[str, NewsItem] = {}
    for feed in _load_feeds():
        name = feed.get("name", feed.get("url", "?"))
        outlet = feed.get("outlet", name)
        language = feed.get("language", "tr")
        url = feed["url"]
        content: bytes | None = None
        for attempt in range(max_retries):
            try:
                r = requests.get(url, headers=HEADERS, timeout=request_timeout)
                if r.status_code == 200 and r.content:
                    content = r.content
                    break
                print(f"  [press:{name}] HTTP {r.status_code}", flush=True)
            except requests.RequestException as e:
                print(f"  [press:{name}] {type(e).__name__}: {e}", flush=True)
            time.sleep(2 ** attempt)
        if content is None:
            print(f"  [press:{name}] skipped (no content)", flush=True)
            continue
        try:
            items = parse_feed(content, outlet, language)
        except Exception as e:  # noqa: BLE001 — never let one feed break the run
            print(f"  [press:{name}] parse failed: {type(e).__name__}: {e}", flush=True)
            continue
        for it in items:
            # First writer wins; later feeds with the same canonical URL skip.
            all_items.setdefault(it.external_id, it)
        print(f"  [press:{name}] {len(items)} banking-relevant items", flush=True)

    out = list(all_items.values())
    out.sort(key=lambda x: x.published_at, reverse=True)
    return out
