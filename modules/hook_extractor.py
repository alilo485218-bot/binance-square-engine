"""Hook Extractor — يحوّل البوست إلى Hook بصري قوي (3-5 كلمات لاتينية).

الهدف: كل بوست لازم يكون عنده "بطل بصري" مكوّن من 3-5 كلمات صادمة باللاتيني،
تظهر في وسط الصورة بخط ضخم وتكسر السكرول.

Why Latin? لأن Pillow ما يدعم تشكيل العربي بشكل موثوق، والمستخدم العربي على
Binance Square يفهم cashtags + كلمات قوة إنجليزية (BREAKOUT, PUMP, ALERT)
هذا هو نمط CryptoZhiga نفسه: الصور إنجليزي/أرقام، الـ caption عربي/روسي.

Two paths:
- `extract_hook(post)` يستدعي Gemini ليقترح أفضل 3-5 كلمات.
- `fallback_hook(post)` template deterministic لو ما في API key.

تطبّق دائمًا قواعد الـ CTR:
- لا تزيد عن 5 كلمات
- بدون أرقام طويلة (إلا إذا كانت Hook قوية مثل "95% WILL LOSE")
- استخدم power-words: BREAKOUT, PUMP, DUMP, ALERT, NOW, READY, FLIP, TRAP, RUG
- النتيجة UPPERCASE دائمًا
"""
from __future__ import annotations

import json
import re
from typing import Any

try:
    import google.generativeai as genai
except ImportError:
    genai = None  # type: ignore

import config


# الكلمات الذهبية: كلمات قوة معروفة بزيادة CTR على crypto-twitter / Binance Square.
POWER_WORDS_UP = (
    "BREAKOUT", "PUMP", "SURGE", "MOON", "READY", "EXPLODES",
    "ABOUT TO PUMP", "ABOUT TO MOON", "IGNITES", "TAKES OFF", "RIPS",
)
POWER_WORDS_DOWN = (
    "DUMP", "CRASH", "TRAP", "RUG", "ALERT", "DANGER", "WILL LOSE",
    "FAKE OUT", "BREAKDOWN", "FLUSH", "RUG PULL",
)
POWER_WORDS_NEWS = (
    "BREAKING", "ALERT", "JUST IN", "NOW", "HUGE NEWS", "MARKET MOVER",
    "WATCH THIS", "GAME CHANGER",
)
POWER_WORDS_GIVEAWAY = (
    "FREE USDT", "WIN BIG", "ENTER NOW", "GIVEAWAY ALERT",
    "GRAB IT", "DON'T MISS",
)

# مفردات يجب تنظيفها — لا تدخل الـ hook.
BANNED_CHARS_PATTERN = re.compile(r"[^A-Za-z0-9$%! ?]+")

MAX_HOOK_WORDS = 5
MIN_HOOK_WORDS = 2


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def extract_hook(post: dict[str, Any]) -> str:
    """يرجع 3-5 كلمات لاتينية UPPERCASE تصلح كـ image hook."""
    existing = post.get("hook_keywords")
    if existing and isinstance(existing, list):
        cand = _clean(" ".join(str(k) for k in existing))
        if _valid(cand):
            return _polish(cand, post)

    if config.HAS_LLM and genai is not None:
        try:
            llm_hook = _llm_hook(post)
            if llm_hook:
                return _polish(llm_hook, post)
        except Exception:  # noqa: BLE001
            pass

    return _polish(fallback_hook(post), post)


def fallback_hook(post: dict[str, Any]) -> str:
    """قالب جاهز عند غياب الـ LLM — يستخدم نوع البوست + الاتجاه."""
    coin = (post.get("coin") or "BTC").upper()
    cashtag = post.get("cashtag") or f"${coin}"
    ptype = (post.get("type") or "").lower()
    direction = (post.get("direction") or "flat").lower()
    side = (post.get("side") or "").lower()

    if ptype == "signal":
        if side == "long" or direction == "up":
            return f"{cashtag} READY TO PUMP"
        if side == "short" or direction == "down":
            return f"{cashtag} BREAKDOWN ALERT"
        return f"{cashtag} SIGNAL NOW"

    if ptype == "giveaway":
        return f"FREE USDT {cashtag}"

    if ptype == "news":
        return f"BREAKING {cashtag} NEWS"

    if ptype == "debate":
        return f"{cashtag} TRAP OR BREAKOUT?"

    if ptype == "wrap_up":
        return f"TODAY'S TOP WINS"

    # analysis / fallback
    if direction == "up":
        return f"{cashtag} ABOUT TO PUMP"
    if direction == "down":
        return f"{cashtag} DANGER ZONE"
    return f"{cashtag} CRITICAL LEVEL"


