-- 0001_baseline_schema
-- Single source of truth for the D1 schema, derived 1:1 from the live bddk-data
-- database. Every statement is idempotent (IF NOT EXISTS), so applying this to the
-- existing DB is a no-op while a fresh DB gets the full schema. Add future schema
-- changes as new numbered migrations (0002_*.sql). Data seeding is separate
-- (scripts/generate_d1_migrations.py -> web/seeds/, gitignored).

-- ===== tables =====
CREATE TABLE IF NOT EXISTS balance_sheet (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    currency VARCHAR(10) NOT NULL,
    bank_type_code VARCHAR(10) NOT NULL,
    item_order INTEGER NOT NULL,
    item_name VARCHAR(300) NOT NULL,
    is_subtotal BOOLEAN DEFAULT FALSE,
    amount_tl DECIMAL(20, 2),
    amount_fx DECIMAL(20, 2),
    amount_total DECIMAL(20, 2),
    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(year, month, currency, bank_type_code, item_order)
);

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

CREATE TABLE IF NOT EXISTS bank_audit_credit_quality (
    bank_ticker      TEXT NOT NULL,
    period           TEXT NOT NULL,
    kind             TEXT NOT NULL,
    section          TEXT NOT NULL,           -- 'loans_ecl' | 'loans_amounts' | 'cash_ecl' | 'amortised_cost_ecl' | 'non_cash_ecl' | 'other_ecl'
    period_type      TEXT NOT NULL,           -- 'current' | 'prior'
    source_page      INTEGER,
    stage1_amount    REAL,
    stage2_amount    REAL,
    stage3_amount    REAL,
    total_amount     REAL,
    heading_snippet  TEXT,
    extracted_at     TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind, section, period_type)
);

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
    success              INTEGER NOT NULL DEFAULT 1,
    note                 TEXT, rows_credit_quality INTEGER,
    PRIMARY KEY (bank_ticker, period, kind)
);

CREATE TABLE IF NOT EXISTS bank_audit_loans_by_sector (
    bank_ticker      TEXT NOT NULL,
    period           TEXT NOT NULL,
    kind             TEXT NOT NULL,
    sector           TEXT NOT NULL,           -- canonical short code (see notes)
    period_type      TEXT NOT NULL,           -- 'current' | 'prior'
    source_page      INTEGER,
    stage2_amount    REAL,
    stage3_amount    REAL,
    ecl_amount       REAL,
    raw_label        TEXT,
    extracted_at     TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind, sector, period_type)
);

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
    extracted_at       TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind, group_code, period_type)
);

CREATE TABLE IF NOT EXISTS bank_audit_profile (
    bank_ticker        TEXT NOT NULL,
    period             TEXT NOT NULL,
    kind               TEXT NOT NULL,
    branches_domestic  INTEGER,
    branches_foreign   INTEGER,
    branches_total     INTEGER,
    personnel          INTEGER,
    extracted_at       TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind)
);

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

CREATE TABLE IF NOT EXISTS bank_audit_stages (
    bank_ticker      TEXT NOT NULL,
    period           TEXT NOT NULL,
    kind             TEXT NOT NULL,
    period_type      TEXT NOT NULL,           -- 'current' | 'prior'
    stage1_amount    REAL,
    stage2_amount    REAL,
    stage3_amount    REAL,
    total_amount     REAL,
    stage1_ecl       REAL,
    stage2_ecl       REAL,
    stage3_ecl       REAL,
    total_ecl        REAL,
    stage1_coverage  REAL,                    -- fraction (0.0083 = 0.83%)
    stage2_coverage  REAL,
    stage3_coverage  REAL,
    extracted_at     TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_ticker, period, kind, period_type)
);

CREATE TABLE IF NOT EXISTS bank_types (
    code VARCHAR(10) PRIMARY KEY,
    name_tr VARCHAR(100) NOT NULL,
    name_en VARCHAR(100),
    category VARCHAR(50),  -- 'sector', 'deposit', 'participation', etc.
    description TEXT
);

CREATE TABLE IF NOT EXISTS deposits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_number INTEGER NOT NULL,  -- 9 or 10
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    currency VARCHAR(10) NOT NULL,
    bank_type_code VARCHAR(10) NOT NULL,
    item_order INTEGER NOT NULL,
    item_name VARCHAR(300) NOT NULL,
    is_subtotal BOOLEAN DEFAULT FALSE,
    -- Table 9: By amount bracket
    bracket_10k DECIMAL(20, 2),
    bracket_50k DECIMAL(20, 2),
    bracket_250k DECIMAL(20, 2),
    bracket_1m DECIMAL(20, 2),
    bracket_over_1m DECIMAL(20, 2),
    -- Table 10: By maturity
    demand DECIMAL(20, 2),
    maturity_1m DECIMAL(20, 2),
    maturity_1_3m DECIMAL(20, 2),
    maturity_3_6m DECIMAL(20, 2),
    maturity_6_12m DECIMAL(20, 2),
    maturity_over_12m DECIMAL(20, 2),
    -- Common
    total_amount DECIMAL(20, 2),
    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(table_number, year, month, currency, bank_type_code, item_order)
);

