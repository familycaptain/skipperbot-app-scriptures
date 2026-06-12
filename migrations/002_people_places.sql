-- Add people and places columns to chapter_summaries
-- These are LLM-generated, cached like the summary column.

SET search_path TO app_scriptures, public;

ALTER TABLE chapter_summaries
    ADD COLUMN IF NOT EXISTS people       TEXT,
    ADD COLUMN IF NOT EXISTS people_model  TEXT,
    ADD COLUMN IF NOT EXISTS people_at     TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS places       TEXT,
    ADD COLUMN IF NOT EXISTS places_model  TEXT,
    ADD COLUMN IF NOT EXISTS places_at     TIMESTAMPTZ;
