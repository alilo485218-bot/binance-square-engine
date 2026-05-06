"""Engagement Assistant — what to do in the first hour after publishing.

Two responsibilities:
  1. Generate human-sounding replies to incoming comments (LLM, with fallback).
  2. Produce a checklist of timed reminders for the first 60 minutes
     (this is the secret to climbing into the Top 10).
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

import google.generativeai as genai

import config

REMINDER_PLAN = [
    (5,  "Reply to the first 3 comments. Aim < 10 minutes — first replies set the tone."),
    (15, "Pin your strongest reply at the top of the thread."),
    (20, "Quote-reply someone with a real number/level. Adds credibility."),
    (30, "Reshare in your community group / DM 3 friends asking for an honest take."),
    (45, "Post a follow-up comment with an UPDATE or NEW DATA point — keeps thread alive."),
    (60, "Final sweep: reply to ALL questions, even one-word ones."),
]

QUESTION_BOOSTERS = [
    "Are you long or short here?",
    "Trap or breakout?",
    "What's your invalidation level?",
    "Buying or waiting?",
    "Bullish or bearish on this news?",
    "Which coin replaces it?",
    "Is this priced in already?",
]


def _load_prompt() -> str:
    path = os.path.join(config.PROMPTS_DIR, "reply.txt")
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    return text


def _fallback_reply(comment: str) -> dict[str, str]:
    is_arabic = bool(re.search(r"[\u0600-\u06FF]", comment))
    if is_arabic:
        reply = "وجهة نظر منطقية. ما هو مستوى الإبطال عندك؟"
        tone = "neutral"
    else:
        c = comment.lower()
        if any(w in c for w in ["scam", "trash", "wrong", "no way", "lol"]):
            reply = "Fair pushback. What level invalidates the setup for you?"
            tone = "disagree"
        elif "?" in comment:
            reply = "Good question. Watching the next 4h candle close. You taking a side?"
            tone = "curious"
        else:
            reply = "Solid take. Where's your invalidation? Mine's nearby."
            tone = "neutral"
    return {"reply": reply, "tone": tone}


def generate_reply(post_body: str, comment: str) -> dict[str, str]:
    """Generate a short reply to a comment on a Binance Square post."""
    if not config.HAS_LLM:
        return _fallback_reply(comment)

    prompt = (_load_prompt()
              .replace("{post_body}", post_body or "")
              .replace("{comment}", comment or ""))
    try:
        genai.configure(api_key=config.GEMINI_API_KEY)
        model = genai.GenerativeModel(
            config.GEMINI_MODEL,
            system_instruction="You output ONLY valid JSON. No markdown, no commentary.",
        )
        resp = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.7,
                "response_mime_type": "application/json",
            },
        )
        return json.loads(_strip_json_fences(resp.text or ""))
    except Exception as exc:  # noqa: BLE001
        print(f"[engagement] Gemini failed, falling back: {exc}")
        return _fallback_reply(comment)


def reminder_plan(post_id: str, published_at_utc: int | None = None) -> list[dict[str, Any]]:
    """Return the post-publish reminder checklist with relative timings."""
    return [
        {
            "post_id": post_id,
            "minute_offset": offset,
            "action": action,
            "fires_at_utc": (published_at_utc + offset * 60) if published_at_utc else None,
            "done": False,
        }
        for offset, action in REMINDER_PLAN
    ]


def suggest_thread_questions(post: dict[str, Any], n: int = 3) -> list[str]:
    """Pick `n` follow-up questions the user can drop in the thread to revive it."""
    coin = (post.get("coin") or "BTC").upper()
    pool = [q.replace("this", f"${coin}") for q in QUESTION_BOOSTERS]
    return pool[:n]
