-- 0025_release_calendar
-- The Turkish banking release calendar — SCHEDULED events, scraped from the
-- authorities that publish a forward calendar.
--
-- WHY: the site's "Ahead" strips answer "what lands next". The derived rows
-- (BDDK weekly/monthly bulletins, BRSA filing windows) come from record cadence
-- and need no source; but the central-bank events have real published dates that
-- were hand-transcribed into web/app/lib/ahead.ts (MPC_DATES). This table holds
-- them instead, scraped from TCMB's own "Monetary Policy Committee Meeting and
-- Reports Calendar" — four event kinds in one table (the page publishes them as
-- four columns):
--   mpc_decision                — the rate decision
--   mpc_minutes                 — "Summary of the MPC Meeting"
--   inflation_report            — quarterly
--   financial_stability_report  — twice-yearly
--
-- Only SCRAPED events live here; the derived (cadence) rows stay computed live in
-- ahead.ts, so this table is not the whole calendar — it is the part with an
-- external publisher. `source` is 'tcmb' today; TÜİK data-release dates (CPI/GDP)
-- would land here later as source='tuik' with no schema change.
--
-- Columns:
--   source        publishing authority ('tcmb')
--   kind          event type (snake_case; see the four above)
--   event_date    'YYYY-MM-DD' — the published date
--   title         display label ("Monetary Policy Committee Decision")
--   source_url    the calendar page
--
-- Natural key (source, kind, event_date) — one row per event, so a re-scrape is
-- idempotent (INSERT OR REPLACE). Synced by push_to_d1.py on `downloaded_at`.
-- Mirrors src/release_calendar/schema.py verbatim.

CREATE TABLE IF NOT EXISTS release_calendar (
    source        TEXT NOT NULL,
    kind          TEXT NOT NULL,
    event_date    TEXT NOT NULL,
    title         TEXT NOT NULL,
    source_url    TEXT NOT NULL,
    downloaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source, kind, event_date)
);

CREATE INDEX IF NOT EXISTS idx_release_calendar_date ON release_calendar(event_date);
