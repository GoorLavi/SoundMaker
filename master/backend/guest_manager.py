"""
Guest landing page configuration.

The homeowner configures the guest Wi-Fi details (SSID, password, security
type) plus an optional welcome message from the authenticated Dashboard.
The guest page itself (GET /guest + GET /api/guest/page) is intentionally
public: anyone who can reach the Master over the LAN is already on the
network, and the page's whole purpose is to be shown to visitors without
logging in. When disabled, the public endpoint reveals nothing.
"""

from typing import Any, Optional

from state_manager import load, save

GUEST_FILENAME = "guest.json"

VALID_SECURITY = {"WPA", "WEP", "nopass"}


def _normalize(data: dict[str, Any]) -> dict[str, Any]:
    security = str(data.get("security") or "WPA")
    if security not in VALID_SECURITY:
        security = "WPA"
    return {
        "enabled": bool(data.get("enabled", False)),
        "ssid": str(data.get("ssid") or "").strip()[:64],
        "password": str(data.get("password") or "")[:128],
        "security": security,
        "hidden": bool(data.get("hidden", False)),
        "welcome_message": str(data.get("welcome_message") or "").strip()[:500],
        "show_jellyfin": bool(data.get("show_jellyfin", True)),
    }


def get_config() -> dict[str, Any]:
    """Full guest config, for the authenticated admin card."""
    return _normalize(load(GUEST_FILENAME))


def set_config(
    enabled: bool,
    ssid: str,
    password: str,
    security: str,
    hidden: bool,
    welcome_message: Optional[str],
    show_jellyfin: bool,
) -> dict[str, Any]:
    config = _normalize(
        {
            "enabled": enabled,
            "ssid": ssid,
            "password": password,
            "security": security,
            "hidden": hidden,
            "welcome_message": welcome_message or "",
            "show_jellyfin": show_jellyfin,
        }
    )
    save(GUEST_FILENAME, config)
    return config


def get_public_page() -> dict[str, Any]:
    """What an unauthenticated guest is allowed to see.

    Returns only {"enabled": False} while the page is turned off, so the
    Wi-Fi credentials never leak through the public endpoint.
    """
    config = get_config()
    if not config["enabled"] or not config["ssid"]:
        return {"enabled": False}
    return {
        "enabled": True,
        "ssid": config["ssid"],
        "password": config["password"],
        "security": config["security"],
        "hidden": config["hidden"],
        "welcome_message": config["welcome_message"],
        "show_jellyfin": config["show_jellyfin"],
    }
