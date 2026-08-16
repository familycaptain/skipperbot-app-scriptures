"""Generated study material sounds like the translation it came from.

Reported from a real household: a summary of a translation that renders the covenant
writings as "Torah" came back describing "the Law" — vocabulary from a different tradition
entirely. The instruction in the prompt was "use the same names, spellings, and terminology
that appear in this translation", which a model reads as a mild preference and then
overrides with whatever wording dominates its training. For English Bibles that is reliably
the King James / mainstream-Christian register.

Somebody choosing a particular translation is choosing its vocabulary. Study material that
quietly translates it back into the common equivalents misrepresents the text they are
reading, and does it in the reader's own study pane.

An LLM's output cannot be asserted deterministically, so these pin the INSTRUCTION — that
it is firm, that it is applied to all four generators rather than one, and that it
prescribes no vocabulary of its own (which would be right for one translation and wrong for
the next).

Run: python3 -m unittest apps.scriptures.tests.test_study_material_keeps_the_translations_voice
"""
import unittest
from unittest import mock

import apps.scriptures.routes as routes

VERSES = [{"verse": 1, "text": "And he spoke."}, {"verse": 2, "text": "She answered."}]


def _prompt(fn, *args):
    stub = mock.MagicMock()
    stub.content = "out" if fn is not routes._generate_pronouns_llm else '{"verses":[]}'
    with mock.patch.object(routes, "chat_completion", return_value=stub) as m:
        fn(*args)
    return m.call_args.kwargs["messages"][1]["content"]


def _all_prompts(version="The Scriptures 2009 (TS2009)"):
    return {
        "summary": _prompt(routes._generate_summary_llm, "Exodus", 20, "text", version),
        "people":  _prompt(routes._generate_people_llm, "Exodus", 20, "text", version),
        "places":  _prompt(routes._generate_places_llm, "Exodus", 20, "text", version),
        "pronouns": _prompt(routes._generate_pronouns_llm, "Exodus", 20, VERSES, version),
    }


class EveryGeneratorIsToldToKeepTheVoice(unittest.TestCase):
    def test_the_three_prose_generators_carry_the_shared_instruction(self):
        # One instruction, used in each, so they cannot drift apart. Pronouns builds a JSON
        # contract of its own and is covered separately below.
        prompts = _all_prompts()
        for kind in ("summary", "people", "places"):
            with self.subTest(kind=kind):
                self.assertIn("VOCABULARY", prompts[kind])
                self.assertIn("must sound like it came from that", prompts[kind])

    def test_pronoun_replacements_must_match_the_translation(self):
        # These are read INLINE in the verse, so a swapped name is most visible of all four.
        p = _all_prompts()["pronouns"]
        self.assertIn("match this translation exactly", p)

    def test_the_translation_is_named_in_every_prompt(self):
        for kind, p in _all_prompts().items():
            with self.subTest(kind=kind):
                self.assertIn("The Scriptures 2009 (TS2009)", p)


class TheInstructionNamesTheAreasThatGoWrong(unittest.TestCase):
    def test_it_points_at_the_categories_translations_disagree_on(self):
        p = _all_prompts()["summary"].lower()
        for area in ("divine name", "covenant writings", "messiah", "appointed times"):
            with self.subTest(area=area):
                self.assertIn(area, p)

    def test_it_forbids_substituting_the_more_familiar_term(self):
        p = _all_prompts()["summary"].lower()
        self.assertIn("not the one that is most familiar", p)
        self.assertIn("another tradition", p)

    def test_it_points_the_model_at_the_chapter_text_as_the_authority(self):
        self.assertIn("Take your wording from the chapter text", _all_prompts()["summary"])


class ItPrescribesNoVocabularyOfItsOwn(unittest.TestCase):
    """Naming specific words would be right for one translation and wrong for the next."""

    def test_it_does_not_hardcode_either_tradition_s_terms(self):
        # The old summary prompt hinted "(e.g. Yahweh, Elohim)", which is guidance for one
        # family of translations and misdirection for the rest.
        joined = " ".join(_all_prompts().values())
        for word in ("Yahweh", "Elohim", "Torah", "Yeshua", "Jesus", "Christ"):
            with self.subTest(word=word):
                self.assertNotIn(word, joined)

    def test_it_says_keep_whichever_form_this_translation_uses(self):
        p = _all_prompts()["summary"]
        self.assertIn("If it uses a Hebrew or transliterated form, keep it", p)
        self.assertIn("if it uses an anglicised one, keep that", p)


class TheTranslationIsIdentifiedByNameAndAbbreviation(unittest.TestCase):
    def test_both_are_given_when_they_differ(self):
        self.assertEqual(
            routes._version_label({"name": "The Scriptures 2009", "abbreviation": "TS2009"}),
            "The Scriptures 2009 (TS2009)")

    def test_it_does_not_repeat_an_abbreviation_already_in_the_name(self):
        self.assertEqual(
            routes._version_label({"name": "KJV Authorised", "abbreviation": "KJV"}),
            "KJV Authorised")

    def test_it_copes_with_missing_pieces(self):
        self.assertEqual(routes._version_label({"name": "", "abbreviation": "TS2009"}), "TS2009")
        self.assertEqual(routes._version_label({"name": "Some Bible", "abbreviation": ""}), "Some Bible")
        self.assertEqual(routes._version_label(None), "Bible")
        self.assertEqual(routes._version_label({}), "Bible")


if __name__ == "__main__":
    unittest.main()
