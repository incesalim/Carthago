-- 0022_banks_dimension_new_entrants
-- Add the six newly-onboarded banks to the canonical `banks` dimension.
--
-- WHY: the per-bank audit universe expands from 31 to 37. These six are the
-- recently-licensed digital / new-entrant banks that publish standard text-based
-- BRSA quarterly reports (verified 2026-07-11) and are being wired into the audit
-- lane (data/banks/audit_report_urls.json). Mirror rows here + in
-- web/app/lib/bank_names.ts keep the cross-lane identity in lockstep, per the
-- rule in 0021_banks_dimension.sql. Feasibility + rationale:
-- docs/knowledge/new-banks-coverage-gap-2026-07-11.md.
--
-- Classification notes (bank_category = colloquial BDDK category as in
-- bddk_bank_list.json; the ownership aggregate code lives in bank_names.ts
-- BANK_TYPE_BY_TICKER, and can diverge — e.g. a Turkish-incorporated
-- foreign-owned bank is 'Özel Mevduat' here but 10007 there, matching QNBFB):
--   ENPARA  — QNB (Qatar) owned digital deposit bank      -> 'Özel Mevduat', 10007 (foreign)
--   COLENDI — domestic-private digital deposit bank        -> 'Özel Mevduat', 10005 (private)
--   ZIRAATD — Ziraat (state) owned digital deposit bank    -> 'Kamu Mevduat', 10006 (state)
--   DUNYAK/HAYATK/TOMK — participation banks               -> 'Katılım',      10003
--
-- Idempotent: INSERT OR REPLACE, so re-applying is a no-op.

INSERT OR REPLACE INTO banks (ticker, name, name_tr, bank_category, is_participation, is_listed, bist_symbol) VALUES
  ('COLENDI', 'Colendi Bank',   'COLENDİ BANK A.Ş.',                  'Özel Mevduat', 0, 0, NULL),
  ('DUNYAK',  'Dünya Katılım',  'DÜNYA KATILIM BANKASI A.Ş.',         'Katılım',      1, 0, NULL),
  ('ENPARA',  'Enpara Bank',    'ENPARA BANK A.Ş.',                   'Özel Mevduat', 0, 0, NULL),
  ('HAYATK',  'Hayat Finans',   'HAYAT FİNANS KATILIM BANKASI A.Ş.',  'Katılım',      1, 0, NULL),
  ('TOMK',    'T.O.M. Katılım', 'T.O.M. KATILIM BANKASI A.Ş.',        'Katılım',      1, 0, NULL),
  ('ZIRAATD', 'Ziraat Dinamik', 'ZİRAAT DİNAMİK BANKA A.Ş.',          'Kamu Mevduat', 0, 0, NULL);
