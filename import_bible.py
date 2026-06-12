"""Import a Bible version into Skipper's Postgres database.
================================================================
Standalone utility — not a migration.

Usage:
    python -m apps.scriptures.import_bible KJV              # fetch from getbible.net API
    python -m apps.scriptures.import_bible /path/to/file.mybible  # import unencrypted MySword file
    python -m apps.scriptures.import_bible /path/to/TS2009.pdf   # import from TS2009 PDF

Supported sources:
  - getbible.net API: KJV, ASV, WEB, YLT, etc.  (--list to see all)
  - Local .mybible file: any unencrypted MySword SQLite module
  - TS2009 PDF: "The Scriptures 1998-2009" PDF with verse references
"""

import os
import re
import sys
import json
import time
import uuid
import sqlite3
import zipfile
import tempfile
import logging
import urllib.request

from dotenv import load_dotenv
load_dotenv(override=True)

from data_layer.db import get_conn
from apps.scriptures.gbf import process_gbf

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SCHEMA = "app_scriptures"

# getbible.net API — known versions available for direct API download
_GETBIBLE_API = "https://api.getbible.net/v2"
_GETBIBLE_HEADERS = {"User-Agent": "SkipperBot/1.0"}

# Chapter counts per book (standard 66-book canon)
_CHAPTER_COUNTS = {
    1: 50, 2: 40, 3: 27, 4: 36, 5: 34, 6: 24, 7: 21, 8: 4, 9: 31, 10: 24,
    11: 22, 12: 25, 13: 29, 14: 36, 15: 10, 16: 13, 17: 10, 18: 42, 19: 150,
    20: 31, 21: 12, 22: 8, 23: 66, 24: 52, 25: 5, 26: 48, 27: 12, 28: 14, 29: 3,
    30: 9, 31: 1, 32: 4, 33: 7, 34: 3, 35: 3, 36: 3, 37: 2, 38: 14, 39: 4,
    40: 28, 41: 16, 42: 24, 43: 21, 44: 28, 45: 16, 46: 16, 47: 13, 48: 6,
    49: 6, 50: 4, 51: 4, 52: 5, 53: 3, 54: 6, 55: 4, 56: 3, 57: 1, 58: 13,
    59: 5, 60: 5, 61: 3, 62: 5, 63: 1, 64: 1, 65: 1, 66: 22,
}

# TS2009 Hebrew-transliterated book names (book_number → name)
# Standard 66-book canon
_TS2009_BOOK_NAMES = {
    1: "Berĕshith", 2: "Shemoth", 3: "Wayyiqra", 4: "Bemiḏbar", 5: "Deḇarim",
    6: "Yehoshua", 7: "Shophetim", 8: "Ruth", 9: "Shemu'ĕl Aleph", 10: "Shemu'ĕl Bĕth",
    11: "Melaḵim Aleph", 12: "Melaḵim Bĕth", 13: "Diḇre haYamim Aleph", 14: "Diḇre haYamim Bĕth",
    15: "Ezra", 16: "Neḥemyah", 17: "Estĕr", 18: "Iyoḇ", 19: "Tehillim",
    20: "Mishlĕ", 21: "Qoheleth", 22: "Shir haShirim", 23: "Yeshayahu", 24: "Yirmeyahu",
    25: "Eiḵah", 26: "Yeḥezqĕl", 27: "Dani'ĕl", 28: "Hoshĕa", 29: "Yo'ĕl",
    30: "Amos", 31: "Oḇaḏyah", 32: "Yonah", 33: "Miḵah", 34: "Naḥum",
    35: "Ḥaḇaqquq", 36: "Tsephanyah", 37: "Ḥaggai", 38: "Zeḵaryah", 39: "Mal'aḵi",
    40: "Mattithyahu", 41: "Marqos", 42: "Luqas", 43: "Yoḥanan", 44: "Ma'asei",
    45: "Romiyim", 46: "Qorintiyim Aleph", 47: "Qorintiyim Bĕth", 48: "Galatiyim",
    49: "Eph'siyim", 50: "Philippiyim", 51: "Qolasim", 52: "Tas'loniqim Aleph",
    53: "Tas'loniqim Bĕth", 54: "Timotiyos Aleph", 55: "Timotiyos Bĕth", 56: "Titos",
    57: "Philĕmon", 58: "Iḇrim", 59: "Ya'aqoḇ", 60: "Kĕpha Aleph", 61: "Kĕpha Bĕth",
    62: "Yoḥanan Aleph", 63: "Yoḥanan Bĕth", 64: "Yoḥanan Gimel", 65: "Yehuḏah",
    66: "Ḥazon",
}

