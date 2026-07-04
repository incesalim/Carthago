-- 0019: read_headlines — LLM-rewritten "The Read" lead sentence per tab.
--
-- Option-1 of the perspective layer: an LLM (Cerebras gpt-oss-120b, Groq
-- failover) rewrites ONLY the one-sentence headline that web/app/lib/insights.ts
-- computes deterministically for each tab. The driver bullets stay deterministic.
--
-- Written by scripts/generate_read_headlines.py (weekly CI cron): it reads the
-- deterministic takeaways from GET /api/reads, rewrites each headline, validates
-- that the rewrite invents no number, and upserts here. The dashboard reads this
-- table on render (web/app/lib/read-headlines.ts) and shows the LLM headline ONLY
-- when `det_hash` still matches the page's live deterministic takeaway — so it can
-- never drift from the charts or go stale (it falls back to the template).
--
-- One row per tab; the generator INSERT OR REPLACEs on the PK.
CREATE TABLE IF NOT EXISTS read_headlines (
    tab          TEXT PRIMARY KEY,          -- 'overview' | 'credit' | ... (reads.ts registry key)
    det_hash     TEXT NOT NULL,             -- hash of the deterministic takeaway this rewrite was derived from
    headline     TEXT NOT NULL,             -- the LLM-rewritten lead sentence
    model        TEXT,                      -- provider/model that produced it (e.g. 'cerebras/gpt-oss-120b')
    generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
