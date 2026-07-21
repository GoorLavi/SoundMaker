"""
Power controls for the Master: restart the backend, reboot the Pi, and an
optional scheduled weekly reboot.

Restart and reboot are performed with `systemd-run --on-active=2`, which
schedules the action as a short-lived transient systemd timer. That timer runs
*outside* the backend's own service group, so restarting the backend does not
kill the command halfway through, and the HTTP request can return before the
action actually happens.

Both commands require passwordless sudo, scoped to exactly these two
invocations via /etc/sudoers.d/soundmaker (installed by install_master.sh and
migration 007).
"""

import asyncio
import logging
import subprocess
from datetime import datetime
from typing import Any, Optional

from state_manager import load, save

logger = logging.getLogger(__name__)

POWER_FILENAME = "power.json"
CHECK_INTERVAL_SEC = 60

VALID_DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
WEEKDAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# These must match the entries in /etc/sudoers.d/soundmaker exactly.
RESTART_CMD = ["sudo", "systemd-run", "--on-active=2", "systemctl", "restart", "soundmaker-backend.service"]
REBOOT_CMD = ["sudo", "systemd-run", "--on-active=2", "systemctl", "reboot"]


# ---------------------------------------------------------------------------
# Immediate actions
# ---------------------------------------------------------------------------


def _schedule(cmd: list[str]) -> bool:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return True
        logger.error("Power command failed %s: %s", cmd, (result.stderr or "").strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.error("Power command error %s: %s", cmd, e)
    return False


def restart_backend() -> bool:
    """Schedule a restart of the SoundMaker backend (in ~2 seconds)."""
    logger.info("Scheduling backend restart")
    return _schedule(RESTART_CMD)


def reboot() -> bool:
    """Schedule a reboot of the whole Pi (in ~2 seconds)."""
    logger.info("Scheduling system reboot")
    return _schedule(REBOOT_CMD)


# ---------------------------------------------------------------------------
# Scheduled weekly reboot config
# ---------------------------------------------------------------------------


def _normalize_time(s: str) -> str:
    s = (s or "").strip()
    if ":" in s:
        parts = s.split(":", 1)
        try:
            h, m = int(parts[0].strip()), int(parts[1].strip())
            return f"{max(0, min(23, h)):02d}:{max(0, min(59, m)):02d}"
        except (ValueError, IndexError):
            pass
    return "04:30"


def _normalize_day(day: Optional[str]) -> str:
    d = (day or "sun").lower().strip()[:3]
    return d if d in VALID_DAYS else "sun"


def get_auto_reboot() -> dict[str, Any]:
    data = load(POWER_FILENAME)
    ar = data.get("auto_reboot") if isinstance(data, dict) else None
    ar = ar or {}
    return {
        "enabled": bool(ar.get("enabled", False)),
        "day": _normalize_day(ar.get("day")),
        "time": _normalize_time(ar.get("time", "04:30")),
    }


def set_auto_reboot(enabled: bool, day: str, time_str: str) -> dict[str, Any]:
    ar = {
        "enabled": bool(enabled),
        "day": _normalize_day(day),
        "time": _normalize_time(time_str),
    }
    data = load(POWER_FILENAME)
    if not isinstance(data, dict):
        data = {}
    data["auto_reboot"] = ar
    save(POWER_FILENAME, data)
    return ar


# ---------------------------------------------------------------------------
# Scheduler (fires the weekly reboot)
# ---------------------------------------------------------------------------


def _should_reboot(ar: dict[str, Any]) -> bool:
    if not ar.get("enabled"):
        return False
    now = datetime.now()
    if now.strftime("%H:%M") != ar.get("time"):
        return False
    return WEEKDAY_NAMES[now.weekday()] == ar.get("day")


# (year, month, day, hour, minute) we last fired — fire at most once per minute.
_last_fired: Optional[tuple[int, int, int, int, int]] = None


async def _loop() -> None:
    global _last_fired
    while True:
        try:
            ar = get_auto_reboot()
            now = datetime.now()
            key = (now.year, now.month, now.day, now.hour, now.minute)
            if _should_reboot(ar) and _last_fired != key:
                _last_fired = key
                logger.info("Scheduled weekly reboot firing (%s %s)", ar.get("day"), ar.get("time"))
                reboot()
        except Exception as e:
            logger.exception("Auto-reboot check failed: %s", e)
        await asyncio.sleep(CHECK_INTERVAL_SEC)


_task: Optional[asyncio.Task] = None


def start_scheduler() -> None:
    """Start the weekly-reboot scheduler. Idempotent. Call from an async context."""
    global _task
    if _task is not None and not _task.done():
        return
    loop = asyncio.get_running_loop()
    _task = loop.create_task(_loop())
    logger.info("Power scheduler started")


def stop_scheduler() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        _task = None
        logger.info("Power scheduler stopped")