# Standard English book names
_ENGLISH_BOOK_NAMES = {
    1: "Genesis", 2: "Exodus", 3: "Leviticus", 4: "Numbers", 5: "Deuteronomy",
    6: "Joshua", 7: "Judges", 8: "Ruth", 9: "1 Samuel", 10: "2 Samuel",
    11: "1 Kings", 12: "2 Kings", 13: "1 Chronicles", 14: "2 Chronicles",
    15: "Ezra", 16: "Nehemiah", 17: "Esther", 18: "Job", 19: "Psalms",
    20: "Proverbs", 21: "Ecclesiastes", 22: "Song of Solomon", 23: "Isaiah", 24: "Jeremiah",
    25: "Lamentations", 26: "Ezekiel", 27: "Daniel", 28: "Hosea", 29: "Joel",  # noqa: family-name
    30: "Amos", 31: "Obadiah", 32: "Jonah", 33: "Micah", 34: "Nahum",  # noqa: family-name
    35: "Habakkuk", 36: "Zephaniah", 37: "Haggai", 38: "Zechariah", 39: "Malachi",
    40: "Matthew", 41: "Mark", 42: "Luke", 43: "John", 44: "Acts",
    45: "Romans", 46: "1 Corinthians", 47: "2 Corinthians", 48: "Galatians",
    49: "Ephesians", 50: "Philippians", 51: "Colossians", 52: "1 Thessalonians",
    53: "2 Thessalonians", 54: "1 Timothy", 55: "2 Timothy", 56: "Titus",
    57: "Philemon", 58: "Hebrews", 59: "James", 60: "1 Peter", 61: "2 Peter",
    62: "1 John", 63: "2 John", 64: "3 John", 65: "Jude",
    66: "Revelation",
}

# Standard abbreviations
_BOOK_ABBREVS = {
    1: "Gen", 2: "Exo", 3: "Lev", 4: "Num", 5: "Deu",
    6: "Jos", 7: "Jdg", 8: "Rth", 9: "1Sa", 10: "2Sa",
    11: "1Ki", 12: "2Ki", 13: "1Ch", 14: "2Ch",
    15: "Ezr", 16: "Neh", 17: "Est", 18: "Job", 19: "Psa",
    20: "Pro", 21: "Ecc", 22: "Sng", 23: "Isa", 24: "Jer",
    25: "Lam", 26: "Eze", 27: "Dan", 28: "Hos", 29: "Joe",
    30: "Amo", 31: "Oba", 32: "Jon", 33: "Mic", 34: "Nah",
    35: "Hab", 36: "Zep", 37: "Hag", 38: "Zec", 39: "Mal",
    40: "Mat", 41: "Mar", 42: "Luk", 43: "Joh", 44: "Act",
    45: "Rom", 46: "1Co", 47: "2Co", 48: "Gal",
    49: "Eph", 50: "Php", 51: "Col", 52: "1Th",
    53: "2Th", 54: "1Ti", 55: "2Ti", 56: "Tit",
    57: "Phm", 58: "Heb", 59: "Jas", 60: "1Pe", 61: "2Pe",
    62: "1Jn", 63: "2Jn", 64: "3Jn", 65: "Jud",
    66: "Rev",
}


# PDF abbreviation → standard book number (as used in the TS2009 PDF)
_PDF_ABBREV_TO_BOOK = {
    "Gen": 1, "Exod": 2, "Lev": 3, "Num": 4, "Deut": 5,
    "Josh": 6, "Judges": 7, "Ruth": 8, "1Sam": 9, "2Sam": 10,
    "1Kings": 11, "2Kings": 12, "1Chron": 13, "2Chron": 14,
    "Ezra": 15, "Nehem": 16, "Esther": 17, "Job": 18, "Psalm": 19,
    "Prov": 20, "Eccl": 21, "Song": 22, "Isaiah": 23, "Jer": 24,
    "Lam": 25, "Ezek": 26, "Dan": 27, "Hos": 28, "Joel": 29,  # noqa: family-name
    "Amos": 30, "Obad": 31, "Jonah": 32, "Micah": 33, "Nahum": 34,  # noqa: family-name
    "Hab": 35, "Zeph": 36, "Hag": 37, "Zech": 38, "Mal": 39,
    "Mat": 40, "Mar": 41, "Luk": 42, "John": 43, "Acts": 44,
    "Rom": 45, "1Cor": 46, "2Cor": 47, "Gal": 48,
    "Eph": 49, "Philip": 50, "Col": 51, "1Thes": 52,
    "2Thes": 53, "1Tim": 54, "2Tim": 55, "Titus": 56,
    "Philemon": 57, "Hebrew": 58, "James": 59, "1Pet": 60, "2Pet": 61,
    "1John": 62, "2John": 63, "3John": 64, "Jude": 65,
    "Rev": 66,
}

