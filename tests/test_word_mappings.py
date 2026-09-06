"""Words the household reads differently — a display aid, not an edit to the text.

A household reading a translation that says "Sovereign" may prefer to see "king". The rules
are theirs, shared, and applied as the page is drawn.

Two properties are easy to get wrong and invisible until somebody reads a real chapter:

* ORDER. "sovereign" is a prefix of "sovereigness". Applied in the order they were typed,
  the short rule fires first and "sovereigness" becomes "kingess". Matching has to try the
  longest source first, whatever order the rules are in.
* CASE. One rule has to cover sovereign, Sovereign and SOVEREIGN, following whatever the
  text does — otherwise a household needs three rules per word and a capitalised word at
  the start of a verse comes out lowercase.

The substitution itself is JavaScript, so it is exercised HERE by running the real function
out of the component through node — asserting the source merely looks right would miss both
of the above. Where node is absent the behavioural half skips and the structural half still
runs.

Run: python3 -m unittest apps.scriptures.tests.test_word_mappings
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPONENT = os.path.join(APP_DIR, "ui", "ScripturesApp.jsx")
NODE = shutil.which("node")


def _engine_source():
    with open(COMPONENT, encoding="utf-8") as fh:
        src = fh.read()
    start = src.index("function escapeForRegex(")
    end = src.index("/** Apply the mapping to the TEXT of an html fragment")
    return src[start:end]


def _run(rules, samples):
    """Map each sample with the REAL engine, via node."""
    script = _engine_source() + f"""
const map = buildWordMapper({json.dumps(rules)});
const out = {json.dumps(samples)}.map(s => (map ? map(s) : s));
console.log(JSON.stringify(out));
"""
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False, encoding="utf-8") as fh:
        fh.write(script)
        path = fh.name
    try:
        res = subprocess.run([NODE, path], capture_output=True, text=True, timeout=30)
        if res.returncode != 0:
            raise AssertionError(f"engine failed: {res.stderr[:300]}")
        return json.loads(res.stdout.strip().splitlines()[-1])
    finally:
        os.unlink(path)


RULES = [
    {"source": "sovereign", "replacement": "king", "active": True},
    {"source": "sovereigness", "replacement": "queen", "active": True},
]


@unittest.skipIf(NODE is None, "node not available — behavioural half skipped")
class TheSubstitution(unittest.TestCase):
    def test_case_follows_the_text(self):
        got = _run(RULES, ["the sovereign spoke", "the Sovereign spoke", "THE SOVEREIGN SPOKE"])
        self.assertEqual(got, ["the king spoke", "the King spoke", "THE KING SPOKE"])

    def test_the_longest_rule_wins_whatever_order_they_are_in(self):
        # The reason this is not a naive loop: "sovereign" first would give "kingess".
        for rules in (RULES, list(reversed(RULES))):
            with self.subTest(order=[r["source"] for r in rules]):
                self.assertEqual(_run(rules, ["the sovereigness spoke"]), ["the queen spoke"])

    def test_it_only_replaces_whole_words(self):
        got = _run(RULES, ["sovereignty endures", "presovereign era", "sovereign-elect"])
        self.assertEqual(got[0], "sovereignty endures")
        self.assertEqual(got[1], "presovereign era")
        self.assertEqual(got[2], "king-elect")     # a hyphen IS a word boundary

    def test_several_words_in_one_sentence(self):
        self.assertEqual(
            _run(RULES, ["Sovereign, and sovereigness, and SOVEREIGN"]),
            ["King, and queen, and KING"])

    def test_a_rule_that_is_switched_off_does_nothing(self):
        off = [{"source": "sovereign", "replacement": "king", "active": False}]
        self.assertEqual(_run(off, ["the sovereign spoke"]), ["the sovereign spoke"])

    def test_no_rules_leaves_the_text_exactly_as_written(self):
        self.assertEqual(_run([], ["the sovereign spoke"]), ["the sovereign spoke"])

    def test_a_word_with_regex_characters_is_taken_literally(self):
        rules = [{"source": "a.b", "replacement": "x", "active": True}]
        got = _run(rules, ["a.b here", "axb here"])
        self.assertEqual(got, ["x here", "axb here"])


class WhereItIsApplied(unittest.TestCase):
    """It must reach the reader's text and the study material, and nothing else."""

    def setUp(self):
        with open(COMPONENT, encoding="utf-8") as fh:
            self.src = fh.read()

    def test_the_verse_and_the_study_material_both_get_it(self):
        self.assertIn("wordMapper={wordMapper}", self.src)
        self.assertEqual(self.src.count("<LlmContent wordMapper={wordMapper}"), 3,
                         "summary, people and places should all be mapped")

    def test_markup_is_never_rewritten_only_text_nodes(self):
        # A rule must not be able to corrupt a tag or an attribute.
        self.assertIn("createTreeWalker", self.src)
        self.assertIn("NodeFilter.SHOW_TEXT", self.src)

    def test_a_highlighted_name_is_mapped_too(self):
        # First cut mapped only plain text, so "Sovereign Aḥashwĕrosh" — where Sovereign is
        # part of the highlighted name — was the ONE place the word did not change, which is
        # exactly where the household most wanted it. Reported from the television.
        self.assertIn("{wordMapper ? wordMapper(seg.content) : seg.content}", self.src)

    def test_plain_text_is_mapped(self):
        self.assertIn('seg.type === "text" && wordMapper', self.src)

    def test_a_revealed_pronoun_is_mapped(self):
        # It is read inline in the verse, so it has to match the words around it.
        self.assertIn("wordMapper(isRevealed ? seg.replacement : seg.content)", self.src)

    def test_the_link_still_resolves_on_the_real_name(self):
        # Only what is SHOWN changes: clicking a person must still find them under the name
        # the translation uses, or the panel opens empty.
        self.assertIn("onClick={() => onEntityClick(seg.entityName)}", self.src)

    def test_every_place_a_reader_sees_text_gets_the_mapper(self):
        # verses, the three study views, and the panel that opens on a person.
        self.assertIn("wordMapper={wordMapper} />", self.src)   # EntityModal
        self.assertEqual(self.src.count("<LlmContent wordMapper={wordMapper}"), 3)

    def test_a_failure_never_stops_the_verse_rendering(self):
        start = self.src.index("function mapHtml(")
        self.assertIn("catch", self.src[start:start + 600])


