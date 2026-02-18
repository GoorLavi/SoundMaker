"""
Pi-hole v6 REST API client for SoundMaker.

Pi-hole v6 uses session-based auth: POST /api/auth with the password to get
a short-lived session ID (SID), then pass it as X-FTL-SID on every request.
Sessions auto-renew when they expire.

The password is read from the PIHOLE_PASSWORD env var.
"""

import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)

PIHOLE_BASE_URL = os.environ.get("PIHOLE_BASE_URL", "http://localhost").rstrip("/")
PIHOLE_PASSWORD = os.environ.get("PIHOLE_PASSWORD", "")

_session: dict = {
    "sid": None,
    "csrf": None,
    "expires_at": 0.0,
}

_http: httpx.AsyncClient | None = None


def _client() -> httpx.AsyncClient:
    global _http
    if _http is None or _http.is_closed:
        _http = httpx.AsyncClient(base_url=f"{PIHOLE_BASE_URL}/api", timeout=10.0)
    return _http


async def _authenticate() -> None:
    """Obtain a new session from Pi-hole."""
    client = _client()
    resp = await client.post("/auth", json={"password": PIHOLE_PASSWORD})
    resp.raise_for_status()
    data = resp.json()

    session = data.get("session", {})
    if not session.get("valid"):
        raise RuntimeError(f"Pi-hole auth failed: {session.get('message', 'unknown error')}")

    _session["sid"] = session["sid"]
    _session["csrf"] = session["csrf"]
    _session["expires_at"] = time.monotonic() + session.get("validity", 300) - 10


async def _headers() -> dict[str, str]:
    """Return auth headers, re-authenticating if the session expired."""
    if _session["sid"] is None or time.monotonic() >= _session["expires_at"]:
        await _authenticate()
    return {
        "X-FTL-SID": _session["sid"],
        "X-FTL-CSRF": _session["csrf"],
    }


async def _get(endpoint: str) -> dict:
    client = _client()
    hdrs = await _headers()
    resp = await client.get(endpoint, headers=hdrs)
    if resp.status_code == 401:
        await _authenticate()
        hdrs = await _headers()
        resp = await client.get(endpoint, headers=hdrs)
    resp.raise_for_status()
    return resp.json()


async def _post(endpoint: str, payload: dict) -> dict:
    client = _client()
    hdrs = await _headers()
    resp = await client.post(endpoint, json=payload, headers=hdrs)
    if resp.status_code == 401:
        await _authenticate()
        hdrs = await _headers()
        resp = await client.post(endpoint, json=payload, headers=hdrs)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Public API used by the FastAPI routes
# ---------------------------------------------------------------------------

async def get_blocking_status() -> dict:
    """Return {"blocking": true/false}."""
    return await _get("/dns/blocking")


async def set_blocking(enabled: bool, timer: int | None = None) -> dict:
    """Enable or disable blocking. Optional timer in seconds."""
    payload: dict = {"blocking": enabled}
    if timer is not None:
        payload["timer"] = timer
    return await _post("/dns/blocking", payload)


async def get_stats_summary() -> dict:
    """Return the Pi-hole activity summary (queries, blocked, etc.)."""
    return await _get("/stats/summary")


async def get_status() -> dict:
    """
    Combined status + stats call for the SoundMaker UI.
    Returns a flat dict the frontend can consume directly.
    If Pi-hole is unreachable, returns a degraded status instead of crashing.
    """
    try:
        blocking, summary = await get_blocking_status(), await get_stats_summary()
        return {
            "available": True,
            "blocking": blocking.get("blocking", "unknown"),
            **summary,
        }
    except Exception as exc:
        logger.warning("Pi-hole unreachable: %s", exc)
        return {"available": False, "blocking": "unknown"}


async def close() -> None:
    """Shut down the HTTP client (call on app shutdown)."""
    global _http
    if _http and not _http.is_closed:
        await _http.aclose()
        _http = None