# Build regex alternation sorted longest-first so "1Kings" matches before "1Ki" etc.
_PDF_ABBREV_PATTERN = "|".join(
    re.escape(a) for a in sorted(_PDF_ABBREV_TO_BOOK, key=len, reverse=True)
)
_VERSE_REF_RE = re.compile(
    rf"^({_PDF_ABBREV_PATTERN}) (\d+):(\d+)  ", re.MULTILINE
)


# ---------------------------------------------------------------------------
# TS2009 PDF import
# ---------------------------------------------------------------------------

def import_from_pdf(pdf_path: str):
    """Import the TS2009 Bible from its PDF into Postgres.

    The PDF uses verse references like 'Gen 1:1  In the beginning...'
    with two spaces between the reference and the verse text.
    Text may wrap across multiple lines and contain Hebrew characters.
    """
    import pymupdf  # pip install pymupdf

    logger.info("Opening PDF: %s", pdf_path)
    doc = pymupdf.open(pdf_path)
    logger.info("PDF has %d pages", len(doc))

    # Extract all text from scripture pages (skip front matter)
    raw_pages = []
    for i in range(4, len(doc)):
        raw_pages.append(doc[i].get_text())
    full_text = "\n".join(raw_pages)

    # Find all verse references and extract text between them
    matches = list(_VERSE_REF_RE.finditer(full_text))
    logger.info("Found %d verse references in PDF", len(matches))

    if not matches:
        logger.error("No verse references found. Is this the right PDF?")
        sys.exit(1)

    version_id = f"bv-{uuid.uuid4().hex[:8]}"
    verses = []
    book_chapters = {}

    for idx, m in enumerate(matches):
        abbrev_pdf = m.group(1)
        chapter = int(m.group(2))
        verse_num = int(m.group(3))
        book_num = _PDF_ABBREV_TO_BOOK[abbrev_pdf]

        # Text runs from end of this match to start of next match (or end)
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(full_text)
        raw = full_text[start:end]

        # Join wrapped lines: replace single newlines with spaces, collapse whitespace
        text = raw.replace("\n", " ").strip()
        text = re.sub(r"  +", " ", text)

        verses.append((version_id, book_num, chapter, verse_num, text, text))

        if book_num not in book_chapters:
            book_chapters[book_num] = set()
        book_chapters[book_num].add(chapter)

    logger.info("Parsed %d verses across %d books from PDF", len(verses), len(book_chapters))

    _insert_into_postgres(
        version_id=version_id,
        version_abbrev="TS2009",
        version_name="The Scriptures 2009",
        language="eng",
        has_ot=True,
        has_nt=True,
        has_strongs=False,
        source_file=os.path.basename(pdf_path),
        book_names=_TS2009_BOOK_NAMES,
        verses=verses,
        book_chapters=book_chapters,
    )


# ---------------------------------------------------------------------------
# getbible.net API helpers
# ---------------------------------------------------------------------------

def _api_get(url: str) -> dict:
    """Fetch JSON from getbible.net API with retries."""
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=_GETBIBLE_HEADERS)
            resp = urllib.request.urlopen(req, timeout=30)
            return json.loads(resp.read())
        except Exception as e:
            if attempt < 2:
                time.sleep(1 + attempt)
            else:
                raise RuntimeError(f"API request failed after 3 attempts: {url} — {e}")


def _list_getbible_versions():
    """List available English versions from getbible.net."""
    data = _api_get(f"{_GETBIBLE_API}/translations.json")
    versions = []
    for key, info in sorted(data.items()):
        if info.get("language", "") == "English":
            versions.append((key, info.get("translation", "")))
    return versions


