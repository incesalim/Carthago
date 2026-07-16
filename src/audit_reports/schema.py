"""SQLite schema for per-bank quarterly BRSA audit-report data.

Three tables coexist with the existing BDDK aggregate tables in data/bddk_data.db:

  bank_audit_balance_sheet  — Assets, Liabilities, Off-Balance (6-column format)
  bank_audit_profit_loss    — P&L line items (single amount column)
  bank_audit_extractions    — One row per (bank, period, kind) extraction run
"""
from __future__ import annotations

import sqlite3

DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_balance_sheet (
    bank_ticker TEXT NOT NULL,
    period      TEXT NOT NULL,
    kind        TEXT NOT NULL,
    statement   TEXT NOT NULL,           -- 'assets' | 'liabilities' | 'off_balance'
    item_order  INTEGER NOT NULL,
    hierarchy   TEXT,
    item_name   TEXT NOT NULL,
    footnote    TEXT,
    amount_tl    REAL,
    amount_fc    REAL,
    amount_total REAL,
    PRIMARY KEY (bank_ticker, period, kind, statement, item_order)
);

CREATE INDEX IF NOT EXISTS idx_bank_bs_bank_period
  ON bank_audit_balance_sheet(bank_ticker, period);

CREATE INDEX IF NOT EXISTS idx_bank_bs_item_name
  ON bank_audit_balance_sheet(item_name);


CREATE TABLE IF NOT EXISTS bank_audit_profit_loss (
    bank_ticker TEXT NOT NULL,
    period      TEXT NOT NULL,
    kind        TEXT NOT NULL,
    item_order  INTEGER NOT NULL,
    hierarchy   TEXT,
    item_name   TEXT NOT NULL,
    footnote    TEXT,
    amount      REAL,
    PRIMARY KEY (bank_ticker, period, kind, item_order)
);

CREATE INDEX IF NOT EXISTS idx_bank_pl_bank_period
  ON bank_audit_profit_loss(bank_ticker, period);

CREATE INDEX IF NOT EXISTS idx_bank_pl_item_name
  ON bank_audit_profit_loss(item_name);


CREATE TABLE IF NOT EXISTS bank_audit_oci (
    bank_ticker TEXT NOT NULL,
    period      TEXT NOT NULL,
    kind        TEXT NOT NULL,
    item_order  INTEGER NOT NULL,
    hierarchy   TEXT,
    item_name   TEXT NOT NULL,
    footnote    TEXT,
    amount      REAL,
    PRIMARY KEY (bank_ticker, period, kind, item_order)
);

CREATE INDEX IF NOT EXISTS idx_bank_oci_bank_period
  ON bank_audit_oci(bank_ticker, period);


-- Cash flow statement — single-column format like P&L/OCI (current period only).
-- Hierarchy: A./B./C. section headers (no values, not stored); numerics
-- 1.1…1.2.10, 2.x, 3.x; romans I.–VII. Follows the equity-change pages.
CREATE TABLE IF NOT EXISTS bank_audit_cash_flow (
    bank_ticker TEXT NOT NULL,
    period      TEXT NOT NULL,
    kind        TEXT NOT NULL,
    item_order  INTEGER NOT NULL,
    hierarchy   TEXT,
    item_name   TEXT NOT NULL,
    footnote    TEXT,
    amount      REAL,
    PRIMARY KEY (bank_ticker, period, kind, item_order)
);

CREATE INDEX IF NOT EXISTS idx_bank_cf_bank_period
  ON bank_audit_cash_flow(bank_ticker, period);


