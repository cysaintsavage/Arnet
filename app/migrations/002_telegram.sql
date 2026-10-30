-- Telegram bot: one Telegram chat is linked to one ARNET AI account, so chats use that account's plan, limits and history.
CREATE TABLE telegram_links (
    chat_id         INTEGER PRIMARY KEY,
    user_id         INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    conversation_id INTEGER REFERENCES conversations(id) ON DELETE SET NULL,
    tool            TEXT NOT NULL DEFAULT 'chat',
    linked_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- Short-lived, single-use codes created on the website and typed into the bot. Only a hash is stored.
CREATE TABLE telegram_link_codes (
    code_hash  TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL
);
CREATE INDEX idx_tg_codes_user ON telegram_link_codes(user_id);
