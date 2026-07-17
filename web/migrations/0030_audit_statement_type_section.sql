-- Give the statement-type registry its report provenance.
-- Mirrored in src/audit_reports/schema.py; rows come from registry.web_metadata()
-- via scripts/sync_audit_expected.py (full DELETE + INSERT each run).
--
-- Why: the /admin coverage matrix grouped its lanes on `is_core` and headed the
-- false group "Footnotes & S4". is_core is a SEVERITY flag -- "an empty lane here
-- means the extraction failed, fail the whole report" -- true for exactly three
-- lanes (BS assets, BS liabilities, P&L). OCI, changes-in-equity, cash-flow and
-- off-balance are is_core=0 so that one unreadable note-page can't discard a good
-- BS+P&L extraction, but they are Bolum 2 PRIMARY STATEMENTS: TAS 1 requires the
-- first three in any complete set, and off-balance ("Nazim Hesaplar Tablosu")
-- prints on the balance-sheet page. The matrix was calling four primary
-- statements footnotes. `section` carries the provenance so is_core can go back
-- to doing its one real job.
--
-- section holds the BARE Bolum number ('1'/'2'/'4'/'5'/'7'); the section sign is
-- typography and lives in the view. section_rank is registry.SECTION_ORDER's
-- position -- the display order (primary statements lead), NOT the filing's own
-- 1->7 order, which would open the matrix on branches/personnel.

ALTER TABLE bank_audit_statement_types ADD COLUMN section TEXT NOT NULL DEFAULT '';
ALTER TABLE bank_audit_statement_types ADD COLUMN section_rank INTEGER NOT NULL DEFAULT 99;

-- Backfill the live rows. sync_audit_expected.py rebuilds this table wholesale
-- from the registry and would set the same values -- but it runs in the audit
-- workflows, not on deploy, so without this the matrix renders every lane under
-- one blank heading until the next audit refresh. Re-running is a no-op.
UPDATE bank_audit_statement_types SET section = '2', section_rank = 0
 WHERE key IN ('balance_sheet_assets', 'balance_sheet_liabilities', 'profit_loss',
               'other_comprehensive_income', 'equity_change', 'cash_flow', 'off_balance');
UPDATE bank_audit_statement_types SET section = '5', section_rank = 1
 WHERE key IN ('credit_quality', 'stages', 'loans_by_sector', 'npl_movement',
               'free_provision');
UPDATE bank_audit_statement_types SET section = '4', section_rank = 2
 WHERE key IN ('capital', 'liquidity', 'fx_position', 'repricing');
UPDATE bank_audit_statement_types SET section = '1', section_rank = 3 WHERE key = 'profile';
UPDATE bank_audit_statement_types SET section = '7', section_rank = 4 WHERE key = 'audit_opinion';
