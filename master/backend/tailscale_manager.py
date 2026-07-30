"""
Tailscale status + exit-node control for the Web UI.

The backend talks to the local tailscaled via the `tailscale` CLI. No sudo is
needed: install_master.sh (and migration 009) set the backend's user as the
Tailscale "operator" (`tailscale set --operator=<user>`), which allows
non-root status queries and preference changes.

Exit node has two halves:
  1. *Advertised* — this device offers itself as an exit node
     (`tailscale set --advertise-exit-node`, controlled from the UI here).
  2. *Approved* — the tailnet admin has approved the offer in the Tailscale
     admin console (https://login.tailscale.com/admin/machines). We can only
     detect and report this, not change it.
"""

import json
import logging
import shutil
import subprocess
from typing import Any, Optional

logger = logging.getLogger(__name__)

TIMEOUT_SEC = 10
ADMIN_CONSOLE_URL = "https://login.tailscale.com/admin/machines"


def _run(cmd: list[str], accept_failure: bool = False) -> Optional[str]:
    """Run a tailscale command, returning stdout (or None on failure).

    With accept_failure, stdout is returned even on a non-zero exit as long as
    the command actually printed something. `tailscale status --json` exits
    non-zero while logged out but still prints a valid status document — that
    document is exactly what tells us the node needs login rather than being
    missing.
    """
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_SEC)
        if result.returncode == 0:
            return result.stdout
        if accept_failure and (result.stdout or "").strip():
            return result.stdout
        logger.warning("tailscale command failed %s: %s", cmd, (result.stderr or "").strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.warning("tailscale command error %s: %s", cmd, e)
    return None


def _is_installed() -> bool:
    return shutil.which("tailscale") is not None


def _status_json() -> Optional[dict[str, Any]]:
    out = _run(["tailscale", "status", "--json"], accept_failure=True)
    if not out:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        logger.warning("Could not parse `tailscale status --json` output")
        return None


def _advertised_exit_node() -> Optional[bool]:
    """Whether this node currently advertises itself as an exit node (from local prefs)."""
    out = _run(["tailscale", "debug", "prefs"])
    if not out:
        return None
    try:
        prefs = json.loads(out)
    except json.JSONDecodeError:
        return None
    routes = prefs.get("AdvertiseRoutes") or []
    return "0.0.0.0/0" in routes and "::/0" in routes


def get_status() -> dict[str, Any]:
    """Tailscale connection + exit-node state for the System tab card."""
    status = _status_json()
    if status is None:
        # No parseable status. Fall back to whether the binary exists at all, so
        # an installed-but-broken tailscaled reads as "not connected" rather
        # than "not installed".
        return {"installed": _is_installed(), "running": False}

    self_info = status.get("Self") or {}
    backend_state = status.get("BackendState")  # "Running", "NeedsLogin", "Stopped", ...
    tailscale_ips = self_info.get("TailscaleIPs") or []
    dns_name = (self_info.get("DNSName") or "").rstrip(".")

    advertised = _advertised_exit_node()
    # The control plane reflects admin-approved exit-node routes back in
    # Self: ExitNodeOption is set, and 0.0.0.0/0 appears in AllowedIPs.
    allowed_ips = self_info.get("AllowedIPs") or []
    approved = bool(self_info.get("ExitNodeOption", False)) or "0.0.0.0/0" in allowed_ips

    return {
        "installed": True,
        "running": backend_state == "Running",
        "backend_state": backend_state,
        "hostname": self_info.get("HostName"),
        "dns_name": dns_name or None,
        "ip": tailscale_ips[0] if tailscale_ips else None,
        "exit_node": {
            "advertised": advertised,
            "approved": approved,
        },
        "admin_console_url": ADMIN_CONSOLE_URL,
    }


def set_exit_node(enabled: bool) -> bool:
    """Advertise (or stop advertising) this device as an exit node."""
    flag = "--advertise-exit-node" if enabled else "--advertise-exit-node=false"
    ok = _run(["tailscale", "set", flag]) is not None
    if ok:
        logger.info("Exit node advertising %s", "enabled" if enabled else "disabled")
    return ok