class TheStoredTextIsUntouched(unittest.TestCase):
    """The whole point: this is a reading aid, not an edit."""

    def test_nothing_writes_a_mapped_value_back(self):
        with open(os.path.join(APP_DIR, "data.py"), encoding="utf-8") as fh:
            data_src = fh.read()
        # The mapping tables are read and written; verses are never rewritten from them.
        self.assertIn("def list_word_mappings", data_src)
        self.assertNotIn("UPDATE verses", data_src)

    def test_the_migration_says_display_only(self):
        with open(os.path.join(APP_DIR, "migrations", "004_word_mappings.sql"), encoding="utf-8") as fh:
            sql = fh.read()
        self.assertIn("DISPLAY ONLY", sql)
        self.assertIn("lower(source)", sql)   # one rule per word, whatever case


if __name__ == "__main__":
    unittest.main()


class SlowGenerationCannotLandOnTheWrongChapter(unittest.TestCase):
    """Reported from the household: Iyoḇ 1 showing Estĕr 1's summary.

    Generating study material is a model call taking seconds, and a reader moves on while it
    runs — pressing through chapters is the normal rhythm, and trivial with a remote. The
    response then arrived and was written into whatever chapter was on screen. The stored
    rows were correct throughout; only the display was wrong, which is why it looked like
    data corruption and was not.

    Each generator now captures where the reader was before it asks, and drops the answer if
    they have since moved.
    """

    def setUp(self):
        with open(COMPONENT, encoding="utf-8") as fh:
            self.src = fh.read()

    def test_all_four_generators_check_before_they_write(self):
        # summary, people, places, pronouns — all four had the same shape, so all four
        # could land on the wrong chapter.
        self.assertEqual(self.src.count("positionRef.current !== requestedFor"), 4)

    def test_the_position_is_captured_before_the_request_not_after(self):
        # Captured after the await it would read the CURRENT position and always match,
        # which is the bug wearing a guard.
        for handler in ("handleViewSummary", "handleViewPeople",
                        "handleViewPlaces", "handleGeneratePronouns"):
            start = self.src.index(f"const {handler} = async")
            body = self.src[start:start + 1000]
            with self.subTest(handler=handler):
                self.assertLess(body.index("const requestedFor = positionRef.current"),
                                body.index("await fetch"),
                                f"{handler} captures its position after the request")

    def test_the_position_follows_version_book_and_chapter(self):
        # Version matters too: the same chapter in another translation is different material.
        self.assertIn("positionRef.current = `${versionId}/${book}/${chapter}`", self.src)


class RemoteScrollingIsAnimated(unittest.TestCase):
    """A screenful appearing instantly costs the reader their place on a television."""

    def setUp(self):
        with open(COMPONENT, encoding="utf-8") as fh:
            self.src = fh.read()

    def test_the_arrows_glide_rather_than_jump(self):
        self.assertIn('behavior: smooth ? "smooth" : "auto"', self.src)
        self.assertIn("glide(page)", self.src)
        self.assertIn("glide(-page)", self.src)

    def test_it_honours_a_reduced_motion_preference(self):
        self.assertIn("prefers-reduced-motion", self.src)

    def test_it_no_longer_sets_scrolltop_directly_for_the_arrows(self):
        start = self.src.index("const glide = (delta)")
        body = self.src[start:start + 700]
        self.assertNotIn("pane.scrollTop +=", body)
        self.assertNotIn("pane.scrollTop -=", body)
