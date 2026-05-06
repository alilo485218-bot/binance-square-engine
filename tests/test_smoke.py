"""Offline smoke tests — no network, no API keys.

Verifies that the most important modules import and produce sane output via the
deterministic fallbacks. Run with `python -m pytest tests/` or
`python tests/test_smoke.py`.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import content_generator, engagement_assistant, image_generator, smart_selector  # noqa: E402


SAMPLE_COIN = {
    "symbol": "BTC", "name": "Bitcoin", "cashtag": "$BTC",
    "price_usd": 68500.0, "change_24h": -2.3,
    "direction": "down", "rank": 1, "source": "coingecko_trending",
}

SAMPLE_NEWS = {
    "title": "SEC approves spot ETH ETF",
    "link": "https://example.com/eth-etf",
    "published": "now",
    "source": "test",
}


class ContentGeneratorTest(unittest.TestCase):
    def test_analysis_fallback(self):
        post = content_generator.generate_post("analysis", SAMPLE_COIN)
        self.assertEqual(post["type"], "analysis")
        self.assertEqual(post["coin"], "BTC")
        self.assertTrue(post["body"])
        self.assertIn("?", post["body"])
        self.assertGreater(len(post["hook_keywords"]), 0)
        self.assertEqual(len(post["id"]), 10)

    def test_debate_fallback(self):
        post = content_generator.generate_post("debate", SAMPLE_COIN)
        self.assertEqual(post["type"], "debate")
        self.assertIn("?", post["body"])

    def test_news_fallback(self):
        post = content_generator.generate_post("news", SAMPLE_NEWS)
        self.assertEqual(post["type"], "news")
        self.assertTrue(post["body"])

    def test_invalid_type_raises(self):
        with self.assertRaises(ValueError):
            content_generator.generate_post("rant", SAMPLE_COIN)


class SmartSelectorTest(unittest.TestCase):
    def test_score_keys(self):
        post = content_generator.generate_post("analysis", SAMPLE_COIN)
        s = smart_selector.score_post(post, trend_symbols={"BTC"})
        self.assertIn("total", s)
        self.assertIn("breakdown", s)
        self.assertGreater(s["total"], 30)  # fallback should not be embarrassing

    def test_rank_orders_by_total(self):
        posts = [
            content_generator.generate_post("analysis", SAMPLE_COIN),
            content_generator.generate_post("debate", SAMPLE_COIN),
            content_generator.generate_post("news", SAMPLE_NEWS),
        ]
        ranked = smart_selector.rank_posts(posts)
        scores = [p["score"]["total"] for p in ranked]
        self.assertEqual(scores, sorted(scores, reverse=True))


class ImageGeneratorTest(unittest.TestCase):
    def test_renders_png(self):
        post = content_generator.generate_post("analysis", SAMPLE_COIN)
        path = image_generator.render_hook_image(post)
        self.assertTrue(os.path.exists(path))
        self.assertTrue(path.endswith(".png"))
        self.assertGreater(os.path.getsize(path), 5_000)


class EngagementTest(unittest.TestCase):
    def test_reply_fallback_english(self):
        r = engagement_assistant.generate_reply(
            post_body="$BTC is at a decision point.",
            comment="lol this is wrong, BTC is going to $50k",
        )
        self.assertIn("reply", r)
        self.assertLessEqual(len(r["reply"].split()), 25)

    def test_reply_fallback_arabic(self):
        r = engagement_assistant.generate_reply(
            post_body="$BTC at a decision point.",
            comment="أعتقد أنك مخطئ، BTC هابط",
        )
        self.assertIn("reply", r)

    def test_reminder_plan_shape(self):
        plan = engagement_assistant.reminder_plan("post123")
        self.assertEqual(len(plan), 6)
        self.assertEqual(plan[0]["minute_offset"], 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
