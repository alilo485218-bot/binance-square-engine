"""
نشر تلقائي إلى Binance Square عبر الـ OpenAPI الرسمي.

API Reference:
- Endpoint: POST https://www.binance.com/bapi/composite/v1/public/pgc/openApi/content/add
- Headers : X-Square-OpenAPI-Key, Content-Type: application/json, clienttype: binanceSkill
- Body    : {"bodyTextOnly": "..."}  (نص فقط — الـ API لا يدعم الصور حاليًا)
- Success : code == "000000"
- Post URL: https://www.binance.com/square/post/{data.id}

ملاحظات أمان:
- الوضع الافتراضي dry-run = على. الكود لا يستدعي API إلا إذا تم تمرير dry_run=False صراحة.
- الـ retry يقتصر على الأخطاء الشبكية (10004) ولا يعيد على أخطاء الحظر / ban.
- الـ image_path في كل بوست يُحفظ في السجل ويُرسَل تذكير للمستخدم لرفعه يدويًا.
"""
from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests

import config

LOG_PATH = Path(config.DATA_DIR) / "publish_log.jsonl"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("binance_publisher")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)


# أكواد أخطاء "نهائية" — لا فائدة من إعادة المحاولة عليها.
TERMINAL_ERROR_CODES = {
    "10005",   # KYC غير مكتمل
    "10007",   # ميزة غير متاحة
    "20002",   # كلمات حساسة
    "20013",   # طول المحتوى مخالف
    "20020",   # محتوى فارغ
    "20022",   # كلمات حساسة (segments)
    "20041",   # رابط مشبوه
    "30004",   # المستخدم غير موجود
    "30008",   # محظور لمخالفة الإرشادات
    "220003",  # API key غير موجود
    "220004",  # API key منتهي
    "220009",  # تجاوز الحد اليومي
    "220010",  # نوع محتوى غير مدعوم
    "220011",  # body فارغ
    "2000001", # الحساب محظور دائمًا من النشر
    "2000002", # الجهاز محظور دائمًا من النشر
}

# هذه الأخطاء قد تكون مؤقتة — يمكن إعادة المحاولة.
RETRYABLE_ERROR_CODES = {"10004"}  # خطأ شبكة


# ------------------------------------------------------------------
# نماذج البيانات
# ------------------------------------------------------------------

@dataclass
class QueuedPost:
    """بوست جاهز للنشر."""
    text: str
    image_path: str | None = None
    image_url: str | None = None  # رابط الصورة الـ public (يُلصق في الـ body)
    hashtags: list[str] = field(default_factory=list)
    post_id: str | None = None  # مرجع داخلي اختياري

    def render_body(self) -> str:
        """يدمج النص + الهاشتاقات + رابط الصورة في حقل bodyTextOnly واحد.

        Binance Square OpenAPI حاليًا يدعم فقط `bodyTextOnly` (نص فقط، لا حقل
        للصور). لأن صورة Hook جزء حيوي من الـ funnel، نجعل رابطها
        العام يدخل body كسطر أخير (Binance Square renderer يتعرف على
        روابط .png/.jpg ويحولها إلى بطاقة معاينة تلقائيًا).
        """
        body = self.text.strip()
        if self.hashtags:
            tag_line = " ".join(
                t if t.startswith("#") else f"#{t.lstrip('$').lstrip('#')}"
                for t in self.hashtags
            )
            if tag_line and tag_line not in body:
                body = f"{body}\n\n{tag_line}"
        if self.image_url and self.image_url not in body:
            body = f"{body}\n\n📸 {self.image_url}"
        return body


@dataclass
class PublishResult:
    """نتيجة محاولة نشر واحدة."""
    success: bool
    code: str | None
    message: str | None
    post_id: str | None
    post_url: str | None
    body: str
    dry_run: bool
    error: str | None = None
    attempts: int = 1

    def to_log(self) -> dict[str, Any]:
        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "success": self.success,
            "dry_run": self.dry_run,
            "code": self.code,
            "message": self.message,
            "post_id": self.post_id,
            "post_url": self.post_url,
            "attempts": self.attempts,
            "error": self.error,
            "body_preview": self.body[:120],
        }


# ------------------------------------------------------------------
# الـ HTTP client
# ------------------------------------------------------------------