# ------------------------------------------------------------------
# Internals
# ------------------------------------------------------------------

def _llm_hook(post: dict[str, Any]) -> str:
    """يطلب من Gemini hook قصير. system instruction قوي + few-shot."""
    genai.configure(api_key=config.GEMINI_API_KEY)
    model = genai.GenerativeModel(
        config.GEMINI_MODEL,
        system_instruction=(
            "You are a Binance Square image-hook writer. "
            "You MUST output EXACTLY 3-5 English words in UPPERCASE, nothing else. "
            "Allowed characters: A-Z, 0-9, $, %, ?. "
            "Never output less than 3 words. Never output more than 5 words. "
            "Use punchy power words: BREAKOUT, PUMP, DUMP, TRAP, ALERT, MOON, "
            "READY, NOW, CRASH, RUG, SURGE, EXPLODES, RIPS, FLUSH, DANGER, ZONE."
        ),
    )

    summary = _post_summary(post)
    prompt = f"""POST CONTEXT:
{summary}

Examples of perfect hooks (study the shape, do not copy):
- "$BTC BREAKOUT NOW"
- "95% WILL LOSE"
- "$ETH READY TO PUMP"
- "DUMP INCOMING $SOL"
- "$DOGE DANGER ZONE"
- "TODAY'S BIG WIN"
- "$TON ABOUT TO PUMP"

Write ONE image hook for the POST above. Output EXACTLY 3-5 words in UPPERCASE.
No quotes, no JSON, no explanation. Just the hook."""
    resp = model.generate_content(
        prompt,
        generation_config={
            "temperature": 0.9,
            "max_output_tokens": 64,
        },
    )
    text = (resp.text or "").strip()
    text = re.sub(r"^[\"'`]+|[\"'`]+$", "", text).strip()
    text = text.split("\n")[0].strip()
    return _clean(text)


def _post_summary(post: dict[str, Any]) -> str:
    """ضغط البوست في وصف قصير للـ LLM."""
    parts: list[str] = []
    if post.get("type"):
        parts.append(f"type: {post['type']}")
    if post.get("coin"):
        parts.append(f"coin: {post['coin']}")
    if post.get("cashtag"):
        parts.append(f"cashtag: {post['cashtag']}")
    if post.get("direction"):
        parts.append(f"direction: {post['direction']}")
    if post.get("side"):
        parts.append(f"side: {post['side']}")
    if post.get("hook"):
        # truncate to avoid bloating the prompt
        parts.append(f"original_hook: {str(post['hook'])[:120]}")
    body = post.get("body", "")
    if body:
        snippet = " ".join(str(body).split())[:180]
        parts.append(f"body_snippet: {snippet}")
    return "\n".join(parts)


def _clean(s: str) -> str:
    s = BANNED_CHARS_PATTERN.sub(" ", s or "")
    s = re.sub(r"\s+", " ", s).strip().upper()
    return s


def _valid(s: str) -> bool:
    if not s:
        return False
    wc = len([w for w in s.split() if w])
    return MIN_HOOK_WORDS <= wc <= MAX_HOOK_WORDS


def _polish(s: str, post: dict[str, Any]) -> str:
    """ضغط إلى حد أقصى 5 كلمات + ضمان وجود كلمات حقيقية + ضمان جودة الـ hook."""
    s = _clean(s)
    words = _meaningful_words(s)

    # If result is junk (single letter, lone $, etc) drop it and use fallback.
    if not _is_meaningful(words):
        words = _meaningful_words(_clean(fallback_hook(post)))

    if not words:
        return "CRYPTO ALERT"

    if len(words) > MAX_HOOK_WORDS:
        words = words[:MAX_HOOK_WORDS]

    if len(words) < MIN_HOOK_WORDS:
        direction = (post.get("direction") or "flat").lower()
        side = (post.get("side") or "").lower()
        if side == "long" or direction == "up":
            words.append("BREAKOUT")
        elif side == "short" or direction == "down":
            words.append("ALERT")
        else:
            words.append("NOW")

    return " ".join(words)


def _meaningful_words(s: str) -> list[str]:
    """يستبعد الكلمات التي تتكوّن من حرف واحد فقط (إلا الـ cashtag)."""
    words = []
    for w in s.split():
        # cashtag $XXX is allowed
        if w.startswith("$") and len(w) >= 2:
            words.append(w)
        elif len(w) >= 2:
            words.append(w)
    return words


def _is_meaningful(words: list[str]) -> bool:
    """A hook is meaningful if it has >=2 real tokens, including a verb-ish word."""
    if len(words) < MIN_HOOK_WORDS:
        return False
    # at least one non-cashtag word with >= 3 letters
    has_word = any((not w.startswith("$")) and len(w) >= 3 for w in words)
    return has_word
