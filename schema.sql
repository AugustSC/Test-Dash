
-- PostgreSQL schema for StarSpy

CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    nickname TEXT,
    rsi_handle TEXT,
    original_nickname TEXT,
    original_rsi_handle TEXT,
    aliases TEXT,
    notes TEXT,
    role TEXT DEFAULT 'user',
    tags TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    timestamp TIMESTAMPTZ,
    author TEXT,
    content TEXT,
    rsi_handle TEXT,
    score REAL,
    source_file TEXT,
    server_name TEXT,
    channel_category TEXT,
    channel_name TEXT,
    avatar_url TEXT,
    reactions JSONB,
    tags TEXT
);

-- Useful indexes
CREATE INDEX IF NOT EXISTS idx_messages_author ON messages(author);
CREATE INDEX IF NOT EXISTS idx_messages_score ON messages(score);
CREATE INDEX IF NOT EXISTS idx_messages_tags ON messages(tags);
