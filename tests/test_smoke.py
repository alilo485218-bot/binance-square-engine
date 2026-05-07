"""Offline smoke tests — no network, no API keys.

Verifies that the most important modules import and produce sane output via the
deterministic Arabic fallbacks. Run with `python -m pytest tests/` or
`python tests/test_smoke.py`.

We forcibly unset GEMINI_API_KEY before importing so these tests stay offline
(no real API calls, no quota burn) regardless of the developer's environment.
"""
from __future__ import annotations

import os
import sys
import unittest

# Force offline mode BEFORE importing modules so HAS_LLM resolves to False.
os.environ.pop("GEMINI_API_KEY", None)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
config.GEMINI_API_KEY = ""
config.HAS_LLM = False

from modules import (  # noqa: E402
    binance_publisher,
    content_generator,
    engagement_assistant,
    image_generator,
    smart_selector,
)


SAMPLE_COIN = {
    "symbol": "BTC", "name": "Bitcoin", "cashtag": "$BTC",
    "price_usd": 68500.0, "change_24h": -2.3,
    "direction": "down", "rank": 1, "source": "coingecko_trending",
}

SAMPLE_COIN_UP = {
    "symbol": "ETH", "name": "Ethereum", "cashtag": "$ETH",
    "price_usd": 2400.0, "change_24h": 5.7,
    "direction": "up", "rank": 2, "source": "coingecko_trending",
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
        # Arabic question mark or English one accepted.
        self.assertTrue("؟" in post["body"] or "?" in post["body"])
        self.assertGreater(len(post["hook_keywords"]), 0)
        self.assertEqual(len(post["id"]), 10)

    def test_debate_fallback(self):
        post = content_generator.generate_post("debate", SAMPLE_COIN)
        self.assertEqual(post["type"], "debate")
        self.assertTrue("؟" in post["body"] or "?" in post["body"])

    def test_news_fallback(self):
        post = content_generator.generate_post("news", SAMPLE_NEWS)
        self.assertEqual(post["type"], "news")
        self.assertTrue(post["body"])

    def test_signal_fallback_long(self):
        post = content_generator.generate_post("signal", SAMPLE_COIN_UP)
        self.assertEqual(post["type"], "signal")
        self.assertEqual(post["side"], "Long")
        self.assertEqual(post["direction"], "up")
        for key in ("entry", "sl", "tp1", "tp2", "tp3", "leverage"):
            self.assertIn(key, post)
        self.assertIn("Entry", post["body"])
        self.assertIn("Long", post["body"])
        self.assertIn("$ETH", post["body"])

    def test_signal_fallback_short(self):
        post = content_generator.generate_post("signal", SAMPLE_COIN)
        self.assertEqual(post["type"], "signal")
        self.assertEqual(post["side"], "Short")
        self.assertEqual(post["direction"], "down")
        self.assertIn("Short", post["body"])

    def test_giveaway_fallback(self):
        post = content_generator.generate_post("giveaway", SAMPLE_COIN_UP)
        self.assertEqual(post["type"], "giveaway")
        self.assertIn("USDT", post["body"])
        self.assertIn("cryptozhiga", post["body"])
        self.assertIn("keyword", post)

    def test_wrap_up_fallback(self):
        post = content_generator.generate_post(
            "wrap_up", {"coins": [SAMPLE_COIN, SAMPLE_COIN_UP], "symbol": "BTC"})
        self.assertEqual(post["type"], "wrap_up")
        self.assertIn("ملخص", post["body"])
        self.assertIn("wins", post)
        self.assertGreater(len(post["wins"]), 0)

    def test_invalid_type_raises(self):
        with self.assertRaises(ValueError):
            content_generator.generate_post("rant", SAMPLE_COIN)

    def test_batch_includes_signal_and_giveaway(self):
        snap = {"coins": [SAMPLE_COIN, SAMPLE_COIN_UP], "news": [SAMPLE_NEWS]}
        posts = content_generator.generate_batch(snap, n_per_type=1)
        types = [p["type"] for p in posts]
        # batch should contain at least 1 signal + 1 giveaway + 1 wrap_up
        self.assertIn("signal", types)
        self.assertIn("giveaway", types)
        self.assertIn("wrap_up", types)


class SmartSelectorTest(unittest.TestCase):
    def test_score_keys(self):
        post = content_generator.generate_post("analysis", SAMPLE_COIN)
        s = smart_selector.score_post(post, trend_symbols={"BTC"})
        self.assertIn("total", s)
        self.assertIn("breakdown", s)
        self.assertIn("signal_format", s["breakdown"])
        self.assertIn("has_emoji", s["breakdown"])
        self.assertGreater(s["total"], 30)

    def test_signal_outscores_other_types(self):
        signal = content_generator.generate_post("signal", SAMPLE_COIN_UP)
        analysis = content_generator.generate_post("analysis", SAMPLE_COIN_UP)
        ranked = smart_selector.rank_posts([analysis, signal])
        # The signal post should dominate due to signal_format + emoji + entry/sl/tp.
        self.assertEqual(ranked[0]["type"], "signal")

    def test_arabic_question_mark_counts(self):
        post = {
            "type": "debate", "coin": "BTC", "body": "$BTC مفاجأة\nفخ ولا اختراق؟",
            "hook": "$BTC مفاجأة", "direction": "down",
        }
        s = smart_selector.score_post(post, trend_symbols={"BTC"})
        self.assertGreaterEqual(s["breakdown"]["has_question"], 12)

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
    def test_renders_default_png(self):
        post = content_generator.generate_post("analysis", SAMPLE_COIN)
        path = image_generator.render_hook_image(post)
        self.assertTrue(os.path.exists(path))
        self.assertTrue(path.endswith(".png"))
        self.assertGreater(os.path.getsize(path), 5_000)

    def test_renders_signal_card(self):
        post = content_generator.generate_post("signal", SAMPLE_COIN_UP)
        path = image_generator.render_hook_image(post)
        self.assertTrue(os.path.exists(path))
        self.assertGreater(os.path.getsize(path), 8_000)


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
        # Arabic comment should produce Arabic reply.
        self.assertTrue(any("\u0600" <= c <= "\u06FF" for c in r["reply"]))

    def test_reminder_plan_shape_arabic(self):
        plan = engagement_assistant.reminder_plan("post123")
        self.assertEqual(len(plan), 6)
        self.assertEqual(plan[0]["minute_offset"], 5)
        # Plan text should be in Arabic.
        self.assertTrue(any("\u0600" <= c <= "\u06FF" for c in plan[0]["action"]))


class BinancePublisherTest(unittest.TestCase):
    def test_queued_post_renders_hashtags(self):
        p = binance_publisher.QueuedPost(
            text="$BTC حركة قوية",
            hashtags=["BTC", "#Bitcoin", "$ETH"],
        )
        body = p.render_body()
        self.assertIn("$BTC حركة قوية", body)
        self.assertIn("#BTC", body)
        self.assertIn("#Bitcoin", body)
        # cashtag prefix should be replaced by # in hashtags.
        self.assertIn("#ETH", body)

    def test_queued_post_does_not_double_tag(self):
        p = binance_publisher.QueuedPost(
            text="hello #BTC #ETH",
            hashtags=["BTC", "ETH"],
        )
        body = p.render_body()
        # already-present hashtags should not be duplicated.
        self.assertEqual(body.count("#BTC"), 1)
        self.assertEqual(body.count("#ETH"), 1)

    def test_publish_text_dry_run_returns_success(self):
        pub = binance_publisher.SquarePublisher(api_key="")
        r = pub.publish_text("hello world", dry_run=True)
        self.assertTrue(r.success)
        self.assertTrue(r.dry_run)
        self.assertEqual(r.code, "000000")

    def test_publish_text_empty_body_fails(self):
        pub = binance_publisher.SquarePublisher(api_key="")
        r = pub.publish_text("   ", dry_run=True)
        self.assertFalse(r.success)
        self.assertEqual(r.code, "20020")

    def test_publish_queue_dry_run_no_real_sleep(self):
        import random as _rand
        rng = _rand.Random(42)
        sleeps: list[float] = []
        events: list[tuple[str, dict]] = []

        def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        posts = [
            {"text": "post 1 $BTC", "hashtags": ["BTC"]},
            {"text": "post 2 $ETH", "hashtags": ["ETH"]},
            {"text": "post 3 $SOL", "hashtags": ["SOL"]},
        ]
        results = binance_publisher.publish_queue(
            posts, dry_run=True, shuffle=False,
            min_delay_min=5, max_delay_min=30,
            sleep_fn=fake_sleep, rng=rng,
            on_event=lambda s, p: events.append((s, p)),
        )
        # All three should succeed in dry-run.
        self.assertEqual(len(results), 3)
        self.assertTrue(all(r.success for r in results))
        # Two waits happen between three posts (no wait after the last).
        wait_events = [e for e in events if e[0] == "waiting"]
        self.assertEqual(len(wait_events), 2)
        for _, payload in wait_events:
            self.assertGreaterEqual(payload["minutes"], 5)
            self.assertLessEqual(payload["minutes"], 30)
        # sleep_fn should have been called twice with the same totals.
        self.assertEqual(len(sleeps), 2)
        self.assertEqual(int(sleeps[0]), wait_events[0][1]["minutes"] * 60)

    def test_publish_queue_shuffles(self):
        import random as _rand
        # Seed picked so that order changes from input.
        rng = _rand.Random(1)
        posts = [{"text": f"p{i}"} for i in range(5)]
        events: list[tuple[str, dict]] = []
        binance_publisher.publish_queue(
            posts, dry_run=True, shuffle=True,
            min_delay_min=0, max_delay_min=0,
            sleep_fn=lambda s: None, rng=rng,
            on_event=lambda s, p: events.append((s, p)),
        )
        publishing_events = [e[1] for e in events if e[0] == "publishing"]
        self.assertEqual(len(publishing_events), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
