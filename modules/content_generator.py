"""Content Generator — تحويل إشارات الترند إلى بوستات جاهزة للنشر على Binance Square.

ست أنواع من البرومبتس مأخوذة من تشريح حسابات Top 10 (مثل CryptoZhiga):
  - signal    : توصية صفقة كاملة (Long/Short + Entry + SL + TP1/2/3 + Leverage)
  - analysis  : تعليق سوق قصير (Market Take)
  - debate    : رأي استقطابي لإشعال التعليقات (Hot Take)
  - news      : رد فعل على خبر
  - giveaway  : بوست توزيع USDT (محرّك التفاعل الحقيقي)
  - wrap_up   : ملخص أرباح اليوم (Wins of the Day)

كل بوست JSON object فيه: type, coin, cashtag, hook, hook_keywords, body,
direction, cta + حقول إضافية حسب النوع.

يعتمد على Gemini عبر `_call_gemini`، ويسقط إلى قوالب deterministic بالعربي
لو ما في GEMINI_API_KEY (يبقى باقي الـ pipeline يعمل).
"""
from __future__ import annotations

import json
import os
import random
import re
import uuid
from typing import Any

import google.generativeai as genai

import config

PROMPT_TYPES = ("signal", "analysis", "debate", "news", "giveaway", "wrap_up")


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

    if prompt_type == "wrap_up":
        # `signal` is expected to contain a list of coins for wins.
        coins = signal.get("coins") or [signal]
        lines = ["TOP_COINS_TODAY:"]
        for c in coins[:4]:
            sym = c.get("symbol") or c.get("coin") or "BTC"
            ch = c.get("change_24h")
            ch_s = f"{ch:+.2f}%" if ch is not None else "?"
            lines.append(f"  - {sym} 24H {ch_s}")
        return "\n".join(lines)

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
        system_instruction=(
            "You output ONLY valid JSON. No markdown fences, no commentary. "
            "Arabic content is welcome inside JSON string values, but JSON "
            "syntax (keys, braces, commas) MUST stay valid ASCII."
        ),
    )
    resp = model.generate_content(
        prompt,
        generation_config={
            "temperature": 0.85,
            "response_mime_type": "application/json",
        },
    )
    return resp.text or ""


def _round_price(p: float) -> float:
    if p >= 1000:
        return round(p, 0)
    if p >= 10:
        return round(p, 2)
    if p >= 1:
        return round(p, 3)
    return round(p, 6)


def _signal_levels(price: float, side: str) -> dict[str, str]:
    """Compute simple Entry / SL / TP1 / TP2 / TP3 for a fallback signal."""
    if not price or price <= 0:
        price = 1.0
    if side == "Long":
        entry_lo = _round_price(price * 0.998)
        entry_hi = _round_price(price * 1.002)
        sl = _round_price(price * 0.985)
        tp1 = _round_price(price * 1.008)
        tp2 = _round_price(price * 1.015)
        tp3 = _round_price(price * 1.025)
    else:  # Short
        entry_lo = _round_price(price * 0.998)
        entry_hi = _round_price(price * 1.002)
        sl = _round_price(price * 1.015)
        tp1 = _round_price(price * 0.992)
        tp2 = _round_price(price * 0.985)
        tp3 = _round_price(price * 0.975)
    return {
        "entry": f"{entry_lo}-{entry_hi}",
        "sl": str(sl), "tp1": str(tp1), "tp2": str(tp2), "tp3": str(tp3),
    }


