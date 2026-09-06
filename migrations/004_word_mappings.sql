-- Reading aid: words the household prefers to see rendered differently.
--
-- A household reading a translation that says "Sovereign" may prefer to read "king". This
-- is DISPLAY ONLY — the stored verses are never altered, so search still finds the real
-- word and anything generated from the text still reads what the translation actually says.
--
-- Household-wide by design: one list everybody reads, so a chapter looks the same on the
-- television as it does on a phone. Applies to every version — a household that reads more
-- than one translation is asking for the same word, whichever edition it came from.

SET search_path TO app_scriptures, public;

CREATE TABLE IF NOT EXISTS word_mappings (
    id          TEXT PRIMARY KEY,
    source      TEXT NOT NULL,
    replacement TEXT NOT NULL,
    active      BOOLEAN NOT NULL DEFAULT true,
    created_by  TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One rule per word, whatever case it was typed in: two rules for the same word would make
-- which one wins depend on row order.
CREATE UNIQUE INDEX IF NOT EXISTS idx_word_mappings_source
    ON word_mappings (lower(source));