-- Statement of changes in equity — wide BRSA template.
-- 14 value columns (unconsolidated) or 16 (consolidated: +minority +grand total).
-- Two pages per report: period_type 'current' | 'prior'. Amounts in thousand TRY.
-- Column mapping is positional by modal token count clamped to {14, 16};
-- every accepted row satisfies total_equity ≈ Σ(13 components).
CREATE TABLE IF NOT EXISTS bank_audit_equity_change (
    bank_ticker                TEXT NOT NULL,
    period                     TEXT NOT NULL,
    kind                       TEXT NOT NULL,
    period_type                TEXT NOT NULL,
    item_order                 INTEGER NOT NULL,
    hierarchy                  TEXT,
    item_name                  TEXT NOT NULL,
    paid_in_capital            REAL,
    share_premium              REAL,
    share_cancellation_profits REAL,
    other_capital_reserves     REAL,
    oci_not_reclassified_1     REAL,
    oci_not_reclassified_2     REAL,
    oci_not_reclassified_3     REAL,
    oci_reclassified_1         REAL,
    oci_reclassified_2         REAL,
    oci_reclassified_3         REAL,
    profit_reserves            REAL,
    prior_period_profit_loss   REAL,
    period_net_profit_loss     REAL,
    total_equity               REAL,
    minority_interest          REAL,
    total_equity_incl_minority REAL,
    source_page                INTEGER,
    extracted_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind, period_type, item_order)
);

CREATE INDEX IF NOT EXISTS idx_bank_eq_bank_period
  ON bank_audit_equity_change(bank_ticker, period);


CREATE TABLE IF NOT EXISTS bank_audit_extractions (
    bank_ticker          TEXT NOT NULL,
    period               TEXT NOT NULL,
    kind                 TEXT NOT NULL,
    pdf_path             TEXT NOT NULL,
    extracted_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    rows_bs_assets       INTEGER,
    rows_bs_liabilities  INTEGER,
    rows_off_balance     INTEGER,
    rows_profit_loss     INTEGER,
    rows_credit_quality  INTEGER,
    rows_oci             INTEGER,
    success              INTEGER NOT NULL DEFAULT 1,
    note                 TEXT,
    PRIMARY KEY (bank_ticker, period, kind)
);


-- IFRS 9 staging extracts: every Stage 1/2/3/Total movement table found in
-- the audit-report footnotes, plus the GARAN-style stage-amount summary.
-- One row per (bank, period, kind, section, period_type).
--
-- `section` taxonomy (best-effort label from the heading above the table):
--   loans_ecl              — Expected credit loss provisions for loans
--   loans_amounts          — Actual loan balances by stage (TL+FC sum)
--   cash_ecl               — ECL for cash & cash equivalents
--   amortised_cost_ecl     — ECL for financial assets at amortized cost
--   non_cash_ecl           — ECL for non-cash loans / commitments / guarantees
--   other_ecl              — Any other Stage 1/2/3 movement table we can't classify
--
-- `period_type` distinguishes "Current Period" tables from "Prior Period"
-- comparatives that often sit immediately below in the same footnote.
CREATE TABLE IF NOT EXISTS bank_audit_credit_quality (
    bank_ticker      TEXT NOT NULL,
    period           TEXT NOT NULL,
    kind             TEXT NOT NULL,
    section          TEXT NOT NULL,
    period_type      TEXT NOT NULL,           -- 'current' | 'prior'
    source_page      INTEGER,
    -- stage1/2/3_amount are POSITIONAL columns whose meaning is SECTION-DEPENDENT:
    --   most sections  -> IFRS-9 Stage 1 / 2 / 3
    --   npl_brsa_*     -> BRSA NPL groups III / IV / V (substandard/doubtful/loss),
    --                     all sub-buckets of IFRS Stage 3. The Stage-3 figure for
    --                     these is total_amount (=III+IV+V), NEVER stage1_amount.
    -- See src/audit_reports/credit_quality.py NPL_GROUP_SECTIONS.
    stage1_amount    REAL,
    stage2_amount    REAL,
    stage3_amount    REAL,
    total_amount     REAL,
    heading_snippet  TEXT,                    -- raw heading we matched on, for debug
    extracted_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind, section, period_type)
);

CREATE INDEX IF NOT EXISTS idx_bank_cq_bank_period
  ON bank_audit_credit_quality(bank_ticker, period);

CREATE INDEX IF NOT EXISTS idx_bank_cq_section
  ON bank_audit_credit_quality(section);


-- Bank-profile metadata extracted from the qualitative section of the
-- audit report: branch counts (domestic / foreign / total) and personnel.
-- One row per (bank, period, kind). Any field may be NULL if the bank's
-- report didn't disclose it in a recognized format.
CREATE TABLE IF NOT EXISTS bank_audit_profile (
    bank_ticker        TEXT NOT NULL,
    period             TEXT NOT NULL,
    kind               TEXT NOT NULL,
    branches_domestic  INTEGER,
    branches_foreign   INTEGER,
    branches_total     INTEGER,
    personnel          INTEGER,
    extracted_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind)
);