CREATE TABLE IF NOT EXISTS download_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_number INTEGER,
    year INTEGER,
    month INTEGER,
    currency VARCHAR(10),
    bank_type_code VARCHAR(10),
    status VARCHAR(20),  -- 'success', 'failed', 'partial'
    rows_downloaded INTEGER,
    error_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS evds_series (code TEXT NOT NULL, period_date DATE NOT NULL, value REAL, label TEXT, category TEXT, downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (code, period_date));

CREATE TABLE IF NOT EXISTS financial_ratios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_number INTEGER NOT NULL,  -- 15 or 17
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    bank_type_code VARCHAR(10) NOT NULL,
    item_order INTEGER NOT NULL,
    item_name VARCHAR(300) NOT NULL,
    ratio_value DECIMAL(10, 6),
    ratio_category VARCHAR(100),  -- 'asset_quality', 'profitability', 'liquidity', 'capital'
    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(table_number, year, month, bank_type_code, item_order)
);

CREATE TABLE IF NOT EXISTS income_statement (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    currency VARCHAR(10) NOT NULL,
    bank_type_code VARCHAR(10) NOT NULL,
    item_order INTEGER NOT NULL,
    item_name VARCHAR(300) NOT NULL,
    is_subtotal BOOLEAN DEFAULT FALSE,
    amount_tl DECIMAL(20, 2),
    amount_fx DECIMAL(20, 2),
    amount_total DECIMAL(20, 2),
    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(year, month, currency, bank_type_code, item_order)
);

CREATE TABLE IF NOT EXISTS loans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_number INTEGER NOT NULL,  -- 3, 4, 5, 6, or 7
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    currency VARCHAR(10) NOT NULL,
    bank_type_code VARCHAR(10) NOT NULL,
    item_order INTEGER NOT NULL,
    item_name VARCHAR(300) NOT NULL,
    is_subtotal BOOLEAN DEFAULT FALSE,
    -- Generic columns (use based on table)
    short_term_tl DECIMAL(20, 2),
    short_term_fx DECIMAL(20, 2),
    short_term_total DECIMAL(20, 2),
    medium_long_tl DECIMAL(20, 2),
    medium_long_fx DECIMAL(20, 2),
    medium_long_total DECIMAL(20, 2),
    total_tl DECIMAL(20, 2),
    total_fx DECIMAL(20, 2),
    total_amount DECIMAL(20, 2),
    npl_amount DECIMAL(20, 2),
    non_cash_amount DECIMAL(20, 2),
    customer_count INTEGER,
    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(table_number, year, month, currency, bank_type_code, item_order)
);

CREATE TABLE IF NOT EXISTS news_items (
    source        TEXT NOT NULL,            -- 'kap' | 'tcmb' | 'bddk'
    external_id   TEXT NOT NULL,            -- source-stable id
    published_at  TEXT NOT NULL,            -- ISO-8601 UTC
    ticker        TEXT,                     -- BIST ticker if applicable
    category      TEXT,                     -- source-specific category
    title         TEXT NOT NULL,
    summary       TEXT,                     -- short body / first paragraph
    url           TEXT NOT NULL,            -- canonical link to the original
    language      TEXT NOT NULL,            -- 'tr' | 'en'
    raw_json      TEXT,                     -- json blob for re-processing
    fetched_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, body_text TEXT,
    PRIMARY KEY (source, external_id)
);

CREATE TABLE IF NOT EXISTS other_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_number INTEGER NOT NULL,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    currency VARCHAR(10),
    bank_type_code VARCHAR(10) NOT NULL,
    item_order INTEGER NOT NULL,
    item_name VARCHAR(300) NOT NULL,
    is_subtotal BOOLEAN DEFAULT FALSE,
    column_name VARCHAR(100),  -- Dynamic column name
    value_numeric DECIMAL(20, 2),
    value_text TEXT,
    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS regulation_briefings (
    generated_at     TEXT NOT NULL,                 -- ISO-8601 UTC, doubles as PK
    window_days      INTEGER NOT NULL,              -- look-back window the briefing covered
    item_count       INTEGER NOT NULL,              -- # source items fed to the LLM
    model            TEXT NOT NULL,                 -- e.g. "moonshot-v1-32k"
    prompt_version   TEXT NOT NULL,                 -- bump when prompt changes; used for diffs
    categories_json  TEXT NOT NULL,                 -- structured response (see schema in prompt)
    raw_response     TEXT,                          -- full Kimi response for audit
    fetched_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (generated_at)
);

