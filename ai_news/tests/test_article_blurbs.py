import os
import sys
import unittest
from unittest import mock
from unittest.mock import PropertyMock

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

sys.path.insert(0, os.path.abspath("ai_news"))

from app.common.blurbs import build_article_blurb
from app.llm.client import LLMClient


class ArticleBlurbTests(unittest.TestCase):
    def test_build_article_blurb_falls_back_to_text_excerpt(self):
        blurb = build_article_blurb(
            title="A rogue AI led to a serious security incident at Meta",
            summary=None,
            snippet=None,
            text=(
                "Meta investigated a rogue AI agent after an internal security incident. "
                "The company isolated the affected systems and reviewed its safeguards."
            ),
            max_length=120,
        )

        self.assertIn("Meta investigated a rogue AI agent", blurb)
        self.assertLessEqual(len(blurb), 123)

    def test_build_article_blurb_falls_back_to_title(self):
        blurb = build_article_blurb(
            title="Generalized Dot-Product Attention: Tackling Real-World Challenges in GPU Kernels",
            summary=None,
            snippet=None,
            text=None,
            max_length=120,
        )

        self.assertEqual(
            blurb,
            "Generalized Dot-Product Attention: Tackling Real-World Challenges in GPU Kernels",
        )

    def test_build_article_blurb_rejects_noisy_text_fallback(self):
        blurb = build_article_blurb(
            title="An open-source AI memory layer that remembers what matters",
            summary=None,
            snippet=None,
            text=".__ .___ .__ __ _ _|__| __| _/____ _____ ____ _____ _____ |__| \\ \\/ \\/ / |/ __ |/ __ \\ / \\_/ __ \\ / \\ \\__ \\",
            max_length=120,
        )

        self.assertEqual(
            blurb,
            "An open-source AI memory layer that remembers what matters",
        )

    def test_build_article_blurb_rejects_noisy_summary(self):
        blurb = build_article_blurb(
            title="An open-source AI memory layer that remembers what matters",
            summary=".__ .___ .__ __ _ _|__| __| _/____ _____ ____ _____ _____ |__| \\ \\/ \\/ / |/ __ |/ __ \\",
            snippet=None,
            text=None,
            max_length=120,
        )

        self.assertEqual(
            blurb,
            "An open-source AI memory layer that remembers what matters",
        )


class SummarizeRecoveryTests(unittest.TestCase):
    def test_summarize_ignores_cached_empty_value_and_recovers_with_json_retry(self):
        client = LLMClient()

        with mock.patch("app.llm.client.get_cached", return_value={"summary": ""}), \
             mock.patch("app.llm.client.set_cached") as set_cached, \
             mock.patch.object(LLMClient, "enabled", new_callable=PropertyMock, return_value=True), \
             mock.patch.object(
                 client,
                 "chat",
                 side_effect=["   ", '{"summary":"Recovered summary from JSON retry."}'],
             ):
            summary = client.summarize(
                "An open-source AI memory layer that remembers what matters",
                "This project introduces a memory layer for agents that keeps durable context.",
            )

        self.assertEqual(summary, "Recovered summary from JSON retry.")
        set_cached.assert_called_once()
        self.assertEqual(set_cached.call_args.args[1]["summary"], "Recovered summary from JSON retry.")

    def test_summarize_does_not_cache_empty_output(self):
        client = LLMClient()

        with mock.patch("app.llm.client.get_cached", return_value=None), \
             mock.patch("app.llm.client.set_cached") as set_cached, \
             mock.patch.object(LLMClient, "enabled", new_callable=PropertyMock, return_value=True), \
             mock.patch.object(
                 client,
                 "chat",
                 side_effect=["   ", '{"summary":"   "}'],
             ):
            summary = client.summarize(
                "Rethinking open source mentorship in the AI era",
                "Maintainers are adapting their mentorship workflows around AI-assisted contribution.",
            )

        self.assertIsNone(summary)
        set_cached.assert_not_called()


if __name__ == "__main__":
    unittest.main()
