"""
Persistent JSON state management for SoundMaker.

All state is stored as JSON files under a configurable directory
(defaults to /opt/soundmaker/state/ on the Pi, overridable via
STATE_DIR env var for local development).
"""

import json
import os
from pathlib import Path
from typing import Any

STATE_DIR = Path(os.environ.get("SOUNDMAKER_STATE_DIR", "/opt/soundmaker/state"))

DEFAULTS: dict[str, Any] = {
    "config.json": {
        "default_stream_url": "https://uk3.internet-radio.com/proxy/1940sradio/stream",
        "default_volume": 100,
    },
    "slaves.json": {
        "slaves": [],
    },
    "bluetooth.json": {
        "paired_devices": [],
    },
    "version.json": {
        "current": None,
        "last_updated_at": None,
    },
    "applied_migrations.json": {
        "applied": [],
    },
    "alarm.json": {
        "enabled": False,
        "time": "07:00",
        "playlist_uri": None,
    },
    "spotify.json": {
        "refresh_token": None,
    },
}


def _ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def load(filename: str) -> dict[str, Any]:
    """Load a state file. Returns defaults if the file doesn't exist yet."""
    path = STATE_DIR / filename
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return DEFAULTS.get(filename, {}).copy()


def save(filename: str, data: dict[str, Any]) -> None:
    """Atomically write a state file (write-tmp then rename)."""
    _ensure_state_dir()
    path = STATE_DIR / filename
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp_path.rename(path)


def update(filename: str, key: str, value: Any) -> dict[str, Any]:
    """Load a state file, update one top-level key, save, and return the new state."""
    data = load(filename)
    data[key] = value
    save(filename, data)
    return data
