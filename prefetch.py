"""Scripture Prefetch
=====================
Nightly job that pre-generates Summary, People, Places, and Pronouns for every
bookmarked chapter plus the next 3 chapters ahead in the same book.

This eliminates the 3-4 minute wait when a reader opens a fresh chapter,
since the LLM content will already be cached in chapter_summaries.
"""

import logging

logger = logging.getLogger(__name__)

LOOK_AHEAD = 5  # number of chapters ahead of each bookmark to pre-generate


def _chapters_ahead(version_id, book, chapter, count, books_cache):
    """Yield ``(book_number, chapter, book_info)`` for `count` chapters from (book, chapter).

    Rolls into the NEXT BOOK when the current one runs out. Preparation used to clamp to the
    end of the book — `min(base + LOOK_AHEAD + 1, chapter_count + 1)` — so a bookmark sitting
    on a book's last chapter prepared that one chapter and nothing else, which is exactly
    when a reader is about to need the next few. Nobody stops reading at a book boundary.

    Walks the version's own ordered book list rather than incrementing a number, so a
    version with gaps in its numbering, or one that does not carry the whole canon, ends
    cleanly instead of asking for books it has never heard of.
    """
    from apps.scriptures import data as _dl     # imported here, as the caller does

    books = books_cache.get(version_id)
    if books is None:
        try:
            books = _dl.get_books(version_id) or []
        except Exception:
            logger.error("SCRIPTURE_PREFETCH: cannot list books for version %s", version_id,
                         exc_info=True)
            books = []
        books_cache[version_id] = books

    idx = next((i for i, b in enumerate(books) if b.get("book_number") == book), None)
    if idx is None:
        return

    ch, yielded = chapter, 0
    while yielded < count and idx < len(books):
        info = books[idx]
        if ch > (info.get("chapter_count") or 0):
            idx += 1          # off the end of this book — carry on into the next
            ch = 1
            continue
        yield info.get("book_number"), ch, info
        yielded += 1
        ch += 1


def prefetch_scripture_summaries() -> str:
    """Walk all bookmarks, generate any missing summary/people/places/pronouns for
    the bookmarked chapter and the next LOOK_AHEAD chapters, continuing into the following
    book when one runs out.

    Returns a human-readable result string suitable for job logging.
    """
    from apps.scriptures import data as _dl
    from apps.scriptures.routes import (
        _generate_summary_llm,
        _generate_people_llm,
        _generate_places_llm,
        _generate_pronouns_llm,
        _get_summary_model,
    )

    bookmarks = _dl.get_all_bookmarks()
    if not bookmarks:
        logger.info("SCRIPTURE_PREFETCH: No bookmarks found — nothing to do")
        return "No bookmarks found — nothing to prefetch"

    model_name = _get_summary_model()
    generated = 0
    skipped = 0
    errors = 0

    # Deduplicate: multiple bookmarks could land on the same chapter — and now that the
    # walk crosses book boundaries, two bookmarks near a boundary overlap more often.
    seen: set[tuple] = set()
    books_cache: dict = {}

    for bm in bookmarks:
        version_id = bm["version_id"]
        start_book = bm["book"]
        base_chapter = bm["chapter"]

        # The version is fixed for a bookmark; the BOOK is not, now that the walk can
        # cross into the next one.
        try:
            version_info = _dl.get_version(version_id)
        except Exception as e:
            logger.error("SCRIPTURE_PREFETCH: Cannot load metadata for bookmark %s: %s", bm.get("id"), e)
            errors += 1
            continue
        version_name = version_info["name"] if version_info else "Bible"

        for book, chapter, book_info in _chapters_ahead(
                version_id, start_book, base_chapter, LOOK_AHEAD + 1, books_cache):
            book_name = (
                (book_info or {}).get("name_english")
                or (book_info or {}).get("name")
                or f"Book {book}"
            )
            key = (version_id, book, chapter)
            if key in seen:
                continue
            seen.add(key)

            try:
                verses = _dl.get_chapter_verses(version_id, book, chapter)
                if not verses:
                    logger.debug("SCRIPTURE_PREFETCH: No verses for %s ch%d — skipping", book_name, chapter)
                    continue

                chapter_text = " ".join(v["text"] for v in verses)

                # ── Summary ──────────────────────────────────────────────
                if _dl.get_chapter_summary(version_id, book, chapter):
                    skipped += 1
                else:
                    logger.info("SCRIPTURE_PREFETCH: Generating summary — %s ch%d", book_name, chapter)
                    text = _generate_summary_llm(book_name, chapter, chapter_text, version_name)
                    if text:
                        _dl.save_chapter_summary(version_id, book, chapter, text, model_name)
                        generated += 1

                # ── People ───────────────────────────────────────────────
                if _dl.get_chapter_people(version_id, book, chapter):
                    skipped += 1
                else:
                    logger.info("SCRIPTURE_PREFETCH: Generating people — %s ch%d", book_name, chapter)
                    text = _generate_people_llm(book_name, chapter, chapter_text, version_name)
                    if text:
                        _dl.save_chapter_people(version_id, book, chapter, text, model_name)
                        generated += 1

                # ── Places ───────────────────────────────────────────────
                if _dl.get_chapter_places(version_id, book, chapter):
                    skipped += 1
                else:
                    logger.info("SCRIPTURE_PREFETCH: Generating places — %s ch%d", book_name, chapter)
                    text = _generate_places_llm(book_name, chapter, chapter_text, version_name)
                    if text:
                        _dl.save_chapter_places(version_id, book, chapter, text, model_name)
                        generated += 1

                # —— Pronouns ————————————————————————————————————————————————
                if _dl.get_chapter_pronouns(version_id, book, chapter):
                    skipped += 1
                else:
                    logger.info("SCRIPTURE_PREFETCH: Generating pronouns — %s ch%d", book_name, chapter)
                    data = _generate_pronouns_llm(book_name, chapter, verses, version_name)
                    _dl.save_chapter_pronouns(version_id, book, chapter, data, model_name)
                    generated += 1

            except Exception as e:
                logger.error(
                    "SCRIPTURE_PREFETCH: Error on %s ch%d: %s", book_name, chapter, e, exc_info=True
                )
                errors += 1

    result = (
        f"Scripture prefetch complete — "
        f"{generated} generated, {skipped} already cached, {errors} errors "
        f"(checked {len(seen)} unique chapters across {len(bookmarks)} bookmark(s))"
    )
    logger.info("SCRIPTURE_PREFETCH: %s", result)
    return result