def _fallback_post(prompt_type: str, signal: dict[str, Any]) -> dict[str, Any]:
    """Deterministic Arabic templates so the pipeline keeps working without an API key."""
    coin = (signal.get("symbol") or signal.get("coin") or "BTC").upper()
    direction = signal.get("direction", "flat")
    change = signal.get("change_24h")
    price = signal.get("price_usd")

    if prompt_type == "news":
        title = signal.get("title", "خبر كريبتو مهم")
        hook = title.split(".")[0][:50]
        body = (
            f"{hook} 🚨\n"
            f"الأكثر تأثرًا: ${coin}\n"
            f"راقب أول ساعة من رد فعل السعر.\n"
            f"رد فعل صعودي ولا هبوطي؟"
        )
        return {
            "type": "news", "coin": coin, "cashtag": f"${coin}",
            "hook": hook, "body": body, "direction": direction,
            "cta": body.splitlines()[-1],
        }

    if prompt_type == "debate":
        hook = f"${coin} عند هذا السعر فخ"
        body = (
            f"{hook} 🚫\n"
            f"اتجاه آخر 24س: {direction}.\n"
            f"معظم الـ Longs مكتظة. الجمهور نادرًا ما يكون صح.\n"
            f"فخ ولا اختراق؟"
        )
        return {
            "type": "debate", "coin": coin, "cashtag": f"${coin}",
            "hook": hook, "body": body, "direction": direction,
            "cta": body.splitlines()[-1],
        }

    if prompt_type == "signal":
        side = "Long" if (change or 0) >= 0 else "Short"
        levels = _signal_levels(price or 100.0, side)
        leverage = 20 if side == "Long" else 10
        hook = f"${coin} يعطي إشارة {('صعودية' if side=='Long' else 'هبوطية')} 🚀"
        body = (
            f"{hook}\n"
            f"ادخل {side} ${coin} رافعة {leverage}x.\n"
            f"Entry: {levels['entry']} · SL: {levels['sl']} · "
            f"TP1: {levels['tp1']} · TP2: {levels['tp2']} · TP3: {levels['tp3']}\n"
            f"$BTC يقود الموجة، لا تفوّت 🔥"
        )
        return {
            "type": "signal", "coin": coin, "cashtag": f"${coin}",
            "hook": hook, "body": body,
            "direction": "up" if side == "Long" else "down",
            "cta": body.splitlines()[-1],
            "side": side, "leverage": leverage,
            **levels, "pnl_pct": round(random.uniform(15, 35), 2),
        }

    if prompt_type == "giveaway":
        hook = "يا شباب 🙌 شكرًا للدعم"
        body = (
            f"{hook}\n"
            f"أول 100 شخص يكتب 'cryptozhiga' في التعليقات يحصل على 5 USDT 💸\n"
            f"تابعني وفعّل التنبيهات 🔔 + شارك البوست\n"
            f"P.S. حاليًا في Long على ${coin} $ETH $SOL — توصيات جديدة الليلة 🔥"
        )
        return {
            "type": "giveaway", "coin": coin, "cashtag": f"${coin}",
            "hook": hook, "body": body, "direction": "flat",
            "cta": body.splitlines()[-1],
            "keyword": "cryptozhiga",
            "prize": "5 USDT للأول 100 شخص",
        }

    if prompt_type == "wrap_up":
        coins = signal.get("coins") or [signal]
        lines = []
        wins = []
        for c in coins[:3]:
            sym = (c.get("symbol") or c.get("coin") or "BTC").upper()
            ch = abs(c.get("change_24h") or random.uniform(20, 80))
            lev = random.choice([10, 20, 50])
            pnl = round(ch * lev / 5, 2)
            lines.append(f"+{pnl}% على ${sym} رافعة {lev}x ✅")
            wins.append({"coin": sym, "pnl_pct": pnl, "leverage": lev})
        hook = "ملخص اليوم 📊"
        body = (
            f"{hook}\n" + "\n".join(lines) +
            "\nالسوق ما ينام، ولا نحن 😎\n"
            f"watchlist الغد: ${coin} — أيهم تختار؟ 🚀"
        )
        return {
            "type": "wrap_up", "coin": coin, "cashtag": f"${coin}",
            "hook": hook, "body": body, "direction": "up",
            "cta": body.splitlines()[-1],
            "wins": wins,
        }

    # default: analysis
    change_str = f"{change:+.2f}%" if change is not None else "مستويات حرجة"
    hook = f"${coin} عند نقطة قرار"
    body = (
        f"{hook} 🔥\n"
        f"حركة 24س: {change_str}.\n"
        f"- المشترون يحتاجون الدفاع عن الدعم.\n"
        f"- البائعون يحتاجون كسرًا نظيفًا.\n"
        f"Long ولا Short هنا؟"
    )
    return {
        "type": "analysis", "coin": coin, "cashtag": f"${coin}",
        "hook": hook, "body": body, "direction": direction,
        "cta": body.splitlines()[-1],
    }


