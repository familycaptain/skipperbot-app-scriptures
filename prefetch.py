"""Scripture Prefetch
=====================
Nightly job that pre-generates Summary, People, Places, and Pronouns for every
bookmarked chapter plus the next 3 chapters ahead in the same book.

This eliminates the 3-4 minute wait when a reader opens a fresh chapter,
since the LLM content will already be cached in chapter_summaries.
"""

import logging

logger = logging.getLogger(__name__)

LOOK_AHEAD = 3  # number of chapters ahead of each bookmark to pre-generate


def prefetch_scripture_summaries() -> str:
    """Walk all bookmarks, generate any missing summary/people/places/pronouns for
    the bookmarked chapter and the next LOOK_AHEAD chapters in the same book.

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

    # Deduplicate: multiple bookmarks could land on the same chapter
    seen: set[tuple] = set()

    for bm in bookmarks:
        version_id = bm["version_id"]
        book = bm["book"]
        base_chapter = bm["chapter"]

        # Resolve book/version metadata once per bookmark
        try:
            book_info = _dl.get_book(version_id, book)
            version_info = _dl.get_version(version_id)
        except Exception as e:
            logger.error("SCRIPTURE_PREFETCH: Cannot load metadata for bookmark %s: %s", bm.get("id"), e)
            errors += 1
            continue

        chapter_count = book_info["chapter_count"] if book_info else base_chapter
        version_name = version_info["name"] if version_info else "Bible"
        book_name = (
            (book_info or {}).get("name_english")
            or bm.get("book_name_english")
            or bm.get("book_name")
            or f"Book {book}"
        )

        for chapter in range(base_chapter, min(base_chapter + LOOK_AHEAD + 1, chapter_count + 1)):
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
