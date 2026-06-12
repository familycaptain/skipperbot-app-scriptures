"""Scriptures App API Routes
==============================
FastAPI router for Bible reading, search, and bookmarks.
Mounted at /api/apps/scriptures/ by the app platform loader.
"""

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Request

from app_platform.auth import current_principal
from apps.scriptures import data as _dl

router = APIRouter()
logger = logging.getLogger(__name__)


def _actor(request: Request) -> str:
    """The authenticated actor's name. Auth is unconditional, so a verified
    principal is always present; the client-supplied value is never trusted."""
    p = current_principal(request)
    return (p["name"] if p else "").lower().strip()


# --- Versions ---

@router.get("/versions")
async def api_list_versions():
    versions = await asyncio.to_thread(_dl.get_all_versions)
    return {"versions": versions, "count": len(versions)}


@router.get("/versions/{version_id}")
async def api_get_version(version_id: str):
    ver = await asyncio.to_thread(_dl.get_version, version_id)
    if not ver:
        raise HTTPException(404, "Version not found")
    books = await asyncio.to_thread(_dl.get_books, version_id)
    return {**ver, "books": books}


# --- Books ---

@router.get("/books")
async def api_list_books(version_id: str = ""):
    if not version_id:
        ver = await asyncio.to_thread(_dl.get_default_version)
        if not ver:
            raise HTTPException(404, "No Bible versions loaded")
        version_id = ver["id"]
    books = await asyncio.to_thread(_dl.get_books, version_id)
    return {"books": books, "version_id": version_id, "count": len(books)}


# --- Read Chapter ---

@router.get("/read")
async def api_read_chapter(version_id: str = "", book: int = 1, chapter: int = 1):
    if not version_id:
        ver = await asyncio.to_thread(_dl.get_default_version)
        if not ver:
            raise HTTPException(404, "No Bible versions loaded")
        version_id = ver["id"]

    verses = await asyncio.to_thread(_dl.get_chapter_verses, version_id, book, chapter)
    if not verses:
        raise HTTPException(404, f"No verses found for book={book} chapter={chapter}")

    book_info = await asyncio.to_thread(_dl.get_book, version_id, book)
    summary_row = await asyncio.to_thread(_dl.get_chapter_summary, version_id, book, chapter)
    people_row = await asyncio.to_thread(_dl.get_chapter_people, version_id, book, chapter)
    places_row = await asyncio.to_thread(_dl.get_chapter_places, version_id, book, chapter)
    pronouns_row = await asyncio.to_thread(_dl.get_chapter_pronouns, version_id, book, chapter)
    bookmarks = await asyncio.to_thread(_dl.get_all_bookmarks)

    return {
        "version_id": version_id,
        "book": book,
        "chapter": chapter,
        "book_info": book_info,
        "verses": verses,
        "summary": summary_row["summary"] if summary_row else None,
        "people": people_row["people"] if people_row else None,
        "places": places_row["places"] if places_row else None,
        "pronouns": pronouns_row["pronouns"] if pronouns_row else None,
        "bookmarks": bookmarks,
        "chapter_count": book_info["chapter_count"] if book_info else 0,
    }


# --- Single Verse ---

@router.get("/verse")
async def api_get_verse(version_id: str, book: int, chapter: int, verse: int):
    v = await asyncio.to_thread(_dl.get_verse, version_id, book, chapter, verse)
    if not v:
        raise HTTPException(404, "Verse not found")
    return v


# --- Chapter Summary ---

@router.post("/summary")
async def api_generate_summary(request: Request):
    """Generate (or return cached) LLM chapter summary."""
    body = await request.json()
    version_id = body.get("version_id", "")
    book = body.get("book", 1)
    chapter = body.get("chapter", 1)

    if not version_id:
        ver = await asyncio.to_thread(_dl.get_default_version)
        if not ver:
            raise HTTPException(404, "No Bible versions loaded")
        version_id = ver["id"]

    # Check cache first
    existing = await asyncio.to_thread(_dl.get_chapter_summary, version_id, book, chapter)
    if existing:
        return {"summary": existing["summary"], "cached": True}

    # Generate via LLM
    verses = await asyncio.to_thread(_dl.get_chapter_verses, version_id, book, chapter)
    if not verses:
        raise HTTPException(404, "No verses found for this chapter")

    book_info = await asyncio.to_thread(_dl.get_book, version_id, book)
    book_name = book_info["name_english"] if book_info else f"Book {book}"
    version_info = await asyncio.to_thread(_dl.get_version, version_id)
    version_name = version_info["name"] if version_info else "Bible"

    chapter_text = " ".join(v["text"] for v in verses)

    try:
        summary = await asyncio.to_thread(_generate_summary_llm, book_name, chapter, chapter_text, version_name)
    except Exception as e:
        logger.exception("Summary generation failed")
        raise HTTPException(500, f"Failed to generate summary: {e}")

    if not summary:
        raise HTTPException(500, "Failed to generate summary — empty response")

    # Cache only successful summaries
    model_name = _get_summary_model()
    await asyncio.to_thread(_dl.save_chapter_summary, version_id, book, chapter, summary, model_name)

    return {"summary": summary, "cached": False}


