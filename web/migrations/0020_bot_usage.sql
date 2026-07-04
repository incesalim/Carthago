-- Telegram bot rate-limiting counters. One row per (chat, UTC day); the special
-- chat_id '__global__' tracks the whole bot's daily volume. Written by the
-- webhook (web/app/lib/bot.ts); also lazily CREATE-IF-NOT-EXISTS'd there so the
-- bot works even before this migration is applied.
CREATE TABLE IF NOT EXISTS bot_usage (
    chat_id TEXT    NOT NULL,
    day     TEXT    NOT NULL,          -- 'YYYY-MM-DD' (UTC)
    count   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (chat_id, day)
);
