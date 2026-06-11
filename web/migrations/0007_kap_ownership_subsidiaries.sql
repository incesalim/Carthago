-- Subsidiary rows (KAP Genel Bilgi Formu §7 "Bağlı Ortaklıklar, Finansal
-- Duran Varlıklar ile Finansal Yatırımlar") join kap_ownership as
-- item='subsidiary'. Their amounts are filed in a per-row currency
-- (TRY/EUR/USD), and they carry activity + relation-type text.
ALTER TABLE kap_ownership ADD COLUMN currency TEXT;
ALTER TABLE kap_ownership ADD COLUMN activity TEXT;
ALTER TABLE kap_ownership ADD COLUMN relation TEXT;
