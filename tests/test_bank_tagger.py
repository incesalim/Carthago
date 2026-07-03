"""Pure-logic tests for src/news/bank_tagger.py (no network).

Covers the Turkish collision traps the alias map is designed around, the
title/summary precedence, and retag_all's diff semantics (idempotence,
stale-tag deletion + d1_pending_deletes outbox).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.news.bank_tagger import (
    DEFAULT_ALIASES,
    load_aliases,
    match_banks,
    retag_all,
)
from src.news.schema import init_schema

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- match_banks

def test_matches_simple_bank_name():
    assert match_banks("Akbank'ın kredi hacmi arttı") == {"AKBNK": "title"}


def test_agglutinative_suffixes_match():
    # LEFT-boundary-only prefix aliases must survive Turkish suffixing.
    assert "GARAN" in match_banks("Garanti Bankası'nın bilançosu açıklandı")
    assert "ISCTR" in match_banks("İş Bankası'ndan yeni mevduat ürünü")
    assert "VAKBN" in match_banks("VakıfBank'tan konut kredisi kampanyası")


def test_uppercase_turkish_i_normalization():
    assert "ISCTR" in match_banks("İŞ BANKASI KÂRINI AÇIKLADI")


def test_garanti_word_collision():
    # "garantili" (guaranteed) must not tag GARAN; bare "garanti" is not an alias.
    assert match_banks("Garantili mevduat ürünlerine ilgi arttı") == {}
    assert match_banks("Devlet garantisi kapsamı genişledi") == {}


def test_teb_vs_teblig():
    assert match_banks("BDDK yeni tebliğ yayımladı") == {}
    assert match_banks("TEB'den KOBİ'lere yeni destek paketi") == {"TEB": "title"}


def test_ing_vs_ingiltere():
    assert match_banks("İngiltere Merkez Bankası faiz kararını açıkladı") == {}
    assert match_banks("ING'den konut kredisi faiz indirimi") == {"ING": "title"}


def test_aktif_vs_aktif_buyume():
    # "aktif" = assets/active; only the bank's actual names may tag AKTIF.
    assert match_banks("Bankacılık sektörünün aktif büyüklüğü arttı") == {}
    assert match_banks("Sektörde aktif bankacılık modeli tartışılıyor") == {}
    assert "AKTIF" in match_banks("Aktifbank'tan yeni dijital ürün")
    assert "AKTIF" in match_banks("Aktif Bank'ın tahvil ihracı tamamlandı")


def test_emlak_vs_emlak_piyasasi():
    assert match_banks("Emlak piyasasında hareketlilik sürüyor") == {}
    assert match_banks("Emlak Katılım'dan sukuk ihracı") == {"EMLAK": "title"}


def test_katilim_banks_not_confused_with_parents():
    assert match_banks("Ziraat Katılım kâr payı oranlarını güncelledi") == {
        "ZIRAATK": "title"
    }
    assert match_banks("Vakıf Katılım'dan yeni şube açılışı") == {"VAKIFK": "title"}
    # ...and the deposit-bank parents still match their own names.
    assert match_banks("Ziraat Bankası tarım kredilerini artırdı") == {
        "ZIRAAT": "title"
    }
    assert "VAKBN" in match_banks("VakıfBank sendikasyon kredisini yeniledi")


def test_yapi_kredi_vs_yapi_kredisi():
    # "yapı kredisi" (construction loan) must not tag YKBNK.
    assert match_banks("Konut için yapı kredisi başvuruları arttı") == {}
    assert "YKBNK" in match_banks("Yapı Kredi'nin net kârı beklentileri aştı")


def test_turkiye_finans_vs_finansal():
    assert match_banks("Türkiye finansal istikrar raporu yayımlandı") == {}
    assert "TFKB" in match_banks("Türkiye Finans'tan katılım hesabı kampanyası")


def test_multi_bank_headline_tags_all():
    got = match_banks("Akbank ve Yapı Kredi'den ortak sendikasyon kredisi")
    assert got == {"AKBNK": "title", "YKBNK": "title"}


def test_title_outranks_summary():
    got = match_banks(
        "Garanti BBVA yeni genel müdürünü atadı",
        "Halkbank da yönetim değişikliğine gitti",
    )
    assert got == {"GARAN": "title", "HALKB": "summary"}


def test_none_inputs():
    assert match_banks(None, None) == {}


# ------------------------------------------------------------------- aliases

def test_alias_file_keys_match_canonical_bank_universe():
    kap_map = json.loads(
        (REPO_ROOT / "data" / "banks" / "kap_company_map.json").read_text(
            encoding="utf-8"
        )
    )
    assert set(load_aliases().keys()) == set(kap_map["banks"].keys())


def test_default_aliases_in_sync_with_json():
    # DEFAULT_ALIASES is the hand-maintained fallback (press.py convention).
    assert load_aliases() == DEFAULT_ALIASES


# ----------------------------------------------------------------- retag_all

def _mem_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    return conn


def _insert_item(conn, source, ext_id, title, summary=None):
    conn.execute(
        "INSERT OR REPLACE INTO news_items"
        " (source, external_id, published_at, title, summary, url, language)"
        " VALUES (?, ?, '2026-07-01T00:00:00+00:00', ?, ?, 'https://x', 'tr')",
        (source, ext_id, title, summary),
    )


def test_retag_all_tags_and_is_idempotent():
    conn = _mem_db()
    _insert_item(conn, "press", "a1", "Akbank'tan yeni kredi paketi")
    _insert_item(conn, "google_news", "g1", "Piyasalar güne yatay başladı",
                 "Halkbank hisseleri yükseldi")
    _insert_item(conn, "kap", "k1", "Akbank finansal rapor")  # kap: never tagged

    stats = retag_all(conn)
    assert stats["added"] == 2 and stats["removed"] == 0
    rows = conn.execute(
        "SELECT source, external_id, ticker, matched_in FROM news_item_banks"
        " ORDER BY source"
    ).fetchall()
    assert rows == [
        ("google_news", "g1", "HALKB", "summary"),
        ("press", "a1", "AKBNK", "title"),
    ]

    # Second run: nothing changes, nothing rewritten (no fetched_at churn).
    stats2 = retag_all(conn)
    assert stats2["added"] == 0 and stats2["removed"] == 0


def test_retag_all_removes_stale_tags_via_outbox():
    conn = _mem_db()
    _insert_item(conn, "press", "a1", "Akbank'tan yeni kredi paketi")
    retag_all(conn)

    # The item disappears (e.g. its outlet was removed from press_feeds.json).
    conn.execute("DELETE FROM news_items WHERE source='press' AND external_id='a1'")
    stats = retag_all(conn)
    assert stats["removed"] == 1
    assert conn.execute("SELECT COUNT(*) FROM news_item_banks").fetchone()[0] == 0
    outbox = [r[0] for r in conn.execute("SELECT sql FROM d1_pending_deletes")]
    assert outbox == [
        "DELETE FROM news_item_banks WHERE source='press'"
        " AND external_id='a1' AND ticker='AKBNK';"
    ]
