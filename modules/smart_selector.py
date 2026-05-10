"""Smart Selector — تقييم البوستات واختيار الأفضل (محدَّث لأسلوب CryptoZhiga).

نظام تقييم من 100:
  - hook_strength      (0-25)  Hook ≤ 8 كلمات، ينتهي بضربة، لا يبدأ بمقدمة عامة
  - has_trend_coin     (0-15)  يذكر BTC/ETH أو رمز ترند
  - has_question       (0-12)  CTA سؤال في النهاية (يدعم ? و ؟)
  - length_ok          (0-10)  جسم البوست بطول مناسب لكل نوع
  - has_cashtag        (0-8)   فيه نمط $XYZ
  - has_number         (0-8)   فيه رقم (سعر، نسبة، مستوى)
  - has_directional    (0-4)   موقف up/down واضح
  - signal_format      (0-10)  فيه Entry/SL/TP لو نوعه signal
  - has_emoji          (0-5)   إيموجي 1-3 (أسلوب CryptoZhiga البصري)
  - bullish_tag        (0-3)   كلمات Bullish/Bearish/صعود/هبوط
"""
from __future__ import annotations

import re
from typing import Any

# عملات تُحسب دائمًا "ترند" لأنها الأكثر تداولًا.
ALWAYS_TREND = {"BTC", "ETH", "SOL", "BNB", "XRP", "DOGE"}

WEAK_HOOK_STARTS_EN = (
    "today", "let's", "lets ", "in this", "here is", "here's", "just in",
    "breaking", "i think", "imho",
)
WEAK_HOOK_STARTS_AR = (
    "اليوم ", "هلموا", "في هذا", "هنا ", "خبر عاجل", "أعتقد", "في رأيي",
)

# Range of body word counts that fit each post type's CryptoZhiga DNA.
LENGTH_RANGES = {
    "signal":   (15, 70),
    "analysis": (25, 90),
    "debate":   (20, 80),
    "news":     (20, 80),
    "wrap_up":  (20, 90),
    "giveaway": (25, 100),
}

EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F700-\U0001F77F"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\u2600-\u27BF"          # misc symbols
    "]"
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
    if hook.strip().endswith((".", "?", "!", "؟", "...")):
        score += 5
    weak = WEAK_HOOK_STARTS_EN + WEAK_HOOK_STARTS_AR
    if not any(hook.lower().startswith(p) for p in weak):
        score += 5
    return min(score, 25)


def _score_trend_coin(post: dict[str, Any], trend_symbols: set[str]) -> int:
    coin = (post.get("coin") or "").upper()
    if coin in ALWAYS_TREND:
        return 15
    if coin in trend_symbols:
        return 13
    body = post.get("body", "").upper()
    if any(t in body for t in ALWAYS_TREND):
        return 7
    return 0


def _score_question(post: dict[str, Any]) -> int:
    body = post.get("body", "")
    last_line = body.splitlines()[-1] if body else ""
    if "?" in last_line or "؟" in last_line:
        return 12
    if "?" in body or "؟" in body:
        return 4
    return 0


def _score_length(post: dict[str, Any]) -> int:
    n = post.get("word_count") or len(re.findall(r"\w+", post.get("body", "")))
    lo, hi = LENGTH_RANGES.get(post.get("type", "analysis"), (25, 90))
    if lo <= n <= hi:
        return 10
    if lo - 10 <= n < lo or hi < n <= hi + 20:
        return 5
    return 0


def _score_cashtag(post: dict[str, Any]) -> int:
    return 8 if re.search(r"\$[A-Z]{2,6}", post.get("body", "")) else 0


def _score_number(post: dict[str, Any]) -> int:
    return 8 if re.search(r"\d", post.get("body", "")) else 0


def _score_direction(post: dict[str, Any]) -> int:
    return 4 if post.get("direction") in {"up", "down"} else 0


def _score_signal_format(post: dict[str, Any]) -> int:
    """Reward signal posts that actually carry Entry/SL/TP data."""
    if post.get("type") != "signal":
        return 0
    body = post.get("body", "")
    has_entry = "entry" in body.lower() or post.get("entry")
    has_sl = "sl" in body.lower() or "stop" in body.lower() or post.get("sl")
    has_tp = ("tp1" in body.lower() or "tp:" in body.lower()
              or post.get("tp1") or post.get("tp2"))
    has_lev = "x" in body.lower() and re.search(r"\b\d+x", body.lower()) or post.get("leverage")
    pts = 0
    if has_entry: pts += 3
    if has_sl:    pts += 3
    if has_tp:    pts += 3
    if has_lev:   pts += 1
    return min(pts, 10)


def _score_emoji(post: dict[str, Any]) -> int:
    body = post.get("body", "")
    n = len(EMOJI_RE.findall(body))
    if 1 <= n <= 3:
        return 5
    if n == 4:
        return 3
    return 0


def _score_bullish_tag(post: dict[str, Any]) -> int:
    body = post.get("body", "")
    keywords = ("Bullish", "Bearish", "Long", "Short",
                "صعودي", "هبوطي", "صعود", "هبوط")
    return 3 if any(k in body for k in keywords) else 0


def score_post(post: dict[str, Any], trend_symbols: set[str] | None = None) -> dict[str, Any]:
    trend_symbols = trend_symbols or set()
    breakdown = {
        "hook_strength":  _score_hook(post.get("hook", "")),
        "has_trend_coin": _score_trend_coin(post, trend_symbols),
        "has_question":   _score_question(post),
        "length_ok":      _score_length(post),
        "has_cashtag":    _score_cashtag(post),
        "has_number":     _score_number(post),
        "has_directional": _score_direction(post),
        "signal_format":  _score_signal_format(post),
        "has_emoji":      _score_emoji(post),
        "bullish_tag":    _score_bullish_tag(post),
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
