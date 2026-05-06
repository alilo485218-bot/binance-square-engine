"""Smart Selector — score generated posts and pick the best one(s) to publish.

Scoring philosophy (out of 100):
  - hook_strength      (0-25)  Hook ≤ 8 words, ends punchy, not a generic intro
  - has_trend_coin     (0-20)  Mentions BTC, ETH, or a trending symbol
  - has_question       (0-15)  CTA question at the end
  - length_ok          (0-15)  Body word count between 40 and 120
  - has_cashtag        (0-10)  Contains $XYZ pattern
  - has_number         (0-10)  Mentions a concrete number (price, %, level)
  - has_directional    (0-5)   Clear up/down stance
"""
from __future__ import annotations

import re
from typing import Any

# Coins that always count as "trend" because they're the most-traded on Binance.
ALWAYS_TREND = {"BTC", "ETH", "SOL", "BNB", "XRP", "DOGE"}

WEAK_HOOK_STARTS = (
    "today", "let's", "lets ", "in this", "here is", "here's", "just in",
    "breaking", "i think", "imho",
)


def _score_hook(hook: str) -> int:
    if not hook:
        return 0
    words = re.findall(r"\S+", hook)
    score = 0
    if 3 <= len(words) <= 8:
        score += 15
    elif len(words) <= 10:
        score += 8
    if hook.strip().endswith((".", "?", "!", "...")):
        score += 5
    if not any(hook.lower().startswith(p) for p in WEAK_HOOK_STARTS):
        score += 5
    return min(score, 25)


def _score_trend_coin(post: dict[str, Any], trend_symbols: set[str]) -> int:
    coin = (post.get("coin") or "").upper()
    if coin in ALWAYS_TREND:
        return 20
    if coin in trend_symbols:
        return 18
    body = post.get("body", "").upper()
    if any(t in body for t in ALWAYS_TREND):
        return 10
    return 0


def _score_question(post: dict[str, Any]) -> int:
    body = post.get("body", "")
    if "?" in body.splitlines()[-1] if body else False:
        return 15
    return 5 if "?" in body else 0


def _score_length(post: dict[str, Any]) -> int:
    n = post.get("word_count") or len(re.findall(r"\w+", post.get("body", "")))
    if 40 <= n <= 120:
        return 15
    if 25 <= n < 40 or 120 < n <= 140:
        return 8
    return 0


def _score_cashtag(post: dict[str, Any]) -> int:
    return 10 if re.search(r"\$[A-Z]{2,6}", post.get("body", "")) else 0


def _score_number(post: dict[str, Any]) -> int:
    body = post.get("body", "")
    if re.search(r"\d", body):
        return 10
    return 0


def _score_direction(post: dict[str, Any]) -> int:
    return 5 if post.get("direction") in {"up", "down"} else 0


def score_post(post: dict[str, Any], trend_symbols: set[str] | None = None) -> dict[str, Any]:
    trend_symbols = trend_symbols or set()
    breakdown = {
        "hook_strength": _score_hook(post.get("hook", "")),
        "has_trend_coin": _score_trend_coin(post, trend_symbols),
        "has_question": _score_question(post),
        "length_ok": _score_length(post),
        "has_cashtag": _score_cashtag(post),
        "has_number": _score_number(post),
        "has_directional": _score_direction(post),
    }
    total = sum(breakdown.values())
    return {"total": total, "breakdown": breakdown}


def rank_posts(posts: list[dict[str, Any]],
               snapshot: dict[str, Any] | None = None,
               top_n: int | None = None) -> list[dict[str, Any]]:
    """Return posts sorted best-first, each annotated with `score`."""
    trend_symbols = set()
    if snapshot:
        trend_symbols = {(c.get("symbol") or "").upper() for c in snapshot.get("coins", [])}

    scored = []
    for post in posts:
        s = score_post(post, trend_symbols)
        new = dict(post)
        new["score"] = s
        scored.append(new)

    scored.sort(key=lambda p: p["score"]["total"], reverse=True)
    return scored[:top_n] if top_n else scored
