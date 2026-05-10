"""Flask web UI — the single page where you run the daily workflow.

Endpoints:
  GET  /                       Main UI.
  POST /api/trends             Fetch fresh trend snapshot.
  POST /api/generate           Generate a batch of posts from latest trends.
  POST /api/select              Rank + return best posts.
  POST /api/image               Render a hook image for a post.
  POST /api/reply               Generate a reply to a comment.
  POST /api/schedule            Queue a publish reminder.
  GET  /api/pending             List pending reminders.
  GET  /api/prime-windows       Return today's remaining UTC posting windows.
  GET  /output/<filename>       Serve generated images.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from typing import Any

from flask import Flask, jsonify, render_template, request, send_from_directory

import config
from modules import (
    binance_publisher,
    content_generator,
    engagement_assistant,
    image_generator,
    image_host,
    scheduler,
    smart_selector,
    trend_engine,
)

app = Flask(__name__, template_folder="templates", static_folder="static")

_SNAPSHOT_PATH = os.path.join(config.DATA_DIR, "snapshot.json")
_POSTS_PATH = os.path.join(config.DATA_DIR, "posts.json")


def _save_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def _load_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


@app.route("/")
def index() -> Any:
    return render_template(
        "index.html",
        has_llm=config.HAS_LLM,
        has_square_api=config.HAS_SQUARE_API,
    )


@app.route("/api/trends", methods=["POST"])
def api_trends() -> Any:
    snapshot = trend_engine.get_full_snapshot()
    _save_json(_SNAPSHOT_PATH, snapshot)
    return jsonify(snapshot)


@app.route("/api/generate", methods=["POST"])
def api_generate() -> Any:
    body = request.get_json(silent=True) or {}
    n_per_type = int(body.get("n_per_type", 2))
    snapshot = _load_json(_SNAPSHOT_PATH, None)
    if not snapshot:
        snapshot = trend_engine.get_full_snapshot()
        _save_json(_SNAPSHOT_PATH, snapshot)

    posts = content_generator.generate_batch(snapshot, n_per_type=n_per_type)
    ranked = smart_selector.rank_posts(posts, snapshot=snapshot)
    _save_json(_POSTS_PATH, ranked)
    return jsonify({"posts": ranked, "snapshot_at": snapshot.get("fetched_at")})


@app.route("/api/select", methods=["POST"])
def api_select() -> Any:
    posts = _load_json(_POSTS_PATH, [])
    snapshot = _load_json(_SNAPSHOT_PATH, None)
    ranked = smart_selector.rank_posts(posts, snapshot=snapshot)
    _save_json(_POSTS_PATH, ranked)
    return jsonify({"posts": ranked})


@app.route("/api/image", methods=["POST"])
def api_image() -> Any:
    """يولّد صورة Hook + يرجع رابط عام صالح للإرسال مع البوست.

    Body: {post, upload?}.
      - upload=true  → يرفع الصورة لاستضافة عامة (ImgBB إن وُجد المفتاح، 0x0.st احتياط).
      - upload=false (افتراضي) → يرجع رابط داخلي فقط (للمعاينة/التحميل).
    """
    body = request.get_json(silent=True) or {}
    post = body.get("post")
    if not post:
        return jsonify({"error": "missing 'post' in body"}), 400
    upload = bool(body.get("upload", config.AUTO_UPLOAD_IMAGE))

    path = image_generator.render_hook_image(post)
    fname = os.path.basename(path)
    rel_url = f"/output/{fname}"
    local_public_url = request.host_url.rstrip("/") + rel_url

    # رابط القرار: لو upload=True نحاول رفع لاستضافة عامة، وإلا نستخدم المحلي.
    hosted_url: str | None = None
    host_error: str | None = None
    if upload:
        try:
            hosted_url = image_host.upload_to_public(path)
            if not hosted_url:
                host_error = "image host did not return a URL"
        except Exception as exc:  # noqa: BLE001
            host_error = str(exc)

    publish_url = hosted_url or local_public_url
    return jsonify({
        "path": path,
        "url": rel_url,
        "public_url": local_public_url,
        "hosted_url": hosted_url,
        "publish_url": publish_url,
        "host_error": host_error,
        "hook": post.get("image_hook"),
    })


@app.route("/api/reply", methods=["POST"])
def api_reply() -> Any:
    body = request.get_json(silent=True) or {}
    post_body = body.get("post_body", "")
    comment = body.get("comment", "")
    if not comment:
        return jsonify({"error": "missing 'comment'"}), 400
    return jsonify(engagement_assistant.generate_reply(post_body, comment))


@app.route("/api/schedule", methods=["POST"])
def api_schedule() -> Any:
    body = request.get_json(silent=True) or {}
    post_id = body.get("post_id")
    fire_at_utc = body.get("fire_at_utc")
    if not post_id or not fire_at_utc:
        return jsonify({"error": "post_id and fire_at_utc required"}), 400
    item = scheduler.schedule_post_reminder(
        post_id=post_id, fire_at_utc=fire_at_utc,
        label=body.get("label", "Time to publish"),
    )
    return jsonify(item)


@app.route("/api/pending", methods=["GET"])
def api_pending() -> Any:
    return jsonify({"pending": scheduler.list_pending()})


@app.route("/api/prime-windows", methods=["GET"])
def api_prime_windows() -> Any:
    return jsonify({
        "now_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "windows": scheduler.prime_windows_today(),
        "all_hours_utc": config.PRIME_POSTING_HOURS_UTC,
    })


@app.route("/api/reminder-plan/<post_id>", methods=["GET"])
def api_reminder_plan(post_id: str) -> Any:
    return jsonify({"plan": engagement_assistant.reminder_plan(post_id)})


@app.route("/api/publish/single", methods=["POST"])
def api_publish_single() -> Any:
    """Publish ONE post immediately.

    Body: {text, hashtags?, dry_run?, image_url?}.
    `image_url`: رابط عام للصورة — يُلصق في آخر الـ body.
    """
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text is required"}), 400
    hashtags = list(body.get("hashtags") or [])
    image_url = (body.get("image_url") or "").strip() or None
    dry_run = bool(body.get("dry_run", config.PUBLISH_DRY_RUN_DEFAULT))
    post = binance_publisher.QueuedPost(
        text=text, hashtags=hashtags, image_url=image_url,
    )
    publisher = binance_publisher.SquarePublisher()
    result = publisher.publish_text(
        post.render_body(), dry_run=dry_run, image_url=image_url,
    )
    return jsonify({
        "success": result.success,
        "dry_run": result.dry_run,
        "code": result.code,
        "message": result.message,
        "post_id": result.post_id,
        "post_url": result.post_url,
        "error": result.error,
        "attempts": result.attempts,
        "image_url": image_url,
        "body_preview": post.render_body()[:240],
    })


@app.route("/api/publish/queue/preview", methods=["POST"])
def api_publish_queue_preview() -> Any:
    """Preview a queue without sleeping (always dry-run, max delay 0). Useful for the UI."""
    body = request.get_json(silent=True) or {}
    posts = body.get("posts") or []
    if not isinstance(posts, list) or not posts:
        return jsonify({"error": "posts must be a non-empty list"}), 400
    events: list[dict[str, Any]] = []
    binance_publisher.publish_queue(
        posts,
        dry_run=True, shuffle=bool(body.get("shuffle", True)),
        min_delay_min=int(body.get("min_delay_min", 5)),
        max_delay_min=int(body.get("max_delay_min", 30)),
        sleep_fn=lambda s: None,
        on_event=lambda stage, payload: events.append({"stage": stage, **payload}),
    )
    return jsonify({"events": events})


@app.route("/api/publish/status", methods=["GET"])
def api_publish_status() -> Any:
    pub = binance_publisher.SquarePublisher()
    return jsonify({
        "has_api_key": bool(pub.api_key),
        "masked_key": pub.masked_key(),
        "endpoint": pub.api_url,
        "dry_run_default": config.PUBLISH_DRY_RUN_DEFAULT,
        "min_delay_min": config.PUBLISH_MIN_DELAY_MIN,
        "max_delay_min": config.PUBLISH_MAX_DELAY_MIN,
        "daily_cap": config.PUBLISH_DAILY_CAP,
        "posted_today": binance_publisher.count_published_today(),
    })


@app.route("/output/<path:filename>", methods=["GET"])
def serve_output(filename: str) -> Any:
    return send_from_directory(config.OUTPUT_DIR, filename)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.PORT, debug=True)