-- Independent auditor's verdict, classified from the auditor's report at the
-- front of every BRSA filing (src/audit_reports/audit_opinion.py). One row per
-- (bank, period, kind).
--   opinion_type  'clean' | 'qualified' | 'adverse' | 'disclaimer' | 'unknown'
--   is_modified   1 when opinion_type is qualified/adverse/disclaimer (the flag)
--   report_kind   'audit'  (annual, full opinion) | 'review' (interim, limited)
--   basis_text    the "Basis for Qualified/Adverse …" paragraph (NULL if clean)
-- 'unknown' rows are never written (skip-if-empty), so a failed re-extract can't
-- overwrite a previously-captured verdict — same rule as bank_audit_profile.
CREATE TABLE IF NOT EXISTS bank_audit_opinion (
    bank_ticker   TEXT NOT NULL,
    period        TEXT NOT NULL,
    kind          TEXT NOT NULL,
    opinion_type  TEXT NOT NULL,
    is_modified   INTEGER NOT NULL DEFAULT 0,
    report_kind   TEXT,
    basis_text    TEXT,
    auditor       TEXT,
    language      TEXT,
    source_page   INTEGER,
    extracted_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind)
);

CREATE INDEX IF NOT EXISTS idx_bank_opinion_modified
  ON bank_audit_opinion(is_modified);


-- Free provision (serbest karşılık) — the discretionary "rainy-day" reserve a
-- bank sets aside OUTSIDE the BRSA provisioning rules. Auditors qualify over it
-- (see bank_audit_opinion); releasing it inflates profit — the mechanism behind
-- the ALBRK Q1-2025 case. Held nowhere before; lives only in the "Other
-- provisions" liability note, in several prose/table forms. Classified by
-- src/audit_reports/free_provision.py (deterministic, fitz-only).
--   free_provision       current-period STOCK, thousand TL; 0 = bank holds none
--   free_provision_prior prior-period (Dec 31) stock from the note's parenthetical
--                        comparison — best-effort, may be NULL
--   source_text          the matched sentence, for verification
-- One row per (bank, period, kind). Only DISCLOSED rows are written (a row with
-- free_provision=0 means the bank explicitly disclosed "none"; a MISSING row
-- means no disclosure was found) — so a failed re-extract can't wipe a value.
CREATE TABLE IF NOT EXISTS bank_audit_free_provision (
    bank_ticker          TEXT NOT NULL,
    period               TEXT NOT NULL,
    kind                 TEXT NOT NULL,
    free_provision       REAL,
    free_provision_prior REAL,
    source_page          INTEGER,
    source_text          TEXT,
    extracted_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind)
);

CREATE INDEX IF NOT EXISTS idx_bank_freeprov_bank_period
  ON bank_audit_free_provision(bank_ticker, period);


-- Sector-level loan exposure with TFRS 9 stage breakdown. Sourced from
-- the "Information by major sectors and type of counterparties" /
-- "Önemli Sektörlere veya Karşı Taraf Türüne Göre" footnote table.
--
-- One row per (bank, period, kind, sector, period_type). The `sector`
-- key is a canonical short code mapped from bilingual labels:
--   agri_total, agri_farming, agri_forestry, agri_fishery,
--   mfg_total, mfg_mining, mfg_production, mfg_utilities,
--   construction,
--   svc_total, svc_trade, svc_hospitality, svc_transport,
--   svc_financial, svc_realestate, svc_professional,
--   svc_education, svc_health,
--   other, total.
--
-- *_total keys are the group parent (sum of sub-sectors). `total` is the
-- grand total across all groups.
CREATE TABLE IF NOT EXISTS bank_audit_loans_by_sector (
    bank_ticker      TEXT NOT NULL,
    period           TEXT NOT NULL,
    kind             TEXT NOT NULL,
    sector           TEXT NOT NULL,
    period_type      TEXT NOT NULL,           -- 'current' | 'prior'
    source_page      INTEGER,
    stage2_amount    REAL,                    -- loans with significant increase in credit risk
    stage3_amount    REAL,                    -- defaulted / impaired loans (sector NPL gross)
    ecl_amount       REAL,                    -- expected credit loss provisions
    raw_label        TEXT,                    -- original row label, for debug
    extracted_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind, sector, period_type)
);

