"""Scriptures App — Schema-aware data layer
=============================================
All tables live in app_scriptures schema.
"""

import logging
import json
import uuid
from datetime import datetime, timezone

from app_platform.db import (
    fetch_one_in_schema,
    fetch_all_in_schema,
    execute_in_schema,
    execute_returning_in_schema,
)

logger = logging.getLogger(__name__)

SCHEMA = "app_scriptures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_one(query, params=()):
    return fetch_one_in_schema(SCHEMA, query, params)


def _fetch_all(query, params=()):
    return fetch_all_in_schema(SCHEMA, query, params)


def _execute(query, params=()):
    return execute_in_schema(SCHEMA, query, params)


def _execute_returning(query, params=()):
    return execute_returning_in_schema(SCHEMA, query, params)


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------

def get_all_versions() -> list[dict]:
    return _fetch_all("SELECT * FROM bible_versions ORDER BY imported_at")


def get_version(version_id: str) -> dict | None:
    return _fetch_one("SELECT * FROM bible_versions WHERE id = %s", (version_id,))


def get_version_by_abbrev(abbrev: str) -> dict | None:
    return _fetch_one("SELECT * FROM bible_versions WHERE abbreviation = %s", (abbrev.upper(),))


def get_default_version() -> dict | None:
    """Return the first (or only) loaded version."""
    return _fetch_one("SELECT * FROM bible_versions ORDER BY imported_at LIMIT 1")


# ---------------------------------------------------------------------------
# Books
# ---------------------------------------------------------------------------

def get_books(version_id: str) -> list[dict]:
    return _fetch_all(
        "SELECT * FROM bible_books WHERE version_id = %s ORDER BY book_number",
        (version_id,),
    )


def get_book(version_id: str, book_number: int) -> dict | None:
    return _fetch_one(
        "SELECT * FROM bible_books WHERE version_id = %s AND book_number = %s",
        (version_id, book_number),
    )


# ---------------------------------------------------------------------------
# Verses (read chapter)
# ---------------------------------------------------------------------------

def get_chapter_verses(version_id: str, book: int, chapter: int) -> list[dict]:
    return _fetch_all(
        """SELECT verse, text, text_html
           FROM bible_verses
           WHERE version_id = %s AND book = %s AND chapter = %s
           ORDER BY verse""",
        (version_id, book, chapter),
    )


