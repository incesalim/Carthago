"""Tests for src/news/sources/press.py — the banking-sector press aggregator.

All pure (no network): the relevance filter, RSS/Atom parsing, date handling,
canonical-link dedup. The live RSS feeds are validated by the cron run, not
here — these guard the parsing/filtering logic that turns feed bytes into
NewsItems."""
from src.news.sources import press


# --- relevance filter ---------------------------------------------------

def test_keeps_genuine_banking_items():
    assert press.is_banking_relevant("Bankacılık sektörünün net kârı 75 milyar TL oldu")
    assert press.is_banking_relevant("Merkez Bankası faaliyet iznini iptal etti")
    assert press.is_banking_relevant("Konut kredisi faizleri düştü")
    assert press.is_banking_relevant("Garanti BBVA bilançosunu açıkladı")
    assert press.is_banking_relevant("BDDK'dan yeni karşılık düzenlemesi")


def test_drops_substring_false_positives():
    # "garantili" (guaranteed) must not match the bank "garanti";
    # "akreditasyonu" (accreditation) must not match "kredi" — the leading
    # word boundary is what prevents these mid-word collisions.
    assert not press.is_banking_relevant("Gelir Garantili Besicilik Projesi et fiyatları")
    assert not press.is_banking_relevant("TAV havalimanları Karbon Akreditasyonu aldı")


def test_drops_non_banking_items():
    assert not press.is_banking_relevant("Kırmızı ette yeni dönem üreticiye güvence")
    assert not press.is_banking_relevant("Altın fiyatları canlı grafik")


def test_hurriyet_not_in_enabled_outlets():
    # Hürriyet was removed for serving a stale Oct-2024 block; guard against
    # it (or the stale fallback) creeping back into the configured feeds.
    outlets = press.enabled_outlets()
    assert outlets, "expected at least one configured press feed"
    assert "Hürriyet Ekonomi" not in outlets
    assert all("hurriyet" not in f["url"] for f in press.DEFAULT_FEEDS)


def test_negative_keyword_dropped_unless_strong_signal():
    # World Bank alone → out; World Bank + a domestic-banking signal → in.
    assert not press.is_banking_relevant("Dünya Bankası'ndan Türkiye'ye 191 milyon euro destek")
    assert press.is_banking_relevant("Dünya Bankası ve BDDK ortak çalışması mevduat üzerine")


# --- parsing ------------------------------------------------------------

RSS_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title><![CDATA[Bankacılık sektörünün net kârı arttı]]></title>
    <link>https://example.com/haber/banka-kari-123?utm_source=rss#yorum</link>
    <guid>https://example.com/haber/banka-kari-123</guid>
    <pubDate>Sat, 06 Jun 2026 11:20:07 +0300</pubDate>
    <description><![CDATA[<p>Sektörün net k&#226;rı 75 milyar TL oldu.</p>]]></description>
  </item>
  <item>
    <title>Kırmızı et fiyatları yükseldi</title>
    <link>https://example.com/haber/et-456</link>
    <pubDate>Sat, 06 Jun 2026 10:00:00 +0300</pubDate>
  </item>
</channel></rss>""".encode("utf-8")


def test_parse_feed_filters_and_normalizes():
    items = press.parse_feed(RSS_SAMPLE, "Example", "tr")
    # Only the banking item survives the relevance filter.
    assert len(items) == 1
    it = items[0]
    assert it.source == "press"
    assert it.category == "Example"
    assert it.language == "tr"
    assert it.ticker is None
    assert it.body_text is None
    # Date → ISO-8601 UTC (11:20 +03:00 == 08:20Z).
    assert it.published_at.startswith("2026-06-06T08:20:07")
    # Summary: HTML stripped, entities unescaped.
    assert "75 milyar TL" in it.summary
    assert "<p>" not in it.summary


def test_canonical_link_strips_tracking_and_fragment():
    items = press.parse_feed(RSS_SAMPLE, "Example", "tr")
    # utm param + #fragment removed; guid (clean) and link collapse to one id.
    assert items[0].url == "https://example.com/haber/banka-kari-123"


def test_parse_feed_dedups_same_link():
    doubled = RSS_SAMPLE.replace(
        b"</channel></rss>",
        b"""<item>
            <title>Banka kredi faizleri</title>
            <link>https://example.com/haber/banka-kari-123</link>
            <pubDate>Sat, 06 Jun 2026 12:00:00 +0300</pubDate>
        </item></channel></rss>""",
    )  # second item shares the first's canonical link
    items = press.parse_feed(doubled, "Example", "tr")
    ids = [it.external_id for it in items]
    assert len(ids) == len(set(ids))  # same canonical link → one item


ATOM_SAMPLE = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>TCMB faiz kararı açıklandı</title>
    <link href="https://example.com/atom/faiz-1"/>
    <id>https://example.com/atom/faiz-1</id>
    <updated>2026-05-25T10:38:59+03:00</updated>
    <summary>Politika faizi sabit tutuldu.</summary>
  </entry>
</feed>""".encode("utf-8")


def test_parse_feed_handles_atom():
    items = press.parse_feed(ATOM_SAMPLE, "Example", "tr")
    assert len(items) == 1
    assert items[0].url == "https://example.com/atom/faiz-1"
    assert items[0].published_at.startswith("2026-05-25T07:38:59")  # +03:00 → UTC


def test_parse_feed_tolerates_malformed_xml():
    # AA's feed emits unbalanced tags; recover mode must not raise.
    broken = b"<rss><channel><item><title>Banka haberi</title>" \
             b"<link>https://x.com/1</link><pubDate>bad date</pubDate></item></rss>"
    items = press.parse_feed(broken, "Example", "tr")
    assert len(items) == 1
    # Unparseable date falls back to a valid ISO timestamp (now()).
    assert items[0].published_at.endswith("+00:00") or "T" in items[0].published_at
