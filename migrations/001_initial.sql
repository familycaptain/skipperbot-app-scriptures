-- Scriptures App — Initial migration
-- Creates all tables in app_scriptures schema.

CREATE SCHEMA IF NOT EXISTS app_scriptures;
SET search_path TO app_scriptures, public;

-- Enable trigram extension for fuzzy search (idempotent)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================================
-- BIBLE VERSIONS (loaded translations)
-- ============================================================================

CREATE TABLE IF NOT EXISTS bible_versions (
    id              TEXT PRIMARY KEY,
    abbreviation    TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    language        TEXT NOT NULL DEFAULT 'eng',
    description     TEXT DEFAULT '',
    has_ot          BOOLEAN NOT NULL DEFAULT TRUE,
    has_nt          BOOLEAN NOT NULL DEFAULT TRUE,
    has_strongs     BOOLEAN NOT NULL DEFAULT FALSE,
    source_file     TEXT,
    verse_count     INTEGER NOT NULL DEFAULT 0,
    imported_at     TIMESTAMPTZ DEFAULT now()
);

-- ============================================================================
-- BIBLE BOOKS (book metadata per version)
-- ============================================================================

CREATE TABLE IF NOT EXISTS bible_books (
    id              TEXT PRIMARY KEY,
    version_id      TEXT NOT NULL REFERENCES bible_versions(id) ON DELETE CASCADE,
    book_number     INTEGER NOT NULL,
    name            TEXT NOT NULL,
    name_english    TEXT NOT NULL,
    abbreviation    TEXT NOT NULL,
    testament       TEXT NOT NULL CHECK (testament IN ('OT', 'NT')),
    chapter_count   INTEGER NOT NULL DEFAULT 0,
    UNIQUE(version_id, book_number)
);

CREATE INDEX IF NOT EXISTS idx_bible_books_version ON bible_books(version_id);

-- ============================================================================
-- BIBLE VERSES (scripture text)
-- ============================================================================

CREATE TABLE IF NOT EXISTS bible_verses (
    version_id      TEXT NOT NULL REFERENCES bible_versions(id) ON DELETE CASCADE,
    book            INTEGER NOT NULL,
    chapter         INTEGER NOT NULL,
    verse           INTEGER NOT NULL,
    text            TEXT NOT NULL,
    text_html       TEXT NOT NULL,
    PRIMARY KEY (version_id, book, chapter, verse)
);

-- Fast reference lookups (version + book + chapter)
CREATE INDEX IF NOT EXISTS idx_bible_verses_ref
    ON bible_verses (version_id, book, chapter);

-- Trigram index for full-text search
CREATE INDEX IF NOT EXISTS idx_bible_verses_text_trgm
    ON bible_verses USING gin (text gin_trgm_ops);

-- ============================================================================
-- CHAPTER SUMMARIES (LLM-generated, cached permanently)
-- ============================================================================

CREATE TABLE IF NOT EXISTS chapter_summaries (
    version_id      TEXT NOT NULL REFERENCES bible_versions(id) ON DELETE CASCADE,
    book            INTEGER NOT NULL,
    chapter         INTEGER NOT NULL,
    summary         TEXT NOT NULL,
    model           TEXT NOT NULL DEFAULT '',
    generated_at    TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (version_id, book, chapter)
);

-- ============================================================================
-- SCRIPTURE BOOKMARKS (named reading positions — shared)
-- ============================================================================

CREATE TABLE IF NOT EXISTS scripture_bookmarks (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    version_id      TEXT NOT NULL REFERENCES bible_versions(id) ON DELETE CASCADE,
    book            INTEGER NOT NULL,
    chapter         INTEGER NOT NULL,
    color           TEXT,
    created_by      TEXT NOT NULL DEFAULT '',
    updated_by      TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- ============================================================================
-- SCRIPTURE HIGHLIGHTS (per-user, per-verse) — Phase 2
-- ============================================================================

CREATE TABLE IF NOT EXISTS scripture_highlights (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    version_id      TEXT NOT NULL REFERENCES bible_versions(id) ON DELETE CASCADE,
    book            INTEGER NOT NULL,
    chapter         INTEGER NOT NULL,
    verse           INTEGER NOT NULL,
    color           TEXT NOT NULL DEFAULT 'yellow',
    created_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, version_id, book, chapter, verse, color)
);

-- ============================================================================
-- SCRIPTURE NOTES (per-user, per-verse) — Phase 2
-- ============================================================================

CREATE TABLE IF NOT EXISTS scripture_notes (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    version_id      TEXT NOT NULL REFERENCES bible_versions(id) ON DELETE CASCADE,
    book            INTEGER NOT NULL,
    chapter         INTEGER NOT NULL,
    verse           INTEGER NOT NULL,
    content         TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, version_id, book, chapter, verse)
);

-- ============================================================================
-- READING PLANS — Phase 3
-- ============================================================================

CREATE TABLE IF NOT EXISTS reading_plans (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    total_days      INTEGER NOT NULL DEFAULT 0,
    plan_type       TEXT NOT NULL DEFAULT 'sequential',
    is_builtin      BOOLEAN NOT NULL DEFAULT FALSE,
    created_by      TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS reading_plan_days (
    id              TEXT PRIMARY KEY,
    plan_id         TEXT NOT NULL REFERENCES reading_plans(id) ON DELETE CASCADE,
    day_number      INTEGER NOT NULL,
    title           TEXT,
    passages        JSONB NOT NULL DEFAULT '[]',
    created_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE(plan_id, day_number)
);

CREATE INDEX IF NOT EXISTS idx_reading_plan_days_plan ON reading_plan_days(plan_id);

CREATE TABLE IF NOT EXISTS reading_plan_progress (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    plan_id         TEXT NOT NULL REFERENCES reading_plans(id) ON DELETE CASCADE,
    current_day     INTEGER NOT NULL DEFAULT 1,
    started_at      TIMESTAMPTZ DEFAULT now(),
    last_read_at    TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    UNIQUE(user_id, plan_id)
);

-- ============================================================================
-- ENTITY TYPES (register with platform)
-- ============================================================================

INSERT INTO public.entity_types (prefix, name, id_format, table_name) VALUES
    ('bv',  'Bible Version',          'bv-',  'app_scriptures.bible_versions'),
    ('bb',  'Bible Book',             'bb-',  'app_scriptures.bible_books'),
    ('sbm', 'Scripture Bookmark',     'sbm-', 'app_scriptures.scripture_bookmarks'),
    ('shl', 'Scripture Highlight',    'shl-', 'app_scriptures.scripture_highlights'),
    ('sn',  'Scripture Note',         'sn-',  'app_scriptures.scripture_notes'),
    ('rpl', 'Reading Plan',           'rpl-', 'app_scriptures.reading_plans'),
    ('rpp', 'Reading Plan Progress',  'rpp-', 'app_scriptures.reading_plan_progress')
ON CONFLICT (prefix) DO NOTHING;