def get_verse(version_id: str, book: int, chapter: int, verse: int) -> dict | None:
    return _fetch_one(
        """SELECT verse, text, text_html
           FROM bible_verses
           WHERE version_id = %s AND book = %s AND chapter = %s AND verse = %s""",
        (version_id, book, chapter, verse),
    )


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search_verses(
    version_id: str,
    query: str,
    book: int | None = None,
    testament: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Full-text search using trigram similarity."""
    conditions = ["v.version_id = %s", "v.text ILIKE %s"]
    params: list = [version_id, f"%{query}%"]

    if book is not None:
        conditions.append("v.book = %s")
        params.append(book)

    if testament:
        if testament.upper() == "OT":
            conditions.append("v.book <= 39")
        elif testament.upper() == "NT":
            conditions.append("v.book >= 40")

    params.extend([limit, offset])

    sql = f"""
        SELECT v.book, v.chapter, v.verse, v.text,
               b.name AS book_name, b.name_english AS book_name_english,
               b.abbreviation AS book_abbrev
        FROM bible_verses v
        JOIN bible_books b ON b.version_id = v.version_id AND b.book_number = v.book
        WHERE {' AND '.join(conditions)}
        ORDER BY v.book, v.chapter, v.verse
        LIMIT %s OFFSET %s
    """
    return _fetch_all(sql, tuple(params))


def count_search_results(
    version_id: str,
    query: str,
    book: int | None = None,
    testament: str | None = None,
) -> int:
    conditions = ["version_id = %s", "text ILIKE %s"]
    params: list = [version_id, f"%{query}%"]

    if book is not None:
        conditions.append("book = %s")
        params.append(book)
    if testament:
        if testament.upper() == "OT":
            conditions.append("book <= 39")
        elif testament.upper() == "NT":
            conditions.append("book >= 40")

    row = _fetch_one(
        f"SELECT COUNT(*) AS cnt FROM bible_verses WHERE {' AND '.join(conditions)}",
        tuple(params),
    )
    return row["cnt"] if row else 0


# ---------------------------------------------------------------------------
# Chapter Summaries
# ---------------------------------------------------------------------------

def get_chapter_summary(version_id: str, book: int, chapter: int) -> dict | None:
    row = _fetch_one(
        """SELECT summary, model, generated_at
           FROM chapter_summaries
           WHERE version_id = %s AND book = %s AND chapter = %s""",
        (version_id, book, chapter),
    )
    if row and row.get("summary"):
        return row
    return None


def save_chapter_summary(version_id: str, book: int, chapter: int, summary: str, model: str):
    _execute(
        """INSERT INTO chapter_summaries (version_id, book, chapter, summary, model, generated_at)
           VALUES (%s, %s, %s, %s, %s, now())
           ON CONFLICT (version_id, book, chapter) DO UPDATE
           SET summary = EXCLUDED.summary, model = EXCLUDED.model, generated_at = now()""",
        (version_id, book, chapter, summary, model),
    )


def clear_chapter_field(version_id: str, book: int, chapter: int, field: str):
    """Clear a single cached field (summary, people, places, or pronouns) to force regeneration."""
    allowed = {"summary", "people", "places", "pronouns"}
    if field not in allowed:
        return
    if field == "summary":
        _execute(
            "UPDATE chapter_summaries SET summary = '', model = '', generated_at = now() "
            "WHERE version_id = %s AND book = %s AND chapter = %s",
            (version_id, book, chapter),
        )
    else:
        model_col = f"{field}_model"
        at_col = f"{field}_at"
        _execute(
            f"UPDATE chapter_summaries SET {field} = NULL, {model_col} = NULL, {at_col} = NULL "
            f"WHERE version_id = %s AND book = %s AND chapter = %s",
            (version_id, book, chapter),
        )


# ---------------------------------------------------------------------------
# Chapter People
# ---------------------------------------------------------------------------

def get_chapter_people(version_id: str, book: int, chapter: int) -> dict | None:
    row = _fetch_one(
        """SELECT people, people_model, people_at
           FROM chapter_summaries
           WHERE version_id = %s AND book = %s AND chapter = %s""",
        (version_id, book, chapter),
    )
    if row and row.get("people"):
        return row
    return None


def save_chapter_people(version_id: str, book: int, chapter: int, people: str, model: str):
    _execute(
        """INSERT INTO chapter_summaries (version_id, book, chapter, summary, people, people_model, people_at)
           VALUES (%s, %s, %s, '', %s, %s, now())
           ON CONFLICT (version_id, book, chapter) DO UPDATE
           SET people = EXCLUDED.people, people_model = EXCLUDED.people_model, people_at = now()""",
        (version_id, book, chapter, people, model),
    )


# ---------------------------------------------------------------------------
# Chapter Places
# ---------------------------------------------------------------------------

def get_chapter_places(version_id: str, book: int, chapter: int) -> dict | None:
    row = _fetch_one(
        """SELECT places, places_model, places_at
           FROM chapter_summaries
           WHERE version_id = %s AND book = %s AND chapter = %s""",
        (version_id, book, chapter),
    )
    if row and row.get("places"):
        return row
    return None


def save_chapter_places(version_id: str, book: int, chapter: int, places: str, model: str):
    _execute(
        """INSERT INTO chapter_summaries (version_id, book, chapter, summary, places, places_model, places_at)
           VALUES (%s, %s, %s, '', %s, %s, now())
           ON CONFLICT (version_id, book, chapter) DO UPDATE
           SET places = EXCLUDED.places, places_model = EXCLUDED.places_model, places_at = now()""",
        (version_id, book, chapter, places, model),
    )


# ---------------------------------------------------------------------------
# Chapter Pronouns
# ---------------------------------------------------------------------------

def get_chapter_pronouns(version_id: str, book: int, chapter: int) -> dict | None:
    row = _fetch_one(
        """SELECT pronouns, pronouns_model, pronouns_at
           FROM chapter_summaries
           WHERE version_id = %s AND book = %s AND chapter = %s""",
        (version_id, book, chapter),
    )
    if row and row.get("pronouns") is not None:
        raw = row.get("pronouns")
        if isinstance(raw, str):
            try:
                row["pronouns"] = json.loads(raw)
            except Exception:
                logger.exception("Failed to parse cached pronouns for %s %s %s", version_id, book, chapter)
                return None
        return row
    return None


def save_chapter_pronouns(version_id: str, book: int, chapter: int, pronouns: list[dict], model: str):
    payload = json.dumps(pronouns, ensure_ascii=False)
    _execute(
        """INSERT INTO chapter_summaries (version_id, book, chapter, summary, pronouns, pronouns_model, pronouns_at)
           VALUES (%s, %s, %s, '', %s, %s, now())
           ON CONFLICT (version_id, book, chapter) DO UPDATE
           SET pronouns = EXCLUDED.pronouns, pronouns_model = EXCLUDED.pronouns_model, pronouns_at = now()""",
        (version_id, book, chapter, payload, model),
    )


# ---------------------------------------------------------------------------
# Bookmarks (named reading positions — shared)
# ---------------------------------------------------------------------------

def get_all_bookmarks() -> list[dict]:
    return _fetch_all(
        """SELECT bm.*, b.name AS book_name, b.name_english AS book_name_english
           FROM scripture_bookmarks bm
           JOIN bible_books b ON b.version_id = bm.version_id AND b.book_number = bm.book
           ORDER BY bm.updated_at DESC""",
    )


def get_bookmark(bookmark_id: str) -> dict | None:
    return _fetch_one(
        "SELECT * FROM scripture_bookmarks WHERE id = %s",
        (bookmark_id,),
    )


def create_bookmark(name: str, version_id: str, book: int, chapter: int,
                    color: str | None = None, created_by: str = "") -> dict:
    bm_id = f"sbm-{uuid.uuid4().hex[:8]}"
    _execute(
        """INSERT INTO scripture_bookmarks (id, name, version_id, book, chapter, color, created_by, updated_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, now())""",
        (bm_id, name, version_id, book, chapter, color, created_by),
    )
    return get_bookmark(bm_id)


def update_bookmark(bookmark_id: str, updates: dict) -> bool:
    allowed = {"name", "color", "book", "chapter", "updated_by"}
    sets, vals = [], []
    for key, val in updates.items():
        if key not in allowed:
            continue
        sets.append(f"{key} = %s")
        vals.append(val)
    if not sets:
        return False
    sets.append("updated_at = now()")
    vals.append(bookmark_id)
    return _execute(
        f"UPDATE scripture_bookmarks SET {', '.join(sets)} WHERE id = %s",
        tuple(vals),
    ) > 0


def move_bookmark(bookmark_id: str, book: int, chapter: int, user_id: str = "") -> bool:
    return _execute(
        """UPDATE scripture_bookmarks
           SET book = %s, chapter = %s, updated_by = %s, updated_at = now()
           WHERE id = %s""",
        (book, chapter, user_id, bookmark_id),
    ) > 0


def delete_bookmark(bookmark_id: str) -> bool:
    return _execute("DELETE FROM scripture_bookmarks WHERE id = %s", (bookmark_id,)) > 0
