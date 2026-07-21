"""
SoundMaker — Master backend entry point.

Run locally with:
    SOUNDMAKER_STATE_DIR=./state uvicorn main:app --reload --port 8000
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Body, Cookie, Depends, FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from pydantic import BaseModel

import pihole_api
from alarm_manager import get_alarm, set_alarm, start_scheduler, stop_scheduler
from auth import (
    SESSION_TTL,
    check_rate_limit,
    create_session,
    get_password_hash,
    require_auth,
    revoke_session,
    validate_session,
    verify_password,
)
from state_manager import STATE_DIR, load
from system_info import get_system_info
from update_manager import (
    check_for_updates,
    get_current_version,
    get_last_updated_at,
    get_progress,
    start_apply,
)
import spotify_auth
import jellyfin_manager
import power_manager
import metrics_history
import system_logs

logger = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    start_scheduler()
    power_manager.start_scheduler()
    metrics_history.start_sampler()
    try:
        yield
    finally:
        metrics_history.stop_sampler()
        power_manager.stop_scheduler()
        stop_scheduler()
        await pihole_api.close()


app = FastAPI(title="SoundMaker", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    password: str


@app.post("/api/auth/login")
async def auth_login(body: LoginRequest, request: Request):
    check_rate_limit(request.client.host)

    pw_hash = get_password_hash()
    if not pw_hash:
        return JSONResponse({"error": "Password not configured on server"}, status_code=500)

    if not verify_password(body.password, pw_hash):
        return JSONResponse({"error": "Invalid password"}, status_code=401)

    token = create_session()
    response = JSONResponse({"ok": True})
    response.set_cookie(
        key="session",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=SESSION_TTL,
        path="/",
    )
    return response


@app.post("/api/auth/logout")
async def auth_logout(session: Optional[str] = Cookie(None)):
    revoke_session(session)
    response = JSONResponse({"ok": True})
    response.delete_cookie(key="session", path="/")
    return response


@app.get("/api/auth/check")
async def auth_check(session: Optional[str] = Cookie(None)):
    return {"authenticated": validate_session(session)}


# ---------------------------------------------------------------------------
# Health / status (public)
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Config (protected)
# ---------------------------------------------------------------------------

@app.get("/api/config", dependencies=[Depends(require_auth)])
async def get_config():
    return load("config.json")


# ---------------------------------------------------------------------------
# Pi-hole (protected)
# ---------------------------------------------------------------------------

@app.get("/api/pihole/status", dependencies=[Depends(require_auth)])
async def pihole_status():
    """Combined blocking status + stats for the UI."""
    return await pihole_api.get_status()


@app.post("/api/pihole/enable", dependencies=[Depends(require_auth)])
async def pihole_enable():
    try:
        return await pihole_api.set_blocking(True)
    except Exception as exc:
        logger.warning("Pi-hole enable failed: %s", exc)
        return JSONResponse({"error": "Pi-hole unreachable"}, status_code=502)


@app.post("/api/pihole/disable", dependencies=[Depends(require_auth)])
async def pihole_disable(timer: Optional[int] = None):
    """Disable blocking. Optional query param ?timer=300 for temporary disable (seconds)."""
    try:
        return await pihole_api.set_blocking(False, timer=timer)
    except Exception as exc:
        logger.warning("Pi-hole disable failed: %s", exc)
        return JSONResponse({"error": "Pi-hole unreachable"}, status_code=502)


# ---------------------------------------------------------------------------
# System info (protected, read-only dashboard)
# ---------------------------------------------------------------------------

@app.get("/api/system/info", dependencies=[Depends(require_auth)])
def system_info():
    """Master device system information for the System tab (CPU, memory, temp, storage, network, OS, app)."""
    return get_system_info()


@app.get("/api/system/metrics-history", dependencies=[Depends(require_auth)])
def system_metrics_history():
    """Rolling 24h history of CPU temperature, CPU load, and memory use (for the System tab graph)."""
    return metrics_history.get_history()


@app.get("/api/system/logs/services", dependencies=[Depends(require_auth)])
def system_logs_services():
    """List the services whose logs can be viewed."""
    return {"services": system_logs.available_services()}


@app.get("/api/system/logs", dependencies=[Depends(require_auth)])
def system_logs_get(service: str = "backend", lines: int = 100):
    """Recent journal log entries for a whitelisted service."""
    return system_logs.get_logs(service, lines)


# ---------------------------------------------------------------------------
# Power controls (protected): restart backend, reboot Pi, weekly auto-reboot
# ---------------------------------------------------------------------------

@app.post("/api/system/restart-service", dependencies=[Depends(require_auth)])
def system_restart_service():
    """Restart the SoundMaker backend service (no SSH needed)."""
    if not power_manager.restart_backend():
        return JSONResponse({"error": "Could not restart backend"}, status_code=500)
    return {"ok": True, "message": "Backend restarting…"}


@app.post("/api/system/reboot", dependencies=[Depends(require_auth)])
def system_reboot():
    """Reboot the whole Raspberry Pi."""
    if not power_manager.reboot():
        return JSONResponse({"error": "Could not reboot"}, status_code=500)
    return {"ok": True, "message": "Rebooting…"}


@app.get("/api/system/auto-reboot", dependencies=[Depends(require_auth)])
def system_auto_reboot_get():
    """Current scheduled weekly reboot config: enabled, day, time."""
    return power_manager.get_auto_reboot()


class AutoRebootUpdate(BaseModel):
    enabled: bool = False
    day: str = "sun"
    time: str = "04:30"


@app.put("/api/system/auto-reboot", dependencies=[Depends(require_auth)])
def system_auto_reboot_put(body: AutoRebootUpdate):
    """Set the scheduled weekly reboot (day + time, on/off)."""
    return power_manager.set_auto_reboot(body.enabled, body.day, body.time)


# ---------------------------------------------------------------------------
# Updates (protected)
# ---------------------------------------------------------------------------

@app.get("/api/updates/status", dependencies=[Depends(require_auth)])
async def updates_status():
    """Current version and last update time for the UI."""
    return {
        "current_version": get_current_version(),
        "last_updated_at": get_last_updated_at(),
    }


@app.post("/api/updates/check", dependencies=[Depends(require_auth)])
async def updates_check():
    """Check if a newer version exists on the remote. Does not modify the system."""
    return check_for_updates()


@app.post("/api/updates/apply", dependencies=[Depends(require_auth)])
async def updates_apply():
    """Start the update process (runs in background). Returns immediately."""
    result = start_apply()
    if not result["ok"]:
        return JSONResponse({"error": result["error"]}, status_code=409)
    return {"ok": True}


@app.get("/api/updates/progress", dependencies=[Depends(require_auth)])
async def updates_progress():
    """Real-time progress: status, log lines, and result message."""
    return get_progress()


# ---------------------------------------------------------------------------
# Alarm / Morning wake-up (protected except callback)
# ---------------------------------------------------------------------------

@app.get("/api/alarm", dependencies=[Depends(require_auth)])
def alarm_get():
    """Current alarm config: enabled, time (HH:MM), playlist_uri."""
    return get_alarm()


class AlarmUpdate(BaseModel):
    enabled: bool = False
    time: str = "07:00"
    days: Optional[list[str]] = None
    playlist_uri: Optional[str] = None


@app.put("/api/alarm", dependencies=[Depends(require_auth)])
def alarm_put(body: AlarmUpdate):
    """Update alarm: enabled, time (HH:MM), days (list), playlist_uri (optional)."""
    return set_alarm(body.enabled, body.time, body.days, body.playlist_uri)


def _redirect_uri(request: Request) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}/api/spotify/callback"


@app.get("/api/spotify/auth-url", dependencies=[Depends(require_auth)])
def spotify_auth_url(request: Request):
    """Return Spotify OAuth URL for the user to open. Redirect URI is derived from request."""
    if not spotify_auth.is_configured():
        return JSONResponse({"error": "Spotify not configured (missing client ID/secret)"}, status_code=503)
    url = spotify_auth.get_auth_url(_redirect_uri(request))
    if not url:
        return JSONResponse({"error": "Spotify not configured"}, status_code=503)
    return {"url": url}


@app.get("/api/spotify/callback")
async def spotify_callback(request: Request, code: Optional[str] = None, error: Optional[str] = None):
    """
    OAuth callback from Spotify. No auth required (user arrives from Spotify with ?code=...).
    Exchanges code for tokens, saves refresh_token, then redirects to frontend with ?spotify=ok.
    """
    if error:
        logger.warning("Spotify OAuth error: %s", error)
        base = str(request.base_url).rstrip("/")
        return JSONResponse(status_code=400, content={"error": f"Spotify auth failed: {error}"})
    if not code:
        return JSONResponse({"error": "Missing code"}, status_code=400)
    redirect_uri = _redirect_uri(request)
    try:
        spotify_auth.exchange_code_for_tokens(code, redirect_uri)
    except Exception as exc:
        logger.exception("Spotify token exchange failed: %s", exc)
        return JSONResponse({"error": "Token exchange failed"}, status_code=502)
    base = str(request.base_url).rstrip("/")
    return RedirectResponse(url=f"{base}/?spotify=connected", status_code=302)


@app.get("/api/spotify/status", dependencies=[Depends(require_auth)])
def spotify_status():
    """Whether Spotify is configured and connected (has refresh token)."""
    return {
        "configured": spotify_auth.is_configured(),
        "connected": spotify_auth.is_connected(),
    }


@app.get("/api/spotify/playlists", dependencies=[Depends(require_auth)])
def spotify_playlists():
    """Return the user's Spotify playlists (name, uri, image, track count)."""
    if not spotify_auth.is_connected():
        return JSONResponse({"error": "Spotify not connected"}, status_code=400)
    playlists = spotify_auth.fetch_playlists()
    return {"playlists": playlists}


