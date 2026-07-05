-- 0021_banks_dimension
-- Canonical per-bank dimension table + cross-lane identifier alias views.
--
-- WHY: the bank identifier is spelled three ways across the fact tables —
-- `bank_ticker` (the bank_audit_* / kap_ownership / faaliyet_* lanes),
-- `ticker` (news_items, bank_earnings, news_item_banks), and `symbol`
-- (bist_prices/dividends/shares). The VALUES match (GARAN == GARAN), but there
-- was no single table to join against and no in-D1 source of truth for a bank's
-- name / category / listed status — that lived only in app code
-- (web/app/lib/bank_names.ts) and a committed JSON (data/banks/bddk_bank_list.json).
--
-- This migration adds `banks` as that single source of truth (the audited-bank
-- universe = the 31 tickers used as bank_ticker across the audit lanes), seeded
-- from bddk_bank_list.json + bank_names.ts, and three additive VIEWs that expose
-- a uniform `bank_ticker` column over the differently-named lanes so cross-lane
-- queries (and the Telegram text-to-SQL bot) can join on one name.
--
-- Slowly-changing reference data: seeded here, not synced by push_to_d1.py.
-- When a bank is added to the audit pipeline, mirror it here AND in bank_names.ts
-- (add a follow-up migration to upsert the row). Idempotent: CREATE ... IF NOT
-- EXISTS + INSERT OR REPLACE, so re-applying against a fresh DB is a no-op.

CREATE TABLE IF NOT EXISTS banks (
    ticker          TEXT PRIMARY KEY,     -- internal code == bank_ticker / ticker across all lanes
    name            TEXT NOT NULL,        -- friendly English name (mirrors bank_names.ts)
    name_tr         TEXT NOT NULL,        -- BDDK legal name (bddk_bank_list.json)
    bank_category   TEXT NOT NULL,        -- verbatim BDDK category: 'Özel Mevduat' | 'Kamu Mevduat'
                                          --   | 'Yabancı Mevduat' | 'Katılım' | 'Kalkınma ve Yatırım'
    is_participation INTEGER NOT NULL DEFAULT 0,  -- 1 for Katılım (interest-free) banks
    is_listed       INTEGER NOT NULL DEFAULT 0,   -- 1 if BIST-listed (per bddk_bank_list.json)
    bist_symbol     TEXT                  -- BIST ticker for the bist_* lanes; NULL if unlisted
);

CREATE INDEX IF NOT EXISTS idx_banks_bist_symbol ON banks(bist_symbol);

