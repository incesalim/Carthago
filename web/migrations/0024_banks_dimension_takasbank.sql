-- 0024_banks_dimension_takasbank
-- Add Takasbank to the canonical `banks` dimension (universe 37 -> 38).
--
-- WHY: İstanbul Takas ve Saklama Bankası A.Ş. is on BDDK's licensed-bank list as a
-- development-and-investment bank, but was missing from our registry entirely
-- (data/banks/bddk_bank_list.json listed 20 dev/inv banks while its own summary
-- claimed 21 — Takasbank was the gap). It files standard quarterly BRSA reports
-- (BdrUyg institution code 132, SOLO only, 2022Q1->2026Q1), so it is now carried in
-- the audit lane like any other bank.
--
-- IMPORTANT — carried, but NOT a peer. Takasbank is Turkey's central securities
-- settlement / clearing (CCP) and custody institution, i.e. market infrastructure
-- rather than a lender: at 2026Q1 it reports ZERO deposits, customer loans ~2.5% of
-- assets, and ~94% of the balance sheet in cash + placements (member cash and
-- collateral it merely custodies), plus ~178bn TL of off-balance CCP guarantees.
-- It is therefore EXCLUDED from peer ranking, the market-share league and the sector
-- HHI (`PEER_EXCLUDED_TICKERS` in web/app/lib/bank_names.ts, enforced in heatmap.ts
-- and market-share.ts). Its own /banks/TAKAS page still shows balance sheet, capital
-- and liquidity, which ARE meaningful.
--
-- Idempotent: INSERT OR REPLACE, so re-applying is a no-op.

INSERT OR REPLACE INTO banks (ticker, name, name_tr, bank_category, is_participation, is_listed, bist_symbol) VALUES
  ('TAKAS', 'Takasbank', 'İSTANBUL TAKAS VE SAKLAMA BANKASI A.Ş.', 'Kalkınma ve Yatırım', 0, 0, NULL);
