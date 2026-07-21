"""
Rolling history of the Master's vitals (CPU temperature, CPU load, memory use)
so the System tab can draw a 24-hour graph.

A background task samples once a minute and keeps the last 24 hours in memory.
To limit SD-card wear the history is written to disk only every few samples
(and once on shutdown), not on every tick — so the graph survives a restart or
the weekly reboot without hammering the card.
"""

import asyncio
import logging
import time
from typing import Any, Optional

from state_manager import load, save
import system_info

logger = logging.getLogger(__name__)

FILENAME = "metrics_history.json"
SAMPLE_INTERVAL_SEC = 60
MAX_POINTS = 24 * 60  # 24 hours at one sample per minute
PERSIST_EVERY = 5     # write to disk every 5th sample (~5 min)

_points: list[dict[str, Any]] = []


def _load_from_disk() -> None:
    global _points
    try:
        data = load(FILENAME)
        pts = data.get("points") if isinstance(data, dict) else None
        if isinstance(pts, list):
            _points = pts[-MAX_POINTS:]
    except Exception as e:
        logger.debug("Could not load metrics history: %s", e)


def _persist() -> None:
    try:
        save(FILENAME, {"points": _points})
    except Exception as e:
        logger.debug("Could not persist metrics history: %s", e)


def _sample() -> dict[str, Any]:
    temp = system_info._get_cpu_temp_c()
    load_1m, _ = system_info._get_loadavg()
    total_kb, used_kb, _ = system_info._get_memory()
    mem_pct = (
        round(used_kb / total_kb * 100, 1)
        if total_kb and used_kb is not None
        else None
    )
    return {
        "t": int(time.time()),
        "temp_c": temp,
        "load": load_1m,
        "mem_pct": mem_pct,
    }


def _append_sample() -> None:
    _points.append(_sample())
    if len(_points) > MAX_POINTS:
        del _points[: len(_points) - MAX_POINTS]


def get_history() -> dict[str, Any]:
    """Return the recorded points plus the sampling metadata for the UI."""
    return {
        "points": _points,
        "sample_interval_sec": SAMPLE_INTERVAL_SEC,
        "max_points": MAX_POINTS,
    }


async def _loop() -> None:
    count = 0
    while True:
        await asyncio.sleep(SAMPLE_INTERVAL_SEC)
        try:
            _append_sample()
            count += 1
            if count % PERSIST_EVERY == 0:
                _persist()
        except Exception as e:
            logger.exception("Metrics sample failed: %s", e)


_task: Optional[asyncio.Task] = None


def start_sampler() -> None:
    """Load past history, take one sample now, and start the sampler. Idempotent."""
    global _task
    if _task is not None and not _task.done():
        return
    _load_from_disk()
    try:
        _append_sample()  # one point immediately so the graph isn't empty
    except Exception as e:
        logger.debug("Initial metrics sample failed: %s", e)
    loop = asyncio.get_running_loop()
    _task = loop.create_task(_loop())
    logger.info("Metrics sampler started")


def stop_sampler() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        _task = None
    _persist()
    logger.info("Metrics sampler stopped")
