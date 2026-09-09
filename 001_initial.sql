-- Initial persistent state for the Discord AI agent.
-- Message contents are retained for a limited period by a later cleanup job.

CREATE TABLE IF NOT EXISTS conversation_sessions (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    summary TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (guild_id, channel_id, user_id)
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id BIGSERIAL PRIMARY KEY,
    session_id BIGINT NOT NULL REFERENCES conversation_sessions(id) ON DELETE CASCADE,
    discord_message_id BIGINT UNIQUE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS conversation_messages_session_created_idx
    ON conversation_messages (session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS conversation_messages_expires_idx
    ON conversation_messages (expires_at);

CREATE TABLE IF NOT EXISTS memories (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    memory_type TEXT NOT NULL DEFAULT 'preference',
    content TEXT NOT NULL,
    source_message_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS memories_guild_user_idx
    ON memories (guild_id, user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS memories_expires_idx ON memories (expires_at);

CREATE TABLE IF NOT EXISTS usage_daily (
    usage_date DATE NOT NULL,
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0 CHECK (request_count >= 0),
    input_tokens INTEGER NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
    output_tokens INTEGER NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
    PRIMARY KEY (usage_date, guild_id, user_id)
);

CREATE INDEX IF NOT EXISTS usage_daily_guild_date_idx
    ON usage_daily (guild_id, usage_date);

CREATE TABLE IF NOT EXISTS agent_jobs (
    id BIGSERIAL PRIMARY KEY,
    job_type TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    run_after TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    last_error TEXT
);

CREATE INDEX IF NOT EXISTS agent_jobs_ready_idx
    ON agent_jobs (status, run_after)
    WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS audit_events (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT,
    channel_id BIGINT,
    user_id BIGINT,
    event_type TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS audit_events_created_idx
    ON audit_events (created_at DESC);
