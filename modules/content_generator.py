"""Content Generator — turn trend signals into ready-to-post Binance Square content.

Three prompt types:
  - analysis : technical/on-chain take on a coin
  - news     : reaction to a news headline
  - debate   : contrarian/polarizing take to drive comments

Each generated post is a JSON object with: type, coin, cashtag, hook, hook_keywords,
body, direction, cta.

Falls back to a deterministic template if GEMINI_API_KEY is missing, so the rest of
the pipeline (selector, image generator, scheduler) keeps working without an LLM.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any

import google.generativeai as genai

import config

PROMPT_TYPES = ("analysis", "news", "debate")


def _load_prompt(prompt_type: str) -> str:
    path = os.path.join(config.PROMPTS_DIR, f"{prompt_type}.txt")
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _build_input_block(prompt_type: str, signal: dict[str, Any]) -> str:
    """Render the trend signal into the {input_block} slot of each prompt."""
    if prompt_type == "news":
        title = signal.get("title", "")
        link = signal.get("link", "")
        return f"HEADLINE: {title}\nLINK: {link}"

    coin = signal.get("symbol") or signal.get("coin") or "BTC"
    name = signal.get("name") or coin
    price = signal.get("price_usd")
    change = signal.get("change_24h")
    direction = signal.get("direction", "flat")
    rank = signal.get("rank")
    parts = [
        f"COIN: {coin} ({name})",
        f"DIRECTION_24H: {direction}",
    ]
    if price is not None:
        parts.append(f"PRICE_USD: {price}")
    if change is not None:
        parts.append(f"CHANGE_24H_PCT: {change:+.2f}")
    if rank:
        parts.append(f"MARKET_CAP_RANK: {rank}")
    return "\n".join(parts)


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    return text


def _call_gemini(prompt: str) -> str:
    genai.configure(api_key=config.GEMINI_API_KEY)
    model = genai.GenerativeModel(
        config.GEMINI_MODEL,
        system_instruction="You output ONLY valid JSON. No markdown, no commentary.",
    )
    resp = model.generate_content(
        prompt,
        generation_config={
            "temperature": 0.85,
            "response_mime_type": "application/json",
        },
    )
    return resp.text or ""


def _fallback_post(prompt_type: str, signal: dict[str, Any]) -> dict[str, Any]:
    """Used when no API key is present — keeps the rest of the system functional."""
    coin = (signal.get("symbol") or signal.get("coin") or "BTC").upper()
    direction = signal.get("direction", "flat")
    change = signal.get("change_24h")

    if prompt_type == "news":
        title = signal.get("title", "Major crypto news")
        hook = title.split(".")[0][:50]
        body = (
            f"{hook}.\n"
            f"This impacts ${coin} the most.\n"
            f"Watch for the first hour of price action.\n"
            f"Bullish or bearish reaction here?"
        )
    elif prompt_type == "debate":
        hook = f"${coin} at this level is a trap."
        body = (
            f"{hook}\n"
            f"Direction last 24h: {direction}.\n"
            f"Most longs are crowded. Crowd is rarely right.\n"
            f"Trap or breakout — what side are you on?"
        )
    else:  # analysis
        change_str = f"{change:+.2f}%" if change is not None else "key levels"
        hook = f"${coin} is at a decision point."
        body = (
            f"{hook}\n"
            f"24h move: {change_str}.\n"
            f"- Bulls need to defend support.\n"
            f"- Bears need a clean break.\n"
            f"Long or short here?"
        )

    return {
        "type": prompt_type,
        "coin": coin,
        "cashtag": f"${coin}",
        "hook": hook,
        "hook_keywords": _extract_keywords(hook),
        "body": body,
        "direction": direction,
        "cta": body.splitlines()[-1],
    }


def _extract_keywords(hook: str, max_words: int = 4) -> list[str]:
    """Pick the strongest 2-4 words from the hook for the image overlay."""
    stop = {"the", "a", "an", "is", "to", "of", "in", "on", "at", "and", "or",
            "for", "with", "this", "that", "it", "as", "be"}
    words = re.findall(r"[A-Za-z$0-9]+", hook)
    keep = [w for w in words if w.lower() not in stop]
    if not keep:
        keep = words
    return keep[:max_words] or [hook[:20]]


def generate_post(prompt_type: str, signal: dict[str, Any]) -> dict[str, Any]:
    """Generate a single post for one trend signal.

    Args:
        prompt_type: one of "analysis", "news", "debate".
        signal: a TrendCoin.to_dict() OR TrendNews.to_dict().
    """
    if prompt_type not in PROMPT_TYPES:
        raise ValueError(f"prompt_type must be one of {PROMPT_TYPES}")

    if not config.HAS_LLM:
        post = _fallback_post(prompt_type, signal)
    else:
        template = _load_prompt(prompt_type)
        prompt = template.replace("{input_block}", _build_input_block(prompt_type, signal))
        try:
            raw = _call_gemini(prompt)
            post = json.loads(_strip_json_fences(raw))
        except Exception as exc:  # noqa: BLE001
            print(f"[content_generator] Gemini failed, falling back: {exc}")
            post = _fallback_post(prompt_type, signal)

    # Normalize and stamp.
    post.setdefault("hook_keywords", _extract_keywords(post.get("hook", "")))
    post["id"] = uuid.uuid4().hex[:10]
    post["source_signal"] = signal
    post["word_count"] = len(re.findall(r"\w+", post.get("body", "")))
    return post


def generate_batch(snapshot: dict[str, Any], n_per_type: int = 2) -> list[dict[str, Any]]:
    """Generate a batch of posts from a Trend Engine snapshot.

    By default: 2 analysis + 2 debate (from top coins) + 2 news (from headlines).
    """
    coins = snapshot.get("coins", [])[:max(n_per_type * 2, 4)]
    news = snapshot.get("news", [])[:n_per_type]
    out: list[dict[str, Any]] = []

    for coin in coins[:n_per_type]:
        out.append(generate_post("analysis", coin))
    for coin in coins[n_per_type: n_per_type * 2]:
        out.append(generate_post("debate", coin))
    for headline in news:
        out.append(generate_post("news", headline))

    return out


if __name__ == "__main__":
    sample = {
        "symbol": "BTC", "name": "Bitcoin", "cashtag": "$BTC",
        "price_usd": 68500, "change_24h": -2.3, "direction": "down", "rank": 1,
    }
    print(json.dumps(generate_post("analysis", sample), indent=2, ensure_ascii=False))
