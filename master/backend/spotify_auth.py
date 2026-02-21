"""
Spotify Web API OAuth and playback control for morning alarm.

Uses refresh token (stored in state/spotify.json) to obtain access tokens
and call Spotify API: list devices, transfer playback, start playlist.
"""

import base64
import logging
import os
from typing import Any, Optional

import httpx

from state_manager import load, save

logger = logging.getLogger(__name__)

SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE = "https://api.spotify.com/v1"
SCOPES = "user-read-playback-state user-modify-playback-state playlist-read-private"
SOUNDMAKER_DEVICE_NAME = "SoundMaker"


def _client_id() -> Optional[str]:
    return os.environ.get("SPOTIFY_CLIENT_ID")


def _client_secret() -> Optional[str]:
    return os.environ.get("SPOTIFY_CLIENT_SECRET")


def is_configured() -> bool:
    return bool(_client_id() and _client_secret())


def get_auth_url(redirect_uri: str, state: Optional[str] = None) -> Optional[str]:
    """Build Spotify OAuth authorization URL. Returns None if client not configured."""
    client_id = _client_id()
    if not client_id:
        return None
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
    }
    if state:
        params["state"] = state
    q = "&".join(f"{k}={_q(v)}" for k, v in params.items())
    return f"{SPOTIFY_AUTH_URL}?{q}"


def _q(s: str) -> str:
    from urllib.parse import quote
    return quote(s, safe="")


def exchange_code_for_tokens(code: str, redirect_uri: str) -> dict[str, Any]:
    """
    Exchange authorization code for access and refresh tokens.
    Saves refresh_token to state/spotify.json.
    Raises httpx.HTTPStatusError on failure.
    """
    client_id = _client_id()
    client_secret = _client_secret()
    if not client_id or not client_secret:
        raise ValueError("Spotify client ID and secret not configured")

    auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    with httpx.Client() as client:
        resp = client.post(
            SPOTIFY_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    refresh = data.get("refresh_token")
    if refresh:
        save("spotify.json", {"refresh_token": refresh})
    return data


def get_refresh_token() -> Optional[str]:
    data = load("spotify.json")
    return data.get("refresh_token") or None


def is_connected() -> bool:
    return bool(get_refresh_token())


def disconnect() -> None:
    """Remove stored refresh token."""
    save("spotify.json", {"refresh_token": None})


def _get_access_token() -> Optional[str]:
    """Use refresh token to get a fresh access token. Returns None on failure."""
    refresh = get_refresh_token()
    if not refresh:
        return None
    client_id = _client_id()
    client_secret = _client_secret()
    if not client_id or not client_secret:
        return None

    auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    with httpx.Client() as client:
        resp = client.post(
            SPOTIFY_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh,
            },
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        if resp.status_code != 200:
            logger.warning("Spotify token refresh failed: %s %s", resp.status_code, resp.text)
            return None
        data = resp.json()
    return data.get("access_token")


def _api_get(access_token: str, path: str, **kwargs: Any) -> httpx.Response:
    url = f"{SPOTIFY_API_BASE}{path}"
    with httpx.Client() as client:
        return client.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            **kwargs,
        )


def _api_put(access_token: str, path: str, json: Optional[dict] = None, **kwargs: Any) -> httpx.Response:
    url = f"{SPOTIFY_API_BASE}{path}"
    with httpx.Client() as client:
        return client.put(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            json=json,
            **kwargs,
        )


def get_user_playlists(access_token: str, limit: int = 50) -> list[dict]:
    """GET /me/playlists. Returns list of {name, uri, image_url, track_count}."""
    all_playlists: list[dict] = []
    offset = 0
    while True:
        resp = _api_get(access_token, f"/me/playlists?limit={limit}&offset={offset}")
        if resp.status_code != 200:
            logger.warning("Spotify get playlists failed: %s %s", resp.status_code, resp.text)
            break
        data = resp.json()
        items = data.get("items") or []
        for p in items:
            images = p.get("images") or []
            all_playlists.append({
                "name": p.get("name", ""),
                "uri": p.get("uri", ""),
                "image_url": images[0]["url"] if images else None,
                "track_count": (p.get("tracks") or {}).get("total", 0),
            })
        if not data.get("next"):
            break
        offset += limit
    return all_playlists


def fetch_playlists() -> list[dict]:
    """Public helper: get access token and return user's playlists."""
    token = _get_access_token()
    if not token:
        return []
    return get_user_playlists(token)


def get_devices(access_token: str) -> list[dict]:
    """GET /me/player/devices. Returns list of device dicts."""
    resp = _api_get(access_token, "/me/player/devices")
    if resp.status_code != 200:
        logger.warning("Spotify get devices failed: %s %s", resp.status_code, resp.text)
        return []
    data = resp.json()
    return data.get("devices") or []


def find_soundmaker_device_id(access_token: str) -> Optional[str]:
    """Return device id for a device named SOUNDMAKER_DEVICE_NAME, or first available."""
    devices = get_devices(access_token)
    for d in devices:
        if d.get("name") == SOUNDMAKER_DEVICE_NAME:
            return d.get("id")
    if devices:
        return devices[0].get("id")
    return None


def transfer_playback(access_token: str, device_id: str, play: bool = True) -> bool:
    """PUT /me/player — transfer playback to device and optionally start."""
    resp = _api_put(
        access_token,
        "/me/player",
        json={"device_ids": [device_id], "play": play},
    )
    if resp.status_code not in (200, 204):
        logger.warning("Spotify transfer playback failed: %s %s", resp.status_code, resp.text)
        return False
    return True


def start_playback(
    access_token: str,
    device_id: Optional[str] = None,
    context_uri: Optional[str] = None,
) -> bool:
    """
    PUT /me/player/play — start playback (e.g. playlist).
    If context_uri is None, Spotify may resume user's last context.
    """
    params = {}
    if device_id:
        params["device_id"] = device_id
    path = "/me/player/play"
    if params:
        path += "?" + "&".join(f"{k}={_q(v)}" for k, v in params.items())
    resp = _api_put(access_token, path, json={"context_uri": context_uri} if context_uri else {})
    if resp.status_code not in (200, 204):
        logger.warning("Spotify start playback failed: %s %s", resp.status_code, resp.text)
        return False
    return True


def pause_playback(access_token: str) -> bool:
    """PUT /me/player/pause — pause playback."""
    resp = _api_put(access_token, "/me/player/pause")
    if resp.status_code not in (200, 204):
        logger.warning("Spotify pause failed: %s %s", resp.status_code, resp.text)
        return False
    return True


def pause_now() -> bool:
    """Get access token and pause playback. Returns True if paused successfully."""
    token = _get_access_token()
    if not token:
        return False
    return pause_playback(token)


def play_alarm_on_pi(playlist_uri: Optional[str] = None) -> bool:
    """
    Get access token, find SoundMaker device, transfer playback and start playlist.
    Returns True if playback was started successfully.
    """
    token = _get_access_token()
    if not token:
        logger.warning("Alarm: no Spotify access token")
        return False
    device_id = find_soundmaker_device_id(token)
    if not device_id:
        logger.warning("Alarm: SoundMaker device not found (is raspotify running?)")
        return False
    if not transfer_playback(token, device_id, play=True):
        return False
    if playlist_uri:
        if not start_playback(token, device_id=device_id, context_uri=playlist_uri):
            return False
    return True