CREATE TABLE IF NOT EXISTS table_definitions (
    table_number INTEGER PRIMARY KEY,
    name_tr VARCHAR(200) NOT NULL,
    name_en VARCHAR(200),
    description TEXT,
    unit VARCHAR(50),  -- 'million TL', 'thousand TL', 'percentage', 'count'
    typical_rows INTEGER,
    category VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS weekly_bulletin (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        period_id VARCHAR(10),
        period_date DATE,
        week_number INTEGER,
        year INTEGER,
        category VARCHAR(50),
        item_id INTEGER,
        item_name VARCHAR(200),
        tp_value FLOAT,
        yp_value FLOAT,
        total_value FLOAT,
        bank_type_code VARCHAR(10) DEFAULT '10001',
        currency VARCHAR(10) DEFAULT 'TL',
        download_date DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

CREATE TABLE IF NOT EXISTS weekly_series (
    period_date    DATE    NOT NULL,
    category       TEXT    NOT NULL,
    item_id        TEXT    NOT NULL,
    item_name      TEXT    NOT NULL,
    bank_type_code TEXT    NOT NULL,
    currency       TEXT    NOT NULL,
    value          REAL,
    downloaded_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (period_date, item_id, bank_type_code, currency)
);

-- ===== indexes =====
CREATE INDEX IF NOT EXISTS idx_bank_bs_bank_period
  ON bank_audit_balance_sheet(bank_ticker, period);
CREATE INDEX IF NOT EXISTS idx_bank_bs_item_name
  ON bank_audit_balance_sheet(item_name);
CREATE INDEX IF NOT EXISTS idx_bank_cq_bank_period
  ON bank_audit_credit_quality(bank_ticker, period);
CREATE INDEX IF NOT EXISTS idx_bank_cq_section
  ON bank_audit_credit_quality(section);
CREATE INDEX IF NOT EXISTS idx_bank_lbs_bank_period
  ON bank_audit_loans_by_sector(bank_ticker, period);
CREATE INDEX IF NOT EXISTS idx_bank_lbs_sector
  ON bank_audit_loans_by_sector(sector);
CREATE INDEX IF NOT EXISTS idx_bank_npl_bank_period
  ON bank_audit_npl_movement(bank_ticker, period);
CREATE INDEX IF NOT EXISTS idx_bank_pl_bank_period
  ON bank_audit_profit_loss(bank_ticker, period);
CREATE INDEX IF NOT EXISTS idx_bank_pl_item_name
  ON bank_audit_profit_loss(item_name);
CREATE INDEX IF NOT EXISTS idx_bank_profile_bank
  ON bank_audit_profile(bank_ticker);
CREATE INDEX IF NOT EXISTS idx_bank_stages_bank_period
  ON bank_audit_stages(bank_ticker, period);
CREATE INDEX IF NOT EXISTS idx_bs_bank_type ON balance_sheet(bank_type_code);
CREATE INDEX IF NOT EXISTS idx_bs_period ON balance_sheet(year, month);
CREATE INDEX IF NOT EXISTS idx_deposits_period ON deposits(year, month);
CREATE INDEX IF NOT EXISTS idx_evds_category ON evds_series(category);
CREATE INDEX IF NOT EXISTS idx_evds_code_date ON evds_series(code, period_date);
CREATE INDEX IF NOT EXISTS idx_is_bank_type ON income_statement(bank_type_code);
CREATE INDEX IF NOT EXISTS idx_is_period ON income_statement(year, month);
CREATE INDEX IF NOT EXISTS idx_loans_period ON loans(year, month);
CREATE INDEX IF NOT EXISTS idx_loans_table ON loans(table_number);
CREATE INDEX IF NOT EXISTS idx_log_status ON download_log(status, completed_at);
CREATE INDEX IF NOT EXISTS idx_news_published
  ON news_items(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_source
  ON news_items(source, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_ticker
  ON news_items(ticker, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_other_period ON other_data(year, month, table_number);
CREATE INDEX IF NOT EXISTS idx_ratios_category ON financial_ratios(ratio_category);
CREATE INDEX IF NOT EXISTS idx_ratios_period ON financial_ratios(year, month);
CREATE INDEX IF NOT EXISTS idx_reg_briefings_generated
  ON regulation_briefings(generated_at DESC);
CREATE INDEX IF NOT EXISTS idx_weekly_by_date
    ON weekly_series(period_date);
CREATE INDEX IF NOT EXISTS idx_weekly_by_item
    ON weekly_series(item_name, bank_type_code, currency, period_date);
CREATE INDEX IF NOT EXISTS idx_weekly_cat_item_cur
    ON weekly_series(category, item_id, currency, bank_type_code, period_date, value);
