"""A chapter summary is an executive summary, not a retelling.

What the app produced was a paraphrase: every verse restated in slightly different words,
which is longer than the chapter and tells a reader nothing they could not get by reading
it. The prompt asked for exactly that — "several paragraphs covering the chapter's
narrative, key events, prayers, speeches, and actions", each covering "a distinct section",
and to "be factual and thorough" — and closed by prescribing a "Key Themes:" list.

What is wanted instead: a short, plain-language account of what happened and what the
chapter is about, one page at most, in continuous prose with no lists, headings or trailing
sections.

An LLM's output cannot be asserted deterministically, so this pins the INSTRUCTIONS — the
part that caused the behaviour and the part a later edit could quietly undo. Both directions
matter: the prompt must ask for the summary, and must not re-acquire the structure that was
removed.

Run: python3 -m unittest apps.scriptures.tests.test_summary_is_an_executive_summary
"""
import unittest
from unittest import mock

import apps.scriptures.routes as routes


def _prompt(book="Genesis", chapter=1, text="In the beginning...", version="KJV"):
    """The user message the summary helper actually builds."""
    stub = mock.MagicMock()
    stub.content = "out"
    with mock.patch.object(routes, "chat_completion", return_value=stub) as m:
        routes._generate_summary_llm(book, chapter, text, version)
    return m.call_args.kwargs["messages"][1]["content"]


def _system():
    stub = mock.MagicMock()
    stub.content = "out"
    with mock.patch.object(routes, "chat_completion", return_value=stub) as m:
        routes._generate_summary_llm("Genesis", 1, "t", "KJV")
    return m.call_args.kwargs["messages"][0]["content"]


class ItAsksForTheChaptersPointNotItsContents(unittest.TestCase):
    def test_it_asks_what_the_chapter_is_about(self):
        p = _prompt().lower()
        self.assertIn("what it is about", p)
        self.assertIn("point of the chapter", p)

    def test_it_asks_for_plain_language(self):
        self.assertIn("plain-language", _prompt().lower())

    def test_it_caps_the_length_at_a_page(self):
        p = _prompt().lower()
        self.assertIn("one page at most", p)

    def test_it_forbids_going_verse_by_verse(self):
        # The specific failure being corrected.
        p = _prompt().lower()
        self.assertIn("verse by verse", p)
        self.assertIn("do not", p)

    def test_the_system_message_agrees_with_the_prompt(self):
        # A system message still calling for "concise chapter summaries" would leave the
        # model reconciling two different jobs.
        s = _system().lower()
        self.assertIn("plain language", s)
        self.assertNotIn("verse-by-verse", s.replace("never verse-by-verse", ""))


class ItAsksForNothingButTheSummary(unittest.TestCase):
    def test_no_structure_is_requested(self):
        p = _prompt().lower()
        for banned in ("bullet points", "numbered lists", "headings", "section"):
            with self.subTest(banned=banned):
                self.assertIn(banned, p, f"the prompt must explicitly rule out {banned}")

    def test_the_key_themes_footer_is_no_longer_prescribed(self):
        # It used to END with an instruction to produce one. Now it is named only to
        # forbid it, so check it is never requested.
        p = _prompt()
        self.assertNotIn("End with a 'Key Themes:'", p)
        self.assertNotIn("listing 3-6 themes", p)

    def test_the_old_paraphrase_instructions_are_gone(self):
        p = _prompt()
        for gone in ("Write several paragraphs covering",
                     "Each paragraph should focus on a distinct",
                     "Be factual and thorough"):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, p)


class WhatWasWorthKeepingIsKept(unittest.TestCase):
    """The rewrite must not drop the constraints that were already right."""

    def test_it_still_follows_the_translations_wording(self):
        # It used to assert the hint "(e.g. Yahweh, Elohim)". That hint has gone: naming one
        # translation's vocabulary is guidance for that family and misdirection for the
        # rest. What must survive is that the translation is NAMED and its wording is
        # binding — see test_study_material_keeps_the_translations_voice for the detail.
        p = _prompt(version="Cepher")
        self.assertIn("Cepher", p)
        self.assertIn("VOCABULARY", p)

    def test_it_still_refuses_devotional_commentary(self):
        self.assertIn("devotional commentary", _prompt().lower())

    def test_it_still_asks_for_blank_line_separated_paragraphs(self):
        p = _prompt().lower()
        self.assertIn("blank line", p)

    def test_the_chapter_text_is_still_supplied(self):
        self.assertIn("In the beginning...", _prompt(text="In the beginning..."))

    def test_the_book_and_chapter_are_named(self):
        self.assertIn("Exodus chapter 14", _prompt(book="Exodus", chapter=14))


if __name__ == "__main__":
    unittest.main()