CREATE INDEX IF NOT EXISTS idx_bank_lbs_bank_period
  ON bank_audit_loans_by_sector(bank_ticker, period);

CREATE INDEX IF NOT EXISTS idx_bank_lbs_sector
  ON bank_audit_loans_by_sector(sector);


-- NPL gross-amount roll-forward by BRSA severity group (III / IV / V).
-- Sourced from the "Information on the movement of non-performing loans"
-- / "Toplam donuk alacak hareketlerine ilişkin bilgiler" footnote.
--
-- For each (bank, period, kind, group_code, period_type) row:
--   opening_balance     prior-period-end NPL balance
--   additions           new NPL inflows during the period
--   transfers_in        loans migrating INTO this group from another NPL group
--   transfers_out       loans migrating OUT of this group to another NPL group
--   collections         recoveries during the period
--   write_offs          write-downs against the balance sheet
--   sold                NPL portfolio sales
--   fx_diff             FX revaluation (rare; GARAN-style banks only)
--   closing_balance     period-end NPL balance
--   provision           cumulative loss provision against the group
--   net_balance         closing_balance − provision (carrying amount)
CREATE TABLE IF NOT EXISTS bank_audit_npl_movement (
    bank_ticker        TEXT NOT NULL,
    period             TEXT NOT NULL,
    kind               TEXT NOT NULL,
    group_code         TEXT NOT NULL,         -- 'III' | 'IV' | 'V'
    period_type        TEXT NOT NULL,         -- 'current' | 'prior'
    source_page        INTEGER,
    opening_balance    REAL,
    additions          REAL,
    transfers_in       REAL,
    transfers_out      REAL,
    collections        REAL,
    write_offs         REAL,
    sold               REAL,
    fx_diff            REAL,
    closing_balance    REAL,
    provision          REAL,
    net_balance        REAL,
    extracted_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind, group_code, period_type)
);

CREATE INDEX IF NOT EXISTS idx_bank_npl_bank_period
  ON bank_audit_npl_movement(bank_ticker, period);


-- Consolidated TFRS 9 stage view per (bank, period, kind, period_type).
-- Derived from bank_audit_credit_quality by combining the four sources
-- that publish Stage 1/2/3 figures:
--   amounts:
--     1st choice  bank_audit_credit_quality.section='loans_amounts'
--                 (single row holds S1/S2/S3 inline — AKBNK-style banks)
--     2nd choice  section='loans_by_stage' for S1+S2 +
--                 section='npl_brsa_gross'.total_amount for S3
--   provisions:
--     1st choice  section='loans_ecl'      (full S1/S2/S3)
--     2nd choice  section='loans_ecl_brsa' for S1+S2 +
--                 section='npl_brsa_provision'.total_amount for S3
--
-- Coverage ratio = ecl / amount per stage. Stored as REAL fractions
-- (0.0083 = 0.83%) so the consumer chooses formatting.
--
-- Populated by scripts/build_bank_audit_stages.py — re-run whenever
-- credit_quality data changes.
CREATE TABLE IF NOT EXISTS bank_audit_stages (
    bank_ticker      TEXT NOT NULL,
    period           TEXT NOT NULL,
    kind             TEXT NOT NULL,
    period_type      TEXT NOT NULL,           -- 'current' | 'prior'
    stage1_amount    REAL,
    stage2_amount    REAL,
    stage3_amount    REAL,
    total_amount     REAL,                    -- stage1 + stage2 + stage3
    stage1_ecl       REAL,
    stage2_ecl       REAL,
    stage3_ecl       REAL,
    total_ecl        REAL,                    -- stage1 + stage2 + stage3 ECL
    stage1_coverage  REAL,                    -- stage1_ecl / stage1_amount
    stage2_coverage  REAL,
    stage3_coverage  REAL,
    extracted_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind, period_type)
);

CREATE INDEX IF NOT EXISTS idx_bank_stages_bank_period
  ON bank_audit_stages(bank_ticker, period);


