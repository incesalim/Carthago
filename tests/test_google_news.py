"""Tests for src/news/sources/google_news.py — the Google News long-tail lane.

All pure (no network, no decoding): feed parsing, <source url> outlet
extraction, the "Headline - Publisher" suffix strip, host-level dedup against
the press feeds, and stable ids. The live search feeds + redirect-token decode
are exercised by the cron run, not here — and googlenewsdecoder is imported
lazily inside _decode_url, so this test runs under the minimal-deps CI job
(ruff/pytest/lxml/requests) without it installed.
"""
import hashlib

from src.news.sources import google_news


# A Google News search-feed item carries a <source url="…">Name</source> child
# and a news.google.com redirect <link>/<guid> (the post-2024 AU_yqL… token).
GN_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>BDDK'dan onay çıktı, yeni katılım bankası kuruluyor - Akdeniz Gazetesi</title>
    <link>https://news.google.com/rss/articles/CBMiAU_yqLABCDEF?oc=5</link>
    <guid isPermaLink="false">CBMiAU_yqLABCDEF</guid>
    <pubDate>Tue, 17 Jun 2026 09:00:00 GMT</pubDate>
    <description><![CDATA[<a href="x">BDDK onayı</a> <font>Akdeniz Gazetesi</font>]]></description>
    <source url="https://www.akdenizgazetesi.com">Akdeniz Gazetesi</source>
  </item>
  <item>
    <title>Mevduat faizleri yükseldi - Bloomberg HT</title>
    <link>https://news.google.com/rss/articles/CBMiAU_yqLZZZ?oc=5</link>
    <guid isPermaLink="false">CBMiAU_yqLZZZ</guid>
    <pubDate>Tue, 17 Jun 2026 08:00:00 GMT</pubDate>
    <source url="https://www.bloomberght.com">Bloomberg HT</source>
  </item>
  <item>
    <title>Hava durumu: yarın yağmurlu - Akdeniz Gazetesi</title>
    <link>https://news.google.com/rss/articles/CBMiAU_yqLWEATHER?oc=5</link>
    <guid isPermaLink="false">CBMiAU_yqLWEATHER</guid>
    <pubDate>Tue, 17 Jun 2026 07:00:00 GMT</pubDate>
    <source url="https://www.akdenizgazetesi.com">Akdeniz Gazetesi</source>
  </item>
</channel></rss>""".encode("utf-8")


def test_parse_feed_extracts_outlet_and_strips_publisher_suffix():
    # bloomberght.com is a press feed → its item is dropped (no duplicate outlet).
    items = google_news.parse_feed(GN_SAMPLE, "tr", skip_hosts={"bloomberght.com"})
    assert len(items) == 1
    it = items[0]
    assert it.source == "google_news"
    assert it.category == "Akdeniz Gazetesi"          # from <source> tag
    # " - Akdeniz Gazetesi" suffix stripped from the headline.
    assert it.title == "BDDK'dan onay çıktı, yeni katılım bankası kuruluyor"
    assert it.language == "tr"
    assert it.ticker is None
    assert it.body_text is None
    # url stays the un-decoded google redirect link (decoded later, only if new).
    assert it.url.startswith("https://news.google.com/rss/articles/")


def test_external_id_is_stable_guid_hash():
    items = google_news.parse_feed(GN_SAMPLE, "tr", skip_hosts={"bloomberght.com"})
    expected = hashlib.sha1(b"CBMiAU_yqLABCDEF").hexdigest()[:16]
    assert items[0].external_id == expected


def test_host_dedup_drops_existing_press_outlets():
    # Without skip_hosts the Bloomberg HT item survives; with it, it's gone.
    kept_all = google_news.parse_feed(GN_SAMPLE, "tr", skip_hosts=set())
    outlets = {it.category for it in kept_all}
    assert "Bloomberg HT" in outlets
    assert "Akdeniz Gazetesi" in outlets


def test_relevance_filter_drops_non_banking():
    items = google_news.parse_feed(GN_SAMPLE, "tr", skip_hosts=set())
    # The weather item is dropped even though it shares an allowed outlet.
    assert all("Hava durumu" not in it.title for it in items)


def test_host_normalizes_www():
    assert google_news._host("https://www.example.com/a/b") == "example.com"
    assert google_news._host("https://news.google.com/x") == "news.google.com"
    assert google_news._host(None) is None


def test_build_feed_url_is_a_search_feed():
    url = google_news._build_feed_url("BDDK bankacılık", "tr")
    assert url.startswith("https://news.google.com/rss/search?q=")
    assert "hl=tr" in url and "gl=TR" in url and "ceid=TR:tr" in url
