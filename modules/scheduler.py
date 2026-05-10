"""Scheduler — UTC-based posting reminders.

We do NOT auto-post (Binance Square has no public posting API for individuals).
Instead, the scheduler queues reminders that fire at UTC times the user picks
(the UI surfaces these), and exposes a list of "prime windows" tuned for Top 10.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import threading
import uuid
from typing import Any, Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import config

_QUEUE_PATH = os.path.join(config.DATA_DIR, "schedule_queue.json")
_LOCK = threading.Lock()
_SCHED: BackgroundScheduler | None = None


def _load_queue() -> list[dict[str, Any]]:
    if not os.path.exists(_QUEUE_PATH):
        return []
    with open(_QUEUE_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _save_queue(items: list[dict[str, Any]]) -> None:
    with open(_QUEUE_PATH, "w", encoding="utf-8") as fh:
        json.dump(items, fh, indent=2, ensure_ascii=False)


def get_scheduler() -> BackgroundScheduler:
    global _SCHED
    if _SCHED is None:
        _SCHED = BackgroundScheduler(timezone=config.TIMEZONE)
        _SCHED.start()
    return _SCHED


def prime_windows_today() -> list[str]:
    """Return UTC ISO timestamps for today's prime posting windows that are still in the future."""
    now = dt.datetime.now(dt.timezone.utc)
    out: list[str] = []
    for hour in config.PRIME_POSTING_HOURS_UTC:
        slot = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if slot > now:
            out.append(slot.isoformat())
    return out


def _fire(reminder_id: str, callback: Callable[[dict[str, Any]], None] | None) -> None:
    """Mark a reminder as fired in the queue and optionally invoke a callback."""
    with _LOCK:
        items = _load_queue()
        item = next((i for i in items if i["id"] == reminder_id), None)
        if not item:
            return
        item["fired"] = True
        item["fired_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        _save_queue(items)
    if callback:
        try:
            callback(item)
        except Exception as exc:  # noqa: BLE001
            print(f"[scheduler] callback failed: {exc}")


def schedule_post_reminder(post_id: str, fire_at_utc: str,
                           label: str = "Time to publish",
                           callback: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    """Queue a reminder to publish `post_id` at `fire_at_utc` (ISO 8601)."""
    when = dt.datetime.fromisoformat(fire_at_utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.timezone.utc)

    rid = uuid.uuid4().hex[:10]
    item = {
        "id": rid,
        "post_id": post_id,
        "fire_at_utc": when.isoformat(),
        "label": label,
        "fired": False,
    }

    with _LOCK:
        items = _load_queue()
        items.append(item)
        _save_queue(items)

    sched = get_scheduler()
    sched.add_job(_fire, "date", run_date=when, args=[rid, callback], id=rid,
                  replace_existing=True)
    return item


def schedule_engagement_pings(post_id: str, published_at_utc: str,
                              minute_offsets: list[int] | None = None,
                              callback: Callable[[dict[str, Any]], None] | None = None) -> list[dict[str, Any]]:
    """Queue first-hour engagement reminders relative to publish time."""
    minute_offsets = minute_offsets or [5, 15, 30, 45, 60]
    base = dt.datetime.fromisoformat(published_at_utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=dt.timezone.utc)
    out = []
    for m in minute_offsets:
        fire = base + dt.timedelta(minutes=m)
        out.append(schedule_post_reminder(
            post_id=post_id,
            fire_at_utc=fire.isoformat(),
            label=f"Engagement check (+{m} min)",
            callback=callback,
        ))
    return out


def list_pending() -> list[dict[str, Any]]:
    return [i for i in _load_queue() if not i.get("fired")]


def install_daily_cron(callback: Callable[[], None]) -> None:
    """Optional: trigger `callback` at every prime UTC hour to auto-fetch trends."""
    sched = get_scheduler()
    for hour in config.PRIME_POSTING_HOURS_UTC:
        sched.add_job(callback, CronTrigger(hour=hour, minute=0, timezone=config.TIMEZONE),
                      id=f"daily_trends_{hour}", replace_existing=True)