def _get_summary_model() -> str:
    from config import DUMB_MODEL
    return DUMB_MODEL


def _generate_summary_llm(book_name: str, chapter: int, chapter_text: str, version_name: str = "Bible") -> str:
    """Call OpenAI to generate a chapter summary."""
    from config import openai_client, DUMB_MODEL

    prompt = (
        f"Summarize {book_name} chapter {chapter} from the {version_name}.\n\n"
        f"IMPORTANT FORMATTING RULE: Separate every paragraph with a blank line "
        f"(two newlines). Do NOT run paragraphs together.\n\n"
        f"Write your response in a style consistent with the {version_name} — "
        f"use the same names, spellings, and terminology that appear in this translation.\n\n"
        f"Write several paragraphs covering the chapter's narrative, key events, "
        f"prayers, speeches, and actions. Each paragraph should focus on a distinct "
        f"section or theme of the chapter. Be factual and thorough.\n\n"
        f"End with a 'Key Themes:' section listing 3-6 themes, each on its own line.\n\n"
        f"Do not add personal interpretation or devotional commentary. "
        f"Do not include a heading or title line. "
        f"Use the names as they appear in the text (e.g. Yahweh, Elohim).\n\n"
        f"Chapter text:\n{chapter_text}"
    )

    try:
        resp = openai_client.chat.completions.create(
            model=DUMB_MODEL,
            messages=[
                {"role": "system", "content": "You are a Bible study assistant. Provide clear, concise chapter summaries."},
                {"role": "user", "content": prompt},
            ],
            max_completion_tokens=16000,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        logger.exception("Failed to generate summary for %s %d", book_name, chapter)
        raise


# --- Chapter People ---

@router.post("/people")
async def api_generate_people(request: Request):
    """Generate (or return cached) LLM people list for a chapter."""
    try:
        body = await request.json()
        version_id = body.get("version_id", "")
        book = body.get("book", 1)
        chapter = body.get("chapter", 1)

        if not version_id:
            ver = await asyncio.to_thread(_dl.get_default_version)
            if not ver:
                raise HTTPException(404, "No Bible versions loaded")
            version_id = ver["id"]

        existing = await asyncio.to_thread(_dl.get_chapter_people, version_id, book, chapter)
        if existing:
            return {"people": existing["people"], "cached": True}

        verses = await asyncio.to_thread(_dl.get_chapter_verses, version_id, book, chapter)
        if not verses:
            raise HTTPException(404, "No verses found for this chapter")

        book_info = await asyncio.to_thread(_dl.get_book, version_id, book)
        book_name = book_info["name_english"] if book_info else f"Book {book}"
        version_info = await asyncio.to_thread(_dl.get_version, version_id)
        version_name = version_info["name"] if version_info else "Bible"
        chapter_text = " ".join(v["text"] for v in verses)

        result = await asyncio.to_thread(_generate_people_llm, book_name, chapter, chapter_text, version_name)

        if not result:
            raise HTTPException(500, "Failed to generate people — empty response")

        model_name = _get_summary_model()
        await asyncio.to_thread(_dl.save_chapter_people, version_id, book, chapter, result, model_name)
        return {"people": result, "cached": False}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("People endpoint failed")
        raise HTTPException(500, f"People generation error: {e}")


def _generate_people_llm(book_name: str, chapter: int, chapter_text: str, version_name: str = "Bible") -> str:
    """Call OpenAI to generate a people list for a chapter."""
    from config import openai_client, DUMB_MODEL

    prompt = (
        f"List every person mentioned in {book_name} chapter {chapter} from the {version_name}.\n\n"
        f"IMPORTANT FORMATTING RULE: Separate every paragraph with a blank line "
        f"(two newlines). Do NOT run paragraphs together.\n\n"
        f"Write your response in a style consistent with the {version_name} — "
        f"use the same names, spellings, and terminology that appear in this translation.\n\n"
        f"For each person, write one paragraph that includes:\n"
        f"- Their name (bold using **Name**)\n"
        f"- Who they were (their role, lineage, or title)\n"
        f"- What they did or what happened to them in this chapter\n"
        f"- Why they are significant in the broader narrative\n\n"
        f"Include every named individual AND identifiable groups treated as characters "
        f"(e.g. 'the sons of Israel', 'the Levites'). "
        f"If a person is referred to by title only (e.g. 'the king'), identify them by name if possible.\n\n"
        f"Do not add personal interpretation or devotional commentary. "
        f"Do not include a heading or title line. "
        f"Use the names as they appear in the text.\n\n"
        f"Chapter text:\n{chapter_text}"
    )

    try:
        resp = openai_client.chat.completions.create(
            model=DUMB_MODEL,
            messages=[
                {"role": "system", "content": "You are a Bible study assistant. Provide thorough, factual analysis."},
                {"role": "user", "content": prompt},
            ],
            max_completion_tokens=16000,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        logger.exception("Failed to generate people for %s %d", book_name, chapter)
        raise


# --- Chapter Places ---

@router.post("/places")
async def api_generate_places(request: Request):
    """Generate (or return cached) LLM places list for a chapter."""
    try:
        body = await request.json()
        version_id = body.get("version_id", "")
        book = body.get("book", 1)
        chapter = body.get("chapter", 1)

        if not version_id:
            ver = await asyncio.to_thread(_dl.get_default_version)
            if not ver:
                raise HTTPException(404, "No Bible versions loaded")
            version_id = ver["id"]

        existing = await asyncio.to_thread(_dl.get_chapter_places, version_id, book, chapter)
        if existing:
            return {"places": existing["places"], "cached": True}

        verses = await asyncio.to_thread(_dl.get_chapter_verses, version_id, book, chapter)
        if not verses:
            raise HTTPException(404, "No verses found for this chapter")

        book_info = await asyncio.to_thread(_dl.get_book, version_id, book)
        book_name = book_info["name_english"] if book_info else f"Book {book}"
        version_info = await asyncio.to_thread(_dl.get_version, version_id)
        version_name = version_info["name"] if version_info else "Bible"
        chapter_text = " ".join(v["text"] for v in verses)

        result = await asyncio.to_thread(_generate_places_llm, book_name, chapter, chapter_text, version_name)

        if not result:
            raise HTTPException(500, "Failed to generate places — empty response")

        model_name = _get_summary_model()
        await asyncio.to_thread(_dl.save_chapter_places, version_id, book, chapter, result, model_name)
        return {"places": result, "cached": False}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Places endpoint failed")
        raise HTTPException(500, f"Places generation error: {e}")


def _generate_places_llm(book_name: str, chapter: int, chapter_text: str, version_name: str = "Bible") -> str:
    """Call OpenAI to generate a places list for a chapter."""
    from config import openai_client, DUMB_MODEL

    prompt = (
        f"List every place mentioned or implied in {book_name} chapter {chapter} from the {version_name}.\n\n"
        f"IMPORTANT FORMATTING RULE: Separate every paragraph with a blank line "
        f"(two newlines). Do NOT run paragraphs together.\n\n"
        f"Write your response in a style consistent with the {version_name} — "
        f"use the same names, spellings, and terminology that appear in this translation.\n\n"
        f"For each place, write one paragraph that includes:\n"
        f"- The place name (bold using **Name**)\n"
        f"- Where it is (geographic region, modern-day location if known)\n"
        f"- Its significance in this chapter — what happened there or why it is mentioned\n"
        f"- Any broader biblical significance\n\n"
        f"Include:\n"
        f"- Places explicitly named in the text\n"
        f"- The implied or stated setting where the events of this chapter take place\n"
        f"- Regions, cities, rivers, mountains, temples, or other landmarks\n\n"
        f"Do not add personal interpretation or devotional commentary. "
        f"Do not include a heading or title line. "
        f"Use the names as they appear in the text.\n\n"
        f"Chapter text:\n{chapter_text}"
    )

    try:
        resp = openai_client.chat.completions.create(
            model=DUMB_MODEL,
            messages=[
                {"role": "system", "content": "You are a Bible study assistant. Provide thorough, factual analysis."},
                {"role": "user", "content": prompt},
            ],
            max_completion_tokens=16000,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        logger.exception("Failed to generate places for %s %d", book_name, chapter)
        raise


# --- Chapter Pronouns ---

@router.post("/pronouns")
async def api_generate_pronouns(request: Request):
    """Generate (or return cached) pronoun resolution data for a chapter."""
    try:
        body = await request.json()
        version_id = body.get("version_id", "")
        book = body.get("book", 1)
        chapter = body.get("chapter", 1)

        if not version_id:
            ver = await asyncio.to_thread(_dl.get_default_version)
            if not ver:
                raise HTTPException(404, "No Bible versions loaded")
            version_id = ver["id"]

        existing = await asyncio.to_thread(_dl.get_chapter_pronouns, version_id, book, chapter)
        if existing:
            return {"pronouns": existing["pronouns"], "cached": True}

        verses = await asyncio.to_thread(_dl.get_chapter_verses, version_id, book, chapter)
        if not verses:
            raise HTTPException(404, "No verses found for this chapter")

        book_info = await asyncio.to_thread(_dl.get_book, version_id, book)
        book_name = book_info["name_english"] if book_info else f"Book {book}"
        version_info = await asyncio.to_thread(_dl.get_version, version_id)
        version_name = version_info["name"] if version_info else "Bible"

        result = await asyncio.to_thread(_generate_pronouns_llm, book_name, chapter, verses, version_name)
        model_name = _get_summary_model()
        await asyncio.to_thread(_dl.save_chapter_pronouns, version_id, book, chapter, result, model_name)
        return {"pronouns": result, "cached": False}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Pronouns endpoint failed")
        raise HTTPException(500, f"Pronoun generation error: {e}")


def _generate_pronouns_llm(book_name: str, chapter: int, verses: list[dict], version_name: str = "Bible") -> list[dict]:
    """Call OpenAI to resolve pronouns for each verse in a chapter."""
    from config import openai_client, DUMB_MODEL

    chapter_text = "\n".join(f"{v['verse']}. {v['text']}" for v in verses)
    prompt = (
        f"Resolve pronouns in {book_name} chapter {chapter} from the {version_name}.\n\n"
        f"Return JSON only. No markdown. No explanation.\n\n"
        f"Use this exact schema:\n"
        f'{{"verses":[{{"verse":1,"instances":[{{"text":"he","replacement":"Menashsheh"}}]}}]}}\n\n'
        f"Rules:\n"
        f"- Include every personal pronoun, possessive pronoun/determiner, and reflexive pronoun that refers to someone or something in context.\n"
        f"- Include capitalized divine pronouns when they appear (for example He, Him, His) and resolve them the same way.\n"
        f"- Do not include articles or non-referential words such as 'the' or 'a'.\n"
        f"- Group results by verse number.\n"
        f"- Inside each verse, list instances in exact left-to-right order.\n"
        f"- `text` must be the exact pronoun text from the verse, preserving case.\n"
        f"- `replacement` must be the short text that should replace that single pronoun in the verse, using names/spellings from this translation.\n"
        f"- For possessives, make `replacement` possessive as it should appear inline (for example `Dawiḏ's`, `יהוה's`, `the priests'`).\n"
        f"- Keep replacements concise. Do not explain significance.\n"
        f"- If a verse has no resolvable pronouns, omit that verse from the JSON.\n\n"
        f"Chapter text:\n{chapter_text}"
    )

    try:
        resp = openai_client.chat.completions.create(
            model=DUMB_MODEL,
            messages=[
                {"role": "system", "content": "You are a Bible study assistant. Resolve pronouns accurately and return strict JSON only."},
                {"role": "user", "content": prompt},
            ],
            max_completion_tokens=16000,
            response_format={"type": "json_object"},
        )
        raw = (resp.choices[0].message.content or "").strip()
        data = json.loads(raw)
        verses_out = data.get("verses") if isinstance(data, dict) else None
        if not isinstance(verses_out, list):
            raise ValueError("Pronoun response did not contain a 'verses' array")

        normalized: list[dict] = []
        for verse_entry in verses_out:
            if not isinstance(verse_entry, dict):
                continue
            verse_num = verse_entry.get("verse")
            instances = verse_entry.get("instances")
            if not isinstance(verse_num, int) or not isinstance(instances, list):
                continue
            clean_instances = []
            for item in instances:
                if not isinstance(item, dict):
                    continue
                text = str(item.get("text", "")).strip()
                replacement = str(item.get("replacement", "")).strip()
                if text and replacement:
                    clean_instances.append({"text": text, "replacement": replacement})
            if clean_instances:
                normalized.append({"verse": verse_num, "instances": clean_instances})
        return normalized
    except Exception:
        logger.exception("Failed to generate pronouns for %s %d", book_name, chapter)
        raise


# --- Regenerate (clear cache for a field) ---

@router.post("/regenerate")
async def api_regenerate(request: Request):
    """Clear cached LLM content for a field (summary/people/places/pronouns) so it regenerates on next request."""
    body = await request.json()
    version_id = body.get("version_id", "")
    book = body.get("book", 1)
    chapter = body.get("chapter", 1)
    field = body.get("field", "")

    if field not in ("summary", "people", "places", "pronouns"):
        raise HTTPException(400, "field must be summary, people, places, or pronouns")

    if not version_id:
        ver = await asyncio.to_thread(_dl.get_default_version)
        if not ver:
            raise HTTPException(404, "No Bible versions loaded")
        version_id = ver["id"]

    await asyncio.to_thread(_dl.clear_chapter_field, version_id, book, chapter, field)
    return {"ok": True, "cleared": field}


# --- Search ---

@router.get("/search")
async def api_search(
    q: str = "",
    version_id: str = "",
    book: int | None = None,
    testament: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    if not q or len(q) < 3:
        raise HTTPException(400, "Search query must be at least 3 characters")

    if not version_id:
        ver = await asyncio.to_thread(_dl.get_default_version)
        if not ver:
            raise HTTPException(404, "No Bible versions loaded")
        version_id = ver["id"]

    results = await asyncio.to_thread(
        _dl.search_verses, version_id, q, book, testament, limit, offset
    )
    total = await asyncio.to_thread(
        _dl.count_search_results, version_id, q, book, testament
    )
    return {"results": results, "total": total, "query": q}


# --- Bookmarks ---

@router.get("/bookmarks")
async def api_list_bookmarks():
    bookmarks = await asyncio.to_thread(_dl.get_all_bookmarks)
    return {"bookmarks": bookmarks, "count": len(bookmarks)}


@router.post("/bookmarks")
async def api_create_bookmark(request: Request):
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(400, "Bookmark name is required")

    version_id = body.get("version_id", "")
    if not version_id:
        ver = await asyncio.to_thread(_dl.get_default_version)
        if not ver:
            raise HTTPException(404, "No Bible versions loaded")
        version_id = ver["id"]

    bm = await asyncio.to_thread(
        _dl.create_bookmark,
        name=name,
        version_id=version_id,
        book=body.get("book", 1),
        chapter=body.get("chapter", 1),
        color=body.get("color"),
        created_by=_actor(request),
    )
    return bm


@router.patch("/bookmarks/{bookmark_id}")
async def api_update_bookmark(bookmark_id: str, request: Request):
    body = await request.json()
    ok = await asyncio.to_thread(_dl.update_bookmark, bookmark_id, body)
    if not ok:
        raise HTTPException(404, "Bookmark not found")
    return await asyncio.to_thread(_dl.get_bookmark, bookmark_id)


@router.post("/bookmarks/{bookmark_id}/move")
async def api_move_bookmark(bookmark_id: str, request: Request):
    body = await request.json()
    book = body.get("book")
    chapter = body.get("chapter")
    user_id = _actor(request)
    if book is None or chapter is None:
        raise HTTPException(400, "book and chapter are required")
    ok = await asyncio.to_thread(_dl.move_bookmark, bookmark_id, book, chapter, user_id)
    if not ok:
        raise HTTPException(404, "Bookmark not found")
    return await asyncio.to_thread(_dl.get_bookmark, bookmark_id)


@router.delete("/bookmarks/{bookmark_id}")
async def api_delete_bookmark(bookmark_id: str):
    ok = await asyncio.to_thread(_dl.delete_bookmark, bookmark_id)
    if not ok:
        raise HTTPException(404, "Bookmark not found")
    return {"ok": True}