class PlayNowRequest(BaseModel):
    playlist_uri: Optional[str] = None


@app.post("/api/spotify/play-now", dependencies=[Depends(require_auth)])
def spotify_play_now(body: Optional[PlayNowRequest] = Body(None)):
    """Start playback on SoundMaker device now (optional playlist_uri in body)."""
    if not spotify_auth.is_connected():
        return JSONResponse({"error": "Spotify not connected"}, status_code=400)
    playlist_uri = body.playlist_uri if body else None
    ok = spotify_auth.play_alarm_on_pi(playlist_uri=playlist_uri)
    if not ok:
        return JSONResponse({"error": "Could not start playback"}, status_code=502)
    return {"ok": True}


@app.post("/api/spotify/pause", dependencies=[Depends(require_auth)])
def spotify_pause():
    """Pause current Spotify playback."""
    if not spotify_auth.is_connected():
        return JSONResponse({"error": "Spotify not connected"}, status_code=400)
    ok = spotify_auth.pause_now()
    if not ok:
        return JSONResponse({"error": "Could not pause"}, status_code=502)
    return {"ok": True}


@app.post("/api/spotify/disconnect", dependencies=[Depends(require_auth)])
def spotify_disconnect():
    """Remove stored Spotify refresh token."""
    spotify_auth.disconnect()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Jellyfin media server (protected, read-only status)
# ---------------------------------------------------------------------------

@app.get("/api/jellyfin/status", dependencies=[Depends(require_auth)])
def jellyfin_status():
    """Jellyfin service status and URL for the UI."""
    return jellyfin_manager.get_status()


# ---------------------------------------------------------------------------
# Static frontend (only mounted if the build exists)
# ---------------------------------------------------------------------------

class SPAStaticFiles(StaticFiles):
    """Serve built frontend, but tell clients never to cache the HTML shell.

    The hashed JS/CSS under assets/ are safe to cache forever (their filenames
    change every build). index.html must NOT be cached, or an installed
    "Add to Home Screen" web app on iOS keeps launching a stale shell that
    references old asset hashes and never picks up an update. `no-cache` forces
    a cheap revalidation on every launch so new builds show up automatically.
    """

    async def get_response(self, path: str, scope) -> Response:
        response = await super().get_response(path, scope)
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("text/html"):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


if FRONTEND_DIR.is_dir():
    app.mount("/", SPAStaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