-- Seed: the 31-bank audited universe (bank_ticker values used across bank_audit_*).
INSERT OR REPLACE INTO banks (ticker, name, name_tr, bank_category, is_participation, is_listed, bist_symbol) VALUES
  ('AKBNK',   'Akbank',                  'AKBANK T.A.Ş.',                              'Özel Mevduat',        0, 1, 'AKBNK'),
  ('AKTIF',   'Aktif Yatırım Bankası',   'AKTİF YATIRIM BANKASI A.Ş.',                 'Kalkınma ve Yatırım', 0, 0, NULL),
  ('ALBRK',   'Albaraka Türk',           'ALBARAKA TÜRK KATILIM BANKASI A.Ş.',         'Katılım',             1, 1, 'ALBRK'),
  ('ALNTF',   'Alternatifbank',          'ALTERNATİFBANK A.Ş.',                        'Özel Mevduat',        0, 0, NULL),
  ('ANADOLU', 'Anadolubank',             'ANADOLUBANK A.Ş.',                           'Özel Mevduat',        0, 0, NULL),
  ('ATBANK',  'Arap Türk Bankası',       'ARAP TÜRK BANKASI A.Ş.',                     'Özel Mevduat',        0, 0, NULL),
  ('BURGAN',  'Burgan Bank',             'BURGAN BANK A.Ş.',                           'Özel Mevduat',        0, 0, NULL),
  ('DENIZ',   'Denizbank',               'DENİZBANK A.Ş.',                             'Özel Mevduat',        0, 0, NULL),
  ('EMLAK',   'Emlak Katılım',           'TÜRKİYE EMLAK KATILIM BANKASI A.Ş.',         'Katılım',             1, 0, NULL),
  ('EXIM',    'Türk Eximbank',           'TÜRKİYE İHRACAT KREDİ BANKASI A.Ş.',         'Kalkınma ve Yatırım', 0, 0, NULL),
  ('FIBA',    'Fibabanka',               'FİBABANKA A.Ş.',                             'Özel Mevduat',        0, 0, NULL),
  ('GARAN',   'Garanti BBVA',            'TÜRKİYE GARANTİ BANKASI A.Ş.',               'Özel Mevduat',        0, 1, 'GARAN'),
  ('HALKB',   'Halkbank',                'TÜRKİYE HALK BANKASI A.Ş.',                  'Kamu Mevduat',        0, 1, 'HALKB'),
  ('HSBC',    'HSBC Türkiye',            'HSBC BANK A.Ş.',                             'Yabancı Mevduat',     0, 0, NULL),
  ('ICBCT',   'ICBC Turkey',             'ICBC TURKEY BANK A.Ş.',                      'Yabancı Mevduat',     0, 1, 'ICBCT'),
  ('ING',     'ING Türkiye',            'ING BANK A.Ş.',                              'Yabancı Mevduat',     0, 0, NULL),
  ('ISCTR',   'İş Bankası',              'TÜRKİYE İŞ BANKASI A.Ş.',                    'Kamu Mevduat',        0, 1, 'ISCTR'),
  ('KLNMA',   'Kalkınma ve Yatırım Bk.', 'TÜRKİYE KALKINMA VE YATIRIM BANKASI A.Ş.',   'Kalkınma ve Yatırım', 0, 1, 'KLNMA'),
  ('KUVEYT',  'Kuveyt Türk',             'KUVEYT TÜRK KATILIM BANKASI A.Ş.',           'Katılım',             1, 0, NULL),
  ('ODEA',    'Odea Bank',               'ODEA BANK A.Ş.',                             'Özel Mevduat',        0, 0, NULL),
  ('PASHA',   'Pasha Yatırım',           'PASHA YATIRIM BANKASI A.Ş.',                 'Kalkınma ve Yatırım', 0, 0, NULL),
  ('QNBFB',   'QNB',                     'QNB BANK A.Ş.',                              'Özel Mevduat',        0, 1, 'QNBFB'),
  ('SKBNK',   'Şekerbank',               'ŞEKERBANK T.A.Ş.',                           'Özel Mevduat',        0, 1, 'SKBNK'),
  ('TEB',     'TEB',                     'TÜRK EKONOMİ BANKASI A.Ş.',                  'Özel Mevduat',        0, 0, NULL),
  ('TFKB',    'Türkiye Finans',          'TÜRKİYE FİNANS KATILIM BANKASI A.Ş.',        'Katılım',             1, 0, NULL),
  ('TSKB',    'TSKB',                    'TÜRKİYE SINAİ KALKINMA BANKASI A.Ş.',        'Kalkınma ve Yatırım', 0, 1, 'TSKB'),
  ('VAKBN',   'VakıfBank',               'TÜRKİYE VAKIFLAR BANKASI T.A.O.',            'Kamu Mevduat',        0, 1, 'VAKBN'),
  ('VAKIFK',  'Vakıf Katılım',           'VAKIF KATILIM BANKASI A.Ş.',                 'Katılım',             1, 0, NULL),
  ('YKBNK',   'Yapı Kredi',              'YAPI VE KREDİ BANKASI A.Ş.',                 'Özel Mevduat',        0, 1, 'YKBNK'),
  ('ZIRAAT',  'Ziraat Bankası',          'T.C. ZİRAAT BANKASI A.Ş.',                   'Kamu Mevduat',        0, 0, NULL),
  ('ZIRAATK', 'Ziraat Katılım',          'ZİRAAT KATILIM BANKASI A.Ş.',                'Katılım',             1, 0, NULL);

-- ===== cross-lane identifier alias views =====
-- Expose a uniform `bank_ticker` column over the lanes that spell it differently,
-- so a query can JOIN banks b ON b.ticker = v.bank_ticker regardless of source.

-- bist_prices.symbol carries BOTH bank tickers and index codes (XU100/XBANK);
-- this view is the bank-only slice, aliased to bank_ticker.
CREATE VIEW IF NOT EXISTS v_bist_prices AS
  SELECT symbol AS bank_ticker, period_date, open_price, high_price, low_price,
         close_price, volume, label, downloaded_at
  FROM bist_prices
  WHERE kind = 'bank';

-- news_items.ticker -> bank_ticker (KAP disclosures carry the single owning bank;
-- press/google multi-bank tags live in news_item_banks, which already uses `ticker`).
CREATE VIEW IF NOT EXISTS v_news_items AS
  SELECT source, external_id, published_at, ticker AS bank_ticker, category,
         title, summary, url, language, fetched_at
  FROM news_items
  WHERE ticker IS NOT NULL;

-- bank_earnings.ticker -> bank_ticker.
CREATE VIEW IF NOT EXISTS v_bank_earnings AS
  SELECT source, external_id, ticker AS bank_ticker, period, kind, event_date,
         title, url, language, fetched_at
  FROM bank_earnings;
