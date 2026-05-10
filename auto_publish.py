#!/usr/bin/env python3
"""
نشر تلقائي إلى Binance Square من ملف JSON.

الاستخدام:
    # تشغيل dry-run (آمن، لا يستدعي API)
    python auto_publish.py data/posts.queue.json

    # نشر فعلي (يتطلب X_SQUARE_OPENAPI_KEY في البيئة)
    python auto_publish.py data/posts.queue.json --live

    # تخصيص التأخير
    python auto_publish.py data/posts.queue.json --live --min 5 --max 30

    # عدم خلط الطابور
    python auto_publish.py data/posts.queue.json --live --no-shuffle

تنسيق ملف JSON المتوقع:
    [
      {"text": "...", "image_path": "...", "hashtags": ["BTC", "ETH"]},
      ...
    ]

ملاحظات:
- الـ API يدعم نصًا فقط حاليًا. الصور تُسجَّل في log فقط (ارفعها يدويًا).
- التأخير العشوائي بين بوست وآخر افتراضيًا 5-30 دقيقة.
- توقّف تلقائي إذا تجاوزنا الحد اليومي أو حدث خطأ نهائي (مثل ban).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from modules.binance_publisher import (
    QueuedPost,
    SquarePublisher,
    publish_queue,
)


def _load_queue(path: Path) -> list[QueuedPost]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise SystemExit(f"expected a JSON array, got {type(raw).__name__}")
    queue: list[QueuedPost] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise SystemExit(f"item {i}: must be an object")
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            raise SystemExit(f"item {i}: 'text' is required and must be a non-empty string")
        queue.append(QueuedPost(
            text=text,
            image_path=item.get("image_path") or None,
            hashtags=list(item.get("hashtags") or []),
            post_id=item.get("id") or item.get("post_id"),
        ))
    return queue


def _on_event(stage: str, payload: dict) -> None:
    if stage == "publishing":
        print(f"[{payload['index'] + 1}/{payload['total']}] جاري النشر...")
    elif stage == "published":
        if payload["success"]:
            url = payload.get("post_url") or "(dry-run, no URL)"
            print(f"  ✓ نُشر: {url}")
            if payload.get("image_path"):
                print(f"  📎 تذكير: ارفع الصورة يدويًا — {payload['image_path']}")
        else:
            print(f"  ✗ فشل: code={payload.get('code')} — {payload.get('error')}")
    elif stage == "waiting":
        print(f"  ⏰ ننتظر {payload['minutes']} دقيقة قبل البوست التالي...")
    elif stage == "daily_cap_reached":
        print(f"  ⚠ توقفنا — تجاوزنا الحد اليومي ({payload['cap']})")
    elif stage == "aborted":
        print(f"  ⛔ توقفنا: {payload['reason']} — {payload.get('message')}")
    elif stage == "done":
        print(f"\nانتهى. نجح: {payload['succeeded']} · فشل: {payload['failed']} · إجمالي: {payload['total']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Binance Square auto-publisher")
    parser.add_argument("queue_file", type=Path, help="JSON file with posts array")
    parser.add_argument("--live", action="store_true",
                        help="ينشر فعليًا (افتراضي: dry-run)")
    parser.add_argument("--min", dest="min_delay", type=int, default=None,
                        help="أقل تأخير بالدقائق (افتراضي 5)")
    parser.add_argument("--max", dest="max_delay", type=int, default=None,
                        help="أقصى تأخير بالدقائق (افتراضي 30)")
    parser.add_argument("--cap", dest="cap", type=int, default=None,
                        help="حد أقصى يومي للنشر (افتراضي 12)")
    parser.add_argument("--no-shuffle", action="store_true",
                        help="لا تخلط ترتيب البوستات")
    args = parser.parse_args()

    if not args.queue_file.exists():
        print(f"file not found: {args.queue_file}", file=sys.stderr)
        return 2

    queue = _load_queue(args.queue_file)
    if not queue:
        print("queue is empty", file=sys.stderr)
        return 1

    publisher = SquarePublisher()
    mode = "LIVE" if args.live else "DRY-RUN"
    key_disp = publisher.masked_key() or "(لا يوجد مفتاح)"
    print(f"Binance Square Auto-Publisher — {mode}")
    print(f"  مفتاح API: {key_disp}")
    print(f"  عدد البوستات: {len(queue)}")
    print(f"  تأخير: {args.min_delay or 5}-{args.max_delay or 30} دقيقة")
    print(f"  shuffle: {'لا' if args.no_shuffle else 'نعم'}\n")

    if args.live and not publisher.api_key:
        print("✗ --live يحتاج X_SQUARE_OPENAPI_KEY في البيئة", file=sys.stderr)
        return 3

    results = publish_queue(
        queue,
        dry_run=not args.live,
        shuffle=not args.no_shuffle,
        min_delay_min=args.min_delay,
        max_delay_min=args.max_delay,
        daily_cap=args.cap,
        on_event=_on_event,
        publisher=publisher,
    )
    failures = sum(1 for r in results if not r.success)
    return 0 if failures == 0 else 4


if __name__ == "__main__":
    raise SystemExit(main())