def _extract_keywords(hook: str, max_words: int = 4) -> list[str]:
    """Pick the strongest 2-4 LATIN words from the hook for the image overlay.

    Image rendering uses Pillow without Arabic shaping, so we strip Arabic and
    keep only Latin/$/digits — which always works on any default font.
    """
    stop = {"the", "a", "an", "is", "to", "of", "in", "on", "at", "and", "or",
            "for", "with", "this", "that", "it", "as", "be"}
    # Keep only Latin letters, $, digits.
    latin_only = re.findall(r"[A-Za-z$0-9]+", hook)
    keep = [w for w in latin_only if w.lower() not in stop]
    if not keep:
        keep = latin_only
    return keep[:max_words] or ["CRYPTO"]


def generate_post(prompt_type: str, signal: dict[str, Any]) -> dict[str, Any]:
    """Generate a single post for one trend signal.

    Args:
        prompt_type: one of PROMPT_TYPES.
        signal: a TrendCoin.to_dict(), TrendNews.to_dict(), or
                {"coins": [...]} for wrap_up.
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
            post.setdefault("type", prompt_type)
        except Exception as exc:  # noqa: BLE001
            print(f"[content_generator] Gemini failed, falling back: {exc}")
            post = _fallback_post(prompt_type, signal)

    # Normalize and stamp.
    if not post.get("hook_keywords"):
        post["hook_keywords"] = _extract_keywords(post.get("hook", ""))
    post["id"] = uuid.uuid4().hex[:10]
    post["source_signal"] = signal
    post["word_count"] = len(re.findall(r"\w+", post.get("body", "")))
    return post


def generate_batch(snapshot: dict[str, Any], n_per_type: int = 1) -> list[dict[str, Any]]:
    """Generate a daily batch reflecting CryptoZhiga's content mix.

    Default mix (per call):
      - 2 signals     (Long/Short trade cards) — top 2 trending coins
      - 1 analysis    (market take on top coin)
      - 1 debate      (hot take on a different coin)
      - 1 news        (top headline)
      - 1 wrap_up     (daily wins) — uses top 3 coins
      - 1 giveaway    (community engine)
    Total 7 posts. `n_per_type` multiplies signal count only (most-used type).
    """
    coins = snapshot.get("coins", [])
    news = snapshot.get("news", [])
    out: list[dict[str, Any]] = []

    # SIGNALS (the bread and butter — 70-75% of CryptoZhiga's feed)
    n_signals = max(1, n_per_type * 2)
    for c in coins[:n_signals]:
        out.append(generate_post("signal", c))

    # ANALYSIS — top coin
    if coins:
        out.append(generate_post("analysis", coins[0]))

    # DEBATE — pick a different coin (or same if only one)
    if len(coins) >= 2:
        out.append(generate_post("debate", coins[1]))
    elif coins:
        out.append(generate_post("debate", coins[0]))

    # NEWS — top headline
    if news:
        out.append(generate_post("news", news[0]))

    # WRAP-UP — multi-coin
    if coins:
        out.append(generate_post("wrap_up", {"coins": coins[:3], "symbol": coins[0].get("symbol", "BTC")}))

    # GIVEAWAY — community engine (always include 1)
    seed = coins[0] if coins else {"symbol": "BTC", "name": "Bitcoin"}
    out.append(generate_post("giveaway", seed))

    return out


if __name__ == "__main__":
    sample = {
        "symbol": "BTC", "name": "Bitcoin", "cashtag": "$BTC",
        "price_usd": 68500, "change_24h": -2.3, "direction": "down", "rank": 1,
    }
    print(json.dumps(generate_post("signal", sample), indent=2, ensure_ascii=False))
