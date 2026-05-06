"""Engagement Assistant — ماذا تفعل في أول ساعة بعد النشر (سر التوب 10).

مسؤوليتان:
  1. توليد ردود إنسانية على التعليقات (Gemini مع fallback).
  2. خطة تذكيرات بأول 60 دقيقة بعد النشر — هذه هي المفتاح للوصول إلى Top 10.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

import google.generativeai as genai

import config

# قائمة تذكيرات أول ساعة (بالعربي مباشرة لاستخدامها في الواجهة).
REMINDER_PLAN = [
    (5,  "ردّ على أول 3 تعليقات. الهدف < 10 دقائق — أول الردود تحدد إيقاع الخيط."),
    (15, "ثبّت أقوى رد عندك في أعلى الخيط (Pin)."),
    (20, "اعمل Quote-reply لأحدهم بمستوى رقمي حقيقي. يضيف مصداقية."),
    (30, "شارك البوست في مجموعتك أو DM لـ 3 أصدقاء يطلب رأيهم الصريح."),
    (45, "انشر تعليق متابعة فيه UPDATE أو رقم جديد — لإبقاء الخيط حيًا."),
    (60, "كنس نهائي: ردّ على كل سؤال حتى الكلمة الواحدة."),
]

QUESTION_BOOSTERS = [
    "أنت في Long ولا Short هنا؟",
    "فخ ولا اختراق؟",
    "ما مستوى الإبطال (invalidation) عندك؟",
    "تشتري أو تنتظر؟",
    "هل ستشارك في الموجة؟",
    "صعودي ولا هبوطي على هذا الخبر؟",
    "أي عملة تأخذ مكانه؟",
    "هل السعر مسبقًا مسعّر بالخبر؟",
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
        c = comment
        if any(w in c for w in ["نصب", "هراء", "خطأ", "غلط", "كذب", "مستحيل"]):
            reply = "ملاحظة جيدة. ما المستوى الذي يبطل الإعداد عندك؟"
            tone = "disagree"
        elif "؟" in c or "?" in c:
            reply = "سؤال ممتاز. أراقب إغلاق شمعة 4 ساعات. ما رأيك؟"
            tone = "curious"
        else:
            reply = "وجهة نظر منطقية. أين الإبطال عندك؟ عندي قريب."
            tone = "neutral"
        return {"reply": reply, "tone": tone}

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
            system_instruction=(
                "You output ONLY valid JSON. No markdown, no commentary. "
                "Arabic content inside JSON string values is welcome."
            ),
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
    """خطة التذكيرات بعد النشر — قائمة 6 مهام بعد +5/+15/+20/+30/+45/+60 دقيقة."""
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
    """اقتراح أسئلة لإحياء الخيط بعد النشر."""
    coin = (post.get("coin") or "BTC").upper()
    pool = [q.replace("هنا", f"على ${coin}") for q in QUESTION_BOOSTERS]
    return pool[:n]
