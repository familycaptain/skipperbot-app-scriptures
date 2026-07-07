"""Bound test for spec app.scriptures.llm-endpoints-tier-migration (issue #105).

The four scriptures chapter-LLM helpers must generate through the tier system
(providers.compat.chat_completion, tier 'fast') instead of the removed
config.openai_client. Prose helpers (summary/people/places) return markdown
unchanged; only pronouns is JSON — it drops response_format and parses robustly.

Deterministic: providers.compat.chat_completion is stubbed at the routes module
seam (no network, no real model). Needs the product runtime (imports
apps.scriptures.routes) so it runs on the test host.

Run: python3 -m unittest apps.scriptures.tests.test_llm_endpoints_tier_migration
"""
import os
import re
import unittest
from types import SimpleNamespace
from unittest import mock

import apps.scriptures.routes as routes

ROUTES_SRC = os.path.join(os.path.dirname(routes.__file__), "routes.py")
VERSES = [{"verse": 1, "text": "And he went to his house."},
          {"verse": 2, "text": "She spoke to them."}]


def _stub(content):
    """A fake ChatResult (only .content is consumed)."""
    return SimpleNamespace(content=content)


class TierMigration(unittest.TestCase):

    # (a)+(f) each helper calls chat_completion(tier='fast', ..., max_completion_tokens=16000)
    #         with the same system+user messages (prompt sentinel preserved).
    def test_all_helpers_call_chat_completion_fast(self):
        cases = [
            (lambda: routes._generate_summary_llm("Genesis", 1, "text", "KJV"), "Summarize Genesis"),
            (lambda: routes._generate_people_llm("Genesis", 1, "text", "KJV"), "List every person"),
            (lambda: routes._generate_places_llm("Genesis", 1, "text", "KJV"), "List every place"),
        ]
        for call, sentinel in cases:
            with mock.patch.object(routes, "chat_completion", return_value=_stub("PROSE OUT")) as m:
                out = call()
            self.assertEqual(out, "PROSE OUT")            # prose returned unchanged
            kw = m.call_args.kwargs
            self.assertEqual(kw["tier"], "fast")
            self.assertEqual(kw["max_completion_tokens"], 16000)
            roles = [msg["role"] for msg in kw["messages"]]
            self.assertEqual(roles, ["system", "user"])
            self.assertIn(sentinel, kw["messages"][1]["content"])   # prompt preserved

        with mock.patch.object(routes, "chat_completion",
                               return_value=_stub('{"verses":[]}')) as m:
            routes._generate_pronouns_llm("Genesis", 1, VERSES, "KJV")
        kw = m.call_args.kwargs
        self.assertEqual(kw["tier"], "fast")
        self.assertEqual(kw["max_completion_tokens"], 16000)
        self.assertIn("Resolve pronouns", kw["messages"][1]["content"])

    # (b) source no longer references the removed client / JSON-mode
    def test_source_has_no_legacy_client(self):
        src = open(ROUTES_SRC, encoding="utf-8").read()
        # allow the words in comments/docstrings; assert no CODE usage
        self.assertNotIn("openai_client.chat.completions", src)
        self.assertNotIn("from config import openai_client", src)
        self.assertNotIn("response_format=", src)
        self.assertIn("from providers.compat import chat_completion", src)

    # (c) prose helpers do NOT parse JSON — markdown returned verbatim
    def test_prose_helpers_passthrough(self):
        md = "## Summary\n\n**Adam** did things.\n\nKey Themes:\n- creation"
        for call in (
            lambda: routes._generate_summary_llm("Genesis", 1, "t"),
            lambda: routes._generate_people_llm("Genesis", 1, "t"),
            lambda: routes._generate_places_llm("Genesis", 1, "t"),
        ):
            with mock.patch.object(routes, "chat_completion", return_value=_stub(md)):
                self.assertEqual(call(), md)

    # (d) pronouns JSON parse: fenced AND bare both work; missing 'verses' raises
    def test_pronouns_robust_json(self):
        payload = '{"verses":[{"verse":1,"instances":[{"text":"he","replacement":"Adam"}]}]}'
        for content in (payload, f"```json\n{payload}\n```", f"Here is the JSON:\n{payload}"):
            with mock.patch.object(routes, "chat_completion", return_value=_stub(content)):
                out = routes._generate_pronouns_llm("Genesis", 1, VERSES, "KJV")
            self.assertEqual(out, [{"verse": 1, "instances": [{"text": "he", "replacement": "Adam"}]}])
        # missing 'verses' array -> raise
        with mock.patch.object(routes, "chat_completion", return_value=_stub('{"nope":1}')):
            with self.assertRaises(Exception):
                routes._generate_pronouns_llm("Genesis", 1, VERSES, "KJV")

    # (e) fail-loud: empty content -> prose '' (endpoint's `if not result` then raises);
    #     pronouns parse raises on empty.
    def test_empty_content_behavior(self):
        with mock.patch.object(routes, "chat_completion", return_value=_stub(None)):
            self.assertEqual(routes._generate_summary_llm("Genesis", 1, "t"), "")
            with self.assertRaises(Exception):
                routes._generate_pronouns_llm("Genesis", 1, VERSES, "KJV")

    # (g) model provenance is the tier label
    def test_get_summary_model_is_fast(self):
        self.assertEqual(routes._get_summary_model(), "fast")


if __name__ == "__main__":
    unittest.main()
