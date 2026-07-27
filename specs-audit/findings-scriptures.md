# Findings — scriptures

Survey only; nothing fixed. Corpus 0 → 63 records (written from scratch). Items marked **VERIFIED**
were confirmed independently by the PM.

## Translation defaults — NOT a licensing concern

**Operator ruling:** the repo does not ship or supply TS2009 text. `import_bible.py` is an *importer*; the
household supplies its own PDF. There is no redistribution, so there is no licensing exposure and this is
not a defect. An earlier draft of this file called it one — that was wrong and is struck.

What remains is small and separable from licensing:

- `ui/ScripturesApp.jsx:106` prefers TS2009 by abbreviation
  (`data.versions.find(v => v.abbreviation === "TS2009")`), so one household's edition is the shipped
  default preference for every install (brief rule 5 — encode no single household as product intent). A
  reasonable fix is to prefer whatever the install actually holds, or the first available version.
- `bible_versions` has no field for a translation's own copyright or attribution line, so an install that
  imports a translation requiring displayed attribution has nowhere to put it. Optional, and the
  household's call — noted only because the schema forecloses it.

## Chat surface promised but absent

1. `manifest.yaml` declares a `tool_category` with 22 routing keywords ("show me Psalm 23", "torah
   portion", "parashah"), and `help.md` documents chat workflows in detail — but there is **no `tools.py`
   and no `guide.md`** in the repo. Without `tools.py` the app exposes nothing to chat, so the keywords
   pull conversation toward an app that has nothing to offer and every chat example in `help.md` is
   unachievable.

2. **Nothing in the product parses a scripture reference.** The only reference parser is
   `import_bible.py::_VERSE_REF_RE`, used solely for the TS2009 PDF. The REST API takes numeric
   `book`/`chapter`/`verse` only. Nothing resolves "Psalm 23", "Ps 23:1-6", a range, an abbreviation or a
   book name — so "what happens to an ambiguous reference" has no answer, because references are never
   parsed. `data.py::get_version_by_abbrev`, the one abbreviation resolver, is dead code.

3. `routes.py::api_read_chapter` defaults `book: int = 1, chapter: int = 1`, and `/summary`, `/people`,
   `/places`, `/pronouns`, `/regenerate` all use `body.get("book", 1)`. **A missing or mistyped parameter
   silently returns Genesis 1 instead of an error** — for an app where the wrong passage is a serious
   failure, that should 400.

## Passage completeness — the serious ones

4. **A network import silently drops chapters.** `import_from_getbible` retries a chapter three times,
   then `logger.warning`s and continues. The chapter is absent, `book_chapters[book].add(ch)` is skipped,
   and `_insert_into_postgres` sets `chapter_count = len(book_chapters[book_num])`. So a 21-chapter book
   missing chapter 7 reports `chapter_count = 20`: the picker offers 1–20, chapter 7 renders blank, **and
   chapter 21 exists in the database but is unreachable.** `verse_count` records the short count with
   nothing marking it short. `_CHAPTER_COUNTS` is already in the module and is used only to drive the
   fetch loop, never as post-import validation.

5. **A missing chapter is indistinguishable from a blank screen.** `api_read_chapter` returns 404 with no
   verses; `ScripturesApp.loadChapter` does not check `res.ok`, so `data.verses` is undefined and
   `setVerses([])` leaves the reader looking at a chapter heading above nothing. With §4, **a truncated
   Bible looks exactly like an empty one.**

6. `chapter_count` is `len(set of chapters that arrived)` on every import path. `max(chapters)` would at
   least expose a gap; `len()` hides it and makes the tail unreachable.

7. **PDF import assembles verse text by heuristic with no check.** `import_from_pdf` takes
   `full_text[m.end():next_match.start()]`, so running heads, page numbers, column artifacts and anything
   else between two references is concatenated into the preceding verse, and the final match absorbs all
   trailing back matter to the end of the document. `raw.replace("\n", " ")` also collapses genuine hard
   breaks (poetry). No per-chapter verse count is validated.

8. `import_from_pdf` hardcodes a four-page front-matter skip (`for i in range(4, len(doc))`) with no
   assertion that page 5 starts at Genesis 1:1 — silently wrong for any other printing.

9. **Strong's numbers are declared then discarded.** `import_mybible_file` records `has_strongs` from the
   module's `Details` table, but `gbf._STANDALONE_RE` strips `WG…`/`WH…`/`WT…` from both copies. A version
   can report `has_strongs = true` while holding none.

## What leaves the install

10. **Chapter text is sent to an external model with no consent gate and no off switch.**
    `_generate_summary_llm` / `_people_llm` / `_places_llm` / `_pronouns_llm` post the full chapter to
    `providers.compat.chat_completion`. `manifest.yaml` has no `config[]` block, so an operator cannot
    disable study aids; `help.md` never mentions that generating an aid leaves the house; and `prefetch.py`
    would send whole books unattended. (Reading, browsing and searching genuinely stay local — that part is
    sound.)

## Background work that never runs

11. **`prefetch.py::prefetch_scripture_summaries` is never scheduled or queued.** README and the module
    docstring call it "nightly". The platform registers the handler
    (`job_handlers.py::_handle_scripture_prefetch`, commented "the job is only ever queued BY the app"),
    but the app never calls `app_platform.jobs.submit_job` and ships no `public.schedules` seed.
    `manifest.yaml` also declares no `job_types`, so the app does not own its own handler — **the platform
    hardcodes an import of an optional app.** Net: the documented fix for the "3-4 minute wait" is not in
    effect on any install.

12. `prefetch.py`'s per-chapter `try` wraps all four aids, so one failed summary skips people, places and
    pronouns for that chapter too. Its report also mixes units — `skipped`/`generated` count per-aid while
    "checked K unique chapters" counts per-chapter.

## Platform contract violations

13. **No `digest_record` anywhere.** `create_bookmark`/`update_bookmark`/`move_bookmark`/`delete_bookmark`
    call it zero times, while `help.md` explicitly promises "your bookmarks, highlights, and study notes …
    are pulled into Skipper's memory, so you can ask 'what did I highlight in Romans?' later." That promise
    cannot be met.
14. **Imports outside `app_platform.*`** — `routes.py` imports `providers.compat`, `import_bible.py`
    imports `data_layer.db.get_conn`. `import_bible.py` also calls `load_dotenv(override=True)` at module
    import time, mutating process env for anything that imports it.
15. `data.py::_now()` uses `datetime.now(timezone.utc)` rather than `app_platform.time` — and is dead code,
    as are `_execute_returning()` and `get_version_by_abbrev()`.

## Documented features with no implementation

16. `migrations/001_initial.sql` creates `scripture_highlights`, `scripture_notes`, `reading_plans`,
    `reading_plan_days`, `reading_plan_progress`, and registers entity prefixes `shl`/`sn`/`rpl`/`rpp` into
    `public.entity_types`. **No Python or JSX anywhere in the repo references any of those five tables.**
    Yet the manifest description, `help.md` ("Bookmarks & highlights", "Notes", "Study notes you've
    attached to passages") and the routing keywords ("reading plan", "torah portion", "haftarah") all
    present them as available. The platform now believes four entity types are linkable against tables
    nothing writes.

## Security / correctness

17. **VERIFIED — unescaped imported text rendered as HTML.** `import_from_getbible` and `import_from_pdf`
    store source text as *both* `text` and `text_html` with no escaping, and `gbf.process_gbf` leaves any
    non-GBF `<…>` in the HTML copy. `ui/ScripturesApp.jsx` has four `dangerouslySetInnerHTML` sites (723,
    751, 825, 840) rendering that content, and `SearchTab` renders `r.text` raw inside a `<mark>` wrapper.
    A third-party translation source or a crafted `.mybible` containing markup lands in the reader's DOM.
    Model output is likewise rendered raw in `LlmContent` and `EntityModal` after a `**bold**` substitution.

18. **Attribution is spoofable.** `api_update_bookmark` passes the raw request body to
    `data.py::update_bookmark`, whose allow-list includes `updated_by`. The *move* endpoint carefully
    derives the actor from `current_principal`; PATCH lets any caller write any name into the "moved by
    <name>" shown in the UI.

19. `data.py::clear_chapter_field` interpolates the column name into SQL. Guarded by an allow-list directly
    above, so safe today — but the route validates the same field list independently, i.e. two allow-lists
    that must stay in sync around a format-string SQL build.

20. `search_verses` builds `f"%{query}%"` for `ILIKE`. Parameterised, but `%` and `_` act as wildcards, and
    `%%%` passes the 3-character minimum and matches every verse — forcing a full scan twice (results and
    count). Its docstring also claims "full-text search using trigram similarity" while the query is a
    plain `ILIKE`; the `pg_trgm` GIN index accelerates it, but the docstring describes something the code
    does not do.

21. `search_verses` / `count_search_results` hardcode the OT/NT split as `book <= 39` / `book >= 40`
    instead of using the `bible_books.testament` column that already exists — wrong for any non-66-book
    canon.

22. **Duplicate bookmark name → unhandled 500.** `scripture_bookmarks.name` is `NOT NULL UNIQUE`; neither
    create nor update pre-checks or catches the integrity error, so a second "Morning Reading" produces an
    opaque server error rather than "that name is taken".

## UI gaps

23. `BookmarksTab.handleCreate` always posts `book: 1, chapter: 1` regardless of what the reader has open,
    so every new reading position starts at Genesis 1 and must then be moved.
24. `SearchTab` requests `limit=50` and never sends `offset`, though the API supports both — the screen
    displays the true total above at most 50 rows, telling a reader about matches they cannot reach. It
    also never sends `book` or `testament`, so the API's narrowing filters are unreachable from the UI.
25. **`injectEntityLinks` (~line 774) is dead and broken** — nothing calls it, and it emits
    `onclick="window.__eClick&&…"` where `window.__eClick` is never assigned anywhere in the repo.
26. `GET /verse` is dead — no caller — and is the only read endpoint requiring `version_id` with no default
    fallback, unlike every sibling.

## Cache provenance

27. **Empty pronoun results are cached as "analysed".** `api_generate_pronouns` saves whatever the helper
    returns, including `[]`, and `get_chapter_pronouns` treats `pronouns IS NOT NULL` as present. A chapter
    the model returned nothing for is permanently "done", indistinguishable from one that genuinely has no
    pronouns. Summary/people/places correctly refuse to cache empties; pronouns is the odd one out.
28. `clear_chapter_field("summary")` sets `summary = ''`, blanks `model`, and bumps `generated_at` to the
    clear time — so between a discard and the next successful generation the row's provenance is untrue.
29. `_get_summary_model()` returns the literal `"fast"`, so `chapter_summaries.model` records a tier label,
    not a model id. Two summaries a year apart from different models are indistinguishable. Deliberate per
    the ev-105 comment — flagged because "which model wrote this commentary on scripture" is exactly the
    provenance a household may care about.

## Tests

30. `tests/` contains one file, all of it about `providers.compat` plumbing. Nothing tests
    `gbf.process_gbf` — the conversion that decides what a verse actually reads like — nor import fidelity,
    search, bookmarks, or the data layer. Its docstring binds it to spec id
    `app.scriptures.llm-endpoints-tier-migration`, which matches no corpus id scheme; bound instead to
    `scriptures.study.nothing-broken-is-kept`, which it genuinely covers.
31. Minor: `import_bible.py` imports `dotenv`, which is not in `requirements.txt` (it arrives via the
    platform).
