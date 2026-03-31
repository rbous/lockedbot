-- Accountability tracker configuration per guild
CREATE TABLE IF NOT EXISTS tracker_configs (
    guild_id INTEGER PRIMARY KEY,
    channel_id INTEGER NOT NULL,
    summary_channel_id INTEGER,
    calendar_id TEXT,
    timezone TEXT DEFAULT 'UTC',
    ping_interval_minutes INTEGER DEFAULT 15,
    summary_time TEXT DEFAULT '22:00',
    enabled INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Individual accountability responses from users
CREATE TABLE IF NOT EXISTS tracker_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    response_type TEXT NOT NULL,
    calendar_event TEXT,
    prompt_message_id INTEGER,
    response_date TEXT NOT NULL,
    responded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (guild_id) REFERENCES tracker_configs(guild_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tracker_responses_guild_date
    ON tracker_responses(guild_id, response_date);
