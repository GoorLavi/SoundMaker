"""
Jellyfin media server status checker.

Provides read-only status information for the Web UI.
"""

import subprocess
from typing import TypedDict


class JellyfinStatus(TypedDict):
    installed: bool
    running: bool
    url: str | None


def get_status() -> JellyfinStatus:
    """
    Check if Jellyfin is installed and running.
    
    Returns:
        - installed: whether jellyfin.service exists
        - running: whether the service is active
        - url: local URL (http://master.local:8096) if installed
    """
    installed = False
    running = False
    
    # Check if the systemd service exists and is running
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "jellyfin.service"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # is-active returns "active" if running, "inactive" if stopped, "unknown" if not installed
        output = result.stdout.strip()
        if output in ("active", "inactive", "failed", "activating"):
            installed = True
            running = (output == "active")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    url = "http://master.local:8096" if installed else None
    
    return {
        "installed": installed,
        "running": running,
        "url": url,
    }