def import_from_getbible(abbrev: str):
    """Import a Bible version from getbible.net API into Postgres."""
    abbrev_lower = abbrev.lower()

    # Verify version exists
    logger.info("Checking getbible.net for version '%s' ...", abbrev_lower)
    translations = _api_get(f"{_GETBIBLE_API}/translations.json")
    if abbrev_lower not in translations:
        logger.error("Version '%s' not found on getbible.net", abbrev_lower)
        logger.info("Available English versions:")
        for key, info in sorted(translations.items()):
            if info.get("language", "") == "English":
                logger.info("  %s — %s", key, info.get("translation", ""))
        sys.exit(1)

    version_info = translations[abbrev_lower]
    version_name = version_info.get("translation", abbrev.upper())
    version_abbrev = abbrev.upper()

    # Use TS2009 names if importing TS2009, otherwise English
    if abbrev.upper() == "TS2009":
        book_names = _TS2009_BOOK_NAMES
    else:
        book_names = _ENGLISH_BOOK_NAMES

    version_id = f"bv-{uuid.uuid4().hex[:8]}"

    # Fetch all verses book by book, chapter by chapter
    verses = []
    book_chapters = {}  # book_number → set of chapters
    total_books = len(_CHAPTER_COUNTS)

    for book_num, ch_count in _CHAPTER_COUNTS.items():
        book_name_eng = _ENGLISH_BOOK_NAMES.get(book_num, f"Book {book_num}")
        logger.info("  Fetching %s (%d chapters) [%d/%d] ...", book_name_eng, ch_count, book_num, total_books)
        book_chapters[book_num] = set()

        for ch in range(1, ch_count + 1):
            try:
                data = _api_get(f"{_GETBIBLE_API}/{abbrev_lower}/{book_num}/{ch}.json")
                for v in data.get("verses", []):
                    text = v.get("text", "").strip()
                    # API returns plain text — use as both plain and HTML
                    verses.append((version_id, book_num, ch, v["verse"], text, text))
                book_chapters[book_num].add(ch)
            except Exception as e:
                logger.warning("    Failed to fetch %s %d: %s", book_name_eng, ch, e)

        # Be polite to the API
        time.sleep(0.05)

    logger.info("Fetched %d verses across %d books", len(verses), len(book_chapters))

    # Insert into Postgres
    _insert_into_postgres(
        version_id=version_id,
        version_abbrev=version_abbrev,
        version_name=version_name,
        language="eng",
        has_ot=True,
        has_nt=True,
        has_strongs=False,
        source_file=f"getbible.net/{abbrev_lower}",
        book_names=book_names,
        verses=verses,
        book_chapters=book_chapters,
    )


# ---------------------------------------------------------------------------
# MySword .mybible file helpers
# ---------------------------------------------------------------------------