-- ===========================================================================
-- §4 (Risk Management) tables — deterministic pdfplumber extraction, same lane
-- as bank_audit_loans_by_sector / bank_audit_npl_movement. `period_type`
-- distinguishes the report's Current-Period column from the Prior-Period
-- comparative. Arithmetic sanity (CET1<=Tier1<=Total, CAR=capital/RWA, LCR/NSFR
-- bands) is checked downstream in scripts/check_audit_quality.py.
-- ===========================================================================

-- Capital adequacy (BRSA §4.1 "Total capital" + "Capital adequacy ratios").
-- Amounts in thousand TRY (report native unit); ratios as percent (14.23 = 14.23%).
CREATE TABLE IF NOT EXISTS bank_audit_capital (
    bank_ticker              TEXT NOT NULL,
    period                   TEXT NOT NULL,
    kind                     TEXT NOT NULL,
    period_type              TEXT NOT NULL,        -- 'current' | 'prior'
    cet1_capital             REAL,                 -- Common Equity Tier 1 capital
    additional_tier1_capital REAL,
    tier1_capital            REAL,
    tier2_capital            REAL,
    total_capital            REAL,                 -- own funds (Tier 1 + Tier 2)
    total_rwa                REAL,                 -- total risk-weighted assets
    cet1_ratio               REAL,                 -- percent
    tier1_ratio              REAL,                 -- percent
    capital_adequacy_ratio   REAL,                 -- CAR, percent
    source_page              INTEGER,
    extracted_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind, period_type)
);

CREATE INDEX IF NOT EXISTS idx_bank_capital_bank_period
  ON bank_audit_capital(bank_ticker, period);


-- Liquidity & leverage (BRSA §4.6 LCR / NSFR, §4.7 leverage ratio).
-- All values are percentages.
CREATE TABLE IF NOT EXISTS bank_audit_liquidity (
    bank_ticker     TEXT NOT NULL,
    period          TEXT NOT NULL,
    kind            TEXT NOT NULL,
    period_type     TEXT NOT NULL,        -- 'current' | 'prior'
    leverage_ratio  REAL,                 -- percent (3-month average)
    lcr_total       REAL,                 -- Liquidity Coverage Ratio, total, percent
    lcr_fc          REAL,                 -- LCR, foreign currency, percent
    nsfr            REAL,                 -- Net Stable Funding Ratio, percent
    source_page     INTEGER,
    extracted_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind, period_type)
);

CREATE INDEX IF NOT EXISTS idx_bank_liquidity_bank_period
  ON bank_audit_liquidity(bank_ticker, period);


-- FX net open position (BRSA §4 "Currency risk" footnote). One row per
-- (bank, period, kind, period_type, currency) where currency ∈ EUR/USD/GBP/
-- OTHER/TOTAL. Amounts in thousand TRY; negatives stored negative. The bank's
-- overall FX net open position ("YP net genel pozisyon") is net_position =
-- net_on_balance + net_off_balance. Footing (Σ currencies = TOTAL;
-- net_on_balance = assets − liab) checked in validator.py.
CREATE TABLE IF NOT EXISTS bank_audit_fx_position (
    bank_ticker        TEXT NOT NULL,
    period             TEXT NOT NULL,
    kind               TEXT NOT NULL,
    period_type        TEXT NOT NULL,        -- 'current' | 'prior'
    currency           TEXT NOT NULL,        -- 'EUR' | 'USD' | 'GBP' | 'OTHER' | 'TOTAL'
    on_bs_assets       REAL,
    on_bs_liab         REAL,
    net_on_balance     REAL,                 -- net balance-sheet position (assets − liab)
    net_off_balance    REAL,                 -- net off-balance / derivatives position
    off_bs_receivable  REAL,                 -- derivative financial instruments — receivable leg
    off_bs_payable     REAL,                 -- derivative financial instruments — payable leg
    net_position       REAL,                 -- net_on_balance + net_off_balance (YP net genel pozisyon)
    source_page        INTEGER,
    extracted_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind, period_type, currency)
);

CREATE INDEX IF NOT EXISTS idx_bank_fx_bank_period
  ON bank_audit_fx_position(bank_ticker, period);


