-- What the Telegram bot actually asked the database.
--
-- Exists because the bot generated SQL, ran it, and threw it away: `bot_usage`
-- records only (chat_id, day, count). When a ranking came back with 8 banks
-- instead of 27, and another with 36 instead of 38, neither cause was
-- recoverable — both had to be reconstructed by re-deriving the answers from
-- D1 and inferring backwards what query could have produced them.
--
-- Both bugs shared a shape: the model silently narrowed the population (a label
-- pattern that missed two banks; a self-chosen IN list that missed nineteen)
-- and then wrote a fluent answer over the subset. Nothing errored. The only
-- way to catch that class early is to see the query and its row count.
--
-- Deliberately NOT keyed to a user. chat_id is stored as a short hash so
-- repeated failures from one conversation can be grouped without retaining who
-- asked; the question text is kept because the query is meaningless without it.
CREATE TABLE IF NOT EXISTS bot_queries (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    asked_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    chat_hash  TEXT,                   -- short non-reversible hash, not the chat id
    question   TEXT NOT NULL,
    step       INTEGER NOT NULL,       -- 0-based round within the agent loop
    sql_text   TEXT NOT NULL,          -- the sanitized SQL actually executed, or the rejected one
    outcome    TEXT NOT NULL,          -- 'rows' | 'rejected' | 'error'
    row_count  INTEGER,                -- rows returned when outcome='rows'
    detail     TEXT                    -- rejection reason or error message
);

-- "What went wrong lately" and "which questions return nothing" are the two
-- queries this table exists to answer.
CREATE INDEX IF NOT EXISTS idx_bot_queries_asked_at
  ON bot_queries(asked_at);
CREATE INDEX IF NOT EXISTS idx_bot_queries_outcome
  ON bot_queries(outcome);