def _read_mysword_details(sqlite_path: str) -> dict:
    """Read the Details table from a MySword .mybible file."""
    conn = sqlite3.connect(sqlite_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM Details LIMIT 1")
        cols = [d[0] for d in cur.description]
        row = cur.fetchone()
        if not row:
            return {}
        return dict(zip(cols, row))
    finally:
        conn.close()


def _read_mysword_verses(sqlite_path: str):
    """Yield (book, chapter, verse, scripture) from the Bible table."""
    conn = sqlite3.connect(sqlite_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT Book, Chapter, Verse, Scripture FROM Bible ORDER BY Book, Chapter, Verse")
        for row in cur:
            yield row
    finally:
        conn.close()


def import_mybible_file(source_path: str):
    """Import a local .mybible SQLite file into Postgres."""
    abbrev = os.path.basename(source_path).split(".")[0].upper()

    # Read metadata
    details = _read_mysword_details(source_path)
    logger.info("MySword details: %s", details)

    # Check for encryption
    encryption = details.get("encryption", 0)
    if encryption and encryption != 0:
        logger.error("This .mybible file is encrypted (encryption=%s). Cannot import.", encryption)
        logger.error("Try importing from getbible.net API instead: python -m apps.scriptures.import_bible KJV")
        sys.exit(1)

    version_name = details.get("Description", abbrev)
    version_abbrev = details.get("Abbreviation", abbrev)
    language = details.get("Language", "eng")
    has_ot = bool(details.get("OT", 1))
    has_nt = bool(details.get("NT", 1))
    has_strongs = bool(details.get("Strong", 0))

    version_id = f"bv-{uuid.uuid4().hex[:8]}"

    # Determine book names to use
    if abbrev == "TS2009":
        book_names = _TS2009_BOOK_NAMES
    else:
        book_names = _ENGLISH_BOOK_NAMES

    # Process all verses
    logger.info("Processing verses from %s ...", source_path)
    verses = []
    book_chapters = {}

    for book, chapter, verse, scripture in _read_mysword_verses(source_path):
        if isinstance(scripture, bytes):
            scripture = scripture.decode("utf-8", errors="replace")
        plain, html = process_gbf(scripture or "")
        verses.append((version_id, book, chapter, verse, plain, html))

        if book not in book_chapters:
            book_chapters[book] = set()
        book_chapters[book].add(chapter)

    logger.info("Processed %d verses across %d books", len(verses), len(book_chapters))

    _insert_into_postgres(
        version_id=version_id,
        version_abbrev=version_abbrev,
        version_name=version_name,
        language=language,
        has_ot=has_ot,
        has_nt=has_nt,
        has_strongs=has_strongs,
        source_file=os.path.basename(source_path),
        book_names=book_names,
        verses=verses,
        book_chapters=book_chapters,
    )


# ---------------------------------------------------------------------------
# Shared Postgres insert logic
# ---------------------------------------------------------------------------

def _insert_into_postgres(
    version_id: str,
    version_abbrev: str,
    version_name: str,
    language: str,
    has_ot: bool,
    has_nt: bool,
    has_strongs: bool,
    source_file: str,
    book_names: dict,
    verses: list,
    book_chapters: dict,
):
    """Insert a fully-processed Bible version into Postgres."""
    with get_conn() as pg:
        with pg.cursor() as cur:
            cur.execute(f"SET search_path TO {SCHEMA}, public")

            # Check if this version already exists
            cur.execute("SELECT id FROM bible_versions WHERE abbreviation = %s", (version_abbrev,))
            existing = cur.fetchone()
            if existing:
                logger.info("Version %s already exists (id=%s). Skipping import.", version_abbrev, existing[0])
                return

            # Insert version
            cur.execute(
                """INSERT INTO bible_versions
                   (id, abbreviation, name, language, has_ot, has_nt, has_strongs, source_file, verse_count)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (version_id, version_abbrev, version_name, language,
                 has_ot, has_nt, has_strongs, source_file, len(verses)),
            )
            logger.info("Inserted version: %s (%s) → %s", version_abbrev, version_name, version_id)

            # Insert books
            for book_num in sorted(book_chapters.keys()):
                book_id = f"bb-{uuid.uuid4().hex[:8]}"
                name = book_names.get(book_num, _ENGLISH_BOOK_NAMES.get(book_num, f"Book {book_num}"))
                name_eng = _ENGLISH_BOOK_NAMES.get(book_num, f"Book {book_num}")
                abbr = _BOOK_ABBREVS.get(book_num, f"B{book_num}")
                testament = "OT" if book_num <= 39 else "NT"
                ch_count = len(book_chapters[book_num])

                cur.execute(
                    """INSERT INTO bible_books
                       (id, version_id, book_number, name, name_english, abbreviation, testament, chapter_count)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (book_id, version_id, book_num, name, name_eng, abbr, testament, ch_count),
                )

            logger.info("Inserted %d books", len(book_chapters))

            # Insert verses in batches
            batch_size = 500
            for i in range(0, len(verses), batch_size):
                batch = verses[i : i + batch_size]
                args = []
                placeholders = []
                for v in batch:
                    placeholders.append("(%s, %s, %s, %s, %s, %s)")
                    args.extend(v)
                sql = (
                    "INSERT INTO bible_verses (version_id, book, chapter, verse, text, text_html) VALUES "
                    + ", ".join(placeholders)
                )
                cur.execute(sql, args)

                if (i + batch_size) % 5000 < batch_size:
                    logger.info("  ... inserted %d / %d verses", min(i + batch_size, len(verses)), len(verses))

        pg.commit()
        logger.info("Import complete: %s — %d verses, %d books", version_abbrev, len(verses), len(book_chapters))


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("--help", "-h"):
        print("Usage: python -m apps.scriptures.import_bible <VERSION|/path/to/file>")
        print()
        print("  VERSION        Abbreviation to fetch from getbible.net (e.g. KJV, ASV, WEB, YLT)")
        print("  file.mybible   Path to an unencrypted MySword SQLite module")
        print("  file.pdf       Path to a TS2009 PDF file")
        print()
        print("  --list         Show available English versions from getbible.net")
        sys.exit(0)

    if sys.argv[1] == "--list":
        print("Available English versions on getbible.net:")
        for abbr, name in _list_getbible_versions():
            print(f"  {abbr:20s} {name}")
        sys.exit(0)

    source = sys.argv[1]

    if os.path.isfile(source) and source.lower().endswith(".pdf"):
        import_from_pdf(source)
    elif os.path.isfile(source) and source.endswith(".mybible"):
        import_mybible_file(source)
    else:
        import_from_getbible(source)
