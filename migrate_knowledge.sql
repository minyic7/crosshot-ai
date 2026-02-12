-- Migration: Add knowledge pipeline columns to contents
-- Run on NAS via: docker compose exec -T postgres psql -U crosshot -d crosshot < migrate_knowledge.sql

BEGIN;

-- Content triage + integration tracking
ALTER TABLE contents ADD COLUMN IF NOT EXISTS processing_status VARCHAR(16);
ALTER TABLE contents ADD COLUMN IF NOT EXISTS key_points JSONB;
CREATE INDEX IF NOT EXISTS ix_contents_processing_status ON contents(processing_status);

COMMIT;
