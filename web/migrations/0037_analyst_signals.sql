-- The analyst layer: detector signals, generated notes, and the comparability
-- basis metadata behind the per-bank badge.
-- Build spec: docs/knowledge/2026-08-04-analyst-build-plan.md (Tasks 1.7, 1.5).
-- Local staging mirror: src/analyst/schema.py — keep in lockstep (pytest-gated).
--
-- NOTE: authored under the standing D1-write freeze (2026-08-01, indefinite).
-- Do not apply remotely until the freeze lifts; local-dev apply is fine.

-- One row per detector firing. The analytical fact, not the prose.
CREATE TABLE IF NOT EXISTS analyst_signals (
    signal_id     TEXT NOT NULL,          -- "unit_change:SKBNK:2026Q2:unconsolidated"
    signal_type   TEXT NOT NULL,          -- unit_change | cross_period_mismatch | opinion_change | perimeter_change | divergence
    bank_ticker   TEXT NOT NULL,
    period        TEXT NOT NULL,          -- YYYYQN, no hyphen
    kind          TEXT NOT NULL,          -- consolidated | unconsolidated
    severity      TEXT NOT NULL,          -- notice | alert | critical
    fired_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    payload       TEXT NOT NULL,          -- JSON: { prior_value, current_value, ratio, ... }
    PRIMARY KEY (signal_id)
);
CREATE INDEX IF NOT EXISTS idx_signals_bank_period ON analyst_signals(bank_ticker, period);

-- One row per analyst note produced. The prose, grounded on signals.
-- note_id carries kind + a timestamp: same-day reruns are VERSIONS.
CREATE TABLE IF NOT EXISTS analyst_notes (
    note_id       TEXT NOT NULL,          -- "note:SKBNK:2026Q1:unconsolidated:20260805T071500"
    bank_ticker   TEXT NOT NULL,
    period        TEXT NOT NULL,
    kind          TEXT NOT NULL,
    signal_ids    TEXT NOT NULL,          -- JSON array of signal_ids the note is based on
    title         TEXT NOT NULL,          -- one-line summary
    body          TEXT NOT NULL,          -- markdown, ~2-3 pages
    generated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    model         TEXT,                   -- which LLM produced it
    fact_check_passed INTEGER NOT NULL DEFAULT 0,  -- grounding guard verdict (runtime gate)
    -- `data_hash` is NOT here: it is added by 0038, because THIS file had already
    -- been applied to D1 without it. Restoring the as-applied shape is what makes
    -- a from-scratch replay (0037 then 0038) and the live database agree. Do not
    -- re-add it here — an applied migration is immutable, and editing this one is
    -- exactly what produced the drift 0038 repairs.
    PRIMARY KEY (note_id)
);
CREATE INDEX IF NOT EXISTS idx_notes_bank_period ON analyst_notes(bank_ticker, period);

-- The comparability badge: reporting unit, assurance level, consolidation
-- basis per extracted partition. reporting_unit NULL means "not yet read",
-- never "assume thousands" — null is not a default.
CREATE TABLE IF NOT EXISTS analyst_basis_metadata (
    bank_ticker      TEXT NOT NULL,
    period           TEXT NOT NULL,
    kind             TEXT NOT NULL,
    reporting_unit   TEXT,                -- bin | milyon | milyar | NULL (pending)
    unit_source      TEXT NOT NULL,       -- sweep-2026-08-01 | regex | pending_regex
    assurance_level  TEXT NOT NULL,       -- audit | review
    assurance_source TEXT NOT NULL,       -- opinion | expected_rhythm
    consolidation_basis TEXT NOT NULL,    -- consolidated | unconsolidated
    PRIMARY KEY (bank_ticker, period, kind)
);
CREATE INDEX IF NOT EXISTS idx_basis_bank_period ON analyst_basis_metadata(bank_ticker, period);

-- Latest PASSING note per (bank, kind) — the page's read path. Partitioned by
-- kind (the two bases are different reports) and filtered to passing, so a
-- failed later run can never hide the most recent passing report.
CREATE VIEW IF NOT EXISTS v_latest_analyst_note AS
SELECT n.* FROM analyst_notes n
JOIN (
    SELECT bank_ticker, kind, MAX(generated_at) AS max_at
    FROM analyst_notes WHERE fact_check_passed = 1
    GROUP BY bank_ticker, kind
) latest ON n.bank_ticker = latest.bank_ticker AND n.kind = latest.kind
        AND n.generated_at = latest.max_at
WHERE n.fact_check_passed = 1;
