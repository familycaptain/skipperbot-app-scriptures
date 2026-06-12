-- Add pronouns cache columns to chapter_summaries
-- Stored as JSON text keyed by verse/instance order.

SET search_path TO app_scriptures, public;

ALTER TABLE chapter_summaries
    ADD COLUMN IF NOT EXISTS pronouns        TEXT,
    ADD COLUMN IF NOT EXISTS pronouns_model  TEXT,
    ADD COLUMN IF NOT EXISTS pronouns_at     TIMESTAMPTZ;
