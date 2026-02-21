"""
Morning wake-up: alarm config (time, playlist), scheduler, and fire action.

At the configured time (local), the scheduler calls Spotify Web API to start
playback on the Pi's Spotify Connect device (HDMI output).
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Optional

from state_manager import load, save

import spotify_auth

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SEC = 60
ALARM_FILENAME = "alarm.json"


DEFAULT_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def get_alarm() -> dict[str, Any]:
    data = load(ALARM_FILENAME)
    if "days" not in data or not data["days"]:
        data["days"] = list(DEFAULT_DAYS)
    return data


VALID_DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
DAY_INDEX_MAP = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def set_alarm(
    enabled: bool,
    time_str: str,
    days: Optional[list[str]] = None,
    playlist_uri: Optional[str] = None,
) -> dict[str, Any]:
    """time_str: HH:MM (24-hour). days: list of day abbreviations (None = keep existing). playlist_uri can be None."""
    data = load(ALARM_FILENAME)
    data["enabled"] = bool(enabled)
    data["time"] = _normalize_time(time_str)
    if days is not None:
        data["days"] = _normalize_days(days)
    elif "days" not in data or not data["days"]:
        data["days"] = list(DEFAULT_DAYS)
    data["playlist_uri"] = playlist_uri.strip() or None if playlist_uri else None
    save(ALARM_FILENAME, data)
    return data


def _normalize_days(days: Optional[list[str]]) -> list[str]:
    if not days:
        return sorted(VALID_DAYS, key=lambda d: DAY_INDEX_MAP[d])
    normalized = [d.lower().strip()[:3] for d in days if d.lower().strip()[:3] in VALID_DAYS]
    return sorted(set(normalized), key=lambda d: DAY_INDEX_MAP[d]) if normalized else sorted(VALID_DAYS, key=lambda d: DAY_INDEX_MAP[d])


def _normalize_time(s: str) -> str:
    """Ensure HH:MM with leading zero if needed."""
    s = (s or "").strip()
    if not s:
        return "07:00"
    if ":" in s:
        parts = s.split(":", 1)
        try:
            h, m = int(parts[0].strip()), int(parts[1].strip())
            h = max(0, min(23, h))
            m = max(0, min(59, m))
            return f"{h:02d}:{m:02d}"
        except (ValueError, IndexError):
            pass
    return "07:00"


def _current_time_str() -> str:
    return datetime.now().strftime("%H:%M")


WEEKDAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _current_day_abbr() -> str:
    return WEEKDAY_NAMES[datetime.now().weekday()]


def _should_fire(alarm: dict[str, Any]) -> bool:
    if not alarm.get("enabled"):
        return False
    if _current_time_str() != alarm.get("time", "07:00"):
        return False
    days = alarm.get("days") or WEEKDAY_NAMES
    return _current_day_abbr() in days


# Tracks (year, month, day, hour, minute) we last fired so we only fire once per alarm minute.
_last_fired: Optional[tuple[int, int, int, int, int]] = None


def _mark_fired() -> None:
    global _last_fired
    now = datetime.now()
    _last_fired = (now.year, now.month, now.day, now.hour, now.minute)


def _already_fired_this_minute() -> bool:
    global _last_fired
    if _last_fired is None:
        return False
    now = datetime.now()
    return (now.year, now.month, now.day, now.hour, now.minute) == _last_fired


async def _alarm_loop(on_fire: Callable[[], None]) -> None:
    while True:
        try:
            alarm = get_alarm()
            if _should_fire(alarm) and not _already_fired_this_minute():
                _mark_fired()
                logger.info("Alarm firing at %s", alarm.get("time"))
                on_fire()
        except Exception as e:
            logger.exception("Alarm check failed: %s", e)
        await asyncio.sleep(CHECK_INTERVAL_SEC)


_task: Optional[asyncio.Task] = None


def _fire() -> None:
    alarm = get_alarm()
    playlist_uri = alarm.get("playlist_uri")
    if not spotify_auth.play_alarm_on_pi(playlist_uri=playlist_uri):
        logger.warning("Alarm: Spotify playback could not be started")
    else:
        logger.info("Alarm: Spotify playback started")


def start_scheduler() -> None:
    """Start the alarm scheduler background task. Idempotent. Call from async context (e.g. lifespan)."""
    global _task
    if _task is not None and not _task.done():
        return
    loop = asyncio.get_running_loop()
    _task = loop.create_task(_alarm_loop(_fire))
    logger.info("Alarm scheduler started")


def stop_scheduler() -> None:
    """Cancel the alarm scheduler task."""
    global _task
    if _task is not None:
        _task.cancel()
        _task = None
        logger.info("Alarm scheduler stopped")