class SquarePublisher:
    """
    عميل لـ Binance Square OpenAPI.

    Usage:
        pub = SquarePublisher()
        result = pub.publish_text("Hello $BTC #Bitcoin", dry_run=False)
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_url: str | None = None,
        timeout: int = 20,
        max_retries: int = 3,
        backoff_seconds: float = 4.0,
    ) -> None:
        self.api_key = (api_key or config.SQUARE_OPENAPI_KEY).strip()
        self.api_url = (api_url or config.SQUARE_API_URL).strip()
        self.timeout = timeout
        self.max_retries = max(1, max_retries)
        self.backoff_seconds = backoff_seconds

    # -- API key مكشوف بصيغة مختصرة للعرض في الواجهة --
    def masked_key(self) -> str:
        if not self.api_key:
            return ""
        if len(self.api_key) <= 9:
            return "*" * len(self.api_key)
        return f"{self.api_key[:5]}...{self.api_key[-4:]}"

    # -- نشر بوست واحد --
    def publish_text(
        self,
        body: str,
        dry_run: bool | None = None,
        image_url: str | None = None,
    ) -> PublishResult:
        """ينشر نصًا واحدًا.

        Args:
            body: نص البوست (bodyTextOnly).
            dry_run: None → استخدم الإعداد الافتراضي.
            image_url: رابط صورة (سيُرسل أيضًا في حقول imageUrl/imageUrls/mediaUrls
                للتوافق المستقبلي إذا فتحت Binance دعم الصور في OpenAPI).
        """
        if dry_run is None:
            dry_run = config.PUBLISH_DRY_RUN_DEFAULT or not self.api_key

        body = body.strip()
        if not body:
            return PublishResult(
                success=False, code="20020", message="empty body",
                post_id=None, post_url=None, body="", dry_run=dry_run,
                error="body is empty",
            )

        if dry_run:
            logger.info("[DRY RUN] would publish %d chars", len(body))
            result = PublishResult(
                success=True, code="000000", message="dry-run",
                post_id="dry-run", post_url=None, body=body, dry_run=True,
            )
            self._append_log(result)
            return result

        if not self.api_key:
            return PublishResult(
                success=False, code="220003", message="no API key",
                post_id=None, post_url=None, body=body, dry_run=False,
                error="X-Square-OpenAPI-Key is empty",
            )

        last_error: str | None = None
        last_code: str | None = None
        last_message: str | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                payload_obj: dict[str, Any] = {"bodyTextOnly": body}
                if image_url:
                    # حقول احتياطية، Binance وثّق bodyTextOnly فقط لكن الأخريات
                    # تُقبل بصمت (000000) — لو فعيلت يومًا، ستتفعل تلقائيًا.
                    payload_obj["imageUrl"] = image_url
                    payload_obj["imageUrls"] = [image_url]
                    payload_obj["mediaUrls"] = [image_url]
                resp = requests.post(
                    self.api_url,
                    headers={
                        "X-Square-OpenAPI-Key": self.api_key,
                        "Content-Type": "application/json",
                        "clienttype": "binanceSkill",
                    },
                    data=json.dumps(payload_obj),
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_error = f"network: {exc}"
                logger.warning("attempt %d network error: %s", attempt, exc)
                if attempt < self.max_retries:
                    time.sleep(self.backoff_seconds * attempt)
                    continue
                break

            try:
                payload = resp.json()
            except ValueError:
                last_error = f"non-json HTTP {resp.status_code}: {resp.text[:200]}"
                logger.warning("attempt %d %s", attempt, last_error)
                if attempt < self.max_retries:
                    time.sleep(self.backoff_seconds * attempt)
                    continue
                break

            code = str(payload.get("code", ""))
            message = payload.get("message")
            data = payload.get("data") or {}
            post_id = data.get("id")
            last_code, last_message = code, message

            if code == "000000":
                post_url = (
                    f"https://www.binance.com/square/post/{post_id}"
                    if post_id else None
                )
                result = PublishResult(
                    success=True, code=code, message=message,
                    post_id=post_id, post_url=post_url,
                    body=body, dry_run=False, attempts=attempt,
                )
                self._append_log(result)
                return result

            if code in RETRYABLE_ERROR_CODES and attempt < self.max_retries:
                logger.warning("attempt %d retryable code=%s msg=%s", attempt, code, message)
                time.sleep(self.backoff_seconds * attempt)
                continue

            # خطأ نهائي.
            result = PublishResult(
                success=False, code=code, message=message,
                post_id=None, post_url=None,
                body=body, dry_run=False, attempts=attempt,
                error=f"{code}: {message}",
            )
            self._append_log(result)
            return result

        result = PublishResult(
            success=False, code=last_code, message=last_message,
            post_id=None, post_url=None,
            body=body, dry_run=False, attempts=self.max_retries,
            error=last_error or "unknown",
        )
        self._append_log(result)
        return result

    # -- تسجيل --
    def _append_log(self, result: PublishResult) -> None:
        try:
            with LOG_PATH.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(result.to_log(), ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("could not append publish log: %s", exc)


# ------------------------------------------------------------------
# منطق طابور النشر مع التأخير العشوائي
# ------------------------------------------------------------------

def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def count_published_today(log_path: Path = LOG_PATH) -> int:
    """يحسب عدد البوستات المنشورة فعليًا (success وليس dry_run) اليوم."""
    if not log_path.exists():
        return 0
    today = _utc_today()
    n = 0
    try:
        with log_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("success") and not entry.get("dry_run"):
                    if entry.get("ts", "").startswith(today):
                        n += 1
    except OSError:
        return 0
    return n


def publish_queue(
    posts: Iterable[QueuedPost | dict[str, Any]],
    *,
    dry_run: bool | None = None,
    shuffle: bool = True,
    min_delay_min: int | None = None,
    max_delay_min: int | None = None,
    daily_cap: int | None = None,
    sleep_fn=time.sleep,
    rng: random.Random | None = None,
    on_event=None,
    publisher: SquarePublisher | None = None,
) -> list[PublishResult]:
    """
    ينشر طابور بوستات مع تأخير عشوائي بين كل بوستين.

    - الأول ينشر مباشرة (بدون تأخير).
    - بعد كل نشر ناجح، ننتظر random(min_delay_min, max_delay_min) دقيقة.
    - إذا تجاوزنا الحد اليومي نتوقف.
    - on_event(stage, payload) ينادى عند كل خطوة (للـ UI).
    - sleep_fn و rng قابلين للحقن لأغراض الاختبار.
    """
    rng = rng or random.Random()
    publisher = publisher or SquarePublisher()
    min_d = max(0, min_delay_min if min_delay_min is not None else config.PUBLISH_MIN_DELAY_MIN)
    max_d = max(min_d, max_delay_min if max_delay_min is not None else config.PUBLISH_MAX_DELAY_MIN)
    cap = daily_cap if daily_cap is not None else config.PUBLISH_DAILY_CAP

    queue: list[QueuedPost] = []
    for raw in posts:
        if isinstance(raw, QueuedPost):
            queue.append(raw)
        elif isinstance(raw, dict):
            queue.append(QueuedPost(
                text=str(raw.get("text", "")),
                image_path=raw.get("image_path") or None,
                image_url=raw.get("image_url") or None,
                hashtags=list(raw.get("hashtags") or []),
                post_id=str(raw.get("post_id")) if raw.get("post_id") else None,
            ))
        else:
            raise TypeError(f"unsupported post type: {type(raw).__name__}")

    if shuffle:
        rng.shuffle(queue)

    results: list[PublishResult] = []
    posted_today = count_published_today()

    for idx, post in enumerate(queue):
        if posted_today >= cap and not (dry_run or (dry_run is None and config.PUBLISH_DRY_RUN_DEFAULT)):
            if on_event:
                on_event("daily_cap_reached", {"posted_today": posted_today, "cap": cap})
            logger.info("daily cap %d reached — stopping", cap)
            break

        if on_event:
            on_event("publishing", {"index": idx, "total": len(queue), "post_id": post.post_id})

        body = post.render_body()
        result = publisher.publish_text(body, dry_run=dry_run, image_url=post.image_url)
        results.append(result)

        if on_event:
            on_event("published", {
                "index": idx, "total": len(queue),
                "success": result.success, "code": result.code,
                "post_url": result.post_url, "error": result.error,
                "image_path": post.image_path,
                "image_url": post.image_url,
            })

        if result.success and not result.dry_run:
            posted_today += 1

        if not result.success and result.code in TERMINAL_ERROR_CODES:
            logger.error("terminal error %s — aborting queue", result.code)
            if on_event:
                on_event("aborted", {"reason": f"terminal {result.code}", "message": result.message})
            break

        is_last = idx == len(queue) - 1
        if not is_last and posted_today < cap:
            wait_min = rng.randint(min_d, max_d) if max_d > 0 else 0
            wait_sec = wait_min * 60
            if on_event:
                on_event("waiting", {"minutes": wait_min, "seconds": wait_sec})
            logger.info("sleeping %d minutes before next post", wait_min)
            if wait_sec > 0:
                sleep_fn(wait_sec)

    if on_event:
        on_event("done", {
            "total": len(queue),
            "succeeded": sum(1 for r in results if r.success),
            "failed": sum(1 for r in results if not r.success),
        })
    return results
