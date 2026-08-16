"""Preparation runs ahead of the reader, across book boundaries.

Reported from a live household: a bookmark sat on the LAST chapter of a book, that chapter
had its study material, and the next two did not. The walk was
`range(base, min(base + LOOK_AHEAD + 1, chapter_count + 1))`, which clamps to the end of
the current book — so a bookmark on a book's final chapter prepared exactly one chapter and
stopped, precisely when a reader is about to need what comes next. Nobody stops reading at
a book boundary.

Also raises the look-ahead from three chapters to five, at the operator's request.

The walk is what these test. It feeds summary, people, places and pronouns from one loop,
so getting it right fixes all four at once — and getting it wrong breaks all four silently,
which is how this went unnoticed.

Run: python3 -m unittest apps.scriptures.tests.test_preparation_crosses_book_boundaries
"""
import unittest
from unittest import mock

from apps.scriptures import prefetch


def _books(*specs):
    """specs: (book_number, chapter_count, name)"""
    return [{"book_number": n, "chapter_count": c, "name_english": name}
            for n, c, name in specs]


def _walk(books, start_book, start_chapter, count):
    # The data layer is imported inside the function, so patch it at its source.
    with mock.patch("apps.scriptures.data.get_books", return_value=books):
        return [(b, c) for b, c, _ in
                prefetch._chapters_ahead("v1", start_book, start_chapter, count, {})]


GENESIS_EXODUS = _books((1, 50, "Genesis"), (2, 40, "Exodus"), (3, 27, "Leviticus"))


class ItRollsIntoTheNextBook(unittest.TestCase):
    def test_a_bookmark_on_the_last_chapter_still_prepares_ahead(self):
        # The reported failure, exactly: previously this returned Genesis 50 alone.
        got = _walk(GENESIS_EXODUS, 1, 50, 6)
        self.assertEqual(got, [(1, 50), (2, 1), (2, 2), (2, 3), (2, 4), (2, 5)])

    def test_it_crosses_more_than_one_boundary_if_it_has_to(self):
        # A short book must not swallow the whole look-ahead.
        short = _books((1, 2, "Short"), (2, 1, "Shorter"), (3, 10, "Long"))
        self.assertEqual(_walk(short, 1, 2, 5),
                         [(1, 2), (2, 1), (3, 1), (3, 2), (3, 3)])

    def test_mid_book_is_unchanged(self):
        self.assertEqual(_walk(GENESIS_EXODUS, 1, 10, 6),
                         [(1, 10), (1, 11), (1, 12), (1, 13), (1, 14), (1, 15)])

    def test_it_reports_which_book_each_chapter_belongs_to(self):
        # The book NAME goes into every prompt; carrying the bookmark's book across a
        # boundary would label Exodus 1 as Genesis.
        with mock.patch("apps.scriptures.data.get_books", return_value=GENESIS_EXODUS):
            walked = list(prefetch._chapters_ahead("v1", 1, 50, 3, {}))
        self.assertEqual([info["name_english"] for _, _, info in walked],
                         ["Genesis", "Exodus", "Exodus"])


class ItStopsCleanlyAtTheEnd(unittest.TestCase):
    def test_the_last_book_simply_runs_out(self):
        got = _walk(GENESIS_EXODUS, 3, 26, 6)
        self.assertEqual(got, [(3, 26), (3, 27)])

    def test_a_version_missing_the_bookmarked_book_yields_nothing(self):
        self.assertEqual(_walk(GENESIS_EXODUS, 99, 1, 6), [])

    def test_gaps_in_numbering_are_followed_not_guessed(self):
        # Walking by incrementing the number would ask for book 2, which this version does
        # not have. The version's own ordered list is the authority.
        gapped = _books((1, 2, "One"), (7, 3, "Seven"))
        self.assertEqual(_walk(gapped, 1, 2, 4), [(1, 2), (7, 1), (7, 2), (7, 3)])

    def test_an_unreadable_book_list_does_not_raise(self):
        boom = mock.MagicMock(side_effect=RuntimeError("db down"))
        with mock.patch("apps.scriptures.data.get_books", boom):
            self.assertEqual(list(prefetch._chapters_ahead("v1", 1, 1, 5, {})), [])


class TheLookAhead(unittest.TestCase):
    def test_it_is_five(self):
        self.assertEqual(prefetch.LOOK_AHEAD, 5)

    def test_five_ahead_means_six_chapters_including_the_bookmarked_one(self):
        # The reader's own chapter plus the five after it.
        self.assertEqual(len(_walk(GENESIS_EXODUS, 1, 10, prefetch.LOOK_AHEAD + 1)), 6)


class TheBookListIsFetchedOncePerVersion(unittest.TestCase):
    def test_several_bookmarks_share_one_lookup(self):
        # Bookmarks are walked in a loop; re-listing every book for each one would be a
        # query per bookmark for data that cannot change during a run.
        cache = {}
        getter = mock.MagicMock(return_value=GENESIS_EXODUS)
        with mock.patch("apps.scriptures.data.get_books", getter):
            for start in (1, 2, 3):
                list(prefetch._chapters_ahead("v1", start, 1, 3, cache))
        self.assertEqual(getter.call_count, 1)


if __name__ == "__main__":
    unittest.main()
