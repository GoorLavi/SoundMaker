"""
Read recent systemd journal logs for the Master's services (System tab log
viewer).

Only a fixed whitelist of services can be read — the service key from the UI is
never passed to the shell, it only selects a known unit name. The backend user
is added to the `systemd-journal` group by the installer so it can read the
journal without sudo.

Logs are fetched as journald JSON so we get the real severity (PRIORITY) and a
clean message per entry, instead of parsing free-form text.
"""

import json
import logging
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

# UI service key -> (systemd unit, human label)
SERVICES: dict[str, tuple[str, str]] = {
    "backend": ("soundmaker-backend.service", "SoundMaker backend"),
    "jellyfin": ("jellyfin.service", "Jellyfin"),
    "pihole": ("pihole-FTL.service", "Pi-hole"),
    "caddy": ("caddy.service", "Caddy (HTTPS)"),
    "raspotify": ("raspotify.service", "Spotify (raspotify)"),
    "tailscale": ("tailscaled.service", "Tailscale VPN"),
}

DEFAULT_LINES = 100
MAX_LINES = 500


def available_services() -> list[dict[str, str]]:
    return [{"key": key, "label": label} for key, (_unit, label) in SERVICES.items()]


def _priority_to_level(priority: Any) -> str:
    """journald PRIORITY 0-7 -> error / warning / info."""
    try:
        p = int(priority)
    except (ValueError, TypeError):
        return "info"
    if p <= 3:
        return "error"
    if p == 4:
        return "warning"
    return "info"


def _decode_message(msg: Any) -> str:
    # journald may return MESSAGE as a list of byte values for non-UTF8 data.
    if isinstance(msg, list):
        try:
            return bytes(msg).decode("utf-8", "replace")
        except Exception:
            return str(msg)
    return "" if msg is None else str(msg)


def get_logs(service_key: str, lines: int = DEFAULT_LINES) -> dict[str, Any]:
    entry = SERVICES.get(service_key)
    if not entry:
        return {"error": "Unknown service", "entries": []}
    unit, _label = entry

    try:
        n = max(1, min(MAX_LINES, int(lines)))
    except (ValueError, TypeError):
        n = DEFAULT_LINES

    cmd = [
        "journalctl",
        "-u", unit,
        "-n", str(n),
        "--no-pager",
        "-o", "json",
        "--output-fields=MESSAGE,PRIORITY,SYSLOG_IDENTIFIER,__REALTIME_TIMESTAMP",
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.warning("journalctl failed for %s: %s", unit, e)
        return {"error": "Could not read logs", "entries": []}

    if out.returncode != 0:
        msg = (out.stderr or "").strip() or "journalctl returned an error"
        logger.warning("journalctl error for %s: %s", unit, msg)
        return {"error": msg, "entries": []}

    entries: list[dict[str, Any]] = []
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts_us = obj.get("__REALTIME_TIMESTAMP")
        try:
            ts = int(ts_us) / 1_000_000 if ts_us else None
        except (ValueError, TypeError):
            ts = None
        entries.append({
            "t": ts,
            "level": _priority_to_level(obj.get("PRIORITY")),
            "ident": obj.get("SYSLOG_IDENTIFIER"),
            "message": _decode_message(obj.get("MESSAGE")),
        })

    return {"unit": unit, "entries": entries}