-- Interest-rate repricing / maturity gap (BRSA §4 "Interest-rate risk"
-- footnote). One row per (bank, period, kind, period_type, bucket) where bucket
-- ∈ lt_1m / 1_3m / 3_12m / 1_5y / gt_5y / non_sensitive / total (standard
-- 7-column template). `gap` is the reported total repricing position (on + off
-- balance); `cumulative_gap` is the running sum over the dated buckets. Footing
-- (Σ buckets = total; RSA total = RSL total) checked in validator.py.
CREATE TABLE IF NOT EXISTS bank_audit_repricing (
    bank_ticker            TEXT NOT NULL,
    period                 TEXT NOT NULL,
    kind                   TEXT NOT NULL,
    period_type            TEXT NOT NULL,    -- 'current' | 'prior'
    bucket                 TEXT NOT NULL,    -- lt_1m|1_3m|3_12m|1_5y|gt_5y|non_sensitive|total
    rate_sensitive_assets  REAL,
    rate_sensitive_liab    REAL,
    gap                    REAL,
    cumulative_gap         REAL,
    source_page            INTEGER,
    extracted_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind, period_type, bucket)
);

CREATE INDEX IF NOT EXISTS idx_bank_repricing_bank_period
  ON bank_audit_repricing(bank_ticker, period);


-- Structural-validation results per extracted statement (see
-- src/audit_reports/validator.py and docs/AUDIT_REWORK_PLAN.md). One row per
-- (bank, period, kind, statement); statement is 'assets' | 'liabilities' |
-- 'cross' (assets vs liabilities+equity). failed_detail is a JSON list of
-- {check, node, expected, actual, diff} for the failing identities.
CREATE TABLE IF NOT EXISTS bank_audit_validation (
    bank_ticker    TEXT NOT NULL,
    period         TEXT NOT NULL,
    kind           TEXT NOT NULL,
    statement      TEXT NOT NULL,
    checks_passed  INTEGER NOT NULL DEFAULT 0,
    checks_failed  INTEGER NOT NULL DEFAULT 0,
    checks_skipped INTEGER NOT NULL DEFAULT 0,
    failed_detail  TEXT,
    validated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind, statement)
);

CREATE INDEX IF NOT EXISTS idx_bank_validation_failed
  ON bank_audit_validation(checks_failed);


-- Per-row semantic tags for the income statement: which row IS the period-net,
-- the gross operating profit, the two opex lines, etc. — resolved against the
-- FILER'S OWN roman numbering by validator.pl_roles() and rebuilt from stored
-- rows by scripts/revalidate_audit_db.py (no re-extraction).
--
-- Exists because the BRSA roman ordinals are NOT fixed across the corpus: the
-- compressed template some participation banks file puts net-operating at XII
-- and period-net at XXIV, not XIII/XXV. A SQL consumer that hardcodes an ordinal
-- silently reads the wrong LINE — heatmap.ts's `COALESCE(XXV., XIX.)` reported
-- DUNYAK's net profit as 0 for six quarters (it fell through to XIX =
-- discontinued-ops income) and its `XI. + XII.` summed other-opex plus net
-- operating PROFIT as "opex". Consumers join here instead of guessing, so the
-- resolution lives in exactly one place — the Python side, which has the Turkish
-- fold that SQL's ASCII-only UPPER() lacks.
CREATE TABLE IF NOT EXISTS bank_audit_pl_roles (
    bank_ticker TEXT NOT NULL,
    period      TEXT NOT NULL,
    kind        TEXT NOT NULL,
    hierarchy   TEXT NOT NULL,
    role        TEXT NOT NULL,
    derived_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind, hierarchy)
);

CREATE INDEX IF NOT EXISTS idx_bank_pl_roles_role
  ON bank_audit_pl_roles(role);


-- ===========================================================================
-- Coverage spine for the /admin audit coverage matrix. All three are rebuilt
-- wholesale by scripts/sync_audit_expected.py (DELETE + INSERT), so they carry
-- no per-row timestamp; the registry table mirrors src/audit_reports/registry.py.
-- ===========================================================================

