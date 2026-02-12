-- Migration: Add users table, topic_users junction, and contents.user_id
-- Run on NAS via: docker compose exec -T postgres psql -U crosshot -d crosshot < migrate_users.sql

BEGIN;

-- 1. Create users table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(256) NOT NULL,
    platform VARCHAR(16) NOT NULL,
    profile_url TEXT NOT NULL,
    username VARCHAR(128),
    config JSONB NOT NULL DEFAULT '{}',
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    is_pinned BOOLEAN NOT NULL DEFAULT FALSE,
    position INTEGER NOT NULL DEFAULT 0,
    total_contents INTEGER NOT NULL DEFAULT 0,
    last_crawl_at TIMESTAMPTZ,
    last_summary TEXT,
    summary_data JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_users_status ON users(status);
CREATE INDEX IF NOT EXISTS ix_users_platform ON users(platform);
CREATE INDEX IF NOT EXISTS ix_users_username ON users(username);

-- 2. Create topic_users junction table
CREATE TABLE IF NOT EXISTS topic_users (
    topic_id UUID REFERENCES topics(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (topic_id, user_id)
);

-- 3. Add user_id FK to contents
ALTER TABLE contents ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS ix_contents_user_id ON contents(user_id);

COMMIT;