-- The EXPECTED universe: one row per (bank, period, kind) the corpus should
-- hold (from data/audit_profiles.json), overlaid with whether the PDF is in R2.
CREATE TABLE IF NOT EXISTS bank_audit_expected (
    bank_ticker    TEXT NOT NULL,
    period         TEXT NOT NULL,
    kind           TEXT NOT NULL,
    bank_type      TEXT,                 -- 'deposit' | 'participation' | 'development'
    language       TEXT,                 -- 'tr' | 'en'
    equity_numeral TEXT,                 -- BS roman where equity sits ('XVI'/'XIV')
    pdf_present    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (bank_ticker, period, kind)
);

-- The statement-type registry mirrored from registry.web_metadata(), so the
-- Worker reads the type list/labels from D1 instead of importing Python.
CREATE TABLE IF NOT EXISTS bank_audit_statement_types (
    key           TEXT PRIMARY KEY,
    label         TEXT NOT NULL,
    source_table  TEXT NOT NULL,
    statement     TEXT,                  -- BS sub-statement value, else NULL
    is_core       INTEGER NOT NULL DEFAULT 0,
    has_validator INTEGER NOT NULL DEFAULT 0,
    sort_order    INTEGER NOT NULL DEFAULT 0
);

-- Precomputed coverage rollup: one row per (bank, period, kind, statement_type).
-- status ∈ 'not_expected' | 'missing' | 'error' | 'manual' | 'ok'.
CREATE TABLE IF NOT EXISTS bank_audit_coverage (
    bank_ticker    TEXT NOT NULL,
    period         TEXT NOT NULL,
    kind           TEXT NOT NULL,
    statement_type TEXT NOT NULL,        -- registry key
    status         TEXT NOT NULL,
    row_count      INTEGER NOT NULL DEFAULT 0,
    checks_failed  INTEGER NOT NULL DEFAULT 0,
    is_manual      INTEGER NOT NULL DEFAULT 0,
    pdf_present    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (bank_ticker, period, kind, statement_type)
);

CREATE INDEX IF NOT EXISTS idx_bank_coverage_status
  ON bank_audit_coverage(status);
CREATE INDEX IF NOT EXISTS idx_bank_coverage_type_kind
  ON bank_audit_coverage(statement_type, kind);
"""


# Column-level migrations for tables that already exist in older snapshots.
# `CREATE TABLE IF NOT EXISTS` won't add a column to a pre-existing table, so
# every column added to an existing table needs an explicit ALTER entry here.
# Append new tuples as columns are introduced — they're applied idempotently
# (guarded by PRAGMA table_info), so re-running is always safe.
#
# Format: (table, column_name, column_declaration)
_COLUMN_MIGRATIONS: list[tuple[str, str, str]] = [
    # Added 2026-05-14 (commit 6b429d8) alongside the IFRS 9 credit-quality
    # extractor. Without this, old snapshots in R2 crash inside
    # src/audit_reports/loader.py:upsert_report.
    ("bank_audit_extractions", "rows_credit_quality", "INTEGER"),
    # Added 2026-06-12: OCI (Other Comprehensive Income) extraction.
    ("bank_audit_extractions", "rows_oci", "INTEGER"),
    # Added 2026-06-12: cash flow + equity-change extraction.
    ("bank_audit_extractions", "rows_cash_flow", "INTEGER"),
    ("bank_audit_extractions", "rows_equity_change", "INTEGER"),
    # Added 2026-06-27: §4 market-risk (FX net open position + interest-rate
    # repricing gap) extraction.
    ("bank_audit_extractions", "rows_fx_position", "INTEGER"),
    ("bank_audit_extractions", "rows_repricing", "INTEGER"),
]


def _ensure_column(conn: sqlite3.Connection, table: str, col: str, decl: str) -> None:
    """Idempotently add a column to an existing table."""
    have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    # If the table doesn't exist at all, CREATE TABLE IF NOT EXISTS in DDL
    # will have created it with the column already — nothing to do here.
    if not have or col in have:
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    for table, col, decl in _COLUMN_MIGRATIONS:
        _ensure_column(conn, table, col, decl)
    conn.commit()


if __name__ == '__main__':
    import sys
    from pathlib import Path
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('data/bddk_data.db')
    with sqlite3.connect(db) as conn:
        init_schema(conn)
    print(f'schema initialized at {db}')
